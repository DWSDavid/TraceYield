"""Walk-forward backtest for the v2 UST curve engine."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest.walk_forward import _lagged_history, fred_release_lags
from src.models.curve_engine import CurveForecast, forecast_curve
from src.signals.fomc_series import fomc_factor_asof
from src.utils.config import DATA

TENOR_COLUMNS = {"2Y": "DGS2", "5Y": "DGS5", "10Y": "DGS10", "30Y": "DGS30"}
HORIZON_DAYS = {"3m_core": 63, "6m_core": 126}
DEFAULT_OUTPUT = DATA / "backtest" / "curve_v2_backtest.csv"


def _sign_hit(predicted: float, realized: float) -> bool:
    return bool(np.sign(predicted) == np.sign(realized))


def _shape_from_call(curve_call: str) -> str:
    if "STEEPENING" in curve_call:
        return "STEEPENING"
    if "FLATTENING" in curve_call:
        return "FLATTENING"
    return curve_call


def _realized_shape(realized: dict[str, float]) -> str:
    front = (realized["2Y"] + realized["5Y"]) / 2
    long = (realized["10Y"] + realized["30Y"]) / 2
    slope = long - front
    if slope > 0:
        return "STEEPENING"
    if slope < 0:
        return "FLATTENING"
    return "RANGE_BOUND"


def _realized_changes(
    df: pd.DataFrame,
    d: pd.Timestamp,
    horizon_days: int,
) -> dict[str, float] | None:
    realized: dict[str, float] = {}
    for tenor, col in TENOR_COLUMNS.items():
        s = df[col].dropna().sort_index()
        current_pos = s.index.searchsorted(pd.Timestamp(d), side="right") - 1
        future_pos = current_pos + horizon_days
        if current_pos < 0 or future_pos >= len(s):
            return None
        realized[tenor] = float(s.iloc[future_pos] - s.iloc[current_pos])
    return realized


def _forecast_by_horizon(forecasts: list[CurveForecast]) -> dict[str, CurveForecast]:
    return {forecast.horizon: forecast for forecast in forecasts}


def _row_for_forecast(
    d: pd.Timestamp,
    forecast: CurveForecast,
    realized: dict[str, float],
) -> dict:
    predicted_shape = _shape_from_call(forecast.curve_call)
    realized_shape = _realized_shape(realized)
    row = {
        "date": pd.Timestamp(d).date().isoformat(),
        "horizon": forecast.horizon,
        "curve_call": forecast.curve_call,
        "predicted_shape": predicted_shape,
        "realized_shape": realized_shape,
        "curve_shape_hit": predicted_shape == realized_shape,
        "confidence": forecast.confidence,
        "main_driver": forecast.main_driver,
        "secondary_driver": forecast.secondary_driver,
    }
    for tenor in TENOR_COLUMNS:
        pressure = forecast.tenor_pressure[tenor]
        change = realized[tenor]
        row[f"pressure_{tenor}"] = pressure
        row[f"realized_{tenor}"] = change
        row[f"hit_{tenor}"] = _sign_hit(pressure, change)
    return row


def _summarize(rows: pd.DataFrame) -> dict:
    summary: dict[str, dict] = {}
    thresholds = (0.50, 0.60, 0.70)
    for horizon, group in rows.groupby("horizon"):
        tenor_da = {
            tenor: float(group[f"hit_{tenor}"].mean()) for tenor in TENOR_COLUMNS
        }
        ic_by_tenor = {
            tenor: float(group[f"pressure_{tenor}"].corr(group[f"realized_{tenor}"]))
            for tenor in TENOR_COLUMNS
        }
        threshold_stats = {}
        for threshold in thresholds:
            selected = group[group["confidence"] >= threshold]
            coverage = len(selected) / len(group) if len(group) else 0.0
            if len(selected):
                hit_cols = [f"hit_{tenor}" for tenor in TENOR_COLUMNS]
                tenor_hit = float(selected[hit_cols].to_numpy().mean())
                shape_hit = float(selected["curve_shape_hit"].mean())
            else:
                tenor_hit = float("nan")
                shape_hit = float("nan")
            threshold_stats[threshold] = {
                "coverage": coverage,
                "tenor_hit": tenor_hit,
                "curve_shape_hit": shape_hit,
            }
        summary[horizon] = {
            "n": int(len(group)),
            "tenor_directional_accuracy": tenor_da,
            "ic_by_tenor": ic_by_tenor,
            "curve_shape_hit_rate": float(group["curve_shape_hit"].mean()),
            "confidence_thresholds": threshold_stats,
        }
    return summary


def _print_summary(summary: dict) -> None:
    for horizon, stats in summary.items():
        print(f"\n{horizon}  n={stats['n']}")
        da = "  ".join(
            f"{tenor}:{value * 100:5.1f}%"
            for tenor, value in stats["tenor_directional_accuracy"].items()
        )
        ic = "  ".join(
            f"{tenor}:{value: .3f}" for tenor, value in stats["ic_by_tenor"].items()
        )
        print(f"  Directional accuracy: {da}")
        print(f"  IC: {ic}")
        print(f"  Curve-shape hit: {stats['curve_shape_hit_rate'] * 100:5.1f}%")
        print("  Confidence thresholds:")
        for threshold, threshold_stats in stats["confidence_thresholds"].items():
            print(
                f"    >= {threshold:.2f}: "
                f"coverage={threshold_stats['coverage'] * 100:5.1f}% "
                f"tenor_hit={threshold_stats['tenor_hit'] * 100:5.1f}% "
                f"shape_hit={threshold_stats['curve_shape_hit'] * 100:5.1f}%"
            )


def run_backtest(
    df: pd.DataFrame,
    start: str = "2015-01-01",
    output_path: str | Path = DEFAULT_OUTPUT,
) -> tuple[pd.DataFrame, dict]:
    """Run v2 curve walk-forward backtest and write row-level CSV."""
    df = df.sort_index()
    release_lags = fred_release_lags()
    rows = []
    dates = df["DGS10"].dropna().loc[start:].index

    for d in dates:
        forecasts = _forecast_by_horizon(
            forecast_curve(
                _lagged_history(df, pd.Timestamp(d), release_lags),
                hawkish=fomc_factor_asof(d),
            )
        )
        for horizon, horizon_days in HORIZON_DAYS.items():
            realized = _realized_changes(df, pd.Timestamp(d), horizon_days)
            if realized is None:
                continue
            rows.append(
                _row_for_forecast(pd.Timestamp(d), forecasts[horizon], realized)
            )

    out = pd.DataFrame(rows)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False)
    summary = _summarize(out) if not out.empty else {}
    print(f"Wrote {len(out)} rows -> {output_path}")
    _print_summary(summary)
    return out, summary
