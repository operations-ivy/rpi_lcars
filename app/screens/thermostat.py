"""The thermostat: its controls and readings on one screen, open to anyone.
Mode buttons along the top; a scale on the left (the guardrails' range, the
setpoints and the house average on it); one setpoint column (heat or cool)
or two (auto), each with drawn arrows; the house average, upstairs and downstairs, what the
ecobee is doing and the lock on the right.

The controls work only while the lock allows it: otherwise they're greyed
out and the sidebar's UNLOCK opens the keypad (SECURE locks it again). On a
read-only panel it's a preview: no UNLOCK, nothing is sent (Panel.call
refuses too). Arrow taps show at once and gather for SEND_AFTER_SECONDS
before one call goes to Home Assistant; a sent value shows until Home
Assistant reports it (or CONFIRM_SECONDS pass)."""
from panel import lock as L
from panel.thermostat import ACTION_LABELS, MODE_LABELS, MODES, fmt_temp, step, targets
from screens.base import LEFT, RIGHT, TOP, PanelScreen
from ui import colours
from ui.utils.sound import Sound
from ui.widgets.panel_widgets import LcarsArrow, LcarsGauge, LcarsKey, LcarsLabel

CONFIRM_SECONDS = 15
MODE_SIZE, MODE_GAP = (112, 44), 10
ARROW_SIZE = (120, 58)
# Column centres: one setpoint, or auto's heat and cool.
SINGLE_X, AUTO_X = 455, (330, 580)
# The right column, clear of auto's cool arrows.
SIDE_WIDTH = RIGHT - 640
# The scale: its top left and size, clear of auto's heat arrows.
GAUGE_POS, GAUGE_SIZE = (TOP + 64, LEFT + 4), (104, 262)
MARK_COLOURS = {"temperature": None, "target_temp_low": colours.ORANGE, "target_temp_high": colours.BLUE}
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


class ScreenThermostat(PanelScreen):
    name = "thermostat"

    @property
    def editable(self):
        return not self.panel.read_only and self.panel.lock.can_change

    @property
    def title(self):
        return "CLIMATE CONTROL - PREVIEW" if self.panel.read_only else "CLIMATE CONTROL"

    def build(self):
        # The last sidebar block: SECURE while open, UNLOCK while not, none read-only.
        self.action_key = None if self.panel.read_only else self.nav(("UNLOCK", self.unlock, colours.GOLD))
        if self.action_key is None:
            self.nav()

        self.mode_keys = {}
        for i, mode in enumerate(MODES):
            pos = (TOP + 5, LEFT + i * (MODE_SIZE[0] + MODE_GAP))
            key = LcarsKey(colours.GREY_BLUE, pos, MODE_SIZE, MODE_LABELS[mode], self.set_mode, pill=True)
            key.mode = mode
            self.mode_keys[mode] = self.add(key, layer=2)
        self.average = self.add(LcarsLabel(colours.BEIGE, (TOP + 2, RIGHT), "--", 2.2, "right"))
        self.add(LcarsLabel(colours.ORANGE, (TOP + 45, RIGHT), "HOUSE AVERAGE", 1.0, "right"))
        self.floors = [self.add(LcarsLabel(colours.GREY_BLUE, (TOP + 70 + i * 22, RIGHT), "", 1.0, "right",
                                           max_width=SIDE_WIDTH)) for i in range(2)]

        self.gauge = self.add(LcarsGauge(GAUGE_POS, GAUGE_SIZE))
        self.single = Column(self, SINGLE_X)
        self.auto = (Column(self, AUTO_X[0]), Column(self, AUTO_X[1]))
        self.offline = self.add(LcarsLabel(colours.GREY_BLUE, (TOP + 150, SINGLE_X), "", 1.5, "center"))
        self.action = self.add(LcarsLabel(colours.BLUE, (TOP + 122, RIGHT), "", 1.1, "right", max_width=SIDE_WIDTH))
        self.limits = self.add(LcarsLabel(colours.GREY_BLUE, (TOP + 148, RIGHT), "", 1.0, "right"))
        self.sending = self.add(LcarsLabel(colours.GOLD, (TOP + 180, RIGHT), "", 1.0, "right", max_width=SIDE_WIDTH))
        self.notice = self.add(LcarsLabel(colours.GREY_BLUE, (TOP + 202, RIGHT), "", 1.0, "right",
                                          max_width=SIDE_WIDTH))

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
        if target is None or not self.editable:
            return
        lo, hi = self.panel.guardrails()
        data = step(self.setpoints(), target, delta, lo, hi, self.panel.cfg.HEAT_COOL_GAP)
        if data is None:
            self.sound_limit.play()
            return
        self.pending.update(data)
        self.pending_at = self.panel.clock()

    def set_mode(self, key, event, clock):
        if not self.editable or key.mode == self.mode():
            return
        self.flush()
        if self.panel.call("climate", "set_hvac_mode", "set_hvac_mode",
                           entity_id=self.panel.cfg.THERMOSTAT, hvac_mode=key.mode):
            self.mode_sent, self.mode_sent_at = key.mode, self.panel.clock()
            self.sent, self.pending = {}, {}

    def unlock(self, *_):
        self.go_authorize()

    def secure(self, *_):
        self.flush()
        self.panel.lock.lock()
        self.panel.metrics.inc("lcars_relocks_total", reason="button")
        self.go_status()

    def flush(self):
        """Send the gathered taps now."""
        if not self.pending or not self.editable:
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
        editable = self.editable
        if not editable:
            self.pending = {}  # nothing goes out once locked
        if self.action_key is not None:
            text, handler, colour = ("SECURE", self.secure, colours.RED_BROWN) if editable \
                else ("UNLOCK", self.unlock, colours.GOLD)
            self.action_key.set_text(text)
            self.action_key.set_colour(colour)
            self.action_key.handler = handler
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
            key.set_enabled(editable)
        up, down, average = p.house()
        self.average.set("--" if average is None else f"{average:.1f}{unit}",
                         colours.GREY_BLUE if average is None else colours.BEIGE)
        self.floors[0].set(f"UPSTAIRS {'--' if up is None else f'{up:.1f}{unit}'}")
        self.floors[1].set(f"DOWNSTAIRS {fmt_temp(down, unit)}")

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
                        editable and step(shown, key, 1, lo, hi, gap) is not None,
                        editable and step(shown, key, -1, lo, hi, gap) is not None)
        marks = [(shown.get(key), MARK_COLOURS[key] or (colours.BLUE if mode == "cool" else colours.ORANGE))
                 for key in keys]
        self.gauge.set(lo, hi, average if average is not None else down, marks)
        if self.mode_sent:
            self.offline.set(f"SETTING {MODE_LABELS.get(self.mode_sent, self.mode_sent.upper())}")
        else:
            self.offline.set("" if keys else "SYSTEM OFF - SELECT A MODE")

        action = attrs.get("hvac_action")
        state = ACTION_LABELS.get(action, (action or "--").upper())
        if not editable:  # the mode keys are all greyed out: name the mode
            state = f"{MODE_LABELS.get(mode, (mode or '--').upper())} - {state}"
        self.action.set(state, colours.ORANGE if action in ("heating", "cooling") else colours.BLUE)
        self.limits.set(f"LIMITS {lo:.0f}-{hi:.0f}{unit}")
        if p.read_only:
            line, notice, colour = "PREVIEW ONLY", "CONTROLS DISABLED", colours.GOLD
        elif editable:
            line = "TRANSMITTING" if self.pending or self.sent or self.mode_sent else "CONTROLS OPEN"
            notice, colour = "SECURE WHEN DONE", colours.GOLD
        elif p.lock.remote == L.HARD_LOCKED:
            line, notice, colour = "CONTROLS LOCKED", "BY HOME ASSISTANT", colours.RED
        else:
            line, notice, colour = "CONTROLS SECURED", "UNLOCK TO ADJUST", colours.ORANGE
        self.sending.set(line, colour)
        self.notice.set(notice)
