import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.signals.yield_trend import yield_trend_factor


def test_yield_trend_positive_when_10y_trend_rises_and_curve_steepens():
    dates = pd.date_range("2025-01-01", periods=300, freq="D")
    df = pd.DataFrame(
        {
            "DGS2": [3.0 + i * 0.001 for i in range(300)],
            "DGS10": [4.0 + i * 0.004 for i in range(300)],
            "DGS30": [4.5 + i * 0.003 for i in range(300)],
        },
        index=dates,
    )

    assert yield_trend_factor(df) > 0


def test_yield_trend_negative_when_10y_trend_falls_and_curve_flattens():
    dates = pd.date_range("2025-01-01", periods=300, freq="D")
    df = pd.DataFrame(
        {
            "DGS2": [4.0 + i * 0.001 for i in range(300)],
            "DGS10": [5.0 - i * 0.004 for i in range(300)],
            "DGS30": [5.5 - i * 0.003 for i in range(300)],
        },
        index=dates,
    )

    assert yield_trend_factor(df) < 0
