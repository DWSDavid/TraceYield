"""Translate v2 driver scores into UST tenor pressure and curve calls."""

from __future__ import annotations

from src.utils.config import load_yaml

TENORS = ("2Y", "5Y", "10Y", "30Y")


def _clip(value: float) -> float:
    return float(max(-1.0, min(1.0, value)))


def _rules() -> dict:
    return load_yaml("curve_rules")


def tenor_pressure_from_drivers(driver_scores: dict[str, float]) -> dict[str, float]:
    """Map driver scores to 2Y/5Y/10Y/30Y pressure using configured loadings."""
    loadings = _rules()["tenor_loadings"]
    pressure = {tenor: 0.0 for tenor in TENORS}
    for driver, score in driver_scores.items():
        driver_loadings = loadings.get(driver, {})
        for tenor in TENORS:
            pressure[tenor] += float(score) * float(driver_loadings.get(tenor, 0.0))
    return {tenor: round(_clip(value), 4) for tenor, value in pressure.items()}


def classify_curve_call(tenor_pressure: dict[str, float]) -> str:
    """Classify level and slope pressure into the v2 curve-call vocabulary."""
    thresholds = _rules().get("call_thresholds", {})
    level_threshold = float(thresholds.get("level", 0.04))
    slope_threshold = float(thresholds.get("slope", 0.025))
    conflict_threshold = float(thresholds.get("conflict", 0.08))

    front = (tenor_pressure["2Y"] + tenor_pressure["5Y"]) / 2
    long = (tenor_pressure["10Y"] + tenor_pressure["30Y"]) / 2
    level = (front + long) / 2
    slope = long - front

    if max(abs(v) for v in tenor_pressure.values()) < level_threshold:
        return "RANGE_BOUND"
    if front * long < 0 and abs(front - long) > conflict_threshold:
        return "MIXED_CONFLICT"
    if abs(level) < level_threshold:
        return "MIXED_CONFLICT"

    direction = "BEAR" if level > 0 else "BULL"
    if abs(slope) < slope_threshold:
        return "RANGE_BOUND"
    shape = "STEEPENING" if slope > 0 else "FLATTENING"
    return f"{direction}_{shape}"
