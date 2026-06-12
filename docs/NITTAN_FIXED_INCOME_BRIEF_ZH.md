# TraceYield 给 Nittan / Fixed Income Desk 的业务说明

## 1. 为什么这个项目适合 inter-dealer broker / fixed income 场景

Nittan Capital 这类 inter-dealer broker 的核心价值，是在 OTC 市场中连接 dealer、银行和机构客户，帮助市场参与者发现价格、寻找流动性、传递跨市场信息。根据 Nittan 官方介绍，其业务覆盖香港、新加坡和韩国，并在亚洲 inter-dealer brokerage 市场中服务金融机构的 OTC 衍生品和金融工具交易。

TraceYield 对这种 fixed income desk 的价值不是“替代交易员判断”，而是把多个市场信息源整理成一套每日可复用的 curve intelligence：

- 快速判断 UST curve 的核心方向和风险区间。
- 把 2Y、5Y、10Y、30Y 的变化拆成政策、通胀、增长、供给、全球利差等驱动。
- 帮助 broker / dealer 在和客户沟通时，更快解释“为什么今天 curve 这样动”。
- 给跨市场 desks 提供统一 reference：UST 对 JGB、Bund、FX、gold、equities、credit 的联动。
- 在事件日前，例如 CPI、NFP、FOMC、QRA，提前标出不确定性和可能触发点。

参考：

- Nittan Capital Company: https://www.nittancap.com/
- Nittan Capital Group: https://www.nittan-capital.com/index_english.html

## 2. 为什么 US Treasury 重要

UST 是全球 fixed income 的核心锚。它的重要性主要来自五点：

1. Risk-free benchmark：UST yield curve 是全球资产定价的基础参考利率。
2. Fed policy transmission：Fed 政策预期最直接地反映在 2Y、5Y 和前端利率。
3. Discount rate：10Y 影响 equity valuation、real estate、corporate borrowing 和 long-duration assets。
4. Global collateral / liquidity：UST 是全球金融体系中最重要的安全资产和抵押品之一。
5. Cross-market signal：UST 变化会传导到 FX、gold、commodities、EM rates、credit spreads 和 global duration。

换句话说，预测 UST 不是只预测一个美国利率数字，而是在读全球资金价格的主轴。

参考：

- Brookings 对 Treasury market 功能的解释: https://www.brookings.edu/articles/whats-going-on-in-the-us-treasury-market-and-why-does-it-matter/
- SIFMA 对 UST benchmark 和全球借贷成本影响的说明: https://www.sifma.org/news/blog/revisiting-us-treasury-market-capacity-and-resiliency-part-i
- FRED DGS10 数据页: https://fred.stlouisfed.org/series/DGS10

## 3. TraceYield 的核心逻辑

TraceYield 的基本流程是：

```text
Raw macro / rates / Fed text
-> point-in-time features
-> macro blocks
-> FADNS curve forecast
-> baseline + macro adjustment + event uncertainty
-> Markdown / HTML report
```

它不是简单预测“10Y 明天涨跌”，而是输出一条 12 个月曲线路径：

- 2Y：更敏感于 Fed path。
- 5Y：连接政策预期和中期增长/通胀。
- 10Y：全球风险资产的关键 benchmark。
- 30Y：更敏感于 term premium、供给、长期 inflation risk。
- 2s10s / 5s30s：用于看 curve steepening / flattening。

当前系统的报告更偏 3m / 6m fixed income decision-support，因为这个时间窗口比日内或 1w 噪音更低，也更适合宏观数据和政策路径发挥作用。

## 4. FADNS 是什么，为什么可以用

FADNS = Factor-Augmented Dynamic Nelson-Siegel。

先拆开看：

- Nelson-Siegel：一种经典 yield curve 模型，把整条曲线压缩为三个直观因子：level、slope、curvature。
- Dynamic Nelson-Siegel：让这三个因子随时间变化，用历史曲线动态预测未来曲线。
- Factor-Augmented：在曲线自身动态之外，加入宏观因子，例如 inflation、policy path、growth、liquidity 和 global relative value。

为什么适合 TraceYield：

1. 它预测的是整条曲线，不只是单点 10Y。
2. level / slope / curvature 对交易员很直观，方便解释。
3. 它能把 2Y、5Y、10Y、30Y 放在同一个结构里，避免每个期限孤立预测。
4. 加入宏观因子后，可以解释“为什么 base curve path 被政策或通胀推离 baseline”。
5. 它比深度学习黑盒更适合固定收益研究场景，因为每个输出仍能拆回可解释 driver。

TraceYield 当前实现方式：

- 用 2Y、5Y、10Y、30Y 拟合 Nelson-Siegel betas。
- 用 ridge transition 预测未来 beta 变化。
- 加入五个 macro blocks 作为 state variables。
- 用历史 forecast errors 生成 p10/p25/p50/p75/p90 fan band。
- 用 macro block IC sanity check 判断哪些 block 是 signal，哪些只是 explanation-only。

参考：

- Diebold and Li, Forecasting the Term Structure of Government Bond Yields: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=461369
- Factor-augmented DNS 文献摘要: https://ideas.repec.org/a/eee/dyncon/v106y2019ic4.html
- Federal Reserve 关于 term structure + macro factors 的研究: https://www.federalreserve.gov/pubs/ifdp/2010/993/ifdp993.htm

## 5. Baseline 为什么重要

在 fixed income 中，baseline 是防止过度解释的关键。

TraceYield 使用几层 baseline：

### Random-walk baseline

最简单的假设：当前 yield 不变。

这条线很重要，因为很多利率预测在短期内很难稳定击败 random walk。报告中保留它，是为了让使用者知道模型预测到底有没有明显偏离“什么都不发生”的基准。

### FADNS base

只看 yield curve 自身的历史动态，不加入新的宏观 block。

这表示“如果只按照曲线过去的 level/slope/curvature 运动，未来可能怎么走”。

### Macro-adjusted central

在 FADNS base 上加入 inflation、policy path、growth、liquidity/supply、global relative value。

这才是 TraceYield 的正式 central path。

### Event / fan overlay

FOMC、CPI、NFP、PCE、QRA 等事件通常先增加不确定性。只有在政策路径信号足够强时，系统才让事件移动 central path。这样可以避免在数据公布前假装知道 surprise。

## 6. 主要宏观驱动和联动效应

### Policy path -> front end -> curve shape

如果市场重新定价 Fed 更 hawkish：

```text
2Y / 5Y yields up
-> front end sells off
-> 2s10s flattening or bear flattening
-> USD support
-> equities valuation pressure
```

如果市场重新定价 Fed 更 dovish：

```text
2Y / 5Y yields down
-> front end rallies
-> 2s10s steepening or bull steepening
-> USD pressure
-> gold and duration assets may benefit
```

### Inflation -> real yield / breakeven -> 10Y

通胀上行或 breakevens 抬升：

```text
inflation compensation rises
-> nominal 10Y yield pressure higher
-> mortgages / corporate borrowing costs rise
-> long-duration equities face valuation pressure
```

### Liquidity / supply -> term premium -> long end

QT、TGA、RRP、auction stress 或 Treasury supply 压力：

```text
duration supply pressure rises
-> investors demand higher term premium
-> 10Y / 30Y underperform
-> bear steepening risk
```

### Growth risk -> Fed cuts / safe haven -> bull curve

增长放缓或 risk-off：

```text
growth risk rises
-> Fed cuts priced in
-> front end rallies
-> safe-haven demand supports UST
-> bull steepening or bull flattening depending on long-end response
```

### Global relative value -> UST demand -> long-end support or pressure

如果 Bund/JGB yield 上升，或 FX-hedged UST 不再有吸引力：

```text
global duration repricing
-> foreign demand for UST may weaken
-> 10Y / 30Y pressure higher
```

如果 UST 相对全球债券变便宜：

```text
UST relative value improves
-> foreign demand potential rises
-> long-end support
```

## 7. 事件时间轴：什么时间会改变 curve view

固定收益市场不是每天被同一种信息驱动。TraceYield 把驱动分成不同时间层级，这样 desk 可以判断“今天应该看哪个因子”。

### Daily / intraday：价格确认和风险情绪

日频主要看 market confirmation，而不是重新发明宏观叙事：

- 2Y / 5Y：最快反映 Fed path repricing。
- 10Y real yield：反映实际贴现率和长期资金成本。
- Breakevens：反映 inflation compensation。
- DXY / USDJPY：反映美元和利差 channel。
- Gold：通常对 real yield 和美元敏感。
- Equities / credit：反映 discount-rate pressure 和 risk appetite。
- MOVE / VIX：反映 volatility regime，影响仓位和 liquidity premium。

典型变化：

```text
2Y up + DXY up + equities down
-> market is pricing tighter Fed path
-> front-end bearish / bear flattening risk
```

```text
10Y down + gold up + equities down + VIX up
-> risk-off duration bid
-> bull flattening or safe-haven rally
```

### Weekly：claims、Fed speakers、auction cycle

周频信息经常影响 tactical timing：

- Initial jobless claims 连续上升：growth risk 上升，Fed cut pricing 更容易被激活。
- Fed speakers 语气偏 hawkish：2Y / 5Y 先动，curve 容易 bear flatten。
- Fed speakers 语气偏 dovish：front end rally，curve 可能 bull steepen。
- 3Y / 10Y / 30Y auction tail 或 bid-to-cover 走弱：duration supply pressure 上升，10Y / 30Y 容易 underperform。

对于 inter-dealer broker，weekly auction 和 speaker flow 很适合做 client color，因为它们常常解释“为什么今天曲线 move 不是由 CPI 这种大数据引起的”。

### Monthly：NFP、CPI、PCE 是政策路径的核心触发器

月度数据通常决定 3m core view 是否需要调整。

#### NFP / labor market

强 NFP、低 unemployment、claims 下降：

```text
labor market resilient
-> Fed can stay restrictive longer
-> 2Y / 5Y yields higher
-> bear flattening bias
-> USD support, equities valuation pressure
```

弱 NFP、unemployment 上升、claims 上升：

```text
labor market cooling
-> cut probability rises
-> 2Y rallies first
-> bull steepening if long end falls less
-> USD softens, gold/duration assets supported
```

#### CPI / Core CPI

Hot CPI 或 core services inflation sticky：

```text
inflation surprise higher
-> Fed easing path delayed
-> 2Y / 5Y sell off
-> breakevens and real yields may both push 10Y higher
-> equities and credit face discount-rate pressure
```

Soft CPI：

```text
disinflation confirmation
-> Fed has more room to cut
-> front end rallies
-> 10Y lower if real-yield channel dominates
-> gold and long-duration assets can benefit
```

#### PCE / Core PCE

PCE 是 Fed 更偏好的 inflation gauge。它的影响通常比 CPI 更“政策化”：

- Core PCE sticky：policy path hawkish，front end 和 belly 更敏感。
- Core PCE soft：cut path 更可信，bull steepening 或 bull flattening 取决于 growth/risk backdrop。
- 如果 CPI hot 但 PCE soft，市场可能从 inflation scare 切回“Fed 可以等待”的 mixed regime。

### FOMC：statement、SEP/dot plot、press conference

FOMC 是改变 policy path 的最大离散事件。

看三个层次：

1. Decision：cut、hold、hike 是否符合市场定价。
2. Statement / press conference：Powell 是否强调 inflation risk、labor cooling、financial conditions。
3. SEP / dot plot：committee 对未来 policy rate、inflation、unemployment 的路径是否上移或下移。

典型场景：

```text
hawkish hold
-> no hike, but dots higher / inflation concern stronger
-> 2Y sells off
-> 2s10s bear flattening
-> USD stronger, equities weaker
```

```text
dovish hold
-> no cut yet, but labor risk acknowledged / dots lower
-> 2Y rallies
-> bull steepening
-> USD weaker, gold and duration supported
```

```text
hawkish cut
-> Fed cuts but says inflation risk remains
-> front end may rally less than expected
-> curve reaction can be mixed
```

### Quarterly：QRA、Treasury supply、TBAC、fiscal path

QRA 是 long-end / term-premium 事件，不是传统 macro data。

重点看：

- coupon auction size 是否上调。
- long-end issuance 比例是否增加。
- Treasury bills vs coupons 的融资组合。
- buyback schedule 是否支持 off-the-run liquidity。
- deficit / cash balance / TGA 路径是否改变 funding needs。

典型场景：

```text
larger coupon supply, especially 10Y/20Y/30Y
-> duration supply pressure
-> term premium higher
-> 10Y / 30Y underperform
-> bear steepening
```

```text
more bill-heavy issuance or supportive buybacks
-> less long-end supply pressure
-> 10Y / 30Y supported
-> curve flattening or long-end rally
```

### Overseas central banks：BOJ、ECB、Bund/JGB channel

UST 不只由美国数据决定。跨市场 desk 要特别看：

- BOJ hawkish / JGB yields higher：global duration repricing，UST long end may cheapen。
- ECB hawkish / Bund yields higher：UST-Bund relative value changes，影响 cross-market rates flow。
- Dollar funding stress：USD 上行，risk appetite 下降，可能同时推高美元并引发 UST safe-haven bid。
- FX-hedged yield 变差：海外投资者买 UST 的吸引力下降，长端 demand 可能减弱。

### Risk-off shock：正常宏观链条会被覆盖

战争、银行压力、credit event、equity drawdown、流动性冲击可能让正常宏观逻辑短期失效。

```text
risk-off shock
-> safe-haven demand for UST
-> 10Y / 30Y yields lower
-> gold and USD often supported
-> equities/credit weaker
```

但如果 shock 同时带来 fiscal expansion 或 supply concern，长端可能不跌反升，形成 difficult regime：

```text
risk shock + fiscal/supply concern
-> front end prices cuts
-> long end prices term premium
-> bull steepening or bear steepening depends on which force dominates
```

## 8. 近期事件雷达（as of 2026-06-12）

这些日期是当前 TraceYield event overlay 最关注的近期节点。报告不会在数据公布前假装知道 surprise；它会先扩大 fan band，等 released data 或高置信 policy path 出现后再调整 central view。

| 日期 | 事件 | 主要影响部位 | 如果偏 hawkish / hot | 如果偏 dovish / soft |
|---|---|---|---|---|
| 2026-06-17 | FOMC + SEP | 2Y / 5Y，2s10s | dots higher、inflation language hawkish -> bear flattening | dots lower、labor risk acknowledged -> bull steepening |
| 2026-06-25 | Personal Income & Outlays / PCE | 2Y / 5Y / 10Y | core PCE sticky -> cut path delayed | core PCE soft -> disinflation confirmation |
| 2026-07-02 | Employment Situation / NFP | 2Y / 5Y | strong payrolls / low unemployment -> restrictive Fed path | weak payrolls / unemployment up -> cuts priced |
| 2026-07-14 | CPI | 2Y / 5Y / 10Y | hot CPI -> real yield / breakeven pressure | soft CPI -> front-end rally |
| 2026-07-29 | FOMC | 2Y / 5Y | hawkish hold -> front-end selloff | dovish hold -> front-end rally |
| 2026-08-05 | Treasury QRA | 10Y / 30Y，5s30s | larger coupon/long-end supply -> bear steepening | bill-heavy / buyback supportive -> long-end support |
| 2026-09-16 | FOMC + SEP | Full curve | dots higher -> policy path repricing | dots lower -> easing path validation |
| 2026-12-09 | FOMC + SEP | Full curve | higher terminal / inflation risk -> long-end pressure | lower dots / weaker growth -> bull curve |

官方日历来源：

- Fed FOMC calendar: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
- BLS CPI schedule: https://www.bls.gov/schedule/news_release/cpi.htm
- BLS Employment Situation schedule: https://www.bls.gov/schedule/news_release/empsit.htm
- BEA release schedule: https://www.bea.gov/news/schedule
- U.S. Treasury Quarterly Refunding documents: https://home.treasury.gov/policy-issues/financing-the-government/quarterly-refunding/most-recent-quarterly-refunding-documents

## 9. 判断如何被“推翻”：desk 应该盯的 reversal triggers

TraceYield 的 view 不是固定不变的。以下变化会触发重新评估：

### 从 bull view 转向 bear view

- CPI/PCE 连续 hot，尤其 core services sticky。
- 2Y yield 突破近期 range 上沿，market prices fewer cuts。
- Fed dots 上移，Powell 强调 inflation risk。
- QRA 显示 long-end coupon supply 超预期。
- 10Y real yield 上行并带动 equities/credit 承压。
- Bund/JGB yields 同步上行，global duration 被重新定价。

### 从 bear view 转向 bull view

- Payrolls 明显转弱，unemployment 上升，claims trend 恶化。
- CPI/PCE soft，disinflation path 被确认。
- Fed statement / press conference 转向 labor-risk narrative。
- 2Y yield 下破 range，cut probability 快速上升。
- Equity/credit risk-off 触发 safe-haven UST demand。
- Auction demand 强、QRA 不增加 long-end supply，term premium 压力缓解。

### 从 directional view 转向 range-bound / mixed

- Inflation hot 但 growth weak：stagflation-like conflict。
- Fed dovish 但 QRA supply bearish：front-end rally 与 long-end pressure 对冲。
- UST cheaper 但 FX hedge cost 太高：relative value signal mixed。
- Polymarket / market-implied checks 与 model central path 不一致。
- Event calendar 太密集，data before FOMC，市场等待确认。

## 10. 对 Nittan fixed income desk 的具体用途

### Morning meeting

每天早上用 HTML 报告快速回答：

- 今天 UST curve 的 base case 是什么？
- 3m / 6m 核心看法是什么？
- 当前是 policy-driven、inflation-driven、supply-driven，还是 global RV-driven？
- 哪些事件会改变判断？

### Client color

给 dealer / institutional client 提供更结构化的 market color：

- “10Y central path lower/higher 的主要原因是什么？”
- “这是不是 Fed path repricing？”
- “2s10s 变陡是 bull steepening 还是 bear steepening？”
- “长端压力来自 inflation 还是 term premium / supply？”

### Cross-market read-through

帮助不同 desks 使用同一个 UST anchor：

- USD / JPY：美日利差变化。
- Bund / EUR rates：UST-Bund 相对价值。
- Gold：real yield 和 dollar channel。
- Equities：discount rate channel。
- Credit：funding cost 和 risk appetite channel。
- Commodities / EM：美元和全球流动性 channel。

### Risk dashboard

把事件风险前置：

- FOMC：policy path 和 SEP/dot plot。
- CPI / PCE：inflation surprise。
- NFP / claims：growth 和 labor market repricing。
- QRA / auction：Treasury supply 和 long-end term premium。

## 11. 当前限制和后续增强

当前限制：

- 不是 intraday execution signal。
- 免费数据会有 release lag。
- 某些 surprise 数据需要 consensus source，当前仍以 released data 和 proxy 为主。
- Polymarket 只作为 external check，不进入 central forecast。
- LLM 只用于 narrative/regime，不直接设定 bp magnitude。

后续增强方向：

- 接入更完整的 SOFR / Fed funds futures policy path。
- 加入 macro surprise consensus 数据。
- 加入 CFTC positioning、dealer inventory、ETF/fund flow。
- 扩展 Japan / Bund / China rates read-through。
- 做一个 manager-friendly dashboard 或 GitHub Pages 静态报告页。

## 12. 给 boss 的一句话

TraceYield 是一套面向 fixed income desk 的 UST curve intelligence workflow：它用 FADNS 把美国国债曲线拆成 level、slope、curvature，再用政策、通胀、增长、流动性/供给和全球相对价值解释曲线未来 12 个月的 central path、baseline 和不确定性，帮助 inter-dealer broker 在跨市场报价、客户沟通和事件风险管理中更快形成一致的 rates view。
