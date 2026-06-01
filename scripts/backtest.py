"""Run the walk-forward backtest on the cached FRED history.

  python scripts/backtest.py            # uses latest cached FRED parquet
  python scripts/backtest.py 2010-01-01 # custom start date
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

import pandas as pd

from src.utils.config import DATA
from src.ingestion.fred_client import fetch_all
from src.backtest.walk_forward import run


def _load_history() -> pd.DataFrame:
    """Prefer the freshest cached FRED parquet; else fetch."""
    cached = sorted((DATA / "processed").glob("fred_*.parquet"))
    if cached:
        print(f"Loading cached history: {cached[-1].name}")
        df = pd.read_parquet(cached[-1])
        df.index = pd.to_datetime(df.index)
        return df
    print("No cache found; fetching from FRED...")
    return fetch_all()


def main() -> None:
    start = sys.argv[1] if len(sys.argv) > 1 else "2015-01-01"
    df = _load_history()
    run(df, start=start)


if __name__ == "__main__":
    main()
