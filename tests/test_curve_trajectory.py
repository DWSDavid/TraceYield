import json
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.curve_trajectory import (
    apply_event_uncertainty_overlay,
    apply_policy_event_overlay,
    build_curve_trajectory,
    save_curve_trajectory,
)
from src.models.fadns import build_fadns_prediction_frames


def _curve_history(periods: int = 340) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=periods, freq="D")
    trend = np.linspace(0.0, 1.0, periods)
    cycle = np.sin(np.arange(periods) / 18.0)
    level = 3.6 + 0.18 * trend + 0.03 * cycle
    slope = -0.7 + 0.30 * trend - 0.04 * cycle
    curvature = 0.08 * np.sin(np.arange(periods) / 27.0)
    return pd.DataFrame(
        {
            "DGS2": level - 0.32 * slope + 0.10 * curvature,
            "DGS5": level - 0.08 * slope + 0.35 * curvature,
            "DGS10": level + 0.16 * slope - 0.20 * curvature,
            "DGS30": level + 0.48 * slope,
            "T10Y2Y": (level + 0.16 * slope) - (level - 0.32 * slope),
            "PCEPILFE": 120 + trend + 0.01 * cycle,
            "CPIAUCSL": 300 + 1.2 * trend + 0.02 * cycle,
        },
        index=dates,
    )


@lru_cache(maxsize=1)
def _build_test_trajectory() -> dict:
    return build_curve_trajectory(
        _curve_history(),
        start="2024-02-15",
        min_train=30,
        ridge_alpha=1.0,
    )


def test_curve_trajectory_has_monthly_tenor_and_spread_contract():
    trajectory = _build_test_trajectory()

    assert set(trajectory) >= {"as_of", "tenors"}
    assert set(trajectory["tenors"]) == {"2Y", "5Y", "10Y", "30Y", "2s10s", "5s30s"}

    ten_year = trajectory["tenors"]["10Y"]
    assert [point["month"] for point in ten_year] == list(range(1, 13))
    assert [point["horizon_days"] for point in ten_year] == [
        21 * m for m in range(1, 13)
    ]

    first = ten_year[0]
    assert {
        "current",
        "central",
        "delta_bp",
        "p10",
        "p25",
        "p50",
        "p75",
        "p90",
    }.issubset(first)
    assert first["delta_bp"] == round((first["central"] - first["current"]) * 100, 6)


def test_curve_trajectory_central_path_matches_latest_fadns_forecast():
    history = _curve_history()
    trajectory = build_curve_trajectory(
        history,
        start="2024-02-15",
        min_train=30,
        ridge_alpha=1.0,
    )
    as_of = pd.Timestamp(trajectory["as_of"])
    expected = build_fadns_prediction_frames(
        history,
        start=as_of.strftime("%Y-%m-%d"),
        horizons={"3m": 63},
        min_train=30,
        ridge_alpha=1.0,
    )["3m"].loc[as_of, "10Y"]

    three_month_point = trajectory["tenors"]["10Y"][2]
    actual = three_month_point["delta_bp"] / 100.0

    assert actual == round(float(expected), 6)


def test_curve_trajectory_p50_is_central_not_bias_corrected():
    trajectory = _build_test_trajectory()

    for target, points in trajectory["tenors"].items():
        for point in points:
            assert point["p50"] == point["central"], target
    assert trajectory["metadata"]["fan_center"] == "central_fadns_macro_adjusted"


def test_curve_trajectory_includes_random_walk_and_market_10y_range():
    trajectory = _build_test_trajectory()

    baselines = trajectory["metadata"]["baselines"]
    ten_year = baselines["10Y"]
    assert ten_year["random_walk"]["level"] == trajectory["tenors"]["10Y"][0]["current"]
    assert ten_year["market_range"]["low"] == 3.9
    assert ten_year["market_range"]["high"] == 4.8
    assert ten_year["market_range"]["source"] == "manual_market_observed"


def test_curve_trajectory_empirical_fan_widths_are_non_decreasing():
    trajectory = _build_test_trajectory()

    for target, points in trajectory["tenors"].items():
        p10_p90_widths = [round(point["p90"] - point["p10"], 10) for point in points]
        p25_p75_widths = [round(point["p75"] - point["p25"], 10) for point in points]
        assert p10_p90_widths == sorted(p10_p90_widths), target
        assert p25_p75_widths == sorted(p25_p75_widths), target


def test_save_curve_trajectory_writes_json_and_flat_csv(tmp_path):
    trajectory = _build_test_trajectory()

    json_path, csv_path = save_curve_trajectory(trajectory, output_dir=tmp_path)

    assert json_path.exists()
    assert csv_path.exists()
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    flat = pd.read_csv(csv_path)

    assert saved["as_of"] == trajectory["as_of"]
    assert len(flat) == 12 * 6
    assert {
        "as_of",
        "target",
        "month",
        "horizon_days",
        "current",
        "central",
        "delta_bp",
        "p10",
        "p25",
        "p50",
        "p75",
        "p90",
    }.issubset(flat.columns)


def test_curve_trajectory_metadata_contains_base_adjusted_attribution():
    trajectory = _build_test_trajectory()

    audit = trajectory["metadata"]["realized_macro_data_audit"]
    assert (
        audit["central_path_role"] == "already released macro data can move central/p50"
    )
    assert (
        audit["future_event_role"] == "scheduled unknown future events widen fan only"
    )
    assert "CPIAUCSL" in audit["central_path"]["inflation_regime"]["available_series"]
    assert "PCEPILFE" in audit["central_path"]["inflation_regime"]["available_series"]
    assert "CPILFESL" in audit["central_path"]["inflation_regime"]["missing_or_proxy"]
    assert "cpi" in audit["fan_only_future_events"]
    assert "qra" in audit["fan_only_future_events"]

    attribution = trajectory["metadata"]["base_vs_adjusted"]
    assert attribution["linearity_assertion"] == "passed"
    assert set(attribution["macro_block_sanity"]) == {
        "inflation_regime",
        "policy_path",
        "growth_risk",
        "liquidity_supply",
        "global_relative_value",
    }
    policy_sanity = attribution["macro_block_sanity"]["policy_path"]
    assert {
        "ic_3m",
        "ic_6m",
        "dir_acc_3m",
        "nw_t_3m",
        "aligned_target",
        "expected_sign",
        "verdict",
        "note",
    }.issubset(policy_sanity)
    assert policy_sanity["verdict"] in {"signal", "explanation-only"}
    assert "3" in attribution["horizons"]
    ten_year = attribution["horizons"]["3"]["targets"]["10Y"]
    assert {"base", "adjusted", "total_delta_bp", "contributions_bp"}.issubset(ten_year)
    assert (
        abs(sum(ten_year["contributions_bp"].values()) - ten_year["total_delta_bp"])
        < 1e-6
    )


def _bare_overlay_trajectory() -> dict:
    points = [
        {
            "month": month,
            "horizon_days": month * 21,
            "current": 4.0,
            "central": 4.0,
            "delta_bp": 0.0,
            "p10": 3.5,
            "p25": 3.75,
            "p50": 4.0,
            "p75": 4.25,
            "p90": 4.5,
        }
        for month in range(1, 13)
    ]
    return {
        "as_of": "2026-05-29",
        "tenors": {
            "2Y": [point.copy() for point in points],
            "5Y": [point.copy() for point in points],
            "10Y": [point.copy() for point in points],
            "30Y": [point.copy() for point in points],
            "2s10s": [point.copy() for point in points],
            "5s30s": [point.copy() for point in points],
        },
        "metadata": {},
    }


def test_policy_event_overlay_steps_front_end_at_next_fomc_month():
    policy_path = {
        "source": "fedwatch_csv",
        "next_meeting_date": pd.Timestamp("2026-06-17").date(),
        "next_meeting_cut_prob": 0.70,
        "next_meeting_hike_prob": 0.05,
        "direction": "EASING",
        "reason": "FedWatch CSV prices a high cut probability.",
    }
    overlay_config = {
        "fomc_policy_path": {
            "cut_prob_high": 0.60,
            "hike_prob_high": 0.60,
            "front_end_cut_bp": -12.5,
            "front_end_hike_bp": 12.5,
            "targets": {"2Y": 1.0},
            "reason_template": (
                "{source}: cut probability {cut_prob:.0%}; "
                "front-end scenario step {step_bp:+.1f}bp."
            ),
        }
    }

    adjusted = apply_policy_event_overlay(
        _bare_overlay_trajectory(),
        policy_path=policy_path,
        overlay_config=overlay_config,
    )

    two_year = adjusted["tenors"]["2Y"][0]
    spread = adjusted["tenors"]["2s10s"][0]
    assert two_year["base_central"] == 4.0
    assert two_year["central"] == 3.875
    assert two_year["delta_bp"] == -12.5
    assert two_year["overlay_bp"] == -12.5
    assert "cut probability 70%" in two_year["overlay_reasons"][0]
    assert spread["central"] == 4.125
    assert spread["overlay_bp"] == 12.5
    assert adjusted["metadata"]["event_overlays"][0]["month"] == 1


def _uncertainty_overlay_config() -> dict:
    return {
        "uncertainty_widen_bp": {
            "fomc": {"2Y": 18, "5Y": 14, "10Y": 12, "30Y": 10},
            "cpi": {"2Y": 8, "5Y": 9, "10Y": 10, "30Y": 9},
            "nfp": {"2Y": 10, "5Y": 10, "10Y": 9, "30Y": 8},
            "pce": {"2Y": 7, "5Y": 8, "10Y": 9, "30Y": 8},
            "qra": {"2Y": 3, "5Y": 6, "10Y": 9, "30Y": 10},
        },
        "combine": "sqrt_sum_of_squares",
    }


def test_event_uncertainty_overlay_widens_single_event_without_central_shift():
    release_cal = {
        "releases": [
            {
                "indicator": "cpi",
                "release_date": "2026-07-14",
                "reference_month": "2026-06",
                "precision": "estimated",
            }
        ]
    }

    adjusted = apply_event_uncertainty_overlay(
        _bare_overlay_trajectory(),
        as_of="2026-05-29",
        overlay_config=_uncertainty_overlay_config(),
        fomc_cal={"meetings": []},
        release_cal=release_cal,
    )

    month_1 = adjusted["tenors"]["10Y"][0]
    month_2 = adjusted["tenors"]["10Y"][1]
    assert month_1["p10"] == 3.5
    assert month_1["p90"] == 4.5
    assert month_2["central"] == 4.0
    assert month_2["p50"] == 4.0
    assert month_2["p10"] == 3.4
    assert month_2["p25"] == 3.7
    assert month_2["p75"] == 4.3
    assert month_2["p90"] == 4.6
    assert month_2["uncertainty_widen_bp"] == 10.0
    assert "date estimated" in month_2["overlay_reasons"][0]


def test_event_uncertainty_overlay_combines_multiple_events_by_quadrature():
    release_cal = {
        "releases": [
            {
                "indicator": "cpi",
                "release_date": "2026-07-14",
                "reference_month": "2026-06",
                "precision": "estimated",
            },
            {
                "indicator": "nfp",
                "release_date": "2026-07-03",
                "reference_month": "2026-06",
                "precision": "estimated",
            },
        ]
    }

    adjusted = apply_event_uncertainty_overlay(
        _bare_overlay_trajectory(),
        as_of="2026-05-29",
        overlay_config=_uncertainty_overlay_config(),
        fomc_cal={"meetings": []},
        release_cal=release_cal,
    )

    ten_year = adjusted["tenors"]["10Y"][1]
    spread = adjusted["tenors"]["2s10s"][1]
    expected_10y = round(float(np.sqrt(10**2 + 9**2)), 6)
    expected_spread = round(float(np.sqrt(8**2 + 10**2 + 10**2 + 9**2)), 6)
    assert ten_year["uncertainty_widen_bp"] == expected_10y
    assert ten_year["p90"] == round(4.5 + expected_10y / 100.0, 6)
    assert spread["uncertainty_widen_bp"] == expected_spread
    assert adjusted["metadata"]["event_overlays"][0]["widen_bp"]["10Y"] == expected_10y


def test_event_uncertainty_overlay_leaves_no_event_month_unchanged():
    release_cal = {
        "releases": [
            {
                "indicator": "qra",
                "release_date": "2026-08-05",
                "reference_month": "2026-08",
                "precision": "estimated",
            }
        ]
    }
    base = _bare_overlay_trajectory()

    adjusted = apply_event_uncertainty_overlay(
        base,
        as_of="2026-05-29",
        overlay_config=_uncertainty_overlay_config(),
        fomc_cal={"meetings": []},
        release_cal=release_cal,
    )

    assert adjusted["tenors"]["2Y"][0] == base["tenors"]["2Y"][0]
    assert adjusted["tenors"]["10Y"][0] == base["tenors"]["10Y"][0]


def test_policy_step_and_uncertainty_widening_coexist_independently():
    policy_path = {
        "source": "fedwatch_csv",
        "next_meeting_date": pd.Timestamp("2026-06-17").date(),
        "next_meeting_cut_prob": 0.70,
        "next_meeting_hike_prob": 0.05,
        "direction": "EASING",
    }
    overlay_config = {
        **_uncertainty_overlay_config(),
        "fomc_policy_path": {
            "cut_prob_high": 0.60,
            "hike_prob_high": 0.60,
            "front_end_cut_bp": -12.5,
            "front_end_hike_bp": 12.5,
            "targets": {"2Y": 1.0},
            "reason_template": "{source}: front-end scenario step {step_bp:+.1f}bp.",
        },
    }
    fomc_cal = {
        "meetings": [
            {
                "meeting": "2026-06",
                "decision_date": "2026-06-17",
                "has_sep": True,
            }
        ]
    }

    stepped = apply_policy_event_overlay(
        _bare_overlay_trajectory(),
        policy_path=policy_path,
        overlay_config=overlay_config,
    )
    adjusted = apply_event_uncertainty_overlay(
        stepped,
        as_of="2026-05-29",
        overlay_config=overlay_config,
        fomc_cal=fomc_cal,
        release_cal={"releases": []},
    )

    two_year = adjusted["tenors"]["2Y"][0]
    assert two_year["central"] == 3.875
    assert two_year["p50"] == 3.875
    assert two_year["overlay_bp"] == -12.5
    assert two_year["uncertainty_widen_bp"] == 18.0
    assert two_year["p90"] == 4.555
    overlay_types = [row["type"] for row in adjusted["metadata"]["event_overlays"]]
    assert overlay_types == ["FOMC", "UNCERTAINTY"]
