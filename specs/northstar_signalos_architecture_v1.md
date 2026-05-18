# Northstar SignalOS — Multi-Model Governance Architecture v1

> Document date: 2026-05-10  
> Status: APPROVED DESIGN — pending phased implementation  
> Authority: Claude Code (CC) — Principal Architecture Agent

---

## 1. Current System Assessment

### 1.1 Codebase Inventory

| Agent | Path | LLM Usage Today | Status |
|-------|------|-----------------|--------|
| `finance_bot` | `agents/finance_bot/` | None — pure rule-based | Running |
| `web3_monitor` | `agents/web3_monitor/scripts/` | None — rule-based + MCP-ready tools | Running |
| `school_helper` | `agents/school_helper/` | Claude (Anthropic SDK, hard-coded) | CLI one-shot |
| `_template` | `agents/_template/` | Abstracted (Registry/Orchestrator) | Reference template |

### 1.2 Existing Infrastructure Strengths

- `shared/core/bus.py` — pub/sub message bus (asyncio, swappable to Redis/NATS)
- `shared/core/tool_registry.py` — tool invocation registry
- `shared/core/tracing.py` — distributed trace IDs
- `shared/core/envelope.py` — structured message envelope
- `_template/agent/orchestrator.py` — plan→dispatch→compose pattern (no business logic)
- `web3_monitor/scripts/mcp_tools/` — MCP-ready tool surface (market, signal, notify, review)
- `_template/mcp_server/` — MCP server scaffold

### 1.3 Current Architecture Gaps

| Gap | Risk | Priority |
|-----|------|----------|
| `school_helper/analyzer/llm_client.py` hardcodes Anthropic/Claude | Vendor lock-in, no fallback | High |
| No model router — no Qwen or Codex integration exists | Cannot route by cost/capability | High |
| Telegram pipeline is raw formatter code — no draft/validate stage | Quality not governed | Medium |
| No provider abstraction layer — each agent calls providers directly | Scattered access | High |
| Finance bot and web3_monitor produce all text in Python — no LLM-assisted summarization | No Qwen cost savings | Medium |
| No governance checkpoint before Telegram delivery | No CC safety gate | Medium |

### 1.4 What Must NOT Change

- `finance_bot/alerts/telegram_alert.py` — stable delivery endpoint, not touched
- `finance_bot/scheduler.py` — running production scheduler, only additive changes allowed
- `school_helper/output/` — git-tracked output repo, structure preserved
- `web3_monitor/scripts/mcp_tools/` — MCP tool contracts, backward-compatible only
- All `.env` files — never modified by this architecture

---

## 2. Recommended Directory Structure

### 2.1 New Shared Layer

```
ai_workspace/
└── shared/
    ├── core/                    # EXISTING — bus, registry, tracing, envelope
    └── llm/                     # NEW — unified LLM governance layer
        ├── __init__.py
        ├── interface.py         # UnifiedLLMClient protocol + base class
        ├── model_router.py      # CC-controlled routing decisions
        ├── providers/
        │   ├── __init__.py
        │   ├── anthropic_client.py   # Claude (CC tier)
        │   ├── qwen_client.py        # Qwen (low-cost tier)
        │   └── codex_client.py       # Codex/OpenAI (execution tier)
        ├── governance/
        │   ├── __init__.py
        │   ├── output_gate.py   # CC governance validation before delivery
        │   └── audit_log.py     # Immutable audit trail for all LLM outputs
        └── fallback.py          # Fallback chain logic
```

### 2.2 Finance Bot Additions (additive only)

```
agents/finance_bot/
├── [ALL EXISTING FILES UNTOUCHED]
└── summarizer/                  # NEW — Qwen-powered summary generation
    ├── __init__.py
    ├── signal_summarizer.py     # Qwen drafts of inflection/scanner alerts
    └── daily_report_drafter.py  # Qwen drafts for daily summary messages
```

### 2.3 Web3 Monitor Additions (additive only)

```
agents/web3_monitor/scripts/
├── [ALL EXISTING FILES UNTOUCHED]
└── summarizer/                  # NEW — Qwen pre-screening layer
    ├── __init__.py
    ├── signal_explainer.py      # Qwen natural-language explanation of signals
    └── project_screener.py      # Qwen web3 project pre-screening
```

### 2.4 School Helper Refactor (minimal)

```
agents/school_helper/analyzer/
├── llm_client.py                # EXISTING — will become thin wrapper
└── [NO OTHER CHANGES]
```

The `LLMClient` class becomes a thin shim that delegates to `shared/llm/interface.py`.

### 2.5 New Governance Spec Files

```
ai_workspace/specs/
├── northstar_signalos_architecture_v1.md   # THIS FILE
└── llm_routing_rules_v1.md                 # Routing decision table (maintained by CC)
```

---

## 3. CC / Codex / Qwen Responsibility Matrix

### 3.1 System-Level Roles

| Dimension | CC (Claude Code) | Codex | Qwen |
|-----------|-----------------|-------|------|
| Architecture decisions | ✅ Sole authority | ❌ | ❌ |
| Security review | ✅ Sole authority | ❌ | ❌ |
| Production approval | ✅ Sole authority | ❌ | ❌ |
| Governance enforcement | ✅ Sole authority | ❌ | ❌ |
| MCP design & approval | ✅ Sole authority | ❌ | ❌ |
| Feature implementation | Review only | ✅ Primary | ❌ |
| Bug fixes (scoped) | Review only | ✅ Primary | ❌ |
| Tests & type-checking | Review only | ✅ Primary | ❌ |
| Formatters / boilerplate | Review only | ✅ Primary | ❌ |
| Text summarization (bulk) | ❌ | ❌ | ✅ Primary |
| Draft generation | ❌ | ❌ | ✅ Primary |
| Translation | ❌ | ❌ | ✅ Primary |
| Classification (low-risk) | ❌ | ❌ | ✅ Primary |
| Signal explanation drafts | ❌ | ❌ | ✅ Primary |
| Final trading signals | ✅ System rules | ❌ | ❌ |

### 3.2 Telegram Pipeline Roles

| Stage | Responsible Model | Notes |
|-------|------------------|-------|
| Raw data collection | No LLM | Existing fetchers |
| Signal computation | No LLM | Existing engines |
| Natural-language draft | **Qwen** | Optional enrichment layer |
| Rule-based filter | No LLM | Existing throttle/cooldown |
| Formatter assembly | No LLM / **Codex** | Existing formatters; Codex for new ones |
| Governance gate | **CC rules** | `output_gate.py` — static rules first, CC on ambiguity |
| Delivery | No LLM | Existing `telegram_alert.py` — UNTOUCHED |

---

## 4. Qwen-Compatible Modules

These modules are safe for Qwen to process. All are low-risk, high-volume text tasks where a draft is acceptable and final validation is handled by rules or CC.

| Module | Agent | Qwen Task | Draft or Final? |
|--------|-------|-----------|-----------------|
| `scanner/daily_summary.py` | finance_bot | Enrich daily summary with narrative context | Draft |
| `scanner/macro_scanner.py` | finance_bot | Generate plain-language macro explanation | Draft |
| `monitors/portfolio_formatter.py` | finance_bot | Narrative summary of portfolio movements | Draft |
| `china_fund_engine/reporter.py` | finance_bot | Translate/localize China fund close report | Draft |
| `mcp_tools/notify_tools.py` | web3_monitor | Natural-language signal explanation | Draft |
| `scripts/cross_signal_engine.py` | web3_monitor | Pre-screening narrative for cross-signals | Draft |
| `analyzer/extractor.py` | school_helper | ES/EN/ZH event summarization | Draft → validated by extract rules |
| `renderers/summary_writer.py` | school_helper | Parent-friendly weekly summary | Draft |
| `renderers/markdown_writer.py` | school_helper | Child-friendly event explanations | Draft |
| Log summarization | all agents | Compress error logs into human summaries | Final (non-critical) |

**Qwen output contract:** All Qwen outputs are typed as `DraftOutput` with a `source="qwen"` tag. They must never be delivered to Telegram directly without passing through `output_gate.py`.

---

## 5. Codex-Compatible Modules

These modules are engineering tasks — clearly bounded, testable, reversible. CC assigns; Codex executes.

| Module | Agent | Codex Task |
|--------|-------|-----------|
| `alerts/telegram_alert.py` wrappers | finance_bot | New formatter functions (HTML mode, message splitting) |
| `telegram_notify.py` | web3_monitor | Multi-format message rendering, Markdown escaping |
| `shared/llm/providers/qwen_client.py` | shared | Implementation of Qwen API client |
| `shared/llm/providers/codex_client.py` | shared | Implementation of Codex/OpenAI API client |
| `shared/llm/fallback.py` | shared | Fallback chain implementation |
| `shared/llm/governance/audit_log.py` | shared | Structured audit logging |
| `summarizer/` (any agent) | all | Boilerplate summarizer scaffolding |
| Test files (`tests/`) | all | Unit tests for new summarizer and router modules |
| `renderers/html_writer.py` improvements | school_helper | Layout/styling updates |
| `parsers/pdf_reader.py` enhancements | school_helper | OCR pipeline, additional PDF formats |
| `renderers/ics_writer.py` | school_helper | New ICS fields, timezone handling |

**Codex task contract:** All Codex tasks must have a defined input/output contract (typed), a test file, and a size limit of ≤300 lines changed per task. CC reviews diffs before merge.

---

## 6. CC-Exclusive Modules

These modules must only be modified by CC. They represent governance boundaries, security surfaces, or system-wide orchestration logic.

| Module | Reason |
|--------|--------|
| `shared/llm/model_router.py` | Routing decisions are architecture — CC sole authority |
| `shared/llm/governance/output_gate.py` | Output governance policy — CC sole authority |
| `shared/llm/interface.py` | Provider abstraction contract — CC designs |
| `shared/core/bus.py` | Cross-agent message bus — CC controls protocol |
| `shared/core/tool_registry.py` | Tool registry — CC controls registration |
| `agents/_template/agent/orchestrator.py` | Canonical orchestration pattern — CC maintains |
| `AI_WORKFLOW_RULES.md` | Governance rules document — CC updates |
| Any `.env` file | Security boundary — never modified by any model |
| `finance_bot/alerts/telegram_alert.py` | Production delivery — CC controls change authority |
| `web3_monitor/scripts/core/config.py` | Runtime configuration — CC approves changes |

---

## 7. `model_router.py` Design

**Location:** `shared/llm/model_router.py`  
**Authority:** CC-exclusive — no Codex/Qwen modifications permitted

```python
# shared/llm/model_router.py
"""
Model routing table for Northstar SignalOS.

Routing decisions are CC-governed. To add or change a route, update this file
via a CC-reviewed change only. No automated mutation permitted.

Route priority: task_type → urgency → token_budget → fallback_tier
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Literal


class ModelTier(str, Enum):
    CC       = "cc"        # Claude Code tier — architecture, governance, reasoning
    CODEX    = "codex"     # Codex/OpenAI tier — engineering execution
    QWEN     = "qwen"      # Qwen tier — low-cost bulk processing
    RULE     = "rule"      # No LLM — handled by deterministic rules


class TaskType(str, Enum):
    # CC-exclusive tasks
    ARCHITECTURE      = "architecture"
    SECURITY_REVIEW   = "security_review"
    GOVERNANCE_GATE   = "governance_gate"
    PRODUCTION_APPROVAL = "production_approval"
    MCP_DESIGN        = "mcp_design"
    SIGNAL_FINAL      = "signal_final"       # Final trading signal determination

    # Codex tasks
    FEATURE_IMPL      = "feature_impl"
    BUG_FIX           = "bug_fix"
    TEST_CREATION     = "test_creation"
    FORMATTER_IMPL    = "formatter_impl"
    BOILERPLATE       = "boilerplate"

    # Qwen tasks
    SUMMARIZE_BULK    = "summarize_bulk"
    TRANSLATE         = "translate"
    TELEGRAM_DRAFT    = "telegram_draft"
    CLASSIFY_LOW_RISK = "classify_low_risk"
    LOG_COMPRESS      = "log_compress"
    SIGNAL_EXPLAIN    = "signal_explain"
    SCHOOL_EXTRACT    = "school_extract"
    REPORT_DRAFT      = "report_draft"

    # Rule-based (no LLM)
    SIGNAL_COMPUTE    = "signal_compute"
    ALERT_THROTTLE    = "alert_throttle"
    DATA_FETCH        = "data_fetch"


# Routing table: TaskType → ModelTier
# CC retains override authority over any entry in this table.
ROUTING_TABLE: dict[TaskType, ModelTier] = {
    # CC exclusive
    TaskType.ARCHITECTURE:          ModelTier.CC,
    TaskType.SECURITY_REVIEW:       ModelTier.CC,
    TaskType.GOVERNANCE_GATE:       ModelTier.CC,
    TaskType.PRODUCTION_APPROVAL:   ModelTier.CC,
    TaskType.MCP_DESIGN:            ModelTier.CC,
    TaskType.SIGNAL_FINAL:          ModelTier.CC,

    # Codex
    TaskType.FEATURE_IMPL:          ModelTier.CODEX,
    TaskType.BUG_FIX:               ModelTier.CODEX,
    TaskType.TEST_CREATION:         ModelTier.CODEX,
    TaskType.FORMATTER_IMPL:        ModelTier.CODEX,
    TaskType.BOILERPLATE:           ModelTier.CODEX,

    # Qwen
    TaskType.SUMMARIZE_BULK:        ModelTier.QWEN,
    TaskType.TRANSLATE:             ModelTier.QWEN,
    TaskType.TELEGRAM_DRAFT:        ModelTier.QWEN,
    TaskType.CLASSIFY_LOW_RISK:     ModelTier.QWEN,
    TaskType.LOG_COMPRESS:          ModelTier.QWEN,
    TaskType.SIGNAL_EXPLAIN:        ModelTier.QWEN,
    TaskType.SCHOOL_EXTRACT:        ModelTier.QWEN,
    TaskType.REPORT_DRAFT:          ModelTier.QWEN,

    # Rule-based
    TaskType.SIGNAL_COMPUTE:        ModelTier.RULE,
    TaskType.ALERT_THROTTLE:        ModelTier.RULE,
    TaskType.DATA_FETCH:            ModelTier.RULE,
}


@dataclass
class RouteDecision:
    task_type: TaskType
    tier: ModelTier
    model_id: str
    fallback_tier: ModelTier | None


# Model IDs — updated by CC when providers change
MODEL_IDS: dict[ModelTier, str] = {
    ModelTier.CC:    "claude-sonnet-4-6",
    ModelTier.CODEX: "gpt-4o",
    ModelTier.QWEN:  "qwen-plus",         # or qwen-turbo for max cost savings
    ModelTier.RULE:  "__rule_based__",
}

FALLBACK_CHAIN: dict[ModelTier, ModelTier | None] = {
    ModelTier.CC:    None,          # CC has no fallback — fail explicitly
    ModelTier.CODEX: ModelTier.CC,  # Codex fails → escalate to CC
    ModelTier.QWEN:  ModelTier.CC,  # Qwen fails → escalate to CC (not Codex)
    ModelTier.RULE:  None,
}


def route(task_type: TaskType) -> RouteDecision:
    tier = ROUTING_TABLE.get(task_type, ModelTier.CC)
    return RouteDecision(
        task_type=task_type,
        tier=tier,
        model_id=MODEL_IDS[tier],
        fallback_tier=FALLBACK_CHAIN[tier],
    )
```

---

## 8. `qwen_client.py` Design

**Location:** `shared/llm/providers/qwen_client.py`  
**Implementation by:** Codex (Codex task: `TaskType.BOILERPLATE`)  
**Review by:** CC before merge

```python
# shared/llm/providers/qwen_client.py
"""
Qwen API client for Northstar SignalOS.

Constraints:
- Qwen may ONLY be used for TaskTypes in the QWEN tier (see model_router.py)
- Outputs are always tagged DraftOutput(source="qwen")
- Qwen must never receive: secrets, credentials, trading decisions, repo access
- Max input: 32k tokens; outputs > 2k tokens are anomalies and should be logged

Provider: Alibaba Cloud DashScope (openai-compatible endpoint)
Fallback: If Qwen fails, router escalates to CC — see fallback.py
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from openai import OpenAI, APIError   # DashScope is OpenAI-compatible
from shared.llm.interface import LLMResponse, DraftOutput


DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


@dataclass
class QwenConfig:
    api_key: str
    model: str = "qwen-plus"
    max_tokens: int = 2048
    temperature: float = 0.3
    timeout: float = 30.0
    max_retries: int = 3


class QwenClient:
    def __init__(self, cfg: QwenConfig):
        self._cfg = cfg
        self._client = OpenAI(
            api_key=cfg.api_key,
            base_url=DASHSCOPE_BASE_URL,
            timeout=cfg.timeout,
        )

    def complete(self, system: str, user: str) -> DraftOutput:
        last_err: Exception | None = None
        for attempt in range(1, self._cfg.max_retries + 1):
            try:
                resp = self._client.chat.completions.create(
                    model=self._cfg.model,
                    max_tokens=self._cfg.max_tokens,
                    temperature=self._cfg.temperature,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user},
                    ],
                )
                text = resp.choices[0].message.content or ""
                return DraftOutput(text=text, source="qwen", model=self._cfg.model)
            except APIError as e:
                last_err = e
                time.sleep(min(2 ** attempt, 8))
        raise RuntimeError(f"Qwen failed after {self._cfg.max_retries} attempts: {last_err}")
```

---

## 9. Unified LLM Interface Design

**Location:** `shared/llm/interface.py`  
**Authority:** CC-exclusive

```python
# shared/llm/interface.py
"""
Unified LLM interface protocol for Northstar SignalOS.

All model clients must implement LLMClient protocol.
All outputs are typed: DraftOutput (Qwen) or ValidatedOutput (CC-gated).
No raw strings should cross agent boundaries — always use these types.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, Literal


@dataclass
class DraftOutput:
    text: str
    source: Literal["qwen", "codex", "claude", "rule"]
    model: str
    validated: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass
class ValidatedOutput:
    text: str
    source: str
    model: str
    validated: bool = True
    gate_passed: bool = True
    metadata: dict = field(default_factory=dict)


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> DraftOutput: ...


class GovernanceGate(Protocol):
    def validate(self, draft: DraftOutput) -> ValidatedOutput: ...
```

---

## 10. Fallback Strategy Design

**Location:** `shared/llm/fallback.py`  
**Authority:** CC-exclusive

```
Fallback Chain:

Qwen fails  →  log warning  →  escalate to CC with full context
                              (never silently drop; always log + notify)

Codex fails →  log warning  →  escalate to CC for review
                              (CC decides: retry, redesign, or skip)

CC fails    →  log critical →  use rule-based fallback if available
                              →  skip and alert operator via Telegram
                              →  never produce unvalidated output

Rule fails  →  log error    →  skip signal; never substitute LLM
```

**Key principle:** Fallback escalation flows UP the governance hierarchy, never DOWN. Qwen never falls back to a lower-quality model — it escalates to CC. This preserves the governance invariant.

---

## 11. Telegram Pipeline Redesign

### 11.1 Current State

```
Fetchers → Engine → Formatters → TelegramAlert.send()
```

All text is generated deterministically in Python. No LLM involvement. This is STABLE and should not be broken.

### 11.2 Target State (additive, non-breaking)

```
Fetchers → Engine → Formatters → [OPTIONAL: Qwen Draft Enrichment]
                                → OutputGate (CC governance rules)
                                → TelegramAlert.send()   ← UNCHANGED
```

### 11.3 Implementation Notes

The Qwen draft enrichment layer is **opt-in per job type**. Configuration flag:

```yaml
# In config.yaml for each agent
llm_enrichment:
  daily_summary: true       # Qwen drafts narrative context
  signal_alerts: false      # Rule-based only — Qwen NOT used for trading signals
  portfolio_report: true    # Qwen enriches with narrative
  china_close: true         # Qwen translates/localizes
  macro_snapshot: false     # Rule-based — no LLM
  school_notifications: true  # Qwen ES/EN/ZH summary
```

**Invariant:** `signal_alerts` and all final trading signal messages MUST remain `false`. Qwen never participates in trading decision output. CC-governed rule system remains sole authority.

### 11.4 OutputGate Rules (static, CC-maintained)

```python
# output_gate.py validates DraftOutput before Telegram delivery
# Rules applied in order — any REJECT blocks delivery

GATE_RULES = [
    "no_api_keys",          # reject if any key-like pattern found
    "no_wallet_addresses",  # reject if crypto wallet address found  
    "no_school_pii",        # reject if child name / school info detected
    "length_limit_4096",    # Telegram message limit
    "no_financial_advice",  # reject advisory language ("you should buy...")
    "no_unvalidated_trading_signal",  # reject if source=qwen AND signal_type=trading
]
```

---

## 12. School Notification Agent Redesign

### 12.1 Current LLM Usage

`school_helper/analyzer/llm_client.py` hardcodes Anthropic Claude. This is the ONLY agent currently using an LLM.

### 12.2 Migration Path (minimal-change)

**Phase 1 (immediate):** Make `LLMClient` accept a provider parameter that defaults to the existing Anthropic client. Zero behavior change.

```python
# Modified school_helper/analyzer/llm_client.py
class LLMClient:
    def __init__(self, cfg: dict):
        provider = cfg.get("llm", {}).get("provider", "anthropic")
        if provider == "qwen":
            from shared.llm.providers.qwen_client import QwenClient, QwenConfig
            self._delegate = QwenClient(QwenConfig(api_key=cfg["qwen_api_key"]))
        else:
            # existing Anthropic logic unchanged
            ...
```

**Phase 2:** Route specific tasks to Qwen via `model_router.py`:
- `TaskType.SCHOOL_EXTRACT` → Qwen (event extraction, summarization)
- `TaskType.TRANSLATE` → Qwen (ES→ZH→EN)

**CC-only tasks remain with Claude:**
- Final almanac logic (fetch_week_almanac)
- Weather integration governance
- Output validation

### 12.3 Qwen Prompt Contract for School Tasks

Qwen receives only:
- Sanitized text from PDFs (no URLs, no credentials)
- Structured extraction prompts
- Language translation prompts

Qwen never receives:
- Student names or grades beyond what's needed for classification
- Family configuration data
- Output file paths

---

## 13. MCP Governance Strategy

### 13.1 Current MCP Infrastructure

- `web3_monitor/scripts/mcp_tools/` — 4 tool namespaces (market, signal, notify, review)
- `web3_monitor/scripts/mcp_tool_registry.py` — registration
- `_template/mcp_server/server.py` — server scaffold
- `shared/core/tool_registry.py` — shared registry

### 13.2 MCP Governance Rules

```
MCP Tool Registration:
  → CC must approve any new MCP tool registration
  → Security review required for tools that access: filesystem, network, secrets, DB
  → All MCP tools must declare: name, description, input_schema, access_level

Access Levels:
  READ_PUBLIC   → Qwen may consume outputs
  READ_PRIVATE  → CC only may consume outputs (finance data, school data)  
  WRITE_LOCAL   → CC approval required; Codex may implement
  WRITE_REMOTE  → CC sole authority; requires explicit session approval

Qwen MCP Access:
  PERMITTED:  READ_PUBLIC market data outputs, summarization inputs
  FORBIDDEN:  Any PRIVATE data, WRITE operations, credential-bearing tools

Codex MCP Access:
  PERMITTED:  Implement tool handlers, write tests, update schemas
  FORBIDDEN:  Approve new tools, modify access_level declarations, deploy to production
```

### 13.3 Future MCP Server Architecture

```
MCP Server Layer:
  web3_monitor_mcp/      → market data tools (READ_PUBLIC)
  finance_mcp/           → portfolio tools (READ_PRIVATE, CC-gated)
  school_mcp/            → school event tools (READ_PRIVATE, CC-gated)
  governance_mcp/        → CC audit/review tools (CC-exclusive)
```

---

## 14. Provider Abstraction Strategy

### 14.1 OpenRouter Evaluation

| Dimension | OpenRouter | Direct APIs | Hybrid (Recommended) |
|-----------|-----------|-------------|---------------------|
| Reliability | Medium (proxy layer risk) | High (direct) | High |
| Cost | Variable (markup on some) | Pay per API | Optimized per provider |
| Fallback | Built-in (some models) | Manual fallback.py | Manual but controlled |
| MCP compatibility | Unknown/untested | Yes (direct) | Yes |
| Vendor lock-in | High (single gateway) | Medium (per provider) | Low |
| Secret exposure | High (all keys via one endpoint) | Contained | Contained |
| Multi-model orchestration | Limited | Full control | Full control |
| Long-term maintainability | Low (external dependency) | High | High |

**Recommendation: Do NOT adopt OpenRouter at this time.**

Reasons:
1. Single point of failure for all LLM traffic
2. All API keys route through a third-party — security risk
3. Loss of per-call governance (cannot intercept for output gate)
4. Insufficient MCP integration track record
5. Adds proxy latency to all model calls

### 14.2 Adopted Architecture: Direct APIs + Provider Abstraction

```
shared/llm/
├── interface.py           # Protocol contracts (LLMClient, GovernanceGate)
├── model_router.py        # Routing table (CC-controlled)
├── fallback.py            # Escalation logic
├── providers/
│   ├── anthropic_client.py  # Direct Anthropic SDK
│   ├── qwen_client.py       # Direct DashScope (OpenAI-compatible)
│   └── codex_client.py      # Direct OpenAI API
└── governance/
    ├── output_gate.py       # CC rule-based gate
    └── audit_log.py         # Append-only audit trail
```

This gives:
- Full control over routing, fallback, governance
- No external dependency for orchestration
- Per-provider API key isolation
- Auditable output trail
- Swap any provider without changing agent code

### 14.3 Future Local Model Compatibility

The `QwenClient` uses the OpenAI-compatible interface. Any local model (Ollama, llama.cpp) that serves an OpenAI-compatible endpoint can be swapped in by changing `DASHSCOPE_BASE_URL` and the API key — zero agent code changes required.

---

## 15. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Qwen produces incorrect financial narrative | Medium | Low (draft only, gate blocks delivery) | `output_gate.py` + `signal_alerts: false` |
| Qwen leaks school PII | Low (PDF text only) | High | `no_school_pii` gate rule; Qwen never receives config/paths |
| Fallback escalation floods CC context | Low | Medium | Rate-limit fallback escalations; log-only threshold |
| Codex makes architecture change | Low (procedural risk) | High | CC-exclusive file list; no Codex PR without CC review |
| Provider API key exposure | Low | Critical | Keys in `.env` only; provider clients read env at init |
| finance_bot Telegram disruption | Low | High | `telegram_alert.py` untouched; enrichment is opt-in |
| OpenRouter adoption without evaluation | Mitigated | High | Explicitly deferred in this document |
| model_router.py drift (unauthorized changes) | Low | High | CC-exclusive file + governance note in file header |

---

## 16. Minimal-Change Migration Roadmap

### Phase 0 — Foundation (CC designs, Codex implements)

**Goal:** Create the shared LLM layer. Zero agent behavior changes.

| # | Task | Assignee | Files Created |
|---|------|----------|---------------|
| 0.1 | Create `shared/llm/` directory structure | CC design + Codex impl | `interface.py`, `model_router.py` stubs, `fallback.py` |
| 0.2 | Implement `qwen_client.py` | Codex | `providers/qwen_client.py` |
| 0.3 | Implement `anthropic_client.py` (wraps existing) | Codex | `providers/anthropic_client.py` |
| 0.4 | Implement `output_gate.py` static rules | Codex impl, CC spec | `governance/output_gate.py` |
| 0.5 | Implement `audit_log.py` | Codex | `governance/audit_log.py` |
| 0.6 | Tests for all Phase 0 modules | Codex | `shared/llm/tests/` |

**Confirmation required from CC before Phase 1.**

### Phase 1 — School Helper Migration (lowest risk, isolated)

**Goal:** school_helper uses the unified LLM layer. Behavior identical; routing governed.

| # | Task | Assignee | Files Modified |
|---|------|----------|----------------|
| 1.1 | Add provider abstraction to `llm_client.py` | Codex (thin wrapper) | `school_helper/analyzer/llm_client.py` |
| 1.2 | Route `SCHOOL_EXTRACT` tasks to Qwen via config flag | Codex | `school_helper/config.py`, `llm_client.py` |
| 1.3 | Validate output through `output_gate.py` | Codex impl, CC config | `school_helper/analyzer/llm_client.py` |
| 1.4 | Test with `--no-llm` guard intact | Codex | `school_helper/tests/` |

**Validation:** Run school_helper end-to-end with both `provider: anthropic` and `provider: qwen`. Output diff must be functionally equivalent (structure, not exact text).

### Phase 2 — Finance Bot Enrichment (additive only)

**Goal:** Add Qwen draft layer for daily_summary and portfolio_report. All signal alerts remain rule-based.

| # | Task | Assignee | Files Created/Modified |
|---|------|----------|----------------------|
| 2.1 | Create `finance_bot/summarizer/daily_report_drafter.py` | Codex | New file |
| 2.2 | Create `finance_bot/summarizer/signal_summarizer.py` | Codex | New file |
| 2.3 | Add `llm_enrichment` config section to `config.yaml` | Codex | `finance_bot/config.yaml` (additive) |
| 2.4 | Wire `_daily_summary()` in scheduler to call drafter (optional) | Codex impl, CC review | `scheduler.py` (minimal) |
| 2.5 | Wire `_portfolio_daily_report()` to call enricher | Codex impl, CC review | `scheduler.py` (minimal) |

**Invariant:** `_high_freq_check`, `_mid_freq_check`, `_low_freq_check`, `_stock_scan` — NO LLM wiring. Ever.

### Phase 3 — Web3 Monitor Enrichment (additive only)

**Goal:** Qwen pre-screens and explains web3 signals before Telegram dispatch.

| # | Task | Assignee | Files Created |
|---|------|----------|---------------|
| 3.1 | Create `web3_monitor/scripts/summarizer/signal_explainer.py` | Codex | New file |
| 3.2 | Create `web3_monitor/scripts/summarizer/project_screener.py` | Codex | New file |
| 3.3 | Add optional `enrich_signal()` call in `agent_orchestrator.py` | Codex impl, CC review | `agent_orchestrator.py` (additive) |

### Phase 4 — MCP Server Scaffold (future)

**Goal:** Wrap existing agent capabilities as MCP tools with governance.

Deferred pending Phase 0–3 stability. CC designs MCP server contracts; Codex implements.

---

## 17. Files to Create

```
shared/llm/__init__.py
shared/llm/interface.py
shared/llm/model_router.py
shared/llm/fallback.py
shared/llm/providers/__init__.py
shared/llm/providers/anthropic_client.py
shared/llm/providers/qwen_client.py
shared/llm/providers/codex_client.py
shared/llm/governance/__init__.py
shared/llm/governance/output_gate.py
shared/llm/governance/audit_log.py
agents/finance_bot/summarizer/__init__.py
agents/finance_bot/summarizer/signal_summarizer.py
agents/finance_bot/summarizer/daily_report_drafter.py
agents/web3_monitor/scripts/summarizer/__init__.py
agents/web3_monitor/scripts/summarizer/signal_explainer.py
agents/web3_monitor/scripts/summarizer/project_screener.py
specs/llm_routing_rules_v1.md
```

---

## 18. Files That Must Remain Untouched

The following files have production stability guarantees and must not be modified
without explicit CC authorization and user confirmation:

```
agents/finance_bot/alerts/telegram_alert.py          # Production delivery endpoint
agents/finance_bot/scheduler.py                      # Running scheduler — additive only
agents/finance_bot/engine/inflection.py              # Core signal engine
agents/finance_bot/engine/cross_asset.py             # Core signal engine
agents/finance_bot/engine/regime.py                  # Core signal engine
agents/web3_monitor/scripts/mcp_tools/*.py           # MCP tool contracts
agents/web3_monitor/scripts/core/config.py           # Runtime config loader
agents/web3_monitor/scripts/storage.py               # Signal store
shared/core/bus.py                                   # Message bus protocol
shared/core/tool_registry.py                         # Tool registry
shared/core/tracing.py                               # Trace ID generation
agents/school_helper/output/                         # Git-tracked output repo
AI_WORKFLOW_RULES.md                                 # Governance rules
Any .env file                                        # Secrets — never touched
```

---

## 19. Governance Enforcement Summary

```
┌─────────────────────────────────────────────────────────────┐
│                    CC (Claude Code)                         │
│  Architecture · Security · Governance · Production Approval │
│  model_router.py · output_gate.py · interface.py            │
└───────────────┬─────────────────────────────────────────────┘
                │ designs & approves
    ┌───────────┴──────────┐
    │                      │
┌───▼───────────┐    ┌────▼──────────────┐
│    Codex      │    │      Qwen          │
│  Engineering  │    │   Low-cost Layer   │
│  Execution    │    │   Draft Generator  │
│               │    │                    │
│ feature_impl  │    │ summarize_bulk     │
│ bug_fix       │    │ telegram_draft     │
│ test_creation │    │ translate          │
│ formatter     │    │ signal_explain     │
│ boilerplate   │    │ school_extract     │
└───────────────┘    └────────────────────┘
         │                    │
         └────────┬───────────┘
                  │ all outputs
         ┌────────▼────────────┐
         │   output_gate.py    │  ← CC-governed static rules
         └────────┬────────────┘
                  │ validated outputs only
         ┌────────▼────────────┐
         │  telegram_alert.py  │  ← UNTOUCHED production delivery
         └─────────────────────┘
```

**Invariants that must never be violated:**
1. Qwen never directly calls `telegram_alert.py`
2. Trading signal alerts (`signal_alerts: false`) bypass Qwen entirely
3. `model_router.py` is CC-exclusive — no automated mutation
4. All Qwen outputs carry `DraftOutput(source="qwen", validated=False)` until gate-cleared
5. Fallback always escalates UP (never down to a lower-governance model)
6. No API key, secret, or `.env` value ever passes as prompt context to any model

---

*End of Architecture Document v1*  
*Next review: After Phase 1 completion or if provider landscape changes significantly.*  
*CC authority: All sections. Modification requires CC session + user confirmation.*
