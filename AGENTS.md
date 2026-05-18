# AGENTS.md — Global Governance

All AI agents operating in this workspace (Claude, Codex, Qwen, or rule-based) must comply with this file.
This is the authoritative source for engineering rules, security policy, and multi-LLM coordination.

---

## 1. Multi-LLM Role Definitions

| Tier | Role | Handles |
|------|------|---------|
| **CC (Claude)** | Architecture · Reasoning · Orchestration | Design, review, complex debug, security, final decisions |
| **Codex** | Runtime Worker · Batch Executor | Boilerplate, CRUD, formatters, tests, long-running tasks |
| **Qwen** | Low-cost Execution | README, JSON schema, Telegram formatting, summarization, news curation |
| **Rule** | Deterministic | Signal compute, alert throttle, data fetch |

CC retains override authority on all tier boundaries.

**CC does NOT handle:** README, JSON schema, config boilerplate, Telegram formatting, simple CRUD, small wrappers.

Authoritative routing table: `shared/llm/model_router.py` (CC-exclusive file — changes require CC session + user confirmation).

---

## 2. Engineering Execution Rules (R1–R17)

> Caution over speed on non-trivial work.

| Rule | Description |
|------|-------------|
| **R1 Think First** | State assumptions; ask when uncertain; stop when confused |
| **R2 Simplicity** | Minimum code; no speculative features; no single-use abstractions |
| **R3 Surgical Changes** | Touch only what's necessary; no unrelated cleanup |
| **R4 Goal-Driven** | Define success criteria before coding; iterate until verified |
| **R5 Use LLMs Correctly** | LLM for reasoning/classification; deterministic code for exact math/state |
| **R6 Token Budget** | ~4k/task, ~30k/session; checkpoint and summarize on overrun |
| **R7 Surface Conflicts** | If patterns conflict, pick one, explain, flag alternative |
| **R8 Read Before Write** | Check exports, callers, shared utils before changing anything |
| **R9 Tests Verify Intent** | Tests cover business intent, not just implementation |
| **R10 Checkpoint Progress** | After major steps: changed / verified / risks / next |
| **R11 Respect Conventions** | Conform to existing style; discuss concerns separately |
| **R12 Fail Loud** | Never silently skip tests, validations, or failures |
| **R13 No Blind Overwrites** | Identify what works; additive over destructive; keep rollback simple |
| **R14 Deps Are Liabilities** | Check existing stack first; justify every new dependency |
| **R15 Preserve Observability** | Never remove logs/metrics/health checks without explicit request |
| **R16 One Agent One Responsibility** | Each agent: clear scope, defined I/O, minimal shared state |
| **R17 Human Approval for Irreversible Actions** | Require explicit confirmation before: deletes, config overwrites, secret rotation, deploys, financial changes, external comms |

**Standard execution protocol (non-trivial tasks):**
1. Understand current system
2. Define success criteria
3. Identify affected files/services
4. Make smallest viable change
5. Verify locally
6. Summarize results and risks
7. Suggest next steps only if necessary

---

## 3. Security Rules

**Prohibited:**
- API key or token in any code file
- Secrets committed to any repo
- Sensitive data in log output (API keys, auth headers, wallet addresses, bearer tokens)

**Required:**
- Secrets in `.env` only — never hardcoded
- `.gitignore` must include: `.env`, `.env.*`, `logs/`, `*.log`, `*.pem`, `*.key`, `secrets/`
- Logs must redact: API keys, Authorization headers, Bearer tokens, webhook URLs, wallet addresses

---

## 4. Repository Rules

Default posture: **private family AI agent project**

Never expose: school/children's data, financial positions, wallet addresses, personal locations, Google Drive private links.
Default: private repo. Never push to public without explicit approval.

---

## 5. MCP / Future Compatibility

All core functionality must be:
- Tool-based design with JSON structured I/O
- Low coupling; independently testable
- Encapsulatable as MCP tools in the future

Avoid: monolithic `main.py`, hard-coded workflows, strong inter-agent coupling.

---

## 6. Approval Gates

Require **explicit user confirmation** before:
- File or branch deletion
- Database schema changes
- `.env` modification or secret rotation
- Force push, rebase, or `git reset --hard`
- CI/CD pipeline changes
- Production Telegram sends (outside scheduled jobs)
- Financial config changes (positions, NAV base)
- Any external API call that creates, modifies, or deletes records

When in doubt: ask, don't act.

---

## 7. CC Notification Protocol

### 7.1 Before any Qwen call:

```
────────────────────────────────
🤖 QWEN 调用
任务类型 : <TaskType>
Agent    : <agent 名称>
输入摘要 : <传给 Qwen 的内容摘要，不含敏感数据>
敏感检查 : ✓ 无 API key / 钱包 / 姓名 / 金额
────────────────────────────────
```

After completion:

```
────────────────────────────────
✅ QWEN 返回  /  ❌ QWEN 失败（降级为原始内容）
OutputGate : 通过 / 拒绝（原因：...）
内容预览  : <前 60 字符>
────────────────────────────────
```

### 7.2 Before any Codex task handoff:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 CODEX TASK：<任务名>
TaskType：<FEATURE_IMPL / BUG_FIX / TEST_CREATION / ...>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【目标】<1-3 句说明期望结果>
【允许修改的文件】<绝对路径列表>
【禁止修改的文件】.env / shared/llm/model_router.py / <其他>
【期望输出】<函数签名 / 行为>
【测试命令】<完整可执行命令>
【回滚方式】git checkout -- <文件路径>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

CC review outcome: `✅ APPROVED` / `❌ REJECTED` (reason + restore cmd) / `🔄 NEEDS_REVISION` (specific issues)

---

## 8. Observability Requirements

Every agent must:
- Write structured logs to `logs/<agent_name>/`
- Log all external API calls (redacted)
- Log all LLM calls with task type and gate result
- Maintain a PID file: `logs/<agent_name>/<agent_name>.pid`
- Retain logs 30 days minimum

---

## Related Files

- `CLAUDE.md` — Claude-specific context: agent table, startup sequence, skill-loading workflow
- `README_WORKFLOW.md` — Workspace workflow, task loading, execution standards
- `AI_WORKFLOW_RULES.md` — Legacy multi-LLM routing reference (superseded by this file + `model_router.py`)
- `shared/llm/model_router.py` — Authoritative LLM routing table (CC-exclusive)
- `templates/SKILL_TEMPLATE.md` — Standard structure for agent SKILL.md files
