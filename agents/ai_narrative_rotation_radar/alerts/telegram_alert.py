"""Telegram alert sender — same pattern as finance_bot."""
from __future__ import annotations

import logging

import requests

logger = logging.getLogger("radar.telegram")

_MAX_LEN = 4096  # Telegram message limit


class TelegramAlert:
    def __init__(self, token: str, chat_id: str):
        self.chat_id = chat_id
        self._url = f"https://api.telegram.org/bot{token}/sendMessage"

    def send(self, message: str) -> bool:
        # Truncate gracefully if message exceeds Telegram limit
        if len(message) > _MAX_LEN:
            message = message[:_MAX_LEN - 20] + "\n…_(truncated)_"
        try:
            resp = requests.post(
                self._url,
                json={
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.error("Telegram send failed: %s", exc)
            return False
