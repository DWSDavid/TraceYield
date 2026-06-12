"""Grounded macro narrative built from raw FOMC docs and current macro data.

This layer is narrative/evidence only. It does not write basis-point magnitudes,
move the central path, change fan bands, or tune model parameters.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd

from src.utils.config import DATA, load_yaml

MODEL_USAGE = "narrative_and_regime_only_no_bp_or_central_shift"
RAW_FOMC_DIR = DATA / "raw" / "fomc"
ANALYSIS_CACHE_DIR = DATA / "cache" / "grounded_macro_analysis"
CONTEXT_CHAR_LIMIT = 90000

PROMPT = """You are a rates macro analyst writing TraceYield's end-of-report
grounded macro analysis. Use ONLY the provided context. Return STRICT JSON only.

Hard rules:
- Do not create basis-point forecasts.
- Do not change central path, p50, fan bands, event overlays, or model weights.
- Explain causality in plain English, not jargon.
- Use specific data points and exact FOMC quotes from the context.
- Use percent changes for index/level series and bp changes for rate/yield series.
- Be explicit when a relationship is indirect.

Schema:
{{
  "executive_summary": "4-6 sentences tying the current curve view to the evidence",
  "factor_notes": {{
    "inflation_regime": {{
      "stance": "hot|neutral|cool",
      "reason": "plain-English causal logic",
      "data_points": ["specific data point strings"],
      "quotes": ["short exact quotes from FOMC docs"]
    }},
    "policy_path": {{"stance": "hawkish|neutral|dovish", "reason": "...", "data_points": [], "quotes": []}},
    "growth_risk": {{"stance": "strong|neutral|weak", "reason": "...", "data_points": [], "quotes": []}},
    "liquidity_supply": {{"stance": "tight|neutral|easy", "reason": "...", "data_points": [], "quotes": []}},
    "global_relative_value": {{"stance": "rich|neutral|cheapening", "reason": "...", "data_points": [], "quotes": []}}
  }},
  "logic_chain": ["step-by-step causal chain, no bp forecasts"],
  "key_quotes": [{{"source": "statement|minutes YYYY-MM-DD", "quote": "short exact quote"}}]
}}

Context:
---
{context}
---"""


def _as_of(as_of: Any | None, trajectory: dict[str, Any] | None = None) -> str:
    if as_of is not None:
        return pd.Timestamp(as_of).date().isoformat()
    if trajectory and trajectory.get("as_of"):
        return pd.Timestamp(trajectory["as_of"]).date().isoformat()
    return pd.Timestamp.today().date().isoformat()


def _cache_path(as_of: str) -> Path:
    return ANALYSIS_CACHE_DIR / f"grounded_macro_analysis_{as_of}.json"


def _latest_doc(
    kind: str, as_of: str, raw_fomc_dir: str | Path
) -> dict[str, Any] | None:
    folder = Path(raw_fomc_dir) / kind
    if not folder.exists():
        return None
    cutoff = pd.Timestamp(as_of).normalize()
    candidates = []
    for path in folder.glob("*.txt"):
        try:
            date = pd.Timestamp(path.stem).normalize()
        except ValueError:
            continue
        if date <= cutoff:
            candidates.append((date, path))
    if not candidates:
        return None
    date, path = sorted(candidates)[-1]
    text = path.read_text(encoding="utf-8")
    return {
        "kind": kind,
        "date": date.date().isoformat(),
        "path": str(path),
        "char_count": len(text),
        "text": text,
    }


def _latest_value(df: pd.DataFrame, column: str, as_of: str) -> float | None:
    if column not in df:
        return None
    series = df[column].dropna().sort_index()
    if series.empty:
        return None
    known = series[series.index <= pd.Timestamp(as_of)]
    if known.empty:
        return None
    return float(known.iloc[-1])


def _value_at_or_before(series: pd.Series, cutoff: pd.Timestamp) -> float | None:
    known = series[series.index <= cutoff]
    if known.empty:
        return None
    return float(known.iloc[-1])


def _series_snapshot(
    df: pd.DataFrame,
    column: str,
    as_of: str,
    *,
    yoy: bool = False,
    rate_like: bool = False,
) -> dict[str, Any]:
    if column not in df:
        return {
            "latest": None,
            "latest_date": None,
            "change_3m_pct": None,
            "change_3m_bp": None,
            "yoy_pct": None,
        }
    latest = _latest_value(df, column, as_of)
    series = df[column].dropna().sort_index()
    known = series[series.index <= pd.Timestamp(as_of)]
    latest_date = known.index[-1].date().isoformat() if not known.empty else None
    pct_3m = None
    bp_3m = None
    yoy_value = None
    if latest is not None and latest_date:
        latest_ts = pd.Timestamp(latest_date)
        prev_3m = _value_at_or_before(series, latest_ts - pd.DateOffset(months=3))
        if prev_3m is not None:
            if rate_like:
                bp_3m = round((latest - prev_3m) * 100.0, 1)
            else:
                pct_3m = (
                    None if prev_3m == 0 else round((latest / prev_3m - 1.0) * 100.0, 3)
                )
    if yoy and latest is not None and latest_date:
        latest_ts = pd.Timestamp(latest_date)
        prev_y = _value_at_or_before(series, latest_ts - pd.DateOffset(months=12))
        yoy_value = (
            None
            if prev_y is None or prev_y == 0
            else round((latest / prev_y - 1.0) * 100.0, 3)
        )
    return {
        "latest": None if latest is None else round(float(latest), 6),
        "latest_date": latest_date,
        "change_3m_pct": pct_3m,
        "change_3m_bp": bp_3m,
        "yoy_pct": yoy_value,
    }


def _curve_snapshot(trajectory: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for target in ("2Y", "10Y", "2s10s"):
        points = trajectory.get("tenors", {}).get(target, [])
        if not points:
            continue
        first = points[0]
        last = points[-1]
        out[target] = {
            "current": first.get("current"),
            "month_12_central": last.get("central"),
            "month_12_p10": last.get("p10"),
            "month_12_p90": last.get("p90"),
        }
    return out


def build_grounded_macro_context(
    df: pd.DataFrame,
    trajectory: dict[str, Any],
    *,
    as_of: Any | None = None,
    raw_fomc_dir: str | Path = RAW_FOMC_DIR,
) -> dict[str, Any]:
    """Build the structured context GPT reads for grounded narrative analysis."""
    as_of_value = _as_of(as_of, trajectory)
    history = df.copy()
    history.index = pd.to_datetime(history.index)
    history = history.sort_index()

    statement = _latest_doc("statement", as_of_value, raw_fomc_dir)
    minutes = _latest_doc("minutes", as_of_value, raw_fomc_dir)
    return {
        "as_of": as_of_value,
        "fomc_documents": {
            "statement": statement,
            "minutes": minutes,
            "speeches": [],
        },
        "macro_snapshot": {
            "inflation": {
                column: _series_snapshot(
                    history,
                    column,
                    as_of_value,
                    yoy=column in {"CPIAUCSL", "CPILFESL", "PCEPI", "PCEPILFE"},
                    rate_like=column in {"T5YIE", "T10YIE", "T5YIFR"},
                )
                for column in (
                    "CPIAUCSL",
                    "CPILFESL",
                    "PCEPI",
                    "PCEPILFE",
                    "T5YIE",
                    "T10YIE",
                    "T5YIFR",
                )
            },
            "growth": {
                column: _series_snapshot(
                    history,
                    column,
                    as_of_value,
                    yoy=column in {"PAYEMS", "RSAFS", "IPMAN"},
                    rate_like=column == "UNRATE",
                )
                for column in ("PAYEMS", "UNRATE", "ICSA", "IPMAN", "RSAFS", "JTSJOL")
            },
            "liquidity_supply": {
                column: _series_snapshot(history, column, as_of_value)
                for column in ("WALCL", "WRESBAL", "RRPONTSYD", "WTREGEN")
            },
            "global_relative_value": {
                column: _series_snapshot(
                    history,
                    column,
                    as_of_value,
                    rate_like=column in {"IRLTLT01DEM156N", "IRLTLT01JPM156N"},
                )
                for column in ("IRLTLT01DEM156N", "IRLTLT01JPM156N", "DTWEXBGS")
            },
        },
        "policy_path": trajectory.get("metadata", {}).get("policy_path", {}),
        "polymarket_check": trajectory.get("metadata", {}).get("polymarket_check", {}),
        "curve_view": _curve_snapshot(trajectory),
        "model_guardrail": MODEL_USAGE,
    }


def _context_for_prompt(context: dict[str, Any]) -> str:
    return json.dumps(context, ensure_ascii=False, indent=2)[:CONTEXT_CHAR_LIMIT]


def _openai_scorer(prompt: str) -> dict[str, Any]:
    cfg = load_yaml("model")["llm"]
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model=cfg["models"]["openai"],
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    return json.loads(response.choices[0].message.content)


def _quote_from_doc(doc: dict[str, Any] | None, needle: str) -> str | None:
    if not doc:
        return None
    for line in str(doc.get("text", "")).splitlines():
        clean = " ".join(line.split())
        if needle.lower() in clean.lower() and 20 <= len(clean) <= 260:
            return clean
    return None


def _deterministic_analysis(context: dict[str, Any], reason: str) -> dict[str, Any]:
    statement = context.get("fomc_documents", {}).get("statement")
    minutes = context.get("fomc_documents", {}).get("minutes")
    inflation_quote = _quote_from_doc(statement, "inflation") or _quote_from_doc(
        minutes, "inflation"
    )
    labor_quote = _quote_from_doc(statement, "labor") or _quote_from_doc(
        minutes, "labor"
    )
    policy = context.get("policy_path", {})
    curve = context.get("curve_view", {}).get("10Y", {})
    key_quotes = []
    if inflation_quote:
        key_quotes.append(
            {"source": f"statement {statement.get('date')}", "quote": inflation_quote}
        )
    if labor_quote:
        source_kind = (
            "statement"
            if statement and labor_quote in statement.get("text", "")
            else "minutes"
        )
        source_date = (statement if source_kind == "statement" else minutes or {}).get(
            "date"
        )
        key_quotes.append(
            {"source": f"{source_kind} {source_date}", "quote": labor_quote}
        )
    return {
        "available": False,
        "source": "grounded_macro_analysis_fallback",
        "model_usage": MODEL_USAGE,
        "executive_summary": (
            "Grounded GPT analysis was unavailable, so this section uses deterministic "
            "context from the latest raw FOMC documents and macro snapshot. Inflation "
            "language and the policy-path gap are the main evidence points; curve levels "
            "remain model-derived, not narrative-derived."
        ),
        "factor_notes": {
            "inflation_regime": {
                "stance": "hot" if inflation_quote else "neutral",
                "reason": (
                    "Inflation language matters because bond investors are paid back in "
                    "future dollars. If inflation is elevated, those dollars buy less, so "
                    "investors demand more compensation and yields face upward pressure."
                ),
                "data_points": ["See macro_snapshot inflation fields in metadata."],
                "quotes": [inflation_quote] if inflation_quote else [],
            },
            "policy_path": {
                "stance": str(policy.get("direction", "HOLD")).lower(),
                "reason": (
                    f"Policy path source says {policy.get('direction', 'HOLD')} with "
                    f"market-vs-dot gap {policy.get('market_vs_fed_gap_bp')}bp. That "
                    "affects the front end first because 2Y reflects expected Fed policy."
                ),
                "data_points": [str(policy.get("reason", ""))],
                "quotes": [],
            },
            "growth_risk": {
                "stance": "neutral",
                "reason": "Labor and growth data matter through recession risk and Fed-cut timing.",
                "data_points": ["See macro_snapshot growth fields in metadata."],
                "quotes": [labor_quote] if labor_quote else [],
            },
        },
        "logic_chain": [
            "Raw FOMC language and released macro data describe the current regime.",
            "Inflation pressure raises required compensation and limits Fed easing room.",
            "Policy-path evidence mainly affects the 2Y/front-end curve.",
            f"The saved 10Y central path is {curve.get('month_12_central')} versus current {curve.get('current')}; GPT does not set these levels.",
        ],
        "key_quotes": key_quotes[:4],
        "degraded_reason": reason,
    }


def _sanitize(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    docs = [
        {
            "kind": doc.get("kind"),
            "date": doc.get("date"),
            "char_count": doc.get("char_count"),
        }
        for doc in context.get("fomc_documents", {}).values()
        if isinstance(doc, dict)
    ]
    return {
        "available": True,
        "source": "grounded_gpt",
        "model_usage": MODEL_USAGE,
        "documents_used": docs,
        "executive_summary": str(payload.get("executive_summary", "")),
        "factor_notes": payload.get("factor_notes", {}),
        "logic_chain": [str(item) for item in payload.get("logic_chain", [])][:8],
        "key_quotes": [
            {
                "source": str(item.get("source", "")),
                "quote": str(item.get("quote", "")),
            }
            for item in payload.get("key_quotes", [])
            if isinstance(item, dict)
        ][:8],
    }


def grounded_macro_analysis(
    df: pd.DataFrame,
    trajectory: dict[str, Any],
    *,
    as_of: Any | None = None,
    raw_fomc_dir: str | Path = RAW_FOMC_DIR,
    cache_path: str | Path | None = None,
    scorer: Callable[[str], Any] | None = None,
    use_llm: bool = True,
) -> dict[str, Any]:
    """Return cached grounded macro analysis using full latest raw FOMC docs."""
    as_of_value = _as_of(as_of, trajectory)
    path = Path(cache_path) if cache_path is not None else _cache_path(as_of_value)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    context = build_grounded_macro_context(
        df,
        trajectory,
        as_of=as_of_value,
        raw_fomc_dir=raw_fomc_dir,
    )
    prompt = PROMPT.format(context=_context_for_prompt(context))
    try:
        if not use_llm and scorer is None:
            raise RuntimeError("LLM disabled")
        if scorer is None and not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY unavailable")
        payload = (scorer or _openai_scorer)(prompt)
        result = _sanitize(payload, context)
    except Exception as exc:  # noqa: BLE001 - report must degrade gracefully.
        result = _deterministic_analysis(context, str(exc))
        result["documents_used"] = [
            {
                "kind": doc.get("kind"),
                "date": doc.get("date"),
                "char_count": doc.get("char_count"),
            }
            for doc in context.get("fomc_documents", {}).values()
            if isinstance(doc, dict)
        ]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def attach_grounded_macro_analysis(
    df: pd.DataFrame,
    trajectory: dict[str, Any],
    *,
    as_of: Any | None = None,
    raw_fomc_dir: str | Path = RAW_FOMC_DIR,
    cache_path: str | Path | None = None,
    scorer: Callable[[str], Any] | None = None,
    use_llm: bool = True,
) -> dict[str, Any]:
    """Attach grounded narrative metadata without changing curve values."""
    import copy

    adjusted = copy.deepcopy(trajectory)
    adjusted.setdefault("metadata", {})["grounded_macro_analysis"] = (
        grounded_macro_analysis(
            df,
            adjusted,
            as_of=as_of,
            raw_fomc_dir=raw_fomc_dir,
            cache_path=cache_path,
            scorer=scorer,
            use_llm=use_llm,
        )
    )
    return adjusted
