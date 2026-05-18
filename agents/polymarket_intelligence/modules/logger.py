from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_logger(log_dir: Path, name: str = "polymarket_intelligence") -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{name}.log"

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        fh = logging.FileHandler(log_file)
        fh.setFormatter(formatter)
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(formatter)
        logger.addHandler(fh)
        logger.addHandler(sh)

    return logger
