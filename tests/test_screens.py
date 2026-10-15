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
    def __init__(self, hour=12, states=None):
        os.chdir(APP)
        self.clock = Clock()
        self.hour = hour
        self.ha = FakeHA(states if states is not None else {
            config.THERMOSTAT: thermostat(),
            config.WEATHER: {"state": "partlycloudy", "attributes": {"temperature": 54}},
            config.LOCK_ENTITY: {"state": "normal", "attributes": {}},
            config.SETPOINT_MIN_ENTITY: {"state": "64.0", "attributes": {}},
            config.SETPOINT_MAX_ENTITY: {"state": "76.0", "attributes": {}},
        })
        self.metrics = Metrics()
        self.lock = PanelLock(PIN, idle_seconds=120, clock=self.clock)
        self.night = Night("21:00-07:00", 0.08, 1.0, 60,
                           now=lambda: datetime(2026, 10, 15, self.hour, 0), clock=self.clock)
        self.panel = Panel(self.ha, self.lock, self.night, self.metrics, clock=self.clock)
        self.ui = UserInterface(ScreenStatus(self.panel), (800, 480), fps=1000, audio=False, panel=self.panel)
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


@pytest.fixture
def rig():
    return Rig()


def test_status_shows_the_thermostat_and_weather(rig):
    assert rig.screen == "status"
    texts = rig.texts()
    for expected in ("68.5°F", "HEAT", "HEATING", "70°F", "41%", "54°F", "PARTLY CLOUDY",
                     "CONTROLS SECURED", "HOME ASSISTANT LINK: NOMINAL", "LIMITS 64-76°F"):
        assert expected in texts, expected
    rig.shot("1-status")


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
    rig = Rig(hour=23)
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
    rig = Rig(states={})
    rig.ha.connected, rig.ha.error = False, "NO SIGNAL"
    rig.tick()
    assert "HOME ASSISTANT LINK: NO SIGNAL" in rig.texts()
    assert "--" in rig.texts()
    rig.shot("7-status-no-signal")
