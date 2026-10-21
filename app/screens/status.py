"""The resting screen: read-only, open to anyone. The house average leads
(upstairs, downstairs and the thermostat are on the thermostat screen) over a
headline (the news feed's top few in turn; not a link); on the right, outside,
the internet and the sun, each a label over its value;
along the bottom, the weather alert or the lock. The detail is a touch away."""
from panel import lock as L
from panel.thermostat import fmt_temp
from screens.base import LEFT, RIGHT, TOP, PanelScreen
from ui import colours
from ui.widgets.panel_widgets import LcarsLabel, wrap

ROWS = ("OUTSIDE", "NETWORK", "SUN")
# The right column: each row a small label with its value under it.
COL_LABEL, ROW_TOP, ROW_HEIGHT, VALUE_DROP = 470, TOP + 12, 72, 20
# The headline under the average: at most two lines.
NEWS_TOP, NEWS_WIDTH, NEWS_LINES, NEWS_SIZE, NEWS_HEIGHT = TOP + 170, COL_LABEL - LEFT - 30, 2, 1.1, 24


class ScreenStatus(PanelScreen):
    name = "status"
    title = "STATUS REPORT"

    def build(self):
        self.nav()

        self.add(LcarsLabel(colours.ORANGE, (TOP + 10, LEFT), "HOUSE AVERAGE", 1.5))
        self.big = self.add(LcarsLabel(colours.BEIGE, (TOP + 32, LEFT), "--", 5))
        # Beside the number, why there's no average; under it, whose headline.
        self.note = self.add(LcarsLabel(colours.GREY_BLUE, (TOP + 65, LEFT + 70), "", 1.0,
                                        max_width=NEWS_WIDTH - 70))
        self.source = self.add(LcarsLabel(colours.GREY_BLUE, (NEWS_TOP - 24, LEFT), "", 1.0, max_width=NEWS_WIDTH))
        self.news = [self.add(LcarsLabel(colours.BEIGE, (NEWS_TOP + i * NEWS_HEIGHT, LEFT), "", NEWS_SIZE))
                     for i in range(NEWS_LINES)]

        self.values = {}
        for i, row in enumerate(ROWS):
            top = ROW_TOP + i * ROW_HEIGHT
            self.add(LcarsLabel(colours.PURPLE, (top, COL_LABEL), row, 1.0))
            self.values[row] = self.add(LcarsLabel(colours.BLUE, (top + VALUE_DROP, COL_LABEL), "--", 1.5,
                                                   max_width=RIGHT - COL_LABEL))

        self.lock_line = self.add(LcarsLabel(colours.ORANGE, (TOP + 245, LEFT), "", 1.4, max_width=RIGHT - LEFT))
        self.hint = self.add(LcarsLabel(colours.GREY_BLUE, (TOP + 280, LEFT), "", 1.0, max_width=RIGHT - LEFT))

    def show_headline(self):
        p = self.panel
        shown = p.headline()
        if shown is None:
            self.source.set(f"{p.cfg.NEWS_SOURCE} OFFLINE" if "news" in p.feeds else "")
            title = ""
        else:
            item, number, of = shown
            self.source.set(f"{p.cfg.NEWS_SOURCE} {number}/{of}")
            title = item["title"]
        for label, line in zip(self.news, wrap(title, NEWS_SIZE, NEWS_WIDTH, NEWS_LINES) + [""] * NEWS_LINES):
            label.set(line)

    def refresh(self):
        p = self.panel
        unit = p.ha.unit
        average = p.house()[2]
        self.big.set("--" if average is None else f"{average:.1f}{unit}",
                     colours.GREY_BLUE if average is None else colours.BEIGE)
        self.note.set(p.house_note())
        self.show_headline()

        temp, condition = p.outside()
        self.values["OUTSIDE"].set(f"{fmt_temp(temp, '°F')} {condition or ''}".strip(),
                                   colours.GREY_BLUE if p.weather_stale() else colours.BLUE)
        network = p.network() or ("--", True)
        self.values["NETWORK"].set(network[0], colours.BLUE if network[1] else colours.RED)
        self.values["SUN"].set(p.sun_line() or "--")
        alert, kind = p.alert_line()
        alert_colour = {"alert": colours.RED, "ok": colours.GREY_BLUE, "unknown": colours.ORANGE}[kind]
        lock = p.lock
        if p.read_only:
            self.lock_line.set(alert, alert_colour if kind == "alert" else colours.ORANGE)
            self.hint.set("")  # the THERMOSTAT screen says PREVIEW; nothing to add here
            return
        if lock.remote == L.HARD_LOCKED:
            line, hint, colour = "CONTROLS LOCKED BY HOME ASSISTANT", "UNLOCK FROM HOME ASSISTANT", colours.RED
        elif lock.can_change:
            line, hint, colour = "CONTROLS OPEN", "TOUCH THERMOSTAT TO ADJUST", colours.GOLD
        else:
            line, hint, colour = "CONTROLS SECURED", "TOUCH THERMOSTAT, THEN UNLOCK, TO ADJUST", colours.ORANGE
        if kind == "alert":
            # An alert outranks the lock line; the lock moves to the hint.
            self.lock_line.set(alert, colours.RED)
            self.hint.set(line)
            return
        self.lock_line.set(line, colour)
        self.hint.set(hint)

