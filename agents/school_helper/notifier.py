"""Telegram 通知封装。

复用 finance_bot 的 Bot Token / Chat ID（首选 school_helper 自己的 .env，
若未配置则回退到 finance_bot/.env），失败只打日志、不抛出，避免阻断主流程。
"""

import os
from pathlib import Path

import requests
from dotenv import dotenv_values

from utils.logger import setup_logger

logger = setup_logger("notifier")

_HERE = Path(__file__).resolve().parent
_FINANCE_ENV = _HERE.parent / "finance_bot" / ".env"


def _load_telegram_creds() -> tuple[str, str]:
    """优先用本 agent 的 .env；为空再读 finance_bot/.env。"""
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if token and chat_id:
        return token, chat_id

    if _FINANCE_ENV.exists():
        finance = dotenv_values(_FINANCE_ENV)
        token   = token   or (finance.get("TELEGRAM_BOT_TOKEN") or "").strip()
        chat_id = chat_id or (finance.get("TELEGRAM_CHAT_ID")  or "").strip()

    return token, chat_id


class Notifier:
    def __init__(self, token: str = "", chat_id: str = ""):
        if not token or not chat_id:
            t, c = _load_telegram_creds()
            token   = token   or t
            chat_id = chat_id or c
        self.enabled = bool(token and chat_id)
        self.chat_id = chat_id
        self._url    = f"https://api.telegram.org/bot{token}/sendMessage" if token else ""
        if not self.enabled:
            logger.warning("Telegram 凭证未配置，notifier 已禁用")

    def send(self, message: str, *, parse_mode: str | None = "Markdown") -> bool:
        if not self.enabled:
            logger.info(f"(TG disabled) {message[:120]}")
            return False
        # Telegram 单条上限 4096 字节
        if len(message) > 3900:
            message = message[:3900] + "\n…(已截断)"
        payload = {"chat_id": self.chat_id, "text": message,
                   "disable_web_page_preview": False}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            resp = requests.post(self._url, json=payload, timeout=10)
            resp.raise_for_status()
            return True
        except Exception as e:
            # 若是 Markdown 解析失败，自动降级为纯文本重试一次
            if parse_mode and "Bad Request" in str(e):
                logger.warning(f"Telegram {parse_mode} 解析失败，降级纯文本重试")
                payload.pop("parse_mode", None)
                try:
                    resp = requests.post(self._url, json=payload, timeout=10)
                    resp.raise_for_status()
                    return True
                except Exception as e2:
                    logger.error(f"Telegram 纯文本重试仍失败: {e2}")
                    return False
            logger.error(f"Telegram 发送失败: {e}")
            return False
