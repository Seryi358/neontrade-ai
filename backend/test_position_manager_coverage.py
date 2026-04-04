"""
Tests for position_manager.py — covering critical methods.
Focus: EMA key resolution (forex vs crypto), EMA buffer, CPA trigger,
       _update_sl direction guard, track/remove position, update_all_positions
       price tracking, phase dispatch, _get_trail_ema lookup.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from core.position_manager import (
    PositionManager, ManagedPosition, PositionPhase, ManagementStyle, TradingStyle,
    _EMA_TIMEFRAME_GRID, _EMA_TIMEFRAME_GRID_CRYPTO,
)


@pytest.fixture
def pm():
    """Create a PositionManager with mocked broker."""
    broker = MagicMock()
    broker.modify_trade_sl = AsyncMock(return_value=True)
    broker.close_trade = AsyncMock(return_value=True)
    risk_manager = MagicMock()
    mgr = PositionManager(
        broker_client=broker,
        risk_manager=risk_manager,
        management_style="cp",
        trading_style="day_trading",
        allow_partial_profits=False,
    )
    return mgr


@pytest.fixture
def buy_pos():
    """Create a standard BUY position."""
    return ManagedPosition(
        trade_id="t1",
        instrument="EUR_USD",
        direction="BUY",
        entry_price=1.1000,
        original_sl=1.0950,
        current_sl=1.0950,
        take_profit_1=1.1100,
        units=1000,
        style="day_trading",
        highest_price=1.1000,
    )


@pytest.fixture
def sell_pos():
    """Create a standard SELL position."""
    return ManagedPosition(
        trade_id="t2",
        instrument="EUR_USD",
        direction="SELL",
        entry_price=1.1000,
        original_sl=1.1050,
        current_sl=1.1050,
        take_profit_1=1.0900,
        units=-1000,
        style="day_trading",
        lowest_price=1.1000,
    )


# ──────────────────────────────────────────────────────────────────
# EMA Timeframe Grid
# ──────────────────────────────────────────────────────────────────

class TestEMATimeframeGrid:
    def test_forex_lp_day_trading(self):
        """LP day trading forex should use H1 EMA 50."""
        key = _EMA_TIMEFRAME_GRID[(ManagementStyle.LP, TradingStyle.DAY_TRADING)]
        assert key == "EMA_H1_50"

    def test_forex_cp_scalping(self):
        """CP scalping forex should use M1 EMA 50."""
        key = _EMA_TIMEFRAME_GRID[(ManagementStyle.CP, TradingStyle.SCALPING)]
        assert key == "EMA_M1_50"

    def test_forex_cpa_day_trading(self):
        """CPA day trading should use M2 EMA 50."""
        key = _EMA_TIMEFRAME_GRID[(ManagementStyle.CPA, TradingStyle.DAY_TRADING)]
        assert key == "EMA_M2_50"

    def test_crypto_lp_swing(self):
        """LP swing crypto should use Weekly EMA 50 (wider than forex Daily)."""
        key = _EMA_TIMEFRAME_GRID_CRYPTO[(ManagementStyle.LP, TradingStyle.SWING)]
        assert key == "EMA_W_50"

    def test_crypto_cp_day_trading(self):
        """CP day trading crypto should use M15 (wider than forex M5)."""
        key = _EMA_TIMEFRAME_GRID_CRYPTO[(ManagementStyle.CP, TradingStyle.DAY_TRADING)]
        assert key == "EMA_M15_50"

    def test_crypto_cpa_same_as_forex(self):
        """CPA should be identical for crypto and forex."""
        for ts in TradingStyle:
            forex_key = _EMA_TIMEFRAME_GRID[(ManagementStyle.CPA, ts)]
            crypto_key = _EMA_TIMEFRAME_GRID_CRYPTO[(ManagementStyle.CPA, ts)]
            assert forex_key == crypto_key, f"CPA mismatch for {ts}: {forex_key} != {crypto_key}"


# ──────────────────────────────────────────────────────────────────
# _get_base_ema_key / _get_cpa_ema_key (forex vs crypto)
# ──────────────────────────────────────────────────────────────────

class TestEMAKeyResolution:
    def test_forex_instrument_uses_forex_grid(self, pm):
        """Forex instrument should use forex EMA keys."""
        with patch.object(pm, '_is_crypto', return_value=False):
            key = pm._get_base_ema_key("EUR_USD")
        assert key == pm._base_ema_key

    def test_crypto_instrument_uses_crypto_grid(self, pm):
        """Crypto instrument should use crypto-specific wider EMA keys."""
        with patch.object(pm, '_is_crypto', return_value=True):
            key = pm._get_base_ema_key("BTC_USD")
        assert key == pm._crypto_base_ema_key

    def test_cpa_key_forex(self, pm):
        """CPA key for forex."""
        with patch.object(pm, '_is_crypto', return_value=False):
            key = pm._get_cpa_ema_key("EUR_USD")
        assert key == pm._cpa_ema_key

    def test_cpa_key_crypto(self, pm):
        """CPA key for crypto."""
        with patch.object(pm, '_is_crypto', return_value=True):
            key = pm._get_cpa_ema_key("BTC_USD")
        assert key == pm._crypto_cpa_ema_key


# ──────────────────────────────────────────────────────────────────
# _ema_buffer
# ──────────────────────────────────────────────────────────────────

class TestEMABuffer:
    def test_normal_buffer_2pct(self, buy_pos):
        """Normal buffer should be 2% of trade range."""
        pm_inst = MagicMock()
        trade_range = abs(buy_pos.take_profit_1 - buy_pos.entry_price)  # 0.01
        expected = trade_range * 0.02  # 0.0002
        result = PositionManager._ema_buffer(pm_inst, buy_pos, aggressive=False)
        assert abs(result - expected) < 1e-9

    def test_aggressive_buffer_1pct(self, buy_pos):
        """Aggressive buffer should be 1% of trade range."""
        pm_inst = MagicMock()
        trade_range = abs(buy_pos.take_profit_1 - buy_pos.entry_price)  # 0.01
        expected = trade_range * 0.01  # 0.0001
        result = PositionManager._ema_buffer(pm_inst, buy_pos, aggressive=True)
        assert abs(result - expected) < 1e-9


# ──────────────────────────────────────────────────────────────────
# set_cpa_trigger
# ──────────────────────────────────────────────────────────────────

class TestCPATrigger:
    def test_trigger_from_be_phase(self, pm, buy_pos):
        """CPA trigger from BREAK_EVEN should switch to BEYOND_TP1."""
        buy_pos.phase = PositionPhase.BREAK_EVEN
        pm.positions["t1"] = buy_pos
        pm.set_cpa_trigger("t1", "friday_close")
        assert buy_pos.phase == PositionPhase.BEYOND_TP1
        assert buy_pos.pre_cpa_phase == "break_even"

    def test_trigger_from_trailing_phase(self, pm, buy_pos):
        """CPA trigger from TRAILING should switch to BEYOND_TP1."""
        buy_pos.phase = PositionPhase.TRAILING_TO_TP1
        pm.positions["t1"] = buy_pos
        pm.set_cpa_trigger("t1", "high_impact_news")
        assert buy_pos.phase == PositionPhase.BEYOND_TP1

    def test_trigger_ignored_initial_phase(self, pm, buy_pos):
        """CPA trigger from INITIAL should be ignored (too early)."""
        buy_pos.phase = PositionPhase.INITIAL
        pm.positions["t1"] = buy_pos
        pm.set_cpa_trigger("t1", "news")
        assert buy_pos.phase == PositionPhase.INITIAL

    def test_trigger_ignored_already_aggressive(self, pm, buy_pos):
        """CPA trigger from BEYOND_TP1 should be ignored (already aggressive)."""
        buy_pos.phase = PositionPhase.BEYOND_TP1
        pm.positions["t1"] = buy_pos
        pm.set_cpa_trigger("t1", "news")
        # Should stay the same, pre_cpa_phase should not be overwritten
        assert buy_pos.phase == PositionPhase.BEYOND_TP1

    def test_trigger_nonexistent_position(self, pm):
        """CPA trigger for unknown position should not crash."""
        pm.set_cpa_trigger("nonexistent", "test")  # Should not raise

    def test_temporary_cpa_sets_flags(self, pm, buy_pos):
        """Temporary CPA should set cpa_temporary and revert_level."""
        buy_pos.phase = PositionPhase.BREAK_EVEN
        pm.positions["t1"] = buy_pos
        pm.set_cpa_trigger("t1", "key_level", temporary=True, revert_level=1.1050)
        assert buy_pos.cpa_temporary is True
        assert buy_pos.cpa_revert_level == 1.1050


# ──────────────────────────────────────────────────────────────────
# set_ema_values / _get_trail_ema
# ──────────────────────────────────────────────────────────────────

class TestEMAValues:
    def test_set_and_get_ema(self, pm):
        """Should store and retrieve EMA values."""
        pm.set_ema_values("EUR_USD", {"EMA_M5_50": 1.0990, "EMA_H1_50": 1.0980})
        result = pm._get_trail_ema("EUR_USD", "EMA_M5_50")
        assert result == 1.0990

    def test_get_missing_ema_returns_none(self, pm):
        """Missing EMA key should return None."""
        pm.set_ema_values("EUR_USD", {"EMA_M5_50": 1.0990})
        result = pm._get_trail_ema("EUR_USD", "EMA_H4_50")
        assert result is None

    def test_get_unknown_instrument_returns_none(self, pm):
        """Unknown instrument should return None."""
        result = pm._get_trail_ema("UNKNOWN", "EMA_M5_50")
        assert result is None


# ──────────────────────────────────────────────────────────────────
# set_swing_values
# ──────────────────────────────────────────────────────────────────

class TestSwingValues:
    def test_set_swing_values(self, pm):
        """Should store swing highs and lows."""
        pm.set_swing_values("EUR_USD", [1.1020, 1.1050], [1.0950, 1.0920])
        assert pm._latest_swings["EUR_USD"]["highs"] == [1.1020, 1.1050]
        assert pm._latest_swings["EUR_USD"]["lows"] == [1.0950, 1.0920]


# ──────────────────────────────────────────────────────────────────
# track_position / remove_position
# ──────────────────────────────────────────────────────────────────

class TestTrackRemove:
    def test_track_position(self, pm, buy_pos):
        """track_position should add to positions dict."""
        pm.track_position(buy_pos)
        assert "t1" in pm.positions
        assert pm.positions["t1"].instrument == "EUR_USD"

    def test_remove_position(self, pm, buy_pos):
        """remove_position should delete from positions dict."""
        pm.positions["t1"] = buy_pos
        pm.remove_position("t1")
        assert "t1" not in pm.positions

    def test_remove_nonexistent_no_crash(self, pm):
        """remove_position for unknown ID should not crash."""
        pm.remove_position("nonexistent")  # Should not raise


# ──────────────────────────────────────────────────────────────────
# _update_sl — direction guard
# ──────────────────────────────────────────────────────────────────

class TestUpdateSL:
    @pytest.mark.asyncio
    async def test_buy_sl_moves_up(self, pm, buy_pos):
        """BUY: SL should move UP (favorable)."""
        buy_pos.current_sl = 1.0960
        result = await pm._update_sl(buy_pos, 1.0970)
        assert result is True
        assert buy_pos.current_sl == 1.0970

    @pytest.mark.asyncio
    async def test_buy_sl_blocked_down(self, pm, buy_pos):
        """BUY: SL should NOT move DOWN (unfavorable)."""
        buy_pos.current_sl = 1.0960
        result = await pm._update_sl(buy_pos, 1.0950)
        assert result is False
        assert buy_pos.current_sl == 1.0960  # unchanged

    @pytest.mark.asyncio
    async def test_sell_sl_moves_down(self, pm, sell_pos):
        """SELL: SL should move DOWN (favorable)."""
        sell_pos.current_sl = 1.1040
        result = await pm._update_sl(sell_pos, 1.1030)
        assert result is True
        assert sell_pos.current_sl == 1.1030

    @pytest.mark.asyncio
    async def test_sell_sl_blocked_up(self, pm, sell_pos):
        """SELL: SL should NOT move UP (unfavorable)."""
        sell_pos.current_sl = 1.1040
        result = await pm._update_sl(sell_pos, 1.1050)
        assert result is False
        assert sell_pos.current_sl == 1.1040  # unchanged

    @pytest.mark.asyncio
    async def test_broker_rejects_sl(self, pm, buy_pos):
        """Broker rejection should return False and keep old SL."""
        pm.broker.modify_trade_sl = AsyncMock(return_value=False)
        buy_pos.current_sl = 1.0960
        result = await pm._update_sl(buy_pos, 1.0970)
        assert result is False
        assert buy_pos.current_sl == 1.0960

    @pytest.mark.asyncio
    async def test_broker_exception_returns_false(self, pm, buy_pos):
        """Broker exception should return False gracefully."""
        pm.broker.modify_trade_sl = AsyncMock(side_effect=Exception("timeout"))
        buy_pos.current_sl = 1.0960
        result = await pm._update_sl(buy_pos, 1.0970)
        assert result is False


# ──────────────────────────────────────────────────────────────────
# update_all_positions — price tracking
# ──────────────────────────────────────────────────────────────────

class TestUpdateAllPositions:
    @pytest.mark.asyncio
    async def test_buy_highest_price_updated(self, pm, buy_pos):
        """BUY position should track highest_price."""
        pm.positions["t1"] = buy_pos
        buy_pos.highest_price = 1.1000

        price_mock = MagicMock()
        price_mock.bid = 1.1050
        price_mock.ask = 1.1052

        # Patch _manage_position to avoid phase logic
        with patch.object(pm, '_manage_position', new_callable=AsyncMock):
            await pm.update_all_positions({"EUR_USD": price_mock})

        assert buy_pos.highest_price == 1.1050

    @pytest.mark.asyncio
    async def test_sell_lowest_price_updated(self, pm, sell_pos):
        """SELL position should track lowest_price."""
        pm.positions["t2"] = sell_pos
        sell_pos.lowest_price = 1.1000

        price_mock = MagicMock()
        price_mock.bid = 1.0948
        price_mock.ask = 1.0950

        with patch.object(pm, '_manage_position', new_callable=AsyncMock):
            await pm.update_all_positions({"EUR_USD": price_mock})

        assert sell_pos.lowest_price == 1.0950  # ask for SELL

    @pytest.mark.asyncio
    async def test_missing_instrument_skipped(self, pm, buy_pos):
        """Position with missing price data should be skipped."""
        pm.positions["t1"] = buy_pos
        with patch.object(pm, '_manage_position', new_callable=AsyncMock) as mock_manage:
            await pm.update_all_positions({})  # No price data
        mock_manage.assert_not_called()


# ──────────────────────────────────────────────────────────────────
# _manage_position — phase dispatch
# ──────────────────────────────────────────────────────────────────

class TestPhaseDispatch:
    @pytest.mark.asyncio
    async def test_dispatches_initial(self, pm, buy_pos):
        """INITIAL phase should dispatch to _handle_initial_phase."""
        buy_pos.phase = PositionPhase.INITIAL
        with patch.object(pm, '_handle_initial_phase', new_callable=AsyncMock) as mock:
            await pm._manage_position(buy_pos, 1.1020)
        mock.assert_called_once_with(buy_pos, 1.1020)

    @pytest.mark.asyncio
    async def test_dispatches_sl_moved(self, pm, buy_pos):
        """SL_MOVED phase should dispatch to _handle_sl_moved_phase."""
        buy_pos.phase = PositionPhase.SL_MOVED
        with patch.object(pm, '_handle_sl_moved_phase', new_callable=AsyncMock) as mock:
            await pm._manage_position(buy_pos, 1.1020)
        mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatches_be(self, pm, buy_pos):
        """BREAK_EVEN should dispatch to _handle_be_phase."""
        buy_pos.phase = PositionPhase.BREAK_EVEN
        with patch.object(pm, '_handle_be_phase', new_callable=AsyncMock) as mock:
            await pm._manage_position(buy_pos, 1.1020)
        mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatches_trailing(self, pm, buy_pos):
        """TRAILING should dispatch to _handle_trailing_phase."""
        buy_pos.phase = PositionPhase.TRAILING_TO_TP1
        with patch.object(pm, '_handle_trailing_phase', new_callable=AsyncMock) as mock:
            await pm._manage_position(buy_pos, 1.1020)
        mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatches_aggressive(self, pm, buy_pos):
        """BEYOND_TP1 should dispatch to _handle_aggressive_phase."""
        buy_pos.phase = PositionPhase.BEYOND_TP1
        with patch.object(pm, '_handle_aggressive_phase', new_callable=AsyncMock) as mock:
            await pm._manage_position(buy_pos, 1.1020)
        mock.assert_called_once()


# ──────────────────────────────────────────────────────────────────
# _notify_trade_closed
# ──────────────────────────────────────────────────────────────────

class TestNotifyTradeClosed:
    @pytest.mark.asyncio
    async def test_callback_called(self, pm, buy_pos):
        """Registered callback should be invoked on trade close."""
        callback = AsyncMock()
        pm.set_on_trade_closed(callback)
        await pm._notify_trade_closed(buy_pos, exit_price=1.1050, pnl_dollars=50.0, reason="tp_max")
        callback.assert_called_once()
        call_kwargs = callback.call_args[1]
        assert call_kwargs["trade_id"] == "t1"
        assert call_kwargs["exit_price"] == 1.1050
        assert call_kwargs["reason"] == "tp_max"

    @pytest.mark.asyncio
    async def test_no_callback_no_crash(self, pm, buy_pos):
        """No callback registered should not crash."""
        await pm._notify_trade_closed(buy_pos, 1.1050, 50.0, "tp_max")

    @pytest.mark.asyncio
    async def test_callback_error_logged_not_raised(self, pm, buy_pos):
        """Callback exception should be logged but not propagated."""
        callback = AsyncMock(side_effect=Exception("DB down"))
        pm.set_on_trade_closed(callback)
        # Should not raise
        await pm._notify_trade_closed(buy_pos, 1.1050, 50.0, "tp_max")


# ──────────────────────────────────────────────────────────────────
# PositionManager initialization — style combinations
# ──────────────────────────────────────────────────────────────────

class TestInitialization:
    def test_price_action_style(self):
        """PRICE_ACTION style should have no base_ema_key."""
        broker = MagicMock()
        mgr = PositionManager(broker, management_style="price_action", trading_style="swing")
        assert mgr._base_ema_key is None
        assert mgr._cpa_ema_key is not None

    def test_lp_swing_forex(self):
        """LP swing forex should use Daily EMA 50."""
        broker = MagicMock()
        mgr = PositionManager(broker, management_style="lp", trading_style="swing")
        assert mgr._base_ema_key == "EMA_D_50"
        assert mgr._crypto_base_ema_key == "EMA_W_50"  # Wider for crypto
