"""Load FOMC PDFs from FOMC/ (Statement/ and Minutes/), extract text, sort by date.

Filename conventions in this repo:
  Statement/  ->  "Jan 2026.pdf", "March 2026.pdf", "April 2026.pdf"
  Minutes/    ->  "MJan 2026.pdf", "MMar 2026.pdf", "MApr 2026.pdf"  (leading M)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from src.utils.config import DATA, ROOT

FOMC_DIR = ROOT / "FOMC"
RAW_FOMC_DIR = DATA / "raw" / "fomc"

_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


@dataclass
class FomcDoc:
    kind: str  # "statement" | "minutes"
    doc_date: date  # parsed from filename (day defaults to 1)
    path: Path
    text: str = ""
    source: str = "local_pdf"


def _parse_date(stem: str, kind: str) -> date | None:
    """Parse 'March 2026' (statement) / 'MJan 2026' (minutes) -> date.

    Minutes filenames carry exactly ONE leading 'M' prefix; statements don't.
    We key off the folder (kind), never a filename heuristic — otherwise 'March'
    looks like an M-prefixed month and gets mangled.
    """
    s = stem.strip()
    if kind == "minutes" and s[:1] in "Mm":
        s = s[1:]
    m = re.search(r"([A-Za-z]+)\s+(\d{4})", s)
    if not m:
        return None
    month = _MONTHS.get(m.group(1).lower())
    if not month:
        return None
    return date(int(m.group(2)), month, 1)


def _extract_text(path: Path) -> str:
    import pdfplumber  # lazy import

    chunks = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            chunks.append(page.extract_text() or "")
    return "\n".join(chunks).strip()


def _load_pdf_docs(kind: str, extract: bool) -> list[FomcDoc]:
    docs: list[FomcDoc] = []
    folders = {"statement": "Statement", "minutes": "Minutes"}
    sub = FOMC_DIR / folders[kind]
    if not sub.exists():
        return docs
    for pdf in sub.glob("*.pdf"):
        d = _parse_date(pdf.stem, kind)
        if d is None:
            print(f"[fomc] skip unparseable filename: {pdf.name}")
            continue
        doc = FomcDoc(kind=kind, doc_date=d, path=pdf, source="local_pdf")
        if extract:
            doc.text = _extract_text(pdf)
        docs.append(doc)
    return docs


def _load_html_docs(kind: str, extract: bool) -> list[FomcDoc]:
    docs: list[FomcDoc] = []
    sub = RAW_FOMC_DIR / kind
    if not sub.exists():
        return docs
    for txt in sub.glob("*.txt"):
        try:
            d = date.fromisoformat(txt.stem)
        except ValueError:
            print(f"[fomc] skip unparseable html text file: {txt.name}")
            continue
        doc = FomcDoc(
            kind=kind,
            doc_date=d,
            path=txt,
            source="federalreserve.gov",
        )
        if extract:
            doc.text = txt.read_text(encoding="utf-8")
        docs.append(doc)
    return docs


def load(kind: str | None = None, extract: bool = True) -> list[FomcDoc]:
    """Load docs of a kind ('statement'/'minutes'/None=both), newest last.

    Reads both the legacy local PDFs under FOMC/ and the downloaded Fed HTML
    extracts under data/raw/fomc/. When an exact date+kind duplicate exists,
    the Fed HTML extract wins because it carries the real release date/source.
    """
    docs_by_key: dict[tuple[str, date], FomcDoc] = {}
    wanted = [kind] if kind else ["statement", "minutes"]
    for k in wanted:
        for doc in _load_pdf_docs(k, extract):
            docs_by_key[(doc.kind, doc.doc_date)] = doc
        for doc in _load_html_docs(k, extract):
            docs_by_key[(doc.kind, doc.doc_date)] = doc
    docs = list(docs_by_key.values())
    docs.sort(key=lambda x: x.doc_date)
    return docs


def hydrate(doc: FomcDoc) -> FomcDoc:
    """Return a copy of doc with text loaded, extracting only this one file."""
    if doc.text:
        return doc
    if doc.path.suffix.lower() == ".pdf":
        text = _extract_text(doc.path)
    else:
        text = doc.path.read_text(encoding="utf-8")
    return FomcDoc(
        kind=doc.kind,
        doc_date=doc.doc_date,
        path=doc.path,
        text=text,
        source=doc.source,
    )


def latest(kind: str = "statement") -> FomcDoc | None:
    docs = load(kind=kind)
    return docs[-1] if docs else None


if __name__ == "__main__":
    for d in load(extract=True):
        print(f"{d.kind:9s} {d.doc_date}  {len(d.text):>6} chars  {d.path.name}")
