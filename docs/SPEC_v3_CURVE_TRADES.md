# TraceYield v3 — UST Curve-Shape & Curve-Trade Forecast

> Locked product spec, 2026-06-01.
> v2 proved the framework runs but had no yardstick and unvalidated factors.
> v3 narrows the product to what is actually predictable, enforces a benchmark,
> and validates factors one at a time before fusing them.

---

## 1. Locked Product Definition

TraceYield v3 predicts, within a 1-year horizon:

```text
The most likely change in UST CURVE SHAPE and the direction of CURVE TRADES,
NOT the level of any yield.
```

### Why not yield levels

Yield *levels* cannot reliably beat a random walk (Duffee 2002, and the broad
"random walk is hard to beat" literature). Predicting "10Y will be 4.6%" is a
losing game. What *is* predictable, and only at 3m+ horizons, is:

- curve **shape** change (steepening / flattening, bull / bear)
- **relative** tenor performance (which part of the curve outperforms)
- the direction of standard **curve trades** (2s10s, 5s30s)

This is also why the horizon is 3m/6m: below that, macro signal drowns in noise;
this is the window where factor models start beating the random walk.

### Strategic Narrowing: 10Y stays headline, but is reconstructed

The product's headline output remains the **10Y US Treasury directional view**.
The narrowing is about **how** the 10Y view is produced, not whether the 10Y is
shown.

TraceYield v3 must not predict the 10Y outright level in isolation. Instead:

```text
10Y_view = 2Y_view + 2s10s_view
```

- `2Y_view` comes from the validated front-end / policy-expectations axis.
- `2s10s_view` comes from the validated curve-slope axis
  (`policy_path` now, FADNS slope when validated).
- The sum is the headline 10Y directional call.

The report must show the 10Y call first and explicitly decompose it into:

1. front-end `2Y` / policy component,
2. `2s10s` curve component,
3. residual pure-term-premium / long-end component, flagged
   low-confidence and context-only.

Demoted from core:

- standalone 10Y outright-level prediction,
- 30Y as a separate primary focus,
- pure long-end / term-premium factors (`term_premium`, `liquidity_supply`,
  `global_relative_value`) as core inputs.

30Y remains context-only. 10Y does not.

---

## 2. Horizons

| Horizon | Role | Forecast? |
|---|---|---|
| `1m` | Tactical / event context, entry timing | Secondary |
| `3m` | **Core tradeable forecast** | **Primary** |
| `6m` | **Core tradeable forecast** | **Primary** |
| `12m` | Single structural background note only | Dropped from forecasting |

Short/medium-term trading focus → 12m is no longer a forecast target.

---

## 3. Output Schema (per core horizon)

Three layers, from narrative to executable:

### Layer 1 — Shape narrative (interpretable)
- `curve_call`: `BULL_STEEPENING`, `BULL_FLATTENING`, `BEAR_STEEPENING`,
  `BEAR_FLATTENING`, `RANGE_BOUND`, `MIXED_CONFLICT`
- `main_driver`, `secondary_driver` with **signed contributions**

### Layer 2 — Tradeable signals (executable; DIRECTION, never bp)
- `2s10s`: `steepener` / `flattener` / `neutral`
- `5s30s`: `steepener` / `flattener` / `neutral`
- `tenor_direction`: per `2Y`/`5Y`/`10Y`/`30Y` → `up` / `down` / `neutral`

### Layer 3 — Risk / trust
- `confidence`: calibrated, coverage-aware
- `triggers`: data/levels that strengthen or invalidate the call
- `benchmark_tag`: **does this call beat random walk? by how much?**

### Discipline
Every call carries a `benchmark_tag`. A call that does not beat the random-walk
benchmark is flagged `NO_ALPHA — do not trade`, regardless of its hit rate.

---

## 4. Factor Philosophy — Few But Refined

Target **3–5 INDEPENDENT, individually validated factors**, not 8. Rates
literature shows the count of genuinely effective factors is single-digit
(Cochrane-Piazzesi compress the whole forward curve into ONE factor with 44% R²;
Ludvigson-Ng reduce macro to TWO factors).

No factor enters the fused model until it passes single-factor IC testing.

### 4.1 Highest-priority MISSING factors (both free FRED data)
- **Cochrane-Piazzesi forward-rate factor** — tent-shaped combo of forward rates;
  strongest single bond-return predictor in the literature. v2 has none.
- **Nelson-Siegel Level / Slope** — explain >99% of curve variation. v2 has none.

### 4.2 Known v2 factor bugs to fix during the single-factor pass
- `macro_surprise` measures inflation **level**, not **surprise** — concept error
  (event-study lit: surprise vs consensus is what moves yields, not level). With
  no paid consensus, proxy surprise via release-over-release **acceleration**.
- `risk_off_overlay` double-counts VIX with `growth_risk` — separate the inputs.
- `term_premium` ACM change scaled by fixed /0.50 crushes the signal — normalize
  by a rolling std of ACM changes instead.

---

## 5. Build Order (Decision Tree)

### Phase 0 — Build the yardstick (BLOCKER for everything else)
- Random-walk benchmark: next-horizon curve shape = today's shape.
- Momentum / AR(1) benchmark: shape continues its recent trend.
- Lock the evaluation harness: **Rank IC, ICIR, quantile monotonicity,
  curve-shape hit rate, directional accuracy**, all point-in-time / no look-ahead.
- Decision: this is the bar every factor and the fused model must clear.

### Phase 1 — Single-factor isolated IC testing (one factor at a time)
- For each candidate factor, alone: compute 3m/6m Rank IC + ICIR vs realized
  curve/tenor moves.
- Add the two missing curve factors (CP, NS Slope) FIRST — they are the strongest.
- Keep a factor only if `|mean IC| > 0.05`, sign matches economic logic, and IC is
  temporally stable (positive across sub-periods, not one lucky window).
- Drop any factor near zero IC. Investigate any factor whose IC sign is backwards
  (likely a sign/scaling bug, e.g. the v2 long-end factors).

### Phase 2 — Prune to few-but-refined
- Among survivors, drop one of any pair with IC correlation > 0.7 (keep the one
  with cleaner economic logic). Target 3–5 independent factors.

### Phase 3 — Simple fusion
- Equal-weight or ICIR-weighted blend (start simple, no fancy ML).
- Decision: fused IC MUST exceed the strongest single-factor IC, else fusion adds
  nothing.

### Phase 4 — Beat the benchmark
- Compare fused model vs Phase-0 random walk / momentum.
- If it beats RW → real alpha, proceed to tune (weights, thresholds, confidence
  calibration). If not → return to Phase 1; the factors are the problem, not the
  weights.

### Phase 5 — Add data ONLY after factors are validated
- TreasuryDirect auctions, MOVE/rates-vol proxy, etc. — added one at a time, each
  re-validated through Phase 1's IC harness.

**Rule: do not add any new data source until Phase 0 + Phase 1 are complete.**
No yardstick and no per-factor validation = stacking bricks with no foundation.

---

## 6. Constraints (carried from v2, permanent)

- **Free data only.** No Bloomberg, Refinitiv, Trading Economics, Econoday.
- All factors built on FRED + free government downloads (NY Fed ACM, Cleveland
  Fed, TreasuryDirect).
- Missing optional data degrades gracefully to neutral, never blocks a run.
- No factor may use data unavailable as of the forecast date (point-in-time).

---

## 7. Division of Labour

- **Codex implements phase-by-phase.**
- **Claude validates each phase** (look-ahead audit, IC sanity, benchmark
  comparison, acceptance gates) before the next phase starts.
- Codex should STOP after each phase for validation, not run straight through.

---

## 8. First Milestone

Phase 0 + Phase 1 only:
1. Random-walk and momentum benchmarks with the locked IC/ICIR/hit-rate harness.
2. Single-factor IC report for: CP factor, NS Slope, plus the existing v2 factors
   re-tested individually (with the three known bugs fixed).

Deliverable: a table ranking every candidate factor by 3m/6m Rank IC and ICIR,
each tagged keep / drop / fix, with the random-walk bar shown for reference.
Do NOT build fusion or add new data in this milestone.
