"""
BUGFIX-002: Exhaustive unit tests for RiskManager.

Tests cover:
- 1% rule per style (day/scalping/swing)
- Position sizing (Alex's formula)
- Drawdown management (3 methods: fixed_1pct, variable, fixed_levels)
- Correlated pairs (fixed 0.75%)
- Delta risk algorithm (winning streak bonus)
- Scale-in rule (require BE)
- Reward-risk validation
- Trade registration/unregistration
- Funded account limits
- Recovery math
- DD alert levels
- Risk status reporting
"""

import sys
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, ".")

from core.risk_manager import RiskManager, TradingStyle, TradeRisk, TradeResult


# ── Fixtures ──────────────────────────────────────────────────────────

class MockBroker:
    """Minimal mock broker for RiskManager tests."""

    def __init__(self, balance=10000.0, pip_value=0.0001):
        self._balance = balance
        self._pip_value = pip_value

    async def get_account_balance(self):
        return self._balance

    async def get_pip_value(self, instrument):
        return self._pip_value


@pytest.fixture
def broker():
    return MockBroker(balance=10000.0, pip_value=0.0001)


@pytest.fixture
def rm(broker):
    """Fresh RiskManager with known state."""
    r = RiskManager(broker)
    r._peak_balance = 10000.0
    r._current_balance = 10000.0
    return r


# ── Helper ────────────────────────────────────────────────────────────

def run(coro):
    return asyncio.run(coro)


# =====================================================================
# 1. Base risk per style
# =====================================================================

class TestBaseRiskPerStyle:
    """Verify the 1% day / 0.5% scalping / 1% swing rule (1% NON-NEGOTIABLE per mentorship)."""

    @patch("core.risk_manager.settings")
    def test_day_trading_risk_1pct(self, mock_settings, rm):
        mock_settings.risk_day_trading = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.delta_max_risk = 0.02
        assert rm.get_risk_for_style(TradingStyle.DAY_TRADING) == 0.01

    @patch("core.risk_manager.settings")
    def test_scalping_risk_05pct(self, mock_settings, rm):
        mock_settings.risk_scalping = 0.005
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.delta_max_risk = 0.02
        assert rm.get_risk_for_style(TradingStyle.SCALPING) == 0.005

    @patch("core.risk_manager.settings")
    def test_swing_risk_1pct(self, mock_settings, rm):
        mock_settings.risk_swing = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.delta_max_risk = 0.02
        assert rm.get_risk_for_style(TradingStyle.SWING) == 0.01


# =====================================================================
# 2. Position sizing — Alex's formula
# =====================================================================

class TestPositionSizing:
    """Risk Amount = Balance × Risk%, Units = Risk Amount / SL Distance."""

    @patch("core.risk_manager.settings")
    @patch("core.risk_manager.balance_cache")
    def test_basic_position_size(self, mock_cache, mock_settings, rm):
        mock_cache.get.return_value = 10000.0
        mock_settings.risk_day_trading = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.delta_max_risk = 0.02
        mock_settings.correlation_groups = []
        mock_settings.indices_correlation_groups = []
        mock_settings.crypto_correlation_groups = []
        mock_settings.equities_correlation_groups = []
        mock_settings.leverage_forex = 100
        mock_settings.leverage_crypto = 20
        mock_settings.leverage_commodities = 100
        mock_settings.leverage_indices = 100

        # BUY: entry=1.1000, SL=1.0950, distance=0.005
        # Risk = 10000 * 0.01 = 100, Units = int(100 / 0.005) ≈ 19999-20000 (float truncation)
        units = run(rm.calculate_position_size("EUR_USD", TradingStyle.DAY_TRADING, 1.1000, 1.0950))
        assert abs(units - 20000) <= 1  # int() truncation tolerance
        assert units > 0  # positive = BUY

    @patch("core.risk_manager.settings")
    @patch("core.risk_manager.balance_cache")
    def test_sell_position_negative_units(self, mock_cache, mock_settings, rm):
        mock_cache.get.return_value = 10000.0
        mock_settings.risk_day_trading = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.delta_max_risk = 0.02
        mock_settings.correlation_groups = []
        mock_settings.indices_correlation_groups = []
        mock_settings.crypto_correlation_groups = []
        mock_settings.equities_correlation_groups = []
        mock_settings.leverage_forex = 100
        mock_settings.leverage_crypto = 20
        mock_settings.leverage_commodities = 100
        mock_settings.leverage_indices = 100

        # SELL: entry=1.0950, SL=1.1000 → entry < SL → units negative
        units = run(rm.calculate_position_size("EUR_USD", TradingStyle.DAY_TRADING, 1.0950, 1.1000))
        assert abs(units + 20000) <= 1  # int() truncation tolerance
        assert units < 0  # negative = SELL

    @patch("core.risk_manager.settings")
    @patch("core.risk_manager.balance_cache")
    def test_zero_sl_distance_returns_zero(self, mock_cache, mock_settings, rm):
        mock_cache.get.return_value = 10000.0
        mock_settings.risk_day_trading = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.delta_max_risk = 0.02
        mock_settings.correlation_groups = []
        mock_settings.indices_correlation_groups = []
        mock_settings.crypto_correlation_groups = []
        mock_settings.equities_correlation_groups = []

        units = run(rm.calculate_position_size("EUR_USD", TradingStyle.DAY_TRADING, 1.1000, 1.1000))
        assert units == 0

    @patch("core.risk_manager.settings")
    @patch("core.risk_manager.balance_cache")
    def test_position_size_capped_at_max_units(self, mock_cache, mock_settings):
        """Very small SL distance → huge position → must be capped at 10M."""
        broker = MockBroker(balance=1_000_000.0, pip_value=0.0001)
        r = RiskManager(broker)
        r._peak_balance = 1_000_000.0
        r._current_balance = 1_000_000.0

        mock_cache.get.return_value = 1_000_000.0
        mock_settings.risk_day_trading = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.delta_max_risk = 0.02
        mock_settings.correlation_groups = []
        mock_settings.indices_correlation_groups = []
        mock_settings.crypto_correlation_groups = []
        mock_settings.equities_correlation_groups = []
        mock_settings.leverage_forex = 100
        mock_settings.leverage_crypto = 20
        mock_settings.leverage_commodities = 100
        mock_settings.leverage_indices = 100

        # Risk = 1M * 0.01 = 10000, SL distance = 0.00001 → Units = 1B → capped to 10M
        units = run(r.calculate_position_size("EUR_USD", TradingStyle.DAY_TRADING, 1.10000, 1.09999))
        assert abs(units) <= 10_000_000


# =====================================================================
# 3. Drawdown management — three methods
# =====================================================================

class TestDrawdownFixed1Pct:
    """fixed_1pct: no adjustment regardless of DD."""

    @patch("core.risk_manager.settings")
    def test_no_adjustment_even_at_high_dd(self, mock_settings, rm):
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.delta_max_risk = 0.02
        mock_settings.risk_day_trading = 0.01
        rm._peak_balance = 10000.0
        rm._current_balance = 8500.0  # 15% DD
        assert rm.get_risk_for_style(TradingStyle.DAY_TRADING) == 0.01


class TestDrawdownVariable:
    """Variable method: winrate × base_risk × multiplier."""

    @patch("core.risk_manager.settings")
    def test_at_max_dd_reduces_risk(self, mock_settings, rm):
        mock_settings.drawdown_method = "variable"
        mock_settings.delta_enabled = False
        mock_settings.delta_max_risk = 0.02
        mock_settings.risk_day_trading = 0.01

        rm._peak_balance = 10000.0
        rm._current_balance = 9500.0  # 5% DD
        rm._max_historical_dd = 0.05   # max = current

        # dd_ratio = 1.0 → multiplier 1.0 → adjusted = win_rate * 0.01 * 1.0
        # Default win rate with no history = 0.5
        risk = rm.get_risk_for_style(TradingStyle.DAY_TRADING)
        # 0.5 * 0.01 * 1.0 = 0.005
        assert risk == pytest.approx(0.005, abs=1e-6)

    @patch("core.risk_manager.settings")
    def test_no_dd_returns_base_risk(self, mock_settings, rm):
        mock_settings.drawdown_method = "variable"
        mock_settings.delta_enabled = False
        mock_settings.delta_max_risk = 0.02
        mock_settings.risk_day_trading = 0.01

        rm._peak_balance = 10000.0
        rm._current_balance = 10000.0  # 0% DD
        rm._max_historical_dd = 0.05

        # dd_ratio = 0 → below 0.50 → no adjustment → base risk
        risk = rm.get_risk_for_style(TradingStyle.DAY_TRADING)
        assert risk == 0.01

    @patch("core.risk_manager.settings")
    def test_minimum_25pct_of_base(self, mock_settings, rm):
        """Even with very low win rate, minimum is 25% of base."""
        mock_settings.drawdown_method = "variable"
        mock_settings.delta_enabled = False
        mock_settings.delta_max_risk = 0.02
        mock_settings.risk_day_trading = 0.01

        rm._peak_balance = 10000.0
        rm._current_balance = 9500.0  # 5% DD
        rm._max_historical_dd = 0.05  # dd_ratio = 1.0

        # Win rate = 0.1 → adjusted = 0.1 * 0.01 * 1.0 = 0.001
        # min = 0.01 * 0.25 = 0.0025 → wins
        rm._trade_history = [TradeResult(f"t{i}", "EUR_USD", -0.01, False) for i in range(45)]
        rm._trade_history += [TradeResult(f"w{i}", "EUR_USD", 0.02, True) for i in range(5)]

        risk = rm.get_risk_for_style(TradingStyle.DAY_TRADING)
        assert risk >= 0.01 * 0.25  # floor at 25% of base


class TestDrawdownFixedLevels:
    """Fixed levels: step-down at -5%, -7.5%, -10%."""

    @patch("core.risk_manager.settings")
    def test_level_1_at_5pct_dd(self, mock_settings, rm):
        mock_settings.drawdown_method = "fixed_levels"
        mock_settings.delta_enabled = False
        mock_settings.delta_max_risk = 0.02
        mock_settings.risk_day_trading = 0.01
        mock_settings.drawdown_level_1 = 0.05
        mock_settings.drawdown_level_2 = 0.075
        mock_settings.drawdown_level_3 = 0.10
        mock_settings.drawdown_risk_1 = 0.0075
        mock_settings.drawdown_risk_2 = 0.005
        mock_settings.drawdown_risk_3 = 0.0025

        rm._peak_balance = 10000.0
        rm._current_balance = 9400.0  # 6% DD (>= level_1, < level_2)

        risk = rm.get_risk_for_style(TradingStyle.DAY_TRADING)
        assert risk == 0.0075

    @patch("core.risk_manager.settings")
    def test_level_2_at_75pct_dd(self, mock_settings, rm):
        mock_settings.drawdown_method = "fixed_levels"
        mock_settings.delta_enabled = False
        mock_settings.delta_max_risk = 0.02
        mock_settings.risk_day_trading = 0.01
        mock_settings.drawdown_level_1 = 0.05
        mock_settings.drawdown_level_2 = 0.075
        mock_settings.drawdown_level_3 = 0.10
        mock_settings.drawdown_risk_1 = 0.0075
        mock_settings.drawdown_risk_2 = 0.005
        mock_settings.drawdown_risk_3 = 0.0025

        rm._peak_balance = 10000.0
        rm._current_balance = 9200.0  # 8% DD (>= level_2, < level_3)

        risk = rm.get_risk_for_style(TradingStyle.DAY_TRADING)
        assert risk == 0.005

    @patch("core.risk_manager.settings")
    def test_level_3_at_10pct_dd(self, mock_settings, rm):
        mock_settings.drawdown_method = "fixed_levels"
        mock_settings.delta_enabled = False
        mock_settings.delta_max_risk = 0.02
        mock_settings.risk_day_trading = 0.01
        mock_settings.drawdown_level_1 = 0.05
        mock_settings.drawdown_level_2 = 0.075
        mock_settings.drawdown_level_3 = 0.10
        mock_settings.drawdown_risk_1 = 0.0075
        mock_settings.drawdown_risk_2 = 0.005
        mock_settings.drawdown_risk_3 = 0.0025

        rm._peak_balance = 10000.0
        rm._current_balance = 8900.0  # 11% DD (>= level_3)

        risk = rm.get_risk_for_style(TradingStyle.DAY_TRADING)
        assert risk == 0.0025

    @patch("core.risk_manager.settings")
    def test_no_reduction_below_level_1(self, mock_settings, rm):
        mock_settings.drawdown_method = "fixed_levels"
        mock_settings.delta_enabled = False
        mock_settings.delta_max_risk = 0.02
        mock_settings.risk_day_trading = 0.01
        mock_settings.drawdown_level_1 = 0.05
        mock_settings.drawdown_level_2 = 0.075
        mock_settings.drawdown_level_3 = 0.10

        rm._peak_balance = 10000.0
        rm._current_balance = 9700.0  # 3% DD (below level_1)

        risk = rm.get_risk_for_style(TradingStyle.DAY_TRADING)
        assert risk == 0.01


# =====================================================================
# 4. Current drawdown calculation
# =====================================================================

class TestCurrentDrawdown:
    def test_zero_dd_at_peak(self, rm):
        rm._peak_balance = 10000.0
        rm._current_balance = 10000.0
        assert rm.get_current_drawdown() == 0.0

    def test_5pct_dd(self, rm):
        rm._peak_balance = 10000.0
        rm._current_balance = 9500.0
        assert rm.get_current_drawdown() == pytest.approx(0.05)

    def test_zero_peak_returns_0(self, rm):
        rm._peak_balance = 0.0
        rm._current_balance = 0.0
        assert rm.get_current_drawdown() == 0.0

    def test_balance_above_peak_returns_0(self, rm):
        rm._peak_balance = 10000.0
        rm._current_balance = 10500.0
        assert rm.get_current_drawdown() == 0.0


# =====================================================================
# 5. Correlation handling — fixed 0.75%
# =====================================================================

class TestCorrelation:
    @patch("core.risk_manager.settings")
    def test_correlated_pair_returns_fixed_075pct(self, mock_settings, rm):
        mock_settings.correlation_groups = [["EUR_USD", "GBP_USD", "EUR_GBP"]]
        mock_settings.indices_correlation_groups = []
        mock_settings.crypto_correlation_groups = []
        mock_settings.equities_correlation_groups = []
        mock_settings.correlated_risk_pct = 0.0075

        # Register a trade on EUR_USD
        rm.register_trade("t1", "EUR_USD", 0.01)

        adjusted = rm._adjust_for_correlation("GBP_USD", 0.01)
        assert adjusted == 0.0075

    @patch("core.risk_manager.settings")
    def test_uncorrelated_pair_returns_base_risk(self, mock_settings, rm):
        mock_settings.correlation_groups = [["EUR_USD", "GBP_USD"]]
        mock_settings.indices_correlation_groups = []
        mock_settings.crypto_correlation_groups = []
        mock_settings.equities_correlation_groups = []
        mock_settings.correlated_risk_pct = 0.0075

        rm.register_trade("t1", "EUR_USD", 0.01)

        adjusted = rm._adjust_for_correlation("USD_JPY", 0.01)
        assert adjusted == 0.01

    @patch("core.risk_manager.settings")
    def test_no_active_trades_returns_base_risk(self, mock_settings, rm):
        mock_settings.correlation_groups = [["EUR_USD", "GBP_USD"]]
        mock_settings.indices_correlation_groups = []
        mock_settings.crypto_correlation_groups = []
        mock_settings.equities_correlation_groups = []

        adjusted = rm._adjust_for_correlation("GBP_USD", 0.01)
        assert adjusted == 0.01


# =====================================================================
# 6. Reward-Risk validation
# =====================================================================

class TestRewardRisk:
    @patch("core.risk_manager.settings")
    def test_valid_rr_above_minimum(self, mock_settings, rm):
        mock_settings.min_rr_ratio = 1.5
        assert rm.validate_reward_risk(1.1000, 1.0950, 1.1100) is True  # R:R = 2.0

    @patch("core.risk_manager.settings")
    def test_invalid_rr_below_minimum(self, mock_settings, rm):
        mock_settings.min_rr_ratio = 1.5
        assert rm.validate_reward_risk(1.1000, 1.0950, 1.1050) is False  # R:R = 1.0

    @patch("core.risk_manager.settings")
    def test_exactly_at_minimum_is_valid(self, mock_settings, rm):
        mock_settings.min_rr_ratio = 2.0
        # R:R = 0.010 / 0.005 = 2.0 exactly
        assert rm.validate_reward_risk(1.1000, 1.0950, 1.1100) is True

    @patch("core.risk_manager.settings")
    def test_zero_risk_returns_false(self, mock_settings, rm):
        mock_settings.min_rr_ratio = 1.5
        assert rm.validate_reward_risk(1.1000, 1.1000, 1.1100) is False


# =====================================================================
# 7. Trade registration / unregistration
# =====================================================================

class TestTradeRegistration:
    def test_register_trade(self, rm):
        rm.register_trade("t1", "EUR_USD", 0.01)
        assert rm.get_current_total_risk() == pytest.approx(0.01)

    def test_register_multiple_trades(self, rm):
        rm.register_trade("t1", "EUR_USD", 0.01)
        rm.register_trade("t2", "GBP_USD", 0.01)
        assert rm.get_current_total_risk() == pytest.approx(0.02)

    def test_unregister_trade(self, rm):
        rm.register_trade("t1", "EUR_USD", 0.01)
        rm.unregister_trade("t1", "EUR_USD")
        assert rm.get_current_total_risk() == 0.0

    def test_unregister_cleans_be_tracking(self, rm):
        rm.register_trade("t1", "EUR_USD", 0.01)
        rm.mark_position_at_be("t1")
        assert "t1" in rm._positions_at_be
        rm.unregister_trade("t1", "EUR_USD")
        assert "t1" not in rm._positions_at_be

    def test_unregister_all(self, rm):
        rm.register_trade("t1", "EUR_USD", 0.01)
        rm.register_trade("t2", "GBP_USD", 0.01)
        rm.mark_position_at_be("t1")
        rm.unregister_all_trades()
        assert rm.get_current_total_risk() == 0.0
        assert len(rm._positions_at_be) == 0


# =====================================================================
# 8. Can take trade (max risk check)
# =====================================================================

class TestCanTakeTrade:
    @patch("core.risk_manager.settings")
    def test_allowed_when_under_max(self, mock_settings, rm):
        mock_settings.max_total_risk = 0.07
        mock_settings.risk_day_trading = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.delta_max_risk = 0.02
        mock_settings.funded_account_mode = False
        mock_settings.scale_in_require_be = False
        mock_settings.correlation_groups = []
        mock_settings.indices_correlation_groups = []
        mock_settings.crypto_correlation_groups = []
        mock_settings.equities_correlation_groups = []

        assert rm.can_take_trade(TradingStyle.DAY_TRADING, "EUR_USD") is True

    @patch("core.risk_manager.settings")
    def test_blocked_when_at_max(self, mock_settings, rm):
        mock_settings.max_total_risk = 0.07
        mock_settings.risk_day_trading = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.delta_max_risk = 0.02
        mock_settings.funded_account_mode = False
        mock_settings.scale_in_require_be = False
        mock_settings.correlation_groups = []
        mock_settings.indices_correlation_groups = []
        mock_settings.crypto_correlation_groups = []
        mock_settings.equities_correlation_groups = []

        # Fill up to 7%
        for i in range(7):
            rm.register_trade(f"t{i}", f"PAIR_{i}", 0.01)

        assert rm.can_take_trade(TradingStyle.DAY_TRADING, "NEW_PAIR") is False


# =====================================================================
# 9. Scale-in rule
# =====================================================================

class TestScaleIn:
    @patch("core.risk_manager.settings")
    def test_blocked_when_first_trade_not_at_be(self, mock_settings, rm):
        mock_settings.scale_in_require_be = True
        rm.register_trade("t1", "EUR_USD", 0.01)
        assert rm.can_scale_in("EUR_USD") is False

    @patch("core.risk_manager.settings")
    def test_allowed_when_first_trade_at_be(self, mock_settings, rm):
        mock_settings.scale_in_require_be = True
        rm.register_trade("t1", "EUR_USD", 0.01)
        rm.mark_position_at_be("t1")
        assert rm.can_scale_in("EUR_USD") is True

    @patch("core.risk_manager.settings")
    def test_allowed_when_disabled(self, mock_settings, rm):
        mock_settings.scale_in_require_be = False
        rm.register_trade("t1", "EUR_USD", 0.01)
        assert rm.can_scale_in("EUR_USD") is True

    @patch("core.risk_manager.settings")
    def test_different_instrument_allowed(self, mock_settings, rm):
        mock_settings.scale_in_require_be = True
        rm.register_trade("t1", "EUR_USD", 0.01)
        assert rm.can_scale_in("GBP_USD") is True


# =====================================================================
# 10. Delta risk algorithm
# =====================================================================

class TestDeltaAlgorithm:
    @patch("core.risk_manager.settings")
    def test_no_bonus_when_disabled(self, mock_settings, rm):
        mock_settings.delta_enabled = False
        assert rm._get_delta_bonus(0.01) == 0.0

    @patch("core.risk_manager.settings")
    def test_no_bonus_when_no_accumulated_gain(self, mock_settings, rm):
        mock_settings.delta_enabled = True
        mock_settings.delta_parameter = 0.60
        mock_settings.delta_max_risk = 0.03
        rm._delta_accumulated_gain = 0.0
        assert rm._get_delta_bonus(0.01) == 0.0

    @patch("core.risk_manager.settings")
    def test_level_1_bonus(self, mock_settings, rm):
        mock_settings.delta_enabled = True
        mock_settings.delta_parameter = 0.60
        mock_settings.delta_max_risk = 0.03

        rm._max_historical_dd = 0.05  # delta_threshold = 0.05 * 0.60 = 0.03
        rm._delta_accumulated_gain = 0.035  # level = int(0.035 / 0.03) = 1

        bonus = rm._get_delta_bonus(0.01)
        # Level 1 target = 0.015, bonus = 0.015 - 0.01 = 0.005
        assert bonus == pytest.approx(0.005)

    @patch("core.risk_manager.settings")
    def test_level_2_bonus(self, mock_settings, rm):
        mock_settings.delta_enabled = True
        mock_settings.delta_parameter = 0.60
        mock_settings.delta_max_risk = 0.03

        rm._max_historical_dd = 0.05  # threshold = 0.03
        rm._delta_accumulated_gain = 0.07  # level = int(0.07/0.03) = 2

        bonus = rm._get_delta_bonus(0.01)
        # Level 2 target = 0.020, bonus = 0.020 - 0.01 = 0.01
        assert bonus == pytest.approx(0.01)

    @patch("core.risk_manager.settings")
    def test_level_capped_at_3(self, mock_settings, rm):
        mock_settings.delta_enabled = True
        mock_settings.delta_parameter = 0.60
        mock_settings.delta_max_risk = 0.05

        rm._max_historical_dd = 0.05  # threshold = 0.03
        rm._delta_accumulated_gain = 0.50  # level = min(16, 3) = 3

        bonus = rm._get_delta_bonus(0.01)
        # Level 3 target = 0.020 (capped per TradingLab max 2%), bonus = 0.020 - 0.01 = 0.01
        assert bonus == pytest.approx(0.01)

    @patch("core.risk_manager.settings")
    def test_bonus_capped_at_max_risk(self, mock_settings, rm):
        mock_settings.delta_enabled = True
        mock_settings.delta_parameter = 0.60
        mock_settings.delta_max_risk = 0.015  # cap: bonus max = 0.015 - 0.01 = 0.005

        rm._max_historical_dd = 0.05
        rm._delta_accumulated_gain = 0.07  # level 2 → target 0.02 → bonus 0.01

        bonus = rm._get_delta_bonus(0.01)
        # But capped to delta_max_risk - base = 0.015 - 0.01 = 0.005
        assert bonus == pytest.approx(0.005)

    def test_record_win_accumulates(self, rm):
        rm.record_trade_result("t1", "EUR_USD", 0.02)
        assert rm._delta_accumulated_gain == pytest.approx(0.02)
        assert len(rm._trade_history) == 1

    def test_record_loss_resets_accumulated(self, rm):
        rm.record_trade_result("t1", "EUR_USD", 0.02)
        rm.record_trade_result("t2", "EUR_USD", -0.01)
        # Graduated reduction: 0.02 + (-0.01) = 0.01 (not full reset to 0)
        assert rm._delta_accumulated_gain >= 0.0
        assert rm._delta_accumulated_gain == pytest.approx(0.01)

    def test_history_trimmed_at_200(self, rm):
        for i in range(210):
            rm.record_trade_result(f"t{i}", "EUR_USD", 0.001)
        # Trim happens when >200: keeps last 100, then 9 more appended = 109
        assert len(rm._trade_history) <= 110
        assert len(rm._trade_history) >= 100


# =====================================================================
# 11. Win rate calculation
# =====================================================================

class TestWinRate:
    def test_default_with_no_history(self, rm):
        assert rm._calculate_recent_win_rate() == 0.5

    def test_all_wins(self, rm):
        for i in range(10):
            rm._trade_history.append(TradeResult(f"t{i}", "EUR_USD", 0.01, True))
        assert rm._calculate_recent_win_rate() == 1.0

    def test_uses_last_50(self, rm):
        # 30 losses then 50 wins
        for i in range(30):
            rm._trade_history.append(TradeResult(f"l{i}", "EUR_USD", -0.01, False))
        for i in range(50):
            rm._trade_history.append(TradeResult(f"w{i}", "EUR_USD", 0.01, True))
        assert rm._calculate_recent_win_rate() == 1.0  # last 50 are all wins


# =====================================================================
# 12. Recovery math
# =====================================================================

class TestRecoveryMath:
    def test_zero_dd(self):
        assert RiskManager.calculate_recovery_pct(0.0) == 0.0

    def test_10pct_dd(self):
        assert RiskManager.calculate_recovery_pct(10) == pytest.approx(11.11, abs=0.01)

    def test_50pct_dd(self):
        assert RiskManager.calculate_recovery_pct(50) == pytest.approx(100.0)

    def test_100pct_dd_is_inf(self):
        assert RiskManager.calculate_recovery_pct(100) == float('inf')

    def test_negative_dd(self):
        assert RiskManager.calculate_recovery_pct(-5) == 0.0

    def test_recovery_table_values(self):
        """Verify the recovery table matches Alex's teaching."""
        for dd, expected in RiskManager.RECOVERY_TABLE:
            actual = RiskManager.calculate_recovery_pct(dd)
            assert actual == pytest.approx(expected, abs=0.01), \
                f"DD={dd}%: expected {expected}%, got {actual}%"


# =====================================================================
# 13. DD alert levels
# =====================================================================

class TestDDAlertLevels:
    def test_no_alert_below_5pct(self, rm):
        rm._peak_balance = 10000.0
        rm._current_balance = 9600.0  # 4% DD
        assert rm.get_dd_alert_level() is None

    def test_warning_at_5pct(self, rm):
        rm._peak_balance = 10000.0
        rm._current_balance = 9500.0  # 5% DD
        assert rm.get_dd_alert_level() == "warning"

    def test_high_at_10pct(self, rm):
        rm._peak_balance = 10000.0
        rm._current_balance = 9000.0  # 10% DD
        assert rm.get_dd_alert_level() == "high"

    def test_critical_at_15pct(self, rm):
        rm._peak_balance = 10000.0
        rm._current_balance = 8500.0  # 15% DD
        assert rm.get_dd_alert_level() == "critical"


# =====================================================================
# 14. Balance tracking
# =====================================================================

class TestBalanceTracking:
    def test_update_peak_on_new_high(self, rm):
        rm._peak_balance = 10000.0
        rm._current_balance = 10500.0

        # Simulate what update_balance_tracking does for peak
        if rm._current_balance > rm._peak_balance:
            rm._peak_balance = rm._current_balance
        assert rm._peak_balance == 10500.0

    def test_peak_unchanged_during_dd(self, rm):
        rm._peak_balance = 10000.0
        rm._current_balance = 9500.0

        if rm._current_balance > rm._peak_balance:
            rm._peak_balance = rm._current_balance
        assert rm._peak_balance == 10000.0

    def test_historical_max_dd_tracking(self, rm):
        rm._peak_balance = 10000.0
        rm._current_balance = 9200.0  # 8% DD
        rm._max_historical_dd = 0.0

        current_dd = rm.get_current_drawdown()
        rm._max_historical_dd = max(rm._max_historical_dd, current_dd)
        assert rm._max_historical_dd == pytest.approx(0.08)


# =====================================================================
# 15. Funded account limits
# =====================================================================

class TestFundedAccount:
    @patch("core.risk_manager.settings")
    def test_not_funded_always_allows(self, mock_settings, rm):
        mock_settings.funded_account_mode = False
        can_trade, reason = rm.check_funded_account_limits()
        assert can_trade is True
        assert reason == ""

    @patch("core.risk_manager.settings")
    def test_funded_blocks_on_zero_balance(self, mock_settings, rm):
        mock_settings.funded_account_mode = True
        rm._current_balance = 0.0
        can_trade, reason = rm.check_funded_account_limits()
        assert can_trade is False
        assert "balance" in reason.lower()

    @patch("core.risk_manager.settings")
    def test_funded_blocks_on_total_dd_exceeded(self, mock_settings, rm):
        mock_settings.funded_account_mode = True
        mock_settings.funded_evaluation_type = "standard"
        mock_settings.funded_max_total_dd = 0.10
        mock_settings.funded_max_daily_dd = 0.05

        rm._peak_balance = 10000.0
        rm._current_balance = 8900.0  # 11% DD > 10% limit

        can_trade, reason = rm.check_funded_account_limits()
        assert can_trade is False
        assert "total DD" in reason or "total dd" in reason.lower()

    @patch("core.risk_manager.settings")
    def test_funded_pnl_accumulates(self, mock_settings, rm):
        mock_settings.funded_account_mode = True
        rm.record_funded_pnl(-50.0)
        rm.record_funded_pnl(-30.0)
        assert rm._funded_daily_pnl == pytest.approx(-80.0)


# =====================================================================
# 16. Risk status reporting
# =====================================================================

class TestRiskStatus:
    @patch("core.risk_manager.settings")
    def test_status_contains_all_fields(self, mock_settings, rm):
        mock_settings.risk_day_trading = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.delta_max_risk = 0.02
        mock_settings.max_total_risk = 0.07

        status = rm.get_risk_status()

        expected_keys = [
            "current_drawdown", "peak_balance", "current_balance",
            "drawdown_method", "base_risk_day", "adjusted_risk_day",
            "delta_enabled", "delta_accumulated_gain", "total_active_risk",
            "max_total_risk", "recent_win_rate", "recent_trades",
            "recovery_pct_needed", "loss_dollars", "dd_alert_level",
            "recovery_table",
        ]
        for key in expected_keys:
            assert key in status, f"Missing key: {key}"

    @patch("core.risk_manager.settings")
    def test_status_values_correct(self, mock_settings, rm):
        mock_settings.risk_day_trading = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.delta_max_risk = 0.02
        mock_settings.max_total_risk = 0.07

        rm._peak_balance = 10000.0
        rm._current_balance = 9500.0

        status = rm.get_risk_status()
        assert status["current_drawdown"] == 5.0
        assert status["peak_balance"] == 10000.0
        assert status["current_balance"] == 9500.0
        assert status["loss_dollars"] == 500.0
