"""The calendar: Home Assistant's calendar API through the panel's client,
the agenda the screen draws, and the CALENDAR screen. Every event here is
made up: real titles never go in this public repo."""
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


def timed(summary, start, end):
    return {"summary": summary, "start": {"dateTime": start}, "end": {"dateTime": end},
            "description": "never kept", "location": "never kept"}


def all_day(summary, start, end):
    return {"summary": summary, "start": {"date": start}, "end": {"date": end}}


RAW = {
    "calendar.family": [
        timed("Dentist", "2026-10-21T14:30:00-04:00", "2026-10-21T15:15:00-04:00"),       # in 10 minutes
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


def test_parse_keeps_only_titles_and_times():
    e = cal.parse(RAW["calendar.family"][0], "calendar.family", NY)
    assert set(e) == {"summary", "start", "end", "all_day", "calendar"}
    assert e["start"] == datetime(2026, 10, 21, 14, 30, tzinfo=NY) and not e["all_day"]
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
    assert query["start"] == ["2026-10-21T04:00:00+00:00"] and query["end"] == ["2026-10-24T04:00:00+00:00"]
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

def rig(monkeypatch, raw=RAW, fail=(), age=0):
    from test_screens import FakeHA, Rig
    monkeypatch.setattr(config, "CALENDARS", list(raw))
    r = Rig()
    fake = FakeCalendars(raw, fail)
    ha = client(fake, Clock())
    ha.poll()
    r.ha._events, r.ha.events_updated = ha.events(), r.ha.clock() - age
    r.ha.now = lambda: NOW
    assert isinstance(r.ha, FakeHA)
    return r


def test_calendar_screen(monkeypatch):
    r = rig(monkeypatch)
    r.tap(r.key("CALENDAR"))
    assert r.screen == "calendar"
    texts = r.texts()
    for expected in ("TODAY", "ALL DAY", "BIN DAY", "NOW", "STANDUP", "14:30", "DENTIST - IN 10 MIN",
                     "TOMORROW", "TRIP", "22:00", "LATE SHIFT", "FRIDAY 23 OCTOBER", "UNTIL 06:00",
                     "CALENDAR VIA HOME ASSISTANT"):
        assert expected in texts, expected
    assert "BREAKFAST" not in texts and "NEXT WEEK" not in texts
    r.shot("20-calendar")


def test_calendar_screen_stale_and_empty(monkeypatch):
    r = rig(monkeypatch, age=3600)
    r.tap(r.key("CALENDAR"))
    assert "CALENDAR OFFLINE - UPDATED 60 MIN AGO" in r.texts()
    assert "DENTIST - IN 10 MIN" in r.texts()                     # the last events stay
    r = rig(monkeypatch, raw={"calendar.family": []})
    r.tap(r.key("CALENDAR"))
    assert "NOTHING SCHEDULED" in r.texts()


def test_long_days_say_how_many_more(monkeypatch):
    many = {"calendar.family": [timed(f"Meeting {i}", f"2026-10-21T{15 + i // 4}:{(i % 4) * 15:02d}:00-04:00",
                                      f"2026-10-21T{15 + i // 4}:{(i % 4) * 15 + 10:02d}:00-04:00")
                                for i in range(14)]}
    r = rig(monkeypatch, raw=many)
    r.tap(r.key("CALENDAR"))
    assert "+5 MORE" in r.texts()                                 # 1 day line + 9 events + the count


def test_no_calendar_button_without_calendars(monkeypatch):
    from test_screens import Rig
    monkeypatch.setattr(config, "CALENDARS", [])
    assert "CALENDAR" not in [k.text for k in Rig().sprites(__import__("ui.widgets.panel_widgets",
                                                                       fromlist=["LcarsKey"]).LcarsKey)]


def test_titles_the_font_cant_draw():
    from ui.widgets.panel_widgets import drawable
    assert drawable("Café 🎂 party") == "Cafe party"
