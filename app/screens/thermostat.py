"""The thermostat and the weather side by side: inside, what the ecobee is
doing, its setpoints and the lock on the left; outside, alerts and the next
four forecast periods (datasources/weather.py: the National Weather Service,
or a backup when it's down) on the right. Read-only, open to anyone; changes
are on the climate screen."""
from panel import lock as L
from panel.thermostat import ACTION_LABELS, MODE_LABELS, fmt_temp, targets
from screens.base import LEFT, RIGHT, TOP, PanelScreen
from ui import colours
from ui.widgets.panel_widgets import LcarsLabel

SOURCE_LABELS = {"nws": "NWS", "open-meteo": "OPEN-METEO", "met-norway": "MET NORWAY"}
WEATHER_X = 470
# The thermostat's rows, under the inside temperature.
ROWS = ("MODE", "STATUS", "TARGET", "HUMIDITY", "LIMITS")
ROW_TOP, ROW_HEIGHT, COL_VALUE = TOP + 118, 27, LEFT + 115
# Forecast rows: name, temperature, forecast, chance of rain.
FORECAST_TOP, FORECAST_HEIGHT = TOP + 192, 23
COL_NAME, COL_TEMP, COL_TEXT = WEATHER_X, WEATHER_X + 92, WEATHER_X + 140
DAYS = {d: d[:3] for d in ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")}


def age_text(seconds):
    if seconds < 90:
        return "JUST NOW"
    if seconds < 5400:
        return f"{seconds / 60:.0f} MIN AGO"
    return f"{seconds / 3600:.0f} HR AGO"


def short_name(name):
    """"FRIDAY NIGHT" -> "FRI NIGHT", "THIS AFTERNOON" -> "AFTERNOON": the
    column is narrow."""
    return " ".join(DAYS.get(w, w) for w in name.split() if w != "THIS")


class ScreenThermostat(PanelScreen):
    name = "thermostat"
    title = "ENVIRONMENTAL CONTROL"

    def build(self):
        self.nav()
        left_width = WEATHER_X - LEFT - 20

        self.add(LcarsLabel(colours.ORANGE, (TOP + 10, LEFT), "INTERIOR", 1.5))
        self.inside = self.add(LcarsLabel(colours.BEIGE, (TOP + 32, LEFT), "--", 4))
        self.values = {}
        for i, row in enumerate(ROWS):
            top = ROW_TOP + i * ROW_HEIGHT
            self.add(LcarsLabel(colours.PURPLE, (top, LEFT), row, 1.1))
            self.values[row] = self.add(LcarsLabel(colours.BLUE, (top, COL_VALUE), "--", 1.1,
                                                   max_width=WEATHER_X - COL_VALUE - 20))
        self.lock_line = self.add(LcarsLabel(colours.ORANGE, (TOP + 255, LEFT), "", 1.2, max_width=left_width))
        self.hint = self.add(LcarsLabel(colours.GREY_BLUE, (TOP + 281, LEFT), "", 1.0, max_width=left_width))

        right_width = RIGHT - WEATHER_X
        self.add(LcarsLabel(colours.ORANGE, (TOP + 10, WEATHER_X), "EXTERIOR", 1.5))
        self.temp = self.add(LcarsLabel(colours.BEIGE, (TOP + 32, WEATHER_X), "--", 4))
        self.condition = self.add(LcarsLabel(colours.BLUE, (TOP + 115, WEATHER_X), "", 1.2, max_width=right_width))
        self.details = self.add(LcarsLabel(colours.GREY_BLUE, (TOP + 142, WEATHER_X), "", 1.0, max_width=right_width))
        self.alert = self.add(LcarsLabel(colours.GREY_BLUE, (TOP + 166, WEATHER_X), "", 1.0, max_width=right_width))
        self.rows = []
        for i in range(4):
            top = FORECAST_TOP + i * FORECAST_HEIGHT
            self.rows.append((
                self.add(LcarsLabel(colours.PURPLE, (top, COL_NAME), "", 1.0, max_width=COL_TEMP - COL_NAME - 6)),
                self.add(LcarsLabel(colours.BEIGE, (top, COL_TEMP), "", 1.0)),
                self.add(LcarsLabel(colours.BLUE, (top, COL_TEXT), "", 1.0, max_width=RIGHT - COL_TEXT - 50)),
                self.add(LcarsLabel(colours.GREY_BLUE, (top, RIGHT), "", 1.0, "right")),
            ))

    def link_text(self):
        """Home Assistant's link while it's down, else where the weather came
        from and how old it is."""
        ok, text = self.panel.link()
        if not ok:
            return False, f"HOME ASSISTANT LINK: {text}"
        w = self.panel.weather
        if w is None or not w.point:
            return False, "WEATHER: NO LOCATION SET"
        age = w.age()
        if age is None:
            return False, "WEATHER: ALL SOURCES OFFLINE" if w.error else "WEATHER: CONNECTING"
        source = SOURCE_LABELS.get(w.source, (w.source or "").upper())
        if not w.connected:
            return False, f"WEATHER OFFLINE - {source} DATA {age_text(age)}"
        return True, f"WEATHER VIA {source} - {age_text(age)}"

    def refresh(self):
        self.refresh_thermostat()
        self.refresh_weather()

    def refresh_thermostat(self):
        p = self.panel
        attrs, unit = p.thermostat, p.ha.unit
        self.inside.set(fmt_temp(attrs.get("current_temperature"), unit))
        mode = p.hvac_mode
        self.values["MODE"].set(MODE_LABELS.get(mode, (mode or "--").upper()))
        action = attrs.get("hvac_action")
        self.values["STATUS"].set(ACTION_LABELS.get(action, (action or "--").upper()),
                                  colours.ORANGE if action in ("heating", "cooling") else colours.BLUE)
        keys = targets(attrs)
        self.values["TARGET"].set(" - ".join(fmt_temp(attrs.get(k), unit) for k in keys) or "--")
        humidity = attrs.get("current_humidity")
        self.values["HUMIDITY"].set("--" if humidity is None else f"{humidity:.0f}%")
        lo, hi = p.guardrails()
        self.values["LIMITS"].set(f"{lo:.0f}-{hi:.0f}{unit}")

        lock = p.lock
        if p.read_only:
            line, hint, colour = "MONITOR ONLY", "CONTROLS DISABLED", colours.ORANGE
        elif lock.remote == L.HARD_LOCKED:
            line, hint, colour = "CONTROLS LOCKED BY HOME ASSISTANT", "UNLOCK FROM HOME ASSISTANT", colours.RED
        elif lock.can_change:
            line, hint, colour = "CONTROLS OPEN", "TOUCH CLIMATE TO ADJUST", colours.GOLD
        else:
            line, hint, colour = "CONTROLS SECURED", "TOUCH CLIMATE AND ENTER CODE", colours.ORANGE
        self.lock_line.set(line, colour)
        self.hint.set(hint)

    def refresh_weather(self):
        p = self.panel
        w = p.weather
        stale = p.weather_stale()
        current = w.current() if w else {}
        self.temp.set(fmt_temp(current.get("temperature"), "°F"), colours.GREY_BLUE if stale else colours.BEIGE)
        self.condition.set(current.get("condition") or ("WEATHER UNAVAILABLE" if stale else ""))
        details = []
        if current.get("humidity") is not None:
            details.append(f"HUMIDITY {current['humidity']:.0f}%")
        if current.get("wind_mph") is not None:
            wind = current["wind_mph"]
            details.append("WIND CALM" if wind < 1 else f"WIND {current.get('wind_from') or ''} {wind:.0f} MPH".replace("  ", " "))
        self.details.set("   ".join(details))

        alerts = w.alerts() if w else None
        if alerts is None:
            self.alert.set("ALERTS UNAVAILABLE", colours.ORANGE)
        elif not alerts:
            self.alert.set("NO ACTIVE ALERTS", colours.GREY_BLUE)
        else:
            a = alerts[0]
            until = ""
            if a.get("ends"):
                until = " UNTIL " + a["ends"].astimezone().strftime("%-I %p" if a["ends"].minute == 0 else "%-I:%M %p")
            more = f" +{len(alerts) - 1}" if len(alerts) > 1 else ""
            self.alert.set(a["event"] + until + more,
                           colours.RED if a["severity"] in ("Extreme", "Severe") else colours.ORANGE)

        periods = w.periods() if w else []
        for i, (name, temp, text, rain) in enumerate(self.rows):
            if i < len(periods):
                f = periods[i]
                name.set(short_name(f["name"]))
                temp.set(fmt_temp(f["temperature"], "°F"), colours.BEIGE if f["day"] else colours.BLUE)
                text.set(f["forecast"])
                rain.set(f"{f['rain']:.0f}%" if f.get("rain") else "")
            else:
                for label in (name, temp, text, rain):
                    label.set("")
