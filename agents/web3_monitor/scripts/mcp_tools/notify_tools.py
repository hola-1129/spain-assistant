"""Notification tools."""
from __future__ import annotations

from core.models import ToolContext, ToolResult
from coingecko_market_monitor import format_market_alert
from telegram_notify import format_signal_alert


def send_telegram_alert(payload: dict, ctx: ToolContext) -> dict:
    text = payload.get("text")
    signal = payload.get("signal")
    if not text and signal:
        text = format_market_alert(signal) if signal.get("type") == "market_mover" else format_signal_alert(signal)
    if not text:
        return ToolResult(ok=False, tool="send_telegram_alert", errors=["text or signal is required"]).to_json()
    sent = ctx.service("telegram").send(text)
    return ToolResult(ok=sent, tool="send_telegram_alert", data={"sent": sent}).to_json()
