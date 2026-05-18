"""
Signal summarizer — Qwen plain-language explanations for signals.

GOVERNANCE NOTICE — CC-maintained invariant:
  signal_alerts in config.yaml MUST remain false.
  This module must NEVER be wired into:
    _high_freq_check, _mid_freq_check, _low_freq_check,
    _stock_scan, _asia_scan, _macro_scan, _macro_snapshot

This module exists for non-trading use cases only:
  - Post-hoc research notes
  - Weekly digest summaries (future)
  - Analyst review reports (future)

Trading signal determination remains rule-based and CC-governed.
Qwen outputs from this module carry source="qwen" and must pass OutputGate.

Python 3.9 compatible.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

from shared.llm.governance.output_gate import validate_safe
from shared.llm.interface import DraftOutput
from shared.llm.model_router import TaskType

logger = logging.getLogger("summarizer.signal")

_SYSTEM = (
    "你是市场信号解读助手。用简洁中文解释以下技术信号的含义（≤60字）。"
    "只描述信号的技术含义，不包含任何买卖建议。"
)


class SignalSummarizer:
    """
    Generates plain-language explanations of technical signals.
    NOT wired into any trading alert path — for research/digest use only.
    """

    def __init__(self, qwen_client):
        self._qwen = qwen_client

    def explain_inflection(self, symbol: str, direction: str, signals: list, score: float) -> Optional[str]:
        """
        Explain an inflection event in plain Chinese.
        Returns None on any error.
        """
        try:
            signal_names = ", ".join(s.label for s in signals[:3]) if signals else "综合信号"
            user = (
                f"标的: {symbol}\n"
                f"方向: {direction}\n"
                f"得分: {score:.1f}/10\n"
                f"触发信号: {signal_names}\n"
                "请用一句话解释此技术信号的含义。"
            )
            draft = DraftOutput(
                text=self._qwen.complete(system=_SYSTEM, user=user).text,
                source="qwen",
                model="qwen",
            )
            result = validate_safe(draft, TaskType.SIGNAL_EXPLAIN)
            if not result.passed:
                logger.warning("OutputGate rejected signal explanation: %s", result.rejection_reason)
                return None
            return result.output.text.strip()  # type: ignore[union-attr]
        except Exception as e:
            logger.debug("signal explain failed for %s: %s", symbol, e)
            return None
