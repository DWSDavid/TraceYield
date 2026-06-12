# SPEC v4 — Report / HTML Platform

Status: DRAFT (Claude, 2026-06-02). Build target = after Phase 2b (uncertainty-widening
overlay) lands. This is the user-facing deliverable: a single self-contained HTML page that
presents the 12-month forward UST curve VIEW.

## Product framing (carry over from v4)
This is a **decision-support VIEW**, not an alpha signal. Every panel must communicate
**direction + range + the "why"**, and stay honest about uncertainty. No claim of beating
random walk anywhere in the UI.

## Data sources (all already produced upstream — the report only READS them)
- `data/forecasts/curve_trajectory_<asof>.json` — central path + p10/p25/p50/p75/p90 fan,
  per tenor (2Y/5Y/10Y/30Y/2s10s/5s30s) × 12 months, plus `metadata.event_overlays` and
  `metadata.policy_path`.
- `src/signals/policy_path.py` → merged policy-path contract + `market_confirmation_row`.
- `configs/fomc_calendar.yaml`, `configs/data_release_calendar.yaml` — event markers.

## Page layout (single HTML, top → bottom)

### 1. Headline strip
- As-of date, headline 10Y direction + 3m / 6m CORE readouts (e.g. "10Y: lower over 12m,
  mildly; curve bull-steepening").
- One-line honesty disclaimer: "Scenario view with uncertainty; not a trading signal."

### 2. Fan charts (the centerpiece)
- One fan chart per CORE tenor: **2Y, 10Y, 2s10s** (5Y/30Y collapsible).
- X = next 12 months; Y = yield % (or bp for spreads).
- Shaded p10–p90 and p25–p75 bands; solid central/p50 line; dashed "today" reference.
- **Event markers** on the x-axis: FOMC (★ if SEP), CPI, NFP, QRA — hover shows the event +
  its overlay reason (directional step and/or fan-widening). Months with wider bands should be
  visually obvious.

### 3. Policy-path panel
- Direction (EASING/HOLD/TIGHTENING) + confidence, implied 3m/6m/12m path, dot-plot median,
  `market_vs_fed_gap_bp` with plain-English label ("market prices LESS easing than the dots").
- Provider/source line (fred_proxy / Atlanta / FedWatch) so the user knows the data quality.
- Market-confirmation row: DGS2/DGS5/2s10s + agrees? flag.

### 4. Driver / "why" table
- Per contributing input (policy path, inflation, growth, liquidity/supply, risk-off): a signed
  directional lean (↑/↓/→) for the front end vs long end + a one-line reason. This is the
  "combine multiple reasonable views" surface; it is explanatory, not a weighted alpha score.

### 5. Event timeline (next 12 months)
- Chronological list of scheduled events with date, type, and expected impact note
  (e.g. "Jun 17 FOMC — hold expected; Jul 14 CPI — front-end risk"). Mark estimated dates.

### 6. Methodology / honesty footer
- One paragraph: FADNS core (4 tenors + core PCE + FOMC tone), empirical fan from historical
  forecast errors, event overlay = surprise-only direction + quadrature fan widening, long-end ≈
  random walk caveat, free-data-only. Cite arXiv:2601.04608 (FADNS) + Kuttner/GSS for the overlay.

## Engineering
- New module `src/report/render_html.py` (do NOT modify FADNS / trajectory / policy_path logic;
  read their outputs only). Reuse existing `src/report/render_curve.py` text where possible.
- Charts: matplotlib → static PNG/SVG embedded, OR a lightweight self-contained JS lib
  (e.g. inline Plotly/Chart.js) — **single file, no external network at view time**, no build step.
- Entry: `scripts/curve_run.py --html` writes `data/reports/curve_latest.html`.
- Strictly read-only on data; deterministic; no paid data; no live calls required to render.

## Acceptance (for Claude, later)
- Renders from a saved trajectory JSON with zero network access.
- Central/p50 lines match the JSON exactly; event markers align to the overlay months.
- Honesty disclaimers present; sources/confidence shown; estimated dates flagged.
- Degrades gracefully if policy-path providers were unavailable (panel shows "proxy only, low
  confidence" rather than blank/crash).

## Out of scope (later phases)
- Interactive web server / hosting. Multi-day history browser. News crawler. Cross-country panel.
