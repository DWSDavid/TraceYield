"""Phase 0 naive benchmarks for v3 curve-shape targets."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.backtest.eval import (
    CURVE_SPREADS,
    HORIZON_DAYS,
    TARGETS,
    TENOR_COLUMNS,
    curve_spread_levels,
    evaluate_prediction_frame,
    forward_curve_shapes,
    forward_curve_targets,
)
from src.utils.config import DATA

DEFAULT_OUTPUT = DATA / "backtest" / "phase0_benchmarks.csv"
MOMENTUM_LOOKBACK_DAYS = 63


def _prediction_shell(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(0.0, index=df.index, columns=TARGETS)


def random_walk_predictions(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Random walk: tenor moves are neutral; curve shape sign persists."""
    clean = df[[*TENOR_COLUMNS.values()]].dropna().sort_index()
    predictions = _prediction_shell(clean)
    spreads = curve_spread_levels(clean)
    for spread in CURVE_SPREADS:
        predictions[spread] = spreads[spread]
    return predictions, spreads


def momentum_predictions(
    df: pd.DataFrame,
    lookback_days: int = MOMENTUM_LOOKBACK_DAYS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """AR(1)/momentum: trailing 3m yield and spread moves continue."""
    clean = df[[*TENOR_COLUMNS.values()]].dropna().sort_index()
    predictions = _prediction_shell(clean)

    for tenor, col in TENOR_COLUMNS.items():
        predictions[tenor] = clean[col] - clean[col].shift(lookback_days)

    spreads = curve_spread_levels(clean)
    spread_moves = spreads - spreads.shift(lookback_days)
    for spread in CURVE_SPREADS:
        predictions[spread] = spread_moves[spread]

    predicted_shapes = spreads + spread_moves
    return predictions, predicted_shapes


def _print_phase0_summary(scorecard: pd.DataFrame) -> None:
    print("\nPhase 0 benchmark scorecard")
    print("-" * 76)
    for (model, horizon), group in scorecard.groupby(["model", "horizon"]):
        tenor = group[group["target"].isin(TENOR_COLUMNS)]
        curves = group[group["target"].isin(CURVE_SPREADS)]
        tenor_ic = tenor["rank_ic"].mean(skipna=True)
        curve_ic = curves["rank_ic"].mean(skipna=True)
        tenor_da = tenor["directional_accuracy"].mean(skipna=True)
        curve_hit = curves["curve_shape_hit_rate"].mean(skipna=True)
        print(
            f"{model:16s} {horizon:>2s}  "
            f"tenor Rank IC={tenor_ic: .3f}  "
            f"tenor DA={tenor_da * 100:5.1f}%  "
            f"curve Rank IC={curve_ic: .3f}  "
            f"shape hit={curve_hit * 100:5.1f}%"
        )


def run_phase0_benchmarks(
    df: pd.DataFrame,
    *,
    start: str = "2015-01-01",
    output_path: str | Path = DEFAULT_OUTPUT,
) -> pd.DataFrame:
    """Run random-walk and 3m momentum benchmarks and write the scorecard."""
    history = df.sort_index()
    rows = []
    benchmark_builders = {
        "random_walk": random_walk_predictions,
        "momentum_3m": momentum_predictions,
    }

    for horizon, horizon_days in HORIZON_DAYS.items():
        targets = forward_curve_targets(history, horizon_days).loc[start:]
        future_shapes = forward_curve_shapes(history, horizon_days).reindex(
            targets.index
        )
        for name, builder in benchmark_builders.items():
            predictions, predicted_shapes = builder(history)
            scorecard = evaluate_prediction_frame(
                predictions.reindex(targets.index),
                targets,
                model=name,
                horizon=horizon,
                predicted_shapes=predicted_shapes.reindex(targets.index),
                future_shapes=future_shapes,
            )
            scorecard.insert(0, "phase", "phase0")
            rows.append(scorecard)

    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False)
    print(f"Wrote Phase 0 benchmarks -> {output_path} ({len(out)} rows)")
    if not out.empty:
        _print_phase0_summary(out)
    return out
