"""JSON from the homelab's own pages, each polled from a background thread so
a slow one never freezes the screen: Prometheus' firing alerts, overwatch's
state and wigle-console's status. A feed keeps its last answer while its
source is down; the screens show how old it is."""
import json
import logging
import threading
import time
import urllib.request

log = logging.getLogger(__name__)


class JsonFeed(threading.Thread):
    def __init__(self, name, url, poll_seconds, metrics=None, opener=urllib.request.urlopen,
                 timeout=30, now=time.time):
        super().__init__(name=f"feed-{name}", daemon=True)
        self.feed, self.url, self.poll_seconds = name, url, poll_seconds
        self.metrics, self.opener, self.timeout, self.now = metrics, opener, timeout, now
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._data = None
        self.updated = None  # time.time() of the last answer
        self.error = ""
        self._warned = False
        if metrics:
            metrics.set("lcars_feed_up", 0, feed=name)

    @property
    def data(self):
        with self._lock:
            return self._data

    def age(self):
        return None if self.updated is None else self.now() - self.updated

    def poll(self):
        try:
            req = urllib.request.Request(self.url, headers={"Accept": "application/json"})
            with self.opener(req, timeout=self.timeout) as r:
                data = json.loads(r.read())
        except Exception as e:  # noqa: BLE001 - shown as offline, tried again next poll
            self.error = "OFFLINE"
            if not self._warned:  # once, not every poll while it's down
                log.warning("feed %s: %s", self.feed, e)
                self._warned = True
            if self.metrics:
                self.metrics.set("lcars_feed_up", 0, feed=self.feed)
                self.metrics.inc("lcars_feed_requests_total", feed=self.feed, result="error")
            return False
        with self._lock:
            self._data = data
        self.updated, self.error, self._warned = self.now(), "", False
        if self.metrics:
            self.metrics.set("lcars_feed_up", 1, feed=self.feed)
            self.metrics.inc("lcars_feed_requests_total", feed=self.feed, result="ok")
        return True

    def run(self):
        while not self._stop.is_set():
            self.poll()
            self._stop.wait(self.poll_seconds)

    def stop(self):
        self._stop.set()
