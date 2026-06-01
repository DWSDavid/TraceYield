"""Orchestrates FOMC scoring: load Fed docs -> keyword + LLM -> cache -> blend.

Caches per-document scores in data/cache/fomc_scores.json, so the (paid) LLM
only runs on documents it hasn't seen. The latest statement's blended score
feeds the pipeline's `fomc_nlp` factor.
"""

from __future__ import annotations

import argparse
import json

from src.utils.config import DATA
from src.nlp.fomc_loader import FomcDoc, hydrate, load
from src.nlp.keyword_scorer import score_text
from src.nlp.llm_scorer import score_document

CACHE = DATA / "cache" / "fomc_scores.json"
_KIND_ORDER = {"statement": 0, "minutes": 1}


def _load_cache() -> dict:
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {}


def _save_cache(c: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(c, indent=2, ensure_ascii=False), encoding="utf-8")


# LLM is the trusted read (understands context + gives rationale); the keyword
# scorer is a noisy sanity-check, so it gets a small weight and can't flip signs.
LLM_WEIGHT = 0.8


def _cache_key(doc: FomcDoc) -> str:
    """Stable score-cache key; HTML statement/minutes share filenames by date."""
    if doc.source == "local_pdf":
        return doc.path.name
    return f"{doc.source}:{doc.kind}:{doc.doc_date.isoformat()}"


def _blend(keyword: float, llm: float | None) -> float:
    """Combine scores. Falls back to keyword alone if no LLM score available."""
    if llm is None:
        return round(keyword, 3)
    return round(LLM_WEIGHT * llm + (1 - LLM_WEIGHT) * keyword, 3)


def analyze(
    use_llm: bool = True,
    refresh: bool = False,
    docs: list[FomcDoc] | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Score every FOMC doc (cached). Returns list of dicts, oldest -> newest."""
    cache = _load_cache()
    docs = docs if docs is not None else load(extract=True)
    docs = sorted(docs, key=lambda d: (d.doc_date, _KIND_ORDER.get(d.kind, 99)))
    if limit is not None:
        docs = docs[-limit:] if limit > 0 else []
    out = []
    for d in docs:
        key = _cache_key(d)
        cached = cache.get(key)
        can_reuse = cached and (not use_llm or cached.get("llm_score") is not None)
        if not refresh and can_reuse:
            rec = cache[key]
            rec["cache_key"] = key
            rec["file"] = d.path.name
            rec["source"] = d.source
        else:
            kw = score_text(d.text)["score"]
            llm_res, llm_score = None, None
            if use_llm:
                try:
                    llm_res = score_document(d.text)
                    llm_score = float(llm_res.get("hawkish_score", 0.0))
                except Exception as e:  # noqa: BLE001
                    print(f"[fomc] LLM scoring failed for {key}: {e}")
            rec = {
                "cache_key": key,
                "file": d.path.name,
                "kind": d.kind,
                "date": d.doc_date.isoformat(),
                "source": d.source,
                "keyword_score": kw,
                "llm_score": llm_score,
                "rationale": (llm_res or {}).get("rationale", ""),
                "key_phrases": (llm_res or {}).get("key_phrases", []),
                "key_quotes": (llm_res or {}).get("key_quotes", []),
                "provider": (llm_res or {}).get("provider", "keyword-only"),
            }
            cache[key] = rec

        # blended is ALWAYS recomputed from raw scores, so tuning LLM_WEIGHT
        # never requires re-calling the (paid) LLM.
        rec["blended"] = _blend(rec["keyword_score"], rec["llm_score"])
        out.append(rec)

    _save_cache(cache)
    out.sort(key=lambda r: (r["date"], _KIND_ORDER.get(r["kind"], 99)))
    return out


def latest_statement_score(use_llm: bool = True) -> dict | None:
    """The newest STATEMENT's record."""
    docs = load(kind="statement", extract=False)
    if not docs:
        return None
    return analyze(use_llm=use_llm, docs=[hydrate(docs[-1])])[0]


def latest_minutes_score(use_llm: bool = True) -> dict | None:
    """The newest MINUTES record."""
    docs = load(kind="minutes", extract=False)
    if not docs:
        return None
    return analyze(use_llm=use_llm, docs=[hydrate(docs[-1])])[0]


# Statement is the official current stance; minutes adds the detailed debate
# behind it. Statement leads, minutes informs.
STATEMENT_WEIGHT = 0.6


def combined_fomc_score(use_llm: bool = True) -> dict | None:
    """Blend latest statement + latest minutes into the fomc_nlp factor.

    Returns a record carrying the blended hawkish score plus BOTH source docs
    (with their quotes) so the report can show the evidence trail.
    """
    docs = load(extract=False)
    stmt_doc = next((d for d in reversed(docs) if d.kind == "statement"), None)
    mins_doc = next((d for d in reversed(docs) if d.kind == "minutes"), None)
    latest_docs = [hydrate(d) for d in (stmt_doc, mins_doc) if d is not None]
    recs = analyze(use_llm=use_llm, docs=latest_docs) if latest_docs else []
    stmt = next((r for r in recs if r["kind"] == "statement"), None)
    mins = next((r for r in recs if r["kind"] == "minutes"), None)
    if not stmt and not mins:
        return None
    if stmt and mins:
        blended = round(
            STATEMENT_WEIGHT * stmt["blended"]
            + (1 - STATEMENT_WEIGHT) * mins["blended"],
            3,
        )
    else:
        src = stmt or mins
        blended = src["blended"]
    return {"blended": blended, "statement": stmt, "minutes": mins}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of most recent docs to score. Use 0 to score none.",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Use keyword-only scoring; useful for smoke tests.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Ignore cached scores for selected docs.",
    )
    args = parser.parse_args(argv)

    for r in analyze(use_llm=not args.no_llm, refresh=args.refresh, limit=args.limit):
        print(
            f"{r['date']} {r['kind']:9s} kw={r['keyword_score']:+.2f} "
            f"llm={r['llm_score']} blend={r['blended']:+.2f}  {r['file']}"
        )
        if r["rationale"]:
            print(f"    -> {r['rationale'][:140]}")


if __name__ == "__main__":
    main()
