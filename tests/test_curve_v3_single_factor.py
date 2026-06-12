import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.backtest.single_factor import (
    build_phase1_scorecard,
    cochrane_piazzesi_factor_asof,
    nelson_siegel_factors_asof,
    single_factor_target_signal,
)
from src.signals import curve_drivers
from src.signals.curve_drivers import compute_driver_signals


def _daily_curve_history(periods: int = 90) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=periods, freq="D")
    return pd.DataFrame(
        {
            "DGS2": [3.00 + 0.004 * i for i in range(periods)],
            "DGS5": [3.20 + 0.005 * i for i in range(periods)],
            "DGS10": [3.50 + 0.006 * i for i in range(periods)],
            "DGS30": [3.90 + 0.007 * i for i in range(periods)],
            "T10Y2Y": [0.50 + 0.001 * i for i in range(periods)],
            "VIXCLS": [15.0 for _ in range(periods)],
        },
        index=dates,
    )


def test_cp_and_nelson_siegel_factors_use_existing_curve_yields():
    hist = _daily_curve_history()

    ns = nelson_siegel_factors_asof(hist)
    cp = cochrane_piazzesi_factor_asof(hist)

    assert {"ns_level", "ns_slope"}.issubset(ns)
    assert isinstance(ns["ns_level"], float)
    assert isinstance(ns["ns_slope"], float)
    assert isinstance(cp, float)

    cp_targets = single_factor_target_signal("cochrane_piazzesi", 0.5)
    assert set(cp_targets) == {"2Y", "5Y", "10Y", "30Y", "2s10s", "5s30s"}
    assert cp_targets["10Y"] < 0
    assert cp_targets["30Y"] < cp_targets["5Y"]


def test_macro_surprise_uses_release_acceleration_proxy_not_inflation_level():
    dates = pd.date_range("2022-01-31", periods=48, freq="ME")
    cpi = [300.0]
    pce = [120.0]
    for i in range(1, len(dates)):
        cpi.append(cpi[-1] * (1.0 + 0.001 + 0.0001 * i))
        pce.append(pce[-1] * (1.0 + 0.0005 + 0.00005 * i))
    df = pd.DataFrame({"CPIAUCSL": cpi, "PCEPILFE": pce}, index=dates)

    macro = compute_driver_signals(df, hawkish=0.0)["macro_surprise"]

    assert macro.score > 0
    assert "cpi_release_acceleration_proxy" in macro.components
    assert "core_pce_release_acceleration_proxy" in macro.components
    assert "cpi_level_proxy" not in macro.components
    assert "release-over-release acceleration" in macro.rationale


def test_growth_risk_no_longer_reuses_vix_and_risk_off_detects_vix_spikes():
    base = _daily_curve_history()
    calm = base.copy()
    stressed = base.copy()
    stressed["VIXCLS"] = [15.0 for _ in range(len(stressed) - 5)] + [
        20.0,
        24.0,
        29.0,
        35.0,
        42.0,
    ]

    calm_signals = compute_driver_signals(calm, hawkish=0.0)
    stressed_signals = compute_driver_signals(stressed, hawkish=0.0)

    assert stressed_signals["growth_risk"].score == calm_signals["growth_risk"].score
    assert (
        stressed_signals["risk_off_overlay"].score
        < calm_signals["risk_off_overlay"].score
    )
    assert "vix" not in " ".join(stressed_signals["growth_risk"].components)
    assert "vix_spike" in stressed_signals["risk_off_overlay"].components


def test_term_premium_signal_uses_rolling_std_normalization(monkeypatch):
    dates = pd.date_range("2026-01-01", periods=90, freq="D")
    df = pd.DataFrame(index=dates)

    monkeypatch.setattr(
        curve_drivers,
        "term_premium_change_zscore_asof",
        lambda asof: (
            0.8,
            {
                "acm_10y_term_premium_change": 0.20,
                "acm_10y_change_rolling_std": 0.25,
            },
        ),
    )

    score, components, rationale = curve_drivers._term_premium_signal(
        df, pd.Timestamp("2026-03-31")
    )

    assert score == -0.8
    assert components["acm_10y_change_rolling_std"] == 0.25
    assert "rolling std" in rationale
    assert "long-end cheapness" in rationale


def test_phase1_scorecard_preserves_per_target_rows_and_keeps_aligned_curve_signal():
    metrics = pd.DataFrame(
        [
            {
                "model": "policy_path",
                "horizon": "3m",
                "target": "2Y",
                "n": 126,
                "rank_ic": 0.20,
                "directional_accuracy": 0.56,
            },
            {
                "model": "policy_path",
                "horizon": "3m",
                "target": "5Y",
                "n": 126,
                "rank_ic": 0.04,
                "directional_accuracy": 0.51,
            },
            {
                "model": "policy_path",
                "horizon": "3m",
                "target": "10Y",
                "n": 126,
                "rank_ic": -0.03,
                "directional_accuracy": 0.49,
            },
            {
                "model": "policy_path",
                "horizon": "3m",
                "target": "30Y",
                "n": 126,
                "rank_ic": -0.18,
                "directional_accuracy": 0.45,
            },
            {
                "model": "policy_path",
                "horizon": "3m",
                "target": "2s10s",
                "n": 126,
                "rank_ic": 0.26,
                "directional_accuracy": 0.58,
            },
            {
                "model": "policy_path",
                "horizon": "3m",
                "target": "5s30s",
                "n": 126,
                "rank_ic": 0.08,
                "directional_accuracy": 0.53,
            },
            {
                "model": "policy_path",
                "horizon": "6m",
                "target": "2Y",
                "n": 126,
                "rank_ic": 0.18,
                "directional_accuracy": 0.55,
            },
            {
                "model": "policy_path",
                "horizon": "6m",
                "target": "5Y",
                "n": 126,
                "rank_ic": 0.03,
                "directional_accuracy": 0.50,
            },
            {
                "model": "policy_path",
                "horizon": "6m",
                "target": "10Y",
                "n": 126,
                "rank_ic": -0.02,
                "directional_accuracy": 0.49,
            },
            {
                "model": "policy_path",
                "horizon": "6m",
                "target": "30Y",
                "n": 126,
                "rank_ic": -0.16,
                "directional_accuracy": 0.46,
            },
            {
                "model": "policy_path",
                "horizon": "6m",
                "target": "2s10s",
                "n": 126,
                "rank_ic": 0.24,
                "directional_accuracy": 0.57,
            },
            {
                "model": "policy_path",
                "horizon": "6m",
                "target": "5s30s",
                "n": 126,
                "rank_ic": 0.07,
                "directional_accuracy": 0.52,
            },
        ]
    )

    phase0 = pd.DataFrame(
        [
            {
                "model": "momentum_3m",
                "horizon": "3m",
                "target": "2Y",
                "n": 126,
                "rank_ic": 0.22,
            },
            {
                "model": "momentum_3m",
                "horizon": "6m",
                "target": "2Y",
                "n": 126,
                "rank_ic": 0.24,
            },
            {
                "model": "momentum_3m",
                "horizon": "3m",
                "target": "2s10s",
                "n": 126,
                "rank_ic": 0.15,
            },
            {
                "model": "momentum_3m",
                "horizon": "6m",
                "target": "2s10s",
                "n": 126,
                "rank_ic": 0.20,
            },
            {
                "model": "momentum_3m",
                "horizon": "3m",
                "target": "5s30s",
                "n": 126,
                "rank_ic": 0.05,
            },
            {
                "model": "momentum_3m",
                "horizon": "6m",
                "target": "5s30s",
                "n": 126,
                "rank_ic": 0.05,
            },
        ]
    )

    scorecard = build_phase1_scorecard({"policy_path": metrics}, phase0)

    factor_rows = scorecard[scorecard["row_type"].eq("factor")]
    assert len(factor_rows) == 12
    assert {"horizon", "target", "rank_ic"}.issubset(scorecard.columns)
    assert "mean_rank_ic" not in scorecard.columns
    assert "icir" not in scorecard.columns
    assert "benchmark_rank_ic" in scorecard.columns
    assert "benchmark_delta_ic" in scorecard.columns
    policy = factor_rows[factor_rows["factor"] == "policy_path"]
    assert set(policy["target"]) == {"2Y", "5Y", "10Y", "30Y", "2s10s", "5s30s"}
    assert policy["tag"].unique().tolist() == ["keep"]
    assert policy["decision_target"].unique().tolist() == ["2s10s"]
    assert policy.loc[policy["target"].eq("30Y"), "rank_ic"].iloc[0] == -0.18
    decision = policy[policy["target"].eq("2s10s") & policy["horizon"].eq("3m")].iloc[0]
    assert decision["benchmark_rank_ic"] == 0.15
    assert decision["benchmark_delta_ic"] == 0.11


def test_phase1_scorecard_demotes_positive_signal_below_momentum_bar():
    rows = []
    phase0_rows = []
    for horizon, bar in (("3m", 0.22), ("6m", 0.24)):
        rows.append(
            {
                "model": "positioning_momentum",
                "horizon": horizon,
                "target": "2Y",
                "n": 252,
                "rank_ic": 0.10,
                "directional_accuracy": 0.53,
            }
        )
        phase0_rows.append(
            {
                "model": "momentum_3m",
                "horizon": horizon,
                "target": "2Y",
                "n": 252,
                "rank_ic": bar,
            }
        )

    scorecard = build_phase1_scorecard(
        {"positioning_momentum": pd.DataFrame(rows)},
        pd.DataFrame(phase0_rows),
    )

    factor_rows = scorecard[scorecard["row_type"].eq("factor")]
    assert factor_rows["tag"].unique().tolist() == ["below_benchmark"]
    assert factor_rows["decision_target"].unique().tolist() == ["2Y"]
    assert factor_rows["decision_benchmark_delta_3m"].unique().tolist() == [-0.12]
    assert factor_rows["decision_benchmark_delta_6m"].unique().tolist() == [-0.14]


def test_phase1_scorecard_does_not_posthoc_flip_wrong_sign_without_code_bug():
    rows = []
    for horizon in ("3m", "6m"):
        for target in ("2Y", "5Y", "10Y", "30Y", "2s10s", "5s30s"):
            rank_ic = -0.02
            if target in {"10Y", "30Y"}:
                rank_ic = -0.16 if horizon == "3m" else -0.14
            rows.append(
                {
                    "model": "liquidity_supply",
                    "horizon": horizon,
                    "target": target,
                    "n": 252,
                    "rank_ic": rank_ic,
                    "directional_accuracy": 0.45,
                }
            )

    scorecard = build_phase1_scorecard({"liquidity_supply": pd.DataFrame(rows)})

    assert scorecard["tag"].unique().tolist() == ["sign_mismatch"]
    assert scorecard["decision_target"].unique().tolist() == ["10Y"]
    assert "adjusted_rank_ic" not in scorecard.columns
    assert "sign_adjustment" not in scorecard.columns
    assert scorecard["sign_audit_status"].unique().tolist() == ["no_code_sign_bug"]
    decision_row = scorecard[
        scorecard["target"].eq("10Y") & scorecard["horizon"].eq("3m")
    ].iloc[0]
    assert decision_row["rank_ic"] == -0.16
    assert "overlapping" in decision_row["window_caveat"]
    assert decision_row["effective_independent_n"] == 4.0
