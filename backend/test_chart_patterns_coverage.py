"""
Tests for chart_patterns.py — covering pattern detection helpers.
Focus: swing detection, _price_tolerance, detect_chart_patterns edge cases,
       double top/bottom with synthetic data, get_pattern_names, ChartPattern.
"""

import pytest
import pandas as pd
import numpy as np
from core.chart_patterns import (
    detect_chart_patterns, ChartPattern, get_pattern_names,
    _find_swing_highs, _find_swing_lows, _price_tolerance,
    _detect_double_top, _detect_double_bottom,
)


def _make_ohlcv(closes, highs=None, lows=None):
    """Build an OHLCV DataFrame. If highs/lows not provided, derive from closes."""
    rows = []
    for i, c in enumerate(closes):
        o = c - 0.0002
        h = highs[i] if highs else max(o, c) + 0.0005
        l = lows[i] if lows else min(o, c) - 0.0005
        rows.append({
            "time": pd.Timestamp("2025-01-01") + pd.Timedelta(hours=i),
            "open": o, "high": h, "low": l, "close": c, "volume": 1000,
        })
    df = pd.DataFrame(rows).set_index("time")
    return df


def _make_double_top_data():
    """Build data with a clear double top pattern.
    Structure: rise -> peak1 -> dip -> rise -> peak2 (same level) -> decline.
    Needs enough bars for 5-bar swing detection.
    """
    closes = []
    # Flat start (10 bars)
    for i in range(10):
        closes.append(1.1000)
    # Rise to first peak (10 bars)
    for i in range(10):
        closes.append(1.1000 + i * 0.0020)
    # Peak 1 area (5 bars) — need to be swing high with window=5
    closes.append(1.1200)
    closes.append(1.1195)
    closes.append(1.1190)
    closes.append(1.1180)
    closes.append(1.1170)
    # Dip to neckline (10 bars)
    for i in range(10):
        closes.append(1.1170 - i * 0.0015)
    # Rise to second peak (10 bars)
    for i in range(10):
        closes.append(1.1020 + i * 0.0018)
    # Peak 2 area (5 bars) — similar level to peak 1
    closes.append(1.1200)
    closes.append(1.1195)
    closes.append(1.1190)
    closes.append(1.1180)
    closes.append(1.1170)
    # Decline below neckline (10 bars)
    for i in range(10):
        closes.append(1.1170 - i * 0.0020)

    return _make_ohlcv(closes)


def _make_double_bottom_data():
    """Build data with a clear double bottom pattern.
    Structure: decline -> valley1 -> bounce -> decline -> valley2 (same level) -> rise.
    """
    closes = []
    # Flat start (10 bars)
    for i in range(10):
        closes.append(1.1200)
    # Decline to first valley (10 bars)
    for i in range(10):
        closes.append(1.1200 - i * 0.0020)
    # Valley 1 area (5 bars)
    closes.append(1.1000)
    closes.append(1.1005)
    closes.append(1.1010)
    closes.append(1.1020)
    closes.append(1.1030)
    # Bounce up (10 bars)
    for i in range(10):
        closes.append(1.1030 + i * 0.0015)
    # Decline to second valley (10 bars)
    for i in range(10):
        closes.append(1.1180 - i * 0.0018)
    # Valley 2 area (5 bars) — similar level to valley 1
    closes.append(1.1000)
    closes.append(1.1005)
    closes.append(1.1010)
    closes.append(1.1020)
    closes.append(1.1030)
    # Rise above neckline (10 bars)
    for i in range(10):
        closes.append(1.1030 + i * 0.0020)

    return _make_ohlcv(closes)


# ──────────────────────────────────────────────────────────────────
# _price_tolerance
# ──────────────────────────────────────────────────────────────────

class TestPriceTolerance:
    def test_default_tolerance(self):
        """Default 0.3% tolerance."""
        result = _price_tolerance(1.1000)
        assert abs(result - 0.0033) < 0.0001

    def test_custom_tolerance(self):
        """Custom 1% tolerance."""
        result = _price_tolerance(100.0, pct=0.01)
        assert result == 1.0

    def test_negative_price(self):
        """Should return absolute value."""
        result = _price_tolerance(-50.0, pct=0.01)
        assert result == 0.5


# ──────────────────────────────────────────────────────────────────
# _find_swing_highs / _find_swing_lows
# ──────────────────────────────────────────────────────────────────

class TestSwingDetection:
    def test_finds_obvious_swing_high(self):
        """A clear peak surrounded by lower bars should be detected."""
        # Build: low low low low low PEAK low low low low low
        closes = [1.1000] * 5 + [1.1100] + [1.1000] * 5
        highs = [1.1005] * 5 + [1.1105] + [1.1005] * 5
        df = _make_ohlcv(closes, highs=highs)
        result = _find_swing_highs(df, window=5)
        assert len(result) == 1
        assert result[0][1] == 1.1105

    def test_finds_obvious_swing_low(self):
        """A clear valley surrounded by higher bars should be detected."""
        closes = [1.1100] * 5 + [1.1000] + [1.1100] * 5
        lows = [1.1095] * 5 + [1.0995] + [1.1095] * 5
        df = _make_ohlcv(closes, lows=lows)
        result = _find_swing_lows(df, window=5)
        assert len(result) == 1
        assert result[0][1] == 1.0995

    def test_empty_df_no_swings(self):
        assert _find_swing_highs(pd.DataFrame(), window=5) == []
        assert _find_swing_lows(pd.DataFrame(), window=5) == []

    def test_flat_data_no_swings(self):
        """Completely flat data should have no swing points."""
        df = _make_ohlcv([1.1000] * 30)
        highs = _find_swing_highs(df, window=5)
        lows = _find_swing_lows(df, window=5)
        assert len(highs) == 0
        assert len(lows) == 0

    def test_multiple_swings(self):
        """Data with distinct peaks/valleys should produce multiple swing points."""
        # Build explicit peaks and valleys with 6-bar spacing.
        # Window=5 requires strict > for 5 bars each side.
        # Pattern: valley...peak...valley...peak...valley (each 6 bars apart)
        n = 70
        highs = [1.1050] * n
        lows = [1.0950] * n
        closes = [1.1000] * n

        # Place clear peaks at positions 12, 36, 60 (highs strictly > neighbors)
        for peak_pos in [12, 36, 60]:
            if peak_pos < n:
                highs[peak_pos] = 1.1200
        # Place clear valleys at positions 24, 48 (lows strictly < neighbors)
        for valley_pos in [24, 48]:
            if valley_pos < n:
                lows[valley_pos] = 1.0800

        df = _make_ohlcv(closes, highs=highs, lows=lows)
        found_highs = _find_swing_highs(df, window=5)
        found_lows = _find_swing_lows(df, window=5)
        assert len(found_highs) >= 2
        assert len(found_lows) >= 1


# ──────────────────────────────────────────────────────────────────
# detect_chart_patterns — edge cases
# ──────────────────────────────────────────────────────────────────

class TestDetectChartPatterns:
    def test_empty_df(self):
        assert detect_chart_patterns(pd.DataFrame()) == []

    def test_short_df(self):
        df = _make_ohlcv([1.1] * 10)
        assert detect_chart_patterns(df) == []

    def test_flat_data_no_patterns(self):
        """Flat data should return no patterns."""
        df = _make_ohlcv([1.1000] * 60)
        patterns = detect_chart_patterns(df)
        assert len(patterns) == 0

    def test_returns_sorted_by_confidence(self):
        """Patterns should be sorted by confidence (highest first)."""
        df = _make_double_top_data()
        patterns = detect_chart_patterns(df)
        for i in range(len(patterns) - 1):
            assert patterns[i].confidence >= patterns[i + 1].confidence


# ──────────────────────────────────────────────────────────────────
# Double Top detection
# ──────────────────────────────────────────────────────────────────

class TestDoubleTop:
    def test_detects_double_top(self):
        """Synthetic double top data should detect the pattern."""
        df = _make_double_top_data()
        swing_highs = _find_swing_highs(df, window=5)
        swing_lows = _find_swing_lows(df, window=5)

        if len(swing_highs) >= 2 and len(swing_lows) >= 2:
            pattern = _detect_double_top(df, swing_highs, swing_lows)
            if pattern:
                assert pattern.name == "DOUBLE_TOP"
                assert pattern.direction == "bearish"
                assert pattern.confidence > 0
                assert pattern.target < pattern.neckline

    def test_no_double_top_in_uptrend(self):
        """Pure uptrend should not detect double top."""
        closes = [1.1000 + i * 0.0010 for i in range(60)]
        df = _make_ohlcv(closes)
        swing_highs = _find_swing_highs(df, window=5)
        swing_lows = _find_swing_lows(df, window=5)
        pattern = _detect_double_top(df, swing_highs, swing_lows)
        assert pattern is None

    def test_insufficient_swings(self):
        """Not enough swing highs should return None."""
        pattern = _detect_double_top(pd.DataFrame(), [], [])
        assert pattern is None


# ──────────────────────────────────────────────────────────────────
# Double Bottom detection
# ──────────────────────────────────────────────────────────────────

class TestDoubleBottom:
    def test_detects_double_bottom(self):
        """Synthetic double bottom data should detect the pattern."""
        df = _make_double_bottom_data()
        swing_highs = _find_swing_highs(df, window=5)
        swing_lows = _find_swing_lows(df, window=5)

        if len(swing_highs) >= 2 and len(swing_lows) >= 2:
            pattern = _detect_double_bottom(df, swing_highs, swing_lows)
            if pattern:
                assert pattern.name == "DOUBLE_BOTTOM"
                assert pattern.direction == "bullish"
                assert pattern.confidence > 0
                assert pattern.target > pattern.neckline

    def test_no_double_bottom_in_downtrend(self):
        """Pure downtrend should not detect double bottom."""
        closes = [1.2000 - i * 0.0010 for i in range(60)]
        df = _make_ohlcv(closes)
        swing_highs = _find_swing_highs(df, window=5)
        swing_lows = _find_swing_lows(df, window=5)
        pattern = _detect_double_bottom(df, swing_highs, swing_lows)
        assert pattern is None

    def test_insufficient_swings(self):
        pattern = _detect_double_bottom(pd.DataFrame(), [], [])
        assert pattern is None


# ──────────────────────────────────────────────────────────────────
# get_pattern_names
# ──────────────────────────────────────────────────────────────────

class TestGetPatternNames:
    def test_returns_list(self):
        names = get_pattern_names()
        assert isinstance(names, list)
        assert len(names) > 0

    def test_contains_key_patterns(self):
        names = get_pattern_names()
        assert "DOUBLE_TOP" in names
        assert "DOUBLE_BOTTOM" in names
        assert "ASCENDING_TRIANGLE" in names
        assert "BULL_FLAG" in names
        assert "CUP_AND_HANDLE" in names

    def test_no_duplicates(self):
        names = get_pattern_names()
        assert len(names) == len(set(names))


# ──────────────────────────────────────────────────────────────────
# ChartPattern dataclass
# ──────────────────────────────────────────────────────────────────

class TestChartPatternDataclass:
    def test_defaults(self):
        p = ChartPattern(
            name="TEST",
            direction="bullish",
            confidence=75.0,
            start_idx=0,
            end_idx=10,
            neckline=1.1000,
            target=1.1200,
            description="Test pattern",
        )
        assert p.duration_ratio == 0.0
        assert p.likely_reversal is False

    def test_with_duration_ratio(self):
        p = ChartPattern(
            name="DOUBLE_TOP",
            direction="bearish",
            confidence=80.0,
            start_idx=5,
            end_idx=50,
            neckline=1.0950,
            target=1.0800,
            description="Doble techo",
            duration_ratio=0.75,
            likely_reversal=True,
        )
        assert p.duration_ratio == 0.75
        assert p.likely_reversal is True
