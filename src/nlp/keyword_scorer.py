"""Fast keyword-based hawkish/dovish scorer for daily scans.

Returns a score in [-1, +1]: positive = hawkish (tighter policy, yields up),
negative = dovish (easier policy, yields down). This is the cheap daily pass;
the LLM scorer (llm_scorer.py) does the deep read on FOMC/event days.
"""

from __future__ import annotations

import re

# Weighted lexicon for the 20%-weight keyword sanity-check (LLM carries 80% and
# is the trusted read — see fomc_analyzer.LLM_WEIGHT). Phrases are drawn from
# real 2022-2026 FOMC statements/minutes and Powell pressers. Prefer DISTINCTIVE
# multi-word phrases; keep bare single words at lower weight to limit noise.
# Matching is whole-word (\b) so short tokens like "hike"/"pause" can't fire
# inside unrelated words ("confirm", "paused-out" contexts, etc.).
HAWKISH = {
    # --- policy-stance language (tighter / stay high) ---
    "higher for longer": 1.2,
    "additional policy firming": 1.1,
    "additional firming": 1.0,
    "further tightening": 1.1,
    "sufficiently restrictive": 1.0,
    "more restrictive": 0.9,
    "restrictive": 0.7,
    "tightening": 0.9,
    "raise the target range": 1.0,
    "raise rates": 0.9,
    "rate hike": 0.9,
    "hike": 0.7,
    "no rush": 0.8,
    "not in a hurry": 0.8,
    "more confidence": 0.5,  # "need more confidence" before cutting → hawkish lean
    # --- inflation pressure language ---
    "upside risks to inflation": 1.0,
    "inflation remains elevated": 1.1,
    "inflation has been elevated": 1.0,
    "elevated inflation": 0.9,
    "inflationary pressures": 0.9,
    "price pressures": 0.6,
    "upward pressure": 0.7,
    "overheating": 0.9,
    "above target": 0.7,
    "above 2 percent": 0.7,
    "persistently": 0.6,
    "persistent": 0.6,
    "sticky": 0.7,
    "de-anchor": 0.9,
    "unanchored": 0.9,
    "highly attentive to inflation": 0.8,
    "attentive to inflation": 0.6,
    "vigilant": 0.6,
    # --- strong-economy language (good news = hawkish for bonds) ---
    "tight labor market": 0.7,
    "strong labor market": 0.7,
    "robust job gains": 0.7,
    "resilient": 0.5,
    "broad-based": 0.5,
}
DOVISH = {
    # --- policy-stance language (cut / ease) ---
    "rate cut": 1.0,
    "cut rates": 1.0,
    "rate reduction": 1.0,
    "reduce the target range": 1.0,
    "lower the target range": 1.0,
    "lower the policy rate": 0.9,
    "begin reducing": 0.8,
    "policy easing": 1.0,
    "easing": 0.9,
    "accommodative": 1.0,
    "accommodation": 0.8,
    "recalibrate": 0.8,
    "recalibration": 0.8,
    "normalize": 0.6,
    "normalization": 0.6,
    "patient": 0.5,
    "pause": 0.6,
    "step down": 0.5,
    "gradual": 0.4,
    # --- disinflation language ---
    "disinflation": 0.9,
    "disinflationary": 0.9,
    "further progress": 0.8,
    "progress toward": 0.6,
    "well-anchored": 0.6,
    "moderating": 0.7,
    "moderated": 0.6,
    "roughly balanced": 0.6,
    # --- weakening-economy language (bad news = dovish for bonds) ---
    "downside risks to growth": 1.0,
    "downside risks to employment": 1.0,
    "downside risks": 0.6,
    "cooling labor market": 0.9,
    "labor market has cooled": 0.8,
    "slowing job gains": 0.8,
    "slower job gains": 0.7,
    "softening": 0.7,
    "softened": 0.6,
    "weakening": 0.8,
    "weakened": 0.7,
    "slack": 0.7,
    "soft landing": 0.5,
}
# Genuinely neutral phrases — kept as documentation so future edits don't
# mistakenly file them as hawkish/dovish. (Not subtracted; score_text ignores them.)
NEUTRAL = {
    "data dependent",
    "data-dependent",
    "meeting by meeting",
    "meeting-by-meeting",
    "carefully",
    "incoming data",
    "totality of",
    "well positioned",
}


# Confidence damping: short docs with only a hit or two should NOT claim a
# saturated +/-1 read. We scale the raw ratio by min(1, total_hits/FULL) so a
# 1-word statement is pulled toward neutral and only richly-worded docs reach
# full conviction. Calibrated to FOMC corpus: statements carry ~4 weight median,
# minutes ~36, so FULL=6 leaves minutes at full strength and tempers sparse
# statements (which otherwise flip the blended score at their 20% weight).
CONFIDENCE_FULL_WEIGHT = 6.0


def _count(term: str, text: str) -> int:
    """Whole-word occurrences of `term` in already-lowercased `text`."""
    return len(re.findall(rf"\b{re.escape(term)}\b", text))


def score_text(text: str) -> dict:
    """Score a document. Returns {score, hawkish_weight, dovish_weight}."""
    t = text.lower()
    haw = sum(w * _count(k, t) for k, w in HAWKISH.items())
    dov = sum(w * _count(k, t) for k, w in DOVISH.items())
    total = haw + dov
    raw = 0.0 if total == 0 else (haw - dov) / total  # directional ratio [-1, +1]
    confidence = min(1.0, total / CONFIDENCE_FULL_WEIGHT)  # sparse docs -> toward 0
    score = raw * confidence
    return {
        "score": round(score, 3),
        "hawkish_weight": round(haw, 2),
        "dovish_weight": round(dov, 2),
    }


if __name__ == "__main__":
    sample = (
        "The Committee remains highly attentive to inflation risks. "
        "Inflation remains elevated and the stance is restrictive."
    )
    print(score_text(sample))
