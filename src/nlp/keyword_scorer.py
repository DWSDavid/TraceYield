"""Fast keyword-based hawkish/dovish scorer for daily scans.

Returns a score in [-1, +1]: positive = hawkish (tighter policy, yields up),
negative = dovish (easier policy, yields down). This is the cheap daily pass;
the LLM scorer (llm_scorer.py) does the deep read on FOMC/event days.
"""
from __future__ import annotations

import re

# Weighted lexicon. Tune these against historical statements in backtesting.
HAWKISH = {
    "restrictive": 1.0, "tightening": 1.0, "higher for longer": 1.2,
    "inflation remains elevated": 1.2, "additional firming": 1.0,
    "upside risks to inflation": 1.0, "vigilant": 0.6, "persistent": 0.6,
    "overheating": 0.9, "hike": 0.8, "raise rates": 0.9,
}
DOVISH = {
    "rate cut": 1.0, "cut rates": 1.0, "easing": 1.0, "accommodative": 1.0,
    "downside risks to growth": 1.0, "further progress": 0.8, "softening": 0.7,
    "moderating": 0.7, "disinflation": 0.9, "patient": 0.5, "pause": 0.6,
    "cooling labor market": 0.9,
}
# "data dependent" is genuinely neutral — listed so we don't accidentally score it.
NEUTRAL = {"data dependent", "data-dependent", "carefully", "incoming data"}


def score_text(text: str) -> dict:
    """Score a document. Returns {score, hawkish_hits, dovish_hits, hits}."""
    t = text.lower()
    haw = sum(w * len(re.findall(re.escape(k), t)) for k, w in HAWKISH.items())
    dov = sum(w * len(re.findall(re.escape(k), t)) for k, w in DOVISH.items())
    total = haw + dov
    score = 0.0 if total == 0 else (haw - dov) / total  # in [-1, +1]
    return {
        "score": round(score, 3),
        "hawkish_weight": round(haw, 2),
        "dovish_weight": round(dov, 2),
    }


if __name__ == "__main__":
    sample = ("The Committee remains highly attentive to inflation risks. "
              "Inflation remains elevated and the stance is restrictive.")
    print(score_text(sample))
