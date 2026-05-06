from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from engine.cross_asset import analyze_cross_asset
from engine.inflection import detect_inflection
from engine.regime import classify_regime
from fetchers.coingecko_fetcher import CoinGeckoFetcher
from fetchers.yfinance_fetcher import YFinanceFetcher
from scanner.alert_throttle import AlertThrottle
from scanner.asia_scanner import AsiaScanner, format_asia_alert
from scanner.crypto_scanner import CryptoScanner
from scanner.daily_summary import format_daily_summary
from scanner.macro_scanner import MacroScanner, format_macro_alert, format_macro_snapshot, format_trend_alert
from scanner.scorer import format_alert
from scanner.stock_scanner import StockScanner
from scanner.universe import ALL_ETFS, ASIA_MARKETS
from signals.base import InflectionEvent
from storage.data_store import DataStore
from utils.logger import setup_logger

logger = setup_logger("scheduler")
_ET    = ZoneInfo("America/New_York")


def _is_market_open() -> bool:
    now  = datetime.now(_ET)
    if now.weekday() >= 5:
        return False
    mins = now.hour * 60 + now.minute
    return 570 <= mins <= 960   # 09:30–16:00 ET


class BotScheduler:
    def __init__(self, config: dict, alert):
        self.config  = config
        self.alert   = alert
        self.yf      = YFinanceFetcher(config)
        self.cg      = CoinGeckoFetcher(config)
        self.store   = DataStore(config)
        self.throttle = AlertThrottle(
            store         = self.store,
            max_per_hour  = config.get("scanner", {}).get("max_alerts_per_hour", 8),
            cooldown_min  = config.get("scanner", {}).get("cooldown_minutes", 60),
        )
        self.stock_scanner  = StockScanner()
        self.crypto_scanner = CryptoScanner()
        self.asia_scanner   = AsiaScanner()
        self.macro_scanner  = MacroScanner()

        self._scheduler = BlockingScheduler(
            executors={"default": ThreadPoolExecutor(4)}
        )
        self._register_jobs()

    # ────────────────────────────────────────── job registration ──────────
    def _register_jobs(self):
        freq    = self.config.get("monitoring_frequency", {})
        scanner = self.config.get("scanner", {})

        # ── Existing inflection jobs ──────────────────────────────────────
        hf = freq.get("high_freq", {})
        self._scheduler.add_job(
            self._high_freq_check,
            IntervalTrigger(minutes=hf.get("interval_minutes", 3)),
            id="high_freq", misfire_grace_time=60,
        )

        mf = freq.get("mid_freq", {})
        self._scheduler.add_job(
            self._mid_freq_check,
            IntervalTrigger(minutes=mf.get("interval_minutes", 15)),
            id="mid_freq", misfire_grace_time=120,
        )

        lf = freq.get("low_freq", {})
        self._scheduler.add_job(
            self._low_freq_check,
            IntervalTrigger(hours=lf.get("interval_hours", 4)),
            id="low_freq", misfire_grace_time=600,
        )

        mc = freq.get("macro", {})
        self._scheduler.add_job(
            self._macro_check,
            IntervalTrigger(hours=mc.get("interval_hours", 24)),
            id="macro", misfire_grace_time=3600,
        )

        # ── Scanner jobs ──────────────────────────────────────────────────
        self._scheduler.add_job(
            self._stock_scan,
            IntervalTrigger(minutes=scanner.get("stock_scan_interval_min", 30)),
            id="stock_scan", misfire_grace_time=300,
        )

        self._scheduler.add_job(
            self._crypto_scan,
            IntervalTrigger(minutes=scanner.get("crypto_scan_interval_min", 15)),
            id="crypto_scan", misfire_grace_time=120,
        )

        # Daily summary: 4:15 PM ET on market days
        self._scheduler.add_job(
            self._daily_summary,
            CronTrigger(hour=16, minute=15,
                        day_of_week="mon-fri",
                        timezone=_ET),
            id="daily_summary", misfire_grace_time=1800,
        )

        # Asia scanner: every 30 min (skips internally if no markets open)
        self._scheduler.add_job(
            self._asia_scan,
            IntervalTrigger(minutes=scanner.get("asia_scan_interval_min", 30)),
            id="asia_scan", misfire_grace_time=300,
        )

        # Macro unusual alerts: every 30 min
        self._scheduler.add_job(
            self._macro_scan,
            IntervalTrigger(minutes=scanner.get("macro_scan_interval_min", 30)),
            id="macro_scan", misfire_grace_time=300,
        )

        # Macro overview snapshot: every 4 hours
        self._scheduler.add_job(
            self._macro_snapshot,
            IntervalTrigger(hours=scanner.get("macro_snapshot_interval_hours", 4)),
            id="macro_snapshot", misfire_grace_time=1800,
        )

    # ────────────────────────────────────────────── alert helpers ─────────
    def _send_event(self, event: InflectionEvent):
        rule = f"inflection_{event.direction}"
        if self.store.can_send_alert(event.symbol, rule):
            msg = event.format_message()
            logger.info(f"[inflection] {event.symbol} {event.score} {event.direction}")
            if self.alert.send(msg):
                self.store.record_alert(event.symbol, rule, msg)
                self.store.save_signals(event.symbol, event.signals, event.score)

    def _send_raw(self, symbol: str, rule: str, msg: str):
        if self.store.can_send_alert(symbol, rule):
            logger.info(f"[{rule}] {symbol}")
            if self.alert.send(msg):
                self.store.record_alert(symbol, rule, msg)

    # ──────────────────────────────── existing inflection jobs ───────────
    def _high_freq_check(self):
        logger.info("▶ high_freq (crypto inflection)")
        crypto_assets = self.config["monitoring_frequency"]["high_freq"]["assets"]
        min_score     = self.config.get("engine", {}).get("min_score_high_freq", 4.0)
        quick_pct     = self.config.get("engine", {}).get("quick_move_pct", 5.0)
        try:
            prices = self.cg.get_prices(crypto_assets)
            self.store.save_prices(prices, "crypto")
            for sym, data in prices.items():
                chg = data.get("change_24h_pct")
                if chg is not None and abs(chg) >= quick_pct:
                    emoji = "🚀" if chg > 0 else "💥"
                    self._send_raw(sym, "quick_move",
                        f"{emoji} *{sym}* 快速波动\n"
                        f"24h: {chg:+.2f}%  ${data['price']:,.2f}")
        except Exception as e:
            logger.error(f"high_freq error: {e}", exc_info=True)

    def _mid_freq_check(self):
        logger.info("▶ mid_freq (stock inflection)")
        stocks    = self.config["monitoring_frequency"]["mid_freq"]["assets"]
        min_score = self.config.get("engine", {}).get("min_score_mid_freq", 3.0)
        try:
            quotes = self.yf.get_quotes(stocks)
            self.store.save_prices(quotes, "stock")
            hist = self.yf.get_history(stocks, period="6mo")
            for sym in stocks:
                if sym in hist:
                    ev = detect_inflection(sym, hist[sym], min_score)
                    if ev:
                        self._send_event(ev)
        except Exception as e:
            logger.error(f"mid_freq error: {e}", exc_info=True)

    def _low_freq_check(self):
        logger.info("▶ low_freq (deep + cross-asset)")
        stocks    = self.config["monitoring_frequency"]["mid_freq"]["assets"]
        cryptos   = self.config["monitoring_frequency"]["high_freq"]["assets"]
        min_score = self.config.get("engine", {}).get("min_score_low_freq", 2.5)
        try:
            stock_hist  = self.yf.get_history(stocks + ["SPY", "QQQ"], period="1y")
            crypto_hist = self.cg.get_history(cryptos, days=65)
            for sym in stocks:
                if sym in stock_hist:
                    ev = detect_inflection(sym, stock_hist[sym], min_score)
                    if ev:
                        self._send_event(ev)
            for sym in cryptos:
                if sym in crypto_hist:
                    ev = detect_inflection(sym, crypto_hist[sym], min_score)
                    if ev:
                        self._send_event(ev)
            cross = analyze_cross_asset(stock_hist, crypto_hist)
            if cross:
                lines = ["🔗 *跨资产信号*"]
                for s in cross:
                    arrow = "↑" if s.direction == "bullish" else ("↓" if s.direction == "bearish" else "→")
                    lines.append(f"  {arrow} {s.label}: {s.detail}")
                self._send_raw("MARKET", "cross_asset", "\n".join(lines))
        except Exception as e:
            logger.error(f"low_freq error: {e}", exc_info=True)

    def _macro_check(self):
        logger.info("▶ macro (regime report)")
        stocks    = self.config["monitoring_frequency"]["mid_freq"]["assets"]
        cryptos   = self.config["monitoring_frequency"]["high_freq"]["assets"]
        min_score = self.config.get("engine", {}).get("min_score_low_freq", 2.5)
        try:
            stock_hist  = self.yf.get_history(stocks + ["SPY", "QQQ", "^VIX", "^TNX", "^FVX", "GC=F"], period="1y")
            vix_data    = self.yf.get_quotes(["^VIX"])
            crypto_hist = self.cg.get_history(cryptos, days=65)
            regime      = classify_regime(stock_hist, vix_data)

            bar   = "●" * regime["score"] + "○" * (10 - regime["score"])
            lines = [
                "📊 *每日市场快照*",
                f"状态: {regime['label']}  {bar}  {regime['score']}/10",
            ]
            if regime["vix"]:
                lines.append(f"VIX: {regime['vix']:.1f}  |  SPY: {regime['spy_trend']}")
            if regime["spread_note"]:
                lines.append(regime["spread_note"])
            if regime.get("yield_curve_note"):
                lines.append(regime["yield_curve_note"])
            if regime.get("gold_note"):
                lines.append(regime["gold_note"])

            notable = []
            for sym in stocks:
                if sym in stock_hist:
                    ev = detect_inflection(sym, stock_hist[sym], min_score)
                    if ev:
                        notable.append(ev)
            for sym in cryptos:
                if sym in crypto_hist:
                    ev = detect_inflection(sym, crypto_hist[sym], min_score)
                    if ev:
                        notable.append(ev)
            if notable:
                notable.sort(key=lambda e: e.score, reverse=True)
                lines.append("\n*拐点信号*")
                for ev in notable[:5]:
                    emoji = "🟢" if ev.direction == "bullish" else (
                            "🔴" if ev.direction == "bearish" else "🔀")
                    top   = ev.signals[0].label if ev.signals else ""
                    lines.append(f"  {emoji} {ev.symbol}  {ev.score:.1f}/10  {top}")
            self._send_raw("MARKET", "daily_regime", "\n".join(lines))
        except Exception as e:
            logger.error(f"macro error: {e}", exc_info=True)

    # ──────────────────────────────────────────── scanner jobs ───────────
    def _stock_scan(self):
        if not _is_market_open():
            return
        logger.info("▶ stock_scan")
        cfg       = self.config.get("scanner", {})
        min_alert = cfg.get("min_score_alert", 60.0)
        min_log   = cfg.get("min_score_log", 30.0)

        try:
            results = self.stock_scanner.scan(min_score=min_log)
            self.store.save_unusual_movers(results, "stock")

            if not results:
                return

            # Crash check: if SPY down ≥ 3%, only ETFs + top-5
            spy_hist   = self.yf.get_history(["SPY"], period="5d").get("SPY")
            is_crash   = self.throttle.is_market_crash(spy_hist)
            candidates = [r for r in results if r["unusual_score"] >= min_alert]

            if is_crash:
                etfs  = [r for r in candidates if r["asset_type"] == "etf"]
                others = [r for r in candidates if r["asset_type"] != "etf"]
                candidates = etfs + others[:5]
                if candidates:
                    self._send_raw("MARKET", "crash_mode",
                        "⚠️ *市场大跌模式* — 仅播报指数ETF及得分最高标的")

            for r in candidates:
                if self.throttle.is_hourly_limit_reached():
                    logger.info("Hourly unusual-mover limit reached, skipping rest")
                    break
                if not self.throttle.can_send(r["symbol"]):
                    continue
                msg = format_alert(r)
                logger.info(f"[unusual] {r['symbol']} score={r['unusual_score']}")
                if self.alert.send(msg):
                    self.store.record_alert(r["symbol"],
                                            f"unusual_{r['level'].lower()}", msg)

        except Exception as e:
            logger.error(f"stock_scan error: {e}", exc_info=True)

    def _crypto_scan(self):
        logger.info("▶ crypto_scan")
        cfg       = self.config.get("scanner", {})
        min_alert = cfg.get("min_score_alert", 60.0)
        min_log   = cfg.get("min_score_log", 30.0)

        try:
            results = self.crypto_scanner.scan(min_score=min_log)
            self.store.save_unusual_movers(results, "crypto")

            candidates = [r for r in results if r["unusual_score"] >= min_alert]
            for r in candidates:
                if self.throttle.is_hourly_limit_reached():
                    logger.info("Hourly unusual-mover limit reached")
                    break
                if not self.throttle.can_send(r["symbol"]):
                    continue
                msg = format_alert(r)
                logger.info(f"[unusual-crypto] {r['symbol']} score={r['unusual_score']}")
                if self.alert.send(msg):
                    self.store.record_alert(r["symbol"],
                                            f"unusual_{r['level'].lower()}", msg)

        except Exception as e:
            logger.error(f"crypto_scan error: {e}", exc_info=True)

    def _asia_scan(self):
        logger.info("▶ asia_scan")
        cfg       = self.config.get("scanner", {})
        min_alert = cfg.get("min_score_alert", 60.0)
        min_log   = cfg.get("min_score_log", 30.0)
        try:
            results_by_market = self.asia_scanner.scan_open_markets(min_score=min_log)
            if not results_by_market:
                logger.debug("asia_scan: no markets open")
                return
            for mkey, results in results_by_market.items():
                candidates = [r for r in results if r["unusual_score"] >= min_alert]
                for r in candidates:
                    if self.throttle.is_hourly_limit_reached():
                        logger.info("Hourly limit reached during asia_scan")
                        return
                    if not self.throttle.can_send(r["symbol"]):
                        continue
                    msg = format_asia_alert(r)
                    logger.info(f"[unusual-asia] {r['symbol']} score={r['unusual_score']}")
                    if self.alert.send(msg):
                        self.store.record_alert(r["symbol"],
                                                f"unusual_{r['level'].lower()}", msg)
        except Exception as e:
            logger.error(f"asia_scan error: {e}", exc_info=True)

    def _macro_scan(self):
        logger.info("▶ macro_scan (unusual + trend)")
        try:
            snapshot = self.macro_scanner.snapshot()

            # ── Unusual move alerts ───────────────────────────────────────
            for r in self.macro_scanner.scan_unusual(snapshot):
                if self.throttle.is_hourly_limit_reached():
                    logger.info("Hourly limit reached during macro_scan (unusual)")
                    break
                rule = f"macro_{r['group']}"
                if not self.store.can_send_alert(r["symbol"], rule):
                    continue
                msg = format_macro_alert(r)
                logger.info(f"[macro-unusual] {r['symbol']} {r['daily_change_pct']:+.2f}%")
                if self.alert.send(msg):
                    self.store.record_alert(r["symbol"], rule, msg)

            # ── Trend-layer alerts (MA crossovers / key-level breaks) ─────
            for r in self.macro_scanner.scan_trend(snapshot):
                if self.throttle.is_hourly_limit_reached():
                    logger.info("Hourly limit reached during macro_scan (trend)")
                    break
                rule = f"macro_trend_{r['symbol']}"
                if not self.store.can_send_alert(r["symbol"], rule):
                    continue
                msg = format_trend_alert(r)
                logger.info(f"[macro-trend] {r['symbol']} {r['trend_signal']}")
                if self.alert.send(msg):
                    self.store.record_alert(r["symbol"], rule, msg)

        except Exception as e:
            logger.error(f"macro_scan error: {e}", exc_info=True)

    def _macro_snapshot(self):
        logger.info("▶ macro_snapshot (overview)")
        try:
            snapshot = self.macro_scanner.snapshot()
            if not snapshot:
                return
            msg = format_macro_snapshot(snapshot)
            self._send_raw("MARKET", "macro_snapshot", msg)
        except Exception as e:
            logger.error(f"macro_snapshot error: {e}", exc_info=True)

    def _daily_summary(self):
        logger.info("▶ daily_summary")
        try:
            stock_results  = self.stock_scanner.scan(min_score=0)
            crypto_results = self.crypto_scanner.scan(min_score=0)
            asia_results   = self.asia_scanner.scan_open_markets(min_score=0)
            macro_snapshot = self.macro_scanner.snapshot()
            date_str       = datetime.now(_ET).strftime("%Y-%m-%d")
            msg = format_daily_summary(
                stock_results, crypto_results, date_str,
                asia_results=asia_results or None,
                macro_snapshot=macro_snapshot or None,
            )
            self._send_raw("MARKET", "daily_summary", msg)
        except Exception as e:
            logger.error(f"daily_summary error: {e}", exc_info=True)

    # ──────────────────────────────────────────────── control ─────────────
    def start(self):
        logger.info("Scheduler started. Ctrl-C to stop.")
        self._scheduler.start()

    def stop(self):
        self._scheduler.shutdown(wait=False)
