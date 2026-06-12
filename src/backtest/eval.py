"""Reusable v3 curve-trade evaluation harness.

All signals are point-in-time inputs indexed by the forecast date. Realized
targets are forward changes computed only for dates with a full future horizon.
Positive spread targets mean steepening: 2s10s = DGS10 - DGS2 and
5s30s = DGS30 - DGS5.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

TENOR_COLUMNS = {"2Y": "DGS2", "5Y": "DGS5", "10Y": "DGS10", "30Y": "DGS30"}
CURVE_SPREADS = {"2s10s": ("DGS10", "DGS2"), "5s30s": ("DGS30", "DGS5")}
TARGETS = (*TENOR_COLUMNS.keys(), *CURVE_SPREADS.keys())
HORIZON_DAYS = {"3m": 63, "6m": 126}


def _required_columns() -> list[str]:
    cols = set(TENOR_COLUMNS.values())
    for long_col, short_col in CURVE_SPREADS.values():
        cols.add(long_col)
        cols.add(short_col)
    return sorted(cols)


def curve_spread_levels(df: pd.DataFrame) -> pd.DataFrame:
    """Return 2s10s and 5s30s spread levels from Treasury yield columns."""
    out = pd.DataFrame(index=df.index)
    for name, (long_col, short_col) in CURVE_SPREADS.items():
        out[name] = df[long_col] - df[short_col]
    return out


def forward_curve_shapes(df: pd.DataFrame, horizon_days: int) -> pd.DataFrame:
    """Return future spread levels aligned to each forecast date."""
    clean = df[_required_columns()].dropna().sort_index()
    future = clean.shift(-horizon_days)
    shapes = pd.DataFrame(index=clean.index)
    for name, (long_col, short_col) in CURVE_SPREADS.items():
        shapes[name] = future[long_col] - future[short_col]
    return shapes.dropna(how="any")


def forward_curve_targets(df: pd.DataFrame, horizon_days: int) -> pd.DataFrame:
    """Compute forward tenor and curve-spread changes for one horizon."""
    clean = df[_required_columns()].dropna().sort_index()
    future = clean.shift(-horizon_days)
    targets = pd.DataFrame(index=clean.index)

    for tenor, col in TENOR_COLUMNS.items():
        targets[tenor] = future[col] - clean[col]

    current_spreads = curve_spread_levels(clean)
    future_spreads = curve_spread_levels(future)
    for spread in CURVE_SPREADS:
        targets[spread] = future_spreads[spread] - current_spreads[spread]

    return targets.dropna(how="any")


def _spearman(predicted: pd.Series, realized: pd.Series) -> float:
    data = pd.DataFrame({"predicted": predicted, "realized": realized}).dropna()
    if len(data) < 2:
        return float("nan")
    if data["predicted"].nunique() < 2 or data["realized"].nunique() < 2:
        return float("nan")
    return float(data["predicted"].rank().corr(data["realized"].rank()))


def _directional_accuracy(predicted: pd.Series, realized: pd.Series) -> float:
    data = pd.DataFrame({"predicted": predicted, "realized": realized}).dropna()
    if data.empty:
        return float("nan")
    return float((np.sign(data["predicted"]) == np.sign(data["realized"])).mean())


def _period_icir(
    predicted: pd.Series,
    realized: pd.Series,
    freq: str,
    min_group_obs: int,
) -> float:
    data = pd.DataFrame({"predicted": predicted, "realized": realized}).dropna()
    if data.empty:
        return float("nan")

    ics = []
    for _, group in data.groupby(pd.Grouper(freq=freq)):
        if len(group) < min_group_obs:
            continue
        ic = _spearman(group["predicted"], group["realized"])
        if not np.isnan(ic):
            ics.append(ic)

    if len(ics) < 2:
        return float("nan")
    std = float(pd.Series(ics).std(ddof=1))
    if std == 0 or np.isnan(std):
        return float("nan")
    return float(pd.Series(ics).mean() / std)


def _quantile_check(
    predicted: pd.Series,
    realized: pd.Series,
    quantiles: int,
) -> tuple[bool, str]:
    data = pd.DataFrame({"predicted": predicted, "realized": realized}).dropna()
    if len(data) < quantiles or data["predicted"].nunique() < quantiles:
        return False, ""

    buckets = pd.qcut(
        data["predicted"].rank(method="first"),
        q=quantiles,
        labels=False,
        duplicates="drop",
    )
    means = data.groupby(buckets, observed=True)["realized"].mean().sort_index()
    if len(means) < quantiles:
        return False, "|".join(f"{value:.6f}" for value in means)

    diffs = means.diff().dropna()
    monotonic = bool((diffs >= -1e-12).all())
    return monotonic, "|".join(f"{value:.6f}" for value in means)


def _shape_hit_rate(
    target: str,
    predicted_shapes: pd.DataFrame | None,
    future_shapes: pd.DataFrame | None,
) -> float:
    if (
        predicted_shapes is None
        or future_shapes is None
        or target not in predicted_shapes
        or target not in future_shapes
    ):
        return float("nan")
    data = pd.DataFrame(
        {
            "predicted": predicted_shapes[target],
            "future": future_shapes[target],
        }
    ).dropna()
    if data.empty:
        return float("nan")
    return float((np.sign(data["predicted"]) == np.sign(data["future"])).mean())


def evaluate_prediction_frame(
    predictions: pd.DataFrame,
    realized_targets: pd.DataFrame,
    *,
    model: str,
    horizon: str,
    targets: Iterable[str] = TARGETS,
    predicted_shapes: pd.DataFrame | None = None,
    future_shapes: pd.DataFrame | None = None,
    quantiles: int = 5,
    icir_freq: str = "QE",
    min_icir_obs: int = 20,
) -> pd.DataFrame:
    """Evaluate a model/factor prediction frame against realized targets."""
    rows = []
    aligned_predictions = predictions.sort_index()
    aligned_targets = realized_targets.sort_index()

    for target in targets:
        if target not in aligned_predictions or target not in aligned_targets:
            continue
        predicted = aligned_predictions[target].reindex(aligned_targets.index)
        realized = aligned_targets[target]
        monotonic, q_means = _quantile_check(predicted, realized, quantiles)
        data = pd.DataFrame({"predicted": predicted, "realized": realized}).dropna()
        rows.append(
            {
                "model": model,
                "horizon": horizon,
                "target": target,
                "n": int(len(data)),
                "rank_ic": _spearman(predicted, realized),
                "icir": _period_icir(predicted, realized, icir_freq, min_icir_obs),
                "directional_accuracy": _directional_accuracy(predicted, realized),
                "curve_shape_hit_rate": _shape_hit_rate(
                    target, predicted_shapes, future_shapes
                ),
                "quantile_monotonic": monotonic,
                "quantile_realized_means": q_means,
            }
        )

    out = pd.DataFrame(rows)
    if "quantile_monotonic" in out:
        out["quantile_monotonic"] = out["quantile_monotonic"].astype(object)
    return out
