"""Climate control, open only while the lock allows it. Mode buttons along the
top; one setpoint column (heat or cool) or two (auto), each with drawn
arrows. Arrow taps show at once and gather for SEND_AFTER_SECONDS before one
call goes to Home Assistant; a sent value shows until Home Assistant reports
it (or CONFIRM_SECONDS pass)."""
from panel.thermostat import ACTION_LABELS, MODE_LABELS, MODES, fmt_temp, step, targets
from screens.base import LEFT, RIGHT, TOP, PanelScreen
from ui import colours
from ui.utils.sound import Sound
from ui.widgets.panel_widgets import LcarsArrow, LcarsKey, LcarsLabel

CONFIRM_SECONDS = 15
MODE_SIZE, MODE_GAP = (112, 44), 10
ARROW_SIZE = (120, 58)
# Column centres: one setpoint, or auto's heat and cool.
SINGLE_X, AUTO_X = 455, (330, 580)
TARGET_LABELS = {"temperature": None, "target_temp_low": "HEAT TO", "target_temp_high": "COOL TO"}


class Column:
    """A setpoint's label, arrows and value."""

    def __init__(self, screen, centre_x):
        left = centre_x - ARROW_SIZE[0] // 2
        self.label = screen.add(LcarsLabel(colours.PURPLE, (TOP + 62, centre_x), "", 1.2, "center"))
        self.up = screen.add(LcarsArrow(colours.ORANGE, (TOP + 92, left), ARROW_SIZE, True, self.press), 2)
        self.value = screen.add(LcarsLabel(colours.BEIGE, (TOP + 152, centre_x), "", 3.2, "center"))
        self.down = screen.add(LcarsArrow(colours.ORANGE, (TOP + 222, left), ARROW_SIZE, False, self.press), 2)
        self.screen, self.target = screen, None

    def press(self, arrow, event, clock):
        self.screen.nudge(self.target, 1 if arrow is self.up else -1)

    def show(self, target, label, value, colour, can_up, can_down):
        self.target = target
        for w in (self.label, self.up, self.value, self.down):
            w.visible = True
        self.label.set(label)
        self.value.set(value, colour)
        self.up.set_enabled(can_up)
        self.down.set_enabled(can_down)

    def hide(self):
        for w in (self.label, self.up, self.value, self.down):
            w.visible = False


class ScreenClimate(PanelScreen):
    name = "climate"
    title = "CLIMATE CONTROL"

    def build(self):
        self.nav("SECURE", self.secure, colours.RED_BROWN)

        self.mode_keys = {}
        for i, mode in enumerate(MODES):
            pos = (TOP + 5, LEFT + i * (MODE_SIZE[0] + MODE_GAP))
            key = LcarsKey(colours.GREY_BLUE, pos, MODE_SIZE, MODE_LABELS[mode], self.set_mode)
            key.mode = mode
            self.mode_keys[mode] = self.add(key, layer=2)
        self.inside = self.add(LcarsLabel(colours.BEIGE, (TOP + 2, RIGHT), "--", 2.2, "right"))
        self.add(LcarsLabel(colours.ORANGE, (TOP + 45, RIGHT), "INTERIOR", 1.0, "right"))

        self.single = Column(self, SINGLE_X)
        self.auto = (Column(self, AUTO_X[0]), Column(self, AUTO_X[1]))
        self.offline = self.add(LcarsLabel(colours.GREY_BLUE, (TOP + 150, SINGLE_X), "", 1.5, "center"))
        self.action = self.add(LcarsLabel(colours.BLUE, (TOP + 85, RIGHT), "", 1.1, "right"))
        self.limits = self.add(LcarsLabel(colours.GREY_BLUE, (TOP + 112, RIGHT), "", 1.0, "right"))
        self.sending = self.add(LcarsLabel(colours.GOLD, (TOP + 139, RIGHT), "", 1.0, "right"))

        self.pending, self.pending_at = {}, 0.0  # taps not sent yet
        self.sent, self.sent_at = {}, 0.0        # sent, not yet reported back
        self.mode_sent, self.mode_sent_at = None, 0.0
        self.sound_limit = Sound("assets/audio/deny_1.wav")
        self.sound_sent = Sound("assets/audio/executed.wav")

    # What to show: Home Assistant's values, overlaid with ours in flight.

    def setpoints(self):
        shown = dict(self.panel.thermostat)
        shown.update(self.sent)
        shown.update(self.pending)
        return shown

    def mode(self):
        return self.mode_sent or self.panel.hvac_mode

    # Taps.

    def nudge(self, target, delta):
        if target is None:
            return
        lo, hi = self.panel.guardrails()
        data = step(self.setpoints(), target, delta, lo, hi, self.panel.cfg.HEAT_COOL_GAP)
        if data is None:
            self.sound_limit.play()
            return
        self.pending.update(data)
        self.pending_at = self.panel.clock()

    def set_mode(self, key, event, clock):
        if key.mode == self.mode():
            return
        self.flush()
        if self.panel.call("climate", "set_hvac_mode", "set_hvac_mode",
                           entity_id=self.panel.cfg.THERMOSTAT, hvac_mode=key.mode):
            self.mode_sent, self.mode_sent_at = key.mode, self.panel.clock()
            self.sent, self.pending = {}, {}

    def secure(self, *_):
        self.flush()
        self.panel.lock.lock()
        self.panel.metrics.inc("lcars_relocks_total", reason="button")
        self.go_status()

    def flush(self):
        """Send the gathered taps now."""
        if not self.pending:
            return
        if self.panel.call("climate", "set_temperature", "set_temperature",
                           entity_id=self.panel.cfg.THERMOSTAT, **self.pending):
            self.sent, self.sent_at = {**self.sent, **self.pending}, self.panel.clock()
            self.sound_sent.play()
        self.pending = {}

    def leave(self):
        self.flush()

    # Every frame.

    def refresh(self):
        p = self.panel
        if not p.lock.can_change:
            self.pending = {}  # nothing goes out once locked
            self.go_status()
            return
        now = p.clock()
        if self.pending and now - self.pending_at >= p.cfg.SEND_AFTER_SECONDS:
            self.flush()
        attrs = p.thermostat
        if self.sent and (now - self.sent_at > CONFIRM_SECONDS
                          or all(attrs.get(k) == v for k, v in self.sent.items())):
            self.sent = {}
        if self.mode_sent and (now - self.mode_sent_at > CONFIRM_SECONDS or p.hvac_mode == self.mode_sent):
            self.mode_sent = None

        unit = p.ha.unit
        mode = self.mode()
        available = attrs.get("hvac_modes") or MODES
        for m, key in self.mode_keys.items():
            key.visible = m in available
            key.set_colour(colours.GOLD if m == mode else colours.GREY_BLUE)
        self.inside.set(fmt_temp(attrs.get("current_temperature"), unit))

        lo, hi = p.guardrails()
        gap = p.cfg.HEAT_COOL_GAP
        shown = self.setpoints()
        keys = [] if self.mode_sent else targets(shown)
        columns = [self.single] if len(keys) == 1 else list(self.auto) if len(keys) == 2 else []
        for column in (self.single, *self.auto):
            if column not in columns:
                column.hide()
        for column, key in zip(columns, keys):
            label = TARGET_LABELS[key] or ("COOL TO" if mode == "cool" else "HEAT TO")
            in_flight = key in self.pending or key in self.sent
            column.show(key, label, fmt_temp(shown.get(key), unit),
                        colours.WHITE if in_flight else colours.BEIGE,
                        step(shown, key, 1, lo, hi, gap) is not None,
                        step(shown, key, -1, lo, hi, gap) is not None)
        if self.mode_sent:
            self.offline.set(f"SETTING {MODE_LABELS.get(self.mode_sent, self.mode_sent.upper())}")
        else:
            self.offline.set("" if keys else "SYSTEM OFF - SELECT A MODE")

        action = attrs.get("hvac_action")
        state = ACTION_LABELS.get(action, (action or "--").upper())
        self.action.set(state, colours.ORANGE if action in ("heating", "cooling") else colours.BLUE)
        self.limits.set(f"LIMITS {lo:.0f}-{hi:.0f}{unit}")
        self.sending.set("TRANSMITTING" if self.pending or self.sent or self.mode_sent else "")
