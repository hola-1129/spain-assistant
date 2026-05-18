"""SQLite storage for Web3 Monitor v2."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

try:
    from signal_model import Signal
except ModuleNotFoundError:  # allows `from scripts.storage import ...`
    from .signal_model import Signal


SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT,
    token TEXT,
    symbol TEXT,
    chain TEXT,
    signal_type TEXT,
    price REAL,
    volume REAL,
    liquidity REAL,
    score REAL,
    reason TEXT,
    raw_data_json TEXT,
    telegram_sent INTEGER DEFAULT 0,
    price_1h REAL,
    price_change_1h_pct REAL,
    price_6h REAL,
    price_change_6h_pct REAL,
    price_24h REAL,
    price_change_24h_pct REAL,
    reviewed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp);
CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);
CREATE INDEX IF NOT EXISTS idx_signals_type ON signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_signals_source ON signals(source);
"""


def resolve_db_path(root: Path, cfg: dict[str, Any]) -> Path:
    raw = cfg.get("storage", {}).get("sqlite_path", "data/web3_monitor.db")
    p = Path(raw)
    if not p.is_absolute():
        p = (root / p).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


class SignalStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def save_signal(self, signal: Signal, telegram_sent: bool = False) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO signals (
                    timestamp, source, token, symbol, chain, signal_type,
                    price, volume, liquidity, score, reason, raw_data_json,
                    telegram_sent
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.timestamp,
                    signal.source,
                    signal.token,
                    signal.symbol,
                    signal.chain,
                    signal.signal_type,
                    signal.price,
                    signal.volume,
                    signal.liquidity,
                    signal.score,
                    signal.reason,
                    json.dumps(signal.raw_data, ensure_ascii=False, default=str),
                    1 if telegram_sent else 0,
                ),
            )
            return int(cur.lastrowid)

    def get_recent_signals(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM signals ORDER BY timestamp DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_signal_by_id(self, signal_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
        return dict(row) if row else None

    def update_signal_review(self, signal_id: int, updates: dict[str, Any]) -> None:
        allowed = {
            "price_1h", "price_change_1h_pct",
            "price_6h", "price_change_6h_pct",
            "price_24h", "price_change_24h_pct",
            "reviewed_at",
        }
        fields = [key for key in updates if key in allowed]
        if not fields:
            return
        assignments = ", ".join(f"{field} = ?" for field in fields)
        values = [updates[field] for field in fields]
        values.append(signal_id)
        with self.connect() as conn:
            conn.execute(f"UPDATE signals SET {assignments} WHERE id = ?", values)

    def get_score_summary(self) -> dict[str, Any]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    source,
                    signal_type,
                    COUNT(*) AS count,
                    AVG(score) AS avg_score,
                    AVG(price_change_1h_pct) AS avg_1h,
                    AVG(price_change_6h_pct) AS avg_6h,
                    AVG(price_change_24h_pct) AS avg_24h,
                    SUM(CASE WHEN telegram_sent = 1 THEN 1 ELSE 0 END) AS telegram_sent_count
                FROM signals
                GROUP BY source, signal_type
                ORDER BY count DESC
                """
            ).fetchall()
        return {"groups": [dict(row) for row in rows]}
