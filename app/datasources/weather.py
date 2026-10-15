"""Weather for one point, from a background thread like the Home Assistant
client, so a slow or missing service never freezes the screen.

Three sources, tried in order until one answers:

1. The National Weather Service (api.weather.gov; US only): the latest
   observation at the nearest station, its own forecast periods, and active
   alerts. The only source of alerts.
2. Open-Meteo (api.open-meteo.com): current conditions and hourly forecast.
3. MET Norway (api.met.no): current conditions and hourly forecast.

All free, no keys. The backups' hours are folded into the NWS's 12-hour
periods (TODAY / TONIGHT / FRIDAY / FRIDAY NIGHT), so the screens don't care
which source answered. If none answers, the last good data stays, with its
source and age for the screens to show, and the next try comes sooner (one
minute, doubling up to the normal interval)."""
import json
import logging
import threading
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

# api.weather.gov and api.met.no ask every client to say who it is.
USER_AGENT = "rpi_lcars (github.com/operations-ivy/rpi_lcars)"
COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
RETRY_SECONDS = 60

# WMO weather interpretation codes (Open-Meteo).
WMO = {0: "CLEAR", 1: "MOSTLY CLEAR", 2: "PARTLY CLOUDY", 3: "CLOUDY", 45: "FOG", 48: "FREEZING FOG",
       51: "LIGHT DRIZZLE", 53: "DRIZZLE", 55: "HEAVY DRIZZLE", 56: "FREEZING DRIZZLE", 57: "FREEZING DRIZZLE",
       61: "LIGHT RAIN", 63: "RAIN", 65: "HEAVY RAIN", 66: "FREEZING RAIN", 67: "FREEZING RAIN",
       71: "LIGHT SNOW", 73: "SNOW", 75: "HEAVY SNOW", 77: "SNOW GRAINS",
       80: "RAIN SHOWERS", 81: "RAIN SHOWERS", 82: "HEAVY RAIN SHOWERS", 85: "SNOW SHOWERS", 86: "SNOW SHOWERS",
       95: "THUNDERSTORMS", 96: "THUNDERSTORMS AND HAIL", 99: "THUNDERSTORMS AND HAIL"}


def parse_point(text):
    """"lat,lon" -> (lat, lon), or None when empty."""
    text = (text or "").strip()
    if not text:
        return None
    lat, lon = (float(v) for v in text.split(","))
    return round(lat, 4), round(lon, 4)


def c_to_f(c):
    return None if c is None else c * 9 / 5 + 32


def compass(degrees):
    return None if degrees is None else COMPASS[int((degrees % 360) / 22.5 + 0.5) % 16]


def met_symbol(code):
    """MET Norway symbol codes ("lightrainshowers_day") -> "LIGHT RAIN SHOWERS"."""
    if not code:
        return None
    text = code.split("_")[0]
    for word in ("light", "heavy", "and", "thunder", "showers", "sleet", "snow", "rain", "fog",
                 "partly", "cloudy", "fair", "clearsky"):
        text = text.replace(word, f" {word} ")
    text = " ".join(text.split()).replace("clearsky", "clear").replace("fair", "mostly clear")
    return text.upper()


def current_dict(temperature, condition, humidity, wind_mph, wind_degrees, when):
    return {"temperature": temperature, "condition": condition, "humidity": humidity,
            "wind_mph": wind_mph, "wind_from": compass(wind_degrees), "time": when}


def fold_hours(hours, now, count=4):
    """Hourly (local datetime, °F, condition, rain %) -> 12-hour periods like
    the NWS's: day 06-18 (the high), night 18-06 (the low), the most common
    condition, the highest chance of rain."""
    periods = []
    start = now.replace(minute=0, second=0, microsecond=0)
    day = 6 <= start.hour < 18
    end = start.replace(hour=18 if day else 6)
    if not day and start.hour >= 18:
        end += timedelta(days=1)
    while len(periods) < count:
        inside = [h for h in hours if start <= h[0] < end and h[1] is not None]
        # The current period may be part gone; a later one needs nearly all
        # its hours, or its high or low would be a guess (a day's high comes
        # in the afternoon).
        if not inside or (periods and len(inside) < 10):
            break
        temps = [h[1] for h in inside]
        rains = [h[3] for h in inside if h[3] is not None]
        conditions = Counter(h[2] for h in inside if h[2])
        if day:
            name = "TODAY" if start.date() == now.date() else start.strftime("%A").upper()
        else:
            # A night belongs to the evening it starts on (01:00 is last night).
            night_of = (start - timedelta(hours=6)).date()
            tonight = (now - timedelta(hours=6)).date()
            name = "TONIGHT" if night_of == tonight else night_of.strftime("%A").upper() + " NIGHT"
        periods.append({"name": name, "temperature": max(temps) if day else min(temps),
                        "forecast": conditions.most_common(1)[0][0] if conditions else "",
                        "rain": max(rains) if rains else None, "day": day})
        start, end, day = end, end + timedelta(hours=12), not day
    return periods


class Source:
    """One weather service. fetch() returns (current, periods, alerts), with
    alerts None when the source has none to give."""
    name = ""

    def __init__(self, point, get):
        self.point, self.get = point, get


class NWS(Source):
    name = "nws"
    API = "https://api.weather.gov"

    def __init__(self, point, get):
        super().__init__(point, get)
        self.forecast_url = self.station = None

    def fetch(self, now):
        lat, lon = self.point
        if not self.forecast_url:
            props = self.get(self.name, "points", f"{self.API}/points/{lat},{lon}")["properties"]
            stations = self.get(self.name, "stations", props["observationStations"])["features"]
            self.station = stations[0]["properties"]["stationIdentifier"] if stations else None
            self.forecast_url = props["forecast"]
        current = {}
        if self.station:
            p = self.get(self.name, "observation", f"{self.API}/stations/{self.station}/observations/latest")["properties"]
            value = lambda k: (p.get(k) or {}).get("value")  # noqa: E731
            wind = value("windSpeed")
            current = current_dict(c_to_f(value("temperature")), (p.get("textDescription") or "").upper() or None,
                                   value("relativeHumidity"), None if wind is None else wind / 1.609344,
                                   value("windDirection"), p.get("timestamp"))
        periods = []
        for x in self.get(self.name, "forecast", self.forecast_url)["properties"]["periods"]:
            temp = x.get("temperature")
            if temp is not None and x.get("temperatureUnit") == "C":
                temp = c_to_f(temp)
            periods.append({"name": (x.get("name") or "").upper(), "temperature": temp,
                            "forecast": (x.get("shortForecast") or "").upper(),
                            "rain": (x.get("probabilityOfPrecipitation") or {}).get("value"),
                            "day": bool(x.get("isDaytime"))})
        alerts = []
        for f in self.get(self.name, "alerts", f"{self.API}/alerts/active?point={lat},{lon}")["features"]:
            a = f["properties"]
            ends = a.get("ends") or a.get("expires")
            alerts.append({"event": (a.get("event") or "ALERT").upper(), "severity": a.get("severity") or "Unknown",
                           "ends": datetime.fromisoformat(ends) if ends else None})
        return current, periods, alerts


class OpenMeteo(Source):
    name = "open-meteo"

    def fetch(self, now):
        lat, lon = self.point
        query = urllib.parse.urlencode({
            "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 3,
            "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,wind_direction_10m",
            "hourly": "temperature_2m,weather_code,precipitation_probability"})
        d = self.get(self.name, "forecast", f"https://api.open-meteo.com/v1/forecast?{query}")
        c = d["current"]
        current = current_dict(c.get("temperature_2m"), WMO.get(c.get("weather_code")), c.get("relative_humidity_2m"),
                               c.get("wind_speed_10m"), c.get("wind_direction_10m"), c.get("time"))
        h = d["hourly"]
        hours = [(datetime.fromisoformat(t), temp, WMO.get(code), rain)
                 for t, temp, code, rain in zip(h["time"], h["temperature_2m"], h["weather_code"],
                                                h["precipitation_probability"])]
        return current, fold_hours(hours, now.replace(tzinfo=None)), None


class MetNorway(Source):
    name = "met-norway"

    def fetch(self, now):
        lat, lon = self.point
        d = self.get(self.name, "forecast",
                     f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={lat}&lon={lon}")
        series = d["properties"]["timeseries"]
        local = now.tzinfo or datetime.now().astimezone().tzinfo
        hours = []
        for entry in series:
            when = datetime.fromisoformat(entry["time"].replace("Z", "+00:00")).astimezone(local)
            details = entry["data"]["instant"]["details"]
            summary = (entry["data"].get("next_1_hours") or entry["data"].get("next_6_hours") or {}).get("summary", {})
            hours.append((when.replace(tzinfo=None), c_to_f(details.get("air_temperature")),
                          met_symbol(summary.get("symbol_code")), None))
        first = series[0]["data"]
        details = first["instant"]["details"]
        wind = details.get("wind_speed")
        current = current_dict(c_to_f(details.get("air_temperature")),
                               met_symbol(((first.get("next_1_hours") or {}).get("summary") or {}).get("symbol_code")),
                               details.get("relative_humidity"), None if wind is None else wind * 2.236936,
                               details.get("wind_from_direction"), series[0]["time"])
        return current, fold_hours(hours, now.replace(tzinfo=None)), None


class Weather(threading.Thread):
    SOURCES = (NWS, OpenMeteo, MetNorway)

    def __init__(self, point, poll_seconds=300, metrics=None, opener=urllib.request.urlopen,
                 now=lambda: datetime.now().astimezone(), sources=None):
        super().__init__(name="weather", daemon=True)
        self.point = parse_point(point) if isinstance(point, str) else point
        self.poll_seconds = poll_seconds
        self.metrics, self.opener, self.now = metrics, opener, now
        self.sources = [cls(self.point, self._get) for cls in (sources or self.SOURCES)] if self.point else []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._current, self._periods, self._alerts = {}, [], None
        self.source = None      # the source of the data shown
        self.updated = None     # time.time() of that data
        self.connected = False  # the last try got an answer
        self.error = "" if self.point else "NO LOCATION"
        self.retry = RETRY_SECONDS
        if metrics:
            metrics.set("lcars_weather_up", 0)
            for cls in (sources or self.SOURCES):
                metrics.set("lcars_weather_source", 0, source=cls.name)

    # The screens' side.

    def current(self):
        with self._lock:
            return dict(self._current)

    def periods(self):
        with self._lock:
            return list(self._periods)

    def alerts(self):
        """Active alerts, or None when no source that has alerts answered."""
        with self._lock:
            return None if self._alerts is None else list(self._alerts)

    def age(self):
        return None if self.updated is None else time.time() - self.updated

    def stop(self):
        self._stop.set()

    # The thread's side.

    def run(self):
        if not self.point:
            return
        while not self._stop.is_set():
            ok = self.poll()
            if ok:
                self.retry = RETRY_SECONDS
                wait = self.poll_seconds
            else:
                wait, self.retry = self.retry, min(self.retry * 2, self.poll_seconds)
            self._stop.wait(wait)

    def _get(self, source, kind, url):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json, application/json"})
        try:
            with self.opener(req, timeout=15) as r:
                body = json.loads(r.read())
        except Exception:
            self._count(source, kind, "error")
            raise
        self._count(source, kind, "ok")
        return body

    def _count(self, source, kind, result):
        if self.metrics:
            self.metrics.inc("lcars_weather_requests_total", source=source, kind=kind, result=result)

    def poll(self):
        """Try each source in turn; True if one answered."""
        now = self.now()
        for source in self.sources:
            try:
                current, periods, alerts = source.fetch(now)
            except Exception as e:  # noqa: BLE001 - next source
                log.warning("weather from %s: %s", source.name, e)
                continue
            with self._lock:
                self._current, self._periods, self._alerts = current, periods, alerts
            self.source, self.updated, self.connected, self.error = source.name, time.time(), True, ""
            self._publish()
            return True
        self.connected, self.error = False, "ALL SOURCES OFFLINE"
        self._publish()
        return False

    def _publish(self):
        if not self.metrics:
            return
        m = self.metrics
        m.set("lcars_weather_up", 1 if self.connected else 0)
        for source in self.sources:
            m.set("lcars_weather_source", 1 if self.connected and source.name == self.source else 0, source=source.name)
        if self.updated is not None:
            m.set("lcars_weather_last_update_timestamp_seconds", round(self.updated))
        if self.connected:
            alerts = self._alerts
            m.set("lcars_weather_alerts", -1 if alerts is None else len(alerts))
            temp = self._current.get("temperature")
            if temp is not None:
                m.set("lcars_weather_temperature_fahrenheit", round(temp, 1))
