# TraceYield v2 - UST Curve Impact Forecast

> Draft coding spec for the next architecture pass.
> v2 narrows the product from daily 10Y noise prediction to a 3m/6m UST curve
> impact forecast. The system can still run daily, but the forecast object is
> staged around macro repricing cycles, not daily fluctuations.

---

## 1. Product Goal

TraceYield should answer one practical question:

```text
Over the next 3 to 6 months, what is the most likely UST curve impact, why,
and what would change the call?
```

The forecast should focus on the U.S. Treasury curve. China and Japan linkage
can appear as a light read-through section, but they are not separate forecast
targets in this phase.

### Primary Output

- UST curve call:
  - `BULL_STEEPENING`
  - `BULL_FLATTENING`
  - `BEAR_STEEPENING`
  - `BEAR_FLATTENING`
  - `RANGE_BOUND`
  - `MIXED_CONFLICT`
- Main impacted tenors: `2Y`, `5Y`, `10Y`, `30Y`
- Primary driver attribution
- 3m and 6m base-case forecast
- Light 1m tactical context and 12m structural context
- Key triggers that would invalidate or strengthen the call

---

## 2. Scope Change From v1

### Do Less

- Do not optimize for daily yield fluctuations.
- Do not treat 1w/daily direction as a core product.
- Do not make news NLP a primary factor.
- Do not forecast China or Japan curves independently yet.

### Do More

- Forecast curve shape, not only 10Y direction.
- Separate front-end, belly, and long-end drivers.
- Distinguish expected policy path from term premium.
- Focus on 3m/6m where macro signal is useful and daily noise is lower.
- Keep every call interpretable through signed factor contributions.

---

## 3. Forecast Horizons

v2 keeps four named stages, but only two are primary.

| Stage | Role | Product Weight |
|---|---|---|
| `1m_tactical` | Near-term event and positioning context | Secondary |
| `3m_core` | Primary forecast window: policy/data repricing | Primary |
| `6m_core` | Primary forecast window: regime and term-premium transition | Primary |
| `12m_structural` | Long-run anchor and risk scenario | Secondary |

The report should lead with `3m_core` and `6m_core`.

`1m_tactical` is used to explain near-term noise, event risk, and entry timing.
`12m_structural` is used to anchor fair value and long-end risk, not to pretend
we can make a precise one-year point forecast.

---

## 4. Core Factor Taxonomy

Replace the current macro-label factor set with rate-market driver blocks.

### 4.1 `policy_path`

**Question:** Is the market repricing the Fed path?

Inputs:
- Fed funds target and effective fed funds rate
- SOFR / fed funds futures when available
- FOMC statement, minutes, speeches
- SEP / dot plot when available
- 2Y yield and near-term forward rates as market-implied policy proxies

Curve impact:
- Hawkish repricing: `2Y` and `5Y` sell off most, usually `BEAR_FLATTENING`
- Dovish repricing: `2Y` and `5Y` rally most, usually `BULL_STEEPENING`

### 4.2 `macro_surprise`

**Question:** Are data releases changing the market's expected policy/growth path?

Inputs:
- CPI and Core CPI surprise
- PCE and Core PCE surprise
- Nonfarm payrolls and unemployment surprise
- Wage growth surprise
- ISM / PMI surprise
- Retail sales and claims surprise

Important distinction:

```text
Inflation level matters less at short horizons than surprise versus consensus.
```

Curve impact:
- Hot inflation/labor surprise: front-end and belly sell off
- Soft inflation/labor surprise: front-end and belly rally
- Persistent upside surprises can migrate into long-end term premium

### 4.3 `liquidity_supply`

**Question:** Is Treasury market supply or balance-sheet liquidity pressuring duration?

Inputs:
- QT pace / Fed balance sheet
- Reserve balances
- RRP usage
- Treasury issuance and refunding composition
- Auction tails / bid-to-cover when available
- Dealer balance-sheet constraints when available

Curve impact:
- Supply/liquidity pressure: `10Y`/`30Y` underperform, `BEAR_STEEPENING`
- Liquidity relief or strong demand: long-end support, flatter or bullish curve

### 4.4 `term_premium`

**Question:** Is the long end demanding more or less risk compensation?

Inputs:
- ACM / NY Fed term premium estimates
- Real yields
- Breakevens
- Long-forward rates
- Fiscal deficit / debt supply proxies
- Rates volatility / uncertainty

Curve impact:
- Higher term premium: `10Y`/`30Y` sell off, `BEAR_STEEPENING`
- Lower term premium: long-end rally, often `BULL_FLATTENING`

### 4.5 `growth_risk`

**Question:** Is the market pricing a growth slowdown or recession risk?

Inputs:
- Claims trend
- Unemployment trend
- ISM / PMI level and direction
- Credit spreads
- Yield curve recession proxies
- Equity drawdown context

Curve impact:
- Growth scare: Fed cuts priced, front-end rallies, usually `BULL_STEEPENING`
- Growth resilience: policy stays restrictive, belly/long-end can sell off

### 4.6 `global_relative_value`

**Question:** Are global bond markets making UST duration more or less attractive?

Inputs:
- UST vs JGB yield spreads
- UST vs Bund yield spreads
- UST vs CGB yield spreads
- FX-hedged yield when available
- USD, JPY, CNH context
- Foreign official and reserve-flow proxies when available

Curve impact:
- UST cheapens versus global peers: more foreign demand potential, long-end support
- JGB/Bund yields rise sharply: global duration repricing, long-end UST pressure

### 4.7 `positioning_momentum`

**Question:** Is market positioning or trend likely to amplify the move?

Inputs:
- 2Y/5Y/10Y/30Y momentum
- 2s10s and 5s30s curve momentum
- MOVE index
- CFTC Treasury futures positioning when available
- ETF/fund flow proxies when available

Curve impact:
- Trend confirmation increases confidence
- Crowded positioning reduces confidence or raises reversal risk

### 4.8 `risk_off_overlay`

**Question:** Is there a shock/risk-off regime that overrides normal macro signals?

Inputs:
- VIX
- Credit spreads
- Dollar stress
- Geopolitical shock flag

Usage:
- This is an overlay, not a core predictor.
- It should adjust confidence, trigger language, and scenario balance.
- It should not dominate the base case unless stress is extreme.

---

## 5. Recommended Horizon Weights

These are starting priors. They must be tuned by walk-forward backtest before
being treated as signal evidence.

| Factor | 1m Tactical | 3m Core | 6m Core | 12m Structural |
|---|---:|---:|---:|---:|
| `policy_path` | 25% | 23% | 18% | 12% |
| `macro_surprise` | 22% | 22% | 20% | 15% |
| `liquidity_supply` | 22% | 17% | 12% | 8% |
| `term_premium` | 8% | 14% | 22% | 28% |
| `growth_risk` | 8% | 10% | 12% | 12% |
| `global_relative_value` | 5% | 7% | 10% | 15% |
| `positioning_momentum` | 8% | 5% | 4% | 3% |
| `risk_off_overlay` | 2% | 2% | 2% | 7% |

Interpretation:

- `1m_tactical`: event risk, liquidity, and market pricing.
- `3m_core`: policy path and macro surprise trend.
- `6m_core`: macro regime and term-premium transition.
- `12m_structural`: term premium, fiscal/supply, global relative value.

---

## 6. UST Curve Impact Logic

The model must translate factor scores into tenor-level pressure.

### Driver To Curve Mapping

| Driver | 2Y | 5Y | 10Y | 30Y | Typical Curve Call |
|---|---:|---:|---:|---:|---|
| Hawkish policy repricing | ++ | ++ | + | 0/+ | `BEAR_FLATTENING` |
| Dovish policy repricing | -- | -- | - | 0/- | `BULL_STEEPENING` |
| Hot macro surprise | ++ | ++ | + | 0/+ | `BEAR_FLATTENING` or parallel bear |
| Soft macro surprise | -- | -- | - | 0/- | `BULL_STEEPENING` |
| Liquidity/supply pressure | 0/+ | + | ++ | ++ | `BEAR_STEEPENING` |
| Higher term premium | 0 | + | ++ | ++ | `BEAR_STEEPENING` |
| Growth scare | -- | -- | - | - | `BULL_STEEPENING` or `BULL_FLATTENING` |
| Risk-off duration bid | - | - | -- | -- | `BULL_FLATTENING` |

Signs mean yield pressure:

```text
++ strong yield-up pressure
+  mild yield-up pressure
0   neutral
-   mild yield-down pressure
--  strong yield-down pressure
```

### Required Curve Outputs

For each of `3m_core` and `6m_core`, output:

- `curve_call`
- `tenor_pressure`: dict for `2Y`, `5Y`, `10Y`, `30Y`
- `main_driver`
- `secondary_driver`
- `confidence`
- `rationale`
- `triggers`

---

## 7. Data Priorities

### Phase A - Use What We Already Have

Use currently available FRED/cached data first:

- Treasury yields: `DGS2`, `DGS5`, `DGS10`, `DGS20`, `DGS30`
- Curve spreads: `T10Y2Y`, computed `5s30s`
- Inflation: `PCEPILFE`, `CPIAUCSL`, `T10YIE`, `T5YIE`, `T5YIFR`
- Liquidity: `WALCL`, `WRESBAL`, `RRPONTSYD`, `WTREGEN`
- Policy: `DFEDTARU`, `EFFR`, `SOFR`
- Global: Germany/Japan long yields currently in config
- Risk: `VIXCLS`, USD index

### Phase B - Add High-Value Missing Inputs

Prioritize these before news NLP:

1. Macro consensus/surprise source for CPI, NFP, PCE, ISM.
2. Term premium series from NY Fed / ACM-style data.
3. Treasury refunding / issuance schedule and auction metrics.
4. MOVE index or rates-vol proxy.
5. Fed funds/SOFR futures or market-implied policy path.

---

## 8. Proposed Code Architecture

Keep v1's interpretability pattern, but replace the factor layer and output schema.

```text
src/
  signals/
    policy_path.py
    macro_surprise.py
    liquidity_supply.py
    term_premium.py
    growth_risk.py
    global_relative_value.py
    positioning_momentum.py
    risk_off_overlay.py
    curve_impact.py
  models/
    curve_engine.py
  report/
    render_curve.py
configs/
  curve_factors.yaml
  curve_weights.yaml
  curve_rules.yaml
scripts/
  curve_run.py
```

### `signals/*`

Each signal module returns a bounded score:

```python
score in [-1, +1]
positive = upward yield pressure
negative = downward yield pressure
```

Each signal also returns:

```python
{
    "score": float,
    "components": dict,
    "rationale": str,
    "asof": date,
}
```

### `signals/curve_impact.py`

Converts driver scores into tenor-level pressures:

```python
{
    "2Y": float,
    "5Y": float,
    "10Y": float,
    "30Y": float,
}
```

### `models/curve_engine.py`

Produces staged forecasts:

```python
@dataclass
class CurveForecast:
    horizon: str                 # 1m_tactical, 3m_core, 6m_core, 12m_structural
    curve_call: str              # BEAR_STEEPENING, etc.
    tenor_pressure: dict         # 2Y/5Y/10Y/30Y signed scores
    factor_scores: dict
    contributions: dict
    main_driver: str
    secondary_driver: str
    confidence: float
    rationale: str
    triggers: list[str]
    linkage_note: str
```

### `report/render_curve.py`

The report should lead with:

1. 3m UST curve call
2. 6m UST curve call
3. Driver attribution
4. Tenor pressure table
5. Triggers
6. Light China/Japan linkage note

---

## 9. Report Shape

The generated curve report should look like this:

```text
UST Curve Impact Forecast

Core View
  3m: [curve_call] - [main_driver]
  6m: [curve_call] - [main_driver]

Tenor Pressure
  2Y:  ...
  5Y:  ...
  10Y: ...
  30Y: ...

Driver Attribution
  policy_path
  macro_surprise
  liquidity_supply
  term_premium
  growth_risk
  global_relative_value
  positioning_momentum
  risk_off_overlay

Key Triggers
  - CPI surprise threshold
  - 2Y/10Y level breakout
  - auction/supply stress
  - Fed pricing shift

Light Cross-Market Linkage
  JGB: brief read-through from UST long-end and global duration repricing.
  CGB: brief read-through through USD/CNH, global duration risk, and China easing room.
```

---

## 10. Validation Gates

Before v2 is considered useful:

1. `3m_core` and `6m_core` forecasts must backtest against realized curve moves.
2. Backtest should evaluate:
   - 2Y direction
   - 5Y direction
   - 10Y direction
   - 30Y direction
   - 2s10s steepen/flatten
   - 5s30s steepen/flatten
3. Every forecast must show signed factor contributions.
4. No factor may use data unavailable as of the forecast date.
5. Missing optional data must degrade gracefully to neutral.

Useful metrics:

- IC between tenor pressure and realized yield change
- Directional accuracy by tenor
- Curve-shape hit rate
- Coverage and hit rate at confidence thresholds
- Driver attribution sanity checks on known episodes

Known episodes to sanity-check:

- 2020 COVID risk-off / policy floor
- 2021-2022 inflation repricing
- 2023 Treasury term-premium / supply selloff
- 2024-2025 disinflation and Fed-path repricing

---

## 11. Research Anchors

The architecture is based on the following research conclusions:

- Treasury yields decompose into expected short rates and term premium.
  - NY Fed: Treasury Term Premia, 1961-Present
    https://libertystreeteconomics.newyorkfed.org/2014/05/treasury-term-premia-1961-present.html
  - Fed: Three-Factor Nominal Term Structure Model
    https://www.federalreserve.gov/data/three-factor-nominal-term-structure-model.htm
- Macro news matters most as surprise versus expectation, not as raw level.
  - Fed FEDS: Low Frequency Effects of Macroeconomic News on Government Bond Yields
    https://www.federalreserve.gov/econres/feds/low-frequency-effects-of-macroeconomic-news-on-government-bond-yields.htm
  - Fed FEDS: Macroeconomic News Announcements, Volatility and Jumps
    https://www.federalreserve.gov/econres/feds/macroeconomic-news-announcements-systemic-risk-financial-market-volatility-and-jumps.htm
  - Fed FEDS: How Markets Process Macro News
    https://www.federalreserve.gov/econres/feds/how-markets-process-macro-news-the-importance-of-investor-attention.htm
- Long-end selloffs can be driven by term premium, QT, issuance, and uncertainty.
  - Fed FEDS Notes: The Treasury Tantrum of 2023
    https://www.federalreserve.gov/econres/notes/feds-notes/the-treasury-tantrum-of-2023-20240903.html
- VIX and rates volatility should not be treated identically.
  - BIS: Market volatility, monetary policy and the term premium
    https://www.bis.org/publ/work606.htm
- Foreign yield spillovers matter mainly through long-end and term-premium channels.
  - Fed: International Yield Spillovers
    https://www.federalreserve.gov/econres/feds/international-yield-spillovers.htm
  - BIS: Channels of US monetary policy spillovers to international bond markets
    https://www.bis.org/publ/work719.htm

---

## 12. Implementation Order

Recommended coding sequence:

1. Freeze v2 schema in dataclasses.
2. Add `curve_weights.yaml` and `curve_rules.yaml`.
3. Build `curve_impact.py` driver-to-tenor mapping.
4. Refactor existing factors into the new driver taxonomy using current data.
5. Add `curve_engine.py` for 1m/3m/6m/12m staged outputs.
6. Render a curve-focused markdown report.
7. Add backtest for 3m/6m tenor and curve-shape accuracy.
8. Add missing high-value data sources one at a time.

The first coding milestone should be a working 3m/6m UST curve report using
only existing cached/FRED data. That keeps scope controlled while moving the
product toward the right conceptual target.
