# SKILL: school_helper

> One-shot CLI that converts weekly school PDFs into a Chinese parent briefing, ICS calendar, and static site. Run manually; not a persistent service.

---

## Purpose

Parse the Spanish school's weekly *Briefing Semanal* PDF (Spanish/English) and produce: Chinese summary, ICS calendar files, and a self-contained static HTML site for GitHub Pages. Does NOT communicate with school systems or send messages autonomously.

## Inputs

| Input | Type | Source | Required |
|-------|------|--------|----------|
| Briefing PDF | file | `input/` directory | yes |
| API key | env | `.env` (ANTHROPIC_API_KEY) | yes |
| Optional linked PDFs | URL | extracted from main PDF | no |

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| `index.html` | static site | `output/` → GitHub Pages |
| `school_events.ics` | calendar | `output/` |
| `events/NN-slug.ics` | per-event calendar | `output/events/` |
| `weekly_briefing_cn.md` | Chinese markdown | `output/` |
| `weekly_briefing_summary.txt` | short WeChat version | `output/` |
| `extracted_links.json` | link inventory | `output/` |
| `processing_log.txt` | run log | `output/` (git-ignored) |
| `archive/<YYYY-Www>/` | previous week | `output/archive/` |

## Workflow

```
1. Place PDF in input/
2. Run: .venv/bin/python main.py
3. Extract text + links from PDF (pdfplumber / pdf2image + OCR)
4. Download linked event PDFs → cache/
5. LLM extraction: parse events, dates, actions (SCHOOL_EXTRACT → Qwen)
6. Generate Chinese briefing (CC for advice; Qwen for translation)
7. Generate ICS files (deterministic)
8. Generate static HTML (deterministic)
9. Archive previous output
10. Print summary to stdout
```

Invariant: Output files never contain raw document content; only structured summaries.

## Tool Usage Policy

| Tool / API | Usage | Approval |
|------------|-------|----------|
| Anthropic Claude | SCHOOL_EXTRACT, structured output | auto |
| PDF/OCR libraries | local processing | auto |
| GitHub Pages deploy | publish output/ | manual (user-initiated) |
| School portal URLs | read-only fetch | auto |

## Approval Boundaries

Actions requiring explicit user confirmation:
- [ ] Publishing to GitHub Pages (user runs `git push` manually)
- [ ] Saving documents to `data/` (outside `cache/`)
- [ ] Any automated email or form submission

## Observability

- `output/processing_log.txt` — per-run log (git-ignored)
- Errors surface as stdout/stderr immediately
- No persistent daemon; no background jobs

## Failure Handling

| Failure | Behavior |
|---------|----------|
| PDF parse error | log + exit with clear error message |
| Linked PDF download failure | log URL as failed in `extracted_links.json`, continue |
| LLM extraction failure | log + surface to user; do not silently produce empty output |
| Duplicate week detection | auto-archive previous, re-run cleanly |

## Security Constraints

- No child names, school addresses, or parent contact info in LLM prompts
- `output/cache/` is git-ignored — cached PDFs stay local
- `processing_log.txt` is git-ignored
- GitHub Pages output (index.html) must be reviewed before push to ensure no PII leaks

## Token Discipline

- LLM tier: Qwen for `SCHOOL_EXTRACT` (bulk text parsing)
- CC for any reasoning involving family decisions or enrollment advice
- Estimated tokens per run: ~2000–4000 (Qwen); ~500 (CC, if used)

## Related Files

```
agents/school_helper/main.py
agents/school_helper/input/         # PDFs placed here
agents/school_helper/output/        # Generated site + ICS
agents/school_helper/output/cache/  # Downloaded PDFs (git-ignored)
agents/school_helper/.env
skills/education/README.md
```

## MCP Coordination

- Depends on: local PDFs, Anthropic API (optional Qwen)
- Produces for: Leslie + family via GitHub Pages
- Shared state: none (each run is independent)

## Rollback Strategy

Each run archives the previous week automatically to `output/archive/<YYYY-Www>/`. To restore previous output:
```bash
cp -r output/archive/<YYYY-Www>/* output/
```

## Operational Philosophy

- One-shot tool: run it, review output, then decide whether to publish
- Human reviews GitHub Pages content before every push
- Children's privacy is non-negotiable; when in doubt, exclude from output
