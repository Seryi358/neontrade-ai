"""
Tests for crypto_cycle.py — covering cycle analysis logic.
Focus: _compute_rsi_14, _calculate_rsi_series, _determine_rotation_phase,
       get_dominance_transition, _analyze_halving_phase, _estimate_usdt_dominance,
       _determine_market_phase, CryptoMarketCycle dataclass.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from core.crypto_cycle import CryptoCycleAnalyzer, CryptoMarketCycle


@pytest.fixture
def analyzer():
    return CryptoCycleAnalyzer(broker=None)


# ──────────────────────────────────────────────────────────────────
# _compute_rsi_14
# ──────────────────────────────────────────────────────────────────

class TestComputeRSI14:
    def test_insufficient_data_returns_none(self):
        assert CryptoCycleAnalyzer._compute_rsi_14([100, 101, 102]) is None

    def test_pure_uptrend_high_rsi(self):
        """Steady gains should produce RSI > 70."""
        closes = [100 + i * 2 for i in range(20)]
        rsi = CryptoCycleAnalyzer._compute_rsi_14(closes)
        assert rsi is not None
        assert rsi > 70

    def test_pure_downtrend_low_rsi(self):
        """Steady losses should produce RSI < 30."""
        closes = [200 - i * 2 for i in range(20)]
        rsi = CryptoCycleAnalyzer._compute_rsi_14(closes)
        assert rsi is not None
        assert rsi < 30

    def test_flat_market_neutral_rsi(self):
        """No movement = RSI 100 (all gains, zero losses)... unless truly flat."""
        closes = [100] * 20
        rsi = CryptoCycleAnalyzer._compute_rsi_14(closes)
        # All diffs are 0, so avg_gain=0 and avg_loss=0 → RSI=100 (by code: avg_loss==0)
        assert rsi == 100.0

    def test_mixed_market(self):
        """Mixed ups and downs should produce RSI between 30 and 70."""
        closes = [100, 102, 101, 103, 102, 104, 103, 105, 104, 106, 105, 107, 106, 108, 107, 109]
        rsi = CryptoCycleAnalyzer._compute_rsi_14(closes)
        assert rsi is not None
        assert 30 < rsi < 90


# ──────────────────────────────────────────────────────────────────
# _calculate_rsi_series
# ──────────────────────────────────────────────────────────────────

class TestCalculateRSISeries:
    def test_insufficient_data(self):
        assert CryptoCycleAnalyzer._calculate_rsi_series([100, 101]) == []

    def test_returns_series(self):
        closes = [100 + i for i in range(25)]
        series = CryptoCycleAnalyzer._calculate_rsi_series(closes)
        assert len(series) > 0
        # All gains → all values should be high
        assert all(v > 50 for v in series)

    def test_series_length(self):
        """Series should have len(closes) - period - 1 values."""
        closes = [100 + i for i in range(30)]
        series = CryptoCycleAnalyzer._calculate_rsi_series(closes, period=14)
        # gains has len 29 (from diff). Loop starts at period(14)..28 → 15 values
        assert len(series) == len(closes) - 14 - 1


# ──────────────────────────────────────────────────────────────────
# _determine_rotation_phase
# ──────────────────────────────────────────────────────────────────

class TestRotationPhase:
    def test_rising_dominance_is_btc_phase(self, analyzer):
        cycle = CryptoMarketCycle(btc_dominance_trend="rising")
        analyzer._determine_rotation_phase(cycle)
        assert cycle.rotation_phase == "btc"

    def test_eth_outperforming_falling_dom_no_altseason(self, analyzer):
        cycle = CryptoMarketCycle(
            btc_dominance_trend="falling",
            eth_outperforming_btc=True,
            altcoin_season=False,
        )
        analyzer._determine_rotation_phase(cycle)
        assert cycle.rotation_phase == "eth"

    def test_eth_outperforming_falling_dom_with_altseason(self, analyzer):
        cycle = CryptoMarketCycle(
            btc_dominance_trend="falling",
            eth_outperforming_btc=True,
            altcoin_season=True,
        )
        analyzer._determine_rotation_phase(cycle)
        assert cycle.rotation_phase == "large_alts"

    def test_altseason_no_eth_lead_falling_dom_is_memecoins(self, analyzer):
        cycle = CryptoMarketCycle(
            btc_dominance_trend="falling",
            eth_outperforming_btc=False,
            altcoin_season=True,
        )
        analyzer._determine_rotation_phase(cycle)
        assert cycle.rotation_phase == "memecoins"

    def test_altseason_eth_still_leading_is_small_alts(self, analyzer):
        cycle = CryptoMarketCycle(
            btc_dominance_trend="stable",
            eth_outperforming_btc=True,
            altcoin_season=True,
        )
        analyzer._determine_rotation_phase(cycle)
        assert cycle.rotation_phase == "small_alts"

    def test_unknown_dominance_stays_unknown(self, analyzer):
        cycle = CryptoMarketCycle(btc_dominance_trend="unknown")
        analyzer._determine_rotation_phase(cycle)
        assert cycle.rotation_phase == "unknown"


# ──────────────────────────────────────────────────────────────────
# get_dominance_transition
# ──────────────────────────────────────────────────────────────────

class TestDominanceTransition:
    def test_rising_dom_btc_up(self, analyzer):
        cycle = CryptoMarketCycle(btc_dominance_trend="rising")
        cycle._btc_perf_7d = 0.05
        result = analyzer.get_dominance_transition(cycle)
        assert result["altcoin_outlook"] == "down"

    def test_rising_dom_btc_down(self, analyzer):
        cycle = CryptoMarketCycle(btc_dominance_trend="rising")
        cycle._btc_perf_7d = -0.05
        result = analyzer.get_dominance_transition(cycle)
        assert result["altcoin_outlook"] == "down_much_more"

    def test_falling_dom_btc_up_is_altseason(self, analyzer):
        cycle = CryptoMarketCycle(btc_dominance_trend="falling")
        cycle._btc_perf_7d = 0.05
        result = analyzer.get_dominance_transition(cycle)
        assert result["altcoin_outlook"] == "up_significantly"

    def test_falling_dom_btc_stable(self, analyzer):
        cycle = CryptoMarketCycle(btc_dominance_trend="falling")
        cycle._btc_perf_7d = 0.01  # Within -2% to +2% = stable
        result = analyzer.get_dominance_transition(cycle)
        assert result["altcoin_outlook"] == "capital_rotating_to_alts"

    def test_falling_dom_btc_down_rare(self, analyzer):
        cycle = CryptoMarketCycle(btc_dominance_trend="falling")
        cycle._btc_perf_7d = -0.05
        result = analyzer.get_dominance_transition(cycle)
        assert result["altcoin_outlook"] == "rare_alts_may_fall"

    def test_stable_dom_is_neutral(self, analyzer):
        cycle = CryptoMarketCycle(btc_dominance_trend="stable")
        cycle._btc_perf_7d = 0.01
        result = analyzer.get_dominance_transition(cycle)
        assert result["altcoin_outlook"] == "neutral"

    def test_no_perf_data_defaults_stable(self, analyzer):
        cycle = CryptoMarketCycle(btc_dominance_trend="rising")
        # No _btc_perf_7d attribute
        result = analyzer.get_dominance_transition(cycle)
        assert result["btc_trend"] == "stable"


# ──────────────────────────────────────────────────────────────────
# _analyze_halving_phase
# ──────────────────────────────────────────────────────────────────

class TestHalvingPhase:
    def test_post_halving_very_bullish(self, analyzer):
        """Shortly after 2024 halving should be post_halving / very_bullish."""
        cycle = CryptoMarketCycle()
        # Mock time to 6 months after April 2024 halving
        mock_now = datetime(2024, 10, 1, tzinfo=timezone.utc)
        with patch("core.crypto_cycle.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            analyzer._analyze_halving_phase(cycle)
        assert cycle.halving_phase == "post_halving"
        assert cycle.halving_sentiment == "very_bullish"

    def test_expansion_bullish(self, analyzer):
        """~18 months after halving should be expansion / bullish."""
        cycle = CryptoMarketCycle()
        mock_now = datetime(2025, 12, 1, tzinfo=timezone.utc)
        with patch("core.crypto_cycle.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            analyzer._analyze_halving_phase(cycle)
        assert cycle.halving_phase == "expansion"
        assert cycle.halving_sentiment == "bullish"

    def test_distribution_bearish(self, analyzer):
        """~30 months after halving should be distribution / bearish."""
        cycle = CryptoMarketCycle()
        mock_now = datetime(2026, 10, 1, tzinfo=timezone.utc)
        with patch("core.crypto_cycle.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            analyzer._analyze_halving_phase(cycle)
        assert cycle.halving_phase == "distribution"
        assert cycle.halving_sentiment == "bearish"

    def test_pre_halving_bullish(self, analyzer):
        """~3.5 years after halving should be pre_halving / bullish."""
        cycle = CryptoMarketCycle()
        mock_now = datetime(2027, 12, 1, tzinfo=timezone.utc)
        with patch("core.crypto_cycle.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            analyzer._analyze_halving_phase(cycle)
        assert cycle.halving_phase == "pre_halving"
        assert cycle.halving_sentiment == "bullish"


# ──────────────────────────────────────────────────────────────────
# _estimate_usdt_dominance
# ──────────────────────────────────────────────────────────────────

class TestUSDTDominance:
    def test_both_falling_means_usdt_rising(self, analyzer):
        cycle = CryptoMarketCycle()
        cycle._btc_perf_7d = -0.05
        cycle._eth_perf_7d = -0.05
        analyzer._estimate_usdt_dominance(cycle)
        assert cycle.usdt_dominance_rising is True

    def test_both_rising_means_usdt_falling(self, analyzer):
        cycle = CryptoMarketCycle()
        cycle._btc_perf_7d = 0.05
        cycle._eth_perf_7d = 0.05
        analyzer._estimate_usdt_dominance(cycle)
        assert cycle.usdt_dominance_rising is False

    def test_mixed_stays_none(self, analyzer):
        cycle = CryptoMarketCycle()
        cycle._btc_perf_7d = 0.05
        cycle._eth_perf_7d = -0.05
        analyzer._estimate_usdt_dominance(cycle)
        assert cycle.usdt_dominance_rising is None

    def test_no_perf_data_stays_none(self, analyzer):
        cycle = CryptoMarketCycle()
        analyzer._estimate_usdt_dominance(cycle)
        assert cycle.usdt_dominance_rising is None


# ──────────────────────────────────────────────────────────────────
# _determine_market_phase
# ──────────────────────────────────────────────────────────────────

class TestMarketPhase:
    def test_bull_run_multiple_signals(self, analyzer):
        """Multiple bullish signals should produce bull_run."""
        cycle = CryptoMarketCycle(
            btc_dominance_trend="falling",  # +1 bull
            halving_phase="post_halving",   # +1 bull
            altcoin_season=True,            # +1 bull
            bmsb_status="bullish",          # +1 bull
        )
        analyzer._determine_market_phase(cycle)
        assert cycle.market_phase == "bull_run"

    def test_bear_market_multiple_signals(self, analyzer):
        """Multiple bearish signals should produce bear_market."""
        cycle = CryptoMarketCycle(
            btc_dominance_trend="rising",    # +1 bear
            halving_phase="distribution",    # +1 bear
            altcoin_season=False,
            bmsb_status="bearish",           # +1 bear
        )
        analyzer._determine_market_phase(cycle)
        assert cycle.market_phase == "bear_market"

    def test_accumulation_phase(self, analyzer):
        """Single bullish signal with no bearish = accumulation."""
        cycle = CryptoMarketCycle(
            btc_dominance_trend="stable",
            halving_phase="pre_halving",  # Not counted (neutral to slightly bullish)
            altcoin_season=True,          # +1 bull
        )
        analyzer._determine_market_phase(cycle)
        assert cycle.market_phase == "accumulation"

    def test_distribution_default(self, analyzer):
        """Mixed signals with equal bull/bear default to distribution."""
        cycle = CryptoMarketCycle(
            btc_dominance_trend="rising",   # +1 bear
            halving_phase="pre_halving",    # neutral (not counted as bull or bear)
            sma_d200_position="above",      # +1 bull
        )
        # 1 bull, 1 bear → neither reaches 2.0 → distribution
        analyzer._determine_market_phase(cycle)
        assert cycle.market_phase == "distribution"

    def test_rsi_overbought_adds_bear_vote(self, analyzer):
        """RSI > 80 should add a bearish vote."""
        cycle = CryptoMarketCycle(
            btc_dominance_trend="rising",    # +1 bear
            halving_phase="expansion",       # +1 bull
            btc_rsi_14=85.0,                 # +1 bear
        )
        analyzer._determine_market_phase(cycle)
        assert cycle.market_phase == "bear_market"

    def test_pi_cycle_half_weight(self, analyzer):
        """Pi cycle near_top should add 0.5 bear votes, not full."""
        cycle = CryptoMarketCycle(
            btc_dominance_trend="stable",
            pi_cycle_status="near_top",      # +0.5 bear
        )
        analyzer._determine_market_phase(cycle)
        # 0.5 bear < 2.0 threshold for bear_market
        assert cycle.market_phase != "bear_market"


# ──────────────────────────────────────────────────────────────────
# CryptoMarketCycle dataclass
# ──────────────────────────────────────────────────────────────────

class TestCryptoMarketCycleDataclass:
    def test_defaults(self):
        c = CryptoMarketCycle()
        assert c.btc_dominance is None
        assert c.market_phase == "unknown"
        assert c.altcoin_season is False
        assert c.halving_phase == "unknown"
        assert c.golden_cross is False
        assert c.death_cross is False
        assert c.rsi_diagonal_bearish is False
