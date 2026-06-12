"""Walk-forward backtest — does the blended signal actually predict yields?

For each historical day we compute factor scores using ONLY data up to that day
(no look-ahead), build the per-horizon blended score, and compare it to the
REALIZED change in the 10Y yield N days later.

Key metrics (threshold-free, so they judge the raw signal, not our arbitrary
±0.15 cutoff):
  - IC  : correlation(score, forward yield change). Positive = signal works
          (high score -> yields rise -> bond bearish, as intended).
  - DA  : directional accuracy using sign(score) vs sign(forward change).
Then a THRESHOLD SWEEP shows hit-rate vs coverage so we can calibrate the band.

NOTE: this tests the FRED-driven factors (inflation/liquidity/global_rates).
fomc_nlp and political_risk are 0 over history (no historical doc scoring yet),
so they don't contribute here — this is the macro-data baseline.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from src.signals.factors import compute_all, political_risk_proxy
from src.signals.fomc_series import fomc_factor_asof
from src.utils.config import fred_series, weights

HORIZON_DAYS = {"1m": 21, "3m": 63, "6m": 126, "12m": 252}


def fred_release_lags() -> dict[str, int]:
    """Configured publication lag per FRED series, in calendar days."""
    lags: dict[str, int] = {}
    for group in fred_series().values():
        for sid, meta in group.items():
            if isinstance(meta, dict):
                lags[sid] = int(meta.get("release_lag_days", 1))
            else:
                lags[sid] = 1
    return lags


def _lagged_history(
    df: pd.DataFrame,
    asof: pd.Timestamp,
    release_lags: dict[str, int],
) -> pd.DataFrame:
    """Column-wise point-in-time view using approximate public release lags."""
    asof = pd.Timestamp(asof)
    lagged = {}
    for col in df.columns:
        lag_days = int(release_lags.get(col, 1))
        cutoff = asof - timedelta(days=lag_days)
        lagged[col] = df[col].loc[:cutoff]
    return pd.DataFrame(lagged)


def _daily_factors(df: pd.DataFrame, start: str) -> pd.DataFrame:
    """Walk forward computing factor scores per day (point-in-time)."""
    df = df.sort_index()
    release_lags = fred_release_lags()
    rows = []
    for d in df.loc[start:].index:
        hist = _lagged_history(df, pd.Timestamp(d), release_lags)
        cur = hist["DGS10"].dropna()
        if cur.empty:
            continue
        f = compute_all(
            hist,
            hawkish=fomc_factor_asof(d),
            political=political_risk_proxy(hist),
        )
        rows.append({"date": d, "cur": float(cur.iloc[-1]), **f})
    return pd.DataFrame(rows).set_index("date")


def run(df: pd.DataFrame, start: str = "2015-01-01") -> dict:
    cfg = weights()
    horizons = cfg["horizons"]
    th_cfg = cfg["thresholds"]
    y = df["DGS10"].sort_index()
    bt = _daily_factors(df, start)

    summary = {}
    print(f"Backtest {start} -> {bt.index.max().date()}  ({len(bt)} days)\n")
    print(
        f"{'H':>4} {'IC':>7} {'DirAcc':>7} {'n':>6}   threshold sweep (hit% @ coverage%)"
    )
    print("-" * 78)

    contribs_3m = {
        f: float((bt[f].abs() * horizons["3m"][f]).mean())
        for f in horizons["3m"]
        if f in bt
    }
    contrib_str = "  ".join(f"{f}={v:.3f}" for f, v in contribs_3m.items())
    print(f"Avg |3m contrib|: {contrib_str}\n")

    for h, days in HORIZON_DAYS.items():
        score = sum(w * bt[f] for f, w in horizons[h].items())
        fwd = (y.shift(-days) - y).reindex(bt.index)  # realized change, % pts
        d = pd.DataFrame({"score": score, "fwd": fwd}).dropna()

        ic = d["score"].corr(d["fwd"])
        da = float((np.sign(d["score"]) == np.sign(d["fwd"])).mean())

        sweep = []
        for th in (0.05, 0.10, 0.15, 0.20, 0.30):
            sel = d[d["score"].abs() > th]
            cov = len(sel) / len(d) if len(d) else 0.0
            hit = (
                float((np.sign(sel["score"]) == np.sign(sel["fwd"])).mean())
                if len(sel)
                else float("nan")
            )
            sweep.append((th, hit, cov))

        sweep_str = "  ".join(
            f"{th:.2f}:{hit*100:4.0f}%@{cov*100:3.0f}%" for th, hit, cov in sweep
        )
        print(f"{h:>4} {ic:>7.3f} {da*100:>6.1f}% {len(d):>6}   {sweep_str}")
        summary[h] = {"ic": ic, "dir_acc": da, "n": len(d), "sweep": sweep}

    print(f"\nCurrent configured band: ±{th_cfg['bear_above']}")
    print("Read: IC>0 and DirAcc>50% => signal has predictive value.")
    print("Pick a threshold where hit% is comfortably >50% with usable coverage.")
    return summary
