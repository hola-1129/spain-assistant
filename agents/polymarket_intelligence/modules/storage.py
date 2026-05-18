from __future__ import annotations

import csv
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger("polymarket_intelligence.storage")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (
    market_id TEXT PRIMARY KEY,
    question TEXT,
    event_title TEXT,
    category TEXT,
    url TEXT,
    volume REAL,
    liquidity REAL,
    end_date TEXT,
    active INTEGER,
    closed INTEGER,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS market_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT,
    timestamp TEXT,
    yes_price REAL,
    no_price REAL,
    best_bid REAL,
    best_ask REAL,
    spread REAL,
    volume REAL,
    liquidity REAL
);

CREATE TABLE IF NOT EXISTS signal_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT,
    timestamp TEXT,
    signal_type TEXT,
    score INTEGER,
    probability_before REAL,
    probability_after REAL,
    probability_delta REAL,
    window_minutes INTEGER,
    liquidity_delta REAL,
    reason TEXT,
    market_url TEXT
);
"""

_CSV_FIELDS = [
    "market_id", "timestamp", "signal_type", "score",
    "probability_before", "probability_after", "probability_delta",
    "window_minutes", "liquidity_delta", "reason", "market_url",
]


class Storage:
    def __init__(self, db_path: str, csv_path: str) -> None:
        self.db_path = Path(db_path)
        self.csv_path = Path(csv_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._init_csv()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(_SCHEMA)

    def _init_csv(self) -> None:
        if not self.csv_path.exists():
            with open(self.csv_path, "w", newline="") as f:
                csv.DictWriter(f, fieldnames=_CSV_FIELDS).writeheader()

    # ------------------------------------------------------------------ writes

    def upsert_market(self, market: dict) -> None:
        sql = """
        INSERT INTO markets
            (market_id, question, event_title, category, url,
             volume, liquidity, end_date, active, closed, created_at, updated_at)
        VALUES
            (:market_id, :question, :event_title, :category, :url,
             :volume, :liquidity, :end_date, :active, :closed, :created_at, :updated_at)
        ON CONFLICT(market_id) DO UPDATE SET
            question=excluded.question,
            event_title=excluded.event_title,
            volume=excluded.volume,
            liquidity=excluded.liquidity,
            active=excluded.active,
            closed=excluded.closed,
            updated_at=excluded.updated_at
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(sql, market)
        except Exception as e:
            logger.error(f"upsert_market failed [{market.get('market_id')}]: {e}")

    def insert_snapshot(self, snapshot: dict) -> None:
        sql = """
        INSERT INTO market_snapshots
            (market_id, timestamp, yes_price, no_price,
             best_bid, best_ask, spread, volume, liquidity)
        VALUES
            (:market_id, :timestamp, :yes_price, :no_price,
             :best_bid, :best_ask, :spread, :volume, :liquidity)
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(sql, snapshot)
        except Exception as e:
            logger.error(f"insert_snapshot failed [{snapshot.get('market_id')}]: {e}")

    def insert_signal(self, signal: dict) -> None:
        sql = """
        INSERT INTO signal_events
            (market_id, timestamp, signal_type, score,
             probability_before, probability_after, probability_delta,
             window_minutes, liquidity_delta, reason, market_url)
        VALUES
            (:market_id, :timestamp, :signal_type, :score,
             :probability_before, :probability_after, :probability_delta,
             :window_minutes, :liquidity_delta, :reason, :market_url)
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(sql, signal)
            self._append_csv(signal)
        except Exception as e:
            logger.error(f"insert_signal failed [{signal.get('market_id')}]: {e}")

    def _append_csv(self, signal: dict) -> None:
        try:
            with open(self.csv_path, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS, extrasaction="ignore")
                writer.writerow(signal)
        except Exception as e:
            logger.error(f"csv append failed: {e}")

    # ------------------------------------------------------------------ reads

    def get_recent_snapshots(self, market_id: str, minutes: int) -> list[dict]:
        sql = """
        SELECT * FROM market_snapshots
        WHERE market_id = ?
          AND timestamp >= datetime('now', ? || ' minutes')
        ORDER BY timestamp ASC
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(sql, (market_id, f"-{minutes}")).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"get_recent_snapshots failed [{market_id}]: {e}")
            return []
