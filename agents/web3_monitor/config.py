import os

import yaml
from dotenv import load_dotenv

load_dotenv()


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        cfg = yaml.safe_load(f)

    cfg["telegram_token"]   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    cfg["telegram_chat_id"] = os.environ.get("TELEGRAM_CHAT_ID", "")
    cfg["polymarket_wallet"] = os.environ.get("POLYMARKET_WALLET", "")

    if not cfg["telegram_token"]:
        raise ValueError("TELEGRAM_BOT_TOKEN not set in .env")
    if not cfg["telegram_chat_id"]:
        raise ValueError("TELEGRAM_CHAT_ID not set in .env")

    return cfg
