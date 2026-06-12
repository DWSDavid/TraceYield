"""Factor-augmented dynamic Nelson-Siegel curve forecasts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.backtest.eval import HORIZON_DAYS, TARGETS, evaluate_prediction_frame
from src.backtest.eval import forward_curve_targets
from src.backtest.hac import fit_hac_regression, max_benchmark_lookup
from src.backtest.single_factor import NS_COLUMNS, _available_frame
from src.backtest.single_factor import _fit_ns_betas, _rolling_zscore_series
from src.backtest.walk_forward import fred_release_lags
from src.ingestion.treasury_auctions import auction_stress_asof
from src.signals.fomc_series import fomc_factor_asof
from src.utils.config import DATA, load_yaml

DEFAULT_OUTPUT = DATA / "backtest" / "phase2_fadns_scorecard.csv"
MACRO_BLOCK_IC_OUTPUT = DATA / "backtest" / "phase4_macro_block_ic.csv"
NS_MATURITIES = np.array([2.0, 5.0, 10.0, 30.0])
TENOR_TARGETS = ("2Y", "5Y", "10Y", "30Y")
NS_FACTOR_NAMES = ("level", "slope", "curvature")
MACRO_BLOCKS = (
    "inflation_regime",
    "policy_path",
    "growth_risk",
    "liquidity_supply",
    "global_relative_value",
)
MACRO_BLOCK_ALIGNED_TARGETS = {
    "inflation_regime": ("10Y",),
    "policy_path": ("2Y", "2s10s"),
    "growth_risk": ("2s10s", "10Y"),
    "liquidity_supply": ("10Y", "30Y"),
    "global_relative_value": ("10Y", "30Y"),
}
MACRO_BLOCK_EXPECTED_SIGNS = {
    ("inflation_regime", "10Y"): "+",
    ("policy_path", "2Y"): "+",
    ("policy_path", "2s10s"): "-",
    ("growth_risk", "2s10s"): "+",
    ("growth_risk", "10Y"): "+",
    ("liquidity_supply", "10Y"): "+",
    ("liquidity_supply", "30Y"): "+",
    ("global_relative_value", "10Y"): "+",
    ("global_relative_value", "30Y"): "+",
}
MACRO_BLOCK_IC_NOISE_BANDS = {"3m": 0.15, "6m": 0.22}
REALIZED_MACRO_INPUTS = {
    "inflation_regime": (
        "CPIAUCSL",
        "CPILFESL",
        "PCEPI",
        "PCEPILFE",
        "T5YIE",
        "T10YIE",
        "T5YIFR",
    ),
    "policy_path": (
        "DFEDTARU",
        "EFFR",
        "DGS2",
        "DGS3MO",
        "DGS6MO",
        "FEDTARMD",
        "fomc_tone",
    ),
    "growth_risk": (
        "PAYEMS",
        "UNRATE",
        "ICSA",
        "IPMAN",
        "RSAFS",
        "JTSJOL",
    ),
    "liquidity_supply": (
        "WALCL",
        "WRESBAL",
        "RRPONTSYD",
        "WTREGEN",
        "treasury_auction_stress",
    ),
    "global_relative_value": (
        "IRLTLT01DEM156N",
        "IRLTLT01JPM156N",
        "DTWEXBGS",
    ),
}


def _ns_loadings() -> np.ndarray:
    lam = 0.0609
    slope_loading = (1.0 - np.exp(-lam * NS_MATURITIES)) / (lam * NS_MATURITIES)
    curvature_loading = slope_loading - np.exp(-lam * NS_MATURITIES)
    return np.column_stack(
        [np.ones_like(NS_MATURITIES), slope_loading, curvature_loading]
    )


def nelson_siegel_beta_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Fit daily Nelson-Siegel level/slope/curvature from FRED curve yields."""
    clean = df[NS_COLUMNS].dropna().sort_index()
    if clean.empty:
        return pd.DataFrame(columns=["level", "slope", "curvature"])
    betas = [_fit_ns_betas(row) for _, row in clean.iterrows()]
    return pd.DataFrame(
        betas,
        index=clean.index,
        columns=["level", "slope", "curvature"],
    )


def _curve_from_betas(beta: np.ndarray) -> dict[str, float]:
    values = _ns_loadings() @ beta
    return {
        "2Y": float(values[0]),
        "5Y": float(values[1]),
        "10Y": float(values[2]),
        "30Y": float(values[3]),
    }


def _macro_feature_frame(df: pd.DataFrame, index: pd.Index) -> pd.DataFrame:
    features = pd.DataFrame(index=index)
    parts = {
        "inflation_regime": _inflation_regime_series(df, index),
        "policy_path": _policy_path_series(df, index),
        "growth_risk": _growth_risk_series(df, index),
        "liquidity_supply": _liquidity_supply_series(df, index),
        "global_relative_value": _global_relative_value_series(df, index),
    }
    for name in MACRO_BLOCKS:
        features[name] = _clip_series(parts[name].reindex(index).fillna(0.0))
    return features.fillna(0.0)


def _clip_series(s: pd.Series) -> pd.Series:
    return s.astype(float).clip(lower=-1.0, upper=1.0)


def _asof_series(s: pd.Series, index: pd.Index) -> pd.Series:
    s = s.dropna().sort_index()
    if s.empty:
        return pd.Series(0.0, index=index, dtype="float64")
    return (
        s.reindex(s.index.union(index))
        .sort_index()
        .ffill()
        .reindex(index)
        .fillna(0.0)
        .astype(float)
    )


def _z_asof(s: pd.Series, index: pd.Index) -> pd.Series:
    return _asof_series(_rolling_zscore_series(s), index)


def _mean_parts(parts: list[pd.Series], index: pd.Index) -> pd.Series:
    if not parts:
        return pd.Series(0.0, index=index, dtype="float64")
    return (
        _clip_series(pd.concat(parts, axis=1).mean(axis=1)).reindex(index).fillna(0.0)
    )


def _inflation_regime_series(df: pd.DataFrame, index: pd.Index) -> pd.Series:
    parts: list[pd.Series] = []
    for col in ("PCEPI", "PCEPILFE", "CPIAUCSL", "CPILFESL"):
        if col in df:
            parts.append(_z_asof(df[col].dropna().pct_change(252).mul(100), index))
    for col in ("T5YIE", "T10YIE", "T5YIFR"):
        if col in df:
            parts.append(_z_asof(df[col].dropna(), index))
    return _mean_parts(parts, index)


def _policy_path_series(df: pd.DataFrame, index: pd.Index) -> pd.Series:
    parts = [
        pd.Series([fomc_factor_asof(d) for d in index], index=index, dtype="float64")
    ]
    current = None
    if "DFEDTARU" in df:
        current = df["DFEDTARU"].dropna()
    elif "EFFR" in df:
        current = df["EFFR"].dropna()
    if current is not None and "DGS2" in df:
        front_gap = pd.concat({"DGS2": df["DGS2"], "current": current}, axis=1)
        parts.append(
            _z_asof((front_gap["DGS2"] - front_gap["current"]).dropna(), index)
        )
    if {"DGS3MO", "DGS6MO"}.issubset(df.columns):
        implied_6m = 2.0 * df["DGS6MO"] - df["DGS3MO"]
        if current is not None:
            path_gap = pd.concat({"path": implied_6m, "current": current}, axis=1)
            parts.append(
                _z_asof((path_gap["path"] - path_gap["current"]).dropna(), index)
            )
    if {"DGS2", "FEDTARMD"}.issubset(df.columns):
        dot_gap = pd.concat({"DGS2": df["DGS2"], "dot": df["FEDTARMD"]}, axis=1)
        parts.append(_z_asof((dot_gap["DGS2"] - dot_gap["dot"]).dropna(), index))
    return _mean_parts(parts, index)


def _growth_risk_series(df: pd.DataFrame, index: pd.Index) -> pd.Series:
    parts: list[pd.Series] = []
    if "PAYEMS" in df:
        parts.append(-_z_asof(df["PAYEMS"].dropna().pct_change(252).mul(100), index))
    if "UNRATE" in df:
        parts.append(_z_asof(df["UNRATE"].dropna(), index))
    if "ICSA" in df:
        parts.append(_z_asof(df["ICSA"].dropna(), index))
    if "NAPM" in df:
        parts.append(-_z_asof(df["NAPM"].dropna(), index))
    if "IPMAN" in df:
        parts.append(-_z_asof(df["IPMAN"].dropna().pct_change(252).mul(100), index))
    if "RSAFS" in df:
        parts.append(-_z_asof(df["RSAFS"].dropna().pct_change(252).mul(100), index))
    if "JTSJOL" in df:
        parts.append(-_z_asof(df["JTSJOL"].dropna(), index))
    if not parts:
        if "T10Y2Y" in df:
            parts.append(-_z_asof(df["T10Y2Y"].dropna(), index))
        elif {"DGS10", "DGS2"}.issubset(df.columns):
            parts.append(-_z_asof((df["DGS10"] - df["DGS2"]).dropna(), index))
    return _mean_parts(parts, index)


def _qra_proximity_series(index: pd.Index) -> pd.Series:
    try:
        releases = load_yaml("data_release_calendar").get("releases", [])
    except FileNotFoundError:
        releases = []
    dates = [
        pd.Timestamp(item["release_date"]).normalize()
        for item in releases
        if str(item.get("indicator", "")).lower() == "qra"
    ]
    values = []
    for date in pd.to_datetime(index):
        if not dates:
            values.append(0.0)
            continue
        distance = min(abs((event - date.normalize()).days) for event in dates)
        values.append(max(0.0, 1.0 - distance / 21.0))
    return pd.Series(values, index=index, dtype="float64")


def _auction_stress_series(index: pd.Index) -> pd.Series:
    values = []
    for date in pd.to_datetime(index):
        stress = auction_stress_asof(date)
        values.append(float(stress) if stress is not None else float("nan"))
    return pd.Series(values, index=index, dtype="float64")


def _liquidity_supply_series(df: pd.DataFrame, index: pd.Index) -> pd.Series:
    parts: list[pd.Series] = []
    if "WALCL" in df:
        parts.append(-_z_asof(df["WALCL"].dropna().pct_change(13), index))
    if "WRESBAL" in df:
        parts.append(-_z_asof(df["WRESBAL"].dropna().pct_change(13), index))
    if "RRPONTSYD" in df:
        parts.append(_z_asof(df["RRPONTSYD"].dropna(), index))
    if "WTREGEN" in df:
        parts.append(_z_asof(df["WTREGEN"].dropna(), index))
    auction_stress = _auction_stress_series(index)
    if not auction_stress.dropna().empty:
        parts.append(_asof_series(auction_stress, index))
    return _mean_parts(parts, index)


def _global_relative_value_series(df: pd.DataFrame, index: pd.Index) -> pd.Series:
    parts: list[pd.Series] = []
    if {"DGS10", "IRLTLT01DEM156N"}.issubset(df.columns):
        parts.append(_z_asof((df["DGS10"] - df["IRLTLT01DEM156N"]).dropna(), index))
    if {"DGS10", "IRLTLT01JPM156N"}.issubset(df.columns):
        parts.append(_z_asof((df["DGS10"] - df["IRLTLT01JPM156N"]).dropna(), index))
    if "DTWEXBGS" in df:
        parts.append(_z_asof(df["DTWEXBGS"].dropna(), index))
    return _mean_parts(parts, index)


def _ridge_transition(
    betas: pd.DataFrame,
    macro: pd.DataFrame,
    *,
    alpha: float,
) -> np.ndarray | None:
    macro_cols = list(macro.columns)
    joined = pd.concat(
        [betas[list(NS_FACTOR_NAMES)], macro[macro_cols]], axis=1
    ).dropna()
    if len(joined) < 20:
        return None

    beta_cols = list(NS_FACTOR_NAMES)
    y = joined[beta_cols].iloc[1:].to_numpy(dtype=float)
    x_lag = joined[beta_cols + macro_cols].iloc[:-1].to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(x_lag)), x_lag])
    penalty = np.eye(design.shape[1]) * float(alpha)
    penalty[0, 0] = 0.0
    return np.linalg.pinv(design.T @ design + penalty) @ design.T @ y


def _forecast_beta(
    coefficients: np.ndarray,
    last_beta: np.ndarray,
    last_macro: np.ndarray,
    horizon_days: int,
) -> np.ndarray:
    state = last_beta.astype(float).copy()
    for _ in range(max(1, int(horizon_days))):
        x = np.array([1.0, *state, *last_macro], dtype=float)
        state = x @ coefficients
    return state


def _prediction_from_forecast(
    current_beta: np.ndarray,
    forecast_beta: np.ndarray,
) -> dict[str, float]:
    current_curve = _curve_from_betas(current_beta)
    future_curve = _curve_from_betas(forecast_beta)
    tenor_moves = {
        tenor: future_curve[tenor] - current_curve[tenor] for tenor in TENOR_TARGETS
    }
    return {
        **tenor_moves,
        "2s10s": tenor_moves["10Y"] - tenor_moves["2Y"],
        "5s30s": tenor_moves["30Y"] - tenor_moves["5Y"],
    }


def forecast_base_adjusted_attribution(
    coefficients: np.ndarray,
    last_beta: np.ndarray,
    last_macro: np.ndarray,
    *,
    macro_columns: list[str],
    horizon_days: int,
) -> dict[str, dict[str, dict[str, float]]]:
    """Return exact linear base-vs-adjusted attribution for one horizon."""
    intercept = coefficients[0]
    transition_a = coefficients[1:4]
    macro_b = coefficients[4 : 4 + len(macro_columns)]
    base = last_beta.astype(float).copy()
    adjusted = last_beta.astype(float).copy()
    block_contrib = {name: np.zeros(3, dtype=float) for name in macro_columns}

    for _ in range(max(1, int(horizon_days))):
        base = intercept + base @ transition_a
        adjusted = intercept + adjusted @ transition_a + last_macro @ macro_b
        for idx, name in enumerate(macro_columns):
            block_contrib[name] = block_contrib[name] @ transition_a + (
                last_macro[idx] * macro_b[idx]
            )

    total_beta_delta = adjusted - base
    summed_beta_delta = sum(block_contrib.values(), np.zeros(3, dtype=float))
    if not np.allclose(total_beta_delta, summed_beta_delta, atol=1e-8):
        raise AssertionError(
            "Macro block beta contributions do not sum to adjusted-base delta."
        )

    base_curve = _curve_from_betas(base)
    adjusted_curve = _curve_from_betas(adjusted)
    loading = _ns_loadings()
    tenor_block_contrib: dict[str, dict[str, float]] = {}
    for block, beta_delta in block_contrib.items():
        curve_delta = loading @ beta_delta
        tenor_block_contrib[block] = {
            "2Y": float(curve_delta[0]),
            "5Y": float(curve_delta[1]),
            "10Y": float(curve_delta[2]),
            "30Y": float(curve_delta[3]),
        }
        tenor_block_contrib[block]["2s10s"] = (
            tenor_block_contrib[block]["10Y"] - tenor_block_contrib[block]["2Y"]
        )
        tenor_block_contrib[block]["5s30s"] = (
            tenor_block_contrib[block]["30Y"] - tenor_block_contrib[block]["5Y"]
        )

    targets = {}
    for target in ("2Y", "5Y", "10Y", "30Y", "2s10s", "5s30s"):
        if target == "2s10s":
            base_value = base_curve["10Y"] - base_curve["2Y"]
            adjusted_value = adjusted_curve["10Y"] - adjusted_curve["2Y"]
        elif target == "5s30s":
            base_value = base_curve["30Y"] - base_curve["5Y"]
            adjusted_value = adjusted_curve["30Y"] - adjusted_curve["5Y"]
        else:
            base_value = base_curve[target]
            adjusted_value = adjusted_curve[target]
        contributions_bp = {
            block: float(values[target] * 100.0)
            for block, values in tenor_block_contrib.items()
        }
        total_delta_bp = float((adjusted_value - base_value) * 100.0)
        if not np.isclose(sum(contributions_bp.values()), total_delta_bp, atol=1e-6):
            raise AssertionError(
                f"{target} contributions do not sum to adjusted-base delta."
            )
        targets[target] = {
            "base": float(base_value),
            "adjusted": float(adjusted_value),
            "total_delta_bp": total_delta_bp,
            "contributions_bp": contributions_bp,
        }

    ns_factors = {}
    for idx, factor in enumerate(NS_FACTOR_NAMES):
        contributions = {
            block: float(delta[idx]) for block, delta in block_contrib.items()
        }
        total_delta = float(total_beta_delta[idx])
        if not np.isclose(sum(contributions.values()), total_delta, atol=1e-8):
            raise AssertionError(
                f"{factor} contributions do not sum to adjusted-base delta."
            )
        ns_factors[factor] = {
            "base": float(base[idx]),
            "adjusted": float(adjusted[idx]),
            "total_delta": total_delta,
            "contributions": contributions,
        }
    return {"ns_factors": ns_factors, "targets": targets}


def _point_in_time_inputs(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    release_lags = fred_release_lags()
    curve = _available_frame(df, list(NS_COLUMNS), release_lags)
    betas = nelson_siegel_beta_frame(curve)
    candidate_macro_cols = [
        "PCEPI",
        "PCEPILFE",
        "CPIAUCSL",
        "CPILFESL",
        "T5YIE",
        "T10YIE",
        "T5YIFR",
        "DGS3MO",
        "DGS6MO",
        "DFEDTARU",
        "EFFR",
        "FEDTARMD",
        "PAYEMS",
        "UNRATE",
        "ICSA",
        "NAPM",
        "IPMAN",
        "RSAFS",
        "JTSJOL",
        "T10Y2Y",
        "WALCL",
        "WRESBAL",
        "RRPONTSYD",
        "WTREGEN",
        "IRLTLT01DEM156N",
        "IRLTLT01JPM156N",
        "DTWEXBGS",
    ]
    macro_cols = [col for col in candidate_macro_cols if col in df.columns]
    macro_available = _available_frame(df, macro_cols, release_lags)
    macro_source = pd.concat(
        [curve, macro_available],
        axis=1,
        sort=True,
    ).sort_index()
    macro = _macro_feature_frame(macro_source, betas.index)
    return betas, macro


def realized_macro_data_audit(
    df: pd.DataFrame,
    *,
    as_of: str | pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Describe realized macro inputs that can move central vs future fan events."""
    history = df.sort_index()
    asof = (
        pd.Timestamp(as_of) if as_of is not None else pd.Timestamp(history.index.max())
    )
    release_lags = fred_release_lags()
    central_path: dict[str, dict[str, Any]] = {}
    for block, series_ids in REALIZED_MACRO_INPUTS.items():
        available: list[str] = []
        missing: list[str] = []
        latest_dates: dict[str, str] = {}
        for sid in series_ids:
            if sid == "fomc_tone":
                available.append(sid)
                latest_dates[sid] = asof.date().isoformat()
                continue
            if sid == "treasury_auction_stress":
                stress = auction_stress_asof(asof)
                if stress is None:
                    missing.append(
                        f"{sid} (cached TreasuryDirect auctions unavailable)"
                    )
                else:
                    available.append(sid)
                    latest_dates[sid] = asof.date().isoformat()
                continue
            if sid not in history:
                missing.append(sid)
                continue
            point_in_time = _available_frame(history, [sid], release_lags).loc[:asof]
            values = (
                point_in_time[sid].dropna() if sid in point_in_time else pd.Series()
            )
            if values.empty:
                missing.append(f"{sid} (not yet release-lag available)")
                continue
            available.append(sid)
            latest_dates[sid] = pd.Timestamp(values.index[-1]).date().isoformat()
        if block == "growth_risk" and not available and "T10Y2Y" in history:
            point_in_time = _available_frame(history, ["T10Y2Y"], release_lags).loc[
                :asof
            ]
            values = point_in_time["T10Y2Y"].dropna()
            if not values.empty:
                proxy_name = "T10Y2Y (fallback curve proxy)"
                available.append(proxy_name)
                latest_dates[proxy_name] = (
                    pd.Timestamp(values.index[-1]).date().isoformat()
                )
                missing.append(
                    "labor realized series absent in current cache; growth block "
                    "falls back to 2s10s curve stress proxy"
                )
        central_path[block] = {
            "available_series": available,
            "latest_dates": latest_dates,
            "missing_or_proxy": missing,
            "role": "already released values feed the FADNS macro block and can move central/p50",
        }

    return {
        "central_path_role": "already released macro data can move central/p50",
        "future_event_role": "scheduled unknown future events widen fan only",
        "central_overlay_exception": (
            "FOMC policy-path surprise can move central only when high-confidence "
            "cut/hike probabilities clear the configured threshold."
        ),
        "central_path": central_path,
        "fan_only_future_events": _fan_only_future_events(),
        "free_data_only": True,
        "point_in_time_release_lagged": True,
    }


def _fan_only_future_events() -> list[str]:
    try:
        releases = load_yaml("data_release_calendar").get("releases", [])
    except FileNotFoundError:
        releases = []
    event_types = {
        str(item.get("indicator", "")).lower()
        for item in releases
        if item.get("indicator")
    }
    event_types.update({"cpi", "nfp", "pce", "qra", "fomc"})
    return sorted(event_types)


def build_fadns_prediction_frames(
    df: pd.DataFrame,
    *,
    start: str = "2015-01-01",
    horizons: dict[str, int] | None = None,
    min_train: int = 756,
    ridge_alpha: float = 10.0,
) -> dict[str, pd.DataFrame]:
    """Build point-in-time FADNS prediction frames by horizon."""
    horizons = horizons or HORIZON_DAYS
    history = df.sort_index()
    betas, macro = _point_in_time_inputs(history)
    max_forecast_date = pd.Timestamp(history.index.max())
    forecast_index = betas.loc[start:].loc[:max_forecast_date].index
    rows = {horizon: [] for horizon in horizons}

    for date in forecast_index:
        train_betas = betas.loc[:date]
        if len(train_betas) < min_train:
            continue
        train_macro = macro.reindex(train_betas.index).fillna(0.0)
        coefficients = _ridge_transition(train_betas, train_macro, alpha=ridge_alpha)
        if coefficients is None:
            continue
        last_beta = train_betas.iloc[-1].to_numpy(dtype=float)
        last_macro = train_macro.iloc[-1].to_numpy(dtype=float)
        for horizon, horizon_days in horizons.items():
            forecast_beta = _forecast_beta(
                coefficients,
                last_beta,
                last_macro,
                horizon_days,
            )
            rows[horizon].append(
                {"date": date, **_prediction_from_forecast(last_beta, forecast_beta)}
            )

    return {
        horizon: (
            pd.DataFrame(values).set_index("date").sort_index()
            if values
            else pd.DataFrame(columns=TARGETS)
        )
        for horizon, values in rows.items()
    }


def _target_levels_from_beta(beta: np.ndarray) -> dict[str, float]:
    curve = _curve_from_betas(beta)
    return {
        **curve,
        "2s10s": curve["10Y"] - curve["2Y"],
        "5s30s": curve["30Y"] - curve["5Y"],
    }


def build_fadns_base_adjusted_prediction_frames(
    df: pd.DataFrame,
    *,
    start: str = "2015-01-01",
    horizons: dict[str, int] | None = None,
    min_train: int = 756,
    ridge_alpha: float = 10.0,
) -> dict[str, dict[str, pd.DataFrame]]:
    """Build paired base and adjusted FADNS prediction frames."""
    horizons = horizons or HORIZON_DAYS
    history = df.sort_index()
    betas, macro = _point_in_time_inputs(history)
    max_forecast_date = pd.Timestamp(history.index.max())
    forecast_index = betas.loc[start:].loc[:max_forecast_date].index
    rows = {
        model: {horizon: [] for horizon in horizons} for model in ("base", "adjusted")
    }

    for date in forecast_index:
        train_betas = betas.loc[:date]
        if len(train_betas) < min_train:
            continue
        train_macro = macro.reindex(train_betas.index).fillna(0.0)
        coefficients = _ridge_transition(train_betas, train_macro, alpha=ridge_alpha)
        if coefficients is None:
            continue
        last_beta = train_betas.iloc[-1].to_numpy(dtype=float)
        last_macro = train_macro.iloc[-1].to_numpy(dtype=float)
        current = _target_levels_from_beta(last_beta)
        for horizon, horizon_days in horizons.items():
            attribution = forecast_base_adjusted_attribution(
                coefficients,
                last_beta,
                last_macro,
                macro_columns=list(train_macro.columns),
                horizon_days=horizon_days,
            )
            base_row = {"date": date}
            adjusted_row = {"date": date}
            for target, values in attribution["targets"].items():
                base_row[target] = float(values["base"] - current[target])
                adjusted_row[target] = float(values["adjusted"] - current[target])
            rows["base"][horizon].append(base_row)
            rows["adjusted"][horizon].append(adjusted_row)

    return {
        model: {
            horizon: (
                pd.DataFrame(values).set_index("date").sort_index()
                if values
                else pd.DataFrame(columns=TARGETS)
            )
            for horizon, values in model_rows.items()
        }
        for model, model_rows in rows.items()
    }


def build_base_adjusted_ic_summary(
    df: pd.DataFrame,
    *,
    start: str = "2015-01-01",
    horizons: dict[str, int] | None = None,
    min_train: int = 756,
    ridge_alpha: float = 10.0,
) -> pd.DataFrame:
    """Return honest Rank IC rows for base vs adjusted FADNS predictions."""
    horizons = horizons or HORIZON_DAYS
    frames = build_fadns_base_adjusted_prediction_frames(
        df,
        start=start,
        horizons=horizons,
        min_train=min_train,
        ridge_alpha=ridge_alpha,
    )
    rows = []
    for model, horizon_frames in frames.items():
        for horizon, predictions in horizon_frames.items():
            targets = forward_curve_targets(df, int(horizons[horizon])).reindex(
                predictions.index
            )
            metrics = evaluate_prediction_frame(
                predictions,
                targets,
                model=f"fadns_{model}",
                horizon=horizon,
            )
            rows.extend(metrics.to_dict("records"))
    return pd.DataFrame(rows)


def _directional_accuracy(predicted: pd.Series, realized: pd.Series) -> float:
    data = pd.DataFrame({"predicted": predicted, "realized": realized}).dropna()
    if data.empty:
        return float("nan")
    return float((np.sign(data["predicted"]) == np.sign(data["realized"])).mean())


def build_macro_block_sanity_scorecard(
    df: pd.DataFrame,
    *,
    start: str = "2015-01-01",
    horizons: dict[str, int] | None = None,
) -> pd.DataFrame:
    """Backward-compatible alias for the Phase 4 macro-block IC sanity table."""
    return build_macro_block_ic_scorecard(df, start=start, horizons=horizons)


def build_macro_block_ic_scorecard(
    df: pd.DataFrame,
    *,
    start: str = "2015-01-01",
    horizons: dict[str, int] | None = None,
) -> pd.DataFrame:
    """Point-in-time single-factor IC sanity rows for FADNS macro blocks."""
    horizons = horizons or HORIZON_DAYS
    _, macro = _point_in_time_inputs(df.sort_index())
    forecast_index = macro.loc[start:].index
    rows = []
    for block in MACRO_BLOCKS:
        signal = macro[block].reindex(forecast_index)
        for horizon, days in horizons.items():
            targets = forward_curve_targets(df, int(days)).reindex(forecast_index)
            noise_band = _noise_band_for_horizon(horizon)
            for target in MACRO_BLOCK_ALIGNED_TARGETS[block]:
                expected_sign = MACRO_BLOCK_EXPECTED_SIGNS[(block, target)]
                sign_multiplier = _expected_sign_multiplier(expected_sign)
                signed_signal = signal * sign_multiplier
                metrics = evaluate_prediction_frame(
                    pd.DataFrame({target: signed_signal}),
                    targets,
                    model=f"macro_block:{block}",
                    horizon=str(horizon),
                    targets=(target,),
                )
                metric = metrics.iloc[0] if not metrics.empty else pd.Series()
                signed_rank_ic = metric.get("rank_ic", float("nan"))
                rank_ic = (
                    signed_rank_ic * sign_multiplier
                    if not pd.isna(signed_rank_ic)
                    else float("nan")
                )
                nw = fit_hac_regression(
                    targets[target],
                    signed_signal.rename("signal").to_frame(),
                    lag=int(days),
                    kernel="bartlett",
                )
                nw_t = nw.t_stats.get("signal", float("nan"))
                rows.append(
                    {
                        "macro_block": block,
                        "horizon": horizon,
                        "target": target,
                        "expected_sign": expected_sign,
                        "noise_band": noise_band,
                        "n": int(metric.get("n", 0)),
                        "rank_ic": rank_ic,
                        "signed_rank_ic": signed_rank_ic,
                        "directional_accuracy": metric.get(
                            "directional_accuracy",
                            float("nan"),
                        ),
                        "nw_t_stat": nw_t,
                        "nw_abs_t_stat": (
                            abs(nw_t) if not pd.isna(nw_t) else float("nan")
                        ),
                        "nw_p_value": nw.p_values.get("signal", float("nan")),
                        "correct_sign": (
                            signed_rank_ic > 0.0
                            if not pd.isna(signed_rank_ic)
                            else False
                        ),
                    }
                )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    verdicts = _macro_block_target_verdicts(out)
    out["verdict"] = [
        verdicts.get((block, target), "explanation-only")
        for block, target in zip(out["macro_block"], out["target"])
    ]
    out["decision"] = out["verdict"]
    return out


def _noise_band_for_horizon(horizon: str) -> float:
    return float(MACRO_BLOCK_IC_NOISE_BANDS.get(str(horizon), float("nan")))


def _expected_sign_multiplier(expected_sign: str) -> float:
    return -1.0 if expected_sign == "-" else 1.0


def _macro_block_target_verdicts(scorecard: pd.DataFrame) -> dict[tuple[str, str], str]:
    verdicts = {}
    for (block, target), group in scorecard.groupby(["macro_block", "target"]):
        by_horizon = {str(row["horizon"]): row for _, row in group.iterrows()}
        required = [h for h in ("3m", "6m") if h in by_horizon]
        if len(required) < 2:
            verdicts[(str(block), str(target))] = "explanation-only"
            continue
        correct_sign = all(bool(by_horizon[h]["correct_sign"]) for h in required)
        band_pass = all(
            not pd.isna(by_horizon[h]["signed_rank_ic"])
            and abs(float(by_horizon[h]["rank_ic"]))
            > float(by_horizon[h]["noise_band"])
            for h in required
        )
        nw_pass = any(
            not pd.isna(by_horizon[h]["nw_abs_t_stat"])
            and float(by_horizon[h]["nw_abs_t_stat"]) >= 2.0
            for h in required
        )
        verdicts[(str(block), str(target))] = (
            "signal" if correct_sign and (band_pass or nw_pass) else "explanation-only"
        )
    return verdicts


def summarize_macro_block_sanity(
    scorecard: pd.DataFrame,
) -> dict[str, dict[str, object]]:
    """Condense row-level IC sanity into trajectory JSON metadata."""
    if scorecard.empty:
        return {
            block: _empty_macro_block_sanity(
                block, MACRO_BLOCK_ALIGNED_TARGETS[block][0]
            )
            for block in MACRO_BLOCKS
        }

    summary = {}
    for block in MACRO_BLOCKS:
        block_rows = scorecard[scorecard["macro_block"].eq(block)]
        target = _macro_block_summary_target(block, block_rows)
        target_rows = block_rows[block_rows["target"].eq(target)]
        row_3m = _row_for_horizon(target_rows, "3m")
        row_6m = _row_for_horizon(target_rows, "6m")
        verdict = (
            str(target_rows["verdict"].iloc[0])
            if not target_rows.empty and "verdict" in target_rows
            else "explanation-only"
        )
        expected_sign = MACRO_BLOCK_EXPECTED_SIGNS[(block, target)]
        summary[block] = {
            "ic_3m": _json_float(row_3m.get("rank_ic")),
            "ic_6m": _json_float(row_6m.get("rank_ic")),
            "signed_ic_3m": _json_float(row_3m.get("signed_rank_ic")),
            "signed_ic_6m": _json_float(row_6m.get("signed_rank_ic")),
            "dir_acc_3m": _json_float(row_3m.get("directional_accuracy")),
            "dir_acc_6m": _json_float(row_6m.get("directional_accuracy")),
            "nw_t_3m": _json_float(row_3m.get("nw_t_stat")),
            "nw_t_6m": _json_float(row_6m.get("nw_t_stat")),
            "noise_band_3m": MACRO_BLOCK_IC_NOISE_BANDS["3m"],
            "noise_band_6m": MACRO_BLOCK_IC_NOISE_BANDS["6m"],
            "aligned_target": target,
            "expected_sign": expected_sign,
            "verdict": verdict,
            "note": _macro_block_sanity_note(verdict, expected_sign),
        }
    return summary


def _empty_macro_block_sanity(block: str, target: str) -> dict[str, object]:
    return {
        "ic_3m": None,
        "ic_6m": None,
        "signed_ic_3m": None,
        "signed_ic_6m": None,
        "dir_acc_3m": None,
        "dir_acc_6m": None,
        "nw_t_3m": None,
        "nw_t_6m": None,
        "noise_band_3m": MACRO_BLOCK_IC_NOISE_BANDS["3m"],
        "noise_band_6m": MACRO_BLOCK_IC_NOISE_BANDS["6m"],
        "aligned_target": target,
        "expected_sign": MACRO_BLOCK_EXPECTED_SIGNS[(block, target)],
        "verdict": "explanation-only",
        "note": "No sufficient point-in-time aligned observations; kept as explanation-only.",
    }


def _macro_block_summary_target(block: str, block_rows: pd.DataFrame) -> str:
    aligned_targets = MACRO_BLOCK_ALIGNED_TARGETS[block]
    for target in aligned_targets:
        target_rows = block_rows[block_rows["target"].eq(target)]
        if not target_rows.empty and target_rows["verdict"].eq("signal").any():
            return target
    return aligned_targets[0]


def _row_for_horizon(rows: pd.DataFrame, horizon: str) -> pd.Series:
    matching = rows[rows["horizon"].astype(str).eq(horizon)]
    return matching.iloc[0] if not matching.empty else pd.Series(dtype=object)


def _json_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _macro_block_sanity_note(verdict: str, expected_sign: str) -> str:
    direction = "positive" if expected_sign == "+" else "negative"
    if verdict == "signal":
        return (
            f"Correct {direction} sign and clears the 3m/6m IC noise band "
            "or Newey-West |t| >= 2."
        )
    return (
        f"Does not clear the correct {direction} sign plus IC noise-band/NW-t gate; "
        "kept for attribution and narrative only."
    )


def run_macro_block_ic_sanity(
    df: pd.DataFrame,
    *,
    start: str = "2015-01-01",
    horizons: dict[str, int] | None = None,
    output_path: str | Path = MACRO_BLOCK_IC_OUTPUT,
) -> pd.DataFrame:
    """Write Phase 4 macro-block single-factor IC sanity CSV."""
    scorecard = build_macro_block_ic_scorecard(df, start=start, horizons=horizons)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    scorecard.to_csv(output_path, index=False)
    print(
        "Macro block single-factor IC sanity "
        "(point-in-time, release-lagged; IC noise bands: "
        "3m=0.15, 6m=0.22)"
    )
    if not scorecard.empty:
        print(
            scorecard[
                [
                    "macro_block",
                    "horizon",
                    "target",
                    "expected_sign",
                    "rank_ic",
                    "directional_accuracy",
                    "nw_abs_t_stat",
                    "noise_band",
                    "verdict",
                ]
            ].to_string(index=False)
        )
    print(f"Wrote Phase 4 macro block IC -> {output_path} ({len(scorecard)} rows)")
    return scorecard


def _spearman(predicted: pd.Series, realized: pd.Series) -> float:
    data = pd.DataFrame({"predicted": predicted, "realized": realized}).dropna()
    if (
        len(data) < 2
        or data["predicted"].nunique() < 2
        or data["realized"].nunique() < 2
    ):
        return float("nan")
    return float(data["predicted"].rank().corr(data["realized"].rank()))


def _policy_path_lookup(
    phase1_scorecard: pd.DataFrame | None,
) -> dict[tuple[str, str], float]:
    if phase1_scorecard is None or phase1_scorecard.empty:
        return {}
    detail = phase1_scorecard[
        phase1_scorecard.get("factor", pd.Series(dtype=str))
        .astype(str)
        .eq("policy_path")
    ]
    if "row_type" in detail:
        detail = detail[detail["row_type"].astype(str).eq("factor")]
    return {
        (str(row["horizon"]), str(row["target"])): float(row["rank_ic"])
        for _, row in detail.dropna(subset=["rank_ic"]).iterrows()
    }


def _fadns_scorecard_rows(
    df: pd.DataFrame,
    predictions_by_horizon: dict[str, pd.DataFrame],
    *,
    phase0_scorecard: pd.DataFrame | None,
    phase1_scorecard: pd.DataFrame | None,
) -> pd.DataFrame:
    benchmark_lookup = max_benchmark_lookup(phase0_scorecard)
    policy_lookup = _policy_path_lookup(phase1_scorecard)
    rows = []
    for horizon, predictions in predictions_by_horizon.items():
        horizon_days = HORIZON_DAYS.get(horizon)
        if horizon_days is None:
            horizon_days = 63 if horizon == "3m" else 126
        targets = forward_curve_targets(df, horizon_days).reindex(predictions.index)
        metrics = evaluate_prediction_frame(
            predictions, targets, model="fadns", horizon=horizon
        )
        for _, metric in metrics.iterrows():
            target = str(metric["target"])
            predicted = predictions[target].reindex(targets.index)
            realized = targets[target]
            hac = fit_hac_regression(
                realized,
                predicted.rename("signal").to_frame(),
                lag=int(horizon_days),
                kernel="bartlett",
            )
            benchmark_rank_ic, benchmark_source_model = benchmark_lookup.get(
                (horizon, target),
                (float("nan"), ""),
            )
            policy_rank_ic = policy_lookup.get((horizon, target), float("nan"))
            rank_ic = float(metric["rank_ic"])
            rows.append(
                {
                    "model": "fadns",
                    "horizon": horizon,
                    "target": target,
                    "n": int(metric["n"]),
                    "rank_ic": rank_ic,
                    "benchmark_model": "max_random_walk_momentum",
                    "benchmark_source_model": benchmark_source_model,
                    "benchmark_rank_ic": benchmark_rank_ic,
                    "benchmark_delta_ic": (
                        rank_ic - benchmark_rank_ic
                        if not pd.isna(benchmark_rank_ic)
                        else float("nan")
                    ),
                    "policy_path_rank_ic": policy_rank_ic,
                    "policy_path_delta_ic": (
                        rank_ic - policy_rank_ic
                        if not pd.isna(policy_rank_ic)
                        else float("nan")
                    ),
                    "beta": hac.params.get("signal", float("nan")),
                    "nw_t_stat": hac.t_stats.get("signal", float("nan")),
                    "nw_abs_t_stat": abs(hac.t_stats.get("signal", float("nan"))),
                    "nw_p_value": hac.p_values.get("signal", float("nan")),
                    "r2": hac.r2,
                    "directional_accuracy": metric["directional_accuracy"],
                    "quantile_monotonic": metric["quantile_monotonic"],
                    "quantile_realized_means": metric["quantile_realized_means"],
                    "beats_benchmark": (
                        rank_ic > benchmark_rank_ic
                        if not pd.isna(benchmark_rank_ic)
                        else False
                    ),
                    "beats_policy_path": (
                        rank_ic > policy_rank_ic
                        if not pd.isna(policy_rank_ic)
                        else False
                    ),
                    "hac_significant": abs(hac.t_stats.get("signal", float("nan")))
                    >= 2.0,
                }
            )
    out = pd.DataFrame(rows)
    if not out.empty:
        out["validated_pass"] = out["beats_benchmark"] & out["hac_significant"]
    return out


def _print_fadns_summary(scorecard: pd.DataFrame) -> None:
    print("\nFADNS scorecard")
    print("-" * 104)
    curve_rows = scorecard[scorecard["target"].isin(["2s10s", "5s30s"])]
    for _, row in curve_rows.iterrows():
        print(
            f"{row['horizon']:>2s} {row['target']:>6s} "
            f"IC={row['rank_ic']: .3f} "
            f"bar={row['benchmark_rank_ic']: .3f} "
            f"delta={row['benchmark_delta_ic']: .3f} "
            f"policy_delta={row['policy_path_delta_ic']: .3f} "
            f"NW t={row['nw_t_stat']: .2f}"
        )


def run_fadns_scorecard(
    df: pd.DataFrame,
    *,
    start: str = "2015-01-01",
    phase0_scorecard: pd.DataFrame | None,
    phase1_scorecard: pd.DataFrame | None = None,
    output_path: str | Path = DEFAULT_OUTPUT,
    horizons: dict[str, int] | None = None,
    min_train: int = 756,
    ridge_alpha: float = 10.0,
) -> pd.DataFrame:
    """Run point-in-time FADNS forecasts through Phase 0 and HAC metrics."""
    history = df.sort_index()
    predictions = build_fadns_prediction_frames(
        history,
        start=start,
        horizons=horizons,
        min_train=min_train,
        ridge_alpha=ridge_alpha,
    )
    scorecard = _fadns_scorecard_rows(
        history,
        predictions,
        phase0_scorecard=phase0_scorecard,
        phase1_scorecard=phase1_scorecard,
    )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    scorecard.to_csv(output_path, index=False)
    print(f"Wrote FADNS scorecard -> {output_path} ({len(scorecard)} rows)")
    _print_fadns_summary(scorecard)
    return scorecard
