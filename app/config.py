"""Settings, from the environment. On brick1982 that's ~/.config/lcars/env, the
kiosk unit's EnvironmentFile (deploy/lcars.env.example lists every one); the
Home Assistant token and the code live only there, never in git."""
import os


def _str(name, default=""):
    return os.environ.get(name, default).strip()


def _bool(name, default):
    value = _str(name)
    return default if not value else value.lower() in ("1", "true", "yes", "on")


def _float(name, default):
    value = _str(name)
    return float(value) if value else default


# The official 7" panel.
RESOLUTION = (800, 480)
FULLSCREEN = _bool("LCARS_FULLSCREEN", False)
# Frames per second. The GIF gadgets step at 10, so more only costs CPU.
FPS = int(_float("LCARS_FPS", 15))
# Show the cursor and an exit button; drag widgets to print their place.
DEV_MODE = _bool("LCARS_DEV_MODE", False)
UI_PLACEMENT_MODE = _bool("LCARS_UI_PLACEMENT_MODE", False)
SOUND = _bool("LCARS_SOUND", True)
# Everything drawn is multiplied by this (1.0: the stock LCARS colours; 0.8:
# a fifth darker). Separate from the backlight, which also darkens black.
COLOUR_LEVEL = min(1.0, max(0.2, _float("LCARS_COLOUR_LEVEL", 1.0)))
# Show the thermostat, never change it: no climate control, no keypad, and
# no service calls go to Home Assistant.
READ_ONLY = _bool("LCARS_READ_ONLY", False)

# The code that opens climate control. Empty: the panel can't be opened with a
# code, only from Home Assistant (input_select.lcars_panel_lock: unlocked).
PIN = _str("LCARS_PIN")
# Back to locked after this long without a touch.
IDLE_RELOCK_SECONDS = _float("LCARS_IDLE_RELOCK_SECONDS", 120)
# Wrong codes in a row before a lockout, and the first lockout (it doubles on
# each one after, up to the maximum, until a right code).
MISSES_BEFORE_LOCKOUT = int(_float("LCARS_MISSES_BEFORE_LOCKOUT", 3))
LOCKOUT_SECONDS = _float("LCARS_LOCKOUT_SECONDS", 30)
MAX_LOCKOUT_SECONDS = _float("LCARS_MAX_LOCKOUT_SECONDS", 600)

HA_URL = _str("HA_URL", "https://homeassistant.brick.nozdormu.cloud").rstrip("/")
HA_TOKEN = _str("HA_TOKEN")
HA_POLL_SECONDS = _float("HA_POLL_SECONDS", 5)
THERMOSTAT = _str("LCARS_THERMOSTAT", "climate.thermostat")
LOCK_ENTITY = "input_select.lcars_panel_lock"
SETPOINT_MIN_ENTITY = "input_number.thermostat_setpoint_min"
SETPOINT_MAX_ENTITY = "input_number.thermostat_setpoint_max"
# Weather for this point ("lat,lon"; empty: no weather), from the National
# Weather Service, then Open-Meteo, then MET Norway (datasources/weather.py).
# Kept in the env file, not here: it's where the panel is.
WEATHER_POINT = _str("LCARS_WEATHER_POINT")
WEATHER_POLL_SECONDS = _float("LCARS_WEATHER_POLL_SECONDS", 300)
# Weather older than this is shown as stale.
WEATHER_STALE_SECONDS = _float("LCARS_WEATHER_STALE_SECONDS", 3600)

# The ecobee keeps heat and cool setpoints at least this far apart in auto.
HEAT_COOL_GAP = _float("LCARS_HEAT_COOL_GAP", 5)
# Taps on the arrows gather for this long before going to Home Assistant.
SEND_AFTER_SECONDS = _float("LCARS_SEND_AFTER_SECONDS", 1.5)

# Night ("HH:MM-HH:MM", may wrap past midnight; empty for never): the panel is
# dark and silent, and a tap wakes it, dimmed, for WAKE_SECONDS.
NIGHT = _str("LCARS_NIGHT", "21:00-07:00")
NIGHT_LEVEL = _float("LCARS_NIGHT_LEVEL", 0.08)
DAY_LEVEL = _float("LCARS_DAY_LEVEL", 1.0)
WAKE_SECONDS = _float("LCARS_WAKE_SECONDS", 60)

# Prometheus metrics on this port (0 turns them off).
METRICS_PORT = int(_float("LCARS_METRICS_PORT", 8767))
