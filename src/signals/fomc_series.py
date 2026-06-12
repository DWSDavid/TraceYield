"""Build and read point-in-time historical FOMC tone scores."""

from __future__ import annotations

import argparse
import re
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd

from src.ingestion.fomc_scraper import (
    calendar_urls,
    classify_url,
    fetch_url,
)
from src.nlp.fomc_analyzer import analyze
from src.nlp.fomc_loader import FomcDoc, hydrate, load
from src.utils.config import DATA, load_yaml

SERIES_PATH = DATA / "processed" / "fomc_scores.parquet"
_RELEASE_RE = re.compile(r"Released\s+([A-Za-z]+ \d{1,2}, \d{4})", re.I)
_HREF_RE = re.compile(r"<a\b[^>]+href=[\"']([^\"']+)[\"']", re.I)
_KIND_ORDER = {"statement": 0, "minutes": 1}


def backfill_model() -> str:
    """Cheap model configured for historical backfills."""
    return load_yaml("model")["llm"].get("backfill_model", "gpt-4o-mini")


def _parse_release_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%B %d, %Y").date()
    except ValueError:
        return None


def _cache_key_for_link(kind: str, doc_date: date) -> str:
    return f"federalreserve.gov:{kind}:{doc_date.isoformat()}"


def _release_dates_from_calendar_html(html: str, base_url: str) -> dict[str, date]:
    mapping: dict[str, date] = {}
    for match in _HREF_RE.finditer(html):
        url = urljoin(base_url, match.group(1))
        link = classify_url(url)
        if not link:
            continue
        key = _cache_key_for_link(link.kind, link.doc_date)
        if link.kind == "statement":
            mapping[key] = link.doc_date
            continue

        window = html[max(0, match.start() - 300) : match.end() + 500]
        release_match = _RELEASE_RE.search(window)
        release_date = (
            _parse_release_date(release_match.group(1)) if release_match else None
        )
        mapping[key] = release_date or link.doc_date + timedelta(days=21)
    return mapping


def release_date_map(start_year: int = 2010) -> dict[str, date]:
    """Map official Fed document cache keys to public release dates."""
    mapping: dict[str, date] = {}
    for url in calendar_urls(start_year=start_year):
        html = fetch_url(url)
        mapping.update(_release_dates_from_calendar_html(html, url))
    return mapping


def _official_html_docs() -> list[FomcDoc]:
    docs = [doc for doc in load(extract=False) if doc.source == "federalreserve.gov"]
    return [hydrate(doc) for doc in docs]


def estimate_backfill_cost(docs: list[FomcDoc], model: str) -> dict[str, float]:
    """Approximate token and USD cost for the historical scoring run."""
    cfg = load_yaml("model")["llm"]
    max_chars = int(cfg.get("max_chars", 40000))
    input_tokens = sum((min(len(doc.text), max_chars) + 2500) / 4 for doc in docs)
    output_tokens = len(docs) * 350
    pricing = cfg.get("pricing_per_1m_tokens", {}).get(model, {})
    input_usd = float(pricing.get("input", 0.0)) * input_tokens / 1_000_000
    output_usd = float(pricing.get("output", 0.0)) * output_tokens / 1_000_000
    return {
        "docs": float(len(docs)),
        "input_tokens": float(round(input_tokens)),
        "output_tokens": float(round(output_tokens)),
        "estimated_usd": round(input_usd + output_usd, 4),
    }


def build(use_llm: bool = True) -> pd.DataFrame:
    """Score historical FOMC docs and save the point-in-time score series."""
    docs = _official_html_docs()
    model = backfill_model()
    estimate = estimate_backfill_cost(docs, model)
    print(
        "[fomc_series] backfill estimate "
        f"model={model} docs={int(estimate['docs'])} "
        f"input_tokens~{int(estimate['input_tokens']):,} "
        f"output_tokens~{int(estimate['output_tokens']):,} "
        f"cost~${estimate['estimated_usd']:.4f}"
    )

    release_dates = release_date_map()
    recs = analyze(use_llm=use_llm, docs=docs, scoring_model=model)
    rows = []
    for rec in recs:
        release_date = release_dates.get(rec["cache_key"])
        if release_date is None:
            release_date = date.fromisoformat(rec["date"])
        rows.append(
            {
                "release_date": pd.Timestamp(release_date),
                "kind_order": _KIND_ORDER.get(rec["kind"], 99),
                "blended": float(rec["blended"]),
                "llm": (
                    float(rec["llm_score"])
                    if rec.get("llm_score") is not None
                    else float("nan")
                ),
                "keyword": float(rec["keyword_score"]),
                "kind": rec["kind"],
            }
        )

    df = pd.DataFrame(rows).sort_values(["release_date", "kind_order"])
    if df.empty:
        out = pd.DataFrame(columns=["blended", "llm", "keyword", "kind"])
        out.index.name = "release_date"
    else:
        out = df.set_index("release_date")[["blended", "llm", "keyword", "kind"]]
        out.index.name = "release_date"

    SERIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(SERIES_PATH)
    _load_series.cache_clear()
    return out


@lru_cache(maxsize=1)
def _load_series(path_key: str) -> pd.DataFrame:
    path = Path(path_key)
    if not path.exists():
        return build(use_llm=False)
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def fomc_factor_asof(d: date | str | pd.Timestamp) -> float:
    """Return the latest FOMC score known on or before d, with no look-ahead."""
    asof = pd.Timestamp(d).normalize()
    df = _load_series(str(SERIES_PATH))
    known = df[df.index <= asof]
    if known.empty:
        return 0.0
    return float(known.iloc[-1]["blended"])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keyword-only",
        action="store_true",
        help="Build using keyword scores only; avoids LLM calls.",
    )
    args = parser.parse_args(argv)
    df = build(use_llm=not args.keyword_only)
    start = df.index.min().date() if not df.empty else "n/a"
    end = df.index.max().date() if not df.empty else "n/a"
    print(f"[fomc_series] wrote {len(df)} rows to {SERIES_PATH} ({start} -> {end})")


if __name__ == "__main__":
    main()
