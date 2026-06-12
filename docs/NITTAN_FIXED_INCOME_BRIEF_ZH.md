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

## 7. 对 Nittan fixed income desk 的具体用途

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

## 8. 当前限制和后续增强

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

## 9. 给 boss 的一句话

TraceYield 是一套面向 fixed income desk 的 UST curve intelligence workflow：它用 FADNS 把美国国债曲线拆成 level、slope、curvature，再用政策、通胀、增长、流动性/供给和全球相对价值解释曲线未来 12 个月的 central path、baseline 和不确定性，帮助 inter-dealer broker 在跨市场报价、客户沟通和事件风险管理中更快形成一致的 rates view。
