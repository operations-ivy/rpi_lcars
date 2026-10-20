"""The brick1982 wall panel: Home Assistant's thermostat in LCARS. Settings
come from the environment (config.py)."""
import logging
import os

# Assets are loaded relative to this folder.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402
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
                       pictures=[e for e in (config.MEDIA_PLAYER, config.MEDIA_IMAGE) if e])
    ha.start()
    weather = Weather(config.WEATHER_POINT, config.WEATHER_POLL_SECONDS, metrics)
    weather.start()
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
    panel = Panel(ha, lock, night, metrics, weather=weather, room=room)
    ui = UserInterface(ScreenStatus(panel), config.RESOLUTION, config.UI_PLACEMENT_MODE, config.FPS,
                       config.DEV_MODE, config.SOUND, fullscreen=config.FULLSCREEN, panel=panel,
                       colour_level=config.COLOUR_LEVEL)
    while ui.running:
        ui.tick()
    ha.stop()
    weather.stop()


if __name__ == "__main__":
    main()
