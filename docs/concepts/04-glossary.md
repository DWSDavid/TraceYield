# 4 · Glossary

Quick reference. Bookmark this; the macro-tutor agent can expand any entry.

## Rates & bonds
- **Yield** — the annual return on a bond. Moves *opposite* to price.
- **Basis point (bp)** — 0.01%. "25 bps" = 0.25%, the Fed's usual move size.
- **Coupon** — the fixed interest a bond pays.
- **Term premium** — extra yield demanded for holding longer-maturity bonds
  (compensation for rate/inflation uncertainty + supply).
- **DV01** — dollar P&L per 1bp yield move; a position's rate risk.
- **Duration** — sensitivity of a bond's price to yield changes (years-ish).
- **Bull bonds** — yields ↓, prices ↑. **Bear bonds** — yields ↑, prices ↓.

## The curve
- **Yield curve** — yields plotted across maturities (2Y…30Y).
- **2s10s** — 10Y minus 2Y yield. Negative = **inverted** = recession signal.
- **5s30s** — 30Y minus 5Y; shape of the long end.
- **Steepening** — long yields rise faster than short (or short fall faster).
- **Flattening / Inversion** — short approaches/exceeds long.

## The Fed
- **FOMC** — Federal Open Market Committee; sets US rates, meets 8×/yr.
- **Fed funds rate** — the overnight target rate the Fed sets directly.
- **Hawkish** — leaning toward tighter policy / higher rates (yields ↑).
- **Dovish** — leaning toward easier policy / lower rates (yields ↓).
- **Dot plot / SEP** — quarterly chart of officials' projected rate path.
- **Forward guidance** — communicating the likely future path to shape expectations.
- **Minutes** — detailed record of an FOMC meeting, released 3 weeks later.

## Liquidity / plumbing
- **QE** — Quantitative Easing; Fed buys bonds, adds liquidity (yields ↓).
- **QT** — Quantitative Tightening; Fed shrinks balance sheet (yields ↑ pressure).
- **Bank reserves** — money banks park at the Fed; a gauge of system liquidity.
- **RRP (reverse repo)** — where excess cash parks overnight at the Fed; a
  liquidity buffer. Falling RRP can signal tightening conditions.
- **TGA** — Treasury General Account; the government's checking account at the Fed.
- **SOFR** — Secured Overnight Financing Rate; the main overnight benchmark.

## Inflation
- **CPI** — Consumer Price Index; the headline inflation number.
- **Core PCE** — the Fed's *preferred* inflation gauge (ex food & energy); 2% target.
- **Breakeven inflation** — market-implied inflation (nominal yield − TIPS yield).
- **5y5y forward** — expected inflation 5 years out, for 5 years; a key anchor.
- **Disinflation** — inflation slowing (still positive). **Deflation** — prices falling.

## Markets
- **DXY** — US Dollar Index (USD vs a basket of currencies).
- **TLT** — popular ETF of long-dated Treasuries; a way to trade the bond view.
- **VIX** — equity volatility ("fear") index.
- **Credit spread** — extra yield of corporate over Treasury bonds; widens in stress.
- **Risk-on / Risk-off** — markets buying risky assets / fleeing to safety.
- **Taper tantrum** — 2013 episode: hint of less Fed support spiked yields, hit EM.

## Global
- **Bund** — German government bond (Europe's benchmark).
- **JGB** — Japanese Government Bond.
- **BOJ / ECB / PBOC** — central banks of Japan / Eurozone / China.
- **Rate differential** — gap between two countries' yields; drives FX flows.

## Project terms
- **Factor** — one of our 5 weighted inputs (fomc_nlp, inflation, liquidity,
  global_rates, political_risk).
- **Hawkish score** — NLP output in [-1, +1]; our quantified Fed tone.
- **Horizon** — prediction window: 1w / 1m / 3m.
- **Walk-forward backtest** — testing predictions on history with no look-ahead.
- **Hit rate** — % of direction calls that were correct.
