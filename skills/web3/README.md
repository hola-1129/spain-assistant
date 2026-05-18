# Web3 Domain

Covers: crypto market monitoring, DeFi strategy tracking, on-chain anomaly detection.

## Key Agents

- `agents/web3_monitor/` — CoinGecko Top-100 movers, DexScreener, DeFiLlama, Polymarket

## Operational Rules

1. **Wallet addresses are strictly private** — never log, output, or pass to any LLM.
2. **No on-chain transactions** may be initiated by any agent without explicit human confirmation.
3. **Price and signal compute is rule-based** — `SIGNAL_COMPUTE` task type, no LLM.
4. **DeFi research summarization** may use Qwen — no wallet context, no positions.
5. **`dry_run = true` is mandatory** in web3_monitor config; never disable without explicit approval.
6. **CoinGecko / DexScreener calls are rate-limited** — respect free tier limits; log all calls.

## LLM Routing (web3 domain)

| Task | Tier | Notes |
|------|------|-------|
| Signal scoring | Rule | No LLM |
| Research summarization | Qwen | No position/wallet context |
| Strategy decisions | CC | Requires explicit user initiation |

## Observability

- Logs: `logs/web3_monitor/`
- Signal log: `data/web3_monitor/signal_log.jsonl`
- DB: `data/web3_monitor/web3_monitor.db`
- Alert threshold: HIGH ≥ 80, MEDIUM ≥ 60 (per-symbol cooldown configurable)

## Domain-Specific Constraints

- Never store raw wallet private keys anywhere in the workspace
- All external RPC/API calls must be logged with response status (no sensitive params)
- Crypto scan interval in `finance_bot/config.yaml` must remain `0` (migrated to this agent)

## Project Skills

- `agents/web3_monitor/SKILL.md`
