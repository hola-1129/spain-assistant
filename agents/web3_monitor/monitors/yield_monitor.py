from alerts.telegram_alert import TelegramAlert
from fetchers.defillama_fetcher import DefiLlamaFetcher
from storage.data_store import DataStore
from utils.logger import setup_logger

logger = setup_logger("yield_monitor")

_TVL_M = 1_000_000


class YieldMonitor:
    def __init__(self, config: dict, store: DataStore, alert: TelegramAlert):
        self.cfg     = config
        self.store   = store
        self.alert   = alert
        self.fetcher = DefiLlamaFetcher(config)
        self.protocols = config.get("defi", {}).get("protocols", [])
        self.drop_pct  = config.get("defi", {}).get("tvl_drop_pct", 15.0)

    def run(self):
        self._check_tvl()
        self._scan_yields()

    def _check_tvl(self):
        logger.info("TVL 监控...")
        for slug in self.protocols:
            current = self.fetcher.get_protocol_tvl(slug)
            if current is None:
                continue

            prev = self.store.get_prev_tvl(slug, hours=25)
            self.store.save_tvl(slug, current)

            if prev and prev > 0:
                drop = (prev - current) / prev * 100
                if drop >= self.drop_pct:
                    key = f"tvl_drop_{slug}"
                    if self.store.can_alert(key):
                        msg = (
                            f"⚠️ *{slug.upper()}* TVL 大幅下降\n"
                            f"当前: ${current / _TVL_M:.1f}M\n"
                            f"24h 跌幅: -{drop:.1f}%"
                        )
                        if self.alert.send(msg):
                            self.store.record_alert(key)
                            logger.info(f"TVL alert: {slug} -{drop:.1f}%")

    def _scan_yields(self):
        logger.info("收益扫描...")
        key = "yield_scan_report"
        if not self.store.can_alert(key):
            return

        pools = self.fetcher.get_yield_opportunities()
        if not pools:
            return

        lines = ["💰 *DeFi 收益机会*\n"]
        for p in pools:
            tvl_m = (p["tvl_usd"] or 0) / _TVL_M
            lines.append(
                f"• *{p['project']}* `{p['symbol']}` [{p['chain']}]\n"
                f"  APY: {p['apy']}% | TVL: ${tvl_m:.1f}M"
            )

        if self.alert.send("\n".join(lines)):
            self.store.record_alert(key)
            logger.info(f"Yield report sent: {len(pools)} pools")
