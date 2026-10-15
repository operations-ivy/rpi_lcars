"""Setpoint arithmetic for the climate screen, kept apart from drawing so it
can be tested: one step at a time, inside the guardrails, and with heat and
cool kept apart in auto. Home Assistant enforces the guardrails too."""

MODES = ("heat", "cool", "heat_cool", "off")
MODE_LABELS = {"heat": "HEAT", "cool": "COOL", "heat_cool": "AUTO", "off": "OFF"}
ACTION_LABELS = {"heating": "HEATING", "cooling": "COOLING", "idle": "STANDING BY",
                 "fan": "FAN ONLY", "off": "OFFLINE"}


def clamp(value, lo, hi):
    return min(max(value, lo), hi)


def targets(attrs):
    """What the screen adjusts in this mode: [] (off), ["temperature"], or
    ["target_temp_low", "target_temp_high"] (auto)."""
    if attrs.get("target_temp_low") is not None and attrs.get("target_temp_high") is not None \
            and attrs.get("temperature") is None:
        return ["target_temp_low", "target_temp_high"]
    if attrs.get("temperature") is not None:
        return ["temperature"]
    return []


def step(attrs, target, delta, lo, hi, gap=5):
    """The setpoints after one press: the data for climate.set_temperature, or
    None when the press changes nothing (at a guardrail)."""
    if target == "temperature":
        t = attrs.get("temperature")
        if t is None:
            return None
        new = clamp(t + delta, lo, hi)
        return None if new == t else {"temperature": new}
    low, high = attrs.get("target_temp_low"), attrs.get("target_temp_high")
    if low is None or high is None:
        return None
    if target == "target_temp_low":
        new_low = clamp(low + delta, lo, hi - gap)
        new_high = clamp(max(high, new_low + gap), lo, hi)
    elif target == "target_temp_high":
        new_high = clamp(high + delta, lo + gap, hi)
        new_low = clamp(min(low, new_high - gap), lo, hi)
    else:
        raise ValueError(target)
    if (new_low, new_high) == (low, high):
        return None
    return {"target_temp_low": new_low, "target_temp_high": new_high}


def fmt_temp(value, unit="°F"):
    if value is None:
        return "--"
    return f"{value:.0f}{unit}" if float(value).is_integer() else f"{value:.1f}{unit}"
