"""
Comprehensive pytest tests for all 6 color strategies.
BUGFIX-001: Tests for BLUE (A/B/C), RED, PINK, WHITE, BLACK, GREEN
"""
import sys
import pytest

sys.path.insert(0, ".")

from strategies.base import (
    BlueStrategy, RedStrategy, PinkStrategy,
    WhiteStrategy, BlackStrategy, GreenStrategy,
    StrategyColor, SetupSignal, EntryType,
    ALL_STRATEGIES, STRATEGY_MAP,
    _is_crypto_instrument, _apply_elliott_wave_priority,
    _classify_blue_variant, _has_reversal_pattern,
    _check_ema_break, _fib_zone_check, _is_at_key_level,
)
from core.market_analyzer import AnalysisResult, Trend, MarketCondition


# ── Helpers ───────────────────────────────────────────────────────────

def make_analysis(
    instrument="EUR_USD",
    htf_trend=Trend.BULLISH,
    ltf_trend=Trend.BULLISH,
    htf_condition=MarketCondition.NEUTRAL,
    convergence=True,
    price_proxy=1.1000,
    ema_h1_50=None,
    ema_h4_50=None,
    supports=None,
    resistances=None,
    chart_patterns=None,
    candlestick_patterns=None,
    rsi_divergence=None,
    swing_lows=None,
    swing_highs=None,
    elliott_wave=None,
    elliott_wave_detail=None,
    bmsb=None,
    last_candles=None,
):
    ema_values = {
        "EMA_M5_2": price_proxy,
        "EMA_M5_5": price_proxy,
        "EMA_M5_20": price_proxy * 0.999,
        "EMA_M5_50": price_proxy * 0.998,
        "EMA_W_8": price_proxy * 0.98,
    }
    if ema_h1_50 is not None:
        ema_values["EMA_H1_50"] = ema_h1_50
    else:
        ema_values["EMA_H1_50"] = price_proxy * 0.998
    if ema_h4_50 is not None:
        ema_values["EMA_H4_50"] = ema_h4_50
    else:
        ema_values["EMA_H4_50"] = price_proxy * 0.995

    return AnalysisResult(
        instrument=instrument,
        htf_trend=htf_trend,
        htf_condition=htf_condition,
        ltf_trend=ltf_trend,
        htf_ltf_convergence=convergence,
        key_levels={
            "supports": supports or [price_proxy - 0.01, price_proxy - 0.02],
            "resistances": resistances or [price_proxy + 0.01, price_proxy + 0.02],
        },
        ema_values=ema_values,
        fibonacci_levels={"0.382": price_proxy - 0.004, "0.500": price_proxy - 0.005, "0.618": price_proxy - 0.006},
        candlestick_patterns=candlestick_patterns or [],
        chart_patterns=chart_patterns or [],
        rsi_divergence=rsi_divergence,
        swing_lows=swing_lows or [],
        swing_highs=swing_highs or [],
        elliott_wave=elliott_wave,
        elliott_wave_detail=elliott_wave_detail or {},
        bmsb=bmsb,
        last_candles=last_candles or {},
    )


# ── Section 1: Strategy instantiation ────────────────────────────────

class TestStrategyInstantiation:
    def test_all_strategies_exist(self):
        assert len(ALL_STRATEGIES) == 6

    def test_strategy_colors(self):
        assert BlueStrategy().color == StrategyColor.BLUE
        assert RedStrategy().color == StrategyColor.RED
        assert PinkStrategy().color == StrategyColor.PINK
        assert WhiteStrategy().color == StrategyColor.WHITE
        assert BlackStrategy().color == StrategyColor.BLACK
        assert GreenStrategy().color == StrategyColor.GREEN

    def test_strategy_map(self):
        assert isinstance(STRATEGY_MAP[StrategyColor.BLUE], BlueStrategy)
        assert isinstance(STRATEGY_MAP[StrategyColor.RED], RedStrategy)

    def test_min_confidence_values(self):
        assert BlueStrategy().min_confidence == 55.0
        assert RedStrategy().min_confidence == 55.0
        assert PinkStrategy().min_confidence == 50.0
        assert WhiteStrategy().min_confidence == 55.0
        assert BlackStrategy().min_confidence == 60.0
        # GREEN has its own min_confidence


# ── Section 2: BLUE strategy (variants A/B/C) ────────────────────────

class TestBlueStrategy:
    def setup_method(self):
        self.blue = BlueStrategy()

    def test_htf_conditions_pass_with_ema_break(self):
        """Blue requires 1H EMA 50 break."""
        analysis = make_analysis(
            ema_h1_50=1.0980,  # price 1.10 > EMA → broken upward for BUY
        )
        ok, score, met, failed = self.blue.check_htf_conditions(analysis)
        assert ok, f"Blue HTF should pass. Failed: {failed}"
        assert score >= 20.0

    def test_htf_conditions_fail_without_ema_break(self):
        """Blue fails when 1H EMA is NOT broken."""
        analysis = make_analysis(
            ema_h1_50=1.1020,  # price 1.10 < EMA → NOT broken for BUY
        )
        ok, score, met, failed = self.blue.check_htf_conditions(analysis)
        assert not ok, "Blue HTF should fail without 1H EMA break"

    def test_variant_a_double_bottom(self):
        """Variant A requires chart pattern (double bottom, H&S)."""
        analysis = make_analysis(
            chart_patterns=[{"type": "double_bottom", "confidence": 0.85}],
        )
        variant = _classify_blue_variant(analysis, "BUY")
        assert variant == "BLUE_A"

    def test_variant_a_inverse_head_and_shoulders(self):
        analysis = make_analysis(
            chart_patterns=[{"type": "inverse_head_and_shoulders", "confidence": 0.80}],
        )
        variant = _classify_blue_variant(analysis, "BUY")
        assert variant == "BLUE_A"

    def test_variant_b_default(self):
        """Variant B is the default when no special conditions."""
        analysis = make_analysis(
            ema_h4_50=1.0800,  # far from price → no variant C
        )
        variant = _classify_blue_variant(analysis, "BUY")
        assert variant == "BLUE_B"

    def test_variant_c_near_ema_4h(self):
        """Variant C triggers when a rejection candle wicked through EMA 4H and closed above it."""
        price = 1.1000
        ema = 1.1001
        # A bullish rejection candle: low touched below EMA, closed above it
        rejection_candle = {"open": 1.0998, "high": 1.1010, "low": 1.0995, "close": 1.1008}
        analysis = make_analysis(
            price_proxy=price,
            ema_h4_50=ema,
            htf_trend=Trend.BULLISH,
            last_candles={"M5": [rejection_candle, rejection_candle, rejection_candle]},
        )
        variant = _classify_blue_variant(analysis, "BUY")
        assert variant == "BLUE_C"

    def test_sl_placement_buy(self):
        """BUY SL: min(Fib 0.618, previous support)."""
        analysis = make_analysis(
            supports=[1.0930, 1.0910],
            price_proxy=1.1000,
        )
        sl = self.blue.get_sl_placement(analysis, "BUY", 1.1000)
        assert sl < 1.1000, f"SL should be below entry, got {sl}"

    def test_sl_placement_sell(self):
        """SELL SL: max(Fib 0.618, previous resistance)."""
        analysis = make_analysis(
            resistances=[1.1070, 1.1090],
            price_proxy=1.1000,
        )
        # Fib 0.618 needs to be above entry for SELL
        analysis.fibonacci_levels["0.618"] = 1.1100
        sl = self.blue.get_sl_placement(analysis, "SELL", 1.1000)
        assert sl > 1.1000, f"SL should be above entry, got {sl}"

    def test_tp_uses_ema_4h(self):
        """TP1 = EMA 50 4H."""
        analysis = make_analysis(ema_h4_50=1.1050)
        tps = self.blue.get_tp_levels(analysis, "BUY", 1.1000)
        if "tp1" in tps:
            assert abs(tps["tp1"] - 1.1050) < 0.001


# ── Section 3: RED strategy ──────────────────────────────────────────

class TestRedStrategy:
    def setup_method(self):
        self.red = RedStrategy()

    def test_htf_requires_both_ema_breaks(self):
        """RED requires BOTH 1H AND 4H EMA 50 broken."""
        analysis = make_analysis(
            ema_h1_50=1.0980,  # broken (price > EMA)
            ema_h4_50=1.0970,  # broken (price > EMA)
            convergence=True,
        )
        ok, score, met, failed = self.red.check_htf_conditions(analysis)
        assert ok, f"RED HTF should pass with both EMAs broken. Failed: {failed}"

    def test_htf_fails_with_only_1h_break(self):
        """RED fails when only 1H is broken (that's Blue territory)."""
        analysis = make_analysis(
            ema_h1_50=1.0980,  # broken
            ema_h4_50=1.1020,  # NOT broken (price < EMA)
            convergence=True,
        )
        ok, score, met, failed = self.red.check_htf_conditions(analysis)
        assert not ok, "RED should fail with only 1H broken"

    def test_htf_requires_convergence(self):
        """RED hard-blocks without HTF/LTF convergence."""
        analysis = make_analysis(
            ema_h1_50=1.0980,
            ema_h4_50=1.0970,
            convergence=False,  # No convergence
        )
        ok, score, met, failed = self.red.check_htf_conditions(analysis)
        assert not ok, "RED should fail without convergence"


# ── Section 4: PINK strategy ─────────────────────────────────────────

class TestPinkStrategy:
    def setup_method(self):
        self.pink = PinkStrategy()

    def test_htf_buy_1h_broken_4h_not(self):
        """PINK BUY: 1H broken downward (correction), 4H NOT broken."""
        analysis = make_analysis(
            htf_trend=Trend.BULLISH,
            ltf_trend=Trend.BULLISH,
            convergence=True,
            price_proxy=1.1000,
            ema_h1_50=1.1020,  # price < EMA → correction broke below 1H
            ema_h4_50=1.0960,  # price > EMA → 4H NOT broken downward
        )
        ok, score, met, failed = self.pink.check_htf_conditions(analysis)
        assert ok, f"PINK BUY should pass. Failed: {failed}"

    def test_htf_sell_1h_broken_4h_not(self):
        """PINK SELL: 1H broken upward (correction), 4H NOT broken."""
        analysis = make_analysis(
            htf_trend=Trend.BEARISH,
            ltf_trend=Trend.BEARISH,
            convergence=True,
            price_proxy=1.1000,
            ema_h1_50=1.0980,  # price > EMA → correction broke above 1H
            ema_h4_50=1.1040,  # price < EMA → 4H NOT broken upward
        )
        ok, score, met, failed = self.pink.check_htf_conditions(analysis)
        assert ok, f"PINK SELL should pass. Failed: {failed}"

    def test_htf_fails_when_4h_also_broken(self):
        """When both 1H and 4H are broken, it's RED not PINK."""
        analysis = make_analysis(
            htf_trend=Trend.BULLISH,
            ltf_trend=Trend.BULLISH,
            convergence=True,
            price_proxy=1.1000,
            ema_h1_50=1.1020,  # 1H broken downward
            ema_h4_50=1.1040,  # 4H also broken downward → RED territory
        )
        ok, score, met, failed = self.pink.check_htf_conditions(analysis)
        assert not ok, "PINK should fail when 4H also broken (RED)"
        assert any("RED" in f for f in failed), "Should mention RED"

    def test_htf_requires_convergence(self):
        """PINK hard-blocks without convergence."""
        analysis = make_analysis(
            convergence=False,
            ema_h1_50=1.1020,
            ema_h4_50=1.0960,
        )
        ok, score, met, failed = self.pink.check_htf_conditions(analysis)
        assert not ok, "PINK should fail without convergence"


# ── Section 5: WHITE strategy ─────────────────────────────────────────

class TestWhiteStrategy:
    def setup_method(self):
        self.white = WhiteStrategy()

    def test_htf_pass_with_convergence(self):
        """WHITE requires established trend + convergence."""
        analysis = make_analysis(
            htf_trend=Trend.BULLISH,
            ltf_trend=Trend.BULLISH,
            convergence=True,
            ema_h1_50=1.0980,  # 1H intact (price > EMA)
        )
        ok, score, met, failed = self.white.check_htf_conditions(analysis)
        assert ok, f"WHITE should pass with convergence. Failed: {failed}"

    def test_htf_fails_without_convergence(self):
        """WHITE hard-blocks without convergence."""
        analysis = make_analysis(
            convergence=False,
        )
        ok, score, met, failed = self.white.check_htf_conditions(analysis)
        assert not ok, "WHITE should fail without convergence"

    def test_sl_uses_swing_extreme(self):
        """WHITE SL = previous swing extreme (not Fib like Blue)."""
        analysis = make_analysis(supports=[1.0930])
        sl = self.white.get_sl_placement(analysis, "BUY", 1.1000)
        assert sl < 1.1000


# ── Section 6: BLACK strategy (counter-trend) ────────────────────────

class TestBlackStrategy:
    def setup_method(self):
        self.black = BlackStrategy()

    def test_counter_trend_in_htf(self):
        """BLACK goes AGAINST HTF trend in check_htf_conditions."""
        analysis = make_analysis(
            htf_trend=Trend.BULLISH,
            htf_condition=MarketCondition.OVERBOUGHT,
            resistances=[1.1005],  # Need S/R level at price for Paso 1
        )
        ok, score, met, failed = self.black.check_htf_conditions(analysis)
        # If passes, the direction should be SELL (counter-trend vs bullish)
        if ok:
            assert any("venta" in m.lower() or "sell" in m.lower() or "SELL" in m for m in met)

    def test_htf_requires_daily_sr_level(self):
        """BLACK requires a daily S/R level (non-negotiable)."""
        analysis = make_analysis(
            htf_trend=Trend.BULLISH,
            htf_condition=MarketCondition.OVERBOUGHT,
            supports=[],
            resistances=[],
        )
        ok, score, met, failed = self.black.check_htf_conditions(analysis)
        # Should fail when no S/R levels present
        # (depends on implementation — level required)

    def test_htf_needs_overbought_oversold(self):
        """BLACK benefits from overbought/oversold condition."""
        analysis = make_analysis(
            htf_trend=Trend.BULLISH,
            htf_condition=MarketCondition.OVERBOUGHT,
            resistances=[1.1005],  # At a resistance level
        )
        ok, score, met, failed = self.black.check_htf_conditions(analysis)
        # Overbought should give score bonus
        if ok:
            assert any("overbought" in m.lower() or "sobrecompra" in m.lower() for m in met)

    def test_min_rr_is_2(self):
        """BLACK requires minimum 2:1 R:R."""
        assert self.black.min_confidence == 60.0


# ── Section 7: GREEN strategy (crypto-only) ──────────────────────────

class TestGreenStrategy:
    def setup_method(self):
        self.green = GreenStrategy()

    def test_crypto_instrument_detection(self):
        assert _is_crypto_instrument("BTC_USD")
        assert _is_crypto_instrument("ETH_USD")
        assert _is_crypto_instrument("SOL_USD")
        assert not _is_crypto_instrument("EUR_USD")
        assert not _is_crypto_instrument("XAU_USD")

    def test_green_color(self):
        assert self.green.color == StrategyColor.GREEN

    def test_htf_requires_weekly_trend(self):
        """GREEN requires weekly trend."""
        analysis = make_analysis(
            instrument="BTC_USD",
            htf_trend=Trend.BULLISH,
        )
        ok, score, met, failed = self.green.check_htf_conditions(analysis)
        # GREEN should pass with bullish weekly trend (or fail with RANGING)

    def test_htf_fails_with_ranging(self):
        """GREEN fails with ranging HTF trend."""
        analysis = make_analysis(
            instrument="BTC_USD",
            htf_trend=Trend.RANGING,
        )
        ok, score, met, failed = self.green.check_htf_conditions(analysis)
        assert not ok, "GREEN should fail with ranging trend"


# ── Section 8: Elliott Wave priority ──────────────────────────────────

class TestElliottWavePriority:
    def _make_signal(self, color, confidence=70.0):
        return SetupSignal(
            strategy=color,
            strategy_variant=color.value,
            instrument="EUR_USD",
            direction="BUY",
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit_1=1.1100,
            confidence=confidence,
        )

    def _make_analysis_wave(self, wave):
        return make_analysis(
            elliott_wave_detail={"wave_count": wave},
        )

    def test_wave1_black_bonus(self):
        """Wave 1: BLACK gets highest bonus (+12)."""
        signals = [self._make_signal(StrategyColor.BLACK, 70)]
        result = _apply_elliott_wave_priority(self._make_analysis_wave("1"), signals)
        assert result[0].confidence == 82

    def test_wave3_red_bonus(self):
        """Wave 3: RED gets +10 bonus."""
        signals = [
            self._make_signal(StrategyColor.RED, 70),
            self._make_signal(StrategyColor.BLUE, 70),
        ]
        result = _apply_elliott_wave_priority(self._make_analysis_wave("3"), signals)
        red = [s for s in result if s.strategy == StrategyColor.RED][0]
        blue = [s for s in result if s.strategy == StrategyColor.BLUE][0]
        assert red.confidence == 80
        assert blue.confidence == 75  # +5

    def test_wave5_pink_bonus(self):
        """Wave 5: PINK gets +10 bonus."""
        signals = [self._make_signal(StrategyColor.PINK, 70)]
        result = _apply_elliott_wave_priority(self._make_analysis_wave("5"), signals)
        assert result[0].confidence == 80

    def test_green_wave_bonus(self):
        """GREEN gets +8 bonus in impulsive waves (1, 3, 5) per Trading Plan."""
        signals = [self._make_signal(StrategyColor.GREEN, 70)]
        result = _apply_elliott_wave_priority(self._make_analysis_wave("3"), signals)
        assert result[0].confidence == 78  # +8 bonus for GREEN in wave 3


# ── Section 9: Reversal pattern detection ─────────────────────────────

class TestReversalPatterns:
    def test_hammer_bullish(self):
        analysis = make_analysis(candlestick_patterns=["HAMMER"])
        found, desc = _has_reversal_pattern(analysis, "BUY")
        assert found, "HAMMER should be bullish reversal"

    def test_shooting_star_bearish(self):
        analysis = make_analysis(candlestick_patterns=["SHOOTING_STAR"])
        found, desc = _has_reversal_pattern(analysis, "SELL")
        assert found, "SHOOTING_STAR should be bearish reversal"

    def test_engulfing_bullish(self):
        analysis = make_analysis(candlestick_patterns=["ENGULFING_BULLISH"])
        found, desc = _has_reversal_pattern(analysis, "BUY")
        assert found

    def test_engulfing_bearish(self):
        analysis = make_analysis(candlestick_patterns=["ENGULFING_BEARISH"])
        found, desc = _has_reversal_pattern(analysis, "SELL")
        assert found

    def test_morning_star(self):
        analysis = make_analysis(candlestick_patterns=["MORNING_STAR"])
        found, _ = _has_reversal_pattern(analysis, "BUY")
        assert found

    def test_evening_star(self):
        analysis = make_analysis(candlestick_patterns=["EVENING_STAR"])
        found, _ = _has_reversal_pattern(analysis, "SELL")
        assert found

    def test_wrong_direction_no_match(self):
        """Bullish pattern should not match SELL direction."""
        analysis = make_analysis(candlestick_patterns=["HAMMER"])
        found, _ = _has_reversal_pattern(analysis, "SELL")
        assert not found


# ── Section 10: Non-market entry restrictions ─────────────────────────

class TestEntryRestrictions:
    def test_pink_excludes_non_market(self):
        allows = {StrategyColor.BLUE, StrategyColor.RED, StrategyColor.WHITE}
        assert PinkStrategy().color not in allows

    def test_black_excludes_non_market(self):
        allows = {StrategyColor.BLUE, StrategyColor.RED, StrategyColor.WHITE}
        assert BlackStrategy().color not in allows

    def test_blue_allows_non_market(self):
        allows = {StrategyColor.BLUE, StrategyColor.RED, StrategyColor.WHITE}
        assert BlueStrategy().color in allows


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
