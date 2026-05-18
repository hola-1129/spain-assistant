"""
Rotation detection — RULE tier.
Detects capital flow shifts between themes by comparing RS deltas over N days.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from .breadth import ThemeBreadth

logger = logging.getLogger("radar.rotation")


@dataclass
class RotationSignal:
    detected: bool = False
    from_themes: list[str] = field(default_factory=list)
    to_themes:   list[str] = field(default_factory=list)
    max_swing: float = 0.0          # RS delta between top gainer and top loser
    confidence: int = 0             # 0–100
    description: str = ""
    as_of: date = field(default_factory=date.today)


def detect_rotation(
    current: dict[str, ThemeBreadth],
    historical: dict[str, ThemeBreadth],
    thresholds: dict,
) -> RotationSignal:
    """
    Compare current theme avg_rs_spy_1m vs historical (N days ago).
    Emits a RotationSignal when meaningful divergence is found.
    """
    signal = RotationSignal(as_of=date.today())

    if not historical:
        return signal

    threshold = thresholds.get("rotation_rs_delta_5d", 5.0)
    gaining: list[tuple[str, float]] = []
    losing:  list[tuple[str, float]] = []

    for key, cur in current.items():
        if key == "defensive_excluded":
            continue
        hist = historical.get(key)
        if hist is None:
            continue
        delta = cur.avg_rs_spy_1m - hist.avg_rs_spy_1m
        if delta >= threshold:
            gaining.append((key, delta))
        elif delta <= -threshold:
            losing.append((key, delta))

    if not gaining or not losing:
        return signal

    gaining.sort(key=lambda x: x[1], reverse=True)
    losing.sort(key=lambda x: x[1])

    signal.detected  = True
    signal.to_themes   = [k for k, _ in gaining]
    signal.from_themes = [k for k, _ in losing]
    signal.max_swing   = gaining[0][1] - losing[0][1]

    # Confidence: magnitude + breadth confirmation
    rs_factor      = min(signal.max_swing / 20.0, 1.0)
    gain_breadth   = current[gaining[0][0]].breadth_rs
    lose_breadth   = current[losing[0][0]].breadth_rs
    breadth_factor = max(0.0, gain_breadth - lose_breadth)
    raw_conf = rs_factor * 0.6 + breadth_factor * 0.4
    signal.confidence = int(max(30, min(95, raw_conf * 100)))

    to_names   = [current[k].theme_name for k in signal.to_themes[:2]   if k in current]
    from_names = [current[k].theme_name for k in signal.from_themes[:2] if k in current]
    signal.description = (
        f"Capital rotating FROM {' / '.join(from_names)} "
        f"→ TO {' / '.join(to_names)}"
    )

    logger.info("Rotation: %s (confidence %d)", signal.description, signal.confidence)
    return signal
