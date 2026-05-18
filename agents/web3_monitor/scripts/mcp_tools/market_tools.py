"""Read-only market data tools."""
from __future__ import annotations

from core.models import ToolContext, ToolResult


def scan_dex_anomalies(payload: dict, ctx: ToolContext) -> dict:
    assets = payload.get("assets") or ctx.config.get("assets", [])
    chains = payload.get("chains") or ctx.config.get("chains", [])
    signals = ctx.service("dex").scan_assets(assets, chains)
    return ToolResult(
        ok=True,
        tool="scan_dex_anomalies",
        signals=signals,
        meta={"assets": list(assets), "chains": list(chains), "count": len(signals)},
    ).to_json()


def scan_market_movers(payload: dict, ctx: ToolContext) -> dict:
    min_score = payload.get("min_score", ctx.config.get("thresholds", {}).get("coingecko_market_min_score", 60))
    signals = ctx.service("coingecko_market").scan_top100(min_score=min_score)
    return ToolResult(
        ok=True,
        tool="scan_market_movers",
        signals=signals,
        meta={"min_score": min_score, "count": len(signals)},
    ).to_json()


def scan_new_pools(payload: dict, ctx: ToolContext) -> dict:
    chains = payload.get("chains") or ctx.config.get("chains", [])
    signals = ctx.service("geckoterminal").scan_new_pools(chains)
    return ToolResult(
        ok=True,
        tool="scan_new_pools",
        signals=signals,
        meta={"chains": list(chains), "count": len(signals)},
    ).to_json()


def get_macro_snapshot(payload: dict, ctx: ToolContext) -> dict:
    chains = payload.get("chains") or ctx.config.get("chains", [])
    data = ctx.service("defillama").macro_snapshot(chains)
    return ToolResult(
        ok=True,
        tool="get_macro_snapshot",
        data=data,
        meta={"chains": list(chains)},
    ).to_json()


def scan_prediction_markets(payload: dict, ctx: ToolContext) -> dict:
    categories = payload.get("categories") or ctx.config.get("polymarket_categories", [])
    prev_state = payload.get("prev_state") or ctx.state.get("pm_state", {})
    signals = ctx.service("polymarket").scan_categories(categories, prev_state=prev_state)
    return ToolResult(
        ok=True,
        tool="scan_prediction_markets",
        signals=signals,
        meta={
            "categories": list(categories),
            "count": len(signals),
            "signal_count": sum(1 for signal in signals if signal.get("is_signal")),
        },
    ).to_json()
