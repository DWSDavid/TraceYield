import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models import fadns
from src.models.fadns import (
    MACRO_BLOCK_ALIGNED_TARGETS,
    MACRO_BLOCKS,
    build_base_adjusted_ic_summary,
    build_fadns_prediction_frames,
    build_macro_block_ic_scorecard,
    build_macro_block_sanity_scorecard,
    forecast_base_adjusted_attribution,
    nelson_siegel_beta_frame,
    run_fadns_scorecard,
    run_macro_block_ic_sanity,
    summarize_macro_block_sanity,
    _macro_feature_frame,
)


def _curve_history(periods: int = 240) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=periods, freq="D")
    trend = np.linspace(0.0, 1.0, periods)
    level = 3.5 + 0.15 * trend
    slope = -0.6 + 0.35 * trend
    curvature = 0.05 * np.sin(np.arange(periods) / 15.0)
    return pd.DataFrame(
        {
            "DGS2": level - 0.30 * slope + curvature,
            "DGS5": level - 0.10 * slope + 0.3 * curvature,
            "DGS10": level + 0.15 * slope - 0.2 * curvature,
            "DGS30": level + 0.45 * slope,
            "T10Y2Y": (level + 0.15 * slope) - (level - 0.30 * slope),
            "PCEPILFE": 120 + trend,
            "PCEPI": 125 + 1.2 * trend,
            "CPIAUCSL": 300 + 1.5 * trend,
            "CPILFESL": 305 + 1.4 * trend,
            "T5YIE": 2.1 + 0.05 * trend,
            "T10YIE": 2.2 + 0.04 * trend,
            "T5YIFR": 2.3 + 0.03 * trend,
            "DFEDTARU": 4.0,
            "DGS3MO": 3.9 + 0.01 * trend,
            "DGS6MO": 3.95 + 0.02 * trend,
            "FEDTARMD": 3.5,
            "PAYEMS": 155000 + 1000 * trend,
            "UNRATE": 4.0 - 0.1 * trend,
            "ICSA": 220000 - 5000 * trend,
            "RSAFS": 700000 + 1500 * trend,
            "WALCL": 7500000 - 100000 * trend,
            "WRESBAL": 3200000 - 50000 * trend,
            "RRPONTSYD": 400000 - 25000 * trend,
            "WTREGEN": 800000 + 100000 * trend,
            "IRLTLT01DEM156N": 2.5 + 0.02 * trend,
            "IRLTLT01JPM156N": 1.0 + 0.01 * trend,
            "DTWEXBGS": 120 + 0.5 * trend,
        },
        index=dates,
    )


def _phase0_scorecard() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"model": model, "horizon": horizon, "target": target, "rank_ic": rank_ic}
            for model, rank_ic in (("random_walk", -0.05), ("momentum_3m", 0.02))
            for horizon in ("3m", "6m")
            for target in ("2Y", "5Y", "10Y", "30Y", "2s10s", "5s30s")
        ]
    )


def test_nelson_siegel_beta_frame_uses_curve_columns():
    betas = nelson_siegel_beta_frame(_curve_history(80))

    assert list(betas.columns) == ["level", "slope", "curvature"]
    assert len(betas) == 80
    assert betas.index.is_monotonic_increasing
    assert betas.notna().all().all()


def test_fadns_walk_forward_predictions_are_point_in_time_and_target_shaped():
    history = _curve_history(240)

    frames = build_fadns_prediction_frames(
        history,
        start="2025-04-15",
        horizons={"3m": 21, "6m": 42},
        min_train=60,
        ridge_alpha=1.0,
    )

    assert set(frames) == {"3m", "6m"}
    for frame in frames.values():
        assert {"2Y", "5Y", "10Y", "30Y", "2s10s", "5s30s"}.issubset(frame.columns)
        assert frame.index.min() >= pd.Timestamp("2025-04-15")
        assert frame.index.max() <= history.index.max()
        assert frame.notna().all().all()


def test_macro_feature_frame_uses_five_standardized_blocks():
    history = _curve_history(240)
    macro = _macro_feature_frame(history, history.index)

    assert tuple(macro.columns) == MACRO_BLOCKS
    assert set(macro.columns) == {
        "inflation_regime",
        "policy_path",
        "growth_risk",
        "liquidity_supply",
        "global_relative_value",
    }
    assert macro.notna().all().all()
    assert (macro.abs() <= 1.0).all().all()


def test_inflation_regime_uses_latest_core_cpi_and_headline_pce():
    history = _curve_history(320)
    base_history = history.drop(columns=["CPILFESL", "PCEPI"])
    enriched = base_history.copy()
    enriched["CPILFESL"] = base_history["CPIAUCSL"].copy()
    enriched["PCEPI"] = base_history["PCEPILFE"].copy()
    enriched.loc[enriched.index[-80:], "CPILFESL"] += np.linspace(0.0, 8.0, 80)
    enriched.loc[enriched.index[-80:], "PCEPI"] += np.linspace(0.0, 6.0, 80)

    base_inflation = _macro_feature_frame(
        base_history,
        base_history.index,
    )[
        "inflation_regime"
    ].iloc[-1]
    enriched_inflation = _macro_feature_frame(
        enriched,
        enriched.index,
    )[
        "inflation_regime"
    ].iloc[-1]

    assert enriched_inflation != base_inflation


def test_liquidity_supply_ignores_future_qra_calendar_for_central(monkeypatch):
    history = _curve_history(240)
    future_qra = pd.Timestamp(history.index[-1]) + pd.Timedelta(days=5)

    def calendar_with_future_qra(name: str) -> dict:
        if name == "data_release_calendar":
            return {
                "releases": [
                    {
                        "indicator": "qra",
                        "release_date": future_qra.date().isoformat(),
                        "reference_month": future_qra.strftime("%Y-%m"),
                        "precision": "estimated",
                    }
                ]
            }
        return {}

    monkeypatch.setattr(fadns, "load_yaml", calendar_with_future_qra)
    monkeypatch.setattr(fadns, "auction_stress_asof", lambda d: None, raising=False)
    with_future_qra = fadns._macro_feature_frame(
        history,
        history.index,
    )[
        "liquidity_supply"
    ].iloc[-1]

    monkeypatch.setattr(fadns, "load_yaml", lambda name: {"releases": []})
    without_future_qra = fadns._macro_feature_frame(
        history,
        history.index,
    )[
        "liquidity_supply"
    ].iloc[-1]

    assert with_future_qra == without_future_qra


def test_liquidity_supply_uses_realized_auction_stress(monkeypatch):
    history = _curve_history(240)
    monkeypatch.setattr(fadns, "load_yaml", lambda name: {"releases": []})
    monkeypatch.setattr(fadns, "auction_stress_asof", lambda d: None, raising=False)
    without_auction = fadns._macro_feature_frame(
        history,
        history.index,
    )[
        "liquidity_supply"
    ].iloc[-1]

    monkeypatch.setattr(fadns, "auction_stress_asof", lambda d: 0.8, raising=False)
    with_auction = fadns._macro_feature_frame(
        history,
        history.index,
    )[
        "liquidity_supply"
    ].iloc[-1]

    assert with_auction > without_auction


def test_base_adjusted_attribution_sums_exactly_by_ns_factor_and_target():
    macro_columns = list(MACRO_BLOCKS)
    coefficients = np.zeros((1 + 3 + len(macro_columns), 3))
    coefficients[1:4, :] = np.eye(3)
    coefficients[4, :] = [0.10, 0.00, 0.00]
    coefficients[5, :] = [0.00, -0.20, 0.00]
    coefficients[6, :] = [0.00, 0.00, 0.30]
    last_beta = np.array([3.0, -0.6, 0.1])
    last_macro = np.array([1.0, 0.5, -1.0, 0.0, 0.0])

    result = forecast_base_adjusted_attribution(
        coefficients,
        last_beta,
        last_macro,
        macro_columns=macro_columns,
        horizon_days=1,
    )

    for factor, row in result["ns_factors"].items():
        assert (
            abs(sum(row["contributions"].values()) - row["total_delta"]) < 1e-10
        ), factor

    for target in ("2Y", "5Y", "10Y", "2s10s"):
        row = result["targets"][target]
        assert (
            abs(sum(row["contributions_bp"].values()) - row["total_delta_bp"]) < 1e-8
        ), target


def test_fadns_scorecard_reports_hac_and_benchmark_comparison(tmp_path):
    scorecard = run_fadns_scorecard(
        _curve_history(260),
        start="2025-04-15",
        phase0_scorecard=_phase0_scorecard(),
        phase1_scorecard=pd.DataFrame(
            [
                {
                    "row_type": "factor",
                    "factor": "policy_path",
                    "horizon": horizon,
                    "target": target,
                    "rank_ic": 0.03,
                }
                for horizon in ("3m", "6m")
                for target in ("2s10s", "5s30s")
            ]
        ),
        output_path=tmp_path / "fadns.csv",
        horizons={"3m": 21, "6m": 42},
        min_train=60,
        ridge_alpha=1.0,
    )

    assert (tmp_path / "fadns.csv").exists()
    assert {
        "rank_ic",
        "nw_t_stat",
        "benchmark_delta_ic",
        "policy_path_delta_ic",
    }.issubset(scorecard.columns)
    curve_rows = scorecard[scorecard["target"].isin(["2s10s", "5s30s"])]
    assert not curve_rows.empty
    assert curve_rows["model"].unique().tolist() == ["fadns"]


def test_base_adjusted_ic_and_macro_block_sanity_contracts():
    history = _curve_history(260)

    base_adjusted = build_base_adjusted_ic_summary(
        history,
        start="2025-04-15",
        horizons={"3m": 21},
        min_train=60,
        ridge_alpha=1.0,
    )
    sanity = build_macro_block_sanity_scorecard(
        history,
        start="2025-04-15",
        horizons={"3m": 21},
    )

    assert {"model", "horizon", "target", "rank_ic"}.issubset(base_adjusted.columns)
    assert set(base_adjusted["model"]) == {"fadns_base", "fadns_adjusted"}
    assert {"macro_block", "horizon", "target", "rank_ic", "decision"}.issubset(
        sanity.columns
    )
    assert set(sanity["macro_block"]) == set(MACRO_BLOCKS)


def test_macro_block_ic_scorecard_uses_aligned_targets_noise_and_nw_contract():
    history = _curve_history(320)

    scorecard = build_macro_block_ic_scorecard(
        history,
        start="2025-04-15",
        horizons={"3m": 21, "6m": 42},
    )

    expected_pairs = {
        (block, horizon, target)
        for block, targets in MACRO_BLOCK_ALIGNED_TARGETS.items()
        for horizon in ("3m", "6m")
        for target in targets
    }
    actual_pairs = set(
        zip(scorecard["macro_block"], scorecard["horizon"], scorecard["target"])
    )
    assert actual_pairs == expected_pairs
    assert {
        "expected_sign",
        "noise_band",
        "rank_ic",
        "signed_rank_ic",
        "directional_accuracy",
        "nw_t_stat",
        "nw_abs_t_stat",
        "correct_sign",
        "verdict",
    }.issubset(scorecard.columns)
    assert scorecard.loc[
        scorecard["horizon"].eq("3m"), "noise_band"
    ].unique().tolist() == [0.15]
    assert scorecard.loc[
        scorecard["horizon"].eq("6m"), "noise_band"
    ].unique().tolist() == [0.22]
    policy_slope = scorecard[
        scorecard["macro_block"].eq("policy_path") & scorecard["target"].eq("2s10s")
    ]
    assert policy_slope["expected_sign"].unique().tolist() == ["-"]
    assert set(scorecard["verdict"]).issubset({"signal", "explanation-only"})


def test_macro_block_sanity_summary_and_csv_contract(tmp_path):
    history = _curve_history(320)
    output_path = tmp_path / "phase4_macro_block_ic.csv"

    scorecard = run_macro_block_ic_sanity(
        history,
        start="2025-04-15",
        horizons={"3m": 21, "6m": 42},
        output_path=output_path,
    )
    summary = summarize_macro_block_sanity(scorecard)

    assert output_path.exists()
    assert set(summary) == set(MACRO_BLOCKS)
    for block, row in summary.items():
        assert {
            "ic_3m",
            "ic_6m",
            "dir_acc_3m",
            "nw_t_3m",
            "aligned_target",
            "expected_sign",
            "verdict",
            "note",
        }.issubset(row)
        assert row["aligned_target"] in MACRO_BLOCK_ALIGNED_TARGETS[block]
        assert row["verdict"] in {"signal", "explanation-only"}
