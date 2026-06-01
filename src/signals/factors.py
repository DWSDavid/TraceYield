"""Turn raw data into the five factor scores, each normalized to ~[-1, +1]
where POSITIVE = upward pressure on yields (bond bearish).

This is deliberately simple and rule-based for v0 so the first backtest is
interpretable. The ML model (models/) later learns refinements on top of these.
"""
from __future__ import annotations

import pandas as pd


def _zscore_last(s: pd.Series, window: int = 252) -> float:
    """Z-score of the latest value vs a trailing window, clipped to [-1, 1]."""
    s = s.dropna()
    if len(s) < 20:
        return 0.0
    w = s.tail(window)
    std = w.std()
    if std == 0:
        return 0.0
    z = (s.iloc[-1] - w.mean()) / std
    return float(max(-1.0, min(1.0, z / 2.0)))  # /2 so ~2sigma maps to the edge


def inflation_factor(df: pd.DataFrame) -> float:
    """Rising core PCE + rising breakevens => positive (yields up)."""
    parts = []
    if "PCEPILFE" in df:
        parts.append(_zscore_last(df["PCEPILFE"].pct_change(12) * 100))
    if "T10YIE" in df:
        parts.append(_zscore_last(df["T10YIE"]))
    return sum(parts) / len(parts) if parts else 0.0


def liquidity_factor(df: pd.DataFrame) -> float:
    """Shrinking Fed assets / falling reserves => tighter => positive."""
    parts = []
    if "WALCL" in df:
        parts.append(-_zscore_last(df["WALCL"].pct_change(13)))   # QT = balance down
    if "WRESBAL" in df:
        parts.append(-_zscore_last(df["WRESBAL"].pct_change(13)))
    return sum(parts) / len(parts) if parts else 0.0


def global_rates_factor(df: pd.DataFrame) -> float:
    """Widening US-foreign differential => relative US yield pressure."""
    if "DGS10" in df and "IRLTLT01DEM156N" in df:
        diff = (df["DGS10"] - df["IRLTLT01DEM156N"]).dropna()
        return _zscore_last(diff)
    return 0.0


def political_risk_factor(score: float = 0.0) -> float:
    """Placeholder: fed by news NLP later. Safe-haven demand can push EITHER way;
    default neutral until the news pipeline exists."""
    return max(-1.0, min(1.0, score))


def fomc_factor(hawkish_score: float = 0.0) -> float:
    """Direct pass-through of the NLP hawkish/dovish score (already in [-1, 1])."""
    return max(-1.0, min(1.0, hawkish_score))


def compute_all(df: pd.DataFrame, hawkish: float = 0.0,
                political: float = 0.0) -> dict:
    return {
        "fomc_nlp": fomc_factor(hawkish),
        "inflation": inflation_factor(df),
        "liquidity": liquidity_factor(df),
        "global_rates": global_rates_factor(df),
        "political_risk": political_risk_factor(political),
    }
