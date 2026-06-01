# TraceYield v1 — Implementation Spec (Codex build sheet)

> **Read this first.** This is the authoritative spec for the v1 upgrade.
> **Codex implements; Claude validates.** Build phase by phase, in order. Do not
> start a phase before the previous phase's acceptance gate is green. Keep the
> existing `scripts/daily_run.py` pipeline working at every commit.

---

## 0. Why we're doing this (the v0 diagnosis)

v0 is a transparent but **blunt static scoring table**:
`FRED → z-score → weighted average → Bull/Bear/Neutral`.

Backtest (2015–2026, macro factors only): **3m IC 0.088, dir-acc 52.6%, 1w = noise.**
Today's run is Neutral because inflation (+0.111) and liquidity (-0.102) cancel,
while `fomc_nlp` ≈ 0 and `political_risk` = 0 (hardcoded).

**The core defect is NOT that it says Neutral — it's that Neutral carries no
information.** v1 must keep Neutral honest but make it *useful*: explain *why*
direction is weak, whether a *curve* or *event* trade is live, which factor is
fighting which, and what *trigger* would break the tie.

### Design north star
Preserve everything good about v0 (transparent, interpretable, config-driven,
backtestable, no black boxes). **Add layers and richer outputs — do not replace
the linear blend with an opaque model.** Every output must still decompose into
named, signed contributions.

---

## 1. Target architecture — three layers

Replace the single weighted-average step with a 3-layer pipeline. Each layer is
its own module with a clean dataclass output; the report shows all three.

```
Layer 1  MACRO REGIME      → what world are we in?      src/signals/regime.py
Layer 2  MARKET CONFIRM    → does the market agree?     src/signals/confirmation.py
Layer 3  TRADE SIGNAL      → what (if anything) to do    src/models/signal_engine.py
```

### Layer 1 — Macro Regime
Inputs: growth, inflation, Fed reaction function, liquidity, global rates,
fiscal/term premium, risk sentiment. Output a **regime label** (not Bull/Bear):
```
DISINFLATION_DOVISH        # bull bonds
STICKY_INFLATION_HAWKISH   # bear bonds
FISCAL_BEAR_STEEPENING     # supply/term-premium driven
RISK_OFF_BULL_FLATTENING   # flight to safety
GROWTH_RESILIENCE_BEAR_FLATTENING
LIQUIDITY_SQUEEZE
NEUTRAL_MIXED              # explicit conflict state
```
Output: `RegimeView{regime, confidence, factor_scores, rationale}`.

### Layer 2 — Market Confirmation
Ask whether market-implied / price data confirm the regime narrative:
2Y move, 10Y real yield breakout, breakeven direction, DXY, gold divergence,
equities, MOVE/VIX. Output `ConfirmationView{score in [-1,1], checks: {...},
agrees: bool, rationale}`. `score` aligns sign with the regime's bond direction.

### Layer 3 — Trade Signal
Synthesize L1 + L2 into an **actionable, graded** output (see §3 schema). This is
where Conflict / Bias / Trigger / Curve live. Neutral splits into informative
states ("Neutral until CPI", "Neutral, curve signal active", "No trade: low
conviction", "Watch: 10Y close > 4.50%").

---

## 2. Phased plan (build in this order)

Each task lists: **files**, **contract**, **acceptance gate** (what Claude checks).

### PHASE 1 — Fill the gaps so the backtest is honest (highest ROI)
The model is starved of its two biggest factors over history. Fix that first.

**1.1 Historical FOMC scraper (HTML, not PDF)**
- File: `src/ingestion/fomc_scraper.py`
- Source: federalreserve.gov.
  - Statements (recent): `https://www.federalreserve.gov/newsevents/pressreleases/monetary{YYYYMMDD}a.htm`
  - Minutes (recent): `https://www.federalreserve.gov/monetarypolicy/fomcminutes{YYYYMMDD}.htm`
  - Discover historical links by scraping the year pages:
    `https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm` (last ~5y) and
    `https://www.federalreserve.gov/monetarypolicy/fomchistorical{YEAR}.htm` (older).
- Behaviour: discover all statement + minutes URLs from a start year (default
  2010), fetch HTML, extract the main article text with BeautifulSoup, save raw
  HTML to `data/raw/fomc/{kind}/{YYYY-MM-DD}.html` and extracted text alongside.
  Be polite: cache, skip already-downloaded, `time.sleep` between requests, set a
  descriptive User-Agent.
- Contract: `scrape(start_year:int=2010) -> list[FomcDoc]` reusing the `FomcDoc`
  shape from `src/nlp/fomc_loader.py` (add `source="federalreserve.gov"`). Extend
  `fomc_loader.load()` to read from BOTH the existing `FOMC/` PDFs and the new
  `data/raw/fomc/` HTML, deduped by date+kind.
- **Acceptance gate:** `python -m src.ingestion.fomc_scraper` downloads ≥ 80
  statements and ≥ 80 minutes (2010→now), each with non-empty extracted text;
  re-running re-uses cache (no re-download); a unit test parses a saved fixture
  HTML into clean text.

**1.2 Historical FOMC scoring (cost-aware)**
- Score every historical doc with the existing `fomc_analyzer`/`llm_scorer`.
- **Cost control:** add a `scoring_model` override so the historical *backfill*
  uses `gpt-4o-mini` (cheap); keep `gpt-4o` for the latest/live doc. Put the
  choice in `configs/model.yaml` (`backfill_model: gpt-4o-mini`). Reuse the
  existing on-disk cache so each doc is scored once.
- Build a **point-in-time FOMC score series**: `data/processed/fomc_scores.parquet`
  indexed by the doc's *release date*, columns `[blended, llm, keyword, kind]`.
  Statements and minutes both included.
- Contract: `src/signals/fomc_series.py::build() -> pd.DataFrame` and
  `fomc_factor_asof(date) -> float` returning the most recent FOMC score known
  **on or before** `date` (no look-ahead).
- **Acceptance gate:** the series spans 2010→now; `fomc_factor_asof` never
  returns a value dated after its argument; Claude re-runs the backtest with FOMC
  wired in and reports the new IC vs the 0.088 baseline.

**1.3 Wire `fomc_nlp` + `political_risk` into the backtest**
- `walk_forward.py`: pass `hawkish=fomc_factor_asof(d)` per day instead of 0.
- `political_risk`: at minimum stop hardcoding 0 — wire a simple proxy now (e.g.
  MOVE index z-score or a debt-ceiling/election calendar flag); full news NLP is
  Phase 3. Document the proxy.
- **Acceptance gate:** backtest output shows fomc_nlp contributing; Claude
  confirms no look-ahead and records the IC delta in `PROGRESS.md`.

**1.4 Release-date (vintage) correction**
- FRED series are indexed to *reference* date, not *release* date → look-ahead.
- Use ALFRED vintages (`fredapi` `get_series_first_release` / `get_series_as_of_date`)
  for the macro series in the backtest path, or apply a documented per-series
  publication lag (e.g. CPI/PCE +1 month, NFP +1 week) as a v1 approximation.
- **Acceptance gate:** backtest re-run with lags applied; Claude compares IC
  before/after and documents the (likely lower, more honest) numbers.

> **Phase 1 done when:** Claude has a believable, look-ahead-free backtest with
> FOMC included, and the IC/dir-acc deltas are written to PROGRESS.md.

---

### PHASE 2 — Make the output informative (no new data, big UX win)
Express the signal richly. This is what fixes "useless Neutral."

**2.1 Conflict Index** — `src/signals/conflict.py`
- Quantify factor disagreement. Define
  `conflict = 1 - |Σ wᵢsᵢ| / Σ wᵢ|sᵢ|` (0 = aligned, 1 = fully offsetting).
- Identify `main_tension` = the top opposing pair by weighted magnitude
  (e.g. "sticky inflation (+0.11) vs easing liquidity (-0.10)").
- **Acceptance gate:** on the 2026-06-01 data, conflict is HIGH and main_tension
  names inflation vs liquidity; unit tests cover aligned/offsetting cases.

**2.2 Directional Strength (graded bias)** — extend `predictor`/`signal_engine`
- Replace hard 3-way with a graded `bias`:
  `Strong Bull | Weak Bull | Neutral | Weak Bear | Strong Bear`, derived from the
  score magnitude AND conflict (high conflict caps strength). Keep the raw score.
- **Acceptance gate:** score +0.05 → "Slight bearish pressure", +0.25 (low
  conflict) → "Bear"; high conflict downgrades the label even if |score| is high.

**2.3 Market Triggers** — `src/models/signal_engine.py`
- Emit yield levels that would flip the call:
  `bear_trigger`/`bull_trigger` (e.g. 10Y close > 4.50% / < 4.35%), derived from
  recent range (e.g. ±1 ATR / N-day high-low) around current.
- **Acceptance gate:** triggers bracket the current yield and move with volatility.

**2.4 Yield-curve prediction** — `src/models/curve.py`
- Predict direction of **2s10s** and **5s30s** (steepen / flatten / neutral),
  with the same factor → score → graded-bias treatment. Regime informs curve
  (e.g. FISCAL_BEAR_STEEPENING → steepener; RISK_OFF → bull flattener).
- Add a curve section to the report and a `curve_view` to the output schema.
- **Acceptance gate:** backtest 2s10s direction the same way (IC/dir-acc); curve
  view is internally consistent with the regime label.

> **Phase 2 done when:** the daily report shows Regime + Bias + Conflict +
> Triggers + Curve, and Neutral days produce a useful "here's why / watch this"
> message.

---

### PHASE 3 — New data layers (market-implied, surprise, positioning)
This is where real predictive edge likely comes from.

**3.1 Fed market pricing** — `src/ingestion/fed_futures.py`
- Market-implied policy path: cut/hike probability for the next meeting, 3m/6m
  expected policy rate, year-end implied fed funds. Sources: CME FedWatch (scrape)
  or derive from fed funds / SOFR futures; FRED has SOFR. Add a `fed_pricing`
  factor that compares market-implied path vs the FOMC's stated path (gap = signal).
- **Acceptance gate:** plausible cut probabilities for known dates; backtest delta.

**3.2 Macro surprise layer** — `src/signals/surprise.py`
- Trade the *surprise*, not the level: actual vs consensus for CPI, PCE, NFP, ISM,
  retail sales. Needs a consensus source (economic calendar API — research and
  propose; may need a key). Output a rolling `surprise` factor.
- **Acceptance gate:** surprise series aligns with known beats/misses; backtest delta.

**3.3 Rates decomposition** — extend `signals`
- Real yield (DFII10), breakeven decomposition (T10YIE), term premium (NY Fed ACM,
  published series). Separate "Fed-expectations move" from "term-premium move".
- **Acceptance gate:** 10Y ≈ real + breakeven reconciles; term-premium factor wired.

**3.4 Technical / positioning** — `src/signals/technical.py`
- 10Y momentum, 5/20/60-day trend, yield breakout, CFTC positioning (CFTC public
  data), TLT price action, volatility-adjusted signal (scale by MOVE).
- **Acceptance gate:** technical factor backtests with non-zero IC at 1w/1m
  (this is the layer most likely to help the SHORT horizons v0 fails at).

> **Phase 3 done when:** market-implied + surprise + technical factors are in the
> blend and the backtest IC at 1m/3m is materially above the 0.088 baseline
> (target: 3m IC > 0.15, 1w dir-acc > 52% — revisit with Claude after data lands).

---

### PHASE 4 — Regime classifier + synthesis polish
- Formalize Layer 1 as a rules-based regime classifier (transparent thresholds in
  `configs/regimes.yaml`), Layer 2 confirmation, Layer 3 synthesis with all the
  Phase 2/3 signals. Optionally add an interpretable ML head (logistic / gradient
  boosting) that predicts P(up/down) from the factor vector — but only if it beats
  the linear blend out-of-sample in the backtest, and SHAP/contributions are shown.
- **Acceptance gate:** end-to-end report renders all layers; backtest beats the
  linear blend OOS or the linear blend is kept.

---

## 3. Output schema (the contract the report renders)

`src/models/signal_engine.py` produces, per horizon (1w/1m/3m) and for the curve:

```python
@dataclass
class Signal:
    horizon: str
    regime: str                 # Layer-1 label
    regime_confidence: float
    bias: str                   # Strong/Weak Bull|Bear | Neutral
    directional_score: float    # raw blended score, ~[-1,1]
    conflict_index: float       # 0..1
    main_tension: str           # "sticky inflation vs easing liquidity"
    confirmation: float         # Layer-2 score, [-1,1]
    market_agrees: bool
    target_yield: float         # level estimate (kept from v0, calibrated)
    bear_trigger: float         # 10Y level that flips bearish
    bull_trigger: float
    curve_view: str             # 2s10s/5s30s steepen|flatten|neutral
    watch: str                  # "Neutral until CPI (Jun 12)"
    contributions: dict         # signed per-factor — STILL REQUIRED
    rationale: str
```

The HTML report (`src/report/render.py`) gains sections: **Regime**, **Bias +
Conflict**, **Triggers**, **Curve**, alongside the existing forecast table and
FOMC evidence/quotes. No black boxes: `contributions` always shown.

---

## 4. Division of labour & validation protocol

- **Codex (implementer):** writes code per phase, keeps `daily_run.py` working,
  adds/updates unit tests, runs `pytest` + `ruff` + `black` before each commit,
  commits per task with a clear message, and updates `PROGRESS.md`.
- **Claude (validator):** after each phase, runs the backtest + full pipeline,
  checks acceptance gates, audits for look-ahead bias, reviews the diff for
  correctness/interpretability, and records IC/dir-acc deltas. Claude does NOT
  do the bulk implementation (token budget) — it reviews, tests, and unblocks.

### Hard rules for Codex
1. **No look-ahead, ever.** Any factor used at date `d` must use only data known
   on/before `d` (release dates, not reference dates). Flag anything uncertain.
2. **Interpretability is non-negotiable.** Every signal decomposes into signed
   named contributions in the output. No opaque models without shown attributions.
3. **Config-driven.** New thresholds/weights/series go in `configs/*.yaml`, never
   hardcoded.
4. **Backtest before claiming.** No factor/weight "works" without a walk-forward
   number. Report honestly, including when something doesn't help.
5. **Don't break v0.** `python scripts/daily_run.py` and `pytest` stay green at
   every commit. New layers degrade gracefully if a data source/key is missing.
6. **Cost-aware LLM use.** Historical backfill = `gpt-4o-mini`; live/latest =
   `gpt-4o`. Cache every scored doc.
7. **Secrets in `.env`** (gitignored). Never commit keys or `data/raw`, `FOMC/`.

### Suggested commit/PR cadence
One commit per numbered task (1.1, 1.2, …). At each phase boundary, stop and let
Claude validate before proceeding.

---

## 5. New data sources cheat-sheet
| Need | Source | Notes |
|------|--------|-------|
| Historical FOMC statements/minutes | federalreserve.gov HTML | Phase 1.1 |
| FOMC point-in-time score | our LLM scorer (gpt-4o-mini backfill) | Phase 1.2 |
| Real yield | FRED `DFII10` | Phase 3.3 |
| Breakeven | FRED `T10YIE`, `T5YIE` (have) | Phase 3.3 |
| Term premium | NY Fed ACM term premium series | Phase 3.3 |
| Fed pricing / cut odds | CME FedWatch / fed funds futures / SOFR | Phase 3.1 |
| Macro surprise | economic calendar API (consensus) | Phase 3.2, needs key |
| Rates vol | MOVE index (`^MOVE` via yfinance) | Phase 2/3 |
| Equity vol | FRED `VIXCLS` (have) | — |
| USD | FRED `DTWEXBGS` (have) | — |
| Positioning | CFTC Commitments of Traders (public) | Phase 3.4 |
| TLT / price action | yfinance `TLT` | Phase 3.4 |

---

## 6. Current repo state (what Codex inherits — all working)
- `scripts/daily_run.py` — end-to-end: FRED → factors → blend → md+HTML report.
- `scripts/backtest.py` + `src/backtest/walk_forward.py` — IC/dir-acc/threshold sweep.
- `src/signals/factors.py` — inflation/liquidity/global_rates (z-score), fomc/political pass-through.
- `src/nlp/` — `keyword_scorer`, pluggable `llm_scorer` (openai/anthropic/gemini),
  `fomc_loader` (PDF), `fomc_analyzer` (cache + statement/minutes blend + key_quotes).
- `configs/` — `weights.yaml`, `fred_series.yaml`, `model.yaml`.
- `src/report/render.py` — markdown + styled HTML with FOMC quote evidence.
- Baseline backtest: 3m IC 0.088, dir-acc 52.6%; 1w noise. **Beat this.**
