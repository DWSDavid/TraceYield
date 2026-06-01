# 1 · The Fed and the FOMC

## What the Federal Reserve is
The **Federal Reserve ("the Fed")** is the central bank of the United States.
Its job, set by Congress, is a **dual mandate**:
1. **Maximum employment** (low unemployment)
2. **Price stability** (low, stable inflation — target: **2%** core PCE)

It pursues these mainly by controlling **the price of money** (interest rates)
and **the quantity of money** (liquidity / its balance sheet).

## The FOMC — who actually decides
The **Federal Open Market Committee (FOMC)** is the Fed's rate-setting body.
- **12 voting members:** the 7 Fed Governors (in DC) + the NY Fed president
  (always votes) + 4 of the other 11 regional Fed presidents (rotating).
- Chaired by the **Fed Chair** (the single most market-moving person in finance).
- Meets **8 times a year** (~every 6 weeks). Each meeting they decide whether to
  raise, hold, or cut the **federal funds rate**.

### Why the FOMC matters so much
They don't just set today's rate — they set **expectations** for the *path* of
rates. Markets price months/years ahead, so a hint about *future* policy moves
the 10Y more than the actual rate change does. This is why **Fed communication
is the #1 input in this project (30% weight).**

## The tools the Fed uses
| Tool | What it does | Effect on yields |
|------|--------------|------------------|
| **Fed funds rate** | Target for overnight bank lending | Anchors the short end |
| **Hiking** | Raise the rate to cool inflation | Yields ↑ (esp. short end) |
| **Cutting** | Lower the rate to support growth/jobs | Yields ↓ |
| **QE** (Quantitative Easing) | Fed *buys* bonds → adds liquidity | Yields ↓ |
| **QT** (Quantitative Tightening) | Fed *lets bonds roll off* → drains liquidity | Yields ↑ (upward pressure) |
| **Forward guidance** | Telling markets the likely path | Moves expectations directly |

> **Hawkish vs Dovish** — the two words you'll use constantly:
> - **Hawkish** 🦅 = worried about inflation → favors *higher* rates / tighter policy → **yields up**.
> - **Dovish** 🕊️ = worried about growth/jobs → favors *lower* rates / easier policy → **yields down**.
> Our NLP scorer outputs exactly this, as a number in [-1 dovish, +1 hawkish].

## The documents we actually parse (the inputs)
Every one of these is a tradable signal. Released on a known calendar:
1. **FOMC Statement** — released at 2:00pm ET on decision day. Short, every word
   scrutinized. Changes vs the prior statement matter enormously.
2. **The "Dot Plot" (SEP)** — quarterly; each official's projection of where rates
   go. A visual of the committee's expected path.
3. **Press conference** — the Chair takes questions 30 min after the statement.
   Often moves markets *more* than the statement.
4. **Meeting Minutes** — released **3 weeks later**. The detailed debate. Reveals
   how united/divided the committee is.
5. **Speeches** — individual officials between meetings. We weight these by the
   speaker's rank (Chair > Vice Chair > voting presidents > non-voters).

## Liquidity & the balance sheet (the 20% factor)
Beyond the rate, the Fed controls **how much money is sloshing around**:
- **QT** is currently shrinking the balance sheet (~$1.8T+ drained over the cycle).
- **Bank reserves** (`WRESBAL`) and the **reverse-repo (RRP)** balance tell you how
  much spare liquidity exists. When reserves get "scarce," funding stress can spike
  yields. This is the plumbing — boring until it isn't.

## The political layer (the 10% factor — and the tricky one)
- **Chair transitions** create two-sided risk: a new Chair can reset the whole
  policy tone. (Markets obsess over who the next Chair will be.)
- **Elections, fiscal policy, debt-ceiling fights, geopolitics** all inject a risk
  premium. Treasury *supply* (how much debt the government issues) also pushes
  yields independent of the Fed.
- This factor is the hardest to quantify — handle it as a probability-weighted
  scenario overlay, not a clean number.

## Next
→ [02-the-10y-treasury.md](02-the-10y-treasury.md): what the 10Y yield actually is.
