from alerts.telegram_alert import TelegramAlert
from utils.logger import setup_logger

logger = setup_logger("task_reminder")


class TaskReminder:
    def __init__(self, config: dict, alert: TelegramAlert):
        self.alert = alert
        self.items = config.get("tasks", {}).get("items", [])

    def run(self):
        logger.info("发送每周任务提醒...")
        if not self.items:
            return

        priority_icon = {"高": "🔴", "中": "🟡", "低": "🟢"}
        lines = ["📋 *Web3 本周任务清单*\n"]
        for item in self.items:
            icon = priority_icon.get(item.get("priority", "中"), "⚪")
            lines.append(f"{icon} {item['name']} `[{item['track']}]`")

        self.alert.send("\n".join(lines))
