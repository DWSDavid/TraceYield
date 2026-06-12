# TraceYield — Progress Log

Newest entry on top. One entry per meaningful update. Format: `## YYYY-MM-DD — title`.

---

## 2026-06-03 - Grounded GPT macro analysis from raw FOMC docs
- Added a grounded macro analysis metadata/report layer.
  - Reads the latest raw `data/raw/fomc/statement/*.txt` and
    `data/raw/fomc/minutes/*.txt` at or before the trajectory `as_of`.
  - Passes full statement/minutes context plus the released macro snapshot,
    policy path, Polymarket check, and curve view into GPT.
  - Writes `metadata.grounded_macro_analysis` with factor stances, plain-English
    causal logic, data points, and short FOMC quotes.
- Preserved model guardrails.
  - `model_usage` is `narrative_and_regime_only_no_bp_or_central_shift`.
  - The attachment step asserts that curve `tenors` are unchanged; GPT does not
    set bp magnitudes, central/p50, fan bands, overlays, or weights.
- Fixed the explanation-layer macro snapshot units.
  - Calendar-month comparisons are used for monthly CPI/PCE data instead of
    observation-count offsets.
  - Index/level series report percent changes; rate/yield series report bp
    changes.
- Regenerated:
  - `data/cache/grounded_macro_analysis/grounded_macro_analysis_2026-05-30.json`
  - `data/forecasts/curve_trajectory_20260530.json`
  - `data/reports/curve_report_20260530.html`
  - `data/reports/curve_latest.html`
- Verification:
  - Focused grounded-analysis tests passed: 3 tests.
  - Full `pytest -q -p no:cacheprovider --basetemp=...` passed: 91 tests.

## 2026-06-03 - Random-walk curve and plain-English explanation pass
- Upgraded the random-walk baseline from a single displayed value into a full
  flat reference curve in the interactive factor explorer.
  - The factor scenario JSON now exposes `random_walk` for each month.
  - 10Y uses the stored baseline path; other displayed targets use their current
    level as a flat random-walk path.
  - The in-page chart can show/hide the random-walk curve, and the monthly table
    includes a "Random-walk curve" column.
- Rewrote factor explanations in plainer market language.
  - Inflation now explains the bond-buyer compensation channel, Fed reaction,
    borrowing-cost channel, and "bond price down, yield up" mechanism.
  - Growth, policy, liquidity/supply, and global relative value explain their
    chain effects rather than implying direct mechanical relationships.
- Clarified the interactive path definitions.
  - Random walk = current yield stays flat.
  - Base = no-macro FADNS curve dynamics.
  - Selected factors = base plus chosen macro forces.
  - Official central = all macro blocks selected.
- Regenerated final report:
  - `data/reports/curve_report_20260530.html`
  - `data/reports/curve_latest.html`
- Verification:
  - Focused render tests passed: 4 tests.
  - `ruff check src scripts tests` passed.
  - `black --check src scripts tests` passed.
  - Full `pytest -q -p no:cacheprovider --basetemp=...` passed: 89 tests.

## 2026-06-02 - HTML report explanation and control upgrade
- Expanded the report from a chart-first view into an explanation-first
  decision-support page.
  - Added detailed factor cards for all five macro blocks.
  - Each card now explains what the block includes and the transmission channel:
    data -> Fed path / term premium / risk appetite -> curve.
- Added sub-factor controls under each macro block.
  - Inflation now exposes CPI, Core CPI, PCE, Core PCE, T5YIE, T10YIE, and
    T5YIFR as sub-items.
  - Growth exposes payrolls, unemployment, claims, manufacturing production,
    retail sales, and JOLTS.
  - Liquidity/supply exposes Fed balance sheet, reserves, RRP, TGA, and auction
    stress.
  - Sub-factor toggles are clearly labeled as explanation-only proportional
    splits of the exact block attribution; the official curve remains unchanged.
- Added explanatory sections.
  - "Why It Moves" shows the 10Y 12m contribution and the causal chain for each
    block.
  - "Whole Prediction Logic" explains raw released data, macro z-score blocks,
    base FADNS, selected factors, central path, fan bands, and external checks.
  - The methodology now states that TraceYield is not an error-correction model;
    historical errors are used for range, not central-line forcing.
- Added "Policy Mapping Sandbox".
  - Shows current threshold map: `cut_prob_high`, `hike_prob_high`,
    `front_end_cut_bp`, and `front_end_hike_bp`.
  - Inputs can be adjusted in-page to see hypothetical next-FOMC 2Y / 10Y /
    2s10s scenario effects without changing config or the official path.
- Regenerated final report:
  - `data/reports/curve_report_20260530.html`
  - `data/reports/curve_latest.html`
- Verification:
  - Focused render tests passed: 4 tests.
  - `ruff check src scripts tests` passed.
  - `black --check src scripts tests` passed.
  - Full `pytest -q -p no:cacheprovider --basetemp=...` passed: 89 tests.

## 2026-06-02 - HTML report interaction upgrade
- Enlarged the fan-chart layout.
  - 10Y is now a full-width featured chart.
  - 2Y and 2s10s remain directly below as core supporting charts.
- Added a "Macro Factor Explorer" section to the self-contained HTML report.
  - Checkboxes let the user include/exclude the five FADNS macro blocks:
    inflation, policy path, growth, liquidity/supply, and global relative value.
  - The selected-factor path is recomputed in-browser from exact
    base-vs-adjusted attribution already stored in the trajectory JSON.
  - The interaction is view-only; official central, p50, fan bands, event
    overlays, and stored model outputs are unchanged.
- Added quantitative monthly output.
  - The explorer table shows month-by-month base, selected-factor path,
    official central, selected-vs-today bp change, and p10-p90 range.
  - The selected-all path matches the official macro-adjusted central path.
- Regenerated final report:
  - `data/reports/curve_report_20260530.html`
  - `data/reports/curve_latest.html`
- Verification:
  - Browser plugin could not inspect the local `file://` report because of its
    URL security policy, so the HTML file was verified directly.
  - Focused render tests passed: 4 tests.
  - `ruff check src scripts tests` passed.
  - `black --check src scripts tests` passed.
  - Full `pytest -q -p no:cacheprovider --basetemp=...` passed: 89 tests.

## 2026-06-02 - Polymarket external market check
- Added read-only Polymarket confirmation layer.
  - New module: `src/signals/polymarket_check.py`.
  - Uses public Gamma API `public-search` for discovery; no HTML scraping, no
    paid data, no trading/auth endpoints.
  - Applies an internal relevance filter so generic `rates` results do not leak
    into the 10Y Treasury yield check.
- Kept model separation explicit.
  - Polymarket output is written only to `metadata.polymarket_check`.
  - It does not move FADNS central, `p50`, fan bands, event overlays, weights,
    thresholds, or any bp magnitude.
  - Added tests proving `attach_polymarket_check(...)` leaves curve values
    unchanged.
- Added point-in-time snapshots.
  - Latest snapshot: `data/cache/polymarket/polymarket_check_20260530.json`.
  - Latest trajectory now carries the same contract:
    `data/forecasts/curve_trajectory_20260530.json`.
- Added HTML display.
  - `curve_latest.html` now includes a "Polymarket External Check" panel with
    status, alignment, model-usage guardrail, relevant market prices,
    bid/ask/spread, volume, confidence, and risk flags.
- Latest live check:
  - Status: `available`.
  - Alignment: `agree`.
  - Public markets show lower-threshold Yes around `0.475` for dipping below
    `3.9%` before 2027 versus higher-threshold Yes around `0.245` for hitting
    `4.8%`; this agrees with TraceYield's lower 10Y central-path lean.
- Verification:
  - Focused Polymarket/report/trajectory tests passed: 18 tests.
  - `ruff check src scripts tests` passed.
  - `black --check src scripts tests` passed.
  - Full `pytest -q -p no:cacheprovider --basetemp=...` passed: 88 tests.

## 2026-06-02 - Final curve report cleanup: realized data refresh, central path, and baselines
- Refreshed the free FRED cache and regenerated the curve trajectory.
  - Latest processed cache: `data/processed/fred_20260602.parquet`.
  - Replaced invalid FRED growth/manufacturing proxy `NAPM` with free FRED
    series `IPMAN`; the refreshed cache now includes realized CPI/core CPI,
    PCE/core PCE, payroll/unemployment/claims/retail/JOLTS, short Treasury
    proxies, dot-plot series, and `IPMAN`.
- Cleaned up the center-line design.
  - Recentered empirical forecast-error fan quantiles around the
    macro-adjusted FADNS central path.
  - `p50` now equals `central`; the report no longer treats a historical-error
    median bias as a separate corrected center.
- Added 10Y baselines and market range.
  - New `configs/market_ranges.yaml` stores the manual/free observed 10Y range:
    `3.90` to `4.80`.
  - Trajectory metadata now includes a flat 10Y random-walk baseline plus that
    market range.
  - The HTML report renders a new "10Y Baselines & Market Range" panel.
- Generated final artifacts:
  - `data/forecasts/curve_trajectory_20260530.json`
  - `data/forecasts/curve_trajectory_20260530.csv`
  - `data/reports/curve_report_20260530.html`
  - `data/reports/curve_latest.html`
- Latest sanity result after the data refresh:
  - `policy_path` remains a signal on `2s10s`.
  - `growth_risk` is now also a signal on `2s10s` after real labor and
    manufacturing data are available.
  - Inflation, liquidity/supply, and global relative value remain
    explanation-only.
- Verification:
  - Focused tests for center-line invariance, 10Y baseline/range metadata, and
    required HTML sections passed: 3 tests.
  - `ruff check src scripts tests ...` passed.
  - `black --check src scripts tests` passed.
  - `pytest -q -p no:cacheprovider --basetemp=...` passed: 85 tests.

## 2026-06-02 - Realized macro data central-path clarification
- Audited and strengthened the boundary between realized data and future events.
  - Already released macro data can move the FADNS central/p50 path through the
    five macro blocks.
  - Scheduled-but-unknown CPI/NFP/PCE/QRA dates still widen only
    `p10/p25/p75/p90`; they do not move central before release.
  - FOMC remains the only event overlay allowed to shift central, and only when
    high-confidence cut/hike probabilities clear config thresholds.
- Updated `src/models/fadns.py`.
  - Inflation block now consumes free realized headline PCE `PCEPI`, core PCE
    `PCEPILFE`, headline CPI `CPIAUCSL`, core CPI `CPILFESL`, breakevens, and
    5y5y when cached and release-lag available.
  - Growth block now supports labor `PAYEMS`, `UNRATE`, `ICSA`, `NAPM`,
    `RSAFS`, and `JTSJOL`; if labor series are absent from the current cache it
    explicitly falls back to the 2s10s curve-stress proxy.
  - Liquidity/supply block no longer uses future QRA proximity as a central-path
    input. It uses released Fed liquidity/TGA/RRP data plus cached
    TreasuryDirect auction stress when available.
  - Added `realized_macro_data_audit(...)` for trajectory metadata.
- Updated `configs/fred_series.yaml`.
  - Added free FRED series `CPILFESL`, `PCEPI`, and `JTSJOL`.
- Updated `src/models/curve_trajectory.py`.
  - Writes `metadata.realized_macro_data_audit` into trajectory JSON.
  - The latest audit shows current cached data includes CPI/core-PCE/breakevens,
    policy target/EFFR/DGS2/FOMC tone, liquidity/TGA/RRP/auction stress, and
    global relative-value series.
  - Current cache is still missing `CPILFESL`, `PCEPI`, `PAYEMS`, `UNRATE`,
    `ICSA`, `NAPM`, `RSAFS`, `JTSJOL`, `DGS3MO`, `DGS6MO`, and `FEDTARMD`;
    these are labeled honestly as missing/proxy until the FRED cache refreshes.
- Updated `src/report/render_html.py` wording.
  - Released CPI/PCE/labor/supply data can affect central through macro blocks.
  - Upcoming CPI/NFP/PCE/QRA dates widen only the fan.
- Generated updated artifacts from cached data:
  - `data/backtest/phase4_macro_block_ic.csv`
  - `data/forecasts/curve_trajectory_20260529.json`
  - `data/forecasts/curve_trajectory_20260529.csv`
  - `data/reports/curve_report_20260529.html`
  - `data/reports/curve_latest.html`
- Verification:
  - New tests failed first on the old behavior, then passed.
  - Focused realized-macro tests passed: 4 tests.
  - `ruff check .` passed.
  - `black --check .` passed.
  - `pytest -q -p no:cacheprovider --basetemp=pytest-tmp-realized-macro-full-a`
    passed: 83 tests.

## 2026-06-02 - Phase 4 item 5 macro block IC sanity
- Added point-in-time single-factor IC sanity for the five FADNS macro blocks.
  - `inflation_regime`, `policy_path`, `growth_risk`, `liquidity_supply`, and
    `global_relative_value` are evaluated against only their aligned economic
    targets.
  - The macro series are the same release-lagged, rolling-z composites used by
    the FADNS transition inputs.
  - Row-level Rank IC and directional accuracy reuse the existing evaluation
    harness; Newey-West t-stats reuse the HAC regression helper.
  - Noise bands are explicit: 3m `0.15`, 6m `0.22`, reflecting the small
    effective independent sample caveat.
- Added `data/backtest/phase4_macro_block_ic.csv`.
  - 18 aligned rows: inflation `10Y`; policy `2Y` and `2s10s`; growth `2s10s`
    and `10Y`; liquidity `10Y` and `30Y`; global relative value `10Y` and
    `30Y`, each at 3m and 6m.
- Updated trajectory metadata.
  - `metadata.base_vs_adjusted.macro_block_sanity` now contains one summary row
    per block with `ic_3m`, `ic_6m`, `dir_acc_3m`, `nw_t_3m`,
    `aligned_target`, `expected_sign`, `verdict`, and `note`.
  - Latest trajectory regenerated:
    `data/forecasts/curve_trajectory_20260529.json` and `.csv`.
- Latest honest sanity result:
  - `policy_path` is `signal` on `2s10s` with expected negative sign:
    3m IC `-0.2803`, 6m IC `-0.3764`, NW |t| `2.54` / `2.84`.
  - `inflation_regime`, `growth_risk`, `liquidity_supply`, and
    `global_relative_value` are `explanation-only`.
- Confirmed no look-ahead path:
  - Uses `_point_in_time_inputs(...)`, FRED release lags, and forward targets
    aligned to forecast dates.
- Fixed the lingering test pattern that wrote directly under `.codex-tmp`;
  `tests/test_curve_trajectory.py` now uses pytest `tmp_path`.
- Verification:
  - New tests failed first on missing macro-block IC contract, then passed.
  - Focused tests passed: 3 tests.
  - `ruff check .` passed.
  - `black --check .` passed.
  - `pytest -q -p no:cacheprovider --basetemp=pytest-tmp-phase4-full-a` passed:
    80 tests.
- STOPPED for Claude validation. No paid data, no news crawler, and no changes
  to Nelson-Siegel fitting or curve reconstruction math.

## 2026-06-02 - Phase 3 HTML report platform
- Added `src/report/render_html.py`.
  - Renders a single self-contained HTML page from a saved
    `data/forecasts/curve_trajectory_<asof>.json` contract.
  - Produces inline SVG fan charts for 2Y, 10Y, and 2s10s, with collapsible 5Y,
    30Y, and 5s30s supporting charts.
  - Embeds exact chart data in a local JSON script tag so central and p50 paths
    can be audited against the trajectory JSON.
  - Uses no external scripts, stylesheets, fonts, images, or network resources at
    view time.
  - Shows event markers and hover titles from trajectory overlay metadata;
    widened months are highlighted on the fan charts.
  - Includes policy-path source/confidence, proxy-only degradation language,
    implied rates, dot median, market-vs-dot gap wording, and market-confirmation
    context when cached FRED data is available.
  - Adds explanatory driver-why table, event timeline with estimated-date flags,
    and methodology/honesty footer citing arXiv:2601.04608 plus Kuttner/GSS.
  - Contains no alpha or beat-random-walk claims.
- Updated `scripts/curve_run.py`.
  - Added `--html` and optional `--trajectory-json`.
  - `--html` is read-only on saved trajectory JSON and writes
    `data/reports/curve_report_<asof>.html` plus `data/reports/curve_latest.html`
    without regenerating upstream model outputs.
- Added `tests/test_render_html.py`.
  - Required sections and honesty language.
  - Central/p50 chart-data fidelity against the input JSON.
  - Dated/latest HTML persistence.
- Generated HTML artifacts:
  - `data/reports/curve_report_20260529.html`
  - `data/reports/curve_latest.html`
- Acceptance checks:
  - `scripts/curve_run.py --html` rendered from
    `data/forecasts/curve_trajectory_20260529.json`.
  - Static self-contained check passed: no `http://` or `https://` references.
  - Chart-data fidelity passed for 2Y central and 10Y p50 against saved JSON.
  - Estimated dates and `proxy only, low confidence` degradation language are
    present.
  - Browser plugin visual sanity was attempted twice, but the local Node browser
    kernel failed to start under the Windows sandbox (`spawn setup refresh`);
    deterministic HTML checks and render tests passed.
- Verification:
  - `tests/test_render_html.py` failed first on missing `src.report.render_html`,
    then passed: 3 tests.
  - `ruff check .` passed.
  - `black --check .` passed.
  - `pytest -q --basetemp=.codex-tmp/pytest/basetemp` passed: 72 tests.
  - `daily_run.main(use_llm=False)` completed using cached FRED data after
    sandbox socket permissions blocked live FRED pulls.
- STOPPED after Phase 3 implementation for Claude validation. No FADNS,
  trajectory, or policy-path logic changes; no paid data, news crawler, web
  server, or build step.

## 2026-06-02 - Phase 2b event uncertainty fan widening
- Added symmetric scheduled-event uncertainty widening to
  `src/models/curve_trajectory.py`.
  - New `apply_event_uncertainty_overlay(...)` consumes
    `configs/fomc_calendar.yaml` and `configs/data_release_calendar.yaml`.
  - Calendar events map into the existing 1-12 forecast-month buckets via the
    same month convention as the policy-path FOMC step.
  - Widening touches only `p10/p25/p75/p90`; it leaves `central` and `p50`
    unchanged. Existing policy-path directional steps remain the only central
    nudge.
  - Multiple events in one bucket combine by sqrt-sum-of-squares; 2s10s and
    5s30s widths are derived from their underlying tenor legs.
  - Estimated release dates still apply and are tagged in event reasons.
  - The monotone fan-width guard is re-applied after widening so bands cannot
    narrow versus the prior month.
- Updated `configs/event_overlay.yaml`.
  - Added `uncertainty_widen_bp` for FOMC/CPI/NFP/PCE/QRA per tenor.
  - Added `combine: sqrt_sum_of_squares`; no bp constants live in code.
- Wired the curve trajectory pipeline so uncertainty widening runs after the
  Phase 2a policy-path FOMC step.
- Added tests in `tests/test_curve_trajectory.py`.
  - Single-event symmetric fan widening.
  - Multi-event quadrature rather than simple sum.
  - No-event no-change using a controlled calendar fixture.
  - Central-line / p50 invariance.
  - FOMC directional step and uncertainty widening coexisting independently.
- Acceptance output from latest cached curve trajectory as of `2026-05-29`:
  - Month 1 events: NFP `2026-06-05`, CPI `2026-06-10`, FOMC `2026-06-17`,
    PCE `2026-06-25`.
  - Month 1 widen bp: 2Y `23.173260`, 5Y `21.000000`, 10Y `20.149442`,
    30Y `17.578396`, 2s10s `30.708305`, 5s30s `27.386128`.
  - Month 1 2Y before/after uncertainty: central `3.836102 -> 3.836102`,
    p50 `4.127274 -> 4.127274`, p10 `3.506318 -> 3.274585`,
    p90 `4.599522 -> 4.831255`.
  - Month 3 contains QRA + NFP + CPI + PCE and uses quadrature:
    10Y widen `18.520259bp` = sqrt(9^2 + 9^2 + 10^2 + 9^2).
  - Month 1 carries both overlay records independently:
    FOMC policy-path step `0.0bp` due no high-conviction probability source, plus
    uncertainty widen `23.173260bp` on 2Y.
  - Latest full calendar has no true no-event forecast bucket because NFP/CPI/PCE
    recur monthly; no-event no-change is covered by the controlled unit test.
- Generated updated trajectory artifacts:
  - `data/forecasts/curve_trajectory_20260529.json`
  - `data/forecasts/curve_trajectory_20260529.csv`
- Verification:
  - `tests/test_curve_trajectory.py` failed first on missing
    `apply_event_uncertainty_overlay`, then passed: 9 tests.
  - `ruff check .` passed.
  - `black --check .` passed.
  - `pytest -q --basetemp=.codex-tmp/pytest/basetemp` passed: 69 tests.
  - `daily_run.main(use_llm=False)` completed using cached FRED data after
    sandbox socket permissions blocked live FRED pulls.
- STOPPED after Phase 2b implementation for Claude validation. No FADNS core
  changes, no paid data, no news crawler.

## 2026-06-02 - Phase 2 policy-path validation fixes
- Fixed FRED-proxy direction overstatement after Claude validation.
  - Widened the front-end proxy HOLD band from +/-10bp to +/-25bp so a small
    positive Treasury bill-vs-funds basis is not labeled as a tightening path.
  - Capped standalone FRED-proxy confidence at `low`; probability sources can
    still supply their own confidence when they win precedence.
  - Added the bill-vs-funds basis / term-premium caveat to the FRED proxy
    reason while keeping `market_vs_fed_gap_bp` as the signed market-vs-dot
    signal.
- Fixed the latent probability-source merge bug.
  - `_overlay_probability_source` now derives `EASING` / `TIGHTENING` from high
    cut/hike probability even when `expected_target_rate_after_meeting` is
    unavailable, covering Atlanta probability-only payloads.
- Not done in this round:
  - Did not add the future uncertainty-widening overlay.
  - Did not touch FADNS core.
- Verification:
  - `tests/test_policy_path.py` failed first on the old behavior, then passed:
    7 tests.
  - Live policy-path output as of `2026-05-31`: FRED proxy 3m `3.81`,
    6m `3.87`, 12m `3.99`, direction `HOLD`, confidence `low`,
    market-vs-dot gap `+47bp`; Atlanta/FedWatch still degrade gracefully when
    unavailable.
  - `ruff check .` passed.
  - `black --check .` passed.
  - `pytest -q --basetemp=.codex-tmp/pytest/basetemp` passed: 65 tests.
  - `daily_run.main(use_llm=False)` completed using cached FRED data after
    sandbox socket permissions blocked live FRED pulls.

## 2026-06-02 - Phase 2 policy-path enrichment
- Added `src/signals/policy_path.py`.
  - Defines a `PolicyPathProvider` contract.
  - Implements free FRED proxy provider using `DGS3MO/DGS6MO/DGS1` when
    available and documented fallbacks to current policy-to-2Y slope when the
    new short Treasury series are not cached yet.
  - Implements optional manual `data/manual/fedwatch_latest.csv` provider.
    FedWatch CSV overrides next-meeting probability fields when present, but
    CME/FedWatch scraping and futures are not hard dependencies.
  - Implements best-effort Atlanta Fed MPT object-pod provider. The official MPT
    page says the tracker estimates SOFR option-implied distributions and offers
    source/historical-data links, but the currently linked old
    `mpt_histdata.xlsx` / `mpt_source.zip` URLs return 404. The reachable
    `data/research-data` object-pod feed exposes only a headline MPT indicator,
    not the full distribution, so this provider degrades gracefully.
  - Adds an OIS/Bloomberg WIRP stub that raises `NotImplementedError` with a
    paid-data note.
  - Adds `market_confirmation_row` for DGS2/DGS5/2s10s repricing context.
- Updated `configs/fred_series.yaml`.
  - Added free short-end proxy series: `DGS3MO`, `DGS6MO`, `DGS1`.
  - Added free SEP dot-plot series: `FEDTARMD`, `FEDTARMDLR`.
  - Existing cached data does not yet include those new series because the
    sandbox blocked outbound FRED sockets; the provider falls back cleanly.
- Added `configs/event_overlay.yaml`.
  - Keeps all policy-path FOMC overlay bp magnitudes in config.
  - Current high-conviction cut/hike thresholds are 60%; front-end scenario step
    is +/-12.5bp.
- Extended `src/models/curve_trajectory.py`.
  - Does not touch FADNS core.
  - Base central path remains the FADNS path.
  - Optional policy-path overlay records `base_central`, `overlay_bp`, and
    `overlay_reasons` on affected points.
  - `python -m src.models.curve_trajectory` now generates the base trajectory,
    merges policy-path providers, applies the configured next-FOMC overlay, and
    writes JSON/CSV.
- Added tests in `tests/test_policy_path.py` and extended
  `tests/test_curve_trajectory.py`.
  - Covered FRED forward proxy formula, dot-path gap, FedWatch CSV precedence,
    Atlanta feed graceful degradation, Atlanta object-pod parsing, paid OIS stub,
    and high-cut-prob front-end overlay.
- Acceptance output:
  - FRED proxy as of `2026-05-31`: 3m `3.81`, 6m `3.87`, 12m `3.99`,
    direction `TIGHTENING`, confidence `med`, market-vs-dot gap `+47bp`.
  - Atlanta provider degraded gracefully in sandbox:
    `atlanta_mpt_unavailable` due socket permission block.
  - FedWatch CSV degraded gracefully:
    `data/manual/fedwatch_latest.csv` absent, optional source skipped.
  - Merged result used `fred_proxy` with reason explicitly labeling it as a
    Treasury/front-end proxy, not futures pricing.
  - Next FOMC overlay for `2026-06-17` maps to month 1. Because no usable
    next-meeting cut/hike probabilities were available, the live overlay step was
    `0.0bp`; the reason is attached to 2Y and 2s10s. Tests verify nonzero
    behavior when a high cut probability is supplied.
- Generated updated trajectory artifacts:
  - `data/forecasts/curve_trajectory_20260529.json`
  - `data/forecasts/curve_trajectory_20260529.csv`
- Verification:
  - `ruff check .` passed.
  - `black --check .` passed.
  - `pytest -q --basetemp=.codex-tmp/pytest/basetemp` passed: 63 tests.
  - `daily_run.main(use_llm=False)` completed using cached data after sandbox
    socket permissions blocked live FRED pulls.
- STOPPED after Phase 2 enrichment for Claude validation. No HTML platform work.

## 2026-06-02 - Forward trajectory Phase 1 deliverable
- Added `src/models/curve_trajectory.py`.
  - Reuses the existing FADNS beta transition and forecast helpers.
  - Builds the latest 1-12 month path for `2Y`, `5Y`, `10Y`, `30Y`, `2s10s`,
    and `5s30s`.
  - Converts FADNS forecast changes into central level paths plus bp deltas
    versus the current fitted curve.
  - Computes empirical historical FADNS forecast-error quantiles
    (`p10/p25/p50/p75/p90`) from point-in-time predicted-vs-realized residuals.
  - Applies a monotone fan guard so p10-p90 and p25-p75 bands do not shrink with
    horizon.
- Added `tests/test_curve_trajectory.py` for the output contract, direct FADNS
  equality check, widening empirical fan, and JSON/CSV persistence.
- Generated Phase 1 artifacts:
  - `data/forecasts/curve_trajectory_20260529.json`
  - `data/forecasts/curve_trajectory_20260529.csv`
- Acceptance sanity:
  - `as_of=2026-05-29` after point-in-time release-lag handling.
  - 10Y 3m direct FADNS change `-0.466712` vs trajectory delta `-0.466712`
    (rounding diff about `-0.0000000117`).
  - Flat CSV has 72 rows: 6 targets x 12 months.
  - 10Y p10-p90 width widens from `1.048875` to `2.898486`.
- Verification:
  - `ruff check .` passed.
  - `black --check .` passed after mechanical formatting of
    `scripts/backtest.py` and `src/nlp/keyword_scorer.py`.
  - `pytest -q --basetemp=.codex-tmp/pytest/basetemp` passed: 57 tests.
  - `daily_run.main(use_llm=False)` completed using cached FRED data after the
    sandbox blocked outbound FRED sockets.
- STOPPED after Phase 1 for Claude validation before event-calendar work.

## 2026-06-02 - v3 Part A/B HAC inference and FADNS scorecards
- Implemented Part A HAC significance testing in `src/backtest/hac.py`.
  - Predictive regressions use all overlapping daily forward-window observations.
  - Newey-West/Bartlett HAC is primary with lag equal to the horizon
    (`63` for 3m, `126` for 6m).
  - Hansen-Hodrick/rectangular HAC is reported alongside; non-PSD HH covariance
    falls back to NW and is flagged.
  - Output includes beta, NW t-stat, HH t-stat, p-value, R2, Rank IC, and
    benchmark delta per `factor x target x horizon`.
- Added the FOMC circularity diagnostic:
  `forward target ~ fomc_tone + front_momentum`, with HAC t-stat on FOMC tone
  after controlling for front-end momentum.
- Implemented Part B FADNS in `src/models/fadns.py`.
  - Fits Nelson-Siegel `level/slope/curvature` from DGS2/DGS5/DGS10/DGS30.
  - Uses a small ridge VAR(1) augmented with existing free-data features:
    `fomc_tone`, inflation proxy, and 2s10s growth proxy.
  - Walk-forward refits use only release-lagged data available as of the forecast
    date; no new data sources.
  - Forecasts NS factors forward, reconstructs tenor moves, and derives
    2s10s/5s30s direction.
- Added runner `scripts/v3_part_ab.py`.
- Regenerated deliverables:
  - `data/backtest/phase1b_hac_significance.csv` (142 rows).
  - `data/backtest/phase2_fadns_scorecard.csv` (12 rows).
- Honest Part A verdict:
  - `policy_path` passes HAC on aligned `2s10s`:
    3m IC 0.262 vs bar 0.147, NW t 2.08;
    6m IC 0.319 vs bar 0.287, NW t 2.27.
  - `growth_risk` passes HAC on aligned `2Y`:
    3m IC 0.290 vs bar 0.222, NW t 2.70;
    6m IC 0.268 vs bar 0.249, NW t 2.11.
  - All other isolated factors fail the combined rule of beating the max Phase 0
    bar and clearing NW |t| >= 2 at both horizons.
- FOMC control result:
  - FOMC tone is not significant after controlling for front momentum.
  - On 2s10s: 3m beta -0.0287, t -0.40; 6m beta -0.0361, t -0.27.
  - Front momentum remains significant on 2s10s in the control regression
    (3m t -2.05, 6m t -2.60), so policy_path's raw 2s10s strength needs to be
    interpreted cautiously.
- Honest Part B verdict:
  - FADNS does not validate. It fails to beat the max(random_walk, momentum)
    benchmark and does not clear NW |t| >= 2 on curve targets.
  - 3m 2s10s: IC 0.134 vs bar 0.147, NW t 1.48.
  - 6m 2s10s: IC 0.191 vs bar 0.287, NW t 1.65.
  - 5s30s is negative IC at both horizons.
- STOPPED after Part A/B for validation. No final fusion was built.

## 2026-06-02 - v3 Part C clarification: 10Y headline by reconstruction
- Applied the strategic-narrowing clarification: 10Y remains the product's
  headline output, but the report now produces it by reconstruction rather than
  by isolated outright-level prediction.
- `configs/curve_weights.yaml` now marks `term_premium`, `liquidity_supply`, and
  `global_relative_value` as `context_only_factors`. The engine still computes
  them, but excludes them from core headline contributions.
- `src/models/curve_engine.py` now splits factor contributions into core vs
  context-only buckets and adds:
  - `context_contributions`
  - `context_tenor_pressure`
  - `ten_year_reconstruction`
- The reconstructed 10Y view is:
  `10Y_view = front_end_2Y + curve_2s10s`.
  The pure term-premium residual is shown separately as low-confidence,
  context-only information.
- `src/report/render_curve.py` now starts the curve report with a
  "Headline 10Y Direction" section and explicitly decomposes each core 10Y call
  into front-end 2Y, 2s10s curve, reconstructed 10Y, and residual term-premium
  context. 30Y moved to the context-only long-end section.
- `docs/SPEC_v3_CURVE_TRADES.md` now records the clarified rule: 30Y is
  context-only; 10Y is not.
- Regenerated `data/reports/curve_report_20260531.md` and `curve_latest.md`.
- Verification:
  - TDD red/green for `tests/test_curve_engine.py` and `tests/test_curve_report.py`.
  - `scripts/curve_run.py` completed from cached FRED data and printed the new
    reconstructed 10Y headline.

## 2026-06-01 - v3 Phase 1 benchmark-gated sign-audit redo completed
- Re-ran the accepted per-target Phase 1 aggregation with the missing Phase 0
  discipline restored: a `keep` now requires aligned-target IC above `0.05` and
  above the `momentum_3m` benchmark IC at both 3m and 6m.
- Removed post-hoc sign flipping from the scorecard. `phase1_single_factor_ic.csv`
  no longer emits `adjusted_rank_ic` or `sign_adjustment`; sign issues must be
  fixed in factor code and re-tested fresh.
- Added benchmark columns to every per-target row:
  `benchmark_model`, `benchmark_rank_ic`, and `benchmark_delta_ic`.
- Audited sign-convention bugs and fixed only the ones with an economic code
  issue before re-running IC:
  - `growth_risk`: fixed. The implemented proxy is curve-based growth-risk /
    easing stress, so higher curve stress should lean yields lower.
  - `term_premium`: fixed. Rising ACM term premium is treated as long-end
    cheapness / mean-reversion pressure, not automatic yield-up pressure.
  - `global_relative_value`: fixed. A wider UST premium versus Bund/JGB is
    treated as relative-value demand for Treasuries, leaning yields lower.
  - `liquidity_supply`: no code sign bug found. Tighter Fed liquidity / auction
    stress remains positive long-end yield pressure, so it is not flipped.
- Re-examined economic target alignment:
  - `term_premium` judged on `10Y` / `30Y`.
  - `ns_level` judged on `10Y` / `30Y`.
  - `cochrane_piazzesi` audited on all six targets because 2Y was a poor fit.
- Corrected surviving `keep` set after fresh point-in-time rerun:
  - `policy_path`: `2s10s`, IC 0.262 / 0.319 vs bar 0.147 / 0.287.
  - `cochrane_piazzesi`: `10Y`, IC 0.068 / 0.081 vs bar -0.052 / 0.014.
  - `growth_risk`: `5Y`, IC 0.211 / 0.165 vs bar 0.040 / 0.088.
  - `term_premium`: `30Y`, IC 0.150 / 0.070 vs bar -0.105 / -0.031.
  - `global_relative_value`: `30Y`, IC 0.101 / 0.115 vs bar -0.105 / -0.031.
- Corrected non-keep set:
  - `positioning_momentum`: `below_benchmark` on `2Y`, IC 0.088 / 0.116 vs
    bar 0.222 / 0.249.
  - `liquidity_supply`: `sign_mismatch` on `10Y`, no code-sign flip.
  - `risk_off_overlay`: `drop`, weak IC at both horizons.
  - `ns_slope`, `ns_level`, `macro_surprise`: `mixed`, not validated keeps.
- Cochrane-Piazzesi target audit:
  - `2Y`: below bar at both horizons.
  - `10Y`: clears bar and IC threshold at both horizons, so this is its decision
    target.
  - `30Y`: clears bar but fails the 3m IC threshold.
  - `2s10s` and `5s30s`: wrong sign versus bar.
- Outputs regenerated:
  - `data/backtest/phase0_benchmarks.csv`
  - `data/backtest/phase1_single_factor_ic.csv`
- Verification:
  - `python scripts/v3_phase01.py --start 2015-01-01` completed and stopped
    after Phase 1; no fusion, no Phase 2, no new data sources.
  - Focused `tests/test_curve_v3_single_factor.py`: 7 passed.
  - Full `pytest`: 47 passed.
  - `ruff check src tests scripts`: passed.
  - Black check passed on touched files.
  - `daily_run.main(use_llm=False)` completed using cached FRED data.

## 2026-06-01 - v3 Phase 1 aggregation redo completed
- Reworked the failed Phase 1 scorecard exactly at the aggregation layer; no
  Phase 2 work, no fusion, and no new data sources.
- `data/backtest/phase1_single_factor_ic.csv` now persists one row per
  `factor x target x horizon`. The file has 156 rows: 132 factor rows plus 24
  Phase 0 benchmark reference rows.
- Removed ICIR from the Phase 1 gate and CSV. The gate now uses aligned-target
  Rank IC sign and 3m/6m consistency only.
- Added aligned-target decision rules:
  - curve/slope factors (`policy_path`, `ns_slope`, `cochrane_piazzesi`) are
    judged on `2s10s`, `5s30s`, and `2Y`.
  - level-type factors (`ns_level`, `term_premium`) are judged on tenor targets.
  - other v2 factors are judged per target without cross-target averaging.
- Added `fix-sign`: when the strongest aligned target is consistently below
  `-0.05` across both 3m and 6m, the scorecard marks `fix-sign`, sets
  `sign_adjustment=-1`, and reports `adjusted_rank_ic` as the flip retest.
- Added the required caveat to every output row and stdout: overlapping 63/126d
  forward windows sampled daily mean effective independent N is roughly
  `n/horizon_days`; IC should be treated as a relative ranking metric, not an
  absolute significance test.
- Corrected decisions after rerun:
  - `policy_path`: `keep`, target `2s10s`, raw IC 0.262 / 0.319.
  - `cochrane_piazzesi`: `keep`, target `2Y`, raw IC 0.173 / 0.147.
  - `positioning_momentum`: `keep`, target `2Y`, raw IC 0.088 / 0.116.
  - `growth_risk`: `fix-sign`, target `2Y`, raw IC -0.290 / -0.268, adjusted
    IC 0.290 / 0.268.
  - `term_premium`: `fix-sign`, target `5Y`, raw IC -0.162 / -0.104, adjusted
    IC 0.162 / 0.104.
  - `global_relative_value`: `fix-sign`, target `2s10s`, raw IC -0.145 / -0.245.
  - `liquidity_supply`: `fix-sign`, target `10Y`, raw IC -0.097 / -0.136.
  - `ns_level`: `fix-sign`, target `2Y`, raw IC -0.125 / -0.101.
  - `risk_off_overlay`: `drop`, target `5Y`, IC 0.040 / 0.049.
  - `ns_slope`: `mixed`, target `5s30s`, IC 0.051 / 0.046; not dropped because
    it is borderline at 3m but does not hold above threshold at 6m.
  - `macro_surprise`: `mixed`, target `10Y`, IC -0.042 / -0.075; not cleanly
    weak in both horizons and not consistently wrong beyond threshold.
- Verification:
  - `python scripts/v3_phase01.py --start 2015-01-01` rewrote Phase 0/1 CSVs.
  - Focused test `tests/test_curve_v3_single_factor.py`: 6 passed.
  - Full `pytest` with workspace basetemp: 46 passed.
  - `ruff check src tests scripts`: passed.
  - Black check passed on touched files; full Black still flags two pre-existing
    untouched files (`scripts/backtest.py`, `src/nlp/keyword_scorer.py`).
  - `daily_run.main(use_llm=False)` completed using cached FRED data.

## 2026-06-01 - v3 Phase 1 VALIDATION (Claude): scorecard INVALID, redo aggregation
- Verdict: Phase 1 keep/drop conclusions are NOT acceptable. The point-in-time
  plumbing is clean (no look-ahead), but the aggregation layer makes the entire
  scorecard meaningless. Do NOT proceed to Phase 2 until fixed.
- PASS: point-in-time verified. Release lags applied via _available_series, all
  z-scores trailing/rolling, NS betas fit cross-sectionally per date (no time
  leak), forward targets use shift(-horizon) as label. Phase 0 momentum benchmark
  is a valid bar (3m 2s10s IC 0.147, 6m 0.287).
- FATAL FLAW: _aggregate_factor_metrics averages rank_ic across all 6 targets
  (2Y/5Y/10Y/30Y/2s10s/5s30s). Curve factors have intentionally opposite-signed
  tenor loadings (ns_slope 2Y=-0.80, 30Y=+0.80), so averaging IC across tenors
  CANCELS real signal to ~0. Every "drop" verdict is an artifact, not a finding.
- Proof (per-target 3m rank IC, recovered by un-averaging):
  - policy_path: 2Y 0.20, 2s10s 0.26 (BEATS momentum bar 0.147) but averaged to
    0.107 and wrongly tagged "drop". This is a KEEP factor. First real signal that
    beats a naive benchmark in the whole project.
  - cochrane_piazzesi: 2Y 0.17, 2s10s -0.22 → averages to ~0. Has signal but
    tenor vs curve sign is inverted; investigate sign, do not discard.
  - growth_risk: uniformly ~-0.20 across ALL 6 targets → consistent sign means
    it's a STRONG factor with an inverted sign; flip to ~+0.20, don't drop.
  - term_premium: 5Y/10Y/30Y uniformly ~-0.16 → same sign-flip situation.
  - ns_slope: weak everywhere (0.04/-0.03) → likely genuinely weak, confirm after
    per-target redo.
- SECONDARY: ICIR is negative even for positive-IC factors (computed within-quarter
  on overlapping 63d windows) — uninformative, drop it as a gate. Overlapping
  windows mean effective independent N ~= N/horizon (~44 for 3m); treat IC as
  relative ranking, not absolute significance.
- CORRECTIVE INSTRUCTION ISSUED to Codex: stop averaging IC across targets; persist
  per-target IC; judge curve factors on 2s10s/5s30s/2Y, level factors on tenor
  direction; keep/fix-sign/drop rule per aligned target; drop ICIR gate; add
  overlapping-window caveat. Then STOP again for validation. No fusion, no new data.
- Takeaway: the FAILURE is in evaluation method, not direction. Single-factor IC +
  few-but-refined approach is sound; corrected aggregation likely recovers 3-4 real
  factors (policy_path confirmed, growth_risk/term_premium via sign flip, CP via
  sign investigation) instead of the apparent total wipeout.

## 2026-06-01 - v3 Phase 0/1 curve-trade yardstick and single-factor IC
- Implemented v3 only through Phase 0 + Phase 1, then stopped for validation.
- Added reusable curve-trade evaluation harness in `src/backtest/eval.py`:
  - forward 3m/6m tenor moves for 2Y/5Y/10Y/30Y
  - forward 2s10s and 5s30s spread moves
  - Rank IC (Spearman via rank-correlation, no SciPy dependency), ICIR,
    directional accuracy, curve-shape hit rate, and 5-quantile monotonicity.
- Added Phase 0 benchmark runner:
  - `src/backtest/benchmarks.py`
  - `scripts/v3_phase01.py`
  - output: `data/backtest/phase0_benchmarks.csv`
  - cached FRED backtest window starts at 2015-01-01.
  - Phase 0 summary:
    - random walk 3m: curve Rank IC -0.259, curve-shape hit 93.0%;
      tenor direction is intentionally neutral/no-change, so tenor Rank IC is
      undefined and tenor DA is 1.5%.
    - random walk 6m: curve Rank IC -0.406, curve-shape hit 90.4%.
    - momentum 3m: tenor Rank IC 0.026, tenor DA 49.9%, curve Rank IC 0.130,
      shape hit 91.2%.
    - momentum 6m: tenor Rank IC 0.080, tenor DA 51.5%, curve Rank IC 0.222,
      shape hit 90.3%.
- Added Phase 1 isolated factor runner:
  - `src/backtest/single_factor.py`
  - output: `data/backtest/phase1_single_factor_ic.csv`
  - no fusion model and no new data sources.
  - Added FRED-only Nelson-Siegel level/slope and Cochrane-Piazzesi
    forward-rate factors.
  - Evaluated every candidate alone against the Phase 0 harness for 3m/6m.
- Fixed the three v2 factor issues required by v3:
  - `macro_surprise` now uses CPI/core-PCE release-over-release acceleration as
    a free-data surprise proxy, not inflation level.
  - `growth_risk` no longer reuses VIX; it is curve-growth based. `risk_off`
    now separately detects VIX spikes/stress.
  - `term_premium` now normalizes ACM 10Y term-premium changes by rolling std
    instead of fixed `/0.50` scaling.
- Phase 1 headline IC table:
  - `policy_path`: mean Rank IC 0.126, tagged drop because subperiod IC was not
    stable despite positive average IC.
  - `risk_off_overlay`: mean Rank IC 0.021, drop.
  - `ns_slope`: mean Rank IC 0.014, drop.
  - `cochrane_piazzesi`: mean Rank IC 0.001, drop.
  - `macro_surprise`: mean Rank IC -0.028, drop.
  - `ns_level`: mean Rank IC -0.048, drop.
  - `term_premium`: mean Rank IC -0.050, drop.
  - `positioning_momentum`: mean Rank IC -0.061, fix.
  - `liquidity_supply`: mean Rank IC -0.075, fix.
  - `global_relative_value`: mean Rank IC -0.078, fix.
  - `growth_risk`: mean Rank IC -0.200, fix.
- Added cache/performance hardening:
  - FOMC score parquet loading is cached by path, without breaking tests that
    monkeypatch `SERIES_PATH`.
  - Treasury auction cache loading and ACM rolling z-score calculations are
    cached/precomputed for faster backtests.
  - `fred_client.fetch_all()` now honors its documented behavior and falls back
    to cached FRED parquet files when `fredapi` is unavailable.
- Verification:
  - `python scripts/v3_phase01.py --start 2015-01-01` wrote both required CSVs.
  - `pytest` with workspace basetemp: 44 passed.
  - `ruff check src tests scripts`: passed.
  - Black check passed on all touched files.
  - Full Black check still reports two pre-existing untouched files
    (`scripts/backtest.py`, `src/nlp/keyword_scorer.py`) would be reformatted;
    left untouched to avoid unrelated churn.
  - `daily_run.main(use_llm=False)` completed using cached FRED data because
    this runtime lacks `fredapi`.

## 2026-06-01 - Long-end signal audit plus TreasuryDirect auction stress
- Audited v2 long-end drivers after Phase A backtest showed front-end signal but
  weak/negative 10Y/30Y IC.
  - `liquidity_supply` sign was not inverted: falling WALCL/WRESBAL still maps to
    positive yield pressure, and sampled diagnostics showed small positive
    correlation to 10Y/30Y forward changes.
  - `term_premium` was using the ACMTP10 level. This was spec-signed
    (higher ACMTP10 -> positive yield pressure) but empirically mixed with
    mean-reversion. Switched the ACM input to trailing ACMTP10 change so the
    signal measures term-premium repricing rather than structural level.
- Added `term_premium_change_asof()` in `src/ingestion/nyfed_acm.py` and wired it
  into `src/signals/curve_drivers.py`.
- Added free TreasuryDirect auction ingestion:
  - `src/ingestion/treasury_auctions.py`
  - Source: `https://treasurydirect.gov/TA_WS/securities/search`
  - Cache: `data/cache/treasury/auctions.parquet`
  - Cached 275 records from 2015-01-13 through 2026-05-13: 138 10Y auctions and
    137 30Y auctions.
  - TreasuryDirect search JSON exposes bid-to-cover, high yield, indirect bidder
    accepted, total accepted, and offering amount. It does not expose WI yield in
    the records fetched, so true tail (`stop-out - when-issued`) is unavailable
    and `tail_bp` remains null rather than fabricated.
- Wired rolling auction stress into `liquidity_supply`. Poor auctions
  (low bid-to-cover, low indirect bidder share, and positive tail when available)
  add positive long-end yield pressure. Missing auction cache degrades to the
  balance-sheet liquidity score.
- Current curve report after changes:
  - `3m_core`: `BEAR_FLATTENING`, main driver `policy_path`, confidence 60%.
  - `6m_core`: `BEAR_FLATTENING`, main driver `policy_path`, confidence 58%.
- Backtest after changes, start `2015-01-01`:
  - Baseline before this change: 3m 10Y IC -0.045 / DA 48.4%, 30Y IC -0.108 /
    DA 39.5%; 6m 10Y IC -0.089 / DA 41.4%, 30Y IC -0.194 / DA 37.7%.
  - New `3m_core`: 10Y IC -0.078 / DA 48.5%; 30Y IC -0.161 / DA 44.5%;
    curve-shape hit improved from 31.6% to 38.5%.
  - New `6m_core`: 10Y IC -0.055 / DA 47.1%; 30Y IC -0.129 / DA 48.7%;
    curve-shape hit improved from 27.8% to 30.3%.
  - Interpretation: DA and curve-shape improved, especially 30Y DA, but 10Y/30Y
    IC remains negative. Directly signed term-premium repricing is not yet a
    good forward long-end predictor; next step should separate contemporaneous
    pressure from mean-reversion/valuation.
- Verification: `pytest` = 35 passed; `ruff check src tests scripts` passed;
  Black check passed on touched files.

## 2026-06-01 - v2 curve backtest and NY Fed ACM term premium
- Added NY Fed ACM ingestion in `src/ingestion/nyfed_acm.py`.
  - Official free source:
    `https://www.newyorkfed.org/medialibrary/media/research/data_indicators/ACMTermPremium.xls`.
  - Raw cache: `data/cache/nyfed/ACMTermPremium.xls`.
  - Processed cache: `data/processed/nyfed_acm_term_premium.parquet` plus CSV.
  - Cached 16,203 daily rows from 1961-06-14 through 2026-05-28.
- Added `xlrd>=2.0.1` to `requirements.txt` because the NY Fed official file is
  an `.xls` workbook.
- Wired ACM `ACMTP10` into `src/signals/curve_drivers.py` so the `term_premium`
  driver now prefers NY Fed ACM 10Y term premium and gracefully falls back to the
  previous breakeven/real-yield/30Y-momentum proxy when ACM data is unavailable.
- Added v2 curve walk-forward backtest in `src/backtest/curve_v2.py` and
  `scripts/curve_backtest.py`.
  - Uses release-lagged point-in-time histories for each forecast date.
  - Records `3m_core` and `6m_core` `curve_call`, `tenor_pressure`, realized
    2Y/5Y/10Y/30Y changes, tenor hit flags, curve-shape hit flags, confidence,
    and main/secondary drivers.
  - Writes row-level output to `data/backtest/curve_v2_backtest.csv`.
- Backtest run on `fred_20260601.parquet`, start `2015-01-01`, wrote 5,515 rows:
  - `3m_core` n=2,789: 2Y DA 59.7%, 5Y DA 54.8%, 10Y DA 48.4%, 30Y DA 39.5%;
    ICs 2Y 0.217, 5Y 0.113, 10Y -0.045, 30Y -0.108; curve-shape hit 31.6%.
    At confidence >=0.70: coverage 9.2%, tenor hit 68.9%, shape hit 51.6%.
  - `6m_core` n=2,726: 2Y DA 57.2%, 5Y DA 54.9%, 10Y DA 41.4%, 30Y DA 37.7%;
    ICs 2Y 0.307, 5Y 0.199, 10Y -0.089, 30Y -0.194; curve-shape hit 27.8%.
    At confidence >=0.70: coverage 8.1%, tenor hit 57.2%, shape hit 13.6%.
- Interpretation: current v2 engine has useful front-end signal but weak long-end
  and curve-shape accuracy; next improvements should target supply/auction,
  MOVE/rates-vol, and richer term-premium/long-end mapping.
- Verification: `pytest` = 31 passed; `ruff check src tests scripts` passed;
  Black check passed on touched files.

## 2026-06-01 - v2 Phase A UST curve report from existing FRED data
- Added the v2 Phase A implementation plan at
  `docs/superpowers/plans/2026-06-01-v2-ust-curve-phase-a.md`.
- Added v2 configs:
  - `configs/curve_weights.yaml` for `1m_tactical`, `3m_core`, `6m_core`, and
    `12m_structural` driver weights from `docs/SPEC_v2_UST_CURVE.md`.
  - `configs/curve_rules.yaml` for driver-to-tenor loadings and curve-call
    thresholds.
- Added v2 signal and engine modules:
  - `src/signals/curve_drivers.py` computes Phase-A proxy scores for
    `policy_path`, `macro_surprise`, `liquidity_supply`, `term_premium`,
    `growth_risk`, `global_relative_value`, `positioning_momentum`, and
    `risk_off_overlay` using existing cached/FRED data.
  - `src/signals/curve_impact.py` maps driver contributions into signed 2Y, 5Y,
    10Y, and 30Y pressure and classifies `BULL/BEAR` + `STEEPENING/FLATTENING`
    or range/conflict states.
  - `src/models/curve_engine.py` emits `CurveForecast` dataclasses for all four
    v2 stages with factor scores, contributions, main/secondary drivers,
    confidence, rationale, triggers, and linkage note.
- Added `src/report/render_curve.py` and `scripts/curve_run.py`. The script uses
  the latest processed FRED parquet plus configured release lags, so this first
  v2 report does not require live API calls.
- Current cached v2 report (`fred_20260601.parquet`, data through 2026-05-31):
  - `3m_core`: `BEAR_FLATTENING`, main driver `policy_path`, confidence 62%.
  - `6m_core`: `BEAR_FLATTENING`, main driver `policy_path`, confidence 60%.
  - Saved to `data/reports/curve_report_20260531.md`.
- Verification: `scripts/curve_run.py` passed; `scripts/mvp_data_check.py`
  passed; `pytest` = 27 passed; `ruff check src tests scripts` passed; Black
  check passed on the new/touched v2 Python files. Full-repo Black still flags
  pre-existing formatting in `scripts/backtest.py` and `src/nlp/keyword_scorer.py`.

## 2026-06-01 - Treasury yield trend factor and 1m/3m/6m/12m horizons
- Added `src/signals/yield_trend.py`, an interpretable Treasury historical
  pattern factor using 10Y momentum, 10Y range position, and 2s10s/5s30s curve
  trend. Positive remains upward yield pressure; negative remains downward yield
  pressure.
- Wired `yield_trend` into `src/signals/factors.py` and `configs/weights.yaml`.
  News NLP remains out of scope; `political_risk` stays as the VIX proxy with a
  smaller 5% weight.
- Replaced the old `1w/1m/3m` forecast set with `1m/3m/6m/12m` in weights,
  predictor sensitivity, smoke tests, and walk-forward horizon day counts.
- Updated report labels so top-driver attribution follows the longest active
  horizon, currently `12m`.
- MVP data check passed on `fred_20260601.parquet`: `yield_trend=+0.306`; 1m,
  3m, 6m, and 12m all rendered as Neutral with target yields 4.476%, 4.484%,
  4.480%, and 4.516%.
- Verification: `pytest` = 22 passed. `daily_run` with `use_llm=False` was tried
  twice but timed out while fetching FRED before producing a report, so the
  cached-data path is verified and the live-fetch daily path still needs a local
  rerun.

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
