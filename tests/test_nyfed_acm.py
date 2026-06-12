import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingestion.nyfed_acm import (
    normalize_acm_table,
    term_premium_change_asof,
    term_premium_change_zscore_asof,
    term_premium_asof,
)
from src.signals.curve_drivers import compute_driver_signals


def test_normalize_acm_table_parses_date_and_10y_term_premium():
    raw = pd.DataFrame(
        {
            "DATE": ["2026-01-31", "2026-02-28"],
            "ACMTP10": [0.12, 0.20],
            "ACMTP5": [0.05, 0.08],
        }
    )

    out = normalize_acm_table(raw)

    assert list(out.columns) == ["ACMTP5", "ACMTP10"]
    assert out.index.name == "date"
    assert out.loc[pd.Timestamp("2026-02-28"), "ACMTP10"] == 0.20


def test_term_premium_asof_never_looks_forward():
    df = pd.DataFrame(
        {"ACMTP10": [0.10, 0.30]},
        index=pd.to_datetime(["2026-01-31", "2026-03-31"]),
    )

    assert term_premium_asof("2026-03-01", df=df) == 0.10


def test_term_premium_change_asof_uses_past_change_with_positive_rising_signal():
    dates = pd.date_range("2026-01-01", periods=80, freq="D")
    df = pd.DataFrame({"ACMTP10": [0.10 + i * 0.01 for i in range(80)]}, index=dates)

    assert term_premium_change_asof("2026-03-20", periods=20, df=df) > 0


def test_term_premium_change_zscore_asof_normalizes_by_rolling_std():
    dates = pd.date_range("2024-01-01", periods=160, freq="D")
    values = [0.10 + i * 0.005 for i in range(120)] + [
        0.70 + i * 0.015 for i in range(40)
    ]
    df = pd.DataFrame({"ACMTP10": values}, index=dates)

    out = term_premium_change_zscore_asof(
        "2024-05-30",
        periods=20,
        window=80,
        df=df,
    )

    assert out is not None
    score, components = out
    assert score > 0
    assert components["acm_10y_change_rolling_std"] > 0


def test_curve_driver_prefers_acm_term_premium_zscore_with_reversion_sign(
    monkeypatch,
):
    dates = pd.date_range("2025-01-01", periods=260, freq="D")
    df = pd.DataFrame(
        {
            "DGS2": [4.0 for _ in dates],
            "DGS5": [4.0 for _ in dates],
            "DGS10": [4.0 for _ in dates],
            "DGS30": [4.0 for _ in dates],
            "T10YIE": [2.0 for _ in dates],
            "T5YIFR": [2.1 for _ in dates],
            "T10Y2Y": [0.0 for _ in dates],
            "VIXCLS": [15.0 for _ in dates],
        },
        index=dates,
    )
    monkeypatch.setattr(
        "src.signals.curve_drivers.term_premium_change_zscore_asof",
        lambda asof: (
            0.80,
            {
                "acm_10y_term_premium_change": 0.50,
                "acm_10y_change_rolling_std": 0.625,
            },
        ),
    )

    signals = compute_driver_signals(df, hawkish=0.0)

    assert signals["term_premium"].components["acm_10y_term_premium_change"] == 0.50
    assert signals["term_premium"].components["acm_10y_change_rolling_std"] == 0.625
    assert signals["term_premium"].score == -0.80
    assert "long-end cheapness" in signals["term_premium"].rationale
