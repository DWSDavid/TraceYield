import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.signals.grounded_macro_analysis import (
    attach_grounded_macro_analysis,
    build_grounded_macro_context,
    grounded_macro_analysis,
)


def _write_doc(root: Path, kind: str, name: str, text: str) -> None:
    folder = root / kind
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text, encoding="utf-8")


def _df() -> pd.DataFrame:
    idx = pd.date_range("2026-04-01", periods=40, freq="D")
    return pd.DataFrame(
        {
            "CPIAUCSL": [320.0 + i * 0.1 for i in range(len(idx))],
            "CPILFESL": [325.0 + i * 0.08 for i in range(len(idx))],
            "PCEPI": [130.0 + i * 0.03 for i in range(len(idx))],
            "PCEPILFE": [128.0 + i * 0.02 for i in range(len(idx))],
            "PAYEMS": [160000 + i for i in range(len(idx))],
            "UNRATE": [4.0 for _ in idx],
            "ICSA": [230000 - i * 10 for i in range(len(idx))],
            "DGS2": [3.9 for _ in idx],
            "DGS10": [4.4 for _ in idx],
            "WALCL": [7000000 - i * 1000 for i in range(len(idx))],
            "WTREGEN": [800000 + i * 100 for i in range(len(idx))],
        },
        index=idx,
    )


def _trajectory() -> dict:
    return {
        "as_of": "2026-05-10",
        "tenors": {
            "10Y": [
                {"month": month, "current": 4.4, "central": 4.3, "p10": 3.8, "p90": 4.9}
                for month in range(1, 13)
            ],
            "2Y": [
                {"month": month, "current": 3.9, "central": 3.8, "p10": 3.1, "p90": 4.4}
                for month in range(1, 13)
            ],
            "2s10s": [
                {
                    "month": month,
                    "current": 0.5,
                    "central": 0.5,
                    "p10": -0.2,
                    "p90": 1.0,
                }
                for month in range(1, 13)
            ],
        },
        "metadata": {
            "policy_path": {
                "direction": "HOLD",
                "confidence": "low",
                "market_vs_fed_gap_bp": 47.0,
                "reason": "FRED proxy says hold.",
            },
            "polymarket_check": {
                "traceyield_alignment": "agree",
                "alignment_reason": "Polymarket agrees with lower 10Y lean.",
            },
        },
    }


def test_grounded_macro_context_reads_latest_raw_fomc_docs(tmp_path):
    raw = tmp_path / "fomc"
    _write_doc(
        raw,
        "statement",
        "2026-04-29.txt",
        "Inflation is elevated. The Committee is strongly committed to returning inflation to 2 percent.",
    )
    _write_doc(
        raw,
        "minutes",
        "2026-04-29.txt",
        "Participants judged that uncertainty remained high. Labor market conditions were balanced.",
    )

    context = build_grounded_macro_context(
        _df(),
        _trajectory(),
        as_of="2026-05-10",
        raw_fomc_dir=raw,
    )

    assert context["as_of"] == "2026-05-10"
    assert context["fomc_documents"]["statement"]["date"] == "2026-04-29"
    assert "Inflation is elevated" in context["fomc_documents"]["statement"]["text"]
    assert context["macro_snapshot"]["inflation"]["CPIAUCSL"]["latest"] is not None
    assert context["curve_view"]["10Y"]["month_12_central"] == 4.3


def test_grounded_macro_context_uses_calendar_changes_for_monthly_data(tmp_path):
    raw = tmp_path / "fomc"
    _write_doc(raw, "statement", "2026-04-29.txt", "Inflation is elevated.")
    _write_doc(
        raw, "minutes", "2026-04-29.txt", "Labor market conditions were balanced."
    )
    idx = pd.date_range("2025-01-01", periods=16, freq="MS")
    df = pd.DataFrame(
        {
            "CPIAUCSL": [300.0 + i for i in range(len(idx))],
            "T10YIE": [2.0 + i * 0.01 for i in range(len(idx))],
        },
        index=idx,
    )

    context = build_grounded_macro_context(
        df,
        _trajectory(),
        as_of="2026-04-15",
        raw_fomc_dir=raw,
    )
    cpi = context["macro_snapshot"]["inflation"]["CPIAUCSL"]
    breakeven = context["macro_snapshot"]["inflation"]["T10YIE"]

    assert cpi["change_3m_pct"] == round((315.0 / 312.0 - 1.0) * 100.0, 3)
    assert cpi["yoy_pct"] == round((315.0 / 303.0 - 1.0) * 100.0, 3)
    assert breakeven["change_3m_bp"] == 3.0
    assert breakeven["change_3m_pct"] is None


def test_grounded_macro_analysis_uses_cache_and_attaches_without_changing_curve(
    tmp_path,
):
    raw = tmp_path / "fomc"
    _write_doc(
        raw,
        "statement",
        "2026-04-29.txt",
        "Inflation is elevated. The Committee is strongly committed to returning inflation to 2 percent.",
    )
    _write_doc(
        raw,
        "minutes",
        "2026-04-29.txt",
        "Participants judged that uncertainty remained high. Labor market conditions were balanced.",
    )
    cache = tmp_path / "analysis.json"
    scorer_calls = []

    def scorer(prompt: str) -> dict:
        scorer_calls.append(prompt)
        return {
            "executive_summary": "Inflation pressure and cautious Fed language keep the curve biased higher than base.",
            "factor_notes": {
                "inflation_regime": {
                    "stance": "hot",
                    "reason": "Inflation remains elevated, so investors demand more compensation.",
                    "data_points": ["CPI available"],
                    "quotes": ["Inflation is elevated."],
                }
            },
            "logic_chain": [
                "Inflation hot -> Fed cautious -> yields need compensation."
            ],
            "key_quotes": [
                {
                    "source": "statement 2026-04-29",
                    "quote": "Inflation is elevated.",
                }
            ],
        }

    analysis = grounded_macro_analysis(
        _df(),
        _trajectory(),
        as_of="2026-05-10",
        raw_fomc_dir=raw,
        cache_path=cache,
        scorer=scorer,
    )
    second = grounded_macro_analysis(
        _df(),
        _trajectory(),
        as_of="2026-05-10",
        raw_fomc_dir=raw,
        cache_path=cache,
        scorer=lambda _prompt: (_ for _ in ()).throw(AssertionError("cache miss")),
    )
    before = json.dumps(_trajectory()["tenors"], sort_keys=True)
    attached = attach_grounded_macro_analysis(
        _df(),
        _trajectory(),
        as_of="2026-05-10",
        raw_fomc_dir=raw,
        cache_path=tmp_path / "attached.json",
        scorer=scorer,
    )

    assert len(scorer_calls) >= 1
    assert analysis["source"] == "grounded_gpt"
    assert second["executive_summary"] == analysis["executive_summary"]
    assert json.dumps(attached["tenors"], sort_keys=True) == before
    assert attached["metadata"]["grounded_macro_analysis"]["model_usage"] == (
        "narrative_and_regime_only_no_bp_or_central_shift"
    )
