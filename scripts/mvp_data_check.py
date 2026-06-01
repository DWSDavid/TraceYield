"""MVP data-path check for TraceYield.

Run from VS Code or terminal:
  python scripts/mvp_data_check.py

This is intentionally lightweight: it uses the latest cached FRED parquet,
applies the configured publication lags, computes factor scores, and produces
the current v0 prediction without calling any LLM or external API.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.backtest.walk_forward import _lagged_history, fred_release_lags
from src.models.predictor import predict
from src.signals.factors import compute_all, political_risk_proxy
from src.signals.fomc_series import fomc_factor_asof
from src.utils.config import DATA, fred_series


def _configured_series_ids() -> list[str]:
    ids: list[str] = []
    for group in fred_series().values():
        ids.extend(group.keys())
    return ids


def _latest_fred_cache() -> Path:
    cached = sorted((DATA / "processed").glob("fred_*.parquet"))
    if not cached:
        raise FileNotFoundError(
            "No processed FRED cache found. Run scripts/daily_run.py first."
        )
    return cached[-1]


def main() -> None:
    path = _latest_fred_cache()
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()

    configured = _configured_series_ids()
    missing = [sid for sid in configured if sid not in df.columns]
    empty = [sid for sid in configured if sid in df.columns and df[sid].dropna().empty]
    latest_date = df.index.max()

    if missing or empty:
        print("MVP DATA CHECK: FAIL")
        print(f"cache: {path}")
        if missing:
            print("missing columns:", ", ".join(missing))
        if empty:
            print("empty columns:", ", ".join(empty))
        raise SystemExit(1)

    lagged = _lagged_history(df, latest_date, fred_release_lags())
    current_10y = float(lagged["DGS10"].dropna().iloc[-1])
    hawkish = fomc_factor_asof(latest_date)
    factors = compute_all(
        lagged,
        hawkish=hawkish,
        political=political_risk_proxy(lagged),
    )
    preds = predict(factors, current_10y)

    print("MVP DATA CHECK: PASS")
    print(f"cache: {path.name}")
    print(f"configured series: {len(configured)}")
    print(f"date range: {df.index.min().date()} -> {latest_date.date()}")
    print(f"lagged 10Y as-of: {lagged['DGS10'].dropna().index.max().date()}")
    print(f"current 10Y used: {current_10y:.2f}%")
    print("factor scores:")
    for name, score in factors.items():
        print(f"  {name:14s} {score:+.3f}")
    print("predictions:")
    for pred in preds:
        print(
            f"  {pred.horizon:>2s}: {pred.direction:7s} "
            f"score={pred.score:+.3f} target={pred.target_yield:.3f}%"
        )


if __name__ == "__main__":
    main()
