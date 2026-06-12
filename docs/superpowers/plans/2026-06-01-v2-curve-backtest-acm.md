# v2 Curve Backtest and ACM Term Premium Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a walk-forward backtest for the v2 curve engine and wire free NY Fed ACM term premium data into the `term_premium` signal.

**Architecture:** Add a parallel v2 backtest module that replays `forecast_curve()` with column-specific release lags and evaluates 3m/6m tenor and curve-shape outcomes. Add an NY Fed ACM ingestion module that downloads the official free file, caches raw/processed copies, exposes an as-of loader, and lets the term-premium driver prefer ACM data while degrading to the current proxy when unavailable.

**Tech Stack:** Python, pandas, requests, pytest, existing FRED parquet/cache.

---

### Task 1: NY Fed ACM Fetcher

**Files:**
- Create: `src/ingestion/nyfed_acm.py`
- Modify: `src/signals/curve_drivers.py`
- Test: `tests/test_nyfed_acm.py`

- [ ] **Step 1: Write failing parser/cache tests**

Test parsing a small ACM-shaped table with a date column and `ACMTP10`, test `term_premium_asof()` never returns values after the requested date, and test the curve driver uses ACM when provided.

- [ ] **Step 2: Run red**

Run: `python -m pytest tests/test_nyfed_acm.py -v`

Expected: fail because `src.ingestion.nyfed_acm` does not exist.

- [ ] **Step 3: Implement fetch/cache/load**

Use official NY Fed URL `https://www.newyorkfed.org/medialibrary/media/research/data_indicators/ACMTermPremium.xls`. Cache raw file under `data/cache/nyfed/`, processed parquet under `data/processed/nyfed_acm_term_premium.parquet`, and expose `load_term_premium(fetch_if_missing=False)` plus `term_premium_asof(date)`.

- [ ] **Step 4: Run green**

Run: `python -m pytest tests/test_nyfed_acm.py -v`

Expected: pass.

### Task 2: v2 Curve Backtest

**Files:**
- Create: `src/backtest/curve_v2.py`
- Create: `scripts/curve_backtest.py`
- Test: `tests/test_curve_v2_backtest.py`

- [ ] **Step 1: Write failing backtest tests**

Test that a small synthetic curve history produces rows for `3m_core` and `6m_core`, includes realized tenor changes, curve shape hit fields, IC/DA summary, and writes `data/backtest/curve_v2_backtest.csv`.

- [ ] **Step 2: Run red**

Run: `python -m pytest tests/test_curve_v2_backtest.py -v`

Expected: fail because `src.backtest.curve_v2` does not exist.

- [ ] **Step 3: Implement walk-forward backtest**

For each date, lag FRED columns with `_lagged_history()`, run `forecast_curve()` on as-of data, compare predicted 3m/6m pressure versus realized yield changes at 63/126 trading days, evaluate per-tenor directional accuracy, curve-shape hit rate, IC, and threshold coverage/hit.

- [ ] **Step 4: Run green and full verification**

Run:
- `python scripts/curve_backtest.py`
- `python -m pytest`
- `python -m ruff check src tests scripts`

Expected: backtest CSV written and tests pass.
