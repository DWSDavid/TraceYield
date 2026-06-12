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
from src.signals.factors import compute_all, political_risk_proxy
from src.models.predictor import predict
from src.nlp.fomc_analyzer import combined_fomc_score
from src.report import render


def main(use_llm: bool = True) -> None:
    print("[1/5] Ingesting FRED data...")
    df = fetch_all()
    current_10y = float(df["DGS10"].dropna().iloc[-1])
    print(f"      Current 10Y = {current_10y:.2f}%")

    print("[2/5] Scoring latest FOMC statement + minutes...")
    fomc = combined_fomc_score(use_llm=use_llm)
    hawkish = float(fomc["blended"]) if fomc else 0.0
    if fomc:
        s, m = fomc.get("statement"), fomc.get("minutes")
        if s:
            print(f"      statement {s['file']}: blended {s['blended']:+.2f}")
        if m:
            print(f"      minutes   {m['file']}: blended {m['blended']:+.2f}")
        print(f"      -> combined fomc_nlp {hawkish:+.2f}")
    else:
        print("      no FOMC docs found; fomc_nlp=0")

    print("[3/5] Computing factor scores...")
    factors = compute_all(df, hawkish=hawkish, political=political_risk_proxy(df))
    for k, v in factors.items():
        print(f"      {k:14s} {v:+.3f}")

    print("[4/5] Predicting...")
    preds = predict(factors, current_10y)

    print("[5/5] Rendering reports (markdown + HTML)...")
    md = render.to_markdown(preds, current_10y)
    md_path = render.save(md)
    html = render.to_html(preds, current_10y, factors, fomc=fomc)
    html_path = render.save_html(html)
    print("\n" + md)
    print(f"\nSaved -> {md_path}\n        {html_path}")


if __name__ == "__main__":
    main()
