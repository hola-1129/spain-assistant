"""统一日志配置。所有模块通过 get_logger(__name__) 获取 logger。"""

import logging
import logging.handlers
from pathlib import Path
from src.core import config


def _setup_root_logger():
    level_str = config.get("logging.level", "INFO")
    level = getattr(logging, level_str.upper(), logging.INFO)

    log_file = config.logs_dir / config.get("logging.file", "logs/spain_assistant.log").split("/")[-1]
    log_file.parent.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)

    if not root.handlers:
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        root.addHandler(ch)

        fh = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=config.get("logging.max_bytes", 10 * 1024 * 1024),
            backupCount=config.get("logging.backup_count", 5),
            encoding="utf-8",
        )
        fh.setFormatter(fmt)
        root.addHandler(fh)


_setup_root_logger()


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
