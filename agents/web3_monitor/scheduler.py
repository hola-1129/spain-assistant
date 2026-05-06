import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from alerts.telegram_alert import TelegramAlert
from monitors.prediction_monitor import PredictionMonitor
from monitors.task_reminder import TaskReminder
from monitors.token_monitor import TokenMonitor
from monitors.yield_monitor import YieldMonitor
from storage.data_store import DataStore
from utils.logger import setup_logger

logger = setup_logger("scheduler")

logging.getLogger("apscheduler").setLevel(logging.WARNING)


def start(config: dict):
    store  = DataStore(config)
    alert  = TelegramAlert(config["telegram_token"], config["telegram_chat_id"])

    token_mon  = TokenMonitor(config, store, alert)
    yield_mon  = YieldMonitor(config, store, alert)
    pred_mon   = PredictionMonitor(config, store, alert)
    task_rem   = TaskReminder(config, alert)

    sched = BlockingScheduler(timezone="Asia/Shanghai")

    # 每 30 分钟：token 价格检查
    sched.add_job(token_mon.run, IntervalTrigger(minutes=30), id="token_check")

    # 每 4 小时：DeFi TVL + 收益扫描
    sched.add_job(yield_mon.run, IntervalTrigger(hours=4), id="yield_scan")

    # 每 4 小时：Polymarket 即将结算检查
    sched.add_job(pred_mon.run, IntervalTrigger(hours=4), id="prediction_resolving")

    # 每天 9:00：Polymarket 热门市场播报
    sched.add_job(pred_mon.run_top_markets, CronTrigger(hour=9, minute=0), id="prediction_top")

    # 每周一 9:00：任务提醒
    task_cfg = config.get("tasks", {}).get("weekly_reminder", {})
    sched.add_job(
        task_rem.run,
        CronTrigger(day_of_week=task_cfg.get("day", "mon").lower(),
                    hour=task_cfg.get("hour", 9)),
        id="weekly_tasks",
    )

    if config.get("alerts", {}).get("startup_message"):
        alert.send("🤖 *Web3 Monitor 已启动*\n监控: Token 价格 | DeFi TVL+收益 | Polymarket | 每周任务提醒")

    logger.info("Scheduler started.")
    sched.start()
