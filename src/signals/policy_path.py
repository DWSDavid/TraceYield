"""Free and pluggable market-implied policy-path providers."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol
from urllib.request import urlopen

import pandas as pd

from src.utils.config import DATA, load_yaml

ATLANTA_RESEARCH_DATA_URL = "https://www.atlantafed.org/data/research-data"
MANUAL_FEDWATCH_PATH = DATA / "manual" / "fedwatch_latest.csv"
DIRECTION_THRESHOLD_BP = 25.0
PROBABILITY_DIRECTION_THRESHOLD = 0.50


class PolicyPathProvider(Protocol):
    """Provider interface for policy-path contracts."""

    def get_policy_path(
        self,
        df: pd.DataFrame,
        *,
        as_of: pd.Timestamp | str | None = None,
    ) -> dict[str, Any]:
        """Return one policy-path contract."""


def _as_timestamp(value: pd.Timestamp | str | None, df: pd.DataFrame) -> pd.Timestamp:
    if value is not None:
        return pd.Timestamp(value).normalize()
    if df.empty:
        return pd.Timestamp.today().normalize()
    return pd.Timestamp(df.index.max()).normalize()


def _as_date(value: Any) -> Any:
    return pd.Timestamp(value).date()


def _latest_value(
    df: pd.DataFrame,
    column: str,
    as_of: pd.Timestamp,
) -> float | None:
    if column not in df:
        return None
    series = df[column].dropna().sort_index()
    if series.empty:
        return None
    known = series[series.index <= as_of]
    if known.empty:
        return None
    return float(known.iloc[-1])


def _next_fomc_meeting(as_of: pd.Timestamp) -> Any | None:
    cfg = load_yaml("fomc_calendar")
    meetings = sorted(
        (_as_date(item["decision_date"]) for item in cfg.get("meetings", [])),
        key=pd.Timestamp,
    )
    for meeting in meetings:
        if pd.Timestamp(meeting) >= as_of:
            return meeting
    return None


def _yaml_dot_path() -> dict[str, float]:
    cfg = load_yaml("fed_dot_plot")
    medians = cfg.get("median_fed_funds_rate_pct", {})
    return {
        str(key): float(value) for key, value in medians.items() if value is not None
    }


def _current_policy_from_yaml() -> float | None:
    cfg = load_yaml("fed_dot_plot")
    value = cfg.get("current_target_midpoint_pct")
    return float(value) if value is not None else None


def fed_dot_median_path(
    df: pd.DataFrame | None = None,
    *,
    as_of: pd.Timestamp | str | None = None,
) -> dict[str, float]:
    """Return SEP median path, preferring available FRED columns over YAML."""
    path = _yaml_dot_path()
    if df is None or df.empty:
        return path

    timestamp = _as_timestamp(as_of, df)
    current_year = str(timestamp.year)
    fred_current_year = _latest_value(df, "FEDTARMD", timestamp)
    fred_longer_run = _latest_value(df, "FEDTARMDLR", timestamp)
    if fred_current_year is not None:
        path[current_year] = round(fred_current_year, 4)
    if fred_longer_run is not None:
        path["longer_run"] = round(fred_longer_run, 4)
    return path


def _current_policy_rate(df: pd.DataFrame, as_of: pd.Timestamp) -> float | None:
    return (
        _latest_value(df, "DFEDTARU", as_of)
        or _latest_value(df, "EFFR", as_of)
        or _current_policy_from_yaml()
    )


def _direction(implied_6m: float | None, current: float | None) -> str:
    if implied_6m is None or current is None:
        return "HOLD"
    gap_bp = (float(implied_6m) - float(current)) * 100.0
    if gap_bp <= -DIRECTION_THRESHOLD_BP:
        return "EASING"
    if gap_bp >= DIRECTION_THRESHOLD_BP:
        return "TIGHTENING"
    return "HOLD"


def _direction_from_probabilities(contract: dict[str, Any]) -> str | None:
    cut_prob = contract.get("next_meeting_cut_prob")
    hike_prob = contract.get("next_meeting_hike_prob")
    if cut_prob is not None and float(cut_prob) >= PROBABILITY_DIRECTION_THRESHOLD:
        return "EASING"
    if hike_prob is not None and float(hike_prob) >= PROBABILITY_DIRECTION_THRESHOLD:
        return "TIGHTENING"
    return None


def _market_vs_fed_gap_bp(
    implied_6m: float | None,
    dot_path: dict[str, float],
    as_of: pd.Timestamp,
) -> float | None:
    dot = dot_path.get(str(as_of.year))
    if implied_6m is None or dot is None:
        return None
    return round((float(implied_6m) - float(dot)) * 100.0, 1)


def _base_contract(
    *,
    as_of: pd.Timestamp,
    source: str,
    next_meeting_date: Any | None,
    fed_dot_path: dict[str, float],
    reason: str,
) -> dict[str, Any]:
    return {
        "as_of": as_of.date(),
        "source": source,
        "next_meeting_date": next_meeting_date,
        "next_meeting_cut_prob": None,
        "next_meeting_hike_prob": None,
        "next_meeting_hold_prob": None,
        "expected_target_rate_after_meeting": None,
        "implied_policy_rate_3m": None,
        "implied_policy_rate_6m": None,
        "implied_policy_rate_12m": None,
        "fed_dot_median_path": fed_dot_path,
        "market_vs_fed_gap_bp": None,
        "direction": "HOLD",
        "confidence": "low",
        "reason": reason,
    }


class FredProxyPolicyPathProvider:
    """Free FRED short-rate proxy for the market-implied policy path."""

    source = "fred_proxy"

    def get_policy_path(
        self,
        df: pd.DataFrame,
        *,
        as_of: pd.Timestamp | str | None = None,
    ) -> dict[str, Any]:
        timestamp = _as_timestamp(as_of, df)
        dot_path = fed_dot_median_path(df, as_of=timestamp)
        next_meeting = _next_fomc_meeting(timestamp)
        current = _current_policy_rate(df, timestamp)

        dgs3mo = _latest_value(df, "DGS3MO", timestamp)
        dgs6mo = _latest_value(df, "DGS6MO", timestamp)
        dgs1 = _latest_value(df, "DGS1", timestamp)
        dgs2 = _latest_value(df, "DGS2", timestamp)
        dgs5 = _latest_value(df, "DGS5", timestamp)

        fallback_notes: list[str] = []
        if dgs3mo is not None:
            implied_3m = dgs3mo
        elif current is not None and dgs2 is not None:
            implied_3m = current + 0.25 * (dgs2 - current)
            fallback_notes.append("DGS3MO missing, 3m uses current-to-2Y slope")
        else:
            implied_3m = current
            fallback_notes.append("DGS3MO missing")

        if dgs3mo is not None and dgs6mo is not None:
            implied_6m = 2.0 * dgs6mo - dgs3mo
        elif current is not None and dgs2 is not None:
            implied_6m = current + 0.50 * (dgs2 - current)
            fallback_notes.append("DGS6MO missing, 6m uses current-to-2Y slope")
        else:
            implied_6m = implied_3m
            fallback_notes.append("DGS6MO missing")

        if dgs6mo is not None and dgs1 is not None:
            implied_12m = 2.0 * dgs1 - dgs6mo
        elif dgs1 is not None:
            implied_12m = dgs1
            fallback_notes.append("DGS6MO missing, 12m uses DGS1")
        elif dgs2 is not None:
            implied_12m = dgs2
            fallback_notes.append("DGS1 missing, 12m uses DGS2")
        elif dgs5 is not None:
            implied_12m = dgs5
            fallback_notes.append("DGS1/DGS2 missing, 12m uses DGS5")
        else:
            implied_12m = implied_6m
            fallback_notes.append("term structure missing")

        implied_3m = None if implied_3m is None else round(float(implied_3m), 4)
        implied_6m = None if implied_6m is None else round(float(implied_6m), 4)
        implied_12m = None if implied_12m is None else round(float(implied_12m), 4)

        confidence = "low"
        direction = _direction(implied_6m, current)
        gap_bp = _market_vs_fed_gap_bp(implied_6m, dot_path, timestamp)
        formula = "3m=DGS3MO; 6m=2*DGS6MO-DGS3MO; 12m=2*DGS1-DGS6MO"
        fallback = f" Fallbacks: {'; '.join(fallback_notes)}." if fallback_notes else ""
        reason = (
            f"FRED proxy ({formula}) says {direction.lower()}: "
            f"6m {implied_6m} vs current policy {current}."
            f"{fallback} This is a Treasury/front-end proxy, not futures pricing; "
            f"the +/-{DIRECTION_THRESHOLD_BP:.0f}bp HOLD band allows for "
            "bill-vs-funds basis and term premium."
        )

        return {
            "as_of": timestamp.date(),
            "source": self.source,
            "next_meeting_date": next_meeting,
            "next_meeting_cut_prob": None,
            "next_meeting_hike_prob": None,
            "next_meeting_hold_prob": None,
            "expected_target_rate_after_meeting": None,
            "implied_policy_rate_3m": implied_3m,
            "implied_policy_rate_6m": implied_6m,
            "implied_policy_rate_12m": implied_12m,
            "fed_dot_median_path": dot_path,
            "market_vs_fed_gap_bp": gap_bp,
            "direction": direction,
            "confidence": confidence,
            "reason": reason,
        }


class FedWatchCsvPolicyPathProvider:
    """Optional manual CME FedWatch CSV drop, never a hard dependency."""

    source = "fedwatch_csv"

    def __init__(self, path: str | Path = MANUAL_FEDWATCH_PATH) -> None:
        self.path = Path(path)

    def get_policy_path(
        self,
        df: pd.DataFrame,
        *,
        as_of: pd.Timestamp | str | None = None,
    ) -> dict[str, Any]:
        timestamp = _as_timestamp(as_of, df)
        dot_path = fed_dot_median_path(df, as_of=timestamp)
        next_meeting = _next_fomc_meeting(timestamp)
        if not self.path.exists():
            return _base_contract(
                as_of=timestamp,
                source="fedwatch_csv_unavailable",
                next_meeting_date=next_meeting,
                fed_dot_path=dot_path,
                reason=f"FedWatch CSV absent at {self.path}; optional source skipped.",
            )

        data = pd.read_csv(self.path)
        if "meeting_date" not in data:
            return _base_contract(
                as_of=timestamp,
                source="fedwatch_csv_unavailable",
                next_meeting_date=next_meeting,
                fed_dot_path=dot_path,
                reason="FedWatch CSV missing meeting_date column; optional source skipped.",
            )
        data["meeting_date"] = pd.to_datetime(data["meeting_date"]).dt.date
        upcoming = data[data["meeting_date"] >= timestamp.date()].sort_values(
            "meeting_date"
        )
        if upcoming.empty:
            return _base_contract(
                as_of=timestamp,
                source="fedwatch_csv_unavailable",
                next_meeting_date=next_meeting,
                fed_dot_path=dot_path,
                reason="FedWatch CSV has no upcoming meeting row.",
            )

        row = upcoming.iloc[0]
        cut_prob = float(row.get("cut25_prob", 0.0)) + float(row.get("cut50_prob", 0.0))
        hold_prob = float(row.get("hold_prob", 0.0))
        hike_prob = float(row.get("hike_prob", 0.0))
        implied_rate = (
            float(row["implied_rate"])
            if "implied_rate" in row and pd.notna(row["implied_rate"])
            else None
        )
        current = _current_policy_rate(df, timestamp)
        direction = _direction(implied_rate, current)

        return {
            "as_of": timestamp.date(),
            "source": self.source,
            "next_meeting_date": row["meeting_date"],
            "next_meeting_cut_prob": round(cut_prob, 4),
            "next_meeting_hike_prob": round(hike_prob, 4),
            "next_meeting_hold_prob": round(hold_prob, 4),
            "expected_target_rate_after_meeting": (
                round(implied_rate, 4) if implied_rate is not None else None
            ),
            "implied_policy_rate_3m": (
                round(implied_rate, 4) if implied_rate is not None else None
            ),
            "implied_policy_rate_6m": (
                round(implied_rate, 4) if implied_rate is not None else None
            ),
            "implied_policy_rate_12m": (
                round(implied_rate, 4) if implied_rate is not None else None
            ),
            "fed_dot_median_path": dot_path,
            "market_vs_fed_gap_bp": _market_vs_fed_gap_bp(
                implied_rate, dot_path, timestamp
            ),
            "direction": direction,
            "confidence": "med",
            "reason": (
                "FedWatch CSV manual drop supplies next-meeting probabilities; "
                "CME scraping/futures are not a hard dependency."
            ),
        }


class AtlantaFedPolicyPathProvider:
    """Best-effort Atlanta Fed MPT object-pod provider."""

    source = "atlanta_mpt_object_pod"

    def __init__(
        self,
        url: str = ATLANTA_RESEARCH_DATA_URL,
        fetcher: Callable[[str], Any] | None = None,
    ) -> None:
        self.url = url
        self.fetcher = fetcher or self._default_fetcher

    @staticmethod
    def _default_fetcher(url: str) -> Any:
        with urlopen(url, timeout=10) as response:  # noqa: S310 - official Fed URL.
            raw = response.read().decode("utf-8")
        return json.loads(raw)

    @staticmethod
    def _probability_from_indicator(value: Any) -> float | None:
        if value is None:
            return None
        text = str(value).strip().replace("%", "")
        try:
            return round(float(text) / 100.0, 4)
        except ValueError:
            return None

    @staticmethod
    def _meeting_date_from_name(value: Any) -> Any | None:
        match = re.search(r"by\s+(\d{4}-\d{2}-\d{2})", str(value), flags=re.I)
        return pd.Timestamp(match.group(1)).date() if match else None

    def get_policy_path(
        self,
        df: pd.DataFrame,
        *,
        as_of: pd.Timestamp | str | None = None,
    ) -> dict[str, Any]:
        timestamp = _as_timestamp(as_of, df)
        dot_path = fed_dot_median_path(df, as_of=timestamp)
        next_meeting = _next_fomc_meeting(timestamp)
        try:
            payload = self.fetcher(self.url)
            if isinstance(payload, str):
                payload = json.loads(payload)
            if not payload:
                raise RuntimeError("empty Atlanta Fed payload")
            items = payload.get("ResearchData", [])
            mpt = next(
                (
                    item
                    for item in items
                    if str(item.get("IconAlias", "")).upper() == "MPT"
                ),
                None,
            )
            if not mpt:
                raise RuntimeError("MPT object not found")
        except Exception as exc:  # noqa: BLE001 - provider must degrade.
            return _base_contract(
                as_of=timestamp,
                source="atlanta_mpt_unavailable",
                next_meeting_date=next_meeting,
                fed_dot_path=dot_path,
                reason=f"Atlanta MPT feed unavailable: {exc}",
            )

        probability = self._probability_from_indicator(mpt.get("Indicator"))
        meeting_date = self._meeting_date_from_name(mpt.get("Name")) or next_meeting
        name = str(mpt.get("Name", ""))
        cut_prob = probability if "cut" in name.lower() else None
        hike_prob = probability if "hike" in name.lower() else None
        hold_prob = probability if "hold" in name.lower() else None
        return {
            "as_of": timestamp.date(),
            "source": self.source,
            "next_meeting_date": meeting_date,
            "next_meeting_cut_prob": cut_prob,
            "next_meeting_hike_prob": hike_prob,
            "next_meeting_hold_prob": hold_prob,
            "expected_target_rate_after_meeting": None,
            "implied_policy_rate_3m": None,
            "implied_policy_rate_6m": None,
            "implied_policy_rate_12m": None,
            "fed_dot_median_path": dot_path,
            "market_vs_fed_gap_bp": None,
            "direction": "HOLD",
            "confidence": "low",
            "reason": (
                "Atlanta Fed object-pod feed supplies a single MPT headline "
                "probability, not the full distribution."
            ),
        }


class OisPaidPolicyPathProvider:
    """Stub for paid OIS/Bloomberg WIRP data."""

    def get_policy_path(
        self,
        df: pd.DataFrame,
        *,
        as_of: pd.Timestamp | str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError(
            "OIS/Bloomberg WIRP requires paid data; not implemented for TraceYield."
        )


def _has_probability(contract: dict[str, Any]) -> bool:
    return any(
        contract.get(key) is not None
        for key in (
            "next_meeting_cut_prob",
            "next_meeting_hike_prob",
            "next_meeting_hold_prob",
        )
    )


def _overlay_probability_source(
    base: dict[str, Any],
    probability_source: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(base)
    for key in (
        "source",
        "next_meeting_date",
        "next_meeting_cut_prob",
        "next_meeting_hike_prob",
        "next_meeting_hold_prob",
        "expected_target_rate_after_meeting",
    ):
        if probability_source.get(key) is not None:
            merged[key] = probability_source[key]
    if probability_source.get("source"):
        merged["source"] = probability_source["source"]
    probability_direction = _direction_from_probabilities(probability_source)
    if probability_direction is not None:
        merged["direction"] = probability_direction
    elif probability_source.get("expected_target_rate_after_meeting") is not None:
        merged["direction"] = probability_source["direction"]
    merged["confidence"] = probability_source.get(
        "confidence", base.get("confidence", "low")
    )
    display_names = {
        "fedwatch_csv": "FedWatch CSV",
        "atlanta_mpt_object_pod": "Atlanta Fed MPT",
    }
    display = display_names.get(
        str(probability_source["source"]),
        str(probability_source["source"]).replace("_", " "),
    )
    merged["reason"] = (
        f"{display} probability source; FRED proxy supplies short-rate path. "
        f"{base['reason']}"
    )
    return merged


def merge_policy_paths(
    df: pd.DataFrame,
    *,
    as_of: pd.Timestamp | str | None = None,
    fedwatch_csv: str | Path = MANUAL_FEDWATCH_PATH,
    atlanta_provider: AtlantaFedPolicyPathProvider | None = None,
) -> dict[str, Any]:
    """Merge providers using FedWatch CSV > Atlanta Fed > FRED proxy precedence."""
    timestamp = _as_timestamp(as_of, df)
    fred = FredProxyPolicyPathProvider().get_policy_path(df, as_of=timestamp)
    atlanta = (atlanta_provider or AtlantaFedPolicyPathProvider()).get_policy_path(
        df,
        as_of=timestamp,
    )
    fedwatch = FedWatchCsvPolicyPathProvider(fedwatch_csv).get_policy_path(
        df,
        as_of=timestamp,
    )

    merged = dict(fred)
    if _has_probability(atlanta) and not str(atlanta["source"]).endswith("unavailable"):
        merged = _overlay_probability_source(merged, atlanta)
    if _has_probability(fedwatch) and fedwatch["source"] == "fedwatch_csv":
        merged = _overlay_probability_source(fred, fedwatch)
    return merged


def market_confirmation_row(
    df: pd.DataFrame,
    policy_path: dict[str, Any],
    *,
    as_of: pd.Timestamp | str | None = None,
) -> dict[str, Any]:
    """Return DGS2/DGS5/2s10s repricing context aligned to policy direction."""
    timestamp = _as_timestamp(as_of, df)
    dgs2 = _latest_value(df, "DGS2", timestamp)
    dgs5 = _latest_value(df, "DGS5", timestamp)
    dgs10 = _latest_value(df, "DGS10", timestamp)
    spread = dgs10 - dgs2 if dgs10 is not None and dgs2 is not None else None
    direction = policy_path.get("direction", "HOLD")
    front_end = dgs2
    current = _current_policy_rate(df, timestamp)
    agrees = None
    if front_end is not None and current is not None:
        front_gap_bp = (front_end - current) * 100.0
        agrees = (
            direction == "TIGHTENING"
            and front_gap_bp > DIRECTION_THRESHOLD_BP
            or direction == "EASING"
            and front_gap_bp < -DIRECTION_THRESHOLD_BP
            or direction == "HOLD"
            and abs(front_gap_bp) <= DIRECTION_THRESHOLD_BP
        )
    return {
        "as_of": timestamp.date(),
        "DGS2": dgs2,
        "DGS5": dgs5,
        "2s10s": spread,
        "direction": direction,
        "agrees": agrees,
        "reason": "DGS2/DGS5/2s10s context for market policy-path repricing.",
    }


def provider_outputs(
    df: pd.DataFrame,
    *,
    as_of: pd.Timestamp | str | None = None,
    fedwatch_csv: str | Path = MANUAL_FEDWATCH_PATH,
) -> dict[str, dict[str, Any]]:
    """Return each free/pluggable provider output plus the merged contract."""
    timestamp = _as_timestamp(as_of, df)
    atlanta = AtlantaFedPolicyPathProvider().get_policy_path(df, as_of=timestamp)
    return {
        "fred_proxy": FredProxyPolicyPathProvider().get_policy_path(
            df, as_of=timestamp
        ),
        "atlanta": atlanta,
        "fedwatch_csv": FedWatchCsvPolicyPathProvider(fedwatch_csv).get_policy_path(
            df,
            as_of=timestamp,
        ),
        "merged": merge_policy_paths(df, as_of=timestamp, fedwatch_csv=fedwatch_csv),
    }


def _json_default(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _latest_processed_fred_cache() -> Path:
    cached = sorted((DATA / "processed").glob("fred_*.parquet"))
    if not cached:
        raise FileNotFoundError(
            "No processed FRED cache found. Run scripts/daily_run.py first."
        )
    return cached[-1]


def main() -> None:
    path = _latest_processed_fred_cache()
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)
    outputs = provider_outputs(df)
    merged = outputs["merged"]
    outputs["market_confirmation"] = market_confirmation_row(
        df,
        merged,
        as_of=merged["as_of"],
    )
    print(json.dumps(outputs, indent=2, default=_json_default))


if __name__ == "__main__":
    main()
