import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.report.render_html import render_report_html, save_html_report


def _point(month: int, central: float, p50: float) -> dict:
    return {
        "month": month,
        "horizon_days": 21 * month,
        "current": 4.0,
        "central": central,
        "delta_bp": round((central - 4.0) * 100.0, 6),
        "p10": central - 0.30,
        "p25": central - 0.15,
        "p50": p50,
        "p75": central + 0.15,
        "p90": central + 0.30,
        "uncertainty_widen_bp": 18.0 if month == 1 else 0.0,
        "overlay_reasons": ["Jun 2026 contains FOMC; fan widened."],
    }


def _trajectory() -> dict:
    points = [
        _point(month, 4.0 + month / 100.0, 4.1 + month / 100.0)
        for month in range(1, 13)
    ]
    return {
        "as_of": "2026-05-29",
        "tenors": {
            "2Y": [point.copy() for point in points],
            "5Y": [point.copy() for point in points],
            "10Y": [point.copy() for point in points],
            "30Y": [point.copy() for point in points],
            "2s10s": [point.copy() for point in points],
            "5s30s": [point.copy() for point in points],
        },
        "metadata": {
            "policy_path": {
                "source": "fred_proxy",
                "direction": "HOLD",
                "confidence": "low",
                "implied_policy_rate_3m": 3.81,
                "implied_policy_rate_6m": 3.87,
                "implied_policy_rate_12m": 3.99,
                "fed_dot_median_path": {"2026": 3.4, "longer_run": 3.0},
                "market_vs_fed_gap_bp": 47.0,
                "reason": "FRED proxy path; bill-vs-funds basis caveat.",
            },
            "event_overlays": [
                {
                    "type": "FOMC",
                    "month": 1,
                    "event_date": "2026-06-17",
                    "step_bp": 0.0,
                    "reason": "No high-conviction next-meeting probability.",
                },
                {
                    "type": "UNCERTAINTY",
                    "month": 1,
                    "events": [
                        {
                            "event_type": "fomc",
                            "release_date": "2026-06-17",
                            "precision": "confirmed",
                            "has_sep": True,
                        },
                        {
                            "event_type": "cpi",
                            "release_date": "2026-06-10",
                            "precision": "estimated",
                        },
                    ],
                    "widen_bp": {"2Y": 18.0, "10Y": 12.0, "2s10s": 21.633308},
                    "reason": "Jun 2026 contains CPI (date estimated) + FOMC.",
                },
            ],
            "event_uncertainty": {
                "month_events": {
                    "1": [
                        {
                            "event_type": "fomc",
                            "release_date": "2026-06-17",
                            "precision": "confirmed",
                            "has_sep": True,
                        },
                        {
                            "event_type": "cpi",
                            "release_date": "2026-06-10",
                            "precision": "estimated",
                        },
                    ]
                }
            },
            "baselines": {
                "10Y": {
                    "random_walk": {"level": 4.0, "reason": "Hold current 10Y flat."},
                    "market_range": {
                        "low": 3.9,
                        "high": 4.8,
                        "source": "manual_market_observed",
                        "reason": "Observed market range.",
                    },
                }
            },
            "polymarket_check": {
                "as_of": "2026-05-29",
                "source": "polymarket_gamma",
                "status": "available",
                "query_terms": ["10Y Treasury", "Treasury yield"],
                "markets": [
                    {
                        "id": "m39",
                        "slug": "will-the-10-year-treasury-yield-dip-below-3pt9-before-2027",
                        "question": "Will the 10-year Treasury yield dip below 3.9% before 2027?",
                        "description": "Resolves Yes if the 10-year yield dips below 3.9%.",
                        "end_date": "2026-12-31T00:00:00Z",
                        "active": True,
                        "closed": False,
                        "outcomes": ["Yes", "No"],
                        "outcome_prices": [0.475, 0.525],
                        "yes_price": 0.475,
                        "no_price": 0.525,
                        "volume": 40796.0,
                        "liquidity": 7208.0,
                        "spread": 0.01,
                        "last_trade_price": 0.47,
                        "best_bid": 0.47,
                        "best_ask": 0.48,
                        "resolution_note": "Treasury source threshold market.",
                        "relevance_score": 0.95,
                        "confidence": "med",
                        "risk_flags": [],
                    },
                ],
                "traceyield_alignment": "agree",
                "alignment_reason": "Polymarket lower-threshold pricing agrees with TraceYield lower 10Y lean; external check only.",
                "model_usage": "external_check_only_no_central_shift",
            },
            "grounded_macro_analysis": {
                "available": True,
                "source": "grounded_gpt",
                "model_usage": "narrative_and_regime_only_no_bp_or_central_shift",
                "documents_used": [
                    {
                        "kind": "statement",
                        "date": "2026-04-29",
                        "char_count": 2246,
                    },
                    {
                        "kind": "minutes",
                        "date": "2026-04-29",
                        "char_count": 46257,
                    },
                ],
                "executive_summary": "Inflation pressure plus cautious Fed language keeps the curve biased above the no-macro base.",
                "factor_notes": {
                    "inflation_regime": {
                        "stance": "hot",
                        "reason": "Inflation remains elevated, so bond investors demand more compensation.",
                        "data_points": ["Core CPI and PCE context included."],
                        "quotes": ["Inflation is elevated."],
                    },
                    "policy_path": {
                        "stance": "hawkish",
                        "reason": "The Committee says it will assess incoming data before easing.",
                        "data_points": ["market_vs_fed_gap_bp +47"],
                        "quotes": ["carefully assess incoming data"],
                    },
                },
                "logic_chain": [
                    "Inflation elevated -> Fed cautious -> investors demand more compensation -> yield pressure.",
                    "Policy path hold -> front end resists rally -> curve view stays range-bound.",
                ],
                "key_quotes": [
                    {
                        "source": "statement 2026-04-29",
                        "quote": "Inflation is elevated.",
                    }
                ],
            },
            "base_vs_adjusted": {
                "linearity_assertion": "passed",
                "bounded_gpt_regime": {
                    "available": False,
                    "numeric_bp_allowed": False,
                    "regime": {
                        "inflation": "neutral",
                        "policy": "neutral",
                        "growth": "neutral",
                        "liquidity_supply": "neutral",
                        "global_relative_value": "neutral",
                    },
                    "rationale": "LLM degraded; B matrix supplies magnitudes.",
                    "key_quotes": [],
                },
                "horizons": {
                    "3": {
                        "targets": {
                            "2Y": {
                                "base": 4.05,
                                "adjusted": 4.10,
                                "total_delta_bp": 5.0,
                                "contributions_bp": {
                                    "policy_path": 3.0,
                                    "inflation_regime": 2.0,
                                },
                            },
                            "10Y": {
                                "base": 4.20,
                                "adjusted": 4.18,
                                "total_delta_bp": -2.0,
                                "contributions_bp": {
                                    "policy_path": -1.0,
                                    "inflation_regime": -1.0,
                                },
                            },
                        }
                    }
                },
            },
        },
    }


def test_html_report_contains_required_sections_and_no_alpha_claims():
    html = render_report_html(
        _trajectory(),
        market_confirmation={
            "DGS2": 3.99,
            "DGS5": 4.15,
            "2s10s": 0.46,
            "agrees": True,
            "reason": "DGS2/DGS5/2s10s context.",
        },
    )

    assert "<!doctype html>" in html.lower()
    assert "Scenario view with uncertainty; not a trading signal." in html
    assert "Fan Charts" in html
    assert 'id="chart-10Y-featured"' in html
    assert "Macro Factor Explorer" in html
    assert 'data-factor="policy_path"' in html
    assert 'data-factor="inflation_regime"' in html
    assert 'data-subfactor="CPILFESL"' in html
    assert 'data-subfactor="PCEPI"' in html
    assert "Factor Breakdown" in html
    assert "CPI / Core CPI" in html
    assert "Liquidity / Supply" in html
    assert "Why It Moves" in html
    assert "Policy Mapping Sandbox" in html
    assert "cut_prob_high" in html
    assert "front_end_cut_bp" in html
    assert "Random-walk curve" in html
    assert "Show random-walk curve" in html
    assert "What this means in plain English" in html
    assert "investors demand more compensation" in html
    assert "Bond price down, yield up" in html
    assert "Whole Prediction Logic" in html
    assert "Grounded Macro Analysis" in html
    assert "statement 2026-04-29" in html
    assert "Inflation is elevated." in html
    assert "narrative_and_regime_only_no_bp_or_central_shift" in html
    assert "Base means" in html
    assert "not an error-correction model" in html
    assert 'id="factor-monthly-body"' in html
    assert 'id="mapping-result-body"' in html
    assert "updateFactorScenario" in html
    assert "updatePolicyMappingSandbox" in html
    assert 'id="traceyield-factor-scenario-data"' in html
    assert 'id="traceyield-policy-mapping-data"' in html
    assert "Policy Path" in html
    assert "Driver Why Table" in html
    assert "Event Timeline" in html
    assert "Base vs Adjusted" in html
    assert "10Y Baselines" in html
    assert "Polymarket External Check" in html
    assert "external_check_only_no_central_shift" in html
    assert "Will the 10-year Treasury yield dip below 3.9%" in html
    assert "random-walk" in html
    assert "3.90" in html
    assert "4.80" in html
    assert "B matrix supplies magnitudes" in html
    assert "Methodology" in html
    assert "bias-corrected center" not in html
    assert "proxy only, low confidence" in html
    assert "estimated" in html
    assert "alpha" not in html.lower()
    assert "beat random walk" not in html.lower()


def test_factor_scenario_data_exposes_monthly_base_and_contributions():
    trajectory = _trajectory()
    html = render_report_html(trajectory)
    start = html.index(
        '<script type="application/json" id="traceyield-factor-scenario-data">'
    )
    start = html.index(">", start) + 1
    end = html.index("</script>", start)
    factor_data = json.loads(html[start:end])

    ten_year_m3 = factor_data["targets"]["10Y"]["months"]["3"]
    assert ten_year_m3["base"] == 4.20
    assert ten_year_m3["adjusted"] == 4.18
    assert ten_year_m3["random_walk"] == 4.0
    assert ten_year_m3["contributions_bp"]["policy_path"] == -1.0
    assert ten_year_m3["contributions_bp"]["inflation_regime"] == -1.0
    assert "policy_path" in factor_data["blocks"]
    assert "subfactors" in factor_data
    assert "CPILFESL" in factor_data["subfactors"]["inflation_regime"]
    assert factor_data["subfactor_weights"]["inflation_regime"]["CPILFESL"] > 0


def test_chart_data_preserves_json_central_and_p50_values_exactly():
    trajectory = _trajectory()
    html = render_report_html(trajectory)
    start = html.index('<script type="application/json" id="traceyield-chart-data">')
    start = html.index(">", start) + 1
    end = html.index("</script>", start)
    chart_data = json.loads(html[start:end])

    assert chart_data["2Y"]["central"] == [
        p["central"] for p in trajectory["tenors"]["2Y"]
    ]
    assert chart_data["2Y"]["p50"] == [p["p50"] for p in trajectory["tenors"]["2Y"]]
    assert chart_data["10Y"]["central"] == [
        p["central"] for p in trajectory["tenors"]["10Y"]
    ]
    assert chart_data["2s10s"]["central"] == [
        p["central"] for p in trajectory["tenors"]["2s10s"]
    ]


def test_save_html_report_writes_dated_and_latest_copies(tmp_path):
    dated, latest = save_html_report(_trajectory(), output_dir=tmp_path)

    assert dated.name == "curve_report_20260529.html"
    assert latest.name == "curve_latest.html"
    assert dated.exists()
    assert latest.exists()
    assert dated.read_text(encoding="utf-8") == latest.read_text(encoding="utf-8")
