"""v0 predictor: weighted linear blend of factor scores -> direction + level.

This is the interpretable baseline the whole system starts from. Every output
is fully explained by signed factor contributions. An XGBoost/LightGBM model
can later replace the blend while keeping the same input/output contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.utils.config import weights


@dataclass
class HorizonPrediction:
    horizon: str
    direction: str            # "Bull" | "Bear" | "Neutral"
    probability: float        # confidence in [0.5, 1.0]
    score: float              # raw blended signal in ~[-1, 1]
    target_yield: float       # predicted 10Y level (%)
    contributions: dict = field(default_factory=dict)  # factor -> signed contrib


def _direction(score: float, th: dict) -> str:
    if score > th["bear_above"]:
        return "Bear"     # yields up
    if score < th["bull_below"]:
        return "Bull"     # yields down
    return "Neutral"


# Rough sensitivity: how many bps the 10Y moves per 1.0 of signal, per horizon.
# Starting guess; backtesting calibrates this.
BPS_PER_UNIT = {"1w": 12.0, "1m": 30.0, "3m": 55.0}


def predict(factor_scores: dict, current_10y: float) -> list[HorizonPrediction]:
    """Blend factor scores per horizon into direction + level predictions."""
    cfg = weights()
    th = cfg["thresholds"]
    out: list[HorizonPrediction] = []

    for horizon, w in cfg["horizons"].items():
        contribs = {f: round(w[f] * factor_scores.get(f, 0.0), 4) for f in w}
        score = sum(contribs.values())
        direction = _direction(score, th)
        # Confidence grows with |score|, capped.
        prob = round(min(0.95, 0.5 + abs(score)), 3)
        bps = BPS_PER_UNIT.get(horizon, 30.0) * score
        target = round(current_10y + bps / 100.0, 3)
        out.append(HorizonPrediction(
            horizon=horizon, direction=direction, probability=prob,
            score=round(score, 4), target_yield=target, contributions=contribs,
        ))
    return out
