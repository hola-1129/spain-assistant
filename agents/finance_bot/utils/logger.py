import logging
import os
from logging.handlers import TimedRotatingFileHandler


def setup_logger(name: str, logs_dir: str = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    if logs_dir is None:
        logs_dir = os.getenv("LOGS_DIR", "/Volumes/AI_DISK/data/logs")

    os.makedirs(logs_dir, exist_ok=True)
    fh = TimedRotatingFileHandler(
        os.path.join(logs_dir, f"{name}.log"),
        when="midnight",
        backupCount=30,
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger
