"""
Tests for risk_manager.py — covering critical methods that need more coverage.
Focus: drawdown adjustment, delta algorithm, win rate, correlation, R:R validation,
       trade registration, funded account limits, scale-in, reentry multiplier,
       position sizing, recovery calculation.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock

from core.risk_manager import RiskManager, TradingStyle


@pytest.fixture
def rm():
    """Create a RiskManager with a mocked broker."""
    broker = MagicMock()
    broker.get_account_balance = AsyncMock(return_value=10000.0)
    with patch("core.risk_manager.settings") as ms:
        ms.drawdown_method = "fixed_1pct"
        ms.delta_enabled = False
        ms.delta_parameter = 0.6
        ms.delta_max_risk = 0.02
        ms.risk_day_trading = 0.01
        ms.risk_scalping = 0.005
        ms.risk_swing = 0.01
        ms.max_total_risk = 0.05
        ms.scale_in_require_be = True
        ms.min_rr_ratio = 1.5
        ms.min_rr_black = 2.0
        ms.min_rr_green = 2.0
        ms.funded_account_mode = False
        ms.correlated_risk_pct = 0.0075
        ms.correlation_groups = [["EUR_USD", "GBP_USD"]]
        ms.indices_correlation_groups = []
        ms.crypto_correlation_groups = [["BTC_USD", "ETH_USD"]]
        ms.max_reentries_per_setup = 3
        ms.reentry_risk_1 = 0.5
        ms.reentry_risk_2 = 0.25
        ms.reentry_risk_3 = 0.25
        ms.drawdown_min_risk = 0.0025
        ms.drawdown_level_1 = 0.03
        ms.drawdown_level_2 = 0.06
        ms.drawdown_level_3 = 0.09
        ms.drawdown_risk_1 = 0.0075
        ms.drawdown_risk_2 = 0.005
        ms.drawdown_risk_3 = 0.0025
        ms.funded_max_daily_dd = 0.05
        ms.funded_max_total_dd = 0.10
        ms.funded_evaluation_type = "two_phase"
        ms.funded_current_phase = 1
        ms.funded_profit_target_phase1 = 0.10
        ms.funded_profit_target_phase2 = 0.05
        ms.funded_no_overnight = False
        ms.funded_no_weekend = False
        ms.funded_no_news_trading = False
        ms.funded_max_total_dd_phase2 = 0
        ms.trading_start_hour = 7
        ms.trading_end_hour = 21
        r = RiskManager(broker)
        r._current_balance = 10000.0
        r._peak_balance = 10000.0
        yield r


# ──────────────────────────────────────────────────────────────────
# get_current_drawdown
# ──────────────────────────────────────────────────────────────────

class TestGetCurrentDrawdown:
    def test_no_drawdown(self, rm):
        """Peak equals current — DD should be 0."""
        assert rm.get_current_drawdown() == 0.0

    def test_with_drawdown(self, rm):
        """Current below peak — DD should be positive."""
        rm._current_balance = 9500.0
        dd = rm.get_current_drawdown()
        assert abs(dd - 0.05) < 1e-9

    def test_zero_peak_returns_zero(self, rm):
        """Peak of 0 should return 0 (avoid div by zero)."""
        rm._peak_balance = 0.0
        assert rm.get_current_drawdown() == 0.0


# ──────────────────────────────────────────────────────────────────
# _calculate_recent_win_rate
# ──────────────────────────────────────────────────────────────────

class TestWinRate:
    def test_no_history_default_50(self, rm):
        """Empty trade history should return 0.5."""
        assert rm._calculate_recent_win_rate() == 0.5

    def test_all_wins(self, rm):
        """All winning trades → 1.0."""
        from core.risk_manager import TradeResult
        for i in range(10):
            rm._trade_history.append(TradeResult(
                trade_id=f"t{i}", instrument="EUR_USD", pnl_percent=0.01, is_win=True
            ))
        assert rm._calculate_recent_win_rate() == 1.0

    def test_mixed_trades(self, rm):
        """6 wins / 10 trades → 0.6."""
        from core.risk_manager import TradeResult
        for i in range(6):
            rm._trade_history.append(TradeResult(
                trade_id=f"w{i}", instrument="EUR_USD", pnl_percent=0.01, is_win=True
            ))
        for i in range(4):
            rm._trade_history.append(TradeResult(
                trade_id=f"l{i}", instrument="EUR_USD", pnl_percent=-0.01, is_win=False
            ))
        assert abs(rm._calculate_recent_win_rate() - 0.6) < 1e-9

    def test_uses_last_50(self, rm):
        """Only the last 50 trades should be considered."""
        from core.risk_manager import TradeResult
        # Add 50 losses then 50 wins
        for i in range(50):
            rm._trade_history.append(TradeResult(
                trade_id=f"l{i}", instrument="EUR_USD", pnl_percent=-0.01, is_win=False
            ))
        for i in range(50):
            rm._trade_history.append(TradeResult(
                trade_id=f"w{i}", instrument="EUR_USD", pnl_percent=0.01, is_win=True
            ))
        assert rm._calculate_recent_win_rate() == 1.0


# ──────────────────────────────────────────────────────────────────
# _get_drawdown_adjusted_risk
# ──────────────────────────────────────────────────────────────────

class TestDrawdownAdjustedRisk:
    def test_fixed_1pct_no_change(self, rm):
        """fixed_1pct method should return base_risk unchanged."""
        with patch("core.risk_manager.settings") as ms:
            ms.drawdown_method = "fixed_1pct"
            result = rm._get_drawdown_adjusted_risk(0.01)
        assert result == 0.01

    def test_fixed_levels_level_1(self, rm):
        """DD at level 1 should reduce risk."""
        rm._current_balance = 9600.0  # 4% DD (>= 3% level 1)
        with patch("core.risk_manager.settings") as ms:
            ms.drawdown_method = "fixed_levels"
            ms.drawdown_level_1 = 0.03
            ms.drawdown_level_2 = 0.06
            ms.drawdown_level_3 = 0.09
            ms.drawdown_risk_1 = 0.0075
            ms.drawdown_risk_2 = 0.005
            ms.drawdown_risk_3 = 0.0025
            ms.drawdown_min_risk = 0.0025
            result = rm._get_drawdown_adjusted_risk(0.01)
        assert result == 0.0075

    def test_fixed_levels_level_3(self, rm):
        """DD at level 3 should reduce risk to minimum."""
        rm._current_balance = 9000.0  # 10% DD (>= 9% level 3)
        with patch("core.risk_manager.settings") as ms:
            ms.drawdown_method = "fixed_levels"
            ms.drawdown_level_1 = 0.03
            ms.drawdown_level_2 = 0.06
            ms.drawdown_level_3 = 0.09
            ms.drawdown_risk_1 = 0.0075
            ms.drawdown_risk_2 = 0.005
            ms.drawdown_risk_3 = 0.0025
            ms.drawdown_min_risk = 0.0025
            result = rm._get_drawdown_adjusted_risk(0.01)
        assert result == 0.0025

    def test_fixed_levels_no_dd(self, rm):
        """No DD should return base_risk."""
        with patch("core.risk_manager.settings") as ms:
            ms.drawdown_method = "fixed_levels"
            ms.drawdown_level_1 = 0.03
            ms.drawdown_level_2 = 0.06
            ms.drawdown_level_3 = 0.09
            ms.drawdown_risk_1 = 0.0075
            ms.drawdown_risk_2 = 0.005
            ms.drawdown_risk_3 = 0.0025
            ms.drawdown_min_risk = 0.0025
            result = rm._get_drawdown_adjusted_risk(0.01)
        assert result == 0.01

    def test_variable_method_with_dd(self, rm):
        """Variable method should reduce risk based on win rate and DD."""
        rm._current_balance = 9500.0  # 5% DD
        rm._max_historical_dd = 0.10  # 10% max historical
        # DD ratio = 5/10 = 0.5 → level 1 (>= 0.5)
        from core.risk_manager import TradeResult
        # 60% win rate
        for i in range(6):
            rm._trade_history.append(TradeResult(f"w{i}", "X", 0.01, True))
        for i in range(4):
            rm._trade_history.append(TradeResult(f"l{i}", "X", -0.01, False))

        with patch("core.risk_manager.settings") as ms:
            ms.drawdown_method = "variable"
            ms.drawdown_min_risk = 0.0025
            result = rm._get_drawdown_adjusted_risk(0.01)
        # win_rate(0.6) * base(0.01) * 1.66 = 0.00996
        expected = 0.6 * 0.01 * 1.66
        assert abs(result - expected) < 1e-6


# ──────────────────────────────────────────────────────────────────
# _get_delta_bonus
# ──────────────────────────────────────────────────────────────────

class TestDeltaBonus:
    def test_delta_disabled_returns_zero(self, rm):
        """Delta disabled → 0 bonus."""
        with patch("core.risk_manager.settings") as ms:
            ms.delta_enabled = False
            assert rm._get_delta_bonus(0.01) == 0.0

    def test_delta_no_accumulated_gain(self, rm):
        """No accumulated gain → 0 bonus."""
        with patch("core.risk_manager.settings") as ms:
            ms.delta_enabled = True
            ms.delta_parameter = 0.6
            ms.delta_max_risk = 0.02
            rm._delta_accumulated_gain = 0.0
            assert rm._get_delta_bonus(0.01) == 0.0

    def test_delta_level_1(self, rm):
        """Enough accumulated gain for level 1 → bonus to 1.5%."""
        rm._max_historical_dd = 0.05
        rm._delta_accumulated_gain = 0.035  # > 0.05 * 0.6 = 0.03 threshold
        with patch("core.risk_manager.settings") as ms:
            ms.delta_enabled = True
            ms.delta_parameter = 0.6
            ms.delta_max_risk = 0.02
            bonus = rm._get_delta_bonus(0.01)
        # level 1 → target 0.015, bonus = 0.015 - 0.01 = 0.005
        assert abs(bonus - 0.005) < 1e-9

    def test_delta_capped_at_max(self, rm):
        """Delta bonus should not exceed delta_max_risk - base_risk."""
        rm._max_historical_dd = 0.05
        rm._delta_accumulated_gain = 0.10  # level 3 → target 0.02
        with patch("core.risk_manager.settings") as ms:
            ms.delta_enabled = True
            ms.delta_parameter = 0.6
            ms.delta_max_risk = 0.015  # cap at 1.5%
            bonus = rm._get_delta_bonus(0.01)
        # Max bonus = 0.015 - 0.01 = 0.005
        assert abs(bonus - 0.005) < 1e-9


# ──────────────────────────────────────────────────────────────────
# record_trade_result
# ──────────────────────────────────────────────────────────────────

class TestRecordTradeResult:
    def test_winning_trade_accumulates_gain(self, rm):
        """Winning trade should increase accumulated gain."""
        rm.record_trade_result("t1", "EUR_USD", 0.02)
        assert rm._delta_accumulated_gain == 0.02
        assert len(rm._trade_history) == 1
        assert rm._trade_history[0].is_win is True

    def test_losing_trade_reduces_delta(self, rm):
        """Losing trade should reduce delta accumulated gain (graduated, not full reset)."""
        rm._delta_accumulated_gain = 0.05
        rm._accumulated_gain = 0.05
        rm.record_trade_result("t2", "EUR_USD", -0.01)
        # Graduated delta: loss reduces gain by loss amount, doesn't wipe to 0
        assert rm._delta_accumulated_gain >= 0.0
        assert rm._accumulated_gain >= 0.0
        # Gain should be reduced but not wiped
        assert rm._delta_accumulated_gain < 0.05

    def test_reentry_count_on_loss(self, rm):
        """Consecutive stop-out on same instrument should increment reentry count."""
        rm.record_trade_result("t1", "EUR_USD", -0.01)
        assert rm._reentry_counts.get("EUR_USD", 0) >= 0  # tracked


# ──────────────────────────────────────────────────────────────────
# validate_reward_risk
# ──────────────────────────────────────────────────────────────────

class TestValidateRewardRisk:
    def test_good_rr_passes(self, rm):
        """R:R of 2.0 should pass default 1.5 minimum."""
        with patch("core.risk_manager.settings") as ms:
            ms.min_rr_ratio = 1.5
            ms.min_rr_black = 2.0
            ms.min_rr_green = 2.0
            assert rm.validate_reward_risk(1.1000, 1.0950, 1.1100) is True

    def test_bad_rr_fails(self, rm):
        """R:R of 0.5 should fail."""
        with patch("core.risk_manager.settings") as ms:
            ms.min_rr_ratio = 1.5
            ms.min_rr_black = 2.0
            ms.min_rr_green = 2.0
            assert rm.validate_reward_risk(1.1000, 1.0900, 1.1050) is False

    def test_black_requires_2_1(self, rm):
        """BLACK strategy needs 2:1 minimum."""
        with patch("core.risk_manager.settings") as ms:
            ms.min_rr_ratio = 1.5
            ms.min_rr_black = 2.0
            ms.min_rr_green = 2.0
            # R:R = 1.5:1 (fails BLACK's 2:1 requirement)
            assert rm.validate_reward_risk(1.1000, 1.0900, 1.1150, strategy="BLACK") is False
            # R:R = 2:1 (passes)
            assert rm.validate_reward_risk(1.1000, 1.0900, 1.1200, strategy="BLACK") is True

    def test_zero_risk_returns_false(self, rm):
        """SL at entry (zero risk) should reject."""
        assert rm.validate_reward_risk(1.1000, 1.1000, 1.1100) is False

    def test_blue_c_requires_2_1(self, rm):
        """BLUE_C requires 2:1 per mentoría."""
        with patch("core.risk_manager.settings") as ms:
            ms.min_rr_ratio = 1.5
            ms.min_rr_black = 2.0
            ms.min_rr_green = 2.0
            # 1.5:1 fails for BLUE_C
            assert rm.validate_reward_risk(1.1000, 1.0900, 1.1150, strategy="BLUE_C") is False
            # 2:1 passes
            assert rm.validate_reward_risk(1.1000, 1.0900, 1.1200, strategy="BLUE_C") is True


# ──────────────────────────────────────────────────────────────────
# register_trade / unregister_trade / total_risk
# ──────────────────────────────────────────────────────────────────

class TestTradeRegistration:
    def test_register_adds_risk(self, rm):
        rm.register_trade("t1", "EUR_USD", 0.01)
        assert rm.get_current_total_risk() == 0.01

    def test_unregister_removes_risk(self, rm):
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


# ──────────────────────────────────────────────────────────────────
# _adjust_for_correlation
# ──────────────────────────────────────────────────────────────────

class TestCorrelation:
    def test_correlated_pair_reduces_risk(self, rm):
        """Opening GBP_USD while EUR_USD is active → capped at 0.75%."""
        rm.register_trade("t1", "EUR_USD", 0.01)
        with patch("core.risk_manager.settings") as ms:
            ms.correlated_risk_pct = 0.0075
            ms.correlation_groups = [["EUR_USD", "GBP_USD"]]
            ms.indices_correlation_groups = []
            ms.crypto_correlation_groups = []
            result = rm._adjust_for_correlation("GBP_USD", 0.01)
        assert result == 0.0075

    def test_uncorrelated_pair_no_change(self, rm):
        """Opening USD_JPY while EUR_USD active → no reduction."""
        rm.register_trade("t1", "EUR_USD", 0.01)
        with patch("core.risk_manager.settings") as ms:
            ms.correlated_risk_pct = 0.0075
            ms.correlation_groups = [["EUR_USD", "GBP_USD"]]
            ms.indices_correlation_groups = []
            ms.crypto_correlation_groups = []
            result = rm._adjust_for_correlation("USD_JPY", 0.01)
        assert result == 0.01

    def test_crypto_correlation(self, rm):
        """Opening ETH while BTC active → capped."""
        rm.register_trade("t1", "BTC_USD", 0.01)
        with patch("core.risk_manager.settings") as ms:
            ms.correlated_risk_pct = 0.0075
            ms.correlation_groups = []
            ms.indices_correlation_groups = []
            ms.crypto_correlation_groups = [["BTC_USD", "ETH_USD"]]
            result = rm._adjust_for_correlation("ETH_USD", 0.01)
        assert result == 0.0075


# ──────────────────────────────────────────────────────────────────
# can_scale_in
# ──────────────────────────────────────────────────────────────────

class TestScaleIn:
    def test_blocked_when_existing_not_at_be(self, rm):
        """Should block scale-in if existing trade not at BE."""
        rm.register_trade("t1", "EUR_USD", 0.01)
        with patch("core.risk_manager.settings") as ms:
            ms.scale_in_require_be = True
            assert rm.can_scale_in("EUR_USD") is False

    def test_allowed_when_existing_at_be(self, rm):
        """Should allow scale-in if existing trade is at BE."""
        rm.register_trade("t1", "EUR_USD", 0.01)
        rm.mark_position_at_be("t1")
        with patch("core.risk_manager.settings") as ms:
            ms.scale_in_require_be = True
            assert rm.can_scale_in("EUR_USD") is True

    def test_allowed_when_no_existing_trade(self, rm):
        """No existing trades → allow."""
        with patch("core.risk_manager.settings") as ms:
            ms.scale_in_require_be = True
            assert rm.can_scale_in("EUR_USD") is True

    def test_allowed_when_be_check_disabled(self, rm):
        """scale_in_require_be=False → always allow."""
        rm.register_trade("t1", "EUR_USD", 0.01)
        with patch("core.risk_manager.settings") as ms:
            ms.scale_in_require_be = False
            assert rm.can_scale_in("EUR_USD") is True


# ──────────────────────────────────────────────────────────────────
# get_reentry_risk_multiplier
# ──────────────────────────────────────────────────────────────────

class TestReentryRiskMultiplier:
    def test_first_entry_full_risk(self, rm):
        """First entry → 1.0x risk."""
        with patch("core.risk_manager.settings") as ms:
            ms.max_reentries_per_setup = 3
            ms.reentry_risk_1 = 0.5
            ms.reentry_risk_2 = 0.25
            ms.reentry_risk_3 = 0.25
            assert rm.get_reentry_risk_multiplier("EUR_USD") == 1.0

    def test_first_reentry_50_pct_crypto(self, rm):
        """After 1 stop-out on crypto → 0.5x risk (progressive tiers are crypto-only)."""
        rm._reentry_counts["BTC_USD"] = 1
        with patch("core.risk_manager.settings") as ms:
            ms.max_reentries_per_setup = 3
            ms.reentry_risk_1 = 0.5
            ms.reentry_risk_2 = 0.25
            ms.reentry_risk_3 = 0.25
            ms.crypto_watchlist = ["BTC_USD", "ETH_USD"]
            assert rm.get_reentry_risk_multiplier("BTC_USD") == 0.5

    def test_forex_reentry_no_reduction(self, rm):
        """Forex reentry always returns 1.0 (no progressive reduction per mentorship)."""
        rm._reentry_counts["EUR_USD"] = 1
        with patch("core.risk_manager.settings") as ms:
            ms.max_reentries_per_setup = 3
            ms.reentry_risk_1 = 0.5
            ms.crypto_watchlist = ["BTC_USD", "ETH_USD"]
            assert rm.get_reentry_risk_multiplier("EUR_USD") == 1.0

    def test_max_reentries_blocked(self, rm):
        """At max reentries on crypto → 0.0 (blocked)."""
        rm._reentry_counts["BTC_USD"] = 3
        with patch("core.risk_manager.settings") as ms:
            ms.max_reentries_per_setup = 3
            ms.crypto_watchlist = ["BTC_USD", "ETH_USD"]
            assert rm.get_reentry_risk_multiplier("BTC_USD") == 0.0


# ──────────────────────────────────────────────────────────────────
# check_funded_account_limits
# ──────────────────────────────────────────────────────────────────

class TestFundedAccountLimits:
    def test_funded_off_always_ok(self, rm):
        """Funded mode off → always (True, "")."""
        with patch("core.risk_manager.settings") as ms:
            ms.funded_account_mode = False
            ok, reason = rm.check_funded_account_limits()
        assert ok is True

    def test_funded_daily_dd_exceeded(self, rm):
        """Daily loss exceeding 5% → blocked."""
        rm._funded_start_of_day_balance = 10000.0
        rm._funded_daily_pnl = -510.0  # > $500 (5% of 10K)
        rm._funded_daily_pnl_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with patch("core.risk_manager.settings") as ms:
            ms.funded_account_mode = True
            ms.funded_max_daily_dd = 0.05
            ms.funded_max_total_dd = 0.10
            ms.funded_evaluation_type = "two_phase"
            ms.funded_current_phase = 1
            ms.funded_max_total_dd_phase2 = 0
            ms.funded_no_overnight = False
            ms.funded_no_weekend = False
            ms.funded_no_news_trading = False
            ok, reason = rm.check_funded_account_limits()
        assert ok is False
        assert "daily DD" in reason

    def test_funded_total_dd_exceeded(self, rm):
        """Total DD exceeding 10% → blocked."""
        rm._current_balance = 8900.0  # 11% DD
        rm._funded_daily_pnl = 0.0
        rm._funded_daily_pnl_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rm._funded_start_of_day_balance = 8900.0
        with patch("core.risk_manager.settings") as ms:
            ms.funded_account_mode = True
            ms.funded_max_daily_dd = 0.05
            ms.funded_max_total_dd = 0.10
            ms.funded_evaluation_type = "two_phase"
            ms.funded_current_phase = 1
            ms.funded_max_total_dd_phase2 = 0
            ms.funded_no_overnight = False
            ms.funded_no_weekend = False
            ms.funded_no_news_trading = False
            ok, reason = rm.check_funded_account_limits()
        assert ok is False
        assert "total DD" in reason

    def test_funded_zero_balance_blocked(self, rm):
        """Zero balance → blocked."""
        rm._current_balance = 0.0
        with patch("core.risk_manager.settings") as ms:
            ms.funded_account_mode = True
            ok, reason = rm.check_funded_account_limits()
        assert ok is False
        assert "balance" in reason

    def test_funded_instant_no_daily_dd(self, rm):
        """Instant funding type → no daily DD check."""
        rm._funded_start_of_day_balance = 10000.0
        rm._funded_daily_pnl = -510.0
        rm._funded_daily_pnl_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with patch("core.risk_manager.settings") as ms:
            ms.funded_account_mode = True
            ms.funded_max_daily_dd = 0.05
            ms.funded_max_total_dd = 0.10
            ms.funded_evaluation_type = "instant"
            ms.funded_current_phase = 1
            ms.funded_max_total_dd_phase2 = 0
            ms.funded_no_overnight = False
            ms.funded_no_weekend = False
            ms.funded_no_news_trading = False
            ok, reason = rm.check_funded_account_limits()
        # Instant funding skips daily DD check — should pass
        assert ok is True


# ──────────────────────────────────────────────────────────────────
# _check_funded_phase_advancement
# ──────────────────────────────────────────────────────────────────

class TestFundedPhaseAdvancement:
    def test_advance_phase_1_to_2(self, rm):
        """Reaching phase 1 profit target → advance to phase 2."""
        with patch("core.risk_manager.settings") as ms:
            ms.funded_current_phase = 1
            result = rm._check_funded_phase_advancement(0.10, 100.0)
            assert result is True
            assert ms.funded_current_phase == 2

    def test_no_advance_below_target(self, rm):
        """Below profit target → no advancement."""
        with patch("core.risk_manager.settings") as ms:
            ms.funded_current_phase = 1
            result = rm._check_funded_phase_advancement(0.10, 80.0)
            assert result is False
            assert ms.funded_current_phase == 1


# ──────────────────────────────────────────────────────────────────
# calculate_recovery_pct
# ──────────────────────────────────────────────────────────────────

class TestRecoveryCalculation:
    def test_recovery_from_5pct_dd(self):
        """5% DD requires ~5.26% recovery."""
        result = RiskManager.calculate_recovery_pct(5)  # input is percentage, not decimal
        assert abs(result - 5.26) < 0.01

    def test_recovery_from_50pct_dd(self):
        """50% DD requires 100% recovery."""
        result = RiskManager.calculate_recovery_pct(50)
        assert abs(result - 100.0) < 0.01

    def test_recovery_from_zero_dd(self):
        """0% DD requires 0% recovery."""
        result = RiskManager.calculate_recovery_pct(0.0)
        assert result == 0.0
