from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _build_engine():
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

        mock_settings.active_broker = "capital"
        mock_settings.capital_api_key = "test"
        mock_settings.capital_password = "test"
        mock_settings.capital_identifier = "test"
        mock_settings.capital_environment = "demo"
        mock_settings.capital_account_id = None
        mock_settings.position_management_style = "cp"
        mock_settings.trading_style = "day_trading"
        mock_settings.allow_partial_profits = False
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
        mock_settings.strict_recent_pink_context_hours = 72
        mock_settings.strict_mentoria_mode = True
        mock_settings.auto_hold_qualified_overnight_positions = True
        mock_settings.overnight_fee_rate_estimate = 0.0003
        mock_settings.overnight_fee_min_usd = 0.05
        mock_settings.overnight_hold_min_open_r = 0.25
        mock_settings.overnight_hold_min_remaining_r = 0.75
        mock_settings.auto_close_overnight_positions = True
        mock_settings.funded_account_mode = False
        mock_settings.funded_no_overnight = False

        mock_broker_fn.return_value = MagicMock()

        from core.trading_engine import TradingEngine

        engine = TradingEngine()
        engine.explanation_engine.STRATEGY_NAMES = {"BLACK": "BLACK"}
        return engine


def test_setup_reasoning_separates_analysis_quality_from_setup_confidence():
    engine = _build_engine()

    setup = SimpleNamespace(
        instrument="UK100_GBP",
        direction="BUY",
        reward_risk_ratio=4.09,
        strategy_variant="BLACK",
        _strategy_confidence=100.0,
    )
    analysis = SimpleNamespace(score=75.0)
    explanation = SimpleNamespace(
        overall_bias="BAJISTA",
        confidence_level="MEDIA",
        strategy_detected="BLACK",
        conditions_met=["Convergencia HTF/LTF confirmada"],
        conditions_missing=[],
        recommendation="Setup operable con cautela.",
    )

    reasoning = engine._build_setup_reasoning(setup, analysis, explanation)

    assert "Score de análisis: 75/100" in reasoning
    assert "Calidad del análisis: MEDIA" in reasoning
    assert "Confianza del setup: 100% (ALTA)" in reasoning
    assert "Nota: BLACK es estrategia CONTRATENDENCIA" in reasoning
