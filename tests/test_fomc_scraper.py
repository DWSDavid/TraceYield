import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingestion import fomc_scraper
from src.nlp import fomc_analyzer
from src.nlp import fomc_loader

STATEMENT_HTML = """
<html>
  <body>
    <nav>Navigation should not be included.</nav>
    <main id="content">
      <p>January 28, 2026</p>
      <h3>Federal Reserve issues FOMC statement</h3>
      <p>For release at 2:00 p.m. EST</p>
      <p>Available indicators suggest that economic activity has been expanding
      at a solid pace.</p>
      <p>The Committee decided to maintain the target range for the federal
      funds rate at 3-1/2 to 3-3/4 percent.</p>
      <p>For media inquiries, please email media@example.com.</p>
    </main>
    <footer>Footer should not be included.</footer>
  </body>
</html>
"""


CALENDAR_HTML = """
<html>
  <body>
    <h4>January</h4>
    <p>Statement:
      <a href="/newsevents/pressreleases/monetary20260128a.htm">HTML</a>
    </p>
    <p>Minutes:
      <a href="/monetarypolicy/fomcminutes20260128.htm">HTML</a>
    </p>
    <p>Implementation Note
      <a href="/newsevents/pressreleases/monetary20260128a1.htm">HTML</a>
    </p>
  </body>
</html>
"""


FED_ARTICLE_HTML = """
<html>
  <body>
    <div id="content" class="container container__main" role="main">
      <ol class="breadcrumb"><li>Home</li></ol>
      <div id="article">
        <div class="heading">
          <p class="article__time">January 28, 2026</p>
          <h3 class="title">Federal Reserve issues FOMC statement</h3>
          <p class="releaseTime">For release at 2:00 p.m. EST</p>
        </div>
        <div class="col-xs-12 col-sm-8 col-md-8">
          <p>Available indicators suggest that economic activity has been
          expanding at a solid pace.</p>
        </div>
      </div>
    </div>
  </body>
</html>
"""


def test_extract_release_text_keeps_policy_body_only():
    text = fomc_scraper.extract_release_text(STATEMENT_HTML)

    assert "Available indicators suggest" in text
    assert "maintain the target range" in text
    assert "Navigation should not be included" not in text
    assert "Footer should not be included" not in text
    assert "For media inquiries" not in text


def test_extract_release_text_prefers_fed_article_container():
    text = fomc_scraper.extract_release_text(FED_ARTICLE_HTML)

    assert "Available indicators suggest" in text
    assert "Home" not in text


def test_discover_doc_links_classifies_statement_and_minutes():
    links = fomc_scraper.discover_doc_links_from_html(
        CALENDAR_HTML,
        base_url="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
    )

    assert [(link.kind, link.doc_date.isoformat()) for link in links] == [
        ("statement", "2026-01-28"),
        ("minutes", "2026-01-28"),
    ]
    assert links[0].url == (
        "https://www.federalreserve.gov/newsevents/pressreleases/"
        "monetary20260128a.htm"
    )


def test_loader_reads_downloaded_html_text():
    original_raw = fomc_loader.RAW_FOMC_DIR
    original_pdf = fomc_loader.FOMC_DIR
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        raw = root / "raw" / "fomc"
        txt = raw / "statement" / "2026-01-28.txt"
        txt.parent.mkdir(parents=True)
        txt.write_text("Policy text from Fed HTML", encoding="utf-8")
        fomc_loader.RAW_FOMC_DIR = raw
        fomc_loader.FOMC_DIR = root / "missing-pdfs"
        try:
            docs = fomc_loader.load(kind="statement", extract=True)
        finally:
            fomc_loader.RAW_FOMC_DIR = original_raw
            fomc_loader.FOMC_DIR = original_pdf

    assert len(docs) == 1
    assert docs[0].doc_date.isoformat() == "2026-01-28"
    assert docs[0].text == "Policy text from Fed HTML"
    assert docs[0].source == "federalreserve.gov"


def test_analyzer_cache_key_keeps_same_date_html_docs_distinct():
    statement = fomc_loader.FomcDoc(
        kind="statement",
        doc_date=date(2026, 1, 28),
        path=Path("statement/2026-01-28.txt"),
        source="federalreserve.gov",
    )
    minutes = fomc_loader.FomcDoc(
        kind="minutes",
        doc_date=date(2026, 1, 28),
        path=Path("minutes/2026-01-28.txt"),
        source="federalreserve.gov",
    )

    assert fomc_analyzer._cache_key(statement) != fomc_analyzer._cache_key(minutes)
    assert "statement" in fomc_analyzer._cache_key(statement)
    assert "minutes" in fomc_analyzer._cache_key(minutes)


def test_combined_fomc_score_only_analyzes_latest_statement_and_minutes():
    original_load = fomc_analyzer.load
    original_cache = fomc_analyzer.CACHE
    original_score_text = fomc_analyzer.score_text
    seen_texts = []

    docs = [
        fomc_loader.FomcDoc("statement", date(2026, 1, 28), Path("s1.txt"), "old s"),
        fomc_loader.FomcDoc("minutes", date(2026, 1, 28), Path("m1.txt"), "old m"),
        fomc_loader.FomcDoc("statement", date(2026, 4, 29), Path("s2.txt"), "new s"),
        fomc_loader.FomcDoc("minutes", date(2026, 4, 29), Path("m2.txt"), "new m"),
    ]

    def fake_load(extract=True, kind=None):
        selected = docs if kind is None else [doc for doc in docs if doc.kind == kind]
        return selected

    def fake_score_text(text):
        seen_texts.append(text)
        return {"score": 0.25}

    with tempfile.TemporaryDirectory() as tmp:
        fomc_analyzer.load = fake_load
        fomc_analyzer.CACHE = Path(tmp) / "fomc_scores.json"
        fomc_analyzer.score_text = fake_score_text
        try:
            result = fomc_analyzer.combined_fomc_score(use_llm=False)
        finally:
            fomc_analyzer.load = original_load
            fomc_analyzer.CACHE = original_cache
            fomc_analyzer.score_text = original_score_text

    assert result["statement"]["file"] == "s2.txt"
    assert result["minutes"]["file"] == "m2.txt"
    assert seen_texts == ["new s", "new m"]


def test_analyze_upgrades_keyword_only_cache_when_llm_requested():
    original_cache = fomc_analyzer.CACHE
    original_score_document = fomc_analyzer.score_document
    key = "federalreserve.gov:statement:2026-01-28"
    doc = fomc_loader.FomcDoc(
        "statement",
        date(2026, 1, 28),
        Path("statement/2026-01-28.txt"),
        "policy text",
        "federalreserve.gov",
    )
    calls = []

    def fake_score_document(text):
        calls.append(text)
        return {
            "hawkish_score": 0.8,
            "rationale": "hawkish",
            "key_phrases": [],
            "key_quotes": [],
            "provider": "test",
        }

    with tempfile.TemporaryDirectory() as tmp:
        cache_path = Path(tmp) / "fomc_scores.json"
        cache_path.write_text(
            (
                '{"%s": {"file": "2026-01-28.txt", "kind": "statement", '
                '"date": "2026-01-28", "keyword_score": 0.2, '
                '"llm_score": null}}'
            )
            % key,
            encoding="utf-8",
        )
        fomc_analyzer.CACHE = cache_path
        fomc_analyzer.score_document = fake_score_document
        try:
            rec = fomc_analyzer.analyze(use_llm=True, docs=[doc])[0]
        finally:
            fomc_analyzer.CACHE = original_cache
            fomc_analyzer.score_document = original_score_document

    assert calls == ["policy text"]
    assert rec["llm_score"] == 0.8
    assert rec["file"] == "2026-01-28.txt"
    assert rec["cache_key"] == key
