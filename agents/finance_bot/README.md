# Finance Market Monitor

个人金融市场监控系统 — 价格提醒 + 期权信号 + 仓位风险，**只监控，不交易**。

## 功能模块

| 模块 | 频率 | 内容 |
|------|------|------|
| 高频 (3 min) | BTC / ETH / WLD | 价格突破、单日涨跌幅 |
| 中频 (15 min) | NVDA / TSLA / PL / PLTR / HIMS | 价格突破、单日涨跌幅 |
| 低频 (12 h) | 全部标的 | MA趋势、相对强弱Alpha、期权信号、仓位风险 |
| 宏观 (24 h) | VIX / SPY / QQQ | 恐慌指数、大盘回撤 |

### 规则覆盖

- **A 价格规则** — 跌破/突破目标价、单日涨跌幅超阈值
- **B Alpha/相对强弱** — 相对 SPY/QQQ 的 20/60 日表现；相对 BTC 的 7/30 日表现
- **C 趋势** — MA20 / MA50 / MA200；跌破 MA50 提醒，跌破 MA200 高风险提醒
- **D 期权** — IV Rank、Covered Call / CSP 候选（Black-Scholes Delta + 年化收益率）、财报日临近提醒
- **E 市场风险** — VIX 高/极端、SPY/QQQ 从高点回撤百分比
- **F 仓位风险** — 单一资产集中度、加密总占比、现金比例

## 目录结构

```
finance_bot/
├── main.py                  # 入口
├── config.py                # 配置加载
├── scheduler.py             # APScheduler 多频率调度
├── fetchers/
│   ├── yfinance_fetcher.py  # 股票/ETF/期权数据
│   └── coingecko_fetcher.py # 加密货币数据
├── rules/
│   ├── price_rules.py
│   ├── trend_rules.py
│   ├── alpha_rules.py
│   ├── options_rules.py
│   ├── market_risk_rules.py
│   └── position_risk_rules.py
├── alerts/
│   └── telegram_alert.py
├── storage/
│   └── data_store.py        # SQLite + CSV
└── utils/
    └── logger.py
```

数据目录：
- `/Volumes/AI_DISK/ai_workspace/data/market_data/` — SQLite DB + CSV 价格历史
- `/Volumes/AI_DISK/ai_workspace/logs/finance_bot/` — 按天轮转日志（保留 30 天）

## 快速开始

### 1. 安装依赖

```bash
cd /Volumes/AI_DISK/ai_workspace/agents/finance_bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 创建配置文件

```bash
cp config.example.yaml config.yaml
cp .env.example .env
```

编辑 `.env`，填入你的 Telegram 凭证：

```
TELEGRAM_BOT_TOKEN=1234567890:ABCDEFxxxxxxxx
TELEGRAM_CHAT_ID=987654321
```

编辑 `config.yaml`，调整：
- `rules.price` 里各标的的目标价 / 涨跌幅阈值
- `portfolio.positions` 填入你的实际持仓
- `portfolio.cash` 填入现金余额
- `alerts.cooldown_hours` 同一条规则的报警间隔（默认 4 小时）

### 3. 运行

```bash
python main.py
```

## 注意事项

- **CoinGecko 免费 API** 限速约 30 次/分钟，高频检查已内置 2s 间隔
- **期权 IV Rank** 需要积累至少 20 条历史数据（约 20 个交易日）才能计算
- **仓位风险** 依赖 `config.yaml` 中手动填写的持仓，不自动同步券商账户
- `daily_change_pct` 对股票基于当日涨跌幅（相对前收），对加密货币基于 24h 涨跌幅
