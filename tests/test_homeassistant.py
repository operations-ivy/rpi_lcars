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
        self.items, self.item_fetches, self.picture_fetches = [], 0, 0

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
        elif path.startswith("api/services/todo/get_items"):
            self.item_fetches += 1
            entity = json.loads(req.data)["entity_id"]
            body = {"changed_states": [], "service_response": {entity: {"items": self.items}}}
        elif path.startswith("api/services/"):
            self.calls.append((path[len("api/services/"):], json.loads(req.data)))
            body = []
        elif path.startswith("api/image_proxy/"):
            self.picture_fetches += 1
            if "broken" in path:
                raise urllib.error.HTTPError(req.full_url, 500, "no image", {}, None)
            return io.BytesIO(b"JPEG" + path.encode())
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


def test_link_is_down_until_a_poll_answers():
    m = Metrics()
    HomeAssistant("http://ha", "", ["climate.thermostat"], metrics=m, opener=FakeHA({}))
    assert m.get("lcars_ha_up") == 0
    assert "lcars_ha_up 0" in m.render()


def test_todo_items_fetched_now_and_then_and_after_a_change():
    clock = [0.0]
    fake = FakeHA({"todo.shopping_list": state("1")})
    fake.items = [{"summary": "Milk", "uid": "a", "status": "needs_action"}]
    ha = HomeAssistant("http://ha", "tok", [], opener=fake, clock=lambda: clock[0], todo="todo.shopping_list")
    assert ha.items() is None
    ha.poll()
    assert ha.items() == fake.items and fake.item_fetches == 1
    ha.poll()
    assert fake.item_fetches == 1          # not every poll
    clock[0] += 30
    ha.poll()
    assert fake.item_fetches == 2
    ha.set_item_status("a", "completed")
    assert ha.items()[0]["status"] == "completed"
    ha._call("todo", "update_item", {"entity_id": "todo.shopping_list", "item": "a", "status": "completed"})
    ha.poll()
    assert fake.item_fetches == 3          # a change: at once


def test_pictures_fetched_once_per_picture_not_per_token():
    pic = "/api/image_proxy/image.now_playing?token=one"
    fake = FakeHA({"image.now_playing": state("t1", entity_picture=pic)})
    ha = HomeAssistant("http://ha", "tok", [], opener=fake, pictures=["image.now_playing"])
    ha.poll()
    assert ha.picture("image.now_playing").startswith(b"JPEG")
    assert fake.picture_fetches == 1
    fake.states["image.now_playing"] = state("t1", entity_picture=pic.replace("one", "two"))
    ha.poll()
    assert fake.picture_fetches == 1       # a new token, the same picture
    fake.states["image.now_playing"] = state("t2", entity_picture=pic)
    ha.poll()
    assert fake.picture_fetches == 2
    fake.states["image.now_playing"] = state("t2")
    ha.poll()
    assert ha.picture("image.now_playing") is None


def test_a_picture_home_assistant_cant_serve_isnt_asked_for_every_poll():
    pic = "/api/image_proxy/image.broken?token=one"
    fake = FakeHA({"image.broken": state("t1", entity_picture=pic)})
    m = Metrics()
    ha = HomeAssistant("http://ha", "tok", [], opener=fake, metrics=m, pictures=["image.broken"])
    ha.poll()
    ha.poll()
    assert ha.connected and ha.picture("image.broken") is None
    assert fake.picture_fetches == 1
    assert m.get("lcars_ha_requests_total", kind="picture", result="error") == 1
