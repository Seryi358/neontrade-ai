"""Atlas config defaults aligned with TradingLab mentorship + 190.88 USD capital.

Covers the findings from 2026-04-17-findings-consolidated.md §A2, §A3, §M5.
Values that are intentional caps for small-capital safety (risk_swing 1%,
max_total_risk 5%) are kept — this test locks them in place with honest
comments sourced in config.py.
"""
import pytest

from config import settings, TRADING_PROFILES


class TestTradingStyle:
    def test_trading_style_is_day_trading(self):
        assert settings.trading_style == "day_trading"

    def test_scalping_disabled_by_default(self):
        assert settings.scalping_enabled is False

    def test_position_management_is_cp(self):
        assert settings.position_management_style == "cp"

    def test_discretion_is_zero(self):
        assert settings.discretion_pct == 0.0


class TestRisk:
    def test_risk_day_trading_is_1_percent(self):
        assert settings.risk_day_trading == 0.01

    def test_risk_scalping_is_half_percent(self):
        assert settings.risk_scalping == 0.005

    def test_risk_swing_capped_at_1_percent_for_small_capital(self):
        """Intentional cap for 190 USD capital. PDF pg.3 says 3% — we choose 1%."""
        assert settings.risk_swing == 0.01

    def test_max_total_risk_capped_at_5_percent_for_small_capital(self):
        """Intentional cap for 190 USD. PDF pg.3 says 7% — we choose 5%."""
        assert settings.max_total_risk == 0.05

    def test_correlated_risk_pct_is_075(self):
        assert settings.correlated_risk_pct == 0.0075


class TestOvertrading:
    def test_max_trades_per_day_is_3(self):
        assert settings.max_trades_per_day == 3

    def test_cooldown_minutes_is_120(self):
        assert settings.cooldown_minutes == 120

    def test_cooldown_after_2_consecutive_losses(self):
        assert settings.cooldown_after_consecutive_losses == 2


class TestBreakEven:
    def test_be_trigger_method_is_pct_to_tp1(self):
        """PDF pg.5 (autoritative): 'mitad del beneficio hasta TP1'.
        Alex oral says 'risk_distance'. PDF wins — it's consistent across all R:R."""
        assert settings.be_trigger_method == "pct_to_tp1"

    def test_be_trigger_pct_is_50_percent(self):
        assert settings.move_sl_to_be_pct_to_tp1 == 0.50


class TestDrawdown:
    def test_drawdown_method_is_fixed_levels(self):
        assert settings.drawdown_method == "fixed_levels"

    def test_drawdown_level_1_4_12_percent(self):
        assert settings.drawdown_level_1 == pytest.approx(0.0412)
        assert settings.drawdown_risk_1 == 0.0075

    def test_drawdown_level_2_6_18_percent(self):
        assert settings.drawdown_level_2 == pytest.approx(0.0618)
        assert settings.drawdown_risk_2 == 0.005

    def test_drawdown_level_3_8_23_percent(self):
        assert settings.drawdown_level_3 == pytest.approx(0.0823)
        assert settings.drawdown_risk_3 == 0.0025

    def test_drawdown_min_risk_floor(self):
        assert settings.drawdown_min_risk == 0.0025


class TestLeverageCapitalCom:
    """Leverage activos en Capital.com para la cuenta de Sergio (verificado 2026-04-17)."""

    def test_leverage_forex(self):
        assert settings.leverage_forex == 100

    def test_leverage_indices(self):
        assert settings.leverage_indices == 100

    def test_leverage_commodities(self):
        assert settings.leverage_commodities == 100

    def test_leverage_stocks(self):
        assert settings.leverage_stocks == 20

    def test_leverage_crypto(self):
        assert settings.leverage_crypto == 20

    def test_leverage_bonds_and_rates(self):
        # bonds & interest rates share 200:1 in Capital.com
        assert settings.leverage_bonds == 200


class TestTradingHours:
    def test_start_hour_07_utc(self):
        assert settings.trading_start_hour == 7

    def test_end_hour_21_utc(self):
        assert settings.trading_end_hour == 21

    def test_close_before_friday_20(self):
        assert settings.close_before_friday_hour == 20

    def test_no_new_trades_friday_18(self):
        assert settings.no_new_trades_friday_hour == 18


class TestNewsFilter:
    def test_avoid_news_before_30_min(self):
        assert settings.avoid_news_minutes_before == 30

    def test_avoid_news_after_30_min_for_day_trading(self):
        """Audit M5: originally 15 min is too short for NFP/CPI/FOMC volatility windows."""
        assert settings.avoid_news_minutes_after == 30


class TestTradingProfiles:
    def test_tradinglab_profile_risk_swing_comment_honest(self):
        """Comment should reflect Alex's oral preference, not claim NON-NEGOTIABLE."""
        profile = TRADING_PROFILES["tradinglab_recommended"]
        assert profile["settings"]["risk_swing"] == 0.01

    def test_tradinglab_profile_max_total_risk_pdf_7_percent(self):
        """Profile tradinglab_recommended honors the PDF's 7% (vs global default 5%)."""
        profile = TRADING_PROFILES["tradinglab_recommended"]
        assert profile["settings"]["max_total_risk"] == 0.07

    def test_conservative_profile_risk_swing_honest_comment(self):
        """Comment should NOT claim NON-NEGOTIABLE per mentorship (that's false)."""
        profile = TRADING_PROFILES["conservative"]
        assert profile["settings"]["risk_swing"] == 0.01
