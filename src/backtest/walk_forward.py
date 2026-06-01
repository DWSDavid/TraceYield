"""Walk-forward backtest skeleton — the source of truth for any weight/factor.

Idea: for each historical day, compute factor scores using ONLY data available
up to that day, make a prediction, then compare to the realized 10Y move N days
later. Report hit-rate (direction) and RMSE (level) per horizon. No look-ahead.

This is a stub: fill in once ingestion has real history cached.
"""
from __future__ import annotations

import pandas as pd

from src.signals.factors import compute_all
from src.models.predictor import predict

HORIZON_DAYS = {"1w": 5, "1m": 21, "3m": 63}


def run(df: pd.DataFrame, start: str = "2015-01-01") -> pd.DataFrame:
    """Naive walk-forward over the cached FRED frame. Returns per-day results."""
    df = df.sort_index()
    dates = df.loc[start:].index
    rows = []
    for d in dates:
        hist = df.loc[:d]
        if "DGS10" not in hist or hist["DGS10"].dropna().empty:
            continue
        cur = float(hist["DGS10"].dropna().iloc[-1])
        factors = compute_all(hist)
        preds = predict(factors, cur)
        for p in preds:
            fwd = HORIZON_DAYS[p.horizon]
            future = df["DGS10"].shift(-fwd).loc[d]
            if pd.isna(future):
                continue
            realized_dir = "Bear" if future > cur else "Bull"
            rows.append({
                "date": d, "horizon": p.horizon, "pred_dir": p.direction,
                "realized_dir": realized_dir, "score": p.score,
                "pred_target": p.target_yield, "realized": future,
                "correct": p.direction == realized_dir,
            })
    res = pd.DataFrame(rows)
    if not res.empty:
        print(res.groupby("horizon")["correct"].mean().rename("hit_rate"))
    return res
