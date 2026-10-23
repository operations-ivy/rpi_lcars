"""The alert condition: Prometheus' firing alerts (the homelab's
infrastructure) on the left, overwatch's feeds and their recent alerts on the
right, the worst of both as CONDITION RED, YELLOW or GREEN. Read-only, open
to anyone."""
from panel.infra import ago
from screens.base import LEFT, RIGHT, TOP, PanelScreen
from ui import colours
from ui.widgets.panel_widgets import LcarsHeader, LcarsKey, LcarsLabel

RIGHT_X = 470
ROW_TOP, ROW_HEIGHT, INFRA_ROWS = TOP + 92, 26, 8
MARK = (12, 18)  # the coloured block before each line
FEED_VALUE = RIGHT_X + 105
DETAIL_TOP, DETAIL_ROWS = TOP + 190, 4
SEVERITY_COLOURS = {"critical": colours.RED, "warning": colours.GOLD, "info": colours.GREY_BLUE}
CONDITION_COLOURS = {"RED": colours.RED, "YELLOW": colours.GOLD, "GREEN": colours.BLUE, "UNKNOWN": colours.GREY_BLUE}


def feed_colour(severity):
    return colours.RED if severity >= 3 else colours.GOLD if severity == 2 else colours.BLUE


class ScreenAlerts(PanelScreen):
    name = "alerts"
    title = "ALERT CONDITION"

    def build(self):
        self.nav()
        self.condition = self.add(LcarsLabel(colours.BLUE, (TOP + 8, LEFT), "", 2.2))

        self.add(LcarsHeader(colours.ORANGE, (TOP + 62, LEFT), RIGHT_X - LEFT - 24, "INFRASTRUCTURE", 1.3))
        self.infra = []
        for i in range(INFRA_ROWS):
            top = ROW_TOP + i * ROW_HEIGHT
            mark = self.add(LcarsKey(colours.BLUE, (top + 2, LEFT), MARK, "", pill=True), layer=2)
            label = self.add(LcarsLabel(colours.BLUE, (top, LEFT + 22), "", 1.1, max_width=RIGHT_X - LEFT - 42))
            self.infra.append((mark, label))

        self.add(LcarsHeader(colours.ORANGE, (TOP + 62, RIGHT_X), RIGHT - RIGHT_X, "OVERWATCH", 1.3))
        self.feeds = []
        for i in range(3):
            top = ROW_TOP + i * ROW_HEIGHT
            mark = self.add(LcarsKey(colours.BLUE, (top + 2, RIGHT_X), MARK, "", pill=True), layer=2)
            name = self.add(LcarsLabel(colours.PURPLE, (top, RIGHT_X + 22), "", 1.1))
            word = self.add(LcarsLabel(colours.BLUE, (top, FEED_VALUE), "", 1.1, max_width=RIGHT - FEED_VALUE))
            self.feeds.append((mark, name, word))
        self.details = [self.add(LcarsLabel(colours.GREY_BLUE, (DETAIL_TOP + i * 24, RIGHT_X), "", 1.0,
                                            max_width=RIGHT - RIGHT_X)) for i in range(DETAIL_ROWS)]

    def link_text(self):
        p = self.panel
        parts, ok = [], True
        for name, label in (("prometheus", "PROMETHEUS"), ("overwatch", "OVERWATCH")):
            if name not in p.feeds:
                continue
            stale = p.feed_stale(name)
            ok = ok and not stale
            parts.append(f"{label} {'OFFLINE' if p.feed_age(name) is None else ago(p.feed_age(name))}")
        return ok, " - ".join(parts) or "NO ALERT SOURCES"

    def refresh(self):
        status = self.panel.alerts()
        condition = status["condition"]
        self.condition.set(f"CONDITION {condition}", CONDITION_COLOURS[condition])
        self.refresh_infra(status["infra"])
        self.refresh_watch(status["watch"])

    def refresh_infra(self, alerts):
        if alerts is None:
            lines = [("PROMETHEUS OFFLINE", colours.ORANGE)]
        elif not alerts:
            lines = [("ALL SYSTEMS NOMINAL", colours.BLUE)]
        else:
            lines = [(a["text"], SEVERITY_COLOURS[a["severity"]]) for a in alerts]
            if len(lines) > INFRA_ROWS:
                lines = lines[:INFRA_ROWS - 1] + [(f"+{len(lines) - INFRA_ROWS + 1} MORE", colours.GREY_BLUE)]
        for i, (mark, label) in enumerate(self.infra):
            text, colour = lines[i] if i < len(lines) else ("", colours.BLUE)
            label.set(text, colour)
            mark.visible = bool(text)
            mark.set_colour(colour)

    def refresh_watch(self, watch):
        feeds = (watch or {}).get("feeds", [])
        for i, (mark, name, word) in enumerate(self.feeds):
            if i < len(feeds):
                f = feeds[i]
                mark.visible = True
                mark.set_colour(feed_colour(f["severity"]))
                name.set(f["name"])
                word.set(f["word"], feed_colour(f["severity"]))
            else:
                mark.visible = False
                name.set("OVERWATCH OFFLINE" if i == 0 and watch is None else "", colours.ORANGE)
                word.set("")

        lines = []
        for f in feeds:
            if f["severity"] >= 2 and f["line"]:
                lines.append((f"{f['name']}: {f['line']}", feed_colour(f["severity"])))
        now = self.panel.now()
        for a in (watch or {}).get("recent", []):
            lines.append((f"{ago(now - a['at'])}: {a['text']}", colours.RED if a["live"] else colours.GOLD))
        if watch is not None and not lines:
            lines = [("NO ALERTS IN THE LAST 30 MIN", colours.GREY_BLUE)]
        for i, label in enumerate(self.details):
            text, colour = lines[i] if i < len(lines) else ("", colours.GREY_BLUE)
            label.set(text, colour)
