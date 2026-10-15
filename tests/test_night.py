from datetime import datetime

from panel import night as N


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def at(hhmm):
    h, m = map(int, hhmm.split(":"))
    return lambda: datetime(2026, 10, 15, h, m)


def test_window_parsing_and_wrap():
    w = N.parse_window("21:00-07:00")
    assert N.in_window(w, at("23:30")())
    assert N.in_window(w, at("06:59")())
    assert not N.in_window(w, at("07:00")())
    assert not N.in_window(w, at("12:00")())
    day = N.parse_window("09:00-17:00")
    assert N.in_window(day, at("09:00")())
    assert not N.in_window(day, at("17:00")())
    assert N.parse_window("") is None
    assert not N.in_window(None, at("23:00")())


def test_day_is_full_and_taps_pass_through():
    night = N.Night("21:00-07:00", 0.08, 1.0, 60, now=at("12:00"), clock=Clock())
    assert night.level == 1.0
    assert night.tap() is False


def test_night_is_dark_first_tap_wakes_dimmed_then_sleeps():
    clock = Clock()
    night = N.Night("21:00-07:00", 0.08, 1.0, 60, now=at("23:00"), clock=clock)
    assert night.dark and night.level == 0
    assert night.tap() is True       # only woke it
    assert night.level == 0.08
    clock.t += 30
    assert night.tap() is False      # a real press, and it extends the wake
    clock.t += 59
    assert not night.dark
    clock.t += 1
    assert night.dark


def test_backlight_writes_levels(tmp_path):
    dev = tmp_path / "10-0045"
    dev.mkdir()
    (dev / "max_brightness").write_text("255\n")
    (dev / "brightness").write_text("255\n")
    bl = N.Backlight(tmp_path)
    bl.set(0.08)
    assert (dev / "brightness").read_text() == "20"
    bl.set(0.001)
    assert (dev / "brightness").read_text() == "1"  # lit, however dim
    bl.set(0)
    assert (dev / "brightness").read_text() == "0"


def test_no_backlight_is_harmless(tmp_path):
    bl = N.Backlight(tmp_path)
    bl.set(0.5)
    assert bl.path is None


def test_unwritable_backlight_warns_once(tmp_path, caplog):
    dev = tmp_path / "10-0045"
    dev.mkdir()
    (dev / "max_brightness").write_text("255\n")
    (dev / "brightness").mkdir()  # writing to a directory fails like EACCES would
    bl = N.Backlight(tmp_path)
    for level in (0.5, 0.2, 0.1):
        bl.set(level)
    assert bl.path is None
    assert len([r for r in caplog.records if "not writable" in r.message]) == 1
