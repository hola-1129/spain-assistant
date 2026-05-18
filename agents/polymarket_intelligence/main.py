#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = AGENT_ROOT.parent.parent
LOG_DIR = WORKSPACE_ROOT / "logs" / "polymarket_intelligence"
PID_FILE = LOG_DIR / "polymarket_intelligence.pid"

# Both agent modules and shared workspace utilities must be importable
sys.path.insert(0, str(AGENT_ROOT))
sys.path.insert(0, str(WORKSPACE_ROOT))

from modules.config import load_config
from modules.logger import setup_logger
from modules.storage import Storage
from modules.polymarket_client import PolymarketClient
from modules.market_filter import filter_markets
from modules.snapshot import build_snapshot
from modules.signal_engine import detect_rapid_reprice, detect_liquidity_spike
from modules.score_engine import score_signal
from modules.telegram import send_alert
from modules.utils import utcnow_iso
from shared.utils.telegram import TelegramNotifier


def _write_pid() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))


def _remove_pid() -> None:
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def run_cycle(
    cfg: dict,
    storage: Storage,
    client: PolymarketClient,
    notifier: TelegramNotifier,
    logger: logging.Logger,
) -> None:
    threshold = int(cfg.get("signal_alert_threshold", 75))
    windows: list[int] = cfg.get("price_move_windows_minutes", [5, 15, 60])
    min_moves: dict = cfg.get("min_probability_move", {})
    max_window = max(windows) if windows else 60

    logger.info("--- cycle start ---")

    markets_raw = client.fetch_active_markets()
    if not markets_raw:
        logger.warning("No markets returned — skipping cycle")
        return

    markets = filter_markets(markets_raw, cfg)
    if not markets:
        logger.warning("No markets passed filter — skipping cycle")
        return

    logger.info(f"Processing {len(markets)} markets")

    for market in markets:
        market_id = market.get("id") or market.get("conditionId", "")
        if not market_id:
            continue
        try:
            _process_market(
                market=market,
                market_id=market_id,
                cfg=cfg,
                storage=storage,
                client=client,
                notifier=notifier,
                windows=windows,
                min_moves=min_moves,
                max_window=max_window,
                threshold=threshold,
                logger=logger,
            )
        except Exception as e:
            logger.error(f"Error processing market {market_id}: {e}", exc_info=True)

    logger.info("--- cycle end ---")


def _process_market(
    market: dict,
    market_id: str,
    cfg: dict,
    storage: Storage,
    client: PolymarketClient,
    notifier: TelegramNotifier,
    windows: list[int],
    min_moves: dict,
    max_window: int,
    threshold: int,
    logger: logging.Logger,
) -> None:
    now = utcnow_iso()

    storage.upsert_market({
        "market_id": market_id,
        "question": market.get("question"),
        "event_title": market.get("groupItemTitle") or market.get("category"),
        "category": market.get("category"),
        "url": market.get("url"),
        "volume": float(market.get("volume", 0) or 0),
        "liquidity": float(market.get("liquidity", 0) or 0),
        "end_date": market.get("endDate") or market.get("end_date"),
        "active": int(bool(market.get("active", True))),
        "closed": int(bool(market.get("closed", False))),
        "created_at": market.get("createdAt") or now,
        "updated_at": now,
    })

    # Try CLOB orderbook; gracefully fall back to Gamma prices.
    # clobTokenIds from Gamma API may be a JSON string — parse it first.
    orderbook = None
    raw_ids = market.get("clobTokenIds") or []
    if isinstance(raw_ids, str):
        try:
            raw_ids = json.loads(raw_ids)
        except Exception:
            raw_ids = []
    token_id = raw_ids[0] if isinstance(raw_ids, list) and raw_ids else None
    if token_id:
        orderbook = client.fetch_orderbook(str(token_id))
        if orderbook is None:
            logger.debug(f"CLOB unavailable for {market_id}, using Gamma prices")

    snapshot = build_snapshot(market, orderbook)
    storage.insert_snapshot(snapshot)

    recent = storage.get_recent_snapshots(market_id, max_window)
    if len(recent) < 2:
        return

    signals = detect_rapid_reprice(market_id, snapshot, recent, windows, min_moves)
    signals += detect_liquidity_spike(market_id, snapshot, recent)

    for sig in signals:
        score = score_signal(sig, market, cfg)
        sig["score"] = score
        sig["market_url"] = market.get("url") or ""
        storage.insert_signal(sig)

        if score >= threshold:
            send_alert(sig, market, score, notifier)


def _daily_report_due(now: datetime, last_date: str, cfg: dict) -> bool:
    """Return True once per UTC day after the configured hour."""
    rcfg = cfg.get("reporting", {})
    if not rcfg.get("enabled", False):
        return False
    hour = int(rcfg.get("daily_report_hour_utc", 23))
    today = now.strftime("%Y-%m-%d")
    return now.hour >= hour and today != last_date


def _run_reporting_pipeline(date_str: str, db_path: Path, cfg: dict, logger: logging.Logger) -> None:
    """Build and send the daily Polymarket report. Non-fatal — errors are logged only."""
    try:
        from reporting.aggregator import fetch_daily_signals
        from reporting.report_builder import PolymarketReportBuilder
        from shared.reporting import (
            build_brief,
            build_daily_index,
            render_html,
            write_report,
        )
        from shared.reporting.index_builder import build_nav_index

        data = fetch_daily_signals(db_path, date_str)
        report = PolymarketReportBuilder().build(data)
        md_path = write_report(report)
        render_html(report)
        build_daily_index(date_str)
        build_nav_index()

        brief = build_brief(date_str, [report])
        notifier = TelegramNotifier.from_config(cfg)
        notifier.send(brief)

        logger.info("Daily report sent | date=%s | md=%s", date_str, md_path)
    except Exception as exc:
        logger.error("Reporting pipeline failed (non-fatal): %s", exc, exc_info=True)


def main() -> None:
    cfg = load_config()
    logger = setup_logger(LOG_DIR)
    _write_pid()

    def _shutdown(signum, frame):
        logger.info("Shutdown signal received")
        _remove_pid()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    db_path = AGENT_ROOT / cfg["storage"]["sqlite_path"]
    csv_path = LOG_DIR / "signal_events.csv"

    storage = Storage(str(db_path), str(csv_path))
    client = PolymarketClient(cfg)
    notifier = TelegramNotifier.from_config(cfg)
    poll_interval = int(cfg.get("poll_interval_seconds", 120))

    logger.info(
        f"Polymarket Intelligence Monitor started"
        f" | pid={os.getpid()}"
        f" | dry_run={notifier.dry_run}"
        f" | interval={poll_interval}s"
    )

    last_daily_report_date = ""
    try:
        while True:
            try:
                run_cycle(cfg, storage, client, notifier, logger)
            except Exception as e:
                logger.error(f"Unhandled cycle error (continuing): {e}", exc_info=True)

            now = datetime.now(timezone.utc)
            if _daily_report_due(now, last_daily_report_date, cfg):
                date_str = now.strftime("%Y-%m-%d")
                _run_reporting_pipeline(date_str, db_path, cfg, logger)
                last_daily_report_date = date_str

            logger.info(f"Sleeping {poll_interval}s...")
            time.sleep(poll_interval)
    finally:
        _remove_pid()


if __name__ == "__main__":
    main()
