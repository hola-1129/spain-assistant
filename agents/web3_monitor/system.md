# Web3 Monitor — Agent 定义

Web3 / DeFi 策略监控系统。对应用户"极客节点 + DeFi 收益 + Web3 早期机会"策略，**只监控，不操作**。

## 监控模块

| 模块 | 频率 | 内容 |
|------|------|------|
| Token 价格 | 30 min | WLD / TAO / OLAS / FET / LINK / ZRO / AR 涨跌幅 |
| DeFi TVL | 4 h | EigenLayer / Pendle / Hyperliquid TVL 异常下降 |
| DeFi 收益 | 4 h | 全网 APY ≥ 8%、TVL ≥ $5M 的稳健收益池 |
| Polymarket 结算 | 4 h | 关键词市场 ≤ 3 天结算提醒 |
| Polymarket 热门 | 每天 9:00 | 当日宏观热门市场播报 |
| 每周任务提醒 | 周一 9:00 | Restaking / RFQ / perp DEX / Polymarket / RWA |

## 路径

| 资源 | 路径 |
|------|------|
| 代码 | `/Volumes/AI_DISK/ai_workspace/agents/web3_monitor/` |
| 配置 | `config.yaml` / `.env` |
| 数据库 | `/Volumes/AI_DISK/ai_workspace/data/web3_monitor/web3_monitor.db` |
| 日志 | `/Volumes/AI_DISK/ai_workspace/logs/web3_monitor/` |
| 策略参考 | `/Volumes/AI_DISK/ai_workspace/specs/web3/` |

## 生命周期

```bash
# 安装依赖（首次）
cd /Volumes/AI_DISK/ai_workspace/agents/web3_monitor
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 配置
cp .env.example .env   # 填入 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID

# 启动
nohup .venv/bin/python main.py > ../../logs/web3_monitor/stdout.log 2>&1 &

# 查看日志
tail -f ../../logs/web3_monitor/main.log
```

## 数据来源

| 数据 | 来源 | 限速 |
|------|------|------|
| Token 价格 | CoinGecko 免费 API | ~30 次/min |
| TVL / 收益 | DeFiLlama 免费 API | 无严格限速 |
| 预测市场 | Polymarket Gamma API | 无严格限速 |

## 扩展指南

- **新增监控 token**：在 `config.yaml` 的 `tokens.watchlist` 和 `crypto_id_map` 中添加
- **新增 DeFi 协议 TVL**：在 `config.yaml` 的 `defi.protocols` 中添加 DeFiLlama slug
- **新增 Polymarket 关键词**：在 `config.yaml` 的 `prediction.polymarket.keywords` 中添加
- **新增每周任务**：在 `config.yaml` 的 `tasks.items` 中添加
