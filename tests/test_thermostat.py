import pytest

from panel import thermostat as T


def test_targets_by_mode():
    assert T.targets({"temperature": 70}) == ["temperature"]
    assert T.targets({"temperature": None, "target_temp_low": 66, "target_temp_high": 74}) == \
        ["target_temp_low", "target_temp_high"]
    assert T.targets({"temperature": None}) == []
    assert T.targets({}) == []


def test_single_setpoint_steps_and_stops_at_guardrails():
    assert T.step({"temperature": 70}, "temperature", 1, 64, 76) == {"temperature": 71}
    assert T.step({"temperature": 76}, "temperature", 1, 64, 76) is None
    assert T.step({"temperature": 64}, "temperature", -1, 64, 76) is None
    # Outside the guardrails already (set elsewhere): a press pulls it in.
    assert T.step({"temperature": 80}, "temperature", 1, 64, 76) == {"temperature": 76}


def test_auto_keeps_the_gap_by_pushing_the_other_setpoint():
    attrs = {"target_temp_low": 68, "target_temp_high": 73}
    assert T.step(attrs, "target_temp_low", 1, 64, 76, gap=5) == \
        {"target_temp_low": 69, "target_temp_high": 74}
    assert T.step(attrs, "target_temp_high", -1, 64, 76, gap=5) == \
        {"target_temp_low": 67, "target_temp_high": 72}


def test_auto_stops_when_the_pushed_setpoint_hits_a_guardrail():
    attrs = {"target_temp_low": 71, "target_temp_high": 76}
    assert T.step(attrs, "target_temp_low", 1, 64, 76, gap=5) is None
    attrs = {"target_temp_low": 64, "target_temp_high": 69}
    assert T.step(attrs, "target_temp_high", -1, 64, 76, gap=5) is None


def test_auto_unknown_target():
    with pytest.raises(ValueError):
        T.step({"target_temp_low": 1, "target_temp_high": 9}, "humidity", 1, 0, 10)


def test_fmt_temp():
    assert T.fmt_temp(None) == "--"
    assert T.fmt_temp(70.0) == "70°F"
    assert T.fmt_temp(70.5, "°C") == "70.5°C"
