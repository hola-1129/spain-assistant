"""Build and send the daily Telegram brief (summary + URL only).

The brief is intentionally short — full content lives in the HTML report.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Ensure shared.utils is importable when called from an agent
_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

from shared.utils.telegram import TelegramNotifier

from .base_report import ReportData
from .paths import daily_index_url

logger = logging.getLogger("reporting.telegram_summary")

_AGENT_EMOJI = {
    "finance_bot": "📈",
    "ai_narrative_rotation_radar": "🧭",
    "polymarket_intelligence": "🎯",
    "web3_monitor": "⛓",
}

_RISK_EMOJI = {
    "low": "🟢",
    "medium": "🟡",
    "high": "🟠",
    "critical": "🔴",
}

_OPP_EMOJI = {
    "none": "",
    "low": "",
    "medium": "💡",
    "high": "💡💡",
}

_SEP = "━" * 28


def build_brief(
    date: str,
    reports: List[ReportData],
    cross_summary: str = "",
    risk_items: Optional[List[str]] = None,
    opportunity_items: Optional[List[str]] = None,
) -> str:
    """Return the Telegram brief text (≤800 chars). Never truncates — callers ensure inputs fit."""
    lines = [
        f"📊 *Daily Intelligence Brief｜{date}*",
        _SEP,
    ]

    if cross_summary:
        lines += [cross_summary, ""]

    # Per-agent one-liners
    for r in reports:
        emoji = _AGENT_EMOJI.get(r.meta.agent, "•")
        risk_e = _RISK_EMOJI.get(r.meta.risk_level, "")
        opp_e = _OPP_EMOJI.get(r.meta.opportunity_level, "")
        label = r.meta.agent.replace("_", "\\_")
        summary = r.meta.summary or "—"
        lines.append(f"{emoji} *{label}*：{summary} {risk_e}{opp_e}")

    lines.append("")

    # Risk bullets (max 2)
    if risk_items:
        lines.append("⚠️ *风险*")
        for item in risk_items[:2]:
            lines.append(f"- {item}")
        lines.append("")

    # Opportunity bullets (max 2)
    if opportunity_items:
        lines.append("💡 *机会*")
        for item in opportunity_items[:2]:
            lines.append(f"- {item}")
        lines.append("")

    lines.append(f"👉 [完整日报]({daily_index_url(date)})")

    return "\n".join(lines)


def send_brief(
    brief: str,
    notifier: TelegramNotifier,
) -> bool:
    """Send the brief. Returns True on success."""
    ok = notifier.send(brief, parse_mode="Markdown")
    if ok:
        logger.info("Daily brief sent")
    else:
        logger.error("Daily brief send failed")
    return ok
