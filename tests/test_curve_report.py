import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.curve_engine import CurveForecast
from src.report.render_curve import to_markdown


def test_curve_report_contains_v2_sections():
    forecasts = [
        CurveForecast(
            horizon="3m_core",
            curve_call="BEAR_STEEPENING",
            tenor_pressure={"2Y": 0.2, "5Y": 0.25, "10Y": 0.35, "30Y": 0.22},
            factor_scores={"policy_path": 0.7, "term_premium": 0.7},
            contributions={"policy_path": 0.2},
            context_contributions={"term_premium": -0.1, "liquidity_supply": 0.03},
            context_tenor_pressure={"2Y": 0.0, "5Y": -0.03, "10Y": -0.10, "30Y": -0.12},
            ten_year_reconstruction={
                "front_end_2y": 0.2,
                "curve_2s10s": 0.15,
                "reconstructed_10y": 0.35,
                "context_term_premium_residual": -0.10,
            },
            main_driver="policy_path",
            secondary_driver="front_end_momentum",
            confidence=0.68,
            rationale="Front-end policy pressure dominates.",
            triggers=["10Y close above recent range"],
            linkage_note="JGB and CGB read-through is light.",
            asof=pd.Timestamp("2026-06-01"),
        )
    ]

    md = to_markdown(forecasts, run_date=pd.Timestamp("2026-06-01"))

    assert "UST Curve Impact Forecast" in md
    assert "Headline 10Y Direction" in md
    assert "10Y view is reconstructed" in md
    assert "Front-end 2Y" in md
    assert "2s10s curve" in md
    assert "Context-only long end" in md
    assert "30Y" in md
    assert "Core View" in md
    assert "Tenor Pressure" in md
    assert "Driver Attribution" in md
    assert "Key Triggers" in md
    assert "Light Cross-Market Linkage" in md
