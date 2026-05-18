# MCP Plan

v2 已把核心能力拆成可包装的函数，未来可以直接暴露为 MCP tools。
详细架构见 `docs/MCP_ARCHITECTURE.md`。

## Candidate Tools

- `scan_dex_anomalies(payload)`
  - 扫描配置资产的 DEX 异动。

- `scan_market_movers(payload)`
  - 扫描 CoinGecko Top-100 market movers。

- `scan_new_pools(payload)`
  - 扫描 GeckoTerminal 新池子。

- `scan_prediction_markets(payload)`
  - 扫描 Polymarket 事件概率和成交量变化。

- `get_macro_snapshot(payload)`
  - 读取 DeFiLlama 链 TVL 快照。

- `persist_signal(payload)`
  - 写 JSONL + SQLite。

- `get_recent_signals(limit=50)`
  - 读取最近信号，适合 Dashboard、聊天查询、移动端摘要。

- `get_signal_by_id(signal_id)`
  - 查看单条信号详情和原始数据。

- `get_score_summary()`
  - 按 source / signal_type 聚合评分与复盘表现。

- `send_telegram_alert(text)`
  - 手动发送只读提醒，不包含任何交易能力。

- `run_monitor_once()`
  - 手动触发一次扫描。MCP 化时建议封装成更细的 service 函数，避免依赖 CLI 参数。

## Security Rules

- MCP tools 不得读取 `.env` 内容并返回给用户。
- 不暴露任何私钥、助记词、交易账户。
- 不加入交易、签名、授权、撤单、下单工具。
- 所有工具只读或只发送提醒。
- 所有工具统一 `payload: dict -> JSON dict`，未来 MCP Server 只做薄包装。

## Future Dashboard Flow

```text
SQLite signals
  -> tools.py functions
  -> MCP server tools
  -> personal dashboard / mobile UI / Codex queries
```
