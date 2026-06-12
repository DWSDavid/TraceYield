"""HAC significance tests for overlapping v3 forward windows."""

from __future__ import annotations

from dataclasses import dataclass
from math import erfc, sqrt
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest.eval import HORIZON_DAYS, TARGETS, forward_curve_targets
from src.backtest.single_factor import (
    _asof_to_index,
    _available_frame,
    _change_score_series,
    aligned_targets_for_factor,
    build_single_factor_prediction_frames,
)
from src.backtest.walk_forward import fred_release_lags
from src.signals.fomc_series import fomc_factor_asof
from src.utils.config import DATA

DEFAULT_OUTPUT = DATA / "backtest" / "phase1b_hac_significance.csv"
PRIMARY_BENCHMARKS = ("random_walk", "momentum_3m")
CONTROL_TARGETS = ("2s10s", "2Y", "5Y", "10Y", "30Y")
CURVE_COLUMNS = ["DGS2", "DGS5", "DGS10", "DGS30"]


@dataclass
class HACRegressionResult:
    n: int
    params: dict[str, float]
    std_errors: dict[str, float]
    t_stats: dict[str, float]
    p_values: dict[str, float]
    r2: float
    covariance_psd: bool


def _normal_p_value(t_stat: float) -> float:
    if pd.isna(t_stat):
        return float("nan")
    return float(erfc(abs(float(t_stat)) / sqrt(2.0)))


def _regression_frame(y: pd.Series, predictors: pd.DataFrame) -> pd.DataFrame:
    data = pd.concat([y.rename("y"), predictors], axis=1).dropna()
    for col in data.columns:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    return data.dropna()


def _kernel_weight(kernel: str, lag_idx: int, max_lag: int) -> float:
    if kernel == "bartlett":
        return 1.0 - lag_idx / (max_lag + 1.0)
    if kernel == "rectangular":
        return 1.0
    raise ValueError(f"Unsupported HAC kernel: {kernel}")


def _hac_covariance(
    design: np.ndarray,
    residuals: np.ndarray,
    xtx_inv: np.ndarray,
    lag: int,
    kernel: str,
) -> tuple[np.ndarray, bool]:
    nobs = len(residuals)
    max_lag = min(max(int(lag), 0), max(nobs - 1, 0))
    z = design * residuals[:, None]
    meat = z.T @ z

    for lag_idx in range(1, max_lag + 1):
        weight = _kernel_weight(kernel, lag_idx, max_lag)
        gamma = z[lag_idx:].T @ z[:-lag_idx]
        meat += weight * (gamma + gamma.T)

    covariance = xtx_inv @ meat @ xtx_inv
    covariance = (covariance + covariance.T) / 2.0
    eigvals = np.linalg.eigvalsh(covariance)
    covariance_psd = bool(np.nanmin(eigvals) >= -1e-10)
    return covariance, covariance_psd


def fit_hac_regression(
    y: pd.Series,
    predictors: pd.DataFrame,
    *,
    lag: int,
    kernel: str = "bartlett",
) -> HACRegressionResult:
    """Fit OLS y ~ predictors with HAC standard errors."""
    data = _regression_frame(y, predictors)
    predictor_names = list(predictors.columns)
    if len(data) <= len(predictor_names) + 1:
        empty = {name: float("nan") for name in predictor_names}
        return HACRegressionResult(
            n=int(len(data)),
            params=empty,
            std_errors=empty,
            t_stats=empty,
            p_values=empty,
            r2=float("nan"),
            covariance_psd=False,
        )

    x = data[predictor_names].to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(data)), x])
    y_arr = data["y"].to_numpy(dtype=float)
    xtx_inv = np.linalg.pinv(design.T @ design)
    beta = xtx_inv @ design.T @ y_arr
    fitted = design @ beta
    residuals = y_arr - fitted
    covariance, covariance_psd = _hac_covariance(
        design,
        residuals,
        xtx_inv,
        lag=lag,
        kernel=kernel,
    )
    diag = np.diag(covariance)[1:]
    std_errors = np.sqrt(np.where(diag >= 0.0, diag, np.nan))
    slopes = beta[1:]
    t_stats = np.divide(
        slopes,
        std_errors,
        out=np.full_like(slopes, np.nan, dtype=float),
        where=(std_errors != 0) & ~np.isnan(std_errors),
    )
    ss_res = float(np.sum(residuals**2))
    ss_tot = float(np.sum((y_arr - y_arr.mean()) ** 2))
    r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan")

    return HACRegressionResult(
        n=int(len(data)),
        params={name: float(value) for name, value in zip(predictor_names, slopes)},
        std_errors={
            name: float(value) for name, value in zip(predictor_names, std_errors)
        },
        t_stats={name: float(value) for name, value in zip(predictor_names, t_stats)},
        p_values={
            name: _normal_p_value(value)
            for name, value in zip(predictor_names, t_stats)
        },
        r2=r2,
        covariance_psd=covariance_psd,
    )


def _spearman(predicted: pd.Series, realized: pd.Series) -> float:
    data = pd.DataFrame({"predicted": predicted, "realized": realized}).dropna()
    if (
        len(data) < 2
        or data["predicted"].nunique() < 2
        or data["realized"].nunique() < 2
    ):
        return float("nan")
    return float(data["predicted"].rank().corr(data["realized"].rank()))


def max_benchmark_lookup(
    phase0_scorecard: pd.DataFrame | None,
) -> dict[tuple[str, str], tuple[float, str]]:
    """Return max(random_walk, momentum_3m) Rank IC by horizon/target."""
    if phase0_scorecard is None or phase0_scorecard.empty:
        return {}
    detail = phase0_scorecard[
        phase0_scorecard["model"].astype(str).isin(PRIMARY_BENCHMARKS)
    ]
    lookup = {}
    for (horizon, target), group in detail.groupby(["horizon", "target"]):
        valid = group.dropna(subset=["rank_ic"])
        if valid.empty:
            continue
        best = valid.sort_values("rank_ic", ascending=False).iloc[0]
        lookup[(str(horizon), str(target))] = (
            float(best["rank_ic"]),
            str(best["model"]),
        )
    return lookup


def _hh_result_or_fallback(
    y: pd.Series,
    x: pd.DataFrame,
    lag: int,
    nw: HACRegressionResult,
) -> tuple[HACRegressionResult, bool]:
    hh = fit_hac_regression(y, x, lag=lag, kernel="rectangular")
    if hh.covariance_psd:
        return hh, False
    return nw, True


def _hac_row(
    *,
    factor: str,
    horizon: str,
    target: str,
    predicted: pd.Series,
    realized: pd.Series,
    benchmark_rank_ic: float,
    benchmark_source_model: str,
    lag: int,
) -> dict:
    predictor = predicted.rename("signal").to_frame()
    nw = fit_hac_regression(realized, predictor, lag=lag, kernel="bartlett")
    hh, hh_fallback = _hh_result_or_fallback(realized, predictor, lag, nw)
    rank_ic = _spearman(predicted, realized)
    benchmark_delta = (
        float(rank_ic - benchmark_rank_ic)
        if not pd.isna(rank_ic) and not pd.isna(benchmark_rank_ic)
        else float("nan")
    )
    nw_t = nw.t_stats.get("signal", float("nan"))
    return {
        "row_type": "factor",
        "factor": factor,
        "horizon": horizon,
        "target": target,
        "n": nw.n,
        "rank_ic": rank_ic,
        "benchmark_model": "max_random_walk_momentum",
        "benchmark_source_model": benchmark_source_model,
        "benchmark_rank_ic": benchmark_rank_ic,
        "benchmark_delta_ic": benchmark_delta,
        "beta": nw.params.get("signal", float("nan")),
        "nw_t_stat": nw_t,
        "nw_abs_t_stat": abs(nw_t) if not pd.isna(nw_t) else float("nan"),
        "nw_p_value": nw.p_values.get("signal", float("nan")),
        "hh_t_stat": hh.t_stats.get("signal", float("nan")),
        "hh_p_value": hh.p_values.get("signal", float("nan")),
        "hh_covariance_psd": hh.covariance_psd,
        "hh_fallback_to_nw": hh_fallback,
        "r2": nw.r2,
    }


def _with_decisions(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return rows
    rows = rows.copy()
    rows["aligned_target"] = [
        target in aligned_targets_for_factor(factor)
        for factor, target in zip(rows["factor"], rows["target"])
    ]
    rows["beats_benchmark"] = rows["rank_ic"] > rows["benchmark_rank_ic"]
    rows["nw_significant"] = rows["nw_abs_t_stat"] >= 2.0
    rows["hac_pass"] = (
        rows["aligned_target"] & rows["beats_benchmark"] & rows["nw_significant"]
    )
    decisions = {}
    for factor, group in rows.groupby("factor"):
        decision = {
            "decision_tag": "fail",
            "decision_target": "",
            "decision_reason": "no_aligned_target_beats_bar_with_nw_t_ge_2_both_horizons",
        }
        for target, target_rows in group[group["aligned_target"]].groupby("target"):
            horizons = set(target_rows.loc[target_rows["hac_pass"], "horizon"])
            if set(HORIZON_DAYS).issubset(horizons):
                decision = {
                    "decision_tag": "keep",
                    "decision_target": target,
                    "decision_reason": "beats_max_phase0_bar_and_nw_t_ge_2_both_horizons",
                }
                break
        decisions[factor] = decision
    for col in ("decision_tag", "decision_target", "decision_reason"):
        rows[col] = [decisions[factor][col] for factor in rows["factor"]]
    return rows


def build_phase1b_hac_scorecard(
    factor_predictions: dict[str, pd.DataFrame],
    targets_by_horizon: dict[str, pd.DataFrame],
    *,
    phase0_scorecard: pd.DataFrame | None,
    start: str = "2015-01-01",
    hac_lags: dict[str, int] | None = None,
) -> pd.DataFrame:
    """Build HAC significance rows for isolated Phase 1 factor predictions."""
    hac_lags = hac_lags or HORIZON_DAYS
    benchmark_lookup = max_benchmark_lookup(phase0_scorecard)
    rows = []
    for factor, predictions in factor_predictions.items():
        for horizon, targets in targets_by_horizon.items():
            lag = int(hac_lags.get(horizon, HORIZON_DAYS.get(horizon, 0)))
            aligned_targets = targets.loc[start:]
            aligned_predictions = predictions.reindex(aligned_targets.index)
            for target in TARGETS:
                if target not in aligned_predictions or target not in aligned_targets:
                    continue
                benchmark_rank_ic, benchmark_source_model = benchmark_lookup.get(
                    (horizon, target),
                    (float("nan"), ""),
                )
                rows.append(
                    _hac_row(
                        factor=factor,
                        horizon=horizon,
                        target=target,
                        predicted=aligned_predictions[target],
                        realized=aligned_targets[target],
                        benchmark_rank_ic=benchmark_rank_ic,
                        benchmark_source_model=benchmark_source_model,
                        lag=lag,
                    )
                )
    return _with_decisions(pd.DataFrame(rows))


def _front_momentum_frame(df: pd.DataFrame, index: pd.Index) -> pd.DataFrame:
    release_lags = fred_release_lags()
    curve = _available_frame(df, CURVE_COLUMNS, release_lags)
    front_momentum = 0.60 * _change_score_series(
        curve["DGS2"], periods=63, full_scale=0.50
    ) + 0.40 * _change_score_series(curve["DGS5"], periods=63, full_scale=0.50)
    return pd.DataFrame(
        {
            "fomc_tone": pd.Series(
                [fomc_factor_asof(d) for d in index],
                index=index,
                dtype="float64",
            ),
            "front_momentum": _asof_to_index(front_momentum, index),
        }
    )


def build_fomc_control_hac_rows(
    df: pd.DataFrame,
    targets_by_horizon: dict[str, pd.DataFrame],
    *,
    start: str = "2015-01-01",
    hac_lags: dict[str, int] | None = None,
) -> pd.DataFrame:
    """Test FOMC tone after controlling for front-end momentum."""
    hac_lags = hac_lags or HORIZON_DAYS
    forecast_index = df["DGS10"].dropna().loc[start:].index
    predictors = _front_momentum_frame(df, forecast_index)
    rows = []
    for horizon, targets in targets_by_horizon.items():
        aligned_targets = targets.loc[start:]
        x = predictors.reindex(aligned_targets.index)
        lag = int(hac_lags.get(horizon, HORIZON_DAYS.get(horizon, 0)))
        for target in CONTROL_TARGETS:
            result = fit_hac_regression(
                aligned_targets[target],
                x[["fomc_tone", "front_momentum"]],
                lag=lag,
                kernel="bartlett",
            )
            fomc_t = result.t_stats.get("fomc_tone", float("nan"))
            rows.append(
                {
                    "row_type": "fomc_control",
                    "factor": "fomc_tone_after_front_momentum",
                    "horizon": horizon,
                    "target": target,
                    "n": result.n,
                    "rank_ic": float("nan"),
                    "benchmark_model": "",
                    "benchmark_source_model": "",
                    "benchmark_rank_ic": float("nan"),
                    "benchmark_delta_ic": float("nan"),
                    "beta": result.params.get("fomc_tone", float("nan")),
                    "nw_t_stat": fomc_t,
                    "nw_abs_t_stat": (
                        abs(fomc_t) if not pd.isna(fomc_t) else float("nan")
                    ),
                    "nw_p_value": result.p_values.get("fomc_tone", float("nan")),
                    "hh_t_stat": float("nan"),
                    "hh_p_value": float("nan"),
                    "hh_covariance_psd": "",
                    "hh_fallback_to_nw": "",
                    "r2": result.r2,
                    "aligned_target": True,
                    "beats_benchmark": "",
                    "nw_significant": (
                        abs(fomc_t) >= 2.0 if not pd.isna(fomc_t) else False
                    ),
                    "hac_pass": "",
                    "decision_tag": "diagnostic",
                    "decision_target": target,
                    "decision_reason": "fomc_tone_hac_t_after_front_momentum_control",
                    "front_momentum_beta": result.params.get(
                        "front_momentum", float("nan")
                    ),
                    "front_momentum_nw_t_stat": result.t_stats.get(
                        "front_momentum", float("nan")
                    ),
                }
            )
    return pd.DataFrame(rows)


def _print_hac_summary(scorecard: pd.DataFrame) -> None:
    factor_rows = scorecard[scorecard["row_type"].eq("factor")]
    decisions = (
        factor_rows[["factor", "decision_tag", "decision_target", "decision_reason"]]
        .drop_duplicates()
        .sort_values(["decision_tag", "factor"])
    )
    print("\nPhase 1b HAC decisions")
    print("-" * 96)
    for _, row in decisions.iterrows():
        print(
            f"{row['factor'][:30]:30s} {row['decision_tag']:>6s} "
            f"target={row['decision_target'] or '-':>6s} "
            f"{row['decision_reason']}"
        )

    controls = scorecard[scorecard["row_type"].eq("fomc_control")]
    if not controls.empty:
        print("\nFOMC tone after front-momentum control (NW t-stat)")
        print("-" * 72)
        for _, row in controls.iterrows():
            print(
                f"{row['horizon']:>2s} {row['target']:>6s}: "
                f"beta={row['beta']: .4f}  t={row['nw_t_stat']: .2f}  "
                f"p={row['nw_p_value']: .3f}"
            )


def run_phase1b_hac_significance(
    df: pd.DataFrame,
    *,
    start: str = "2015-01-01",
    phase0_scorecard: pd.DataFrame | None,
    output_path: str | Path = DEFAULT_OUTPUT,
) -> pd.DataFrame:
    """Run HAC significance testing for all Phase 1 isolated factors."""
    history = df.sort_index()
    factor_predictions = build_single_factor_prediction_frames(history, start=start)
    targets_by_horizon = {
        horizon: forward_curve_targets(history, days).loc[start:]
        for horizon, days in HORIZON_DAYS.items()
    }
    factor_rows = build_phase1b_hac_scorecard(
        factor_predictions,
        targets_by_horizon,
        phase0_scorecard=phase0_scorecard,
        start=start,
    )
    control_rows = build_fomc_control_hac_rows(
        history,
        targets_by_horizon,
        start=start,
    )
    out = pd.concat([factor_rows, control_rows], ignore_index=True, sort=False)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False)
    print(f"Wrote Phase 1b HAC significance -> {output_path} ({len(out)} rows)")
    _print_hac_summary(out)
    return out
