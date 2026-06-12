import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.backtest.benchmarks import momentum_predictions, random_walk_predictions
from src.backtest.eval import evaluate_prediction_frame, forward_curve_targets


def _curve_history(periods: int = 12) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=periods, freq="D")
    return pd.DataFrame(
        {
            "DGS2": [3.00 + 0.01 * i + 0.001 * i * i for i in range(periods)],
            "DGS5": [3.20 + 0.02 * i + 0.002 * i * i for i in range(periods)],
            "DGS10": [3.60 + 0.03 * i + 0.003 * i * i for i in range(periods)],
            "DGS30": [4.10 + 0.04 * i + 0.004 * i * i for i in range(periods)],
        },
        index=dates,
    )


def test_forward_curve_targets_are_future_changes_without_lookahead():
    df = _curve_history()

    targets = forward_curve_targets(df, horizon_days=2)

    assert targets.loc[pd.Timestamp("2026-01-01"), "2Y"] == pytest.approx(0.024)
    assert targets.loc[pd.Timestamp("2026-01-01"), "10Y"] == pytest.approx(0.072)
    assert targets.loc[pd.Timestamp("2026-01-01"), "2s10s"] == pytest.approx(0.048)
    assert targets.loc[pd.Timestamp("2026-01-01"), "5s30s"] == pytest.approx(0.048)
    assert pd.Timestamp("2026-01-12") not in targets.index


def test_evaluate_prediction_frame_reports_ic_da_icir_and_monotonicity():
    df = _curve_history(periods=30)
    targets = forward_curve_targets(df, horizon_days=2)
    predictions = targets * 2.0

    scorecard = evaluate_prediction_frame(
        predictions,
        targets,
        model="toy",
        horizon="2d",
        icir_freq="10D",
    )

    ten_year = scorecard.set_index("target").loc["10Y"]
    assert ten_year["rank_ic"] == pytest.approx(1.0)
    assert ten_year["directional_accuracy"] == 1.0
    assert ten_year["quantile_monotonic"] is True
    assert ten_year["n"] == len(targets)
    assert "icir" in scorecard.columns


def test_random_walk_and_momentum_predictions_match_phase0_definitions():
    df = _curve_history()

    rw_moves, rw_shape = random_walk_predictions(df)
    assert (rw_moves[["2Y", "5Y", "10Y", "30Y"]] == 0.0).all().all()
    assert rw_moves.loc[pd.Timestamp("2026-01-05"), "2s10s"] == (
        df.loc[pd.Timestamp("2026-01-05"), "DGS10"]
        - df.loc[pd.Timestamp("2026-01-05"), "DGS2"]
    )
    assert rw_shape.equals(rw_moves[["2s10s", "5s30s"]])

    mom_moves, mom_shape = momentum_predictions(df, lookback_days=3)
    assert mom_moves.loc[pd.Timestamp("2026-01-05"), "2Y"] == pytest.approx(0.045)
    assert mom_moves.loc[pd.Timestamp("2026-01-05"), "2s10s"] == pytest.approx(0.09)
    assert mom_shape.loc[pd.Timestamp("2026-01-05"), "2s10s"] == pytest.approx(
        df.loc[pd.Timestamp("2026-01-05"), "DGS10"]
        - df.loc[pd.Timestamp("2026-01-05"), "DGS2"]
        + 0.09
    )
