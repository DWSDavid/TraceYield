"""Render v2 UST curve impact forecasts."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from src.models.curve_engine import CurveForecast
from src.utils.config import DATA


def _fmt_pressure(value: float) -> str:
    if value >= 0.35:
        return f"++ ({value:+.2f})"
    if value >= 0.08:
        return f"+ ({value:+.2f})"
    if value <= -0.35:
        return f"-- ({value:+.2f})"
    if value <= -0.08:
        return f"- ({value:+.2f})"
    return f"0 ({value:+.2f})"


def _core_forecasts(forecasts: list[CurveForecast]) -> list[CurveForecast]:
    core = [f for f in forecasts if f.horizon in {"3m_core", "6m_core"}]
    return core or forecasts


def _direction(value: float) -> str:
    if value >= 0.08:
        return "Bearish / yield-up"
    if value <= -0.08:
        return "Bullish / yield-down"
    return "Neutral"


def _fmt_context_drivers(forecast: CurveForecast) -> str:
    if not forecast.context_contributions:
        return "none"
    ranked = sorted(
        forecast.context_contributions.items(),
        key=lambda kv: abs(kv[1]),
        reverse=True,
    )
    return ", ".join(f"`{name}` {value:+.3f}" for name, value in ranked)


def to_markdown(
    forecasts: list[CurveForecast],
    run_date: date | pd.Timestamp | None = None,
) -> str:
    run_date = pd.Timestamp(run_date or date.today()).date()
    core = _core_forecasts(forecasts)
    primary = core[0]

    lines = [
        f"# UST Curve Impact Forecast - {run_date:%Y-%m-%d}",
        "",
        "## Headline 10Y Direction",
        "",
        "10Y view is reconstructed from the front-end policy view plus the "
        "2s10s curve view; it is not an isolated 10Y outright-level forecast.",
        "",
        "| Horizon | 10Y call | Front-end 2Y | 2s10s curve | Reconstructed 10Y | Pure term-premium residual |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for forecast in core:
        view = forecast.ten_year_reconstruction
        ten_year = view.get("reconstructed_10y", forecast.tenor_pressure["10Y"])
        front_end = view.get("front_end_2y", forecast.tenor_pressure["2Y"])
        curve = view.get("curve_2s10s", ten_year - front_end)
        residual = view.get("context_term_premium_residual", 0.0)
        lines.append(
            f"| {forecast.horizon} | {_direction(ten_year)} "
            f"| {_fmt_pressure(front_end)} "
            f"| {_fmt_pressure(curve)} "
            f"| {_fmt_pressure(ten_year)} "
            f"| context-only / low-confidence {_fmt_pressure(residual)} |"
        )

    lines += [
        "",
        "## Core View",
        "",
    ]
    for forecast in core:
        lines.append(
            f"- **{forecast.horizon}:** `{forecast.curve_call}` - "
            f"{forecast.main_driver} (confidence {forecast.confidence:.0%})"
        )

    lines += [
        "",
        "## Tenor Pressure",
        "",
        "| Horizon | 2Y policy | 5Y bridge | 2s10s curve | 10Y reconstructed |",
        "|---|---:|---:|---:|---:|",
    ]
    for forecast in forecasts:
        pressure = forecast.tenor_pressure
        view = forecast.ten_year_reconstruction
        ten_year = view.get("reconstructed_10y", pressure["10Y"])
        front_end = view.get("front_end_2y", pressure["2Y"])
        curve = view.get("curve_2s10s", ten_year - front_end)
        lines.append(
            f"| {forecast.horizon} | {_fmt_pressure(front_end)} "
            f"| {_fmt_pressure(pressure['5Y'])} "
            f"| {_fmt_pressure(curve)} "
            f"| {_fmt_pressure(ten_year)} |"
        )

    lines += [
        "",
        "## Context-only long end",
        "",
        "30Y and pure long-end / term-premium factors are retained as context, "
        "not as core trade drivers.",
        "",
        "| Horizon | 30Y context | Term-premium residual | Long-end context drivers |",
        "|---|---:|---:|---|",
    ]
    for forecast in forecasts:
        context_pressure = forecast.context_tenor_pressure
        view = forecast.ten_year_reconstruction
        lines.append(
            f"| {forecast.horizon} | "
            f"{_fmt_pressure(context_pressure.get('30Y', 0.0))} | "
            f"{_fmt_pressure(view.get('context_term_premium_residual', 0.0))} | "
            f"{_fmt_context_drivers(forecast)} |"
        )

    lines += ["", "## Driver Attribution", ""]
    ranked = sorted(
        primary.contributions.items(), key=lambda kv: abs(kv[1]), reverse=True
    )
    lines.append("Core drivers:")
    for driver, contribution in ranked:
        raw = primary.factor_scores.get(driver, 0.0)
        lines.append(f"- `{driver}` raw={raw:+.3f}, contrib={contribution:+.3f}")
    lines.append("")
    lines.append("Context-only drivers:")
    for driver, contribution in sorted(
        primary.context_contributions.items(),
        key=lambda kv: abs(kv[1]),
        reverse=True,
    ):
        raw = primary.factor_scores.get(driver, 0.0)
        lines.append(f"- `{driver}` raw={raw:+.3f}, contrib={contribution:+.3f}")

    lines += ["", "## Key Triggers", ""]
    for trigger in primary.triggers:
        lines.append(f"- {trigger}")

    lines += [
        "",
        "## Rationale",
        "",
        primary.rationale,
        "",
        "## Light Cross-Market Linkage",
        "",
        primary.linkage_note,
        "",
        "*Positive pressure = yield-up pressure. Negative pressure = yield-down pressure.*",
    ]
    return "\n".join(lines)


def save(markdown: str, run_date: date | pd.Timestamp | None = None) -> Path:
    run_date = pd.Timestamp(run_date or date.today()).date()
    out = DATA / "reports" / f"curve_report_{run_date:%Y%m%d}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown, encoding="utf-8")
    latest = DATA / "reports" / "curve_latest.md"
    latest.write_text(markdown, encoding="utf-8")
    return out
