"""Read-only Polymarket external market check for the curve report.

This module is deliberately not a model input. It only writes a point-in-time
metadata snapshot so the report can compare TraceYield's 10Y view against a
public prediction-market signal.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from src.utils.config import DATA

GAMMA_API_BASE = "https://gamma-api.polymarket.com"
QUERY_TERMS = ["10Y Treasury", "Treasury yield", "US 10 year yield", "rates"]
USER_AGENT = "TraceYield/0.1 external-market-check"
MIN_RELEVANCE_SCORE = 0.60
MAX_MARKETS = 12


def _today_iso() -> str:
    return date.today().isoformat()


def _as_of_iso(trajectory: dict[str, Any] | None, as_of: str | None) -> str:
    if as_of:
        return pd.Timestamp(as_of).date().isoformat()
    if trajectory and trajectory.get("as_of"):
        return pd.Timestamp(trajectory["as_of"]).date().isoformat()
    return _today_iso()


def _default_fetch_json(url: str) -> Any:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _empty_contract(
    *,
    as_of: str,
    status: str,
    reason: str,
    query_terms: list[str],
) -> dict[str, Any]:
    return {
        "as_of": as_of,
        "source": "polymarket_gamma",
        "status": status,
        "query_terms": query_terms,
        "markets": [],
        "traceyield_alignment": "unavailable",
        "alignment_reason": reason,
        "model_usage": "external_check_only_no_central_shift",
    }


def _parse_jsonish_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        if isinstance(parsed, list):
            return parsed
        return [parsed]
    return [value]


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)


def _text_for_market(
    market: dict[str, Any], event: dict[str, Any] | None = None
) -> str:
    event = event or {}
    return " ".join(
        str(part or "")
        for part in (
            event.get("title"),
            event.get("slug"),
            market.get("question"),
            market.get("slug"),
            market.get("description"),
        )
    ).lower()


def _relevance_score(
    market: dict[str, Any], event: dict[str, Any] | None = None
) -> float:
    text = _text_for_market(market, event)
    has_treasury = "treasury" in text or "t-bond" in text or "t bond" in text
    has_yield = "yield" in text
    has_10y = any(
        token in text
        for token in (
            "10-year",
            "10 year",
            "10y",
            "10 yr",
            "10-yr",
            "10-year treasury",
        )
    )
    score = 0.0
    if has_treasury and has_yield:
        score += 0.45
    if has_10y:
        score += 0.30
    if "before 2027" in text or "by 2027" in text:
        score += 0.10
    if "dip below" in text or "hit" in text or "above" in text or "reach" in text:
        score += 0.10
    if "department of the treasury" in text:
        score += 0.05
    if not (has_treasury and has_yield and has_10y):
        score = min(score, 0.35)
    return round(min(score, 1.0), 4)


def _risk_flags(
    *,
    closed: bool,
    volume: float | None,
    liquidity: float | None,
    spread: float | None,
    description: str | None,
    outcomes: list[str],
) -> list[str]:
    flags: list[str] = []
    if closed:
        flags.append("closed_or_resolved")
    if volume is None or volume < 10_000:
        flags.append("low_volume")
    if not closed and liquidity is not None and liquidity < 1_000:
        flags.append("low_liquidity")
    if spread is not None and spread > 0.10:
        flags.append("wide_spread")
    if len(outcomes) < 2 or not {"yes", "no"}.issubset(
        {str(outcome).lower() for outcome in outcomes}
    ):
        flags.append("non_binary_outcomes")
    if not description:
        flags.append("weak_resolution_note")
    return flags


def _confidence(
    *,
    closed: bool,
    volume: float | None,
    liquidity: float | None,
    spread: float | None,
    risk_flags: list[str],
) -> str:
    if closed:
        return "low"
    volume_value = volume or 0.0
    liquidity_value = liquidity or 0.0
    spread_value = 1.0 if spread is None else spread
    if (
        volume_value >= 100_000
        and liquidity_value >= 5_000
        and spread_value <= 0.03
        and not risk_flags
    ):
        return "high"
    if volume_value >= 10_000 and spread_value <= 0.10:
        return "med"
    return "low"


def _normalized_market(
    market: dict[str, Any],
    *,
    event: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    relevance = _relevance_score(market, event)
    if relevance < MIN_RELEVANCE_SCORE:
        return None

    outcomes = [str(item) for item in _parse_jsonish_list(market.get("outcomes"))]
    prices = [
        _to_float(item) for item in _parse_jsonish_list(market.get("outcomePrices"))
    ]
    outcome_prices = [float(item) for item in prices if item is not None]
    price_by_outcome = {
        outcome.lower(): price
        for outcome, price in zip(outcomes, prices, strict=False)
        if price is not None
    }
    closed = _to_bool(market.get("closed"))
    active = _to_bool(market.get("active"))
    volume = _to_float(market.get("volumeNum", market.get("volume")))
    liquidity = _to_float(market.get("liquidityNum", market.get("liquidity")))
    spread = _to_float(market.get("spread"))
    best_bid = _to_float(market.get("bestBid"))
    best_ask = _to_float(market.get("bestAsk"))
    description = market.get("description")
    flags = _risk_flags(
        closed=closed,
        volume=volume,
        liquidity=liquidity,
        spread=spread,
        description=description,
        outcomes=outcomes,
    )
    confidence = _confidence(
        closed=closed,
        volume=volume,
        liquidity=liquidity,
        spread=spread,
        risk_flags=flags,
    )
    return {
        "id": str(market.get("id", "")),
        "slug": str(market.get("slug", "")),
        "question": str(market.get("question", "")),
        "description": str(description) if description else None,
        "end_date": market.get("endDate") or market.get("endDateIso"),
        "active": active,
        "closed": closed,
        "outcomes": outcomes,
        "outcome_prices": outcome_prices,
        "yes_price": price_by_outcome.get("yes"),
        "no_price": price_by_outcome.get("no"),
        "volume": volume,
        "liquidity": liquidity,
        "spread": spread,
        "last_trade_price": _to_float(market.get("lastTradePrice")),
        "best_bid": best_bid,
        "best_ask": best_ask,
        "resolution_note": market.get("resolutionSource") or description,
        "relevance_score": relevance,
        "confidence": confidence,
        "risk_flags": flags,
    }


def _extract_markets(
    payload: Any,
) -> list[tuple[dict[str, Any], dict[str, Any] | None]]:
    if not isinstance(payload, dict):
        return []
    extracted: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    for event in payload.get("events", []) or []:
        if not isinstance(event, dict):
            continue
        for market in event.get("markets", []) or []:
            if isinstance(market, dict):
                extracted.append((market, event))
    for market in payload.get("markets", []) or []:
        if isinstance(market, dict):
            extracted.append((market, None))
    return extracted


def _dedupe_markets(markets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for market in sorted(
        markets,
        key=lambda item: (
            item["confidence"] != "high",
            item["confidence"] != "med",
            -(item.get("relevance_score") or 0.0),
            -float(item.get("volume") or 0.0),
        ),
    ):
        key = market.get("id") or market.get("slug") or market.get("question")
        if key in seen:
            continue
        seen.add(str(key))
        out.append(market)
    return out[:MAX_MARKETS]


def _traceyield_direction(trajectory: dict[str, Any] | None) -> str:
    if not trajectory:
        return "unavailable"
    points = trajectory.get("tenors", {}).get("10Y") or []
    if not points:
        return "unavailable"
    first = points[0]
    final = points[-1]
    current = first.get("current")
    central = final.get("central")
    if current is None or central is None:
        return "unavailable"
    delta_bp = (float(central) - float(current)) * 100.0
    if delta_bp <= -10.0:
        return "lower"
    if delta_bp >= 10.0:
        return "higher"
    return "range-bound"


def _threshold_side(question: str) -> str | None:
    text = question.lower()
    if "dip below" in text or "below" in text:
        return "lower"
    if "hit" in text or "above" in text or "reach" in text:
        return "higher"
    return None


def _polymarket_direction(markets: list[dict[str, Any]]) -> tuple[str, str]:
    lower_probs: list[float] = []
    higher_probs: list[float] = []
    for market in markets:
        if market.get("closed"):
            continue
        yes_price = market.get("yes_price")
        if yes_price is None:
            continue
        side = _threshold_side(str(market.get("question", "")))
        if side == "lower":
            lower_probs.append(float(yes_price))
        elif side == "higher":
            higher_probs.append(float(yes_price))

    if not lower_probs and not higher_probs:
        return "unavailable", "no active threshold prices"
    lower = max(lower_probs) if lower_probs else 0.0
    higher = max(higher_probs) if higher_probs else 0.0
    if lower >= higher + 0.10:
        return (
            "lower",
            f"lower-threshold Yes {lower:.2f} vs higher-threshold Yes {higher:.2f}",
        )
    if higher >= lower + 0.10:
        return (
            "higher",
            f"higher-threshold Yes {higher:.2f} vs lower-threshold Yes {lower:.2f}",
        )
    return (
        "mixed",
        f"lower-threshold Yes {lower:.2f} vs higher-threshold Yes {higher:.2f}",
    )


def _alignment(
    *,
    trajectory: dict[str, Any] | None,
    markets: list[dict[str, Any]],
) -> tuple[str, str]:
    traceyield = _traceyield_direction(trajectory)
    polymarket, poly_reason = _polymarket_direction(markets)
    suffix = (
        " External check only; no central, p50, fan, overlay, or bp magnitude changed."
    )
    if traceyield == "unavailable" or polymarket == "unavailable":
        return "unavailable", f"Alignment unavailable: {poly_reason}.{suffix}"
    if polymarket == "mixed":
        return (
            "mixed",
            f"Polymarket threshold prices are mixed while TraceYield is {traceyield}.{suffix}",
        )
    if traceyield == polymarket:
        return (
            "agree",
            f"Polymarket {poly_reason} agrees with TraceYield {traceyield} 10Y lean.{suffix}",
        )
    if traceyield == "range-bound":
        return (
            "mixed",
            f"TraceYield is range-bound while Polymarket leans {polymarket}: {poly_reason}.{suffix}",
        )
    return (
        "disagree",
        f"Polymarket {poly_reason} disagrees with TraceYield {traceyield} 10Y lean.{suffix}",
    )


def _snapshot_payload(
    *,
    contract: dict[str, Any],
    raw_responses: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "captured_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "contract": contract,
        "raw_responses": raw_responses,
    }


def _write_snapshot(
    *,
    contract: dict[str, Any],
    raw_responses: list[dict[str, Any]],
    snapshot_dir: str | Path,
) -> None:
    directory = Path(snapshot_dir)
    directory.mkdir(parents=True, exist_ok=True)
    payload = _snapshot_payload(contract=contract, raw_responses=raw_responses)
    as_of = str(contract["as_of"]).replace("-", "")
    dated = directory / f"polymarket_check_{as_of}.json"
    latest = directory / "polymarket_check_latest.json"
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    dated.write_text(text, encoding="utf-8")
    latest.write_text(text, encoding="utf-8")


class PolymarketGammaProvider:
    """Public/read-only Polymarket Gamma discovery provider."""

    source = "polymarket_gamma"

    def __init__(
        self,
        *,
        fetcher: Callable[[str], Any] | None = None,
        query_terms: list[str] | None = None,
    ) -> None:
        self.fetcher = fetcher or _default_fetch_json
        self.query_terms = query_terms or QUERY_TERMS

    def _search_url(self, term: str) -> str:
        return f"{GAMMA_API_BASE}/public-search?{urlencode({'q': term, 'limit': 10})}"

    def get_check(
        self,
        trajectory: dict[str, Any] | None = None,
        *,
        as_of: str | None = None,
        snapshot_dir: str | Path = DATA / "cache" / "polymarket",
        save_snapshot: bool = True,
    ) -> dict[str, Any]:
        """Return the external-market-check contract."""
        as_of_value = _as_of_iso(trajectory, as_of)
        raw_responses: list[dict[str, Any]] = []
        normalized: list[dict[str, Any]] = []

        try:
            for term in self.query_terms:
                url = self._search_url(term)
                payload = self.fetcher(url)
                raw_responses.append({"query": term, "url": url, "payload": payload})
                for market, event in _extract_markets(payload):
                    item = _normalized_market(market, event=event)
                    if item is not None:
                        normalized.append(item)
        except Exception as exc:  # noqa: BLE001 - external check must degrade.
            contract = _empty_contract(
                as_of=as_of_value,
                status="unavailable",
                reason=f"Polymarket public API unavailable: {exc}",
                query_terms=self.query_terms,
            )
            if save_snapshot:
                _write_snapshot(
                    contract=contract,
                    raw_responses=raw_responses,
                    snapshot_dir=snapshot_dir,
                )
            return contract

        markets = _dedupe_markets(normalized)
        if not markets:
            contract = _empty_contract(
                as_of=as_of_value,
                status="no_relevant_market",
                reason="No relevant public Polymarket 10Y Treasury yield market found.",
                query_terms=self.query_terms,
            )
            if save_snapshot:
                _write_snapshot(
                    contract=contract,
                    raw_responses=raw_responses,
                    snapshot_dir=snapshot_dir,
                )
            return contract

        alignment, reason = _alignment(trajectory=trajectory, markets=markets)
        status = (
            "available"
            if any(market.get("confidence") in {"med", "high"} for market in markets)
            else "low_confidence"
        )
        contract = {
            "as_of": as_of_value,
            "source": self.source,
            "status": status,
            "query_terms": self.query_terms,
            "markets": markets,
            "traceyield_alignment": alignment,
            "alignment_reason": reason,
            "model_usage": "external_check_only_no_central_shift",
        }
        if save_snapshot:
            _write_snapshot(
                contract=contract,
                raw_responses=raw_responses,
                snapshot_dir=snapshot_dir,
            )
        return contract


def attach_polymarket_check(
    trajectory: dict[str, Any],
    *,
    provider: PolymarketGammaProvider | None = None,
    snapshot_dir: str | Path = DATA / "cache" / "polymarket",
    save_snapshot: bool = True,
) -> dict[str, Any]:
    """Attach Polymarket metadata without changing any curve values."""
    adjusted = copy.deepcopy(trajectory)
    check_provider = provider or PolymarketGammaProvider()
    adjusted.setdefault("metadata", {})["polymarket_check"] = check_provider.get_check(
        adjusted,
        snapshot_dir=snapshot_dir,
        save_snapshot=save_snapshot,
    )
    return adjusted


if __name__ == "__main__":
    result = PolymarketGammaProvider().get_check()
    print(json.dumps(result, indent=2, ensure_ascii=False))
