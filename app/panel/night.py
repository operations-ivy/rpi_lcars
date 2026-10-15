"""Night and the backlight: dark and silent overnight, woken (dimmed) by a tap
for a while. The first tap on a dark screen only wakes it, so nothing is
pressed by accident. The backlight is /sys/class/backlight, writable by the
video group (brick1982's udev rule)."""
import logging
import time
from datetime import datetime, time as dtime
from pathlib import Path

log = logging.getLogger(__name__)


def parse_window(text):
    """"HH:MM-HH:MM" (may wrap past midnight), or empty for never."""
    text = (text or "").strip()
    if not text:
        return None
    start, end = (dtime.fromisoformat(t.strip()) for t in text.split("-"))
    return start, end


def in_window(window, at):
    if window is None:
        return False
    start, end = window
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
                 now=datetime.now, clock=time.monotonic):
        self.window = parse_window(window)
        self.night_level, self.day_level = night_level, day_level
        self.wake_seconds = wake_seconds
        self.backlight = backlight
        self.now, self.clock = now, clock
        self._awake_until = 0.0

    @property
    def is_night(self):
        return in_window(self.window, self.now())

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
