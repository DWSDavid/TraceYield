# Yield Trend Horizons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an interpretable Treasury historical-pattern factor and change prediction horizons to 1m, 3m, 6m, and 12m.

**Architecture:** Keep the v0 linear blend, adding `yield_trend` as one more signed factor in `[-1, +1]`, where positive means upward yield pressure. The factor uses only cached Treasury yield history from FRED and combines 10Y momentum, range position, and curve trend without any external API or news NLP.

**Tech Stack:** Python, pandas, YAML config, pytest.

---

### Task 1: Add Yield Trend Factor Tests

**Files:**
- Create: `tests/test_yield_trend.py`

- [ ] **Step 1: Write failing tests**

```python
import pandas as pd

from src.signals.yield_trend import yield_trend_factor


def test_yield_trend_positive_when_10y_trend_rises_and_curve_steepens():
    dates = pd.date_range("2025-01-01", periods=300, freq="D")
    df = pd.DataFrame(
        {
            "DGS2": [3.0 + i * 0.001 for i in range(300)],
            "DGS10": [4.0 + i * 0.004 for i in range(300)],
            "DGS30": [4.5 + i * 0.003 for i in range(300)],
        },
        index=dates,
    )

    assert yield_trend_factor(df) > 0


def test_yield_trend_negative_when_10y_trend_falls_and_curve_flattens():
    dates = pd.date_range("2025-01-01", periods=300, freq="D")
    df = pd.DataFrame(
        {
            "DGS2": [4.0 + i * 0.001 for i in range(300)],
            "DGS10": [5.0 - i * 0.004 for i in range(300)],
            "DGS30": [5.5 - i * 0.003 for i in range(300)],
        },
        index=dates,
    )

    assert yield_trend_factor(df) < 0
```

- [ ] **Step 2: Verify red**

Run: `pytest tests/test_yield_trend.py -v`

Expected: fail because `src.signals.yield_trend` does not exist.

- [ ] **Step 3: Implement minimal code**

Create `src/signals/yield_trend.py` with a bounded `yield_trend_factor(df)` that combines 10Y momentum, 10Y range position, and 2s10s/5s30s curve trend.

- [ ] **Step 4: Verify green**

Run: `pytest tests/test_yield_trend.py -v`

Expected: 2 passed.

### Task 2: Wire Factor And Horizons

**Files:**
- Modify: `src/signals/factors.py`
- Modify: `configs/weights.yaml`
- Modify: `src/models/predictor.py`
- Modify: `src/backtest/walk_forward.py`
- Modify: `tests/test_smoke.py`

- [ ] **Step 1: Write failing tests**

Update smoke tests to expect four horizons, `yield_trend` in contributions, and `12m` output.

- [ ] **Step 2: Verify red**

Run: `pytest tests/test_smoke.py -v`

Expected: fail because current config emits only 1w/1m/3m and no `yield_trend`.

- [ ] **Step 3: Implement wiring**

Add `yield_trend` to `compute_all`, replace horizons with `1m/3m/6m/12m`, update `BPS_PER_UNIT`, and update backtest horizon day counts.

- [ ] **Step 4: Verify green**

Run: `pytest tests/test_smoke.py tests/test_yield_trend.py -v`

Expected: all selected tests pass.

### Task 3: End-To-End Verification

**Files:**
- No new files.

- [ ] **Step 1: Run MVP check**

Run: `python scripts/mvp_data_check.py`

Expected: PASS and predictions for `1m`, `3m`, `6m`, and `12m`.

- [ ] **Step 2: Run full test suite**

Run: `pytest`

Expected: all tests pass.
