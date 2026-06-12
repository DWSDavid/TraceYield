"""Forward one-year UST curve trajectory view built on the existing FADNS core."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from src.backtest.eval import TARGETS, forward_curve_targets
from src.models.fadns import (
    _curve_from_betas,
    _forecast_beta,
    _point_in_time_inputs,
    _prediction_from_forecast,
    _ridge_transition,
    build_macro_block_ic_scorecard,
    build_fadns_prediction_frames,
    forecast_base_adjusted_attribution,
    realized_macro_data_audit,
    run_macro_block_ic_sanity,
    summarize_macro_block_sanity,
)
from src.signals.grounded_macro_analysis import attach_grounded_macro_analysis
from src.signals.polymarket_check import attach_polymarket_check
from src.signals.regime_gpt import bounded_regime_read
from src.signals.policy_path import merge_policy_paths
from src.utils.config import DATA, load_yaml

DEFAULT_MONTHS = tuple(range(1, 13))
MONTH_TRADING_DAYS = 21
QUANTILE_LABELS = {
    0.10: "p10",
    0.25: "p25",
    0.50: "p50",
    0.75: "p75",
    0.90: "p90",
}


def _prepare_history(df: pd.DataFrame) -> pd.DataFrame:
    history = df.copy()
    history.index = pd.to_datetime(history.index)
    return history.sort_index()


def _month_horizons(months: tuple[int, ...]) -> dict[str, int]:
    return {f"m{month:02d}": int(month * MONTH_TRADING_DAYS) for month in months}


def _latest_forecast_date(betas: pd.DataFrame, history: pd.DataFrame) -> pd.Timestamp:
    max_forecast_date = pd.Timestamp(history.index.max())
    available = betas.loc[:max_forecast_date]
    if available.empty:
        raise ValueError("FADNS has no point-in-time beta history for the input data.")
    return pd.Timestamp(available.index[-1])


def _current_levels(current_beta: Any) -> dict[str, float]:
    curve = _curve_from_betas(current_beta)
    return {
        **curve,
        "2s10s": float(curve["10Y"] - curve["2Y"]),
        "5s30s": float(curve["30Y"] - curve["5Y"]),
    }


def _latest_fadns_changes(
    history: pd.DataFrame,
    months: tuple[int, ...],
    *,
    min_train: int,
    ridge_alpha: float,
) -> tuple[
    pd.Timestamp,
    dict[str, float],
    dict[int, dict[str, float]],
    dict[str, Any],
]:
    betas, macro = _point_in_time_inputs(history)
    as_of = _latest_forecast_date(betas, history)
    train_betas = betas.loc[:as_of]
    if len(train_betas) < min_train:
        raise ValueError(
            f"Need at least {min_train} FADNS beta observations; "
            f"found {len(train_betas)}."
        )

    train_macro = macro.reindex(train_betas.index).fillna(0.0)
    coefficients = _ridge_transition(
        train_betas,
        train_macro,
        alpha=ridge_alpha,
    )
    if coefficients is None:
        raise ValueError("Could not fit FADNS transition from the available history.")

    current_beta = train_betas.iloc[-1].to_numpy(dtype=float)
    current_macro = train_macro.iloc[-1].to_numpy(dtype=float)
    changes_by_month = {}
    attribution_by_month: dict[str, Any] = {}
    for month, horizon_days in _month_horizons(months).items():
        month_number = int(month[1:])
        forecast_beta = _forecast_beta(
            coefficients,
            current_beta,
            current_macro,
            horizon_days,
        )
        changes_by_month[month_number] = _prediction_from_forecast(
            current_beta,
            forecast_beta,
        )
        attribution_by_month[str(month_number)] = forecast_base_adjusted_attribution(
            coefficients,
            current_beta,
            current_macro,
            macro_columns=list(train_macro.columns),
            horizon_days=horizon_days,
        )

    return (
        as_of,
        _current_levels(current_beta),
        changes_by_month,
        {
            "macro_blocks": list(train_macro.columns),
            "linearity_assertion": "passed",
            "horizons": attribution_by_month,
            "bounded_gpt_regime": bounded_regime_read(as_of=as_of.date().isoformat()),
            "magnitude_source": "fitted ridge transition B matrix; GPT categories do not inject bp",
        },
    )


def _safe_quantile(value: float) -> float:
    if pd.isna(value):
        return 0.0
    return float(value)


def _monotone_error_quantiles(
    raw: dict[str, dict[int, dict[str, float]]],
    months: tuple[int, ...],
) -> dict[str, dict[int, dict[str, float]]]:
    out: dict[str, dict[int, dict[str, float]]] = {target: {} for target in TARGETS}
    for target in TARGETS:
        running_lower = {"p10": float("inf"), "p25": float("inf")}
        running_upper = {"p75": float("-inf"), "p90": float("-inf")}
        for month in months:
            point = raw[target][month]
            for label in running_lower:
                running_lower[label] = min(running_lower[label], point[label])
            for label in running_upper:
                running_upper[label] = max(running_upper[label], point[label])
            out[target][month] = {
                "p10": running_lower["p10"],
                "p25": running_lower["p25"],
                "p50": point["p50"],
                "p75": running_upper["p75"],
                "p90": running_upper["p90"],
            }
    return out


def _historical_error_quantiles(
    history: pd.DataFrame,
    months: tuple[int, ...],
    *,
    start: str,
    min_train: int,
    ridge_alpha: float,
) -> dict[str, dict[int, dict[str, float]]]:
    horizons = _month_horizons(months)
    prediction_frames = build_fadns_prediction_frames(
        history,
        start=start,
        horizons=horizons,
        min_train=min_train,
        ridge_alpha=ridge_alpha,
    )

    raw: dict[str, dict[int, dict[str, float]]] = {target: {} for target in TARGETS}
    for key, horizon_days in horizons.items():
        month = int(key[1:])
        predictions = prediction_frames[key]
        realized = forward_curve_targets(history, horizon_days)
        for target in TARGETS:
            if predictions.empty or target not in predictions or target not in realized:
                quantiles = pd.Series(dtype=float)
            else:
                aligned_realized = realized[target].reindex(predictions.index)
                errors = (aligned_realized - predictions[target]).dropna()
                quantiles = errors.quantile(list(QUANTILE_LABELS))
                if not quantiles.empty:
                    median_error = float(quantiles.get(0.50, 0.0) or 0.0)
                    quantiles = quantiles - median_error
            raw[target][month] = {
                label: _safe_quantile(quantiles.get(q))
                for q, label in QUANTILE_LABELS.items()
            }

    return _monotone_error_quantiles(raw, months)


def _baseline_metadata(current_levels: dict[str, float]) -> dict[str, Any]:
    try:
        market_cfg = load_yaml("market_ranges").get("ten_year", {})
    except FileNotFoundError:
        market_cfg = {}
    current_10y = round(float(current_levels["10Y"]), 6)
    return {
        "10Y": {
            "random_walk": {
                "level": current_10y,
                "path": [current_10y for _ in DEFAULT_MONTHS],
                "reason": "Random-walk baseline holds the current 10Y level flat.",
            },
            "market_range": {
                "low": float(market_cfg.get("low", 3.90)),
                "high": float(market_cfg.get("high", 4.80)),
                "source": str(market_cfg.get("source", "manual_market_observed")),
                "as_of": str(market_cfg.get("as_of", "")),
                "reason": str(
                    market_cfg.get(
                        "reason",
                        "Manual/free market-observed 10Y range placeholder.",
                    )
                ),
            },
        }
    }


def build_curve_trajectory(
    df: pd.DataFrame,
    *,
    start: str = "2015-01-01",
    months: tuple[int, ...] = DEFAULT_MONTHS,
    min_train: int = 756,
    ridge_alpha: float = 10.0,
    policy_path: dict[str, Any] | None = None,
    macro_block_sanity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the latest 12-month FADNS level path with empirical error bands."""
    history = _prepare_history(df)
    months = tuple(int(month) for month in months)
    as_of, current_levels, changes, base_vs_adjusted = _latest_fadns_changes(
        history,
        months,
        min_train=min_train,
        ridge_alpha=ridge_alpha,
    )
    if macro_block_sanity is None:
        macro_block_sanity = summarize_macro_block_sanity(
            build_macro_block_ic_scorecard(history, start=start)
        )
    base_vs_adjusted["macro_block_sanity"] = macro_block_sanity
    error_quantiles = _historical_error_quantiles(
        history,
        months,
        start=start,
        min_train=min_train,
        ridge_alpha=ridge_alpha,
    )

    tenors: dict[str, list[dict[str, float | int]]] = {target: [] for target in TARGETS}
    horizons = _month_horizons(months)
    for target in TARGETS:
        current = round(float(current_levels[target]), 6)
        for key, horizon_days in horizons.items():
            month = int(key[1:])
            change_pct = round(float(changes[month][target]), 6)
            central = round(current + change_pct, 6)
            point: dict[str, float | int] = {
                "month": month,
                "horizon_days": horizon_days,
                "current": current,
                "central": central,
                "delta_bp": round(change_pct * 100.0, 6),
            }
            for label, offset in error_quantiles[target][month].items():
                point[label] = round(central + float(offset), 6)
            tenors[target].append(point)

    trajectory = {
        "as_of": as_of.date().isoformat(),
        "tenors": tenors,
        "metadata": {
            "model": "fadns",
            "month_trading_days": MONTH_TRADING_DAYS,
            "error_definition": "realized_change_minus_predicted_change",
            "uncertainty": (
                "empirical historical FADNS forecast-error quantiles, recentered "
                "around the macro-adjusted central path"
            ),
            "fan_center": "central_fadns_macro_adjusted",
            "fan_quantiles": list(QUANTILE_LABELS.values()),
            "baselines": _baseline_metadata(current_levels),
            "realized_macro_data_audit": realized_macro_data_audit(
                history,
                as_of=as_of,
            ),
            "base_vs_adjusted": base_vs_adjusted,
        },
    }
    if policy_path is not None:
        stepped = apply_policy_event_overlay(trajectory, policy_path=policy_path)
        return apply_event_uncertainty_overlay(stepped, as_of=trajectory["as_of"])
    return trajectory


def _event_month(as_of: Any, event_date: Any) -> int | None:
    asof_date = pd.Timestamp(as_of).date()
    event = pd.Timestamp(event_date).date()
    if event < asof_date:
        return None
    month = (event.year - asof_date.year) * 12 + event.month - asof_date.month
    month = max(1, month)
    return month if month <= 12 else None


def _overlay_step_bp(
    policy_path: dict[str, Any],
    cfg: dict[str, Any],
) -> tuple[float, str]:
    cut_prob = policy_path.get("next_meeting_cut_prob")
    hike_prob = policy_path.get("next_meeting_hike_prob")
    cut_prob = float(cut_prob) if cut_prob is not None else 0.0
    hike_prob = float(hike_prob) if hike_prob is not None else 0.0
    source = str(policy_path.get("source", "policy_path"))

    if cut_prob >= float(cfg.get("cut_prob_high", 1.0)):
        step_bp = float(cfg.get("front_end_cut_bp", 0.0))
        template = cfg.get("reason_template", "{source}: {step_bp:+.1f}bp")
    elif hike_prob >= float(cfg.get("hike_prob_high", 1.0)):
        step_bp = float(cfg.get("front_end_hike_bp", 0.0))
        template = cfg.get("reason_template", "{source}: {step_bp:+.1f}bp")
    else:
        step_bp = 0.0
        template = cfg.get("no_step_reason_template", "{source}: {step_bp:+.1f}bp")

    reason = template.format(
        source=source,
        cut_prob=cut_prob,
        hike_prob=hike_prob,
        step_bp=step_bp,
        direction=policy_path.get("direction", "HOLD"),
        market_vs_fed_gap_bp=policy_path.get("market_vs_fed_gap_bp"),
    )
    return step_bp, reason


def _shift_point(point: dict[str, Any], step_bp: float, reason: str) -> None:
    shift = float(step_bp) / 100.0
    point.setdefault("base_central", point["central"])
    point["central"] = round(float(point["central"]) + shift, 6)
    point["delta_bp"] = round(float(point["delta_bp"]) + float(step_bp), 6)
    for label in QUANTILE_LABELS.values():
        if label in point:
            point[label] = round(float(point[label]) + shift, 6)
    point["overlay_bp"] = round(float(point.get("overlay_bp", 0.0)) + step_bp, 6)
    point.setdefault("overlay_reasons", []).append(reason)


def apply_policy_event_overlay(
    trajectory: dict[str, Any],
    *,
    policy_path: dict[str, Any],
    overlay_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply a configured policy-path event overlay to the next FOMC month."""
    adjusted = copy.deepcopy(trajectory)
    cfg = (overlay_config or load_yaml("event_overlay")).get("fomc_policy_path", {})
    event_date = policy_path.get("next_meeting_date")
    month = _event_month(adjusted["as_of"], event_date) if event_date else None
    if month is None:
        adjusted.setdefault("metadata", {}).setdefault("event_overlays", []).append(
            {
                "type": "FOMC",
                "month": None,
                "step_bp": 0.0,
                "reason": "No upcoming FOMC meeting falls inside the 12-month path.",
            }
        )
        return adjusted

    step_bp, reason = _overlay_step_bp(policy_path, cfg)
    targets = cfg.get("targets", {"2Y": 1.0})
    overlay_rows = []
    for target, multiplier in targets.items():
        if target not in adjusted["tenors"]:
            continue
        target_step = float(step_bp) * float(multiplier)
        point = adjusted["tenors"][target][month - 1]
        _shift_point(point, target_step, reason)
        overlay_rows.append({"target": target, "step_bp": round(target_step, 6)})

        if target == "2Y" and "2s10s" in adjusted["tenors"]:
            spread_point = adjusted["tenors"]["2s10s"][month - 1]
            _shift_point(spread_point, -target_step, reason)
            overlay_rows.append({"target": "2s10s", "step_bp": round(-target_step, 6)})
        if target == "5Y" and "5s30s" in adjusted["tenors"]:
            spread_point = adjusted["tenors"]["5s30s"][month - 1]
            _shift_point(spread_point, -target_step, reason)
            overlay_rows.append({"target": "5s30s", "step_bp": round(-target_step, 6)})

    adjusted.setdefault("metadata", {}).setdefault("event_overlays", []).append(
        {
            "type": "FOMC",
            "event_date": pd.Timestamp(event_date).date().isoformat(),
            "month": month,
            "source": policy_path.get("source"),
            "direction": policy_path.get("direction"),
            "step_bp": round(float(step_bp), 6),
            "targets": overlay_rows,
            "reason": reason,
        }
    )
    adjusted["metadata"]["policy_path"] = {
        key: value.isoformat() if hasattr(value, "isoformat") else value
        for key, value in policy_path.items()
    }
    return adjusted


def _calendar_month_events(
    *,
    as_of: Any,
    widen_cfg: dict[str, Any],
    fomc_cal: dict[str, Any] | None,
    release_cal: dict[str, Any] | None,
) -> dict[int, list[dict[str, Any]]]:
    fomc_calendar = fomc_cal if fomc_cal is not None else load_yaml("fomc_calendar")
    release_calendar = (
        release_cal if release_cal is not None else load_yaml("data_release_calendar")
    )
    month_events: dict[int, list[dict[str, Any]]] = {}

    if "fomc" in widen_cfg:
        for item in fomc_calendar.get("meetings", []):
            event_date = item.get("decision_date")
            month = _event_month(as_of, event_date) if event_date else None
            if month is None:
                continue
            month_events.setdefault(month, []).append(
                {
                    "event_type": "fomc",
                    "release_date": pd.Timestamp(event_date).date().isoformat(),
                    "precision": "confirmed",
                    "has_sep": bool(item.get("has_sep", False)),
                }
            )

    for item in release_calendar.get("releases", []):
        event_type = str(item.get("indicator", "")).lower()
        if event_type not in widen_cfg:
            continue
        event_date = item.get("release_date")
        month = _event_month(as_of, event_date) if event_date else None
        if month is None:
            continue
        month_events.setdefault(month, []).append(
            {
                "event_type": event_type,
                "release_date": pd.Timestamp(event_date).date().isoformat(),
                "reference_month": item.get("reference_month"),
                "precision": str(item.get("precision", "unknown")),
            }
        )

    return {
        month: sorted(events, key=lambda event: event["release_date"])
        for month, events in sorted(month_events.items())
    }


def _event_width_bp(
    event_type: str,
    target: str,
    widen_cfg: dict[str, Any],
) -> float:
    widths = widen_cfg.get(event_type, {})
    if target in widths:
        return float(widths[target])
    if target == "2s10s":
        return math.sqrt(
            float(widths.get("2Y", 0.0)) ** 2 + float(widths.get("10Y", 0.0)) ** 2
        )
    if target == "5s30s":
        return math.sqrt(
            float(widths.get("5Y", 0.0)) ** 2 + float(widths.get("30Y", 0.0)) ** 2
        )
    return 0.0


def _combined_widen_bp(
    events: list[dict[str, Any]],
    target: str,
    widen_cfg: dict[str, Any],
) -> float:
    return math.sqrt(
        sum(
            _event_width_bp(str(event["event_type"]), target, widen_cfg) ** 2
            for event in events
        )
    )


def _format_event_for_reason(event: dict[str, Any]) -> str:
    event_date = pd.Timestamp(event["release_date"]).date()
    label = str(event["event_type"]).upper()
    precision = str(event.get("precision", "")).lower()
    suffix = ", date estimated" if precision == "estimated" else ""
    return f"{label} ({event_date.month}/{event_date.day:02d}{suffix})"


def _uncertainty_reason(events: list[dict[str, Any]]) -> str:
    first_date = pd.Timestamp(events[0]["release_date"])
    event_labels = " + ".join(_format_event_for_reason(event) for event in events)
    return (
        f"{first_date.strftime('%b %Y')} contains {event_labels}; "
        "fan widened by configured event uncertainty."
    )


def _widen_point(point: dict[str, Any], widen_bp: float, reason: str) -> None:
    widen = float(widen_bp) / 100.0
    point["p10"] = round(float(point["p10"]) - widen, 6)
    point["p25"] = round(float(point["p25"]) - 0.5 * widen, 6)
    point["p75"] = round(float(point["p75"]) + 0.5 * widen, 6)
    point["p90"] = round(float(point["p90"]) + widen, 6)
    point["uncertainty_widen_bp"] = round(float(widen_bp), 6)
    point.setdefault("overlay_reasons", []).append(reason)


def _enforce_monotone_fan_widths(points: list[dict[str, Any]]) -> None:
    running_p10_p90_width = 0.0
    running_p25_p75_width = 0.0
    for point in points:
        p10_p90_width = float(point["p90"]) - float(point["p10"])
        if p10_p90_width < running_p10_p90_width:
            add = (running_p10_p90_width - p10_p90_width) / 2.0
            point["p10"] = round(float(point["p10"]) - add, 6)
            point["p90"] = round(float(point["p90"]) + add, 6)
        else:
            running_p10_p90_width = p10_p90_width

        p25_p75_width = float(point["p75"]) - float(point["p25"])
        if p25_p75_width < running_p25_p75_width:
            add = (running_p25_p75_width - p25_p75_width) / 2.0
            point["p25"] = round(float(point["p25"]) - add, 6)
            point["p75"] = round(float(point["p75"]) + add, 6)
        else:
            running_p25_p75_width = p25_p75_width


def apply_event_uncertainty_overlay(
    trajectory: dict[str, Any],
    *,
    as_of: Any,
    overlay_config: dict[str, Any] | None = None,
    fomc_cal: dict[str, Any] | None = None,
    release_cal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Symmetrically widen fan bands for scheduled events without moving central."""
    adjusted = copy.deepcopy(trajectory)
    cfg = overlay_config or load_yaml("event_overlay")
    widen_cfg = cfg.get("uncertainty_widen_bp", {})
    if not widen_cfg:
        return adjusted
    combine = cfg.get("combine", "sqrt_sum_of_squares")
    if combine != "sqrt_sum_of_squares":
        raise ValueError(f"Unsupported uncertainty fan combine mode: {combine}")

    month_events = _calendar_month_events(
        as_of=as_of,
        widen_cfg=widen_cfg,
        fomc_cal=fomc_cal,
        release_cal=release_cal,
    )
    month_widen: dict[str, dict[str, float]] = {}
    metadata = adjusted.setdefault("metadata", {})
    metadata.setdefault("event_overlays", [])

    for month, events in month_events.items():
        reason = _uncertainty_reason(events)
        widen_by_target: dict[str, float] = {}
        for target, points in adjusted.get("tenors", {}).items():
            if month > len(points):
                continue
            widen_bp = round(_combined_widen_bp(events, target, widen_cfg), 6)
            if widen_bp <= 0.0:
                continue
            _widen_point(points[month - 1], widen_bp, reason)
            widen_by_target[target] = widen_bp

        if widen_by_target:
            month_widen[str(month)] = widen_by_target
            metadata["event_overlays"].append(
                {
                    "type": "UNCERTAINTY",
                    "month": month,
                    "events": events,
                    "widen_bp": widen_by_target,
                    "combine": combine,
                    "reason": reason,
                }
            )

    for points in adjusted.get("tenors", {}).values():
        _enforce_monotone_fan_widths(points)

    metadata["event_uncertainty"] = {
        "combine": combine,
        "month_events": {str(month): events for month, events in month_events.items()},
        "widen_bp": month_widen,
    }
    return adjusted


def trajectory_to_frame(trajectory: dict[str, Any]) -> pd.DataFrame:
    """Flatten the JSON trajectory contract into one row per target-month."""
    rows = []
    as_of = trajectory["as_of"]
    for target, points in trajectory["tenors"].items():
        for point in points:
            rows.append({"as_of": as_of, "target": target, **point})
    return pd.DataFrame(rows)


def save_curve_trajectory(
    trajectory: dict[str, Any],
    *,
    output_dir: str | Path = DATA / "forecasts",
) -> tuple[Path, Path]:
    """Persist the trajectory contract as JSON plus a flat CSV."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    as_of = str(trajectory["as_of"]).replace("-", "")
    json_path = output_dir / f"curve_trajectory_{as_of}.json"
    csv_path = output_dir / f"curve_trajectory_{as_of}.csv"
    json_path.write_text(
        json.dumps(trajectory, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    trajectory_to_frame(trajectory).to_csv(csv_path, index=False)
    return json_path, csv_path


def _latest_processed_fred_cache() -> Path:
    cached = sorted((DATA / "processed").glob("fred_*.parquet"))
    if not cached:
        raise FileNotFoundError(
            "No processed FRED cache found. Run scripts/daily_run.py first."
        )
    return cached[-1]


def main() -> None:
    path = _latest_processed_fred_cache()
    df = pd.read_parquet(path)
    macro_block_scorecard = run_macro_block_ic_sanity(df)
    base_trajectory = build_curve_trajectory(
        df,
        macro_block_sanity=summarize_macro_block_sanity(macro_block_scorecard),
    )
    policy_path = merge_policy_paths(df, as_of=base_trajectory["as_of"])
    trajectory = apply_policy_event_overlay(
        base_trajectory,
        policy_path=policy_path,
    )
    trajectory = apply_event_uncertainty_overlay(
        trajectory,
        as_of=base_trajectory["as_of"],
    )
    trajectory = attach_polymarket_check(trajectory)
    trajectory = attach_grounded_macro_analysis(df, trajectory)
    json_path, csv_path = save_curve_trajectory(trajectory)
    print(json.dumps(trajectory, indent=2, ensure_ascii=False))
    print(f"\nSaved -> {json_path}\n         {csv_path}")


if __name__ == "__main__":
    main()
