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
# no thermostat service calls go to Home Assistant. (The shopping list can
# still be ticked off: that's not the thermostat.)
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
# Sunrise and sunset (the STATUS screen, and "sunset"/"sunrise" in NIGHT).
SUN_ENTITY = "sun.sun"
# The internet: a connectivity binary_sensor (empty: no NETWORK row).
WAN_ENTITY = _str("LCARS_WAN_ENTITY", "binary_sensor.verizon_router_wan_status")
# The SHOPPING screen's to-do list (empty: no SHOPPING button). Tapping an
# item ticks it off.
SHOPPING_LIST = _str("LCARS_SHOPPING_LIST", "todo.shopping_list")
# The PS5 screen (empty: no PS5 button): the console, and an image entity with
# the game last played (the PlayStation Network integration's "Now playing").
MEDIA_PLAYER = _str("LCARS_MEDIA_PLAYER", "media_player.playstation_5")
MEDIA_IMAGE = _str("LCARS_MEDIA_IMAGE", "image.living_room_ps5_pw_now_playing")
# The PS5 button is off for now: the sidebar holds every button, and it was
# too crowded with it. True brings it back (the screen is unchanged).
MEDIA_BUTTON = _bool("LCARS_MEDIA_BUTTON", False)
# The CALENDAR screen: Home Assistant calendar entities, comma separated
# (empty: no CALENDAR button), e.g. Google Calendar through HA's integration;
# Google's sign-in stays in HA. This month and the MONTHS - 1 after it, read
# every POLL; STATUS shows today's and tomorrow's.
CALENDARS = [c.strip() for c in _str("LCARS_CALENDARS").split(",") if c.strip()]
CALENDAR_MONTHS = max(1, int(_float("LCARS_CALENDAR_MONTHS", 2)))
CALENDAR_POLL_SECONDS = _float("LCARS_CALENDAR_POLL_SECONDS", 300)
# Events older than this are shown as stale (HA or Google down).
CALENDAR_STALE_SECONDS = _float("LCARS_CALENDAR_STALE_SECONDS", 1800)
# Weather for this point ("lat,lon"; empty: no weather), from the National
# Weather Service, then Open-Meteo, then MET Norway (datasources/weather.py).
# Kept in the env file, not here: it's where the panel is.
WEATHER_POINT = _str("LCARS_WEATHER_POINT")
WEATHER_POLL_SECONDS = _float("LCARS_WEATHER_POLL_SECONDS", 300)
# Weather older than this is shown as stale.
WEATHER_STALE_SECONDS = _float("LCARS_WEATHER_STALE_SECONDS", 3600)

# The ALERTS screen: Prometheus' firing alerts (the homelab's infrastructure)
# and overwatch's feeds (Bluetooth, Wi-Fi, UPnP). Empty turns either off; both
# empty, no ALERTS button.
PROMETHEUS_URL = _str("LCARS_PROMETHEUS_URL", "https://prometheus.brick.nozdormu.cloud").rstrip("/")
OVERWATCH_URL = _str("LCARS_OVERWATCH_URL", "https://overwatch.brick.nozdormu.cloud").rstrip("/")
ALERTS_POLL_SECONDS = _float("LCARS_ALERTS_POLL_SECONDS", 30)
# The WIGLE screen: wigle-sync's runs and the WiGLE account, from
# wigle-console's /api/status (empty: no WIGLE button). It takes ~10 s cold.
WIGLE_URL = _str("LCARS_WIGLE_URL", "https://wigle.brick.nozdormu.cloud").rstrip("/")
WIGLE_POLL_SECONDS = _float("LCARS_WIGLE_POLL_SECONDS", 120)
# Headlines under the house average on STATUS: an RSS feed's top items, one
# at a time (empty, the default: no headlines). Titles only, never links.
# The Guardian's US news was dropped (2026-10-22): too depressing.
NEWS_URL = _str("LCARS_NEWS_URL")
NEWS_SOURCE = _str("LCARS_NEWS_SOURCE", "HEADLINES").upper()
NEWS_POLL_SECONDS = _float("LCARS_NEWS_POLL_SECONDS", 900)
NEWS_COUNT = int(_float("LCARS_NEWS_COUNT", 3))
NEWS_CYCLE_SECONDS = _float("LCARS_NEWS_CYCLE_SECONDS", 15)
# A feed older than this is shown as stale.
FEED_STALE_SECONDS = _float("LCARS_FEED_STALE_SECONDS", 600)

# The room's own sensor (datasources/room.py): an SHT3x on the Pi's I2C bus.
# Off unless LCARS_ROOM_SENSOR=true. The Pi warms the air near it: OFFSET (°F)
# corrects that, measured once against a thermometer.
ROOM_SENSOR = _bool("LCARS_ROOM_SENSOR", False)
ROOM_I2C_BUS = int(_float("LCARS_ROOM_I2C_BUS", 1))
ROOM_I2C_ADDRESS = int(_str("LCARS_ROOM_I2C_ADDRESS", "0x44"), 0)
ROOM_OFFSET = _float("LCARS_ROOM_OFFSET", 0)

# The ecobee keeps heat and cool setpoints at least this far apart in auto.
HEAT_COOL_GAP = _float("LCARS_HEAT_COOL_GAP", 5)
# Taps on the arrows gather for this long before going to Home Assistant.
SEND_AFTER_SECONDS = _float("LCARS_SEND_AFTER_SECONDS", 1.5)

# Night ("HH:MM-HH:MM", may wrap past midnight; either end may be "sunset" or
# "sunrise"; empty for never): the panel is dark and silent, and a tap wakes
# it, dimmed, for WAKE_SECONDS.
NIGHT = _str("LCARS_NIGHT", "21:00-07:00")
NIGHT_LEVEL = _float("LCARS_NIGHT_LEVEL", 0.08)
DAY_LEVEL = _float("LCARS_DAY_LEVEL", 1.0)
WAKE_SECONDS = _float("LCARS_WAKE_SECONDS", 60)

# Prometheus metrics on this port (0 turns them off).
METRICS_PORT = int(_float("LCARS_METRICS_PORT", 8767))
