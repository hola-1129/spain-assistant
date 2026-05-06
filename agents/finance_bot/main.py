#!/usr/bin/env python3
"""Finance market monitor — entry point."""

import signal
import sys

from alerts.telegram_alert import TelegramAlert
from config import load_config
from scheduler import BotScheduler
from utils.logger import setup_logger

logger = setup_logger("main")


def main():
    cfg     = load_config()
    alert   = TelegramAlert(cfg["telegram_token"], cfg["telegram_chat_id"])
    bot     = BotScheduler(cfg, alert)

    def _shutdown(sig, frame):
        logger.info("Shutting down...")
        bot.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info("Finance bot starting...")
    if cfg.get("alerts", {}).get("startup_message", True):
        alert.send("✅ Finance bot started.")

    bot.start()


if __name__ == "__main__":
    main()
