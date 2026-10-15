"""What every screen shares: Home Assistant, the lock, night and the metrics.
The UI loop calls tick() every frame and tap() on every touch; the screens
read from it and never talk to Home Assistant themselves."""
import time

import config
from panel import lock as L
from ui.utils import sound

WEATHER_LABELS = {
    "clear-night": "CLEAR", "cloudy": "CLOUDY", "exceptional": "EXCEPTIONAL", "fog": "FOG",
    "hail": "HAIL", "lightning": "LIGHTNING", "lightning-rainy": "THUNDERSTORMS",
    "partlycloudy": "PARTLY CLOUDY", "pouring": "HEAVY RAIN", "rainy": "RAIN", "snowy": "SNOW",
    "snowy-rainy": "SLEET", "sunny": "SUNNY", "windy": "WINDY", "windy-variant": "WINDY",
}


class Panel:
    def __init__(self, ha, lock, night, metrics, cfg=config, clock=time.monotonic):
        self.ha, self.lock, self.night, self.metrics = ha, lock, night, metrics
        self.cfg, self.clock = cfg, clock

    # Touches and frames.

    def tap(self):
        """A touch. True when it only woke the dark screen: swallow it."""
        woke = self.night.tap()
        self.metrics.inc("lcars_taps_total", woke=str(woke).lower())
        if not woke:
            self.lock.touch()
        return woke

    def tick(self):
        was_unlocked = self.lock.unlocked
        self.lock.set_remote(self.ha.value(self.cfg.LOCK_ENTITY, L.NORMAL))
        reason = None
        if was_unlocked and not self.lock.unlocked:
            reason = "hard_locked"
        elif self.lock.unlocked and self.night.dark:
            self.lock.lock()
            reason = "dark"
        elif self.lock.relock_if_idle():
            reason = "idle"
        if reason:
            self.metrics.inc("lcars_relocks_total", reason=reason)
        self.night.apply()
        sound.MUTED = self.night.is_night
        self.metrics.set("lcars_backlight_level", self.night.level)
        self.metrics.set("lcars_can_change", 1 if self.lock.can_change else 0)

    # What the screens show.

    @property
    def thermostat(self):
        return self.ha.attrs(self.cfg.THERMOSTAT)

    @property
    def hvac_mode(self):
        return self.ha.value(self.cfg.THERMOSTAT)

    def guardrails(self):
        return (self.ha.number(self.cfg.SETPOINT_MIN_ENTITY, 64.0),
                self.ha.number(self.cfg.SETPOINT_MAX_ENTITY, 76.0))

    def weather(self):
        """(temperature, condition label), either may be None."""
        attrs = self.ha.attrs(self.cfg.WEATHER)
        condition = self.ha.value(self.cfg.WEATHER)
        label = WEATHER_LABELS.get(condition, condition.upper()) if condition else None
        return attrs.get("temperature"), label

    def link(self):
        """(ok, text) for the Home Assistant link line."""
        if self.ha.error:
            return False, self.ha.error
        if not self.ha.connected:
            return False, "CONNECTING"
        return True, "NOMINAL"

    # Changes, only while the lock allows them.

    def call(self, domain, service, action, **data):
        if not self.lock.can_change:
            return False
        self.ha.call(domain, service, **data)
        self.metrics.inc("lcars_commands_total", action=action)
        return True
