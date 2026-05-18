# Finance Domain

Covers: portfolio monitoring, market signals, daily/pre-market reports, risk alerts, crypto movers.

## Key Agents

- `agents/finance_bot/` — portfolio monitor, APScheduler, LLM enrichment pipeline
- `agents/web3_monitor/` — CoinGecko Top-100 movers (migrated from finance_bot)

## Operational Rules

1. **No financial advice via Qwen.** All advisory content routes to CC (`FINANCIAL_ADVICE` task type).
2. **No dollar amounts in LLM prompts.** Pass % changes, labels, and ratios only.
3. **OutputGate is mandatory** for all LLM-generated content before Telegram delivery.
4. **Telegram sends are production actions** — never bypass `send()` with raw API calls.
5. **NAV and position data are private.** Never log in plaintext; never include in LLM prompts.
6. **Signal compute is rule-based only.** `SIGNAL_COMPUTE` task type → no LLM.
7. **All position config changes and NAV updates require explicit user approval.**

## LLM Routing (finance domain)

| Task | Tier | Notes |
|------|------|-------|
| Portfolio analysis / advice | CC | OutputGate: `FINANCIAL_ADVICE` |
| News curation | Qwen | OutputGate: `NEWS_CURATION` |
| Daily narrative snippet | Qwen | OutputGate: `REPORT_DRAFT` |
| Signal compute | Rule | No LLM |
| Alert throttle | Rule | No LLM |

## Observability

- Logs: `logs/finance_bot/`, `logs/web3_monitor/`
- PID files in respective log dirs
- Every LLM call logged with task type + OutputGate result

## Domain-Specific Constraints

- `shared/llm/model_router.py` is **CC-exclusive** — any change requires CC session + user confirmation
- `shared/llm/governance/output_gate.py` must not be bypassed or monkey-patched
- Positions defined in `agents/finance_bot/config.yaml` — changes require confirmation
- NAV base (`portfolio.nav_base`) updated monthly; USD/CNY rate updated as needed
- Crypto scan migrated to `agents/web3_monitor/` — do not re-add to finance_bot

## Scheduled Jobs (finance_bot)

| Job | Time (ET) | Days |
|-----|-----------|------|
| Pre-market report | 09:00 | Mon–Fri |
| Daily portfolio report | 16:30 | Mon–Fri |
| Intraday risk check | every 30 min | Mon–Fri market hours |
| Spike alert | event-driven | always |

## Project Skills

- `agents/finance_bot/SKILL.md`
- `agents/web3_monitor/SKILL.md`
