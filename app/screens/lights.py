"""The lights: one row per Home Assistant light (a Hue bulb, or a room or
group, which Hue's integration also makes a light.*), named as Home
Assistant names it, with its state and brightness, - and + for brightness,
and a key that turns it on or off. Which lights is LCARS_LIGHTS.

Like THERMOSTAT, the controls work only while the lock allows it: otherwise
they're greyed out and the sidebar's UNLOCK opens the keypad (SECURE locks
it again); on a read-only panel nothing is sent. On and off go at once;
brightness taps show at once and gather for SEND_AFTER_SECONDS before one
call goes to Home Assistant. What we sent shows until Home Assistant
reports it (or CONFIRM_SECONDS pass)."""
from screens.base import LEFT, RIGHT, TOP, PanelScreen
from ui import colours
from ui.utils.sound import Sound
from ui.widgets.panel_widgets import LcarsHeader, LcarsKey, LcarsLabel

CONFIRM_SECONDS = 15
MAX_ROWS, ROW_TOP, ROW_HEIGHT = 5, TOP + 50, 56
KEY_HEIGHT = 40
STEP_SIZE, TOGGLE_SIZE, KEY_GAP = (60, KEY_HEIGHT), (96, KEY_HEIGHT), 8
TOGGLE_X = RIGHT - TOGGLE_SIZE[0]
PLUS_X = TOGGLE_X - KEY_GAP - STEP_SIZE[0]
MINUS_X = PLUS_X - KEY_GAP - STEP_SIZE[0]
STATE_X = MINUS_X - 16          # the state's right edge
NAME_WIDTH = 250
BRIGHTNESS_STEP = 10            # percent a tap


def light_name(entity, attrs):
    return (attrs.get("friendly_name") or entity.split(".", 1)[-1].replace("_", " ")).upper()


def brightness_pct(attrs):
    """Home Assistant's 0-255 as a percent; None when it has none (off, or
    an on/off-only light)."""
    b = attrs.get("brightness")
    return None if b is None else round(b * 100 / 255)


class Row:
    def __init__(self, screen, top):
        self.name = screen.add(LcarsLabel(colours.BEIGE, (top + 8, LEFT), "", 1.3, max_width=NAME_WIDTH))
        self.state = screen.add(LcarsLabel(colours.BLUE, (top + 10, STATE_X), "", 1.2, "right"))
        self.minus = screen.add(LcarsKey(colours.ORANGE, (top, MINUS_X), STEP_SIZE, "-", screen.dim,
                                         text_size=1.6, pill=True), layer=2)
        self.plus = screen.add(LcarsKey(colours.ORANGE, (top, PLUS_X), STEP_SIZE, "+", screen.brighten,
                                        text_size=1.6, pill=True), layer=2)
        self.toggle = screen.add(LcarsKey(colours.GREY_BLUE, (top, TOGGLE_X), TOGGLE_SIZE, "OFF", screen.toggle,
                                          text_size=1.2, pill=True), layer=2)
        self.entity = None
        for key in (self.minus, self.plus, self.toggle):
            key.row = self

    def widgets(self):
        return self.name, self.state, self.minus, self.plus, self.toggle

    def hide(self):
        self.entity = None
        for w in self.widgets():
            w.visible = False


class ScreenLights(PanelScreen):
    name = "lights"

    @property
    def editable(self):
        return not self.panel.read_only and self.panel.lock.can_change

    @property
    def title(self):
        return "LIGHTING CONTROL"

    def build(self):
        self.action_key = None if self.panel.read_only else self.nav(("UNLOCK", self.unlock, colours.GOLD))
        if self.action_key is None:
            self.nav()
        self.add(LcarsHeader(colours.ORANGE, (TOP + 10, LEFT), RIGHT - LEFT, "LIGHTS", 1.5))
        self.rows = [Row(self, ROW_TOP + i * ROW_HEIGHT) for i in range(MAX_ROWS)]
        self.message = self.add(LcarsLabel(colours.GREY_BLUE, (ROW_TOP + 10, LEFT), "", 1.3))
        self.detail = self.add(LcarsLabel(colours.GREY_BLUE, (ROW_TOP + 40, LEFT), "", 1.0,
                                          max_width=RIGHT - LEFT))
        self.more = self.add(LcarsLabel(colours.GREY_BLUE, (ROW_TOP + MAX_ROWS * ROW_HEIGHT, LEFT), "", 1.0))
        self.pending, self.pending_at = {}, 0.0   # entity: brightness percent, not sent yet
        self.sent = {}                            # entity: ({"on", "pct"}, when), not yet reported back
        self.sound_limit = Sound("assets/audio/deny_1.wav")
        self.sound_sent = Sound("assets/audio/executed.wav")

    # What to show: Home Assistant's state, overlaid with ours in flight.

    def shown(self, entity):
        """{"on", "pct", "available"} for a light, or None before Home
        Assistant has answered for it."""
        state = self.panel.ha.state(entity)
        if state is None:
            return None
        attrs = state.get("attributes") or {}
        value = state.get("state")
        out = {"on": value == "on", "pct": brightness_pct(attrs),
               "available": value in ("on", "off"), "name": light_name(entity, attrs)}
        sent = self.sent.get(entity)
        if sent:
            out.update(sent[0])
        if entity in self.pending:
            out.update(on=True, pct=self.pending[entity])
        return out

    # Taps.

    def toggle(self, key, event, clock):
        entity = key.row.entity
        light = entity and self.shown(entity)
        if not light or not light["available"] or not self.editable:
            return
        self.pending.pop(entity, None)
        if self.panel.call("light", "toggle", "light_toggle", entity_id=entity):
            self.sent[entity] = ({"on": not light["on"]}, self.panel.clock())
            self.sound_sent.play()

    def dim(self, key, event, clock):
        self.step(key.row.entity, -BRIGHTNESS_STEP)

    def brighten(self, key, event, clock):
        self.step(key.row.entity, BRIGHTNESS_STEP)

    def step(self, entity, delta):
        light = entity and self.shown(entity)
        if not light or not light["available"] or not self.editable:
            return
        now = light["pct"] if light["on"] and light["pct"] is not None else 0
        pct = min(100, max(BRIGHTNESS_STEP, now + delta))   # - stops at the lowest step; off is the toggle
        if pct == now:
            self.sound_limit.play()
            return
        self.pending[entity] = pct
        self.pending_at = self.panel.clock()

    def flush(self):
        """Send the gathered brightness taps now."""
        if not self.editable:
            self.pending = {}
        for entity, pct in self.pending.items():
            if self.panel.call("light", "turn_on", "light_brightness", entity_id=entity, brightness_pct=pct):
                self.sent[entity] = ({"on": True, "pct": pct}, self.panel.clock())
                self.sound_sent.play()
        self.pending = {}

    def unlock(self, *_):
        self.go_authorize_for("lights")

    def secure(self, *_):
        self.flush()
        self.panel.lock.lock()
        self.panel.metrics.inc("lcars_relocks_total", reason="button")
        self.go_status()

    def leave(self):
        self.flush()

    # Every frame.

    def refresh(self):
        p = self.panel
        editable = self.editable
        if not editable:
            self.pending = {}
        if self.action_key is not None:
            text, handler, colour = ("SECURE", self.secure, colours.RED_BROWN) if editable \
                else ("UNLOCK", self.unlock, colours.GOLD)
            self.action_key.set_text(text)
            self.action_key.set_colour(colour)
            self.action_key.handler = handler
        now = p.clock()
        if self.pending and now - self.pending_at >= p.cfg.SEND_AFTER_SECONDS:
            self.flush()
        self.forget_confirmed(now)

        lights = p.cfg.LIGHTS
        if not lights:
            self.message.set("NO LIGHTS CONFIGURED", colours.ORANGE)
            self.detail.set("ADD HOME ASSISTANT LIGHTS TO LCARS_LIGHTS")
        elif not p.link()[0]:
            self.message.set("HOME ASSISTANT OFFLINE", colours.ORANGE)
            self.detail.set("")
        else:
            self.message.set("")
            self.detail.set("")
        show = lights if lights and p.link()[0] else []
        for i, row in enumerate(self.rows):
            if i < len(show):
                self.show_row(row, show[i], editable)
            else:
                row.hide()
        extra = len(show) - MAX_ROWS
        self.more.set(f"+{extra} MORE IN LCARS_LIGHTS (THE FIRST {MAX_ROWS} SHOWN)" if extra > 0 else "")

    def show_row(self, row, entity, editable):
        row.entity = entity
        for w in row.widgets():
            w.visible = True
        light = self.shown(entity)
        if light is None:
            row.name.set(light_name(entity, {}), colours.GREY_BLUE)
            row.state.set("--", colours.GREY_BLUE)
            usable = False
        elif not light["available"]:
            row.name.set(light["name"], colours.GREY_BLUE)
            row.state.set("UNAVAILABLE", colours.RED)
            usable = False
        else:
            row.name.set(light["name"], colours.BEIGE)
            if light["on"]:
                row.state.set("ON" if light["pct"] is None else f"ON {light['pct']}%", colours.GOLD)
            else:
                row.state.set("OFF", colours.GREY_BLUE)
            usable = True
        on = bool(light and light["on"])
        row.toggle.set_text("ON" if on else "OFF")
        row.toggle.set_colour(colours.GOLD if on else colours.GREY_BLUE)
        for key in (row.minus, row.plus, row.toggle):
            key.set_enabled(editable and usable)

    def forget_confirmed(self, now):
        """Drop what we sent once Home Assistant shows it, or it's too old."""
        for entity, (values, at) in list(self.sent.items()):
            state = self.panel.ha.state(entity) or {}
            attrs = state.get("attributes") or {}
            reported = {"on": state.get("state") == "on", "pct": brightness_pct(attrs)}
            if now - at >= CONFIRM_SECONDS or all(reported.get(k) == v for k, v in values.items()):
                del self.sent[entity]
