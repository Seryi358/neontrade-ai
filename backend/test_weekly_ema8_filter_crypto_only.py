"""
TASK C3 — EMA 8 Weekly filter SOLO aplica a crypto.

Mentoría TradingLab: EMA 8 Weekly aparece en:
  TradingLab_Notas/Esp. Criptomonedas/01_Contenido/
    08_Indicadores cripto y su función/03_EMA 8 semanal

En Trading Mastery NO existe esta regla. Aplicarla a forex/indices/commodities
bloquea setups válidos y hace BLACK (contratendencial) totalmente inoperable.

Fix: `_check_weekly_ema8_filter` retorna True (pass-through) para instrumentos
que NO son crypto. La lógica original solo se evalúa si el instrumento es crypto.
"""

from core.market_analyzer import AnalysisResult, Trend, MarketCondition
from strategies.base import _check_weekly_ema8_filter


def _make_analysis_for_w8(
    instrument="EUR_USD",
    ema_w8=None,
    current_price=None,
):
    return AnalysisResult(
        instrument=instrument,
        htf_trend=Trend.BULLISH,
        htf_condition=MarketCondition.NEUTRAL,
        ltf_trend=Trend.BULLISH,
        htf_ltf_convergence=True,
        key_levels={"supports": [1.0900], "resistances": [1.1200],
                    "fvg": [], "fvg_zones": [], "liquidity_pools": []},
        ema_values={"EMA_H1_50": 1.1050, "EMA_H4_50": 1.1000},
        fibonacci_levels={"0.382": 1.0900, "0.618": 1.0950},
        candlestick_patterns=[],
        current_price=current_price,
        ema_w8=ema_w8,
    )


def test_weekly_ema8_filter_passes_forex_even_with_price_below_ema():
    """Forex (EUR_USD): Pass-through (no filter) aunque price < ema_w8.
    PDF: esta regla es solo para crypto."""
    analysis = _make_analysis_for_w8(
        instrument="EUR_USD",
        ema_w8=1.2000,          # Way above price
        current_price=1.1000,   # Below ema_w8
    )
    # BUY should pass (normally would be blocked: price < ema_w8)
    assert _check_weekly_ema8_filter(analysis, "BUY") is True, (
        "Forex BUY debe pasar sin filtrar por EMA 8 Weekly (no aplica a forex)"
    )
    # SELL should also pass (normally would be blocked too)
    assert _check_weekly_ema8_filter(analysis, "SELL") is True, (
        "Forex SELL debe pasar sin filtrar por EMA 8 Weekly (no aplica a forex)"
    )


def test_weekly_ema8_filter_passes_forex_missing_ema_w8():
    """Forex sin ema_w8 definida: Pass-through (no se evalúa)."""
    analysis = _make_analysis_for_w8(instrument="EUR_USD", ema_w8=None, current_price=1.1000)
    assert _check_weekly_ema8_filter(analysis, "BUY") is True
    assert _check_weekly_ema8_filter(analysis, "SELL") is True


def test_weekly_ema8_filter_passes_commodities_xau():
    """Commodities (XAU_USD): Pass-through."""
    analysis = _make_analysis_for_w8(
        instrument="XAU_USD",
        ema_w8=3000.0,
        current_price=2500.0,  # Below ema_w8
    )
    assert _check_weekly_ema8_filter(analysis, "BUY") is True, (
        "XAU BUY debe pasar aunque price < ema_w8 (no es crypto)"
    )
    assert _check_weekly_ema8_filter(analysis, "SELL") is True


def test_weekly_ema8_filter_applies_to_crypto_buy():
    """Crypto (BTC_USD): SI aplica el filter. BUY OK si price >= ema_w8."""
    analysis = _make_analysis_for_w8(
        instrument="BTC_USD",
        ema_w8=60000.0,
        current_price=65000.0,
    )
    assert _check_weekly_ema8_filter(analysis, "BUY") is True, (
        "Crypto BUY con price > ema_w8 debe pasar"
    )


def test_weekly_ema8_filter_blocks_crypto_buy_below_ema():
    """Crypto (BTC_USD): BUY bloqueado si price < ema_w8."""
    analysis = _make_analysis_for_w8(
        instrument="BTC_USD",
        ema_w8=60000.0,
        current_price=50000.0,
    )
    assert _check_weekly_ema8_filter(analysis, "BUY") is False, (
        "Crypto BUY con price < ema_w8 debe ser bloqueado"
    )


def test_weekly_ema8_filter_blocks_crypto_sell_above_ema():
    """Crypto (BTC_USD): SELL bloqueado si price > ema_w8."""
    analysis = _make_analysis_for_w8(
        instrument="BTC_USD",
        ema_w8=60000.0,
        current_price=65000.0,
    )
    assert _check_weekly_ema8_filter(analysis, "SELL") is False, (
        "Crypto SELL con price > ema_w8 debe ser bloqueado"
    )


def test_weekly_ema8_filter_crypto_missing_ema_blocks():
    """Crypto sin ema_w8 definida: bloqueado (fail-safe, datos insuficientes)."""
    analysis = _make_analysis_for_w8(
        instrument="BTC_USD",
        ema_w8=None,
        current_price=50000.0,
    )
    # Behaviour preserved: crypto without ema_w8 data blocks the trade (fail-safe).
    assert _check_weekly_ema8_filter(analysis, "BUY") is False
    assert _check_weekly_ema8_filter(analysis, "SELL") is False


def test_black_strategy_not_blocked_on_forex_without_ema_w8():
    """BLACK en forex no debe bloquearse por falta de EMA 8 W.
    Mentoría: BLACK es contratendencial; si price está por encima del promedio
    trend (bullish HTF, overbought), queremos SELL contratendencial.
    Esta regla de EMA 8 W (que bloquearía SELL si price > ema_w8) NO debería
    aplicar en forex.
    """
    analysis = _make_analysis_for_w8(
        instrument="EUR_USD",
        ema_w8=1.0500,        # Below entry price
        current_price=1.1000,  # Would block SELL under old rule
    )
    # Under old rule: SELL blocked (price > ema_w8). New rule: pass.
    assert _check_weekly_ema8_filter(analysis, "SELL") is True, (
        "BLACK contratendencial SELL en forex no debe ser bloqueado por EMA 8 W"
    )
