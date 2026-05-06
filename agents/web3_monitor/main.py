import sys

from config import load_config
from scheduler import start
from utils.logger import setup_logger

logger = setup_logger("main")


def main():
    logger.info("Web3 Monitor starting...")
    try:
        cfg = load_config()
    except ValueError as e:
        logger.error(f"配置错误: {e}")
        sys.exit(1)

    logs_dir = cfg.get("data", {}).get("logs_dir")
    if logs_dir:
        import os
        os.environ["LOGS_DIR"] = logs_dir

    start(cfg)


if __name__ == "__main__":
    main()
