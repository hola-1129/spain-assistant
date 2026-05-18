# SKILL: polymarket_intelligence

> Read-only Polymarket intelligence monitor. Fetches public market data, detects rapid probability repricing and liquidity spikes, scores events, and sends Telegram alerts for high-signal markets. Never executes trades or connects wallets.

---

## Purpose

Monitor Polymarket prediction markets for statistically significant probability moves and liquidity changes. Score signals and alert Leslie via Telegram when score exceeds threshold. Designed as an intelligence radar — not a trading bot.

## Inputs

| Input | Type | Source | Required |
|-------|------|--------|----------|
| Config | YAML | `config.yaml` | yes |
| Polymarket Gamma API | REST API | public, unauthenticated | yes |
| Polymarket CLOB API | REST API | public, unauthenticated | no (graceful fallback) |
| Telegram credentials | env | `.env` | yes (for alerts) |

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| HIGH signal alerts | Telegram message | score ≥ signal_alert_threshold (default 75) |
| Market snapshots | SQLite rows | `storage/intelligence.db` |
| Signal events | SQLite rows + CSV | `storage/intelligence.db` + `logs/signal_events.csv` |
| Runtime logs | Log file + stdout | `ai_workspace/logs/polymarket_intelligence/` |
| PID file | Text | `ai_workspace/logs/polymarket_intelligence/polymarket_intelligence.pid` |

## Workflow

```
Startup:
  load config → write PID → init DB → enter poll loop

Each cycle (poll_interval_seconds):
  1. Fetch active markets from Gamma API
  2. Filter: volume, liquidity, ignored keywords
  3. For each market:
     a. Upsert market metadata to SQLite
     b. Try CLOB orderbook (non-blocking, fallback to Gamma prices)
     c. Build snapshot → save to market_snapshots
     d. Compare with recent snapshots → detect signals
     e. Score each signal (0–100, capped)
     f. If score >= threshold → send Telegram alert
        (dry_run=true → log only, no actual send)
  4. Sleep poll_interval_seconds → repeat
```

## Signal Types

| Signal | Trigger | Base Score |
|--------|---------|------------|
| rapid_reprice_5m | YES price moves ≥5% in 5m | 35 |
| rapid_reprice_15m | YES price moves ≥8% in 15m | 30 |
| rapid_reprice_60m | YES price moves ≥12% in 60m | 25 |
| liquidity_spike | Liquidity ≥1.5× and +$10k in one cycle | 20 |

Score modifiers: +20 priority keyword, +10 high volume, +10 high liquidity, +10 tight spread, −20 wide spread, −20 low volume, −15 closing within 6h. Final score capped at 100.

## Tool Usage Policy

| Tool / API | Usage | Approval |
|------------|-------|----------|
| Polymarket Gamma API | read-only, public | auto |
| Polymarket CLOB API | read-only, public | auto |
| Telegram Bot API | send message (or dry_run log) | auto |
| SQLite | local writes | auto |

## Constraints

- NO wallet connection
- NO private keys
- NO authenticated trading APIs
- NO order placement
- `dry_run: true` by default — must be explicitly set to `false` in config to enable live Telegram sends
- All API calls have timeout + retry (tenacity)
- Single market failure never crashes the loop

## Start Command

```bash
cd agents/polymarket_intelligence && .venv/bin/python main.py
```

Background:
```bash
cd agents/polymarket_intelligence && nohup .venv/bin/python main.py \
  > ../../logs/polymarket_intelligence/stdout.log 2>&1 \
  & echo $! > ../../logs/polymarket_intelligence/polymarket_intelligence.pid
```
