"""Self-contained HTML renderer for the 12-month UST curve view."""

from __future__ import annotations

import html
import json
import math
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd

from src.signals.policy_path import market_confirmation_row
from src.utils.config import DATA, load_yaml

CORE_TARGETS = ("2Y", "10Y", "2s10s")
DETAIL_TARGETS = ("5Y", "30Y", "5s30s")
CHART_WIDTH = 760
CHART_HEIGHT = 310
PLOT_LEFT = 54
PLOT_RIGHT = 24
PLOT_TOP = 28
PLOT_BOTTOM = 54
FORBIDDEN_PHRASES = ("alpha", "beat random walk", "beats random walk")


def load_trajectory(path: str | Path) -> dict[str, Any]:
    """Load a saved curve trajectory JSON contract."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def latest_trajectory_path() -> Path:
    """Return the most recent saved curve trajectory JSON path."""
    paths = sorted((DATA / "forecasts").glob("curve_trajectory_*.json"))
    if not paths:
        raise FileNotFoundError("No saved curve trajectory JSON found.")
    return paths[-1]


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _fmt_num(value: Any, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return _esc(value)


def _month_point(points: list[dict[str, Any]], month: int) -> dict[str, Any]:
    if not points:
        return {}
    index = max(0, min(month - 1, len(points) - 1))
    return points[index]


def _direction_from_delta(delta_bp: float) -> str:
    if delta_bp <= -10.0:
        return "lower"
    if delta_bp >= 10.0:
        return "higher"
    return "range-bound"


def _arrow_from_delta(delta_bp: float) -> str:
    if delta_bp <= -5.0:
        return "down"
    if delta_bp >= 5.0:
        return "up"
    return "flat"


def _arrow_symbol(label: str) -> str:
    return {"up": "↑", "down": "↓", "flat": "→"}.get(label, "→")


def _target_delta_bp(trajectory: dict[str, Any], target: str, month: int) -> float:
    point = _month_point(trajectory["tenors"].get(target, []), month)
    return float(point.get("delta_bp", 0.0))


def _p50_delta_bp(trajectory: dict[str, Any], target: str, month: int) -> float:
    """Macro-adjusted central path minus today's level, in bp."""
    point = _month_point(trajectory["tenors"].get(target, []), month)
    current = point.get("current")
    central = point.get("central")
    if current is None or central is None:
        return float(point.get("delta_bp", 0.0))
    return (float(central) - float(current)) * 100.0


def _headline(trajectory: dict[str, Any]) -> dict[str, str]:
    ten_year_12m = _p50_delta_bp(trajectory, "10Y", 12)
    ten_year_3m = _p50_delta_bp(trajectory, "10Y", 3)
    curve_3m = _p50_delta_bp(trajectory, "2s10s", 3)
    ten_year_6m = _p50_delta_bp(trajectory, "10Y", 6)
    curve_6m = _p50_delta_bp(trajectory, "2s10s", 6)
    return {
        "ten_year": (
            f"10Y {_direction_from_delta(ten_year_12m)} over 12m "
            f"({ten_year_12m:+.1f}bp)"
        ),
        "three_month": (
            f"3m core: 10Y {ten_year_3m:+.1f}bp, " f"2s10s {curve_3m:+.1f}bp"
        ),
        "six_month": (
            f"6m core: 10Y {ten_year_6m:+.1f}bp, " f"2s10s {curve_6m:+.1f}bp"
        ),
    }


def _chart_data(trajectory: dict[str, Any]) -> dict[str, dict[str, list[Any]]]:
    data: dict[str, dict[str, list[Any]]] = {}
    for target, points in trajectory.get("tenors", {}).items():
        data[target] = {
            key: [point.get(key) for point in points]
            for key in (
                "month",
                "current",
                "central",
                "p10",
                "p25",
                "p50",
                "p75",
                "p90",
                "uncertainty_widen_bp",
            )
        }
    return data


def _event_rows(trajectory: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for overlay in trajectory.get("metadata", {}).get("event_overlays", []):
        if overlay.get("type") == "UNCERTAINTY":
            for event in overlay.get("events", []):
                row = dict(event)
                row["month"] = overlay.get("month")
                row["reason"] = overlay.get("reason")
                row["widen_bp"] = overlay.get("widen_bp", {})
                rows.append(row)
        elif overlay.get("type") == "FOMC":
            rows.append(
                {
                    "event_type": "fomc",
                    "release_date": overlay.get("event_date"),
                    "precision": "confirmed",
                    "month": overlay.get("month"),
                    "reason": overlay.get("reason"),
                    "step_bp": overlay.get("step_bp"),
                }
            )
    deduped: dict[tuple[Any, Any], dict[str, Any]] = {}
    for row in rows:
        key = (row.get("event_type"), row.get("release_date"))
        deduped[key] = row
    return sorted(
        deduped.values(),
        key=lambda row: (
            pd.Timestamp(row.get("release_date", "2100-01-01")),
            str(row.get("event_type", "")),
        ),
    )


def _events_by_month(trajectory: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    by_month: dict[int, list[dict[str, Any]]] = {}
    for event in _event_rows(trajectory):
        month = event.get("month")
        if month is None:
            continue
        by_month.setdefault(int(month), []).append(event)
    return by_month


def _event_symbol(event: dict[str, Any]) -> str:
    event_type = str(event.get("event_type", "")).lower()
    if event_type == "fomc":
        return "★" if event.get("has_sep") else "F"
    return {"cpi": "C", "nfp": "N", "qra": "Q", "pce": "P"}.get(
        event_type,
        event_type[:1].upper(),
    )


def _event_label(event: dict[str, Any]) -> str:
    event_type = str(event.get("event_type", "")).upper()
    raw_date = event.get("release_date")
    date_label = pd.Timestamp(raw_date).strftime("%b %d") if raw_date else "date n/a"
    suffix = (
        " (estimated)" if str(event.get("precision", "")).lower() == "estimated" else ""
    )
    sep = " SEP" if event.get("has_sep") else ""
    return f"{date_label} {event_type}{sep}{suffix}"


def _event_title(month_events: Iterable[dict[str, Any]], reason: str = "") -> str:
    labels = [_event_label(event) for event in month_events]
    if reason:
        labels.append(str(reason))
    return " | ".join(labels)


def _scale(values: list[float], height: int) -> tuple[float, float]:
    low = min(values)
    high = max(values)
    if math.isclose(low, high):
        low -= 0.25
        high += 0.25
    pad = (high - low) * 0.08
    return low - pad, high + pad


def _x(month: int) -> float:
    usable = CHART_WIDTH - PLOT_LEFT - PLOT_RIGHT
    return PLOT_LEFT + (month - 1) * usable / 11.0


def _y(value: float, low: float, high: float) -> float:
    usable = CHART_HEIGHT - PLOT_TOP - PLOT_BOTTOM
    return PLOT_TOP + (high - value) * usable / (high - low)


def _polyline(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in points)


def _band_polygon(
    lower: list[float],
    upper: list[float],
    low: float,
    high: float,
) -> str:
    top = [(_x(i + 1), _y(value, low, high)) for i, value in enumerate(upper)]
    bottom = [
        (_x(i + 1), _y(value, low, high))
        for i, value in reversed(list(enumerate(lower)))
    ]
    return _polyline(top + bottom)


def _line(values: list[float], low: float, high: float) -> str:
    return _polyline(
        [(_x(i + 1), _y(value, low, high)) for i, value in enumerate(values)]
    )


def _chart_svg(
    trajectory: dict[str, Any],
    target: str,
    *,
    compact: bool = False,
) -> str:
    points = trajectory["tenors"][target]
    keys = ("p10", "p25", "p50", "p75", "p90", "central", "current")
    values = [float(point[key]) for point in points for key in keys if key in point]
    low, high = _scale(values, CHART_HEIGHT)
    today = float(points[0].get("current", points[0]["central"]))
    by_month = _events_by_month(trajectory)

    highlight = []
    marker = []
    for month, events in by_month.items():
        if month < 1 or month > 12:
            continue
        x = _x(month)
        point = points[month - 1]
        widen = float(point.get("uncertainty_widen_bp", 0.0) or 0.0)
        if widen > 0.0:
            highlight.append(
                f'<rect x="{x - 24:.2f}" y="{PLOT_TOP}" width="48" '
                f'height="{CHART_HEIGHT - PLOT_TOP - PLOT_BOTTOM}" '
                'class="event-band">'
                f"<title>{_esc(_event_title(events, point.get('overlay_reasons', [''])[-1]))}</title>"
                "</rect>"
            )
        for offset, event in enumerate(events[:4]):
            marker_y = CHART_HEIGHT - PLOT_BOTTOM + 17 + offset * 12
            marker.append(
                f'<text x="{x:.2f}" y="{marker_y:.2f}" class="event-marker">'
                f"<title>{_esc(_event_title([event], str(event.get('reason', ''))))}</title>"
                f"{_esc(_event_symbol(event))}</text>"
            )

    p10 = [float(point["p10"]) for point in points]
    p25 = [float(point["p25"]) for point in points]
    p50 = [float(point["p50"]) for point in points]
    p75 = [float(point["p75"]) for point in points]
    p90 = [float(point["p90"]) for point in points]
    central = [float(point["central"]) for point in points]
    today_y = _y(today, low, high)

    y_ticks = []
    for value in (low, (low + high) / 2.0, high):
        y_coord = _y(value, low, high)
        y_ticks.append(
            f'<line x1="{PLOT_LEFT}" x2="{CHART_WIDTH - PLOT_RIGHT}" '
            f'y1="{y_coord:.2f}" y2="{y_coord:.2f}" class="grid" />'
            f'<text x="10" y="{y_coord + 4:.2f}" class="axis-label">{value:.2f}</text>'
        )

    months = []
    for month in range(1, 13):
        x = _x(month)
        months.append(
            f'<text x="{x:.2f}" y="{CHART_HEIGHT - 8}" '
            f'class="axis-label month-label">{month}</text>'
        )

    height = CHART_HEIGHT if not compact else CHART_HEIGHT - 26
    return f"""
    <svg class="fan-svg" viewBox="0 0 {CHART_WIDTH} {height}" role="img" aria-label="{_esc(target)} fan chart">
      <title>{_esc(target)} 12-month fan chart</title>
      {''.join(highlight)}
      {''.join(y_ticks)}
      <polygon points="{_band_polygon(p10, p90, low, high)}" class="band-outer" />
      <polygon points="{_band_polygon(p25, p75, low, high)}" class="band-inner" />
      <line x1="{PLOT_LEFT}" x2="{CHART_WIDTH - PLOT_RIGHT}" y1="{today_y:.2f}" y2="{today_y:.2f}" class="today-line" />
      <polyline points="{_line(p50, low, high)}" class="p50-line" />
      <polyline points="{_line(central, low, high)}" class="central-line" />
      {''.join(marker)}
      {''.join(months)}
    </svg>
    """


def _chart_card(
    trajectory: dict[str, Any],
    target: str,
    *,
    featured: bool = False,
) -> str:
    article_id = f' id="chart-{_esc(target)}-featured"' if featured else ""
    class_name = "chart-card chart-card-featured" if featured else "chart-card"
    return f"""
    <article class="{class_name}"{article_id}>
      <div class="chart-head">
        <h3>{_esc(target)}</h3>
        <span>{_p50_delta_bp(trajectory, target, 3):+.1f}bp at 3m / {_p50_delta_bp(trajectory, target, 12):+.1f}bp at 12m</span>
      </div>
      {_chart_svg(trajectory, target)}
      <div class="legend">
        <span><i class="swatch outer"></i>p10-p90</span>
        <span><i class="swatch inner"></i>p25-p75</span>
        <span><i class="stroke p50"></i>p50 (fan median)</span>
        <span><i class="stroke central"></i>central (FADNS macro)</span>
        <span><i class="stroke today"></i>today</span>
      </div>
    </article>
    """


def _fan_charts_section(trajectory: dict[str, Any]) -> str:
    return f"""
  <section id="fan-charts">
    <div class="section-kicker">Range</div>
    <h2>Fan Charts</h2>
    <div class="featured-chart-grid">
      {_chart_card(trajectory, "10Y", featured=True)}
    </div>
    <div class="chart-grid chart-grid-secondary">
      {_chart_card(trajectory, "2Y")}
      {_chart_card(trajectory, "2s10s")}
    </div>
    <details>
      <summary>Show 5Y / 30Y supporting charts</summary>
      <div class="chart-grid">
        {''.join(_chart_card(trajectory, target) for target in DETAIL_TARGETS)}
      </div>
    </details>
  </section>
    """


def _value_table(trajectory: dict[str, Any]) -> str:
    """Per-month central path + p10-p90 range for the core tenors."""
    head_cells = "".join(f"<th>{_esc(t)}</th>" for t in CORE_TARGETS)
    rows = []
    for month in range(1, 13):
        cells = []
        for target in CORE_TARGETS:
            point = _month_point(trajectory["tenors"].get(target, []), month)
            cells.append(
                f"<td><b>{_fmt_num(point.get('central'), 2)}</b>"
                f"<span class='range'>{_fmt_num(point.get('p10'), 2)} – "
                f"{_fmt_num(point.get('p90'), 2)}</span></td>"
            )
        rows.append(f"<tr><th>m{month}</th>{''.join(cells)}</tr>")
    return f"""
    <section class="panel" id="estimates">
      <div class="section-kicker">Numbers</div>
      <h2>Monthly Estimates — central path (p10–p90 range)</h2>
      <table class="value-table">
        <thead><tr><th>Month</th>{head_cells}</tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
      <p class="source-line">Levels in % (2s10s is a spread in %, e.g. 0.38 = 38bp).
      Central = macro-adjusted FADNS path; p10–p90 ≈ 80% range. These are scenario
      estimates, not point forecasts.</p>
    </section>
    """


def _baseline_panel(trajectory: dict[str, Any]) -> str:
    ten_year = trajectory.get("metadata", {}).get("baselines", {}).get("10Y", {})
    if not ten_year:
        return ""
    random_walk = ten_year.get("random_walk", {})
    market_range = ten_year.get("market_range", {})
    ten_year_points = trajectory.get("tenors", {}).get("10Y", [])
    twelve = _month_point(ten_year_points, 12)
    central = twelve.get("central")
    low = market_range.get("low")
    high = market_range.get("high")
    if central is None or low is None or high is None:
        range_label = "n/a"
    else:
        inside = float(low) <= float(central) <= float(high)
        range_label = "inside observed range" if inside else "outside observed range"
    return f"""
    <section class="panel" id="baselines">
      <div class="section-kicker">Baseline</div>
      <h2>10Y Baselines & Market Range</h2>
      <div class="metric-grid">
        <div><span>random-walk 10Y</span><b>{_fmt_num(random_walk.get('level'))}%</b></div>
        <div><span>12m central 10Y</span><b>{_fmt_num(central)}%</b></div>
        <div><span>market low</span><b>{_fmt_num(low)}%</b></div>
        <div><span>market high</span><b>{_fmt_num(high)}%</b></div>
      </div>
      <p class="plain-label">12m central is {_esc(range_label)} versus the manual/free market-observed range.</p>
      <p class="source-line">Range source: {_esc(market_range.get('source', 'n/a'))}.
      {_esc(market_range.get('reason', ''))} {_esc(random_walk.get('reason', ''))}</p>
    </section>
    """


def _polymarket_panel(trajectory: dict[str, Any]) -> str:
    check = trajectory.get("metadata", {}).get("polymarket_check")
    if not check:
        check = {
            "source": "polymarket_gamma",
            "status": "unavailable",
            "markets": [],
            "traceyield_alignment": "unavailable",
            "alignment_reason": "Polymarket check unavailable in saved trajectory.",
            "model_usage": "external_check_only_no_central_shift",
        }
    markets = check.get("markets", [])[:5]
    rows = []
    for market in markets:
        flags = ", ".join(market.get("risk_flags", [])) or "none"
        rows.append(
            "<tr>"
            f"<th>{_esc(market.get('question'))}</th>"
            f"<td>{_fmt_num(market.get('yes_price'), 3)}</td>"
            f"<td>{_fmt_num(market.get('best_bid'), 3)} / {_fmt_num(market.get('best_ask'), 3)}</td>"
            f"<td>{_fmt_num(market.get('spread'), 3)}</td>"
            f"<td>{_fmt_num(market.get('volume'), 0)}</td>"
            f"<td>{_esc(market.get('confidence', 'low'))}</td>"
            f"<td>{_esc(flags)}</td>"
            "</tr>"
        )
    if not rows:
        rows.append(
            "<tr><th colspan='7'>No relevant active 10Y Treasury yield market found.</th></tr>"
        )
    return f"""
    <section class="panel" id="polymarket-check">
      <div class="section-kicker">External Market Check</div>
      <h2>Polymarket External Check</h2>
      <div class="metric-grid">
        <div><span>status</span><b>{_esc(check.get('status', 'unavailable'))}</b></div>
        <div><span>alignment</span><b>{_esc(check.get('traceyield_alignment', 'unavailable'))}</b></div>
        <div><span>source</span><b>{_esc(check.get('source', 'polymarket_gamma'))}</b></div>
        <div><span>usage</span><b>{_esc(check.get('model_usage', 'external_check_only_no_central_shift'))}</b></div>
      </div>
      <p class="plain-label">{_esc(check.get('alignment_reason', 'External check unavailable.'))}</p>
      <table class="driver-table">
        <thead><tr><th>Market</th><th>Yes</th><th>bid / ask</th><th>spread</th><th>volume</th><th>conf</th><th>flags</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
      <p class="source-line">Read-only public Polymarket API snapshot. This is a sanity check, not a model input.</p>
    </section>
    """


_BLOCK_LABELS = {
    "inflation_regime": "Inflation",
    "policy_path": "Policy",
    "growth_risk": "Growth",
    "liquidity_supply": "Liquidity",
    "global_relative_value": "Global",
}

_FACTOR_DETAILS = {
    "inflation_regime": {
        "label": "Inflation",
        "headline": "CPI / Core CPI, PCE / Core PCE, breakevens, and 5y5y inflation expectations.",
        "why": (
            "When inflation is high, the dollars paid back by a bond buy less in the future, "
            "so investors demand more compensation. The Fed also has less room to cut and may "
            "need to keep short rates high to cool demand. Bond price down, yield up: that is "
            "the basic pressure. Higher yields also make borrowing more expensive, which helps "
            "slow spending and cool inflation. When inflation cools, that pressure can reverse."
        ),
        "caveat": "Not one-for-one: CPI/PCE first changes inflation expectations and Fed expectations, then the curve reacts.",
        "subfactors": {
            "CPIAUCSL": "Headline CPI YoY",
            "CPILFESL": "Core CPI YoY",
            "PCEPI": "Headline PCE YoY",
            "PCEPILFE": "Core PCE YoY",
            "T5YIE": "5Y breakeven inflation",
            "T10YIE": "10Y breakeven inflation",
            "T5YIFR": "5Y5Y forward inflation",
        },
    },
    "policy_path": {
        "label": "Policy",
        "headline": "Fed target/EFFR, FOMC tone, front-end Treasury proxy, and market-vs-dot gap.",
        "why": (
            "The 2Y is basically the market asking: where will the Fed keep rates over the next "
            "few meetings? If the market thinks cuts are delayed, investors demand a higher yield "
            "on short Treasuries. That can also flatten 2s10s because the front end moves more "
            "than the long end."
        ),
        "caveat": "This is the most direct channel for the front end, but Treasury bills also include bill basis and risk premium.",
        "subfactors": {
            "fomc_tone": "FOMC tone",
            "DFEDTARU": "Fed target upper bound",
            "EFFR": "Effective fed funds",
            "DGS2": "2Y vs policy/dots",
            "DGS3MO": "3M bill proxy",
            "DGS6MO": "6M bill forward proxy",
            "FEDTARMD": "SEP dot median",
        },
    },
    "growth_risk": {
        "label": "Growth",
        "headline": "Payrolls, unemployment, claims, manufacturing, retail sales, and JOLTS.",
        "why": (
            "Strong jobs, spending, and production mean the economy can handle higher rates. That "
            "makes Fed cuts less urgent and can push yields up. Weak labor or spending does the "
            "opposite: markets start to price slower growth, safer assets, and easier policy."
        ),
        "caveat": "Growth usually works through a chain: data -> recession risk / Fed path -> curve shape.",
        "subfactors": {
            "PAYEMS": "Nonfarm payrolls",
            "UNRATE": "Unemployment rate",
            "ICSA": "Initial claims",
            "IPMAN": "Manufacturing production",
            "RSAFS": "Retail sales",
            "JTSJOL": "JOLTS openings",
        },
    },
    "liquidity_supply": {
        "label": "Liquidity / Supply",
        "headline": "Fed balance sheet, reserves, RRP, Treasury General Account, and auction stress.",
        "why": (
            "Treasury yields are also a market-clearing price. If there is more Treasury supply or "
            "less cash/liquidity willing to absorb it, buyers may require a higher yield. That is "
            "why this block often matters more for 10Y/30Y term premium than for the policy front end."
        ),
        "caveat": "This is mostly a term-premium channel; it is not the same thing as expected Fed cuts.",
        "subfactors": {
            "WALCL": "Fed balance sheet",
            "WRESBAL": "Bank reserves",
            "RRPONTSYD": "Reverse repo",
            "WTREGEN": "Treasury General Account",
            "treasury_auction_stress": "Auction stress",
        },
    },
    "global_relative_value": {
        "label": "Global Relative Value",
        "headline": "US- Germany 10Y spread, US- Japan 10Y spread, and broad dollar index.",
        "why": (
            "Global investors compare US yields with German/Japanese yields after currency and "
            "hedging costs. If US yields look attractive, demand can cap yields. If the dollar or "
            "hedging cost makes US bonds less attractive, the US yield may need to rise to pull "
            "buyers in."
        ),
        "caveat": "This is a relative-value and capital-flow channel, not a standalone macro forecast.",
        "subfactors": {
            "IRLTLT01DEM156N": "Germany 10Y comparison",
            "IRLTLT01JPM156N": "Japan 10Y comparison",
            "DTWEXBGS": "Broad dollar index",
        },
    },
}


def _factor_blocks(bva: dict[str, Any]) -> list[str]:
    blocks = list(bva.get("macro_blocks", []))
    if blocks:
        return blocks
    seen: list[str] = []
    for horizon in bva.get("horizons", {}).values():
        for target in horizon.get("targets", {}).values():
            for block in target.get("contributions_bp", {}):
                if block not in seen:
                    seen.append(block)
    return seen


def _factor_scenario_data(trajectory: dict[str, Any]) -> dict[str, Any]:
    """Build exact base + selected macro-block contribution data for JS."""
    bva = trajectory.get("metadata", {}).get("base_vs_adjusted") or {}
    horizons = bva.get("horizons", {})
    blocks = _factor_blocks(bva)
    subfactors = {
        block: _FACTOR_DETAILS.get(block, {}).get("subfactors", {}) for block in blocks
    }
    subfactor_weights = {}
    for block, items in subfactors.items():
        weight = 1.0 / len(items) if items else 1.0
        subfactor_weights[block] = {sid: weight for sid in items}
    targets: dict[str, Any] = {}
    for target in CORE_TARGETS:
        points = trajectory.get("tenors", {}).get(target, [])
        random_walk_path = (
            trajectory.get("metadata", {})
            .get("baselines", {})
            .get(target, {})
            .get("random_walk", {})
            .get("path", [])
        )
        if target == "10Y" and not random_walk_path:
            random_walk_path = (
                trajectory.get("metadata", {})
                .get("baselines", {})
                .get("10Y", {})
                .get("random_walk", {})
                .get("path", [])
            )
        months: dict[str, Any] = {}
        for month in range(1, 13):
            point = _month_point(points, month)
            random_walk = (
                random_walk_path[month - 1]
                if len(random_walk_path) >= month
                else point.get("current")
            )
            horizon_cell = (
                horizons.get(str(month), {}).get("targets", {}).get(target, {})
            )
            central = point.get("central")
            base = horizon_cell.get("base", central)
            adjusted = horizon_cell.get("adjusted", central)
            current = point.get("current")
            raw_contrib = horizon_cell.get("contributions_bp", {})
            contributions = {
                block: float(raw_contrib.get(block, 0.0)) for block in blocks
            }
            months[str(month)] = {
                "base": None if base is None else float(base),
                "adjusted": None if adjusted is None else float(adjusted),
                "official": None if central is None else float(central),
                "current": None if current is None else float(current),
                "random_walk": None if random_walk is None else float(random_walk),
                "p10": None if point.get("p10") is None else float(point.get("p10")),
                "p90": None if point.get("p90") is None else float(point.get("p90")),
                "contributions_bp": contributions,
            }
        targets[target] = {"months": months}
    return {
        "blocks": blocks,
        "labels": {block: _BLOCK_LABELS.get(block, block) for block in blocks},
        "subfactors": subfactors,
        "subfactor_weights": subfactor_weights,
        "targets": targets,
    }


def _factor_initial_rows(factor_data: dict[str, Any], target: str = "10Y") -> str:
    rows = []
    target_data = factor_data.get("targets", {}).get(target, {})
    blocks = factor_data.get("blocks", [])
    for month in range(1, 13):
        point = target_data.get("months", {}).get(str(month), {})
        base = point.get("base")
        selected = base
        if selected is not None:
            selected = (
                float(selected)
                + sum(
                    float(point.get("contributions_bp", {}).get(block, 0.0))
                    for block in blocks
                )
                / 100.0
            )
        current = point.get("current")
        delta_bp = (
            (float(selected) - float(current)) * 100.0
            if selected is not None and current is not None
            else None
        )
        rows.append(
            "<tr>"
            f"<th>m{month}</th>"
            f"<td>{_fmt_num(point.get('base'), 3)}</td>"
            f"<td>{_fmt_num(selected, 3)}</td>"
            f"<td>{_fmt_num(point.get('official'), 3)}</td>"
            f"<td>{_fmt_num(point.get('random_walk'), 3)}</td>"
            f"<td>{_fmt_num(delta_bp, 1, 'bp')}</td>"
            f"<td>{_fmt_num(point.get('p10'), 3)} - {_fmt_num(point.get('p90'), 3)}</td>"
            "</tr>"
        )
    return "".join(rows)


def _factor_subfactor_controls(factor_data: dict[str, Any]) -> str:
    cards = []
    available = set(factor_data.get("blocks", []))
    for block, detail in _FACTOR_DETAILS.items():
        subitems = detail.get("subfactors", {})
        disabled = "" if block in available else " disabled"
        checks = "".join(
            "<label class='subfactor-chip'>"
            f'<input type="checkbox" checked{disabled} data-parent-factor="{_esc(block)}" data-subfactor="{_esc(sid)}" />'
            f"<span>{_esc(label)}</span>"
            "</label>"
            for sid, label in subitems.items()
        )
        cards.append(
            "<article class='factor-detail-card'>"
            f"<h3>{_esc(detail.get('label', _BLOCK_LABELS.get(block, block)))}</h3>"
            f"<p><b>Includes:</b> {_esc(detail.get('headline', ''))}</p>"
            f"<p><b>Why it can move yields:</b> {_esc(detail.get('why', ''))}</p>"
            f"<p class='source-line'><b>Transmission caveat:</b> {_esc(detail.get('caveat', ''))}</p>"
            f"<div class='subfactor-grid'>{checks}</div>"
            "</article>"
        )
    return "".join(cards)


def _factor_explorer(trajectory: dict[str, Any]) -> str:
    factor_data = _factor_scenario_data(trajectory)
    blocks = factor_data.get("blocks", [])
    if not blocks:
        return ""
    chips = "".join(
        "<label class='factor-chip'>"
        f'<input type="checkbox" checked data-factor="{_esc(block)}" />'
        f"<span>{_esc(factor_data.get('labels', {}).get(block, block))}</span>"
        "</label>"
        for block in blocks
    )
    options = "".join(
        f"<option value='{_esc(target)}'{(' selected' if target == '10Y' else '')}>{_esc(target)}</option>"
        for target in CORE_TARGETS
    )
    return f"""
    <section class="panel factor-explorer" id="factor-explorer">
      <div class="section-kicker">Interactive Attribution</div>
      <h2>Macro Factor Explorer</h2>
      <div class="plain-english-box">
        <h3>What this means in plain English</h3>
        <p><b>Random-walk curve</b> means "assume the yield does not move at all" for every future month. It is the honest baseline for rates because the long end is hard to beat.</p>
        <p><b>Base</b> means the curve follows its own past shape without macro help. <b>Selected factors</b> means adding only the macro forces you choose below. <b>Official central</b> is selected factors with every macro block turned on.</p>
      </div>
      <div class="factor-toolbar">
        <div class="factor-checks">{chips}</div>
        <label class="target-picker"><span>Target</span><select id="factor-target">{options}</select></label>
      </div>
      <label class="random-walk-toggle"><input type="checkbox" id="factor-show-random-walk" checked /> <span>Show random-walk curve</span></label>
      <details class="factor-breakdown" open>
        <summary>Factor Breakdown</summary>
        <p class="source-line">Category toggles are exact block-level attribution. Sub-factor toggles allocate that block's contribution across its included inputs for explanation-only what-if views; they do not retrain the model or change the official path.</p>
        <div class="factor-detail-grid">{_factor_subfactor_controls(factor_data)}</div>
      </details>
      <div class="factor-layout">
        <div class="factor-chart-shell">
          <svg id="factor-scenario-svg" viewBox="0 0 860 360" role="img" aria-label="Selected macro factor path"></svg>
        </div>
        <div class="factor-summary" id="factor-summary">
          <span>selected 12m</span>
          <b>n/a</b>
          <span>vs today</span>
          <strong>n/a</strong>
        </div>
      </div>
      <table class="factor-table">
        <thead><tr><th>Month</th><th>Base</th><th>Selected factors</th><th>Official central</th><th>Random-walk curve</th><th>vs today</th><th>p10-p90</th></tr></thead>
        <tbody id="factor-monthly-body">{_factor_initial_rows(factor_data)}</tbody>
      </table>
      <p class="source-line">Factor explorer uses exact base-vs-adjusted attribution from the saved trajectory. It is a view-layer what-if; official central and fan bands are unchanged.</p>
    </section>
    """


def _why_it_moves_section(trajectory: dict[str, Any]) -> str:
    factor_data = _factor_scenario_data(trajectory)
    ten_year = factor_data.get("targets", {}).get("10Y", {}).get("months", {})
    month_12 = ten_year.get("12", {})
    contributions = month_12.get("contributions_bp", {})
    rows = []
    for block, value in sorted(
        contributions.items(),
        key=lambda item: abs(float(item[1])),
        reverse=True,
    ):
        detail = _FACTOR_DETAILS.get(block, {})
        direction = "upward pressure" if float(value) > 0 else "downward pressure"
        if abs(float(value)) < 0.05:
            direction = "near neutral"
        rows.append(
            "<tr>"
            f"<th>{_esc(detail.get('label', _BLOCK_LABELS.get(block, block)))}</th>"
            f"<td>{float(value):+.1f}bp</td>"
            f"<td>{_esc(direction)}</td>"
            f"<td>{_esc(detail.get('why', ''))}</td>"
            "</tr>"
        )
    return f"""
    <section class="panel" id="why-it-moves">
      <div class="section-kicker">Mechanism</div>
      <h2>Why It Moves</h2>
      <p class="source-line">These are not simple direct rules. The chain is: released data -> macro block z-score -> fitted ridge transition for Nelson-Siegel level/slope/curvature -> reconstructed tenor path. The table shows the 10Y 12m contribution from each block.</p>
      <table class="driver-table">
        <thead><tr><th>Block</th><th>10Y 12m contribution</th><th>Lean</th><th>Transmission chain</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
    """


def _policy_mapping_data(
    trajectory: dict[str, Any],
    policy_path: dict[str, Any],
) -> dict[str, Any]:
    try:
        cfg = load_yaml("event_overlay").get("fomc_policy_path", {})
    except FileNotFoundError:
        cfg = {}
    next_fomc = next(
        (
            overlay
            for overlay in trajectory.get("metadata", {}).get("event_overlays", [])
            if overlay.get("type") == "FOMC"
        ),
        {},
    )
    month = int(next_fomc.get("month") or 1)
    return {
        "month": month,
        "event_date": str(
            next_fomc.get("event_date") or policy_path.get("next_meeting_date") or ""
        ),
        "cut_prob": policy_path.get("next_meeting_cut_prob"),
        "hike_prob": policy_path.get("next_meeting_hike_prob"),
        "cut_prob_high": float(cfg.get("cut_prob_high", 0.60)),
        "hike_prob_high": float(cfg.get("hike_prob_high", 0.60)),
        "front_end_cut_bp": float(cfg.get("front_end_cut_bp", -12.5)),
        "front_end_hike_bp": float(cfg.get("front_end_hike_bp", 12.5)),
        "base": {
            target: _month_point(
                trajectory.get("tenors", {}).get(target, []), month
            ).get("central")
            for target in ("2Y", "10Y", "2s10s")
        },
    }


def _policy_mapping_panel(
    trajectory: dict[str, Any],
    policy_path: dict[str, Any],
) -> str:
    data = _policy_mapping_data(trajectory, policy_path)
    return f"""
    <section class="panel mapping-sandbox" id="policy-mapping">
      <div class="section-kicker">Config Sandbox</div>
      <h2>Policy Mapping Sandbox</h2>
      <p class="source-line">This shows the current FOMC probability-to-overlay map. Adjusting these fields is an in-page scenario sandbox only; it does not rewrite config or the official path.</p>
      <div class="mapping-controls">
        <label><span>cut probability</span><input id="mapping-cut-prob" type="number" min="0" max="1" step="0.01" value="{_fmt_num(data.get('cut_prob') or 0.0, 2)}" /></label>
        <label><span>hike probability</span><input id="mapping-hike-prob" type="number" min="0" max="1" step="0.01" value="{_fmt_num(data.get('hike_prob') or 0.0, 2)}" /></label>
        <label><span>cut_prob_high</span><input id="mapping-cut-threshold" type="number" min="0" max="1" step="0.01" value="{_fmt_num(data.get('cut_prob_high'), 2)}" /></label>
        <label><span>hike_prob_high</span><input id="mapping-hike-threshold" type="number" min="0" max="1" step="0.01" value="{_fmt_num(data.get('hike_prob_high'), 2)}" /></label>
        <label><span>front_end_cut_bp</span><input id="mapping-cut-step" type="number" step="0.5" value="{_fmt_num(data.get('front_end_cut_bp'), 1)}" /></label>
        <label><span>front_end_hike_bp</span><input id="mapping-hike-step" type="number" step="0.5" value="{_fmt_num(data.get('front_end_hike_bp'), 1)}" /></label>
      </div>
      <table class="driver-table">
        <thead><tr><th>Target</th><th>official central</th><th>sandbox central</th><th>sandbox step</th></tr></thead>
        <tbody id="mapping-result-body"></tbody>
      </table>
      <p class="plain-label">Current rule: if cut probability >= cut_prob_high, apply front_end_cut_bp to 2Y; if hike probability >= hike_prob_high, apply front_end_hike_bp. 10Y is not shifted by this front-end surprise overlay.</p>
    </section>
    """


def _whole_logic_section() -> str:
    return """
    <section class="panel" id="whole-logic">
      <div class="section-kicker">End-to-End Logic</div>
      <h2>Whole Prediction Logic</h2>
      <div class="logic-grid">
        <article><h3>1. What yield means</h3><p>A Treasury yield is the compensation investors require to lend money to the US government. If inflation, policy risk, or supply risk rises, investors may ask for more yield before buying.</p></article>
        <article><h3>2. What data changes</h3><p>Released CPI/PCE, jobs, liquidity, supply, global rates, and Fed tone change the market's story: inflation pressure, Fed cuts/hikes, recession risk, and how hard Treasury supply is to absorb.</p></article>
        <article><h3>3. Base means no-macro FADNS</h3><p>Base means the curve follows its own historical shape dynamics. Random walk means the current yield stays flat. Selected factors means adding only the macro forces you choose on top of base.</p></article>
        <article><h3>4. Why central moves</h3><p>The macro blocks push Nelson-Siegel level/slope/curvature. That becomes 2Y, 10Y, and curve-spread paths. If all selected-factor contributions are on, selected equals official central.</p></article>
        <article><h3>5. Why range widens</h3><p>Unknown future events like CPI/NFP/FOMC/QRA widen uncertainty, not central. p10-p90 is the realistic range around the central view. TraceYield is not an error-correction model.</p></article>
        <article><h3>6. External checks</h3><p>Polymarket, market range, and random-walk baseline ask: does the outside world agree, disagree, or simply say this is a wide uncertain range? They do not tune the model.</p></article>
      </div>
    </section>
    """


def _base_vs_adjusted_section(trajectory: dict[str, Any]) -> str:
    """Show base (no-macro) vs adjusted (macro) + exact per-block bp attribution."""
    bva = trajectory.get("metadata", {}).get("base_vs_adjusted")
    horizons = (bva or {}).get("horizons", {})
    if not bva or not horizons:
        return ""
    blocks = list(bva.get("macro_blocks", []))
    month_key = "6" if "6" in horizons else sorted(horizons, key=lambda m: int(m))[-1]
    targets = horizons.get(month_key, {}).get("targets", {})

    block_heads = "".join(f"<th>{_esc(_BLOCK_LABELS.get(b, b))}</th>" for b in blocks)
    rows = []
    for target in CORE_TARGETS:
        cell = targets.get(target)
        if not cell:
            continue
        base, adj = cell.get("base"), cell.get("adjusted")
        delta_bp = (
            (float(adj) - float(base)) * 100.0
            if base is not None and adj is not None
            else 0.0
        )
        contrib = cell.get("contributions_bp", {})
        contrib_cells = "".join(
            f"<td>{float(contrib.get(b, 0.0)):+.1f}</td>" for b in blocks
        )
        rows.append(
            f"<tr><th>{_esc(target)}</th>"
            f"<td>{_fmt_num(base, 2)}</td>"
            f"<td><b>{_fmt_num(adj, 2)}</b></td>"
            f"<td>{delta_bp:+.1f}</td>"
            f"{contrib_cells}</tr>"
        )

    regime = bva.get("bounded_gpt_regime", {})
    regime_map = regime.get("regime", {})
    regime_state = (
        "live GPT read"
        if regime.get("available")
        else "degraded — neutral (no API key)"
    )
    regime_chips = "".join(
        f"<span class='regime-chip'>{_esc(_BLOCK_LABELS.get(b, b))}: "
        f"<b>{_esc(regime_map.get(b, 'neutral'))}</b></span>"
        for b in blocks
    )
    return f"""
    <section class="panel" id="base-vs-adjusted">
      <div class="section-kicker">Why — Base vs Adjusted</div>
      <h2>Macro augmentation vs base FADNS (at 6m horizon)</h2>
      <p class="source-line">Base = FADNS with no macro. Adjusted = with 5 macro blocks.
      Each block's bp contribution sums exactly to the total change (linearity:
      {_esc(bva.get('linearity_assertion', 'n/a'))}). Magnitudes: {_esc(bva.get('magnitude_source', 'n/a'))}.</p>
      <table class="bva-table">
        <thead><tr><th>Tenor</th><th>Base</th><th>Adjusted</th><th>Δbp</th>{block_heads}</tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
      <h3>Bounded GPT regime ({_esc(regime_state)})</h3>
      <div class="regime-row">{regime_chips}</div>
      <p class="source-line">{_esc(regime.get('rationale', ''))}</p>
    </section>
    """


def _policy_panel(
    policy_path: dict[str, Any], market_confirmation: dict[str, Any] | None
) -> str:
    source = str(policy_path.get("source", "unavailable"))
    confidence = str(policy_path.get("confidence", "low"))
    proxy_note = ""
    if source.endswith("proxy") or confidence == "low":
        proxy_note = '<p class="quality-note">proxy only, low confidence</p>'
    gap = policy_path.get("market_vs_fed_gap_bp")
    if gap is None:
        gap_label = "market-vs-dot gap unavailable"
    elif float(gap) > 0:
        gap_label = f"market prices LESS easing than the dots ({float(gap):+.0f}bp)"
    elif float(gap) < 0:
        gap_label = f"market prices MORE easing than the dots ({float(gap):+.0f}bp)"
    else:
        gap_label = "market aligns with the dot median (0bp gap)"
    dots = policy_path.get("fed_dot_median_path", {})
    market_confirmation = market_confirmation or {}
    agrees = market_confirmation.get("agrees")
    agrees_label = "n/a" if agrees is None else ("agrees" if agrees else "diverges")

    return f"""
    <section class="panel policy-panel" id="policy-path">
      <div class="section-kicker">Policy Path</div>
      <h2>Front-end driver: {_esc(policy_path.get('direction', 'HOLD'))} / {_esc(confidence)}</h2>
      {proxy_note}
      <div class="metric-grid">
        <div><span>3m implied</span><b>{_fmt_num(policy_path.get('implied_policy_rate_3m'))}%</b></div>
        <div><span>6m implied</span><b>{_fmt_num(policy_path.get('implied_policy_rate_6m'))}%</b></div>
        <div><span>12m implied</span><b>{_fmt_num(policy_path.get('implied_policy_rate_12m'))}%</b></div>
        <div><span>Dot median</span><b>{_fmt_num(dots.get('2026'))}%</b></div>
      </div>
      <p class="plain-label">{_esc(gap_label)}</p>
      <p class="source-line">Source: {_esc(source)}. {_esc(policy_path.get('reason', 'No provider reason available.'))}</p>
      <div class="market-row">
        <span>DGS2 {_fmt_num(market_confirmation.get('DGS2'))}%</span>
        <span>DGS5 {_fmt_num(market_confirmation.get('DGS5'))}%</span>
        <span>2s10s {_fmt_num(market_confirmation.get('2s10s'))}</span>
        <span>confirmation: {_esc(agrees_label)}</span>
      </div>
    </section>
    """


def _driver_rows(trajectory: dict[str, Any]) -> str:
    policy = trajectory.get("metadata", {}).get("policy_path", {})
    policy_direction = str(policy.get("direction", "HOLD"))
    front_delta = _p50_delta_bp(trajectory, "2Y", 6)
    long_delta = _p50_delta_bp(trajectory, "10Y", 6)
    curve_delta = _p50_delta_bp(trajectory, "2s10s", 6)
    events = _event_rows(trajectory)
    has_qra = any(str(event.get("event_type", "")).lower() == "qra" for event in events)
    has_cpi = any(
        str(event.get("event_type", "")).lower() in {"cpi", "pce"} for event in events
    )
    has_nfp = any(str(event.get("event_type", "")).lower() == "nfp" for event in events)

    rows = [
        (
            "policy path",
            (
                "down"
                if policy_direction == "EASING"
                else (
                    "up"
                    if policy_direction == "TIGHTENING"
                    else _arrow_from_delta(front_delta)
                )
            ),
            _arrow_from_delta(curve_delta),
            "FRED/probability path drives the front end; low-confidence proxy is labeled when applicable.",
        ),
        (
            "inflation",
            "up" if has_cpi else "flat",
            "up" if has_cpi else "flat",
            "Released CPI/PCE feed the inflation block; upcoming CPI/PCE dates widen the range only.",
        ),
        (
            "growth",
            "up" if has_nfp else "flat",
            _arrow_from_delta(long_delta),
            "Released labor data feed the growth block; upcoming NFP dates add uncertainty only.",
        ),
        (
            "liquidity-supply",
            "flat",
            "up" if has_qra else "flat",
            "Realized Treasury liquidity/auction stress can move central; upcoming QRA dates widen fan only.",
        ),
        (
            "risk-off",
            "down" if long_delta < -5.0 else "flat",
            "down" if long_delta < -5.0 else "flat",
            "Flight-to-quality pressure is a watch item; no news crawler is used here.",
        ),
    ]
    body = "\n".join(
        "<tr>"
        f"<th>{_esc(name)}</th>"
        f"<td>{_arrow_symbol(front)}</td>"
        f"<td>{_arrow_symbol(long)}</td>"
        f"<td>{_esc(reason)}</td>"
        "</tr>"
        for name, front, long, reason in rows
    )
    return f"""
    <section class="panel" id="drivers">
      <div class="section-kicker">Why</div>
      <h2>Driver Why Table</h2>
      <table class="driver-table">
        <thead><tr><th>Input</th><th>front-end lean</th><th>long-end lean</th><th>Reason</th></tr></thead>
        <tbody>{body}</tbody>
      </table>
    </section>
    """


def _bar_style(value: float, max_abs: float) -> str:
    width = 0.0 if max_abs <= 0 else min(100.0, abs(value) / max_abs * 100.0)
    color = "var(--accent-2)" if value >= 0 else "var(--accent)"
    return f"width:{width:.1f}%; background:{color};"


def _base_adjusted_section(trajectory: dict[str, Any]) -> str:
    attribution = trajectory.get("metadata", {}).get("base_vs_adjusted")
    if not attribution:
        return """
        <section class="panel" id="base-adjusted">
          <div class="section-kicker">Attribution</div>
          <h2>Base vs Adjusted</h2>
          <p>Base-vs-adjusted attribution is unavailable in this trajectory.</p>
        </section>
        """

    horizons = attribution.get("horizons", {})
    regime = attribution.get("bounded_gpt_regime", {})
    regime_labels = regime.get("regime", {})
    rows = []
    bar_rows = []
    for month in ("3", "6"):
        targets = horizons.get(month, {}).get("targets", {})
        for target in CORE_TARGETS:
            if target not in targets:
                continue
            item = targets[target]
            rows.append(
                "<tr>"
                f"<th>{_esc(month)}m {target}</th>"
                f"<td>{_fmt_num(item.get('base'), 3)}</td>"
                f"<td>{_fmt_num(item.get('adjusted'), 3)}</td>"
                f"<td>{_fmt_num(item.get('total_delta_bp'), 2, 'bp')}</td>"
                "</tr>"
            )
            contributions = item.get("contributions_bp", {})
            max_abs = max([abs(float(v)) for v in contributions.values()] or [0.0])
            for block, value in contributions.items():
                value = float(value)
                bar_rows.append(
                    '<div class="attrib-row">'
                    f"<span>{_esc(month)}m {target} {_esc(block)}</span>"
                    '<div class="attrib-track">'
                    f'<i style="{_bar_style(value, max_abs)}"></i>'
                    "</div>"
                    f"<b>{value:+.2f}bp</b>"
                    "</div>"
                )

    regime_text = (
        ", ".join(f"{key}: {value}" for key, value in regime_labels.items())
        or "regime unavailable"
    )
    numeric_rule = "Magnitudes come from the fitted transition B matrix; GPT categories do not inject bp."
    return f"""
    <section class="panel" id="base-adjusted">
      <div class="section-kicker">Attribution</div>
      <h2>Base vs Adjusted</h2>
      <p class="plain-label">{_esc(numeric_rule)}</p>
      <p>{_esc(regime_text)}</p>
      <p class="source-line">{_esc(regime.get('rationale', 'No GPT regime rationale available.'))}</p>
      <table class="driver-table">
        <thead><tr><th>Path</th><th>base</th><th>adjusted</th><th>adjusted-base</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
      <div class="attrib-bars">{''.join(bar_rows)}</div>
    </section>
    """


def _timeline(trajectory: dict[str, Any]) -> str:
    items = []
    for event in _event_rows(trajectory):
        event_type = str(event.get("event_type", "")).upper()
        date_label = _event_label(event)
        impact = {
            "FOMC": "policy decision; directional step only if surprise probabilities are high",
            "CPI": "inflation surprise risk; fan widened",
            "PCE": "inflation confirmation risk; fan widened",
            "NFP": "growth and wage-risk print; fan widened",
            "QRA": "supply and term-premium uncertainty; long-end fan widened",
        }.get(event_type, "scheduled event; fan context")
        items.append(
            f"<li><time>{_esc(date_label)}</time><span>{_esc(impact)}</span></li>"
        )
    return f"""
    <section class="panel" id="timeline">
      <div class="section-kicker">Calendar</div>
      <h2>Event Timeline</h2>
      <ol class="timeline">{''.join(items)}</ol>
    </section>
    """


def _grounded_macro_analysis_section(trajectory: dict[str, Any]) -> str:
    analysis = trajectory.get("metadata", {}).get("grounded_macro_analysis")
    if not analysis:
        return """
    <section class="panel" id="grounded-macro-analysis">
      <div class="section-kicker">Grounded Analysis</div>
      <h2>Grounded Macro Analysis</h2>
      <p class="source-line">No grounded macro analysis is attached to this saved trajectory.</p>
    </section>
        """
    doc_rows = "".join(
        "<li>"
        f"{_esc(doc.get('kind'))} {_esc(doc.get('date'))} "
        f"({_fmt_num(doc.get('char_count'), 0)} chars)"
        "</li>"
        for doc in analysis.get("documents_used", [])
    )
    factor_rows = []
    for block, note in (analysis.get("factor_notes") or {}).items():
        if not isinstance(note, dict):
            continue
        data_points = note.get("data_points", [])
        quotes = note.get("quotes", [])
        factor_rows.append(
            "<article class='analysis-factor-card'>"
            f"<h3>{_esc(_BLOCK_LABELS.get(block, block))}: {_esc(note.get('stance', 'n/a'))}</h3>"
            f"<p>{_esc(note.get('reason', ''))}</p>"
            f"<p class='source-line'><b>Data:</b> {_esc('; '.join(str(item) for item in data_points[:4]))}</p>"
            f"<p class='source-line'><b>Quote:</b> {_esc('; '.join(str(item) for item in quotes[:2]))}</p>"
            "</article>"
        )
    chain = "".join(
        f"<li>{_esc(item)}</li>" for item in analysis.get("logic_chain", [])[:8]
    )
    quotes = "".join(
        "<blockquote>"
        f"<p>{_esc(item.get('quote', ''))}</p>"
        f"<cite>{_esc(item.get('source', ''))}</cite>"
        "</blockquote>"
        for item in analysis.get("key_quotes", [])[:6]
        if isinstance(item, dict)
    )
    return f"""
    <section class="panel grounded-analysis" id="grounded-macro-analysis">
      <div class="section-kicker">Grounded Analysis</div>
      <h2>Grounded Macro Analysis</h2>
      <p class="plain-label">{_esc(analysis.get('model_usage', 'narrative only'))}</p>
      <p>{_esc(analysis.get('executive_summary', ''))}</p>
      <div class="analysis-docs"><b>FOMC evidence used:</b><ul>{doc_rows}</ul></div>
      <div class="analysis-grid">{''.join(factor_rows)}</div>
      <h3>Logic chain</h3>
      <ol class="analysis-chain">{chain}</ol>
      <h3>FOMC evidence quotes</h3>
      <div class="quote-grid">{quotes}</div>
    </section>
    """


def _methodology() -> str:
    return """
    <footer class="methodology" id="methodology">
      <h2>Methodology</h2>
      <p>
        This view uses a FADNS-style curve core over Treasury tenors plus macro context,
        empirical historical forecast-error fans, and scheduled-event overlays. Directional
        FOMC nudges are surprise-only; scheduled FOMC, CPI, NFP, PCE, and QRA dates widen
        the fan by quadrature and do not move the center line before the data are known. Once
        CPI/PCE/labor/supply data are released, they enter the macro blocks and can affect the
        central path through the fitted transition. The headline, chart subtitles,
        and estimate table use the macro-adjusted FADNS central path. Historical
        forecast errors are recentered around that central path, so p50 is not a
        separate empirical correction. The Base vs Adjusted panel shows how the
        five macro blocks move the path away from the no-macro base, with each
        block's basis-point contribution summing exactly to the change. The 10Y
        baseline panel compares the model path with a random-walk level and a
        manual/free market-observed range. The Polymarket panel is read-only
        external confirmation; it does not move central, p50, fan bands, event
        overlays, weights, thresholds, or basis-point magnitudes. TraceYield is
        not an error-correction model: it does not estimate a cointegrating
        long-run equilibrium and then force yields back to it. The empirical
        error distribution is used for range only. The long end should be read with a
        random-walk caveat: range and reasons matter more than point precision.
        Inputs are free-data-only. References: arXiv:2601.04608 for the FADNS family;
        Kuttner (2001) and Gürkaynak-Sack-Swanson (2005) for policy-event surprise logic.
      </p>
    </footer>
    """


def _styles() -> str:
    return """
    :root {
      --ink: #1d2228;
      --muted: #64717f;
      --line: #cfd7df;
      --paper: #f4f1ea;
      --panel: #ffffff;
      --accent: #0f6b63;
      --accent-2: #b44d2a;
      --band: rgba(15, 107, 99, 0.16);
      --band-2: rgba(15, 107, 99, 0.28);
      --event: rgba(180, 77, 42, 0.10);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background: var(--paper);
      font-family: "Aptos", "Segoe UI", sans-serif;
      letter-spacing: 0;
    }
    main { max-width: 1180px; margin: 0 auto; padding: 24px; }
    .headline {
      border-top: 5px solid var(--ink);
      border-bottom: 1px solid var(--line);
      padding: 22px 0 18px;
      display: grid;
      grid-template-columns: 1.1fr 1fr;
      gap: 20px;
    }
    .headline h1 {
      margin: 0;
      font-family: "Bahnschrift", "Aptos Display", sans-serif;
      font-size: 36px;
      line-height: 1.05;
      font-weight: 700;
    }
    .headline .readouts { display: grid; gap: 8px; align-content: center; }
    .pill {
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.72);
      padding: 8px 10px;
      border-radius: 4px;
      font-size: 14px;
    }
    .disclaimer { color: var(--accent-2); font-weight: 700; }
    .panel, .chart-card, .methodology {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 18px;
      margin-top: 18px;
    }
    .section-kicker {
      color: var(--accent-2);
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    h2, h3 { margin: 6px 0 12px; letter-spacing: 0; }
    .chart-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
    .featured-chart-grid { display: grid; grid-template-columns: 1fr; gap: 16px; }
    .chart-grid-secondary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .chart-card-featured { padding: 20px; }
    .chart-card-featured .fan-svg { min-height: 420px; }
    .chart-card-featured h3 { font-size: 30px; }
    .chart-head { display: flex; justify-content: space-between; gap: 10px; align-items: baseline; }
    .chart-head span { color: var(--muted); font-size: 13px; }
    .fan-svg { width: 100%; height: auto; display: block; background: #fbfaf6; border: 1px solid #ece5da; }
    .grid { stroke: #e2e6ea; stroke-width: 1; }
    .axis-label { fill: var(--muted); font-size: 11px; }
    .month-label { text-anchor: middle; }
    .band-outer { fill: var(--band); stroke: none; }
    .band-inner { fill: var(--band-2); stroke: none; }
    .central-line { fill: none; stroke: var(--muted); stroke-width: 1.2; stroke-dasharray: 3 3; opacity: 0.7; }
    .p50-line { fill: none; stroke: var(--accent); stroke-width: 2.8; }
    .today-line { stroke: var(--accent-2); stroke-width: 1.3; stroke-dasharray: 6 5; }
    .event-band { fill: var(--event); stroke: rgba(180, 77, 42, 0.20); }
    .event-marker { fill: var(--accent-2); font-size: 12px; font-weight: 800; text-anchor: middle; }
    .legend { display: flex; flex-wrap: wrap; gap: 10px; color: var(--muted); font-size: 12px; margin-top: 8px; }
    .swatch, .stroke { display: inline-block; width: 18px; height: 10px; margin-right: 4px; vertical-align: middle; }
    .swatch.outer { background: var(--band); }
    .swatch.inner { background: var(--band-2); }
    .stroke { border-top: 2px solid var(--ink); height: 4px; }
    .stroke.p50 { border-color: var(--accent); border-top-width: 3px; }
    .stroke.central { border-top-style: dashed; border-color: var(--muted); }
    .stroke.today { border-top-style: dashed; border-color: var(--accent-2); }
    details { margin-top: 14px; }
    summary { cursor: pointer; font-weight: 800; color: var(--accent); }
    .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 12px 0; }
    .metric-grid div, .market-row span {
      border: 1px solid var(--line);
      border-radius: 4px;
      padding: 10px;
      background: #fbfaf6;
    }
    .metric-grid span { display: block; color: var(--muted); font-size: 12px; }
    .metric-grid b { font-size: 22px; }
    .quality-note, .plain-label { font-weight: 800; color: var(--accent-2); }
    .source-line { color: var(--muted); }
    .market-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border-bottom: 1px solid var(--line); padding: 10px 8px; text-align: left; }
    td:nth-child(2), td:nth-child(3) { font-size: 22px; color: var(--accent); }
    .value-table td { text-align: right; font-variant-numeric: tabular-nums; }
    .value-table td b { font-size: 16px; }
    .value-table .range { display: block; color: var(--muted); font-size: 11px; }
    .value-table tbody th { color: var(--muted); font-weight: 700; }
    .bva-table td, .bva-table th { text-align: right; font-variant-numeric: tabular-nums; }
    .bva-table tbody th { text-align: left; color: var(--muted); }
    .bva-table td:nth-child(3) { color: var(--accent); }
    .regime-row { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0 4px; }
    .regime-chip { border: 1px solid var(--line); border-radius: 4px; padding: 6px 10px; background: #fbfaf6; font-size: 13px; }
    .timeline { padding-left: 0; list-style: none; display: grid; gap: 8px; }
    .timeline li { display: grid; grid-template-columns: 190px 1fr; gap: 14px; border-bottom: 1px solid var(--line); padding-bottom: 8px; }
    .timeline time { font-weight: 800; }
    .attrib-bars { display: grid; gap: 8px; margin-top: 14px; }
    .attrib-row { display: grid; grid-template-columns: 210px 1fr 80px; gap: 10px; align-items: center; font-size: 13px; }
    .attrib-track { height: 10px; background: #ece5da; border-radius: 2px; overflow: hidden; }
    .attrib-track i { display: block; height: 100%; }
    .factor-explorer { border-color: #a9c3bd; }
    .plain-english-box {
      border-left: 4px solid var(--accent);
      background: #fbfaf6;
      padding: 12px 14px;
      margin: 10px 0 14px;
    }
    .plain-english-box h3 { margin: 0 0 8px; }
    .plain-english-box p { margin: 6px 0; color: var(--muted); }
    .factor-toolbar {
      display: grid;
      grid-template-columns: 1fr 180px;
      gap: 14px;
      align-items: center;
      margin: 12px 0 16px;
    }
    .factor-checks { display: flex; flex-wrap: wrap; gap: 8px; }
    .factor-chip {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      border: 1px solid var(--line);
      border-radius: 4px;
      padding: 8px 10px;
      background: #fbfaf6;
      font-size: 13px;
      font-weight: 800;
    }
    .factor-chip input { accent-color: var(--accent); }
    .random-walk-toggle {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border: 1px solid var(--line);
      border-radius: 4px;
      padding: 8px 10px;
      background: #fbfaf6;
      font-size: 13px;
      font-weight: 800;
      margin-bottom: 12px;
    }
    .random-walk-toggle input { accent-color: var(--accent-2); }
    .factor-breakdown {
      border: 1px solid #d7dedc;
      border-radius: 6px;
      padding: 12px;
      background: #fcfbf7;
      margin-bottom: 14px;
    }
    .factor-breakdown summary { color: var(--ink); font-size: 18px; }
    .factor-detail-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-top: 10px;
    }
    .factor-detail-card {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px;
      background: white;
    }
    .factor-detail-card h3 { margin-top: 0; }
    .factor-detail-card p { margin: 8px 0; }
    .subfactor-grid { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 10px; }
    .subfactor-chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border: 1px solid #d5ddd9;
      border-radius: 4px;
      padding: 6px 8px;
      background: #f8faf8;
      font-size: 12px;
    }
    .subfactor-chip input { accent-color: var(--accent-2); }
    .target-picker {
      display: grid;
      gap: 4px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
    }
    .target-picker select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 4px;
      padding: 8px;
      background: white;
      color: var(--ink);
      font: inherit;
    }
    .factor-layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 220px;
      gap: 14px;
      align-items: stretch;
    }
    .factor-chart-shell {
      border: 1px solid #d7dedc;
      background: #fbfaf6;
      min-height: 360px;
    }
    #factor-scenario-svg { width: 100%; height: 360px; display: block; }
    .factor-path-selected { fill: none; stroke: var(--accent); stroke-width: 4; }
    .factor-path-official { fill: none; stroke: var(--muted); stroke-width: 2; stroke-dasharray: 6 5; }
    .factor-path-base { fill: none; stroke: var(--accent-2); stroke-width: 2; stroke-dasharray: 3 5; }
    .factor-path-random-walk { fill: none; stroke: #252b31; stroke-width: 1.7; opacity: 0.62; }
    .factor-axis { stroke: #dfe6e3; stroke-width: 1; }
    .factor-axis-label { fill: var(--muted); font-size: 12px; }
    .factor-summary {
      border: 1px solid var(--line);
      background: #fbfaf6;
      border-radius: 4px;
      padding: 14px;
      display: grid;
      align-content: center;
      gap: 8px;
    }
    .factor-summary span { color: var(--muted); font-size: 12px; font-weight: 800; }
    .factor-summary b { font-size: 30px; color: var(--accent); }
    .factor-summary strong { color: var(--accent-2); font-size: 18px; }
    .factor-table { margin-top: 14px; font-variant-numeric: tabular-nums; }
    .factor-table th, .factor-table td { text-align: right; }
    .factor-table th:first-child, .factor-table td:first-child { text-align: left; }
    .mapping-controls {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 10px;
      margin: 12px 0;
    }
    .mapping-controls label {
      display: grid;
      gap: 4px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
    }
    .mapping-controls input {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 4px;
      padding: 8px;
      background: white;
      color: var(--ink);
      font: inherit;
    }
    .logic-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }
    .logic-grid article {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px;
      background: #fbfaf6;
    }
    .logic-grid h3 { font-size: 16px; margin-top: 0; }
    .logic-grid p { color: var(--muted); font-size: 13px; }
    .grounded-analysis { border-color: #98b5ad; }
    .analysis-docs {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px 12px;
      background: #fbfaf6;
      margin: 12px 0;
    }
    .analysis-docs ul { margin: 6px 0 0; padding-left: 20px; }
    .analysis-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      margin-top: 12px;
    }
    .analysis-factor-card {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px;
      background: white;
    }
    .analysis-factor-card h3 { margin-top: 0; }
    .analysis-chain { display: grid; gap: 6px; }
    .quote-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }
    blockquote {
      margin: 0;
      border-left: 4px solid var(--accent-2);
      background: #fbfaf6;
      padding: 10px 12px;
    }
    blockquote p { margin: 0 0 8px; }
    blockquote cite { color: var(--muted); font-size: 12px; }
    .methodology { margin-bottom: 26px; color: var(--muted); }
    @media (max-width: 980px) {
      .headline, .chart-grid, .chart-grid-secondary, .metric-grid, .market-row, .factor-toolbar, .factor-layout, .factor-detail-grid, .mapping-controls, .logic-grid, .analysis-grid, .quote-grid { grid-template-columns: 1fr; }
      main { padding: 14px; }
    }
    """


def _factor_explorer_script() -> str:
    return """
  <script>
  (function () {
    const dataEl = document.getElementById("traceyield-factor-scenario-data");
    const svg = document.getElementById("factor-scenario-svg");
    const targetSelect = document.getElementById("factor-target");
    const showRandomWalk = document.getElementById("factor-show-random-walk");
    const tbody = document.getElementById("factor-monthly-body");
    const summary = document.getElementById("factor-summary");
    if (!dataEl || !svg || !targetSelect || !tbody || !summary) return;

    const scenario = JSON.parse(dataEl.textContent);
    const fmt = (value, digits = 3) => Number.isFinite(value) ? value.toFixed(digits) : "n/a";
    const fmtBp = (value) => Number.isFinite(value) ? `${value >= 0 ? "+" : ""}${value.toFixed(1)}bp` : "n/a";
    const selectedFactors = () => Array.from(document.querySelectorAll("[data-factor]"))
      .filter((input) => input.checked)
      .map((input) => input.dataset.factor);
    const subfactorMultiplier = (factor) => {
      const subInputs = Array.from(document.querySelectorAll(`[data-parent-factor="${factor}"]`));
      if (!subInputs.length) return 1;
      const selectedWeight = subInputs
        .filter((input) => input.checked)
        .reduce((acc, input) => {
          const weight = Number(((scenario.subfactor_weights || {})[factor] || {})[input.dataset.subfactor] || 0);
          return acc + weight;
        }, 0);
      return Math.max(0, Math.min(1, selectedWeight));
    };

    function rowsFor(target, factors) {
      const targetData = scenario.targets[target] || { months: {} };
      return Array.from({ length: 12 }, (_, idx) => {
        const month = String(idx + 1);
        const point = targetData.months[month] || {};
        const base = Number(point.base);
        const contribution = factors.reduce((acc, factor) => {
          const bp = Number((point.contributions_bp || {})[factor] || 0);
          return acc + bp * subfactorMultiplier(factor);
        }, 0);
        const selected = Number.isFinite(base) ? base + contribution / 100 : NaN;
        const current = Number(point.current);
        return {
          month,
          base,
          selected,
          official: Number(point.official),
          current,
          p10: Number(point.p10),
          p90: Number(point.p90),
          randomWalk: Number(point.random_walk),
          deltaBp: Number.isFinite(selected) && Number.isFinite(current) ? (selected - current) * 100 : NaN,
        };
      });
    }

    function pathFor(rows, key, xFor, yFor) {
      return rows
        .filter((row) => Number.isFinite(row[key]))
        .map((row) => `${xFor(Number(row.month))},${yFor(row[key])}`)
        .join(" ");
    }

    function svgNode(name, attrs, text) {
      const node = document.createElementNS("http://www.w3.org/2000/svg", name);
      Object.entries(attrs || {}).forEach(([key, value]) => node.setAttribute(key, value));
      if (text !== undefined) node.textContent = text;
      return node;
    }

    function draw(rows, target) {
      const width = 860;
      const height = 360;
      const left = 58;
      const right = 28;
      const top = 28;
      const bottom = 48;
      const values = rows
        .flatMap((row) => [row.base, row.selected, row.official, showRandomWalk?.checked ? row.randomWalk : NaN])
        .filter(Number.isFinite);
      let low = Math.min(...values);
      let high = Math.max(...values);
      if (!Number.isFinite(low) || !Number.isFinite(high)) return;
      if (Math.abs(high - low) < 0.001) {
        low -= 0.25;
        high += 0.25;
      }
      const pad = (high - low) * 0.12;
      low -= pad;
      high += pad;
      const xFor = (month) => left + ((month - 1) * (width - left - right)) / 11;
      const yFor = (value) => top + ((high - value) * (height - top - bottom)) / (high - low);
      svg.replaceChildren();
      svg.appendChild(svgNode("rect", { x: 0, y: 0, width, height, fill: "#fbfaf6" }));
      [low, (low + high) / 2, high].forEach((tick) => {
        const y = yFor(tick);
        svg.appendChild(svgNode("line", { x1: left, x2: width - right, y1: y, y2: y, class: "factor-axis" }));
        svg.appendChild(svgNode("text", { x: 12, y: y + 4, class: "factor-axis-label" }, tick.toFixed(2)));
      });
      rows.forEach((row) => {
        const x = xFor(Number(row.month));
        svg.appendChild(svgNode("text", { x, y: height - 12, class: "factor-axis-label", "text-anchor": "middle" }, row.month));
      });
      svg.appendChild(svgNode("polyline", { points: pathFor(rows, "base", xFor, yFor), class: "factor-path-base" }));
      if (showRandomWalk?.checked) {
        svg.appendChild(svgNode("polyline", { points: pathFor(rows, "randomWalk", xFor, yFor), class: "factor-path-random-walk" }));
      }
      svg.appendChild(svgNode("polyline", { points: pathFor(rows, "official", xFor, yFor), class: "factor-path-official" }));
      svg.appendChild(svgNode("polyline", { points: pathFor(rows, "selected", xFor, yFor), class: "factor-path-selected" }));
      svg.appendChild(svgNode("text", { x: left, y: 18, class: "factor-axis-label" }, `${target} selected factors`));
      svg.appendChild(svgNode("text", { x: width - 390, y: 18, class: "factor-axis-label" }, "solid=selected dashed=official dotted=base thin=random-walk"));
    }

    function renderTable(rows) {
      tbody.innerHTML = rows.map((row) => `
        <tr>
          <th>m${row.month}</th>
          <td>${fmt(row.base)}</td>
          <td><b>${fmt(row.selected)}</b></td>
          <td>${fmt(row.official)}</td>
          <td>${fmt(row.randomWalk)}</td>
          <td>${fmtBp(row.deltaBp)}</td>
          <td>${fmt(row.p10)} - ${fmt(row.p90)}</td>
        </tr>
      `).join("");
    }

    function renderSummary(rows) {
      const last = rows[rows.length - 1] || {};
      summary.innerHTML = `
        <span>selected 12m</span>
        <b>${fmt(last.selected)}</b>
        <span>vs today</span>
        <strong>${fmtBp(last.deltaBp)}</strong>
      `;
    }

    window.updateFactorScenario = function updateFactorScenario() {
      const target = targetSelect.value;
      const rows = rowsFor(target, selectedFactors());
      draw(rows, target);
      renderTable(rows);
      renderSummary(rows);
    };

    document.querySelectorAll("[data-factor]").forEach((input) => {
      input.addEventListener("change", window.updateFactorScenario);
    });
    document.querySelectorAll("[data-subfactor]").forEach((input) => {
      input.addEventListener("change", window.updateFactorScenario);
    });
    targetSelect.addEventListener("change", window.updateFactorScenario);
    showRandomWalk?.addEventListener("change", window.updateFactorScenario);
    window.updateFactorScenario();
  }());
  </script>
    """


def _policy_mapping_script() -> str:
    return """
  <script>
  (function () {
    const dataEl = document.getElementById("traceyield-policy-mapping-data");
    const body = document.getElementById("mapping-result-body");
    if (!dataEl || !body) return;
    const data = JSON.parse(dataEl.textContent);
    const num = (id) => Number(document.getElementById(id)?.value || 0);
    const fmt = (value, digits = 3) => Number.isFinite(value) ? value.toFixed(digits) : "n/a";
    const fmtBp = (value) => Number.isFinite(value) ? `${value >= 0 ? "+" : ""}${value.toFixed(1)}bp` : "n/a";

    window.updatePolicyMappingSandbox = function updatePolicyMappingSandbox() {
      const cutProb = num("mapping-cut-prob");
      const hikeProb = num("mapping-hike-prob");
      const cutThreshold = num("mapping-cut-threshold");
      const hikeThreshold = num("mapping-hike-threshold");
      const cutStep = num("mapping-cut-step");
      const hikeStep = num("mapping-hike-step");
      let step = 0;
      if (cutProb >= cutThreshold) step = cutStep;
      else if (hikeProb >= hikeThreshold) step = hikeStep;
      const rows = ["2Y", "10Y", "2s10s"].map((target) => {
        const official = Number((data.base || {})[target]);
        let sandbox = official;
        let targetStep = 0;
        if (target === "2Y") targetStep = step;
        if (target === "2s10s") targetStep = -step;
        if (Number.isFinite(official)) sandbox = official + targetStep / 100;
        return `
          <tr>
            <th>${target}</th>
            <td>${fmt(official)}</td>
            <td><b>${fmt(sandbox)}</b></td>
            <td>${fmtBp(targetStep)}</td>
          </tr>
        `;
      });
      body.innerHTML = rows.join("");
    };
    ["mapping-cut-prob", "mapping-hike-prob", "mapping-cut-threshold", "mapping-hike-threshold", "mapping-cut-step", "mapping-hike-step"].forEach((id) => {
      document.getElementById(id)?.addEventListener("input", window.updatePolicyMappingSandbox);
    });
    window.updatePolicyMappingSandbox();
  }());
  </script>
    """


def _market_confirmation_from_cache(
    trajectory: dict[str, Any],
    policy_path: dict[str, Any],
) -> dict[str, Any] | None:
    try:
        cached = sorted((DATA / "processed").glob("fred_*.parquet"))
        if not cached:
            return None
        df = pd.read_parquet(cached[-1])
        df.index = pd.to_datetime(df.index)
        return market_confirmation_row(df, policy_path, as_of=trajectory.get("as_of"))
    except Exception:  # noqa: BLE001 - report must degrade rather than crash.
        return None


def render_report_html(
    trajectory: dict[str, Any],
    *,
    market_confirmation: dict[str, Any] | None = None,
) -> str:
    """Render one self-contained HTML curve report."""
    policy_path = trajectory.get("metadata", {}).get("policy_path") or {
        "source": "policy_path_unavailable",
        "direction": "HOLD",
        "confidence": "low",
        "reason": "Policy-path metadata unavailable in saved trajectory.",
    }
    if market_confirmation is None:
        market_confirmation = _market_confirmation_from_cache(trajectory, policy_path)
    headline = _headline(trajectory)
    chart_json = json.dumps(_chart_data(trajectory), separators=(",", ":"))
    factor_scenario_json = json.dumps(
        _factor_scenario_data(trajectory),
        separators=(",", ":"),
    )
    policy_mapping_json = json.dumps(
        _policy_mapping_data(trajectory, policy_path),
        separators=(",", ":"),
    )

    html_out = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>TraceYield Curve View - {_esc(trajectory.get('as_of'))}</title>
  <style>{_styles()}</style>
</head>
<body>
<main>
  <section class="headline">
    <div>
      <div class="section-kicker">TraceYield Curve View</div>
      <h1>{_esc(headline['ten_year'])}</h1>
      <p class="disclaimer">Scenario view with uncertainty; not a trading signal.</p>
    </div>
    <div class="readouts">
      <div class="pill">As of {_esc(trajectory.get('as_of'))}</div>
      <div class="pill">{_esc(headline['three_month'])}</div>
      <div class="pill">{_esc(headline['six_month'])}</div>
    </div>
  </section>

  {_fan_charts_section(trajectory)}
  {_value_table(trajectory)}
  {_baseline_panel(trajectory)}
  {_polymarket_panel(trajectory)}
  {_factor_explorer(trajectory)}
  {_why_it_moves_section(trajectory)}
  {_policy_mapping_panel(trajectory, policy_path)}
  {_base_vs_adjusted_section(trajectory)}
  {_policy_panel(policy_path, market_confirmation)}
  {_base_adjusted_section(trajectory)}
  {_driver_rows(trajectory)}
  {_timeline(trajectory)}
  {_whole_logic_section()}
  {_grounded_macro_analysis_section(trajectory)}
  {_methodology()}
  <script type="application/json" id="traceyield-chart-data">{chart_json}</script>
  <script type="application/json" id="traceyield-factor-scenario-data">{factor_scenario_json}</script>
  <script type="application/json" id="traceyield-policy-mapping-data">{policy_mapping_json}</script>
  {_factor_explorer_script()}
  {_policy_mapping_script()}
</main>
</body>
</html>
"""
    lowered = html_out.lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in lowered:
            raise ValueError(f"Forbidden report phrase present: {phrase}")
    return html_out


def save_html_report(
    trajectory: dict[str, Any],
    *,
    output_dir: str | Path = DATA / "reports",
    market_confirmation: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    """Write dated and latest self-contained HTML report copies."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    as_of = pd.Timestamp(trajectory["as_of"]).date()
    html_out = render_report_html(
        trajectory,
        market_confirmation=market_confirmation,
    )
    dated = out_dir / f"curve_report_{as_of:%Y%m%d}.html"
    latest = out_dir / "curve_latest.html"
    dated.write_text(html_out, encoding="utf-8")
    latest.write_text(html_out, encoding="utf-8")
    return dated, latest


def render_file_to_html(
    trajectory_path: str | Path,
    *,
    output_dir: str | Path = DATA / "reports",
) -> tuple[Path, Path]:
    """Render a saved trajectory JSON into dated/latest HTML files."""
    return save_html_report(load_trajectory(trajectory_path), output_dir=output_dir)
