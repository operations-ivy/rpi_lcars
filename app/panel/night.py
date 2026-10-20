"""Night and the backlight: dark and silent overnight, woken (dimmed) by a tap
for a while. The first tap on a dark screen only wakes it, so nothing is
pressed by accident. The backlight is /sys/class/backlight, writable by the
video group (brick1982's udev rule).
Either end of the night can be "sunset" or "sunrise", from Home Assistant's
sun.sun; until Home Assistant has answered, those are FALLBACK."""
import logging
import time
from datetime import datetime, time as dtime
from pathlib import Path

log = logging.getLogger(__name__)

SUN_EVENTS = {"sunset": "next_setting", "sunrise": "next_rising"}
FALLBACK = {"sunset": dtime(19, 0), "sunrise": dtime(7, 0)}


def parse_window(text):
    """"HH:MM-HH:MM" (may wrap past midnight; either end may be "sunset" or
    "sunrise"), or empty for never."""
    text = (text or "").strip()
    if not text:
        return None
    ends = [t.strip().lower() for t in text.split("-")]
    return tuple(t if t in SUN_EVENTS else dtime.fromisoformat(t) for t in ends)


def sun_times(attrs):
    """{"sunset": time, "sunrise": time} (local) from sun.sun's attributes;
    either is missing when Home Assistant hasn't said."""
    out = {}
    for name, attr in SUN_EVENTS.items():
        try:
            out[name] = datetime.fromisoformat(attrs[attr]).astimezone().time().replace(second=0, microsecond=0)
        except (KeyError, TypeError, ValueError):
            pass
    return out


def in_window(window, at, sun=None):
    if window is None:
        return False
    sun = sun or {}
    start, end = (sun.get(t, FALLBACK[t]) if isinstance(t, str) else t for t in window)
    t = at.time()
    return start <= t < end if start <= end else t >= start or t < end


class Backlight:
    def __init__(self, root="/sys/class/backlight"):
        devices = sorted(Path(root).glob("*/brightness"))
        self.path = devices[0] if devices else None
        self.max = int((self.path.parent / "max_brightness").read_text()) if self.path else 0
        self.level = None

    def set(self, fraction):
        """0 is off; anything else is at least the lowest lit level."""
        level = 0 if fraction <= 0 else max(1, round(self.max * fraction))
        if self.path is None or level == self.level:
            return
        try:
            self.path.write_text(str(level))
            self.level = level
        except OSError as e:
            # Once is enough: stop trying rather than warn every frame.
            log.warning("backlight %s not writable, leaving it alone: %s", self.path, e)
            self.path = None


class Night:
    def __init__(self, window, night_level, day_level, wake_seconds, backlight=None,
                 now=datetime.now, clock=time.monotonic, sun=dict):
        self.window = parse_window(window)
        self.night_level, self.day_level = night_level, day_level
        self.wake_seconds = wake_seconds
        self.backlight = backlight
        self.now, self.clock = now, clock
        self.sun = sun  # () -> sun_times(...)
        self._awake_until = 0.0

    @property
    def is_night(self):
        return in_window(self.window, self.now(), self.sun())

    @property
    def dark(self):
        return self.is_night and self.clock() >= self._awake_until

    @property
    def level(self):
        if not self.is_night:
            return self.day_level
        return 0.0 if self.dark else self.night_level

    def tap(self):
        """A touch. True when it only woke the screen (swallow it)."""
        was_dark = self.dark
        if self.is_night:
            self._awake_until = self.clock() + self.wake_seconds
        return was_dark

    def apply(self):
        if self.backlight is not None:
            self.backlight.set(self.level)
