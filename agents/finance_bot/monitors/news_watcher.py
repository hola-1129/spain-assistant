"""Real-time news watcher: polls yfinance every 30 min during trading hours.

Only pushes NEW headlines that weren't seen in the last 24h.
Per-symbol push cooldown: 2h (configurable).
Qwen curates; only important breaking news is pushed.
"""

import logging
import time
from typing import Dict, List, Optional

logger = logging.getLogger("monitors.news_watcher")

_CHINA_PROXIES = ["KWEB", "MCHI", "FXI", "BABA", "PDD", "GLD", "AAXJ"]


class NewsWatcher:
    def __init__(
        self,
        us_symbols: List[str],
        alert,
        drafter,
        cooldown_hours: int = 2,
    ):
        self._us_symbols     = us_symbols
        self._alert          = alert
        self._drafter        = drafter
        self._cooldown_secs  = cooldown_hours * 3600
        # {title: first_seen_ts}  — deduplication across runs
        self._seen: Dict[str, float] = {}
        # {symbol: last_push_ts}  — per-symbol push cooldown
        self._last_push: Dict[str, float] = {}

    def _cleanup(self) -> None:
        cutoff = time.time() - 86400  # drop headlines older than 24h
        self._seen = {k: v for k, v in self._seen.items() if v > cutoff}

    def _fetch_new(self, symbols: List[str]) -> List[str]:
        """Return list of 'SYMBOL|title' strings not yet in _seen."""
        try:
            import yfinance as yf
        except ImportError:
            return []

        new_headlines: List[str] = []
        for sym in symbols:
            try:
                news = yf.Ticker(sym).news or []
                for n in news[:5]:
                    title = n.get("content", {}).get("title", "")
                    if title and title not in self._seen:
                        self._seen[title] = time.time()
                        new_headlines.append(f"{sym}|{title}")
                time.sleep(0.12)
            except Exception as exc:
                logger.debug("news fetch %s: %s", sym, exc)
        return new_headlines

    def _in_cooldown(self, symbols: List[str]) -> bool:
        """True if ALL symbols are still in cooldown (skip push entirely)."""
        now = time.time()
        active = [s for s in symbols if now - self._last_push.get(s, 0) < self._cooldown_secs]
        return len(active) == len(symbols)

    def _mark_pushed(self, symbols: List[str]) -> None:
        now = time.time()
        for s in symbols:
            self._last_push[s] = now

    def scan(self, market: str = "us") -> None:
        """Scan for new headlines; push via Telegram if Qwen deems important.

        market: 'us' or 'china'
        """
        if not self._drafter:
            return

        symbols = self._us_symbols if market == "us" else _CHINA_PROXIES
        self._cleanup()

        if self._in_cooldown(symbols):
            logger.debug("news_watcher: all %s symbols in cooldown, skip", market)
            return

        new_headlines = self._fetch_new(symbols)
        if not new_headlines:
            logger.debug("news_watcher: no new %s headlines", market)
            return

        logger.info("news_watcher: %d new %s headlines, curating with Qwen", len(new_headlines), market)
        section = self._drafter.curate_breaking_news(new_headlines, market)
        if section:
            self._alert.send(section)
            self._mark_pushed(symbols)
            logger.info("news_watcher: pushed breaking news (%s, %d chars)", market, len(section))
        else:
            logger.info("news_watcher: Qwen found nothing important in %s headlines", market)
