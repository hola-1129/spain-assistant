"""Thin orchestration layer for Web3 Monitor.

The agent schedules and composes tools. Market fetchers, scoring, persistence,
notifications, and queries live behind MCP-ready tool functions.
"""
from __future__ import annotations

import logging
import signal as os_signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure shared.llm is importable (ai_workspace/ must be on PYTHONPATH)
_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

from coingecko_market_monitor import CoinGeckoMarketMonitor
from core.config import interval_seconds, load_config, setup_logging, validate_runtime_guards
from core.models import ToolContext
from core.state import load_runtime_state, save_runtime_state
from cross_signal_engine import evaluate as evaluate_signal, pair_dex_with_polymarket
from defillama_monitor import DefiLlamaMonitor
from dexscreener_monitor import DexScreenerMonitor
from geckoterminal_monitor import GeckoTerminalMonitor
from mcp_tools.market_tools import (
    get_macro_snapshot,
    scan_dex_anomalies,
    scan_market_movers,
    scan_new_pools,
    scan_prediction_markets,
)
from mcp_tools.notify_tools import send_telegram_alert
from mcp_tools.signal_tools import persist_signal
from polymarket_monitor import PolymarketMonitor
from storage import SignalStore, resolve_db_path
from telegram_notify import TelegramNotifier


class Web3MonitorAgent:
    def __init__(self, root: Path):
        self.root = root
        self.config = load_config(root)
        setup_logging(root, self.config)
        validate_runtime_guards(self.config)
        self.log = logging.getLogger("web3_monitor.agent")
        self.running = True
        self.ctx = self._build_context()
        self.explainer = self._init_explainer()

    def _init_explainer(self):
        """Init Qwen signal explainer if llm_enrichment.enabled=true. Fails gracefully."""
        if not self.config.get("llm_enrichment", {}).get("enabled", False):
            return None
        try:
            from summarizer.signal_explainer import SignalExplainer
            explainer = SignalExplainer.from_cfg(self.config)
            self.log.info("Qwen signal explainer initialised (llm_enrichment enabled)")
            return explainer
        except Exception as e:
            self.log.warning("Qwen explainer init failed, enrichment disabled: %s", e)
            return None

    def _enrichment_on(self, key: str) -> bool:
        enrich = self.config.get("llm_enrichment", {})
        return bool(self.explainer and enrich.get(key, False))

    def _build_context(self) -> ToolContext:
        cfg = self.config
        rl = cfg.get("rate_limit", {})
        timeout = cfg.get("http_timeout", 20)
        thresholds = cfg.get("thresholds", {})
        runtime_state = load_runtime_state(self.root, cfg)

        services = {
            "dex": DexScreenerMonitor(rl.get("dexscreener_min_gap", 1.0), timeout, thresholds),
            "coingecko_market": CoinGeckoMarketMonitor(rl.get("coingecko_market_min_gap", 2.1), timeout, thresholds),
            "geckoterminal": GeckoTerminalMonitor(rl.get("geckoterminal_min_gap", 2.0), timeout, thresholds),
            "defillama": DefiLlamaMonitor(rl.get("defillama_min_gap", 1.0), timeout),
            "polymarket": PolymarketMonitor(rl.get("polymarket_min_gap", 1.0), timeout, thresholds),
            "telegram": TelegramNotifier.from_config(cfg.get("telegram", {})),
            "store": SignalStore(resolve_db_path(self.root, cfg)),
        }
        state = {
            "pm_state": runtime_state.get("pm_state") or {},
            "alert_state": runtime_state.get("alert_state") or {},
            "dex_candidates": [],
            "pm_signals": [],
            "macro": {},
        }
        return ToolContext(root=self.root, config=cfg, services=services, state=state)

    def _stop(self, *_args) -> None:
        self.log.info("shutdown signal received")
        self.running = False

    def _intervals(self) -> dict[str, int]:
        cfg = self.config
        return {
            "dex": interval_seconds(cfg, "dex_minutes", 5),
            "coingecko_market": interval_seconds(cfg, "coingecko_market_minutes", 15),
            "polymarket": interval_seconds(cfg, "polymarket_minutes", 10),
            "new_pools": interval_seconds(cfg, "new_pools_minutes", 30),
            "defillama": interval_seconds(cfg, "defillama_minutes", 60),
        }

    def _cooldown_ok(self, key: str, cooldown_seconds: int) -> bool:
        now = time.time()
        alert_state = self.ctx.state.setdefault("alert_state", {})
        if now - float(alert_state.get(key, 0.0)) < cooldown_seconds:
            return False
        return True

    def _mark_alert(self, key: str) -> None:
        self.ctx.state.setdefault("alert_state", {})[key] = time.time()

    def _persist(self, signal: dict[str, Any], telegram_sent: bool = False) -> None:
        persist_signal({"signal": signal, "telegram_sent": telegram_sent}, self.ctx)

    def _notify_signal(self, signal: dict[str, Any], cooldown_key: str, cooldown_seconds: int) -> bool:
        if not self._cooldown_ok(cooldown_key, cooldown_seconds):
            return False
        result = send_telegram_alert({"signal": signal}, self.ctx)
        sent = bool(result.get("ok"))
        if sent:
            self._mark_alert(cooldown_key)
        return sent

    def _handle_market_movers(self, movers: list[dict[str, Any]]) -> tuple[int, int]:
        cooldown = self.config.get("thresholds", {}).get("market_mover_cooldown_minutes", 60) * 60
        logged = 0
        pushed = 0
        for mover in movers:
            mover["ts"] = datetime.now(timezone.utc).isoformat()
            if self._enrichment_on("market_mover_explain"):
                explanation = self.explainer.explain_mover(mover)
                if explanation:
                    mover["qwen_explanation"] = explanation
            key = f"market_mover:{mover.get('asset')}"
            sent = self._notify_signal(mover, key, cooldown)
            pushed += 1 if sent else 0
            self._persist(mover, telegram_sent=sent)
            logged += 1
        return logged, pushed

    def _score_cross_signals(self) -> tuple[int, int]:
        pairs = pair_dex_with_polymarket(
            self.ctx.state.get("dex_candidates", []),
            self.ctx.state.get("pm_signals", []),
        )
        min_thr = self.config.get("thresholds", {}).get("min_signal_score", 60)
        cooldown = self.config.get("thresholds", {}).get("signal_cooldown_minutes", 60) * 60
        logged = 0
        pushed = 0

        for dex_signal, pm_signal in pairs:
            scored = evaluate_signal(dex_signal, pm_signal, self.config)
            if scored is None:
                continue
            scored["ts"] = datetime.now(timezone.utc).isoformat()
            sent = False
            if scored.get("score", 0) >= min_thr:
                key = "signal:{type}:{asset}:{chain}".format(
                    type=scored.get("type"),
                    asset=scored.get("asset"),
                    chain=scored.get("chain") or "",
                )
                # Optional Qwen explanation — appended by format_signal_alert if present
                if self._enrichment_on("signal_explain"):
                    explanation = self.explainer.explain(scored)
                    if explanation:
                        scored["qwen_explanation"] = explanation
                sent = self._notify_signal(scored, key, cooldown)
                pushed += 1 if sent else 0
            self._persist(scored, telegram_sent=sent)
            logged += 1
        return logged, pushed

    def _update_pm_state(self, snapshots: list[dict[str, Any]]) -> None:
        pm_state = dict(self.ctx.state.get("pm_state") or {})
        for snap in snapshots:
            event_id = snap.get("event_id")
            if not event_id:
                continue
            pm_state[str(event_id)] = {
                "probability": snap.get("probability_now"),
                "volume": snap.get("volume_24h_usd", 0),
            }
        self.ctx.state["pm_state"] = pm_state
        self.ctx.state["pm_signals"] = [snap for snap in snapshots if snap.get("is_signal")]

    def _save_state(self) -> None:
        save_runtime_state(
            self.root,
            self.config,
            self.ctx.state.get("pm_state") or {},
            self.ctx.state.get("alert_state") or {},
        )

    def run_once(self) -> dict[str, Any]:
        logged_total = 0
        pushed_total = 0
        new_pools_count = 0

        dex_result = scan_dex_anomalies({}, self.ctx)
        self.ctx.state["dex_candidates"] = dex_result.get("signals", [])

        market_result = scan_market_movers({}, self.ctx)
        market_logged, market_pushed = self._handle_market_movers(market_result.get("signals", []))
        logged_total += market_logged
        pushed_total += market_pushed

        new_pool_result = scan_new_pools({}, self.ctx)
        for pool in new_pool_result.get("signals", []):
            pool["ts"] = datetime.now(timezone.utc).isoformat()
            self._persist(pool, telegram_sent=False)
        new_pools_count = len(new_pool_result.get("signals", []))

        macro_result = get_macro_snapshot({}, self.ctx)
        self.ctx.state["macro"] = macro_result.get("data", {})

        pm_result = scan_prediction_markets({"prev_state": self.ctx.state.get("pm_state", {})}, self.ctx)
        self._update_pm_state(pm_result.get("signals", []))

        logged, pushed = self._score_cross_signals()
        logged_total += logged
        pushed_total += pushed

        self._save_state()
        macro = self.ctx.state.get("macro") or {}
        summary = {
            "logged": logged_total,
            "pushed": pushed_total,
            "new_pools": new_pools_count,
            "chains_tvl": len(macro.get("watch_chains_tvl", [])),
        }
        self.log.info(
            "▶ cycle done — logged=%s pushed=%s new_pools=%s chains_tvl=%s",
            summary["logged"],
            summary["pushed"],
            summary["new_pools"],
            summary["chains_tvl"],
        )
        return summary

    def _maybe_run_daily_report(self, now_utc: datetime, last_date: str) -> str:
        """Emit daily report once per UTC day after the configured hour. Returns updated last_date."""
        rcfg = self.config.get("reporting", {})
        if not rcfg.get("enabled", False):
            return last_date
        hour = int(rcfg.get("daily_report_hour_utc", 23))
        today = now_utc.strftime("%Y-%m-%d")
        if now_utc.hour < hour or today == last_date:
            return last_date
        try:
            from reporting.aggregator import fetch_daily_signals
            from reporting.report_builder import Web3ReportBuilder
            from shared.reporting import (
                build_brief,
                build_daily_index,
                render_html,
                write_report,
            )
            from shared.reporting.index_builder import build_nav_index
            from shared.utils.telegram import TelegramNotifier

            db_path = self.ctx.service("store").db_path
            data    = fetch_daily_signals(db_path, today)
            report  = Web3ReportBuilder().build(data)
            md_path = write_report(report)
            render_html(report)
            build_daily_index(today)
            build_nav_index()

            brief = build_brief(today, [report])
            TelegramNotifier.from_config(self.config).send(brief)
            self.log.info("Daily report sent | date=%s | md=%s", today, md_path)
        except Exception as exc:
            self.log.error("Reporting pipeline failed (non-fatal): %s", exc, exc_info=True)
        return today

    def run_forever(self) -> int:
        os_signal.signal(os_signal.SIGINT, self._stop)
        os_signal.signal(os_signal.SIGTERM, self._stop)

        telegram = self.ctx.service("telegram")
        if telegram.enabled:
            telegram.send("✅ Web3 Monitor v2 started (MCP-ready, dry-run=true, read-only).")

        intervals = self._intervals()
        tick_sec = max(int(self.config.get("scan_intervals", {}).get("tick_seconds", 60)), 30)
        self.log.info(
            "loop tick=%ss intervals=%s",
            tick_sec,
            ", ".join(f"{name}:{seconds // 60}m" for name, seconds in intervals.items()),
        )

        last_run = {name: 0.0 for name in intervals}
        last_daily_report_date = ""
        while self.running:
            try:
                now = time.time()
                due = {name: now - last_run[name] >= seconds for name, seconds in intervals.items()}
                if any(due.values()):
                    self.log.info("▶ due scan modules: %s", ", ".join(name for name, is_due in due.items() if is_due))

                market_logged = 0
                market_pushed = 0
                new_pools_count = 0

                if due["dex"]:
                    result = scan_dex_anomalies({}, self.ctx)
                    self.ctx.state["dex_candidates"] = result.get("signals", [])
                    last_run["dex"] = now

                if due["coingecko_market"]:
                    result = scan_market_movers({}, self.ctx)
                    market_logged, market_pushed = self._handle_market_movers(result.get("signals", []))
                    last_run["coingecko_market"] = now

                if due["new_pools"]:
                    result = scan_new_pools({}, self.ctx)
                    for pool in result.get("signals", []):
                        pool["ts"] = datetime.now(timezone.utc).isoformat()
                        self._persist(pool, telegram_sent=False)
                    new_pools_count = len(result.get("signals", []))
                    last_run["new_pools"] = now

                if due["defillama"]:
                    result = get_macro_snapshot({}, self.ctx)
                    self.ctx.state["macro"] = result.get("data", {})
                    last_run["defillama"] = now

                if due["polymarket"]:
                    result = scan_prediction_markets({"prev_state": self.ctx.state.get("pm_state", {})}, self.ctx)
                    self._update_pm_state(result.get("signals", []))
                    last_run["polymarket"] = now

                if due["dex"] or due["polymarket"]:
                    logged, pushed = self._score_cross_signals()
                    macro = self.ctx.state.get("macro") or {}
                    self.log.info(
                        "▶ cycle done — logged=%s pushed=%s new_pools=%s chains_tvl=%s",
                        logged + market_logged,
                        pushed + market_pushed,
                        new_pools_count,
                        len(macro.get("watch_chains_tvl", [])),
                    )
                elif due["coingecko_market"]:
                    self.log.info(
                        "▶ market mover cycle done — logged=%s pushed=%s",
                        market_logged,
                        market_pushed,
                    )

                if any(due.values()):
                    self._save_state()

                now_utc = datetime.now(timezone.utc)
                last_daily_report_date = self._maybe_run_daily_report(
                    now_utc, last_daily_report_date
                )
            except Exception as e:
                self.log.error("cycle error: %s", e, exc_info=True)

            for _ in range(tick_sec):
                if not self.running:
                    break
                time.sleep(1)

        self.log.info("exit clean")
        return 0
