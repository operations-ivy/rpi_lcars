"""The panel's lock. Looking is free; changing anything needs the code, which
relocks after a quiet spell. Wrong codes lock it out for a while, longer each
time. Home Assistant can override it (input_select.lcars_panel_lock):
`unlocked` needs no code, `hard_locked` refuses even the right one."""
import hmac
import random
import time

NORMAL, UNLOCKED, HARD_LOCKED = "normal", "unlocked", "hard_locked"
REMOTE_MODES = (NORMAL, UNLOCKED, HARD_LOCKED)

# try_code results
GRANTED, DENIED, LOCKED_OUT, HARD, NO_CODE = "granted", "denied", "locked_out", "hard_locked", "no_code"


class PanelLock:
    def __init__(self, pin, idle_seconds=120, misses_before_lockout=3,
                 lockout_seconds=30, max_lockout_seconds=600, clock=time.monotonic):
        self.pin = str(pin)
        self.idle_seconds = idle_seconds
        self.misses_before_lockout = misses_before_lockout
        self.lockout_seconds = lockout_seconds
        self.max_lockout_seconds = max_lockout_seconds
        self.clock = clock
        self.remote = NORMAL
        self.misses = 0
        self.lockouts = 0
        self._locked_out_until = 0.0
        self._unlocked = False
        self._last_touch = clock()

    def set_remote(self, mode):
        """Home Assistant's mode; anything unknown (or no answer) is normal."""
        mode = mode if mode in REMOTE_MODES else NORMAL
        if mode == HARD_LOCKED:
            self._unlocked = False
        self.remote = mode

    def touch(self):
        self._last_touch = self.clock()

    @property
    def can_change(self):
        if self.remote == HARD_LOCKED:
            return False
        if self.remote == UNLOCKED:
            return True
        return self._unlocked and not self.idle

    @property
    def unlocked(self):
        """Opened with the code (Home Assistant's override aside)."""
        return self._unlocked

    @property
    def idle(self):
        return self.clock() - self._last_touch >= self.idle_seconds

    def lockout_remaining(self):
        return max(0.0, self._locked_out_until - self.clock())

    def try_code(self, code):
        if self.remote == HARD_LOCKED:
            return HARD
        if self.lockout_remaining() > 0:
            return LOCKED_OUT
        if not self.pin:
            return NO_CODE
        if hmac.compare_digest(str(code).encode(), self.pin.encode()):
            self.misses = self.lockouts = 0
            self._unlocked = True
            self.touch()
            return GRANTED
        self.misses += 1
        if self.misses >= self.misses_before_lockout:
            self.misses = 0
            self.lockouts += 1
            seconds = self.lockout_seconds * 2 ** (self.lockouts - 1)
            self._locked_out_until = self.clock() + min(seconds, self.max_lockout_seconds)
            return LOCKED_OUT
        return DENIED

    def lock(self):
        self._unlocked = False

    def relock_if_idle(self):
        """Lock after the quiet spell; True when that just happened."""
        if self._unlocked and self.idle:
            self._unlocked = False
            return True
        return False


def shuffled_digits(rng=random.SystemRandom()):
    """The keypad's labels for one visit: where a digit sits changes every
    time, so watching a hand teaches nothing."""
    digits = list("0123456789")
    rng.shuffle(digits)
    return digits
