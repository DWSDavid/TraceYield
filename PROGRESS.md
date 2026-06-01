# TraceYield — Progress Log

Newest entry on top. One entry per meaningful update. Format: `## YYYY-MM-DD — title`.

---

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
