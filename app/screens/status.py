"""The resting screen: read-only, open to anyone. The room the panel is in
(its own sensor; the thermostat's reading without one), then a row each for
the thermostat, outside, the internet, the sun, the shopping list and the
PS5, and the weather alert or the lock. The detail is a touch away."""
from panel import lock as L
from panel.thermostat import ACTION_LABELS, fmt_temp, targets
from screens.base import LEFT, RIGHT, TOP, PanelScreen
from ui import colours
from ui.widgets.panel_widgets import LcarsLabel

ROWS = ("THERMOSTAT", "TARGET", "OUTSIDE", "NETWORK", "SUN", "SHOPPING", "PS5")
COL_LABEL, COL_VALUE, ROW_HEIGHT = 450, 585, 32
PS5_STATES = {"playing": "PLAYING", "paused": "PAUSED", "on": "ONLINE", "idle": "IDLE",
              "standby": "STANDBY", "off": "OFFLINE"}


class ScreenStatus(PanelScreen):
    name = "status"
    title = "STATUS REPORT"

    def build(self):
        self.nav()

        self.heading = self.add(LcarsLabel(colours.ORANGE, (TOP + 10, LEFT), "", 1.5))
        self.big = self.add(LcarsLabel(colours.BEIGE, (TOP + 35, LEFT), "--", 6))
        self.note = self.add(LcarsLabel(colours.GREY_BLUE, (TOP + 160, LEFT), "", 1.2))

        self.values = {}
        for i, row in enumerate(self.rows()):
            top = TOP + 10 + i * ROW_HEIGHT
            self.add(LcarsLabel(colours.PURPLE, (top, COL_LABEL), row, 1.2))
            self.values[row] = self.add(LcarsLabel(colours.BLUE, (top, COL_VALUE), "--", 1.2,
                                                   max_width=RIGHT - COL_VALUE))

        self.lock_line = self.add(LcarsLabel(colours.ORANGE, (TOP + 245, LEFT), "", 1.4, max_width=RIGHT - LEFT))
        self.hint = self.add(LcarsLabel(colours.GREY_BLUE, (TOP + 280, LEFT), "", 1.0, max_width=RIGHT - LEFT))

    def rows(self):
        cfg = self.panel.cfg
        skip = {"SHOPPING": not cfg.SHOPPING_LIST, "PS5": not cfg.MEDIA_PLAYER}
        return [r for r in ROWS if not skip.get(r)]

    def refresh(self):
        p = self.panel
        attrs, unit = p.thermostat, p.ha.unit
        inside = fmt_temp(attrs.get("current_temperature"), unit)

        room = p.room_reading()
        if p.room is None:
            self.heading.set("INTERIOR")
            self.big.set(inside)
            humidity = attrs.get("current_humidity")
            self.note.set("" if humidity is None else f"HUMIDITY {humidity:.0f}%")
        else:
            self.heading.set(p.cfg.ROOM_NAME)
            if room is None:
                self.big.set("--", colours.GREY_BLUE)
                self.note.set("SENSOR OFFLINE")
            else:
                self.big.set(f"{room[0]:.1f}°F", colours.BEIGE)
                self.note.set(f"HUMIDITY {room[1]:.0f}%")

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
