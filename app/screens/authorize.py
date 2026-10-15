"""The code keypad. Its digits are shuffled on every visit, so watching where a
hand goes teaches nothing; dots show how many digits are in, never which.
Wrong codes lock it out for a while (panel.lock), and Home Assistant can
hard-lock it."""
from panel import lock as L
from screens.base import LEFT, TOP, PanelScreen
from ui import colours
from ui.utils.sound import Sound
from ui.widgets.panel_widgets import LcarsDots, LcarsKey, LcarsLabel

MAX_DIGITS = 8
KEY_SIZE = (100, 62)
KEY_LEFT, KEY_GAP = 450, 8


class ScreenAuthorize(PanelScreen):
    name = "authorize"
    title = "AUTHORIZATION REQUIRED"

    def build(self):
        self.sidebar("upper", colours.BEIGE, "STATUS", self.go_status)
        self.sidebar("middle", colours.ORANGE, "CLIMATE")
        self.sidebar("lower", colours.PEACH, "SECURED")

        self.add(LcarsLabel(colours.ORANGE, (TOP + 10, LEFT), "ENTER CODE", 1.5))
        self.dots = self.add(LcarsDots(colours.BEIGE, (TOP + 60, LEFT + 2), MAX_DIGITS))
        self.message = self.add(LcarsLabel(colours.BLUE, (TOP + 110, LEFT), "", 1.3))
        self.detail = self.add(LcarsLabel(colours.GREY_BLUE, (TOP + 145, LEFT), "", 1.0))

        digits = L.shuffled_digits()
        labels = digits[:9] + ["CLEAR", digits[9], "ENTER"]
        self.keys = []
        for i, label in enumerate(labels):
            row, col = divmod(i, 3)
            pos = (TOP + 5 + row * (KEY_SIZE[1] + KEY_GAP), KEY_LEFT + col * (KEY_SIZE[0] + KEY_GAP))
            if label == "CLEAR":
                key = LcarsKey(colours.RED_BROWN, pos, KEY_SIZE, label, self.clear)
            elif label == "ENTER":
                key = LcarsKey(colours.GOLD, pos, KEY_SIZE, label, self.enter)
            else:
                key = LcarsKey(colours.GREY_BLUE, pos, KEY_SIZE, label, self.digit, text_size=1.8)
            self.keys.append(self.add(key, layer=2))

        self.code = ""
        self.flash = ("", 0.0)  # a message shown until a time
        Sound("assets/audio/enter_authorization_code.wav").play()
        self.sound_granted = Sound("assets/audio/accessing.wav")
        self.sound_denied = Sound("assets/audio/access_denied.wav")
        self.sound_deny = Sound("assets/audio/deny_2.wav")

    def digit(self, key, event, clock):
        if len(self.code) < MAX_DIGITS:
            self.code += key.text

    def clear(self, *_):
        self.code = ""

    def enter(self, *_):
        p = self.panel
        result = p.lock.try_code(self.code)
        self.code = ""
        p.metrics.inc("lcars_unlock_attempts_total", result=result)
        if result == L.GRANTED:
            self.sound_granted.play()
            self.go_climate()
            return
        self.sound_deny.play()
        if result == L.DENIED:
            self.sound_denied.play()
            left = p.lock.misses_before_lockout - p.lock.misses
            self.flash = (f"ACCESS DENIED - {left} ATTEMPT{'S' if left != 1 else ''} REMAIN", p.clock() + 4)

    def refresh(self):
        p = self.panel
        lock = p.lock
        if lock.can_change:  # opened from Home Assistant meanwhile
            self.go_climate()
            return
        if lock.idle:
            self.go_status()
            return

        open_ = False
        if lock.remote == L.HARD_LOCKED:
            text, detail, colour = "LOCKED BY HOME ASSISTANT", "UNLOCK FROM HOME ASSISTANT", colours.RED
        elif not lock.pin:
            text, detail, colour = "NO CODE CONFIGURED", "UNLOCK FROM HOME ASSISTANT", colours.RED
        elif lock.lockout_remaining() > 0:
            secs = int(lock.lockout_remaining() + 0.999)
            text, detail, colour = "SECURITY LOCKOUT", f"KEYPAD RETURNS IN {secs // 60}:{secs % 60:02d}", colours.RED
        else:
            open_ = True
            message, until = self.flash
            if message and p.clock() < until:
                text, detail, colour = message, "", colours.RED
            else:
                text, detail, colour = "AUTHORIZED PERSONNEL ONLY", "", colours.BLUE
        self.message.set(text, colour)
        self.detail.set(detail)
        for key in self.keys:
            key.set_enabled(open_)
        self.dots.set(len(self.code), colours.BEIGE if open_ else colours.DISABLED)
        if not open_:
            self.code = ""
