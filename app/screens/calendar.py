"""Home Assistant's calendars (Google Calendar through HA), a month at a
time: this month's grid first, PREV and NEXT across the months fetched
(config.CALENDAR_MONTHS). A day's cell shows its first events; tapping it
opens the event, or the day's list when there are more, and an event in the
list opens its details: when, where, and its notes. An event starting within
15 minutes, or running now, is picked out in gold; one that's over is
greyed. Read-only and open to anyone: nothing here creates or changes an
event. With HA or Google down it keeps the last events and says how old
they are."""
from datasources import calendar as cal
from screens.base import BOTTOM, LEFT, RIGHT, TOP, PanelScreen
from ui import colours
from ui.widgets.panel_widgets import LcarsCell, LcarsKey, LcarsLabel, drawable, wrap

# The month: its name and the keys along the top, the weekdays, then the grid.
HEAD_SIZE, KEY_W, KEY_H = 1.3, 95, 28
DAYS_TOP, GRID_TOP, GRID_BOTTOM, GAP = TOP + 34, TOP + 54, BOTTOM - 30, 3
CELL_W = (RIGHT - LEFT + GAP) // 7 - GAP
NUMBER_SIZE, EVENT_SIZE = 0.8, 0.65
# A day's list: one bar per event.
BAR_TOP, BAR_H, BAR_STEP = TOP + 44, 30, 36
BARS = (GRID_BOTTOM - BAR_TOP) // BAR_STEP
# An event: its title, then label over value for when, where and the notes.
TITLE_SIZE, VALUE_SIZE, NOTES_SIZE = 1.5, 1.2, 1.0


def colour_of(entry):
    if entry["now"] or entry["soon"]:
        return colours.GOLD
    return colours.GREY_BLUE if entry["past"] else colours.BLUE


def title_of(entry, size):
    return drawable(entry["summary"], size).upper() or "EVENT"


class ScreenCalendar(PanelScreen):
    name = "calendar"
    title = "SCHEDULE"

    def __init__(self, panel, view=None):
        """view: ("month", year, month) (the default: this month), ("day",
        date), or ("event", event, back), back being the view to return to."""
        PanelScreen.__init__(self, panel)
        now = panel.ha.now()
        self.view = view or ("month", now.year, now.month)

    def build(self):
        self.nav()
        # Why there are no events: beside the month's name, or in the day's list.
        at = (TOP + 10, LEFT + 200) if self.view[0] == "month" else (BAR_TOP + 4, LEFT + 15)
        self.message = self.add(LcarsLabel(colours.GREY_BLUE, at, "", 0.9 if self.view[0] == "month" else 1.1))
        getattr(self, f"build_{self.view[0]}")()

    def open(self, view):
        self.leave()
        self.loadScreen(ScreenCalendar(self.panel, view))

    def key(self, text, right, handler):
        return self.add(LcarsKey(colours.ORANGE, (TOP + 2, RIGHT - right), (KEY_W, KEY_H), text, handler,
                                 text_size=0.9), layer=2)

    def shown(self):
        """(events, stale), or None with the reason in the message line."""
        shown = self.panel.calendar()
        if shown is None:
            self.message.set("CALENDAR UNAVAILABLE" if self.panel.ha.error else "CONNECTING TO THE CALENDAR")
        else:
            self.message.set("")
        return shown

    # The month.

    def build_month(self):
        _, year, month = self.view
        now = self.panel.ha.now()
        first, last = (now.year, now.month), cal.add_months(now.year, now.month, self.panel.cfg.CALENDAR_MONTHS - 1)
        self.add(LcarsLabel(colours.ORANGE, (TOP + 2, LEFT), f"{cal.pycal.month_name[month]} {year}".upper(),
                            HEAD_SIZE))
        prev, nxt = cal.add_months(year, month, -1), cal.add_months(year, month, 1)
        self.key("PREV", 2 * KEY_W + 8, lambda *_: self.open(("month", *prev))).set_enabled(prev >= first)
        self.key("NEXT", KEY_W, lambda *_: self.open(("month", *nxt))).set_enabled(nxt <= last)
        weeks = cal.grid(year, month)
        height = (GRID_BOTTOM - GRID_TOP + GAP) // len(weeks) - GAP
        for col, day in enumerate(weeks[0]):
            self.add(LcarsLabel(colours.PURPLE, (DAYS_TOP, LEFT + col * (CELL_W + GAP) + 5), f"{day:%a}".upper(), 0.8))
        self.cells = []
        for row, week in enumerate(weeks):
            for col, day in enumerate(week):
                pos = (GRID_TOP + row * (height + GAP), LEFT + col * (CELL_W + GAP))
                self.cells.append((day, self.add(LcarsCell(pos, (CELL_W, height)))))

    def refresh_month(self, events):
        now = self.panel.ha.now()
        today, month = now.date(), self.view[2]
        for day, cell in self.cells:
            entries = cal.on_day(events, day, now) if events is not None else []
            ours = day.month == month
            number = colours.GOLD if day == today else colours.BEIGE if ours else colours.DISABLED
            outline = colours.GOLD if day == today else colours.GREY_BLUE if ours else None
            room = max(0, (cell.rect.height - 20) // int(19 * EVENT_SIZE))
            shown = entries if len(entries) <= room else entries[:max(0, room - 1)]
            lines = [(str(day.day), number, NUMBER_SIZE)]
            lines += [(title_of(e, EVENT_SIZE), colour_of(e) if ours else colours.DISABLED, EVENT_SIZE)
                      for e in shown]
            if len(shown) < len(entries):
                lines.append((f"+{len(entries) - len(shown)} MORE", colours.GREY_BLUE, EVENT_SIZE))
            cell.set(lines, outline, self.opener(day, entries))

    def opener(self, day, entries):
        """What tapping a day does: its one event, its list, or nothing."""
        back = ("month", *self.view[1:])
        if len(entries) == 1:
            return lambda *_: self.open(("event", entries[0]["event"], back))
        if entries:
            return lambda *_: self.open(("day", day))
        return None

    # A day.

    def build_day(self):
        day = self.view[1]
        self.add(LcarsLabel(colours.ORANGE, (TOP + 2, LEFT), cal.day_name(day, self.panel.ha.now().date()),
                            HEAD_SIZE))
        self.key("MONTH", KEY_W, lambda *_: self.open(("month", day.year, day.month)))
        self.bars = [self.add(LcarsKey(colours.BLUE, (BAR_TOP + i * BAR_STEP, LEFT), (RIGHT - LEFT, BAR_H), "",
                                       align="left"), layer=2) for i in range(BARS)]
        self.more = self.add(LcarsLabel(colours.GREY_BLUE, (BAR_TOP + (BARS - 1) * BAR_STEP + 4, LEFT + 15), "",
                                        1.0))

    def refresh_day(self, events):
        day = self.view[1]
        entries = cal.on_day(events or [], day, self.panel.ha.now())
        if events is not None and not entries:
            self.message.set("NOTHING SCHEDULED")
        shown = entries if len(entries) <= BARS else entries[:BARS - 1]
        for i, bar in enumerate(self.bars):
            bar.visible = i < len(shown)
            if bar.visible:
                e = shown[i]
                soon = f" - IN {e['soon']} MIN" if e["soon"] else ""
                bar.set_text(f"{'NOW' if e['now'] else e['when']}   {title_of(e, 1.0)}{soon}")
                bar.set_colour(colour_of(e))
                bar.handler = self.detail(e["event"])
        self.more.set(f"+{len(entries) - len(shown)} MORE" if len(shown) < len(entries) else "")

    def detail(self, event):
        back = ("day", self.view[1])
        return lambda *_: self.open(("event", event, back))

    # An event.

    def build_event(self):
        _, event, back = self.view
        self.key("BACK", KEY_W, lambda *_: self.open(back))
        width = RIGHT - LEFT
        top = TOP + 2
        for line in wrap(title_of(event, TITLE_SIZE), TITLE_SIZE, width - KEY_W - 15, 2):
            self.add(LcarsLabel(colours.ORANGE, (top, LEFT), line, TITLE_SIZE))
            top += 32
        rows = [("WHEN", [cal.when(event)], VALUE_SIZE, 1)]
        if event["location"]:
            rows.append(("WHERE", [drawable(event["location"], VALUE_SIZE).upper()], VALUE_SIZE, 2))
        if event["description"]:
            rows.append(("NOTES", [drawable(p, NOTES_SIZE) for p in event["description"].split("\n")], NOTES_SIZE,
                         None))
        top += 8
        for label, paragraphs, size, most in rows:
            step = int(19 * size) + 2
            if top + 20 + step > GRID_BOTTOM:
                break
            self.add(LcarsLabel(colours.PURPLE, (top, LEFT), label, 1.0))
            top += 20
            room = (GRID_BOTTOM - top) // step if most is None else most
            lines = []
            for p in paragraphs:
                lines += wrap(p, size, width, room - len(lines))
            for line in lines:
                self.add(LcarsLabel(colours.BEIGE, (top, LEFT), line, size))
                top += step
            top += 8

    # Every frame.

    def refresh(self):
        """The month and the day follow the events; an event's details stay
        as they were opened."""
        if self.view[0] == "event":
            return
        shown = self.shown()
        getattr(self, f"refresh_{self.view[0]}")(None if shown is None else shown[0])

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
