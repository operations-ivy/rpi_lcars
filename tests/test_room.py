import logging

import pytest

from datasources import room as R
from metrics import Metrics


def word(value):
    data = value.to_bytes(2, "big")
    return data + bytes([R.crc8(data)])


def reading(celsius, humidity):
    t = round((celsius + 45) * 65535 / 175)
    rh = round(humidity * 65535 / 100)
    return word(t) + word(rh)


class FakeSHT:
    def __init__(self, raw=None, fail=None):
        self.raw, self.fail, self.commands = raw, fail, []

    def transfer(self, command, length, wait):
        self.commands.append((command, length))
        if self.fail:
            raise self.fail
        return self.raw


def test_crc_matches_the_datasheet_example():
    assert R.crc8(bytes([0xBE, 0xEF])) == 0x92


def test_decode():
    f, rh = R.decode(reading(25.0, 50.0))
    assert f == pytest.approx(77.0, abs=0.01)
    assert rh == pytest.approx(50.0, abs=0.01)


def test_bad_crc_and_length_are_refused():
    raw = bytearray(reading(25.0, 50.0))
    raw[1] ^= 0x01
    with pytest.raises(ValueError):
        R.decode(bytes(raw))
    with pytest.raises(ValueError):
        R.decode(b"\x00\x01")


def test_poll_reads_with_offset_and_metrics():
    m = Metrics()
    dev = FakeSHT(reading(22.0, 45.0))
    room = R.Room(offset=-2.5, metrics=m, device=dev)
    assert room.poll()
    assert dev.commands == [(R.MEASURE, 6)]
    assert room.temperature == pytest.approx(71.6 - 2.5, abs=0.01)
    assert room.humidity == pytest.approx(45.0, abs=0.01)
    assert room.fresh()
    assert m.get("lcars_room_sensor_up") == 1
    assert m.get("lcars_room_temperature_fahrenheit") == pytest.approx(69.1, abs=0.01)


def test_unplugged_warns_once_and_keeps_going(caplog):
    m = Metrics()
    room = R.Room(metrics=m, device=FakeSHT(fail=OSError(121, "Remote I/O error")))
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            assert not room.poll()
    assert room.error == "NO SENSOR" and not room.fresh()
    assert len([r for r in caplog.records if "room sensor" in r.message]) == 1
    assert m.get("lcars_room_sensor_up") == 0
    assert m.get("lcars_room_reads_total", result="error") == 3


def test_a_bad_reading_keeps_the_last_good_one():
    dev = FakeSHT(reading(22.0, 45.0))
    room = R.Room(device=dev)
    room.poll()
    dev.raw = b"\xff" * 6
    assert not room.poll()
    assert room.error == "BAD READING"
    assert room.temperature == pytest.approx(71.6, abs=0.01)


def test_document_for_home_assistant():
    room = R.Room(device=FakeSHT(reading(22.0, 45.0)))
    assert room.document() == {"up": False, "temperature_f": None, "humidity": None}
    room.poll()
    assert room.document() == {"up": True, "temperature_f": 71.6, "humidity": 45.0}
    room.updated -= 600
    assert room.document()["up"] is False
