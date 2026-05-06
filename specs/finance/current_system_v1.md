# Finance Bot — 当前系统文档 v1

> 文档日期：2026-05-06  
> Bot 状态：运行中（PID 93232）  
> 代码路径：`/Volumes/AI_DISK/ai_workspace/agents/finance_bot/`

---

## 1. 系统架构总览

```
main.py
  └── BotScheduler (scheduler.py)
        ├── Fetchers
        │   ├── YFinanceFetcher        # 股票 / ETF / 期货 / FX / 利率
        │   └── CoinGeckoFetcher       # 加密货币
        │
        ├── Engine（拐点识别）
        │   ├── inflection.py          # 信号聚合 → InflectionEvent
        │   ├── cross_asset.py         # 跨资产相关性分析
        │   └── regime.py              # 市场状态分类（牛/熊/震荡）
        │
        ├── Signals（原始信号）
        │   ├── momentum.py            # MACD、MA 交叉、RSI、52周高低
        │   ├── volatility.py          # ATR、布林带、BB Squeeze
        │   └── volume.py              # 成交量突破、量能枯竭
        │
        ├── Scanner（异动扫描）
        │   ├── stock_scanner.py       # 美股全市场扫描
        │   ├── crypto_scanner.py      # 加密货币扫描
        │   ├── asia_scanner.py        # 亚洲市场（A股/港股/日韩）
        │   ├── macro_scanner.py       # 宏观指标（期货/大宗/FX/利率）
        │   ├── daily_summary.py       # 每日收盘汇总
        │   ├── scorer.py              # unusual_score 计算
        │   └── alert_throttle.py      # 每小时限速 + 同标的冷却
        │
        ├── Storage
        │   └── data_store.py          # SQLite + CSV 持久化
        │
        └── Alerts
            └── telegram_alert.py      # Telegram 推送
```

---

## 2. 调度任务一览

| Job ID | 频率 | 触发条件 | 功能 |
|--------|------|---------|------|
| `high_freq` | 每 3 min | 无条件 | BTC/ETH/WLD 快速波动检测（24h 涨跌 ≥5%）|
| `mid_freq` | 每 15 min | 无条件 | NVDA/TSLA/PL/PLTR/HIMS 拐点检测 |
| `low_freq` | 每 4 h | 无条件 | 全标的深度拐点扫描 + 跨资产分析 |
| `macro` | 每 24 h | 无条件 | 市场状态快照 + 每日拐点排行 |
| `stock_scan` | 每 30 min | 美股交易时段 09:30–16:00 ET | 全市场异动扫描（unusual_score）|
| `crypto_scan` | 每 15 min | 无条件（24/7）| 加密市场异动扫描 |
| `asia_scan` | 每 30 min | 各市场交易时段内部判断 | A股/港股/日本/韩国异动扫描 |
| `macro_scan` | 每 30 min | 无条件 | 宏观指标异常提醒（大幅波动）|
| `macro_snapshot` | 每 4 h | 无条件 | 宏观全景播报（期货/大宗/FX）|
| `daily_summary` | 每天 16:15 ET | 周一至周五 | 当日全市场收盘汇总 |

---

## 3. 监控标的

### 3.1 拐点引擎（Engine）标的
| 频率 | 标的 | 数据源 |
|------|------|--------|
| 高频 3 min | BTC, ETH, WLD | CoinGecko |
| 中频 15 min | NVDA, TSLA, PL, PLTR, HIMS | yfinance |
| 低频 4 h | 以上全部 + SPY, QQQ, ^VIX | 混合 |

### 3.2 股票异动扫描器（StockScanner）
约 100+ 标的，分以下板块：

| 板块 | 主要标的 |
|------|---------|
| AI/半导体 | NVDA, AMD, INTC, AVGO, QCOM, MU, ARM, SMCI, ASML, TSM... |
| 软件/云 | MSFT, GOOGL, META, AMZN, AAPL, CRM, PLTR, SNOW, CRWD... |
| 生物科技 | MRNA, REGN, AMGN, HIMS, LLY, NVO, ABBV... |
| 金融科技 | PYPL, COIN, V, MA, SOFI, HOOD... |
| 成长股 | TSLA, UBER, NFLX, SHOP, MELI, PL... |
| 大盘蓝筹 | JPM, BAC, GS, XOM, WMT, COST... |
| ETF | SPY, QQQ, IWM, XLK, SMH, ARKK, XBI... |

### 3.3 亚洲市场（AsiaScanner）
| 市场 | 交易时段 | 范围 |
|------|---------|------|
| A股 🇨🇳 | 09:30–15:00 CST | 大盘蓝筹/科技AI/半导体/新能源/消费医药，约 25 只 |
| 港股 🇭🇰 | 09:30–16:00 HKT | 科技互联网/金融/医药，约 14 只 |
| 日本 🇯🇵 | 09:00–15:30 JST | 科技/半导体/汽车/金融/工业，约 15 只 |
| 韩国 🇰🇷 | 09:00–15:30 KST | 半导体/汽车/互联网/生物医药/电池，约 12 只 |

### 3.4 宏观指标（MacroScanner）
| 类别 | 标的 |
|------|------|
| 股指期货 | ES=F（标普）, NQ=F（纳指）, RTY=F（Russell）|
| 利率/波动 | ^TNX（US10Y）, ^VIX |
| 贵金属 | GC=F（黄金）, SI=F（白银）|
| 能源 | CL=F（WTI）, BZ=F（Brent）, NG=F（天然气）|
| 农产品 | ZC=F（玉米）, ZW=F（小麦）, KC=F（咖啡）|
| 加密 | BTC-USD, ETH-USD |
| 外汇 | DXY, EUR/USD, GBP/USD |

---

## 4. 信号库（Signal Library）

拐点引擎使用 21 种信号，按权重分级：

| 权重 | 信号 | 方向 |
|------|------|------|
| 3.0 | `golden_cross`（MA50上穿MA200）| bullish |
| 3.0 | `death_cross`（MA50下穿MA200）| bearish |
| 2.5 | `break_ma200`（跌破MA200）| bearish |
| 2.5 | `reclaim_ma200`（收复MA200）| bullish |
| 1.8 | `macd_golden`（MACD金叉）| bullish |
| 1.8 | `macd_death`（MACD死叉）| bearish |
| 1.8 | `volume_spike`（成交量突破）| 方向性 |
| 1.5 | `break_ma50` / `reclaim_ma50` | 方向性 |
| 1.4 | `bb_break_down`（布林带下轨跌破）| bearish |
| 1.2 | `atr_expansion`（ATR扩张）| 方向性 |
| 1.2 | `near_52w_high` / `near_52w_low` | 方向性 |
| 1.0 | `rsi_oversold` / `rsi_overbought` | 方向性 |
| 0.8 | `rsi_cross_up` / `rsi_cross_down` | 方向性 |
| 0.6 | `bb_squeeze`（布林带收窄）| neutral |
| 0.5 | `volume_mild_spike` | 方向性 |
| 0.3 | `volume_dryup`（成交量枯竭）| neutral |

**评分公式**：`score = Σ(weight × strength)`，上限 10.0

**拐点触发阈值**：
- 高频：≥ 4.0
- 中频：≥ 3.0
- 低频：≥ 2.5

---

## 5. 异动扫描评分（unusual_score）

`unusual_score`（0–100）基于以下维度：

- 24h 涨跌幅（相对板块均值的偏离度）
- 成交量比（当日 vs 20日均量）
- 价格动能（RSI 极值、布林带位置）
- 波动率变化（ATR 相对历史）

**告警阈值**：
- `unusual_score ≥ 60` → Telegram 推送
- `unusual_score ≥ 30` → 仅写日志

**限速机制**：
- 每小时最多推送 8 条
- 同一标的 60 分钟内不重复
- 市场大跌模式（SPY 日跌 ≥3%）：仅播报 ETF + Top5

---

## 6. 关键配置参数

```yaml
# config.yaml 核心参数（当前值）
engine:
  min_score_high_freq: 4.0
  min_score_mid_freq:  3.0
  min_score_low_freq:  2.5
  quick_move_pct:      5.0    # 加密 24h 涨跌触发快速提醒

scanner:
  stock_scan_interval_min:  30
  crypto_scan_interval_min: 15
  min_score_alert:          60.0
  min_score_log:            30.0
  max_alerts_per_hour:      8
  cooldown_minutes:         60

alerts:
  cooldown_hours: 4           # 拐点系统同一条规则冷却时间
```

---

## 7. 数据存储

| 内容 | 路径 |
|------|------|
| SQLite 数据库 | `/Volumes/AI_DISK/ai_workspace/data/market_data/finance_bot.db` |
| 股票价格 CSV | `/Volumes/AI_DISK/ai_workspace/data/market_data/stock_prices.csv` |
| 加密价格 CSV | `/Volumes/AI_DISK/ai_workspace/data/market_data/crypto_prices.csv` |
| 异动快照 CSV | `/Volumes/AI_DISK/ai_workspace/data/market_data/unusual_movers/` |
| 运行日志 | `/Volumes/AI_DISK/ai_workspace/logs/finance_bot/` |

**SQLite 表结构**：`price_history`, `iv_history`, `alert_history`, `signal_history`

---

## 8. 已知局限 / 待改进

| 编号 | 问题 | 影响 |
|------|------|------|
| L-01 | IV Rank 需 20+ 天历史才能计算 | 新标的前期无期权信号 |
| L-02 | 持仓数据手动填写（不同步券商）| 仓位风险规则依赖手动更新 |
| L-03 | CoinGecko 免费 API 限速 30次/min | 高频请求需内置 2.1s 间隔 |
| L-04 | 无欧洲市场扫描 | 欧股异动无覆盖 |
| L-05 | 宏观信号以异动为主，缺趋势层 | 宏观指标无 MA/拐点体系 |
| L-06 | 无回测框架 | 无法验证信号历史有效性 |

---

## 9. 相关任务文件

- `tasks/finance/tasks.md` — 当前任务列表
- `tasks/finance/macro_upgrade_v1.md` — 宏观层升级（待创建）
- `tasks/finance/asia_scanner_v1.md` — 亚洲扫描器扩展（待创建）
- `tasks/finance/europe_scanner_v1.md` — 欧洲市场扫描（待创建）
- `tasks/finance/signal_layer_v1.md` — 信号层优化（待创建）
