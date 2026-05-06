# Finance Bot — Agent 定义

个人金融市场监控系统。**只监控，不交易**。通过 Telegram 推送价格突破、趋势拐点、期权信号和仓位风险提醒。

## 监控标的

| 频率 | 标的 | 用途 |
|------|------|------|
| 高频 3 min | BTC / ETH / WLD | 捕捉快速波动 |
| 中频 15 min | NVDA / TSLA / PL / PLTR / HIMS | 交易决策核心频率 |
| 低频 4 h | 全部标的 | 拐点深度扫描 |
| 宏观 24 h | VIX / SPY / QQQ | 每日市场状态快照 |

## 规则体系

- **A 价格** — 跌破/突破目标价、单日涨跌幅超阈值
- **B Alpha** — 相对 SPY/QQQ 20/60 日；相对 BTC 7/30 日
- **C 趋势** — MA20/50/200；跌破 MA200 高风险提醒
- **D 期权** — IV Rank、Covered Call / CSP 候选、财报日临近
- **E 市场风险** — VIX 高/极端、SPY/QQQ 从高点回撤
- **F 仓位风险** — 集中度、加密总占比、现金比例

## 路径

| 资源 | 路径 |
|------|------|
| 代码 | `/Volumes/AI_DISK/ai_workspace/agents/finance_bot/` |
| 配置 | `config.yaml` / `.env` |
| 数据库 | `/Volumes/AI_DISK/ai_workspace/data/market_data/finance_bot.db` |
| 市场数据 CSV | `/Volumes/AI_DISK/ai_workspace/data/market_data/` |
| 日志 | `/Volumes/AI_DISK/ai_workspace/logs/finance_bot/` |
| 个股参考资料 | `/Volumes/AI_DISK/ai_workspace/specs/finance/stocks/` |

## 生命周期

```bash
# 启动
cd /Volumes/AI_DISK/ai_workspace/agents/finance_bot
nohup .venv/bin/python main.py > ../../logs/finance_bot/stdout.log 2>&1 &

# 查看状态
ps aux | grep main.py | grep -v grep

# 停止
kill <PID>

# 查看实时日志
tail -f ../../logs/finance_bot/main.log
```

## 扩展指南

- **新增标的**：在 `config.yaml` 的 `assets` / `monitoring_frequency` 中添加
- **新增规则**：在 `rules/` 下创建文件，继承 `BaseRule`，在 `engine/inflection.py` 注册
- **调整阈值**：修改 `config.yaml` 中 `engine` / `scanner` 部分，无需重启即可热加载（重启生效）
