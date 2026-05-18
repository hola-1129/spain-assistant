# Web3 Monitor v2

免费 API 驱动的 Web3 链上异动 + Polymarket 事件预期监控机器人。

当前版本仅做：信号识别 → 综合评分 → Telegram 推送 → SQLite / 本地日志 → 复盘框架。
**不接私钥，不下单，`dry_run=true` 强制开启。**

---

## 功能

1. DexScreener / GeckoTerminal：DEX 池子价格、成交量、流动性变化
2. CoinGecko：Top-100 加密资产 market mover（24h 异动、换手、7日 Alpha）
3. DeFiLlama：链 TVL、协议 TVL、稳定币流动
4. 新池子 / 新币扫描
5. 巨鲸 / 聪明钱线索（占位，第一版仅记录）
6. Polymarket Gamma + CLOB + Data API：事件、盘口概率、成交量
7. 综合 100 分评分 + v2 可配置 scoring 模块
8. Telegram 推送（HIGH ≥ 80，MEDIUM ≥ 60）
9. 信号写入 `data/signal_log.jsonl` 与 `data/web3_monitor.db`
10. 复盘/回测框架与 MCP 预留工具函数

---

## 安装

```bash
cd /Volumes/AI_DISK/ai_workspace/agents/web3_monitor
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 填入 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID
```

## 运行

前台调试：
```bash
.venv/bin/python scripts/main.py
```

只跑一轮验收：
```bash
.venv/bin/python scripts/main.py --once
```

本地个人 Dashboard：
```bash
.venv/bin/python dashboard/app.py
```
打开 `http://127.0.0.1:8787/`。域名 `holaflow.xyz` 的接入说明见 `docs/DASHBOARD.md`。

离线语法检查：
```bash
find scripts -name '*.py' ! -name '._*' -print0 | xargs -0 .venv/bin/python -m py_compile
```

后台守护：
```bash
nohup .venv/bin/python scripts/main.py > ../../logs/web3_monitor/stdout.log 2>&1 &
```

停止：
```bash
pkill -f "web3_monitor.*scripts/main.py"
```

---

## 配置

`config.yaml` 关键项：

| 字段 | 默认 | 说明 |
|------|------|------|
| `dry_run` | `true` | 强制 true，第一版不可改 |
| `auto_trade` | `false` | 强制 false |
| `scan_intervals.tick_seconds` | 60 | 主循环醒来检查频度 |
| `scan_intervals.dex_minutes` | 5 | DexScreener 资产异动扫描 |
| `scan_intervals.coingecko_market_minutes` | 15 | CoinGecko Top-100 market mover 扫描 |
| `scan_intervals.polymarket_minutes` | 10 | Polymarket 事件概率/成交量扫描 |
| `scan_intervals.new_pools_minutes` | 30 | GeckoTerminal 新池子扫描 |
| `scan_intervals.defillama_minutes` | 60 | DeFiLlama 链 TVL 快照 |
| `thresholds.min_liquidity_usd` | 50000 | DEX 池子最低流动性 |
| `thresholds.min_volume_1h_usd` | 50000 | DEX 1h 最低绝对成交额，过滤小额量比噪音 |
| `thresholds.min_signal_score` | 60 | 推送 Telegram 的最低分 |
| `thresholds.high_signal_score` | 80 | HIGH 等级阈值 |
| `thresholds.coingecko_market_min_score` | 60 | Market mover 推送最低分 |
| `thresholds.coingecko_market_high_score` | 70 | Market mover HIGH 等级阈值 |
| `thresholds.signal_cooldown_minutes` | 60 | 同一综合信号推送冷却 |
| `thresholds.market_mover_cooldown_minutes` | 60 | 同一 market mover 推送冷却 |
| `storage.sqlite_path` | data/web3_monitor.db | v2 SQLite 数据库 |

监控范围（chains / assets / polymarket_categories）也在 `config.yaml`。
个人重点关注的池子、地址、事件可写到 `data/watchlist.yaml`。

---

## 输出

- Telegram：HIGH 或 MEDIUM 信号会推送
- `data/signal_log.jsonl`：每条信号一行 JSON
- `data/web3_monitor.db`：SQLite 历史信号库
- `data/runtime_state.json`：Polymarket 上次概率、推送冷却状态
- `../../logs/web3_monitor/`：运行日志（错误、debug、API 限速）

---

## 边界

- 不连私钥，不签名，不下单
- 启动时会拒绝 `PRIVATE_KEY` / `WALLET_PRIVATE_KEY` / `MNEMONIC` / `SEED_PHRASE`
- 仅读取公开免费 API
- 所有 API 调用有 timeout + 异常处理 + rate limit 间隔
- 触发推送前必经过 `risk_filter`
- 不实现任何真实交易、签名、下单、撤单、approve、swap、bridge

---

## 目录

```
web3_monitor/
├── README.md
├── agent.md             # 角色、边界、禁止事项
├── config.yaml
├── requirements.txt
├── .env.example
├── data_sources.md      # 各 API 用途与文档链接
├── strategies/          # 策略说明（Markdown）
├── scripts/             # 可执行 Python
├── data/
│   ├── watchlist.yaml
│   └── signal_log.jsonl
└── logs/
```
