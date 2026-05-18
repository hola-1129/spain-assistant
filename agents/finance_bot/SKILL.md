# SKILL: finance_bot

> Persistent portfolio monitor and market signal system. Sends daily/pre-market reports and risk alerts via Telegram. Monitors only — never trades.

---

## Purpose

Monitor Leslie's multi-broker stock portfolio and selected market signals. Deliver structured Telegram reports on schedule and event-driven alerts on anomalies. Does NOT execute trades or manage orders.

## Inputs

| Input | Type | Source | Required |
|-------|------|--------|----------|
| Portfolio positions | YAML config | `config.yaml` → `portfolio.positions` | yes |
| Market prices | yfinance API | live / prev_close | yes |
| LLM enrichment config | YAML | `config.yaml` → `llm_enrichment` | no |
| API keys | env | `.env` (TELEGRAM, ANTHROPIC, QWEN) | yes |

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| Pre-market report | Telegram message | 09:00 ET Mon–Fri |
| Daily portfolio report | Telegram message | 16:30 ET Mon–Fri |
| Risk alerts | Telegram message | event-driven |
| Spike alerts | Telegram message | event-driven (>5% intraday) |
| Market data | SQLite + CSV | `data/market_data/` |

## Workflow

```
Startup:
  load config.yaml → init APScheduler → register jobs → block

Pre-market (09:00 ET):
  1. Fetch current prices via yfinance
  2. Compute PositionResult for each position
  3. format_premarket_report() → Telegram send
  4. [if enrichment.premarket_report] build_news_section() → send
  5. [if enrichment.premarket_report] build_advice_premarket() → send

Daily close (16:30 ET):
  1. Fetch prices + prev_close via yfinance
  2. Compute PositionResult for each position
  3. format_daily_portfolio_report() → Telegram send
  4. [if enrichment.portfolio_report] build_news_section() → send
  5. [if enrichment.portfolio_report] build_advice_close() → send

Risk check (every 30 min, market hours):
  1. Fetch prices
  2. Evaluate risk flags per position
  3. If flagged: format_portfolio_risk_alert() → send (with cooldown)

Spike alert (event-driven):
  1. Intraday price delta > spike_threshold_pct
  2. format_position_spike_alert() → send (with cooldown)
```

Invariant: Telegram delivery is never blocked by LLM failure. All LLM calls degrade gracefully to raw formatted output.

## Tool Usage Policy

| Tool / API | Usage | Approval |
|------------|-------|----------|
| yfinance | read-only price data | auto |
| Telegram Bot API | scheduled + event sends | auto |
| Qwen (DashScope) | news curation, narrative | auto (OutputGate governs) |
| Anthropic Claude | portfolio advice | auto (OutputGate governs, CC-exclusive task type) |
| SQLite | read/write market data | auto |

## Approval Boundaries

Actions requiring explicit user confirmation:
- [ ] Position changes in `config.yaml`
- [ ] NAV base update (`portfolio.nav_base`)
- [ ] USD/CNY rate update (`portfolio.usd_cny_rate`)
- [ ] `.env` modification
- [ ] Any change to `shared/llm/model_router.py`
- [ ] Any change to `shared/llm/governance/output_gate.py`

## Observability

- Logs: `logs/finance_bot/stdout.log`, `logs/finance_bot/error.log`
- PID file: `logs/finance_bot/finance_bot.pid`
- LLM calls logged with: `[QWEN]` or `[CC]` prefix, task type, gate result, output length
- OutputGate rejections logged with rejection reason

## Failure Handling

| Failure | Behavior |
|---------|----------|
| yfinance timeout | retry 2×, then skip position, log warning |
| Qwen API failure | log warning, skip enrichment, send raw report |
| Claude API failure | log warning, skip advice section, send raw report |
| OutputGate rejection | log reason, skip LLM section, use original formatted message |
| Telegram send failure | log error, retry once, do not crash scheduler |

## Security Constraints

- No dollar amounts in LLM prompts — % changes, labels, ratios only
- No wallet addresses, API keys, or personal names in LLM inputs or outputs
- OutputGate validates all LLM output before Telegram delivery
- `FINANCIAL_ADVICE` is CC-exclusive task type — Qwen must not handle it

## Token Discipline

- Qwen: `REPORT_DRAFT`, `NEWS_CURATION` — ~200–400 tokens/call
- Claude: `FINANCIAL_ADVICE` — ~600–1000 tokens/call
- Excluded from LLM context: absolute dollar values, cost basis amounts, account balances

## Related Files

```
agents/finance_bot/main.py
agents/finance_bot/config.yaml
agents/finance_bot/scheduler.py
agents/finance_bot/monitors/portfolio_monitor.py
agents/finance_bot/monitors/portfolio_formatter.py
agents/finance_bot/summarizer/daily_report_drafter.py
agents/finance_bot/alerts/telegram_alert.py
shared/llm/model_router.py
shared/llm/governance/output_gate.py
skills/finance/README.md
```

## MCP Coordination

- Depends on: yfinance (external), Telegram Bot API (external), Qwen API, Anthropic API
- Produces for: Leslie via Telegram (no downstream agents)
- Shared state: `data/market_data/finance_bot.db` (read by future analytics agents)

## Rollback Strategy

Config rollback:
```bash
git checkout -- agents/finance_bot/config.yaml
```

Process restart:
```bash
kill $(cat logs/finance_bot/finance_bot.pid)
cd /Volumes/AI_DISK/ai_workspace/agents/finance_bot
nohup .venv/bin/python main.py > ../../logs/finance_bot/stdout.log 2>&1 &
echo $! > ../../logs/finance_bot/finance_bot.pid
```

## Operational Philosophy

- Telegram delivery is the only hard requirement; everything else degrades gracefully
- OutputGate is the trust boundary between LLM output and production Telegram
- Never modify `alerts/telegram_alert.py` core send logic without explicit approval
- `model_router.py` is CC-exclusive — routing changes require CC session + user confirmation
