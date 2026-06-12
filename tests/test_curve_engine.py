import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.curve_engine import forecast_curve


def _sample_curve_df() -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=300, freq="D")
    return pd.DataFrame(
        {
            "DGS2": [4.2 + i * 0.001 for i in range(300)],
            "DGS5": [4.0 + i * 0.002 for i in range(300)],
            "DGS10": [4.1 + i * 0.003 for i in range(300)],
            "DGS30": [4.3 + i * 0.004 for i in range(300)],
            "T10Y2Y": [-0.1 + i * 0.001 for i in range(300)],
            "PCEPILFE": [120 + i * 0.02 for i in range(300)],
            "CPIAUCSL": [300 + i * 0.03 for i in range(300)],
            "T10YIE": [2.1 + i * 0.001 for i in range(300)],
            "T5YIE": [2.0 + i * 0.001 for i in range(300)],
            "T5YIFR": [2.2 + i * 0.0005 for i in range(300)],
            "WALCL": [7000000 - i * 1000 for i in range(300)],
            "WRESBAL": [3200000 - i * 500 for i in range(300)],
            "RRPONTSYD": [500000 - i * 100 for i in range(300)],
            "WTREGEN": [800000 + i * 200 for i in range(300)],
            "DFEDTARU": [5.5 for _ in range(300)],
            "EFFR": [5.33 for _ in range(300)],
            "SOFR": [5.31 for _ in range(300)],
            "IRLTLT01DEM156N": [2.5 + i * 0.001 for i in range(300)],
            "IRLTLT01JPM156N": [1.0 + i * 0.0005 for i in range(300)],
            "VIXCLS": [15 + (i % 20) * 0.1 for i in range(300)],
            "DTWEXBGS": [120 + i * 0.01 for i in range(300)],
        },
        index=dates,
    )


def test_forecast_curve_emits_v2_stages_and_tenor_pressure():
    forecasts = forecast_curve(_sample_curve_df(), hawkish=0.0)

    assert [f.horizon for f in forecasts] == [
        "1m_tactical",
        "3m_core",
        "6m_core",
        "12m_structural",
    ]
    for forecast in forecasts:
        assert set(forecast.tenor_pressure) == {"2Y", "5Y", "10Y", "30Y"}
        assert "policy_path" in forecast.factor_scores
        assert "term_premium" in forecast.context_contributions
        assert forecast.main_driver
        assert forecast.triggers


def test_forecast_curve_reconstructs_10y_and_demotes_long_end_context():
    forecasts = forecast_curve(_sample_curve_df(), hawkish=1.0)
    core = next(f for f in forecasts if f.horizon == "3m_core")

    assert "term_premium" not in core.contributions
    assert "liquidity_supply" not in core.contributions
    assert "global_relative_value" not in core.contributions
    assert {"term_premium", "liquidity_supply", "global_relative_value"}.issubset(
        core.context_contributions
    )

    view = core.ten_year_reconstruction
    assert set(view) == {
        "front_end_2y",
        "curve_2s10s",
        "reconstructed_10y",
        "context_term_premium_residual",
    }
    assert view["reconstructed_10y"] == pytest.approx(
        view["front_end_2y"] + view["curve_2s10s"]
    )
    assert view["reconstructed_10y"] == pytest.approx(core.tenor_pressure["10Y"])
    assert core.context_tenor_pressure["30Y"] != core.tenor_pressure["30Y"]
