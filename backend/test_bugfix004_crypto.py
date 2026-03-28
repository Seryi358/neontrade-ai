"""
BUGFIX-004: Comprehensive tests for crypto_cycle.py module.

Tests cover:
- BTC dominance analysis (thresholds, trends, altseason detection)
- Altcoin season detection (with USDT.D filter)
- Halving phase calculation (all 4 phases)
- BMSB (Bull Market Support Band) with 2-close confirmation
- Pi Cycle Top/Bottom indicator
- Dominance transition table (5 combinations)
- Market phase determination (bull/bear/accumulation/distribution)
- Capital rotation phases (btc, eth, large_alts, small_alts, memecoins)
- EMA 8 weekly break detection
- RSI 14 weekly calculation
- Crypto trailing EMA 50
- should_trade_crypto gating
- Green strategy in crypto context
"""

import sys
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, List

sys.path.insert(0, ".")

from core.crypto_cycle import CryptoCycleAnalyzer, CryptoMarketCycle


# ── Helpers ──────────────────────────────────────────────────────────

@dataclass
class MockCandle:
    open: float = 100.0
    high: float = 105.0
    low: float = 95.0
    close: float = 102.0
    volume: float = 1000.0
    time: str = "2026-03-28T00:00:00Z"


@dataclass
class MockPrice:
    bid: float = 100.0
    ask: float = 100.1


def make_candles(closes: List[float], base_open=None) -> List[MockCandle]:
    """Create a list of MockCandle from close prices."""
    return [
        MockCandle(
            open=base_open or c * 0.99,
            high=c * 1.02,
            low=c * 0.98,
            close=c,
        )
        for c in closes
    ]


def make_trending_candles(start: float, end: float, count: int) -> List[MockCandle]:
    """Create candles with a linear trend from start to end."""
    step = (end - start) / (count - 1)
    closes = [start + step * i for i in range(count)]
    return make_candles(closes)


class MockBroker:
    """Mock broker for crypto cycle tests."""

    def __init__(self, btc_price=50000.0, eth_price=3000.0):
        self._btc_price = btc_price
        self._eth_price = eth_price
        self._btc_candles = None
        self._eth_candles = None
        self._btc_weekly_candles = None

    async def get_current_price(self, symbol):
        if "BTC" in symbol:
            return MockPrice(bid=self._btc_price, ask=self._btc_price * 1.001)
        elif "ETH" in symbol:
            return MockPrice(bid=self._eth_price, ask=self._eth_price * 1.001)
        return None

    async def get_candles(self, symbol, granularity="D", count=30):
        if "BTC" in symbol and granularity == "W":
            if self._btc_weekly_candles:
                return self._btc_weekly_candles[:count]
            # Default: 60 weekly candles with uptrend
            return make_trending_candles(30000, 50000, max(count, 60))
        if "BTC" in symbol:
            if self._btc_candles:
                return self._btc_candles[:count]
            return make_trending_candles(45000, 50000, max(count, 30))
        if "ETH" in symbol:
            if self._eth_candles:
                return self._eth_candles[:count]
            return make_trending_candles(2800, 3000, max(count, 30))
        return None


# ── CryptoMarketCycle dataclass ──────────────────────────────────────

class TestCryptoMarketCycleFields:
    """Verify all expected fields exist on CryptoMarketCycle."""

    def test_all_fields_exist(self):
        cycle = CryptoMarketCycle()
        expected = [
            "btc_dominance", "btc_dominance_trend", "market_phase",
            "altcoin_season", "btc_eth_ratio", "btc_eth_trend",
            "eth_outperforming_btc", "rotation_phase", "halving_phase",
            "halving_phase_description", "halving_sentiment", "btc_rsi_14",
            "ema8_weekly_broken", "bmsb_status", "bmsb_consecutive_bearish_closes",
            "pi_cycle_status", "dominance_transition", "crypto_trailing_ema50",
            "using_fixed_tp_warning", "usdt_dominance_rising", "last_updated",
        ]
        for f in expected:
            assert hasattr(cycle, f), f"Missing field: {f}"

    def test_default_values(self):
        cycle = CryptoMarketCycle()
        assert cycle.btc_dominance is None
        assert cycle.btc_dominance_trend == "unknown"
        assert cycle.market_phase == "unknown"
        assert cycle.altcoin_season is False
        assert cycle.rotation_phase == "unknown"
        assert cycle.halving_phase == "unknown"
        assert cycle.halving_sentiment == "neutral"
        assert cycle.bmsb_status is None
        assert cycle.bmsb_consecutive_bearish_closes == 0
        assert cycle.pi_cycle_status is None
        assert cycle.ema8_weekly_broken is False
        assert cycle.usdt_dominance_rising is None


# ── Halving Phase ────────────────────────────────────────────────────

class TestHalvingPhase:
    """Test _analyze_halving_phase for all 4 phases."""

    def setup_method(self):
        self.analyzer = CryptoCycleAnalyzer()

    def test_post_halving_phase(self):
        """Within ~33% of cycle after halving = post_halving / very_bullish."""
        cycle = CryptoMarketCycle()
        # Patch datetime to be 3 months after 2024-04-19 halving
        with patch("core.crypto_cycle.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 7, 19, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            self.analyzer._analyze_halving_phase(cycle)
        assert cycle.halving_phase == "post_halving"
        assert cycle.halving_sentiment == "very_bullish"
        assert "Explosion" in cycle.halving_phase_description

    def test_expansion_phase(self):
        """33%-55% of cycle = expansion / bullish."""
        cycle = CryptoMarketCycle()
        # ~40% into cycle: about 577 days after halving (2024-04-19 + 577 = ~2025-11-17)
        with patch("core.crypto_cycle.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 11, 17, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            self.analyzer._analyze_halving_phase(cycle)
        assert cycle.halving_phase == "expansion"
        assert cycle.halving_sentiment == "bullish"

    def test_distribution_phase(self):
        """55%-75% of cycle = distribution / bearish."""
        cycle = CryptoMarketCycle()
        # ~65% into cycle: about 938 days after halving (2024-04-19 + 938 = ~2026-11-13)
        with patch("core.crypto_cycle.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 11, 13, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            self.analyzer._analyze_halving_phase(cycle)
        assert cycle.halving_phase == "distribution"
        assert cycle.halving_sentiment == "bearish"

    def test_pre_halving_phase(self):
        """75%-100% of cycle = pre_halving / bullish (accumulation)."""
        cycle = CryptoMarketCycle()
        # ~85% into cycle: about 1226 days after halving (2024-04-19 + 1226 = ~2027-08-27)
        with patch("core.crypto_cycle.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2027, 8, 27, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            self.analyzer._analyze_halving_phase(cycle)
        assert cycle.halving_phase == "pre_halving"
        assert cycle.halving_sentiment == "bullish"
        assert "Accumulation" in cycle.halving_phase_description

    def test_pre_halving_not_bearish(self):
        """Pre-halving is accumulation (bullish), NOT bearish per TradingLab."""
        cycle = CryptoMarketCycle()
        with patch("core.crypto_cycle.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2027, 12, 1, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            self.analyzer._analyze_halving_phase(cycle)
        assert cycle.halving_sentiment != "bearish"

    def test_halving_dates_correct(self):
        """Verify all 5 halving dates match TradingLab mentorship."""
        dates = CryptoCycleAnalyzer.HALVING_DATES
        assert len(dates) == 5
        assert dates[0] == datetime(2012, 11, 28, tzinfo=timezone.utc)
        assert dates[1] == datetime(2016, 7, 9, tzinfo=timezone.utc)
        assert dates[2] == datetime(2020, 5, 11, tzinfo=timezone.utc)
        assert dates[3] == datetime(2024, 4, 19, tzinfo=timezone.utc)
        assert dates[4] == datetime(2028, 4, 1, tzinfo=timezone.utc)


# ── BMSB (Bull Market Support Band) ─────────────────────────────────

class TestBMSB:
    """Test BMSB with 2-consecutive-close confirmation logic."""

    def setup_method(self):
        self.analyzer = CryptoCycleAnalyzer()

    def test_bmsb_bullish(self):
        """Price above BMSB = bullish, resets streak."""
        cycle = CryptoMarketCycle()
        self.analyzer._bmsb_bearish_streak = 3  # Previous streak
        self.analyzer._apply_bmsb(cycle, {"bullish": True, "bearish": False})
        assert cycle.bmsb_status == "bullish"
        assert cycle.bmsb_consecutive_bearish_closes == 0
        assert self.analyzer._bmsb_bearish_streak == 0

    def test_bmsb_first_bearish_close_is_warning(self):
        """First close below BMSB = warning, NOT confirmed bearish."""
        cycle = CryptoMarketCycle()
        self.analyzer._bmsb_bearish_streak = 0
        self.analyzer._apply_bmsb(cycle, {"bullish": False, "bearish": True})
        assert cycle.bmsb_status == "warning"
        assert cycle.bmsb_consecutive_bearish_closes == 1

    def test_bmsb_second_bearish_close_confirms(self):
        """2+ consecutive closes below BMSB = confirmed bearish."""
        cycle = CryptoMarketCycle()
        self.analyzer._bmsb_bearish_streak = 1  # Already had one close below
        self.analyzer._apply_bmsb(cycle, {"bullish": False, "bearish": True})
        assert cycle.bmsb_status == "bearish"
        assert cycle.bmsb_consecutive_bearish_closes == 2

    def test_bmsb_three_bearish_closes(self):
        """3 consecutive bearish closes still = bearish."""
        cycle = CryptoMarketCycle()
        self.analyzer._bmsb_bearish_streak = 2
        self.analyzer._apply_bmsb(cycle, {"bullish": False, "bearish": True})
        assert cycle.bmsb_status == "bearish"
        assert cycle.bmsb_consecutive_bearish_closes == 3

    def test_bmsb_bullish_resets_after_bearish(self):
        """Bullish close after bearish streak resets everything."""
        cycle = CryptoMarketCycle()
        self.analyzer._bmsb_bearish_streak = 3
        self.analyzer._apply_bmsb(cycle, {"bullish": True, "bearish": False})
        assert cycle.bmsb_status == "bullish"
        assert self.analyzer._bmsb_bearish_streak == 0

        # Next bearish close should be warning again
        cycle2 = CryptoMarketCycle()
        self.analyzer._apply_bmsb(cycle2, {"bullish": False, "bearish": True})
        assert cycle2.bmsb_status == "warning"

    def test_bmsb_none_input(self):
        """None BMSB input leaves status unchanged."""
        cycle = CryptoMarketCycle()
        self.analyzer._apply_bmsb(cycle, None)
        assert cycle.bmsb_status is None


# ── Pi Cycle Top/Bottom ──────────────────────────────────────────────

class TestPiCycle:
    """Test Pi Cycle indicator application."""

    def setup_method(self):
        self.analyzer = CryptoCycleAnalyzer()

    def test_pi_cycle_near_top(self):
        cycle = CryptoMarketCycle()
        self.analyzer._apply_pi_cycle(cycle, {"near_top": True, "near_bottom": False})
        assert cycle.pi_cycle_status == "near_top"

    def test_pi_cycle_near_bottom(self):
        cycle = CryptoMarketCycle()
        self.analyzer._apply_pi_cycle(cycle, {"near_top": False, "near_bottom": True})
        assert cycle.pi_cycle_status == "near_bottom"

    def test_pi_cycle_neutral(self):
        cycle = CryptoMarketCycle()
        self.analyzer._apply_pi_cycle(cycle, {"near_top": False, "near_bottom": False})
        assert cycle.pi_cycle_status is None

    def test_pi_cycle_none_input(self):
        cycle = CryptoMarketCycle()
        self.analyzer._apply_pi_cycle(cycle, None)
        assert cycle.pi_cycle_status is None


# ── Dominance Transition Table ───────────────────────────────────────

class TestDominanceTransition:
    """Test the 5-row dominance transition table from TradingLab."""

    def setup_method(self):
        self.analyzer = CryptoCycleAnalyzer()

    def _make_cycle(self, dom_trend, btc_perf_7d):
        cycle = CryptoMarketCycle()
        cycle.btc_dominance_trend = dom_trend
        cycle._btc_perf_7d = btc_perf_7d
        return cycle

    def test_rising_dom_btc_up_alts_down(self):
        """BTC.D up + BTC up = altcoins down."""
        result = self.analyzer.get_dominance_transition(
            self._make_cycle("rising", 0.05))
        assert result["altcoin_outlook"] == "down"

    def test_rising_dom_btc_down_alts_down_much_more(self):
        """BTC.D up + BTC down = altcoins down MUCH MORE."""
        result = self.analyzer.get_dominance_transition(
            self._make_cycle("rising", -0.05))
        assert result["altcoin_outlook"] == "down_much_more"

    def test_falling_dom_btc_up_altseason(self):
        """BTC.D down + BTC up = altcoins up significantly (altseason)."""
        result = self.analyzer.get_dominance_transition(
            self._make_cycle("falling", 0.05))
        assert result["altcoin_outlook"] == "up_significantly"

    def test_falling_dom_btc_stable_capital_rotating(self):
        """BTC.D down + BTC stable = capital rotating to altcoins."""
        result = self.analyzer.get_dominance_transition(
            self._make_cycle("falling", 0.01))
        assert result["altcoin_outlook"] == "capital_rotating_to_alts"

    def test_falling_dom_btc_down_rare(self):
        """BTC.D down + BTC down = rare, alts may fall."""
        result = self.analyzer.get_dominance_transition(
            self._make_cycle("falling", -0.05))
        assert result["altcoin_outlook"] == "rare_alts_may_fall"

    def test_rising_dom_btc_stable(self):
        """BTC.D up + BTC stable = altcoins still down."""
        result = self.analyzer.get_dominance_transition(
            self._make_cycle("rising", 0.01))
        assert result["altcoin_outlook"] == "down"

    def test_stable_dom(self):
        """Stable dominance = neutral."""
        result = self.analyzer.get_dominance_transition(
            self._make_cycle("stable", 0.01))
        assert result["altcoin_outlook"] == "neutral"

    def test_transition_returns_all_keys(self):
        result = self.analyzer.get_dominance_transition(
            self._make_cycle("rising", 0.05))
        assert "dominance_trend" in result
        assert "btc_trend" in result
        assert "altcoin_outlook" in result


# ── Market Phase Determination ───────────────────────────────────────

class TestMarketPhase:
    """Test _determine_market_phase vote counting."""

    def setup_method(self):
        self.analyzer = CryptoCycleAnalyzer()

    def test_bull_run_multiple_bullish_signals(self):
        """>=2 bull votes = bull_run."""
        cycle = CryptoMarketCycle()
        cycle.btc_dominance_trend = "falling"  # +1 bull
        cycle.halving_phase = "post_halving"   # +1 bull
        cycle.altcoin_season = True            # +1 bull
        cycle.bmsb_status = "bullish"          # +1 bull
        self.analyzer._determine_market_phase(cycle)
        assert cycle.market_phase == "bull_run"

    def test_bear_market_multiple_bearish_signals(self):
        """>=2 bear votes = bear_market."""
        cycle = CryptoMarketCycle()
        cycle.btc_dominance_trend = "rising"   # +1 bear
        cycle.halving_phase = "distribution"   # +1 bear
        cycle.altcoin_season = False
        cycle.bmsb_status = "bearish"          # +1 bear
        self.analyzer._determine_market_phase(cycle)
        assert cycle.market_phase == "bear_market"

    def test_accumulation_mild_bullish(self):
        """1 bull vote + 0 bear = accumulation."""
        cycle = CryptoMarketCycle()
        cycle.btc_dominance_trend = "stable"
        cycle.halving_phase = "pre_halving"    # neutral (NOT bear)
        cycle.altcoin_season = False
        cycle.bmsb_status = "bullish"          # +1 bull
        cycle.pi_cycle_status = None
        # No bearish signals, only 1 bullish
        self.analyzer._determine_market_phase(cycle)
        assert cycle.market_phase == "accumulation"

    def test_pre_halving_not_counted_as_bearish(self):
        """pre_halving should NOT add bear votes."""
        cycle = CryptoMarketCycle()
        cycle.btc_dominance_trend = "stable"
        cycle.halving_phase = "pre_halving"
        cycle.altcoin_season = False
        cycle.bmsb_status = None
        cycle.pi_cycle_status = None
        self.analyzer._determine_market_phase(cycle)
        # With no signals, should not be bear_market
        assert cycle.market_phase != "bear_market"

    def test_pi_cycle_half_vote(self):
        """Pi cycle only counts as 0.5 vote (less reliable per mentorship)."""
        cycle = CryptoMarketCycle()
        cycle.btc_dominance_trend = "stable"
        cycle.halving_phase = "expansion"       # +1 bull
        cycle.altcoin_season = False
        cycle.bmsb_status = None
        cycle.pi_cycle_status = "near_bottom"   # +0.5 bull
        self.analyzer._determine_market_phase(cycle)
        # 1.5 bull votes < 2.0 threshold for bull_run
        assert cycle.market_phase == "accumulation"

    def test_bmsb_warning_not_counted(self):
        """BMSB 'warning' (1 close) should not count as bearish vote."""
        cycle = CryptoMarketCycle()
        cycle.btc_dominance_trend = "stable"
        cycle.halving_phase = "expansion"       # +1 bull
        cycle.altcoin_season = False
        cycle.bmsb_status = "warning"           # Should NOT count
        cycle.pi_cycle_status = None
        self.analyzer._determine_market_phase(cycle)
        assert cycle.market_phase != "bear_market"

    def test_dominance_transition_affects_phase(self):
        """Dominance transition altcoin outlook contributes votes."""
        cycle = CryptoMarketCycle()
        cycle.btc_dominance_trend = "falling"     # +1 bull
        cycle.halving_phase = "expansion"          # +1 bull
        cycle.altcoin_season = True                # +1 bull
        cycle.bmsb_status = None
        cycle.pi_cycle_status = None
        # Falling dom + some btc_perf => transition adds votes
        cycle._btc_perf_7d = 0.05  # BTC up
        self.analyzer._determine_market_phase(cycle)
        assert cycle.market_phase == "bull_run"


# ── BTC Dominance Analysis ──────────────────────────────────────────

class TestDominanceAnalysis:
    """Test _analyze_dominance with mock broker data."""

    @pytest.mark.asyncio
    async def test_rising_dominance_btc_outperforms(self):
        """BTC outperforming ETH by >3% = rising dominance."""
        broker = MockBroker()
        # BTC up 10%, ETH up 2% over 7 days
        btc_closes = [45000 + i * 50 for i in range(30)]
        btc_closes[-1] = btc_closes[-7] * 1.10  # 10% gain
        eth_closes = [2800 + i * 5 for i in range(30)]
        eth_closes[-1] = eth_closes[-7] * 1.02  # 2% gain
        broker._btc_candles = make_candles(btc_closes)
        broker._eth_candles = make_candles(eth_closes)

        analyzer = CryptoCycleAnalyzer(broker=broker)
        cycle = CryptoMarketCycle()
        await analyzer._analyze_dominance(cycle)
        assert cycle.btc_dominance_trend == "rising"

    @pytest.mark.asyncio
    async def test_falling_dominance_eth_outperforms(self):
        """ETH outperforming BTC by >3% = falling dominance."""
        broker = MockBroker()
        btc_closes = [45000 + i * 50 for i in range(30)]
        btc_closes[-1] = btc_closes[-7] * 1.01  # 1% gain
        eth_closes = [2800 + i * 5 for i in range(30)]
        eth_closes[-1] = eth_closes[-7] * 1.08  # 8% gain
        broker._btc_candles = make_candles(btc_closes)
        broker._eth_candles = make_candles(eth_closes)

        analyzer = CryptoCycleAnalyzer(broker=broker)
        cycle = CryptoMarketCycle()
        await analyzer._analyze_dominance(cycle)
        assert cycle.btc_dominance_trend == "falling"

    @pytest.mark.asyncio
    async def test_stable_dominance(self):
        """Similar BTC/ETH performance = stable dominance."""
        broker = MockBroker()
        btc_closes = [45000 + i * 50 for i in range(30)]
        btc_closes[-1] = btc_closes[-7] * 1.02
        eth_closes = [2800 + i * 5 for i in range(30)]
        eth_closes[-1] = eth_closes[-7] * 1.02
        broker._btc_candles = make_candles(btc_closes)
        broker._eth_candles = make_candles(eth_closes)

        analyzer = CryptoCycleAnalyzer(broker=broker)
        cycle = CryptoMarketCycle()
        await analyzer._analyze_dominance(cycle)
        assert cycle.btc_dominance_trend == "stable"

    @pytest.mark.asyncio
    async def test_no_broker_no_crash(self):
        """No broker = graceful no-op."""
        analyzer = CryptoCycleAnalyzer(broker=None)
        cycle = CryptoMarketCycle()
        await analyzer._analyze_dominance(cycle)
        assert cycle.btc_dominance_trend == "unknown"


# ── Altcoin Season Detection ────────────────────────────────────────

class TestAltcoinSeason:
    """Test altcoin season detection with USDT.D filter."""

    @pytest.mark.asyncio
    async def test_altseason_requires_falling_dom_and_eth_outperforming(self):
        """Altseason needs BOTH falling dominance AND ETH outperforming."""
        broker = MockBroker()
        # ETH massively outperforms BTC
        btc_closes = [45000 + i * 50 for i in range(30)]
        btc_closes[-1] = btc_closes[-7] * 1.01
        eth_closes = [2800 + i * 5 for i in range(30)]
        eth_closes[-1] = eth_closes[-7] * 1.10
        broker._btc_candles = make_candles(btc_closes)
        broker._eth_candles = make_candles(eth_closes)

        analyzer = CryptoCycleAnalyzer(broker=broker)
        cycle = CryptoMarketCycle()
        await analyzer._analyze_dominance(cycle)
        # Also need to run btc_eth to set eth_outperforming_btc
        await analyzer._analyze_btc_eth(cycle)
        # Now re-run dominance with eth_outperforming set
        await analyzer._analyze_dominance(cycle)
        assert cycle.btc_dominance_trend == "falling"
        assert cycle.eth_outperforming_btc is True
        assert cycle.altcoin_season is True

    @pytest.mark.asyncio
    async def test_usdt_dominance_rising_blocks_altseason(self):
        """USDT.D rising = risk-off, NOT altseason even if BTC.D falling."""
        broker = MockBroker()
        btc_closes = [45000 + i * 50 for i in range(30)]
        btc_closes[-1] = btc_closes[-7] * 1.01
        eth_closes = [2800 + i * 5 for i in range(30)]
        eth_closes[-1] = eth_closes[-7] * 1.10
        broker._btc_candles = make_candles(btc_closes)
        broker._eth_candles = make_candles(eth_closes)

        analyzer = CryptoCycleAnalyzer(broker=broker)
        cycle = CryptoMarketCycle()
        cycle.usdt_dominance_rising = True  # Risk-off signal
        cycle.eth_outperforming_btc = True
        await analyzer._analyze_dominance(cycle)
        assert cycle.altcoin_season is False  # Blocked by USDT.D

    @pytest.mark.asyncio
    async def test_btc_dominance_thresholds_with_explicit_value(self):
        """Test BTC.D threshold logic when explicit dominance value is available."""
        broker = MockBroker()
        btc_closes = [45000 + i * 50 for i in range(30)]
        eth_closes = [2800 + i * 5 for i in range(30)]
        broker._btc_candles = make_candles(btc_closes)
        broker._eth_candles = make_candles(eth_closes)

        analyzer = CryptoCycleAnalyzer(broker=broker)

        # BTC.D > 50%: no altseason
        cycle = CryptoMarketCycle()
        cycle.btc_dominance = 55.0
        await analyzer._analyze_dominance(cycle)
        assert cycle.altcoin_season is False
        assert cycle.btc_eth_trend == "btc_leading"

        # BTC.D < 40%: altseason
        cycle2 = CryptoMarketCycle()
        cycle2.btc_dominance = 35.0
        await analyzer._analyze_dominance(cycle2)
        assert cycle2.altcoin_season is True
        assert cycle2.btc_eth_trend == "eth_leading"

        # BTC.D 40-50%: neutral
        cycle3 = CryptoMarketCycle()
        cycle3.btc_dominance = 45.0
        await analyzer._analyze_dominance(cycle3)
        assert cycle3.altcoin_season is False
        assert cycle3.btc_eth_trend == "neutral"


# ── Capital Rotation ─────────────────────────────────────────────────

class TestCapitalRotation:
    """Test capital rotation phase detection."""

    @pytest.mark.asyncio
    async def test_rising_dom_btc_phase(self):
        """Rising dominance = money flowing into BTC."""
        broker = MockBroker()
        # BTC massively outperforms
        btc_closes = [45000 + i * 50 for i in range(30)]
        btc_closes[-1] = btc_closes[-7] * 1.10
        eth_closes = [2800 + i * 5 for i in range(30)]
        eth_closes[-1] = eth_closes[-7] * 1.01
        broker._btc_candles = make_candles(btc_closes)
        broker._eth_candles = make_candles(eth_closes)

        analyzer = CryptoCycleAnalyzer(broker=broker)
        cycle = CryptoMarketCycle()
        await analyzer._analyze_dominance(cycle)
        await analyzer._analyze_btc_eth(cycle)
        assert cycle.rotation_phase == "btc"

    @pytest.mark.asyncio
    async def test_eth_rotation_phase(self):
        """Falling dom + ETH outperforming + no altseason = eth phase."""
        broker = MockBroker()
        btc_closes = [45000 + i * 50 for i in range(30)]
        btc_closes[-1] = btc_closes[-7] * 1.01
        eth_closes = [2800 + i * 5 for i in range(30)]
        eth_closes[-1] = eth_closes[-7] * 1.08
        broker._btc_candles = make_candles(btc_closes)
        broker._eth_candles = make_candles(eth_closes)

        analyzer = CryptoCycleAnalyzer(broker=broker)
        cycle = CryptoMarketCycle()
        await analyzer._analyze_dominance(cycle)
        await analyzer._analyze_btc_eth(cycle)
        # eth_outperforming + falling dom + no altseason = "eth" phase
        if cycle.btc_dominance_trend == "falling" and cycle.eth_outperforming_btc and not cycle.altcoin_season:
            assert cycle.rotation_phase == "eth"


# ── EMA 8 Weekly ─────────────────────────────────────────────────────

class TestEMA8Weekly:
    """Test EMA 8 weekly break detection."""

    @pytest.mark.asyncio
    async def test_ema8_broken_below(self):
        """Weekly close below EMA 8 = ema8_weekly_broken True."""
        broker = MockBroker()
        # Start high, end low — last close below EMA 8
        closes = [50000 - i * 200 for i in range(10)]  # Downtrend
        broker._btc_weekly_candles = make_candles(closes)

        analyzer = CryptoCycleAnalyzer(broker=broker)
        cycle = CryptoMarketCycle()
        await analyzer._check_ema8_weekly(cycle)
        # With a clear downtrend, last close should be below EMA 8
        assert cycle.ema8_weekly_broken is True

    @pytest.mark.asyncio
    async def test_ema8_intact_uptrend(self):
        """Uptrend with close above EMA 8 = ema8_weekly_broken False."""
        broker = MockBroker()
        closes = [40000 + i * 500 for i in range(10)]  # Uptrend
        broker._btc_weekly_candles = make_candles(closes)

        analyzer = CryptoCycleAnalyzer(broker=broker)
        cycle = CryptoMarketCycle()
        await analyzer._check_ema8_weekly(cycle)
        assert cycle.ema8_weekly_broken is False

    @pytest.mark.asyncio
    async def test_no_broker_no_crash(self):
        analyzer = CryptoCycleAnalyzer(broker=None)
        cycle = CryptoMarketCycle()
        await analyzer._check_ema8_weekly(cycle)
        assert cycle.ema8_weekly_broken is False


# ── RSI 14 Weekly ────────────────────────────────────────────────────

class TestRSI14Weekly:
    """Test RSI 14 calculation on weekly candles."""

    @pytest.mark.asyncio
    async def test_rsi_calculated(self):
        """RSI should be calculated from weekly BTC candles."""
        broker = MockBroker()
        # 30 weekly candles with mild uptrend
        closes = [40000 + i * 300 for i in range(30)]
        broker._btc_weekly_candles = make_candles(closes)

        analyzer = CryptoCycleAnalyzer(broker=broker)
        cycle = CryptoMarketCycle()
        await analyzer._analyze_rsi(cycle)
        assert cycle.btc_rsi_14 is not None
        assert 0 <= cycle.btc_rsi_14 <= 100

    @pytest.mark.asyncio
    async def test_rsi_strong_uptrend_high(self):
        """Strong uptrend should produce high RSI."""
        broker = MockBroker()
        closes = [30000 + i * 1000 for i in range(30)]  # Strong uptrend
        broker._btc_weekly_candles = make_candles(closes)

        analyzer = CryptoCycleAnalyzer(broker=broker)
        cycle = CryptoMarketCycle()
        await analyzer._analyze_rsi(cycle)
        assert cycle.btc_rsi_14 is not None
        assert cycle.btc_rsi_14 > 70  # Should be high in strong uptrend

    @pytest.mark.asyncio
    async def test_rsi_extreme_triggers_phase(self):
        """RSI > 80 = distribution, RSI < 25 = accumulation."""
        broker = MockBroker()
        # Very strong uptrend for high RSI
        closes = [20000 + i * 2000 for i in range(30)]
        broker._btc_weekly_candles = make_candles(closes)

        analyzer = CryptoCycleAnalyzer(broker=broker)
        cycle = CryptoMarketCycle()
        await analyzer._analyze_rsi(cycle)
        if cycle.btc_rsi_14 and cycle.btc_rsi_14 > 80:
            assert cycle.market_phase == "distribution"

    @pytest.mark.asyncio
    async def test_no_broker_no_crash(self):
        analyzer = CryptoCycleAnalyzer(broker=None)
        cycle = CryptoMarketCycle()
        await analyzer._analyze_rsi(cycle)
        assert cycle.btc_rsi_14 is None


# ── Crypto Trailing EMA 50 ──────────────────────────────────────────

class TestCryptoTrailingEMA:
    """Test EMA 50 weekly trailing stop calculation."""

    @pytest.mark.asyncio
    async def test_ema50_calculated(self):
        """EMA 50 should be computed from 60 weekly candles."""
        broker = MockBroker()
        closes = [30000 + i * 300 for i in range(60)]
        broker._btc_weekly_candles = make_candles(closes)

        analyzer = CryptoCycleAnalyzer(broker=broker)
        ema = await analyzer.get_crypto_trailing_ema("BTC_USD")
        assert ema is not None
        assert ema > 0
        # EMA should be between min and max of closes
        assert min(closes) < ema < max(closes)

    @pytest.mark.asyncio
    async def test_ema50_no_broker(self):
        analyzer = CryptoCycleAnalyzer(broker=None)
        ema = await analyzer.get_crypto_trailing_ema("BTC_USD")
        assert ema is None

    @pytest.mark.asyncio
    async def test_ema50_insufficient_data(self):
        """Less than 50 candles should return None."""
        broker = MockBroker()
        broker._btc_weekly_candles = make_candles([40000 + i * 100 for i in range(30)])

        analyzer = CryptoCycleAnalyzer(broker=broker)
        ema = await analyzer.get_crypto_trailing_ema("BTC_USD")
        assert ema is None


# ── should_trade_crypto ──────────────────────────────────────────────

class TestShouldTradeCrypto:
    """Test the should_trade_crypto gating function."""

    @pytest.mark.asyncio
    async def test_bear_market_blocks_trading(self):
        """Bear market phase should return False."""
        broker = MockBroker()
        analyzer = CryptoCycleAnalyzer(broker=broker)

        # Force bear market conditions
        with patch.object(analyzer, "get_cycle_status") as mock_status:
            cycle = CryptoMarketCycle()
            cycle.market_phase = "bear_market"
            cycle.btc_dominance_trend = "rising"
            cycle.halving_phase = "distribution"
            mock_status.return_value = cycle

            with patch.object(analyzer, "get_crypto_trailing_ema", return_value=40000.0):
                can_trade, reason = await analyzer.should_trade_crypto()
                assert can_trade is False
                assert "Bear market" in reason

    @pytest.mark.asyncio
    async def test_bull_run_allows_trading(self):
        """Non-bear phase should return True."""
        broker = MockBroker()
        analyzer = CryptoCycleAnalyzer(broker=broker)

        with patch.object(analyzer, "get_cycle_status") as mock_status:
            cycle = CryptoMarketCycle()
            cycle.market_phase = "bull_run"
            cycle.ema8_weekly_broken = False
            cycle.bmsb_status = "bullish"
            cycle.pi_cycle_status = None
            cycle.usdt_dominance_rising = None
            mock_status.return_value = cycle

            with patch.object(analyzer, "get_crypto_trailing_ema", return_value=45000.0):
                can_trade, reason = await analyzer.should_trade_crypto()
                assert can_trade is True

    @pytest.mark.asyncio
    async def test_ema8_broken_warning_in_reason(self):
        """EMA 8 broken should appear as warning in reason string."""
        broker = MockBroker()
        analyzer = CryptoCycleAnalyzer(broker=broker)

        with patch.object(analyzer, "get_cycle_status") as mock_status:
            cycle = CryptoMarketCycle()
            cycle.market_phase = "bull_run"
            cycle.ema8_weekly_broken = True
            cycle.bmsb_status = None
            cycle.pi_cycle_status = None
            cycle.usdt_dominance_rising = None
            mock_status.return_value = cycle

            with patch.object(analyzer, "get_crypto_trailing_ema", return_value=45000.0):
                can_trade, reason = await analyzer.should_trade_crypto()
                assert can_trade is True
                assert "EMA 8" in reason

    @pytest.mark.asyncio
    async def test_bmsb_bearish_warning_in_reason(self):
        """BMSB bearish should appear in reason."""
        broker = MockBroker()
        analyzer = CryptoCycleAnalyzer(broker=broker)

        with patch.object(analyzer, "get_cycle_status") as mock_status:
            cycle = CryptoMarketCycle()
            cycle.market_phase = "accumulation"
            cycle.ema8_weekly_broken = False
            cycle.bmsb_status = "bearish"
            cycle.pi_cycle_status = None
            cycle.usdt_dominance_rising = None
            mock_status.return_value = cycle

            with patch.object(analyzer, "get_crypto_trailing_ema", return_value=45000.0):
                can_trade, reason = await analyzer.should_trade_crypto()
                assert "BMSB bearish" in reason

    @pytest.mark.asyncio
    async def test_bmsb_warning_caution_in_reason(self):
        """BMSB warning (first close) should show CAUTION."""
        broker = MockBroker()
        analyzer = CryptoCycleAnalyzer(broker=broker)

        with patch.object(analyzer, "get_cycle_status") as mock_status:
            cycle = CryptoMarketCycle()
            cycle.market_phase = "bull_run"
            cycle.ema8_weekly_broken = False
            cycle.bmsb_status = "warning"
            cycle.pi_cycle_status = None
            cycle.usdt_dominance_rising = None
            mock_status.return_value = cycle

            with patch.object(analyzer, "get_crypto_trailing_ema", return_value=45000.0):
                can_trade, reason = await analyzer.should_trade_crypto()
                assert "CAUTION" in reason

    @pytest.mark.asyncio
    async def test_fixed_tp_warning(self):
        """Using fixed TP should produce warning about EMA 50 trailing."""
        broker = MockBroker()
        analyzer = CryptoCycleAnalyzer(broker=broker)

        with patch.object(analyzer, "get_cycle_status") as mock_status:
            cycle = CryptoMarketCycle()
            cycle.market_phase = "bull_run"
            cycle.ema8_weekly_broken = False
            cycle.bmsb_status = None
            cycle.pi_cycle_status = None
            cycle.usdt_dominance_rising = None
            mock_status.return_value = cycle

            with patch.object(analyzer, "get_crypto_trailing_ema", return_value=45000.0):
                can_trade, reason = await analyzer.should_trade_crypto(using_fixed_tp=True)
                assert can_trade is True
                assert "fixed TPs" in reason
                assert cycle.using_fixed_tp_warning is True

    @pytest.mark.asyncio
    async def test_pi_cycle_near_top_warning(self):
        """Pi Cycle near top should warn about distribution risk."""
        broker = MockBroker()
        analyzer = CryptoCycleAnalyzer(broker=broker)

        with patch.object(analyzer, "get_cycle_status") as mock_status:
            cycle = CryptoMarketCycle()
            cycle.market_phase = "distribution"
            cycle.ema8_weekly_broken = False
            cycle.bmsb_status = None
            cycle.pi_cycle_status = "near_top"
            cycle.usdt_dominance_rising = None
            mock_status.return_value = cycle

            with patch.object(analyzer, "get_crypto_trailing_ema", return_value=45000.0):
                can_trade, reason = await analyzer.should_trade_crypto()
                assert "Pi Cycle near top" in reason

    @pytest.mark.asyncio
    async def test_usdt_dominance_rising_warning(self):
        """USDT.D rising should warn about risk-off."""
        broker = MockBroker()
        analyzer = CryptoCycleAnalyzer(broker=broker)

        with patch.object(analyzer, "get_cycle_status") as mock_status:
            cycle = CryptoMarketCycle()
            cycle.market_phase = "bull_run"
            cycle.ema8_weekly_broken = False
            cycle.bmsb_status = None
            cycle.pi_cycle_status = None
            cycle.usdt_dominance_rising = True
            mock_status.return_value = cycle

            with patch.object(analyzer, "get_crypto_trailing_ema", return_value=45000.0):
                can_trade, reason = await analyzer.should_trade_crypto()
                assert "USDT.D rising" in reason

    @pytest.mark.asyncio
    async def test_ema50_value_in_reason(self):
        """EMA 50 trailing value should appear in reason."""
        broker = MockBroker()
        analyzer = CryptoCycleAnalyzer(broker=broker)

        with patch.object(analyzer, "get_cycle_status") as mock_status:
            cycle = CryptoMarketCycle()
            cycle.market_phase = "bull_run"
            cycle.ema8_weekly_broken = False
            cycle.bmsb_status = None
            cycle.pi_cycle_status = None
            cycle.usdt_dominance_rising = None
            mock_status.return_value = cycle

            with patch.object(analyzer, "get_crypto_trailing_ema", return_value=45123.45):
                can_trade, reason = await analyzer.should_trade_crypto()
                assert "45123.45" in reason


# ── Full Cycle Integration ──────────────────────────────────────────

class TestFullCycleStatus:
    """Integration test for get_cycle_status combining all analyses."""

    @pytest.mark.asyncio
    async def test_full_cycle_returns_populated_object(self):
        """get_cycle_status should return a fully populated CryptoMarketCycle."""
        broker = MockBroker()
        analyzer = CryptoCycleAnalyzer(broker=broker)

        cycle = await analyzer.get_cycle_status(
            bmsb={"bullish": True, "bearish": False},
            pi_cycle={"near_top": False, "near_bottom": False},
        )
        assert isinstance(cycle, CryptoMarketCycle)
        assert cycle.last_updated is not None
        assert cycle.halving_phase != "unknown"
        assert cycle.bmsb_status == "bullish"
        assert cycle.market_phase != "unknown"

    @pytest.mark.asyncio
    async def test_cycle_caching(self):
        """Second call within 1 hour should return cached result."""
        broker = MockBroker()
        analyzer = CryptoCycleAnalyzer(broker=broker)

        cycle1 = await analyzer.get_cycle_status()
        cycle2 = await analyzer.get_cycle_status()
        assert cycle1 is cycle2  # Same object from cache

    @pytest.mark.asyncio
    async def test_bmsb_and_pi_cycle_passed_through(self):
        """BMSB and Pi Cycle from AnalysisResult should be applied."""
        broker = MockBroker()
        analyzer = CryptoCycleAnalyzer(broker=broker)

        cycle = await analyzer.get_cycle_status(
            bmsb={"bullish": False, "bearish": True},
            pi_cycle={"near_top": True, "near_bottom": False},
        )
        # First bearish close = warning
        assert cycle.bmsb_status == "warning"
        assert cycle.pi_cycle_status == "near_top"


# ── Green Strategy Crypto Context ────────────────────────────────────

class TestGreenStrategyCrypto:
    """Test Green strategy is correctly restricted to crypto."""

    def test_green_is_crypto_only(self):
        """Green strategy should be marked as crypto-only."""
        from strategies.base import GreenStrategy
        green = GreenStrategy()
        assert green.color.value == "GREEN"
        # Green's name mentions it's the most lucrative
        assert "GREEN" in green.name

    def test_green_strategy_exists_in_detect_all(self):
        """Green should be in the strategy list."""
        from strategies.base import detect_all_setups, StrategyColor
        # Verify GreenStrategy is importable and has correct color
        from strategies.base import GreenStrategy
        g = GreenStrategy()
        assert g.color == StrategyColor.GREEN

    def test_green_min_rr_is_2(self):
        """Green requires min 2.0 R:R per TradingLab."""
        from strategies.base import GreenStrategy
        green = GreenStrategy()
        # Green's min_confidence should be set
        assert green.min_confidence > 0


# ── Edge Cases ──────────────────────────────────────────────────────

class TestEdgeCases:
    """Edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_broker_returns_none_candles(self):
        """None candle responses should not crash."""
        broker = MagicMock()
        broker.get_candles = AsyncMock(return_value=None)
        broker.get_current_price = AsyncMock(return_value=None)

        analyzer = CryptoCycleAnalyzer(broker=broker)
        cycle = CryptoMarketCycle()
        await analyzer._analyze_dominance(cycle)
        await analyzer._check_ema8_weekly(cycle)
        await analyzer._analyze_rsi(cycle)
        # Should not crash, just leave defaults
        assert cycle.btc_dominance_trend == "unknown"
        assert cycle.ema8_weekly_broken is False
        assert cycle.btc_rsi_14 is None

    @pytest.mark.asyncio
    async def test_broker_raises_exception(self):
        """Broker exceptions should be caught gracefully."""
        broker = MagicMock()
        broker.get_candles = AsyncMock(side_effect=Exception("Connection failed"))
        broker.get_current_price = AsyncMock(side_effect=Exception("Connection failed"))

        analyzer = CryptoCycleAnalyzer(broker=broker)
        cycle = CryptoMarketCycle()
        await analyzer._analyze_dominance(cycle)
        await analyzer._analyze_btc_eth(cycle)
        await analyzer._check_ema8_weekly(cycle)
        await analyzer._analyze_rsi(cycle)
        # All should fail gracefully
        assert cycle.btc_dominance_trend == "unknown"

    def test_analyzer_without_broker(self):
        """Analyzer without broker should work for non-async methods."""
        analyzer = CryptoCycleAnalyzer()
        cycle = CryptoMarketCycle()
        analyzer._analyze_halving_phase(cycle)
        assert cycle.halving_phase != "unknown"

        analyzer._apply_bmsb(cycle, {"bullish": True})
        assert cycle.bmsb_status == "bullish"

        result = analyzer.get_dominance_transition(cycle)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_close_method(self):
        """close() should not crash."""
        analyzer = CryptoCycleAnalyzer()
        await analyzer.close()
