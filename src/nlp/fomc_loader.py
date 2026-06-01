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

from src.utils.config import ROOT

FOMC_DIR = ROOT / "FOMC"

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


@dataclass
class FomcDoc:
    kind: str          # "statement" | "minutes"
    doc_date: date     # parsed from filename (day defaults to 1)
    path: Path
    text: str = ""


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


def load(kind: str | None = None, extract: bool = True) -> list[FomcDoc]:
    """Load docs of a kind ('statement'/'minutes'/None=both), newest last."""
    docs: list[FomcDoc] = []
    folders = {"statement": "Statement", "minutes": "Minutes"}
    wanted = [kind] if kind else ["statement", "minutes"]
    for k in wanted:
        sub = FOMC_DIR / folders[k]
        if not sub.exists():
            continue
        for pdf in sub.glob("*.pdf"):
            d = _parse_date(pdf.stem, k)
            if d is None:
                print(f"[fomc] skip unparseable filename: {pdf.name}")
                continue
            doc = FomcDoc(kind=k, doc_date=d, path=pdf)
            if extract:
                doc.text = _extract_text(pdf)
            docs.append(doc)
    docs.sort(key=lambda x: x.doc_date)
    return docs


def latest(kind: str = "statement") -> FomcDoc | None:
    docs = load(kind=kind)
    return docs[-1] if docs else None


if __name__ == "__main__":
    for d in load(extract=True):
        print(f"{d.kind:9s} {d.doc_date}  {len(d.text):>6} chars  {d.path.name}")
