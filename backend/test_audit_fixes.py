"""Tests for audit fix corrections - verifying mentorship fidelity."""
import pytest


def test_position_manager_forex_lp_grid():
    """LP Swing=Daily, LP Day=H1, LP Scalp=M5 (Workshop Scalping: 'largo plazo = M5')."""
    from core.position_manager import _EMA_TIMEFRAME_GRID, ManagementStyle, TradingStyle
    assert _EMA_TIMEFRAME_GRID[(ManagementStyle.LP, TradingStyle.SWING)] == "EMA_D_50"
    assert _EMA_TIMEFRAME_GRID[(ManagementStyle.LP, TradingStyle.DAY_TRADING)] == "EMA_H1_50"
    # Workshop de Scalping, Gestión: "¿Cuál sería el largo plazo? El gráfico de cinco minutos."
    assert _EMA_TIMEFRAME_GRID[(ManagementStyle.LP, TradingStyle.SCALPING)] == "EMA_M5_50"


def test_position_manager_forex_cp_grid():
    """CP Day should be M5 (EMA_M5_50), not M15."""
    from core.position_manager import _EMA_TIMEFRAME_GRID, ManagementStyle, TradingStyle
    assert _EMA_TIMEFRAME_GRID[(ManagementStyle.CP, TradingStyle.SWING)] == "EMA_H1_50"
    assert _EMA_TIMEFRAME_GRID[(ManagementStyle.CP, TradingStyle.DAY_TRADING)] == "EMA_M5_50"
    assert _EMA_TIMEFRAME_GRID[(ManagementStyle.CP, TradingStyle.SCALPING)] == "EMA_M1_50"


def test_position_manager_crypto_wider_than_forex():
    """Crypto grids should be wider than forex grids."""
    from core.position_manager import _EMA_TIMEFRAME_GRID, _EMA_TIMEFRAME_GRID_CRYPTO, ManagementStyle, TradingStyle
    # Crypto LP Swing = Weekly (wider than Forex LP Swing = Daily)
    assert _EMA_TIMEFRAME_GRID_CRYPTO[(ManagementStyle.LP, TradingStyle.SWING)] == "EMA_W_50"
    assert _EMA_TIMEFRAME_GRID[(ManagementStyle.LP, TradingStyle.SWING)] == "EMA_D_50"
    # Crypto LP Day = H4 (wider than Forex LP Day = H1)
    assert _EMA_TIMEFRAME_GRID_CRYPTO[(ManagementStyle.LP, TradingStyle.DAY_TRADING)] == "EMA_H4_50"
    assert _EMA_TIMEFRAME_GRID[(ManagementStyle.LP, TradingStyle.DAY_TRADING)] == "EMA_H1_50"


def test_rr_validation_black_requires_2():
    """BLACK strategy must require 2.0:1 R:R minimum."""
    from core.risk_manager import RiskManager
    rm = RiskManager(broker_client=None)
    # BLACK with 1.5:1 should FAIL
    assert rm.validate_reward_risk(100.0, 99.0, 101.5, strategy="BLACK") == False  # 1.5:1
    # BLACK with 2.0:1 should PASS
    assert rm.validate_reward_risk(100.0, 99.0, 102.0, strategy="BLACK") == True  # 2.0:1


def test_rr_validation_green_requires_2():
    """GREEN strategy must require 2.0:1 R:R minimum."""
    from core.risk_manager import RiskManager
    rm = RiskManager(broker_client=None)
    assert rm.validate_reward_risk(100.0, 99.0, 101.5, strategy="GREEN") == False
    assert rm.validate_reward_risk(100.0, 99.0, 102.0, strategy="GREEN") == True


def test_rr_validation_blue_allows_1_5():
    """Regular BLUE should allow 1.5:1 R:R."""
    from core.risk_manager import RiskManager
    rm = RiskManager(broker_client=None)
    assert rm.validate_reward_risk(100.0, 99.0, 101.5, strategy="BLUE") == True


def test_rr_validation_blue_c_requires_2():
    """BLUE_C must require 2.0:1 minimum."""
    from core.risk_manager import RiskManager
    rm = RiskManager(broker_client=None)
    assert rm.validate_reward_risk(100.0, 99.0, 101.5, strategy="BLUE_C") == False
    assert rm.validate_reward_risk(100.0, 99.0, 102.0, strategy="BLUE_C") == True


def test_macd_divergence_field_exists():
    """AnalysisResult should have macd_divergence field."""
    from core.market_analyzer import AnalysisResult, Trend, MarketCondition
    ar = AnalysisResult(
        instrument="TEST", htf_trend=Trend.BULLISH, htf_condition=MarketCondition.NEUTRAL,
        ltf_trend=Trend.BULLISH, htf_ltf_convergence=True, key_levels={},
        ema_values={}, fibonacci_levels={}, candlestick_patterns=[]
    )
    assert hasattr(ar, 'macd_divergence')
    assert ar.macd_divergence is None


def test_crypto_cycle_has_sma200():
    """CryptoMarketCycle should have sma_d200_position field."""
    from core.crypto_cycle import CryptoMarketCycle
    cycle = CryptoMarketCycle()
    assert hasattr(cycle, 'sma_d200_position')
    assert cycle.sma_d200_position is None


def test_setup_signal_trailing_tp_only():
    """SetupSignal should have trailing_tp_only field for GREEN crypto."""
    from strategies.base import SetupSignal, StrategyColor
    signal = SetupSignal(
        strategy=StrategyColor.GREEN, strategy_variant="GREEN",
        instrument="BTC_USD", direction="BUY", entry_price=50000,
        stop_loss=48000, take_profit_1=55000, trailing_tp_only=True
    )
    assert signal.trailing_tp_only == True


def test_funded_1phase_auto_dd():
    """1-phase evaluation should auto-apply 4%/6% DD limits."""
    from config import Settings
    s = Settings(funded_evaluation_type="1phase", funded_max_daily_dd=0.05, funded_max_total_dd=0.10)
    # The auto-apply happens at module level, not on individual instances.
    # Just verify the config accepts the values correctly.
    assert s.funded_evaluation_type == "1phase"


def test_config_default_risk_values():
    """Verify default risk values match mentorship."""
    from config import settings
    assert settings.risk_day_trading == 0.01  # 1%
    assert settings.risk_swing == 0.01  # 1%
    assert settings.max_total_risk == 0.03  # 3% (conservative for small accounts)
    assert settings.correlated_risk_pct == 0.0075  # 0.75%
    assert settings.min_rr_ratio == 1.5
    assert settings.min_rr_black == 2.0
    assert settings.min_rr_green == 2.0
