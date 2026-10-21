"""The brick1982 wall panel: Home Assistant's thermostat in LCARS. Settings
come from the environment (config.py)."""
import logging
import os

# Assets are loaded relative to this folder.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402
from datasources.feeds import JsonFeed  # noqa: E402
from datasources.news import NewsFeed  # noqa: E402
from datasources.homeassistant import HomeAssistant  # noqa: E402
from datasources.room import Room  # noqa: E402
from datasources.weather import Weather  # noqa: E402
from metrics import Metrics  # noqa: E402
from panel.context import Panel  # noqa: E402
from panel.lock import PanelLock  # noqa: E402
from panel.night import Backlight, Night, sun_times  # noqa: E402
from screens.status import ScreenStatus  # noqa: E402
from ui.ui import UserInterface  # noqa: E402


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    metrics = Metrics()
    entities = [config.THERMOSTAT, config.LOCK_ENTITY, config.SETPOINT_MIN_ENTITY,
                config.SETPOINT_MAX_ENTITY, config.SUN_ENTITY, config.WAN_ENTITY, config.MEDIA_PLAYER]
    ha = HomeAssistant(config.HA_URL, config.HA_TOKEN, [e for e in entities if e],
                       config.HA_POLL_SECONDS, metrics, todo=config.SHOPPING_LIST or None,
                       pictures=[e for e in (config.MEDIA_PLAYER, config.MEDIA_IMAGE) if e],
                       calendars=config.CALENDARS, calendar_seconds=config.CALENDAR_POLL_SECONDS,
                       calendar_days=config.CALENDAR_DAYS)
    ha.start()
    weather = Weather(config.WEATHER_POINT, config.WEATHER_POLL_SECONDS, metrics)
    weather.start()
    feeds = {}
    for name, url, seconds in (
            ("prometheus", config.PROMETHEUS_URL and config.PROMETHEUS_URL + "/api/v1/alerts", config.ALERTS_POLL_SECONDS),
            ("overwatch", config.OVERWATCH_URL and config.OVERWATCH_URL + "/api/state", config.ALERTS_POLL_SECONDS),
            ("wigle", config.WIGLE_URL and config.WIGLE_URL + "/api/status", config.WIGLE_POLL_SECONDS)):
        if url:
            feeds[name] = JsonFeed(name, url, seconds, metrics)
            feeds[name].start()
    if config.NEWS_URL:
        feeds["news"] = NewsFeed("news", config.NEWS_URL, config.NEWS_POLL_SECONDS, metrics, config.NEWS_COUNT)
        feeds["news"].start()
    room = None
    if config.ROOM_SENSOR:
        room = Room(config.ROOM_I2C_BUS, config.ROOM_I2C_ADDRESS, config.ROOM_OFFSET, metrics=metrics)
        room.start()
    if config.METRICS_PORT:
        metrics.serve(config.METRICS_PORT, documents={"/room.json": room.document} if room else None)
    lock = PanelLock(config.PIN, config.IDLE_RELOCK_SECONDS, config.MISSES_BEFORE_LOCKOUT,
                     config.LOCKOUT_SECONDS, config.MAX_LOCKOUT_SECONDS)
    night = Night(config.NIGHT, config.NIGHT_LEVEL, config.DAY_LEVEL, config.WAKE_SECONDS, Backlight(),
                  sun=lambda: sun_times(ha.attrs(config.SUN_ENTITY)))
    panel = Panel(ha, lock, night, metrics, weather=weather, room=room, feeds=feeds)
    ui = UserInterface(ScreenStatus(panel), config.RESOLUTION, config.UI_PLACEMENT_MODE, config.FPS,
                       config.DEV_MODE, config.SOUND, fullscreen=config.FULLSCREEN, panel=panel,
                       colour_level=config.COLOUR_LEVEL)
    while ui.running:
        ui.tick()
    ha.stop()
    weather.stop()


if __name__ == "__main__":
    main()
