"""Polymarket-specific Telegram alert formatter.

Formatting lives here; actual HTTP send is delegated to shared.utils.telegram.TelegramNotifier.
"""
from __future__ import annotations

import logging
from typing import Optional

from shared.utils.telegram import TelegramNotifier

logger = logging.getLogger("polymarket_intelligence.telegram")

_AGENT_ID  = "📡 polymarket_intelligence"
_LLM_TIER  = "⚙️ 处理层：Rule-based (SIGNAL_COMPUTE) | 仅提醒，不自动交易"
_SEPARATOR = "─" * 28

# 消息主体模板（中文标注）
_TEMPLATE = """\
{agent_id}
{sep}
🚨 高信号事件

市场：
{question}
事件：
{event_title}
信号类型：
{signal_label}
概率变化：
{move_str}
变动幅度：
{delta_str}
成交量：
${volume:,.0f}
流动性：
${liquidity:,.0f}
价差：
{spread_str}
评分：
{score}/100
触发原因：
{reason}
链接：
{url}
{sep}
{llm_tier}\
"""


def _format_message(signal: dict, market: dict, score: int) -> str:
    question = market.get("question", "N/A")
    event_title = (
        market.get("groupItemTitle")
        or market.get("event_title")
        or market.get("category", "N/A")
    )
    signal_type = signal.get("signal_type", "")

    if "rapid_reprice" in signal_type:
        window = signal.get("window_minutes")
        signal_label = f"Rapid probability repricing ({window}m)"
        pb = signal.get("probability_before")
        pa = signal.get("probability_after")
        pd = signal.get("probability_delta")
        move_str = f"{pb:.0%} → {pa:.0%}" if pb is not None and pa is not None else "N/A"
        delta_str = f"{pd:+.0%} in {window}m" if pd is not None else "N/A"
    elif "liquidity_spike" in signal_type:
        signal_label = "Liquidity spike"
        move_str = "N/A"
        ld = signal.get("liquidity_delta")
        delta_str = f"+${ld:,.0f}" if ld is not None else "N/A"
    else:
        signal_label = signal_type
        move_str = "N/A"
        delta_str = "N/A"

    try:
        bid = float(market.get("bestBid") or 0)
        ask = float(market.get("bestAsk") or 0)
        spread: Optional[float] = round(ask - bid, 3) if bid > 0 and ask > 0 else None
    except (ValueError, TypeError):
        spread = None
    spread_str = f"{spread:.3f}" if spread is not None else "N/A"

    url = market.get("url") or f"https://polymarket.com/event/{market.get('slug', '')}"

    return _TEMPLATE.format(
        agent_id=_AGENT_ID,
        sep=_SEPARATOR,
        llm_tier=_LLM_TIER,
        question=question,
        event_title=event_title,
        signal_label=signal_label,
        move_str=move_str,
        delta_str=delta_str,
        volume=float(market.get("volume", 0) or 0),
        liquidity=float(market.get("liquidity", 0) or 0),
        spread_str=spread_str,
        score=score,
        reason=signal.get("reason", "N/A"),
        url=url,
    )


def send_alert(
    signal: dict,
    market: dict,
    score: int,
    notifier: TelegramNotifier,
) -> bool:
    message = _format_message(signal, market, score)
    sent = notifier.send(message)
    if sent and not notifier.dry_run:
        logger.info(f"Alert sent [market={market.get('id')} score={score}]")
    return sent
