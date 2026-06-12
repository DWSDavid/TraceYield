"""v2 UST curve forecast engine."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.signals.curve_drivers import DriverSignal, compute_driver_signals
from src.signals.curve_impact import classify_curve_call, tenor_pressure_from_drivers
from src.utils.config import load_yaml

DEFAULT_CONTEXT_ONLY_FACTORS = (
    "term_premium",
    "liquidity_supply",
    "global_relative_value",
)


@dataclass
class CurveForecast:
    horizon: str
    curve_call: str
    tenor_pressure: dict[str, float]
    factor_scores: dict[str, float]
    contributions: dict[str, float]
    main_driver: str
    secondary_driver: str
    confidence: float
    rationale: str
    context_contributions: dict[str, float] = field(default_factory=dict)
    context_tenor_pressure: dict[str, float] = field(default_factory=dict)
    ten_year_reconstruction: dict[str, float] = field(default_factory=dict)
    triggers: list[str] = field(default_factory=list)
    linkage_note: str = ""
    asof: pd.Timestamp | None = None


def _weights() -> dict[str, dict[str, float]]:
    return load_yaml("curve_weights")["horizons"]


def _context_only_factors() -> set[str]:
    cfg = load_yaml("curve_weights")
    return set(cfg.get("context_only_factors", DEFAULT_CONTEXT_ONLY_FACTORS))


def _rank_contributions(contributions: dict[str, float]) -> list[tuple[str, float]]:
    return sorted(contributions.items(), key=lambda kv: abs(kv[1]), reverse=True)


def _split_contributions(
    contributions: dict[str, float],
    context_only_factors: set[str],
) -> tuple[dict[str, float], dict[str, float]]:
    core = {
        name: value
        for name, value in contributions.items()
        if name not in context_only_factors
    }
    context = {
        name: value
        for name, value in contributions.items()
        if name in context_only_factors
    }
    return core, context


def _confidence(
    contributions: dict[str, float], tenor_pressure: dict[str, float]
) -> float:
    signal_strength = sum(abs(v) for v in contributions.values())
    curve_strength = max(abs(v) for v in tenor_pressure.values())
    return round(min(0.95, 0.45 + 0.35 * signal_strength + 0.20 * curve_strength), 3)


def _ten_year_reconstruction(
    tenor_pressure: dict[str, float],
    context_contributions: dict[str, float],
) -> dict[str, float]:
    front_end = float(tenor_pressure.get("2Y", 0.0))
    curve_component = float(tenor_pressure.get("10Y", 0.0)) - front_end
    term_premium_residual = tenor_pressure_from_drivers(
        {"term_premium": context_contributions.get("term_premium", 0.0)}
    )["10Y"]
    return {
        "front_end_2y": round(front_end, 4),
        "curve_2s10s": round(curve_component, 4),
        "reconstructed_10y": round(front_end + curve_component, 4),
        "context_term_premium_residual": round(term_premium_residual, 4),
    }


def _triggers(main_driver: str, tenor_pressure: dict[str, float]) -> list[str]:
    ten_year = tenor_pressure.get("10Y", 0.0)
    direction = "above" if ten_year >= 0 else "below"
    driver_triggers = {
        "policy_path": "2Y reprices sharply after FOMC, payrolls, or CPI.",
        "macro_surprise": "CPI/PCE/NFP surprise trend changes sign.",
        "liquidity_supply": "Refunding, auction tails, reserves, or RRP pressure shifts.",
        "term_premium": "10Y/30Y break the recent range or term-premium proxy reverses.",
        "growth_risk": "Claims, ISM, VIX, or curve recession proxies deteriorate.",
        "global_relative_value": "Bund/JGB yields reprice enough to change UST demand.",
        "positioning_momentum": "2s10s or 5s30s momentum breaks the opposite way.",
        "risk_off_overlay": "VIX/credit stress moves into or out of shock regime.",
    }
    return [
        driver_triggers.get(main_driver, "Main driver changes sign."),
        f"10Y closes {direction} its recent range with 2Y and 2s10s confirmation.",
        "3m and 6m core calls diverge, signalling mixed/conflict state.",
    ]


def _rationale(
    horizon: str,
    curve_call: str,
    ranked: list[tuple[str, float]],
    signals: dict[str, DriverSignal],
    context_contributions: dict[str, float],
) -> str:
    main, main_value = ranked[0]
    secondary, secondary_value = ranked[1]
    main_sign = "upward" if main_value >= 0 else "downward"
    secondary_sign = "upward" if secondary_value >= 0 else "downward"
    context = ", ".join(sorted(context_contributions)) or "none"
    return (
        f"{horizon} maps to {curve_call}: {main} is the largest driver "
        f"({main_sign} yield pressure, raw score {signals[main].score:+.2f}), "
        f"with {secondary} as the second driver ({secondary_sign} pressure). "
        f"Context-only long-end drivers excluded from the core call: {context}."
    )


def forecast_curve(
    df: pd.DataFrame,
    hawkish: float | None = None,
) -> list[CurveForecast]:
    """Produce v2 staged UST curve forecasts from existing factor history."""
    signals = compute_driver_signals(df, hawkish=hawkish)
    raw_scores = {name: signal.score for name, signal in signals.items()}
    asof = next(iter(signals.values())).asof if signals else pd.Timestamp.today()
    forecasts: list[CurveForecast] = []
    context_only_factors = _context_only_factors()

    for horizon, weights in _weights().items():
        all_contributions = {
            name: round(float(weight) * raw_scores.get(name, 0.0), 4)
            for name, weight in weights.items()
        }
        contributions, context_contributions = _split_contributions(
            all_contributions,
            context_only_factors,
        )
        tenor_pressure = tenor_pressure_from_drivers(contributions)
        context_tenor_pressure = tenor_pressure_from_drivers(context_contributions)
        curve_call = classify_curve_call(tenor_pressure)
        ranked = _rank_contributions(contributions) or [("policy_path", 0.0)]
        if len(ranked) == 1:
            ranked.append((ranked[0][0], 0.0))
        main_driver = ranked[0][0]
        secondary_driver = ranked[1][0]
        forecasts.append(
            CurveForecast(
                horizon=horizon,
                curve_call=curve_call,
                tenor_pressure=tenor_pressure,
                factor_scores={k: round(v, 4) for k, v in raw_scores.items()},
                contributions=contributions,
                context_contributions=context_contributions,
                context_tenor_pressure=context_tenor_pressure,
                ten_year_reconstruction=_ten_year_reconstruction(
                    tenor_pressure,
                    context_contributions,
                ),
                main_driver=main_driver,
                secondary_driver=secondary_driver,
                confidence=_confidence(contributions, tenor_pressure),
                rationale=_rationale(
                    horizon,
                    curve_call,
                    ranked,
                    signals,
                    context_contributions,
                ),
                triggers=_triggers(main_driver, tenor_pressure),
                linkage_note=(
                    "JGB read-through is mainly long-end/global-duration. "
                    "CGB read-through is light and works through USD/CNH, "
                    "global duration risk, and China easing room."
                ),
                asof=asof,
            )
        )
    return forecasts
