import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingestion import fred_client


def test_fetch_all_falls_back_to_cache_when_fredapi_is_unavailable(
    tmp_path, monkeypatch
):
    cache = tmp_path / "cache" / "fred"
    cache.mkdir(parents=True)
    cached = pd.Series(
        [4.0, 4.1],
        index=pd.to_datetime(["2026-01-01", "2026-01-02"]),
        name="DGS10",
    )
    cached.to_frame().to_parquet(cache / "DGS10.parquet")

    monkeypatch.setitem(sys.modules, "fredapi", None)
    monkeypatch.setattr(fred_client, "CACHE", cache)
    monkeypatch.setattr(fred_client, "DATA", tmp_path)
    monkeypatch.setattr(
        fred_client,
        "fred_series",
        lambda: {"treasury_yields": {"DGS10": {"description": "10Y"}}},
    )

    out = fred_client.fetch_all()

    assert list(out.columns) == ["DGS10"]
    assert out["DGS10"].iloc[-1] == 4.1
    assert list((tmp_path / "processed").glob("fred_*.parquet"))
