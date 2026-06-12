"""Treasury-yield historical pattern factor.

The score is intentionally simple and interpretable:
positive = upward yield pressure, negative = downward yield pressure.
It uses only point-in-time yield history already passed into the factor layer.
"""

from __future__ import annotations

import pandas as pd


def _clip(value: float) -> float:
    return float(max(-1.0, min(1.0, value)))


def _change_score(s: pd.Series, periods: int, full_scale_pct_points: float) -> float:
    s = s.dropna()
    if len(s) <= periods:
        return 0.0
    change = float(s.iloc[-1] - s.iloc[-periods - 1])
    return _clip(change / full_scale_pct_points)


def _range_position_score(s: pd.Series, window: int = 252) -> float:
    s = s.dropna().tail(window)
    if len(s) < 20:
        return 0.0
    low = float(s.min())
    high = float(s.max())
    if high == low:
        return 0.0
    position = (float(s.iloc[-1]) - low) / (high - low)
    return _clip((position - 0.5) * 2.0)


def _curve_change_score(df: pd.DataFrame, short_col: str, long_col: str) -> float:
    if short_col not in df or long_col not in df:
        return 0.0
    spread = (df[long_col] - df[short_col]).dropna()
    return _change_score(spread, periods=63, full_scale_pct_points=0.30)


def yield_trend_factor(df: pd.DataFrame) -> float:
    """Score 10Y momentum, range position, and curve trend in [-1, +1]."""
    if "DGS10" not in df:
        return 0.0

    ten_year = df["DGS10"]
    momentum = (
        0.40 * _change_score(ten_year, periods=21, full_scale_pct_points=0.25)
        + 0.35 * _change_score(ten_year, periods=63, full_scale_pct_points=0.50)
        + 0.25 * _change_score(ten_year, periods=126, full_scale_pct_points=0.75)
    )
    range_position = _range_position_score(ten_year)
    curve_trend = 0.60 * _curve_change_score(
        df, "DGS2", "DGS10"
    ) + 0.40 * _curve_change_score(df, "DGS5", "DGS30")
    if "DGS5" not in df and "DGS30" in df:
        curve_trend = 0.60 * _curve_change_score(
            df, "DGS2", "DGS10"
        ) + 0.40 * _curve_change_score(df, "DGS10", "DGS30")

    return _clip(0.55 * momentum + 0.25 * range_position + 0.20 * curve_trend)
