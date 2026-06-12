# v2 UST Curve Phase A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first v2 UST curve forecast report using only existing FRED/cached data.

**Architecture:** Keep v1 intact and add a parallel v2 path: driver scores in `src/signals/curve_drivers.py`, tenor pressure mapping in `src/signals/curve_impact.py`, staged forecasts in `src/models/curve_engine.py`, report rendering in `src/report/render_curve.py`, and a runnable entrypoint in `scripts/curve_run.py`. The v2 report leads with `3m_core` and `6m_core`, while still showing `1m_tactical` and `12m_structural` context.

**Tech Stack:** Python, pandas, YAML config, pytest, existing FRED parquet/cache.

---

### Task 1: Freeze v2 Config and Schema

**Files:**
- Create: `configs/curve_weights.yaml`
- Create: `configs/curve_rules.yaml`
- Create: `src/models/curve_engine.py`
- Test: `tests/test_curve_engine.py`

- [ ] **Step 1: Write failing tests**

Create tests asserting that the engine produces four horizons named `1m_tactical`, `3m_core`, `6m_core`, and `12m_structural`, and that every forecast has `2Y/5Y/10Y/30Y` tenor pressure.

- [ ] **Step 2: Run test to verify red**

Run: `python -m pytest tests/test_curve_engine.py -v`

Expected: fail because `src.models.curve_engine` does not exist.

- [ ] **Step 3: Implement minimal schema/config loader usage**

Create `CurveForecast` dataclass and `forecast_curve(df, asof=None)` API.

- [ ] **Step 4: Run test to verify green**

Run: `python -m pytest tests/test_curve_engine.py -v`

Expected: tests pass.

### Task 2: Driver Scores and Tenor Mapping

**Files:**
- Create: `src/signals/curve_drivers.py`
- Create: `src/signals/curve_impact.py`
- Test: `tests/test_curve_impact.py`

- [ ] **Step 1: Write failing tests**

Test that hawkish `policy_path` pressures `2Y/5Y` more than `30Y`, while positive `term_premium` pressures `10Y/30Y` more than `2Y`.

- [ ] **Step 2: Run test to verify red**

Run: `python -m pytest tests/test_curve_impact.py -v`

Expected: fail because mapping module does not exist.

- [ ] **Step 3: Implement driver scoring and mapping**

Map existing data into v2 drivers:
- `policy_path`: FOMC tone + 2Y momentum + policy-rate context.
- `macro_surprise`: temporary level/trend proxy from inflation and growth data already in FRED; no consensus API yet.
- `liquidity_supply`: existing liquidity factor.
- `term_premium`: breakevens, long-end momentum, and yield-trend proxy.
- `growth_risk`: VIX and curve inversion/growth proxy.
- `global_relative_value`: UST-Bund/JGB spread proxy.
- `positioning_momentum`: existing yield trend factor.
- `risk_off_overlay`: VIX stress overlay.

- [ ] **Step 4: Run tests to verify green**

Run: `python -m pytest tests/test_curve_impact.py tests/test_curve_engine.py -v`

Expected: tests pass.

### Task 3: Report and Script

**Files:**
- Create: `src/report/render_curve.py`
- Create: `scripts/curve_run.py`
- Test: `tests/test_curve_report.py`

- [ ] **Step 1: Write failing tests**

Test that markdown contains `UST Curve Impact Forecast`, `Core View`, `Tenor Pressure`, `Driver Attribution`, `Key Triggers`, and `Light Cross-Market Linkage`.

- [ ] **Step 2: Run test to verify red**

Run: `python -m pytest tests/test_curve_report.py -v`

Expected: fail because renderer does not exist.

- [ ] **Step 3: Implement renderer and cached-data script**

`scripts/curve_run.py` should load latest `data/processed/fred_*.parquet`, apply release lags, call `forecast_curve`, print markdown, and save reports under `data/reports/curve_report_YYYYMMDD.md`.

- [ ] **Step 4: Verify end-to-end**

Run:
- `python scripts/curve_run.py`
- `python -m pytest`
- `python -m ruff check src tests scripts`

Expected: curve report renders using existing cached FRED data and tests pass.
