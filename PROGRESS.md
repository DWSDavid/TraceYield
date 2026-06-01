# TraceYield — Progress Log

Newest entry on top. One entry per meaningful update. Format: `## YYYY-MM-DD — title`.

---

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
