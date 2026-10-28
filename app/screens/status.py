"""The resting screen: read-only, open to anyone. The house average leads
(upstairs, downstairs and the thermostat are on the thermostat screen), with
today's and tomorrow's events under it (a day with nothing left on isn't
named) and the lock under those (not on a read-only panel); on the right, outside, the
internet, the sun, the weather alerts and the Home Assistant link, each a
label over its value, spread down the right side with a line from each
label to a part of the Enterprise-D beside them (a master systems display);
along the bottom, the forecast's next few periods in
turn (or a news feed's headlines, if one is set; not links). The detail is a touch away."""
from datasources.calendar import day_name
from panel import lock as L
from panel.thermostat import fmt_temp
from screens.base import BOTTOM, LEFT, RIGHT, TOP, PanelScreen
from ui import colours
from ui.widgets.msd import LcarsCallouts, LcarsShip
from ui.widgets.panel_widgets import LcarsHeader, LcarsLabel, drawable, wrap

# Each row, its top, and the part of the ship its label's line goes to.
ROWS = {"OUTSIDE": (TOP + 5, "bow"), "NETWORK": (TOP + 73, "saucer"), "SUN": (TOP + 144, "impulse"),
        "WEATHER ALERTS": (TOP + 215, "nacelle"), "HOME ASSISTANT": (TOP + 286, "hull")}
# The right column: each row a small label with its value under it (OUTSIDE
# has the condition on a line of its own), then the ship to the frame's
# right edge and down to the bottom (a side view under the top one); the
# lines bend at BEND_X.
COL_LABEL, VALUE_DROP, VALUE_SIZE = 470, 19, 1.2
CONDITION_DROP, CONDITION_SIZE = 42, 1.0
SHIP_LEFT, SHIP_SIZE, BEND_X = 592, (183, BOTTOM - TOP - 5), 584
VALUE_WIDTH = BEND_X - COL_LABEL - 4
# The headline along the bottom of the left side (the ship has the right):
# at most two lines, the last on the bottom bar's line (the link is a row on
# this screen). As wide as the events above it.
NEWS_LINES, NEWS_SIZE, NEWS_HEIGHT = 2, 1.1, 24
NEWS_TOP = BOTTOM - 25 - (NEWS_LINES - 1) * NEWS_HEIGHT
# Under the average: the events, a line each under its day's name, then the
# lock and its hint (not read-only: it takes the last two lines' room).
LEFT_WIDTH = NEWS_WIDTH = COL_LABEL - LEFT - 20
AGENDA_TOP, AGENDA_STEP, AGENDA_SIZE, AGENDA_LINES, AGENDA_TIME = TOP + 165, 21, 1.0, 4, 90
LOCK_TOP = AGENDA_TOP + 2 * AGENDA_STEP + 4


def fit(days, lines, cost=lambda e: 1):
    """[(kind, value)] in at most `lines` lines: ("day", (name, more)) then
    ("event", entry) for each day in turn, more being how many of its events
    didn't fit. cost(entry) is the lines an event's title takes (1 or 2); a
    day always shows its first event, clipped to fit. Each later day keeps
    room for its name and one event when there's room for it at all."""
    out = []
    used = 0
    for i, (name, entries) in enumerate(days):
        later = 2 * (len(days) - i - 1)
        room = lines - used
        if room - later >= 2:
            room -= later
        if room < 2:
            break
        budget = room - 1               # the day's name takes one line
        shown, spent = 0, 0
        for e in entries:
            c = cost(e)
            if shown == 0:
                c = min(c, budget)      # the first event always shows, clipped
            elif spent + c > budget:
                break
            shown += 1
            spent += c
        out.append(("day", (name, len(entries) - shown)))
        out += [("event", e) for e in entries[:shown]]
        used += 1 + spent
    return out


class ScreenStatus(PanelScreen):
    name = "status"
    title = "STATUS REPORT"

    def build(self):
        self.nav()

        self.add(LcarsHeader(colours.ORANGE, (TOP + 10, LEFT), LEFT_WIDTH, "HOUSE AVERAGE", 1.5))
        self.big = self.add(LcarsLabel(colours.BEIGE, (TOP + 32, LEFT), "--", 6.65))
        # Beside the number, why there's no average.
        self.note = self.add(LcarsLabel(colours.GREY_BLUE, (TOP + 102, LEFT + 75), "", 1.0,
                                        max_width=LEFT_WIDTH - 75))
        # Whose headline, on the line above it: one slot per headline length
        # (the last is the bottom line, for OFFLINE with no headline).
        self.sources = [self.add(LcarsLabel(colours.GREY_BLUE, (NEWS_TOP - NEWS_HEIGHT * (1 - i), LEFT), "", 1.0,
                                            max_width=NEWS_WIDTH)) for i in range(NEWS_LINES + 1)]
        self.news = [self.add(LcarsLabel(colours.BEIGE, (NEWS_TOP + i * NEWS_HEIGHT, LEFT), "", NEWS_SIZE))
                     for i in range(NEWS_LINES)]

        ship = self.add(LcarsShip((TOP + 5, SHIP_LEFT), SHIP_SIZE))
        self.values, lines = {}, []
        for row, (top, part) in ROWS.items():
            label = self.add(LcarsLabel(colours.PURPLE, (top, COL_LABEL), row, 1.0))
            self.values[row] = self.add(LcarsLabel(colours.BLUE, (top + VALUE_DROP, COL_LABEL), "--", VALUE_SIZE,
                                                   max_width=VALUE_WIDTH))
            if row == "OUTSIDE":
                self.condition = self.add(LcarsLabel(colours.BLUE, (top + CONDITION_DROP, COL_LABEL), "",
                                                     CONDITION_SIZE, max_width=VALUE_WIDTH))
            lines.append(((label.rect.right + 6, label.rect.centery), BEND_X, ship.part(part)))
        self.add(LcarsCallouts((COL_LABEL, TOP, RIGHT - COL_LABEL, BOTTOM - TOP), lines))

        self.agenda = [(self.add(LcarsLabel(colours.ORANGE, (AGENDA_TOP + i * AGENDA_STEP, LEFT), "", AGENDA_SIZE)),
                        self.add(LcarsLabel(colours.BLUE, (AGENDA_TOP + i * AGENDA_STEP, LEFT + AGENDA_TIME), "",
                                            AGENDA_SIZE, max_width=LEFT_WIDTH - AGENDA_TIME)))
                       for i in range(AGENDA_LINES)]
        self.lock_line = self.add(LcarsLabel(colours.ORANGE, (LOCK_TOP, LEFT), "", 1.2, max_width=LEFT_WIDTH))
        self.hint = self.add(LcarsLabel(colours.GREY_BLUE, (LOCK_TOP + 27, LEFT), "", 0.9, max_width=LEFT_WIDTH))

    def link_text(self):
        """Nothing on the bottom bar: the link is a row here."""
        return True, ""

    def show_headline(self):
        p = self.panel
        shown, name = p.headline(), p.headline_source()
        if shown is None or not name:
            source, title = f"{name} OFFLINE" if name else "", ""
        else:
            title, number, of = shown
            source = f"{name} {number}/{of}"
        # An old forecast is greyed, like OUTSIDE.
        colour = colours.GREY_BLUE if name == "FORECAST" and p.weather_stale() else colours.BEIGE
        # Sat on the bottom: a one-line headline takes the bottom line.
        lines = wrap(title, NEWS_SIZE, NEWS_WIDTH, NEWS_LINES)
        lines = [""] * (NEWS_LINES - len(lines)) + lines
        for label, line in zip(self.news, lines):
            label.set(line, colour)
        at = NEWS_LINES - sum(1 for line in lines if line)
        for i, label in enumerate(self.sources):
            label.set(source if i == at else "")

    def title_text(self, e):
        title = drawable(e["summary"], AGENDA_SIZE).upper() or "EVENT"
        return f"{title} - IN {e['soon']} MIN" if e["soon"] else title

    def show_agenda(self):
        p = self.panel
        today = p.ha.now().date()
        days = [(day_name(day, today), entries) for day, entries in p.upcoming()]
        width = LEFT_WIDTH - AGENDA_TIME
        lines = AGENDA_LINES if p.read_only else AGENDA_LINES - 2
        # An event's title wraps to a second line when it won't fit on one, so
        # it costs fit() one line or two; its time sits on the first line only.
        rows = fit(days, lines, lambda e: len(wrap(self.title_text(e), AGENDA_SIZE, width, 2)))
        slot = 0
        for row in rows:
            if slot >= AGENDA_LINES:
                break
            if row[0] == "day":
                left, right = self.agenda[slot]
                name, more = row[1]
                left.set(name, colours.ORANGE)
                right.set(f"+{more} MORE" if more else "", colours.GREY_BLUE)
                slot += 1
            else:
                e = row[1]
                gold = e["now"] or e["soon"]
                when = "NOW" if e["now"] else e["when"]
                for n, line in enumerate(wrap(self.title_text(e), AGENDA_SIZE, width, min(2, AGENDA_LINES - slot))):
                    left, right = self.agenda[slot]
                    left.set(when if n == 0 else "", colours.GOLD if gold else colours.BEIGE)
                    right.set(line, colours.GOLD if gold else colours.BLUE)
                    slot += 1
        for left, right in self.agenda[slot:]:
            left.set("")
            right.set("")

    def refresh(self):
        p = self.panel
        unit = p.ha.unit
        average = p.house()[2]
        self.big.set("--" if average is None else f"{average:.1f}{unit}",
                     colours.GREY_BLUE if average is None else colours.BEIGE)
        self.note.set(p.house_note())
        self.show_headline()
        self.show_agenda()

        temp, condition = p.outside()
        stale = colours.GREY_BLUE if p.weather_stale() else colours.BLUE
        self.values["OUTSIDE"].set(fmt_temp(temp, "°F"), stale)
        self.condition.set(condition or "", stale)
        network = p.network() or ("--", True)
        self.values["NETWORK"].set(network[0], colours.BLUE if network[1] else colours.RED)
        self.values["SUN"].set(p.sun_line() or "--")
        ok, link = p.link()
        self.values["HOME ASSISTANT"].set(link, colours.BLUE if ok else colours.RED)
        alert, kind = p.alert_line()
        self.values["WEATHER ALERTS"].set(
            alert, {"alert": colours.RED, "ok": colours.BLUE, "unknown": colours.ORANGE}[kind])

        lock = p.lock
        if p.read_only:  # the THERMOSTAT screen says PREVIEW; nothing to add here
            self.lock_line.set("")
            self.hint.set("")
            return
        if lock.remote == L.HARD_LOCKED:
            line, hint, colour = "CONTROLS LOCKED BY HOME ASSISTANT", "UNLOCK FROM HOME ASSISTANT", colours.RED
        elif lock.can_change:
            line, hint, colour = "CONTROLS OPEN", "TOUCH THERMOSTAT TO ADJUST", colours.GOLD
        else:
            line, hint, colour = "CONTROLS SECURED", "TOUCH THERMOSTAT, THEN UNLOCK, TO ADJUST", colours.ORANGE
        self.lock_line.set(line, colour)
        self.hint.set(hint)

