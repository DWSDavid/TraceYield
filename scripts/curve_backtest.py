"""Run the v2 UST curve walk-forward backtest from processed FRED cache."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.backtest.curve_v2 import DEFAULT_OUTPUT, run_backtest
from src.utils.config import DATA


def _latest_fred_cache() -> Path:
    cached = sorted((DATA / "processed").glob("fred_*.parquet"))
    if not cached:
        raise FileNotFoundError(
            "No processed FRED cache found. Run scripts/daily_run.py first."
        )
    return cached[-1]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)

    path = _latest_fred_cache()
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)
    print(f"Using cache: {path}")
    run_backtest(df, start=args.start, output_path=args.output)


if __name__ == "__main__":
    main()
