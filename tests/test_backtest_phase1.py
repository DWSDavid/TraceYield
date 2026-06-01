import sys
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
