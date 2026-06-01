"""Daily entrypoint — the thing Windows Task Scheduler runs once a day.

Pipeline: ingest FRED -> compute factors -> (NLP tone) -> predict -> report.
Run manually any time:  python scripts/daily_run.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Windows consoles default to GBK/cp1252 and choke on the report's arrows.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# Make `src` importable when run as a plain script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingestion.fred_client import fetch_all
from src.signals.factors import compute_all
from src.models.predictor import predict
from src.report import render


def main() -> None:
    print("[1/4] Ingesting FRED data...")
    df = fetch_all()

    current_10y = float(df["DGS10"].dropna().iloc[-1])
    print(f"      Current 10Y = {current_10y:.2f}%")

    print("[2/4] Computing factor scores...")
    # hawkish/political default to 0 until NLP + news pipelines are wired in.
    factors = compute_all(df, hawkish=0.0, political=0.0)
    for k, v in factors.items():
        print(f"      {k:14s} {v:+.3f}")

    print("[3/4] Predicting...")
    preds = predict(factors, current_10y)

    print("[4/4] Rendering report...")
    md = render.to_markdown(preds, current_10y)
    path = render.save(md)
    print("\n" + md)
    print(f"\nSaved -> {path}")


if __name__ == "__main__":
    main()
