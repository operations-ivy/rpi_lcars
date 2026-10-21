"""Prometheus metrics on a small HTTP server: counters and gauges with labels,
nothing more. Other read-only JSON documents (the room sensor's, for Home
Assistant) can be served beside them."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HELP = {
    "lcars_ha_up": ("gauge", "1 while Home Assistant answers the panel's polls."),
    "lcars_ha_requests_total": ("counter", "Requests to Home Assistant, by kind (state, items, picture, call) and result."),
    "lcars_unlock_attempts_total": ("counter", "Codes entered, by result (granted, denied, locked_out, hard_locked, no_code)."),
    "lcars_relocks_total": ("counter", "Times the panel locked itself, by reason (idle, dark, hard_locked)."),
    "lcars_commands_total": ("counter", "Changes sent to Home Assistant, by action."),
    "lcars_taps_total": ("counter", "Touches, by whether they only woke the screen."),
    "lcars_screen": ("gauge", "1 for the screen being shown, by screen."),
    "lcars_backlight_level": ("gauge", "Backlight, as a fraction of full (0 is dark)."),
    "lcars_can_change": ("gauge", "1 while climate control is open (unlocked)."),
    "lcars_frame_seconds": ("gauge", "Time the last frame took to draw."),
    "lcars_room_sensor_up": ("gauge", "1 while the room sensor (SHT3x) answers."),
    "lcars_room_reads_total": ("counter", "Room sensor reads, by result."),
    "lcars_room_temperature_fahrenheit": ("gauge", "The room's temperature, offset applied."),
    "lcars_room_humidity_percent": ("gauge", "The room's relative humidity."),
    "lcars_feed_up": ("gauge", "1 while the homelab feed answers, by feed (prometheus, overwatch, wigle)."),
    "lcars_feed_requests_total": ("counter", "Requests to the homelab feeds, by feed and result."),
    "lcars_weather_up": ("gauge", "1 while a weather source answers."),
    "lcars_weather_source": ("gauge", "1 for the weather source the data shown came from, by source."),
    "lcars_weather_requests_total": ("counter", "Requests to weather services, by source, kind and result."),
    "lcars_weather_alerts": ("gauge", "Active weather alerts (-1: unknown, the National Weather Service didn't answer)."),
    "lcars_weather_last_update_timestamp_seconds": ("gauge", "When the weather shown was fetched."),
    "lcars_weather_temperature_fahrenheit": ("gauge", "Outside temperature, from the weather source."),
}


def _labels(labels):
    if not labels:
        return ""
    return "{" + ",".join(f'{k}="{v}"' for k, v in sorted(labels)) + "}"


# Every label value the code can count, shown as 0 from the start: a counter
# that only appears on its first event reads as "no data", not zero.
KNOWN = {
    "lcars_unlock_attempts_total": ("result", ("granted", "denied", "locked_out", "hard_locked", "no_code")),
    "lcars_relocks_total": ("reason", ("idle", "dark", "hard_locked", "button")),
    "lcars_commands_total": ("action", ("set_temperature", "set_hvac_mode", "shopping_item")),
    "lcars_taps_total": ("woke", ("true", "false")),
}


class Metrics:
    def __init__(self):
        self._values = {}
        self._lock = threading.Lock()
        for name, (label, values) in KNOWN.items():
            for value in values:
                self.inc(name, 0, **{label: value})

    def inc(self, name, amount=1, **labels):
        key = (name, tuple(sorted(labels.items())))
        with self._lock:
            self._values[key] = self._values.get(key, 0) + amount

    def set(self, name, value, **labels):
        with self._lock:
            self._values[(name, tuple(sorted(labels.items())))] = value

    def get(self, name, **labels):
        return self._values.get((name, tuple(sorted(labels.items()))), 0)

    def render(self):
        with self._lock:
            items = sorted(self._values.items())
        out, seen = [], set()
        for (name, labels), value in items:
            if name not in seen:
                kind, text = HELP.get(name, ("untyped", name))
                out += [f"# HELP {name} {text}", f"# TYPE {name} {kind}"]
                seen.add(name)
            out.append(f"{name}{_labels(labels)} {value}")
        return "\n".join(out) + "\n"

    def serve(self, port, host="0.0.0.0", documents=None):
        """documents: {path: () -> dict}, served as JSON."""
        metrics, documents = self, documents or {}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path in documents:
                    body, kind, code = json.dumps(documents[self.path]()).encode(), "application/json", 200
                else:
                    body = metrics.render().encode() if self.path == "/metrics" else b"lcars\n"
                    kind, code = "text/plain; version=0.0.4", 200 if self.path in ("/metrics", "/") else 404
                self.send_response(code)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer((host, port), Handler)
        threading.Thread(target=server.serve_forever, name="metrics", daemon=True).start()
        return server
