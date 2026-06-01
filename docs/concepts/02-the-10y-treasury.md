# 2 · The 10-Year Treasury Yield (UST 10Y)

## What a Treasury is
A **US Treasury** is a loan you make to the US government. You pay $100 now, it
pays you interest (a "coupon") and returns the $100 at maturity. Maturities:
- **Bills** = ≤1 year, **Notes** = 2–10 years, **Bonds** = 20–30 years.

Treasuries are considered **"risk-free"** — the US has never failed to pay in USD
(it can print dollars). So their yield is the **baseline return** against which
*every other investment on Earth* is measured.

## Price vs Yield — the one thing you MUST internalize
**Bond price and yield move in OPPOSITE directions.**

- If you own a bond paying 4% and new bonds start paying 5%, nobody wants your 4%
  bond → its **price falls** until its effective yield matches 5%.
- So: **yields up = bond prices down = "bond bear market."**
-       **yields down = bond prices up = "bond bull market."**

This is why our output says "Bear bonds" when we predict yields rising. Get this
backwards and everything else inverts.

> **Bull bonds = yields ↓ = prices ↑** · **Bear bonds = yields ↑ = prices ↓**

## Why specifically the 10-Year?
Of all maturities, the 10Y is the **single most important interest rate in the
world**, because:
1. **Deepest liquidity** — the most heavily traded, so its price is the cleanest,
   most reliable signal. (That's also why we predict *it* and not, say, the 7Y.)
2. **It's the global benchmark** — 30-year mortgages, corporate bond yields,
   discount rates for stocks, and sovereign debt worldwide are all priced as
   "10Y + a spread."
3. **It's the market's verdict on the future** — long enough to embed expectations
   about years of Fed policy, inflation, and growth; short enough to stay liquid.

## What actually determines the 10Y yield
The 10Y is NOT set by the Fed directly. The Fed sets the *overnight* rate; the
market sets the 10Y. You can decompose it:

```
10Y yield  ≈   average expected short-term rate over 10 years   (← the Fed path)
             + term premium                                       (← risk/supply)
```
Broken into the drivers we model:
| Driver | Pushes 10Y... | Our factor |
|--------|---------------|------------|
| Expected Fed path (hawkish) | **Up** | `fomc_nlp` |
| Higher expected inflation | **Up** | `inflation` |
| Less Fed liquidity / more bond supply (QT, deficits) | **Up** | `liquidity` |
| Foreign yields rising / capital leaving US | **Up** | `global_rates` |
| Safe-haven demand (fear, war, recession scare) | **Down** | `political_risk` |

Sum those pressures → net direction. That is literally what
`src/models/predictor.py` does.

## The yield curve (why we track 5Y–20Y, not just 10Y)
Plot yield against maturity (2Y, 5Y, 10Y, 30Y) → the **yield curve**. Its *shape*
tells a story:
- **Normal / steep** (long > short): healthy growth expectations.
- **Flat:** uncertainty / late cycle.
- **Inverted** (short > long, e.g. **2s10s < 0**): the market expects the Fed to
  *cut* rates soon — historically the **most reliable recession warning**.

Key spreads we compute:
- **2s10s** (`DGS10 − DGS2`): the classic recession gauge.
- **5s30s**: shape of the long end; sensitive to inflation & term premium.

A prediction isn't complete without a **curve view** — sometimes the 10Y barely
moves but the *curve steepens/flattens*, and that's the real trade.

## How yields are quoted
- In **percent**, to 2 decimals (e.g. 4.41%). A **basis point (bp) = 0.01%**.
  "The 10Y rose 12 bps" = +0.12%.
- **DV01** = dollar P&L change per 1bp move — how you size a bond position's risk.

## Next
→ [03-chain-reaction.md](03-chain-reaction.md): when the 10Y moves, the whole
world repositions.
