"""Outside: the latest conditions, active alerts, and the next four forecast
periods, from datasources/weather.py (the National Weather Service, or a
backup when it's down). Read-only, open to anyone."""

from panel.thermostat import fmt_temp
from screens.base import LEFT, RIGHT, TOP, PanelScreen
from ui import colours
from ui.widgets.panel_widgets import LcarsLabel

SOURCE_LABELS = {"nws": "NWS", "open-meteo": "OPEN-METEO", "met-norway": "MET NORWAY"}
ALERTS_X = 470
MAX_ALERTS = 4
# Forecast rows: name, temperature, forecast, chance of rain.
ROW_TOP, ROW_HEIGHT = TOP + 205, 23
COL_NAME, COL_TEMP, COL_TEXT, COL_RAIN = LEFT, LEFT + 205, LEFT + 285, RIGHT


def age_text(seconds):
    if seconds < 90:
        return "JUST NOW"
    if seconds < 5400:
        return f"{seconds / 60:.0f} MIN AGO"
    return f"{seconds / 3600:.0f} HR AGO"


class ScreenWeather(PanelScreen):
    name = "weather"
    title = "ATMOSPHERIC CONDITIONS"

    def build(self):
        self.nav("CLIMATE", self.go_climate)
        self.add(LcarsLabel(colours.ORANGE, (TOP + 10, LEFT), "EXTERIOR", 1.5))
        self.temp = self.add(LcarsLabel(colours.BEIGE, (TOP + 35, LEFT), "--", 4.5))
        self.condition = self.add(LcarsLabel(colours.BLUE, (TOP + 128, LEFT), "", 1.3, max_width=ALERTS_X - LEFT - 20))
        self.details = self.add(LcarsLabel(colours.GREY_BLUE, (TOP + 158, LEFT), "", 1.0))

        self.add(LcarsLabel(colours.ORANGE, (TOP + 10, ALERTS_X), "ALERTS", 1.5))
        self.alerts = [self.add(LcarsLabel(colours.GREY_BLUE, (TOP + 45 + i * 28, ALERTS_X), "", 1.1,
                                           max_width=RIGHT - ALERTS_X)) for i in range(MAX_ALERTS)]

        self.rows = []
        for i in range(4):
            top = ROW_TOP + i * ROW_HEIGHT
            self.rows.append((
                self.add(LcarsLabel(colours.PURPLE, (top, COL_NAME), "", 1.0)),
                self.add(LcarsLabel(colours.BEIGE, (top, COL_TEMP), "", 1.0)),
                self.add(LcarsLabel(colours.BLUE, (top, COL_TEXT), "", 1.0, max_width=COL_RAIN - COL_TEXT - 60)),
                self.add(LcarsLabel(colours.GREY_BLUE, (top, COL_RAIN), "", 1.0, "right")),
            ))

    def link_text(self):
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
        lines = []
        if alerts is None:
            lines = [("UNAVAILABLE", colours.ORANGE), ("NATIONAL WEATHER SERVICE OFFLINE", colours.GREY_BLUE)]
        elif not alerts:
            lines = [("NONE ACTIVE", colours.GREY_BLUE)]
        else:
            for a in alerts[:MAX_ALERTS]:
                until = ""
                if a.get("ends"):
                    until = " UNTIL " + a["ends"].astimezone().strftime("%-I %p" if a["ends"].minute == 0 else "%-I:%M %p")
                lines.append((a["event"] + until, colours.RED if a["severity"] in ("Extreme", "Severe") else colours.ORANGE))
        for i, label in enumerate(self.alerts):
            text, colour = lines[i] if i < len(lines) else ("", colours.GREY_BLUE)
            label.set(text, colour)

        periods = w.periods() if w else []
        for i, (name, temp, text, rain) in enumerate(self.rows):
            if i < len(periods):
                f = periods[i]
                name.set(f["name"])
                temp.set(fmt_temp(f["temperature"], "°F"), colours.BEIGE if f["day"] else colours.BLUE)
                text.set(f["forecast"])
                rain.set(f"{f['rain']:.0f}% RAIN" if f.get("rain") else "")
            else:
                for label in (name, temp, text, rain):
                    label.set("")
