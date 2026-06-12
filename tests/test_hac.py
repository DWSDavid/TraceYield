import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.backtest.hac import build_phase1b_hac_scorecard, fit_hac_regression


def test_fit_hac_regression_reports_newey_west_and_hansen_hodrick():
    dates = pd.date_range("2025-01-01", periods=160, freq="D")
    x = pd.Series(np.linspace(-1.0, 1.0, len(dates)), index=dates, name="factor")
    y = 0.02 + 1.50 * x
    y = y + pd.Series(np.sin(np.arange(len(dates)) / 4.0) * 0.05, index=dates)

    nw = fit_hac_regression(y, x.to_frame(), lag=10, kernel="bartlett")
    hh = fit_hac_regression(y, x.to_frame(), lag=10, kernel="rectangular")

    assert nw.n == len(dates)
    assert nw.params["factor"] == pytest_approx(1.50, abs=0.03)
    assert nw.t_stats["factor"] > 20
    assert nw.p_values["factor"] < 0.001
    assert nw.r2 > 0.95
    assert nw.covariance_psd
    assert "factor" in hh.t_stats
    assert isinstance(hh.covariance_psd, bool)


def test_phase1b_hac_scorecard_keeps_only_significant_benchmark_beaters():
    dates = pd.date_range("2025-01-01", periods=220, freq="D")
    realized = pd.DataFrame(
        {
            "2Y": np.linspace(-0.4, 0.4, len(dates)),
            "5Y": np.linspace(-0.2, 0.2, len(dates)),
            "10Y": np.linspace(-0.1, 0.1, len(dates)),
            "30Y": np.linspace(-0.05, 0.05, len(dates)),
            "2s10s": np.linspace(-0.4, 0.4, len(dates)),
            "5s30s": np.linspace(-0.1, 0.1, len(dates)),
        },
        index=dates,
    )
    predictions = {
        "policy_path": pd.DataFrame(
            {
                "2Y": realized["2Y"] * 0.1,
                "5Y": realized["5Y"] * 0.1,
                "10Y": realized["10Y"] * 0.1,
                "30Y": realized["30Y"] * 0.1,
                "2s10s": realized["2s10s"],
                "5s30s": realized["5s30s"] * 0.1,
            },
            index=dates,
        ),
    }
    phase0 = pd.DataFrame(
        [
            {"model": model, "horizon": horizon, "target": target, "rank_ic": rank_ic}
            for model, rank_ic in (("random_walk", -0.10), ("momentum_3m", 0.10))
            for horizon in ("3m", "6m")
            for target in ("2Y", "5Y", "10Y", "30Y", "2s10s", "5s30s")
        ]
    )

    scorecard = build_phase1b_hac_scorecard(
        predictions,
        {"3m": realized, "6m": realized},
        phase0_scorecard=phase0,
        start="2025-01-01",
        hac_lags={"3m": 10, "6m": 20},
    )

    decision = scorecard[
        scorecard["row_type"].eq("factor")
        & scorecard["factor"].eq("policy_path")
        & scorecard["target"].eq("2s10s")
    ]
    assert set(decision["benchmark_model"]) == {"max_random_walk_momentum"}
    assert (decision["rank_ic"] > decision["benchmark_rank_ic"]).all()
    assert (decision["nw_abs_t_stat"] >= 2.0).all()
    assert set(decision["hac_pass"]) == {True}
    assert scorecard["decision_tag"].dropna().unique().tolist() == ["keep"]


def pytest_approx(*args, **kwargs):
    import pytest

    return pytest.approx(*args, **kwargs)
