"""定时调度器：读取 config 中的 fetch_times，按时触发模块运行。"""

import schedule
import time
from src.core import config
from src.core.logger import get_logger

log = get_logger(__name__)


def register_module(name: str, run_fn, times: list[str]):
    """注册模块到调度器。times 格式: ['08:30', '13:30', '18:30']"""
    for t in times:
        schedule.every().day.at(t).do(run_fn)
        log.info(f"[scheduler] 模块 {name} 已注册: {t}")


def run_loop():
    log.info("[scheduler] 调度器启动，等待触发...")
    while True:
        schedule.run_pending()
        time.sleep(30)
