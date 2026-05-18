"""Read today's web3 signals from SQLite, group by source, return structured data.

Deduplication: per (symbol, signal_type, source), keep max-score row.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

_KNOWN_SOURCES = ["coingecko", "cross_signal", "dexscreener", "geckoterminal", "polymarket"]


def fetch_daily_signals(db_path: str | Path, date_str: str) -> dict[str, Any]:
    """Return aggregated daily signal data for date_str (YYYY-MM-DD).

    Return shape:
    {
        "date": str,
        "total_raw": int,
        "signals": [                 # deduped by (symbol, signal_type, source), sorted score desc
            {
                "id": int,
                "source": str,
                "symbol": str,
                "chain": str | None,
                "signal_type": str,
                "score": float | None,
                "reason": str,
                "volume": float | None,
                "liquidity": float | None,
                "timestamp": str,
            }, ...
        ],
        "by_source": {source: {"count": int, "max_score": float, "avg_score": float}},
        "cross_signals": [...],      # signals where source == "cross_signal"
        "top_signals": [...],        # top 10 by score across all sources
    }
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return {"date": date_str, "total_raw": 0, "signals": [], "by_source": {},
                "cross_signals": [], "top_signals": []}

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return _query(conn, date_str)
    except Exception as exc:
        return {"date": date_str, "total_raw": 0, "signals": [], "by_source": {},
                "cross_signals": [], "top_signals": [], "error": str(exc)}
    finally:
        conn.close()


def _query(conn: sqlite3.Connection, date_str: str) -> dict[str, Any]:
    total_raw = conn.execute(
        "SELECT COUNT(*) FROM signals WHERE substr(timestamp,1,10) = ?",
        (date_str,),
    ).fetchone()[0]

    # Deduped: per (symbol, signal_type, source), keep max-score row
    rows = conn.execute(
        """
        SELECT source, symbol, chain, signal_type,
               MAX(score)     AS score,
               MAX(volume)    AS volume,
               MAX(liquidity) AS liquidity,
               reason,
               MAX(timestamp) AS timestamp
        FROM signals
        WHERE substr(timestamp,1,10) = ?
        GROUP BY symbol, signal_type, source
        ORDER BY score DESC NULLS LAST, timestamp DESC
        """,
        (date_str,),
    ).fetchall()

    signals = [dict(r) for r in rows]

    # by_source aggregation
    by_source: dict[str, dict] = {}
    for s in signals:
        src = s["source"] or "unknown"
        if src not in by_source:
            by_source[src] = {"count": 0, "max_score": 0.0, "sum_score": 0.0}
        by_source[src]["count"] += 1
        sc = s["score"] or 0.0
        by_source[src]["max_score"] = max(by_source[src]["max_score"], sc)
        by_source[src]["sum_score"] += sc
    for src, stats in by_source.items():
        stats["avg_score"] = round(stats["sum_score"] / stats["count"], 1) if stats["count"] else 0.0
        del stats["sum_score"]

    cross = [s for s in signals if s["source"] == "cross_signal"]
    top   = sorted(signals, key=lambda s: s["score"] or 0, reverse=True)[:10]

    return {
        "date": date_str,
        "total_raw": total_raw,
        "signals": signals,
        "by_source": by_source,
        "cross_signals": cross,
        "top_signals": top,
    }
