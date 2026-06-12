# TraceYield

**Daily-triggered US Treasury yield prediction.** Aggregates Fed communications +
macro factors into an interpretable, backtestable call on where the **10-Year
Treasury yield** is headed — direction, confidence, and level — across 1-week,
1-month, and 3-month horizons. Plus yield-curve shape and (later) a cross-asset
impact map.

> Predict the Fed + inflation + liquidity → predict the 10Y → predict almost
> every other market that prices off it.

## Quickstart
```powershell
cd $env:USERPROFILE\Desktop\TraceYield
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env          # then add your FRED_API_KEY (free)
python scripts\daily_run.py     # generates data/reports/report_<date>.md
```

## How it works
```
FRED + Fed docs ─▶ 5 factor scores ─▶ weighted blend ─▶ direction + 10Y target ─▶ report
                   (fomc_nlp 30% · inflation 25% · liquidity 20%
                    · global_rates 15% · political_risk 10%)
```
- **Interpretable by design** — every call decomposes into signed factor
  contributions. XGBoost/LightGBM can refine the blend later without changing the
  contract.
- **Config-driven** — all weights/series in `configs/`. Backtesting tunes them.
- **Backtest is truth** — nothing ships without a walk-forward out-of-sample check.

## Two tracks, in parallel
1. **Build** — the pipeline above (`src/`, `scripts/`, `configs/`).
2. **Understand** — the plain-English curriculum in [`docs/concepts/`](docs/concepts/00-roadmap.md):
   the Fed/FOMC, the 10Y, the cross-asset chain reaction, full glossary.
   Use the **macro-tutor** subagent (`.claude/agents/macro-tutor.md`) to ask
   anything and pull live data.

## Layout
See [`CLAUDE.md`](CLAUDE.md) for the full repo map and design decisions.

## Chinese handoff docs
- [`docs/USER_GUIDE_ZH.md`](docs/USER_GUIDE_ZH.md) - Chinese daily SOP, setup, output guide, report interpretation, and GitHub handoff rules.
- [`docs/NITTAN_FIXED_INCOME_BRIEF_ZH.md`](docs/NITTAN_FIXED_INCOME_BRIEF_ZH.md) - Manager-facing fixed-income rationale for Nittan / inter-dealer broker use cases, FADNS, baselines, and cross-market linkage.

## Status
🟢 **Manager handoff build.** Wired: FRED/FOMC ingestion, factor scoring, release-lagged backtests, FADNS curve trajectory, policy-path overlays, Polymarket external check, grounded macro explanation, Markdown reports, and self-contained HTML curve reports.

Current handoff focus: keep `scripts/daily_run.py`, `scripts/curve_run.py`, and `pytest` green; use the Chinese docs above for operating and explaining the system.

## Disclaimer
Research/educational tool. Not investment advice.
