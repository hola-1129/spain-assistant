"""Read today's polymarket signals from SQLite, deduplicate, and return structured data.

Deduplication rule: per (market_id, signal_type), keep only the max-score row.
This collapses the many repeated alerts for the same market event.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def fetch_daily_signals(db_path: str | Path, date_str: str) -> dict[str, Any]:
    """Return aggregated daily signal data for date_str (YYYY-MM-DD).

    Return shape:
    {
        "date": str,
        "total_raw": int,            # raw rows before dedup
        "signals": [                 # deduped, sorted by score desc
            {
                "signal_type": str,
                "score": int,
                "market_id": str,
                "question": str,
                "event_title": str,
                "category": str | None,
                "url": str | None,
                "probability_before": float | None,
                "probability_after": float | None,
                "probability_delta": float | None,
                "window_minutes": int | None,
                "liquidity_delta": float | None,
                "reason": str,
            }, ...
        ],
        "by_type": {signal_type: {"count": int, "max_score": int}},
        "by_category": {category: {"count": int, "max_score": int}},
    }
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return {"date": date_str, "total_raw": 0, "signals": [], "by_type": {}, "by_category": {}}

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return _query(conn, date_str)
    except Exception as exc:
        return {"date": date_str, "total_raw": 0, "signals": [], "by_type": {}, "by_category": {},
                "error": str(exc)}
    finally:
        conn.close()


def _query(conn: sqlite3.Connection, date_str: str) -> dict[str, Any]:
    # Total raw count
    total_raw = conn.execute(
        "SELECT COUNT(*) FROM signal_events WHERE substr(timestamp,1,10) = ?",
        (date_str,),
    ).fetchone()[0]

    # Deduplicated: per (market_id, signal_type), keep max-score row
    rows = conn.execute(
        """
        SELECT se.market_id,
               se.signal_type,
               MAX(se.score)            AS score,
               se.probability_before,
               se.probability_after,
               se.probability_delta,
               se.window_minutes,
               MAX(se.liquidity_delta)  AS liquidity_delta,
               se.reason,
               se.market_url,
               m.question,
               m.event_title,
               m.category,
               m.url
        FROM signal_events se
        LEFT JOIN markets m ON se.market_id = m.market_id
        WHERE substr(se.timestamp,1,10) = ?
        GROUP BY se.market_id, se.signal_type
        ORDER BY score DESC
        """,
        (date_str,),
    ).fetchall()

    signals = [dict(r) for r in rows]

    # by_type stats
    by_type: dict[str, dict] = {}
    for s in signals:
        t = s["signal_type"] or "unknown"
        if t not in by_type:
            by_type[t] = {"count": 0, "max_score": 0}
        by_type[t]["count"] += 1
        by_type[t]["max_score"] = max(by_type[t]["max_score"], s["score"] or 0)

    # by_category stats
    by_cat: dict[str, dict] = {}
    for s in signals:
        cat = s.get("category") or "Uncategorized"
        if cat not in by_cat:
            by_cat[cat] = {"count": 0, "max_score": 0}
        by_cat[cat]["count"] += 1
        by_cat[cat]["max_score"] = max(by_cat[cat]["max_score"], s["score"] or 0)

    return {
        "date": date_str,
        "total_raw": total_raw,
        "signals": signals,
        "by_type": by_type,
        "by_category": by_cat,
    }
