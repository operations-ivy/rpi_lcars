"""Home Assistant's REST API, from a background thread so a slow or missing
Home Assistant never freezes the screen. The screens read the latest states
(state()) and queue service calls (call()); the thread does the talking."""
import json
import logging
import queue
import threading
import time
import urllib.error
import urllib.request

log = logging.getLogger(__name__)


class HomeAssistant(threading.Thread):
    def __init__(self, url, token, entities, poll_seconds=5, metrics=None,
                 opener=urllib.request.urlopen, clock=time.monotonic):
        super().__init__(name="homeassistant", daemon=True)
        self.url, self.token = url.rstrip("/"), token
        self.entities = list(entities)
        self.poll_seconds = poll_seconds
        self.metrics = metrics
        self.opener, self.clock = opener, clock
        self._states = {}
        self._lock = threading.Lock()
        self._calls = queue.Queue()
        self._stop = threading.Event()
        self.connected = False
        self.error = "" if token else "NO TOKEN"
        self.unit = "°F"
        self.last_call = None  # (time.time(), service) of the last call that worked

    # The screens' side.

    def state(self, entity_id):
        with self._lock:
            return self._states.get(entity_id)

    def attrs(self, entity_id):
        s = self.state(entity_id)
        return dict(s["attributes"]) if s else {}

    def value(self, entity_id, default=None):
        s = self.state(entity_id)
        return s["state"] if s and s["state"] not in ("unknown", "unavailable") else default

    def number(self, entity_id, default):
        try:
            return float(self.value(entity_id))
        except (TypeError, ValueError):
            return default

    def call(self, domain, service, **data):
        self._calls.put((domain, service, data))

    def stop(self):
        self._stop.set()
        self._calls.put(None)

    # The thread's side.

    def run(self):
        if not self.token:
            return
        self._fetch_config()
        next_poll = 0.0
        while not self._stop.is_set():
            if self.clock() >= next_poll:
                self.poll()
                next_poll = self.clock() + self.poll_seconds
            try:
                item = self._calls.get(timeout=max(0.0, next_poll - self.clock()))
            except queue.Empty:
                continue
            if item is None:
                break
            self._call(*item)
            next_poll = 0.0  # show the result now

    def _request(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        with self.opener(req, timeout=10) as r:
            return json.loads(r.read() or b"null")

    def _count(self, kind, result):
        if self.metrics:
            self.metrics.inc("lcars_ha_requests_total", kind=kind, result=result)

    def _fetch_config(self):
        try:
            unit = self._request("GET", "/api/config")["unit_system"]["temperature"]
            self.unit = unit if unit.startswith("°") else f"°{unit}"
        except Exception as e:  # noqa: BLE001 - shown as NO SIGNAL; retried by poll
            log.warning("config: %s", e)

    def poll(self):
        states, ok = {}, True
        for entity in self.entities:
            try:
                states[entity] = self._request("GET", f"/api/states/{entity}")
                self._count("state", "ok")
            except urllib.error.HTTPError as e:
                self._count("state", str(e.code))
                if e.code == 404:  # not there (yet): not a lost link
                    continue
                ok, self.error = False, f"HTTP {e.code}"
                break
            except Exception as e:  # noqa: BLE001
                self._count("state", "error")
                ok, self.error = False, "NO SIGNAL"
                log.warning("poll %s: %s", entity, e)
                break
        if ok:
            with self._lock:
                self._states.update(states)
            self.error = ""
        self.connected = ok
        if self.metrics:
            self.metrics.set("lcars_ha_up", 1 if ok else 0)

    def _call(self, domain, service, data):
        try:
            self._request("POST", f"/api/services/{domain}/{service}", data)
            self.last_call = (time.time(), f"{domain}.{service}")
            self._count("call", "ok")
        except Exception as e:  # noqa: BLE001
            self._count("call", "error")
            self.error = "COMMAND FAILED"
            log.warning("%s.%s %s: %s", domain, service, data, e)
