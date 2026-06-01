---
name: daily-rates-report
description: >
  Run or explain TraceYield's daily UST 10Y yield prediction. Use when the user
  wants to generate today's rates report, trigger the daily pipeline, interpret a
  saved report in data/reports/, or wire up the daily Windows Task Scheduler job.
  Covers ingesting FRED data, computing the 5 factor scores, blending into a
  direction+level prediction across 1w/1m/3m horizons, and rendering the report.
---

# Daily Rates Report

## What this does
Runs the end-to-end prediction pipeline and writes a dated report to
`data/reports/report_YYYYMMDD.md`.

Pipeline (see `scripts/daily_run.py`):
1. **Ingest** — pull FRED series (`src/ingestion/fred_client.py`)
2. **Score factors** — fomc_nlp, inflation, liquidity, global_rates, political_risk
   (`src/signals/factors.py`)
3. **Predict** — weighted blend per horizon → direction + confidence + 10Y target
   (`src/models/predictor.py`, weights in `configs/weights.yaml`)
4. **Render** — markdown report with driver attribution (`src/report/render.py`)

## To run it
```powershell
cd $env:USERPROFILE\Desktop\TraceYield
python scripts\daily_run.py
```
Prerequisites: `pip install -r requirements.txt` and a `.env` with `FRED_API_KEY`
(copy from `.env.example`). The Anthropic key is only needed on FOMC/event days
for deep NLP scoring.

## To schedule it daily (Windows Task Scheduler)
Create a task that runs every weekday morning after data updates:
```powershell
$action  = New-ScheduledTaskAction -Execute "python" `
  -Argument "$env:USERPROFILE\Desktop\TraceYield\scripts\daily_run.py" `
  -WorkingDirectory "$env:USERPROFILE\Desktop\TraceYield"
$trigger = New-ScheduledTaskTrigger -Daily -At 7:30am
Register-ScheduledTask -TaskName "TraceYield-Daily" -Action $action -Trigger $trigger
```
(US Treasury data on FRED updates with a 1-day lag; 7:30am local is safe.)

## To interpret a report
- **Direction** = Bull (yields↓/bonds↑), Bear (yields↑/bonds↓), Neutral.
- **Confidence** grows with the absolute blended score.
- **Top drivers** show each factor's *signed* contribution. Positive = upward
  yield pressure. A Bear call driven by `inflation` ≠ one driven by `liquidity`
  — the narrative matters for the cross-asset read.

## Honesty rule
v0 uses a transparent linear blend with placeholder NLP/news inputs (hawkish and
political default to 0 until those pipelines are wired). Don't oversell its
accuracy until the walk-forward backtest (`src/backtest/walk_forward.py`) shows
real out-of-sample hit-rate. Report what's actually wired, not the aspiration.
