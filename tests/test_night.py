from datetime import datetime, timezone

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


def test_sun_ends_follow_home_assistant_then_fall_back():
    w = N.parse_window("sunset-sunrise")
    sun = {"sunset": N.dtime(18, 24), "sunrise": N.dtime(7, 23)}
    assert N.in_window(w, at("18:24")(), sun)
    assert N.in_window(w, at("07:22")(), sun)
    assert not N.in_window(w, at("07:23")(), sun)
    assert not N.in_window(w, at("18:00")(), sun)
    # Before Home Assistant answers: 19:00 to 07:00.
    assert not N.in_window(w, at("18:30")())
    assert N.in_window(w, at("19:00")())
    mixed = N.parse_window("21:00-Sunrise")
    assert N.in_window(mixed, at("07:00")(), sun)
    assert not N.in_window(mixed, at("20:59")(), sun)


def test_sun_times_from_home_assistant():
    setting = datetime(2026, 10, 21, 18, 24, 3).astimezone()   # local, whatever the zone
    rising = datetime(2026, 10, 21, 7, 23, 51).astimezone()
    times = N.sun_times({"next_setting": setting.astimezone(timezone.utc).isoformat(),
                         "next_rising": rising.astimezone(timezone.utc).isoformat()})
    assert times == {"sunset": N.dtime(18, 24), "sunrise": N.dtime(7, 23)}
    assert N.sun_times({}) == {}
    assert N.sun_times({"next_setting": None}) == {}


def test_night_reads_the_sun_each_time():
    sun = {"sunset": N.dtime(18, 0), "sunrise": N.dtime(7, 0)}
    night = N.Night("sunset-sunrise", 0.08, 1.0, 60, now=at("18:30"), clock=Clock(), sun=lambda: sun)
    assert night.is_night
    sun["sunset"] = N.dtime(19, 0)
    assert not night.is_night
