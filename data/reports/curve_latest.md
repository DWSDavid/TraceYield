# UST Curve Impact Forecast - 2028-01-01

## Headline 10Y Direction

10Y view is reconstructed from the front-end policy view plus the 2s10s curve view; it is not an isolated 10Y outright-level forecast.

| Horizon | 10Y call | Front-end 2Y | 2s10s curve | Reconstructed 10Y | Pure term-premium residual |
|---|---|---:|---:|---:|---:|
| 3m_core | Neutral | + (+0.14) | 0 (-0.06) | 0 (+0.07) | context-only / low-confidence 0 (-0.03) |
| 6m_core | Neutral | + (+0.13) | 0 (-0.06) | 0 (+0.07) | context-only / low-confidence 0 (-0.05) |

## Core View

- **3m_core:** `BEAR_FLATTENING` - policy_path (confidence 58%)
- **6m_core:** `BEAR_FLATTENING` - policy_path (confidence 57%)

## Tenor Pressure

| Horizon | 2Y policy | 5Y bridge | 2s10s curve | 10Y reconstructed |
|---|---:|---:|---:|---:|
| 1m_tactical | + (+0.14) | + (+0.12) | 0 (-0.06) | 0 (+0.08) |
| 3m_core | + (+0.14) | + (+0.12) | 0 (-0.06) | 0 (+0.07) |
| 6m_core | + (+0.13) | + (+0.11) | 0 (-0.06) | 0 (+0.07) |
| 12m_structural | + (+0.11) | + (+0.09) | 0 (-0.05) | 0 (+0.06) |

## Context-only long end

30Y and pure long-end / term-premium factors are retained as context, not as core trade drivers.

| Horizon | 30Y context | Term-premium residual | Long-end context drivers |
|---|---:|---:|---|
| 1m_tactical | - (-0.10) | 0 (-0.02) | `liquidity_supply` -0.089, `term_premium` -0.017, `global_relative_value` +0.003 |
| 3m_core | - (-0.09) | 0 (-0.03) | `liquidity_supply` -0.069, `term_premium` -0.030, `global_relative_value` +0.005 |
| 6m_core | - (-0.09) | 0 (-0.05) | `liquidity_supply` -0.049, `term_premium` -0.047, `global_relative_value` +0.007 |
| 12m_structural | - (-0.08) | 0 (-0.06) | `term_premium` -0.060, `liquidity_supply` -0.033, `global_relative_value` +0.010 |

## Driver Attribution

Core drivers:
- `policy_path` raw=+0.566, contrib=+0.130
- `growth_risk` raw=+0.784, contrib=+0.078
- `macro_surprise` raw=-0.354, contrib=-0.078
- `positioning_momentum` raw=+0.288, contrib=+0.014
- `risk_off_overlay` raw=-0.000, contrib=-0.000

Context-only drivers:
- `liquidity_supply` raw=-0.406, contrib=-0.069
- `term_premium` raw=-0.213, contrib=-0.030
- `global_relative_value` raw=+0.066, contrib=+0.005

## Key Triggers

- 2Y reprices sharply after FOMC, payrolls, or CPI.
- 10Y closes above its recent range with 2Y and 2s10s confirmation.
- 3m and 6m core calls diverge, signalling mixed/conflict state.

## Rationale

3m_core maps to BEAR_FLATTENING: policy_path is the largest driver (upward yield pressure, raw score +0.57), with growth_risk as the second driver (upward pressure). Context-only long-end drivers excluded from the core call: global_relative_value, liquidity_supply, term_premium.

## Light Cross-Market Linkage

JGB read-through is mainly long-end/global-duration. CGB read-through is light and works through USD/CNH, global duration risk, and China easing room.

*Positive pressure = yield-up pressure. Negative pressure = yield-down pressure.*