"""
Basic unit tests for signal computation (RULE tier).
Run: .venv/bin/python -m pytest tests/ -v
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.metrics import TickerMetrics, _ret_n, _ma, compute_ticker_metrics
from core.breadth import ThemeBreadth, compute_theme_breadth
from core.rotation import RotationSignal, detect_rotation


def _make_df(prices: list[float], volumes: list[float] | None = None) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="B")
    data = {"Close": prices, "Open": prices, "High": prices, "Low": prices}
    if volumes:
        data["Volume"] = volumes
    else:
        data["Volume"] = [1_000_000] * len(prices)
    return pd.DataFrame(data, index=idx)


class TestReturnComputation:
    def test_1d_return(self):
        df = _make_df([100, 110])
        assert abs(_ret_n(df, 1) - 10.0) < 0.01

    def test_not_enough_data(self):
        df = _make_df([100])
        assert _ret_n(df, 5) == 0.0

    def test_negative_return(self):
        df = _make_df([100, 90])
        assert abs(_ret_n(df, 1) - (-10.0)) < 0.01


class TestMAComputation:
    def test_ma_basic(self):
        prices = [10.0] * 20 + [20.0]
        df = _make_df(prices)
        # MA20 should be close to 10 (last 20 of 21 entries includes one 20)
        ma = _ma(df, 20)
        assert 10.0 <= ma <= 20.0

    def test_insufficient_data(self):
        df = _make_df([100.0] * 5)
        # Should return mean of available data, not crash
        val = _ma(df, 20)
        assert val == 100.0


class TestTickerMetrics:
    def setup_method(self):
        # 230 days of data for full metrics
        self.prices = [100.0 + i * 0.1 for i in range(230)]
        self.df = _make_df(self.prices, [500_000] * 230)
        self.bench = {"SPY": _make_df([300.0 + i * 0.05 for i in range(230)])}

    def test_returns_computed(self):
        m = compute_ticker_metrics("TEST", self.df, self.bench)
        assert m.ticker == "TEST"
        assert m.ret_1d != 0.0
        assert m.ret_1m != 0.0

    def test_above_dma(self):
        # Uptrend → should be above all MAs
        m = compute_ticker_metrics("TEST", self.df, self.bench)
        assert m.above_20dma
        assert m.above_50dma
        assert m.above_200dma

    def test_volume_ratio(self):
        # Uniform volume → ratio should be close to 1.0
        m = compute_ticker_metrics("TEST", self.df, self.bench)
        assert 0.9 < m.volume_ratio_20d < 1.1


class TestThemeBreadth:
    def _make_metrics(self, rs_values: list[float]) -> dict[str, TickerMetrics]:
        out = {}
        for i, rs in enumerate(rs_values):
            m = TickerMetrics(ticker=f"T{i}", as_of=None)
            m.rs_vs_spy_1m = rs
            m.above_20dma  = rs > 0
            m.volume_ratio_20d = 1.2
            out[f"T{i}"] = m
        return out

    def test_all_positive_rs_is_strong(self):
        metrics = self._make_metrics([5, 6, 7, 8])
        b = compute_theme_breadth(
            "test", "Test Theme", ["T0", "T1", "T2", "T3"],
            metrics, {"breadth_expansion_min": 0.6, "breadth_narrow_max": 0.3,
                      "rs_strong_threshold": 3.0, "rs_weak_threshold": -3.0}
        )
        assert b.breadth_rs == 1.0
        assert b.signal == "STRONG"

    def test_all_negative_rs_is_weak(self):
        metrics = self._make_metrics([-5, -6, -7, -8])
        b = compute_theme_breadth(
            "test", "Test Theme", ["T0", "T1", "T2", "T3"],
            metrics, {"breadth_expansion_min": 0.6, "breadth_narrow_max": 0.3,
                      "rs_strong_threshold": 3.0, "rs_weak_threshold": -3.0}
        )
        assert b.breadth_rs == 0.0
        assert b.signal == "WEAK"

    def test_leaders_identified(self):
        metrics = self._make_metrics([1, 5, 3, 10])
        b = compute_theme_breadth(
            "test", "Test Theme", ["T0", "T1", "T2", "T3"],
            metrics, {}
        )
        assert b.leaders[0] == "T3"


class TestRotationDetection:
    def _make_breadth(self, key: str, name: str, rs: float, breadth: float) -> ThemeBreadth:
        b = ThemeBreadth(theme_key=key, theme_name=name, as_of=None)
        b.avg_rs_spy_1m = rs
        b.breadth_rs    = breadth
        b.total_tickers = 4
        return b

    def test_rotation_detected(self):
        current = {
            "theme_a": self._make_breadth("theme_a", "Theme A", rs=8.0,  breadth=0.8),
            "theme_b": self._make_breadth("theme_b", "Theme B", rs=-8.0, breadth=0.2),
        }
        historical = {
            "theme_a": self._make_breadth("theme_a", "Theme A", rs=0.0, breadth=0.5),
            "theme_b": self._make_breadth("theme_b", "Theme B", rs=0.0, breadth=0.5),
        }
        signal = detect_rotation(current, historical, {"rotation_rs_delta_5d": 5.0})
        assert signal.detected
        assert "theme_a" in signal.to_themes
        assert "theme_b" in signal.from_themes
        assert signal.confidence > 0

    def test_no_rotation_when_below_threshold(self):
        current = {
            "theme_a": self._make_breadth("theme_a", "A", rs=3.0, breadth=0.6),
            "theme_b": self._make_breadth("theme_b", "B", rs=-3.0, breadth=0.4),
        }
        historical = {
            "theme_a": self._make_breadth("theme_a", "A", rs=0.0, breadth=0.5),
            "theme_b": self._make_breadth("theme_b", "B", rs=0.0, breadth=0.5),
        }
        signal = detect_rotation(current, historical, {"rotation_rs_delta_5d": 5.0})
        assert not signal.detected

    def test_no_rotation_without_history(self):
        current = {"theme_a": self._make_breadth("theme_a", "A", rs=10.0, breadth=0.9)}
        signal = detect_rotation(current, {}, {"rotation_rs_delta_5d": 5.0})
        assert not signal.detected
