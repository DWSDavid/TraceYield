# TraceYield 中文使用文档

## 1. 项目定位

TraceYield 是一个面向固定收益市场的美国国债收益率曲线分析工具。它每天读取宏观数据、Fed/FOMC 文本、政策路径、流动性与全球利差数据，生成一份可解释的 UST curve view。

它回答的核心问题是：

- 未来 1m / 3m / 6m / 12m，美国国债收益率更可能上行、下行，还是区间震荡？
- 2Y、5Y、10Y、30Y 哪些期限最受影响？
- 2s10s、5s30s 曲线更可能 steepen、flatten，还是 range-bound？
- 这次判断由哪些宏观因素驱动？
- 哪些数据或事件会改变当前判断？

重要边界：TraceYield 是 research / decision-support 工具，不是自动交易系统，也不是投资建议。

## 2. 当前交付内容

代码入口：

- `scripts/daily_run.py`：每日 10Y 方向和水平预测入口。
- `scripts/curve_run.py`：UST curve forecast 入口。
- `scripts/curve_run.py --html`：把最新 curve trajectory 渲染成可离线打开的 HTML 报告。
- `scripts/backtest.py`、`scripts/curve_backtest.py`：回测和验证入口。

核心模块：

- `src/ingestion/`：FRED、FOMC、NY Fed ACM、Treasury auction 等数据读取。
- `src/signals/`：把原始数据转换为宏观信号，例如 inflation、policy path、liquidity/supply、global relative value。
- `src/models/`：方向预测、FADNS curve trajectory、fan band 和 baseline。
- `src/report/`：Markdown 和 HTML 报告渲染。
- `configs/`：权重、FRED series、FOMC 日历、事件日历、curve rules 等配置。
- `tests/`：单元测试和回归测试。

主要输出：

- `data/reports/report_YYYYMMDD.md`：每日文字版报告。
- `data/reports/curve_latest.md`：最新曲线预测 Markdown 摘要。
- `data/reports/curve_latest.html`：最新交互式 HTML 报告。
- `data/forecasts/curve_trajectory_YYYYMMDD.json`：机器可读的 12 个月曲线路径。
- `data/forecasts/curve_trajectory_YYYYMMDD.csv`：表格版曲线路径。
- `data/backtest/*.csv`：回测与 IC sanity check 结果。

## 3. 安装与环境

建议使用 Python 3.13。

```powershell
cd C:\Users\rwu10\Desktop\TraceYield
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

创建 `.env` 文件，至少需要：

```text
FRED_API_KEY=your_fred_key
```

如果要启用 LLM/FOMC 深度文本分析，再加入对应的模型 API key。没有 LLM key 时，系统仍可用 keyword scorer、缓存和 proxy 数据降级运行。

## 4. 每日运行 SOP

### Step 1 - 更新 FRED 数据并生成每日 10Y 报告

```powershell
python scripts\daily_run.py
```

它会执行：

1. 拉取 FRED 数据。
2. 分析最新 FOMC statement / minutes。
3. 计算因子分数。
4. 生成 10Y direction + level 预测。
5. 输出 Markdown 和 HTML daily report。

### Step 2 - 生成 UST curve forecast

```powershell
python scripts\curve_run.py
```

它会读取最新 processed FRED cache，生成 2Y、5Y、10Y、30Y、2s10s、5s30s 的曲线预测摘要。

### Step 3 - 生成可给 manager 打开的 HTML 报告

```powershell
python scripts\curve_run.py --html
```

输出位置：

```text
data/reports/curve_latest.html
```

这个 HTML 是 self-contained 的，可以离线打开，不需要服务器。

## 5. 报告怎么看

### 方向语言

- Bull bonds：收益率下行，债券价格上行。
- Bear bonds：收益率上行，债券价格下行。
- Neutral / range-bound：方向不强，更多是等待数据触发。
- Bull steepening：短端下行多于长端，曲线变陡。
- Bear steepening：长端上行多于短端，曲线变陡。
- Bull flattening：长端下行多于短端，曲线变平。
- Bear flattening：短端上行多于长端，曲线变平。

### 核心图表

- Central / p50：模型中心路径。
- p10 / p90：历史误差和事件不确定性形成的外层区间。
- p25 / p75：更集中的核心区间。
- Random-walk baseline：假设当前收益率未来保持不变的参考线。
- Base path：只用 FADNS 曲线自身动态推出来的路径。
- Selected factors：在 HTML 中手动勾选宏观因子后看到的解释性路径。
- Official central：全部当前宏观因子纳入后的正式中心路径。

### 因子解释

报告中会展示以下宏观 block：

- Inflation regime：CPI、PCE、breakevens、5y5y inflation expectations。
- Policy path：Fed target、EFFR、SOFR、2Y、3M/6M proxy、FOMC tone。
- Growth risk：payroll、unemployment、claims、manufacturing、retail sales、JOLTS。
- Liquidity/supply：Fed balance sheet、reserves、RRP、TGA、Treasury auction stress。
- Global relative value：UST 与 Bund/JGB 的相对收益率、美元环境。

每个 block 会说明它更影响前端、长端、还是曲线形状。

## 6. Baseline 的意义

TraceYield 不只给一个预测数字，而是把预测拆成几个参照层：

- Random-walk baseline：最朴素的基准，假设未来不变。任何模型都应该先和这个参考比较。
- FADNS base：只用 yield curve 自身的 level、slope、curvature 动态来预测。
- Macro-adjusted FADNS：在 FADNS base 上加入 inflation、policy、growth、liquidity、global relative value。
- Event overlay：FOMC、CPI、NFP、PCE、QRA 等事件通常先扩大不确定性，只有高置信 policy path 才移动中心路径。

这种拆法的好处是：manager 可以看到“模型本身怎么看”、“宏观因素额外推了多少”、“事件风险只是放大区间还是改变方向”。

## 7. 验证 SOP

交付或更新前建议运行：

```powershell
ruff check src scripts tests
black --check src scripts tests
pytest -q
```

如果要避免 pytest cache 目录干扰，可以用：

```powershell
pytest -q -p no:cacheprovider --basetemp=pytest-tmp-local
```

## 8. GitHub 交付规则

应该上传：

- `src/`
- `scripts/`
- `configs/`
- `tests/`
- `docs/`
- `README.md`
- `PROGRESS.md`
- `requirements.txt`
- `pytest.ini`
- 经过筛选的小型 `data/backtest/`、`data/forecasts/`、`data/reports/*.md`

不要上传：

- `.env`
- API keys
- `.venv/`
- `data/raw/`
- `data/cache/`
- `data/processed/`
- `pytest-tmp-*`
- `black-cache-*`
- 大量历史 HTML 报告

如果需要给 boss 看 HTML，建议只提供最新 `curve_latest.html` 或单独发送文件，不要把所有历史 HTML 都放进 GitHub。

## 9. 给 manager 的一句话版本

TraceYield 把美国国债曲线拆成政策路径、通胀、增长、流动性/供给、全球相对价值五个可解释驱动，用 FADNS 生成 2Y/5Y/10Y/30Y 的 12 个月 curve view，并用 HTML 报告展示 central path、uncertainty fan、baseline 和触发事件，帮助 fixed income desk 更快理解 UST 曲线对跨市场风险的影响。
