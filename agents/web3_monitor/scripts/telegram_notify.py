"""Telegram push helper. Loads bot_token / chat_id from .env, sends Markdown messages."""
from __future__ import annotations

import logging
import os
from typing import Optional

import requests

logger = logging.getLogger("web3_monitor.telegram")

_API = "https://api.telegram.org"


def _format_probability(value) -> str:
    if isinstance(value, (int, float)):
        return f"{value * 100:.0f}%"
    return "n/a"


class TelegramNotifier:
    def __init__(self, bot_token: Optional[str], chat_id: Optional[str], enabled: bool = True, timeout: int = 15):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = enabled and bool(bot_token) and bool(chat_id)
        self.timeout = timeout
        if enabled and not self.enabled:
            logger.warning("Telegram enabled in config but bot_token / chat_id missing — disabled")

    @classmethod
    def from_config(cls, telegram_cfg: dict) -> "TelegramNotifier":
        token = os.environ.get(telegram_cfg.get("bot_token_env", "TELEGRAM_BOT_TOKEN"))
        chat_id = os.environ.get(telegram_cfg.get("chat_id_env", "TELEGRAM_CHAT_ID"))
        return cls(token, chat_id, enabled=telegram_cfg.get("enabled", True))

    def send(self, text: str, parse_mode: str | None = None) -> bool:
        if not self.enabled:
            logger.debug("Telegram disabled, skipping send")
            return False
        url = f"{_API}/bot{self.bot_token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            r = requests.post(
                url,
                json=payload,
                timeout=self.timeout,
            )
            if r.status_code == 200:
                return True
            logger.error(f"Telegram send failed: {r.status_code} {r.text[:200]}")
            return False
        except Exception as e:
            logger.error(f"Telegram send exception: {e}")
            return False


def format_signal_alert(signal: dict) -> str:
    """Render a signal dict into a concise v2 Telegram message."""
    score = signal.get("score", 0)
    level = signal.get("level", "MEDIUM")
    asset = signal.get("asset", "?")
    chain = signal.get("chain", "?")
    sig_type = signal.get("type", "cross")

    dex = signal.get("dex") or {}
    pm = signal.get("polymarket") or {}
    interp = signal.get("interpretation", "")

    source = "cross_signal" if dex and pm else ("dexscreener" if dex else "polymarket")
    risk = signal.get("risk") or {}
    risk_warning = ", ".join(risk.get("reasons") or []) or "none"
    ts = signal.get("ts") or signal.get("timestamp") or ""

    lines = [
        "🚨 Web3 Quant Signal",
        f"{asset} | {sig_type} | {level} | {score}/100",
        f"Source: {source}",
    ]
    if chain and chain != "?":
        lines.append(f"Chain: {chain}")

    if dex:
        lines.append("DEX:")
        if "price_change_1h_pct" in dex:
            lines.append(f"- Price 1h: {dex['price_change_1h_pct']:+.1f}%")
        if "volume_change_1h_pct" in dex:
            lines.append(f"- Volume 1h: {dex['volume_change_1h_pct']:+.0f}%")
        if "volume_1h_usd" in dex:
            lines.append(f"- Volume: ${dex['volume_1h_usd']:,.0f}")
        if "liquidity_usd" in dex:
            lines.append(f"- Liquidity: ${dex['liquidity_usd']:,.0f}")

    if pm:
        lines.append("Polymarket:")
        if "title" in pm:
            lines.append(f"- Event: {pm['title']}")
        if "probability_prev" in pm and "probability_now" in pm:
            prev = _format_probability(pm.get("probability_prev"))
            now = _format_probability(pm.get("probability_now"))
            lines.append(f"- Probability: {prev} → {now}")
        if "probability_change_pct" in pm:
            lines.append(f"- Change: {pm['probability_change_pct']:+.0f}%")
        if "volume_change_pct" in pm:
            lines.append(f"- Volume: {pm['volume_change_pct']:+.0f}%")

    lines.append(f"Reason: {interp or 'n/a'}")
    lines.append(f"Risk: {risk_warning}")
    if ts:
        lines.append(f"Time: {ts}")
    lines.append("Action: 只提醒，不自动交易。")

    # Optional Qwen explanation — added by agent_orchestrator when llm_enrichment enabled
    if signal.get("qwen_explanation"):
        lines.append(f"\n💡 {signal['qwen_explanation']}")

    return "\n".join(lines)
