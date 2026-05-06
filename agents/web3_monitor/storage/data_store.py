import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from utils.logger import setup_logger

logger = setup_logger("data_store")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS price_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol     TEXT NOT NULL,
    timestamp  TEXT NOT NULL,
    price      REAL NOT NULL,
    change_24h REAL
);

CREATE TABLE IF NOT EXISTS tvl_history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    protocol  TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    tvl_usd   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    key       TEXT NOT NULL,
    sent_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ph_sym_ts   ON price_history(symbol, timestamp);
CREATE INDEX IF NOT EXISTS idx_tvl_prot_ts ON tvl_history(protocol, timestamp);
CREATE INDEX IF NOT EXISTS idx_al_key_ts   ON alert_log(key, sent_at);
"""


class DataStore:
    def __init__(self, config: dict):
        data_cfg  = config.get("data", {})
        db_path   = data_cfg.get("db_path", "/Volumes/AI_DISK/ai_workspace/data/web3_monitor/web3_monitor.db")
        self.cooldown_min = config.get("alerts", {}).get("cooldown_minutes", 120)

        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    # ----------------------------------------------------------------- prices
    def save_prices(self, prices: dict):
        now = datetime.utcnow().isoformat()
        rows = [(sym, now, d["price"], d.get("change_24h_pct"))
                for sym, d in prices.items() if d.get("price")]
        with self._conn() as conn:
            conn.executemany(
                "INSERT INTO price_history (symbol, timestamp, price, change_24h) VALUES (?,?,?,?)",
                rows,
            )

    def get_prev_tvl(self, protocol: str, hours: int = 25) -> Optional[float]:
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        with self._conn() as conn:
            row = conn.execute(
                """SELECT tvl_usd FROM tvl_history
                   WHERE protocol=? AND timestamp<=?
                   ORDER BY timestamp DESC LIMIT 1""",
                (protocol, cutoff),
            ).fetchone()
        return row[0] if row else None

    # ------------------------------------------------------------------- TVL
    def save_tvl(self, protocol: str, tvl_usd: float):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO tvl_history (protocol, timestamp, tvl_usd) VALUES (?,?,?)",
                (protocol, datetime.utcnow().isoformat(), tvl_usd),
            )

    # ----------------------------------------------------------------- alerts
    def can_alert(self, key: str) -> bool:
        cutoff = (datetime.utcnow() - timedelta(minutes=self.cooldown_min)).isoformat()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM alert_log WHERE key=? AND sent_at>? LIMIT 1",
                (key, cutoff),
            ).fetchone()
        return row is None

    def record_alert(self, key: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO alert_log (key, sent_at) VALUES (?,?)",
                (key, datetime.utcnow().isoformat()),
            )
