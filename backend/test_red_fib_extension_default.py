"""
TASK A1 — RED TP_max prioriza Fib 1.0 (PDF pg.6) vs 1.272/1.618.

Trading Plan PDF pg.6 (autoritativo) dice:
  "RED (con HTF a favor): Extensión de Fibonacci de 1"

Es decir: 1.0 (100%), NO 1.272 ni 1.618.

App antes: para Wave 3, priorizaba fib_1618 primero, luego fib_1272, y
fib_100 solo como último recurso.

App ahora (PDF pg.6): para Wave 3 con HTF a favor → tp_max = Fib 1.0 por
default. 1.272/1.618 solo como extensiones opcionales (Wave 3 extendida
con momentum confirmado, ej: HTF overbought/oversold + deceleration,
condición más estricta que antes).
"""

from core.market_analyzer import AnalysisResult, Trend, MarketCondition
from strategies.base import RedStrategy


def _make_red_analysis(
    instrument="EUR_USD",
    direction="BUY",
    htf_trend=Trend.BULLISH,
    htf_condition=MarketCondition.NEUTRAL,
    wave_count="3",
    htf_ltf_convergence=True,
    current_price=1.1030,
    ema_h4_50=1.0990,
    ema_h1_50=1.1000,
    swing_highs=None,
    swing_lows=None,
    fib_ext_bull_10=1.1100,
    fib_ext_bull_1272=1.1200,
    fib_ext_bull_1618=1.1300,
    fib_ext_bear_10=1.0900,
    fib_ext_bear_1272=1.0800,
    fib_ext_bear_1618=1.0700,
):
    ema_values = {
        "EMA_W_8": 1.0900, "EMA_W_50": 1.0800,
        "EMA_D_50": 1.0850, "EMA_D_20": 1.0950,
        "EMA_H4_50": ema_h4_50,
        "EMA_H1_50": ema_h1_50,
        "EMA_M15_50": 1.1010, "EMA_M5_50": 1.1010, "EMA_M5_5": 1.1020,
        "EMA_M5_20": 1.1015, "EMA_M5_2": 1.1025, "EMA_M1_50": 1.1005,
    }

    if direction == "BUY":
        swing_highs = swing_highs or [1.1050, 1.1080]
        swing_lows = swing_lows or [1.0950, 1.0900]
        key_resistances = [1.1150, 1.1250]
        key_supports = [1.0950, 1.0900]
    else:
        swing_highs = swing_highs or [1.1150, 1.1200]
        swing_lows = swing_lows or [1.0980, 1.0950]
        key_resistances = [1.1150]
        key_supports = [1.0850, 1.0800]

    return AnalysisResult(
        instrument=instrument,
        htf_trend=htf_trend,
        htf_condition=htf_condition,
        ltf_trend=htf_trend,
        htf_ltf_convergence=htf_ltf_convergence,
        key_levels={
            "supports": key_supports,
            "resistances": key_resistances,
            "fvg": [], "fvg_zones": [], "liquidity_pools": [],
        },
        ema_values=ema_values,
        fibonacci_levels={
            "0.0": 1.1200, "0.382": 1.1124, "0.5": 1.1100,
            "0.618": 1.1076, "0.750": 1.1050, "1.0": 1.1000,
            "ext_bull_1.0": fib_ext_bull_10,
            "ext_bull_1.272": fib_ext_bull_1272,
            "ext_bull_1.618": fib_ext_bull_1618,
            "ext_bear_1.0": fib_ext_bear_10,
            "ext_bear_1.272": fib_ext_bear_1272,
            "ext_bear_1.618": fib_ext_bear_1618,
        },
        candlestick_patterns=[],
        swing_highs=swing_highs,
        swing_lows=swing_lows,
        current_price=current_price,
        elliott_wave_detail={"wave_count": wave_count},
        ema_w8=1.0900,
    )


def test_red_wave3_htf_favor_uses_fib_100_as_tp_max():
    """PDF pg.6: RED con HTF a favor (Wave 3, convergencia) debe usar
    extensión Fib 1.0 como TP_max default (no 1.272 ni 1.618)."""
    analysis = _make_red_analysis(
        direction="BUY",
        wave_count="3",
        htf_ltf_convergence=True,
        htf_condition=MarketCondition.NEUTRAL,  # NOT overbought: "con HTF a favor" neutral
    )
    strat = RedStrategy()
    entry = 1.1030

    tps = strat.get_tp_levels(analysis, direction="BUY", entry_price=entry)

    assert "tp_max" in tps
    # PDF pg.6: RED con HTF a favor = Fib 1.0 extension (1.1100 in this setup)
    assert tps["tp_max"] == 1.1100, (
        f"TP_max debe ser Fib ext 1.0 (1.1100), got {tps['tp_max']}"
    )


def test_red_wave3_htf_favor_sell_uses_fib_100():
    """PDF pg.6: RED SELL con HTF a favor (Wave 3) debe usar ext Fib 1.0."""
    analysis = _make_red_analysis(
        direction="SELL",
        wave_count="3",
        htf_trend=Trend.BEARISH,
        htf_ltf_convergence=True,
        htf_condition=MarketCondition.NEUTRAL,
        current_price=1.0970,
    )
    strat = RedStrategy()
    entry = 1.0960

    tps = strat.get_tp_levels(analysis, direction="SELL", entry_price=entry)

    assert "tp_max" in tps
    # PDF: Fib bear 1.0 = 1.0900
    assert tps["tp_max"] == 1.0900, (
        f"SELL TP_max debe ser Fib ext 1.0 (1.0900), got {tps['tp_max']}"
    )


def test_red_wave3_extended_momentum_can_target_1272_or_1618():
    """Wave 3 extendida (momentum confirmado: HTF overbought/oversold + deceleration)
    puede escalar a Fib 1.272/1.618, pero 1.0 sigue siendo el default."""
    # This test covers the extended case: strong momentum → can push beyond 1.0
    # With htf_condition=OVERSOLD (for BUY) AND deceleration, tp_max MAY escalate.
    # The default (Fib 1.0) is the baseline; extended is the exception.
    # Use no intermediate resistances between tp1 and the Fib extensions so the
    # test is deterministic about which Fib is chosen.
    analysis = _make_red_analysis(
        direction="BUY",
        wave_count="3",
        htf_condition=MarketCondition.OVERSOLD,  # strong momentum confirmed
        htf_ltf_convergence=True,
    )
    # Clear intermediate resistances so extended momentum path is unblocked.
    analysis.key_levels["resistances"] = []
    # Add deceleration via candlestick pattern to trigger extended logic
    analysis.candlestick_patterns = ["HIGH_TEST", "MORNING_STAR"]

    strat = RedStrategy()
    entry = 1.1030

    tps = strat.get_tp_levels(analysis, direction="BUY", entry_price=entry)

    assert "tp_max" in tps
    # Extended Wave 3 with strong momentum should scale beyond Fib 1.0
    # (either 1.272 = 1.1200 or 1.618 = 1.1300)
    assert tps["tp_max"] in (1.1200, 1.1300), (
        f"Extended Wave 3 tp_max con momentum debe escalar a Fib 1.272/1.618, got {tps['tp_max']}"
    )


def test_red_wave3_htf_against_does_not_use_extensions():
    """Wave 3 SIN HTF a favor (sin convergencia HTF/LTF) NO debe usar Fib extensions
    (la regla es 'CON HTF a favor')."""
    analysis = _make_red_analysis(
        direction="BUY",
        wave_count="3",
        htf_ltf_convergence=False,  # HTF CONTRA
    )
    strat = RedStrategy()
    entry = 1.1030

    tps = strat.get_tp_levels(analysis, direction="BUY", entry_price=entry)

    # Without HTF favor, should fall back to nearest S/R above tp1
    # (not a Fib extension). TP_max could be None or a conservative S/R.
    if "tp_max" in tps:
        assert tps["tp_max"] not in (1.1200, 1.1300), (
            f"Sin HTF favor no debe targetear Fib 1.272/1.618, got {tps['tp_max']}"
        )


def test_red_wave3_tp1_still_swing_anterior():
    """TP1 sigue siendo swing anterior (no cambia con A1)."""
    analysis = _make_red_analysis(direction="BUY", wave_count="3")
    strat = RedStrategy()
    entry = 1.1030

    tps = strat.get_tp_levels(analysis, direction="BUY", entry_price=entry)

    assert "tp1" in tps
    # TP1 = swing high más cercano encima de entry (1.1050)
    assert tps["tp1"] == 1.1050, (
        f"TP1 debe ser swing high más cercano (1.1050), got {tps['tp1']}"
    )
