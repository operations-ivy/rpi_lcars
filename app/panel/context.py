"""What every screen shares: Home Assistant, the weather, the homelab's feeds
(alerts, wigle-sync), the lock, night and the metrics.
The UI loop calls tick() every frame and tap() on every touch; the screens
read from it and never talk to Home Assistant themselves."""
import time

import config
from datasources import calendar as cal
from panel import infra
from panel import lock as L
from panel.night import sun_times
from ui.utils import sound

class Panel:
    def __init__(self, ha, lock, night, metrics, cfg=config, clock=time.monotonic, weather=None, room=None,
                 feeds=None, now=time.time):
        self.ha, self.lock, self.night, self.metrics = ha, lock, night, metrics
        self.cfg, self.clock, self.weather, self.room = cfg, clock, weather, room
        self.feeds = feeds or {}  # "prometheus", "overwatch", "wigle": datasources.feeds.JsonFeed; "news": datasources.news.NewsFeed
        self.now = now

    @property
    def read_only(self):
        return self.cfg.READ_ONLY

    # The homelab's feeds.

    def feed_age(self, name):
        """Seconds since the feed last answered; None if it never has or
        there's no such feed."""
        feed = self.feeds.get(name)
        return feed.age() if feed else None

    def feed_stale(self, name):
        age = self.feed_age(name)
        return age is None or age > self.cfg.FEED_STALE_SECONDS

    def alerts(self):
        """{"infra": [...] or None, "watch": {...} or None, "condition"}
        (panel/infra.py). A feed that's off or stale reads as None."""
        # Every frame asks (the ALERTS block's colour): work it out again only
        # when a feed answers, or every 10 s as overwatch's alerts age.
        key = (tuple(f.updated for f in self.feeds.values()), int(self.now() // 10))
        if getattr(self, "_alerts_key", None) == key:
            return self._alerts

        def data(name):
            feed = self.feeds.get(name)
            return None if feed is None or self.feed_stale(name) else feed.data
        found = infra.infra_alerts(data("prometheus"))
        watch = infra.overwatch(data("overwatch"), self.now())
        self._alerts_key = key
        self._alerts = {"infra": found, "watch": watch, "condition": infra.condition(found, watch)}
        return self._alerts

    def wigle(self):
        """wigle-sync's status (panel/infra.py), or None before an answer."""
        feed = self.feeds.get("wigle")
        return infra.wigle(feed.data if feed else None, self.now())

    def headline(self):
        """(item, number, of) for the headline to show now, each held for
        NEWS_CYCLE_SECONDS; None before the feed has answered."""
        feed = self.feeds.get("news")
        items = (feed.data if feed else None) or []
        if not items:
            return None
        i = int(self.now() // self.cfg.NEWS_CYCLE_SECONDS) % len(items)
        return items[i], i + 1, len(items)

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

    def outside(self):
        """(temperature, condition), either may be None."""
        current = self.weather.current() if self.weather else {}
        return current.get("temperature"), current.get("condition")

    def room_reading(self):
        """(°F, humidity) from the room sensor, or None without a sensor or
        while it's offline."""
        if self.room is None or not self.room.fresh():
            return None
        return self.room.temperature, self.room.humidity

    def house(self):
        """(upstairs, downstairs, average) in Home Assistant's unit, each None
        when missing: upstairs is the room sensor (it reads °F), downstairs
        the ecobee. No average from one floor alone."""
        room = self.room_reading()
        up = None if room is None else (room[0] - 32) * 5 / 9 if self.ha.unit == "°C" else room[0]
        down = self.thermostat.get("current_temperature")
        return up, down, None if up is None or down is None else (up + down) / 2

    def house_note(self):
        """Why there's no average, or ""."""
        up, down, _ = self.house()
        if up is None:
            return "NO UPSTAIRS SENSOR" if self.room is None else "UPSTAIRS SENSOR OFFLINE"
        return "NO THERMOSTAT READING" if down is None else ""

    def weather_stale(self):
        age = self.weather.age() if self.weather else None
        return age is None or age > self.cfg.WEATHER_STALE_SECONDS

    def alert_line(self):
        """(text, colour kind) for the weather alerts: "alert", "ok" or "unknown"."""
        alerts = self.weather.alerts() if self.weather else None
        if alerts is None:
            return "UNAVAILABLE", "unknown"
        if not alerts:
            return "NONE ACTIVE", "ok"
        more = f" +{len(alerts) - 1}" if len(alerts) > 1 else ""
        return f"{alerts[0]['event']}{more}", "alert"

    def link(self):
        """(ok, text) for the Home Assistant link line."""
        if self.ha.error:
            return False, self.ha.error
        if not self.ha.connected:
            return False, "CONNECTING"
        return True, "NOMINAL"

    def network(self):
        """(text, ok) for the internet, or None without a WAN entity."""
        if not self.cfg.WAN_ENTITY:
            return None
        state = self.ha.value(self.cfg.WAN_ENTITY)
        if state is None:
            return "--", True
        return ("ONLINE", True) if state == "on" else ("OFFLINE", False)

    def sun_line(self):
        """"SETS 18:24" while the sun is up, "RISES 07:23" while it's down;
        None until Home Assistant has said."""
        state = self.ha.value(self.cfg.SUN_ENTITY)
        times = sun_times(self.ha.attrs(self.cfg.SUN_ENTITY))
        word, key = ("SETS", "sunset") if state == "above_horizon" else ("RISES", "sunrise")
        if state is None or key not in times:
            return None
        return f"{word} {times[key]:%H:%M}"

    def shopping(self):
        """The shopping list: open items first, then the ticked ones; None
        before Home Assistant has sent it."""
        items = self.ha.items()
        if items is None:
            return None
        return ([i for i in items if i.get("status") != "completed"]
                + [i for i in items if i.get("status") == "completed"])

    def calendar(self):
        """(events, stale) for the CALENDAR screen (datasources/calendar.py's
        parse()), or None before the calendars have answered."""
        events = self.ha.events()
        if events is None:
            return None
        age = self.ha.events_age()
        return events, age is None or age > self.cfg.CALENDAR_STALE_SECONDS

    def upcoming(self):
        """Today's and tomorrow's events still to come, for STATUS:
        [(day, [entry])] (datasources/calendar.py's agenda()); [] without
        calendars or before they've answered."""
        events = self.ha.events() if self.cfg.CALENDARS else None
        return cal.agenda(events, self.ha.now(), 2) if events else []

    def media(self):
        """The console: {"state", "title", "picture"}; picture is image bytes
        or None. The player's own picture while it has one, else the game
        last played."""
        player, image = self.cfg.MEDIA_PLAYER, self.cfg.MEDIA_IMAGE
        attrs = self.ha.attrs(player)
        picture = self.ha.picture(player) or (self.ha.picture(image) if image else None)
        return {"state": self.ha.value(player), "title": attrs.get("media_title"), "picture": picture}

    # Changes, only while the lock allows them.

    def call(self, domain, service, action, **data):
        if self.read_only or not self.lock.can_change:
            return False
        self.ha.call(domain, service, **data)
        self.metrics.inc("lcars_commands_total", action=action)
        return True

    def tick_item(self, item):
        """Tick a shopping list item off, or back on. Not the thermostat, so
        neither the lock nor read-only applies."""
        status = "needs_action" if item.get("status") == "completed" else "completed"
        self.ha.call("todo", "update_item", entity_id=self.cfg.SHOPPING_LIST, item=item["uid"], status=status)
        self.ha.set_item_status(item["uid"], status)
        self.metrics.inc("lcars_commands_total", action="shopping_item")
        return status
