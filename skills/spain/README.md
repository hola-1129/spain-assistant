# Spain Domain

Covers: Spanish life logistics — residency, NIE/TIE, banking, school enrollment, local services, travel.

## Key Agents

- `agents/travel_assistant/` — planned; not yet built

## Operational Rules

1. **Personal location and residency data are private** — never expose in logs, LLM prompts, or any output file.
2. **Document processing** (NIE, TIE, passport, school enrollment forms) — local only; no cloud upload without consent.
3. **Deadlines are hard** — flag bureaucratic deadlines prominently; never let them slip silently.
4. **No automatic form submission or appointment booking** without explicit user approval.
5. **Location data** (home address, passport number, NIE number) must not appear in any LLM input.
6. LLM tier: Qwen for translation/summarization; CC for decisions involving legal, financial, or enrollment implications.

## LLM Routing (spain domain)

| Task | Tier | Notes |
|------|------|-------|
| Document translation (ES/EN → CN) | Qwen | No personal identifiers |
| Deadline extraction from notices | Qwen | Summarize dates/actions only |
| Residency / legal decision-making | CC | User-initiated only |

## Observability

- No persistent daemon currently; all tasks are one-shot CLI
- Deadlines tracked manually in `tasks/personal/`

## Domain-Specific Constraints

- Do not cache government documents in `data/` without explicit consent
- All external service integrations (appointment portals, banking APIs) require explicit approval before implementation
- Treat all family members' data with the same privacy level as Leslie's own

## Project Skills

- `agents/travel_assistant/SKILL.md` — to be created when agent is built
