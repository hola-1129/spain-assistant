"""Shared Telegram notifier used by all workspace agents.

Usage:
    from shared.utils.telegram import TelegramNotifier

    notifier = TelegramNotifier.from_env()          # reads TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
    notifier = TelegramNotifier.from_config(cfg)    # reads env var names from config dict
    notifier.send("hello")
    notifier.send_if(score >= 75, message)          # no-op when condition is false

dry_run support: set dry_run=True (or runtime.dry_run in config) to log instead of send.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import requests

logger = logging.getLogger("shared.telegram")

_API_BASE = "https://api.telegram.org"


class TelegramNotifier:
    def __init__(
        self,
        bot_token: Optional[str],
        chat_id: Optional[str],
        enabled: bool = True,
        dry_run: bool = False,
        timeout: int = 15,
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.dry_run = dry_run
        self.timeout = timeout
        self.enabled = enabled and bool(bot_token) and bool(chat_id)
        if enabled and not self.enabled:
            logger.warning("Telegram enabled but bot_token/chat_id missing — disabled")

    # ---------------------------------------------------------------- factories

    @classmethod
    def from_env(
        cls,
        token_env: str = "TELEGRAM_BOT_TOKEN",
        chat_id_env: str = "TELEGRAM_CHAT_ID",
        dry_run: bool = False,
    ) -> "TelegramNotifier":
        return cls(
            bot_token=os.environ.get(token_env),
            chat_id=os.environ.get(chat_id_env),
            dry_run=dry_run,
        )

    @classmethod
    def from_config(cls, cfg: dict) -> "TelegramNotifier":
        tg = cfg.get("telegram", {})
        runtime = cfg.get("runtime", {})
        token = os.environ.get(tg.get("bot_token_env", "TELEGRAM_BOT_TOKEN"), "")
        chat_id = os.environ.get(tg.get("chat_id_env", "TELEGRAM_CHAT_ID"), "")
        return cls(
            bot_token=token,
            chat_id=chat_id,
            enabled=tg.get("enabled", True),
            dry_run=runtime.get("dry_run", True),
        )

    # ---------------------------------------------------------------- send

    def send(self, text: str, parse_mode: Optional[str] = None) -> bool:
        if self.dry_run:
            logger.info(f"[DRY RUN] Telegram (not sent):\n{text}")
            return True
        if not self.enabled:
            logger.debug("Telegram disabled — skipping")
            return False
        url = f"{_API_BASE}/bot{self.bot_token}/sendMessage"
        payload: dict = {
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            r = requests.post(url, json=payload, timeout=self.timeout)
            if r.status_code == 200:
                return True
            logger.error(f"Telegram send failed: {r.status_code} {r.text[:200]}")
            return False
        except Exception as e:
            logger.error(f"Telegram send exception: {e}")
            return False

    def send_if(self, condition: bool, text: str, **kwargs) -> bool:
        if not condition:
            return False
        return self.send(text, **kwargs)
