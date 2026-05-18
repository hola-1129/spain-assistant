"""
CC-EXCLUSIVE — do not modify without CC session + user confirmation.

OutputGate: governance checkpoint for all LLM outputs before delivery.

Every DraftOutput must pass through this gate before reaching:
  - Telegram delivery (telegram_alert.py)
  - Any external system
  - Any persistent storage that feeds delivery pipelines

Gate rules are evaluated in order. Any REJECT blocks delivery.
Rules are static and CC-maintained — no dynamic rule loading.

Invariants enforced here:
  1. Qwen outputs tagged source="qwen" with signal_type="trading" are always rejected
  2. CC-exclusive task types with non-CC source are rejected
  3. API key patterns are rejected unconditionally
  4. Messages exceeding Telegram length limit are rejected (caller should split first)
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass

from shared.llm.interface import DraftOutput, ValidatedOutput
from shared.llm.model_router import CC_EXCLUSIVE_TASKS, TaskType

logger = logging.getLogger("signalos.llm.output_gate")


class GateRejection(ValueError):
    """Raised when a draft fails the output gate."""
    def __init__(self, rule: str, reason: str):
        self.rule = rule
        self.reason = reason
        super().__init__(f"[{rule}] {reason}")


# ── Compiled patterns ─────────────────────────────────────────────────────────

# API key / token patterns
_API_KEY_RE = re.compile(
    r"(sk-[A-Za-z0-9\-_]{20,}"          # OpenAI / Anthropic style
    r"|Bearer\s+[A-Za-z0-9\-_\.]{10,}"  # Bearer token
    r"|api[_\-]?key[\"'\s:=]+[A-Za-z0-9\-_]{16,}"  # api_key = ...
    r"|token[\"'\s:=]+[A-Za-z0-9\-_]{20,}"          # token = ...
    r")",
    re.IGNORECASE,
)

# Crypto wallet addresses
_ETH_WALLET_RE  = re.compile(r"\b0x[0-9a-fA-F]{40}\b")
_BTC_WALLET_RE  = re.compile(r"\b(bc1[a-z0-9]{6,87}|[13][a-zA-Z0-9]{25,34})\b")

# Financial advisory language patterns (advisory to end users — not analytical statements)
_ADVICE_RE = re.compile(
    r"\b(you should (buy|sell|invest|exit|enter)"
    r"|i (strongly )?recommend (buying|selling|investing)"
    r"|this is (a buy|a sell|financial advice)"
    r"|consider (buying|selling) now)\b",
    re.IGNORECASE,
)

# Telegram hard limit
_TELEGRAM_MAX_CHARS = 4096


@dataclass
class GateResult:
    passed: bool
    output: ValidatedOutput | None
    rejection_rule: str | None = None
    rejection_reason: str | None = None


def validate(draft: DraftOutput, task_type: TaskType | None = None) -> ValidatedOutput:
    """
    Validate a DraftOutput against all gate rules.
    Returns ValidatedOutput on success.
    Raises GateRejection on first failed rule.

    Callers should catch GateRejection and handle gracefully
    (log, skip delivery, alert operator).
    """
    _check_cc_exclusive_task(draft, task_type)
    _check_unvalidated_trading_signal(draft, task_type)
    _check_api_keys(draft)
    _check_wallet_addresses(draft)
    _check_financial_advice(draft)
    _check_length(draft)

    return ValidatedOutput(
        text=draft.text,
        source=draft.source,
        model=draft.model,
        validated=True,
        gate_passed=True,
        metadata={**draft.metadata, "gate": "passed"},
    )


def validate_safe(draft: DraftOutput, task_type: TaskType | None = None) -> GateResult:
    """Non-raising variant. Returns GateResult with passed=False on rejection."""
    try:
        output = validate(draft, task_type)
        return GateResult(passed=True, output=output)
    except GateRejection as e:
        logger.warning("OutputGate rejected draft. rule=%s reason=%s source=%s",
                       e.rule, e.reason, draft.source)
        return GateResult(passed=False, output=None,
                          rejection_rule=e.rule, rejection_reason=e.reason)


# ── Individual rule checks ─────────────────────────────────────────────────────

def _check_cc_exclusive_task(draft: DraftOutput, task_type: TaskType | None) -> None:
    if task_type is None:
        return
    if task_type in CC_EXCLUSIVE_TASKS and draft.source != "claude":
        raise GateRejection(
            "cc_exclusive_task",
            f"task_type={task_type.value} requires CC source, got source={draft.source}",
        )


def _check_unvalidated_trading_signal(draft: DraftOutput, task_type: TaskType | None) -> None:
    is_qwen = draft.source == "qwen"
    is_trading = (
        draft.metadata.get("signal_type") == "trading"
        or task_type == TaskType.SIGNAL_FINAL
    )
    if is_qwen and is_trading:
        raise GateRejection(
            "no_unvalidated_trading_signal",
            "Qwen output must never carry trading signal metadata",
        )


def _check_api_keys(draft: DraftOutput) -> None:
    if _API_KEY_RE.search(draft.text):
        raise GateRejection(
            "no_api_keys",
            "Draft contains pattern matching API key or token — rejected unconditionally",
        )


def _check_wallet_addresses(draft: DraftOutput) -> None:
    if _ETH_WALLET_RE.search(draft.text) or _BTC_WALLET_RE.search(draft.text):
        raise GateRejection(
            "no_wallet_addresses",
            "Draft contains crypto wallet address pattern",
        )


def _check_financial_advice(draft: DraftOutput) -> None:
    if _ADVICE_RE.search(draft.text):
        raise GateRejection(
            "no_financial_advice",
            "Draft contains financial advisory language directed at end user",
        )


def _check_length(draft: DraftOutput) -> None:
    if len(draft.text) > _TELEGRAM_MAX_CHARS:
        raise GateRejection(
            "length_limit_4096",
            f"Draft length {len(draft.text)} exceeds Telegram limit {_TELEGRAM_MAX_CHARS}. "
            "Split before passing to gate.",
        )
