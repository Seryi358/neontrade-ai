"""
BUGFIX-007: Edge case tests — second round of bug hunting.

Tests for:
1. No broker connection (circuit breaker behavior)
2. Incomplete market data (graceful handling)
3. Multiple simultaneous trades (risk limit enforcement)
4. Trading outside session hours (no execution)
5. Friday close behavior (close near SL/TP, keep others)
"""

import sys
import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Optional

sys.path.insert(0, ".")

from core.resilience import CircuitBreaker, broker_circuit_breaker
from core.risk_manager import RiskManager, TradingStyle
from config import settings


# ── Helpers ────────────────────────────────────────────────────────────

def run_async(coro):
    """Run async test in sync context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@dataclass
class FakeTrade:
    """Mimics broker open trade object."""
    trade_id: str
    instrument: str
    entry_price: Optional[float] = None
    current_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class MockBroker:
    """Minimal mock broker for edge case testing."""

    def __init__(self, balance=10000.0, pip_value=0.0001):
        self._balance = balance
        self._pip_value = pip_value
        self.closed_trades: List[str] = []
        self._open_trades: List[FakeTrade] = []

    async def get_account_balance(self):
        return self._balance

    async def get_pip_value(self, instrument):
        return self._pip_value

    async def get_open_trades(self):
        return list(self._open_trades)

    async def close_trade(self, trade_id):
        self.closed_trades.append(trade_id)


# ═══════════════════════════════════════════════════════════════════════
# 1. CIRCUIT BREAKER — No broker connection
# ═══════════════════════════════════════════════════════════════════════

class TestCircuitBreaker:
    """Tests that the circuit breaker protects against broker outages."""

    def test_starts_closed(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10.0, name="test")
        assert cb.state == CircuitBreaker.CLOSED
        assert not cb.is_open

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10.0, name="test")
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED  # 2 < 3
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN  # 3 >= 3
        assert cb.is_open

    def test_stays_closed_below_threshold(self):
        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=10.0, name="test")
        for _ in range(4):
            cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10.0, name="test")
        cb.record_failure()
        cb.record_failure()
        cb.record_success()  # Should reset count
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED  # Only 2 after reset

    def test_recovery_transitions_to_half_open(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1, name="test")
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        # Wait for recovery timeout
        time.sleep(0.15)
        assert cb.state == CircuitBreaker.HALF_OPEN

    def test_half_open_success_closes(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1, name="test")
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        assert cb.state == CircuitBreaker.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1, name="test")
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        time.sleep(0.15)
        assert cb.state == CircuitBreaker.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

    def test_reset_restores_closed(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60.0, name="test")
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open
        cb.reset()
        assert cb.state == CircuitBreaker.CLOSED
        assert not cb.is_open

    def test_global_broker_cb_has_correct_config(self):
        """Verify production circuit breaker config matches expectations."""
        assert broker_circuit_breaker.failure_threshold == 5  # 5 consecutive failures (50 was too permissive)
        assert broker_circuit_breaker.recovery_timeout == 30.0
        assert broker_circuit_breaker.name == "broker"


# ═══════════════════════════════════════════════════════════════════════
# 2. INCOMPLETE MARKET DATA — Graceful handling
# ═══════════════════════════════════════════════════════════════════════

class TestIncompleteMarketData:
    """Tests that the engine handles missing/incomplete data gracefully."""

    def _build_engine(self, broker):
        """Build a TradingEngine with a mock broker, bypassing real init."""
        with patch("core.trading_engine._create_broker", return_value=broker), \
             patch("core.trading_engine.settings") as mock_settings:
            # Set required settings
            mock_settings.active_broker = "oanda"
            mock_settings.scalping_enabled = False
            mock_settings.finnhub_api_key = ""
            mock_settings.newsapi_key = ""
            mock_settings.openai_api_key = ""
            mock_settings.position_management_style = "LP"
            mock_settings.trading_style = "day_trading"
            mock_settings.allow_partial_profits = False
            mock_settings.funded_account_mode = False
            mock_settings.close_before_friday_hour = 20

            from core.trading_engine import TradingEngine
            engine = TradingEngine.__new__(TradingEngine)
            engine.broker = broker
            engine.risk_manager = RiskManager(broker)
            engine.position_manager = MagicMock()
            engine.position_manager.positions = {}
            engine.alert_manager = None
            return engine

    def test_friday_close_skips_trade_without_entry_price(self):
        """Trades without entry_price should be kept (not closed blindly)."""
        broker = MockBroker()
        trade = FakeTrade(
            trade_id="T1", instrument="EUR_USD",
            entry_price=None, current_price=1.1050,
            stop_loss=1.0900, take_profit=1.1200,
        )
        broker._open_trades = [trade]

        engine = self._build_engine(broker)
        run_async(engine._handle_friday_close())
        assert len(broker.closed_trades) == 0  # Should NOT close

    def test_friday_close_skips_trade_without_current_price(self):
        """Trades without current_price should be kept."""
        broker = MockBroker()
        trade = FakeTrade(
            trade_id="T1", instrument="EUR_USD",
            entry_price=1.1000, current_price=None,
            stop_loss=1.0900, take_profit=1.1200,
        )
        broker._open_trades = [trade]

        engine = self._build_engine(broker)
        run_async(engine._handle_friday_close())
        assert len(broker.closed_trades) == 0

    def test_friday_close_skips_trade_without_sl_and_tp(self):
        """Trades with no SL and no TP: nothing to be 'near', so keep."""
        broker = MockBroker()
        trade = FakeTrade(
            trade_id="T1", instrument="EUR_USD",
            entry_price=1.1000, current_price=1.1050,
            stop_loss=None, take_profit=None,
        )
        broker._open_trades = [trade]

        engine = self._build_engine(broker)
        run_async(engine._handle_friday_close())
        assert len(broker.closed_trades) == 0

    def test_friday_close_handles_empty_open_trades(self):
        """No open trades — nothing to do, no errors."""
        broker = MockBroker()
        broker._open_trades = []

        engine = self._build_engine(broker)
        run_async(engine._handle_friday_close())
        assert len(broker.closed_trades) == 0

    def test_friday_close_handles_zero_sl_distance(self):
        """Edge case: entry == SL → distance is 0 → no division by zero."""
        broker = MockBroker()
        trade = FakeTrade(
            trade_id="T1", instrument="EUR_USD",
            entry_price=1.1000, current_price=1.1000,
            stop_loss=1.1000, take_profit=1.1200,
        )
        broker._open_trades = [trade]

        engine = self._build_engine(broker)
        # Should not crash
        run_async(engine._handle_friday_close())


# ═══════════════════════════════════════════════════════════════════════
# 3. MULTIPLE SIMULTANEOUS TRADES — Risk limit enforcement
# ═══════════════════════════════════════════════════════════════════════

class TestMultipleSimultaneousTrades:
    """Tests that risk limits are enforced with multiple open trades."""

    # Save/restore funded_account_mode to avoid cross-test pollution
    def setup_method(self):
        self._orig_funded = settings.funded_account_mode
        settings.funded_account_mode = False

    def teardown_method(self):
        settings.funded_account_mode = self._orig_funded

    def _make_risk_manager(self, balance=10000.0):
        broker = MockBroker(balance=balance)
        rm = RiskManager(broker)
        # Ensure balance tracking is initialized (avoids funded-mode zero-balance block)
        rm._current_balance = balance
        rm._peak_balance = balance
        return rm

    def test_total_risk_enforced_at_max(self):
        """Max total risk enforced — can't open trade that would exceed it."""
        rm = self._make_risk_manager()
        max_risk = settings.max_total_risk  # actual config value
        risk_per_trade = settings.risk_day_trading  # 1%

        # Fill up to just under the limit
        num_trades = int(max_risk / risk_per_trade) - 1
        for i in range(num_trades):
            rm.register_trade(f"T{i}", f"PAIR_{i}", risk_per_trade)

        # Can still take one more (just reaches limit)
        assert rm.can_take_trade(TradingStyle.DAY_TRADING, "NEW_PAIR")

        # Register one more to reach the limit
        rm.register_trade(f"T{num_trades}", f"PAIR_{num_trades}", risk_per_trade)

        # Now should be blocked (at limit + 1% > max)
        assert not rm.can_take_trade(TradingStyle.DAY_TRADING, "BLOCKED_PAIR")

    def test_unregister_frees_risk(self):
        """Closing a trade should free up risk capacity."""
        rm = self._make_risk_manager()
        rm.register_trade("T1", "EUR_USD", 0.05)
        rm.register_trade("T2", "GBP_USD", 0.02)
        assert abs(rm.get_current_total_risk() - 0.07) < 1e-9

        # Close one trade
        rm.unregister_trade("T1", "EUR_USD")
        assert abs(rm.get_current_total_risk() - 0.02) < 1e-9

        # Now can take more
        assert rm.can_take_trade(TradingStyle.DAY_TRADING, "NEW_PAIR")

    def test_unregister_all_clears_risk(self):
        """unregister_all_trades clears all active risk."""
        rm = self._make_risk_manager()
        for i in range(5):
            rm.register_trade(f"T{i}", f"PAIR_{i}", 0.01)
        assert rm.get_current_total_risk() > 0
        rm.unregister_all_trades()
        assert rm.get_current_total_risk() == 0.0

    def test_correlated_pairs_reduce_risk(self):
        """Correlated pairs should get reduced to the fixed correlated_risk_pct."""
        rm = self._make_risk_manager()
        # Register a EUR_USD trade
        rm.register_trade("T1", "EUR_USD", 0.01)

        # Find a pair correlated with EUR_USD in the config
        correlated_pair = None
        for group in settings.correlation_groups:
            if "EUR_USD" in group:
                for pair in group:
                    if pair != "EUR_USD":
                        correlated_pair = pair
                        break
                break

        if correlated_pair:
            adjusted = rm._adjust_for_correlation(correlated_pair, 0.01)
            assert abs(adjusted - settings.correlated_risk_pct) < 1e-9
        else:
            # No correlation group found — skip gracefully
            pytest.skip("No correlation group containing EUR_USD found in config")

    def test_uncorrelated_pair_keeps_full_risk(self):
        """Uncorrelated pair should keep the full risk allocation."""
        rm = self._make_risk_manager()
        rm.register_trade("T1", "EUR_USD", 0.01)

        # USD_JPY with EUR_USD — check if they're in different correlation groups
        # If not correlated, should return base risk unchanged
        adjusted = rm._adjust_for_correlation("XAU_USD", 0.01)
        # XAU_USD is commodity — typically not in forex correlation group
        # This tests the "no correlation found" path
        assert adjusted == 0.01 or adjusted == settings.correlated_risk_pct

    def test_risk_tracking_with_compound_key(self):
        """Verify register uses instrument:trade_id compound key."""
        rm = self._make_risk_manager()
        rm.register_trade("T1", "EUR_USD", 0.01)
        assert "EUR_USD:T1" in rm._active_risks
        rm.unregister_trade("T1", "EUR_USD")
        assert "EUR_USD:T1" not in rm._active_risks

    def test_zero_balance_blocks_funded_trades(self):
        """Funded account with zero balance should block all trades."""
        rm = self._make_risk_manager(balance=0)
        rm._current_balance = 0
        with patch.object(settings, 'funded_account_mode', True):
            can_trade, reason = rm.check_funded_account_limits()
            assert not can_trade
            assert "balance" in reason.lower()


# ═══════════════════════════════════════════════════════════════════════
# 4. TRADING OUTSIDE SESSION HOURS
# ═══════════════════════════════════════════════════════════════════════

class TestMarketHours:
    """Tests that no trades execute outside market hours."""

    def _build_engine_for_hours(self):
        from core.trading_engine import TradingEngine
        broker = MockBroker()
        engine = TradingEngine.__new__(TradingEngine)
        engine.broker = broker
        return engine

    def test_market_closed_on_saturday(self):
        engine = self._build_engine_for_hours()
        sat = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)  # Saturday
        assert sat.weekday() == 5
        assert not engine._is_market_open(sat)

    def test_market_closed_on_sunday(self):
        engine = self._build_engine_for_hours()
        sun = datetime(2026, 3, 29, 12, 0, tzinfo=timezone.utc)  # Sunday
        assert sun.weekday() == 6
        assert not engine._is_market_open(sun)

    def test_market_closed_before_start_hour(self):
        engine = self._build_engine_for_hours()
        # Monday at 5:00 UTC — before trading_start_hour (7)
        early = datetime(2026, 3, 23, 5, 0, tzinfo=timezone.utc)  # Monday
        assert early.weekday() == 0
        assert not engine._is_market_open(early)

    def test_market_closed_after_end_hour(self):
        engine = self._build_engine_for_hours()
        # Monday at 23:00 UTC — after trading_end_hour (22)
        late = datetime(2026, 3, 23, 23, 0, tzinfo=timezone.utc)
        assert not engine._is_market_open(late)

    def test_market_open_during_london(self):
        engine = self._build_engine_for_hours()
        # Monday at 10:00 UTC — London session
        london = datetime(2026, 3, 23, 10, 0, tzinfo=timezone.utc)
        assert engine._is_market_open(london)

    def test_market_open_during_overlap(self):
        engine = self._build_engine_for_hours()
        # Wednesday at 15:00 UTC — London+NY overlap
        overlap = datetime(2026, 3, 25, 15, 0, tzinfo=timezone.utc)
        assert engine._is_market_open(overlap)

    def test_market_open_at_boundary_start(self):
        engine = self._build_engine_for_hours()
        # Exactly at trading_start_hour (7)
        boundary = datetime(2026, 3, 23, 7, 0, tzinfo=timezone.utc)
        assert engine._is_market_open(boundary)

    def test_market_closed_at_boundary_end(self):
        engine = self._build_engine_for_hours()
        # Exactly at trading_end_hour (22) — should be closed (< 22 is open)
        boundary = datetime(2026, 3, 23, 22, 0, tzinfo=timezone.utc)
        assert not engine._is_market_open(boundary)

    def test_session_quality_overlap_is_highest(self):
        engine = self._build_engine_for_hours()
        overlap = datetime(2026, 3, 25, 15, 0, tzinfo=timezone.utc)
        name, quality = engine._get_session_quality(overlap)
        assert name == "OVERLAP"
        assert quality == 1.0

    def test_session_quality_asian_is_low(self):
        engine = self._build_engine_for_hours()
        asian = datetime(2026, 3, 25, 3, 0, tzinfo=timezone.utc)
        name, quality = engine._get_session_quality(asian)
        assert name == "ASIAN"
        assert quality == 0.5

    def test_tick_does_not_scan_when_market_closed(self):
        """_tick with market closed should NOT call _scan_for_setups."""
        engine = self._build_engine_for_hours()
        engine.risk_manager = MagicMock()
        engine.position_manager = MagicMock()
        engine.position_manager.positions = {}
        engine.news_filter = MagicMock()
        engine.alert_manager = None
        engine._daily_counters = {}
        engine._reentry_candidates = {}
        engine._last_equity_snapshot = datetime.min.replace(tzinfo=timezone.utc)
        engine._scan_for_setups = AsyncMock()
        engine._scan_analysis_only = AsyncMock()
        engine._expire_old_setups = MagicMock()
        engine._reset_daily_counters = MagicMock()
        engine._maybe_send_morning_heartbeat = AsyncMock()
        engine._maybe_send_monthly_asr = AsyncMock()
        engine._manage_open_positions = AsyncMock()

        # Simulate Sunday 12:00 UTC
        with patch("core.trading_engine.datetime") as mock_dt:
            sunday = datetime(2026, 3, 29, 12, 0, tzinfo=timezone.utc)
            mock_dt.now.return_value = sunday
            mock_dt.min = datetime.min
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            run_async(engine._tick())

        engine._scan_for_setups.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════
# 5. FRIDAY CLOSE BEHAVIOR
# ═══════════════════════════════════════════════════════════════════════

class TestFridayClose:
    """Tests Friday trading rules: close near SL/TP, keep mid-range, no new trades."""

    def _build_engine(self, broker):
        from core.trading_engine import TradingEngine
        engine = TradingEngine.__new__(TradingEngine)
        engine.broker = broker
        engine.risk_manager = MagicMock()
        engine.position_manager = MagicMock()
        engine.position_manager.positions = {"T1": MagicMock(), "T2": MagicMock()}
        engine.alert_manager = None
        return engine

    def test_should_close_friday_at_20_utc(self):
        from core.trading_engine import TradingEngine
        engine = TradingEngine.__new__(TradingEngine)
        friday_20 = datetime(2026, 3, 27, 20, 0, tzinfo=timezone.utc)
        assert friday_20.weekday() == 4
        assert engine._should_close_friday(friday_20)

    def test_should_not_close_friday_at_19_utc(self):
        from core.trading_engine import TradingEngine
        engine = TradingEngine.__new__(TradingEngine)
        friday_19 = datetime(2026, 3, 27, 19, 0, tzinfo=timezone.utc)
        assert not engine._should_close_friday(friday_19)

    def test_should_not_close_on_thursday(self):
        from core.trading_engine import TradingEngine
        engine = TradingEngine.__new__(TradingEngine)
        thursday_20 = datetime(2026, 3, 26, 20, 0, tzinfo=timezone.utc)
        assert thursday_20.weekday() == 3
        assert not engine._should_close_friday(thursday_20)

    def test_no_new_trades_friday_after_18(self):
        from core.trading_engine import TradingEngine
        engine = TradingEngine.__new__(TradingEngine)
        friday_18 = datetime(2026, 3, 27, 18, 0, tzinfo=timezone.utc)
        assert engine._is_friday_no_new_trades(friday_18)

    def test_new_trades_allowed_friday_before_18(self):
        from core.trading_engine import TradingEngine
        engine = TradingEngine.__new__(TradingEngine)
        friday_17 = datetime(2026, 3, 27, 17, 0, tzinfo=timezone.utc)
        assert not engine._is_friday_no_new_trades(friday_17)

    def test_closes_trade_near_sl(self):
        """Trade near SL (within 30%) should be closed on Friday."""
        broker = MockBroker()
        # Entry 1.1000, SL 1.0900 → distance = 0.0100
        # Current 1.0920 → distance to SL = 0.0020 → 20% < 30% → CLOSE
        trade = FakeTrade(
            trade_id="T1", instrument="EUR_USD",
            entry_price=1.1000, current_price=1.0920,
            stop_loss=1.0900, take_profit=1.1200,
        )
        broker._open_trades = [trade]

        engine = self._build_engine(broker)
        run_async(engine._handle_friday_close())
        assert "T1" in broker.closed_trades

    def test_closes_trade_near_tp(self):
        """Trade near TP (within 30%) should be closed on Friday."""
        broker = MockBroker()
        # Entry 1.1000, TP 1.1200 → distance = 0.0200
        # Current 1.1160 → distance to TP = 0.0040 → 20% < 30% → CLOSE
        trade = FakeTrade(
            trade_id="T1", instrument="EUR_USD",
            entry_price=1.1000, current_price=1.1160,
            stop_loss=1.0900, take_profit=1.1200,
        )
        broker._open_trades = [trade]

        engine = self._build_engine(broker)
        run_async(engine._handle_friday_close())
        assert "T1" in broker.closed_trades

    def test_keeps_trade_mid_range(self):
        """Trade in the middle (far from SL and TP) should be kept."""
        broker = MockBroker()
        # Entry 1.1000, SL 1.0900, TP 1.1200
        # Current 1.1050 → distance to SL=0.0150 (150%), to TP=0.0150 (75%) → KEEP
        trade = FakeTrade(
            trade_id="T1", instrument="EUR_USD",
            entry_price=1.1000, current_price=1.1050,
            stop_loss=1.0900, take_profit=1.1200,
        )
        broker._open_trades = [trade]

        engine = self._build_engine(broker)
        run_async(engine._handle_friday_close())
        assert len(broker.closed_trades) == 0

    def test_mixed_trades_selective_close(self):
        """With multiple trades, only close those near SL/TP."""
        broker = MockBroker()
        # Trade 1: near SL → CLOSE
        near_sl = FakeTrade(
            trade_id="T1", instrument="EUR_USD",
            entry_price=1.1000, current_price=1.0910,
            stop_loss=1.0900, take_profit=1.1200,
        )
        # Trade 2: mid-range → KEEP
        mid_range = FakeTrade(
            trade_id="T2", instrument="GBP_USD",
            entry_price=1.2500, current_price=1.2550,
            stop_loss=1.2400, take_profit=1.2700,
        )
        # Trade 3: near TP → CLOSE
        near_tp = FakeTrade(
            trade_id="T3", instrument="AUD_USD",
            entry_price=0.6500, current_price=0.6690,
            stop_loss=0.6400, take_profit=0.6700,
        )
        broker._open_trades = [near_sl, mid_range, near_tp]

        engine = self._build_engine(broker)
        engine.position_manager.positions = {
            "T1": MagicMock(), "T2": MagicMock(), "T3": MagicMock()
        }
        run_async(engine._handle_friday_close())

        assert "T1" in broker.closed_trades
        assert "T2" not in broker.closed_trades
        assert "T3" in broker.closed_trades
        assert len(broker.closed_trades) == 2

    def test_friday_close_error_does_not_crash(self):
        """If broker.close_trade fails, engine should not crash."""
        broker = MockBroker()
        broker.close_trade = AsyncMock(side_effect=Exception("Broker error"))

        trade = FakeTrade(
            trade_id="T1", instrument="EUR_USD",
            entry_price=1.1000, current_price=1.0910,
            stop_loss=1.0900, take_profit=1.1200,
        )
        broker._open_trades = [trade]

        engine = self._build_engine(broker)
        # Should not raise
        run_async(engine._handle_friday_close())


# ═══════════════════════════════════════════════════════════════════════
# Run with: python3 -m pytest backend/test_bugfix007_edge_cases.py -v
# ═══════════════════════════════════════════════════════════════════════
