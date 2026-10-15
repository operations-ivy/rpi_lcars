import io
import json
from datetime import datetime, timedelta, timezone

from datasources import weather as W
from metrics import Metrics

EST = timezone(timedelta(hours=-4))
NOW = datetime(2026, 10, 15, 10, 30, tzinfo=EST)


def nws_bodies():
    return {
        "https://api.weather.gov/points/39.7456,-97.0892": {"properties": {
            "forecast": "https://api.weather.gov/gridpoints/TOP/31,80/forecast",
            "observationStations": "https://api.weather.gov/gridpoints/TOP/31,80/stations"}},
        "https://api.weather.gov/gridpoints/TOP/31,80/stations": {"features": [
            {"properties": {"stationIdentifier": "KXYZ"}}]},
        "https://api.weather.gov/stations/KXYZ/observations/latest": {"properties": {
            "temperature": {"value": 23}, "textDescription": "Cloudy", "relativeHumidity": {"value": 78.2},
            "windSpeed": {"value": 14.832}, "windDirection": {"value": 60}, "timestamp": "2026-10-15T14:30:00+00:00"}},
        "https://api.weather.gov/gridpoints/TOP/31,80/forecast": {"properties": {"periods": [
            {"name": "Today", "temperature": 72, "temperatureUnit": "F", "shortForecast": "Chance Rain Showers",
             "probabilityOfPrecipitation": {"value": 27}, "isDaytime": True},
            {"name": "Tonight", "temperature": 62, "temperatureUnit": "F", "shortForecast": "Cloudy",
             "probabilityOfPrecipitation": {"value": None}, "isDaytime": False}]}},
        "https://api.weather.gov/alerts/active?point=39.7456,-97.0892": {"features": [
            {"properties": {"event": "Flood Watch", "severity": "Moderate", "ends": "2026-10-15T22:00:00-04:00"}}]},
    }


def open_meteo_body():
    start = datetime(2026, 10, 15, 0, 0)
    hours = [start + timedelta(hours=i) for i in range(72)]
    return {"current": {"temperature_2m": 70.5, "relative_humidity_2m": 86, "weather_code": 3,
                        "wind_speed_10m": 9.7, "wind_direction_10m": 57, "time": "2026-10-15T10:45"},
            "hourly": {"time": [h.isoformat(timespec="minutes") for h in hours],
                       "temperature_2m": [60 + (h.hour if h.hour <= 15 else 30 - h.hour) for h in hours],
                       "weather_code": [3 if h.hour < 18 else 0 for h in hours],
                       "precipitation_probability": [10 if h.day == 15 else 70 for h in hours]}}


def met_body():
    start = datetime(2026, 10, 15, 14, 0, tzinfo=timezone.utc)
    return {"properties": {"timeseries": [
        {"time": (start + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "data": {"instant": {"details": {"air_temperature": 20 + (i % 12), "relative_humidity": 80,
                                          "wind_speed": 4.3, "wind_from_direction": 53}},
                  "next_1_hours": {"summary": {"symbol_code": "lightrainshowers_day" if i < 4 else "clearsky_night"}}}}
        for i in range(48)]}}


class FakeWeb:
    """Stands in for urlopen: answers by URL prefix, or fails a host."""

    def __init__(self):
        self.bodies = nws_bodies()
        self.down = set()
        self.urls = []

    def __call__(self, req, timeout):
        url = req.full_url
        self.urls.append(url)
        assert req.get_header("User-agent") == W.USER_AGENT
        host = url.split("/")[2]
        if host in self.down:
            raise OSError(f"{host} down")
        if host == "api.open-meteo.com":
            body = open_meteo_body()
        elif host == "api.met.no":
            body = met_body()
        else:
            body = self.bodies[url]
        return io.BytesIO(json.dumps(body).encode())


def make(web, metrics=None):
    return W.Weather("39.7456,-97.0892", metrics=metrics, opener=web, now=lambda: NOW)


def test_nws_first():
    web, m = FakeWeb(), Metrics()
    w = make(web, m)
    assert w.poll()
    assert w.source == "nws"
    c = w.current()
    assert round(c["temperature"]) == 73 and c["condition"] == "CLOUDY"
    assert c["wind_from"] == "ENE" and round(c["wind_mph"]) == 9
    assert [p["name"] for p in w.periods()] == ["TODAY", "TONIGHT"]
    assert w.alerts()[0]["event"] == "FLOOD WATCH"
    assert m.get("lcars_weather_up") == 1
    assert m.get("lcars_weather_source", source="nws") == 1
    assert m.get("lcars_weather_alerts") == 1


def test_open_meteo_when_nws_is_down():
    web, m = FakeWeb(), Metrics()
    web.down.add("api.weather.gov")
    w = make(web, m)
    assert w.poll()
    assert w.source == "open-meteo"
    assert w.current()["condition"] == "CLOUDY"
    names = [p["name"] for p in w.periods()]
    assert names == ["TODAY", "TONIGHT", "FRIDAY", "FRIDAY NIGHT"]
    assert w.alerts() is None  # unknown, not "none"
    assert m.get("lcars_weather_alerts") == -1
    assert m.get("lcars_weather_source", source="open-meteo") == 1
    assert m.get("lcars_weather_source", source="nws") == 0


def test_met_norway_when_both_are_down():
    web = FakeWeb()
    web.down |= {"api.weather.gov", "api.open-meteo.com"}
    w = make(web)
    assert w.poll()
    assert w.source == "met-norway"
    c = w.current()
    assert c["condition"] == "LIGHT RAIN SHOWERS"
    assert round(c["temperature"]) == 68  # 20 °C
    assert w.periods()[0]["name"] == "TODAY"


def test_all_down_keeps_the_last_data_and_says_so():
    web, m = FakeWeb(), Metrics()
    w = make(web, m)
    w.poll()
    web.down |= {"api.weather.gov", "api.open-meteo.com", "api.met.no"}
    assert not w.poll()
    assert not w.connected and w.error == "ALL SOURCES OFFLINE"
    assert w.source == "nws" and round(w.current()["temperature"]) == 73
    assert w.age() is not None
    assert m.get("lcars_weather_up") == 0
    # It comes back on its own.
    web.down.clear()
    assert w.poll() and w.connected


def test_all_down_from_the_start():
    web = FakeWeb()
    web.down |= {"api.weather.gov", "api.open-meteo.com", "api.met.no"}
    w = make(web)
    assert not w.poll()
    assert w.current() == {} and w.periods() == [] and w.alerts() is None and w.age() is None


def test_retries_sooner_then_backs_off():
    web = FakeWeb()
    web.down |= {"api.weather.gov", "api.open-meteo.com", "api.met.no"}
    w = make(web)
    w.poll_seconds = 300
    waits = []
    w._stop.wait = lambda seconds: (waits.append(seconds), len(waits) >= 5 and w._stop.set())
    w.run()
    assert waits == [60, 120, 240, 300, 300]


def test_no_location_never_calls_out():
    web = FakeWeb()
    w = W.Weather("", opener=web)
    assert w.error == "NO LOCATION"
    w.start()
    w.join(5)
    assert web.urls == []


def test_nws_point_resolved_once():
    web = FakeWeb()
    w = make(web)
    w.poll()
    w.poll()
    assert sum("/points/" in u for u in web.urls) == 1


def test_fold_hours_names_and_values():
    now = datetime(2026, 10, 15, 22, 0)  # a Thursday night
    hours = [(now + timedelta(hours=i), 50 + i, "CLEAR", i) for i in range(40)]
    periods = W.fold_hours(hours, now)
    assert [p["name"] for p in periods] == ["TONIGHT", "FRIDAY", "FRIDAY NIGHT"]
    assert periods[0]["temperature"] == 50          # the low
    assert periods[1]["temperature"] == 50 + 19     # the high: 17:00 Friday
    early = datetime(2026, 10, 16, 2, 0)            # 2 am counts as last night
    assert W.fold_hours([(early + timedelta(hours=i), 50, "CLEAR", None) for i in range(30)], early)[0]["name"] == "TONIGHT"


def test_met_symbols():
    assert W.met_symbol("lightrainshowersandthunder_day") == "LIGHT RAIN SHOWERS AND THUNDER"
    assert W.met_symbol("clearsky_night") == "CLEAR"
    assert W.met_symbol("fair_day") == "MOSTLY CLEAR"
    assert W.met_symbol("partlycloudy_day") == "PARTLY CLOUDY"
    assert W.met_symbol(None) is None


def test_compass_and_parse():
    assert W.compass(0) == "N" and W.compass(359) == "N" and W.compass(60) == "ENE"
    assert W.parse_point(" 39.74561, -97.08923 ") == (39.7456, -97.0892)
    assert W.parse_point("") is None
