# Education Domain

Covers: school schedule extraction, weekly briefing generation, calendar export, parent communication.

## Key Agents

- `agents/school_helper/` — one-shot CLI; PDF → Chinese weekly report + ICS calendar + static site

## Operational Rules

1. **Children's data is strictly private** — never commit, log publicly, or expose in LLM prompts beyond task scope.
2. **School documents are confidential** — treat as PII; process locally only; no cloud upload without consent.
3. **No autonomous communication** with school systems, email, or forms without explicit user approval.
4. **Output scope**: structured summaries only; raw document content must not appear in logs or outputs beyond generated files.
5. **Google Drive links are private** — never expose in any public context.
6. LLM tier: Qwen for `SCHOOL_EXTRACT`; CC for decisions involving legal/financial/enrollment implications.

## LLM Routing (education domain)

| Task | Tier | Notes |
|------|------|-------|
| PDF extraction / OCR post-processing | Qwen | `SCHOOL_EXTRACT` |
| Weekly briefing draft | Qwen | No child names in output |
| Enrollment / legal decisions | CC | Requires user initiation |

## Observability

- CLI output is primary observability (no persistent daemon)
- `output/processing_log.txt` — per-run processing log (git-ignored)
- Errors surface immediately; no silent skip

## Domain-Specific Constraints

- `output/cache/` is git-ignored — downloaded PDFs stay local
- `output/` static site is published to GitHub Pages (public) — ensure no PII leaks into HTML
- Do not cache raw school documents in `data/` without explicit user consent
- `processing_log.txt` is git-ignored

## Project Skills

- `agents/school_helper/SKILL.md`
