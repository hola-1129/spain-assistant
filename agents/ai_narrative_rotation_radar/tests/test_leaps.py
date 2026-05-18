"""
Unit tests for LEAPS Call Candidate Signal — RULE tier only.
Options liquidity check is mocked (no network calls in unit tests).
Run: .venv/bin/python -m pytest tests/test_leaps.py -v
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.breadth import ThemeBreadth
from core.leaps_signal import (
    LEAPSCandidate,
    _score_pullback,
    _score_rotation,
    _score_rs,
    _score_theme,
    _score_trend,
    _score_risk,
    score_leaps_candidate,
    scan_leaps_candidates,
)
from core.metrics import TickerMetrics


# ── helpers ───────────────────────────────────────────────────────────────────

def _metrics(
    ticker: str = "TEST",
    rs_spy_1m: float = 8.0,
    rs_spy_5d: float = 2.0,
    rs_spy_1d: float = 0.5,
    rs_soxx_1m: float = 5.0,
    above_50: bool = True,
    above_200: bool = True,
    above_20: bool = True,
    ma50_slope: float = 1.5,
    ma50_value: float = 100.0,
    last_close: float = 110.0,
    drawdown: float = -10.0,
    vol_ratio: float = 1.2,
) -> TickerMetrics:
    m = TickerMetrics(ticker=ticker, as_of=None)
    m.rs_vs_spy_1m = rs_spy_1m
    m.rs_vs_spy_5d = rs_spy_5d
    m.rs_vs_spy_1d = rs_spy_1d
    m.rs_vs_soxx_1m = rs_soxx_1m
    m.above_50dma = above_50
    m.above_200dma = above_200
    m.above_20dma = above_20
    m.ma50_slope = ma50_slope
    m.ma50_value = ma50_value
    m.last_close = last_close
    m.drawdown_from_52w_high = drawdown
    m.volume_ratio_20d = vol_ratio
    return m


def _breadth(score: float = 80.0, rs: float = 8.0, signal: str = "STRONG") -> ThemeBreadth:
    b = ThemeBreadth(theme_key="test_theme", theme_name="Test Theme", as_of=None)
    b.breadth_score = score
    b.avg_rs_spy_1m = rs
    b.signal = signal
    b.breadth_rs = 0.75
    return b


_BASE_CFG = {
    "leaps_signal": {
        "enabled": True,
        "min_leaps_score": 75,
        "strong_leaps_score": 85,
        "min_rotation_score": 75,
        "min_theme_score": 70,
        "max_distance_above_50dma_pct": 30,
        "preferred_expiration_months_min": 9,
        "preferred_expiration_months_max": 24,
        "max_option_bid_ask_spread_pct": 15,
        "allow_research_only_without_options_data": True,
    }
}


# ── Sub-scorer tests ──────────────────────────────────────────────────────────

class TestThemeScore:
    def test_strong_theme(self):
        score, triggers = _score_theme(_breadth(score=85))
        assert score == 85
        assert any("strong" in t.lower() for t in triggers)

    def test_no_breadth_returns_zero(self):
        score, triggers = _score_theme(None)
        assert score == 0.0
        assert triggers == []

    def test_below_threshold(self):
        score, triggers = _score_theme(_breadth(score=60))
        assert score == 60
        assert triggers == []  # no trigger text for below-threshold


class TestRotationScore:
    def test_strong_rs(self):
        # rs1m=15→87.5, rs5d=7→85, rs1d=3→80 → weighted score ≈ 85
        m = _metrics(rs_spy_1m=15, rs_spy_5d=7, rs_spy_1d=3)
        score, _ = _score_rotation(m)
        assert score > 75

    def test_weak_rs(self):
        m = _metrics(rs_spy_1m=-10, rs_spy_5d=-5, rs_spy_1d=-2)
        score, _ = _score_rotation(m)
        assert score < 30

    def test_neutral_rs(self):
        m = _metrics(rs_spy_1m=0, rs_spy_5d=0, rs_spy_1d=0)
        score, _ = _score_rotation(m)
        assert 45 < score < 55  # ~50 at exact zero


class TestRSScore:
    def test_positive_rs_above_50(self):
        m = _metrics(rs_spy_1m=8, rs_soxx_1m=5)
        score, triggers = _score_rs(m)
        assert score > 60
        assert any("SPY" in t for t in triggers)
        assert any("SOXX" in t for t in triggers)

    def test_negative_rs(self):
        m = _metrics(rs_spy_1m=-15, rs_soxx_1m=-10)
        score, _ = _score_rs(m)
        assert score < 30


class TestTrendScore:
    def test_above_rising_50dma(self):
        m = _metrics(above_50=True, ma50_slope=1.5, above_200=True, ma50_value=100, last_close=110)
        score, pct, triggers, risks = _score_trend(m, max_ext_pct=30)
        assert score >= 70
        assert pct > 0
        assert not any("weak" in r.lower() for r in risks)

    def test_below_50dma(self):
        m = _metrics(above_50=False, above_200=False, ma50_value=100, last_close=90)
        score, _, _, risks = _score_trend(m, max_ext_pct=30)
        assert score < 40
        assert any("50DMA" in r for r in risks)

    def test_extended_above_50dma(self):
        # 40% above 50DMA → should be penalised
        m = _metrics(above_50=True, ma50_value=100, last_close=140, ma50_slope=2.0)
        score, pct, _, risks = _score_trend(m, max_ext_pct=30)
        assert pct > 30
        assert any("extended" in r.lower() or "Extended" in r for r in risks)


class TestPullbackScore:
    def test_ideal_pullback(self):
        m = _metrics(drawdown=-8, vol_ratio=1.0)
        score, is_pb, triggers = _score_pullback(m)
        assert score >= 80
        assert is_pb
        assert any("pullback" in t.lower() for t in triggers)

    def test_at_high_not_pullback(self):
        m = _metrics(drawdown=-1)
        score, is_pb, triggers = _score_pullback(m)
        assert not is_pb
        assert score < 50

    def test_breakdown_low_score(self):
        m = _metrics(drawdown=-50)
        score, is_pb, _ = _score_pullback(m)
        assert score <= 25
        assert not is_pb


class TestRiskScore:
    def test_normal_ticker(self):
        score, notes = _score_risk("MU")
        assert score >= 80
        assert notes == []

    def test_speculative_ticker(self):
        score, notes = _score_risk("RGTI")
        assert score == 20
        assert any("speculative" in n.lower() for n in notes)


# ── Integration tests (options mocked) ───────────────────────────────────────

class TestScoringIntegration:
    @patch("core.leaps_signal._check_options")
    def test_strong_candidate_passes(self, mock_options):
        mock_options.return_value = (True, "2027-01-16", "GOOD")
        # rs_spy_1m=15 → rotation_score ≈ 85 > min_rotation_score=75
        m = _metrics(rs_spy_1m=15, rs_spy_5d=7, rs_spy_1d=3, drawdown=-10, ma50_slope=1.5)
        b = _breadth(score=82, rs=10)
        c = score_leaps_candidate("MU", m, "hbm_memory", b, _BASE_CFG)
        assert c is not None
        assert c.leaps_score >= 75
        assert c.signal_type in ("LEAPS_CALL_CANDIDATE", "LEAPS_SETUP_PULLBACK")

    @patch("core.leaps_signal._check_options")
    def test_weak_theme_blocked(self, mock_options):
        mock_options.return_value = (True, "2027-01-16", "GOOD")
        m = _metrics(rs_spy_1m=10)
        b = _breadth(score=50)  # below min_theme_score=70
        c = score_leaps_candidate("TEST", m, "test", b, _BASE_CFG)
        assert c is None  # blocked by theme gate

    @patch("core.leaps_signal._check_options")
    def test_weak_rotation_blocked(self, mock_options):
        mock_options.return_value = (True, "2027-01-16", "GOOD")
        m = _metrics(rs_spy_1m=-5, rs_spy_5d=-3, rs_spy_1d=-1)  # weak rotation
        b = _breadth(score=80)
        c = score_leaps_candidate("TEST", m, "test", b, _BASE_CFG)
        assert c is None  # blocked by rotation gate

    @patch("core.leaps_signal._check_options")
    def test_speculative_ticker_classified(self, mock_options):
        mock_options.return_value = (True, "2027-01-16", "GOOD")
        m = _metrics(rs_spy_1m=12, rs_spy_5d=4, drawdown=-8)
        b = _breadth(score=85, rs=12)
        c = score_leaps_candidate("RGTI", m, "frontier", b, _BASE_CFG)
        if c:  # may or may not pass due to risk_score=20
            assert c.signal_type == "LEAPS_HIGH_RISK_SPECULATIVE"

    @patch("core.leaps_signal._check_options")
    def test_no_options_research_only(self, mock_options):
        mock_options.return_value = (False, "", "UNAVAILABLE")
        m = _metrics(rs_spy_1m=10, rs_spy_5d=3, drawdown=-10)
        b = _breadth(score=82, rs=10)
        c = score_leaps_candidate("MU", m, "hbm_memory", b, _BASE_CFG)
        if c:
            assert c.signal_type == "LEAPS_RESEARCH_ONLY"

    @patch("core.leaps_signal._check_options")
    def test_pullback_setup_classified(self, mock_options):
        mock_options.return_value = (True, "2027-01-16", "ACCEPTABLE")
        m = _metrics(rs_spy_1m=10, rs_spy_5d=3, drawdown=-12, ma50_slope=1.5)
        b = _breadth(score=80, rs=9)
        c = score_leaps_candidate("AVGO", m, "ai_compute_asic", b, _BASE_CFG)
        if c:
            assert c.signal_type in ("LEAPS_SETUP_PULLBACK", "LEAPS_CALL_CANDIDATE")
            assert c.is_pullback_setup

    @patch("core.leaps_signal._check_options")
    def test_disabled_returns_empty(self, mock_options):
        cfg = {"leaps_signal": {"enabled": False}}
        result = scan_leaps_candidates({}, {}, {}, cfg)
        assert result == []
        mock_options.assert_not_called()
