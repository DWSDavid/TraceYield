"""Smoke tests: the prediction + report path works with no external deps."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.predictor import predict
from src.report import render
from src.nlp.keyword_scorer import score_text


def test_keyword_scorer_signs():
    haw = score_text("policy is restrictive and inflation remains elevated")
    dov = score_text("the committee will pursue rate cuts and easing")
    assert haw["score"] > 0
    assert dov["score"] < 0


def test_predict_shape_and_direction():
    factors = {
        "fomc_nlp": 0.8,
        "inflation": 0.6,
        "liquidity": 0.4,
        "global_rates": 0.2,
        "political_risk": 0.0,
        "yield_trend": 0.5,
    }
    preds = predict(factors, current_10y=4.40)
    assert [p.horizon for p in preds] == ["1m", "3m", "6m", "12m"]
    assert all(p.direction == "Bear" for p in preds)  # all-positive -> yields up
    assert all(p.target_yield > 4.40 for p in preds)  # bear = higher target
    assert all("yield_trend" in p.contributions for p in preds)


def test_report_renders():
    factors = {
        "fomc_nlp": -0.5,
        "inflation": -0.3,
        "liquidity": 0.0,
        "global_rates": 0.0,
        "political_risk": 0.0,
        "yield_trend": -0.2,
    }
    preds = predict(factors, current_10y=4.40)
    md = render.to_markdown(preds, 4.40)
    assert "UST 10Y Prediction" in md
    assert "Bull" in md  # negative score -> bull
