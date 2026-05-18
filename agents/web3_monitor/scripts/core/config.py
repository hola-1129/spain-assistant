"""Configuration, logging, and runtime guards."""
from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

BLOCKED_SECRET_ENV_NAMES = {
    "PRIVATE_KEY",
    "WALLET_PRIVATE_KEY",
    "MNEMONIC",
    "SEED_PHRASE",
}


def load_config(root: Path) -> dict[str, Any]:
    load_dotenv(root / ".env")
    with (root / "config.yaml").open("r") as f:
        cfg = yaml.safe_load(f) or {}
    cfg["dry_run"] = True
    cfg["auto_trade"] = False
    cfg["qwen_api_key"]    = os.environ.get("QWEN_API_KEY", "")
    cfg["openai_api_key"]  = os.environ.get("OPENAI_API_KEY", "")
    return cfg


def setup_logging(root: Path, cfg: dict[str, Any]) -> None:
    log_dir_cfg = cfg.get("logging", {}).get("log_dir", "../../logs/web3_monitor")
    log_dir = Path(log_dir_cfg)
    if not log_dir.is_absolute():
        log_dir = (root / log_dir).resolve()
    log_dir.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(getattr(logging, cfg.get("logging", {}).get("level", "INFO").upper(), logging.INFO))

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "web3_monitor.log", maxBytes=5_000_000, backupCount=5
    )
    file_handler.setFormatter(fmt)
    root_logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    root_logger.addHandler(stream_handler)


def validate_runtime_guards(cfg: dict[str, Any]) -> None:
    if cfg.get("dry_run") is not True:
        raise RuntimeError("dry_run must be True")
    if cfg.get("auto_trade") is not False:
        raise RuntimeError("auto_trade must be False")
    present = sorted(name for name in BLOCKED_SECRET_ENV_NAMES if os.environ.get(name))
    if present:
        raise RuntimeError(f"private-key style env vars are not allowed: {', '.join(present)}")


def interval_seconds(cfg: dict[str, Any], key: str, default_minutes: int) -> int:
    intervals = cfg.get("scan_intervals", {})
    return max(int(intervals.get(key, default_minutes)) * 60, 60)
