# 3 · The Chain Reaction (cross-asset transmission)

The 10Y is the **"risk-free rate"** in every valuation model on Earth. Move it,
and you re-price everything. This is why a yield-prediction edge is so valuable —
it's upstream of nearly all other markets. Here's how the dominoes fall when the
**10Y yield RISES** (reverse every arrow for a fall).

## The master diagram
```
                  ┌──────────────────────────┐
                  │  FOMC: hawkish / QT /     │
                  │  hot inflation print      │
                  └────────────┬─────────────┘
                               ▼
                  ┌──────────────────────────┐
                  │   10Y Treasury yield ↑    │  ← the hinge
                  └────────────┬─────────────┘
        ┌──────────────┬───────┼────────┬───────────────┐
        ▼              ▼       ▼        ▼               ▼
   USD ↑ (DXY)   Stocks ↓   Gold ↓   Credit ↓     EM/Asia stress
   higher yield  higher     no-yield  spreads      capital flees
   attracts      discount   asset     widen,       to USD, their
   capital       rate hurts loses     borrowing    currencies &
                 growth/    appeal vs costs rise    bonds fall
                 tech most  bonds
```

## Asset by asset (when 10Y rises)
| Asset | Direction | Mechanism |
|-------|-----------|-----------|
| **US Dollar (DXY)** | **↑** | Higher US yields pull global capital into USD assets |
| **Equities (esp. tech/growth)** | **↓** | Stocks are valued by discounting future earnings; a higher discount rate cuts present value. Long-duration "growth" names hurt most |
| **Gold** | **↓** (usually) | Gold pays no yield; when bonds pay more, gold's opportunity cost rises. (Breaks down when the *reason* is inflation/fear) |
| **Corporate credit** | **↓ (spreads widen)** | Borrowing costs rise; refinancing risk up; high-yield hit hardest |
| **Mortgages / housing** | **↓** | 30Y mortgage ≈ 10Y + spread; higher rates kill affordability |
| **Commodities (oil, copper)** | **mixed/↓** | Stronger USD prices them down; but demand/supply can dominate |
| **Emerging markets** | **↓↓** | Capital flees to USD; their currencies fall, $-debt gets costlier — the classic "taper tantrum" |

## The global rates web (why we track Germany & Japan)
The US doesn't move alone. Yields are linked across borders by capital flows:
- **US–Germany (Bund) spread** and **US–Japan (JGB) spread** drive the **USD** and
  global bond flows. If US yields rise far above Europe/Japan, money flows *to* the
  US, lifting the dollar.
- **Japan is special:** decades of ultra-low rates made JGBs an anchor; shifts in
  Bank of Japan policy ripple into US Treasuries (Japanese investors are huge
  holders of USTs).
- **China & Asia:** PBOC policy, the CNY, and Asian demand for Treasuries feed back
  into US yields and commodity demand.
This is the `global_rates` factor (15%) — and the reason the project's ambition is
"overall impact across Asia, Europe, commodities, equities," not just one number.

## The crucial nuance: WHY yields move changes the reaction
The same yield move means opposite things depending on cause:
- **"Good" rise** (strong growth) → stocks can shrug it off, cyclicals rise.
- **"Bad" rise** (inflation fear / supply glut / fiscal worry) → stocks AND bonds
  fall together (the 2022 nightmare), gold can *rise* on inflation hedging.
- **Fall on dovish Fed** (soft landing) → everything rallies ("risk-on").
- **Fall on recession fear** (flight to safety) → bonds up, stocks down, gold up.

> This is why the NLP rationale matters: a number alone ("yields +10bp") is
> useless without the *narrative*. Our system must output the *driver*, not just
> the direction — that's what makes the cross-asset map trustworthy.

## Where this lives in the project
The future **cross-asset impact map** output takes the predicted 10Y move + its
dominant driver, and projects directional impacts on the table above. v1 uses the
historical beta of each asset to 10Y moves (conditioned on the driver regime).

## Next
→ [04-glossary.md](04-glossary.md): every term in one place.
