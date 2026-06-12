"""Run TraceYield v3 Phase 0 benchmarks and Phase 1 single-factor IC tests."""

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

from src.backtest.benchmarks import DEFAULT_OUTPUT as PHASE0_OUTPUT
from src.backtest.benchmarks import run_phase0_benchmarks
from src.backtest.single_factor import DEFAULT_OUTPUT as PHASE1_OUTPUT
from src.backtest.single_factor import run_phase1_single_factor_ic
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
    parser.add_argument("--fred-cache", default=None)
    parser.add_argument("--phase0-output", default=str(PHASE0_OUTPUT))
    parser.add_argument("--phase1-output", default=str(PHASE1_OUTPUT))
    args = parser.parse_args(argv)

    path = Path(args.fred_cache) if args.fred_cache else _latest_fred_cache()
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)

    print(f"Using cache: {path}")
    phase0 = run_phase0_benchmarks(
        df,
        start=args.start,
        output_path=args.phase0_output,
    )
    run_phase1_single_factor_ic(
        df,
        start=args.start,
        phase0_scorecard=phase0,
        output_path=args.phase1_output,
    )
    print("\nStopped after Phase 1 for validation. No fusion was built.")


if __name__ == "__main__":
    main()
