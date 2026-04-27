"""
Tests for trading_engine.py — covering critical methods that were untested.
Focus: session quality, market hours, Friday rules, SL/TP calculation,
       setup expiry, notifications, daily counters, scalping DD limits,
       mode switching, strategy config, presession checklist.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, AsyncMock
from dataclasses import dataclass

# We must patch _create_broker before importing TradingEngine
# because __init__ calls it immediately.


@pytest.fixture
def engine():
    """Create a TradingEngine with all heavy deps mocked out."""
    with patch("core.trading_engine._create_broker") as mock_broker_fn, \
         patch("core.trading_engine.RiskManager"), \
         patch("core.trading_engine.PositionManager"), \
         patch("core.trading_engine.MarketAnalyzer"), \
         patch("core.trading_engine.ExplanationEngine"), \
         patch("core.trading_engine.NewsFilter"), \
         patch("core.trading_engine._ALERTS_AVAILABLE", False), \
         patch("core.trading_engine._AI_AVAILABLE", False), \
         patch("core.trading_engine._SCREENSHOTS_AVAILABLE", False), \
         patch("core.trading_engine._MONTHLY_REVIEW_AVAILABLE", False), \
         patch("core.trading_engine._SCALPING_AVAILABLE", False), \
         patch("core.trading_engine.settings") as mock_settings:

        # Minimal settings
        mock_settings.active_broker = "capital"
        mock_settings.capital_api_key = "test"
        mock_settings.capital_password = "test"
        mock_settings.capital_identifier = "test"
        mock_settings.capital_environment = "demo"
        mock_settings.capital_account_id = None
        mock_settings.position_management_style = "ema_trailing"
        mock_settings.trading_style = "day_trading"
        mock_settings.allow_partial_profits = True
        mock_settings.scalping_enabled = False
        mock_settings.max_reentries_per_setup = 3
        mock_settings.trading_start_hour = 7
        mock_settings.trading_end_hour = 21
        mock_settings.close_before_friday_hour = 20
        mock_settings.no_new_trades_friday_hour = 18
        mock_settings.active_watchlist_categories = ["forex_majors"]
        mock_settings.avoid_news_minutes_before = 30
        mock_settings.avoid_news_minutes_after = 30
        mock_settings.avoid_news_minutes_before_scalping = 60
        mock_settings.avoid_news_minutes_after_scalping = 60
        mock_settings.avoid_news_minutes_before_swing = 15
        mock_settings.avoid_news_minutes_after_swing = 5
        mock_settings.max_trades_per_day = 3
        mock_settings.max_trades_per_day_scalping = 10
        mock_settings.cooldown_minutes = 120
        mock_settings.cooldown_minutes_scalping = 30
        mock_settings.scalping_max_daily_dd = 0.05
        mock_settings.scalping_max_total_dd = 0.10

        mock_broker = MagicMock()
        mock_broker_fn.return_value = mock_broker

        from core.trading_engine import TradingEngine
        eng = TradingEngine()
        eng._settings = mock_settings  # Keep ref for tests that modify settings
        yield eng


# ──────────────────────────────────────────────────────────────────
# _dst_offset
# ──────────────────────────────────────────────────────────────────

class TestDSTOffset:
    def test_summer_edt_returns_0(self, engine):
        """During EDT (summer), offset should be 0."""
        # July 15 2025, UTC — EDT is active
        summer = datetime(2025, 7, 15, 14, 0, tzinfo=timezone.utc)
        assert engine._dst_offset(summer) == 0

    def test_winter_est_returns_1(self, engine):
        """During EST (winter), offset should be 1."""
        # January 15 2025, UTC — EST is active
        winter = datetime(2025, 1, 15, 14, 0, tzinfo=timezone.utc)
        assert engine._dst_offset(winter) == 1

    def test_naive_datetime_fallback(self, engine):
        """Naive datetime should not crash — falls back to 0."""
        naive = datetime(2025, 1, 15, 14, 0)
        # Should still work (astimezone works on naive datetime in Python 3.6+)
        result = engine._dst_offset(naive)
        assert result in (0, 1)  # Accept either — depends on system TZ


# ──────────────────────────────────────────────────────────────────
# _get_session_quality
# ──────────────────────────────────────────────────────────────────

class TestSessionQuality:
    def test_overlap_session(self, engine):
        """12-16 UTC in EDT should be OVERLAP with score 1.0."""
        now = datetime(2025, 7, 15, 13, 0, tzinfo=timezone.utc)
        name, score = engine._get_session_quality(now)
        assert name == "OVERLAP"
        assert score == 1.0

    def test_london_session(self, engine):
        """07-12 UTC in EDT should be LONDON with score 0.9."""
        now = datetime(2025, 7, 15, 9, 0, tzinfo=timezone.utc)
        name, score = engine._get_session_quality(now)
        assert name == "LONDON"
        assert score == 0.9

    def test_new_york_session(self, engine):
        """16-21 UTC in EDT should be NEW_YORK with score 0.8."""
        now = datetime(2025, 7, 15, 18, 0, tzinfo=timezone.utc)
        name, score = engine._get_session_quality(now)
        assert name == "NEW_YORK"
        assert score == 0.8

    def test_asian_session_forex(self, engine):
        """Early UTC hours should be ASIAN with score 0.5 for forex."""
        now = datetime(2025, 7, 15, 3, 0, tzinfo=timezone.utc)
        name, score = engine._get_session_quality(now, instrument="EUR_USD")
        assert name == "ASIAN"
        assert score == 0.5

    def test_asian_session_crypto_higher_score(self, engine):
        """Crypto should get 0.7 during Asian session."""
        now = datetime(2025, 7, 15, 3, 0, tzinfo=timezone.utc)
        with patch("strategies.base._is_crypto_instrument", return_value=True):
            name, score = engine._get_session_quality(now, instrument="BTC_USD")
        assert name == "ASIAN"
        assert score == 0.7

    def test_sydney_session(self, engine):
        """Late UTC (21+) in EDT should be SYDNEY with score 0.4."""
        now = datetime(2025, 7, 15, 22, 0, tzinfo=timezone.utc)
        name, score = engine._get_session_quality(now)
        assert name == "SYDNEY"
        assert score == 0.4


# ──────────────────────────────────────────────────────────────────
# _is_market_open
# ──────────────────────────────────────────────────────────────────

class TestIsMarketOpen:
    def test_weekday_during_session(self, engine):
        """Tuesday 14:00 UTC should be open (within 7-21 EDT range)."""
        now = datetime(2025, 7, 15, 14, 0, tzinfo=timezone.utc)  # Tuesday
        assert engine._is_market_open(now) is True

    def test_weekday_outside_session(self, engine):
        """Tuesday 05:00 UTC should be closed (before 7 UTC)."""
        now = datetime(2025, 7, 15, 5, 0, tzinfo=timezone.utc)  # Tuesday
        assert engine._is_market_open(now) is False

    def test_weekend_closed_for_forex(self, engine):
        """Saturday should be closed for forex-only watchlist."""
        now = datetime(2025, 7, 19, 14, 0, tzinfo=timezone.utc)  # Saturday
        assert engine._is_market_open(now) is False

    def test_weekend_closed_even_with_crypto_default(self, engine):
        """AUTO trading remains session-bound on weekends even with crypto enabled."""
        now = datetime(2025, 7, 19, 14, 0, tzinfo=timezone.utc)  # Saturday
        with patch("core.trading_engine.settings") as ms:
            ms.active_watchlist_categories = ["crypto"]
            ms.trading_start_hour = 7
            ms.trading_end_hour = 21
            assert engine._is_market_open(now) is False


# ──────────────────────────────────────────────────────────────────
# _should_close_friday / _is_friday_no_new_trades
# ──────────────────────────────────────────────────────────────────

class TestFridayRules:
    def test_should_close_friday_true(self, engine):
        """Friday 20:00 UTC (EDT) should trigger close."""
        friday = datetime(2025, 7, 18, 20, 0, tzinfo=timezone.utc)
        assert engine._should_close_friday(friday) is True

    def test_should_close_friday_false_early(self, engine):
        """Friday 15:00 UTC should NOT trigger close."""
        friday = datetime(2025, 7, 18, 15, 0, tzinfo=timezone.utc)
        assert engine._should_close_friday(friday) is False

    def test_should_close_not_friday(self, engine):
        """Wednesday at 20:00 should NOT trigger close."""
        wednesday = datetime(2025, 7, 16, 20, 0, tzinfo=timezone.utc)
        assert engine._should_close_friday(wednesday) is False

    def test_no_new_trades_friday_true(self, engine):
        """Friday 18:00 UTC (EDT) should block new trades."""
        friday = datetime(2025, 7, 18, 18, 0, tzinfo=timezone.utc)
        assert engine._is_friday_no_new_trades(friday) is True

    def test_no_new_trades_friday_false(self, engine):
        """Friday 10:00 UTC should allow new trades."""
        friday = datetime(2025, 7, 18, 10, 0, tzinfo=timezone.utc)
        assert engine._is_friday_no_new_trades(friday) is False


class TestScalpingScan:
    @pytest.mark.asyncio
    async def test_skip_blocklisted_instruments(self, engine):
        """Scalping scan should not fetch candles for blocklisted instruments."""
        engine.broker.is_blocklisted.side_effect = lambda inst: inst == "BAD_USD"
        engine.position_manager.positions = {}
        engine.risk_manager.can_take_trade.return_value = True
        engine.scalping_analyzer = MagicMock()
        engine.scalping_analyzer.analyze_scalping = AsyncMock()
        engine.scalping_analyzer.detect_scalping_setup.return_value = None
        engine._last_scan_results = {"EUR_USD": MagicMock()}
        engine._check_scalping_dd_limits = MagicMock(return_value=True)

        with patch("core.trading_engine.get_active_watchlist", return_value=["BAD_USD", "EUR_USD"]), \
             patch("core.trading_engine.asyncio.sleep", new=AsyncMock()):
            await engine._scan_scalping_setups()

        engine.scalping_analyzer.analyze_scalping.assert_awaited_once_with("EUR_USD")


# ──────────────────────────────────────────────────────────────────
# _calculate_sl_tp
# ──────────────────────────────────────────────────────────────────

class TestCalculateSLTP:
    def _make_analysis(self, supports, resistances):
        a = MagicMock()
        a.key_levels = {"supports": supports, "resistances": resistances}
        return a

    def test_buy_sl_tp(self, engine):
        """BUY: SL at nearest support below, TP at nearest resistance above."""
        analysis = self._make_analysis(
            supports=[1.0900, 1.0950],
            resistances=[1.1050, 1.1100]
        )
        sl, tp = engine._calculate_sl_tp(analysis, "BUY", entry_price=1.1000)
        assert sl == 1.0950  # max support below entry
        assert tp == 1.1050  # min resistance above entry

    def test_sell_sl_tp(self, engine):
        """SELL: SL at nearest resistance above, TP at nearest support below."""
        analysis = self._make_analysis(
            supports=[1.0900, 1.0950],
            resistances=[1.1050, 1.1100]
        )
        sl, tp = engine._calculate_sl_tp(analysis, "SELL", entry_price=1.1000)
        assert sl == 1.1050  # min resistance above entry
        assert tp == 1.0950  # max support below entry

    def test_buy_no_support_returns_none(self, engine):
        """BUY with no supports below entry should return None, None."""
        analysis = self._make_analysis(supports=[1.1100], resistances=[1.1200])
        sl, tp = engine._calculate_sl_tp(analysis, "BUY", entry_price=1.1000)
        assert sl is None
        assert tp is None

    def test_sell_no_resistance_returns_none(self, engine):
        """SELL with no resistances above entry should return None, None."""
        analysis = self._make_analysis(supports=[1.0900], resistances=[1.0800])
        sl, tp = engine._calculate_sl_tp(analysis, "SELL", entry_price=1.1000)
        assert sl is None
        assert tp is None

    def test_buy_no_resistance_above_returns_none(self, engine):
        """BUY with support below but no resistance above should return None."""
        analysis = self._make_analysis(supports=[1.0950], resistances=[1.0980])
        sl, tp = engine._calculate_sl_tp(analysis, "BUY", entry_price=1.1000)
        assert sl is None
        assert tp is None


# ──────────────────────────────────────────────────────────────────
# _expire_old_setups
# ──────────────────────────────────────────────────────────────────

class TestExpireOldSetups:
    def _make_pending_setup(self, status="pending", expires_at=None):
        from core.trading_engine import PendingSetup
        return PendingSetup(
            id="test-1",
            timestamp=datetime.now(timezone.utc).isoformat(),
            instrument="EUR_USD",
            strategy="BLUE",
            direction="BUY",
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100,
            units=1000,
            confidence=75.0,
            risk_reward_ratio=2.0,
            reasoning="Test setup",
            status=status,
            expires_at=expires_at or "",
        )

    def test_pending_setup_expired(self, engine):
        """Pending setup past expiry should be marked expired."""
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        setup = self._make_pending_setup(expires_at=past)
        engine.pending_setups = [setup]
        engine._expire_old_setups()
        assert setup.status == "expired"

    def test_pending_setup_not_expired(self, engine):
        """Pending setup before expiry should remain pending."""
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        setup = self._make_pending_setup(expires_at=future)
        engine.pending_setups = [setup]
        engine._expire_old_setups()
        assert setup.status == "pending"

    def test_non_pending_not_touched(self, engine):
        """Already approved setup should not be re-expired."""
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        setup = self._make_pending_setup(status="approved", expires_at=past)
        engine.pending_setups = [setup]
        engine._expire_old_setups()
        assert setup.status == "approved"

    def test_prune_keeps_max_20_finished(self, engine):
        """Should keep all pending + only last 20 non-pending setups."""
        setups = []
        for i in range(30):
            s = self._make_pending_setup(status="approved")
            s.id = f"setup-{i}"
            setups.append(s)
        # Add one pending
        pending = self._make_pending_setup(status="pending")
        pending.id = "pending-1"
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        pending.expires_at = future
        setups.append(pending)

        engine.pending_setups = setups
        engine._expire_old_setups()
        # Should have 1 pending + 20 finished = 21
        assert len(engine.pending_setups) == 21
        pending_count = sum(1 for s in engine.pending_setups if s.status == "pending")
        assert pending_count == 1

    def test_unparseable_expiry_forces_expiry(self, engine):
        """Setup with unparseable expires_at should be force-expired."""
        setup = self._make_pending_setup(expires_at="not-a-date")
        engine.pending_setups = [setup]
        engine._expire_old_setups()
        assert setup.status == "expired"


# ──────────────────────────────────────────────────────────────────
# Notifications
# ──────────────────────────────────────────────────────────────────

class TestNotifications:
    def test_push_and_get_unread(self, engine):
        """Push a notification and retrieve it as unread."""
        # Engine now loads prior notifications from disk at init (persistence
        # added 2026-04-23). Reset for isolated unit test.
        engine._notifications = []
        engine._push_notification("ALERT", "Test Title", "Test Body", {"key": "val"})
        unread = engine.get_unread_notifications()
        assert len(unread) == 1
        assert unread[0]["title"] == "Test Title"
        assert unread[0]["type"] == "ALERT"
        assert unread[0]["data"] == {"key": "val"}

    def test_unread_marked_as_read(self, engine):
        """After get_unread_notifications, calling again returns empty."""
        engine._notifications = []
        engine._push_notification("INFO", "T", "B")
        engine.get_unread_notifications()
        second_call = engine.get_unread_notifications()
        assert len(second_call) == 0

    def test_notification_trimmed(self, engine):
        """Notifications exceeding max should be trimmed."""
        engine._max_notifications = 5
        for i in range(10):
            engine._push_notification("INFO", f"N{i}", "body")
        assert len(engine._notifications) == 5
        # Should keep the latest 5
        assert engine._notifications[0]["title"] == "N5"


# ──────────────────────────────────────────────────────────────────
# _reset_daily_counters
# ──────────────────────────────────────────────────────────────────

class TestResetDailyCounters:
    def test_resets_on_new_day(self, engine):
        """Counters should reset when date changes."""
        engine._daily_counter_date = "2025-01-01"
        engine._daily_scan_count = 50
        engine._daily_setups_found = 10
        engine._daily_errors = 3
        engine._consecutive_losses_today = 2
        engine._reset_daily_counters()
        assert engine._daily_scan_count == 0
        assert engine._daily_setups_found == 0
        assert engine._daily_errors == 0
        assert engine._consecutive_losses_today == 0

    def test_no_reset_same_day(self, engine):
        """Counters should NOT reset if same day."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        engine._daily_counter_date = today
        engine._daily_scan_count = 50
        engine._reset_daily_counters()
        assert engine._daily_scan_count == 50


# ──────────────────────────────────────────────────────────────────
# _check_scalping_dd_limits
# ──────────────────────────────────────────────────────────────────

class TestScalpingDDLimits:
    def test_within_limits_returns_true(self, engine):
        """When DD is within limits, should return True."""
        engine._scalping_daily_dd = 0.01
        engine._scalping_peak_balance = 10000
        engine.risk_manager._current_balance = 9800  # 2% DD
        with patch("core.trading_engine.settings") as ms:
            ms.scalping_max_daily_dd = 0.05
            ms.scalping_max_total_dd = 0.10
            result = engine._check_scalping_dd_limits()
        assert result is True

    def test_daily_dd_exceeded_returns_false(self, engine):
        """When daily DD > limit, should return False."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        engine._scalping_dd_date = today  # prevent reset
        engine._scalping_daily_dd = 0.06  # 6% > 5%
        engine._scalping_peak_balance = 10000
        engine.risk_manager._current_balance = 9400
        with patch("core.trading_engine.settings") as ms:
            ms.scalping_max_daily_dd = 0.05
            ms.scalping_max_total_dd = 0.10
            result = engine._check_scalping_dd_limits()
        assert result is False

    def test_total_dd_exceeded_returns_false(self, engine):
        """When total DD > limit, should return False."""
        engine._scalping_daily_dd = 0.01  # daily OK
        engine._scalping_peak_balance = 10000
        engine.risk_manager._current_balance = 8900  # 11% DD > 10%
        with patch("core.trading_engine.settings") as ms:
            ms.scalping_max_daily_dd = 0.05
            ms.scalping_max_total_dd = 0.10
            result = engine._check_scalping_dd_limits()
        assert result is False

    def test_daily_dd_reset_on_new_date(self, engine):
        """Daily DD should reset when date changes."""
        engine._scalping_dd_date = "2025-01-01"
        engine._scalping_daily_dd = 0.04
        engine._scalping_peak_balance = 10000
        engine.risk_manager._current_balance = 10000
        with patch("core.trading_engine.settings") as ms:
            ms.scalping_max_daily_dd = 0.05
            ms.scalping_max_total_dd = 0.10
            engine._check_scalping_dd_limits()
        assert engine._scalping_daily_dd == 0.0  # was reset


# ──────────────────────────────────────────────────────────────────
# Mode switching
# ──────────────────────────────────────────────────────────────────

class TestModeSwitching:
    def test_set_mode_string(self, engine):
        """set_mode should accept a string."""
        from core.trading_engine import TradingMode
        engine.set_mode("AUTO")
        assert engine.mode == TradingMode.AUTO

    def test_set_mode_enum(self, engine):
        """set_mode should accept an enum."""
        from core.trading_engine import TradingMode
        engine.set_mode(TradingMode.AUTO)
        assert engine.mode == TradingMode.AUTO

    def test_toggle_scalping_on(self, engine):
        """toggle_scalping(True) should set fast scan interval."""
        from core import trading_engine as te
        te.NewsFilter.reset_mock()
        with patch("core.trading_engine._SCALPING_AVAILABLE", True), \
             patch("core.trading_engine.ScalpingAnalyzer") as mock_sa, \
             patch("core.trading_engine.settings") as ms:
            ms.scalping_enabled = True
            ms.trading_style = "day_trading"
            ms.avoid_news_minutes_before_scalping = 60
            ms.avoid_news_minutes_after_scalping = 60
            ms.avoid_news_minutes_before = 30
            ms.avoid_news_minutes_after = 30
            ms.finnhub_api_key = ""
            ms.newsapi_key = ""
            engine.toggle_scalping(True)
        assert engine._scan_interval == engine._scalping_scan_interval
        _, kwargs = te.NewsFilter.call_args
        assert kwargs["minutes_before"] == 60
        assert kwargs["minutes_after"] == 60

    def test_toggle_scalping_off(self, engine):
        """toggle_scalping(False) should restore normal scan interval."""
        from core import trading_engine as te
        te.NewsFilter.reset_mock()
        with patch("core.trading_engine.settings") as ms:
            ms.scalping_enabled = False
            ms.trading_style = "day_trading"
            ms.avoid_news_minutes_before = 30
            ms.avoid_news_minutes_after = 30
            ms.finnhub_api_key = ""
            ms.newsapi_key = ""
            engine.toggle_scalping(False)
        assert engine._scan_interval == 120
        _, kwargs = te.NewsFilter.call_args
        assert kwargs["minutes_before"] == 30
        assert kwargs["minutes_after"] == 30

    def test_active_scalping_limits_override_day_trading_defaults(self, engine):
        with patch("core.trading_engine.settings") as ms:
            ms.scalping_enabled = True
            ms.max_trades_per_day = 3
            ms.max_trades_per_day_scalping = 10
            ms.cooldown_minutes = 120
            ms.cooldown_minutes_scalping = 30
            assert engine._active_max_trades_per_day() == 10
            assert engine._active_cooldown_minutes() == 30


# ──────────────────────────────────────────────────────────────────
# Strategy config
# ──────────────────────────────────────────────────────────────────

class TestStrategyConfig:
    def test_set_enabled_strategies_merges_defaults(self, engine):
        """set_enabled_strategies should merge with defaults (all keys present)."""
        engine._save_strategy_config = MagicMock()  # Don't write to disk
        engine.set_enabled_strategies({"BLUE": False, "PINK": True})
        result = engine._enabled_strategies
        assert result["BLUE"] is False
        assert result["PINK"] is True
        assert result["RED"] is True  # default

    def test_unknown_key_ignored(self, engine):
        """Unknown strategy keys should be ignored."""
        engine._save_strategy_config = MagicMock()
        engine.set_enabled_strategies({"NONEXISTENT": True})
        assert "NONEXISTENT" not in engine._enabled_strategies

    def test_get_enabled_strategies_returns_copy(self, engine):
        """get_enabled_strategies should return a copy, not the original."""
        result = engine.get_enabled_strategies()
        result["BLUE"] = False
        # Original should be unaffected
        assert engine._enabled_strategies["BLUE"] is True


# ──────────────────────────────────────────────────────────────────
# _build_presession_checklist
# ──────────────────────────────────────────────────────────────────

class TestPresessionChecklist:
    def test_contains_session_label(self, engine):
        """Checklist should include the session label."""
        result = engine._build_presession_checklist("London Open")
        assert "London Open" in result

    def test_contains_psychology_items(self, engine):
        """Checklist should include psychology manual items."""
        result = engine._build_presession_checklist("Test")
        assert "meditado" in result
        assert "emocional" in result
        assert "calendario económico" in result
        assert "respiraciones" in result
