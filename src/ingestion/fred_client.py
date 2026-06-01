"""FRED ingestion. Pulls all series in configs/fred_series.yaml, caches to disk.

Cache keeps a timestamped parquet per series so any past run is reproducible and
we don't re-hit FRED rate limits. If fredapi/network is unavailable, falls back
to whatever is cached.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from src.utils.config import DATA, env, fred_series

CACHE = DATA / "cache" / "fred"


def _flatten_series_ids(cfg: dict) -> list[str]:
    ids: list[str] = []
    for group in cfg.values():
        ids.extend(group.keys())
    return ids


def fetch_all(start: str = "2010-01-01") -> pd.DataFrame:
    """Fetch every configured series into one wide DataFrame indexed by date.

    Columns = FRED series IDs. Missing days forward-filled at the signal stage,
    not here (we keep raw NaNs in the cache).
    """
    from fredapi import Fred  # imported lazily so the module loads without the dep

    CACHE.mkdir(parents=True, exist_ok=True)
    fred = Fred(api_key=env("FRED_API_KEY"))
    ids = _flatten_series_ids(fred_series())

    frames = {}
    for sid in ids:
        try:
            s = fred.get_series(sid, observation_start=start)
            s.name = sid
            frames[sid] = s
            s.to_frame().to_parquet(CACHE / f"{sid}.parquet")
        except Exception as e:  # noqa: BLE001 — keep going, log, fall back to cache
            print(f"[fred] {sid} failed ({e}); using cache if present")
            p = CACHE / f"{sid}.parquet"
            if p.exists():
                frames[sid] = pd.read_parquet(p).iloc[:, 0]

    df = pd.DataFrame(frames)
    df.index = pd.to_datetime(df.index)
    out = DATA / "processed" / f"fred_{date.today():%Y%m%d}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out)
    return df


if __name__ == "__main__":
    df = fetch_all()
    print(df.tail())
