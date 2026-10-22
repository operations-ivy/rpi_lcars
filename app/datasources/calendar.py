"""Calendar events from Home Assistant's calendar API, turned into what the
panel shows: the month's grid, a day's events, an event's details, and the
next days for STATUS. All-day events come first in a day, then by start
time. Each event's title, times, place and notes are kept, for the screen
only: they never go to the log or the metrics."""
import calendar as pycal
import html
import re
from datetime import date, datetime, time, timedelta

_BREAK = re.compile(r"<br\s*/?>|</p>|</div>|</li>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")


def _when(field, tz):
    """(datetime in tz, all_day) from {"dateTime": ...} or {"date": ...}."""
    if "dateTime" in field:
        return datetime.fromisoformat(field["dateTime"]).astimezone(tz), False
    return datetime.combine(date.fromisoformat(field["date"]), time(), tz), True


def _text(value):
    """Plain text from a description, which Google may send as HTML: tags
    out, entities decoded, one line per paragraph, blank lines dropped."""
    text = html.unescape(_TAG.sub("", _BREAK.sub("\n", str(value or ""))))
    return "\n".join(" ".join(line.split()) for line in text.splitlines() if line.strip())


def parse(raw, calendar, tz):
    """An event as HA sends it -> {"summary", "start", "end", "all_day",
    "location", "description", "calendar"}, or None when it can't be read."""
    try:
        start, all_day = _when(raw["start"], tz)
        end, _ = _when(raw["end"], tz)
    except (KeyError, TypeError, ValueError):
        return None
    return {"summary": (raw.get("summary") or "").strip() or "BUSY", "start": start, "end": max(end, start),
            "all_day": all_day, "location": _text(raw.get("location")), "description": _text(raw.get("description")),
            "calendar": calendar}


def grid(year, month):
    """The month's weeks, Sunday first: [[date] * 7], filled out with the
    days either side."""
    return pycal.Calendar(firstweekday=pycal.SUNDAY).monthdatescalendar(year, month)


def add_months(year, month, n):
    """(year, month) n months on (n may be negative)."""
    months = year * 12 + month - 1 + n
    return months // 12, months % 12 + 1


def window(now, months):
    """(start, end) to fetch, in now's zone: the whole grid of this month
    and of the months - 1 after it."""
    first = grid(now.year, now.month)[0][0]
    last = grid(*add_months(now.year, now.month, months - 1))[-1][-1]
    return (datetime.combine(first, time(), now.tzinfo),
            datetime.combine(last + timedelta(days=1), time(), now.tzinfo))


def on_day(events, day, now, past=True):
    """The day's events, all-day first then by start: each {"summary",
    "when", "soon", "now", "past", "all_day", "event"}. "when" is "ALL DAY",
    "14:30", or "UNTIL 10:00" on a timed event's later days. "soon" is minutes
    to a start within 15; "now" is true while a timed event runs; "past" once
    it's over (left out unless past)."""
    begin = datetime.combine(day, time(), now.tzinfo)
    finish = begin + timedelta(days=1)
    entries = []
    for e in events:
        over = e["end"] <= now
        if not (e["start"] < finish and e["end"] > begin) or (over and not past):
            continue
        all_day = e["all_day"] or (e["start"] < begin and e["end"] >= finish)
        if all_day:
            when = "ALL DAY"
        elif e["start"] < begin:
            when = f"UNTIL {e['end']:%H:%M}"
        else:
            when = f"{e['start']:%H:%M}"
        minutes = (e["start"] - now).total_seconds() / 60
        entries.append({
            "summary": e["summary"], "when": when, "all_day": all_day, "past": over, "event": e,
            "soon": int(minutes + 0.999) if not all_day and 0 < minutes <= 15 else None,
            "now": not all_day and e["start"] <= now < e["end"],
        })
    entries.sort(key=lambda x: (not x["all_day"], x["event"]["start"], x["summary"]))
    return entries


def agenda(events, now, days=2):
    """[(day, [entry])] for today and the next days - 1, entries as on_day()
    gives them but none already over. Days with nothing on are left out."""
    out = []
    for offset in range(days):
        day = now.date() + timedelta(days=offset)
        entries = on_day(events, day, now, past=False)
        if entries:
            out.append((day, entries))
    return out


def day_name(day, today):
    if day == today:
        return "TODAY"
    if day == today + timedelta(days=1):
        return "TOMORROW"
    return f"{day:%A %-d %B}".upper()


def when(e):
    """An event's date and times in a line: "WEDNESDAY 21 OCTOBER, 14:30 -
    15:15", "WEDNESDAY 21 OCTOBER, ALL DAY", or both ends when it spans days."""
    start, end = e["start"], e["end"]
    if e["all_day"]:
        last = (end - timedelta(days=1)).date() if end > start else start.date()
        if last == start.date():
            return f"{start:%A %-d %B}, ALL DAY".upper()
        return f"{start:%a %-d %b} - {last:%a %-d %b}, ALL DAY".upper()
    if end.date() == start.date():
        return f"{start:%A %-d %B}, {start:%H:%M} - {end:%H:%M}".upper()
    return f"{start:%a %-d %b %H:%M} - {end:%a %-d %b %H:%M}".upper()
