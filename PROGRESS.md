# TraceYield — Progress Log

Newest entry on top. One entry per meaningful update. Format: `## YYYY-MM-DD — title`.

---

## 2026-06-01 - Phase 1.4 FRED publication-lag backtest correction
- Added `release_lag_days` to every configured FRED series in
  `configs/fred_series.yaml`.
  - CPI/PCE macro releases use 35 calendar days.
  - WALCL/WRESBAL liquidity releases use 7 calendar days.
  - Daily rates, breakevens, policy, VIX, and USD series use 1 calendar day.
- `src/backtest/walk_forward.py` now builds a column-wise lagged history before
  factor scoring, so each backtest date only sees data approximately available
  by that date.
- Added tests covering column-specific lag cutoffs and `_daily_factors()` using
  lagged history before factor scoring.
- Added `scripts/mvp_data_check.py` for a VS Code/terminal smoke check that
  verifies configured FRED columns are present, applies release lags, computes
  factor scores, and emits the current v0 predictions without LLM/API calls.
- P1.4 lagged backtest, 2015-01-01 -> 2026-05-31:
  - 1w: IC 0.051, DA 48.0%.
  - 1m: IC 0.071, DA 49.3%.
  - 3m: IC 0.097, DA 47.5%.
  - At the configured +/-0.15 band, 3m threshold hit-rate is 53% at 66% coverage.
- MVP data check passed on `fred_20260601.parquet`: 22 configured series present,
  date range 2010-01-01 -> 2026-05-31, lagged 10Y as-of 2026-05-28, current 10Y
  used 4.45%, and all five factor scores plus 1w/1m/3m predictions rendered.
- Verification: `pytest tests --basetemp .codex-tmp/pytest` = 20 passed.

## 2026-06-01 - Phase 1.3 FOMC and political proxy wired into backtest
- `src/backtest/walk_forward.py` now calls `fomc_factor_asof(d)` for each
  walk-forward date, so `fomc_nlp` is point-in-time instead of 0 over history.
- `political_risk` is no longer hardcoded to 0. v1 proxy uses FRED `VIXCLS` as a
  risk-off/safe-haven proxy: high VIX maps to negative yield pressure
  (`political_risk = -zscore(VIXCLS)`). This is documented as a temporary proxy
  until Phase 3 news NLP.
- `scripts/daily_run.py` also uses the VIX proxy for the daily political/risk
  score instead of hardcoding neutral.
- Backtest diagnostic now prints average absolute 3m factor contributions; latest
  P1.3 run showed `fomc_nlp=0.072` and `political_risk=0.041`, confirming both
  contribute non-zero signal.
- Backtest 2015-01-01 -> 2026-05-31, before release-date/vintage correction:
  - 1w: IC 0.047, DA 48.0%.
  - 1m: IC 0.074, DA 48.6%.
  - 3m: IC 0.099, DA 47.8%.
- Comparison vs old macro-only baseline (3m IC 0.088, DA 52.6%): FOMC/VIX proxy
  lifted 3m IC by +0.011 but reduced raw sign directional accuracy by -4.8 pp.
  Keep the signal for interpretability, but do not claim predictive improvement
  until P1.4 honest-lag backtest and later tuning.

## 2026-06-01 - Phase 1.2 historical FOMC scoring series implemented
- Added `configs/model.yaml` `llm.backfill_model: gpt-4o-mini`; live/latest
  scoring still uses the configured OpenAI live model (`gpt-4o`).
- Added `src/signals/fomc_series.py` with `build()` and `fomc_factor_asof(d)`.
  The series is indexed by public release date, not meeting/reference date:
  statements use decision/release date; minutes use the calendar's exact
  "Released Month DD, YYYY" date when present, falling back to +21 days.
- Ran historical backfill across official Fed HTML docs: 262 rows, 2010-01-27
  through 2026-05-20, all 262 with non-null LLM scores. Output:
  `data/processed/fomc_scores.parquet`.
- Backfill estimate printed by the CLI: model `gpt-4o-mini`, 262 docs,
  ~1,579,893 input tokens, ~91,700 output tokens, estimated cost ~$0.2920.
- Added tests proving `fomc_factor_asof(d)` returns only scores known on/before
  `d`, and that build uses the configured backfill model plus minutes release
  dates.

## 2026-06-01 - Phase 1.1 historical FOMC HTML scraper implemented
- Added `src/ingestion/fomc_scraper.py`: official federalreserve.gov scraper for
  FOMC statements and minutes. Supports full calendar discovery from 2010 onward
  and single-URL review/download, e.g.
  `python -m src.ingestion.fomc_scraper --url https://www.federalreserve.gov/newsevents/pressreleases/monetary20260128a.htm`.
- Download cache is cache-first and polite: official User-Agent, local HTML cache,
  raw HTML plus extracted text saved under `data/raw/fomc/{statement,minutes}/`.
  Re-running `--start-year 2010 --sleep 0` completed without network access from
  cache.
- Extended `src/nlp/fomc_loader.py` so the NLP pipeline reads both legacy local
  PDFs in `FOMC/` and downloaded Fed HTML text in `data/raw/fomc/`, deduped by
  exact `kind + date` with official HTML preferred.
- Acceptance gate evidence: full backfill loaded 260 official HTML docs: 129
  statements and 131 minutes. File check: all extracted `.txt` files non-empty
  (statement min 870 chars; minutes min 40,353 chars).
- Daily scoring guard: live `combined_fomc_score()` now hydrates only the latest
  statement and latest minutes, so Phase 1.1 does not accidentally trigger a
  260-document LLM backfill. Historical scoring remains Phase 1.2.
- Verification: `pytest tests` = 10 passed; Black check passed on changed files;
  Ruff check passed on changed files.

## 2026-06-01 — v1 spec written; handing implementation to Codex
- Wrote `docs/SPEC_v1.md`: the authoritative v1 build sheet. Upgrades v0 from a
  blunt static scoring table to a 3-layer signal engine (Macro Regime → Market
  Confirmation → Trade Signal) with informative Neutral states.
- **Division of labour:** Codex implements phase by phase; Claude validates each
  phase (backtest, look-ahead audit, acceptance gates, IC/dir-acc deltas).
- Phased plan: P1 fill gaps (historical FOMC HTML scraper + score history + wire
  into backtest + release-date correction) · P2 informative output (Conflict
  Index, graded Bias, Triggers, yield-curve prediction) · P3 new data layers (Fed
  market pricing, macro surprise, rates decomposition, technical/positioning) ·
  P4 regime classifier + synthesis.
- AGENTS.md now points Codex at the spec.
- **Open decision for next session:** macro surprise needs a consensus/calendar
  data source (may require a new API key) — research in P3.2.

## 2026-06-01 — First walk-forward backtest (honest baseline)
- Rewrote `walk_forward.py` to measure IC (corr of score vs forward yield change)
  + directional accuracy + a threshold sweep — all threshold-free metrics.
- Runner: `scripts/backtest.py`. Ran 2015-01-01 → 2026-05-31 (4169 days).
- **Result (macro-data factors only; fomc_nlp/political = 0 in history):**
  - 1w: IC 0.004, DA 49.3% — noise.
  - 1m: IC 0.046, DA 52.2% — very weak.
  - 3m: IC 0.088, DA 52.6% — weak but best; focus on 3m.
- The ±0.15 band is NOT validated — raising the threshold doesn't lift hit-rate
  (3m sits ~51% across thresholds). Tuning it is premature until FOMC is in history.
- **Known bias:** FRED series are indexed to reference date, not release date →
  point-in-time backtest has look-ahead bias → true skill likely weaker. Fix with
  release-date (ALFRED/vintage) data.
- **Next, in order:** (1) score historical FOMC docs so fomc_nlp contributes in
  backtest; (2) release-date correction; (3) only then tune weights/threshold.

## 2026-06-01 — FOMC NLP wired + key-quote evidence + HTML report
- **FRED ingestion** live; current 10Y read = 4.45%.
- **Factors working:** inflation +0.37, liquidity -0.41, global_rates -0.07.
- **FOMC factor (the 30% one) is no longer 0.** Pluggable LLM scorer wired with
  **OpenAI / GPT-4o** (keys for Anthropic/Gemini also supported via configs/model.yaml).
  Reads the 6 PDFs in `FOMC/` (statements + minutes), caches scores.
- **Combined fomc_nlp = 0.6·statement + 0.4·minutes.** Latest (April 2026):
  statement -0.04, minutes +0.04 → combined ~-0.01.
- **Key-quote extraction:** GPT now returns verbatim supporting quotes per doc;
  shown in the HTML report as evidence (credibility boost, esp. for minutes).
- **HTML report** added: `data/reports/latest.html` (dark theme, forecast table,
  factor bars, FOMC evidence). Stable `latest.html` overwritten each run.
- **Current call:** Neutral across 1w/1m/3m — inflation (+) and liquidity (-)
  roughly cancel; FOMC near-neutral. Honest "mixed macro" read.

### Known issues / next
- Keyword scorer is noisy (gave April statement -1.0); GPT carries the signal at
  0.8 weight. Lexicon needs tuning OR lean harder on GPT.
- Weights & bp-sensitivity are untuned priors — need first walk-forward backtest.
- political_risk still 0 (no news pipeline yet).
- Dot plot (SEP) not yet parsed.

## 2026-06-01 — Scaffold
- Repo created at Desktop/TraceYield, pushed to github.com/DWSDavid/TraceYield (private).
- Structure, config-driven weights, factor blend predictor, report, backtest stub,
  docs/concepts learning curriculum, macro-tutor Q&A subagent, smoke tests passing.
