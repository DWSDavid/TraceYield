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

## Status
🟡 **Scaffold.** Wired: structure, config, factor blend, report, backtest stub.
Next: real FRED ingestion run → keyword NLP on FOMC statements → first backtest.

## Disclaimer
Research/educational tool. Not investment advice.
