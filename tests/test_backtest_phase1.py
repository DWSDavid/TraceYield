import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.backtest import walk_forward
from src.signals.factors import political_risk_proxy


def test_political_risk_proxy_uses_vix_as_safe_haven_yield_pressure():
    dates = pd.date_range("2026-01-01", periods=30, freq="D")
    df = pd.DataFrame({"VIXCLS": list(range(10, 40))}, index=dates)

    assert political_risk_proxy(df) < 0


def test_daily_factors_wires_fomc_asof_and_political_proxy(monkeypatch):
    dates = pd.date_range("2026-01-01", periods=30, freq="D")
    df = pd.DataFrame(
        {
            "DGS10": [4.0 + i * 0.01 for i in range(30)],
            "VIXCLS": list(range(10, 40)),
        },
        index=dates,
    )
    monkeypatch.setattr(walk_forward, "fomc_factor_asof", lambda d: 0.7)

    out = walk_forward._daily_factors(df, start="2026-01-25")

    assert (out["fomc_nlp"] == 0.7).all()
    assert out["political_risk"].abs().max() > 0


def test_lagged_history_uses_column_specific_publication_lags():
    dates = pd.date_range("2026-01-01", periods=80, freq="D")
    df = pd.DataFrame(
        {
            "DGS10": range(80),
            "PCEPILFE": range(1000, 1080),
            "WALCL": range(2000, 2080),
        },
        index=dates,
    )
    asof = pd.Timestamp("2026-03-15")

    hist = walk_forward._lagged_history(
        df,
        asof,
        {"DGS10": 1, "PCEPILFE": 35, "WALCL": 7},
    )

    assert hist["DGS10"].dropna().index.max() == asof - timedelta(days=1)
    assert hist["PCEPILFE"].dropna().index.max() == asof - timedelta(days=35)
    assert hist["WALCL"].dropna().index.max() == asof - timedelta(days=7)


def test_daily_factors_applies_publication_lag_before_factor_scoring(monkeypatch):
    dates = pd.date_range("2026-01-01", periods=74, freq="D")
    df = pd.DataFrame(
        {
            "DGS10": range(len(dates)),
            "PCEPILFE": range(1000, 1000 + len(dates)),
            "VIXCLS": range(10, 10 + len(dates)),
        },
        index=dates,
    )
    seen = {}

    def fake_compute_all(hist, hawkish=0.0, political=0.0):
        seen["max_pce_date"] = hist["PCEPILFE"].dropna().index.max()
        seen["max_dgs10_date"] = hist["DGS10"].dropna().index.max()
        return {
            "fomc_nlp": hawkish,
            "inflation": 0.0,
            "liquidity": 0.0,
            "global_rates": 0.0,
            "political_risk": political,
        }

    monkeypatch.setattr(walk_forward, "compute_all", fake_compute_all)
    monkeypatch.setattr(walk_forward, "fomc_factor_asof", lambda d: 0.0)
    monkeypatch.setattr(
        walk_forward,
        "fred_release_lags",
        lambda: {"DGS10": 1, "PCEPILFE": 35, "VIXCLS": 1},
    )

    walk_forward._daily_factors(df, start="2026-03-15")

    assert seen["max_pce_date"] == pd.Timestamp("2026-02-08")
    assert seen["max_dgs10_date"] == pd.Timestamp("2026-03-14")
