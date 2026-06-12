"""Run v3 Part A HAC significance and Part B FADNS scorecards."""

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
from src.backtest.hac import DEFAULT_OUTPUT as HAC_OUTPUT
from src.backtest.hac import run_phase1b_hac_significance
from src.models.fadns import DEFAULT_OUTPUT as FADNS_OUTPUT
from src.models.fadns import run_fadns_scorecard
from src.utils.config import DATA

PHASE1_OUTPUT = DATA / "backtest" / "phase1_single_factor_ic.csv"


def _latest_fred_cache() -> Path:
    cached = sorted((DATA / "processed").glob("fred_*.parquet"))
    if not cached:
        raise FileNotFoundError(
            "No processed FRED cache found. Run scripts/daily_run.py first."
        )
    return cached[-1]


def _load_phase0(df: pd.DataFrame, start: str) -> pd.DataFrame:
    if PHASE0_OUTPUT.exists():
        return pd.read_csv(PHASE0_OUTPUT)
    return run_phase0_benchmarks(df, start=start, output_path=PHASE0_OUTPUT)


def _load_phase1() -> pd.DataFrame | None:
    if PHASE1_OUTPUT.exists():
        return pd.read_csv(PHASE1_OUTPUT)
    return None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--fred-cache", default=None)
    parser.add_argument("--hac-output", default=str(HAC_OUTPUT))
    parser.add_argument("--fadns-output", default=str(FADNS_OUTPUT))
    args = parser.parse_args(argv)

    path = Path(args.fred_cache) if args.fred_cache else _latest_fred_cache()
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()

    print(f"Using cache: {path}")
    phase0 = _load_phase0(df, args.start)
    phase1 = _load_phase1()
    hac = run_phase1b_hac_significance(
        df,
        start=args.start,
        phase0_scorecard=phase0,
        output_path=args.hac_output,
    )
    fadns = run_fadns_scorecard(
        df,
        start=args.start,
        phase0_scorecard=phase0,
        phase1_scorecard=phase1,
        output_path=args.fadns_output,
    )

    kept = sorted(
        hac.loc[
            hac["row_type"].eq("factor") & hac["decision_tag"].eq("keep"),
            "factor",
        ].unique()
    )
    fadns_pass = fadns[
        fadns["target"].isin(["2s10s", "5s30s"]) & fadns["validated_pass"]
    ]

    print("\nHonest Part A/B verdict")
    print("-" * 72)
    print(f"HAC keep set: {kept if kept else 'none'}")
    if fadns_pass.empty:
        print("FADNS: no curve target both beats the bar and clears NW |t| >= 2.")
    else:
        print(
            "FADNS validated rows: "
            + ", ".join(
                f"{row.horizon}/{row.target}" for row in fadns_pass.itertuples()
            )
        )
    print("\nStopped after Part A/B for validation. No final fusion was built.")


if __name__ == "__main__":
    main()
