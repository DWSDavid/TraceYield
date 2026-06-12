"""TreasuryDirect auction-results ingestion.

Free public API, no key:
https://treasurydirect.gov/TA_WS/securities/search

The API exposes bid-to-cover and bidder allocation fields. It does not reliably
include when-issued yields in the JSON response, so true auction tail is stored
only when a WI field is present; otherwise `tail_bp` is NaN and the stress score
degrades to bid-to-cover and indirect-bidder metrics.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Iterable

import pandas as pd

from src.utils.config import DATA

SEARCH_URL = "https://treasurydirect.gov/TA_WS/securities/search"
CACHE_PATH = DATA / "cache" / "treasury" / "auctions.parquet"
TENORS = {"10-Year": "10Y", "9-Year 10-Month": "10Y", "30-Year": "30Y"}


def _to_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_number(record: dict, fields: Iterable[str]) -> float | None:
    for field in fields:
        value = _to_float(record.get(field))
        if value is not None:
            return value
    return None


def normalize_auction_records(records: list[dict]) -> pd.DataFrame:
    """Normalize TreasuryDirect auction records to 10Y/30Y stress inputs."""
    rows = []
    for record in records:
        term = str(record.get("term") or record.get("securityTerm") or "")
        tenor = TENORS.get(term)
        if tenor is None:
            continue
        auction_date = pd.to_datetime(record.get("auctionDate"), errors="coerce")
        if pd.isna(auction_date):
            continue

        high_yield = _first_number(record, ["highYield", "highInvestmentRate"])
        wi_yield = _first_number(
            record,
            [
                "whenIssuedYield",
                "whenIssuedRate",
                "wiYield",
                "WIYield",
                "whenIssued",
            ],
        )
        tail_bp = (
            round((high_yield - wi_yield) * 100, 3)
            if high_yield is not None and wi_yield is not None
            else float("nan")
        )
        indirect_accepted = _to_float(record.get("indirectBidderAccepted"))
        total_accepted = _to_float(record.get("totalAccepted"))
        indirect_pct = (
            indirect_accepted / total_accepted * 100
            if indirect_accepted is not None and total_accepted
            else float("nan")
        )
        rows.append(
            {
                "auction_date": auction_date.normalize(),
                "tenor": tenor,
                "security_type": record.get("type") or record.get("securityType"),
                "security_term": term,
                "bid_to_cover": _to_float(record.get("bidToCoverRatio")),
                "tail_bp": tail_bp,
                "high_yield": high_yield,
                "indirect_pct": indirect_pct,
                "offering_amount": _to_float(record.get("offeringAmount")),
                "total_accepted": total_accepted,
                "cusip": record.get("cusip"),
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["auction_date", "tenor"]).reset_index(drop=True)


def fetch_records(
    start: str = "2015-01-01",
    end: str | None = None,
    security_type: str | None = None,
) -> list[dict]:
    """Fetch raw TreasuryDirect records for a date range."""
    import requests

    end = end or pd.Timestamp.today().strftime("%Y-%m-%d")
    params = {"format": "json", "auctionDate": f"{start},{end}"}
    if security_type:
        params["type"] = security_type
    response = requests.get(SEARCH_URL, params=params, timeout=90)
    response.raise_for_status()
    return response.json()


def fetch_and_cache(start: str = "2015-01-01", end: str | None = None) -> pd.DataFrame:
    """Fetch Note/Bond auction data and cache normalized 10Y/30Y records."""
    records: list[dict] = []
    for security_type in ("Note", "Bond"):
        records.extend(fetch_records(start=start, end=end, security_type=security_type))
    out = normalize_auction_records(records)
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(CACHE_PATH)
    load_auctions.cache_clear()
    return out


@lru_cache(maxsize=2)
def load_auctions(fetch_if_missing: bool = False) -> pd.DataFrame:
    """Load cached normalized auctions, optionally fetching when absent."""
    if CACHE_PATH.exists():
        df = pd.read_parquet(CACHE_PATH)
        df["auction_date"] = pd.to_datetime(df["auction_date"])
        return df.sort_values(["auction_date", "tenor"]).reset_index(drop=True)
    if not fetch_if_missing:
        return pd.DataFrame()
    try:
        return fetch_and_cache()
    except Exception:
        return pd.DataFrame()


def _zscore_latest(values: pd.Series) -> float:
    values = values.dropna()
    if len(values) < 5:
        return 0.0
    std = values.std()
    if std == 0:
        return 0.0
    return float((values.iloc[-1] - values.mean()) / std)


def _stress_component(
    values: pd.Series, neutral: float, scale: float, inverse: bool
) -> float:
    values = values.dropna()
    if values.empty:
        return 0.0
    if len(values) >= 5:
        z = _zscore_latest(values)
        return -z if inverse else z
    latest = float(values.iloc[-1])
    raw = (neutral - latest) / scale if inverse else (latest - neutral) / scale
    return float(max(-2.0, min(2.0, raw)))


def auction_stress_asof(
    d: pd.Timestamp | str,
    df: pd.DataFrame | None = None,
    lookback_days: int = 120,
) -> float | None:
    """Return rolling auction stress in [-1, +1]; positive = yield-up pressure."""
    data = load_auctions(fetch_if_missing=False) if df is None else df.copy()
    if data.empty:
        return None
    data["auction_date"] = pd.to_datetime(data["auction_date"])
    asof = pd.Timestamp(d)
    known = data[data["auction_date"] <= asof].sort_values("auction_date")
    known = known[known["auction_date"] >= asof - pd.Timedelta(days=lookback_days)]
    if known.empty:
        return None

    scores = []
    for _, group in known.groupby("tenor"):
        group = group.sort_values("auction_date")
        b2c_stress = _stress_component(
            group["bid_to_cover"], neutral=2.45, scale=0.35, inverse=True
        )
        indirect_stress = _stress_component(
            group["indirect_pct"], neutral=65.0, scale=20.0, inverse=True
        )
        tail_stress = _stress_component(
            group["tail_bp"], neutral=0.0, scale=5.0, inverse=False
        )
        components = [b2c_stress, indirect_stress]
        if not pd.isna(tail_stress):
            components.append(tail_stress)
        scores.append(sum(components) / len(components))
    if not scores:
        return None
    raw = sum(scores) / len(scores)
    return float(max(-1.0, min(1.0, raw / 2.0)))


def main() -> None:
    df = fetch_and_cache()
    start = df["auction_date"].min().date() if not df.empty else "n/a"
    end = df["auction_date"].max().date() if not df.empty else "n/a"
    print(
        f"[treasury_auctions] wrote {len(df)} rows to {CACHE_PATH} ({start} -> {end})"
    )


if __name__ == "__main__":
    main()
