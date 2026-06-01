"""Orchestrates FOMC scoring: load PDFs -> keyword + LLM score -> cache -> blend.

Caches per-document scores in data/cache/fomc_scores.json keyed by filename, so
the (paid) LLM only runs on documents it hasn't seen. The latest statement's
blended score feeds the pipeline's `fomc_nlp` factor.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from src.utils.config import DATA
from src.nlp.fomc_loader import load, FomcDoc
from src.nlp.keyword_scorer import score_text
from src.nlp.llm_scorer import score_document

CACHE = DATA / "cache" / "fomc_scores.json"


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


def _blend(keyword: float, llm: float | None) -> float:
    """Combine scores. Falls back to keyword alone if no LLM score available."""
    if llm is None:
        return round(keyword, 3)
    return round(LLM_WEIGHT * llm + (1 - LLM_WEIGHT) * keyword, 3)


def analyze(use_llm: bool = True, refresh: bool = False) -> list[dict]:
    """Score every FOMC doc (cached). Returns list of dicts, oldest -> newest."""
    cache = _load_cache()
    docs: list[FomcDoc] = load(extract=True)
    out = []
    for d in docs:
        key = d.path.name
        if not refresh and key in cache:
            rec = cache[key]
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
                "file": key,
                "kind": d.kind,
                "date": d.doc_date.isoformat(),
                "keyword_score": kw,
                "llm_score": llm_score,
                "rationale": (llm_res or {}).get("rationale", ""),
                "key_phrases": (llm_res or {}).get("key_phrases", []),
                "provider": (llm_res or {}).get("provider", "keyword-only"),
            }
            cache[key] = rec

        # blended is ALWAYS recomputed from raw scores, so tuning LLM_WEIGHT
        # never requires re-calling the (paid) LLM.
        rec["blended"] = _blend(rec["keyword_score"], rec["llm_score"])
        out.append(rec)

    _save_cache(cache)
    out.sort(key=lambda r: (r["date"], r["kind"]))
    return out


def latest_statement_score(use_llm: bool = True) -> dict | None:
    """The newest STATEMENT's record — what feeds `fomc_nlp`."""
    recs = [r for r in analyze(use_llm=use_llm) if r["kind"] == "statement"]
    return recs[-1] if recs else None


if __name__ == "__main__":
    for r in analyze(use_llm=True):
        print(f"{r['date']} {r['kind']:9s} kw={r['keyword_score']:+.2f} "
              f"llm={r['llm_score']} blend={r['blended']:+.2f}  {r['file']}")
        if r["rationale"]:
            print(f"    -> {r['rationale'][:140]}")
