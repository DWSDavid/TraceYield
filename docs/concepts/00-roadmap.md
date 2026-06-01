# TraceYield — Concept Roadmap (read in this order)

You're building a system that predicts US Treasury yields. To do that well you
have to actually understand the machine you're predicting. This folder is the
plain-English curriculum. Read top to bottom; each builds on the last.

| # | File | The one question it answers |
|---|------|------------------------------|
| 1 | [01-fomc-and-the-fed.md](01-fomc-and-the-fed.md) | Who sets US interest rates, and how? |
| 2 | [02-the-10y-treasury.md](02-the-10y-treasury.md) | What is the 10Y yield and why is it the most important number in finance? |
| 3 | [03-chain-reaction.md](03-chain-reaction.md) | When the Fed/10Y moves, what dominoes fall across the world? |
| 4 | [04-glossary.md](04-glossary.md) | Every term (QT, RRP, breakevens, 2s10s, DV01...) in one place |
| ★ | [05-core-logic.md](05-core-logic.md) | **核心因果链总梳理(中文+双语)** — yield↔price、通胀/美联储/流动性怎么推动利率、为什么老是 Neutral。**蒙了就先看这篇** |

## The 30-second mental model
1. The **Fed** (via the **FOMC**) sets the *overnight* interest rate and controls
   the supply of money/liquidity.
2. That anchors the **short end** of the curve. The **10Y Treasury yield** is set
   by the *market* and reflects expectations of future Fed policy + inflation +
   growth + supply/demand for safe assets.
3. The **10Y is the world's risk-free benchmark.** Mortgages, corporate bonds,
   stock valuations, EM currencies, gold — all price *off* it.
4. So: **predict the Fed + inflation + liquidity → predict the 10Y → predict
   almost everything else.** That's the whole thesis of this project.

## How the docs map to the code
- FOMC tone → `src/nlp/` (keyword + LLM scorers)
- Inflation, liquidity, global rates → `src/signals/factors.py` + `configs/fred_series.yaml`
- The blend that turns it into a call → `src/models/predictor.py`
- The chain reaction → the future **cross-asset impact map** output

## How to learn fastest here
Spin up the **macro-tutor** subagent (`.claude/agents/macro-tutor.md`). Ask it
anything — "explain 2s10s like I'm 12", "why did the Fed cut in 2024", "walk me
through what happens to gold if the 10Y spikes". It can pull recent data live.
