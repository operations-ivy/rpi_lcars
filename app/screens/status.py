"""The resting screen: read-only, open to anyone. Inside and outside
temperatures, what the thermostat is doing, and whether controls are locked."""
from panel import lock as L
from panel.thermostat import ACTION_LABELS, MODE_LABELS, fmt_temp, targets
from screens.base import LEFT, RIGHT, TOP, PanelScreen
from ui import colours
from ui.widgets.panel_widgets import LcarsLabel

ROWS = ("MODE", "STATUS", "TARGET", "HUMIDITY", "EXTERIOR", "CONDITIONS")
COL_LABEL, COL_VALUE = 470, 610


class ScreenStatus(PanelScreen):
    name = "status"
    title = "ENVIRONMENTAL STATUS"

    def build(self):
        self.nav("CLIMATE", self.go_climate)

        self.add(LcarsLabel(colours.ORANGE, (TOP + 10, LEFT), "INTERIOR", 1.5))
        self.inside = self.add(LcarsLabel(colours.BEIGE, (TOP + 35, LEFT), "--", 6))
        self.inside_note = self.add(LcarsLabel(colours.GREY_BLUE, (TOP + 160, LEFT), "", 1.2))
        self.room = self.add(LcarsLabel(colours.BLUE, (TOP + 190, LEFT), "", 1.2))

        self.values = {}
        for i, row in enumerate(ROWS):
            top = TOP + 10 + i * 36
            self.add(LcarsLabel(colours.PURPLE, (top, COL_LABEL), row, 1.2))
            self.values[row] = self.add(LcarsLabel(colours.BLUE, (top, COL_VALUE), "--", 1.2,
                                                   max_width=RIGHT - COL_VALUE))

        self.lock_line = self.add(LcarsLabel(colours.ORANGE, (TOP + 245, LEFT), "", 1.4, max_width=RIGHT - LEFT))
        self.hint = self.add(LcarsLabel(colours.GREY_BLUE, (TOP + 280, LEFT), "", 1.0, max_width=RIGHT - LEFT))

    def refresh(self):
        p = self.panel
        attrs, unit = p.thermostat, p.ha.unit
        self.inside.set(fmt_temp(attrs.get("current_temperature"), unit))
        lo, hi = p.guardrails()
        self.inside_note.set(f"LIMITS {lo:.0f}-{hi:.0f}{unit}")
        room = p.room_line()
        if room is None:
            self.room.set("")
        else:
            self.room.set(room[0], colours.BLUE if room[1] else colours.GREY_BLUE)

        mode = p.hvac_mode
        self.values["MODE"].set(MODE_LABELS.get(mode, (mode or "--").upper()))
        action = attrs.get("hvac_action")
        self.values["STATUS"].set(ACTION_LABELS.get(action, (action or "--").upper()),
                                  colours.ORANGE if action in ("heating", "cooling") else colours.BLUE)
        keys = targets(attrs)
        self.values["TARGET"].set(" - ".join(fmt_temp(attrs.get(k), unit) for k in keys) or "--")
        humidity = attrs.get("current_humidity")
        self.values["HUMIDITY"].set("--" if humidity is None else f"{humidity:.0f}%")
        temp, condition = p.outside()
        stale = p.weather_stale()
        self.values["EXTERIOR"].set(fmt_temp(temp, "°F"), colours.GREY_BLUE if stale else colours.BLUE)
        self.values["CONDITIONS"].set(condition or "--", colours.GREY_BLUE if stale else colours.BLUE)

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
            self.hint.set("TOUCH WEATHER FOR DETAILS")
            return
        if lock.remote == L.HARD_LOCKED:
            line, hint, colour, block = ("CONTROLS LOCKED BY HOME ASSISTANT",
                                         "UNLOCK FROM HOME ASSISTANT", colours.RED, "LOCKED")
        elif lock.can_change:
            line, hint, colour, block = ("CONTROLS OPEN", "TOUCH CLIMATE TO ADJUST",
                                         colours.GOLD, "OPEN")
        else:
            line, hint, colour, block = ("CONTROLS SECURED", "TOUCH CLIMATE AND ENTER CODE TO ADJUST",
                                         colours.ORANGE, "SECURED")
        self.lock_line.set(line, colour)
        self.hint.set(hint)
