"""The resting screen: read-only, open to anyone. The house average leads
(upstairs and downstairs are on the thermostat screen) over a headline (the
news feed's top few in turn; not a link), then a row each for the thermostat, outside, the internet, the sun,
the shopping list and the PS5, and the weather alert or the lock. The detail
is a touch away."""
from panel import lock as L
from panel.thermostat import ACTION_LABELS, fmt_temp, targets
from screens.base import LEFT, RIGHT, TOP, PanelScreen
from ui import colours
from ui.widgets.panel_widgets import LcarsLabel, wrap

ROWS = ("THERMOSTAT", "TARGET", "OUTSIDE", "NETWORK", "SUN", "SHOPPING", "PS5")
COL_LABEL, COL_VALUE, ROW_HEIGHT = 450, 585, 32
# The headline under the average: at most two lines.
NEWS_TOP, NEWS_WIDTH, NEWS_LINES, NEWS_SIZE, NEWS_HEIGHT = TOP + 170, COL_LABEL - LEFT - 10, 2, 1.1, 24
PS5_STATES = {"playing": "PLAYING", "paused": "PAUSED", "on": "ONLINE", "idle": "IDLE",
              "standby": "STANDBY", "off": "OFFLINE"}


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
        for i, row in enumerate(self.rows()):
            top = TOP + 10 + i * ROW_HEIGHT
            self.add(LcarsLabel(colours.PURPLE, (top, COL_LABEL), row, 1.2))
            self.values[row] = self.add(LcarsLabel(colours.BLUE, (top, COL_VALUE), "--", 1.2,
                                                   max_width=RIGHT - COL_VALUE))

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

    def rows(self):
        cfg = self.panel.cfg
        skip = {"SHOPPING": not cfg.SHOPPING_LIST, "PS5": not cfg.MEDIA_PLAYER}
        return [r for r in ROWS if not skip.get(r)]

    def refresh(self):
        p = self.panel
        attrs, unit = p.thermostat, p.ha.unit
        inside = fmt_temp(attrs.get("current_temperature"), unit)

        average = p.house()[2]
        self.big.set("--" if average is None else f"{average:.1f}{unit}",
                     colours.GREY_BLUE if average is None else colours.BEIGE)
        self.note.set(p.house_note())
        self.show_headline()

        action = attrs.get("hvac_action")
        self.values["THERMOSTAT"].set(f"{inside} {ACTION_LABELS.get(action, (action or '').upper())}".strip(),
                                      colours.ORANGE if action in ("heating", "cooling") else colours.BLUE)
        keys = targets(attrs)
        self.values["TARGET"].set(" - ".join(fmt_temp(attrs.get(k), unit) for k in keys) or "--")
        temp, condition = p.outside()
        self.values["OUTSIDE"].set(f"{fmt_temp(temp, '°F')} {condition or ''}".strip(),
                                   colours.GREY_BLUE if p.weather_stale() else colours.BLUE)
        network = p.network() or ("--", True)
        self.values["NETWORK"].set(network[0], colours.BLUE if network[1] else colours.RED)
        self.values["SUN"].set(p.sun_line() or "--")
        if "SHOPPING" in self.values:
            items = p.shopping()
            needed = None if items is None else sum(1 for i in items if i.get("status") != "completed")
            self.values["SHOPPING"].set("--" if needed is None else f"{needed} NEEDED" if needed else "NOTHING NEEDED")
        if "PS5" in self.values:
            media = p.media()
            state = PS5_STATES.get(media["state"], "--")
            playing = media["state"] in ("playing", "paused")
            self.values["PS5"].set(f"{state} {media['title'].upper()}" if playing and media["title"] else state,
                                   colours.GOLD if playing else colours.BLUE)

        alert, kind = p.alert_line()
        alert_colour = {"alert": colours.RED, "ok": colours.GREY_BLUE, "unknown": colours.ORANGE}[kind]
        lock = p.lock
        if p.read_only:
            self.lock_line.set(alert, alert_colour if kind == "alert" else colours.ORANGE)
            self.hint.set("THERMOSTAT MONITOR ONLY - CONTROLS DISABLED")
            return
        if kind == "alert":
            # An alert outranks the lock line; the block still shows the lock.
            self.lock_line.set(alert, colours.RED)
            self.hint.set("TOUCH THERMOSTAT FOR DETAILS")
            return
        if lock.remote == L.HARD_LOCKED:
            line, hint, colour = "CONTROLS LOCKED BY HOME ASSISTANT", "UNLOCK FROM HOME ASSISTANT", colours.RED
        elif lock.can_change:
            line, hint, colour = "CONTROLS OPEN", "TOUCH CLIMATE TO ADJUST", colours.GOLD
        else:
            line, hint, colour = "CONTROLS SECURED", "TOUCH CLIMATE AND ENTER CODE TO ADJUST", colours.ORANGE
        self.lock_line.set(line, colour)
        self.hint.set(hint)

