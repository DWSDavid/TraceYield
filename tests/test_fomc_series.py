import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.nlp.fomc_loader import FomcDoc
from src.signals import fomc_series


def test_fomc_factor_asof_uses_only_scores_on_or_before_date(tmp_path, monkeypatch):
    series_path = tmp_path / "fomc_scores.parquet"
    df = pd.DataFrame(
        [
            {"blended": 0.1, "llm": 0.2, "keyword": -0.1, "kind": "statement"},
            {"blended": 0.9, "llm": 1.0, "keyword": 0.5, "kind": "minutes"},
        ],
        index=pd.to_datetime(["2026-01-10", "2026-01-20"]),
    )
    df.index.name = "release_date"
    df.to_parquet(series_path)
    monkeypatch.setattr(fomc_series, "SERIES_PATH", series_path)

    assert fomc_series.fomc_factor_asof(date(2026, 1, 9)) == 0.0
    assert fomc_series.fomc_factor_asof(date(2026, 1, 15)) == 0.1
    assert fomc_series.fomc_factor_asof(date(2026, 1, 20)) == 0.9


def test_build_uses_release_dates_and_backfill_model(tmp_path, monkeypatch):
    series_path = tmp_path / "fomc_scores.parquet"
    statement = FomcDoc(
        "statement",
        date(2026, 1, 28),
        Path("statement/2026-01-28.txt"),
        "statement text",
        "federalreserve.gov",
    )
    minutes = FomcDoc(
        "minutes",
        date(2026, 1, 28),
        Path("minutes/2026-01-28.txt"),
        "minutes text",
        "federalreserve.gov",
    )
    seen = {}

    def fake_analyze(use_llm=True, docs=None, scoring_model=None):
        seen["use_llm"] = use_llm
        seen["scoring_model"] = scoring_model
        return [
            {
                "cache_key": "federalreserve.gov:statement:2026-01-28",
                "kind": "statement",
                "date": "2026-01-28",
                "blended": 0.2,
                "llm_score": 0.3,
                "keyword_score": -0.1,
            },
            {
                "cache_key": "federalreserve.gov:minutes:2026-01-28",
                "kind": "minutes",
                "date": "2026-01-28",
                "blended": -0.4,
                "llm_score": -0.5,
                "keyword_score": 0.0,
            },
        ]

    monkeypatch.setattr(fomc_series, "SERIES_PATH", series_path)
    monkeypatch.setattr(fomc_series, "load", lambda extract=True: [statement, minutes])
    monkeypatch.setattr(fomc_series, "hydrate", lambda doc: doc)
    monkeypatch.setattr(fomc_series, "analyze", fake_analyze)
    monkeypatch.setattr(
        fomc_series,
        "release_date_map",
        lambda: {
            "federalreserve.gov:statement:2026-01-28": date(2026, 1, 28),
            "federalreserve.gov:minutes:2026-01-28": date(2026, 2, 18),
        },
    )
    monkeypatch.setattr(fomc_series, "backfill_model", lambda: "gpt-4o-mini")

    df = fomc_series.build(use_llm=True)

    assert seen == {"use_llm": True, "scoring_model": "gpt-4o-mini"}
    assert df.index.strftime("%Y-%m-%d").tolist() == ["2026-01-28", "2026-02-18"]
    assert list(df.columns) == ["blended", "llm", "keyword", "kind"]
    assert pd.read_parquet(series_path).equals(df)
