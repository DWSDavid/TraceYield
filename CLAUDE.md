# TraceYield — US Treasury Yield Direction Prediction

## Project overview
A daily-triggered system that predicts the **direction (bull/bear/neutral) and
point level** of US Treasury yields — primarily the **10-Year (UST 10Y)** — by
aggregating macro factors and Fed communications into an interpretable signal.

Secondary outputs: yield-curve shape forecasts (5Y–20Y, 2s10s, 5s30s) and a
cross-asset impact map (equities, gold, FX, commodities, global rates).

## Why this matters (one-liner)
The UST 10Y is the world's risk-free benchmark. Its direction drives mortgages,
corporate borrowing, equity valuations, EM capital flows, and FX. Predicting it
accurately = an edge across nearly every asset class.

## Prediction targets & horizons
- **Primary:** UST 10Y yield direction + level
- **Horizons (multi):** 1 week, 1 month, 3 months — same factor set, different
  time-decay weights per horizon
- **Output per run:**
  - Direction: Bull / Bear / Neutral + probability (confidence)
  - Level: target yield in % for each horizon
  - Driver attribution: top signals with signed contribution
  - (Later) cross-asset impact + backtest PnL update

## Core inputs (with starting weights — tune via backtest)
| Factor | Weight | Source |
|--------|--------|--------|
| FOMC minutes + official speeches (hawkish/dovish NLP) | 30% | Fed website |
| Inflation regime (CPI / PCE / breakevens) | 25% | FRED API |
| Fed balance sheet / liquidity (QT pace, reserves, RRP) | 20% | FRED H.4.1 |
| Global rate differentials (US–DE, US–JP) | 15% | FRED / ECB / BOJ |
| Political & geopolitical risk | 10% | News NLP |

Weights live in `configs/weights.yaml` and are **not hardcoded** — they are the
main thing backtesting optimizes.

## NLP approach (hybrid: keyword + LLM)
- **Daily fast scan:** keyword dictionary (e.g. "data dependent", "restrictive",
  "further progress", "pause", "cut") → quick hawkish/dovish tilt.
- **Event days (FOMC release, major speeches):** call the Claude API for a deep
  read → hawkish score in [-1, +1] **with a written rationale** (so every score
  is auditable, never a black box).

## Repository layout
```
TraceYield/
├── data/
│   ├── raw/            # pulled API responses, Fed PDFs/HTML (never edited by hand)
│   ├── processed/      # cleaned feature tables (parquet)
│   ├── cache/          # API response cache to avoid re-hitting rate limits
│   └── reports/        # generated daily reports (markdown/html), one per date
├── src/
│   ├── ingestion/      # FRED, Treasury, Fed docs, global-rate fetchers
│   ├── nlp/            # keyword scorer + LLM hawkish/dovish scorer
│   ├── signals/        # turn raw data into the 5 factor scores
│   ├── models/         # XGBoost/LightGBM direction+level predictor
│   ├── backtest/       # rolling walk-forward backtest + weight tuning
│   ├── report/         # render the daily report
│   └── utils/          # config loading, logging, dates, caching
├── configs/            # weights.yaml, fred_series.yaml, model.yaml
├── scripts/            # daily_run.py (the cron entrypoint), one-off jobs
├── notebooks/          # EDA, backtest analysis
├── docs/concepts/      # PLAIN-ENGLISH learning material (FOMC, 10Y, chain reaction)
├── tests/
└── .claude/
    ├── agents/         # macro-tutor: the Q&A explainer subagent
    ├── skills/         # daily-rates-report skill
    └── memory/         # project memory notes
```

## Key design decisions
- **Interpretability first.** XGBoost/LightGBM over deep nets — every prediction
  must be explainable by signed factor contributions. No black boxes.
- **Config-driven.** All weights, FRED series IDs, horizons in `configs/` YAML.
- **Reproducible.** Seed everything; cache every API pull with a timestamp so any
  past day's run can be reconstructed.
- **Backtest is the source of truth.** No weight or factor ships without a
  walk-forward backtest showing it helps out-of-sample.
- **Daily trigger.** `scripts/daily_run.py` is the single entrypoint, run by
  Windows Task Scheduler (and runnable manually any time).

## Conventions
- Python 3.13; formatter `black`; linter `ruff`; tests `pytest`.
- Data cached as parquet in `data/processed/`; raw API JSON in `data/cache/`.
- Never hand-edit anything in `data/raw/` — treat as immutable source.
- Secrets (FRED_API_KEY, ANTHROPIC_API_KEY) in `.env`, never committed.
- Every model/weight change must be backtested before merge.

## Working preferences (David) — don't make him re-state these
- **Reply in Chinese** by default (he writes Chinese); keep code/identifiers English.
- **GPT-4o is the primary LLM** for FOMC scoring (key in `.env`). Keyword scorer is
  only a noisy cross-check at 0.2 weight — never let it flip the LLM's sign.
- **Always show evidence**: FOMC scores must come with verbatim `key_quotes` from
  the source doc (esp. minutes) — credibility matters more than a bare number.
- **Two parallel tracks**: build the system AND teach the concepts. He's learning
  the domain alongside building — explain the "why," use the `macro-tutor` agent.
- **Log progress** to `PROGRESS.md` (newest on top) after each meaningful update.
- **He values interpretability** — every prediction must decompose into signed
  factor contributions; no black boxes.
- Reminder: his OpenAI key was pasted in plaintext once — suggest rotating it.

## Status
🟢 Runs end-to-end on live FRED data + GPT FOMC scoring with quote evidence +
HTML report. See `PROGRESS.md` for the running log.
Next candidates: first walk-forward backtest · tune weights/bp-sensitivity ·
add dot-plot (SEP) parsing · news pipeline for `political_risk`.
