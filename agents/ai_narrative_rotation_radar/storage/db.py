"""
SQLite persistence — daily snapshots, theme scores, signal events, CSV export.
"""
from __future__ import annotations

import csv
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from core.theme_scorer import RadarSnapshot

logger = logging.getLogger("radar.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,
    ticker          TEXT NOT NULL,
    last_close      REAL,
    ret_1d          REAL,
    ret_5d          REAL,
    ret_1m          REAL,
    ret_3m          REAL,
    ret_ytd         REAL,
    rs_spy_1d       REAL,
    rs_spy_5d       REAL,
    rs_spy_1m       REAL,
    rs_qqq_1m       REAL,
    above_20dma     INTEGER,
    above_50dma     INTEGER,
    above_200dma    INTEGER,
    volume_ratio    REAL,
    drawdown_52w    REAL,
    composite_score REAL,
    UNIQUE(date, ticker)
);

CREATE TABLE IF NOT EXISTS theme_scores (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    date             TEXT NOT NULL,
    theme_key        TEXT NOT NULL,
    theme_name       TEXT,
    total_tickers    INTEGER,
    breadth_rs       REAL,
    breadth_20dma    REAL,
    avg_rs_spy_1m    REAL,
    avg_rs_spy_1d    REAL,
    avg_volume_ratio REAL,
    breadth_score    REAL,
    signal           TEXT,
    leaders          TEXT,
    UNIQUE(date, theme_key)
);

CREATE TABLE IF NOT EXISTS signal_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    theme_key   TEXT,
    confidence  INTEGER,
    description TEXT,
    metadata    TEXT
);

CREATE TABLE IF NOT EXISTS leaps_candidates (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    date             TEXT NOT NULL,
    ticker           TEXT NOT NULL,
    theme_key        TEXT,
    theme_name       TEXT,
    leaps_score      REAL,
    signal_type      TEXT,
    theme_score      REAL,
    rotation_score   REAL,
    rs_score         REAL,
    trend_score      REAL,
    pullback_score   REAL,
    options_score    REAL,
    risk_score       REAL,
    is_pullback      INTEGER,
    drawdown_pct     REAL,
    pct_above_50dma  REAL,
    has_leaps        INTEGER,
    options_quality  TEXT,
    nearest_expiry   TEXT,
    triggers         TEXT,
    risk_notes       TEXT,
    UNIQUE(date, ticker)
);
"""


class RadarDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)
        logger.info("DB ready: %s", self.db_path)

    def save_snapshot(self, snapshot: RadarSnapshot) -> None:
        today = snapshot.as_of.isoformat()

        with self._conn() as conn:
            for ticker, m in snapshot.ticker_metrics.items():
                conn.execute(
                    """INSERT OR REPLACE INTO daily_snapshots
                       (date, ticker, last_close, ret_1d, ret_5d, ret_1m, ret_3m, ret_ytd,
                        rs_spy_1d, rs_spy_5d, rs_spy_1m, rs_qqq_1m,
                        above_20dma, above_50dma, above_200dma,
                        volume_ratio, drawdown_52w, composite_score)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        today, ticker, m.last_close,
                        m.ret_1d, m.ret_5d, m.ret_1m, m.ret_3m, m.ret_ytd,
                        m.rs_vs_spy_1d, m.rs_vs_spy_5d, m.rs_vs_spy_1m, m.rs_vs_qqq_1m,
                        int(m.above_20dma), int(m.above_50dma), int(m.above_200dma),
                        m.volume_ratio_20d, m.drawdown_from_52w_high, m.composite_score,
                    ),
                )

            for key, b in snapshot.theme_breadths.items():
                conn.execute(
                    """INSERT OR REPLACE INTO theme_scores
                       (date, theme_key, theme_name, total_tickers,
                        breadth_rs, breadth_20dma, avg_rs_spy_1m, avg_rs_spy_1d,
                        avg_volume_ratio, breadth_score, signal, leaders)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        today, key, b.theme_name, b.total_tickers,
                        b.breadth_rs, b.breadth_20dma, b.avg_rs_spy_1m, b.avg_rs_spy_1d,
                        b.avg_volume_ratio, b.breadth_score, b.signal,
                        json.dumps(b.leaders),
                    ),
                )

            rot = snapshot.rotation_signal
            if rot and rot.detected:
                conn.execute(
                    """INSERT INTO signal_events
                       (timestamp, event_type, confidence, description, metadata)
                       VALUES (?,?,?,?,?)""",
                    (
                        datetime.utcnow().isoformat(),
                        "ROTATION",
                        rot.confidence,
                        rot.description,
                        json.dumps({
                            "from_themes": rot.from_themes,
                            "to_themes":   rot.to_themes,
                        }),
                    ),
                )

            # Save LEAPS candidates
            for c in snapshot.leaps_candidates:
                conn.execute(
                    """INSERT OR REPLACE INTO leaps_candidates
                       (date, ticker, theme_key, theme_name, leaps_score, signal_type,
                        theme_score, rotation_score, rs_score, trend_score,
                        pullback_score, options_score, risk_score,
                        is_pullback, drawdown_pct, pct_above_50dma,
                        has_leaps, options_quality, nearest_expiry,
                        triggers, risk_notes)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        today, c.ticker, c.theme_key, c.theme_name,
                        c.leaps_score, c.signal_type,
                        c.theme_score, c.rotation_score, c.rs_score,
                        c.trend_score, c.pullback_score, c.options_score, c.risk_score,
                        int(c.is_pullback_setup), c.drawdown_pct, c.pct_above_50dma,
                        int(c.has_leaps), c.options_quality, c.nearest_leaps_expiry,
                        json.dumps(c.triggers), json.dumps(c.risk_notes),
                    ),
                )

        logger.info("Snapshot saved: %s (%d tickers, %d themes, %d leaps)",
                    today, len(snapshot.ticker_metrics),
                    len(snapshot.theme_breadths), len(snapshot.leaps_candidates))

    def load_theme_scores_before(self, n_days: int = 5) -> dict[str, dict]:
        """Load the most recent theme scores from at least n_days ago."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT theme_key, avg_rs_spy_1m, breadth_rs, breadth_score, signal, leaders
                   FROM theme_scores
                   WHERE date <= date('now', ?)
                   ORDER BY date DESC""",
                (f"-{n_days} days",),
            ).fetchall()

        seen: dict[str, dict] = {}
        for row in rows:
            key = row[0]
            if key not in seen:
                seen[key] = {
                    "theme_key":    key,
                    "avg_rs_spy_1m": row[1],
                    "breadth_rs":   row[2],
                    "breadth_score": row[3],
                    "signal":       row[4],
                    "leaders":      json.loads(row[5] or "[]"),
                }
        return seen

    def export_csv(self, export_dir: str) -> None:
        today = date.today().isoformat()
        path  = Path(export_dir)
        path.mkdir(parents=True, exist_ok=True)

        with self._conn() as conn:
            for table, fname in [
                ("daily_snapshots", f"snapshots_{today}.csv"),
                ("theme_scores",    f"themes_{today}.csv"),
            ]:
                rows = conn.execute(
                    f"SELECT * FROM {table} WHERE date = ?", (today,)
                ).fetchall()
                if not rows:
                    continue
                cur = conn.execute(f"SELECT * FROM {table} LIMIT 0")
                cols = [d[0] for d in cur.description]
                out = path / fname
                with open(out, "w", newline="") as f:
                    w = csv.writer(f)
                    w.writerow(cols)
                    w.writerows(rows)
                logger.info("CSV exported: %s", out)
