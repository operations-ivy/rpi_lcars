"""Calendar events from Home Assistant's calendar API, turned into the
panel's agenda: day by day, all-day events first, then by start time. Only
each event's title and times are kept (no description, location or
attendees); titles are personal, so they go to the screen and nowhere else:
not the log, not the metrics."""
from datetime import date, datetime, time, timedelta


def _when(field, tz):
    """(datetime in tz, all_day) from {"dateTime": ...} or {"date": ...}."""
    if "dateTime" in field:
        return datetime.fromisoformat(field["dateTime"]).astimezone(tz), False
    return datetime.combine(date.fromisoformat(field["date"]), time(), tz), True


def parse(raw, calendar, tz):
    """An event as HA sends it -> {"summary", "start", "end", "all_day",
    "calendar"}, or None when it can't be read."""
    try:
        start, all_day = _when(raw["start"], tz)
        end, _ = _when(raw["end"], tz)
    except (KeyError, TypeError, ValueError):
        return None
    return {"summary": (raw.get("summary") or "").strip() or "BUSY", "start": start, "end": max(end, start),
            "all_day": all_day, "calendar": calendar}


def agenda(events, now, days=3):
    """[(day, [entry])] for today and the next days - 1, each entry
    {"summary", "when", "soon", "now", "all_day"}: "when" is "ALL DAY", "14:30",
    or "UNTIL 10:00" on a timed event's later days. "soon" is minutes to a
    start within 15; "now" is true while a timed event runs. Days with
    nothing on them are left out; so are events already over."""
    out = []
    today = now.date()
    for offset in range(days):
        day = today + timedelta(days=offset)
        begin = datetime.combine(day, time(), now.tzinfo)
        finish = begin + timedelta(days=1)
        entries = []
        for e in events:
            if not (e["start"] < finish and e["end"] > begin) or e["end"] <= now:
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
                "summary": e["summary"], "when": when, "all_day": all_day,
                "soon": int(minutes + 0.999) if not all_day and 0 < minutes <= 15 else None,
                "now": not all_day and e["start"] <= now < e["end"],
                "_key": (not all_day, e["start"], e["summary"]),
            })
        if entries:
            entries.sort(key=lambda x: x["_key"])
            for x in entries:
                del x["_key"]
            out.append((day, entries))
    return out


def day_name(day, today):
    if day == today:
        return "TODAY"
    if day == today + timedelta(days=1):
        return "TOMORROW"
    return f"{day:%A %-d %B}".upper()

