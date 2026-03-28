"""
BUGFIX-002: Exhaustive unit tests for PositionManager.

Tests cover:
- Phase transitions (INITIAL → SL_MOVED → BREAK_EVEN → TRAILING → AGGRESSIVE)
- Management styles (LP, CP, CPA, PRICE_ACTION)
- Break even logic (two trigger methods)
- EMA-based trailing (with buffer)
- Price action trailing (swing highs/lows)
- CPA auto-trigger
- Partial profits
- Crypto vs forex EMA grid
- Fallback trailing with percentage
- Emergency exit on dual EMA break
- TP_max close
- Edge cases (missing EMA data, missing swing data)
"""

import sys
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from dataclasses import replace

sys.path.insert(0, ".")

from core.position_manager import (
    PositionManager, ManagedPosition, ManagementStyle,
    TradingStyle, PositionPhase,
    _EMA_TIMEFRAME_GRID, _EMA_TIMEFRAME_GRID_CRYPTO,
)


# ── Fixtures ──────────────────────────────────────────────────────────

class MockBroker:
    """Records SL modifications and trade closures for assertions."""

    def __init__(self):
        self.sl_updates = []   # [(trade_id, new_sl), ...]
        self.closed = []       # [(trade_id, units), ...]

    async def modify_trade_sl(self, trade_id, new_sl):
        self.sl_updates.append((trade_id, new_sl))

    async def close_trade(self, trade_id, units=None):
        self.closed.append((trade_id, units))


class MockRiskManager:
    """Tracks mark_position_at_be calls."""

    def __init__(self):
        self.be_marked = []

    def mark_position_at_be(self, trade_id):
        self.be_marked.append(trade_id)


@pytest.fixture
def broker():
    return MockBroker()


@pytest.fixture
def risk_mgr():
    return MockRiskManager()


@pytest.fixture
def pm(broker, risk_mgr):
    """PositionManager in LP/day_trading mode (Alex's default)."""
    return PositionManager(
        broker, risk_manager=risk_mgr,
        management_style="lp", trading_style="day_trading",
        allow_partial_profits=False,
    )


def make_pos(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100, tp_max=1.1200,
             trade_id="test-001", instrument="EUR_USD", units=20000, phase=PositionPhase.INITIAL):
    return ManagedPosition(
        trade_id=trade_id, instrument=instrument, direction=direction,
        entry_price=entry, original_sl=sl, current_sl=sl,
        take_profit_1=tp1, take_profit_max=tp_max,
        units=units, style="day_trading", phase=phase,
        highest_price=entry, lowest_price=entry,
    )


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# =====================================================================
# 1. Instantiation and EMA grid
# =====================================================================

class TestInstantiation:
    def test_lp_day_trading(self, broker):
        pm = PositionManager(broker, management_style="lp", trading_style="day_trading")
        assert pm.management_style == ManagementStyle.LP
        assert pm.trading_style == TradingStyle.DAY_TRADING
        assert pm._base_ema_key == "EMA_H1_50"

    def test_cp_day_trading(self, broker):
        pm = PositionManager(broker, management_style="cp", trading_style="day_trading")
        assert pm._base_ema_key == "EMA_M5_50"

    def test_price_action_has_no_base_ema(self, broker):
        pm = PositionManager(broker, management_style="price_action", trading_style="swing")
        assert pm._base_ema_key is None
        assert pm._cpa_ema_key is not None

    def test_all_grid_combinations_exist(self):
        """Every (ManagementStyle, TradingStyle) combo has a mapping."""
        for ms in [ManagementStyle.LP, ManagementStyle.CP, ManagementStyle.CPA]:
            for ts in [TradingStyle.SCALPING, TradingStyle.DAY_TRADING, TradingStyle.SWING]:
                assert (ms, ts) in _EMA_TIMEFRAME_GRID
                assert (ms, ts) in _EMA_TIMEFRAME_GRID_CRYPTO

    def test_crypto_grid_has_wider_timeframes(self):
        """Crypto LP Day Trading uses H4 vs H1 for forex."""
        assert _EMA_TIMEFRAME_GRID[(ManagementStyle.LP, TradingStyle.DAY_TRADING)] == "EMA_H1_50"
        assert _EMA_TIMEFRAME_GRID_CRYPTO[(ManagementStyle.LP, TradingStyle.DAY_TRADING)] == "EMA_H4_50"

    def test_partial_profits_default_false(self, broker):
        pm = PositionManager(broker)
        assert pm.allow_partial_profits is False

    def test_partial_profits_configurable(self, broker):
        pm = PositionManager(broker, allow_partial_profits=True)
        assert pm.allow_partial_profits is True


# =====================================================================
# 2. Crypto detection
# =====================================================================

class TestCryptoDetection:
    def test_btc_is_crypto(self, pm):
        assert pm._is_crypto("BTC_USD") is True

    def test_eth_is_crypto(self, pm):
        assert pm._is_crypto("ETH_USDT") is True

    def test_eur_is_not_crypto(self, pm):
        assert pm._is_crypto("EUR_USD") is False

    def test_crypto_uses_wider_ema(self, pm):
        assert pm._get_base_ema_key("BTC_USD") == "EMA_H4_50"
        assert pm._get_base_ema_key("EUR_USD") == "EMA_H1_50"


# =====================================================================
# 3. Track / remove position
# =====================================================================

class TestTrackRemove:
    def test_track_position(self, pm):
        pos = make_pos()
        pm.track_position(pos)
        assert "test-001" in pm.positions

    def test_remove_position(self, pm):
        pos = make_pos()
        pm.track_position(pos)
        pm.remove_position("test-001")
        assert "test-001" not in pm.positions


# =====================================================================
# 4. Phase 1: INITIAL → SL_MOVED
# =====================================================================

class TestInitialPhase:
    @patch("config.settings")
    def test_buy_moves_sl_at_30pct_profit(self, mock_settings, pm, broker):
        """BUY: when profit > 30% of risk distance, SL moves to cut 50% risk."""
        pos = make_pos(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100)
        # risk_distance = 0.005, 30% = 0.0015
        # price = 1.1020 → profit = 0.002 > 0.0015
        run(pm._handle_initial_phase(pos, 1.1020))
        assert pos.phase == PositionPhase.SL_MOVED
        # new_sl = 1.0950 + (1.1000 - 1.0950) * 0.5 = 1.0975
        assert broker.sl_updates[-1][1] == pytest.approx(1.0975)

    @patch("config.settings")
    def test_sell_moves_sl_at_30pct_profit(self, mock_settings, pm, broker):
        pos = make_pos(direction="SELL", entry=1.1000, sl=1.1050, tp1=1.0900)
        # profit = 1.1000 - 1.0975 = 0.0025 > 0.005*0.30 = 0.0015
        run(pm._handle_initial_phase(pos, 1.0975))
        assert pos.phase == PositionPhase.SL_MOVED
        # new_sl = 1.1050 - (1.1050 - 1.1000) * 0.5 = 1.1025
        assert broker.sl_updates[-1][1] == pytest.approx(1.1025)

    @patch("config.settings")
    def test_no_move_below_threshold(self, mock_settings, pm, broker):
        pos = make_pos(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100)
        # profit = 0.0005 < 0.005 * 0.30 = 0.0015
        run(pm._handle_initial_phase(pos, 1.1005))
        assert pos.phase == PositionPhase.INITIAL
        assert len(broker.sl_updates) == 0


# =====================================================================
# 5. Phase 2: SL_MOVED → BREAK_EVEN
# =====================================================================

class TestSlMovedPhase:
    @patch("config.settings")
    def test_be_at_risk_distance_method(self, mock_settings, pm, broker, risk_mgr):
        """'risk_distance' method: BE when profit >= 1x risk distance."""
        mock_settings.be_trigger_method = "risk_distance"
        pos = make_pos(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100,
                       phase=PositionPhase.SL_MOVED)
        pos.current_sl = 1.0975  # already moved

        # risk_distance = 0.005, price 1.1055 → profit 0.0055 >= 0.005 → BE
        # (use 1.1055 not 1.1050 to avoid float imprecision: 1.1050-1.1000 ≈ 0.00499...)
        run(pm._handle_sl_moved_phase(pos, 1.1055))
        assert pos.phase == PositionPhase.BREAK_EVEN

        # BE = entry + spread_buffer, buffer = risk_distance * 0.02 = 0.0001
        expected_sl = 1.1000 + 0.005 * 0.02
        assert broker.sl_updates[-1][1] == pytest.approx(expected_sl, abs=1e-5)

        # Risk manager notified
        assert "test-001" in risk_mgr.be_marked

    @patch("config.settings")
    def test_be_at_pct_to_tp1_method(self, mock_settings, pm, broker, risk_mgr):
        """'pct_to_tp1' method: BE at 50% of distance to TP1."""
        mock_settings.be_trigger_method = "pct_to_tp1"
        mock_settings.move_sl_to_be_pct_to_tp1 = 0.50
        pos = make_pos(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100,
                       phase=PositionPhase.SL_MOVED)

        # distance_to_tp1 = 0.01, 50% = 0.005
        # price 1.1055 → profit 0.0055 >= 0.005 → BE
        run(pm._handle_sl_moved_phase(pos, 1.1055))
        assert pos.phase == PositionPhase.BREAK_EVEN

    @patch("config.settings")
    def test_no_be_below_threshold(self, mock_settings, pm, broker):
        mock_settings.be_trigger_method = "risk_distance"
        pos = make_pos(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100,
                       phase=PositionPhase.SL_MOVED)

        # profit = 0.003 < risk_distance 0.005
        run(pm._handle_sl_moved_phase(pos, 1.1030))
        assert pos.phase == PositionPhase.SL_MOVED

    @patch("config.settings")
    def test_sell_be(self, mock_settings, pm, broker, risk_mgr):
        mock_settings.be_trigger_method = "risk_distance"
        pos = make_pos(direction="SELL", entry=1.1000, sl=1.1050, tp1=1.0900,
                       phase=PositionPhase.SL_MOVED)

        # risk_distance = 0.005, profit = 1.1000 - 1.0945 = 0.0055 >= 0.005
        run(pm._handle_sl_moved_phase(pos, 1.0945))
        assert pos.phase == PositionPhase.BREAK_EVEN
        # BE SL = entry - spread_buffer
        expected_sl = 1.1000 - 0.005 * 0.02
        assert broker.sl_updates[-1][1] == pytest.approx(expected_sl, abs=1e-5)


# =====================================================================
# 6. Phase 3: BREAK_EVEN → TRAILING
# =====================================================================

class TestBreakEvenPhase:
    @patch("config.settings")
    def test_transition_to_trailing(self, mock_settings, pm, broker):
        mock_settings.be_trigger_method = "risk_distance"
        pos = make_pos(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100,
                       phase=PositionPhase.BREAK_EVEN)

        # BE distance (risk_distance method) = 0.005
        # distance_to_tp1 = 0.01
        # trailing_trigger = 0.005 + 0.01 * 0.20 = 0.007
        # price 1.1075 → profit 0.0075 >= 0.007
        run(pm._handle_be_phase(pos, 1.1075))
        assert pos.phase == PositionPhase.TRAILING_TO_TP1

    @patch("config.settings")
    def test_no_transition_below_threshold(self, mock_settings, pm, broker):
        mock_settings.be_trigger_method = "risk_distance"
        pos = make_pos(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100,
                       phase=PositionPhase.BREAK_EVEN)

        # profit = 0.006 < 0.007
        run(pm._handle_be_phase(pos, 1.1060))
        assert pos.phase == PositionPhase.BREAK_EVEN


# =====================================================================
# 7. Phase 4: TRAILING (EMA-based)
# =====================================================================

class TestTrailingPhase:
    @patch("config.settings")
    def test_ema_trailing_buy_moves_sl_up(self, mock_settings, pm, broker):
        """SL trails behind EMA with buffer, only moves up for BUY."""
        pos = make_pos(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100,
                       phase=PositionPhase.TRAILING_TO_TP1)
        pos.current_sl = 1.1000  # at BE

        # Inject EMA value
        pm.set_ema_values("EUR_USD", {"EMA_H1_50": 1.1040})

        # buffer = trade_range * 0.02 = 0.01 * 0.02 = 0.0002
        # new_sl = 1.1040 - 0.0002 = 1.1038 > 1.1000 → moves up
        run(pm._handle_trailing_phase(pos, 1.1060))
        assert len(broker.sl_updates) > 0
        assert broker.sl_updates[-1][1] == pytest.approx(1.1040 - 0.01 * 0.02, abs=1e-5)

    @patch("config.settings")
    def test_ema_trailing_sell_moves_sl_down(self, mock_settings, pm, broker):
        pos = make_pos(direction="SELL", entry=1.1000, sl=1.1050, tp1=1.0900,
                       phase=PositionPhase.TRAILING_TO_TP1)
        pos.current_sl = 1.1000

        pm.set_ema_values("EUR_USD", {"EMA_H1_50": 1.0960})

        # buffer = 0.01 * 0.02 = 0.0002
        # new_sl = 1.0960 + 0.0002 = 1.0962 < 1.1000 → moves down
        run(pm._handle_trailing_phase(pos, 1.0940))
        assert len(broker.sl_updates) > 0
        assert broker.sl_updates[-1][1] == pytest.approx(1.0960 + 0.01 * 0.02, abs=1e-5)

    @patch("config.settings")
    def test_sl_never_moves_backward_buy(self, mock_settings, pm, broker):
        """BUY: SL should never move down."""
        pos = make_pos(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100,
                       phase=PositionPhase.TRAILING_TO_TP1)
        pos.current_sl = 1.1040  # already ahead

        pm.set_ema_values("EUR_USD", {"EMA_H1_50": 1.1020})

        # new_sl = 1.1020 - buffer < 1.1040 → no move
        run(pm._handle_trailing_phase(pos, 1.1060))
        assert len(broker.sl_updates) == 0

    @patch("config.settings")
    def test_tp1_reached_transitions_to_aggressive(self, mock_settings, pm, broker):
        pos = make_pos(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100,
                       phase=PositionPhase.TRAILING_TO_TP1)

        run(pm._handle_trailing_phase(pos, 1.1105))  # > tp1
        assert pos.phase == PositionPhase.BEYOND_TP1

    @patch("config.settings")
    def test_fallback_percentage_when_no_ema(self, mock_settings, pm, broker):
        """Falls back to 40% trail when no EMA data available."""
        pos = make_pos(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100,
                       phase=PositionPhase.TRAILING_TO_TP1)
        pos.current_sl = 1.1000

        # No EMA data set → fallback
        run(pm._handle_trailing_phase(pos, 1.1060))
        # trail_distance = 0.01 * 0.4 = 0.004
        # new_sl = 1.1060 - 0.004 = 1.1020 > 1.1000 → moves
        assert len(broker.sl_updates) > 0
        assert broker.sl_updates[-1][1] == pytest.approx(1.1060 - 0.01 * 0.4, abs=1e-5)


# =====================================================================
# 8. Partial profits at TP1
# =====================================================================

class TestPartialProfits:
    @patch("config.settings")
    def test_partial_close_when_enabled(self, mock_settings, broker, risk_mgr):
        pm = PositionManager(broker, risk_manager=risk_mgr,
                             management_style="lp", trading_style="day_trading",
                             allow_partial_profits=True)
        pos = make_pos(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100, units=20000,
                       phase=PositionPhase.TRAILING_TO_TP1)
        pm.track_position(pos)

        run(pm._handle_trailing_phase(pos, 1.1105))  # TP1 reached
        assert pos.phase == PositionPhase.BEYOND_TP1
        # Should have closed half = 10000 units
        assert len(broker.closed) == 1
        assert broker.closed[0][1] == 10000
        assert pos.units == 10000

    @patch("config.settings")
    def test_no_partial_when_disabled(self, mock_settings, pm, broker):
        pos = make_pos(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100, units=20000,
                       phase=PositionPhase.TRAILING_TO_TP1)
        pm.track_position(pos)

        run(pm._handle_trailing_phase(pos, 1.1105))
        assert pos.phase == PositionPhase.BEYOND_TP1
        assert len(broker.closed) == 0  # no partial close
        assert pos.units == 20000


# =====================================================================
# 9. Phase 5: AGGRESSIVE (beyond TP1)
# =====================================================================

class TestAggressivePhase:
    @patch("config.settings")
    def test_close_at_tp_max(self, mock_settings, pm, broker):
        pos = make_pos(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100,
                       tp_max=1.1200, phase=PositionPhase.BEYOND_TP1)
        pm.track_position(pos)

        run(pm._handle_aggressive_phase(pos, 1.1205))  # > tp_max
        assert len(broker.closed) == 1
        assert broker.closed[0][0] == "test-001"

    @patch("config.settings")
    def test_aggressive_trailing_with_cpa_ema(self, mock_settings, pm, broker):
        pos = make_pos(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100,
                       tp_max=1.1200, phase=PositionPhase.BEYOND_TP1)
        pos.current_sl = 1.1050

        # CPA EMA key for LP/day_trading = EMA_M5_50
        pm.set_ema_values("EUR_USD", {"EMA_M5_50": 1.1080})

        # buffer (aggressive) = 0.01 * 0.01 = 0.0001
        # new_sl = 1.1080 - 0.0001 = 1.1079 > 1.1050 → move
        run(pm._handle_aggressive_phase(pos, 1.1150))
        assert len(broker.sl_updates) > 0
        assert broker.sl_updates[-1][1] == pytest.approx(1.1080 - 0.01 * 0.01, abs=1e-5)

    @patch("config.settings")
    def test_emergency_exit_on_dual_ema_break(self, mock_settings, pm, broker):
        pos = make_pos(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100,
                       tp_max=1.1200, phase=PositionPhase.BEYOND_TP1)
        pm.track_position(pos)

        pm.set_ema_values("EUR_USD", {
            "EMA_M5_2": 1.1060,
            "EMA_M5_5": 1.1070,
            "EMA_M5_50": 1.1050,
        })

        # Price below BOTH EMA_M5_2 and EMA_M5_5 → emergency exit
        run(pm._handle_aggressive_phase(pos, 1.1055))
        assert len(broker.closed) == 1

    @patch("config.settings")
    def test_fallback_percentage_when_no_cpa_ema(self, mock_settings, pm, broker):
        pos = make_pos(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100,
                       tp_max=1.1200, phase=PositionPhase.BEYOND_TP1)
        pos.current_sl = 1.1050

        # No EMA data → fallback 20% trail
        run(pm._handle_aggressive_phase(pos, 1.1150))
        # trail_distance = 0.01 * 0.2 = 0.002
        # new_sl = 1.1150 - 0.002 = 1.1130 > 1.1050 → moves
        assert len(broker.sl_updates) > 0
        assert broker.sl_updates[-1][1] == pytest.approx(1.1150 - 0.01 * 0.2, abs=1e-5)


# =====================================================================
# 10. CPA auto-trigger
# =====================================================================

class TestCPATrigger:
    @patch("config.settings")
    def test_cpa_trigger_at_be_phase(self, mock_settings, pm):
        pos = make_pos(phase=PositionPhase.BREAK_EVEN)
        pm.track_position(pos)

        pm.set_cpa_trigger("test-001", "double_top")
        assert pos.phase == PositionPhase.BEYOND_TP1

    @patch("config.settings")
    def test_cpa_trigger_at_trailing_phase(self, mock_settings, pm):
        pos = make_pos(phase=PositionPhase.TRAILING_TO_TP1)
        pm.track_position(pos)

        pm.set_cpa_trigger("test-001", "news_approaching")
        assert pos.phase == PositionPhase.BEYOND_TP1

    @patch("config.settings")
    def test_cpa_trigger_ignored_at_initial_phase(self, mock_settings, pm):
        pos = make_pos(phase=PositionPhase.INITIAL)
        pm.track_position(pos)

        pm.set_cpa_trigger("test-001", "friday_close")
        assert pos.phase == PositionPhase.INITIAL  # unchanged

    @patch("config.settings")
    def test_cpa_trigger_ignored_unknown_id(self, mock_settings, pm):
        """No crash on unknown trade_id."""
        pm.set_cpa_trigger("nonexistent", "news")  # should not raise


# =====================================================================
# 11. Price action trailing
# =====================================================================

class TestPriceActionTrailing:
    @patch("config.settings")
    def test_buy_trails_behind_swing_low(self, mock_settings, broker, risk_mgr):
        pm = PositionManager(broker, risk_manager=risk_mgr,
                             management_style="price_action", trading_style="day_trading")
        pos = make_pos(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100,
                       phase=PositionPhase.TRAILING_TO_TP1)
        pos.current_sl = 1.0990

        pm.set_swing_values("EUR_USD", [1.1050], [1.1010, 1.0980])

        # buffer = 0.01 * 0.02 = 0.0002
        # Most recent swing low below price: 1.1010
        # new_sl = 1.1010 - 0.0002 = 1.1008 > 1.0990 → moves up
        run(pm._trail_with_price_action(pos, 1.1050))
        assert len(broker.sl_updates) > 0
        assert broker.sl_updates[-1][1] == pytest.approx(1.1010 - 0.01 * 0.02, abs=1e-5)

    @patch("config.settings")
    def test_sell_trails_behind_swing_high(self, mock_settings, broker, risk_mgr):
        pm = PositionManager(broker, risk_manager=risk_mgr,
                             management_style="price_action", trading_style="day_trading")
        pos = make_pos(direction="SELL", entry=1.1000, sl=1.1050, tp1=1.0900,
                       phase=PositionPhase.TRAILING_TO_TP1)
        pos.current_sl = 1.1020

        pm.set_swing_values("EUR_USD", [1.0980, 1.1010], [1.0920])

        # Most recent swing high above current price: 1.0980
        # new_sl = 1.0980 + 0.0002 = 1.0982 < 1.1020 → moves down
        run(pm._trail_with_price_action(pos, 1.0950))
        assert len(broker.sl_updates) > 0
        assert broker.sl_updates[-1][1] == pytest.approx(1.0980 + 0.01 * 0.02, abs=1e-5)

    @patch("config.settings")
    def test_fallback_when_no_swing_data(self, mock_settings, broker, risk_mgr):
        pm = PositionManager(broker, risk_manager=risk_mgr,
                             management_style="price_action", trading_style="day_trading")
        pos = make_pos(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100,
                       phase=PositionPhase.TRAILING_TO_TP1)
        pos.current_sl = 1.1000

        # No swing data → fallback to percentage trailing
        run(pm._trail_with_price_action(pos, 1.1060))
        assert len(broker.sl_updates) > 0


# =====================================================================
# 12. Percentage trailing (fallback)
# =====================================================================

class TestPercentageTrailing:
    @patch("config.settings")
    def test_buy_trail_with_percentage(self, mock_settings, pm, broker):
        pos = make_pos(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100)
        pos.current_sl = 1.1000

        # trail_pct=0.4, distance_to_tp1=0.01
        # trail_distance = 0.004
        # new_sl = 1.1060 - 0.004 = 1.1020 > 1.1000 → move
        run(pm._trail_with_percentage(pos, 1.1060, trail_pct=0.4))
        assert broker.sl_updates[-1][1] == pytest.approx(1.1020, abs=1e-5)

    @patch("config.settings")
    def test_no_trail_when_no_profit(self, mock_settings, pm, broker):
        pos = make_pos(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100)
        pos.current_sl = 1.0960

        # price at entry → no profit → no trail
        run(pm._trail_with_percentage(pos, 1.1000, trail_pct=0.4))
        assert len(broker.sl_updates) == 0


# =====================================================================
# 13. EMA buffer calculation
# =====================================================================

class TestEMABuffer:
    def test_base_buffer_2pct(self, pm):
        pos = make_pos(entry=1.1000, tp1=1.1100)
        buffer = pm._ema_buffer(pos, aggressive=False)
        assert buffer == pytest.approx(0.01 * 0.02)

    def test_aggressive_buffer_1pct(self, pm):
        pos = make_pos(entry=1.1000, tp1=1.1100)
        buffer = pm._ema_buffer(pos, aggressive=True)
        assert buffer == pytest.approx(0.01 * 0.01)


# =====================================================================
# 14. EMA fallback chain
# =====================================================================

class TestEMAFallback:
    def test_primary_ema_found(self, pm):
        pm.set_ema_values("EUR_USD", {"EMA_H1_50": 1.1050})
        val = pm._get_trail_ema("EUR_USD", "EMA_H1_50")
        assert val == 1.1050

    def test_fallback_chain(self, pm):
        pm.set_ema_values("EUR_USD", {"EMA_M5_50": 1.1030})
        # EMA_H1_50 not available → fallback chain tries H4→H1→M15→M5
        val = pm._get_trail_ema("EUR_USD", "EMA_H1_50")
        assert val == 1.1030

    def test_none_when_no_ema(self, pm):
        val = pm._get_trail_ema("EUR_USD", "EMA_H1_50")
        assert val is None


# =====================================================================
# 15. Set EMA and swing values
# =====================================================================

class TestDataInjection:
    def test_set_ema_values(self, pm):
        pm.set_ema_values("EUR_USD", {"EMA_H1_50": 1.1050, "EMA_M5_50": 1.1030})
        assert pm._latest_emas["EUR_USD"]["EMA_H1_50"] == 1.1050

    def test_set_swing_values(self, pm):
        pm.set_swing_values("EUR_USD", [1.1100, 1.1080], [1.0900, 1.0920])
        assert pm._latest_swings["EUR_USD"]["highs"] == [1.1100, 1.1080]
        assert pm._latest_swings["EUR_USD"]["lows"] == [1.0900, 1.0920]


# =====================================================================
# 16. Full phase progression (end-to-end)
# =====================================================================

class TestFullPhaseProgression:
    @patch("config.settings")
    def test_buy_full_lifecycle(self, mock_settings, pm, broker, risk_mgr):
        """Simulate BUY going through all 5 phases."""
        mock_settings.be_trigger_method = "risk_distance"

        pos = make_pos(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100,
                       tp_max=1.1200)
        pm.track_position(pos)

        # Phase 1 → 2: profit > 30% of risk_distance
        run(pm._manage_position(pos, 1.1020))
        assert pos.phase == PositionPhase.SL_MOVED

        # Phase 2 → 3: profit >= risk_distance (0.005)
        # Use 1.1055 to avoid float imprecision at boundary
        run(pm._manage_position(pos, 1.1055))
        assert pos.phase == PositionPhase.BREAK_EVEN
        assert "test-001" in risk_mgr.be_marked

        # Phase 3 → 4: profit >= BE + 20% distance_to_tp1
        # trailing_trigger = 0.005 + 0.01 * 0.20 = 0.007
        run(pm._manage_position(pos, 1.1080))
        assert pos.phase == PositionPhase.TRAILING_TO_TP1

        # Phase 4 → 5: price reaches TP1
        pm.set_ema_values("EUR_USD", {"EMA_H1_50": 1.1060, "EMA_M5_50": 1.1080})
        run(pm._manage_position(pos, 1.1105))
        assert pos.phase == PositionPhase.BEYOND_TP1

    @patch("config.settings")
    def test_sell_full_lifecycle(self, mock_settings, pm, broker, risk_mgr):
        """Simulate SELL going through all phases."""
        mock_settings.be_trigger_method = "risk_distance"

        pos = make_pos(direction="SELL", entry=1.1000, sl=1.1050, tp1=1.0900,
                       tp_max=1.0800)
        pos.lowest_price = 1.1000
        pm.track_position(pos)

        # Phase 1 → 2
        run(pm._manage_position(pos, 1.0975))
        assert pos.phase == PositionPhase.SL_MOVED

        # Phase 2 → 3: profit must exceed risk_distance (0.005)
        run(pm._manage_position(pos, 1.0940))
        assert pos.phase == PositionPhase.BREAK_EVEN

        # Phase 3 → 4: profit must exceed trailing_trigger
        run(pm._manage_position(pos, 1.0915))
        assert pos.phase == PositionPhase.TRAILING_TO_TP1

        # Phase 4 → 5
        pm.set_ema_values("EUR_USD", {"EMA_H1_50": 1.0940})
        run(pm._manage_position(pos, 1.0895))
        assert pos.phase == PositionPhase.BEYOND_TP1


# =====================================================================
# 17. ManagedPosition dataclass
# =====================================================================

class TestManagedPosition:
    def test_default_phase(self):
        pos = make_pos()
        assert pos.phase == PositionPhase.INITIAL

    def test_default_highest_price(self):
        pos = make_pos(entry=1.1000)
        assert pos.highest_price == 1.1000

    def test_default_lowest_price(self):
        pos = make_pos(entry=1.1000)
        assert pos.lowest_price == 1.1000

    def test_units_signed(self):
        buy_pos = make_pos(direction="BUY", units=20000)
        assert buy_pos.units > 0
        sell_pos = make_pos(direction="SELL", units=-20000)
        assert sell_pos.units < 0
