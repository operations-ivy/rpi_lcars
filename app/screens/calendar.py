"""Home Assistant's calendars (Google Calendar through HA): today, tomorrow
and the day after, all-day events first, then by time. An event starting
within 15 minutes, or running now, is picked out in gold. Read-only and open
to anyone: nothing here creates or changes an event. With HA or Google down
it keeps the last events and says how old they are."""
from datasources.calendar import day_name
from screens.base import LEFT, RIGHT, TOP, PanelScreen
from ui import colours
from ui.widgets.panel_widgets import LcarsLabel, drawable

LINES, LINE_TOP, LINE_STEP, SIZE = 11, TOP + 8, 26, 1.1
COL_TITLE = LEFT + 110


class ScreenCalendar(PanelScreen):
    name = "calendar"
    title = "SCHEDULE"

    def build(self):
        self.nav()
        self.lines = []
        for i in range(LINES):
            top = LINE_TOP + i * LINE_STEP
            self.lines.append((self.add(LcarsLabel(colours.BEIGE, (top, LEFT), "", SIZE)),
                               self.add(LcarsLabel(colours.BLUE, (top, COL_TITLE), "", SIZE,
                                                   max_width=RIGHT - COL_TITLE))))

    def rows(self):
        """[(left, right, colour)] in order: a day's name, then its events."""
        shown = self.panel.calendar()
        if shown is None:
            return [("", "CALENDAR UNAVAILABLE" if self.panel.ha.error else "CONNECTING TO THE CALENDAR",
                     colours.GREY_BLUE)]
        days, _ = shown
        if not days:
            return [("", "NOTHING SCHEDULED", colours.GREY_BLUE)]
        today = self.panel.ha.now().date()
        out = []
        for day, entries in days:
            out.append((day_name(day, today), "", colours.ORANGE))
            for e in entries:
                title = drawable(e["summary"], SIZE).upper() or "EVENT"
                if e["now"]:
                    out.append(("NOW", title, colours.GOLD))
                elif e["soon"]:
                    out.append((e["when"], f"{title} - IN {e['soon']} MIN", colours.GOLD))
                else:
                    out.append((e["when"], title, colours.BLUE))
        return out

    def refresh(self):
        rows = self.rows()
        if len(rows) > LINES:
            hidden = sum(1 for r in rows[LINES - 1:] if r[2] != colours.ORANGE)
            rows = rows[:LINES - 1] + [("", f"+{hidden} MORE", colours.GREY_BLUE)]
        rows += [("", "", colours.BLUE)] * (LINES - len(rows))
        for (left, right), (when, text, colour) in zip(self.lines, rows):
            heading = colour == colours.ORANGE
            left.set(when, colours.ORANGE if heading else colours.BEIGE if colour == colours.BLUE else colour)
            right.set(text, colour)

    def link_text(self):
        """Home Assistant's link while it's down, else how old the events are
        once they're stale."""
        ok, text = self.panel.link()
        if not ok:
            return False, f"HOME ASSISTANT LINK: {text}"
        shown = self.panel.calendar()
        age = self.panel.ha.events_age()
        if shown is not None and shown[1] and age is not None:
            return False, f"CALENDAR OFFLINE - UPDATED {age / 60:.0f} MIN AGO"
        return True, "CALENDAR VIA HOME ASSISTANT"
