"""Deep LLM hawkish/dovish scorer for FOMC release / major-speech days.

Calls the Claude API to read a Fed document and return a hawkish score in
[-1, +1] WITH a written rationale, so every score is auditable. Use sparingly
(event days only) to control cost; the keyword scorer handles daily scans.
"""
from __future__ import annotations

import json

from src.utils.config import env

MODEL = "claude-opus-4-8"  # deep read; swap to sonnet for cheaper daily use

PROMPT = """You are a Fed-watching rates analyst. Read the following Federal
Reserve document and judge its monetary-policy tone.

Return STRICT JSON only:
{{
  "hawkish_score": <float in [-1, 1], +1 = very hawkish, -1 = very dovish>,
  "confidence": <float in [0, 1]>,
  "rationale": "<2-3 sentences citing specific language>",
  "key_phrases": ["<verbatim phrases that drove the score>"]
}}

Document:
---
{doc}
---"""


def score_document(text: str) -> dict:
    """Score a Fed document with Claude. Returns parsed JSON dict."""
    import anthropic  # lazy import so module loads without the dep

    client = anthropic.Anthropic(api_key=env("ANTHROPIC_API_KEY"))
    # Truncate very long minutes to stay within a sane budget.
    doc = text[:40000]
    msg = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": PROMPT.format(doc=doc)}],
    )
    raw = msg.content[0].text.strip()
    # Strip markdown fences if the model added them.
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"hawkish_score": 0.0, "confidence": 0.0,
                "rationale": "parse_failed", "raw": raw}


if __name__ == "__main__":
    print(score_document("The Committee decided to maintain the target range "
                         "and noted inflation has eased over the past year."))
