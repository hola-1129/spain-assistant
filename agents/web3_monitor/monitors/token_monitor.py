from alerts.telegram_alert import TelegramAlert
from fetchers.coingecko_fetcher import CoinGeckoFetcher
from storage.data_store import DataStore
from utils.logger import setup_logger

logger = setup_logger("token_monitor")


class TokenMonitor:
    def __init__(self, config: dict, store: DataStore, alert: TelegramAlert):
        self.cfg       = config
        self.store     = store
        self.alert     = alert
        self.fetcher   = CoinGeckoFetcher(config)
        self.watchlist = config.get("tokens", {}).get("watchlist", [])
        self.threshold = config.get("tokens", {}).get("alert_change_pct", 10.0)

    def run(self):
        logger.info("Token 价格检查...")
        prices = self.fetcher.get_prices(self.watchlist)
        if not prices:
            return

        self.store.save_prices(prices)

        for sym, d in prices.items():
            chg = d.get("change_24h_pct")
            if chg is None:
                continue
            if abs(chg) >= self.threshold:
                direction = "📈" if chg > 0 else "📉"
                key = f"token_move_{sym}"
                if self.store.can_alert(key):
                    msg = (
                        f"{direction} *{sym}* 24h 大幅波动\n"
                        f"价格: ${d['price']:,.4f}\n"
                        f"涨跌幅: {chg:+.2f}%"
                    )
                    if self.alert.send(msg):
                        self.store.record_alert(key)
                        logger.info(f"Alert sent: {sym} {chg:+.2f}%")
