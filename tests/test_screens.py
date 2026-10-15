"""The screens, driven headless: a stand-in Home Assistant, a clock the test
moves, and taps posted as pygame events. LCARS_SCREENSHOTS=<dir> saves each
screen as a PNG for a look."""
import os
from datetime import datetime
from pathlib import Path

import pygame
import pytest

import config
from datasources.homeassistant import HomeAssistant
from metrics import Metrics
from panel import lock as L
from panel.context import Panel
from panel.lock import PanelLock
from panel.night import Night
from screens.status import ScreenStatus
from ui.ui import UserInterface
from ui.widgets.panel_widgets import LcarsArrow, LcarsKey, LcarsLabel
from test_weather import FakeWeb, make as make_weather

APP = Path(__file__).resolve().parent.parent / "app"
PIN = "2468"


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class FakeHA(HomeAssistant):
    """The real client's reading side over fixed states; calls are recorded."""

    def __init__(self, states):
        super().__init__("http://ha", "token", [])
        self._states = states
        self.connected, self.error = True, ""
        self.calls = []

    def call(self, domain, service, **data):
        self.calls.append((f"{domain}.{service}", data))

    def set(self, entity, value, **attrs):
        self._states[entity] = {"state": value, "attributes": attrs}


def thermostat(mode="heat", **attrs):
    base = {"current_temperature": 68.5, "current_humidity": 41, "hvac_action": "heating",
            "hvac_modes": ["off", "heat", "cool", "heat_cool"], "temperature": 70,
            "target_temp_low": None, "target_temp_high": None}
    base.update(attrs)
    return {"state": mode, "attributes": base}


class Rig:
    def __init__(self, hour=12, states=None, web=None, colour_level=1.0):
        os.chdir(APP)
        self.clock = Clock()
        self.hour = hour
        self.ha = FakeHA(states if states is not None else {
            config.THERMOSTAT: thermostat(),
            config.LOCK_ENTITY: {"state": "normal", "attributes": {}},
            config.SETPOINT_MIN_ENTITY: {"state": "64.0", "attributes": {}},
            config.SETPOINT_MAX_ENTITY: {"state": "76.0", "attributes": {}},
        })
        self.metrics = Metrics()
        self.lock = PanelLock(PIN, idle_seconds=120, clock=self.clock)
        self.night = Night("21:00-07:00", 0.08, 1.0, 60,
                           now=lambda: datetime(2026, 10, 15, self.hour, 0), clock=self.clock)
        self.web = web or FakeWeb()
        self.weather = make_weather(self.web, self.metrics)
        self.weather.poll()
        self.panel = Panel(self.ha, self.lock, self.night, self.metrics, clock=self.clock, weather=self.weather)
        self.ui = UserInterface(ScreenStatus(self.panel), (800, 480), fps=1000, audio=False, panel=self.panel,
                                colour_level=colour_level)
        self.tick()

    def tick(self, n=2):
        for _ in range(n):
            self.ui.tick()

    @property
    def screen(self):
        return self.ui.screen.name

    def sprites(self, kind):
        return [s for s in self.ui.all_sprites.sprites() if isinstance(s, kind) and s.visible]

    def key(self, text):
        matches = [s for s in self.sprites(LcarsKey) if s.text == text]
        assert matches, f"no key {text!r} on {self.screen}"
        return matches[0]

    def texts(self):
        return [s.text for s in self.sprites(LcarsLabel)]

    def tap(self, sprite_or_pos):
        pos = sprite_or_pos.rect.center if hasattr(sprite_or_pos, "rect") else sprite_or_pos
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))
        self.tick()

    def enter(self, code):
        for d in code:
            self.tap(self.key(d))
        self.tap(self.key("ENTER"))

    def shot(self, name):
        out = os.environ.get("LCARS_SCREENSHOTS")
        if out:
            self.tick(1)
            Path(out).mkdir(parents=True, exist_ok=True)
            pygame.image.save(self.ui.screenSurface, str(Path(out) / f"{name}.png"))


def quiet_web():
    """No weather alerts: most tests are about the lock, and an alert outranks it."""
    web = FakeWeb()
    web.bodies["https://api.weather.gov/alerts/active?point=39.7456,-97.0892"] = {"features": []}
    return web


@pytest.fixture
def rig():
    return Rig(web=quiet_web())


@pytest.fixture
def alert_rig():
    return Rig()


def test_status_shows_the_thermostat_and_weather(alert_rig):
    rig = alert_rig
    assert rig.screen == "status"
    texts = rig.texts()
    for expected in ("68.5°F", "HEAT", "HEATING", "70°F", "41%", "73.4°F", "CLOUDY",
                     "WEATHER ALERT: FLOOD WATCH", "HOME ASSISTANT LINK: NOMINAL", "LIMITS 64-76°F"):
        assert expected in texts, expected
    rig.shot("1-status")


def test_no_alert_shows_the_lock(rig):
    assert "CONTROLS SECURED" in rig.texts()


def test_an_alert_outranks_the_lock_line(alert_rig):
    assert "WEATHER ALERT: FLOOD WATCH" in alert_rig.texts()
    assert "TOUCH WEATHER FOR DETAILS" in alert_rig.texts()


def test_keypad_is_shuffled_and_the_code_opens_climate(rig):
    rig.tap(rig.key("CLIMATE"))
    assert rig.screen == "authorize"
    digits = [s.text for s in rig.sprites(LcarsKey) if s.text.isdigit()]
    assert sorted(digits) == list("0123456789")
    rig.tap(rig.key("1"))
    rig.tap(rig.key("2"))
    rig.shot("2-keypad")
    rig.tap(rig.key("CLEAR"))
    rig.enter(PIN)
    assert rig.screen == "climate"
    assert rig.metrics.get("lcars_unlock_attempts_total", result="granted") == 1


def test_wrong_codes_lock_the_keypad_out(rig):
    rig.tap(rig.key("CLIMATE"))
    rig.enter("1111")
    assert "ACCESS DENIED - 2 ATTEMPTS REMAIN" in rig.texts()
    rig.enter("1111")
    rig.enter("1111")
    assert "SECURITY LOCKOUT" in rig.texts()
    assert "KEYPAD RETURNS IN 0:30" in rig.texts()
    assert not rig.key("ENTER").enabled
    rig.shot("3-lockout")
    rig.clock.t += 30
    rig.tick()
    assert rig.key("ENTER").enabled
    rig.enter(PIN)
    assert rig.screen == "climate"


def unlock(rig):
    rig.tap(rig.key("CLIMATE"))
    rig.enter(PIN)
    assert rig.screen == "climate"


def test_arrow_taps_gather_then_send_once(rig):
    unlock(rig)
    up = [a for a in rig.sprites(LcarsArrow) if a.up][0]
    rig.tap(up)
    rig.tap(up)
    assert "72°F" in rig.texts()
    assert rig.ha.calls == []
    rig.shot("4-climate-heat")
    rig.clock.t += config.SEND_AFTER_SECONDS
    rig.tick()
    assert rig.ha.calls == [("climate.set_temperature",
                             {"entity_id": config.THERMOSTAT, "temperature": 72})]
    assert rig.metrics.get("lcars_commands_total", action="set_temperature") == 1
    # Shown as sent until Home Assistant agrees.
    assert "72°F" in rig.texts()
    rig.ha.set(config.THERMOSTAT, "heat", **{**thermostat()["attributes"], "temperature": 72})
    rig.tick()
    assert "72°F" in rig.texts()


def test_arrows_stop_at_the_guardrails(rig):
    rig.ha.set(config.THERMOSTAT, "heat", **{**thermostat()["attributes"], "temperature": 76})
    unlock(rig)
    up, down = sorted(rig.sprites(LcarsArrow), key=lambda a: not a.up)
    assert not up.enabled and down.enabled
    rig.tap(up)
    rig.clock.t += 5
    rig.tick()
    assert rig.ha.calls == []


def test_auto_shows_two_columns_and_keeps_the_gap(rig):
    rig.ha.set(config.THERMOSTAT, "heat_cool", **{**thermostat()["attributes"], "temperature": None,
                                                 "target_temp_low": 68, "target_temp_high": 73})
    unlock(rig)
    assert "HEAT TO" in rig.texts() and "COOL TO" in rig.texts()
    rig.shot("5-climate-auto")
    heat_up = min((a for a in rig.sprites(LcarsArrow) if a.up), key=lambda a: a.rect.left)
    rig.tap(heat_up)
    rig.clock.t += config.SEND_AFTER_SECONDS
    rig.tick()
    assert rig.ha.calls == [("climate.set_temperature", {"entity_id": config.THERMOSTAT,
                                                         "target_temp_low": 69, "target_temp_high": 74})]


def test_mode_buttons(rig):
    unlock(rig)
    rig.tap(rig.key("COOL"))
    assert rig.ha.calls == [("climate.set_hvac_mode", {"entity_id": config.THERMOSTAT, "hvac_mode": "cool"})]
    assert "SETTING COOL" in rig.texts()
    rig.tap(rig.key("COOL"))  # already asked
    assert len(rig.ha.calls) == 1


def test_off_shows_no_setpoints(rig):
    rig.ha.set(config.THERMOSTAT, "off", **{**thermostat()["attributes"], "temperature": None,
                                           "hvac_action": "off"})
    unlock(rig)
    assert rig.sprites(LcarsArrow) == []
    assert "SYSTEM OFF - SELECT A MODE" in rig.texts()


def test_idle_relocks_and_sends_nothing_after(rig):
    unlock(rig)
    rig.clock.t += 120
    rig.tick()
    assert rig.screen == "status"
    assert rig.metrics.get("lcars_relocks_total", reason="idle") == 1
    rig.tap(rig.key("CLIMATE"))
    assert rig.screen == "authorize"


def test_secure_button_flushes_and_locks(rig):
    unlock(rig)
    rig.tap([a for a in rig.sprites(LcarsArrow) if a.up][0])
    rig.tap(rig.key("SECURE"))
    assert rig.screen == "status"
    assert rig.ha.calls == [("climate.set_temperature", {"entity_id": config.THERMOSTAT, "temperature": 71})]
    assert not rig.lock.can_change


def test_home_assistant_hard_lock(rig):
    unlock(rig)
    rig.ha.set(config.LOCK_ENTITY, "hard_locked")
    rig.tick()
    assert rig.screen == "status"
    assert "CONTROLS LOCKED BY HOME ASSISTANT" in rig.texts()
    assert rig.metrics.get("lcars_relocks_total", reason="hard_locked") == 1
    rig.shot("6-status-hard-locked")
    rig.tap(rig.key("CLIMATE"))
    assert rig.screen == "authorize"
    assert "LOCKED BY HOME ASSISTANT" in rig.texts()
    assert not rig.key("ENTER").enabled


def test_home_assistant_unlock_needs_no_code(rig):
    rig.ha.set(config.LOCK_ENTITY, "unlocked")
    rig.tick()
    assert "CONTROLS OPEN" in rig.texts()
    rig.tap(rig.key("CLIMATE"))
    assert rig.screen == "climate"


def test_night_first_tap_only_wakes():
    rig = Rig(hour=23, web=quiet_web())
    assert rig.night.dark
    climate = rig.key("CLIMATE")
    rig.tap(climate)
    assert rig.screen == "status"          # swallowed
    assert not rig.night.dark
    assert rig.metrics.get("lcars_taps_total", woke="true") == 1
    rig.tap(climate)
    assert rig.screen == "authorize"       # now a real press
    rig.enter(PIN)
    assert rig.screen == "climate"
    rig.clock.t += 61                      # back to dark: locked, home
    rig.tick()
    assert rig.screen == "status"
    assert rig.metrics.get("lcars_relocks_total", reason="dark") == 1
    assert rig.metrics.get("lcars_backlight_level") == 0


def test_no_home_assistant_yet():
    rig = Rig(states={}, web=quiet_web())
    rig.ha.connected, rig.ha.error = False, "NO SIGNAL"
    rig.tick()
    assert "HOME ASSISTANT LINK: NO SIGNAL" in rig.texts()
    assert "--" in rig.texts()
    rig.shot("7-status-no-signal")


def test_weather_screen():
    rig = Rig()
    rig.tap(rig.key("WEATHER"))
    assert rig.screen == "weather"
    texts = rig.texts()
    for expected in ("73.4°F", "CLOUDY", "HUMIDITY 78%   WIND ENE 9 MPH", "FLOOD WATCH UNTIL 10 PM",
                     "TODAY", "72°F", "CHANCE RAIN SHOWERS", "27% RAIN", "TONIGHT", "WEATHER VIA NWS - JUST NOW"):
        assert expected in texts, expected
    rig.shot("8-weather")
    rig.tap(rig.key("STATUS"))
    assert rig.screen == "status"


def test_weather_on_a_backup_says_alerts_are_unknown():
    web = FakeWeb()
    web.down.add("api.weather.gov")
    rig = Rig(web=web)
    rig.tap(rig.key("WEATHER"))
    texts = rig.texts()
    assert "UNAVAILABLE" in texts and "NATIONAL WEATHER SERVICE OFFLINE" in texts
    assert "WEATHER VIA OPEN-METEO - JUST NOW" in texts
    rig.shot("9-weather-backup")


def test_all_weather_down_is_graceful():
    web = FakeWeb()
    web.down |= {"api.weather.gov", "api.open-meteo.com", "api.met.no"}
    rig = Rig(web=web)
    assert "WEATHER ALERTS UNAVAILABLE" in rig.texts() or "CONTROLS SECURED" in rig.texts()
    rig.tap(rig.key("WEATHER"))
    texts = rig.texts()
    assert "WEATHER UNAVAILABLE" in texts and "WEATHER: ALL SOURCES OFFLINE" in texts
    rig.shot("10-weather-offline")


def test_read_only_never_opens_climate(monkeypatch):
    monkeypatch.setattr(config, "READ_ONLY", True)
    rig = Rig()
    rig.ha.set(config.LOCK_ENTITY, "unlocked")  # even Home Assistant's override
    rig.tick()
    texts = rig.texts()
    assert "THERMOSTAT MONITOR ONLY - CONTROLS DISABLED" in texts
    assert "WEATHER ALERT: FLOOD WATCH" in texts
    monitor = rig.key("MONITOR ONLY")
    rig.tap(monitor)
    assert rig.screen == "status"
    assert not [k for k in rig.sprites(LcarsKey) if k.text == "CLIMATE"]
    assert rig.panel.call("climate", "set_temperature", "set_temperature", temperature=71) is False
    assert rig.ha.calls == []
    rig.shot("11-status-read-only")


def test_colour_level_darkens_the_frame():
    # pygame has one display surface: read each rig's frame before the next.
    b = Rig().ui.screenSurface.get_at((60, 300))[:3]
    d = Rig(colour_level=0.8).ui.screenSurface.get_at((60, 300))[:3]
    assert all(abs(dv - round(bv * 204 / 255)) <= 1 for bv, dv in zip(b, d)), (b, d)
