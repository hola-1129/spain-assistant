# SKILL: web3_monitor

> Crypto market monitoring agent. Scans CoinGecko Top-100, DexScreener, DeFiLlama, and Polymarket for anomalies. Sends scored alerts via Telegram. Read-only — never executes transactions.

---

## Purpose

Identify significant price moves, volume spikes, TVL changes, and event probability shifts in crypto markets. Score signals and alert Leslie via Telegram when score exceeds threshold. Does NOT execute trades, hold wallets, or interact with smart contracts.

## Inputs

| Input | Type | Source | Required |
|-------|------|--------|----------|
| Watchlist / config | YAML | `config.yaml` | yes |
| CoinGecko data | REST API | live | yes |
| DexScreener data | REST API | live | no |
| DeFiLlama data | REST API | live | no |
| Polymarket data | REST API | live | no |
| API keys | env | `.env` (TELEGRAM) | yes |

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| HIGH signal alerts | Telegram message | score ≥ 80 |
| MEDIUM signal alerts | Telegram message | score ≥ 60 |
| Signal log | JSONL | `data/web3_monitor/signal_log.jsonl` |
| DB records | SQLite | `data/web3_monitor/web3_monitor.db` |

## Workflow

```
Startup:
  load config → init scheduler → register scan jobs → block

CoinGecko scan (interval per config):
  1. Fetch Top-100 market data
  2. Score each asset (price change, volume, market cap delta, 7d alpha)
  3. Apply per-symbol cooldown filter
  4. Score ≥ 80: send HIGH alert via Telegram
  5. Score ≥ 60: log MEDIUM signal
  6. Write all signals to JSONL + SQLite

DexScreener / DeFiLlama / Polymarket scans (separate intervals):
  1. Fetch target data
  2. Score anomalies
  3. Alert if above threshold
```

Invariant: `dry_run = true` is always active; no on-chain actions ever taken.

## Tool Usage Policy

| Tool / API | Usage | Approval |
|------------|-------|----------|
| CoinGecko API | read-only, rate-limited | auto |
| DexScreener API | read-only | auto |
| DeFiLlama API | read-only | auto |
| Polymarket API | read-only | auto |
| Telegram Bot API | sends | auto (score-gated) |
| SQLite | write signals | auto |

## Approval Boundaries

Actions requiring explicit user confirmation:
- [ ] Disabling `dry_run` in config
- [ ] Adding on-chain transaction capability
- [ ] Wallet address configuration
- [ ] `.env` modification

## Observability

- Logs: `logs/web3_monitor/stdout.log`, `logs/web3_monitor/error.log`
- PID file: `logs/web3_monitor/web3_monitor.pid`
- Signal log: `data/web3_monitor/signal_log.jsonl`
- Alert sent / suppressed (cooldown) logged per symbol

## Failure Handling

| Failure | Behavior |
|---------|----------|
| API rate limit | backoff + retry, log warning |
| API timeout | skip this scan cycle, log |
| Telegram send failure | log error, retry once, continue |
| Scoring error | log + skip symbol, do not crash |

## Security Constraints

- No wallet private keys anywhere in workspace
- No wallet addresses in any LLM prompt or log output
- All external API calls logged with status (no auth params)
- `dry_run = true` must remain enabled; modifying requires explicit confirmation

## Token Discipline

- Signal scoring is rule-based (`SIGNAL_COMPUTE`) — no LLM
- Research summarization uses Qwen (`SUMMARIZE_BULK`) — no position/wallet context
- LLM calls: only on explicit user request for research tasks

## Related Files

```
agents/web3_monitor/main.py
agents/web3_monitor/config.yaml
agents/web3_monitor/.env
data/web3_monitor/signal_log.jsonl
data/web3_monitor/web3_monitor.db
skills/web3/README.md
```

## MCP Coordination

- Depends on: CoinGecko, DexScreener, DeFiLlama, Polymarket (all external, read-only)
- Produces for: Leslie via Telegram
- Shared state: signal DB can be read by future analytics agents

## Rollback Strategy

```bash
git checkout -- agents/web3_monitor/config.yaml

# Restart:
kill $(cat logs/web3_monitor/web3_monitor.pid)
cd /Volumes/AI_DISK/ai_workspace/agents/web3_monitor
nohup .venv/bin/python main.py > ../../logs/web3_monitor/stdout.log 2>&1 &
echo $! > ../../logs/web3_monitor/web3_monitor.pid
```

## Operational Philosophy

- Read-only posture: monitor and alert, never act
- `dry_run = true` is a safety invariant, not a feature flag
- Score threshold gates protect against alert fatigue
