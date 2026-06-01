"""Pluggable LLM hawkish/dovish scorer for FOMC docs (event days).

One prompt, swappable backend (OpenAI / Anthropic / Gemini) chosen in
configs/model.yaml. Each returns the SAME contract:
    {hawkish_score in [-1,1], confidence in [0,1], rationale, key_phrases}
Scores are auditable (every one carries a written rationale).
"""
from __future__ import annotations

import json

from src.utils.config import env, load_yaml

PROMPT = """You are a Fed-watching rates analyst. Read the following Federal
Reserve document and judge its monetary-policy tone for US Treasury yields.

Return STRICT JSON only, no prose:
{{
  "hawkish_score": <float in [-1, 1], +1 = very hawkish (tighter, yields up),
                    -1 = very dovish (easier, yields down)>,
  "confidence": <float in [0, 1]>,
  "rationale": "<2-3 sentences citing specific language>",
  "key_phrases": ["<short verbatim phrases that drove the score>"],
  "key_quotes": ["<2-4 FULL verbatim sentences copied EXACTLY from the document
                  that most justify the score — these are evidence, do not
                  paraphrase, quote word-for-word>"]
}}

Document:
---
{doc}
---"""


def _cfg() -> dict:
    return load_yaml("model")["llm"]


def _parse(raw: str) -> dict:
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"hawkish_score": 0.0, "confidence": 0.0,
                "rationale": "parse_failed", "key_phrases": [], "raw": raw}


# --- providers -------------------------------------------------------------

def _score_openai(doc: str, model: str) -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=env("OPENAI_API_KEY"))
    resp = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": PROMPT.format(doc=doc)}],
    )
    return _parse(resp.choices[0].message.content)


def _score_anthropic(doc: str, model: str) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=env("ANTHROPIC_API_KEY"))
    msg = client.messages.create(
        model=model, max_tokens=1024,
        messages=[{"role": "user", "content": PROMPT.format(doc=doc)}],
    )
    return _parse(msg.content[0].text)


def _score_gemini(doc: str, model: str) -> dict:
    from google import genai
    client = genai.Client(api_key=env("GEMINI_API_KEY"))
    resp = client.models.generate_content(
        model=model, contents=PROMPT.format(doc=doc))
    return _parse(resp.text)


_PROVIDERS = {
    "openai": _score_openai,
    "anthropic": _score_anthropic,
    "gemini": _score_gemini,
}


def score_document(text: str, provider: str | None = None) -> dict:
    """Score a Fed document. provider defaults to configs/model.yaml."""
    cfg = _cfg()
    provider = provider or cfg["provider"]
    model = cfg["models"][provider]
    doc = text[: cfg["max_chars"]]
    result = _PROVIDERS[provider](doc, model)
    result["provider"] = provider
    result["model"] = model
    return result


if __name__ == "__main__":
    sample = ("The Committee judges that inflation remains elevated and the "
              "stance of policy is restrictive. It is not yet appropriate to "
              "reduce the target range.")
    print(json.dumps(score_document(sample), indent=2, ensure_ascii=False))
