"""The calendar: Home Assistant's calendar API through the panel's client,
the month, day and event views of the CALENDAR screen, and today's and
tomorrow's events on STATUS. Every event here is made up: real titles never
go in this public repo."""
import io
import json
import urllib.error
import urllib.parse
from datetime import date, datetime
from zoneinfo import ZoneInfo

import config
from datasources import calendar as cal
from datasources.homeassistant import HomeAssistant
from metrics import Metrics

NY = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 21, 14, 20, tzinfo=NY)  # a Wednesday afternoon


def timed(summary, start, end, **more):
    return {"summary": summary, "start": {"dateTime": start}, "end": {"dateTime": end}, **more}


def all_day(summary, start, end):
    return {"summary": summary, "start": {"date": start}, "end": {"date": end}}


RAW = {
    "calendar.family": [
        timed("Dentist", "2026-10-21T14:30:00-04:00", "2026-10-21T15:15:00-04:00",        # in 10 minutes
              location="12 Main St", description="<p>Bring the <b>forms</b></p><br>Ask about x &amp; y"),
        timed("Standup", "2026-10-21T18:00:00Z", "2026-10-21T18:30:00Z"),                   # 14:00-14:30: now
        timed("Breakfast", "2026-10-21T08:00:00-04:00", "2026-10-21T09:00:00-04:00"),       # over
        all_day("Bin day", "2026-10-21", "2026-10-22"),
        all_day("Trip", "2026-10-22", "2026-10-25"),                                        # three days
    ],
    "calendar.work": [
        timed("Late shift", "2026-10-22T22:00:00-04:00", "2026-10-23T06:00:00-04:00"),      # over midnight
        timed("Next week", "2026-10-28T09:00:00-04:00", "2026-10-28T10:00:00-04:00"),       # out of range
    ],
}


def events(raw=RAW):
    return [e for entity, items in raw.items() for e in (cal.parse(r, entity, NY) for r in items) if e]


def test_parse_keeps_titles_times_places_and_notes():
    e = cal.parse(RAW["calendar.family"][0], "calendar.family", NY)
    assert set(e) == {"summary", "start", "end", "all_day", "location", "description", "calendar"}
    assert e["start"] == datetime(2026, 10, 21, 14, 30, tzinfo=NY) and not e["all_day"]
    assert e["location"] == "12 Main St"
    assert e["description"] == "Bring the forms\nAsk about x & y"           # Google's HTML made plain
    utc = cal.parse(RAW["calendar.family"][1], "calendar.family", NY)
    assert utc["start"].hour == 14 and utc["start"].tzinfo == NY          # shown in New York time
    assert cal.parse({"summary": "x", "start": {}}, "c", NY) is None
    assert cal.parse(all_day("", "2026-10-21", "2026-10-22"), "c", NY)["summary"] == "BUSY"


def test_agenda_orders_days_and_events():
    days = cal.agenda(events(), NOW, 3)
    assert [d for d, _ in days] == [date(2026, 10, 21), date(2026, 10, 22), date(2026, 10, 23)]
    today = [(e["when"], e["summary"]) for e in days[0][1]]
    assert today == [("ALL DAY", "Bin day"), ("14:00", "Standup"), ("14:30", "Dentist")]   # Breakfast is over
    standup, dentist = days[0][1][1], days[0][1][2]
    assert standup["now"] and not standup["soon"]
    assert dentist["soon"] == 10 and not dentist["now"]
    tomorrow = [(e["when"], e["summary"]) for e in days[1][1]]
    assert tomorrow == [("ALL DAY", "Trip"), ("22:00", "Late shift")]
    friday = [(e["when"], e["summary"]) for e in days[2][1]]
    assert friday == [("ALL DAY", "Trip"), ("UNTIL 06:00", "Late shift")]


def test_on_day_keeps_what_is_over_and_says_so():
    breakfast, = [e for e in cal.on_day(events(), date(2026, 10, 21), NOW) if e["summary"] == "Breakfast"]
    assert breakfast["past"] and breakfast["event"]["summary"] == "Breakfast"
    assert "Breakfast" not in [e["summary"] for e in cal.on_day(events(), date(2026, 10, 21), NOW, past=False)]


def test_month_grid_and_the_window_fetched():
    weeks = cal.grid(2026, 10)
    assert weeks[0][0] == date(2026, 9, 27) and weeks[-1][-1] == date(2026, 10, 31)   # Sunday first
    assert cal.add_months(2026, 12, 1) == (2027, 1) and cal.add_months(2026, 1, -1) == (2025, 12)
    start, end = cal.window(NOW, 2)
    assert (start.date(), end.date()) == (date(2026, 9, 27), date(2026, 12, 6))       # October's grid to November's


def test_when_an_event_is():
    by = {e["summary"]: e for e in events()}
    assert cal.when(by["Dentist"]) == "WEDNESDAY 21 OCTOBER, 14:30 - 15:15"
    assert cal.when(by["Bin day"]) == "WEDNESDAY 21 OCTOBER, ALL DAY"
    assert cal.when(by["Trip"]) == "THU 22 OCT - SAT 24 OCT, ALL DAY"                   # Google's end is the day after
    assert cal.when(by["Late shift"]) == "THU 22 OCT 22:00 - FRI 23 OCT 06:00"


def test_day_names():
    today = NOW.date()
    assert cal.day_name(today, today) == "TODAY"
    assert cal.day_name(date(2026, 10, 22), today) == "TOMORROW"
    assert cal.day_name(date(2026, 10, 23), today) == "FRIDAY 23 OCTOBER"


class FakeCalendars:
    """Stands in for urlopen: the states and calendar endpoints."""

    def __init__(self, raw, fail=()):
        self.raw, self.fail, self.asked = raw, set(fail), []

    def __call__(self, req, timeout):
        path = req.full_url.split("://", 1)[1].split("/", 1)[1]
        if path.startswith("api/calendars/"):
            entity, query = path[len("api/calendars/"):].split("?")
            self.asked.append((entity, urllib.parse.parse_qs(query)))
            if entity in self.fail:
                raise urllib.error.HTTPError(req.full_url, 500, "down", {}, None)
            return io.BytesIO(json.dumps(self.raw[entity]).encode())
        if path.startswith("api/states/"):
            return io.BytesIO(json.dumps({"state": "on", "attributes": {}}).encode())
        return io.BytesIO(b"{}")


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def client(fake, clock, metrics=None):
    return HomeAssistant("http://ha", "tok", ["sun.sun"], metrics=metrics, opener=fake, clock=clock,
                         calendars=list(fake.raw), calendar_seconds=300, now=lambda: NOW)


def test_client_fetches_every_calendar_for_three_days_and_keeps_the_last_answer():
    fake, clock, m = FakeCalendars(RAW), Clock(), Metrics()
    ha = client(fake, clock, m)
    assert ha.events() is None
    ha.poll()
    assert sorted(e["summary"] for e in ha.events()) == sorted(r["summary"] for rs in RAW.values() for r in rs)
    entity, query = fake.asked[0]
    assert query["start"] == ["2026-09-27T04:00:00+00:00"] and query["end"] == ["2026-12-06T05:00:00+00:00"]
    assert m.get("lcars_calendar_up") == 1 and m.get("lcars_calendar_events_today") == 3
    ha.poll()
    assert len(fake.asked) == 2                                   # not again until calendar_seconds pass
    fake.fail.add("calendar.work")
    clock.t += 300
    ha.poll()
    assert len(ha.events()) == 7 and ha.events_age() == 300      # the last events, getting old
    assert m.get("lcars_calendar_up") == 0
    assert m.get("lcars_ha_requests_total", kind="calendar", result="error") == 1


def test_titles_stay_out_of_metrics_and_logs(caplog):
    fake, clock, m = FakeCalendars(RAW, fail={"calendar.work"}), Clock(), Metrics()
    client(fake, clock, m).poll()
    assert "Dentist" not in m.render() and "Dentist" not in caplog.text
    assert "calendar.work" in caplog.text                         # which calendar failed, no more


# The screen.

def rig(monkeypatch, raw=RAW, fail=(), age=0, read_only=False):
    from test_screens import FakeHA, Rig
    monkeypatch.setattr(config, "CALENDARS", list(raw))
    monkeypatch.setattr(config, "CALENDAR_MONTHS", 2)
    monkeypatch.setattr(config, "READ_ONLY", read_only)
    r = Rig()
    fake = FakeCalendars(raw, fail)
    ha = client(fake, Clock())
    ha.poll()
    r.ha._events, r.ha.events_updated = ha.events(), r.ha.clock() - age
    r.ha.now = lambda: NOW
    assert isinstance(r.ha, FakeHA)
    r.tick()
    return r


def cells(r):
    """{day number: [its lines]} for this month's days on the grid."""
    from ui.widgets.panel_widgets import LcarsCell
    out = {}
    for c in r.sprites(LcarsCell):
        number, *rest = [text for text, _, _ in c.lines]
        if c.outline:                                             # this month's (the others have none)
            out[int(number)] = rest
    return out


def cell(r, n):
    from ui.widgets.panel_widgets import LcarsCell
    return [c for c in r.sprites(LcarsCell) if c.outline and c.lines[0][0] == str(n)][0]


def test_calendar_opens_on_this_month(monkeypatch):
    r = rig(monkeypatch)
    r.tap(r.key("CALENDAR"))
    assert r.screen == "calendar"
    assert "OCTOBER 2026" in r.texts() and "SUN" in r.texts() and "SAT" in r.texts()
    days = cells(r)
    assert sorted(days) == list(range(1, 32))
    assert days[21] == ["BIN DAY", "+3 MORE"]                    # two lines fit a five-week month's cells
    assert days[22] == ["TRIP", "LATE SHIFT"] and days[24] == ["TRIP"] and days[20] == []
    assert cell(r, 21).outline == __import__("ui.colours", fromlist=["GOLD"]).GOLD    # today
    assert not r.key("PREV").enabled and r.key("NEXT").enabled
    assert "CALENDAR VIA HOME ASSISTANT" in r.texts()
    r.shot("20-calendar-month")


def test_next_month_and_back(monkeypatch):
    r = rig(monkeypatch)
    r.tap(r.key("CALENDAR"))
    r.tap(r.key("NEXT"))
    assert "NOVEMBER 2026" in r.texts()
    assert not r.key("NEXT").enabled                                # two months fetched
    r.tap(r.key("PREV"))
    assert "OCTOBER 2026" in r.texts()


def test_a_day_then_an_event(monkeypatch):
    r = rig(monkeypatch)
    r.tap(r.key("CALENDAR"))
    r.tap(cell(r, 21))
    assert "TODAY" in r.texts()
    for bar in ("ALL DAY   BIN DAY", "08:00   BREAKFAST", "NOW   STANDUP", "14:30   DENTIST - IN 10 MIN"):
        r.key(bar)
    r.shot("21-calendar-day")
    r.tap(r.key("14:30   DENTIST - IN 10 MIN"))
    texts = r.texts()
    for expected in ("DENTIST", "WHEN", "WEDNESDAY 21 OCTOBER, 14:30 - 15:15", "WHERE", "12 MAIN ST", "NOTES",
                     "Bring the forms", "Ask about x & y"):
        assert expected in texts, expected
    r.shot("22-calendar-event")
    r.tap(r.key("BACK"))
    r.key("NOW   STANDUP")                                            # back to the day
    r.tap(r.key("MONTH"))
    assert "OCTOBER 2026" in r.texts()


def test_a_day_with_one_event_opens_it(monkeypatch):
    r = rig(monkeypatch)
    r.tap(r.key("CALENDAR"))
    r.tap(cell(r, 24))
    assert "TRIP" in r.texts() and "THU 22 OCT - SAT 24 OCT, ALL DAY" in r.texts()
    assert "WHERE" not in r.texts() and "NOTES" not in r.texts()
    r.tap(r.key("BACK"))
    assert "OCTOBER 2026" in r.texts()


def test_an_empty_day_does_nothing(monkeypatch):
    r = rig(monkeypatch)
    r.tap(r.key("CALENDAR"))
    r.tap(cell(r, 20))
    assert "OCTOBER 2026" in r.texts()


def test_calendar_stale_and_empty(monkeypatch):
    r = rig(monkeypatch, age=3600)
    r.tap(r.key("CALENDAR"))
    assert "CALENDAR OFFLINE - UPDATED 60 MIN AGO" in r.texts()
    assert cells(r)[21] == ["BIN DAY", "+3 MORE"]                # the last events stay
    r = rig(monkeypatch, raw={"calendar.family": []})
    r.tap(r.key("CALENDAR"))
    assert all(not lines for lines in cells(r).values())


def test_long_days_say_how_many_more(monkeypatch):
    many = {"calendar.family": [timed(f"Meeting {i}", f"2026-10-21T{15 + i // 4}:{(i % 4) * 15:02d}:00-04:00",
                                      f"2026-10-21T{15 + i // 4}:{(i % 4) * 15 + 10:02d}:00-04:00")
                                for i in range(14)]}
    r = rig(monkeypatch, raw=many)
    r.tap(r.key("CALENDAR"))
    r.tap(cell(r, 21))
    assert "+8 MORE" in r.texts()                                 # six bars, then the count


def test_no_calendar_button_without_calendars(monkeypatch):
    from test_screens import Rig
    monkeypatch.setattr(config, "CALENDARS", [])
    assert "CALENDAR" not in [k.text for k in Rig().sprites(__import__("ui.widgets.panel_widgets",
                                                                       fromlist=["LcarsKey"]).LcarsKey)]


def test_titles_the_font_cant_draw():
    from ui.widgets.panel_widgets import drawable
    assert drawable("Café 🎂 party") == "Cafe party"


# STATUS: today's and tomorrow's events under the average.

def test_paginate_splits_and_relabels_days():
    from screens.status import paginate
    one = lambda e: 1  # noqa: E731
    pages = paginate([("TODAY", ["a", "b", "c"]), ("TOMORROW", ["d", "e"])], 4, one)
    assert pages == [[("day", "TODAY"), ("event", "a"), ("event", "b"), ("event", "c")],
                     [("day", "TOMORROW"), ("event", "d"), ("event", "e")]]
    # A day that carries over is re-labelled at the top of the next page.
    assert paginate([("TODAY", ["a", "b", "c", "d"])], 3, one) == [
        [("day", "TODAY"), ("event", "a"), ("event", "b")],
        [("day", "TODAY"), ("event", "c"), ("event", "d")]]
    assert paginate([], 4, one) == []


def test_paginate_two_line_events_and_clip():
    from screens.status import paginate
    cost = lambda e: 2 if e == "a" else 1  # noqa: E731  # "a" wraps to two lines
    # day + a (two lines) fills a three-line page; b starts the next, re-labelled.
    assert paginate([("TODAY", ["a", "b"])], 3, cost) == [
        [("day", "TODAY"), ("event", "a")], [("day", "TODAY"), ("event", "b")]]
    # A two-line event is clipped to one rather than dropped on a two-line page.
    assert paginate([("TODAY", ["a"])], 2, cost) == [[("day", "TODAY"), ("event", "a")]]


def at_page(r, i):
    """Render agenda page i (the cycle is driven by the panel's seconds clock)."""
    r.panel.now = lambda: i * config.NEWS_CYCLE_SECONDS
    r.tick()
    return r.texts()


def test_status_cycles_through_a_busy_agenda(monkeypatch):
    # Four rows hold today's three events (page 1); tomorrow's two are page 2.
    r = rig(monkeypatch, read_only=True)
    p0 = at_page(r, 0)
    assert "TODAY" in p0 and "1/2" in p0                              # labelled, and clearly a cycle
    for e in ("BIN DAY", "STANDUP", "DENTIST"):
        assert any(e in t for t in p0), e
    assert "TOMORROW" not in p0 and not any("BREAKFAST" in t for t in p0)   # Breakfast is over
    p1 = at_page(r, 1)
    assert "TOMORROW" in p1 and "2/2" in p1 and "TODAY" not in p1
    for e in ("TRIP", "LATE SHIFT"):
        assert any(e in t for t in p1), e
    assert not any("MORE" in t for t in p0 + p1)                      # nothing truncated away now
    r.shot("23-status-calendar")


def test_status_wraps_a_long_event_title(monkeypatch):
    from screens import status
    from ui.widgets.panel_widgets import drawable, wrap
    summary = "Quarterly Budget Review With The Finance Committee"
    long = {"calendar.family": [timed(summary, "2026-10-22T15:30:00-04:00", "2026-10-22T16:00:00-04:00")]}
    r = rig(monkeypatch, raw=long, read_only=True)
    width = status.LEFT_WIDTH - status.AGENDA_TIME
    expected = wrap(drawable(summary, status.AGENDA_SIZE).upper(), status.AGENDA_SIZE, width, 2)
    texts = r.texts()
    assert len(expected) == 2                         # the title spills onto a second line
    assert not expected[-1].endswith("…")             # and fits in two without being cut
    for line in expected:
        assert line in texts, line                    # both lines are drawn (old code dropped the tail)
    assert "TOMORROW" in texts


def test_status_names_only_days_with_events(monkeypatch):
    late = {"calendar.family": [timed("Movie", "2026-10-22T20:00:00-04:00", "2026-10-22T22:00:00-04:00")]}
    r = rig(monkeypatch, raw=late, read_only=True)
    assert "TODAY" not in r.texts() and "TOMORROW" in r.texts() and "MOVIE" in r.texts()
    r = rig(monkeypatch, raw={"calendar.family": []}, read_only=True)
    assert "TODAY" not in r.texts() and "TOMORROW" not in r.texts()


def test_status_with_the_lock_cycles_in_two_rows(monkeypatch):
    # Not read-only: the lock takes the last two rows, leaving two for one
    # day's name and one event a page - so the five events cycle one at a time.
    r = rig(monkeypatch)
    p0 = at_page(r, 0)
    assert "TODAY" in p0 and any("BIN DAY" in t for t in p0) and "1/5" in p0
    assert "TOMORROW" not in p0 and "CONTROLS SECURED" in p0
    seen = []
    for i in range(5):
        seen += at_page(r, i)
    assert "TOMORROW" in seen and any("TRIP" in t for t in seen) and any("LATE SHIFT" in t for t in seen)
