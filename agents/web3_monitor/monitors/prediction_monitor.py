from alerts.telegram_alert import TelegramAlert
from fetchers.polymarket_fetcher import PolymarketFetcher
from storage.data_store import DataStore
from utils.logger import setup_logger

logger = setup_logger("prediction_monitor")


class PredictionMonitor:
    def __init__(self, config: dict, store: DataStore, alert: TelegramAlert):
        self.store   = store
        self.alert   = alert
        self.fetcher = PolymarketFetcher(config)

    def run(self):
        """检查即将结算的关键词市场，发送提醒。"""
        logger.info("Polymarket 结算检查...")
        resolving = self.fetcher.get_resolving_soon()
        if not resolving:
            return

        key = "polymarket_resolving"
        if not self.store.can_alert(key):
            return

        lines = ["⏰ *Polymarket 即将结算*\n"]
        for m in resolving:
            days = m.get("days_left", "?")
            vol  = m["volume_usd"] / 1000
            lines.append(
                f"• {m['question']}\n"
                f"  结算: {days}天后 | 成交量: ${vol:.0f}K\n"
                f"  {m['url']}"
            )

        if self.alert.send("\n".join(lines)):
            self.store.record_alert(key)
            logger.info(f"Polymarket alert: {len(resolving)} markets resolving soon")

    def run_top_markets(self):
        """推送当前热门宏观市场列表，供参考下注。"""
        logger.info("Polymarket 热门市场扫描...")
        key = "polymarket_top"
        if not self.store.can_alert(key):
            return

        markets = self.fetcher.get_keyword_markets()[:5]
        if not markets:
            return

        lines = ["🔮 *Polymarket 宏观热门*\n"]
        for m in markets:
            vol = m["volume_usd"] / 1000
            lines.append(
                f"• {m['question']}\n"
                f"  成交量: ${vol:.0f}K | {m['url']}"
            )

        if self.alert.send("\n".join(lines)):
            self.store.record_alert(key)
