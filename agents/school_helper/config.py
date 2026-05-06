import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

_HERE = Path(__file__).resolve().parent


def load_config(path: str = "config.yaml") -> dict:
    cfg_path = Path(path)
    if not cfg_path.is_absolute():
        cfg_path = _HERE / cfg_path

    with open(cfg_path) as f:
        cfg = yaml.safe_load(f) or {}

    cfg["anthropic_api_key"] = os.environ.get("ANTHROPIC_API_KEY", "")
    cfg["telegram_token"]    = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    cfg["telegram_chat_id"]  = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not cfg["anthropic_api_key"]:
        raise ValueError("ANTHROPIC_API_KEY not set in .env")

    paths = cfg.setdefault("paths", {})
    paths.setdefault("input_dir",  str(_HERE / "input"))
    paths.setdefault("output_dir", str(_HERE / "output"))
    paths.setdefault("logs_dir",   "/Volumes/AI_DISK/ai_workspace/logs/school_helper")

    if paths.get("logs_dir"):
        os.environ["LOGS_DIR"] = paths["logs_dir"]

    return cfg
