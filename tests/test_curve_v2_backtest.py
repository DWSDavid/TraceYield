import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.backtest.curve_v2 import run_backtest


def _history() -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=230, freq="D")
    return pd.DataFrame(
        {
            "DGS2": [3.0 + i * 0.002 for i in range(len(dates))],
            "DGS5": [3.2 + i * 0.003 for i in range(len(dates))],
            "DGS10": [3.5 + i * 0.004 for i in range(len(dates))],
            "DGS30": [3.8 + i * 0.005 for i in range(len(dates))],
            "T10Y2Y": [0.5 + i * 0.002 for i in range(len(dates))],
            "PCEPILFE": [120 + i * 0.01 for i in range(len(dates))],
            "CPIAUCSL": [300 + i * 0.01 for i in range(len(dates))],
            "T10YIE": [2.0 + i * 0.0005 for i in range(len(dates))],
            "T5YIE": [2.0 + i * 0.0005 for i in range(len(dates))],
            "T5YIFR": [2.2 + i * 0.0002 for i in range(len(dates))],
            "WALCL": [7000000 - i * 100 for i in range(len(dates))],
            "WRESBAL": [3200000 - i * 50 for i in range(len(dates))],
            "VIXCLS": [15.0 for _ in dates],
            "IRLTLT01DEM156N": [2.5 for _ in dates],
        },
        index=dates,
    )


def test_run_backtest_outputs_rows_summary_and_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.backtest.curve_v2.fred_release_lags",
        lambda: {col: 0 for col in _history().columns},
    )
    out_csv = tmp_path / "curve_v2_backtest.csv"

    rows, summary = run_backtest(
        _history(),
        start="2025-03-01",
        output_path=out_csv,
    )

    assert not rows.empty
    assert out_csv.exists()
    assert set(rows["horizon"]) == {"3m_core", "6m_core"}
    assert {"pressure_2Y", "realized_2Y", "curve_shape_hit"}.issubset(rows.columns)
    assert "3m_core" in summary
    assert "tenor_directional_accuracy" in summary["3m_core"]
    assert "ic_by_tenor" in summary["3m_core"]
    assert "confidence_thresholds" in summary["3m_core"]
