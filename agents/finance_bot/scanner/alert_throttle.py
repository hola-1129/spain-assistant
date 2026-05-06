"""
Noise control for unusual movers:
  - Per-symbol 60-minute cooldown
  - Max 8 unusual-mover alerts per hour
  - Crash mode: only ETFs + top-5 by score when SPY ≤ -3%
"""
from datetime import datetime, timedelta


class AlertThrottle:
    def __init__(self, store, max_per_hour: int = 8, cooldown_min: int = 60):
        self.store        = store
        self.max_per_hour = max_per_hour
        self.cooldown_min = cooldown_min

    def can_send(self, symbol: str) -> bool:
        cutoff = (datetime.utcnow() - timedelta(minutes=self.cooldown_min)).isoformat()
        with self.store._conn() as conn:
            row = conn.execute(
                """SELECT 1 FROM alert_history
                   WHERE symbol=? AND rule_type LIKE 'unusual_%' AND sent_at>?
                   LIMIT 1""",
                (symbol, cutoff),
            ).fetchone()
        return row is None

    def hourly_count(self) -> int:
        cutoff = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        with self.store._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM alert_history WHERE rule_type LIKE 'unusual_%' AND sent_at>?",
                (cutoff,),
            ).fetchone()
        return row[0] if row else 0

    def is_hourly_limit_reached(self) -> bool:
        return self.hourly_count() >= self.max_per_hour

    def is_market_crash(self, spy_hist) -> bool:
        """True if SPY is down ≥ 3% today."""
        if spy_hist is None or len(spy_hist) < 2:
            return False
        p, prev = spy_hist["Close"].iloc[-1], spy_hist["Close"].iloc[-2]
        return (p - prev) / prev * 100 <= -3.0
