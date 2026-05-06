import csv
import os
import sqlite3
from datetime import datetime, timedelta

from utils.logger import setup_logger

logger = setup_logger("data_store")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS price_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT    NOT NULL,
    asset_type  TEXT    NOT NULL,
    timestamp   TEXT    NOT NULL,
    price       REAL    NOT NULL,
    volume      REAL,
    open_price  REAL,
    high_price  REAL,
    low_price   REAL,
    prev_close  REAL
);

CREATE TABLE IF NOT EXISTS iv_history (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol  TEXT NOT NULL,
    date    TEXT NOT NULL,
    atm_iv  REAL NOT NULL,
    UNIQUE(symbol, date)
);

CREATE TABLE IF NOT EXISTS alert_history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol    TEXT NOT NULL,
    rule_type TEXT NOT NULL,
    message   TEXT NOT NULL,
    sent_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signal_history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol    TEXT  NOT NULL,
    timestamp TEXT  NOT NULL,
    kind      TEXT  NOT NULL,
    direction TEXT  NOT NULL,
    strength  REAL  NOT NULL,
    score     REAL  NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sh_sym_ts ON signal_history(symbol, timestamp);

CREATE INDEX IF NOT EXISTS idx_ph_sym_ts  ON price_history(symbol, timestamp);
CREATE INDEX IF NOT EXISTS idx_iv_sym_dt  ON iv_history(symbol, date);
CREATE INDEX IF NOT EXISTS idx_ah_sym_rule ON alert_history(symbol, rule_type, sent_at);
"""


class DataStore:
    def __init__(self, config: dict):
        data_cfg = config.get("data", {})
        data_dir = data_cfg.get("market_data_dir", "/Volumes/AI_DISK/data/market_data")
        db_name = data_cfg.get("db_name", "finance_bot.db")
        self.export_csv = data_cfg.get("export_csv", True)
        self.data_dir = data_dir
        self.cooldown_hours = config.get("alerts", {}).get("cooldown_hours", 4)

        os.makedirs(data_dir, exist_ok=True)
        self.db_path = os.path.join(data_dir, db_name)
        self._init_db()

    # ------------------------------------------------------------------ setup
    def _init_db(self):
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    # ------------------------------------------------------------------ prices
    def save_prices(self, prices: dict, asset_type: str):
        now = datetime.utcnow().isoformat()
        rows = [
            (
                sym, asset_type, now,
                d.get("price"), d.get("volume"),
                d.get("open"), d.get("high"),
                d.get("low"), d.get("prev_close"),
            )
            for sym, d in prices.items()
            if d.get("price") is not None
        ]
        with self._conn() as conn:
            conn.executemany(
                """INSERT INTO price_history
                   (symbol, asset_type, timestamp, price, volume,
                    open_price, high_price, low_price, prev_close)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                rows,
            )
        if self.export_csv:
            self._append_csv(prices, asset_type, now)

    def _append_csv(self, prices: dict, asset_type: str, ts: str):
        path = os.path.join(self.data_dir, f"{asset_type}_prices.csv")
        write_header = not os.path.exists(path)
        with open(path, "a", newline="") as f:
            w = csv.writer(f)
            if write_header:
                w.writerow(["timestamp", "symbol", "price", "volume",
                             "open", "high", "low", "prev_close"])
            for sym, d in prices.items():
                w.writerow([ts, sym, d.get("price"), d.get("volume"),
                             d.get("open"), d.get("high"),
                             d.get("low"), d.get("prev_close")])

    def get_latest_prices(self) -> dict:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT symbol, price, asset_type
                FROM price_history
                WHERE (symbol, timestamp) IN (
                    SELECT symbol, MAX(timestamp)
                    FROM price_history GROUP BY symbol
                )
            """).fetchall()
        return {r[0]: {"price": r[1], "asset_type": r[2]} for r in rows}

    # ------------------------------------------------------------------ IV
    def save_iv(self, symbol: str, date: str, atm_iv: float):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO iv_history (symbol, date, atm_iv) VALUES (?,?,?)",
                (symbol, date, atm_iv),
            )

    def get_iv_history(self, symbol: str, days: int = 365) -> list:
        since = (datetime.utcnow() - timedelta(days=days)).date().isoformat()
        with self._conn() as conn:
            return conn.execute(
                "SELECT date, atm_iv FROM iv_history WHERE symbol=? AND date>=? ORDER BY date",
                (symbol, since),
            ).fetchall()

    # ------------------------------------------------------------------ alerts
    def can_send_alert(self, symbol: str, rule_type: str) -> bool:
        cutoff = (datetime.utcnow() - timedelta(hours=self.cooldown_hours)).isoformat()
        with self._conn() as conn:
            row = conn.execute(
                """SELECT 1 FROM alert_history
                   WHERE symbol=? AND rule_type=? AND sent_at>?
                   LIMIT 1""",
                (symbol, rule_type, cutoff),
            ).fetchone()
        return row is None

    def record_alert(self, symbol: str, rule_type: str, message: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO alert_history (symbol, rule_type, message, sent_at) VALUES (?,?,?,?)",
                (symbol, rule_type, message, datetime.utcnow().isoformat()),
            )

    # --------------------------------------------------------- unusual movers
    def save_unusual_movers(self, results: list, scan_type: str):
        """Persist scanner results as a date-stamped CSV."""
        if not results:
            return
        ts      = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        out_dir = os.path.join(self.data_dir, "unusual_movers")
        os.makedirs(out_dir, exist_ok=True)
        path    = os.path.join(out_dir, f"{scan_type}_{ts}.csv")
        import csv
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=[k for k in results[0].keys() if k != "signals"])
            w.writeheader()
            for row in results:
                clean = {k: v for k, v in row.items() if k != "signals"}
                w.writerow(clean)

    # ---------------------------------------------------------------- signals
    def save_signals(self, symbol: str, signals: list, score: float):
        now  = datetime.utcnow().isoformat()
        rows = [(symbol, now, s.kind, s.direction, s.strength, score)
                for s in signals]
        with self._conn() as conn:
            conn.executemany(
                """INSERT INTO signal_history
                   (symbol, timestamp, kind, direction, strength, score)
                   VALUES (?,?,?,?,?,?)""",
                rows,
            )
