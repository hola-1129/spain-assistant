# SKILL: [Agent / Project Name]

> One-line description of what this skill/agent does and its scope boundary.

---

## Purpose

What problem this agent solves. What it explicitly does NOT do.

## Inputs

| Input | Type | Source | Required |
|-------|------|--------|----------|
| ... | str/float/file | config / env / CLI arg | yes/no |

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| ... | Telegram msg / file / DB row | ... |

## Workflow

```
1. [Startup / init]
2. [Main loop or one-shot action]
3. [LLM enrichment if applicable]
4. [Output / delivery]
5. [Cleanup / log]
```

Invariant: [what must remain true at every step — e.g., "Telegram is never blocked by LLM failure"]

## Tool Usage Policy

| Tool / API | Usage | Approval |
|------------|-------|----------|
| yfinance | read-only market data | auto |
| Telegram Bot API | send messages | auto (scheduled) / manual (ad-hoc) |
| OpenAI / Qwen / Anthropic | LLM calls | auto (governed by OutputGate) |

## Approval Boundaries

Actions requiring explicit user confirmation before execution:
- [ ] Position config changes (`config.yaml`)
- [ ] `.env` modifications
- [ ] Schema changes to SQLite DB

## Observability

- Logs: `logs/<agent_name>/stdout.log`, `logs/<agent_name>/error.log`
- PID file: `logs/<agent_name>/<agent_name>.pid`
- Key metrics: LLM call count, Telegram sends, fetch errors per run

## Failure Handling

| Failure | Behavior |
|---------|----------|
| API timeout | retry N times, then log + skip |
| LLM failure | graceful degradation — send raw formatted output |
| Data fetch error | log + send alert to Telegram, do not send stale data silently |
| OutputGate rejection | log rejection reason, fall back to original message |

## Security Constraints

- Secrets in `.env` only; never in code or logs
- LLM inputs: no dollar amounts, no full names — use % changes, labels, ratios
- No wallet addresses, API keys, or personal data in any LLM prompt or output

## Token Discipline

- LLM tier: CC / Qwen / Rule (per `model_router.py`)
- Estimated tokens per run: ~N
- Excluded from LLM context: [dollar amounts / raw positions / personal identifiers]

## Related Files

```
agents/<name>/main.py
agents/<name>/config.yaml
agents/<name>/.env
skills/<domain>/README.md
shared/llm/model_router.py
shared/llm/governance/output_gate.py
```

## MCP Coordination

How this agent interacts with other agents or future MCP tools:
- Depends on: [none / list]
- Produces for: [none / list]
- Shared state: none / [description]

## Rollback Strategy

Config rollback:
```bash
git checkout -- agents/<name>/config.yaml
```

Code rollback:
```bash
git checkout -- agents/<name>/<file>
```

Data rollback: SQLite WAL journal; CSV snapshots in `data/market_data/`.

## Operational Philosophy

- Telegram delivery is never blocked by LLM failure (graceful degradation always)
- Human approval required for all irreversible actions
- Prefer additive changes over destructive rewrites
