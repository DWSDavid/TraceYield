import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.signals.curve_impact import classify_curve_call, tenor_pressure_from_drivers


def test_policy_path_pressures_front_end_more_than_long_end():
    pressure = tenor_pressure_from_drivers(
        {
            "policy_path": 1.0,
            "macro_surprise": 0.0,
            "liquidity_supply": 0.0,
            "term_premium": 0.0,
            "growth_risk": 0.0,
            "global_relative_value": 0.0,
            "positioning_momentum": 0.0,
            "risk_off_overlay": 0.0,
        }
    )

    assert pressure["2Y"] > pressure["10Y"]
    assert pressure["5Y"] > pressure["30Y"]


def test_term_premium_pressures_long_end_more_than_front_end():
    pressure = tenor_pressure_from_drivers(
        {
            "policy_path": 0.0,
            "macro_surprise": 0.0,
            "liquidity_supply": 0.0,
            "term_premium": 1.0,
            "growth_risk": 0.0,
            "global_relative_value": 0.0,
            "positioning_momentum": 0.0,
            "risk_off_overlay": 0.0,
        }
    )

    assert pressure["10Y"] > pressure["2Y"]
    assert pressure["30Y"] > pressure["5Y"]


def test_liquidity_supply_pressure_maps_to_long_end():
    pressure = tenor_pressure_from_drivers(
        {
            "policy_path": 0.0,
            "macro_surprise": 0.0,
            "liquidity_supply": 1.0,
            "term_premium": 0.0,
            "growth_risk": 0.0,
            "global_relative_value": 0.0,
            "positioning_momentum": 0.0,
            "risk_off_overlay": 0.0,
        }
    )

    assert pressure["10Y"] > pressure["2Y"]
    assert pressure["30Y"] > pressure["5Y"]


def test_curve_call_uses_level_and_slope_pressure():
    call = classify_curve_call({"2Y": 0.1, "5Y": 0.2, "10Y": 0.5, "30Y": 0.6})

    assert call == "BEAR_STEEPENING"
