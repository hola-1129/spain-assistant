"""
LEAPS Call Candidate Signal — RULE tier.

Scores tickers for potential LEAPS suitability across 7 dimensions:
  theme strength · rotation · relative strength · trend structure ·
  pullback quality · options liquidity · risk control

Output signals:
  LEAPS_CALL_CANDIDATE       — strong setup, manual review recommended
  LEAPS_SETUP_PULLBACK       — same but triggered on controlled pullback
  LEAPS_RESEARCH_ONLY        — no options data, softer signal
  LEAPS_HIGH_RISK_SPECULATIVE — passes gates but speculative name

This system NEVER says "buy this LEAPS call."
It only flags tickers worth manual LEAPS review.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

import yfinance as yf

from .breadth import ThemeBreadth
from .metrics import TickerMetrics

logger = logging.getLogger("radar.leaps")

# Tickers treated as speculative / high-risk regardless of score
_SPECULATIVE_TICKERS = frozenset({
    "OKLO", "RGTI", "LAES", "POET", "LWLG", "AXSM",
    "CLSK", "IREN", "APLD", "NBIS",
})


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class LEAPSCandidate:
    ticker: str
    as_of: date
    theme_key: str
    theme_name: str

    # Sub-scores 0–100
    theme_score:    float = 0.0
    rotation_score: float = 0.0
    rs_score:       float = 0.0
    trend_score:    float = 0.0
    pullback_score: float = 0.0
    options_score:  float = 0.0
    risk_score:     float = 0.0

    leaps_score: float = 0.0    # weighted composite 0–100

    signal_type: str = ""       # see module docstring
    triggers:   list[str] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)

    is_pullback_setup:    bool  = False
    drawdown_pct:         float = 0.0
    pct_above_50dma:      float = 0.0   # positive = extended above, negative = below

    has_leaps:            bool  = False
    nearest_leaps_expiry: str   = ""
    options_quality:      str   = "UNAVAILABLE"  # GOOD / ACCEPTABLE / POOR / UNAVAILABLE


# ── Sub-scorers ───────────────────────────────────────────────────────────────

def _score_theme(b: Optional[ThemeBreadth]) -> tuple[float, list[str]]:
    if not b:
        return 0.0, []
    score    = b.breadth_score  # already 0–100
    triggers: list[str] = []
    if score >= 80:
        triggers.append(f"Theme score strong ({score:.0f}/100)")
    elif score >= 70:
        triggers.append(f"Theme score above threshold ({score:.0f}/100)")
    return score, triggers


def _score_rotation(m: TickerMetrics) -> tuple[float, list[str]]:
    """RS-based rotation: 1M (50%) + 5D (30%) + 1D (20%), each mapped 0–100."""
    def _map(val: float, lo: float, hi: float) -> float:
        return max(0.0, min(100.0, (val - lo) / (hi - lo) * 100))

    rs1m = _map(m.rs_vs_spy_1m, -20.0, 20.0)
    rs5d = _map(m.rs_vs_spy_5d, -10.0, 10.0)
    rs1d = _map(m.rs_vs_spy_1d,  -5.0,  5.0)
    score = rs1m * 0.5 + rs5d * 0.3 + rs1d * 0.2

    triggers: list[str] = []
    if score >= 80:
        triggers.append(f"Rotation score improving strongly ({score:.0f}/100)")
    elif score >= 75:
        triggers.append(f"Rotation score above threshold ({score:.0f}/100)")
    return score, triggers


def _score_rs(m: TickerMetrics) -> tuple[float, list[str]]:
    """Relative strength vs SPY 1M; bonus for outperforming SOXX."""
    def _map(val: float) -> float:
        return max(0.0, min(100.0, (val + 20.0) / 40.0 * 100))

    score    = _map(m.rs_vs_spy_1m)
    triggers: list[str] = []
    if m.rs_vs_spy_1m > 0:
        triggers.append(f"Relative strength vs SPY 1M: {m.rs_vs_spy_1m:+.1f}%")
    if m.rs_vs_soxx_1m > 0:
        score = min(100.0, score + 5)
        triggers.append(f"Relative strength vs SOXX 1M: {m.rs_vs_soxx_1m:+.1f}%")
    return score, triggers


def _score_trend(
    m: TickerMetrics, max_ext_pct: float
) -> tuple[float, float, list[str], list[str]]:
    """
    Returns (score, pct_above_50dma, triggers, risk_notes).
    Penalises stocks extended > max_ext_pct above 50DMA.
    """
    score    = 0.0
    triggers: list[str] = []
    risks:    list[str] = []

    # Extension above 50DMA
    if m.ma50_value > 0:
        pct_above = (m.last_close / m.ma50_value - 1) * 100
    else:
        pct_above = 0.0

    if m.above_50dma:
        if m.ma50_slope > 0:
            score += 50
            triggers.append("Price above rising 50DMA")
        else:
            score += 30
            triggers.append("Price above 50DMA (slope flat)")

        if pct_above > max_ext_pct:
            score = max(0.0, score - 30)
            risks.append(
                f"Extended {pct_above:.0f}% above 50DMA — avoid chasing"
            )
        elif pct_above > max_ext_pct * 0.6:
            score = max(0.0, score - 10)
            risks.append(f"Moderately extended ({pct_above:.0f}% above 50DMA)")
    else:
        risks.append("Price below 50DMA — trend structure weak")

    if m.above_200dma:
        score += 30
        triggers.append("Price above 200DMA (long-term uptrend intact)")
    else:
        risks.append("Price below 200DMA — caution on long-dated calls")

    if m.above_20dma:
        score += 20

    return min(100.0, score), pct_above, triggers, risks


def _score_pullback(m: TickerMetrics) -> tuple[float, bool, list[str]]:
    """
    Score based on drawdown from 52W high.
    Sweet spot for LEAPS: controlled -5% to -25% pullback.
    """
    d        = m.drawdown_from_52w_high  # negative
    triggers: list[str] = []
    is_pb    = False

    if -10 <= d <= -5:
        score = 90.0
        is_pb = True
        triggers.append(f"Ideal pullback from 52W high ({d:.1f}%)")
    elif -20 <= d < -10:
        score = 75.0
        is_pb = True
        triggers.append(f"Controlled pullback from high ({d:.1f}%)")
    elif -30 <= d < -20:
        score = 55.0
        is_pb = True
        triggers.append(f"Deeper pullback — check support ({d:.1f}%)")
    elif d > -5:
        score = 35.0
        triggers.append(f"Near 52W high ({d:.1f}%) — may be extended")
    else:
        score = 15.0  # steep decline — possible breakdown

    # Volume not collapsing improves conviction
    if m.volume_ratio_20d >= 0.8:
        score = min(100.0, score + 10)
    elif m.volume_ratio_20d < 0.5:
        triggers.append("Volume thin — weak conviction on pullback")

    return score, is_pb, triggers


def _check_options(
    ticker: str,
    min_months: int,
    max_months: int,
    max_spread_pct: float,
) -> tuple[bool, str, str]:
    """
    Check LEAPS option availability and liquidity.
    Returns (has_leaps, nearest_expiry, quality).
    quality: GOOD / ACCEPTABLE / POOR / UNAVAILABLE
    """
    try:
        t = yf.Ticker(ticker)
        expirations = t.options
        if not expirations:
            return False, "", "UNAVAILABLE"

        now      = datetime.utcnow().date()
        min_date = now + timedelta(days=min_months * 30)
        max_date = now + timedelta(days=max_months * 30)

        leaps_dates = [
            d for d in expirations
            if min_date <= datetime.strptime(d, "%Y-%m-%d").date() <= max_date
        ]
        if not leaps_dates:
            return False, "", "POOR"

        nearest = leaps_dates[0]
        calls   = t.option_chain(nearest).calls
        if calls.empty:
            return True, nearest, "POOR"

        # ATM calls only (±15% of current price)
        price = getattr(t.fast_info, "last_price", None)
        if price and price > 0:
            atm = calls[
                (calls["strike"] >= price * 0.85)
                & (calls["strike"] <= price * 1.15)
            ]
            if atm.empty:
                atm = calls
        else:
            atm = calls

        oi    = atm["openInterest"].sum()
        bid   = atm["bid"].mean()
        ask   = atm["ask"].mean()
        mid   = (bid + ask) / 2
        spread_pct = ((ask - bid) / mid * 100) if mid > 0 else 999.0

        if spread_pct <= 5 and oi >= 100:
            quality = "GOOD"
        elif spread_pct <= max_spread_pct and oi >= 50:
            quality = "ACCEPTABLE"
        else:
            quality = "POOR"

        return True, nearest, quality

    except Exception as exc:
        logger.debug("%s: options check error — %s", ticker, exc)
        return False, "", "UNAVAILABLE"


def _score_risk(ticker: str) -> tuple[float, list[str]]:
    if ticker in _SPECULATIVE_TICKERS:
        return 20.0, ["Speculative / binary-risk name — treat as research only"]
    return 85.0, []


# ── Main scoring ──────────────────────────────────────────────────────────────

def score_leaps_candidate(
    ticker: str,
    m: TickerMetrics,
    theme_key: str,
    theme_breadth: Optional[ThemeBreadth],
    cfg: dict,
) -> Optional[LEAPSCandidate]:
    """
    Compute LEAPS score for one ticker.
    Returns None if score is below minimum or fails gates.
    """
    leaps_cfg    = cfg.get("leaps_signal", {})
    min_score    = leaps_cfg.get("min_leaps_score", 75)
    min_theme    = leaps_cfg.get("min_theme_score", 70)
    min_rotation = leaps_cfg.get("min_rotation_score", 75)
    max_ext      = leaps_cfg.get("max_distance_above_50dma_pct", 30.0)
    max_spread   = leaps_cfg.get("max_option_bid_ask_spread_pct", 15.0)
    exp_min      = leaps_cfg.get("preferred_expiration_months_min", 9)
    exp_max      = leaps_cfg.get("preferred_expiration_months_max", 24)
    allow_ro     = leaps_cfg.get("allow_research_only_without_options_data", True)

    # Sub-scores
    th_score, th_trig          = _score_theme(theme_breadth)
    rt_score, rt_trig          = _score_rotation(m)
    rs_score, rs_trig          = _score_rs(m)
    tr_score, pct_50, tr_trig, tr_risks = _score_trend(m, max_ext)
    pb_score, is_pb, pb_trig   = _score_pullback(m)
    rk_score, rk_notes         = _score_risk(ticker)

    # Hard gates — must clear before options check (saves HTTP calls)
    if th_score < min_theme:
        return None
    if rt_score < min_rotation:
        return None

    # Options liquidity
    has_leaps, expiry, opt_quality = _check_options(
        ticker, exp_min, exp_max, max_spread
    )
    if opt_quality in ("GOOD", "ACCEPTABLE"):
        opt_score = 90.0
    elif opt_quality == "POOR":
        opt_score = 40.0
    else:
        opt_score = 20.0  # UNAVAILABLE

    # Composite — weights: theme 25, rotation 20, rs 15, trend 15, pullback 10, options 10, risk 5
    leaps_score = (
        th_score * 0.25
        + rt_score * 0.20
        + rs_score * 0.15
        + tr_score * 0.15
        + pb_score * 0.10
        + opt_score * 0.10
        + rk_score * 0.05
    )

    if leaps_score < min_score:
        return None

    c = LEAPSCandidate(
        ticker=ticker,
        as_of=date.today(),
        theme_key=theme_key,
        theme_name=theme_breadth.theme_name if theme_breadth else theme_key,
        theme_score=round(th_score, 1),
        rotation_score=round(rt_score, 1),
        rs_score=round(rs_score, 1),
        trend_score=round(tr_score, 1),
        pullback_score=round(pb_score, 1),
        options_score=round(opt_score, 1),
        risk_score=round(rk_score, 1),
        leaps_score=round(leaps_score, 1),
        is_pullback_setup=is_pb,
        drawdown_pct=m.drawdown_from_52w_high,
        pct_above_50dma=pct_50,
        has_leaps=has_leaps,
        nearest_leaps_expiry=expiry,
        options_quality=opt_quality,
        triggers=th_trig + rt_trig + rs_trig + tr_trig + pb_trig,
        risk_notes=tr_risks + rk_notes,
    )

    # Classify
    if ticker in _SPECULATIVE_TICKERS:
        c.signal_type = "LEAPS_HIGH_RISK_SPECULATIVE"
    elif not has_leaps and allow_ro:
        c.signal_type = "LEAPS_RESEARCH_ONLY"
    elif is_pb:
        c.signal_type = "LEAPS_SETUP_PULLBACK"
    else:
        c.signal_type = "LEAPS_CALL_CANDIDATE"

    logger.debug(
        "%s: LEAPS score %.1f (%s)", ticker, leaps_score, c.signal_type
    )
    return c


# ── Batch scan ────────────────────────────────────────────────────────────────

def scan_leaps_candidates(
    ticker_metrics: dict[str, TickerMetrics],
    theme_breadths: dict[str, ThemeBreadth],
    ticker_to_theme: dict[str, str],
    cfg: dict,
) -> list[LEAPSCandidate]:
    """
    Scan all watchlist tickers and return LEAPS candidates sorted by score desc.
    Only tickers that pass theme + rotation gates reach the options check.
    """
    if not cfg.get("leaps_signal", {}).get("enabled", True):
        return []

    candidates: list[LEAPSCandidate] = []
    for ticker, m in ticker_metrics.items():
        theme_key    = ticker_to_theme.get(ticker, "")
        theme_breadth = theme_breadths.get(theme_key)
        try:
            c = score_leaps_candidate(ticker, m, theme_key, theme_breadth, cfg)
            if c is not None:
                candidates.append(c)
        except Exception as exc:
            logger.warning("%s: LEAPS scan error — %s", ticker, exc)

    candidates.sort(key=lambda x: x.leaps_score, reverse=True)
    logger.info("LEAPS scan: %d candidates found", len(candidates))
    return candidates
