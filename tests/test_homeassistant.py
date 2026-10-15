import io
import json
import urllib.error

from datasources.homeassistant import HomeAssistant
from metrics import Metrics


class FakeHA:
    """Stands in for urllib.request.urlopen."""

    def __init__(self, states, fail=None):
        self.states, self.fail = states, fail
        self.calls, self.headers = [], []

    def __call__(self, req, timeout):
        self.headers.append(req.get_header("Authorization"))
        if self.fail:
            raise self.fail
        path = req.full_url.split("://", 1)[1].split("/", 1)[1]
        if path == "api/config":
            body = {"unit_system": {"temperature": "°F"}}
        elif path.startswith("api/states/"):
            entity = path[len("api/states/"):]
            if entity not in self.states:
                raise urllib.error.HTTPError(req.full_url, 404, "nf", {}, None)
            body = self.states[entity]
        elif path.startswith("api/services/"):
            self.calls.append((path[len("api/services/"):], json.loads(req.data)))
            body = []
        return io.BytesIO(json.dumps(body).encode())


def state(value, **attrs):
    return {"state": value, "attributes": attrs}


def test_poll_reads_states_and_skips_missing_entities():
    fake = FakeHA({"climate.thermostat": state("heat", temperature=70, current_temperature=68.5)})
    m = Metrics()
    ha = HomeAssistant("http://ha/", "tok", ["climate.thermostat", "weather.home"], metrics=m, opener=fake)
    ha.poll()
    assert ha.connected and ha.error == ""
    assert ha.value("climate.thermostat") == "heat"
    assert ha.attrs("climate.thermostat")["current_temperature"] == 68.5
    assert ha.state("weather.home") is None
    assert fake.headers[0] == "Bearer tok"
    assert m.get("lcars_ha_up") == 1
    assert m.get("lcars_ha_requests_total", kind="state", result="404") == 1


def test_unavailable_reads_as_default():
    fake = FakeHA({"input_number.x": state("unavailable")})
    ha = HomeAssistant("http://ha", "tok", ["input_number.x"], opener=fake)
    ha.poll()
    assert ha.value("input_number.x") is None
    assert ha.number("input_number.x", 64) == 64


def test_lost_link_keeps_the_last_states():
    fake = FakeHA({"climate.thermostat": state("heat", temperature=70)})
    ha = HomeAssistant("http://ha", "tok", ["climate.thermostat"], opener=fake)
    ha.poll()
    fake.fail = OSError("down")
    ha.poll()
    assert not ha.connected and ha.error == "NO SIGNAL"
    assert ha.value("climate.thermostat") == "heat"
    fake.fail = urllib.error.HTTPError("u", 401, "no", {}, None)
    ha.poll()
    assert ha.error == "HTTP 401"


def test_thread_sends_calls_and_stops():
    fake = FakeHA({"climate.thermostat": state("heat", temperature=70)})
    ha = HomeAssistant("http://ha", "tok", ["climate.thermostat"], poll_seconds=60, opener=fake)
    ha.start()
    ha.call("climate", "set_temperature", entity_id="climate.thermostat", temperature=71)
    ha.stop()
    ha.join(5)
    assert not ha.is_alive()
    assert fake.calls == [("climate/set_temperature",
                           {"entity_id": "climate.thermostat", "temperature": 71})]
    assert ha.last_call[1] == "climate.set_temperature"
    assert ha.unit == "°F"


def test_no_token_never_talks():
    fake = FakeHA({})
    ha = HomeAssistant("http://ha", "", ["climate.thermostat"], opener=fake)
    assert ha.error == "NO TOKEN"
    ha.start()
    ha.join(5)
    assert fake.headers == []
