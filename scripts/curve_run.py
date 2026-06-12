"""Run the v2 UST curve impact forecast from cached FRED data.

This Phase-A script avoids live API calls. Run `scripts/daily_run.py` first when
you want to refresh the FRED cache, then use this script to generate the v2
curve report quickly from the latest processed parquet.
"""

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

from src.backtest.walk_forward import _lagged_history, fred_release_lags
from src.models.curve_engine import forecast_curve
from src.report import render_curve
from src.report import render_html
from src.utils.config import DATA


def _latest_fred_cache() -> Path:
    cached = sorted((DATA / "processed").glob("fred_*.parquet"))
    if not cached:
        raise FileNotFoundError(
            "No processed FRED cache found. Run scripts/daily_run.py first."
        )
    return cached[-1]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--html",
        action="store_true",
        help="Render the latest saved curve trajectory JSON to self-contained HTML.",
    )
    parser.add_argument(
        "--trajectory-json",
        type=Path,
        default=None,
        help="Optional saved curve_trajectory_<asof>.json path for --html.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.html:
        trajectory_path = args.trajectory_json or render_html.latest_trajectory_path()
        dated, latest = render_html.render_file_to_html(trajectory_path)
        print(f"Rendered HTML from {trajectory_path}")
        print(f"Saved -> {dated}\n         {latest}")
        return

    path = _latest_fred_cache()
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    latest_date = pd.Timestamp(df.index.max())
    lagged = _lagged_history(df, latest_date, fred_release_lags())

    forecasts = forecast_curve(lagged)
    markdown = render_curve.to_markdown(forecasts, run_date=latest_date)
    out = render_curve.save(markdown, run_date=latest_date)
    print(markdown)
    print(f"\nSaved -> {out}")


if __name__ == "__main__":
    main()
