"""Compute v2 UST curve driver scores from currently available data.

Phase A deliberately uses only existing FRED/cached data. Missing high-value
inputs such as consensus surprises, ACM term premium, auctions, MOVE, and
futures degrade to transparent proxies rather than blocking the report.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.ingestion.nyfed_acm import term_premium_change_zscore_asof
from src.ingestion.treasury_auctions import auction_stress_asof
from src.signals.factors import (
    _pct_change,
    _zscore_last,
    global_rates_factor,
    liquidity_factor,
)
from src.signals.fomc_series import fomc_factor_asof
from src.signals.yield_trend import yield_trend_factor


@dataclass
class DriverSignal:
    score: float
    components: dict[str, float] = field(default_factory=dict)
    rationale: str = ""
    asof: pd.Timestamp | None = None


def _clip(value: float) -> float:
    return float(max(-1.0, min(1.0, value)))


def _last_date(df: pd.DataFrame) -> pd.Timestamp:
    if df.empty:
        return pd.Timestamp.today().normalize()
    return pd.Timestamp(df.index.max()).normalize()


def _change_score(s: pd.Series, periods: int, full_scale: float) -> float:
    s = s.dropna()
    if len(s) <= periods:
        return 0.0
    return _clip(float(s.iloc[-1] - s.iloc[-periods - 1]) / full_scale)


def _series_score(df: pd.DataFrame, col: str) -> float:
    if col not in df:
        return 0.0
    return _zscore_last(df[col])


def _inflation_acceleration_score(df: pd.DataFrame, col: str) -> float:
    if col not in df:
        return 0.0
    release_rate = _pct_change(df, col, 1) * 100
    acceleration = release_rate.diff()
    return _zscore_last(acceleration)


def _macro_surprise_signal(df: pd.DataFrame) -> tuple[float, dict, str]:
    parts = []
    components = {}
    cpi = _inflation_acceleration_score(df, "CPIAUCSL")
    if "CPIAUCSL" in df:
        parts.append(cpi)
        components["cpi_release_acceleration_proxy"] = round(cpi, 4)
    core_pce = _inflation_acceleration_score(df, "PCEPILFE")
    if "PCEPILFE" in df:
        parts.append(core_pce)
        components["core_pce_release_acceleration_proxy"] = round(core_pce, 4)
    score = _clip(sum(parts) / len(parts)) if parts else 0.0
    return (
        score,
        components,
        (
            "Free-data macro-surprise proxy: release-over-release acceleration "
            "in CPI/core PCE inflation rates because paid consensus data is absent."
        ),
    )


def _term_premium_signal(
    df: pd.DataFrame, asof: pd.Timestamp
) -> tuple[float, dict, str]:
    acm = term_premium_change_zscore_asof(asof)
    if acm is not None:
        acm_score, components = acm
        return (
            _clip(-acm_score),
            components,
            (
                "NY Fed ACM 10Y term-premium change normalized by rolling std; "
                "higher/rising term premium is treated as long-end cheapness "
                "and forward mean-reversion pressure."
            ),
        )

    real_yield_proxy = _series_score(df, "DGS10") - _series_score(df, "T10YIE")
    forward_inflation = _series_score(df, "T5YIFR")
    long_momentum = _change_score(df.get("DGS30", pd.Series(dtype=float)), 126, 0.75)
    score = _clip(
        -(0.40 * real_yield_proxy + 0.25 * forward_inflation + 0.35 * long_momentum)
    )
    return (
        score,
        {
            "real_yield_proxy": round(real_yield_proxy, 4),
            "5y5y_inflation_proxy": round(forward_inflation, 4),
            "30y_6m_momentum": round(long_momentum, 4),
        },
        "Fallback term-premium valuation proxy; higher cheapness maps to yields down.",
    )


def _liquidity_supply_signal(
    df: pd.DataFrame, asof: pd.Timestamp
) -> tuple[float, dict, str]:
    base_liquidity = liquidity_factor(df)
    auction_stress = auction_stress_asof(asof)
    if auction_stress is None:
        return (
            base_liquidity,
            {"balance_sheet_liquidity": round(base_liquidity, 4)},
            "Fed balance sheet and reserves liquidity pressure.",
        )
    score = _clip(0.60 * base_liquidity + 0.40 * auction_stress)
    return (
        score,
        {
            "balance_sheet_liquidity": round(base_liquidity, 4),
            "auction_stress": round(auction_stress, 4),
        },
        "Balance-sheet liquidity plus Treasury auction stress.",
    )


def _growth_risk_signal(df: pd.DataFrame) -> tuple[float, dict, str]:
    if "T10Y2Y" in df:
        curve = df["T10Y2Y"].dropna()
    elif {"DGS10", "DGS2"}.issubset(df.columns):
        curve = (df["DGS10"] - df["DGS2"]).dropna()
    else:
        curve = pd.Series(dtype=float)

    if curve.empty:
        return (
            0.0,
            {},
            "Growth proxy unavailable; neutral until curve data is available.",
        )

    curve_level = _zscore_last(curve)
    curve_momentum = _clip(
        float(curve.iloc[-1] - curve.iloc[-64]) / 0.50 if len(curve) > 64 else 0.0
    )
    score = _clip(-(0.70 * curve_level + 0.30 * curve_momentum))
    return (
        score,
        {
            "2s10s_growth_proxy": round(curve_level, 4),
            "2s10s_3m_change_proxy": round(curve_momentum, 4),
        },
        (
            "Curve-based growth-risk/easing proxy separated from VIX; "
            "higher curve stress maps to lower yield pressure."
        ),
    )


def _risk_off_signal(df: pd.DataFrame) -> tuple[float, dict, str]:
    if "VIXCLS" not in df:
        return 0.0, {}, "VIX stress proxy unavailable; neutral risk-off overlay."
    vix = df["VIXCLS"].dropna()
    if len(vix) < 20:
        return 0.0, {}, "Insufficient VIX history for stress detection."

    window = vix.tail(63)
    level_std = window.std()
    level_z = (
        0.0 if level_std == 0 else float((vix.iloc[-1] - window.mean()) / level_std)
    )

    vix_change = vix.diff(5).dropna()
    if len(vix_change) >= 20:
        change_window = vix_change.tail(63)
        change_std = change_window.std()
        change_z = (
            0.0
            if change_std == 0
            else float((vix_change.iloc[-1] - change_window.mean()) / change_std)
        )
    else:
        change_z = 0.0

    vix_spike = max(0.0, change_z / 2.0)
    vix_stress_level = max(0.0, level_z / 2.0)
    stress = _clip(max(vix_spike, vix_stress_level))
    return (
        -stress,
        {
            "vix_spike": round(vix_spike, 4),
            "vix_stress_level": round(vix_stress_level, 4),
        },
        "VIX spike/stress detection; higher stress maps to lower yield pressure.",
    )


def compute_driver_signals(
    df: pd.DataFrame,
    hawkish: float | None = None,
) -> dict[str, DriverSignal]:
    """Return v2 driver signals with transparent Phase-A proxy components."""
    asof = _last_date(df)
    hawkish_score = fomc_factor_asof(asof) if hawkish is None else float(hawkish)

    two_year_momentum = _change_score(df.get("DGS2", pd.Series(dtype=float)), 63, 0.50)
    five_year_momentum = _change_score(df.get("DGS5", pd.Series(dtype=float)), 63, 0.50)
    policy_score = _clip(
        0.45 * hawkish_score + 0.35 * two_year_momentum + 0.20 * five_year_momentum
    )

    macro_score, macro_components, macro_rationale = _macro_surprise_signal(df)

    liquidity_score, liquidity_components, liquidity_rationale = (
        _liquidity_supply_signal(df, asof)
    )

    term_score, term_components, term_rationale = _term_premium_signal(df, asof)

    growth_score, growth_components, growth_rationale = _growth_risk_signal(df)

    global_score = -global_rates_factor(df)

    positioning_score = yield_trend_factor(df)

    risk_off_score, risk_off_components, risk_off_rationale = _risk_off_signal(df)

    return {
        "policy_path": DriverSignal(
            score=policy_score,
            components={
                "fomc_tone": round(hawkish_score, 4),
                "2y_3m_momentum": round(two_year_momentum, 4),
                "5y_3m_momentum": round(five_year_momentum, 4),
            },
            rationale="FOMC tone plus front-end Treasury momentum.",
            asof=asof,
        ),
        "macro_surprise": DriverSignal(
            score=macro_score,
            components=macro_components,
            rationale=macro_rationale,
            asof=asof,
        ),
        "liquidity_supply": DriverSignal(
            score=liquidity_score,
            components=liquidity_components,
            rationale=liquidity_rationale,
            asof=asof,
        ),
        "term_premium": DriverSignal(
            score=term_score,
            components=term_components,
            rationale=term_rationale,
            asof=asof,
        ),
        "growth_risk": DriverSignal(
            score=growth_score,
            components=growth_components,
            rationale=growth_rationale,
            asof=asof,
        ),
        "global_relative_value": DriverSignal(
            score=global_score,
            components={"ust_bund_proxy": round(global_score, 4)},
            rationale=(
                "UST versus Bund/JGB relative-value proxy; wider UST premium "
                "is treated as valuation demand that leans yields lower."
            ),
            asof=asof,
        ),
        "positioning_momentum": DriverSignal(
            score=positioning_score,
            components={"yield_trend": round(positioning_score, 4)},
            rationale="Treasury yield and curve momentum.",
            asof=asof,
        ),
        "risk_off_overlay": DriverSignal(
            score=risk_off_score,
            components=risk_off_components,
            rationale=risk_off_rationale,
            asof=asof,
        ),
    }
