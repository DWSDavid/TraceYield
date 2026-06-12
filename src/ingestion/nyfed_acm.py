"""NY Fed ACM Treasury term-premium ingestion.

Official source:
https://www.newyorkfed.org/medialibrary/media/research/data_indicators/ACMTermPremium.xls

The NY Fed file is public and requires no API key. We cache the raw xls under
data/cache/nyfed/ and a normalized parquet under data/processed/.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

import pandas as pd

from src.utils.config import DATA

ACM_URL = (
    "https://www.newyorkfed.org/medialibrary/media/research/data_indicators/"
    "ACMTermPremium.xls"
)
CACHE_DIR = DATA / "cache" / "nyfed"
RAW_PATH = CACHE_DIR / "ACMTermPremium.xls"
PROCESSED_PATH = DATA / "processed" / "nyfed_acm_term_premium.parquet"
_ACM_COL_RE = re.compile(r"^(ACMTP|ACMY|ACMRNY)0?(\d+)$")


def _acm_column_sort_key(col: str) -> tuple[str, int]:
    match = _ACM_COL_RE.match(col)
    if not match:
        return (col, 999)
    return (match.group(1), int(match.group(2)))


def normalize_acm_table(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize an ACM table to a date index with numeric ACM columns."""
    df = raw.copy()
    df.columns = [str(col).strip().upper() for col in df.columns]
    date_col = next((col for col in df.columns if col in {"DATE", "OBS_DATE"}), None)
    if date_col is None:
        raise ValueError("NY Fed ACM table has no DATE column")

    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col])
    acm_cols = sorted(
        [
            col
            for col in df.columns
            if col.startswith(("ACMTP", "ACMY", "ACMRNY")) and col != date_col
        ],
        key=_acm_column_sort_key,
    )
    if "ACMTP10" not in acm_cols:
        raise ValueError("NY Fed ACM table has no ACMTP10 column")

    out = df[[date_col, *acm_cols]].copy()
    for col in acm_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.set_index(date_col).sort_index()
    out.index.name = "date"
    return out


def fetch_raw(path: Path = RAW_PATH, url: str = ACM_URL) -> Path:
    """Download the official NY Fed ACM xls file to the raw cache."""
    import requests

    path.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    path.write_bytes(response.content)
    return path


def _read_xls(path: Path, sheet_name: str = "ACM Daily") -> pd.DataFrame:
    try:
        return pd.read_excel(path, sheet_name=sheet_name)
    except ImportError as exc:  # pragma: no cover - environment setup issue
        raise RuntimeError(
            "Reading NY Fed ACM .xls requires xlrd. Install dependencies with "
            "`pip install -r requirements.txt`."
        ) from exc


def build_processed(
    raw_path: Path = RAW_PATH,
    processed_path: Path = PROCESSED_PATH,
    sheet_name: str = "ACM Daily",
) -> pd.DataFrame:
    """Parse raw ACM xls and save normalized parquet/csv caches."""
    df = normalize_acm_table(_read_xls(raw_path, sheet_name=sheet_name))
    processed_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(processed_path)
    df.to_csv(processed_path.with_suffix(".csv"))
    load_term_premium.cache_clear()
    _default_term_premium_change_zscores.cache_clear()
    return df


@lru_cache(maxsize=1)
def load_term_premium(fetch_if_missing: bool = False) -> pd.DataFrame:
    """Load normalized ACM term premium data, optionally fetching if missing."""
    if PROCESSED_PATH.exists():
        df = pd.read_parquet(PROCESSED_PATH)
        df.index = pd.to_datetime(df.index)
        return df.sort_index()

    if not RAW_PATH.exists():
        if not fetch_if_missing:
            return pd.DataFrame()
        fetch_raw()

    try:
        return build_processed()
    except (RuntimeError, ValueError, OSError):
        return pd.DataFrame()


def term_premium_asof(
    d: pd.Timestamp | str,
    column: str = "ACMTP10",
    df: pd.DataFrame | None = None,
) -> float | None:
    """Return the latest ACM term premium known on or before d."""
    data = load_term_premium(fetch_if_missing=False) if df is None else df.copy()
    if data.empty or column not in data:
        return None
    data.index = pd.to_datetime(data.index)
    known = data.sort_index().loc[: pd.Timestamp(d)]
    if known.empty:
        return None
    value = known[column].dropna()
    if value.empty:
        return None
    return float(value.iloc[-1])


def term_premium_change_asof(
    d: pd.Timestamp | str,
    column: str = "ACMTP10",
    periods: int = 63,
    df: pd.DataFrame | None = None,
) -> float | None:
    """Return the trailing change in ACM term premium known on or before d."""
    data = load_term_premium(fetch_if_missing=False) if df is None else df.copy()
    if data.empty or column not in data:
        return None
    data.index = pd.to_datetime(data.index)
    known = data.sort_index().loc[: pd.Timestamp(d)][column].dropna()
    if len(known) <= periods:
        return None
    return float(known.iloc[-1] - known.iloc[-periods - 1])


def term_premium_change_zscore_asof(
    d: pd.Timestamp | str,
    column: str = "ACMTP10",
    periods: int = 63,
    window: int = 756,
    df: pd.DataFrame | None = None,
) -> tuple[float, dict[str, float]] | None:
    """Return trailing ACM change normalized by its rolling change volatility."""
    if df is None:
        scores = _default_term_premium_change_zscores(column, periods, window)
        known_scores = scores.loc[: pd.Timestamp(d)].dropna(subset=["score"])
        if known_scores.empty:
            return None
        latest = known_scores.iloc[-1]
        return (
            float(latest["score"]),
            {
                "acm_10y_term_premium_change": round(float(latest["change"]), 4),
                "acm_10y_change_rolling_std": round(float(latest["rolling_std"]), 4),
            },
        )

    data = df.copy()
    if data.empty or column not in data:
        return None
    data.index = pd.to_datetime(data.index)
    known = data.sort_index().loc[: pd.Timestamp(d)][column].dropna()
    if len(known) <= periods + 20:
        return None

    changes = known.diff(periods).dropna()
    if changes.empty:
        return None
    rolling_std = changes.tail(window).std()
    if pd.isna(rolling_std) or rolling_std == 0:
        return None

    change = float(changes.iloc[-1])
    score = max(-1.0, min(1.0, change / float(rolling_std)))
    return (
        float(score),
        {
            "acm_10y_term_premium_change": round(change, 4),
            "acm_10y_change_rolling_std": round(float(rolling_std), 4),
        },
    )


def _term_premium_change_zscore_frame(
    data: pd.DataFrame,
    column: str,
    periods: int,
    window: int,
) -> pd.DataFrame:
    if data.empty or column not in data:
        return pd.DataFrame(columns=["change", "rolling_std", "score"])
    known = data.sort_index()[column].dropna()
    changes = known.diff(periods)
    rolling_std = changes.rolling(window=window, min_periods=20).std()
    score = (changes / rolling_std).clip(-1.0, 1.0)
    return pd.DataFrame(
        {
            "change": changes,
            "rolling_std": rolling_std,
            "score": score,
        }
    )


@lru_cache(maxsize=8)
def _default_term_premium_change_zscores(
    column: str,
    periods: int,
    window: int,
) -> pd.DataFrame:
    return _term_premium_change_zscore_frame(
        load_term_premium(fetch_if_missing=False),
        column,
        periods,
        window,
    )


def main() -> None:
    path = fetch_raw()
    df = build_processed(path)
    print(
        f"[nyfed_acm] wrote {len(df)} rows to {PROCESSED_PATH} "
        f"({df.index.min().date()} -> {df.index.max().date()})"
    )


if __name__ == "__main__":
    main()
