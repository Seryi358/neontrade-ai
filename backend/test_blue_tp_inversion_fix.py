"""
TASK C1 — Verifica que BLUE TP1 = swing anterior, TP_max = EMA 4H.

Trading Plan PDF pg.6 (autoritativo) dice:
  "Pondré SIEMPRE un Take Profit 1 que significará llevar el precio
   hasta el máximo o mínimo anterior. En función de algunas circunstancias,
   situaré un Take Profit máximo.
   BLUE: EMA4H / RED (con HTF a favor): Extensión de Fibonacci de 1
   WHITE: máximo/mínimo del impulso de 4H"

Es decir:
  - TP1 = swing anterior (máximo/mínimo más cercano)
  - TP_max = EMA 4H 50 (para BLUE B/C)
  - TP_max = Fib 1.272/1.618 (para BLUE A, variante con SMT)

La app antes tenía INVERTIDO: `tp1 = EMA 4H 50`. Este test verifica
la corrección.
"""

from core.market_analyzer import AnalysisResult, Trend, MarketCondition
from strategies.base import BlueStrategy


def _make_blue_analysis(
    instrument="EUR_USD",
    direction="BUY",
    ema_h4_50=1.1200,      # used as tp_max for BLUE B/C
    ema_h1_50=1.1050,
    current_price=1.1020,
    swing_highs=None,
    swing_lows=None,
    key_resistances=None,
    key_supports=None,
    fib_ext_1272_bull=1.1400,
    fib_ext_1618_bull=1.1500,
    fib_ext_1272_bear=1.0750,
    fib_ext_1618_bear=1.0650,
):
    ema_values = {
        "EMA_W_8": 1.0900, "EMA_W_50": 1.0800,
        "EMA_D_50": 1.0850, "EMA_D_20": 1.0950,
        "EMA_H4_50": ema_h4_50,
        "EMA_H1_50": ema_h1_50,
        "EMA_M15_50": 1.1010, "EMA_M5_50": 1.1010, "EMA_M5_5": 1.1020,
        "EMA_M5_20": 1.1015, "EMA_M5_2": 1.1025, "EMA_M1_50": 1.1005,
    }

    # For BUY: swings set between entry and ema_h4_50 so we can verify:
    #   - tp1 is closest swing (below ema_h4_50)
    #   - tp_max is ema_h4_50
    if direction == "BUY":
        swing_highs = swing_highs or [1.1080, 1.1120, 1.1180]  # entry < sh < ema_h4
        swing_lows = swing_lows or [1.0950, 1.0900]
        key_resistances = key_resistances or [1.1150, 1.1300]
        key_supports = key_supports or [1.0950, 1.0900]
    else:
        swing_highs = swing_highs or [1.1150, 1.1200]
        swing_lows = swing_lows or [1.0920, 1.0900, 1.0860]  # ema_h4 < sl < entry
        key_resistances = key_resistances or [1.1300]
        key_supports = key_supports or [1.0950, 1.0900, 1.0850]

    return AnalysisResult(
        instrument=instrument,
        htf_trend=Trend.BULLISH if direction == "BUY" else Trend.BEARISH,
        htf_condition=MarketCondition.NEUTRAL,
        ltf_trend=Trend.BULLISH if direction == "BUY" else Trend.BEARISH,
        htf_ltf_convergence=True,
        key_levels={
            "supports": key_supports,
            "resistances": key_resistances,
            "fvg": [],
            "fvg_zones": [],
            "liquidity_pools": [],
        },
        ema_values=ema_values,
        fibonacci_levels={
            "0.0": 1.1200, "0.382": 1.1124, "0.5": 1.1100,
            "0.618": 1.1076, "0.750": 1.1050, "1.0": 1.1000,
            "ext_bull_1.0": 1.1250, "ext_bull_1.272": fib_ext_1272_bull,
            "ext_bull_1.618": fib_ext_1618_bull,
            "ext_bear_1.0": 1.0800, "ext_bear_1.272": fib_ext_1272_bear,
            "ext_bear_1.618": fib_ext_1618_bear,
        },
        candlestick_patterns=[],
        swing_highs=swing_highs,
        swing_lows=swing_lows,
        current_price=current_price,
        ema_w8=1.0900,
    )


def test_blue_b_tp1_is_swing_not_ema_for_buy():
    """BLUE B (BUY): TP1 = swing high más cercano, NO la EMA 4H."""
    analysis = _make_blue_analysis(direction="BUY", ema_h4_50=1.1200)
    strat = BlueStrategy()
    entry = 1.1055  # entre swings

    tps = strat.get_tp_levels(analysis, direction="BUY", entry_price=entry, variant="BLUE_B")

    assert "tp1" in tps
    # TP1 should be the CLOSEST swing high ABOVE entry (1.1080), NOT the EMA 4H (1.1200)
    assert tps["tp1"] == 1.1080, (
        f"TP1 debe ser swing high más cercano (1.1080), got {tps['tp1']}"
    )
    # The EMA 4H 1.1200 should be tp_max, not tp1
    assert tps["tp1"] < 1.1200, "TP1 debe ser < EMA 4H 50 (tp1 es primer target)"


def test_blue_b_tp1_is_swing_not_ema_for_sell():
    """BLUE B (SELL): TP1 = swing low más cercano, NO la EMA 4H."""
    analysis = _make_blue_analysis(direction="SELL", ema_h4_50=1.0800, current_price=1.1030)
    strat = BlueStrategy()
    entry = 1.1000

    tps = strat.get_tp_levels(analysis, direction="SELL", entry_price=entry, variant="BLUE_B")

    assert "tp1" in tps
    # TP1 should be the CLOSEST swing low BELOW entry (0.0920), NOT EMA 4H (1.0800)
    assert tps["tp1"] == 1.0920, (
        f"TP1 debe ser swing low más cercano (1.0920), got {tps['tp1']}"
    )
    assert tps["tp1"] > 1.0800, "TP1 debe ser > EMA 4H 50 (SELL: TP1 más cerca que EMA)"


def test_blue_b_tp_max_is_ema_4h_for_buy():
    """BLUE B (BUY): TP_max = EMA 4H 50 conforme a Trading Plan PDF pg.6."""
    analysis = _make_blue_analysis(direction="BUY", ema_h4_50=1.1200)
    strat = BlueStrategy()
    entry = 1.1055

    tps = strat.get_tp_levels(analysis, direction="BUY", entry_price=entry, variant="BLUE_B")

    assert "tp_max" in tps
    # TP_max should be EMA 4H 50 (1.1200)
    assert tps["tp_max"] == 1.1200, (
        f"TP_max debe ser EMA 4H 50 (1.1200), got {tps['tp_max']}"
    )


def test_blue_b_tp_max_is_ema_4h_for_sell():
    """BLUE B (SELL): TP_max = EMA 4H 50 conforme a Trading Plan PDF pg.6."""
    analysis = _make_blue_analysis(direction="SELL", ema_h4_50=1.0800, current_price=1.1030)
    strat = BlueStrategy()
    entry = 1.1000

    tps = strat.get_tp_levels(analysis, direction="SELL", entry_price=entry, variant="BLUE_B")

    assert "tp_max" in tps
    assert tps["tp_max"] == 1.0800, (
        f"TP_max debe ser EMA 4H 50 (1.0800), got {tps['tp_max']}"
    )


def test_blue_c_tp1_is_swing_not_ema_for_buy():
    """BLUE C (BUY): TP1 = swing high más cercano, NO la EMA 4H."""
    analysis = _make_blue_analysis(direction="BUY", ema_h4_50=1.1200)
    strat = BlueStrategy()
    entry = 1.1055

    tps = strat.get_tp_levels(analysis, direction="BUY", entry_price=entry, variant="BLUE_C")

    assert tps["tp1"] == 1.1080
    assert tps["tp_max"] == 1.1200


def test_blue_a_tp1_is_swing_and_tp_max_is_fib_ext_for_buy():
    """BLUE A (BUY): TP1 = swing anterior, TP_max = Fib 1.272/1.618 extension."""
    analysis = _make_blue_analysis(direction="BUY", ema_h4_50=1.1200)
    strat = BlueStrategy()
    entry = 1.1055

    tps = strat.get_tp_levels(analysis, direction="BUY", entry_price=entry, variant="BLUE_A")

    # TP1 = swing high (unchanged from before)
    assert tps["tp1"] == 1.1080, f"BLUE_A TP1 debe ser swing, got {tps.get('tp1')}"
    # TP_max = fib extension (BLUE_A is aggressive)
    assert "tp_max" in tps
    assert tps["tp_max"] in (1.1400, 1.1500), (
        f"BLUE_A TP_max debe ser Fib ext, got {tps['tp_max']}"
    )
