# UST Curve Impact Forecast - 2026-05-31

## Headline 10Y Direction

10Y view is reconstructed from the front-end policy view plus the 2s10s curve view; it is not an isolated 10Y outright-level forecast.

| Horizon | 10Y call | Front-end 2Y | 2s10s curve | Reconstructed 10Y | Pure term-premium residual |
|---|---|---:|---:|---:|---:|
| 3m_core | Neutral | + (+0.11) | 0 (-0.05) | 0 (+0.06) | context-only / low-confidence 0 (-0.03) |
| 6m_core | Neutral | + (+0.10) | 0 (-0.04) | 0 (+0.05) | context-only / low-confidence 0 (-0.05) |

## Core View

- **3m_core:** `BEAR_FLATTENING` - policy_path (confidence 57%)
- **6m_core:** `BEAR_FLATTENING` - policy_path (confidence 56%)

## Tenor Pressure

| Horizon | 2Y policy | 5Y bridge | 2s10s curve | 10Y reconstructed |
|---|---:|---:|---:|---:|
| 1m_tactical | + (+0.12) | + (+0.11) | 0 (-0.05) | 0 (+0.07) |
| 3m_core | + (+0.11) | + (+0.10) | 0 (-0.05) | 0 (+0.06) |
| 6m_core | + (+0.10) | + (+0.08) | 0 (-0.04) | 0 (+0.05) |
| 12m_structural | 0 (+0.08) | 0 (+0.07) | 0 (-0.03) | 0 (+0.05) |

## Context-only long end

30Y and pure long-end / term-premium factors are retained as context, not as core trade drivers.

| Horizon | 30Y context | Term-premium residual | Long-end context drivers |
|---|---:|---:|---|
| 1m_tactical | 0 (-0.07) | 0 (-0.02) | `liquidity_supply` -0.056, `term_premium` -0.017, `global_relative_value` +0.003 |
| 3m_core | 0 (-0.07) | 0 (-0.03) | `liquidity_supply` -0.043, `term_premium` -0.030, `global_relative_value` +0.005 |
| 6m_core | 0 (-0.07) | 0 (-0.05) | `term_premium` -0.047, `liquidity_supply` -0.030, `global_relative_value` +0.007 |
| 12m_structural | 0 (-0.07) | 0 (-0.06) | `term_premium` -0.060, `liquidity_supply` -0.020, `global_relative_value` +0.010 |

## Driver Attribution

Core drivers:
- `policy_path` raw=+0.566, contrib=+0.130
- `macro_surprise` raw=-0.354, contrib=-0.078
- `growth_risk` raw=+0.506, contrib=+0.051
- `positioning_momentum` raw=+0.305, contrib=+0.015
- `risk_off_overlay` raw=-0.000, contrib=-0.000

Context-only drivers:
- `liquidity_supply` raw=-0.254, contrib=-0.043
- `term_premium` raw=-0.213, contrib=-0.030
- `global_relative_value` raw=+0.066, contrib=+0.005

## Key Triggers

- 2Y reprices sharply after FOMC, payrolls, or CPI.
- 10Y closes above its recent range with 2Y and 2s10s confirmation.
- 3m and 6m core calls diverge, signalling mixed/conflict state.

## Rationale

3m_core maps to BEAR_FLATTENING: policy_path is the largest driver (upward yield pressure, raw score +0.57), with macro_surprise as the second driver (downward pressure). Context-only long-end drivers excluded from the core call: global_relative_value, liquidity_supply, term_premium.

## Light Cross-Market Linkage

JGB read-through is mainly long-end/global-duration. CGB read-through is light and works through USD/CNH, global duration risk, and China easing room.

*Positive pressure = yield-up pressure. Negative pressure = yield-down pressure.*