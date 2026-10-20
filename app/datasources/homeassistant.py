"""Home Assistant's REST API, from a background thread so a slow or missing
Home Assistant never freezes the screen. The screens read the latest states
(state()), a to-do list's items (items()) and entity pictures (picture()), and
queue service calls (call()); the thread does the talking."""
import json
import logging
import queue
import re
import threading
import time
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

# Picture URLs carry an access token that changes every few minutes; the
# picture itself changes far less often.
_TOKEN = re.compile(r"[?&]token=[^&]*")


class HomeAssistant(threading.Thread):
    def __init__(self, url, token, entities, poll_seconds=5, metrics=None,
                 opener=urllib.request.urlopen, clock=time.monotonic,
                 todo=None, todo_seconds=30, pictures=()):
        super().__init__(name="homeassistant", daemon=True)
        self.url, self.token = url.rstrip("/"), token
        self.todo, self.todo_seconds = todo, todo_seconds
        self.pictures = list(pictures)
        self.entities = list(dict.fromkeys(list(entities) + self.pictures + ([todo] if todo else [])))
        self.poll_seconds = poll_seconds
        self.metrics = metrics
        self.opener, self.clock = opener, clock
        self._states = {}
        self._items = None  # the to-do list's items, once fetched
        self._next_items = 0.0
        self._pictures = {}  # entity -> (key, bytes)
        self._lock = threading.Lock()
        self._calls = queue.Queue()
        self._stop = threading.Event()
        self.connected = False
        self.error = "" if token else "NO TOKEN"
        self.unit = "°F"
        self.last_call = None  # (time.time(), service) of the last call that worked
        if metrics:
            metrics.set("lcars_ha_up", 0)  # down until a poll answers, or forever without a token

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

    def items(self):
        """The to-do list's items ({"summary", "uid", "status"}), or None
        before the first fetch."""
        with self._lock:
            return None if self._items is None else [dict(i) for i in self._items]

    def set_item_status(self, uid, status):
        """Show a change at once, before Home Assistant confirms it."""
        with self._lock:
            for item in self._items or []:
                if item.get("uid") == uid:
                    item["status"] = status

    def picture(self, entity_id):
        """The entity's picture as image bytes (JPEG or PNG), or None."""
        with self._lock:
            entry = self._pictures.get(entity_id)
        return entry[1] if entry else None

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

    def _request(self, method, path, body=None, raw=False):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        with self.opener(req, timeout=10) as r:
            body = r.read()
            return body if raw else json.loads(body or b"null")

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
        if ok:
            self._fetch_items()
            for entity in self.pictures:
                self._fetch_picture(entity)

    def _fetch_items(self):
        if not self.todo or self.clock() < self._next_items:
            return
        self._next_items = self.clock() + self.todo_seconds
        try:
            answer = self._request("POST", "/api/services/todo/get_items?return_response",
                                   {"entity_id": self.todo})
            items = answer["service_response"][self.todo]["items"]
            self._count("items", "ok")
        except Exception as e:  # noqa: BLE001 - the list keeps its last items
            self._count("items", "error")
            log.warning("todo items %s: %s", self.todo, e)
            return
        with self._lock:
            self._items = items

    def _fetch_picture(self, entity):
        s = self.state(entity)
        url = (s or {}).get("attributes", {}).get("entity_picture")
        if not url:
            with self._lock:
                self._pictures.pop(entity, None)
            return
        key = (s["state"], _TOKEN.sub("", url))
        with self._lock:
            if self._pictures.get(entity, (None,))[0] == key:
                return
        try:
            data = self._request("GET", url if url.startswith("/") else "/" + url, raw=True)
            self._count("picture", "ok")
        except Exception as e:  # noqa: BLE001
            # Home Assistant may have nothing to show (a console that's off
            # answers 500): no picture until the entity changes, not a retry
            # every poll.
            self._count("picture", "error")
            log.warning("picture %s: %s", entity, e)
            data = None
        with self._lock:
            self._pictures[entity] = (key, data)

    def _call(self, domain, service, data):
        try:
            self._request("POST", f"/api/services/{domain}/{service}", data)
            self.last_call = (time.time(), f"{domain}.{service}")
            self._count("call", "ok")
            if domain == "todo":
                self._next_items = 0.0  # fetch the list again with the next poll
        except Exception as e:  # noqa: BLE001
            self._count("call", "error")
            self.error = "COMMAND FAILED"
            log.warning("%s.%s %s: %s", domain, service, data, e)
