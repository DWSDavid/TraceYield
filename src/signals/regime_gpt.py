"""Bounded GPT regime reader for macro blocks.

The regime reader is intentionally categorical. It may help label macro blocks
and write narrative, but it never supplies basis-point magnitudes.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.utils.config import DATA, load_yaml

REGIME_CATEGORIES = {
    "inflation": {"hot", "neutral", "cool"},
    "policy": {"hawkish", "neutral", "dovish"},
    "growth": {"strong", "neutral", "weak"},
    "liquidity_supply": {"tight", "neutral", "easy"},
    "global_relative_value": {"rich", "neutral", "cheapening"},
}
DEFAULT_REGIME = {key: "neutral" for key in REGIME_CATEGORIES}

PROMPT = """You are a rates macro analyst. Read the supplied FOMC and macro
context and return STRICT JSON only. You may only choose bounded categories.
Do not include basis-point forecasts or any numeric market move.

Schema:
{{
  "regime": {{
    "inflation": "hot|neutral|cool",
    "policy": "hawkish|neutral|dovish",
    "growth": "strong|neutral|weak",
    "liquidity_supply": "tight|neutral|easy",
    "global_relative_value": "rich|neutral|cheapening"
  }},
  "rationale": "2-4 sentences, no bp magnitudes",
  "key_quotes": ["short verbatim evidence quotes"]
}}

Context:
---
{context}
---"""


def _default_cache_path(as_of: str | None = None) -> Path:
    suffix = as_of or "latest"
    return DATA / "cache" / "regime_gpt" / f"bounded_regime_{suffix}.json"


def _provider_key_available(provider: str) -> bool:
    key_by_provider = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }
    key = key_by_provider.get(provider)
    return bool(key and os.getenv(key))


def _degraded(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "source": "bounded_gpt_unavailable",
        "numeric_bp_allowed": False,
        "regime": dict(DEFAULT_REGIME),
        "rationale": f"Degraded bounded GPT read: {reason}. Magnitudes come from fitted B matrix only.",
        "key_quotes": [],
    }


def _parse_raw(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    text = str(raw).strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    raw_regime = payload.get("regime", {})
    regime = {}
    for block, allowed in REGIME_CATEGORIES.items():
        value = str(raw_regime.get(block, "neutral")).lower()
        regime[block] = value if value in allowed else "neutral"
    return {
        "available": True,
        "source": "bounded_gpt",
        "numeric_bp_allowed": False,
        "regime": regime,
        "rationale": str(payload.get("rationale", "")),
        "key_quotes": [str(item) for item in payload.get("key_quotes", [])][:6],
    }


def _configured_scorer(prompt: str) -> dict[str, Any]:
    cfg = load_yaml("model")["llm"]
    provider = str(cfg["provider"])
    if not _provider_key_available(provider):
        raise RuntimeError(f"{provider} API key unavailable")
    if provider == "openai":
        from openai import OpenAI

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        resp = client.chat.completions.create(
            model=cfg["models"][provider],
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        return _parse_raw(resp.choices[0].message.content)
    if provider == "anthropic":
        import anthropic

        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        msg = client.messages.create(
            model=cfg["models"][provider],
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return _parse_raw(msg.content[0].text)
    if provider == "gemini":
        from google import genai

        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        resp = client.models.generate_content(
            model=cfg["models"][provider], contents=prompt
        )
        return _parse_raw(resp.text)
    raise RuntimeError(f"Unsupported LLM provider: {provider}")


def bounded_regime_read(
    *,
    documents: list[str] | None = None,
    as_of: str | None = None,
    cache_path: str | Path | None = None,
    scorer: Callable[[str], Any] | None = None,
    use_llm: bool = True,
) -> dict[str, Any]:
    """Return bounded categorical regime read, cached and graceful on no key."""
    path = Path(cache_path) if cache_path is not None else _default_cache_path(as_of)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    if not use_llm and scorer is None:
        result = _degraded("LLM disabled")
    else:
        context = "\n\n".join(documents or [])
        prompt = PROMPT.format(context=context[:20000])
        try:
            payload = (scorer or _configured_scorer)(prompt)
            result = _sanitize(_parse_raw(payload))
        except Exception as exc:  # noqa: BLE001 - bounded layer must degrade.
            result = _degraded(str(exc))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result
