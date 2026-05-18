# Web3 Monitor v2 Upgrade

v2 把原来的“免费 API → Telegram → JSONL”升级为个人只读 Web3 Quant Monitor。

## 新增模块

- `scripts/signal_model.py`：统一 `Signal` 数据结构。
- `scripts/storage.py`：SQLite 存储层，默认数据库 `data/web3_monitor.db`。
- `scripts/scoring.py`：可配置 0-100 分评分框架。
- `scripts/review.py`：复盘/回测脚手架，预留 1h、6h、24h 后续表现字段。
- `scripts/tools.py`：未来 MCP tools 的函数边界。

## 数据库

默认位置：

```bash
/Volumes/AI_DISK/ai_workspace/agents/web3_monitor/data/web3_monitor.db
```

核心表：`signals`

字段包含：`timestamp`, `source`, `token`, `symbol`, `chain`, `signal_type`,
`price`, `volume`, `liquidity`, `score`, `reason`, `raw_data_json`,
`telegram_sent`，以及 `price_change_1h_pct`, `price_change_6h_pct`,
`price_change_24h_pct` 等复盘字段。

## 运行

```bash
cd /Volumes/AI_DISK/ai_workspace/agents/web3_monitor
.venv/bin/python scripts/main.py --once
```

查看最近信号：

```bash
.venv/bin/python - <<'PY'
from scripts.tools import get_recent_signals
for row in get_recent_signals(5):
    print(row["id"], row["timestamp"], row["source"], row["symbol"], row["score"], row["telegram_sent"])
PY
```

运行复盘统计：

```bash
.venv/bin/python scripts/review.py
```

## 边界

- 个人研究工具，只读。
- 不接私钥、不读取助记词。
- 不实现 swap、approve、bridge、CEX 下单、Polymarket 下单/撤单。
- `dry_run=true` 与 `auto_trade=false` 继续由主程序强制覆盖。

## Dashboard 准备

Dashboard 应只读取 SQLite，不直接读取 `.env` 或调用交易接口。第一版建议：

- Recent Signals
- Signal Detail
- Score Summary
- Review Summary
- API Health

移动端优先，适配 iOS Safari，后续可做 PWA。
