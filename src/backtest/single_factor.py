"""Phase 1 isolated factor IC testing for v3 curve trades."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest.eval import HORIZON_DAYS, TARGETS, evaluate_prediction_frame
from src.backtest.eval import forward_curve_targets
from src.backtest.walk_forward import fred_release_lags
from src.ingestion.nyfed_acm import load_term_premium
from src.ingestion.treasury_auctions import auction_stress_asof
from src.signals.curve_drivers import compute_driver_signals
from src.signals.fomc_series import fomc_factor_asof
from src.utils.config import DATA, load_yaml

DEFAULT_OUTPUT = DATA / "backtest" / "phase1_single_factor_ic.csv"
NS_MATURITIES = np.array([2.0, 5.0, 10.0, 30.0])
NS_COLUMNS = ["DGS2", "DGS5", "DGS10", "DGS30"]
NS_LAMBDA = 0.0609
ROLLING_WINDOW = 756

NEW_FACTOR_NAMES = ("cochrane_piazzesi", "ns_level", "ns_slope")
V2_FACTOR_NAMES = (
    "policy_path",
    "macro_surprise",
    "liquidity_supply",
    "term_premium",
    "growth_risk",
    "global_relative_value",
    "positioning_momentum",
    "risk_off_overlay",
)
FACTOR_NAMES = (*NEW_FACTOR_NAMES, *V2_FACTOR_NAMES)
FACTOR_ALIGNED_TARGETS = {
    "policy_path": ("2s10s", "5s30s", "2Y"),
    "cochrane_piazzesi": TARGETS,
    "ns_slope": ("2s10s", "5s30s", "2Y"),
    "ns_level": ("10Y", "30Y"),
    "term_premium": ("10Y", "30Y"),
    "growth_risk": ("2Y", "5Y", "2s10s"),
    "global_relative_value": ("10Y", "30Y"),
    "liquidity_supply": ("10Y", "30Y"),
    "macro_surprise": ("2Y", "5Y", "10Y"),
    "positioning_momentum": TARGETS,
    "risk_off_overlay": ("10Y", "30Y"),
}
MIN_DECISION_IC = 0.05
BENCHMARK_MODEL = "momentum_3m"
WINDOW_CAVEAT = (
    "Targets use overlapping 63/126-day forward windows sampled daily; "
    "effective independent N is roughly n/horizon_days, so IC is a relative "
    "ranking metric rather than an absolute significance test."
)
SIGN_AUDITS = {
    "growth_risk": (
        "fixed_code_sign_bug",
        "Fixed: curve steepening/high 2s10s is used as growth-risk/easing stress, "
        "so it should map to lower front-end yield pressure rather than higher.",
    ),
    "term_premium": (
        "fixed_code_sign_bug",
        "Fixed: rising ACM term premium is treated as long-end cheapness/expected "
        "mean reversion, not as automatic forward yield-up pressure.",
    ),
    "global_relative_value": (
        "fixed_code_sign_bug",
        "Fixed: a wider UST premium versus Bund/JGB is treated as relative-value "
        "demand for USTs, leaning yields lower.",
    ),
    "liquidity_supply": (
        "no_code_sign_bug",
        "No flip: tighter Fed liquidity or auction stress is intentionally "
        "positive long-end yield pressure.",
    ),
}

NEW_FACTOR_LOADINGS = {
    "cochrane_piazzesi": {"2Y": -0.25, "5Y": -0.55, "10Y": -0.90, "30Y": -1.00},
    "ns_level": {"2Y": 1.00, "5Y": 1.00, "10Y": 1.00, "30Y": 1.00},
    "ns_slope": {"2Y": -0.80, "5Y": -0.30, "10Y": 0.40, "30Y": 0.80},
}


def _clip(value: float) -> float:
    return float(max(-1.0, min(1.0, value)))


def _zscore_last(s: pd.Series, window: int = ROLLING_WINDOW) -> float:
    s = s.dropna()
    if len(s) < 20:
        return 0.0
    w = s.tail(window)
    std = w.std()
    if std == 0 or pd.isna(std):
        return 0.0
    return _clip(float((s.iloc[-1] - w.mean()) / std) / 2.0)


def _clip_series(s: pd.Series) -> pd.Series:
    return s.clip(lower=-1.0, upper=1.0)


def _rolling_zscore_series(
    s: pd.Series,
    window: int = 252,
    scale: float = 2.0,
) -> pd.Series:
    s = s.dropna().sort_index()
    mean = s.rolling(window=window, min_periods=20).mean()
    std = s.rolling(window=window, min_periods=20).std()
    return _clip_series(((s - mean) / std.replace(0, np.nan)) / scale)


def _change_score_series(
    s: pd.Series,
    periods: int,
    full_scale: float,
) -> pd.Series:
    s = s.dropna().sort_index()
    return _clip_series((s - s.shift(periods)) / full_scale)


def _mean_series(parts: list[pd.Series]) -> pd.Series:
    if not parts:
        return pd.Series(dtype=float)
    return pd.concat(parts, axis=1).mean(axis=1)


def _asof_to_index(s: pd.Series, index: pd.Index) -> pd.Series:
    s = s.dropna().sort_index()
    if s.empty:
        return pd.Series(0.0, index=index)
    combined = s.reindex(s.index.union(index)).sort_index().ffill()
    return combined.reindex(index).fillna(0.0)


def _available_series(
    df: pd.DataFrame,
    col: str,
    release_lags: dict[str, int],
) -> pd.Series:
    if col not in df:
        return pd.Series(dtype=float)
    s = df[col].dropna().copy()
    if s.empty:
        return s
    s.index = pd.to_datetime(s.index) + pd.to_timedelta(
        int(release_lags.get(col, 1)), unit="D"
    )
    return s[~s.index.duplicated(keep="last")].sort_index()


def _available_frame(
    df: pd.DataFrame,
    cols: list[str],
    release_lags: dict[str, int],
) -> pd.DataFrame:
    series = {col: _available_series(df, col, release_lags) for col in cols}
    if not series:
        return pd.DataFrame()
    return pd.concat(series, axis=1, sort=True).sort_index().ffill()


def _ns_loadings() -> np.ndarray:
    slope_loading = (1.0 - np.exp(-NS_LAMBDA * NS_MATURITIES)) / (
        NS_LAMBDA * NS_MATURITIES
    )
    curvature_loading = slope_loading - np.exp(-NS_LAMBDA * NS_MATURITIES)
    return np.column_stack(
        [np.ones_like(NS_MATURITIES), slope_loading, curvature_loading]
    )


def _fit_ns_betas(row: pd.Series) -> tuple[float, float, float]:
    y = row[NS_COLUMNS].astype(float).to_numpy()
    betas, *_ = np.linalg.lstsq(_ns_loadings(), y, rcond=None)
    return float(betas[0]), float(betas[1]), float(betas[2])


def _nelson_siegel_beta_frame(df: pd.DataFrame) -> pd.DataFrame:
    clean = df[NS_COLUMNS].dropna().tail(ROLLING_WINDOW).copy()
    if clean.empty:
        return pd.DataFrame(columns=["level", "slope", "curvature"])
    betas = [_fit_ns_betas(row) for _, row in clean.iterrows()]
    return pd.DataFrame(
        betas,
        index=clean.index,
        columns=["level", "slope", "curvature"],
    )


def nelson_siegel_factors_asof(df: pd.DataFrame) -> dict[str, float]:
    """Return NS level and slope valuation signals from the Treasury curve."""
    betas = _nelson_siegel_beta_frame(df)
    if betas.empty:
        return {"ns_level": 0.0, "ns_slope": 0.0}
    return {
        "ns_level": -_zscore_last(betas["level"]),
        "ns_slope": -_zscore_last(betas["slope"]),
    }


def _forward_rate_series(df: pd.DataFrame) -> pd.DataFrame:
    clean = df[NS_COLUMNS].dropna().tail(ROLLING_WINDOW)
    forwards = pd.DataFrame(index=clean.index)
    forwards["f_2_5"] = (5.0 * clean["DGS5"] - 2.0 * clean["DGS2"]) / 3.0
    forwards["f_5_10"] = (10.0 * clean["DGS10"] - 5.0 * clean["DGS5"]) / 5.0
    forwards["f_10_30"] = (30.0 * clean["DGS30"] - 10.0 * clean["DGS10"]) / 20.0
    return forwards


def cochrane_piazzesi_factor_asof(df: pd.DataFrame) -> float:
    """Tent-shaped forward-rate factor built from free FRED Treasury yields."""
    forwards = _forward_rate_series(df)
    if forwards.empty:
        return 0.0
    tent = (
        -0.50 * forwards["f_2_5"]
        + 1.00 * forwards["f_5_10"]
        - 0.50 * forwards["f_10_30"]
    )
    return _zscore_last(tent)


def _nelson_siegel_score_series(curve: pd.DataFrame) -> pd.DataFrame:
    clean = curve[NS_COLUMNS].dropna()
    if clean.empty:
        return pd.DataFrame(columns=["ns_level", "ns_slope"])
    betas = [_fit_ns_betas(row) for _, row in clean.iterrows()]
    beta_frame = pd.DataFrame(
        betas,
        index=clean.index,
        columns=["level", "slope", "curvature"],
    )
    return pd.DataFrame(
        {
            "ns_level": -_rolling_zscore_series(beta_frame["level"]),
            "ns_slope": -_rolling_zscore_series(beta_frame["slope"]),
        }
    )


def _cochrane_piazzesi_score_series(curve: pd.DataFrame) -> pd.Series:
    clean = curve[NS_COLUMNS].dropna()
    if clean.empty:
        return pd.Series(dtype=float)
    forwards = pd.DataFrame(index=clean.index)
    forwards["f_2_5"] = (5.0 * clean["DGS5"] - 2.0 * clean["DGS2"]) / 3.0
    forwards["f_5_10"] = (10.0 * clean["DGS10"] - 5.0 * clean["DGS5"]) / 5.0
    forwards["f_10_30"] = (30.0 * clean["DGS30"] - 10.0 * clean["DGS10"]) / 20.0
    tent = (
        -0.50 * forwards["f_2_5"]
        + 1.00 * forwards["f_5_10"]
        - 0.50 * forwards["f_10_30"]
    )
    return _rolling_zscore_series(tent)


def _loadings_for_factor(factor_name: str) -> dict[str, float]:
    if factor_name in NEW_FACTOR_LOADINGS:
        return NEW_FACTOR_LOADINGS[factor_name]
    return load_yaml("curve_rules")["tenor_loadings"].get(factor_name, {})


def single_factor_target_signal(factor_name: str, score: float) -> dict[str, float]:
    """Map one scalar factor score to tenor and curve-trade target signals."""
    loadings = _loadings_for_factor(factor_name)
    tenor = {
        target: _clip(float(score) * float(loadings.get(target, 0.0)))
        for target in ("2Y", "5Y", "10Y", "30Y")
    }
    return {
        **tenor,
        "2s10s": _clip(tenor["10Y"] - tenor["2Y"]),
        "5s30s": _clip(tenor["30Y"] - tenor["5Y"]),
    }


def _factor_scores_asof(df: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    ns = nelson_siegel_factors_asof(df)
    drivers = compute_driver_signals(df, hawkish=fomc_factor_asof(asof))
    return {
        "cochrane_piazzesi": cochrane_piazzesi_factor_asof(df),
        **ns,
        **{name: drivers[name].score for name in V2_FACTOR_NAMES},
    }


def _term_premium_score_series(index: pd.Index) -> pd.Series:
    acm = load_term_premium(fetch_if_missing=False)
    if acm.empty or "ACMTP10" not in acm:
        return pd.Series(0.0, index=index)
    changes = acm["ACMTP10"].dropna().diff(63)
    rolling_std = changes.rolling(window=756, min_periods=20).std()
    score = _clip_series(changes / rolling_std.replace(0, np.nan))
    return -_asof_to_index(score, index)


def _risk_off_score_series(vix: pd.Series) -> pd.Series:
    level_z = _rolling_zscore_series(vix, window=63, scale=2.0).clip(lower=0.0)
    vix_change = vix.dropna().diff(5)
    change_z = _rolling_zscore_series(vix_change, window=63, scale=2.0).clip(lower=0.0)
    stress = pd.concat([level_z, change_z], axis=1).max(axis=1)
    return -_clip_series(stress)


def _positioning_momentum_score_series(curve: pd.DataFrame) -> pd.Series:
    ten_year = curve["DGS10"].dropna()
    momentum = (
        0.40 * _change_score_series(ten_year, periods=21, full_scale=0.25)
        + 0.35 * _change_score_series(ten_year, periods=63, full_scale=0.50)
        + 0.25 * _change_score_series(ten_year, periods=126, full_scale=0.75)
    )
    low = ten_year.rolling(window=252, min_periods=20).min()
    high = ten_year.rolling(window=252, min_periods=20).max()
    range_position = _clip_series(((ten_year - low) / (high - low) - 0.5) * 2.0)

    spread_2s10s = (curve["DGS10"] - curve["DGS2"]).dropna()
    spread_5s30s = (curve["DGS30"] - curve["DGS5"]).dropna()
    curve_trend = 0.60 * _change_score_series(
        spread_2s10s, periods=63, full_scale=0.30
    ) + 0.40 * _change_score_series(spread_5s30s, periods=63, full_scale=0.30)
    return _clip_series(0.55 * momentum + 0.25 * range_position + 0.20 * curve_trend)


def _vector_factor_scores(df: pd.DataFrame, start: str) -> pd.DataFrame:
    release_lags = fred_release_lags()
    forecast_index = df["DGS10"].dropna().loc[start:].index
    curve = _available_frame(df, NS_COLUMNS, release_lags)
    scores = pd.DataFrame(index=forecast_index)

    ns_scores = _nelson_siegel_score_series(curve)
    scores["ns_level"] = _asof_to_index(
        ns_scores.get("ns_level", pd.Series()), forecast_index
    )
    scores["ns_slope"] = _asof_to_index(
        ns_scores.get("ns_slope", pd.Series()), forecast_index
    )
    scores["cochrane_piazzesi"] = _asof_to_index(
        _cochrane_piazzesi_score_series(curve),
        forecast_index,
    )

    dgs2 = curve["DGS2"].dropna()
    dgs5 = curve["DGS5"].dropna()
    scores["policy_path"] = _clip_series(
        0.45
        * pd.Series(
            [fomc_factor_asof(d) for d in forecast_index],
            index=forecast_index,
        )
        + 0.35 * _asof_to_index(_change_score_series(dgs2, 63, 0.50), forecast_index)
        + 0.20 * _asof_to_index(_change_score_series(dgs5, 63, 0.50), forecast_index)
    )

    cpi = _available_series(df, "CPIAUCSL", release_lags)
    pce = _available_series(df, "PCEPILFE", release_lags)
    cpi_accel = _rolling_zscore_series(cpi.pct_change(1).mul(100).diff())
    pce_accel = _rolling_zscore_series(pce.pct_change(1).mul(100).diff())
    scores["macro_surprise"] = _asof_to_index(
        _clip_series(_mean_series([cpi_accel, pce_accel])),
        forecast_index,
    )

    walcl = _available_series(df, "WALCL", release_lags)
    reserves = _available_series(df, "WRESBAL", release_lags)
    liquidity_base = _asof_to_index(
        _mean_series(
            [
                -_rolling_zscore_series(walcl.pct_change(13)),
                -_rolling_zscore_series(reserves.pct_change(13)),
            ]
        ),
        forecast_index,
    )
    auction = pd.Series(
        [auction_stress_asof(d) for d in forecast_index],
        index=forecast_index,
        dtype="float64",
    )
    scores["liquidity_supply"] = _clip_series(
        liquidity_base.where(auction.isna(), 0.60 * liquidity_base + 0.40 * auction)
    )

    scores["term_premium"] = _term_premium_score_series(forecast_index)

    if "T10Y2Y" in df:
        curve_growth = _available_series(df, "T10Y2Y", release_lags)
    else:
        curve_growth = (curve["DGS10"] - curve["DGS2"]).dropna()
    growth_level = _rolling_zscore_series(curve_growth)
    growth_momentum = _change_score_series(curve_growth, periods=63, full_scale=0.50)
    scores["growth_risk"] = _asof_to_index(
        _clip_series(-(0.70 * growth_level + 0.30 * growth_momentum)),
        forecast_index,
    )

    germany = _available_series(df, "IRLTLT01DEM156N", release_lags)
    global_frame = pd.concat({"DGS10": curve["DGS10"], "DE10Y": germany}, axis=1)
    global_diff = (
        global_frame.sort_index().ffill().dropna()["DGS10"]
        - global_frame.sort_index().ffill().dropna()["DE10Y"]
    )
    scores["global_relative_value"] = -_asof_to_index(
        _rolling_zscore_series(global_diff),
        forecast_index,
    )

    scores["positioning_momentum"] = _asof_to_index(
        _positioning_momentum_score_series(curve),
        forecast_index,
    )

    vix = _available_series(df, "VIXCLS", release_lags)
    scores["risk_off_overlay"] = _asof_to_index(
        _risk_off_score_series(vix),
        forecast_index,
    )

    return scores.fillna(0.0)


def build_single_factor_prediction_frames(
    df: pd.DataFrame,
    *,
    start: str = "2015-01-01",
    factor_names: tuple[str, ...] = FACTOR_NAMES,
) -> dict[str, pd.DataFrame]:
    """Build point-in-time prediction frames for every candidate factor."""
    factor_scores = _vector_factor_scores(df.sort_index(), start)
    frames = {}
    for name in factor_names:
        rows = [
            {"date": date, **single_factor_target_signal(name, score)}
            for date, score in factor_scores[name].items()
        ]
        frames[name] = pd.DataFrame(rows).set_index("date").sort_index()
    return frames


def build_factor_prediction_frame(
    df: pd.DataFrame,
    factor_name: str,
    *,
    start: str = "2015-01-01",
) -> pd.DataFrame:
    """Build a point-in-time target-signal frame for one candidate factor."""
    return build_single_factor_prediction_frames(
        df, start=start, factor_names=(factor_name,)
    )[factor_name]


def aligned_targets_for_factor(factor_name: str) -> tuple[str, ...]:
    """Targets used for the benchmark-gated sign-audit decision for one factor."""
    return FACTOR_ALIGNED_TARGETS.get(factor_name, TARGETS)


def _momentum_benchmark_lookup(
    phase0_scorecard: pd.DataFrame | None,
) -> dict[tuple[str, str], float]:
    if phase0_scorecard is None or phase0_scorecard.empty:
        return {}

    detail = phase0_scorecard.copy()
    if "model" in detail:
        detail = detail[detail["model"].astype(str).eq(BENCHMARK_MODEL)]
    elif "factor" in detail:
        detail = detail[detail["factor"].astype(str).eq(f"benchmark:{BENCHMARK_MODEL}")]
    else:
        return {}

    lookup = {}
    for _, row in detail.dropna(subset=["rank_ic"]).iterrows():
        lookup[(str(row["horizon"]), str(row["target"]))] = float(row["rank_ic"])
    return lookup


def _target_rank_ics(metrics: pd.DataFrame, target: str) -> dict[str, float]:
    target_rows = metrics[metrics["target"] == target]
    return {
        horizon: float(
            target_rows.loc[target_rows["horizon"] == horizon, "rank_ic"].iloc[0]
        )
        for horizon in HORIZON_DAYS
        if not target_rows.loc[target_rows["horizon"] == horizon, "rank_ic"].empty
    }


def _benchmark_rank_ics(
    benchmark_rank_ics: dict[tuple[str, str], float],
    target: str,
) -> dict[str, float]:
    return {
        horizon: float(benchmark_rank_ics.get((horizon, target), float("nan")))
        for horizon in HORIZON_DAYS
    }


def _delta_ic(rank_ic: float, benchmark_rank_ic: float) -> float:
    if pd.isna(rank_ic) or pd.isna(benchmark_rank_ic):
        return float("nan")
    return round(float(rank_ic) - float(benchmark_rank_ic), 12)


def _candidate_strength(ics: dict[str, float]) -> float:
    values = [abs(value) for value in ics.values() if not pd.isna(value)]
    return float(sum(values) / len(values)) if values else float("nan")


def _sign_audit_for_factor(factor_name: str) -> tuple[str, str]:
    return SIGN_AUDITS.get(factor_name, ("not_required", ""))


def _target_candidate(
    metrics: pd.DataFrame,
    benchmark_rank_ics: dict[tuple[str, str], float],
    target: str,
) -> dict | None:
    ics = _target_rank_ics(metrics, target)
    if set(ics) != set(HORIZON_DAYS):
        return None
    values = list(ics.values())
    if any(pd.isna(value) for value in values):
        return None

    benchmark_ics = _benchmark_rank_ics(benchmark_rank_ics, target)
    benchmark_available = all(
        not pd.isna(benchmark_ics[horizon]) for horizon in HORIZON_DAYS
    )
    deltas = {
        horizon: _delta_ic(ics[horizon], benchmark_ics[horizon])
        for horizon in HORIZON_DAYS
    }
    finite_deltas = [value for value in deltas.values() if not pd.isna(value)]
    mean_delta = (
        float(sum(finite_deltas) / len(finite_deltas))
        if finite_deltas
        else float("nan")
    )
    min_delta = min(finite_deltas) if finite_deltas else float("nan")

    return {
        "target": target,
        "rank_ic_3m": ics["3m"],
        "rank_ic_6m": ics["6m"],
        "benchmark_rank_ic_3m": benchmark_ics["3m"],
        "benchmark_rank_ic_6m": benchmark_ics["6m"],
        "benchmark_delta_3m": deltas["3m"],
        "benchmark_delta_6m": deltas["6m"],
        "benchmark_available": benchmark_available,
        "beats_benchmark": benchmark_available
        and all(deltas[horizon] > 0 for horizon in HORIZON_DAYS),
        "positive": all(ics[horizon] > MIN_DECISION_IC for horizon in HORIZON_DAYS),
        "negative": all(ics[horizon] < -MIN_DECISION_IC for horizon in HORIZON_DAYS),
        "weak": all(abs(ics[horizon]) < MIN_DECISION_IC for horizon in HORIZON_DAYS),
        "strength": _candidate_strength(ics),
        "mean_delta": mean_delta,
        "min_delta": min_delta,
    }


def _candidate_delta_key(candidate: dict) -> tuple[float, float, float]:
    min_delta = candidate["min_delta"]
    mean_delta = candidate["mean_delta"]
    return (
        float("-inf") if pd.isna(min_delta) else float(min_delta),
        float("-inf") if pd.isna(mean_delta) else float(mean_delta),
        float(candidate["strength"]),
    )


def _decision_from_candidate(
    candidate: dict,
    *,
    tag: str,
    reason: str,
    audit_status: str,
    audit_note: str,
) -> dict:
    return {
        "tag": tag,
        "decision_target": candidate["target"],
        "decision_reason": reason,
        "sign_audit_status": audit_status,
        "sign_audit_note": audit_note,
        "decision_rank_ic_3m": candidate["rank_ic_3m"],
        "decision_rank_ic_6m": candidate["rank_ic_6m"],
        "decision_benchmark_rank_ic_3m": candidate["benchmark_rank_ic_3m"],
        "decision_benchmark_rank_ic_6m": candidate["benchmark_rank_ic_6m"],
        "decision_benchmark_delta_3m": candidate["benchmark_delta_3m"],
        "decision_benchmark_delta_6m": candidate["benchmark_delta_6m"],
    }


def _empty_decision(
    *,
    tag: str,
    reason: str,
    audit_status: str,
    audit_note: str,
) -> dict:
    return {
        "tag": tag,
        "decision_target": "",
        "decision_reason": reason,
        "sign_audit_status": audit_status,
        "sign_audit_note": audit_note,
        "decision_rank_ic_3m": float("nan"),
        "decision_rank_ic_6m": float("nan"),
        "decision_benchmark_rank_ic_3m": float("nan"),
        "decision_benchmark_rank_ic_6m": float("nan"),
        "decision_benchmark_delta_3m": float("nan"),
        "decision_benchmark_delta_6m": float("nan"),
    }


def _choose_factor_decision(
    factor_name: str,
    metrics: pd.DataFrame,
    benchmark_rank_ics: dict[tuple[str, str], float],
) -> dict:
    audit_status, audit_note = _sign_audit_for_factor(factor_name)
    aligned_targets = aligned_targets_for_factor(factor_name)
    candidates = []
    for target in aligned_targets:
        candidate = _target_candidate(metrics, benchmark_rank_ics, target)
        if candidate is not None:
            candidates.append(candidate)

    if not candidates:
        return _empty_decision(
            tag="drop",
            reason="no_aligned_target_ic",
            audit_status=audit_status,
            audit_note=audit_note,
        )

    positive = [candidate for candidate in candidates if candidate["positive"]]
    negative = [candidate for candidate in candidates if candidate["negative"]]
    benchmark_beaters = [
        candidate for candidate in positive if candidate["beats_benchmark"]
    ]

    if benchmark_beaters:
        best = max(benchmark_beaters, key=_candidate_delta_key)
        return _decision_from_candidate(
            best,
            tag="keep",
            reason="correct_sign_and_beats_momentum_bar_on_aligned_target",
            audit_status=audit_status,
            audit_note=audit_note,
        )

    if positive:
        benchmark_ready = [
            candidate for candidate in positive if candidate["benchmark_available"]
        ]
        best = max(benchmark_ready or positive, key=_candidate_delta_key)
        tag = "below_benchmark" if best["benchmark_available"] else "benchmark_missing"
        reason = (
            "correct_sign_but_does_not_beat_momentum_bar_both_horizons"
            if best["benchmark_available"]
            else "correct_sign_but_momentum_bar_missing_for_aligned_target"
        )
        return _decision_from_candidate(
            best,
            tag=tag,
            reason=reason,
            audit_status=audit_status,
            audit_note=audit_note,
        )

    if negative:
        best = max(negative, key=lambda candidate: candidate["strength"])
        reason = (
            "wrong_sign_after_code_sign_audit_no_posthoc_flip"
            if audit_status == "fixed_code_sign_bug"
            else "wrong_sign_on_aligned_target_no_posthoc_flip"
        )
        return _decision_from_candidate(
            best,
            tag="sign_mismatch",
            reason=reason,
            audit_status=audit_status,
            audit_note=audit_note,
        )

    best = max(candidates, key=lambda candidate: candidate["strength"])
    weak = best["weak"]
    tag = "drop" if weak else "mixed"
    reason = (
        "weak_on_aligned_target_both_horizons"
        if weak
        else "aligned_target_ic_not_consistent_across_3m_6m"
    )
    return _decision_from_candidate(
        best,
        tag=tag,
        reason=reason,
        audit_status=audit_status,
        audit_note=audit_note,
    )


def _effective_n(row: pd.Series) -> float:
    horizon_days = HORIZON_DAYS.get(str(row["horizon"]))
    if horizon_days is None or pd.isna(row["n"]):
        return float("nan")
    return float(row["n"]) / float(horizon_days)


def _factor_detail_rows(
    factor_name: str,
    metrics: pd.DataFrame,
    benchmark_rank_ics: dict[tuple[str, str], float],
) -> pd.DataFrame:
    decision = _choose_factor_decision(factor_name, metrics, benchmark_rank_ics)
    aligned_targets = set(aligned_targets_for_factor(factor_name))
    detail = metrics.copy()
    detail = detail.drop(columns=["icir"], errors="ignore")
    detail = detail.rename(columns={"model": "factor"})
    detail.insert(0, "row_type", "factor")
    detail["aligned_target"] = detail["target"].isin(aligned_targets)
    detail["benchmark_model"] = BENCHMARK_MODEL
    detail["benchmark_rank_ic"] = [
        benchmark_rank_ics.get((str(row["horizon"]), str(row["target"])), float("nan"))
        for _, row in detail.iterrows()
    ]
    detail["benchmark_delta_ic"] = [
        _delta_ic(row["rank_ic"], row["benchmark_rank_ic"])
        for _, row in detail.iterrows()
    ]
    for key, value in decision.items():
        detail[key] = value
    detail["effective_independent_n"] = detail.apply(_effective_n, axis=1)
    detail["window_caveat"] = WINDOW_CAVEAT
    return detail


def _benchmark_detail_rows(
    phase0_scorecard: pd.DataFrame | None,
    benchmark_rank_ics: dict[tuple[str, str], float],
) -> pd.DataFrame:
    if phase0_scorecard is None or phase0_scorecard.empty:
        return pd.DataFrame()
    detail = phase0_scorecard.copy()
    detail = detail.drop(columns=["phase", "icir"], errors="ignore")
    detail["factor"] = "benchmark:" + detail["model"].astype(str)
    detail = detail.drop(columns=["model"], errors="ignore")
    detail.insert(0, "row_type", "benchmark")
    detail["aligned_target"] = False
    detail["tag"] = "bar"
    detail["decision_target"] = detail["target"]
    detail["decision_reason"] = "phase0_reference_bar"
    detail["sign_audit_status"] = ""
    detail["sign_audit_note"] = ""
    detail["benchmark_model"] = BENCHMARK_MODEL
    detail["benchmark_rank_ic"] = [
        benchmark_rank_ics.get((str(row["horizon"]), str(row["target"])), float("nan"))
        for _, row in detail.iterrows()
    ]
    detail["benchmark_delta_ic"] = [
        _delta_ic(row["rank_ic"], row["benchmark_rank_ic"])
        for _, row in detail.iterrows()
    ]
    detail["decision_rank_ic_3m"] = float("nan")
    detail["decision_rank_ic_6m"] = float("nan")
    detail["decision_benchmark_rank_ic_3m"] = float("nan")
    detail["decision_benchmark_rank_ic_6m"] = float("nan")
    detail["decision_benchmark_delta_3m"] = float("nan")
    detail["decision_benchmark_delta_6m"] = float("nan")
    detail["effective_independent_n"] = detail.apply(_effective_n, axis=1)
    detail["window_caveat"] = WINDOW_CAVEAT
    return detail


def build_phase1_scorecard(
    factor_metrics: dict[str, pd.DataFrame],
    phase0_scorecard: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return per-factor, per-target, per-horizon Phase 1 rows."""
    benchmark_rank_ics = _momentum_benchmark_lookup(phase0_scorecard)
    rows = [
        _factor_detail_rows(factor_name, metrics, benchmark_rank_ics)
        for factor_name, metrics in factor_metrics.items()
    ]
    benchmark_rows = _benchmark_detail_rows(phase0_scorecard, benchmark_rank_ics)
    if not benchmark_rows.empty:
        rows.append(benchmark_rows)
    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True)
    sort_cols = ["row_type", "factor", "horizon", "target"]
    return out.sort_values(sort_cols).reset_index(drop=True)


def _print_phase1_summary(scorecard: pd.DataFrame) -> None:
    factor_rows = scorecard[scorecard["row_type"] == "factor"]
    decisions = (
        factor_rows[
            [
                "factor",
                "tag",
                "decision_target",
                "decision_rank_ic_3m",
                "decision_rank_ic_6m",
                "decision_benchmark_rank_ic_3m",
                "decision_benchmark_rank_ic_6m",
                "decision_benchmark_delta_3m",
                "decision_benchmark_delta_6m",
                "sign_audit_status",
                "decision_reason",
            ]
        ]
        .drop_duplicates()
        .sort_values(
            ["tag", "decision_benchmark_delta_3m", "decision_benchmark_delta_6m"],
            ascending=[True, False, False],
        )
    )
    print("\nPhase 1 aligned-target decisions")
    print("-" * 132)
    for _, row in decisions.iterrows():
        print(
            f"{row['factor'][:28]:28s} {row['tag']:>15s} "
            f"target={row['decision_target']:>6s} "
            f"IC/bar/delta 3m="
            f"{row['decision_rank_ic_3m']: .3f}/"
            f"{row['decision_benchmark_rank_ic_3m']: .3f}/"
            f"{row['decision_benchmark_delta_3m']: .3f} "
            f"6m={row['decision_rank_ic_6m']: .3f}/"
            f"{row['decision_benchmark_rank_ic_6m']: .3f}/"
            f"{row['decision_benchmark_delta_6m']: .3f} "
            f"audit={row['sign_audit_status']} "
            f"{row['decision_reason']}"
        )
    cp_rows = factor_rows[factor_rows["factor"].eq("cochrane_piazzesi")]
    if not cp_rows.empty:
        print("\nCochrane-Piazzesi IC versus momentum bar by target")
        print("-" * 76)
        for target in TARGETS:
            target_rows = cp_rows[cp_rows["target"].eq(target)]
            if target_rows.empty:
                continue
            values = {}
            for _, row in target_rows.iterrows():
                values[str(row["horizon"])] = row
            row_3m = values.get("3m")
            row_6m = values.get("6m")
            if row_3m is None or row_6m is None:
                continue
            print(
                f"{target:6s} "
                f"3m={row_3m['rank_ic']: .3f}/"
                f"{row_3m['benchmark_rank_ic']: .3f}/"
                f"{row_3m['benchmark_delta_ic']: .3f} "
                f"6m={row_6m['rank_ic']: .3f}/"
                f"{row_6m['benchmark_rank_ic']: .3f}/"
                f"{row_6m['benchmark_delta_ic']: .3f}"
            )
    print(f"\nCaveat: {WINDOW_CAVEAT}")


def run_phase1_single_factor_ic(
    df: pd.DataFrame,
    *,
    start: str = "2015-01-01",
    phase0_scorecard: pd.DataFrame | None = None,
    output_path: str | Path = DEFAULT_OUTPUT,
) -> pd.DataFrame:
    """Evaluate each candidate factor alone for 3m and 6m targets."""
    history = df.sort_index()
    factor_frames = build_single_factor_prediction_frames(history, start=start)
    factor_metrics = {}

    for factor_name, predictions in factor_frames.items():
        metrics = []
        for horizon, horizon_days in HORIZON_DAYS.items():
            targets = forward_curve_targets(history, horizon_days).loc[start:]
            aligned_predictions = predictions.reindex(targets.index)
            metrics.append(
                evaluate_prediction_frame(
                    aligned_predictions,
                    targets,
                    model=factor_name,
                    horizon=horizon,
                )
            )
        factor_metrics[factor_name] = pd.concat(metrics, ignore_index=True)

    out = build_phase1_scorecard(
        factor_metrics,
        phase0_scorecard=phase0_scorecard,
    )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False)
    print(f"Wrote Phase 1 single-factor IC -> {output_path} ({len(out)} rows)")
    if not out.empty:
        _print_phase1_summary(out)
    return out
