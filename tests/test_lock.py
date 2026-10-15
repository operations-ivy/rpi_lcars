from panel import lock as L


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def make(pin="2468", **kw):
    clock = Clock()
    return L.PanelLock(pin, clock=clock, **kw), clock


def test_starts_locked_and_opens_with_the_code():
    lock, _ = make()
    assert not lock.can_change
    assert lock.try_code("2468") == L.GRANTED
    assert lock.can_change


def test_wrong_code_is_denied():
    lock, _ = make()
    assert lock.try_code("1111") == L.DENIED
    assert not lock.can_change


def test_lockout_after_three_misses_doubles_and_caps():
    lock, clock = make(lockout_seconds=30, max_lockout_seconds=100)
    for _ in range(2):
        assert lock.try_code("0") == L.DENIED
    assert lock.try_code("0") == L.LOCKED_OUT
    assert lock.lockout_remaining() == 30
    # The right code is refused while locked out.
    assert lock.try_code("2468") == L.LOCKED_OUT
    clock.t += 30
    for _ in range(2):
        lock.try_code("0")
    assert lock.try_code("0") == L.LOCKED_OUT
    assert lock.lockout_remaining() == 60
    clock.t += 60
    for _ in range(3):
        lock.try_code("0")
    assert lock.lockout_remaining() == 100  # 120, capped


def test_right_code_resets_the_lockout_ladder():
    lock, clock = make(lockout_seconds=30)
    for _ in range(3):
        lock.try_code("0")
    clock.t += 30
    assert lock.try_code("2468") == L.GRANTED
    for _ in range(3):
        lock.try_code("0")
    assert lock.lockout_remaining() == 30


def test_idle_relock():
    lock, clock = make(idle_seconds=120)
    lock.try_code("2468")
    clock.t += 119
    assert lock.can_change
    lock.touch()
    clock.t += 119
    assert not lock.relock_if_idle()
    clock.t += 1
    assert not lock.can_change
    assert lock.relock_if_idle()
    assert not lock.relock_if_idle()


def test_remote_unlocked_needs_no_code():
    lock, _ = make()
    lock.set_remote(L.UNLOCKED)
    assert lock.can_change


def test_remote_hard_lock_refuses_even_the_code_and_drops_an_unlock():
    lock, _ = make()
    lock.try_code("2468")
    lock.set_remote(L.HARD_LOCKED)
    assert not lock.can_change
    assert lock.try_code("2468") == L.HARD
    lock.set_remote(L.NORMAL)
    assert not lock.can_change


def test_unknown_remote_mode_is_normal():
    lock, _ = make()
    lock.set_remote("unavailable")
    assert lock.remote == L.NORMAL
    lock.set_remote(None)
    assert lock.remote == L.NORMAL


def test_no_pin_means_no_code_can_open_it():
    lock, _ = make(pin="")
    assert lock.try_code("") == L.NO_CODE
    assert not lock.can_change


def test_shuffled_digits_are_all_ten():
    import random
    digits = L.shuffled_digits(random.Random(1))
    assert sorted(digits) == list("0123456789")
    assert digits != list("0123456789")
