# MCP-Ready Architecture

Web3 Monitor is organized as a tool-first, MCP-ready personal research agent.
It remains read-only: no wallet, no signing, no trading, no Polymarket orders.

## Design Rules

1. Core abilities are modular functions.
2. Each tool accepts JSON-style `payload: dict`.
3. Each tool returns a JSON-style dict:

```python
{
  "ok": True,
  "tool": "tool_name",
  "data": {},
  "signals": [],
  "errors": [],
  "meta": {}
}
```

4. `main.py` is only an entrypoint.
5. `agent_orchestrator.py` schedules and composes tools.
6. Data sources, scoring, risk, persistence, notifications, and review stay decoupled.
7. Future MCP Server can import `mcp_tool_registry.TOOL_REGISTRY`.

## Directory Layout

```text
scripts/
├── main.py                  # CLI entrypoint only
├── agent_orchestrator.py    # orchestration only
├── mcp_tool_registry.py     # tool registry for future MCP server
├── core/
│   ├── models.py            # ToolContext / ToolResult
│   ├── config.py            # config, logging, runtime guards
│   └── state.py             # runtime_state JSON
├── mcp_tools/
│   ├── market_tools.py      # DEX, CoinGecko, GeckoTerminal, DeFiLlama, Polymarket
│   ├── signal_tools.py      # persistence and queries
│   ├── notify_tools.py      # Telegram
│   └── review_tools.py      # review summaries
└── ...
```

## Current Tool Registry

- `scan_dex_anomalies`
- `scan_market_movers`
- `scan_new_pools`
- `get_macro_snapshot`
- `scan_prediction_markets`
- `persist_signal`
- `get_recent_signals`
- `get_signal_by_id`
- `get_score_summary`
- `get_review_summary`
- `send_telegram_alert`

## Multi-Agent Interfaces

Future agents should interact through tools, not internal modules:

- Research Agent: `get_recent_signals`, `get_signal_by_id`, `get_score_summary`
- Review Agent: `get_review_summary`, future `review_pending_signals`
- Notification Agent: `send_telegram_alert`
- Monitor Agent: `scan_*`, `persist_signal`

All agents share SQLite as the durable read model and `runtime_state.json` as
short-lived scan state.

## MCP Server Sketch

An MCP server can:

1. Build `ToolContext` with config, services, store, telegram, runtime state.
2. Loop over `TOOL_REGISTRY`.
3. Expose each callable as an MCP tool.
4. Validate payloads at the server boundary.
5. Keep `.env` values private and never return them.
