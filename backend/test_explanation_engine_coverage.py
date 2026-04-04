"""
Tests for explanation_engine.py — covering explanation generation logic.
Focus: confidence levels, bias detection, risk assessment, recommendations,
       strategy steps, entry/SL/TP explanations, notification formatting.
"""

import pytest
from unittest.mock import MagicMock
from core.explanation_engine import (
    ExplanationEngine, StrategyExplanation, TimeframeExplanation,
)
from core.market_analyzer import Trend, MarketCondition


@pytest.fixture
def engine():
    return ExplanationEngine()


def _mock_analysis(
    htf_trend=Trend.BULLISH,
    htf_condition=MarketCondition.NEUTRAL,
    ltf_trend=Trend.BULLISH,
    convergence=True,
    score=70.0,
    current_price=1.1050,
    supports=None,
    resistances=None,
    fib_levels=None,
    patterns=None,
    ema_values=None,
):
    """Build a mock AnalysisResult."""
    m = MagicMock()
    m.htf_trend = htf_trend
    m.htf_condition = htf_condition
    m.ltf_trend = ltf_trend
    m.htf_ltf_convergence = convergence
    m.score = score
    m.current_price = current_price
    m.key_levels = {
        "supports": supports or [1.0950, 1.0900],
        "resistances": resistances or [1.1100, 1.1150],
    }
    m.fibonacci_levels = fib_levels or {"0.382": 1.0980, "0.618": 1.0940}
    m.candlestick_patterns = patterns or []
    m.ema_values = ema_values or {"EMA_H4_50": 1.0990, "EMA_H1_50": 1.1010}
    m.elliott_wave_detail = {}
    return m


def _mock_signal(
    strategy_value="BLUE",
    direction="BUY",
    entry=1.1000,
    sl=1.0950,
    tp1=1.1100,
    tp_max=1.1200,
    confidence=75.0,
):
    """Build a mock SetupSignal."""
    s = MagicMock()
    s.strategy.value = strategy_value
    s.direction = direction
    s.instrument = "EUR_USD"
    s.entry_price = entry
    s.stop_loss = sl
    s.take_profit_1 = tp1
    s.take_profit_max = tp_max
    s.confidence = confidence
    return s


# ──────────────────────────────────────────────────────────────────
# generate_full_analysis — overall structure
# ──────────────────────────────────────────────────────────────────

class TestGenerateFullAnalysis:
    def test_returns_strategy_explanation(self, engine):
        analysis = _mock_analysis()
        result = engine.generate_full_analysis("EUR_USD", analysis)
        assert isinstance(result, StrategyExplanation)
        assert result.instrument == "EUR_USD"

    def test_bullish_bias(self, engine):
        analysis = _mock_analysis(htf_trend=Trend.BULLISH)
        result = engine.generate_full_analysis("EUR_USD", analysis)
        assert result.overall_bias == "ALCISTA"

    def test_bearish_bias(self, engine):
        analysis = _mock_analysis(htf_trend=Trend.BEARISH)
        result = engine.generate_full_analysis("EUR_USD", analysis)
        assert result.overall_bias == "BAJISTA"

    def test_neutral_bias(self, engine):
        analysis = _mock_analysis(htf_trend=Trend.RANGING)
        result = engine.generate_full_analysis("EUR_USD", analysis)
        assert result.overall_bias == "NEUTRAL"

    def test_timeframe_analysis_has_three_tfs(self, engine):
        analysis = _mock_analysis()
        result = engine.generate_full_analysis("EUR_USD", analysis)
        assert len(result.timeframe_analysis) == 3
        tfs = [tf.timeframe for tf in result.timeframe_analysis]
        assert "Diario (D)" in tfs
        assert "4 Horas (H4)" in tfs
        assert "1 Hora (H1)" in tfs


# ──────────────────────────────────────────────────────────────────
# Confidence levels
# ──────────────────────────────────────────────────────────────────

class TestConfidenceLevel:
    def test_alta_confidence(self, engine):
        """Score >= 80 + convergence = ALTA."""
        analysis = _mock_analysis(score=85, convergence=True)
        result = engine.generate_full_analysis("EUR_USD", analysis)
        assert result.confidence_level == "ALTA"

    def test_media_confidence(self, engine):
        """Score >= 65 without convergence = MEDIA."""
        analysis = _mock_analysis(score=70, convergence=False)
        result = engine.generate_full_analysis("EUR_USD", analysis)
        assert result.confidence_level == "MEDIA"

    def test_baja_confidence(self, engine):
        """Score < 65 = BAJA."""
        analysis = _mock_analysis(score=40, convergence=False)
        result = engine.generate_full_analysis("EUR_USD", analysis)
        assert result.confidence_level == "BAJA"


# ──────────────────────────────────────────────────────────────────
# Conditions met / missing
# ──────────────────────────────────────────────────────────────────

class TestConditions:
    def test_convergence_met(self, engine):
        analysis = _mock_analysis(convergence=True)
        result = engine.generate_full_analysis("EUR_USD", analysis)
        assert any("Convergencia" in c for c in result.conditions_met)

    def test_convergence_missing(self, engine):
        analysis = _mock_analysis(convergence=False)
        result = engine.generate_full_analysis("EUR_USD", analysis)
        assert any("convergencia" in c.lower() for c in result.conditions_missing)

    def test_high_score_met(self, engine):
        analysis = _mock_analysis(score=75)
        result = engine.generate_full_analysis("EUR_USD", analysis)
        assert any("Score" in c and "75" in c for c in result.conditions_met)

    def test_low_score_missing(self, engine):
        analysis = _mock_analysis(score=40)
        result = engine.generate_full_analysis("EUR_USD", analysis)
        assert any("insuficiente" in c for c in result.conditions_missing)


# ──────────────────────────────────────────────────────────────────
# With signal
# ──────────────────────────────────────────────────────────────────

class TestWithSignal:
    def test_strategy_detected_from_signal(self, engine):
        analysis = _mock_analysis()
        signal = _mock_signal(strategy_value="RED")
        result = engine.generate_full_analysis("EUR_USD", analysis, signal)
        assert result.strategy_detected == "RED"
        assert result.entry_explanation is not None
        assert result.sl_explanation is not None
        assert result.tp_explanation is not None

    def test_no_signal_no_strategy(self, engine):
        analysis = _mock_analysis()
        result = engine.generate_full_analysis("EUR_USD", analysis, None)
        assert result.strategy_detected is None
        assert result.entry_explanation is None


# ──────────────────────────────────────────────────────────────────
# _build_strategy_steps
# ──────────────────────────────────────────────────────────────────

class TestStrategySteps:
    def test_blue_steps(self, engine):
        signal = _mock_signal(strategy_value="BLUE")
        steps = engine._build_strategy_steps(signal)
        assert len(steps) == 7
        assert any("Rompe, Cierra, Confirma" in s for s in steps)

    def test_red_steps(self, engine):
        signal = _mock_signal(strategy_value="RED")
        steps = engine._build_strategy_steps(signal)
        assert len(steps) == 7
        assert "4H" in steps[2]

    def test_black_steps(self, engine):
        signal = _mock_signal(strategy_value="BLACK")
        steps = engine._build_strategy_steps(signal)
        assert len(steps) == 8
        assert any("RSI" in s for s in steps)

    def test_green_steps(self, engine):
        signal = _mock_signal(strategy_value="GREEN")
        steps = engine._build_strategy_steps(signal)
        assert len(steps) == 6
        assert any("semanal" in s for s in steps)

    def test_unknown_strategy_fallback(self, engine):
        signal = _mock_signal(strategy_value="PURPLE")
        steps = engine._build_strategy_steps(signal)
        assert len(steps) == 1
        assert "PURPLE" in steps[0]


# ──────────────────────────────────────────────────────────────────
# _build_entry_explanation
# ──────────────────────────────────────────────────────────────────

class TestEntryExplanation:
    def test_contains_direction_and_price(self, engine):
        signal = _mock_signal(direction="BUY", entry=1.1000)
        result = engine._build_entry_explanation(signal)
        assert "BUY" in result
        assert "1.10000" in result

    def test_contains_strategy_name(self, engine):
        signal = _mock_signal(strategy_value="BLUE_A")
        result = engine._build_entry_explanation(signal)
        assert "BLUE A" in result


# ──────────────────────────────────────────────────────────────────
# _build_sl_explanation
# ──────────────────────────────────────────────────────────────────

class TestSLExplanation:
    def test_contains_sl_price_and_distance(self, engine):
        signal = _mock_signal(entry=1.1000, sl=1.0950)
        result = engine._build_sl_explanation(signal)
        assert "1.09500" in result
        assert "0.00500" in result  # distance


# ──────────────────────────────────────────────────────────────────
# _build_tp_explanation
# ──────────────────────────────────────────────────────────────────

class TestTPExplanation:
    def test_contains_tp1(self, engine):
        signal = _mock_signal(tp1=1.1100)
        result = engine._build_tp_explanation(signal)
        assert "1.11000" in result

    def test_contains_tp_max(self, engine):
        signal = _mock_signal(tp1=1.1100, tp_max=1.1200)
        result = engine._build_tp_explanation(signal)
        assert "1.12000" in result

    def test_contains_rr_ratio(self, engine):
        signal = _mock_signal(entry=1.1000, sl=1.0950, tp1=1.1100)
        result = engine._build_tp_explanation(signal)
        assert "Ratio" in result
        assert "2.00" in result  # R:R = 100 pips / 50 pips = 2


# ──────────────────────────────────────────────────────────────────
# _build_risk_assessment
# ──────────────────────────────────────────────────────────────────

class TestRiskAssessment:
    def test_no_signal_low_score(self, engine):
        analysis = _mock_analysis(score=30)
        result = engine._build_risk_assessment(analysis, None)
        assert "ALTO" in result

    def test_no_signal_no_convergence(self, engine):
        analysis = _mock_analysis(score=60, convergence=False)
        result = engine._build_risk_assessment(analysis, None)
        assert "MEDIO-ALTO" in result

    def test_no_signal_decent(self, engine):
        analysis = _mock_analysis(score=60, convergence=True)
        result = engine._build_risk_assessment(analysis, None)
        assert "MEDIO" in result

    def test_with_signal_good_rr(self, engine):
        analysis = _mock_analysis()
        # R:R = 150/50 = 3.0 — clearly above 2.0 threshold
        signal = _mock_signal(entry=1.1000, sl=1.0950, tp1=1.1150, confidence=80)
        result = engine._build_risk_assessment(analysis, signal)
        assert "BAJO" in result

    def test_with_signal_bad_rr(self, engine):
        analysis = _mock_analysis()
        signal = _mock_signal(entry=1.1000, sl=1.0950, tp1=1.1020, confidence=60)
        result = engine._build_risk_assessment(analysis, signal)
        # R:R = 20/50 = 0.4 — bad
        assert "ALTO" in result


# ──────────────────────────────────────────────────────────────────
# _build_recommendation
# ──────────────────────────────────────────────────────────────────

class TestRecommendation:
    def test_good_signal_convergence(self, engine):
        analysis = _mock_analysis(convergence=True)
        signal = _mock_signal(confidence=75)
        result = engine._build_recommendation(analysis, signal, True)
        assert "ejecutar" in result

    def test_moderate_signal(self, engine):
        analysis = _mock_analysis(convergence=False)
        signal = _mock_signal(confidence=55)
        result = engine._build_recommendation(analysis, signal, False)
        assert "precaución" in result

    def test_good_score_no_signal(self, engine):
        analysis = _mock_analysis(score=70, convergence=True)
        result = engine._build_recommendation(analysis, None, True)
        assert "Monitorear" in result

    def test_no_recommendation(self, engine):
        analysis = _mock_analysis(score=30, convergence=False)
        result = engine._build_recommendation(analysis, None, False)
        assert "No se recomienda" in result


# ──────────────────────────────────────────────────────────────────
# format_for_notification
# ──────────────────────────────────────────────────────────────────

class TestFormatNotification:
    def test_with_strategy(self, engine):
        explanation = StrategyExplanation(
            instrument="EUR_USD",
            timestamp="2025-01-01T00:00:00Z",
            overall_bias="ALCISTA",
            score=80.0,
            timeframe_analysis=[],
            strategy_detected="BLUE",
            strategy_steps=[],
            conditions_met=[],
            conditions_missing=[],
            entry_explanation=None,
            sl_explanation=None,
            tp_explanation=None,
            risk_assessment="",
            recommendation="",
            confidence_level="ALTA",
        )
        result = engine.format_for_notification(explanation)
        assert "EUR_USD" in result
        assert "BLUE" in result
        assert "80" in result

    def test_without_strategy(self, engine):
        explanation = StrategyExplanation(
            instrument="GBP_JPY",
            timestamp="2025-01-01T00:00:00Z",
            overall_bias="BAJISTA",
            score=45.0,
            timeframe_analysis=[],
            strategy_detected=None,
            strategy_steps=[],
            conditions_met=[],
            conditions_missing=[],
            entry_explanation=None,
            sl_explanation=None,
            tp_explanation=None,
            risk_assessment="",
            recommendation="",
            confidence_level="BAJA",
        )
        result = engine.format_for_notification(explanation)
        assert "GBP_JPY" in result
        assert "Sin señal" in result

    def test_bullish_gets_green_emoji(self, engine):
        explanation = StrategyExplanation(
            instrument="EUR_USD",
            timestamp="",
            overall_bias="ALCISTA",
            score=80.0,
            timeframe_analysis=[],
            strategy_detected="BLUE",
            strategy_steps=[],
            conditions_met=[],
            conditions_missing=[],
            entry_explanation=None,
            sl_explanation=None,
            tp_explanation=None,
            risk_assessment="",
            recommendation="",
            confidence_level="ALTA",
        )
        result = engine.format_for_notification(explanation)
        assert "🟢" in result

    def test_bearish_gets_red_emoji(self, engine):
        explanation = StrategyExplanation(
            instrument="EUR_USD",
            timestamp="",
            overall_bias="BAJISTA",
            score=80.0,
            timeframe_analysis=[],
            strategy_detected="RED",
            strategy_steps=[],
            conditions_met=[],
            conditions_missing=[],
            entry_explanation=None,
            sl_explanation=None,
            tp_explanation=None,
            risk_assessment="",
            recommendation="",
            confidence_level="ALTA",
        )
        result = engine.format_for_notification(explanation)
        assert "🔴" in result


# ──────────────────────────────────────────────────────────────────
# _build_position_management_explanation
# ──────────────────────────────────────────────────────────────────

class TestPositionManagementExplanation:
    def test_contains_all_five_phases(self, engine):
        signal = _mock_signal()
        result = engine._build_position_management_explanation(signal)
        assert "INICIAL" in result
        assert "BREAK EVEN" in result
        assert "TRAILING" in result
        assert "CPA" in result
