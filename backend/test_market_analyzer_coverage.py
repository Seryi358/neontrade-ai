"""
Tests for market_analyzer.py — covering critical calculation methods.
Focus: _detect_trend, _detect_condition, _calculate_emas, _calculate_fibonacci,
       _calculate_rsi, _calculate_macd, _calculate_trade_score,
       _calculate_pivot_points, _analyze_volume, _candles_to_dataframe,
       _detect_session.
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock, patch
from dataclasses import dataclass
from core.market_analyzer import (
    MarketAnalyzer, AnalysisResult, Trend, MarketCondition,
)


@pytest.fixture
def analyzer():
    """Create a MarketAnalyzer with mocked broker."""
    broker = MagicMock()
    return MarketAnalyzer(broker)


def _make_df(closes, n=60, base_open=1.1000):
    """Build an OHLCV DataFrame from a list of close prices.
    Generates synthetic open/high/low around each close.
    """
    if len(closes) < n:
        # Pad with the first close value
        closes = [closes[0]] * (n - len(closes)) + closes
    rows = []
    for i, c in enumerate(closes):
        o = c - 0.0002
        h = max(o, c) + 0.0005
        l = min(o, c) - 0.0005
        rows.append({
            "time": pd.Timestamp(f"2025-01-01") + pd.Timedelta(hours=i),
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": 1000 + i * 10,
        })
    df = pd.DataFrame(rows)
    df.set_index("time", inplace=True)
    return df


def _make_trending_df(direction="up", length=60, start=1.1000, step=0.0010):
    """Build a clearly trending DataFrame."""
    closes = []
    for i in range(length):
        if direction == "up":
            closes.append(start + i * step)
        else:
            closes.append(start - i * step)
    return _make_df(closes, n=length)


# ──────────────────────────────────────────────────────────────────
# _candles_to_dataframe
# ──────────────────────────────────────────────────────────────────

class TestCandlesToDataframe:
    def test_empty_candles_returns_empty_df(self, analyzer):
        result = analyzer._candles_to_dataframe([])
        assert result.empty

    def test_dataclass_candles(self, analyzer):
        """CandleData-like objects should be converted correctly."""
        @dataclass
        class FakeCandle:
            time: str
            open: float
            high: float
            low: float
            close: float
            volume: int
            complete: bool

        candles = [
            FakeCandle("2025-01-01T00:00:00Z", 1.1, 1.12, 1.09, 1.11, 100, True),
            FakeCandle("2025-01-01T01:00:00Z", 1.11, 1.13, 1.10, 1.12, 200, True),
            FakeCandle("2025-01-01T02:00:00Z", 1.12, 1.14, 1.11, 1.13, 150, False),  # incomplete
        ]
        df = analyzer._candles_to_dataframe(candles)
        assert len(df) == 2  # incomplete candle excluded
        assert df["close"].iloc[-1] == 1.12

    def test_legacy_dict_candles(self, analyzer):
        """Legacy OANDA dict format should be converted correctly."""
        candles = [
            {"time": "2025-01-01T00:00:00Z", "mid": {"o": "1.1", "h": "1.12", "l": "1.09", "c": "1.11"}, "volume": "100", "complete": True},
            {"time": "2025-01-01T01:00:00Z", "mid": {"o": "1.11", "h": "1.13", "l": "1.10", "c": "1.12"}, "volume": "200", "complete": True},
        ]
        df = analyzer._candles_to_dataframe(candles)
        assert len(df) == 2
        assert df["close"].iloc[0] == 1.11

    def test_zero_ohlc_filtered(self, analyzer):
        """Candles with all-zero OHLC should be filtered out."""
        @dataclass
        class FakeCandle:
            time: str
            open: float
            high: float
            low: float
            close: float
            volume: int
            complete: bool

        candles = [
            FakeCandle("2025-01-01T00:00:00Z", 0, 0, 0, 0, 0, True),  # zero OHLC
            FakeCandle("2025-01-01T01:00:00Z", 1.1, 1.12, 1.09, 1.11, 100, True),
        ]
        df = analyzer._candles_to_dataframe(candles)
        assert len(df) == 1  # zero candle filtered


# ──────────────────────────────────────────────────────────────────
# _detect_trend
# ──────────────────────────────────────────────────────────────────

class TestDetectTrend:
    def test_empty_df_returns_ranging(self, analyzer):
        assert analyzer._detect_trend(pd.DataFrame()) == Trend.RANGING

    def test_short_df_returns_ranging(self, analyzer):
        df = _make_df([1.1] * 10, n=10)
        assert analyzer._detect_trend(df) == Trend.RANGING

    def test_uptrend_detected(self, analyzer):
        """Uptrend with HH + HL structure should return BULLISH."""
        # Create zigzag uptrend: up 5 bars, down 2 bars, repeat — creates HH/HL
        closes = []
        base = 1.1000
        for cycle in range(10):
            for i in range(5):  # up leg
                closes.append(base + cycle * 0.0050 + i * 0.0015)
            for i in range(3):  # pullback (shallow)
                closes.append(closes[-1] - (i + 1) * 0.0005)
        df = _make_df(closes, n=len(closes))
        result = analyzer._detect_trend(df)
        assert result == Trend.BULLISH

    def test_downtrend_detected(self, analyzer):
        """Downtrend with LH + LL structure should return BEARISH."""
        # Create zigzag downtrend: down 5 bars, up 2 bars, repeat — creates LH/LL
        closes = []
        base = 1.2000
        for cycle in range(10):
            for i in range(5):  # down leg
                closes.append(base - cycle * 0.0050 - i * 0.0015)
            for i in range(3):  # bounce (shallow)
                closes.append(closes[-1] + (i + 1) * 0.0005)
        df = _make_df(closes, n=len(closes))
        result = analyzer._detect_trend(df)
        assert result == Trend.BEARISH

    def test_flat_returns_ranging(self, analyzer):
        """Flat price should return RANGING."""
        df = _make_df([1.1000] * 80, n=80)
        result = analyzer._detect_trend(df)
        assert result == Trend.RANGING


# ──────────────────────────────────────────────────────────────────
# _detect_condition
# ──────────────────────────────────────────────────────────────────

class TestDetectCondition:
    def test_empty_df_returns_neutral(self, analyzer):
        assert analyzer._detect_condition(pd.DataFrame()) == MarketCondition.NEUTRAL

    def test_short_df_returns_neutral(self, analyzer):
        df = _make_df([1.1] * 10, n=10)
        assert analyzer._detect_condition(df) == MarketCondition.NEUTRAL

    def test_strong_uptrend_is_accelerating(self, analyzer):
        """Rapidly expanding candles and distance from EMA should be ACCELERATING."""
        # Small bodies then large bodies — expanding
        closes = [1.1000 + i * 0.0001 for i in range(45)]  # slow start
        closes += [closes[-1] + i * 0.0020 for i in range(1, 16)]  # fast finish
        df = _make_df(closes, n=len(closes))
        result = analyzer._detect_condition(df)
        assert result in (MarketCondition.ACCELERATING, MarketCondition.OVERBOUGHT)

    def test_decelerating_condition(self, analyzer):
        """Shrinking candles approaching EMA should be DECELERATING."""
        # Large bodies then small bodies — contracting
        closes = [1.1000 + i * 0.0020 for i in range(45)]  # fast start
        closes += [closes[-1] + i * 0.0001 for i in range(1, 16)]  # slow finish
        df = _make_df(closes, n=len(closes))
        result = analyzer._detect_condition(df)
        assert result in (MarketCondition.DECELERATING, MarketCondition.NEUTRAL, MarketCondition.OVERBOUGHT)


# ──────────────────────────────────────────────────────────────────
# _calculate_emas
# ──────────────────────────────────────────────────────────────────

class TestCalculateEMAs:
    def test_empty_candles(self, analyzer):
        result = analyzer._calculate_emas({})
        assert result == {}

    def test_daily_emas(self, analyzer):
        """Daily candles should produce EMA_D_20 and EMA_D_50."""
        df = _make_trending_df("up", length=60)
        candles = {"D": df}
        result = analyzer._calculate_emas(candles)
        assert "EMA_D_20" in result
        assert "EMA_D_50" in result
        # EMA_D_20 should be closer to recent price than EMA_D_50
        assert result["EMA_D_20"] > result["EMA_D_50"]

    def test_multiple_timeframes(self, analyzer):
        """Multiple timeframes should produce correct keys."""
        df = _make_trending_df("up", length=60)
        candles = {"H1": df, "M15": df}
        result = analyzer._calculate_emas(candles)
        assert "EMA_H1_20" in result
        assert "EMA_H1_50" in result
        assert "EMA_M15_5" in result
        assert "EMA_M15_20" in result
        assert "EMA_M15_50" in result

    def test_nan_emas_not_stored(self, analyzer):
        """EMA values that are NaN should not be included."""
        # Single row DF — EMA span=50 will still produce a value with ewm (not NaN)
        # but an empty DF should produce nothing
        candles = {"D": pd.DataFrame()}
        result = analyzer._calculate_emas(candles)
        assert "EMA_D_50" not in result


# ──────────────────────────────────────────────────────────────────
# _calculate_fibonacci
# ──────────────────────────────────────────────────────────────────

class TestCalculateFibonacci:
    def test_empty_df_returns_empty(self, analyzer):
        assert analyzer._calculate_fibonacci(pd.DataFrame()) == {}

    def test_short_df_returns_empty(self, analyzer):
        df = _make_df([1.1] * 5, n=5)
        assert analyzer._calculate_fibonacci(df) == {}

    def test_fib_levels_present(self, analyzer):
        """Standard Fibonacci levels should be present."""
        df = _make_trending_df("up", length=80, step=0.0010)
        result = analyzer._calculate_fibonacci(df)
        assert "0.382" in result
        assert "0.5" in result
        assert "0.618" in result
        assert "1.0" in result

    def test_fib_retracement_order(self, analyzer):
        """Retracement levels should be ordered: 0.0 > 0.236 > ... > 1.0."""
        df = _make_trending_df("up", length=80, step=0.0010)
        result = analyzer._calculate_fibonacci(df)
        if "0.0" in result and "1.0" in result:
            assert result["0.0"] > result["0.382"] > result["0.618"] > result["1.0"]

    def test_extensions_present(self, analyzer):
        """Bearish and bullish extensions should be present."""
        df = _make_trending_df("up", length=80, step=0.0010)
        result = analyzer._calculate_fibonacci(df)
        # At minimum, legacy bearish extensions should be present
        assert "ext_0.618" in result or "ext_bear_0.618" in result


# ──────────────────────────────────────────────────────────────────
# _calculate_rsi
# ──────────────────────────────────────────────────────────────────

class TestCalculateRSI:
    def test_empty_df_returns_none(self, analyzer):
        assert analyzer._calculate_rsi(pd.DataFrame()) is None

    def test_short_df_returns_none(self, analyzer):
        df = _make_df([1.1] * 5, n=5)
        assert analyzer._calculate_rsi(df) is None

    def test_strong_uptrend_high_rsi(self, analyzer):
        """Strong uptrend should have RSI > 60."""
        df = _make_trending_df("up", length=60, step=0.0020)
        rsi = analyzer._calculate_rsi(df)
        assert rsi is not None
        assert rsi > 60

    def test_strong_downtrend_low_rsi(self, analyzer):
        """Strong downtrend should have RSI < 40."""
        df = _make_trending_df("down", length=60, step=0.0020)
        rsi = analyzer._calculate_rsi(df)
        assert rsi is not None
        assert rsi < 40

    def test_flat_market_neutral_rsi(self, analyzer):
        """Flat market should have RSI near 50."""
        df = _make_df([1.1000] * 60, n=60)
        rsi = analyzer._calculate_rsi(df)
        assert rsi is not None
        assert 45 <= rsi <= 55


# ──────────────────────────────────────────────────────────────────
# _calculate_macd
# ──────────────────────────────────────────────────────────────────

class TestCalculateMACD:
    def test_empty_df_returns_none(self, analyzer):
        assert analyzer._calculate_macd(pd.DataFrame()) is None

    def test_short_df_returns_none(self, analyzer):
        df = _make_df([1.1] * 10, n=10)
        assert analyzer._calculate_macd(df) is None

    def test_uptrend_bullish_macd(self, analyzer):
        """Strong uptrend should have bullish MACD (line > signal)."""
        df = _make_trending_df("up", length=60, step=0.0020)
        result = analyzer._calculate_macd(df)
        assert result is not None
        assert "macd" in result
        assert "signal" in result
        assert "histogram" in result
        assert "bullish" in result
        assert result["bullish"] is True

    def test_downtrend_bearish_macd(self, analyzer):
        """Strong downtrend should have bearish MACD."""
        df = _make_trending_df("down", length=60, step=0.0020)
        result = analyzer._calculate_macd(df)
        assert result is not None
        assert result["bullish"] is False

    def test_macd_histogram_sign(self, analyzer):
        """Bullish MACD histogram should be positive."""
        df = _make_trending_df("up", length=60, step=0.0020)
        result = analyzer._calculate_macd(df)
        assert result["histogram"] > 0


# ──────────────────────────────────────────────────────────────────
# _calculate_trade_score
# ──────────────────────────────────────────────────────────────────

class TestCalculateTradeScore:
    def test_perfect_convergence_score(self, analyzer):
        """HTF/LTF convergence with trending market should score high."""
        score = analyzer._calculate_trade_score(
            htf_trend=Trend.BULLISH,
            ltf_trend=Trend.BULLISH,
            convergence=True,
            condition=MarketCondition.NEUTRAL,
            patterns=["ENGULFING_BULLISH"],
        )
        assert score >= 50.0  # convergence(30) + htf(15) + ltf(10) + pattern(5) = 60

    def test_divergent_trends_penalty(self, analyzer):
        """Divergent HTF/LTF trends without convergence should get penalty."""
        score = analyzer._calculate_trade_score(
            htf_trend=Trend.BULLISH,
            ltf_trend=Trend.BEARISH,
            convergence=False,
            condition=MarketCondition.NEUTRAL,
            patterns=[],
        )
        # htf(15) + ltf(10) - divergence(10) = 15
        assert score == 15.0

    def test_ranging_both_penalty(self, analyzer):
        """Both ranging should get penalty."""
        score = analyzer._calculate_trade_score(
            htf_trend=Trend.RANGING,
            ltf_trend=Trend.RANGING,
            convergence=False,
            condition=MarketCondition.NEUTRAL,
            patterns=[],
        )
        # ranging both(-10) + no trend bonus = -10 -> clamped to 0
        assert score == 0.0

    def test_oversold_with_reversal_pattern(self, analyzer):
        """Oversold + bullish reversal pattern should get big bonus."""
        score = analyzer._calculate_trade_score(
            htf_trend=Trend.BEARISH,
            ltf_trend=Trend.BEARISH,
            convergence=True,
            condition=MarketCondition.OVERSOLD,
            patterns=["MORNING_STAR"],
        )
        # convergence(30) + htf(15) + ltf(10) + oversold+reversal(20) + pattern(5) = 80
        assert score >= 75.0

    def test_score_clamped_0_100(self, analyzer):
        """Score should be clamped between 0 and 100."""
        score_low = analyzer._calculate_trade_score(
            Trend.RANGING, Trend.RANGING, False, MarketCondition.NEUTRAL, []
        )
        assert 0.0 <= score_low <= 100.0

    def test_pattern_bonus_capped_at_15(self, analyzer):
        """Pattern bonus should cap at 15 (3 patterns * 5)."""
        score_3 = analyzer._calculate_trade_score(
            Trend.RANGING, Trend.RANGING, False, MarketCondition.NEUTRAL,
            ["LOW_TEST", "ENGULFING_BULLISH", "MORNING_STAR"]
        )
        score_5 = analyzer._calculate_trade_score(
            Trend.RANGING, Trend.RANGING, False, MarketCondition.NEUTRAL,
            ["LOW_TEST", "ENGULFING_BULLISH", "MORNING_STAR", "HAMMER", "DOJI"]
        )
        # Both should have same pattern bonus (15 cap)
        assert score_3 == score_5

    def test_chart_pattern_high_confidence_bonus(self, analyzer):
        """Chart pattern with >=70 confidence should add 15 points."""
        base = analyzer._calculate_trade_score(
            Trend.BULLISH, Trend.BULLISH, True, MarketCondition.NEUTRAL, []
        )
        with_pattern = analyzer._calculate_trade_score(
            Trend.BULLISH, Trend.BULLISH, True, MarketCondition.NEUTRAL, [],
            chart_patterns=[{"name": "double_bottom", "confidence": 80}]
        )
        assert with_pattern - base == 15.0


# ──────────────────────────────────────────────────────────────────
# _calculate_pivot_points
# ──────────────────────────────────────────────────────────────────

class TestCalculatePivotPoints:
    def test_empty_df_returns_empty(self, analyzer):
        assert analyzer._calculate_pivot_points(pd.DataFrame()) == {}

    def test_single_candle_returns_empty(self, analyzer):
        """Need at least 2 candles (previous + current)."""
        df = _make_df([1.1], n=1)
        assert analyzer._calculate_pivot_points(df) == {}

    def test_pivot_formula(self, analyzer):
        """P = (H + L + C) / 3, R1 = 2*P - L, S1 = 2*P - H."""
        rows = [
            {"time": pd.Timestamp("2025-01-01"), "open": 1.0, "high": 1.2, "low": 0.9, "close": 1.1, "volume": 100},
            {"time": pd.Timestamp("2025-01-02"), "open": 1.1, "high": 1.3, "low": 1.0, "close": 1.2, "volume": 200},
        ]
        df = pd.DataFrame(rows).set_index("time")
        result = analyzer._calculate_pivot_points(df)

        # Uses iloc[-2] = first candle: H=1.2, L=0.9, C=1.1
        expected_p = (1.2 + 0.9 + 1.1) / 3.0
        expected_r1 = 2 * expected_p - 0.9
        expected_s1 = 2 * expected_p - 1.2

        assert abs(result["P"] - round(expected_p, 5)) < 1e-9
        assert abs(result["R1"] - round(expected_r1, 5)) < 1e-9
        assert abs(result["S1"] - round(expected_s1, 5)) < 1e-9

    def test_r1_above_s1(self, analyzer):
        """R1 should always be above S1."""
        df = _make_trending_df("up", length=10)
        result = analyzer._calculate_pivot_points(df)
        if result:
            assert result["R1"] > result["S1"]


# ──────────────────────────────────────────────────────────────────
# _analyze_volume
# ──────────────────────────────────────────────────────────────────

class TestAnalyzeVolume:
    def test_empty_df_returns_empty(self, analyzer):
        assert analyzer._analyze_volume(pd.DataFrame()) == {}

    def test_short_df_returns_empty(self, analyzer):
        df = _make_df([1.1] * 5, n=5)
        assert analyzer._analyze_volume(df) == {}

    def test_volume_analysis_fields(self, analyzer):
        """Should return all expected fields."""
        df = _make_trending_df("up", length=30)
        result = analyzer._analyze_volume(df)
        assert "avg_volume" in result
        assert "current_volume" in result
        assert "volume_ratio" in result
        assert "above_average" in result

    def test_above_average_detection(self, analyzer):
        """Last candle with high volume should be detected as above average."""
        df = _make_trending_df("up", length=25)
        # Boost last candle volume
        df.iloc[-1, df.columns.get_loc("volume")] = 99999
        result = analyzer._analyze_volume(df)
        assert result["above_average"] is True
        assert result["volume_ratio"] > 1.0


# ──────────────────────────────────────────────────────────────────
# _detect_session
# ──────────────────────────────────────────────────────────────────

class TestDetectSession:
    def test_returns_tuple(self, analyzer):
        """Session should return (session_name, detail) tuple."""
        result = analyzer._detect_session()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_asian_session(self, analyzer):
        """UTC hour 3 (EDT summer) should be ASIAN."""
        from datetime import datetime, timezone
        mock_dt = datetime(2025, 7, 1, 3, 0, tzinfo=timezone.utc)
        with patch("core.market_analyzer.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            mock_datetime.side_effect = lambda *a, **k: datetime(*a, **k)
            # Also need to patch _dst_offset to return 0 (summer)
            with patch.object(analyzer, '_dst_offset', return_value=0):
                result = analyzer._detect_session()
        assert result[0] == "ASIAN"

    def test_london_session(self, analyzer):
        """UTC hour 9 (EDT summer) should be LONDON."""
        from datetime import datetime, timezone
        mock_dt = datetime(2025, 7, 1, 9, 0, tzinfo=timezone.utc)
        with patch("core.market_analyzer.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            mock_datetime.side_effect = lambda *a, **k: datetime(*a, **k)
            with patch.object(analyzer, '_dst_offset', return_value=0):
                result = analyzer._detect_session()
        assert result[0] == "LONDON"

    def test_overlap_session(self, analyzer):
        """UTC hour 13 (EDT summer) should be OVERLAP."""
        from datetime import datetime, timezone
        mock_dt = datetime(2025, 7, 1, 13, 0, tzinfo=timezone.utc)
        with patch("core.market_analyzer.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            mock_datetime.side_effect = lambda *a, **k: datetime(*a, **k)
            with patch.object(analyzer, '_dst_offset', return_value=0):
                result = analyzer._detect_session()
        assert result[0] == "OVERLAP"

    def test_ny_session(self, analyzer):
        """UTC hour 18 (EDT summer) should be NEW_YORK."""
        from datetime import datetime, timezone
        mock_dt = datetime(2025, 7, 1, 18, 0, tzinfo=timezone.utc)
        with patch("core.market_analyzer.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            mock_datetime.side_effect = lambda *a, **k: datetime(*a, **k)
            with patch.object(analyzer, '_dst_offset', return_value=0):
                result = analyzer._detect_session()
        assert result[0] == "NEW_YORK"


# ──────────────────────────────────────────────────────────────────
# AnalysisResult dataclass
# ──────────────────────────────────────────────────────────────────

class TestAnalysisResult:
    def test_defaults(self):
        """AnalysisResult should have sane defaults."""
        result = AnalysisResult(
            instrument="EUR_USD",
            htf_trend=Trend.BULLISH,
            htf_condition=MarketCondition.NEUTRAL,
            ltf_trend=Trend.BULLISH,
            htf_ltf_convergence=True,
            key_levels={"supports": [], "resistances": []},
            ema_values={},
            fibonacci_levels={},
            candlestick_patterns=[],
        )
        assert result.score == 0.0
        assert result.order_blocks == []
        assert result.rsi_divergence is None
        assert result.current_price is None
        assert result.premium_discount_zone is None
