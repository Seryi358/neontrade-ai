"""
NeonTrade AI - Estrategias de Trading
Implementacion completa de las 6 estrategias del curso TradingLab.

Estrategias (por color):
- BLUE:  Cambio de tendencia en 1H (Onda Elliott 1-2) - 3 variantes A/B/C (ranking: A > B > C)
- RED:   Cambio de tendencia en 4H (Onda Elliott 2-3) - Requiere AMBAS EMA 50 1H y 4H rotas
- PINK:  Continuacion por patron correctivo (Onda Elliott 4->5) - 1H EMA 50 rota, 4H NO rota
- WHITE: Continuacion post-Pink (Onda 3 de Onda 5) - Entradas mas ajustadas, mayor win rate que Pink
- BLACK: Contratendencia ONLY (Onda Elliott 1) - Requiere S/R diario. RSI div H4 = bonus. Min R:R 2.0:1
- GREEN: Direccion semanal + Patron diario + Entrada 15M - UNICA estrategia para crypto. Hasta 10:1 R:R

Cada estrategia implementa:
- check_htf_conditions: Condiciones de marcos temporales altos
- check_ltf_entry: Logica de entrada en marcos temporales bajos
- get_sl_placement: Ubicacion del Stop Loss segun reglas del curso
- get_tp_levels: Niveles de Take Profit segun reglas del curso
- Sistema de confianza (0-100) con explicacion detallada en espanol
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger

from config import settings
from core.market_analyzer import AnalysisResult, Trend, MarketCondition


# ---------------------------------------------------------------------------
# Enums y dataclasses
# ---------------------------------------------------------------------------

class StrategyColor(Enum):
    BLACK = "BLACK"
    BLUE = "BLUE"
    RED = "RED"
    PINK = "PINK"
    GREEN = "GREEN"
    WHITE = "WHITE"


class EntryType(Enum):
    """TradingLab entry types (Market, Limit, Stop)."""
    MARKET = "MARKET"   # Execute at current price
    LIMIT = "LIMIT"     # Place limit order at confluence zone
    STOP = "STOP"       # Place stop order above/below level


@dataclass
class SetupSignal:
    """Senal de setup detectada por una estrategia."""
    strategy: StrategyColor
    strategy_variant: str          # ej. "BLUE_A", "BLUE_B", "BLUE_C", "RED", "BLACK"
    instrument: str
    direction: str                 # "BUY" o "SELL"
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_max: Optional[float] = None
    confidence: float = 0.0        # 0-100
    reasoning: str = ""            # Explicacion legible para humanos (ingles)
    explanation_es: str = ""       # Explicacion detallada en espanol
    elliott_wave_phase: str = ""   # Fase de onda Elliott asociada
    timeframes_analyzed: List[str] = field(default_factory=list)
    risk_reward_ratio: float = 0.0  # R:R calculado
    conditions_met: List[str] = field(default_factory=list)
    conditions_failed: List[str] = field(default_factory=list)
    entry_type: str = "MARKET"     # MARKET, LIMIT, or STOP
    limit_price: Optional[float] = None  # Price for limit/stop orders
    confluence_score: int = 0      # Positive confluence points count
    anti_confluence_score: int = 0  # Negative confluence points count
    trailing_tp_only: bool = False  # True for crypto GREEN: use EMA 50 trailing, NOT fixed TP exits


# ---------------------------------------------------------------------------
# Timeframe mapping per trading style (TradingLab MTFA)
# ---------------------------------------------------------------------------
# Day Trading:  Daily(direction) -> H4(confirmation) -> H1(setup) -> M5(execution)
# Swing Trading: Monthly(direction) -> Weekly(confirmation) -> Daily(setup) -> H1(execution)
# Scalping:     H1(direction) -> M15(confirmation) -> M5(setup) -> M1(execution)
#
# EMA keys used by strategies adapt based on trading_style setting.
# This mapping ensures BLUE/RED/PINK/WHITE/BLACK strategies work correctly
# for ALL three trading styles, not just day trading.

def _get_trading_style() -> str:
    """Get current trading style from config."""
    try:
        return settings.trading_style
    except Exception:
        return "day_trading"


def _tf_ema(role: str, period: int = 50) -> str:
    """Get the EMA key for a given role in the current trading style.

    Roles (TradingLab MTFA):
      - 'setup': The timeframe where strategies detect patterns (1H for day, D for swing)
      - 'confirm': The confirmation timeframe (4H for day, W for swing)
      - 'exec': The execution timeframe (M5 for day, H1 for swing)
      - 'direction': The directional timeframe (D for day, W or M for swing)

    Returns EMA key like 'EMA_H1_50' or 'EMA_D_50'.
    """
    style = _get_trading_style()
    tf_map = {
        "day_trading": {"setup": "H1", "confirm": "H4", "exec": "M5", "direction": "D"},
        "swing": {"setup": "D", "confirm": "W", "exec": "H1", "direction": "M"},
        "scalping": {"setup": "M5", "confirm": "M15", "exec": "M1", "direction": "H1"},
    }
    tf = tf_map.get(style, tf_map["day_trading"]).get(role, "H1")
    return f"EMA_{tf}_{period}"


# ---------------------------------------------------------------------------
# Utilidades compartidas
# ---------------------------------------------------------------------------

def _ema_val(analysis: AnalysisResult, key: str) -> Optional[float]:
    """Obtener valor de EMA del analisis; retorna None si no existe."""
    v = analysis.ema_values.get(key)
    return v if v is not None and v > 0 else None


def _nearest_below(values: List[float], ref: float) -> Optional[float]:
    """Nivel mas cercano por debajo de ref."""
    below = [v for v in values if v < ref]
    return max(below) if below else None


def _nearest_above(values: List[float], ref: float) -> Optional[float]:
    """Nivel mas cercano por encima de ref."""
    above = [v for v in values if v > ref]
    return min(above) if above else None


def _fib_zone_check(analysis: AnalysisResult, price: float, direction: str) -> Tuple[bool, str]:
    """
    Verifica si el precio esta en zona Fibonacci 0.382-0.618 (golden zone).
    Tambien reconoce 0.750 como zona extendida (menor probabilidad de continuacion).
    TradingLab: Pullbacks a 0.382, 0.500, 0.618 son estandar.
    Mas alla de 2/3 (0.618), la probabilidad de continuacion disminuye.
    0.750 se usa como referencia de zona extendida.
    Retorna (bool, descripcion).
    """
    fib = analysis.fibonacci_levels
    fib_382 = fib.get("0.382")
    fib_618 = fib.get("0.618")
    fib_500 = fib.get("0.5")
    fib_750 = fib.get("0.750") or fib.get("0.75")

    if fib_382 is None or fib_618 is None:
        return False, "No hay niveles Fibonacci disponibles"

    low = min(fib_382, fib_618)
    high = max(fib_382, fib_618)

    in_zone = low <= price <= high
    if in_zone:
        return True, f"Precio {price:.5f} en zona Fib 0.382-0.618 ({low:.5f} - {high:.5f})"

    # Check extended zone (0.618-0.750): still valid but lower probability
    if fib_750 is not None:
        ext_low = min(fib_618, fib_750)
        ext_high = max(fib_618, fib_750)
        if ext_low <= price <= ext_high:
            return True, (
                f"Precio {price:.5f} en zona Fib extendida 0.618-0.750 "
                f"({ext_low:.5f} - {ext_high:.5f}) - probabilidad reducida"
            )

    return False, f"Precio {price:.5f} fuera de zona Fib ({low:.5f} - {high:.5f})"


def _has_deceleration(analysis: AnalysisResult) -> bool:
    """Detecta desaceleracion usando condicion HTF y patrones de velas."""
    if analysis.htf_condition in (MarketCondition.DECELERATING,):
        return True
    decel_patterns = {
        "DOJI", "LOW_TEST", "HIGH_TEST", "ENGULFING_BULLISH",
        "ENGULFING_BEARISH", "MORNING_STAR", "EVENING_STAR",
        "TWEEZER_TOP", "TWEEZER_BOTTOM",
        "INSIDE_BAR_BULLISH", "INSIDE_BAR_BEARISH",
    }
    return bool(set(analysis.candlestick_patterns) & decel_patterns)


def _has_reversal_pattern(analysis: AnalysisResult, direction: str) -> Tuple[bool, str]:
    """
    Verifica si hay patron de reversal alineado con la direccion.
    direction: 'BUY' (buscamos reversal alcista) o 'SELL' (reversal bajista).
    Includes all patterns from Formación de Velas PDF.
    """
    bullish_reversals = {
        "LOW_TEST", "ENGULFING_BULLISH", "MORNING_STAR",
        "TWEEZER_BOTTOM", "INSIDE_BAR_BULLISH", "HAMMER",
    }
    bearish_reversals = {
        "HIGH_TEST", "ENGULFING_BEARISH", "EVENING_STAR",
        "TWEEZER_TOP", "INSIDE_BAR_BEARISH", "SHOOTING_STAR",
    }
    patterns = set(analysis.candlestick_patterns)

    if direction == "BUY":
        found = patterns & bullish_reversals
        if found:
            return True, f"Patron alcista detectado: {', '.join(found)}"
        return False, "Sin patron de reversal alcista"
    else:
        found = patterns & bearish_reversals
        if found:
            return True, f"Patron bajista detectado: {', '.join(found)}"
        return False, "Sin patron de reversal bajista"


def _is_at_key_level(analysis: AnalysisResult, direction: str) -> Tuple[bool, float, str]:
    """
    Verifica si el precio esta cerca de un nivel clave S/R diario.
    Para BUY: busca soporte cercano.  Para SELL: busca resistencia cercana.
    Retorna (bool, nivel, descripcion).
    """
    supports = analysis.key_levels.get("supports", [])
    resistances = analysis.key_levels.get("resistances", [])

    # Use actual current price first, then fall back to EMAs
    current_price = _get_current_price_proxy(analysis)
    if current_price is None:
        return False, 0.0, "No se puede determinar precio actual"

    tolerance = current_price * 0.003  # 0.3% de tolerancia

    if direction == "BUY":
        for s in sorted(supports, reverse=True):
            if abs(current_price - s) <= tolerance:
                return True, s, f"Precio cerca de soporte diario {s:.5f} (tolerancia {tolerance:.5f})"
        return False, 0.0, "No hay soporte diario cercano al precio actual"
    else:
        for r in sorted(resistances):
            if abs(current_price - r) <= tolerance:
                return True, r, f"Precio cerca de resistencia diaria {r:.5f} (tolerancia {tolerance:.5f})"
        return False, 0.0, "No hay resistencia diaria cercana al precio actual"


def _check_rcc_confirmation(analysis, ema_key: str, direction: str) -> bool:
    """
    TradingLab RCC: Ruptura + Cierre + Confirmación (3 steps).
    1. RUPTURA: Price breaks through the level (EMA)
    2. CIERRE: A candle CLOSES past the level (not just a wick)
    3. CONFIRMACIÓN: The NEXT candle CONTINUES in the direction

    We need at least 3 candles: breakout candle, close candle, confirmation candle.
    The last completed candle ([-2]) must have closed past the EMA (step 2),
    AND the current forming candle ([-1]) must be continuing in the same
    direction (step 3 — "la siguiente vela continúa").
    """
    ema_val = _ema_val(analysis, ema_key)
    if ema_val is None:
        return True  # Can't check, don't block

    m5_candles = getattr(analysis, 'last_candles', {}).get("M5", [])
    if len(m5_candles) < 3:
        return True  # Not enough data, don't block

    # Step 2 (CIERRE): Previous completed candle closed past the EMA
    close_candle = m5_candles[-2]
    close_price = close_candle["close"]

    # Step 3 (CONFIRMACIÓN): Current candle continues in the direction
    confirm_candle = m5_candles[-1]
    confirm_open = confirm_candle["open"]
    confirm_current = confirm_candle["close"]  # Current price of forming candle

    if direction == "BUY":
        step2 = close_price > ema_val  # Closed above EMA
        # Step 3: confirmation candle must be bullish AND also close past the EMA
        # Mentorship: "rompemos, cierre, y la siguiente vela CONTINUA" — must continue past the level
        step3 = confirm_current > confirm_open and confirm_current > ema_val
        return step2 and step3
    else:
        step2 = close_price < ema_val  # Closed below EMA
        step3 = confirm_current < confirm_open and confirm_current < ema_val
        return step2 and step3


def _check_ema_break(analysis: AnalysisResult, ema_key: str, direction: str) -> Tuple[bool, str]:
    """
    Verifica si el precio ha roto la EMA especificada.
    BUY: precio > EMA (la rompio al alza).
    SELL: precio < EMA (la rompio a la baja).
    """
    ema_val = _ema_val(analysis, ema_key)
    if ema_val is None:
        return False, f"EMA {ema_key} no disponible"

    # Precio de referencia: EMA M5 5 como proxy del precio actual
    price = _ema_val(analysis, "EMA_M5_5")
    if price is None:
        price = _ema_val(analysis, "EMA_M5_20")
    if price is None:
        return False, "No se puede determinar precio actual para comparar con EMA"

    if direction == "BUY":
        if price > ema_val:
            return True, f"Precio {price:.5f} por encima de {ema_key} ({ema_val:.5f}) - rompimiento alcista"
        return False, f"Precio {price:.5f} aun debajo de {ema_key} ({ema_val:.5f})"
    else:
        if price < ema_val:
            return True, f"Precio {price:.5f} por debajo de {ema_key} ({ema_val:.5f}) - rompimiento bajista"
        return False, f"Precio {price:.5f} aun encima de {ema_key} ({ema_val:.5f})"


def _check_ema_pullback(analysis: AnalysisResult, ema_key: str, direction: str) -> Tuple[bool, str]:
    """
    Verifica si el precio esta haciendo pullback hacia la EMA (cercano pero no la cruza de vuelta).
    BUY: precio ligeramente por encima de la EMA (pullback hacia ella).
    SELL: precio ligeramente por debajo de la EMA.
    """
    ema_val = _ema_val(analysis, ema_key)
    if ema_val is None:
        return False, f"EMA {ema_key} no disponible"

    price = _ema_val(analysis, "EMA_M5_5")
    if price is None:
        return False, "Precio actual no disponible"

    # Pullback: precio esta a menos de 0.5% de la EMA y en el lado correcto
    distance_pct = abs(price - ema_val) / ema_val * 100

    if direction == "BUY":
        if price >= ema_val and distance_pct < 0.5:
            return True, f"Pullback alcista a {ema_key}: precio {price:.5f} cerca de EMA {ema_val:.5f} ({distance_pct:.2f}%)"
        if price < ema_val and distance_pct < 0.15:
            return True, f"Pullback alcista toca {ema_key}: precio {price:.5f} ligeramente bajo EMA {ema_val:.5f}"
        return False, f"No hay pullback a {ema_key} (distancia {distance_pct:.2f}%)"
    else:
        if price <= ema_val and distance_pct < 0.5:
            return True, f"Pullback bajista a {ema_key}: precio {price:.5f} cerca de EMA {ema_val:.5f} ({distance_pct:.2f}%)"
        if price > ema_val and distance_pct < 0.15:
            return True, f"Pullback bajista toca {ema_key}: precio {price:.5f} ligeramente sobre EMA {ema_val:.5f}"
        return False, f"No hay pullback a {ema_key} (distancia {distance_pct:.2f}%)"


def _get_current_price_proxy(analysis: AnalysisResult) -> Optional[float]:
    """Best estimate of current price. Prefers actual price over EMA proxies."""
    # 1. Use actual current price from market_analyzer (M5 latest close)
    if analysis.current_price and analysis.current_price > 0:
        return analysis.current_price
    # 2. Fall back to shortest-period EMAs as proxy
    for key in ("EMA_M5_2", "EMA_M5_5", "EMA_M5_20", "EMA_H1_50"):
        v = _ema_val(analysis, key)
        if v is not None:
            return v
    return None


def _check_volume_confirmation(analysis, timeframe_key: str = "H1") -> tuple[bool, float]:
    """
    Check if current volume is above average (required by TradingLab for all breakouts).
    Returns (confirmed, volume_ratio).
    """
    vol = analysis.volume_analysis.get(timeframe_key, {})
    if not vol:
        return True, 1.0  # No volume data = pass (don't block)
    ratio = vol.get("volume_ratio", 1.0)
    return ratio >= 1.0, ratio


def _check_rsi_divergence(analysis, direction: str) -> tuple[bool, float]:
    """
    Check for RSI divergence confirming the trade direction.
    Bullish divergence: price makes lower low but RSI makes higher low (BUY signal).
    Bearish divergence: price makes higher high but RSI makes lower high (SELL signal).
    Returns (has_divergence, confidence_bonus).
    """
    divergence = getattr(analysis, 'rsi_divergence', None)
    if divergence is None:
        return (False, 0.0)
    if direction == "BUY" and divergence == "bullish":
        return (True, 10.0)  # bullish divergence supports BUY
    if direction == "SELL" and divergence == "bearish":
        return (True, 10.0)  # bearish divergence supports SELL
    return (False, 0.0)


def _check_weekly_ema8_filter(analysis, direction: str) -> bool:
    """
    TradingLab: EMA 8 Weekly is the long-term trend filter.
    BUY only if price > EMA 8 Weekly. SELL only if price < EMA 8 Weekly.
    """
    ema_w8 = getattr(analysis, 'ema_w8', None)
    if ema_w8 is None:
        return True  # No data = don't block
    current_price = analysis.current_price
    if not current_price:
        return True
    if direction == "BUY":
        return current_price >= ema_w8
    else:
        return current_price <= ema_w8


def _check_premium_discount_zone(analysis, direction: str) -> tuple[bool, str]:
    """
    TradingLab SMC: Check if price is in the correct zone for the trade direction.
    BUY should be in DISCOUNT zone, SELL in PREMIUM zone.
    Returns (favorable, description).
    """
    pd_data = getattr(analysis, 'premium_discount_zone', None)
    if pd_data is None:
        return True, ""  # No data = don't block

    # premium_discount_zone is a Dict with a "zone" key (e.g. "premium", "discount")
    zone = pd_data.get("zone") if isinstance(pd_data, dict) else pd_data
    if zone is None:
        return True, ""

    if direction == "BUY" and zone in ("discount", "deep_discount"):
        return True, f"Precio en zona de DESCUENTO {'profundo ' if zone == 'deep_discount' else ''}(favorable para compra)"
    elif direction == "SELL" and zone == "premium":
        return True, "Precio en zona PREMIUM (favorable para venta)"
    elif zone == "equilibrium":
        return True, "Precio en zona de equilibrio (neutral)"
    else:
        return False, f"Precio en zona {zone} ({direction} desfavorable)"


def _check_pivot_confluence(analysis, direction: str, entry_price: float) -> tuple[bool, float, str]:
    """
    Check if entry price is near a Pivot Point level (acts as S/R).
    Returns (near_pivot, bonus_points, description).
    """
    pivots = getattr(analysis, 'pivot_points', {})
    if not pivots or not entry_price:
        return False, 0.0, ""

    tolerance = entry_price * 0.002  # 0.2%
    bonus = 0.0
    details = []

    for level_name, level_val in pivots.items():
        if abs(entry_price - level_val) < tolerance:
            # Near a pivot level
            if direction == "BUY" and level_name.startswith("S"):
                bonus += 5.0
                details.append(f"Cerca de Pivot {level_name} ({level_val:.5f}) = soporte")
            elif direction == "SELL" and level_name.startswith("R"):
                bonus += 5.0
                details.append(f"Cerca de Pivot {level_name} ({level_val:.5f}) = resistencia")
            elif level_name == "P":
                bonus += 3.0
                details.append(f"Cerca de Pivot P ({level_val:.5f})")

    has = bonus > 0
    desc = "Pivots: " + ", ".join(details) if details else ""
    return has, bonus, desc


def _validate_elliott_fibonacci(analysis, direction: str) -> tuple[bool, str]:
    """
    TradingLab: Validate Elliott Wave position using Fibonacci rules.
    - Wave 2: simple pullback, retrace 38.2%-61.8% of Wave 1
    - Wave 4: complex pullback (ABC), retrace 38.2%-61.8% of Wave 3
      (proportional to Wave 3 which is long; deeper retracements possible)
    - Wave 3 is never the shortest impulse wave
    Alex uses only these Fib levels: 0.382, 0.5, 0.618, 0.75 (reference).
    Returns (valid, description).
    """
    ew = getattr(analysis, 'elliott_wave_detail', {})
    if not ew:
        return True, ""  # No data = don't block

    wave_label = ew.get("wave_count", "")
    fib = analysis.fibonacci_levels
    price = analysis.current_price

    # Elliott Wave fundamental rule: "la onda 3 nunca es la más corta"
    # Wave 3 can NEVER be the shortest impulse wave (1, 3, or 5)
    wave_lengths = ew.get("wave_lengths", {})
    if wave_lengths:
        w1 = wave_lengths.get("1", 0)
        w3 = wave_lengths.get("3", 0)
        w5 = wave_lengths.get("5", 0)
        if w3 > 0 and w1 > 0 and w5 > 0:
            if w3 < w1 and w3 < w5:
                return False, (
                    f"INVALIDO: Onda 3 ({w3:.5f}) es la más corta "
                    f"(W1={w1:.5f}, W5={w5:.5f}). "
                    f"Regla de Elliott: la Onda 3 NUNCA puede ser la más corta."
                )

    # Wave 3/5 role exchange: "si la onda 3 es excesivamente justa, intercambiamos papeles"
    # When Wave 3 is shorter than Wave 1, Wave 5 can target 1.618 extension
    wave3_short = False
    if wave_lengths:
        w1 = wave_lengths.get("1", 0)
        w3 = wave_lengths.get("3", 0)
        if w1 > 0 and w3 > 0 and w3 < w1:
            wave3_short = True  # Used by strategies to allow extended Wave 5 targets

    if not price or not fib:
        return True, ""

    fib_382 = fib.get("0.382")
    fib_500 = fib.get("0.5")
    fib_618 = fib.get("0.618")
    fib_750 = fib.get("0.750") or fib.get("0.75")

    if wave_label == "2" and fib_382 and fib_618:
        # Wave 2: simple pullback, expect price in 38.2%-61.8% retracement zone
        low = min(fib_382, fib_618)
        high = max(fib_382, fib_618)
        if low <= price <= high:
            return True, f"Onda 2: Precio en zona Fib 38.2-61.8% (retroceso valido)"
        else:
            return False, f"Onda 2: Precio fuera de zona Fib 38.2-61.8%"

    elif wave_label == "4" and fib_382 and fib_618:
        # Wave 4: complex pullback (ABC pattern), proportional to Wave 3.
        # TradingLab: Wave 4 uses same Fib levels (0.382-0.618) but since
        # Wave 3 is typically the longest, the correction is more developed.
        # Allow up to 0.750 as extended zone before warning.
        low = min(fib_382, fib_618)
        high = max(fib_382, fib_618)
        if low <= price <= high:
            return True, f"Onda 4: Precio en zona Fib 38.2-61.8% (retroceso valido)"
        elif fib_750 is not None:
            ext_low = min(fib_618, fib_750)
            ext_high = max(fib_618, fib_750)
            if ext_low <= price <= ext_high:
                return True, (
                    f"Onda 4: Precio en zona Fib extendida 61.8-75.0% "
                    f"(pullback complejo, aun valido pero con cautela)"
                )
        # Wave 4 can go deeper — just warn, don't block
        return True, f"Onda 4: Retroceso profundo (fuera de zona 38.2-61.8%)"

    return True, ""


def _check_minimum_candle_count(analysis, ema_key: str, direction: str, min_candles: int = 3) -> bool:
    """
    TradingLab: Before entering on a breakout, verify at least min_candles (3-5)
    have formed after the initial break. Prevents entering on false breakouts.
    Checks M5 last candles to see sustained break of the EMA.
    """
    ema_val = _ema_val(analysis, ema_key)
    if ema_val is None:
        return True  # No data = don't block

    m5_candles = getattr(analysis, 'last_candles', {}).get("M5", [])
    if len(m5_candles) < min_candles:
        return True  # Not enough data to check

    # Count how many of the last N candles closed on the correct side
    count = 0
    for candle in m5_candles[-min_candles:]:
        if direction == "BUY" and candle["close"] > ema_val:
            count += 1
        elif direction == "SELL" and candle["close"] < ema_val:
            count += 1

    return count >= min_candles


def _check_breaker_block_confluence(
    analysis, direction: str, entry_price: float
) -> tuple[bool, float, str]:
    """
    Check if entry price is near a Breaker Block (broken Order Block with flipped bias).
    A breaker block that was bullish OB -> now bearish resistance (and vice versa).
    Returns (near_breaker, bonus_points, description).
    """
    breaker_blocks = getattr(analysis, 'breaker_blocks', [])
    if not breaker_blocks or not entry_price:
        return False, 0.0, ""

    for bb in breaker_blocks:
        bb_type = bb.get("type", "")
        bb_high = bb.get("high", 0)
        bb_low = bb.get("low", 0)
        if bb_high == 0 or bb_low == 0:
            continue
        tolerance = abs(bb_high - bb_low) * 1.5  # 1.5x the BB size

        # Bullish breaker block = support (BUY near it)
        if direction == "BUY" and bb_type == "bullish":
            if bb_low - tolerance <= entry_price <= bb_high + tolerance:
                return True, 6.0, f"Breaker Block alcista ({bb_low:.5f}-{bb_high:.5f})"
        # Bearish breaker block = resistance (SELL near it)
        elif direction == "SELL" and bb_type == "bearish":
            if bb_low - tolerance <= entry_price <= bb_high + tolerance:
                return True, 6.0, f"Breaker Block bajista ({bb_low:.5f}-{bb_high:.5f})"

    return False, 0.0, ""


def _check_power_of_three(analysis, direction: str) -> tuple[bool, str]:
    """
    Check Power of Three (AMD) session alignment with trade direction.
    - Distribution phase + direction matches bias -> favorable
    - Manipulation phase + direction AGAINST manipulation -> favorable (anticipating reversal)
    Returns (favorable, description).
    """
    po3 = getattr(analysis, 'power_of_three', {})
    if not po3:
        return False, ""

    phase = po3.get("phase", "")
    bias = po3.get("direction_bias")

    if phase == "distribution" and bias:
        if (direction == "BUY" and bias == "bullish") or \
           (direction == "SELL" and bias == "bearish"):
            return True, f"Power of Three: fase distribucion, sesgo {bias} a favor"

    if phase == "manipulation":
        manip_dir = po3.get("manipulation_direction", "")
        # If manipulation went up, anticipate real move is down -> SELL favorable
        if manip_dir == "up" and direction == "SELL":
            return True, "Power of Three: manipulacion alcista, anticipando reversal bajista"
        # If manipulation went down, anticipate real move is up -> BUY favorable
        elif manip_dir == "down" and direction == "BUY":
            return True, "Power of Three: manipulacion bajista, anticipando reversal alcista"

    return False, ""


def _check_smc_confluence(analysis, direction: str, entry_price: float) -> tuple[bool, float, str]:
    """
    Check Smart Money Concepts confluence: Order Blocks, FVG, BOS/CHOCH, Breaker Blocks.
    These are already calculated in market_analyzer but not used in strategies.
    Returns (has_confluence, bonus_points, description).
    """
    bonus = 0.0
    details = []

    # Order Blocks - price near a bullish/bearish OB
    for ob in analysis.order_blocks:
        ob_type = ob.get("type", "")
        ob_high = ob.get("high", 0)
        ob_low = ob.get("low", 0)
        if ob_high == 0 or ob_low == 0:
            continue
        ob_mid = (ob_high + ob_low) / 2
        tolerance = abs(ob_high - ob_low) * 1.5  # 1.5x the OB size

        if direction == "BUY" and "bullish" in ob_type:
            if ob_low - tolerance <= entry_price <= ob_high + tolerance:
                bonus += 8.0
                details.append(f"Order Block alcista ({ob_low:.5f}-{ob_high:.5f})")
                break
        elif direction == "SELL" and "bearish" in ob_type:
            if ob_low - tolerance <= entry_price <= ob_high + tolerance:
                bonus += 8.0
                details.append(f"Order Block bajista ({ob_low:.5f}-{ob_high:.5f})")
                break

    # Breaker Blocks - price near a broken OB with flipped bias (+6 bonus)
    bb_ok, bb_bonus, bb_desc = _check_breaker_block_confluence(analysis, direction, entry_price)
    if bb_ok:
        bonus += bb_bonus
        details.append(bb_desc)

    # Fair Value Gaps - price near FVG midpoint
    fvgs = analysis.key_levels.get("fvg", [])
    if fvgs and entry_price:
        for fvg_mid in fvgs[-10:]:  # Check recent FVGs
            tolerance = entry_price * 0.003  # 0.3%
            if abs(entry_price - fvg_mid) < tolerance:
                bonus += 5.0
                details.append(f"Fair Value Gap cerca ({fvg_mid:.5f})")
                break

    # BOS/CHOCH - recent structure break confirming direction
    for sb in analysis.structure_breaks[-5:]:
        sb_type = sb.get("type", "")
        sb_dir = sb.get("direction", "")
        if direction == "BUY" and sb_dir == "bullish":
            if sb_type == "BOS":
                bonus += 5.0
                details.append(f"BOS alcista confirmado")
            elif sb_type == "CHOCH":
                bonus += 7.0
                details.append(f"CHOCH alcista (cambio de caracter)")
            break
        elif direction == "SELL" and sb_dir == "bearish":
            if sb_type == "BOS":
                bonus += 5.0
                details.append(f"BOS bajista confirmado")
            elif sb_type == "CHOCH":
                bonus += 7.0
                details.append(f"CHOCH bajista (cambio de caracter)")
            break

    # Liquidity sweep — high-probability trigger per workshop
    if hasattr(analysis, 'liquidity_sweep') and analysis.liquidity_sweep:
        sweep = analysis.liquidity_sweep
        sweep_dir = sweep.get("direction", "")
        if (direction == "BUY" and sweep_dir == "bullish") or \
           (direction == "SELL" and sweep_dir == "bearish"):
            bonus += 6.0
            level = sweep.get("level", "unknown")
            details.append(f"Liquidity sweep en {level} ({sweep_dir})")

    # Mitigation Blocks — failed OB without liquidity grab, role flips
    if hasattr(analysis, 'mitigation_blocks') and analysis.mitigation_blocks:
        for mb in analysis.mitigation_blocks:
            mb_type = mb.get("type", "")
            mb_high = mb.get("high", 0)
            mb_low = mb.get("low", 0)
            if mb_high == 0 or mb_low == 0:
                continue
            tolerance = abs(mb_high - mb_low) * 1.5

            # Mitigation blocks flip direction (like breaker blocks)
            # mitigation_bullish_ob -> after break becomes bearish resistance
            # mitigation_bearish_ob -> after break becomes bullish support
            if direction == "BUY" and "bearish_ob" in mb_type:
                if mb_low - tolerance <= entry_price <= mb_high + tolerance:
                    bonus += 4.0
                    details.append(f"Mitigation Block soporte ({mb_low:.5f}-{mb_high:.5f})")
                    break
            elif direction == "SELL" and "bullish_ob" in mb_type:
                if mb_low - tolerance <= entry_price <= mb_high + tolerance:
                    bonus += 4.0
                    details.append(f"Mitigation Block resistencia ({mb_low:.5f}-{mb_high:.5f})")
                    break

    # IFVG check — inverted FVGs should be treated as S/R in flipped direction
    fvg_details = analysis.key_levels.get("fvg_details", [])
    if fvg_details and entry_price:
        for fvg_item in fvg_details[-10:]:
            if not isinstance(fvg_item, dict):
                continue
            if not fvg_item.get("inverted", False):
                continue
            fvg_orig_dir = fvg_item.get("original_direction", "")
            fvg_mid = fvg_item.get("midpoint", 0)
            if fvg_mid <= 0:
                continue
            tolerance = entry_price * 0.003
            # IFVG: bullish FVG inverted = now bearish resistance, vice versa
            if direction == "BUY" and fvg_orig_dir == "bearish" and abs(entry_price - fvg_mid) < tolerance:
                bonus += 4.0
                details.append(f"IFVG soporte (FVG bajista invertida en {fvg_mid:.5f})")
                break
            elif direction == "SELL" and fvg_orig_dir == "bullish" and abs(entry_price - fvg_mid) < tolerance:
                bonus += 4.0
                details.append(f"IFVG resistencia (FVG alcista invertida en {fvg_mid:.5f})")
                break

    has = bonus > 0
    desc = "SMC: " + ", ".join(details) if details else "Sin confluencia SMC"
    return has, bonus, desc


def _count_confluence_points(
    analysis: AnalysisResult, direction: str, entry_price: float
) -> Tuple[int, int, List[str], List[str]]:
    """
    TradingLab: Count positive and negative confluence points between HTF and LTF.
    Returns (positive_count, negative_count, positive_details, negative_details).
    """
    pos_pts = 0
    neg_pts = 0
    pos_details: List[str] = []
    neg_details: List[str] = []

    # 1. HTF trend alignment
    if analysis.htf_trend.value == ("bullish" if direction == "BUY" else "bearish"):
        pos_pts += 1
        pos_details.append("Tendencia HTF a favor")
    elif analysis.htf_trend.value != "ranging":
        neg_pts += 1
        neg_details.append("Tendencia HTF en contra")

    # 2. LTF trend alignment
    if analysis.ltf_trend.value == ("bullish" if direction == "BUY" else "bearish"):
        pos_pts += 1
        pos_details.append("Tendencia LTF a favor")
    elif analysis.ltf_trend.value != "ranging":
        neg_pts += 1
        neg_details.append("Tendencia LTF en contra")

    # 3. HTF/LTF convergence
    if analysis.htf_ltf_convergence:
        pos_pts += 1
        pos_details.append("Convergencia HTF/LTF")
    else:
        neg_pts += 1
        neg_details.append("Divergencia HTF/LTF")

    # 4. EMA 8 Weekly filter
    if _check_weekly_ema8_filter(analysis, direction):
        pos_pts += 1
        pos_details.append("EMA 8 semanal a favor")
    else:
        neg_pts += 1
        neg_details.append("EMA 8 semanal en contra")

    # 5. Fibonacci zone
    fib_ok, _ = _fib_zone_check(analysis, entry_price, direction)
    if fib_ok:
        pos_pts += 1
        pos_details.append("Precio en zona Fibonacci")

    # 6. RSI condition
    rsi_d = analysis.rsi_values.get("D", 50)
    if direction == "BUY" and rsi_d < 30:
        pos_pts += 1
        pos_details.append(f"RSI diario sobrevendido favorable ({rsi_d:.0f})")
    elif direction == "SELL" and rsi_d > 70:
        pos_pts += 1
        pos_details.append(f"RSI diario sobrecomprado favorable ({rsi_d:.0f})")
    elif direction == "BUY" and rsi_d > 70:
        neg_pts += 1
        neg_details.append(f"RSI diario sobrecomprado ({rsi_d:.0f})")
    elif direction == "SELL" and rsi_d < 30:
        neg_pts += 1
        neg_details.append(f"RSI diario sobrevendido ({rsi_d:.0f})")

    # 7. Volume confirmation
    vol_ok, vol_ratio = _check_volume_confirmation(analysis, "H1")
    if vol_ok and vol_ratio > 1.2:
        pos_pts += 1
        pos_details.append(f"Volumen alto ({vol_ratio:.1f}x)")
    elif not vol_ok:
        neg_pts += 1
        neg_details.append("Volumen bajo")

    # 8. Reversal pattern
    has_rev, _ = _has_reversal_pattern(analysis, direction)
    if has_rev:
        pos_pts += 1
        pos_details.append("Patron de velas a favor")

    # 9. MACD alignment - check if MACD main line is above/below zero
    macd_h1 = analysis.macd_values.get("H1", {})
    if macd_h1:
        macd_val = macd_h1.get("macd", 0)
        if direction == "BUY" and macd_val > 0:
            pos_pts += 1
            pos_details.append(f"MACD H1 positivo ({macd_val:.5f})")
        elif direction == "SELL" and macd_val < 0:
            pos_pts += 1
            pos_details.append(f"MACD H1 negativo ({macd_val:.5f})")
        else:
            neg_pts += 1
            neg_details.append("MACD H1 en contra")

    # 10. SMA 200 position
    sma_d200 = analysis.sma_d200
    if sma_d200 and entry_price:
        if direction == "BUY" and entry_price > sma_d200:
            pos_pts += 1
            pos_details.append("Precio sobre SMA 200 D")
        elif direction == "SELL" and entry_price < sma_d200:
            pos_pts += 1
            pos_details.append("Precio bajo SMA 200 D")
        else:
            neg_pts += 1
            neg_details.append("SMA 200 D en contra")

    # 11. Premium/Discount zone
    pd_ok, pd_desc = _check_premium_discount_zone(analysis, direction)
    if pd_ok and pd_desc:
        pos_pts += 1
        pos_details.append(pd_desc)
    elif not pd_ok:
        neg_pts += 1
        neg_details.append(pd_desc)

    # 12. Pivot Point confluence
    piv_ok, piv_bonus, piv_desc = _check_pivot_confluence(analysis, direction, entry_price)
    if piv_ok:
        pos_pts += 1
        pos_details.append(piv_desc)

    # 13. Elliott Wave + Fibonacci validation
    ew_ok, ew_desc = _validate_elliott_fibonacci(analysis, direction)
    if ew_ok and ew_desc:
        pos_pts += 1
        pos_details.append(ew_desc)
    elif not ew_ok:
        neg_pts += 1
        neg_details.append(ew_desc)

    # 14. Power of Three / AMD session phase
    po3_ok, po3_desc = _check_power_of_three(analysis, direction)
    if po3_ok:
        pos_pts += 1
        pos_details.append(po3_desc)

    # 15. SMT Divergence (correlated pair swing comparison)
    smt_div = getattr(analysis, 'smt_divergence', None)
    if smt_div:
        expected = "bullish" if direction == "BUY" else "bearish"
        if smt_div == expected:
            pos_pts += 1
            pos_details.append(f"SMT Divergencia {smt_div} a favor")
        else:
            neg_pts += 1
            neg_details.append(f"SMT Divergencia {smt_div} en contra")

    return pos_pts, neg_pts, pos_details, neg_details


def _check_limit_entry_confluence(
    analysis: AnalysisResult, direction: str, entry_price: float
) -> Tuple[bool, Optional[float], str]:
    """
    TradingLab Limit Entry: requires 3-level confluence (Fibonacci + EMA + S/R/FVG).
    Returns (should_use_limit, limit_price, description).
    """
    if not entry_price:
        return False, None, ""

    tolerance = entry_price * 0.003  # 0.3%
    confluence_levels: List[Tuple[float, str]] = []

    # Check Fibonacci levels near price
    for fib_key in ("0.382", "0.5", "0.618"):
        fib_val = analysis.fibonacci_levels.get(fib_key)
        if fib_val and abs(entry_price - fib_val) < tolerance:
            confluence_levels.append((fib_val, f"Fib {fib_key}"))

    # Check EMAs near price
    for ema_key in ("EMA_H1_50", "EMA_H4_50"):
        ema_v = _ema_val(analysis, ema_key)
        if ema_v and abs(entry_price - ema_v) < tolerance:
            confluence_levels.append((ema_v, ema_key))

    # Check S/R levels near price
    levels_key = "supports" if direction == "BUY" else "resistances"
    for level in analysis.key_levels.get(levels_key, []):
        if abs(entry_price - level) < tolerance:
            confluence_levels.append((level, "S/R diario"))
            break

    # Check FVG near price
    for fvg_mid in analysis.key_levels.get("fvg", [])[-10:]:
        if abs(entry_price - fvg_mid) < tolerance:
            confluence_levels.append((fvg_mid, "FVG"))
            break

    # Check Pivot Points near price
    pivots = getattr(analysis, 'pivot_points', {})
    for piv_name, piv_val in pivots.items():
        if piv_val and abs(entry_price - piv_val) < tolerance:
            confluence_levels.append((piv_val, f"Pivot {piv_name}"))
            break

    if len(confluence_levels) >= 3:
        # Calculate optimal limit price as average of confluences
        avg_price = sum(p for p, _ in confluence_levels) / len(confluence_levels)
        names = ", ".join(n for _, n in confluence_levels[:4])
        return True, avg_price, f"Limit entry: {len(confluence_levels)} niveles ({names})"

    return False, None, ""


def _check_stop_entry_opportunity(
    analysis: AnalysisResult, direction: str, entry_price: float
) -> Tuple[bool, Optional[float], str]:
    """
    TradingLab Stop Entry: place a stop order above resistance (BUY) or below support (SELL)
    that triggers automatically when price reaches the level.

    Used when all timeframes align, there's strong momentum, and the trader wants
    automatic entry on a breakout above/below a key level.

    Conditions:
    - HTF/LTF convergence must be True
    - At least 2 confluence factors (S/R + one more)
    - A clear S/R level ahead in the trade direction

    For BUY: stop order placed slightly above the nearest resistance (price must break it).
    For SELL: stop order placed slightly below the nearest support.

    Returns (should_use_stop, stop_price, description).
    """
    if not entry_price:
        return False, None, ""

    # Condition 1: HTF/LTF convergence
    if not analysis.htf_ltf_convergence:
        return False, None, ""

    # Condition 2: Check momentum via MACD and trend alignment
    confluence_count = 0
    details: List[str] = []

    # Momentum: MACD H1 aligned with direction
    macd_h1 = analysis.macd_values.get("H1", {})
    if macd_h1:
        macd_val = macd_h1.get("macd", 0)
        if direction == "BUY" and macd_val > 0:
            confluence_count += 1
            details.append("MACD H1 momentum alcista")
        elif direction == "SELL" and macd_val < 0:
            confluence_count += 1
            details.append("MACD H1 momentum bajista")

    # Volume above average
    vol_ok, vol_ratio = _check_volume_confirmation(analysis, "H1")
    if vol_ok and vol_ratio > 1.0:
        confluence_count += 1
        details.append(f"Volumen favorable ({vol_ratio:.1f}x)")

    # EMA 8 Weekly filter
    if _check_weekly_ema8_filter(analysis, direction):
        confluence_count += 1
        details.append("EMA 8 semanal a favor")

    # Need at least 2 confluence factors
    if confluence_count < 2:
        return False, None, ""

    # Condition 3: Find a clear S/R level ahead
    supports = analysis.key_levels.get("supports", [])
    resistances = analysis.key_levels.get("resistances", [])

    # Determine pip size for offset (slightly beyond the level)
    pip = 0.01 if entry_price > 10 else 0.0001
    offset = 5 * pip  # 5 pips beyond the level

    if direction == "BUY":
        # Find nearest resistance above current price
        above_levels = [r for r in resistances if r > entry_price]
        if not above_levels:
            return False, None, ""
        nearest_resistance = min(above_levels)
        # Don't place stop too far away (max 1% from entry)
        distance_pct = (nearest_resistance - entry_price) / entry_price
        if distance_pct > 0.01:
            return False, None, ""
        stop_price = round(nearest_resistance + offset, 5)
        desc = (
            f"Stop entry BUY: orden sobre resistencia {nearest_resistance:.5f} "
            f"(stop @ {stop_price:.5f}). Confluencia: {', '.join(details)}"
        )
        return True, stop_price, desc

    else:  # SELL
        # Find nearest support below current price
        below_levels = [s for s in supports if s < entry_price]
        if not below_levels:
            return False, None, ""
        nearest_support = max(below_levels)
        # Don't place stop too far away (max 1% from entry)
        distance_pct = (entry_price - nearest_support) / entry_price
        if distance_pct > 0.01:
            return False, None, ""
        stop_price = round(nearest_support - offset, 5)
        desc = (
            f"Stop entry SELL: orden bajo soporte {nearest_support:.5f} "
            f"(stop @ {stop_price:.5f}). Confluencia: {', '.join(details)}"
        )
        return True, stop_price, desc


# Crypto detection: check against the actual crypto_watchlist from config
# This is more reliable than a hardcoded prefix list since new coins are
# added to the watchlist, not to a separate prefix tuple.
_crypto_watchlist_cache: set = set()


def _is_crypto_instrument(instrument: str) -> bool:
    """
    Check if an instrument is a crypto pair.
    TradingLab: GREEN is the ONLY strategy valid for crypto trading.
    Uses the crypto_watchlist from config for accurate detection.
    """
    global _crypto_watchlist_cache
    if not _crypto_watchlist_cache:
        from config import settings
        _crypto_watchlist_cache = {s.upper() for s in settings.crypto_watchlist}
    # Check exact match first, then prefix match for variants (e.g., BTC_USD vs BTCUSD)
    inst_upper = instrument.upper()
    if inst_upper in _crypto_watchlist_cache:
        return True
    # Fallback: check common crypto suffixes (_USD, USD, /USD)
    # This catches instruments like "BTCUSD" when watchlist has "BTC_USD"
    base = inst_upper.replace("_USD", "").replace("/USD", "").replace("USD", "")
    return any(w.replace("_USD", "") == base for w in _crypto_watchlist_cache)


def _classify_blue_variant(analysis: AnalysisResult, direction: str) -> str:
    """
    Clasifica la variante Blue (A, B, C) revisando condiciones en 4H.
    TradingLab confidence ranking: A > B > C
    A: Double bottom/top ("doble suelo" / "minimo creciente") visible in 1H/4H
       BEFORE breaking 1H EMA 50 (most effective, HIGHEST confidence bonus +10)
    B: Simple impulse-pullback with no prior reversal pattern (neutral, no bonus)
    C: Breaks 1H EMA 50 but rejects 4H EMA 50 BEFORE pullback (most restrictive, LOWEST confidence -5)
    """
    ema_4h_50 = _ema_val(analysis, "EMA_H4_50")

    # Variante A: structural double bottom/top detection
    # TradingLab: "doble suelo" or "minimo creciente" - two swing lows/highs
    # at similar levels (within 0.3% tolerance) visible in both 1H and 4H.
    swing_lows = getattr(analysis, 'swing_lows', [])
    swing_highs = getattr(analysis, 'swing_highs', [])
    double_pattern_tolerance = 0.003  # 0.3% tolerance for similar levels

    if direction == "BUY" and len(swing_lows) >= 2:
        # Check last two swing lows for double bottom pattern
        recent_lows = swing_lows[-2:]
        if recent_lows[0] > 0 and recent_lows[1] > 0:
            pct_diff = abs(recent_lows[0] - recent_lows[1]) / max(recent_lows[0], recent_lows[1])
            if pct_diff <= double_pattern_tolerance:
                return "BLUE_A"
            # Also detect "minimo creciente" (higher low) - the second low is higher
            if recent_lows[1] > recent_lows[0]:
                return "BLUE_A"

    if direction == "SELL" and len(swing_highs) >= 2:
        # Check last two swing highs for double top pattern
        recent_highs = swing_highs[-2:]
        if recent_highs[0] > 0 and recent_highs[1] > 0:
            pct_diff = abs(recent_highs[0] - recent_highs[1]) / max(recent_highs[0], recent_highs[1])
            if pct_diff <= double_pattern_tolerance:
                return "BLUE_A"
            # Also detect "maximo decreciente" (lower high) - the second high is lower
            if recent_highs[1] < recent_highs[0]:
                return "BLUE_A"

    # Fallback: check chart_patterns for explicit reversal pattern labels
    # TradingLab: Blue A triggers on "doble suelo, hombro cabeza hombro, minimo creciente"
    if hasattr(analysis, 'chart_patterns'):
        chart_patterns = analysis.chart_patterns or []
        for p in chart_patterns:
            ptype = p.get("type", "") if isinstance(p, dict) else str(p)
            ptype_lower = ptype.lower()
            if direction == "BUY" and any(k in ptype_lower for k in (
                "double_bottom", "doble_suelo", "double bottom",
                "inverse_head_and_shoulders",
            )):
                return "BLUE_A"
            if direction == "SELL" and any(k in ptype_lower for k in (
                "double_top", "doble_techo", "double top",
                "head_and_shoulders",
            )):
                return "BLUE_A"

    # Variante C: price REJECTED from 4H EMA50 (bounced off, not just proximity)
    # TradingLab: Blue C means price approached 4H EMA, showed reversal candle, then pulled back.
    # This is a REJECTION check, not a proximity check.
    price = _get_current_price_proxy(analysis)
    if price and ema_4h_50:
        # Check for rejection: price approached EMA 4H and bounced away
        m5_candles = getattr(analysis, 'last_candles', {}).get("M5", [])
        if len(m5_candles) >= 3:
            # Look for a candle that wicked through EMA 4H but closed on the other side (rejection)
            ema_tolerance = ema_4h_50 * 0.002  # 0.2% tolerance zone
            rejection_detected = False

            for candle in m5_candles[-5:]:
                c_high = candle.get("high", 0)
                c_low = candle.get("low", 0)
                c_open = candle.get("open", 0)
                c_close = candle.get("close", 0)

                if direction == "BUY":
                    # For BUY Blue C: price came DOWN to EMA 4H from above, wicked below, closed above
                    # (rejection of EMA as support from above → now pulling back up)
                    touched_ema = c_low <= ema_4h_50 + ema_tolerance
                    closed_above = c_close > ema_4h_50
                    is_reversal = c_close > c_open  # Bullish candle
                    if touched_ema and closed_above and is_reversal:
                        rejection_detected = True
                        break
                else:
                    # For SELL Blue C: price came UP to EMA 4H from below, wicked above, closed below
                    touched_ema = c_high >= ema_4h_50 - ema_tolerance
                    closed_below = c_close < ema_4h_50
                    is_reversal = c_close < c_open  # Bearish candle
                    if touched_ema and closed_below and is_reversal:
                        rejection_detected = True
                        break

            if rejection_detected:
                return "BLUE_C"

        # Also check if recent candles show price pulled away from EMA 4H after touching it
        # (price is now moving away from EMA = already rejected)
        if price and ema_4h_50:
            dist_pct = abs(price - ema_4h_50) / ema_4h_50 * 100
            # Price is within 0.5% of EMA but moving away (rejection in progress)
            if dist_pct < 0.5:
                # Check if price is moving away from EMA in the last 2 candles
                if len(m5_candles) >= 2:
                    prev_close = m5_candles[-2].get("close", 0)
                    curr_close = m5_candles[-1].get("close", 0)
                    if direction == "BUY" and curr_close > prev_close and curr_close > ema_4h_50:
                        return "BLUE_C"
                    elif direction == "SELL" and curr_close < prev_close and curr_close < ema_4h_50:
                        return "BLUE_C"

    # Variante B: default
    return "BLUE_B"


def _adjust_sl_away_from_round_numbers(sl: float, direction: str) -> float:
    """
    TradingLab: Nudge SL 3-5 pips away from psychological levels (x.x000, x.x500).
    Market makers tend to hunt stops at round numbers.
    For BUY (SL below entry): move SL slightly lower.
    For SELL (SL above entry): move SL slightly higher.
    """
    if sl <= 0:
        return sl

    # Determine pip size based on price magnitude
    # For JPY pairs (price > 10), 1 pip = 0.01; for others 1 pip = 0.0001
    if sl > 10:
        pip = 0.01
    else:
        pip = 0.0001

    nudge = 4 * pip  # 4 pips nudge

    # Check proximity to round numbers (x.x000, x.x500)
    # Get the fractional part at the relevant precision
    if sl > 10:
        # JPY: check .00 and .50 levels
        frac = sl % 1.0
        nearest_round = round(frac * 2) / 2  # nearest 0.00 or 0.50
        distance_to_round = abs(frac - nearest_round)
        threshold = 10 * pip  # within 10 pips of round number
    else:
        # Standard pairs: check .x000 and .x500 levels
        frac = (sl * 10000) % 1000
        # Distance to nearest 000 or 500
        nearest_round = round(frac / 500) * 500
        distance_to_round = abs(frac - nearest_round) * pip
        threshold = 10 * pip

    if distance_to_round < threshold:
        if direction == "BUY":
            # SL is below entry, move it slightly further below
            sl -= nudge
        else:
            # SL is above entry, move it slightly further above
            sl += nudge

    return round(sl, 5)


# ---------------------------------------------------------------------------
# Clase base
# ---------------------------------------------------------------------------

class BaseStrategy(ABC):
    """Clase base para todas las estrategias de trading del curso."""

    def __init__(self):
        self.color: StrategyColor = StrategyColor.BLACK
        self.name: str = "Base Strategy"
        self.min_confidence: float = 50.0

    @abstractmethod
    def check_htf_conditions(self, analysis: AnalysisResult) -> Tuple[bool, float, List[str], List[str]]:
        """
        Verificar condiciones HTF (Semanal/Diario) para esta estrategia.
        Retorna: (condiciones_cumplidas, score_parcial, condiciones_ok, condiciones_fallo)
        """
        pass

    @abstractmethod
    def check_ltf_entry(self, analysis: AnalysisResult) -> Optional[SetupSignal]:
        """Verificar LTF (4H/1H/15m/5m) para senal de entrada."""
        pass

    @abstractmethod
    def get_sl_placement(
        self, analysis: AnalysisResult, direction: str, entry_price: float
    ) -> float:
        """Calcular ubicacion del Stop Loss para esta estrategia."""
        pass

    @abstractmethod
    def get_tp_levels(
        self, analysis: AnalysisResult, direction: str, entry_price: float
    ) -> Dict[str, float]:
        """Calcular TP1 y TP_max para esta estrategia."""
        pass

    def detect(self, analysis: AnalysisResult) -> Optional[SetupSignal]:
        """Metodo principal de deteccion. Retorna SetupSignal si hay setup."""
        htf_ok, htf_score, htf_met, htf_failed = self.check_htf_conditions(analysis)
        if not htf_ok:
            logger.debug(
                f"[{self.color.value}] HTF conditions NOT met for {analysis.instrument}: "
                f"{', '.join(htf_failed)}"
            )
            return None

        signal = self.check_ltf_entry(analysis)
        if signal is not None:
            # TradingLab: Adjust SL away from round numbers (psychological levels)
            if signal.stop_loss > 0:
                adjusted_sl = _adjust_sl_away_from_round_numbers(
                    signal.stop_loss, signal.direction
                )
                if adjusted_sl != signal.stop_loss:
                    signal.stop_loss = adjusted_sl
                    signal.conditions_met.append(
                        f"SL ajustado lejos de numero psicologico: {adjusted_sl:.5f}"
                    )

            # Incorporar score de HTF al confidence total
            signal.confidence = min(100.0, signal.confidence + htf_score)
            signal.conditions_met = htf_met + signal.conditions_met
            signal.conditions_failed = htf_failed + signal.conditions_failed

            # TradingLab: Count positive/negative confluence points
            pos_pts, neg_pts, pos_details, neg_details = _count_confluence_points(
                analysis, signal.direction, signal.entry_price
            )
            signal.confluence_score = pos_pts
            signal.anti_confluence_score = neg_pts

            # TradingLab: Minimum confluence factors required (configurable)
            # The mentorship does NOT specify a minimum of 3 - default is 2.
            min_confluence = getattr(settings, 'min_confluence_points', 2)
            if pos_pts < min_confluence:
                logger.debug(
                    f"[{self.color.value}] Confluence too low: {pos_pts} positive points (min {min_confluence})"
                )
                return None

            # Bonus for high confluence
            if pos_pts >= 7:
                signal.confidence = min(100.0, signal.confidence + 10.0)
                signal.conditions_met.append(
                    f"Alta confluencia: {pos_pts} puntos positivos vs {neg_pts} negativos"
                )
            elif pos_pts >= 5:
                signal.confidence = min(100.0, signal.confidence + 5.0)
                signal.conditions_met.append(
                    f"Confluencia moderada: {pos_pts}+ vs {neg_pts}-"
                )
            if neg_pts >= 5:
                signal.confidence = max(0.0, signal.confidence - 10.0)
                signal.conditions_failed.append(
                    f"Muchos puntos negativos: {neg_pts} (detalles: {', '.join(neg_details[:3])})"
                )

            # TradingLab: Pivot Point confluence bonus
            piv_ok, piv_bonus, piv_desc = _check_pivot_confluence(
                analysis, signal.direction, signal.entry_price
            )
            if piv_ok:
                signal.confidence = min(100.0, signal.confidence + piv_bonus)
                signal.conditions_met.append(piv_desc)

            # TradingLab: Premium/Discount zone check
            pd_ok, pd_desc = _check_premium_discount_zone(analysis, signal.direction)
            if pd_ok and pd_desc:
                signal.confidence = min(100.0, signal.confidence + 3.0)
                signal.conditions_met.append(pd_desc)
            elif not pd_ok:
                signal.confidence = max(0.0, signal.confidence - 5.0)
                signal.conditions_failed.append(pd_desc)

            # TradingLab: Minimum candle count (3 candles sustaining breakout)
            if not _check_minimum_candle_count(analysis, "EMA_M5_50", signal.direction, 3):
                signal.confidence = max(0.0, signal.confidence - 8.0)
                signal.conditions_failed.append(
                    "Rompimiento reciente: menos de 3 velas confirmando"
                )

            # TradingLab: Elliott Wave + Fibonacci validation
            ew_ok, ew_desc = _validate_elliott_fibonacci(analysis, signal.direction)
            if not ew_ok:
                signal.confidence = max(0.0, signal.confidence - 5.0)
                signal.conditions_failed.append(ew_desc)
            elif ew_desc:
                signal.conditions_met.append(ew_desc)

            # TradingLab: PINK and BLACK must ALWAYS use MARKET entries.
            # Limit and Stop entries are only available for BLUE, RED, and WHITE.
            _allows_non_market = self.color in (
                StrategyColor.BLUE, StrategyColor.RED, StrategyColor.WHITE,
            )

            # TradingLab: Check for limit entry opportunity (3-level confluence)
            if _allows_non_market:
                limit_ok, limit_price, limit_desc = _check_limit_entry_confluence(
                    analysis, signal.direction, signal.entry_price
                )
                if limit_ok and limit_price:
                    signal.entry_type = "LIMIT"
                    signal.limit_price = limit_price
                    signal.confidence = min(100.0, signal.confidence + 5.0)
                    signal.conditions_met.append(limit_desc)

            # TradingLab: Check for stop entry opportunity (breakout above/below S/R)
            # Only for strategies NOT already using limit entry AND that allow non-market
            if _allows_non_market and signal.entry_type != "LIMIT":
                stop_ok, stop_price, stop_desc = _check_stop_entry_opportunity(
                    analysis, signal.direction, signal.entry_price
                )
                if stop_ok and stop_price:
                    signal.entry_type = "STOP"
                    signal.limit_price = stop_price
                    signal.confidence = min(100.0, signal.confidence + 3.0)
                    signal.conditions_met.append(stop_desc)

            logger.info(
                f"[{self.color.value}] SETUP detectado {analysis.instrument} "
                f"| {signal.direction} | Confianza: {signal.confidence:.0f}% "
                f"| Variante: {signal.strategy_variant} "
                f"| Confluencia: +{pos_pts}/-{neg_pts} "
                f"| Entrada: {signal.entry_type}"
            )
        return signal

    def _determine_direction(self, analysis: AnalysisResult) -> Optional[str]:
        """Determinar direccion basada en tendencia HTF."""
        if analysis.htf_trend == Trend.BULLISH:
            return "BUY"
        elif analysis.htf_trend == Trend.BEARISH:
            return "SELL"
        return None


# ===========================================================================
# BLUE STRATEGY - Cambio de Tendencia en 1H (Onda Elliott 1-2)
# ===========================================================================

class BlueStrategy(BaseStrategy):
    """
    BLUE Strategy - Cambio de Tendencia en 1H (Onda Elliott 1-2)

    Tres variantes (confidence ranking: A > B > C):
    - Blue A: Double bottom/reversal pattern BEFORE breaking 1H EMA 50 (most effective, +10 bonus)
    - Blue B: Simple impulse-pullback with no prior reversal pattern (neutral, no bonus)
    - Blue C: Breaks 1H EMA 50 but rejects 4H EMA 50 BEFORE pullback (most restrictive, -5 penalty)

    7 Pasos:
    1. Nivel S/R diario (soporte para long, resistencia para short)
    2. Precio ataca el nivel y desacelera en diario
    3. Bajar a 1H: cambio de tendencia confirmado (EMA 50 1H rota + maximos mas altos)
    4. Pullback a EMA 50 1H + niveles Fibonacci (0.382-0.618)
    5. Desaceleracion y giro en 1H (o giro directo)
    6. Bajar a 5M: ejecutar en rompimiento+cierre+confirmacion de EMA 5M / diagonal / EMA 2M
    7. SL debajo de Fib 0.618 o minimo anterior. TP en EMA 50 4H
    """

    def __init__(self):
        super().__init__()
        self.color = StrategyColor.BLUE
        self.name = "BLUE - Cambio de Tendencia 1H (Elliott 1-2)"
        self.min_confidence = 55.0

    def check_htf_conditions(self, analysis: AnalysisResult) -> Tuple[bool, float, List[str], List[str]]:
        score = 0.0
        met: List[str] = []
        failed: List[str] = []

        # --- Paso 1: Nivel S/R diario ---
        direction = self._determine_direction(analysis)
        if direction is None:
            # Para Blue, tambien podemos detectar reversal en ranging
            if analysis.htf_condition in (MarketCondition.OVERSOLD,):
                direction = "BUY"
            elif analysis.htf_condition in (MarketCondition.OVERBOUGHT,):
                direction = "SELL"
            else:
                failed.append("Paso 1: No hay tendencia HTF ni condicion extrema para determinar direccion")
                return False, score, met, failed

        at_level, level_val, level_desc = _is_at_key_level(analysis, direction)
        if at_level:
            score += 15.0
            met.append(f"Paso 1: {level_desc}")
        else:
            # No es descalificante pero resta confianza
            failed.append(f"Paso 1: {level_desc}")

        # --- Paso 2: Desaceleracion en diario ---
        if _has_deceleration(analysis):
            score += 15.0
            met.append("Paso 2: Desaceleracion detectada en diario")
        else:
            failed.append("Paso 2: Sin desaceleracion clara en diario")

        # --- Paso 3: Cambio de tendencia en setup TF (1H for day, Daily for swing) ---
        setup_ema_key = _tf_ema("setup", 50)
        ema_1h_break, ema_1h_desc = _check_ema_break(analysis, setup_ema_key, direction)
        if ema_1h_break:
            score += 20.0
            met.append(f"Paso 3: {ema_1h_desc}")
        else:
            failed.append(f"Paso 3: {ema_1h_desc}")
            # Sin rompimiento de EMA 50 1H, Blue no es valida
            return False, score, met, failed

        # Necesitamos al menos Paso 3 para continuar
        # Score minimo para pasar: haber roto la EMA 50 1H
        passed = score >= 20.0
        return passed, score, met, failed

    def check_ltf_entry(self, analysis: AnalysisResult) -> Optional[SetupSignal]:
        direction = self._determine_direction(analysis)
        if direction is None:
            if analysis.htf_condition == MarketCondition.OVERSOLD:
                direction = "BUY"
            elif analysis.htf_condition == MarketCondition.OVERBOUGHT:
                direction = "SELL"
            else:
                return None

        # Style-adaptive EMA keys (same as check_htf_conditions)
        setup_ema_key = _tf_ema("setup", 50)
        confirm_ema_key = _tf_ema("confirm", 50)

        # TradingLab: Volume confirmation - confluence scoring, not hard block
        # The mentorship does NOT make volume a hard requirement for every entry.
        vol_ok, vol_ratio = _check_volume_confirmation(analysis, "M5")

        # TradingLab: EMA 8 Weekly trend filter
        # BLUE operates in Wave 1-2 (early trend changes) where the weekly EMA
        # may not have turned yet. Use confidence penalty, not hard block.
        weekly_ema8_aligned = _check_weekly_ema8_filter(analysis, direction)

        entry_price = _get_current_price_proxy(analysis)
        if entry_price is None:
            return None

        confidence = 0.0
        if not weekly_ema8_aligned:
            confidence -= 15.0  # Penalty for trading against weekly EMA 8
        met: List[str] = []
        failed: List[str] = []

        # Volume confluence scoring (not hard block)
        if vol_ok and vol_ratio > 1.2:
            confidence += 5.0
            met.append(f"Volumen alto ({vol_ratio:.1f}x) confirma entrada")
        elif not vol_ok:
            confidence -= 3.0
            failed.append(f"Volumen bajo ({vol_ratio:.1f}x) - sin confirmacion de volumen")

        # --- Paso 4: Pullback a setup-TF EMA 50 + Fibonacci ---
        pb_ok, pb_desc = _check_ema_pullback(analysis, setup_ema_key, direction)
        if pb_ok:
            confidence += 15.0
            met.append(f"Paso 4: {pb_desc}")
        else:
            failed.append(f"Paso 4: {pb_desc}")
            # Sin pullback, no hay entrada Blue
            return None

        fib_ok, fib_desc = _fib_zone_check(analysis, entry_price, direction)
        if fib_ok:
            confidence += 10.0
            met.append(f"Paso 4b: {fib_desc}")
        else:
            failed.append(f"Paso 4b: {fib_desc}")

        # --- Paso 5: Desaceleracion y giro en 1H ---
        has_reversal, rev_desc = _has_reversal_pattern(analysis, direction)
        if has_reversal:
            confidence += 15.0
            met.append(f"Paso 5: {rev_desc}")
        elif _has_deceleration(analysis):
            confidence += 8.0
            met.append("Paso 5: Desaceleracion detectada (sin patron de giro completo)")
        else:
            failed.append(f"Paso 5: {rev_desc}")

        # --- Paso 6: Entrada en 5M (RCC: Ruptura + Cierre + Confirmación) ---
        # TradingLab execution priority: "5min MA50 > diagonal > 2min MA/diagonal"
        # 1. Check EMA M5 50 break (HIGHEST priority)
        # 2. If not, check diagonal on 5min
        # 3. If not, check EMA M2 50 (2min, approximated by M5 EMA 20)
        # 4. If not, check diagonal on 2min
        ema_5m_break, ema_5m_desc = _check_ema_break(analysis, "EMA_M5_50", direction)
        # M2 not available from broker API; use M5 EMA 20 as approximation
        # (EMA 50 on M2 ≈ EMA 20 on M5 since M5 is 2.5x the M2 timeframe)
        ema_2m_break, ema_2m_desc = _check_ema_break(analysis, "EMA_M5_20", direction)

        entry_found = False

        # Priority 1: EMA M5 50 break (highest priority per mentorship)
        if ema_5m_break:
            # TradingLab RCC: verify previous candle confirmed the breakout
            if _check_rcc_confirmation(analysis, "EMA_M5_50", direction):
                confidence += 12.0
                met.append(f"Paso 6: RCC confirmado en EMA 5M 50 (prioridad maxima) - {ema_5m_desc}")
            else:
                # RCC failure = REJECT entry (mentorship: "NEVER enter on break alone")
                failed.append(f"Paso 6: EMA 5M rota pero sin confirmacion RCC - entrada rechazada")
                return None
            entry_found = True

        # Priority 2: Diagonal breakout on 5min
        if not entry_found and hasattr(analysis, 'chart_patterns'):
            chart_patterns = analysis.chart_patterns or []
            for p in chart_patterns:
                ptype = p.get("type", "") if isinstance(p, dict) else str(p)
                ptf = p.get("timeframe", "") if isinstance(p, dict) else ""
                ptype_lower = ptype.lower()
                if any(k in ptype_lower for k in ("diagonal", "trendline", "wedge_break")):
                    if ptf in ("M5", ""):
                        confidence += 10.0
                        met.append(f"Paso 6: Rompimiento de diagonal en 5M ({ptype})")
                        entry_found = True
                        break

        # Priority 3: EMA M2 50 break (2min timeframe)
        if not entry_found and ema_2m_break:
            if _check_rcc_confirmation(analysis, "EMA_M5_20", direction):
                confidence += 8.0
                met.append(f"Paso 6: RCC confirmado en EMA 2M (M5 proxy) - {ema_2m_desc}")
            else:
                # RCC failure = REJECT entry
                failed.append(f"Paso 6: EMA 2M rota pero sin confirmacion RCC - entrada rechazada")
                return None
            entry_found = True

        # Priority 4: Diagonal breakout on 2min
        if not entry_found and hasattr(analysis, 'chart_patterns'):
            chart_patterns = analysis.chart_patterns or []
            for p in chart_patterns:
                ptype = p.get("type", "") if isinstance(p, dict) else str(p)
                ptf = p.get("timeframe", "") if isinstance(p, dict) else ""
                ptype_lower = ptype.lower()
                if any(k in ptype_lower for k in ("diagonal", "trendline", "wedge_break")):
                    if ptf == "M2":
                        confidence += 6.0
                        met.append(f"Paso 6: Rompimiento de diagonal en 2M ({ptype})")
                        entry_found = True
                        break

        if not entry_found:
            failed.append(f"Paso 6: Sin entrada valida (ni EMA 5M/2M ni diagonal) - {ema_5m_desc}")

        # Additional confirmation: EMA 2M break adds confluence if not already the primary entry
        if entry_found and ema_2m_break and ema_5m_break:
            confidence += 5.0
            met.append(f"Paso 6b: Confirmacion EMA 2M - {ema_2m_desc}")

        # Clasificar variante
        variant = _classify_blue_variant(analysis, direction)

        # Bonus por variante
        if variant == "BLUE_A":
            confidence += 10.0
            met.append("Variante A: Doble suelo/techo detectado (mas confiable)")
        elif variant == "BLUE_C":
            confidence -= 5.0
            met.append("Variante C: Rechazo de EMA 4H (mas riesgosa)")

        if variant == "BLUE_C":
            # TradingLab: Blue C requires daily timeframe in our favor
            htf_needed = "bullish" if direction == "BUY" else "bearish"
            if analysis.htf_trend.value != htf_needed:
                failed.append(f"Blue C requiere HTF a favor (necesita {htf_needed}, tiene {analysis.htf_trend.value})")
                return None

        # TradingLab: RSI divergence bonus
        has_div, div_bonus = _check_rsi_divergence(analysis, direction)
        if has_div:
            confidence += div_bonus

        # TradingLab SMC: Order Block / FVG / BOS confluence
        smc_ok, smc_bonus, smc_desc = _check_smc_confluence(analysis, direction, entry_price)
        if smc_ok:
            confidence += smc_bonus
            met.append(f"SMC: {smc_desc}")

        # --- Paso 7: SL y TP ---
        sl = self.get_sl_placement(analysis, direction, entry_price)
        tp_levels = self.get_tp_levels(analysis, direction, entry_price, variant=variant)
        tp1 = tp_levels.get("tp1", 0.0)

        if sl == 0.0 or tp1 == 0.0:
            failed.append("Paso 7: No se pudo calcular SL o TP")
            return None

        # Validar que TP esté en el lado correcto de la entrada
        if direction == "BUY" and tp1 <= entry_price:
            failed.append(f"Paso 7: TP1 ({tp1:.5f}) debe estar encima de entrada ({entry_price:.5f}) para BUY")
            return None
        if direction == "SELL" and tp1 >= entry_price:
            failed.append(f"Paso 7: TP1 ({tp1:.5f}) debe estar debajo de entrada ({entry_price:.5f}) para SELL")
            return None

        # Validar R:R minimo (config: min_rr_ratio para Blue)
        min_rr = settings.min_rr_ratio
        if variant == "BLUE_C":
            min_rr = settings.min_rr_blue_c  # Blue C requires min 2:1 R:R (mentorship: "minimo 2 a 1, incluso 3 a 1")

        risk = abs(entry_price - sl)
        reward = abs(tp1 - entry_price)
        if risk > 0:
            rr = reward / risk
            if rr < min_rr - 1e-9:
                failed.append(f"R:R insuficiente: {rr:.2f}:1 (minimo {min_rr}:1)")
                return None
            met.append(f"R:R valido: {rr:.2f}:1")
        else:
            return None

        if confidence < self.min_confidence:
            return None

        explanation_es = (
            f"Estrategia BLUE ({variant}) - Cambio de tendencia en 1H\n"
            f"Direccion: {'COMPRA' if direction == 'BUY' else 'VENTA'}\n"
            f"Onda Elliott: Fase 1-2\n"
            f"Entrada: {entry_price:.5f} | SL: {sl:.5f} | TP: {tp1:.5f}\n"
            f"R:R: {rr:.2f}:1 | Confianza: {confidence:.0f}%\n"
            f"Condiciones cumplidas: {len(met)} | Fallidas: {len(failed)}\n"
            f"Detalles:\n" + "\n".join(f"  + {m}" for m in met)
        )
        if failed:
            explanation_es += "\n" + "\n".join(f"  - {f}" for f in failed)

        return SetupSignal(
            strategy=self.color,
            strategy_variant=variant,
            instrument=analysis.instrument,
            direction=direction,
            entry_price=entry_price,
            stop_loss=sl,
            take_profit_1=tp1,
            take_profit_max=tp_levels.get("tp_max"),
            confidence=confidence,
            reasoning=f"BLUE {variant}: 1H trend change at daily S/R. Pullback to EMA50 1H + Fib zone. Entry on 5M break.",
            explanation_es=explanation_es,
            elliott_wave_phase="Onda 1-2",
            timeframes_analyzed=["D", "H4", "H1", "M5", "M2"],
            risk_reward_ratio=rr,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_sl_placement(self, analysis: AnalysisResult, direction: str, entry_price: float) -> float:
        """
        TradingLab BLUE SL: SIEMPRE proteger el minimo/maximo anterior.
        Fib 0.618 es solo orientacion — si el minimo esta por debajo de 0.618,
        SL va debajo del minimo. Si el minimo esta por ENCIMA de 0.618,
        SL va debajo del minimo (NO en 0.618).
        Alex: "siempre protegemos el minimo anterior, 0.618 simplemente es una orientacion"
        Alex: "dandole un poquito de espacio" — buffer de 0.2% debajo del nivel.
        """
        fib_618 = analysis.fibonacci_levels.get("0.618", 0.0)
        supports = analysis.key_levels.get("supports", [])
        resistances = analysis.key_levels.get("resistances", [])
        buffer_pct = 0.002  # "poquito de espacio" — 0.2% buffer

        if direction == "BUY":
            # Minimo anterior (soporte mas cercano por debajo) tiene PRIORIDAD
            below = [s for s in supports if s < entry_price]
            prev_min = max(below) if below else None
            if prev_min is not None:
                # Mentorship: SL siempre debajo del minimo anterior
                sl = prev_min * (1 - buffer_pct)
            elif fib_618 > 0 and fib_618 < entry_price:
                # Fallback a Fib 0.618 si no hay minimo anterior
                sl = fib_618 * (1 - buffer_pct)
            else:
                # Ultimo recurso: 1% debajo de entrada
                sl = entry_price * 0.99
            return sl
        else:  # SELL
            above = [r for r in resistances if r > entry_price]
            prev_max = min(above) if above else None
            if prev_max is not None:
                sl = prev_max * (1 + buffer_pct)
            elif fib_618 > 0 and fib_618 > entry_price:
                sl = fib_618 * (1 + buffer_pct)
            else:
                return entry_price * 1.01
            return sl

    def get_tp_levels(self, analysis: AnalysisResult, direction: str, entry_price: float, variant: str = "BLUE_B") -> Dict[str, float]:
        """
        BLUE TP levels — variant-specific per TradingLab mentorship:
        - BLUE_A: TP1 = confirm-TF EMA50, TP_max = Fib 1.272 or 1.618 extension
        - BLUE_B/C: TP1 = confirm-TF EMA50 only (no Fib extensions)
        Swing adaptation: TP1 = EMA 50 Weekly (not 4H) per mentorship.
        """
        # Use style-adaptive confirm-timeframe EMA (4H for day, Weekly for swing, M15 for scalping)
        confirm_ema_key = _tf_ema("confirm", 50)
        ema_4h_50 = _ema_val(analysis, confirm_ema_key) or _ema_val(analysis, "EMA_H4_50")
        resistances = analysis.key_levels.get("resistances", [])
        supports = analysis.key_levels.get("supports", [])

        result: Dict[str, float] = {}
        if ema_4h_50 and ema_4h_50 > 0:
            # Only use EMA as TP if it's on the correct side of entry
            if direction == "BUY" and ema_4h_50 > entry_price:
                result["tp1"] = ema_4h_50
            elif direction == "SELL" and ema_4h_50 < entry_price:
                result["tp1"] = ema_4h_50

        if "tp1" not in result:
            # Fallback: resistencia/soporte mas cercano
            if direction == "BUY":
                above = [r for r in resistances if r > entry_price]
                if above:
                    result["tp1"] = min(above)
            else:
                below = [s for s in supports if s < entry_price]
                if below:
                    result["tp1"] = max(below)

        # BLUE_A variant: TP_max targets Fib 1.272 or 1.618 extension (more aggressive)
        # BLUE_B/C variants: TP_max = EMA 4H only (conservative)
        tp1 = result.get("tp1")
        if tp1 and variant == "BLUE_A":
            # TradingLab: Blue A (doble suelo/techo) can target Fib extensions
            fib_1272 = (
                analysis.fibonacci_levels.get("ext_bull_1.272") if direction == "BUY"
                else analysis.fibonacci_levels.get("ext_bear_1.272")
            )
            fib_1618 = (
                analysis.fibonacci_levels.get("ext_bull_1.618") if direction == "BUY"
                else analysis.fibonacci_levels.get("ext_bear_1.618")
            )
            # Try 1.618 first (most aggressive), then 1.272
            if fib_1618:
                valid = (fib_1618 > tp1) if direction == "BUY" else (fib_1618 < tp1)
                if valid:
                    result["tp_max"] = fib_1618
            if "tp_max" not in result and fib_1272:
                valid = (fib_1272 > tp1) if direction == "BUY" else (fib_1272 < tp1)
                if valid:
                    result["tp_max"] = fib_1272
            # Fallback to next S/R if no Fib extensions available
            if "tp_max" not in result:
                if direction == "BUY":
                    above_tp1 = sorted([r for r in resistances if r > tp1])
                    if above_tp1:
                        result["tp_max"] = above_tp1[0]
                else:
                    below_tp1 = sorted([s for s in supports if s < tp1], reverse=True)
                    if below_tp1:
                        result["tp_max"] = below_tp1[0]
        elif tp1:
            # BLUE_B/C: TP_max = EMA 4H (Trading Plan rule: "BLUE B/C: TP maximo = EMA 4H")
            ema_h4 = _ema_val(analysis, "EMA_H4_50")
            if ema_h4 and direction == "BUY" and ema_h4 > tp1:
                result["tp_max"] = ema_h4
            elif ema_h4 and direction == "SELL" and ema_h4 < tp1:
                result["tp_max"] = ema_h4
            else:
                # Fallback to next S/R if EMA H4 not usable
                if direction == "BUY":
                    above_tp1 = sorted([r for r in resistances if r > tp1])
                    if above_tp1:
                        result["tp_max"] = above_tp1[0]
                else:
                    below_tp1 = sorted([s for s in supports if s < tp1], reverse=True)
                    if below_tp1:
                        result["tp_max"] = below_tp1[0]

        return result


# ===========================================================================
# RED STRATEGY - Cambio de Tendencia en 4H (Onda Elliott 2-3)
# ===========================================================================

class RedStrategy(BaseStrategy):
    """
    RED Strategy - Cambio de Tendencia en 4H (Onda Elliott 2-3)

    TradingLab: RED requires BOTH 1H AND 4H EMA 50 broken.
    Used for Wave 3 (target up to 1.618 extension) or Wave 5.

    7 Pasos:
    1. Nivel S/R diario
    2. Precio ataca y desacelera en diario
    3. AMBAS EMA 50 1H y EMA 50 4H rotas (maximos mas altos + diagonales)
    4. Bajar a 1H: pullback a EMA 50 1H + EMA 50 4H + Fibonacci
    5. Desaceleracion en 1H
    6. Bajar a 5M: ejecutar en rompimiento+cierre+confirmacion de diagonal
    7. SL debajo de EMA 50 4H o minimo anterior. TP en swing high reciente (o Fib extension 1.272/1.618)
    """

    def __init__(self):
        super().__init__()
        self.color = StrategyColor.RED
        self.name = "RED - Cambio de Tendencia 4H (Elliott 2-3)"
        self.min_confidence = 55.0

    def check_htf_conditions(self, analysis: AnalysisResult) -> Tuple[bool, float, List[str], List[str]]:
        score = 0.0
        met: List[str] = []
        failed: List[str] = []

        direction = self._determine_direction(analysis)
        if direction is None:
            if analysis.htf_condition == MarketCondition.OVERSOLD:
                direction = "BUY"
            elif analysis.htf_condition == MarketCondition.OVERBOUGHT:
                direction = "SELL"
            else:
                failed.append("Paso 1: Sin direccion HTF determinable")
                return False, score, met, failed

        # --- Paso 1: Nivel S/R diario ---
        at_level, level_val, level_desc = _is_at_key_level(analysis, direction)
        if at_level:
            score += 15.0
            met.append(f"Paso 1: {level_desc}")
        else:
            failed.append(f"Paso 1: {level_desc}")

        # --- Paso 2: Desaceleracion en diario ---
        if _has_deceleration(analysis):
            score += 15.0
            met.append("Paso 2: Desaceleracion detectada en diario")
        else:
            failed.append("Paso 2: Sin desaceleracion clara en diario")

        # --- Paso 3: Cambio de tendencia en confirm + setup TF (AMBAS EMA 50 rotas) ---
        # TradingLab: RED requires BOTH setup AND confirm EMA 50 broken.
        # Style-adaptive: day=H1+H4, swing=D+W, scalping=M5+M15
        setup_ema_key = _tf_ema("setup", 50)
        confirm_ema_key = _tf_ema("confirm", 50)
        ema_4h_break, ema_4h_desc = _check_ema_break(analysis, confirm_ema_key, direction)
        ema_1h_break, ema_1h_desc = _check_ema_break(analysis, setup_ema_key, direction)

        if ema_1h_break:
            score += 10.0
            met.append(f"Paso 3a: EMA 50 1H rota - {ema_1h_desc}")
        else:
            failed.append(f"Paso 3a: EMA 50 1H NO rota - {ema_1h_desc}")
            # Sin rompimiento de EMA 50 1H, Red no es valida
            return False, score, met, failed

        if ema_4h_break:
            score += 10.0
            met.append(f"Paso 3b: EMA 50 4H rota - {ema_4h_desc}")
        else:
            failed.append(f"Paso 3b: EMA 50 4H NO rota - {ema_4h_desc}")
            # Sin rompimiento de EMA 50 4H, Red no es valida
            return False, score, met, failed

        # Convergencia HTF/LTF: hard-block when missing
        # Mentorship: "no operes contra tendencia"
        if analysis.htf_ltf_convergence:
            score += 10.0
            met.append("Convergencia HTF/LTF confirmada")
        else:
            failed.append("Convergencia HTF/LTF ausente — RED bloqueado (no operes contra tendencia)")
            return False, score, met, failed

        passed = score >= 20.0
        return passed, score, met, failed

    def check_ltf_entry(self, analysis: AnalysisResult) -> Optional[SetupSignal]:
        direction = self._determine_direction(analysis)
        if direction is None:
            if analysis.htf_condition == MarketCondition.OVERSOLD:
                direction = "BUY"
            elif analysis.htf_condition == MarketCondition.OVERBOUGHT:
                direction = "SELL"
            else:
                return None

        # TradingLab: Volume confirmation - confluence scoring, not hard block
        vol_ok, vol_ratio = _check_volume_confirmation(analysis, "M5")

        # TradingLab: EMA 8 Weekly trend filter
        if not _check_weekly_ema8_filter(analysis, direction):
            return None  # Don't trade against weekly trend

        entry_price = _get_current_price_proxy(analysis)
        if entry_price is None:
            return None

        confidence = 0.0
        met: List[str] = []
        failed: List[str] = []

        # Volume confluence scoring (not hard block)
        if vol_ok and vol_ratio > 1.2:
            confidence += 5.0
            met.append(f"Volumen alto ({vol_ratio:.1f}x) confirma entrada")
        elif not vol_ok:
            confidence -= 3.0
            failed.append(f"Volumen bajo ({vol_ratio:.1f}x) - sin confirmacion de volumen")

        # --- Paso 3.5: Check for uncontrolled setup EMA break ---
        # TradingLab: be "permisivos" with the setup EMA break during pullback,
        # BUT if the break is "uncontrolled" (price continues strongly through
        # with large bodies, no pullback), it's NOT a RED - it's just momentum.
        # Style-adaptive: day=H1, swing=D, scalping=M5
        setup_ema_key = _tf_ema("setup", 50)
        confirm_ema_key = _tf_ema("confirm", 50)
        ema_1h_val = _ema_val(analysis, setup_ema_key) or _ema_val(analysis, "EMA_H1_50")
        m5_candles = getattr(analysis, 'last_candles', {}).get("M5", [])
        if ema_1h_val and len(m5_candles) >= 3:
            aggressive_count = 0
            for candle in m5_candles[-3:]:
                body_size = abs(candle.get("close", 0) - candle.get("open", 0))
                candle_range = candle.get("high", 0) - candle.get("low", 0)
                if candle_range > 0:
                    body_ratio = body_size / candle_range
                    # Large body (>70% of candle range) = aggressive/momentum candle
                    if body_ratio > 0.70:
                        # Check if it's moving away from the EMA (uncontrolled)
                        if direction == "BUY" and candle.get("close", 0) > candle.get("open", 0):
                            aggressive_count += 1
                        elif direction == "SELL" and candle.get("close", 0) < candle.get("open", 0):
                            aggressive_count += 1
            if aggressive_count >= 2:
                # Uncontrolled break: 2+ aggressive candles = REJECT
                # Alex says "fuera" (out) at uncontrolled break — not just a penalty
                failed.append(
                    f"Rompimiento EMA 1H NO controlado ({aggressive_count} velas agresivas "
                    f"consecutivas) - no es pullback, es momentum puro — RECHAZADO"
                )
                logger.debug(
                    f"[RED] Uncontrolled 1H EMA break on {analysis.instrument}: "
                    f"{aggressive_count} aggressive candles - rejecting (Alex: 'fuera')"
                )
                return None

        # --- Paso 4: Pullback a EMA 50 setup + confirm TF + Fibonacci ---
        # Style-adaptive: day=H1+H4, swing=D+W, scalping=M5+M15
        pb_1h, pb_1h_desc = _check_ema_pullback(analysis, setup_ema_key, direction)
        pb_4h, pb_4h_desc = _check_ema_pullback(analysis, confirm_ema_key, direction)

        if pb_1h:
            confidence += 10.0
            met.append(f"Paso 4a: {pb_1h_desc}")
        else:
            failed.append(f"Paso 4a: {pb_1h_desc}")

        if pb_4h:
            confidence += 10.0
            met.append(f"Paso 4b: {pb_4h_desc}")
        else:
            failed.append(f"Paso 4b: {pb_4h_desc}")

        # Necesitamos al menos un pullback
        if not pb_1h and not pb_4h:
            return None

        fib_ok, fib_desc = _fib_zone_check(analysis, entry_price, direction)
        if fib_ok:
            confidence += 10.0
            met.append(f"Paso 4c: {fib_desc}")
        else:
            failed.append(f"Paso 4c: {fib_desc}")

        # --- Paso 5: Desaceleracion en 1H ---
        if _has_deceleration(analysis):
            confidence += 10.0
            met.append("Paso 5: Desaceleracion detectada en 1H")
        else:
            failed.append("Paso 5: Sin desaceleracion en 1H")

        has_reversal, rev_desc = _has_reversal_pattern(analysis, direction)
        if has_reversal:
            confidence += 10.0
            met.append(f"Paso 5b: {rev_desc}")

        # --- Paso 6: Entrada en 5M (RCC) ---
        # TradingLab execution priority: "5min MA50 > diagonal > 2min MA/diagonal"
        # 1. Check EMA M5 50 break (HIGHEST priority)
        # 2. If not, check diagonal on 5min
        # 3. If not, check EMA M2 50 (2min, approximated by M5 EMA 20)
        # 4. If not, check diagonal on 2min
        ema_5m_break, ema_5m_desc = _check_ema_break(analysis, "EMA_M5_50", direction)
        # M2 not available from broker API; use M5 EMA 20 as approximation
        # (EMA 50 on M2 ≈ EMA 20 on M5 since M5 is 2.5x the M2 timeframe)
        ema_2m_break, ema_2m_desc = _check_ema_break(analysis, "EMA_M5_20", direction)

        entry_found = False

        # Priority 1: EMA M5 50 break (highest priority per mentorship)
        if ema_5m_break:
            if _check_rcc_confirmation(analysis, "EMA_M5_50", direction):
                confidence += 12.0
                met.append(f"Paso 6: RCC confirmado en EMA 5M 50 (prioridad maxima) - {ema_5m_desc}")
            else:
                failed.append(f"Paso 6: EMA 5M rota pero sin confirmacion RCC - entrada rechazada (NEVER enter on break alone)")
                return None
            entry_found = True

        # Priority 2: Diagonal breakout on 5min
        if not entry_found and hasattr(analysis, 'chart_patterns'):
            chart_patterns = analysis.chart_patterns or []
            for p in chart_patterns:
                ptype = p.get("type", "") if isinstance(p, dict) else str(p)
                ptf = p.get("timeframe", "") if isinstance(p, dict) else ""
                ptype_lower = ptype.lower()
                if any(k in ptype_lower for k in ("diagonal", "trendline", "wedge_break")):
                    if ptf in ("M5", ""):
                        confidence += 10.0
                        met.append(f"Paso 6: Rompimiento de diagonal en 5M ({ptype})")
                        entry_found = True
                        break

        # Priority 3: EMA M2 50 break (2min timeframe)
        if not entry_found and ema_2m_break:
            if _check_rcc_confirmation(analysis, "EMA_M5_20", direction):
                confidence += 8.0
                met.append(f"Paso 6: RCC confirmado en EMA 2M (M5 proxy) - {ema_2m_desc}")
            else:
                failed.append(f"Paso 6: EMA 2M rota pero sin confirmacion RCC - entrada rechazada (NEVER enter on break alone)")
                return None
            entry_found = True

        # Priority 4: Diagonal breakout on 2min
        if not entry_found and hasattr(analysis, 'chart_patterns'):
            chart_patterns = analysis.chart_patterns or []
            for p in chart_patterns:
                ptype = p.get("type", "") if isinstance(p, dict) else str(p)
                ptf = p.get("timeframe", "") if isinstance(p, dict) else ""
                ptype_lower = ptype.lower()
                if any(k in ptype_lower for k in ("diagonal", "trendline", "wedge_break")):
                    if ptf == "M2":
                        confidence += 6.0
                        met.append(f"Paso 6: Rompimiento de diagonal en 2M ({ptype})")
                        entry_found = True
                        break

        if not entry_found:
            failed.append(f"Paso 6: Sin entrada valida (ni EMA 5M/2M ni diagonal) - {ema_5m_desc}")

        # Additional confirmation: EMA 2M break adds confluence if not already the primary entry
        if entry_found and ema_2m_break and ema_5m_break:
            confidence += 5.0
            met.append(f"Paso 6b: Confirmacion EMA 2M - {ema_2m_desc}")

        # TradingLab: RSI divergence bonus
        has_div, div_bonus = _check_rsi_divergence(analysis, direction)
        if has_div:
            confidence += div_bonus

        # TradingLab SMC: Order Block / FVG / BOS confluence
        smc_ok, smc_bonus, smc_desc = _check_smc_confluence(analysis, direction, entry_price)
        if smc_ok:
            confidence += smc_bonus
            met.append(f"SMC: {smc_desc}")

        # --- Paso 7: SL y TP ---
        sl = self.get_sl_placement(analysis, direction, entry_price)
        tp_levels = self.get_tp_levels(analysis, direction, entry_price)
        tp1 = tp_levels.get("tp1", 0.0)
        tp_max = tp_levels.get("tp_max")

        if sl == 0.0 or tp1 == 0.0:
            failed.append("Paso 7: No se pudo calcular SL o TP")
            return None

        # Validar que TP esté en el lado correcto de la entrada
        if direction == "BUY" and tp1 <= entry_price:
            failed.append(f"Paso 7: TP1 ({tp1:.5f}) debe estar encima de entrada ({entry_price:.5f}) para BUY")
            return None
        if direction == "SELL" and tp1 >= entry_price:
            failed.append(f"Paso 7: TP1 ({tp1:.5f}) debe estar debajo de entrada ({entry_price:.5f}) para SELL")
            return None

        risk = abs(entry_price - sl)
        reward = abs(tp1 - entry_price)
        if risk > 0:
            rr = reward / risk
            if rr < settings.min_rr_ratio - 1e-9:
                failed.append(f"R:R insuficiente: {rr:.2f}:1 (minimo {settings.min_rr_ratio}:1)")
                return None
            met.append(f"R:R valido: {rr:.2f}:1")
        else:
            return None

        if confidence < self.min_confidence:
            return None

        explanation_es = (
            f"Estrategia RED - Cambio de tendencia en 4H\n"
            f"Direccion: {'COMPRA' if direction == 'BUY' else 'VENTA'}\n"
            f"Onda Elliott: Fase 2-3\n"
            f"Entrada: {entry_price:.5f} | SL: {sl:.5f} | TP1: {tp1:.5f}"
            + (f" | TP_max: {tp_max:.5f}" if tp_max else "") + "\n"
            f"R:R: {rr:.2f}:1 | Confianza: {confidence:.0f}%\n"
            f"Detalles:\n" + "\n".join(f"  + {m}" for m in met)
        )
        if failed:
            explanation_es += "\n" + "\n".join(f"  - {f}" for f in failed)

        return SetupSignal(
            strategy=self.color,
            strategy_variant="RED",
            instrument=analysis.instrument,
            direction=direction,
            entry_price=entry_price,
            stop_loss=sl,
            take_profit_1=tp1,
            take_profit_max=tp_max,
            confidence=confidence,
            reasoning=f"RED: 4H trend change confirmed. Pullback to EMA50 1H/4H + Fib. Entry on 5M diagonal break.",
            explanation_es=explanation_es,
            elliott_wave_phase="Onda 2->3 o 4->5",
            timeframes_analyzed=["D", "H4", "H1", "M5"],
            risk_reward_ratio=rr,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_sl_placement(self, analysis: AnalysisResult, direction: str, entry_price: float) -> float:
        """SL debajo de EMA 50 confirm TF o minimo anterior (para BUY). Inverso para SELL."""
        # Style-adaptive: day=H4, swing=W, scalping=M15 (with hardcoded fallback)
        confirm_ema_key = _tf_ema("confirm", 50)
        ema_4h_50 = _ema_val(analysis, confirm_ema_key) or _ema_val(analysis, "EMA_H4_50")
        supports = analysis.key_levels.get("supports", [])
        resistances = analysis.key_levels.get("resistances", [])

        if direction == "BUY":
            candidates = []
            if ema_4h_50:
                # Ligeramente por debajo de EMA 50 4H
                candidates.append(ema_4h_50 * 0.998)
            below = [s for s in supports if s < entry_price]
            if below:
                candidates.append(max(below))
            if not candidates:
                return entry_price * 0.985
            return min(candidates)
        else:
            candidates = []
            if ema_4h_50:
                candidates.append(ema_4h_50 * 1.002)
            above = [r for r in resistances if r > entry_price]
            if above:
                candidates.append(min(above))
            if not candidates:
                return entry_price * 1.015
            return max(candidates)

    def get_tp_levels(self, analysis: AnalysisResult, direction: str, entry_price: float) -> Dict[str, float]:
        """
        TP differentiated by Elliott wave context (TradingLab mentorship):
        - Wave 3 with strong daily setup: can target 1.618 Fibonacci extension
        - Wave 5: stick to recent high/low (conservative)
        - Daily pullback only: exit at recent high/low
        """
        result: Dict[str, float] = {}
        supports = analysis.key_levels.get("supports", [])
        resistances = analysis.key_levels.get("resistances", [])

        # Determine wave context for TP differentiation
        ew = getattr(analysis, 'elliott_wave_detail', {})
        wave_count = str(ew.get("wave_count", "")).strip()

        # RED TP1: Previous high/low (safest per mentorship)
        # TradingLab: TP1 is the SAFEST target = previous swing high (BUY) or swing low (SELL)
        # Fib extensions are used for tp_max, NOT for TP1.
        swing_highs = getattr(analysis, 'swing_highs', [])
        swing_lows = getattr(analysis, 'swing_lows', [])
        if direction == "BUY":
            valid_swing_highs = [sh for sh in swing_highs if sh > entry_price]
            if valid_swing_highs:
                result["tp1"] = min(valid_swing_highs)  # Nearest previous high = safest
            else:
                above = [r for r in resistances if r > entry_price]
                if above:
                    result["tp1"] = min(above)
        else:
            valid_swing_lows = [sl for sl in swing_lows if sl < entry_price]
            if valid_swing_lows:
                result["tp1"] = max(valid_swing_lows)  # Nearest previous low = safest
            else:
                below = [s for s in supports if s < entry_price]
                if below:
                    result["tp1"] = max(below)

        tp1 = result.get("tp1")
        # Directional Fib extensions for tp_max
        fib_1272_dir = (
            analysis.fibonacci_levels.get("ext_bull_1.272") if direction == "BUY"
            else analysis.fibonacci_levels.get("ext_bear_1.272")
        )
        fib_1618_dir = (
            analysis.fibonacci_levels.get("ext_bull_1.618") if direction == "BUY"
            else analysis.fibonacci_levels.get("ext_bear_1.618")
        )
        fib_100 = analysis.fibonacci_levels.get("ext_1.0")

        # Wave 3 with strong daily setup: aggressive TP, target 1.618 extension
        if wave_count == "3":
            # Check if daily setup is strong (HTF overbought/oversold or deceleration)
            daily_strong = (
                analysis.htf_condition in (MarketCondition.OVERBOUGHT, MarketCondition.OVERSOLD)
                or _has_deceleration(analysis)
            )
            if daily_strong and fib_1618_dir and tp1:
                valid = (fib_1618_dir > tp1) if direction == "BUY" else (fib_1618_dir < tp1)
                if valid:
                    result["tp_max"] = fib_1618_dir
            # Fallback to 1.272 for Wave 3 without strong daily
            if "tp_max" not in result and fib_1272_dir and tp1:
                valid = (fib_1272_dir > tp1) if direction == "BUY" else (fib_1272_dir < tp1)
                if valid:
                    result["tp_max"] = fib_1272_dir

        elif wave_count == "5":
            # Wave 5: conservative - stick to recent high/low only, no extensions
            # tp1 already set to nearest S/R, tp_max stays at next S/R (no Fib ext)
            if tp1:
                if direction == "BUY":
                    further = sorted([r for r in resistances if r > tp1])
                    if further:
                        result["tp_max"] = further[0]
                else:
                    further = sorted([s for s in supports if s < tp1], reverse=True)
                    if further:
                        result["tp_max"] = further[0]

        else:
            # Default / daily pullback: Alex prefers recent high/low only
            # "voy al maximo o al minimo reciente. Me olvido."
            # tp1 already set to nearest swing high/low. tp_max = next S/R beyond tp1.
            if tp1:
                if direction == "BUY":
                    further = sorted([r for r in resistances if r > tp1])
                    if further:
                        result["tp_max"] = further[0]
                else:
                    further = sorted([s for s in supports if s < tp1], reverse=True)
                    if further:
                        result["tp_max"] = further[0]

        # Final fallback to ext_1.0 if no tp_max set
        if "tp_max" not in result and fib_100 and tp1:
            if direction == "BUY" and fib_100 > tp1:
                result["tp_max"] = fib_100
            elif direction == "SELL" and fib_100 < tp1:
                result["tp_max"] = fib_100

        return result


# ===========================================================================
# PINK STRATEGY - Continuacion por Patron Correctivo (Onda Elliott 4->5)
# ===========================================================================

class PinkStrategy(BaseStrategy):
    """
    PINK Strategy - Continuacion por Patron Correctivo (Onda Elliott 4->5)

    TradingLab key condition: 1H EMA 50 breaks BUT 4H EMA 50 does NOT break.
    This differentiates PINK from RED (which requires BOTH 1H and 4H to break).

    6 Pasos:
    1. Nivel S/R diario O tendencia clara desarrollada
    2. Alineacion de tendencia en 4H y 1H
    3. EMA 50 1H rota PERO EMA 50 4H NO rota (condicion clave PINK)
    4. Bajar a 1H: EMA 50 1H se rompe PERO en patron correctivo (cuna/triangulo/canal)
    5. Ejecutar al FINAL del patron cuando 5M rompe (diagonal/patron en porcion final)
    6. SL debajo del minimo anterior (proteger el patron). TP en maximo anterior
    """

    def __init__(self):
        super().__init__()
        self.color = StrategyColor.PINK
        self.name = "PINK - Patron Correctivo (Elliott 4->5)"
        self.min_confidence = 50.0

    def check_htf_conditions(self, analysis: AnalysisResult) -> Tuple[bool, float, List[str], List[str]]:
        score = 0.0
        met: List[str] = []
        failed: List[str] = []

        # --- Paso 1: Nivel S/R diario O tendencia desarrollada ---
        has_trend = analysis.htf_trend != Trend.RANGING
        direction = self._determine_direction(analysis)

        if has_trend:
            score += 10.0
            met.append(f"Paso 1: Tendencia HTF clara ({analysis.htf_trend.value})")
        else:
            # Verificar si hay nivel S/R cercano como alternativa
            if direction:
                at_level, _, level_desc = _is_at_key_level(analysis, direction)
                if at_level:
                    score += 10.0
                    met.append(f"Paso 1: {level_desc}")
                else:
                    failed.append("Paso 1: Sin tendencia clara ni nivel S/R cercano")
                    return False, score, met, failed
            else:
                failed.append("Paso 1: Sin tendencia ni direccion determinable")
                return False, score, met, failed

        if direction is None:
            failed.append("Sin direccion determinable")
            return False, score, met, failed

        # --- Paso 2: Alineacion de tendencia en 4H y 1H ---
        # Mentorship: "no operes contra tendencia" — hard-block for PINK
        if analysis.htf_ltf_convergence:
            score += 15.0
            met.append("Paso 2: Tendencia alineada en 4H y 1H (convergencia HTF/LTF)")
        else:
            failed.append("Paso 2: Tendencia NO alineada entre 4H y 1H — PINK bloqueado (no operes contra tendencia)")
            return False, score, met, failed

        # --- Paso 3: PINK key condition ---
        # TradingLab: The corrective pattern (Wave 4) MUST have broken the setup EMA 50
        # against the trend. By the time PINK triggers, the correction is ending and
        # price may have returned near/above the EMA. We check HISTORICAL candles to
        # see if the EMA WAS broken during the correction, not just current position.
        # Style-adaptive: day=H1+H4, swing=D+W, scalping=M5+M15
        opposite = "SELL" if direction == "BUY" else "BUY"
        setup_ema_key = _tf_ema("setup", 50)
        confirm_ema_key = _tf_ema("confirm", 50)

        # Check if setup EMA was historically broken during correction (last 20 candles)
        ema_h1_val = _ema_val(analysis, setup_ema_key) or _ema_val(analysis, "EMA_H1_50")
        h1_candles = getattr(analysis, 'last_candles', {}).get("H1", [])
        ema_1h_was_broken = False
        if ema_h1_val and len(h1_candles) >= 5:
            for candle in h1_candles[-20:]:
                close = candle.get("close", 0)
                if direction == "BUY" and close < ema_h1_val:
                    ema_1h_was_broken = True
                    break
                elif direction == "SELL" and close > ema_h1_val:
                    ema_1h_was_broken = True
                    break
        else:
            # Fallback to current check if no historical data (style-adaptive)
            ema_1h_was_broken, _ = _check_ema_break(analysis, setup_ema_key, opposite)

        # TradingLab: confirm EMA must NOT be broken by the correction (opposite direction).
        # Style-adaptive: day=H4, swing=W, scalping=M15
        ema_4h_break, ema_4h_desc = _check_ema_break(analysis, confirm_ema_key, opposite)

        # 1H EMA 50 must have been broken during correction (historical check)
        if ema_1h_was_broken:
            score += 15.0
            met.append(f"Paso 3a: EMA 50 1H fue rota durante corrección (histórico)")
        else:
            failed.append(f"Paso 3a: EMA 50 1H NO fue rota durante corrección")
            return False, score, met, failed

        # 4H EMA 50 must NOT be broken (if it were, this would be RED, not PINK)
        if not ema_4h_break:
            score += 10.0
            met.append(f"Paso 3b: EMA 50 4H NO rota (condicion PINK) - {ema_4h_desc}")
        else:
            failed.append(
                f"Paso 3b: EMA 50 4H ROTA - {ema_4h_desc} "
                f"(esto es RED, no PINK)"
            )
            return False, score, met, failed

        passed = score >= 25.0
        return passed, score, met, failed

    def check_ltf_entry(self, analysis: AnalysisResult) -> Optional[SetupSignal]:
        direction = self._determine_direction(analysis)
        if direction is None:
            return None

        # TradingLab: Volume confirmation - confluence scoring, not hard block
        vol_ok, vol_ratio = _check_volume_confirmation(analysis, "M5")

        # TradingLab: EMA 8 Weekly trend filter
        if not _check_weekly_ema8_filter(analysis, direction):
            return None  # Don't trade against weekly trend

        entry_price = _get_current_price_proxy(analysis)
        if entry_price is None:
            return None

        confidence = 0.0
        met: List[str] = []
        failed: List[str] = []

        # Volume confluence scoring (not hard block)
        if vol_ok and vol_ratio > 1.2:
            confidence += 5.0
            met.append(f"Volumen alto ({vol_ratio:.1f}x) confirma entrada")
        elif not vol_ok:
            confidence -= 3.0
            failed.append(f"Volumen bajo ({vol_ratio:.1f}x) - sin confirmacion de volumen")

        # --- Paso 4: Verificar que correccion se esta completando ---
        # Pink concept: HTF already confirmed EMA 50 1H break (correction).
        # LTF should check for corrective pattern completion (price returning),
        # NOT re-check EMA direction (which would conflict with HTF check).
        price = _get_current_price_proxy(analysis)
        ema_1h = _ema_val(analysis, "EMA_H1_50")
        if price and ema_1h:
            dist = abs(price - ema_1h) / ema_1h * 100
            if dist < 0.5:
                # Price is returning near EMA 50 1H - correction completing
                confidence += 15.0
                met.append(f"Paso 4: Precio regresando a EMA 50 1H ({dist:.2f}%) - correccion completandose")
            elif dist < 1.0:
                confidence += 8.0
                met.append(f"Paso 4: Precio cerca de EMA 50 1H ({dist:.2f}%) - correccion en progreso")
            else:
                failed.append(f"Paso 4: Precio lejos de EMA 50 1H ({dist:.2f}%) - correccion no completada")
                return None
        else:
            return None

        # Verificar patron correctivo (usamos patrones de velas como proxy)
        # Patrones de consolidacion: DOJI frecuentes indican compresion
        doji_count = analysis.candlestick_patterns.count("DOJI")
        if doji_count > 0:
            confidence += 5.0
            met.append("Paso 4b: Patron de consolidacion detectado (DOJI = compresion)")

        # TradingLab: "cuando yo veo un canal, no ejecuto pink, ejecuto white."
        # Penalize CHANNEL patterns — prefer wedge/triangle for PINK.
        corrective_pattern_type = None
        if hasattr(analysis, 'chart_patterns'):
            chart_patterns = analysis.chart_patterns or []
            for p in chart_patterns:
                ptype = p.get("type", "") if isinstance(p, dict) else str(p)
                ptype_lower = ptype.lower()
                if "channel" in ptype_lower:
                    corrective_pattern_type = "CHANNEL"
                    break
                elif any(k in ptype_lower for k in ("wedge", "cuna", "triangle", "triangulo")):
                    corrective_pattern_type = "WEDGE_TRIANGLE"

        if corrective_pattern_type == "CHANNEL":
            # Mentorship: Alex PREFERS White over Pink for channels ("cuando yo
            # veo un canal, no ejecuto pink, ejecuto white"), but the PINK intro
            # video lists channels as a valid corrective pattern. Soft penalty
            # instead of hard block — White is preferred, not mandatory.
            confidence -= 15.0
            failed.append(
                "Paso 4b: Canal detectado — Alex prefiere White para canales "
                "(penalidad -15, no bloqueo)"
            )

        # --- Paso 4c: PINK entry happens at pattern COMPLETION, not as standard breakout ---
        # TradingLab: check if the wedge/triangle pattern is near completion
        # (price near the apex/convergence point) before allowing entry.
        pattern_near_completion = False
        if hasattr(analysis, 'chart_patterns'):
            chart_patterns = analysis.chart_patterns or []
            for p in chart_patterns:
                if not isinstance(p, dict):
                    continue
                ptype = p.get("type", "").lower()
                if any(k in ptype for k in ("wedge", "cuna", "triangle", "triangulo")):
                    # Check if pattern has completion percentage or apex proximity
                    completion_pct = p.get("completion_pct", None)
                    if completion_pct is not None and completion_pct >= 0.75:
                        pattern_near_completion = True
                        confidence += 8.0
                        met.append(
                            f"Paso 4c: Patron {ptype} cerca de completitud "
                            f"({completion_pct*100:.0f}%) - entrada PINK valida"
                        )
                        break
                    # Alternative: check if price is near the apex/convergence
                    apex_price = p.get("apex_price", None)
                    if apex_price and price:
                        apex_dist = abs(price - apex_price) / price
                        if apex_dist < 0.005:  # Within 0.5% of apex
                            pattern_near_completion = True
                            confidence += 8.0
                            met.append(
                                f"Paso 4c: Precio cerca del apex del patron {ptype} "
                                f"({apex_dist*100:.2f}%) - entrada PINK valida"
                            )
                            break

        if not pattern_near_completion:
            # If no chart_patterns data available, use price compression as proxy:
            # low distance to EMA and DOJIs indicate the pattern is narrowing
            if doji_count >= 2 and dist < 0.3:
                pattern_near_completion = True
                confidence += 5.0
                met.append(
                    "Paso 4c: Compresion de precio (DOJIs + cercano a EMA) "
                    "sugiere patron cerca de completitud"
                )
            else:
                failed.append(
                    "Paso 4c: Patron correctivo no parece estar cerca de completitud "
                    "(PINK entra al COMPLETAR el patron, no al inicio)"
                )

        # --- Paso 5: Ejecutar al final del patron en 5M (RCC) ---
        # TradingLab: "NEVER enter on break alone" — RCC failure = REJECT entry
        # 4-tier execution cascade (like Blue/Red/Black):
        # NOTE: Per mentorship, the 5M EMA will NOT be respected throughout the
        # Pink pattern due to volatility. Diagonal check is MORE likely to be
        # the valid entry for PINK, so diagonal gets equal/higher confidence.
        ema_5m_break, ema_5m_desc = _check_ema_break(analysis, "EMA_M5_50", direction)
        # M2 not available from broker API; use M5 EMA 20 as approximation
        ema_2m_break, ema_2m_desc = _check_ema_break(analysis, "EMA_M5_20", direction)

        entry_found = False

        # Priority 1: EMA M5 50 break + RCC (+12)
        # (Lower than Blue's +12 since 5M EMA is less reliable for PINK)
        if ema_5m_break:
            if _check_rcc_confirmation(analysis, "EMA_M5_50", direction):
                confidence += 12.0
                met.append(f"Paso 5: RCC confirmado en EMA 5M 50 - {ema_5m_desc}")
            else:
                failed.append(f"Paso 5: EMA 5M rota pero sin confirmacion RCC - entrada rechazada (NEVER enter on break alone)")
                return None
            entry_found = True

        # Priority 2: Diagonal breakout on 5min (+12)
        # PINK-specific: diagonal gets EQUAL confidence to EMA because 5M EMA
        # is often not respected during the corrective pattern volatility.
        if not entry_found and hasattr(analysis, 'chart_patterns'):
            chart_patterns = analysis.chart_patterns or []
            for p in chart_patterns:
                ptype = p.get("type", "") if isinstance(p, dict) else str(p)
                ptf = p.get("timeframe", "") if isinstance(p, dict) else ""
                ptype_lower = ptype.lower()
                if any(k in ptype_lower for k in ("diagonal", "trendline", "wedge_break")):
                    if ptf in ("M5", ""):
                        confidence += 12.0
                        met.append(f"Paso 5: Rompimiento de diagonal en 5M ({ptype}) - entrada PINK preferida")
                        entry_found = True
                        break

        # Priority 3: EMA M2 50 break + RCC (+8)
        if not entry_found and ema_2m_break:
            if _check_rcc_confirmation(analysis, "EMA_M5_20", direction):
                confidence += 8.0
                met.append(f"Paso 5: RCC confirmado en EMA 2M (M5 proxy) - {ema_2m_desc}")
            else:
                failed.append(f"Paso 5: EMA 2M rota pero sin confirmacion RCC - entrada rechazada")
                return None
            entry_found = True

        # Priority 4: Diagonal breakout on 2min (+8)
        # Higher than Blue's +6 for PINK since diagonals are more reliable here
        if not entry_found and hasattr(analysis, 'chart_patterns'):
            chart_patterns = analysis.chart_patterns or []
            for p in chart_patterns:
                ptype = p.get("type", "") if isinstance(p, dict) else str(p)
                ptf = p.get("timeframe", "") if isinstance(p, dict) else ""
                ptype_lower = ptype.lower()
                if any(k in ptype_lower for k in ("diagonal", "trendline", "wedge_break")):
                    if ptf == "M2":
                        confidence += 8.0
                        met.append(f"Paso 5: Rompimiento de diagonal en 2M ({ptype})")
                        entry_found = True
                        break

        if not entry_found:
            failed.append(f"Paso 5: Sin entrada valida (ni EMA 5M/2M ni diagonal) - {ema_5m_desc}")

        # Additional confluence: both EMA levels confirm
        if entry_found and ema_2m_break and ema_5m_break:
            confidence += 5.0
            met.append(f"Paso 5b: Confluencia EMA 2M + 5M - {ema_2m_desc}")

        has_reversal, rev_desc = _has_reversal_pattern(analysis, direction)
        if has_reversal:
            confidence += 10.0
            met.append(f"Paso 5b: Patron de giro detectado - {rev_desc}")

        # TradingLab: RSI divergence bonus
        has_div, div_bonus = _check_rsi_divergence(analysis, direction)
        if has_div:
            confidence += div_bonus

        # TradingLab SMC: Order Block / FVG / BOS confluence
        smc_ok, smc_bonus, smc_desc = _check_smc_confluence(analysis, direction, entry_price)
        if smc_ok:
            confidence += smc_bonus
            met.append(f"SMC: {smc_desc}")

        # --- Paso 6: SL y TP ---
        sl = self.get_sl_placement(analysis, direction, entry_price)
        tp_levels = self.get_tp_levels(analysis, direction, entry_price)
        tp1 = tp_levels.get("tp1", 0.0)

        if sl == 0.0 or tp1 == 0.0:
            failed.append("Paso 6: No se pudo calcular SL o TP")
            return None

        # Validar que TP esté en el lado correcto de la entrada
        if direction == "BUY" and tp1 <= entry_price:
            failed.append(f"Paso 7: TP1 ({tp1:.5f}) debe estar encima de entrada ({entry_price:.5f}) para BUY")
            return None
        if direction == "SELL" and tp1 >= entry_price:
            failed.append(f"Paso 7: TP1 ({tp1:.5f}) debe estar debajo de entrada ({entry_price:.5f}) para SELL")
            return None

        risk = abs(entry_price - sl)
        reward = abs(tp1 - entry_price)
        if risk > 0:
            rr = reward / risk
            if rr < settings.min_rr_ratio - 1e-9:
                failed.append(f"R:R insuficiente: {rr:.2f}:1 (minimo {settings.min_rr_ratio}:1)")
                return None
            met.append(f"R:R valido: {rr:.2f}:1")
        else:
            return None

        if confidence < self.min_confidence:
            return None

        explanation_es = (
            f"Estrategia PINK - Continuacion por patron correctivo\n"
            f"Direccion: {'COMPRA' if direction == 'BUY' else 'VENTA'}\n"
            f"Onda Elliott: Fase 4->5 (fin de correccion)\n"
            f"Entrada: {entry_price:.5f} | SL: {sl:.5f} | TP: {tp1:.5f}\n"
            f"R:R: {rr:.2f}:1 | Confianza: {confidence:.0f}%\n"
            f"Detalles:\n" + "\n".join(f"  + {m}" for m in met)
        )
        if failed:
            explanation_es += "\n" + "\n".join(f"  - {f}" for f in failed)

        return SetupSignal(
            strategy=self.color,
            strategy_variant="PINK",
            instrument=analysis.instrument,
            direction=direction,
            entry_price=entry_price,
            stop_loss=sl,
            take_profit_1=tp1,
            take_profit_max=tp_levels.get("tp_max"),
            confidence=confidence,
            reasoning=f"PINK: Corrective pattern in 1H within 4H trend. Entry at pattern completion on 5M break.",
            explanation_es=explanation_es,
            elliott_wave_phase="Onda 4->5",
            timeframes_analyzed=["D", "H4", "H1", "M5"],
            risk_reward_ratio=rr,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_sl_placement(self, analysis: AnalysisResult, direction: str, entry_price: float) -> float:
        """SL debajo del minimo anterior (proteger el patron). Previous swing extreme only, NO Fibonacci."""
        supports = analysis.key_levels.get("supports", [])
        resistances = analysis.key_levels.get("resistances", [])

        if direction == "BUY":
            below = [s for s in supports if s < entry_price]
            if below:
                return max(below)  # Nearest support below entry (tightest SL)
            return entry_price * 0.99
        else:
            above = [r for r in resistances if r > entry_price]
            if above:
                return min(above)  # Nearest resistance above entry (tightest SL)
            return entry_price * 1.01

    def get_tp_levels(self, analysis: AnalysisResult, direction: str, entry_price: float) -> Dict[str, float]:
        """
        PINK TP1: Previous high/low (safest per mentorship).
        TradingLab: PINK targets previous swing high (BUY) or swing low (SELL) as TP1.
        Trend may be ending (Wave 5), so conservative TP is correct.
        """
        supports = analysis.key_levels.get("supports", [])
        resistances = analysis.key_levels.get("resistances", [])
        swing_highs = getattr(analysis, 'swing_highs', [])
        swing_lows = getattr(analysis, 'swing_lows', [])
        result: Dict[str, float] = {}

        if direction == "BUY":
            # Primary: previous swing high (safest TP per mentorship)
            valid_swing_highs = [sh for sh in swing_highs if sh > entry_price]
            if valid_swing_highs:
                result["tp1"] = min(valid_swing_highs)  # Nearest previous high = safest
            else:
                above = sorted([r for r in resistances if r > entry_price])
                if above:
                    result["tp1"] = above[0]

            # tp_max: next swing high beyond tp1
            tp1 = result.get("tp1")
            if tp1:
                further_highs = [sh for sh in swing_highs if sh > tp1]
                if further_highs:
                    result["tp_max"] = min(further_highs)
                else:
                    further_res = [r for r in resistances if r > tp1]
                    if further_res:
                        result["tp_max"] = sorted(further_res)[0]
        else:
            # Primary: previous swing low (safest TP per mentorship)
            valid_swing_lows = [sl for sl in swing_lows if sl < entry_price]
            if valid_swing_lows:
                result["tp1"] = max(valid_swing_lows)  # Nearest previous low = safest
            else:
                below = sorted([s for s in supports if s < entry_price], reverse=True)
                if below:
                    result["tp1"] = below[0]

            # tp_max: next swing low beyond tp1
            tp1 = result.get("tp1")
            if tp1:
                further_lows = [sl for sl in swing_lows if sl < tp1]
                if further_lows:
                    result["tp_max"] = max(further_lows)
                else:
                    further_sup = [s for s in supports if s < tp1]
                    if further_sup:
                        result["tp_max"] = sorted(further_sup, reverse=True)[0]

        return result


# ===========================================================================
# WHITE STRATEGY - Continuacion Post-Pink (Blue-like after completed Pink)
# ===========================================================================

class WhiteStrategy(BaseStrategy):
    """
    WHITE Strategy - Continuacion Post-Pink (Blue-like impulse-pullback-continuation)

    TradingLab: WHITE is a Blue-like impulse-pullback-continuation following
    a completed Pink. Tighter entries and higher win rate than Pink.

    6 Pasos:
    1. Debe venir de un setup PINK completado
    2. Despues de Pink: impulso + pullback se forma en 1H
    3. Pullback a EMA 50 1H + Fibonacci
    4. Desaceleracion/giro (mismos criterios que Blue)
    5. Bajar a 5M: ejecutar en rompimiento+cierre+confirmacion
    6. SL encima del maximo anterior. TP en nivel objetivo de Pink (extremo del swing previo)

    Nota: En la deteccion automatica, White depende de que Pink ya se haya
    completado. Dado que no tenemos estado persistente de trades previos en
    este modulo, evaluamos las condiciones tecnicas equivalentes:
    - Tendencia establecida con impulso reciente
    - Pullback a EMA 50 1H despues de un movimiento fuerte
    - Estructura similar a Blue pero en contexto de onda 5
    """

    def __init__(self):
        super().__init__()
        self.color = StrategyColor.WHITE
        self.name = "WHITE - Post-Pink Continuacion (Onda 3 de 5)"
        self.min_confidence = 55.0

    def check_htf_conditions(self, analysis: AnalysisResult) -> Tuple[bool, float, List[str], List[str]]:
        score = 0.0
        met: List[str] = []
        failed: List[str] = []

        direction = self._determine_direction(analysis)
        if direction is None:
            failed.append("Paso 1: Sin tendencia HTF clara (White requiere tendencia establecida)")
            return False, score, met, failed

        # --- Paso 1: Debe venir de contexto Pink (tendencia establecida + impulso previo) ---
        # Verificamos que haya tendencia clara y convergencia (indica que Pink ya opero o pudo operar)
        if analysis.htf_trend != Trend.RANGING:
            score += 10.0
            met.append(f"Paso 1: Tendencia HTF establecida ({analysis.htf_trend.value})")
        else:
            failed.append("Paso 1: Sin tendencia HTF - White requiere contexto post-Pink")
            return False, score, met, failed

        # Mentorship: "no operes contra tendencia" — hard-block for WHITE
        if analysis.htf_ltf_convergence:
            score += 10.0
            met.append("Paso 1b: Convergencia HTF/LTF (indica tendencia consolidada)")
        else:
            failed.append("Paso 1b: Sin convergencia HTF/LTF — WHITE bloqueado (no operes contra tendencia)")
            return False, score, met, failed

        # --- Paso 2: Impulso + pullback en setup TF ---
        # Verificar que EMA 50 setup-TF esta en el lado correcto (tendencia ya rota previamente)
        setup_ema_key = _tf_ema("setup", 50)
        confirm_ema_key = _tf_ema("confirm", 50)
        ema_1h_ok, ema_1h_desc = _check_ema_break(analysis, setup_ema_key, direction)
        if ema_1h_ok:
            score += 10.0
            met.append(f"Paso 2: Tendencia setup-TF intacta - {ema_1h_desc}")
        else:
            failed.append(f"Paso 2: Tendencia setup-TF perdida - {ema_1h_desc}")
            return False, score, met, failed

        # EMA 50 confirm-TF tambien debe estar rota a favor
        ema_4h_ok, ema_4h_desc = _check_ema_break(analysis, confirm_ema_key, direction)
        if ema_4h_ok:
            score += 10.0
            met.append(f"Paso 2b: EMA 50 4H a favor - {ema_4h_desc}")

        passed = score >= 20.0
        return passed, score, met, failed

    def check_ltf_entry(self, analysis: AnalysisResult) -> Optional[SetupSignal]:
        direction = self._determine_direction(analysis)
        if direction is None:
            return None

        # TradingLab: White MUST come from PINK. Since we can't track previous
        # trades, we use structural proxies to verify the PINK phase occurred:
        # (a) A recent structure break (BOS) in the trend direction, AND
        # (b) The correction before it was a pattern (wedge/triangle), AND
        # (c) Price is now above/below EMA 50 1H.
        failed: List[str] = []
        pink_proxy_score = 0

        # (a) Check for recent BOS in trend direction
        structure_breaks = getattr(analysis, 'structure_breaks', [])
        expected_sb_dir = "bullish" if direction == "BUY" else "bearish"
        has_recent_bos = False
        for sb in structure_breaks[-5:]:
            if isinstance(sb, dict) and sb.get("type") == "BOS" and sb.get("direction") == expected_sb_dir:
                has_recent_bos = True
                pink_proxy_score += 1
                break

        # (b) Check if a corrective pattern (wedge/triangle) was present
        has_corrective_pattern = False
        if hasattr(analysis, 'chart_patterns'):
            chart_patterns = analysis.chart_patterns or []
            for p in chart_patterns:
                ptype = p.get("type", "") if isinstance(p, dict) else str(p)
                ptype_lower = ptype.lower()
                if any(k in ptype_lower for k in ("wedge", "cuna", "triangle", "triangulo")):
                    has_corrective_pattern = True
                    pink_proxy_score += 1
                    break

        # (c) Check if price is on correct side of EMA 50 setup-TF
        setup_ema_key = _tf_ema("setup", 50)
        ema_1h_check, _ = _check_ema_break(analysis, setup_ema_key, direction)
        if ema_1h_check:
            pink_proxy_score += 1

        # Accept Elliott wave data ONLY if it's Wave 4 or 5 context (PINK territory)
        ew_detail = getattr(analysis, 'elliott_wave_detail', {})
        wave_count = str(ew_detail.get("wave_count", "")).strip() if ew_detail else ""
        if wave_count in ("4", "5"):
            pink_proxy_score += 1

        # Need at least 2 of the 4 proxy conditions to confirm PINK phase
        if pink_proxy_score < 2:
            failed.append(
                f"White requiere contexto post-Pink: solo {pink_proxy_score}/4 "
                f"condiciones proxy cumplidas (BOS={has_recent_bos}, "
                f"patron_correctivo={has_corrective_pattern}, "
                f"EMA_1H_ok={ema_1h_check}, elliott={bool(ew_detail)})"
            )
            return None

        # TradingLab: Volume confirmation - confluence scoring, not hard block
        vol_ok, vol_ratio = _check_volume_confirmation(analysis, "M5")

        # TradingLab: EMA 8 Weekly trend filter
        if not _check_weekly_ema8_filter(analysis, direction):
            return None  # Don't trade against weekly trend

        entry_price = _get_current_price_proxy(analysis)
        if entry_price is None:
            return None

        confidence = 0.0
        met: List[str] = []
        failed = []  # Reset after initial check

        # Volume confluence scoring (not hard block)
        if vol_ok and vol_ratio > 1.2:
            confidence += 5.0
            met.append(f"Volumen alto ({vol_ratio:.1f}x) confirma entrada")
        elif not vol_ok:
            confidence -= 3.0
            failed.append(f"Volumen bajo ({vol_ratio:.1f}x) - sin confirmacion de volumen")

        # --- Paso 3: Pullback a EMA 50 1H + Fibonacci ---
        pb_ok, pb_desc = _check_ema_pullback(analysis, "EMA_H1_50", direction)
        if pb_ok:
            confidence += 15.0
            met.append(f"Paso 3: {pb_desc}")
        else:
            failed.append(f"Paso 3: {pb_desc}")
            return None  # Pullback es requisito esencial

        fib_ok, fib_desc = _fib_zone_check(analysis, entry_price, direction)
        if fib_ok:
            confidence += 10.0
            met.append(f"Paso 3b: {fib_desc}")
        else:
            failed.append(f"Paso 3b: {fib_desc}")

        # --- Paso 4: Desaceleracion/giro (mismos criterios que Blue) ---
        has_reversal, rev_desc = _has_reversal_pattern(analysis, direction)
        if has_reversal:
            confidence += 15.0
            met.append(f"Paso 4: {rev_desc}")
        elif _has_deceleration(analysis):
            confidence += 8.0
            met.append("Paso 4: Desaceleracion detectada (sin giro completo)")
        else:
            failed.append(f"Paso 4: {rev_desc}")

        # --- Paso 5: Entrada en 5M (RCC) ---
        # TradingLab: "NEVER enter on break alone" — RCC failure = REJECT entry
        # 4-tier execution cascade (same as Blue — WHITE is a Blue after Pink)
        ema_5m_break, ema_5m_desc = _check_ema_break(analysis, "EMA_M5_50", direction)
        # M2 not available from broker API; use M5 EMA 20 as approximation
        # (EMA 50 on M2 ≈ EMA 20 on M5 since M5 is 2.5x the M2 timeframe)
        ema_2m_break, ema_2m_desc = _check_ema_break(analysis, "EMA_M5_20", direction)

        entry_found = False

        # Priority 1: EMA M5 50 break + RCC (+12, same as Blue)
        if ema_5m_break:
            if _check_rcc_confirmation(analysis, "EMA_M5_50", direction):
                confidence += 12.0
                met.append(f"Paso 5: RCC confirmado en EMA 5M 50 (prioridad maxima) - {ema_5m_desc}")
            else:
                failed.append(f"Paso 5: EMA 5M rota pero sin confirmacion RCC - entrada rechazada (NEVER enter on break alone)")
                return None
            entry_found = True

        # Priority 2: Diagonal breakout on 5min (+10, same as Blue)
        if not entry_found and hasattr(analysis, 'chart_patterns'):
            chart_patterns = analysis.chart_patterns or []
            for p in chart_patterns:
                ptype = p.get("type", "") if isinstance(p, dict) else str(p)
                ptf = p.get("timeframe", "") if isinstance(p, dict) else ""
                ptype_lower = ptype.lower()
                if any(k in ptype_lower for k in ("diagonal", "trendline", "wedge_break")):
                    if ptf in ("M5", ""):
                        confidence += 10.0
                        met.append(f"Paso 5: Rompimiento de diagonal en 5M ({ptype})")
                        entry_found = True
                        break

        # Priority 3: EMA M2 50 break + RCC (+8, same as Blue)
        if not entry_found and ema_2m_break:
            if _check_rcc_confirmation(analysis, "EMA_M5_20", direction):
                confidence += 8.0
                met.append(f"Paso 5: RCC confirmado en EMA 2M (M5 proxy) - {ema_2m_desc}")
            else:
                failed.append(f"Paso 5: EMA 2M rota pero sin confirmacion RCC - entrada rechazada")
                return None
            entry_found = True

        # Priority 4: Diagonal breakout on 2min (+6, same as Blue)
        if not entry_found and hasattr(analysis, 'chart_patterns'):
            chart_patterns = analysis.chart_patterns or []
            for p in chart_patterns:
                ptype = p.get("type", "") if isinstance(p, dict) else str(p)
                ptf = p.get("timeframe", "") if isinstance(p, dict) else ""
                ptype_lower = ptype.lower()
                if any(k in ptype_lower for k in ("diagonal", "trendline", "wedge_break")):
                    if ptf == "M2":
                        confidence += 6.0
                        met.append(f"Paso 5: Rompimiento de diagonal en 2M ({ptype})")
                        entry_found = True
                        break

        if not entry_found:
            failed.append(f"Paso 5: Sin entrada valida (ni EMA 5M/2M ni diagonal) - {ema_5m_desc}")

        # Additional confluence: both EMA levels confirm
        if entry_found and ema_2m_break and ema_5m_break:
            confidence += 5.0
            met.append(f"Paso 5b: Confluencia EMA 2M + 5M - {ema_2m_desc}")

        # TradingLab: RSI divergence bonus
        has_div, div_bonus = _check_rsi_divergence(analysis, direction)
        if has_div:
            confidence += div_bonus

        # TradingLab SMC: Order Block / FVG / BOS confluence
        smc_ok, smc_bonus, smc_desc = _check_smc_confluence(analysis, direction, entry_price)
        if smc_ok:
            confidence += smc_bonus
            met.append(f"SMC: {smc_desc}")

        # --- Paso 6: SL y TP ---
        sl = self.get_sl_placement(analysis, direction, entry_price)
        tp_levels = self.get_tp_levels(analysis, direction, entry_price)
        tp1 = tp_levels.get("tp1", 0.0)

        if sl == 0.0 or tp1 == 0.0:
            failed.append("Paso 6: No se pudo calcular SL o TP")
            return None

        # Validar que TP esté en el lado correcto de la entrada
        if direction == "BUY" and tp1 <= entry_price:
            failed.append(f"Paso 7: TP1 ({tp1:.5f}) debe estar encima de entrada ({entry_price:.5f}) para BUY")
            return None
        if direction == "SELL" and tp1 >= entry_price:
            failed.append(f"Paso 7: TP1 ({tp1:.5f}) debe estar debajo de entrada ({entry_price:.5f}) para SELL")
            return None

        risk = abs(entry_price - sl)
        reward = abs(tp1 - entry_price)
        if risk > 0:
            rr = reward / risk
            if rr < settings.min_rr_ratio - 1e-9:
                failed.append(f"R:R insuficiente: {rr:.2f}:1 (minimo {settings.min_rr_ratio}:1)")
                return None
            met.append(f"R:R valido: {rr:.2f}:1")
        else:
            return None

        if confidence < self.min_confidence:
            return None

        explanation_es = (
            f"Estrategia WHITE - Continuacion post-Pink\n"
            f"Direccion: {'COMPRA' if direction == 'BUY' else 'VENTA'}\n"
            f"Onda Elliott: Onda 3 de Onda 5\n"
            f"Entrada: {entry_price:.5f} | SL: {sl:.5f} | TP: {tp1:.5f}\n"
            f"R:R: {rr:.2f}:1 | Confianza: {confidence:.0f}%\n"
            f"Detalles:\n" + "\n".join(f"  + {m}" for m in met)
        )
        if failed:
            explanation_es += "\n" + "\n".join(f"  - {f}" for f in failed)

        return SetupSignal(
            strategy=self.color,
            strategy_variant="WHITE",
            instrument=analysis.instrument,
            direction=direction,
            entry_price=entry_price,
            stop_loss=sl,
            take_profit_1=tp1,
            take_profit_max=tp_levels.get("tp_max"),
            confidence=confidence,
            reasoning=f"WHITE: Post-Pink continuation. Pullback to EMA50 1H after impulse. Entry on 5M confirmation.",
            explanation_es=explanation_es,
            elliott_wave_phase="Onda 3 de Onda 5",
            timeframes_analyzed=["D", "H4", "H1", "M5", "M2"],
            risk_reward_ratio=rr,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_sl_placement(self, analysis: AnalysisResult, direction: str, entry_price: float) -> float:
        """SL encima del maximo anterior (SELL) o debajo del minimo anterior (BUY). Previous swing extreme only, NO Fibonacci."""
        supports = analysis.key_levels.get("supports", [])
        resistances = analysis.key_levels.get("resistances", [])

        if direction == "BUY":
            below = [s for s in supports if s < entry_price]
            if below:
                return max(below)  # Nearest support below entry (tightest SL)
            return entry_price * 0.99
        else:
            above = [r for r in resistances if r > entry_price]
            if above:
                return min(above)  # Nearest resistance above entry (tightest SL)
            return entry_price * 1.01

    def get_tp_levels(self, analysis: AnalysisResult, direction: str, entry_price: float) -> Dict[str, float]:
        """
        TP como si fuera el de una PINK (previous swing extreme).
        TradingLab mentorship: "take profit como si fuera el de una PINK."
        Uses previous swing high (BUY) or swing low (SELL) - same logic as PinkStrategy.
        """
        supports = analysis.key_levels.get("supports", [])
        resistances = analysis.key_levels.get("resistances", [])
        swing_highs = getattr(analysis, 'swing_highs', [])
        swing_lows = getattr(analysis, 'swing_lows', [])
        result: Dict[str, float] = {}

        if direction == "BUY":
            # Previous swing high above entry price (same as PINK)
            valid_swing_highs = [sh for sh in swing_highs if sh > entry_price]
            if valid_swing_highs:
                result["tp1"] = min(valid_swing_highs)
            else:
                above = sorted([r for r in resistances if r > entry_price])
                if len(above) >= 2:
                    result["tp1"] = above[1]
                elif above:
                    result["tp1"] = above[0]

            # tp_max: next swing high beyond tp1
            tp1 = result.get("tp1")
            if tp1:
                further_highs = [sh for sh in swing_highs if sh > tp1]
                if further_highs:
                    result["tp_max"] = min(further_highs)
                else:
                    further_res = [r for r in resistances if r > tp1]
                    if further_res:
                        result["tp_max"] = sorted(further_res)[0]
        else:
            # Previous swing low below entry price (same as PINK)
            valid_swing_lows = [sl for sl in swing_lows if sl < entry_price]
            if valid_swing_lows:
                result["tp1"] = max(valid_swing_lows)
            else:
                below = sorted([s for s in supports if s < entry_price], reverse=True)
                if len(below) >= 2:
                    result["tp1"] = below[1]
                elif below:
                    result["tp1"] = below[0]

            # tp_max: next swing low beyond tp1
            tp1 = result.get("tp1")
            if tp1:
                further_lows = [sl for sl in swing_lows if sl < tp1]
                if further_lows:
                    result["tp_max"] = max(further_lows)
                else:
                    further_sup = [s for s in supports if s < tp1]
                    if further_sup:
                        result["tp_max"] = sorted(further_sup, reverse=True)[0]

        # Fallback: EMA H4 50 as tp_max if no swing/S/R levels found
        if "tp_max" not in result:
            tp1 = result.get("tp1")
            if tp1:
                ema_h4_50 = _ema_val(analysis, "EMA_H4_50")
                if ema_h4_50:
                    if direction == "BUY" and ema_h4_50 > tp1:
                        result["tp_max"] = ema_h4_50
                    elif direction == "SELL" and ema_h4_50 < tp1:
                        result["tp_max"] = ema_h4_50

        return result


# ===========================================================================
# BLACK STRATEGY - Contratendencia / Anticipacion (Onda Elliott 1)
# ===========================================================================

class BlackStrategy(BaseStrategy):
    """
    BLACK Strategy - Contratendencia ONLY / Anticipacion (Onda Elliott 1)
    La mas riesgosa pero con mejor R:R promedio (~2.80:1)

    TradingLab REQUIREMENTS:
    - Counter-trend ONLY (trades against the current trend)
    - Min R:R must be 2.0:1 (mentorship avg ~2.80:1)
    - REQUIRES daily S/R level (non-negotiable)
    - RSI divergence on H4 = strong bonus ("añadido", NOT obligatorio per Alex)
    - RSI H4 overbought/oversold = extra confirmation, NOT hard requirement
    - Channels: possible but rare ("muy pocas veces"), penalty not hard block

    7 Pasos:
    1. Nivel S/R diario (OBLIGATORIO, no negociable)
    2. Precio diario ataca el nivel con condicion de sobrecompra/sobreventa
    3. Desaceleracion/senales de reversal en diario (preferencial)
    4. 4H sobrecompra INNEGOCIABLE: precio lejos de EMA 50 4H + consolidacion
       + RSI sobrecompra y divergencias como EXTRAS ("añadido")
    5. 1H: patron de reversal (triangulo/cuna, raro canal).
       EMA 50 1H NO debe actuar como S/R dinamico.
    6. Esperar que el patron se complete, buscar patron de velas de reversal,
       luego ejecutar en rompimiento 5M
    7. SL encima del maximo anterior. TP en EMA 50 4H. R:R MINIMO de 2:1
    """

    def __init__(self):
        super().__init__()
        self.color = StrategyColor.BLACK
        self.name = "BLACK - Contratendencia (Elliott Onda 1)"
        self.min_confidence = 60.0  # Mayor umbral por ser contratendencia

    def check_htf_conditions(self, analysis: AnalysisResult) -> Tuple[bool, float, List[str], List[str]]:
        score = 0.0
        met: List[str] = []
        failed: List[str] = []

        # Para Black, vamos CONTRA la tendencia: si HTF es bullish, buscamos SELL (anticipamos giro)
        if analysis.htf_trend == Trend.BULLISH:
            direction = "SELL"  # Contra-tendencia
        elif analysis.htf_trend == Trend.BEARISH:
            direction = "BUY"  # Contra-tendencia
        else:
            # En ranging, verificar condicion extrema
            if analysis.htf_condition == MarketCondition.OVERBOUGHT:
                direction = "SELL"
            elif analysis.htf_condition == MarketCondition.OVERSOLD:
                direction = "BUY"
            else:
                failed.append("Paso 1: Sin tendencia ni condicion extrema para contra-tendencia")
                return False, score, met, failed

        # --- Paso 1: Nivel S/R diario (OBLIGATORIO) ---
        counter_dir = direction  # Para Black, buscamos nivel opuesto a la tendencia
        at_level, level_val, level_desc = _is_at_key_level(analysis, counter_dir)
        if at_level:
            score += 20.0
            met.append(f"Paso 1 [OBLIGATORIO]: {level_desc}")
        else:
            failed.append(f"Paso 1 [OBLIGATORIO FALLIDO]: {level_desc}")
            # Este es NO NEGOCIABLE - sin nivel S/R, Black no procede
            return False, score, met, failed

        # --- Paso 2: Condicion de sobrecompra/sobreventa ---
        if direction == "SELL" and analysis.htf_condition == MarketCondition.OVERBOUGHT:
            score += 15.0
            met.append("Paso 2: Condicion de SOBRECOMPRA en diario - favorable para venta")
        elif direction == "BUY" and analysis.htf_condition == MarketCondition.OVERSOLD:
            score += 15.0
            met.append("Paso 2: Condicion de SOBREVENTA en diario - favorable para compra")
        else:
            failed.append(f"Paso 2: Condicion diaria es {analysis.htf_condition.value}, no es extrema para {direction}")
            # Importante pero no descalificante absoluto

        # --- Paso 3: Desaceleracion/reversal en diario ---
        if _has_deceleration(analysis):
            score += 10.0
            met.append("Paso 3: Desaceleracion/reversal detectado en diario")
        else:
            failed.append("Paso 3: Sin senales de desaceleracion en diario")

        # --- Paso 4: Confirm-TF sobrecomprado + precio lejos de EMA 50 confirm-TF ---
        confirm_ema_key = _tf_ema("confirm", 50)
        ema_4h_50 = _ema_val(analysis, confirm_ema_key)
        price = _get_current_price_proxy(analysis)

        if ema_4h_50 and price:
            distance_pct = abs(price - ema_4h_50) / ema_4h_50 * 100
            # TradingLab: "strong separation" from EMA 4H requires at least 1.5%
            # (previously 0.5% was too permissive for what the mentorship describes)
            if distance_pct > 1.5:
                score += 10.0
                met.append(f"Paso 4: Precio lejos de EMA 50 4H ({distance_pct:.2f}%) - separacion fuerte")
            elif distance_pct > 0.8:
                score += 5.0
                met.append(f"Paso 4: Precio moderadamente lejos de EMA 50 4H ({distance_pct:.2f}%) - separacion parcial")
            else:
                failed.append(f"Paso 4: Precio cerca de EMA 50 4H ({distance_pct:.2f}%) - no sobreextendido (necesita >1.5%)")
        else:
            failed.append("Paso 4: No se puede evaluar distancia a EMA 50 4H")

        passed = score >= 20.0  # Minimo: Paso 1 cumplido
        return passed, score, met, failed

    def check_ltf_entry(self, analysis: AnalysisResult) -> Optional[SetupSignal]:
        # Determinar direccion contra-tendencia
        if analysis.htf_trend == Trend.BULLISH:
            direction = "SELL"
        elif analysis.htf_trend == Trend.BEARISH:
            direction = "BUY"
        elif analysis.htf_condition == MarketCondition.OVERBOUGHT:
            direction = "SELL"
        elif analysis.htf_condition == MarketCondition.OVERSOLD:
            direction = "BUY"
        else:
            return None

        # --- H4 RSI overbought/oversold — EXTRA confirmation, not hard block ---
        # TradingLab Intro: "Dentro de este paso podemos AÑADIR dos cosas,
        # primero la sobrecompra en el RSI y segundo las divergencias en el RSI
        # en 4 horas." — Alex treats RSI as "un extra" within Step 4.
        # Day short example: "no es obligatorio que estén presentes"
        # The actual "sobrecompra innegociable" is determined by price structure
        # (separation from EMA 4H + candle type), checked in check_htf_conditions().
        rsi_h4 = analysis.rsi_values.get("H4", 50)

        # TradingLab: Volume confirmation - confluence scoring, not hard block
        vol_ok, vol_ratio = _check_volume_confirmation(analysis, "M5")

        # BLACK es contratendencia: NO aplicar EMA 8 Weekly trend filter
        # (filtrar por tendencia semanal bloquearía las señales contra-tendencia)

        entry_price = _get_current_price_proxy(analysis)
        if entry_price is None:
            return None

        confidence = 0.0
        met: List[str] = []
        failed: List[str] = []

        # H4 RSI overbought/oversold — strong bonus, not hard block
        if direction == "SELL" and rsi_h4 > 70:
            confidence += 15.0
            met.append(f"H4 RSI sobrecomprado: {rsi_h4:.1f} > 70 (extra confirmacion para SELL)")
        elif direction == "BUY" and rsi_h4 < 30:
            confidence += 15.0
            met.append(f"H4 RSI sobrevendido: {rsi_h4:.1f} < 30 (extra confirmacion para BUY)")
        else:
            failed.append(f"H4 RSI {rsi_h4:.1f} no en zona extrema (extra, no obligatorio)")

        # Volume confluence scoring (not hard block)
        if vol_ok and vol_ratio > 1.2:
            confidence += 5.0
            met.append(f"Volumen alto ({vol_ratio:.1f}x) confirma entrada")
        elif not vol_ok:
            failed.append(f"Volumen bajo ({vol_ratio:.1f}x) - sin confirmacion")

        # --- Paso 5: Patron de reversal en setup-TF ---
        # EMA 50 setup-TF NO debe actuar como S/R dinamico (precio debe estar lejos o cruzandola)
        setup_ema_key = _tf_ema("setup", 50)
        ema_1h_50 = _ema_val(analysis, setup_ema_key)
        if ema_1h_50:
            dist_1h = abs(entry_price - ema_1h_50) / ema_1h_50 * 100
            if dist_1h > 0.3:
                confidence += 5.0
                met.append(f"Paso 5a: EMA 50 1H NO actua como S/R dinamico (distancia {dist_1h:.2f}%)")
            else:
                failed.append(f"Paso 5a: EMA 50 1H puede estar actuando como S/R (distancia {dist_1h:.2f}%)")

        # TradingLab Intro: "este patrón de aquí, que normalmente será una
        # especie de cuña, una especie de triángulo, MUY POCAS VECES será un
        # canal" — channels are possible but rare, NOT invalid. Penalize
        # confidence rather than hard-blocking.
        chart_patterns = getattr(analysis, 'chart_patterns', [])
        if chart_patterns:
            for cp in chart_patterns:
                cp_name = ""
                if isinstance(cp, dict):
                    cp_name = cp.get("pattern", "").lower()
                elif isinstance(cp, str):
                    cp_name = cp.lower()
                if "channel" in cp_name:
                    confidence -= 10.0
                    failed.append(
                        f"Paso 5: Canal detectado — raro para BLACK, "
                        f"preferible cuña/triángulo (penalizacion -10)"
                    )

        # Patron de reversal en LTF
        has_reversal, rev_desc = _has_reversal_pattern(analysis, direction)
        if has_reversal:
            confidence += 15.0
            met.append(f"Paso 5b: {rev_desc}")
        else:
            failed.append(f"Paso 5b: {rev_desc}")

        # RSI Divergence on H4 — strong bonus, NOT hard block
        # TradingLab Intro: "Esto no es un paso como tal. Esto es simplemente
        # un añadido a las confirmaciones que buscamos y que queremos."
        # Day short example: "no es obligatorio que estén presentes"
        # Alex: "Si vemos algún tipo de divergencia en RSI en gráfico de 4 horas,
        # es mucho más probable que veamos ese movimiento."
        rsi_div = analysis.rsi_divergence
        if rsi_div:
            expected_div = "bullish" if direction == "BUY" else "bearish"
            if rsi_div == expected_div:
                confidence += 15.0
                met.append(f"Paso 5c: Divergencia RSI {rsi_div} en 4H (hace el trade mucho mas probable)")
            else:
                confidence -= 10.0
                failed.append(f"Paso 5c: Divergencia RSI {rsi_div} en direccion contraria a {direction} (penalizacion)")
        else:
            failed.append("Paso 5c: Sin divergencia RSI en 4H (añadido deseable, no obligatorio)")

        # MACD Divergence on H1 — MANDATORY for BLACK
        # TradingLab: "La divergencia MACD en 1H siempre estará presente" para BLACK setups.
        # This is a hard requirement, not a bonus.
        macd_div = getattr(analysis, 'macd_divergence', None)
        if macd_div:
            expected_macd_div = "bullish" if direction == "BUY" else "bearish"
            if macd_div == expected_macd_div:
                confidence += 10.0
                met.append(f"Paso 5c2 [OBLIGATORIO]: MACD divergencia {macd_div} en H1 alineada con {direction}")
            else:
                failed.append(
                    f"Paso 5c2 [OBLIGATORIO]: MACD divergencia {macd_div} en H1 contraria a {direction} "
                    f"— BLACK RECHAZADO (divergencia MACD en H1 siempre debe estar presente)"
                )
                return None
        else:
            # No MACD divergence data = cannot confirm mandatory condition = reject
            failed.append(
                "Paso 5c2 [OBLIGATORIO]: Sin divergencia MACD en H1 — BLACK RECHAZADO "
                "(la mentoria dice: 'la divergencia MACD en 1H siempre estará presente')"
            )
            return None

        # Consolidacion (patron correctivo formandose)
        if "DOJI" in analysis.candlestick_patterns:
            confidence += 5.0
            met.append("Paso 5d: Consolidacion detectada (DOJI = compresion/indecision)")

        # --- Paso 5e: REQUIRED 1H candlestick pattern at completion zone ---
        # TradingLab Step 6: "esperara que se complete al maximo este patron de
        # 1 hora y en el momento en el que se esta formando algun patron de
        # candlestick bajar a 5 minutos."
        # A bearish/bullish candlestick pattern on 1H is REQUIRED before checking 5M.
        h1_candle_patterns = getattr(analysis, 'h1_candlestick_patterns', [])
        if not h1_candle_patterns:
            # Fallback: use the general candlestick_patterns (which are from the LTF analysis)
            h1_candle_patterns = analysis.candlestick_patterns

        h1_has_pattern, h1_pattern_desc = _has_reversal_pattern(analysis, direction)
        if h1_has_pattern:
            confidence += 10.0
            met.append(f"Paso 5e: Patron de velas 1H en zona de completitud - {h1_pattern_desc}")
        else:
            # Check for any candlestick pattern (not just reversal) that signals completion
            completion_patterns = {
                "DOJI", "LOW_TEST", "HIGH_TEST", "ENGULFING_BULLISH",
                "ENGULFING_BEARISH", "MORNING_STAR", "EVENING_STAR",
                "TWEEZER_TOP", "TWEEZER_BOTTOM",
                "INSIDE_BAR_BULLISH", "INSIDE_BAR_BEARISH",
            }
            found_completion = set(h1_candle_patterns) & completion_patterns
            if found_completion:
                confidence += 5.0
                met.append(f"Paso 5e: Patron de velas 1H detectado: {', '.join(found_completion)}")
            else:
                failed.append(
                    "Paso 5e [OBLIGATORIO]: Sin patron de velas en 1H al completar zona correctiva "
                    "(requerido antes de bajar a 5M)"
                )
                return None  # No 1H candle pattern = no Black entry

        # --- Paso 6: Ejecutar en rompimiento 5M (RCC) ---
        # TradingLab execution priority for BLACK:
        # "5min MA50 > diagonal 5min > 2min MA50"
        # Diagonal is especially important for BLACK (triangle/wedge patterns)
        ema_5m_break, ema_5m_desc = _check_ema_break(analysis, "EMA_M5_50", direction)
        # M2 approximation via M5 EMA 20
        ema_2m_break, ema_2m_desc = _check_ema_break(analysis, "EMA_M5_20", direction)

        entry_found = False

        # Priority 1: EMA M5 50 break + RCC (highest priority)
        if ema_5m_break:
            if _check_rcc_confirmation(analysis, "EMA_M5_50", direction):
                confidence += 12.0
                met.append(f"Paso 6: RCC confirmado en EMA 5M 50 (prioridad maxima) - {ema_5m_desc}")
            else:
                failed.append(f"Paso 6: EMA 5M rota pero sin confirmacion RCC - entrada rechazada (NEVER enter on break alone)")
                return None
            entry_found = True

        # Priority 2: Diagonal breakout on 5min (especially important for BLACK triangle patterns)
        if not entry_found and hasattr(analysis, 'chart_patterns'):
            chart_patterns = analysis.chart_patterns or []
            for p in chart_patterns:
                ptype = p.get("type", "") if isinstance(p, dict) else str(p)
                ptf = p.get("timeframe", "") if isinstance(p, dict) else ""
                ptype_lower = ptype.lower()
                if any(k in ptype_lower for k in ("diagonal", "trendline", "wedge_break", "triangle_break")):
                    if ptf in ("M5", ""):
                        confidence += 10.0
                        met.append(f"Paso 6: Rompimiento de diagonal/triangulo en 5M ({ptype}) - clave para BLACK")
                        entry_found = True
                        break

        # Priority 3: EMA M2 50 break + RCC (2min timeframe)
        if not entry_found and ema_2m_break:
            if _check_rcc_confirmation(analysis, "EMA_M5_20", direction):
                confidence += 8.0
                met.append(f"Paso 6: RCC confirmado en EMA 2M (M5 proxy) - {ema_2m_desc}")
            else:
                failed.append(f"Paso 6: EMA 2M rota pero sin confirmacion RCC - entrada rechazada (NEVER enter on break alone)")
                return None
            entry_found = True

        if not entry_found:
            failed.append(f"Paso 6: Sin rompimiento 5M ni diagonal - {ema_5m_desc}")

        # NOTE: RSI divergence already checked above (Paso 5c) with BLACK-specific
        # logic (+15/-10). Do NOT call _check_rsi_divergence() here to avoid double-counting.

        # TradingLab SMC: Order Block / FVG / BOS confluence
        smc_ok, smc_bonus, smc_desc = _check_smc_confluence(analysis, direction, entry_price)
        if smc_ok:
            confidence += smc_bonus
            met.append(f"SMC: {smc_desc}")

        # TradingLab: "Si la media movil de 50 de 1 hora esta actuando como
        # soporte o como resistencia dinamica, no hay black."
        # Check if EMA 50 H1 acts as dynamic support (blocks SELL) or
        # dynamic resistance (blocks BUY).
        ema_1h_50 = _ema_val(analysis, "EMA_H1_50")
        if ema_1h_50 and ema_1h_50 > 0:
            distance_to_ema = abs(entry_price - ema_1h_50) / entry_price

            # Check if price is near EMA (within 0.3%) = acting as S/R
            if distance_to_ema < 0.003:
                failed.append("EMA 50 1H actuando como S/R dinamica (precio muy cerca) — no Black")
                return None

            # Check direction-specific dynamic S/R behavior using recent candles
            m5_candles = getattr(analysis, 'last_candles', {}).get("M5", [])
            if len(m5_candles) >= 5:
                # Count how many of last 5 candles bounced off the EMA
                bounce_count = 0
                for candle in m5_candles[-5:]:
                    c_low = candle.get("low", 0)
                    c_high = candle.get("high", 0)
                    c_close = candle.get("close", 0)
                    ema_tolerance = ema_1h_50 * 0.002

                    if direction == "BUY":
                        # EMA acting as dynamic resistance: price approaches from below, gets rejected
                        if c_high >= ema_1h_50 - ema_tolerance and c_close < ema_1h_50:
                            bounce_count += 1
                    else:  # SELL
                        # EMA acting as dynamic support: price approaches from above, gets rejected
                        if c_low <= ema_1h_50 + ema_tolerance and c_close > ema_1h_50:
                            bounce_count += 1

                if bounce_count >= 2:
                    ema_role = "resistencia dinamica" if direction == "BUY" else "soporte dinamico"
                    failed.append(
                        f"EMA 50 1H actuando como {ema_role} "
                        f"({bounce_count} rechazos recientes) — no Black"
                    )
                    return None

        # --- Paso 7: SL y TP ---
        sl = self.get_sl_placement(analysis, direction, entry_price)
        tp_levels = self.get_tp_levels(analysis, direction, entry_price)
        tp1 = tp_levels.get("tp1", 0.0)

        if sl == 0.0 or tp1 == 0.0:
            failed.append("Paso 7: No se pudo calcular SL o TP")
            return None

        # Validar que TP esté en el lado correcto de la entrada
        if direction == "BUY" and tp1 <= entry_price:
            failed.append(f"Paso 7: TP1 ({tp1:.5f}) debe estar encima de entrada ({entry_price:.5f}) para BUY")
            return None
        if direction == "SELL" and tp1 >= entry_price:
            failed.append(f"Paso 7: TP1 ({tp1:.5f}) debe estar debajo de entrada ({entry_price:.5f}) para SELL")
            return None

        risk = abs(entry_price - sl)
        reward = abs(tp1 - entry_price)
        if risk > 0:
            rr = reward / risk
            # BLACK requiere MINIMO 2:1 (contratendencia = mayor riesgo, mejor R:R)
            black_min_rr = max(settings.min_rr_black, settings.min_rr_ratio)
            if rr < black_min_rr - 1e-9:
                failed.append(f"R:R insuficiente: {rr:.2f}:1 (BLACK requiere MINIMO {black_min_rr}:1)")
                return None
            met.append(f"R:R valido: {rr:.2f}:1 (minimo Black: {black_min_rr}:1)")
            if rr >= 2.8:
                confidence += 5.0
                met.append(f"R:R excepcional (>= 2.80 promedio del curso)")
        else:
            return None

        if confidence < self.min_confidence:
            return None

        explanation_es = (
            f"Estrategia BLACK - CONTRATENDENCIA / Anticipacion\n"
            f"*** ESTRATEGIA DE ALTO RIESGO - R:R promedio 2.80:1 ***\n"
            f"Direccion: {'COMPRA' if direction == 'BUY' else 'VENTA'} (CONTRA tendencia {analysis.htf_trend.value})\n"
            f"Onda Elliott: Onda 1 (anticipacion de cambio)\n"
            f"Entrada: {entry_price:.5f} | SL: {sl:.5f} | TP: {tp1:.5f}\n"
            f"R:R: {rr:.2f}:1 | Confianza: {confidence:.0f}%\n"
            f"Detalles:\n" + "\n".join(f"  + {m}" for m in met)
        )
        if failed:
            explanation_es += "\n" + "\n".join(f"  - {f}" for f in failed)

        return SetupSignal(
            strategy=self.color,
            strategy_variant="BLACK",
            instrument=analysis.instrument,
            direction=direction,
            entry_price=entry_price,
            stop_loss=sl,
            take_profit_1=tp1,
            take_profit_max=tp_levels.get("tp_max"),
            confidence=confidence,
            reasoning=f"BLACK: Counter-trend at daily S/R. Overbought/oversold with deceleration. TP at EMA50 4H. Min 2:1 R:R.",
            explanation_es=explanation_es,
            elliott_wave_phase="Onda 1 (anticipacion)",
            timeframes_analyzed=["D", "H4", "H1", "M5"],
            risk_reward_ratio=rr,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_sl_placement(self, analysis: AnalysisResult, direction: str, entry_price: float) -> float:
        """SL encima del maximo anterior (SELL) o debajo del minimo anterior (BUY). Previous swing extreme only."""
        supports = analysis.key_levels.get("supports", [])
        resistances = analysis.key_levels.get("resistances", [])

        if direction == "BUY":
            below = [s for s in supports if s < entry_price]
            if below:
                return max(below)  # Nearest support below entry (tightest SL)
            return entry_price * 0.985  # 1.5% fallback (tight for counter-trend)
        else:
            above = [r for r in resistances if r > entry_price]
            if above:
                return min(above)  # Nearest resistance above entry (tightest SL)
            return entry_price * 1.015

    def get_tp_levels(self, analysis: AnalysisResult, direction: str, entry_price: float) -> Dict[str, float]:
        """TP en confirm-TF EMA 50 (with slight offset — Alex: "sacrificas 10 pips por salir antes").
        Swing: EMA 50 Weekly. Day Trading: EMA 50 4H. Scalping: EMA 50 M15."""
        confirm_ema_key = _tf_ema("confirm", 50)
        ema_4h_50 = _ema_val(analysis, confirm_ema_key) or _ema_val(analysis, "EMA_H4_50")
        result: Dict[str, float] = {}

        if ema_4h_50 and ema_4h_50 > 0:
            # Apply 97% offset: exit slightly before EMA 4H, not exactly on it
            # Alex: "no queremos ser el último en salir" — sacrifice a few pips for safety
            if direction == "BUY" and ema_4h_50 > entry_price:
                offset_tp = entry_price + (ema_4h_50 - entry_price) * 0.97
                result["tp1"] = offset_tp
            elif direction == "SELL" and ema_4h_50 < entry_price:
                offset_tp = entry_price - (entry_price - ema_4h_50) * 0.97
                result["tp1"] = offset_tp

        if "tp1" not in result:
            # BLACK TP is ALWAYS EMA 50 4H per mentorship.
            # If EMA is on the wrong side or unavailable, use its value anyway
            # as a projected target but apply a confidence warning.
            if ema_4h_50 and ema_4h_50 > 0:
                # EMA exists but is on the wrong side — still use it with warning
                result["tp1"] = ema_4h_50
                result["tp_warning"] = "EMA50_4H on wrong side of entry; confidence reduced"
            else:
                # EMA truly unavailable — use a conservative 1:2 R:R projection
                # This preserves the BLACK principle of targeting mean reversion
                sl = analysis.key_levels.get("supports", []) if direction == "BUY" else analysis.key_levels.get("resistances", [])
                if direction == "BUY":
                    result["tp1"] = entry_price + abs(entry_price - entry_price * 0.985) * 2
                else:
                    result["tp1"] = entry_price - abs(entry_price * 1.015 - entry_price) * 2
                result["tp_warning"] = "EMA50_4H unavailable; using 2R projection as fallback"

        return result


# ===========================================================================
# GREEN STRATEGY - Semanal + Patron Diario + Entrada 15M (Hasta 10:1 R:R)
# ===========================================================================

class GreenStrategy(BaseStrategy):
    """
    GREEN Strategy - Direccion Semanal + Patron Diario + Entrada 15M
    La mas lucrativa (hasta 10:1 R:R)
    TradingLab: GREEN is the ONLY strategy valid for crypto trading.

    Timeframe layouts:
    - Forex/General (all styles): W->D->H1->M15 (fixed, per Trading Mastery)
    - Crypto Swing:       W->D->H1->M15 (same as forex)
    - Crypto Day Trading: H4->H1->M15->M2 (per Crypto Mastery)
    - Crypto Scalping:    M15->M5->M1->M1 (M1 as fallback for 30s, per Crypto Mastery)

    7 Pasos:
    1. Direccion de tendencia semanal (alcista/bajista)
    2. Correccion semanal forma un patron diario (cuna/triangulo)
    3. Fibonacci, S/R, medias moviles como zonas de soporte dentro del patron
    4. Bajar a 1H: encontrar cambio de tendencia al FINAL del patron
       (rompimiento de diagonal, H&S, triangulo)
    5. Copiar nivel de 1H a 15M, ejecutar en PRIMER rompimiento+confirmacion en 15M
    6. SL debajo del minimo anterior de 1H (ajustado!). TP en maximo/minimo diario anterior
    """

    # Crypto timeframe layouts per trading style (Crypto Mastery)
    # Keys: direction, pattern, diagonal, execution
    CRYPTO_TIMEFRAMES = {
        "swing":       {"direction": "W",   "pattern": "D",  "diagonal": "H1",  "execution": "M15"},
        "day_trading": {"direction": "H4",  "pattern": "H1", "diagonal": "M15", "execution": "M2"},
        "scalping":    {"direction": "M15", "pattern": "M5", "diagonal": "M1",  "execution": "M1"},
    }
    # Forex/general: fixed layout regardless of style
    FOREX_TIMEFRAMES = {"direction": "W", "pattern": "D", "diagonal": "H1", "execution": "M15"}

    def __init__(self):
        super().__init__()
        self.color = StrategyColor.GREEN
        self.name = "GREEN - Semanal + Diario + 15M (Hasta 10:1 R:R)"
        self.min_confidence = 55.0

    def _get_green_timeframes(self, instrument: str) -> dict:
        """Get the correct timeframe layout for GREEN strategy.

        For forex/general instruments: always W->D->H1->M15 (Trading Mastery).
        For crypto: depends on current trading style (Crypto Mastery).
        """
        is_crypto = _is_crypto_instrument(instrument)
        if not is_crypto:
            return self.FOREX_TIMEFRAMES
        style = _get_trading_style()
        return self.CRYPTO_TIMEFRAMES.get(style, self.CRYPTO_TIMEFRAMES["swing"])

    def check_htf_conditions(self, analysis: AnalysisResult) -> Tuple[bool, float, List[str], List[str]]:
        score = 0.0
        met: List[str] = []
        failed: List[str] = []

        # --- Paso 1: Direccion de tendencia semanal ---
        direction = self._determine_direction(analysis)
        if direction is None:
            failed.append("Paso 1: Sin tendencia semanal clara (Green requiere tendencia semanal)")
            return False, score, met, failed

        score += 15.0
        met.append(f"Paso 1: Tendencia semanal {analysis.htf_trend.value}")

        # --- Paso 2: Correccion semanal forma patron diario ---
        # TradingLab: Also check for breakout of weekly resistance/support level
        # (not just divergence — the correction should break a key weekly level)
        if not analysis.htf_ltf_convergence:
            # LTF va contra HTF = posible correccion (bueno para Green)
            score += 15.0
            met.append("Paso 2: Divergencia HTF/LTF detectada - posible correccion semanal formando patron diario")
        else:
            # Convergencia: verificar si hay desaceleracion (fin de impulso, inicio de correccion)
            if _has_deceleration(analysis):
                score += 10.0
                met.append("Paso 2: Convergencia con desaceleracion - posible inicio de correccion")
            else:
                failed.append("Paso 2: Convergencia sin desaceleracion - puede no haber patron correctivo")

        # Paso 2b: Check breakout of weekly S/R level
        weekly_sr_broken = False
        price = _get_current_price_proxy(analysis)
        if price:
            w_supports = analysis.key_levels.get("supports", [])
            w_resistances = analysis.key_levels.get("resistances", [])
            tolerance = price * 0.005  # 0.5%
            if direction == "BUY":
                # For BUY: price should have broken above a weekly resistance
                for r in w_resistances:
                    if price > r and abs(price - r) < tolerance * 3:
                        weekly_sr_broken = True
                        score += 5.0
                        met.append(f"Paso 2b: Rompimiento de resistencia semanal {r:.5f}")
                        break
            else:
                # For SELL: price should have broken below a weekly support
                for s in w_supports:
                    if price < s and abs(price - s) < tolerance * 3:
                        weekly_sr_broken = True
                        score += 5.0
                        met.append(f"Paso 2b: Rompimiento de soporte semanal {s:.5f}")
                        break
        if not weekly_sr_broken:
            failed.append("Paso 2b: Sin rompimiento claro de nivel S/R semanal")

        # --- Paso 3: Fibonacci, S/R, medias moviles como soporte dentro del patron ---
        fib_382 = analysis.fibonacci_levels.get("0.382")
        fib_618 = analysis.fibonacci_levels.get("0.618")
        fib_750 = analysis.fibonacci_levels.get("0.750") or analysis.fibonacci_levels.get("0.75")
        ema_4h_50 = _ema_val(analysis, "EMA_H4_50")
        supports = analysis.key_levels.get("supports", [])
        resistances = analysis.key_levels.get("resistances", [])

        confluence_count = 0
        price = _get_current_price_proxy(analysis)

        # TradingLab Crypto: If Fib 0.75 is CLEARLY broken, the pullback is too deep
        # and the setup is invalid. Alex: "Si se rompe claramente el 0.75, no hay reentrada."
        # For BUY: price below 0.75 means correction went too deep.
        # For SELL: price above 0.75 means correction went too deep.
        if price and fib_750:
            fib_1000 = analysis.fibonacci_levels.get("1.0")
            fib_0 = analysis.fibonacci_levels.get("0.0")
            broken_075 = False
            if direction == "BUY" and fib_1000 is not None and fib_0 is not None:
                # In a BUY setup: 0.0 = swing high, 1.0 = swing low (retracement)
                # 0.75 is deeper retracement. If price < fib_750 (clearly past 75%), invalid.
                if fib_1000 > fib_0:
                    # fib_1000 is the low, fib_0 is the high — price below 0.75 = too deep
                    broken_075 = price < fib_750 and abs(price - fib_750) / price > 0.003
                else:
                    broken_075 = price > fib_750 and abs(price - fib_750) / price > 0.003
            elif direction == "SELL" and fib_1000 is not None and fib_0 is not None:
                if fib_1000 < fib_0:
                    broken_075 = price > fib_750 and abs(price - fib_750) / price > 0.003
                else:
                    broken_075 = price < fib_750 and abs(price - fib_750) / price > 0.003
            if broken_075:
                failed.append("Paso 3: Fibonacci 0.75 claramente roto - pullback demasiado profundo (setup invalido)")
                return False, score, met, failed

        if price:
            tolerance = price * 0.005  # 0.5%

            # Verificar confluencia de niveles
            if fib_382 and abs(price - fib_382) < tolerance:
                confluence_count += 1
            if fib_618 and abs(price - fib_618) < tolerance:
                confluence_count += 1
            if ema_4h_50 and abs(price - ema_4h_50) < tolerance:
                confluence_count += 1

            if direction == "BUY":
                nearby_supports = [s for s in supports if abs(price - s) < tolerance]
                confluence_count += len(nearby_supports)
            else:
                nearby_resistances = [r for r in resistances if abs(price - r) < tolerance]
                confluence_count += len(nearby_resistances)

        if confluence_count >= 2:
            score += 15.0
            met.append(f"Paso 3: Alta confluencia ({confluence_count} niveles coinciden) - zona de soporte fuerte")
        elif confluence_count == 1:
            score += 8.0
            met.append(f"Paso 3: Confluencia moderada ({confluence_count} nivel)")
        else:
            failed.append("Paso 3: Sin confluencia de niveles en zona actual")

        # Paso 3b: Check pullback TO the broken weekly level specifically
        # TradingLab: price should pull back to the broken S/R level (now acting as support/resistance)
        if weekly_sr_broken and price:
            # The broken level should now act as support (BUY) or resistance (SELL)
            pullback_to_level = False
            if direction == "BUY":
                for r in w_resistances:
                    if price > r and abs(price - r) / price < 0.008:  # Within 0.8% of broken resistance
                        pullback_to_level = True
                        score += 5.0
                        met.append(f"Paso 3b: Pullback al nivel roto {r:.5f} (ahora soporte)")
                        break
            else:
                for s in w_supports:
                    if price < s and abs(price - s) / price < 0.008:
                        pullback_to_level = True
                        score += 5.0
                        met.append(f"Paso 3b: Pullback al nivel roto {s:.5f} (ahora resistencia)")
                        break
            if not pullback_to_level:
                failed.append("Paso 3b: Sin pullback al nivel semanal roto")

        passed = score >= 25.0
        return passed, score, met, failed

    def check_ltf_entry(self, analysis: AnalysisResult) -> Optional[SetupSignal]:
        direction = self._determine_direction(analysis)
        if direction is None:
            return None

        # TradingLab: Volume confirmation - confluence scoring, not hard block
        vol_ok, vol_ratio = _check_volume_confirmation(analysis, "M5")

        # TradingLab: EMA 8 Weekly trend filter
        if not _check_weekly_ema8_filter(analysis, direction):
            return None  # Don't trade against weekly trend

        entry_price = _get_current_price_proxy(analysis)
        if entry_price is None:
            return None

        confidence = 0.0
        met: List[str] = []
        failed: List[str] = []

        # Volume confluence scoring (not hard block)
        if vol_ok and vol_ratio > 1.2:
            confidence += 5.0
            met.append(f"Volumen alto ({vol_ratio:.1f}x) confirma entrada")
        elif not vol_ok:
            confidence -= 3.0
            failed.append(f"Volumen bajo ({vol_ratio:.1f}x) - sin confirmacion de volumen")

        # TradingLab: Green REQUIRES 1H diagonal (non-negotiable)
        has_diagonal = False
        if hasattr(analysis, 'chart_patterns'):
            patterns = analysis.chart_patterns or []
            for p in patterns:
                ptype = p.get("type", "") if isinstance(p, dict) else str(p)
                if any(k in ptype.lower() for k in ("diagonal", "wedge", "triangle", "channel", "trendline")):
                    has_diagonal = True
                    break
        # TradingLab: "Si no hay diagonal en una hora, no hay trade. Esto no es negociable."
        # BOS/CHOCH is NOT a substitute for a diagonal pattern per the mentorship.
        # A diagonal/wedge/triangle/channel/trendline MUST be present.
        if not has_diagonal:
            failed.append("Green REQUIERE diagonal en 1H (non-negotiable) — sin patron diagonal, cuña, triangulo o canal")
            return None

        # --- Paso 4: Cambio de tendencia en 1H al final del patron ---
        # Buscamos que la tendencia LTF este girando a favor de la HTF
        # (reversal del movimiento correctivo)
        has_reversal, rev_desc = _has_reversal_pattern(analysis, direction)
        if has_reversal:
            confidence += 15.0
            met.append(f"Paso 4: Cambio de tendencia en 1H - {rev_desc}")
        else:
            # Verificar rompimiento de EMA como alternativa
            ema_1h_break, ema_1h_desc = _check_ema_break(analysis, "EMA_H1_50", direction)
            if ema_1h_break:
                confidence += 10.0
                met.append(f"Paso 4: EMA 50 1H rota a favor - {ema_1h_desc}")
            else:
                failed.append(f"Paso 4: Sin cambio de tendencia claro en 1H - {rev_desc}")

        # Deceleration as supporting evidence
        if _has_deceleration(analysis):
            confidence += 5.0
            met.append("Paso 4b: Desaceleracion confirma fin de patron")

        # TradingLab: RSI divergence bonus
        has_div, div_bonus = _check_rsi_divergence(analysis, direction)
        if has_div:
            confidence += div_bonus

        # TradingLab SMC: Order Block / FVG / BOS confluence
        smc_ok, smc_bonus, smc_desc = _check_smc_confluence(analysis, direction, entry_price)
        if smc_ok:
            confidence += smc_bonus
            met.append(f"SMC: {smc_desc}")

        # --- Paso 5: Entrada en 15M ---
        # TradingLab: "copiar la diagonal de 1H a 15M y ejecutar en rompimiento+cierre+
        # confirmacion de ese nivel" — NOT on EMA breaks.
        # Primary: detect diagonal/trendline breakout on 15M.
        # Fallback: use EMA breaks only if no diagonal data is available.
        diagonal_breakout_detected = False
        if hasattr(analysis, 'chart_patterns'):
            chart_patterns = analysis.chart_patterns or []
            for p in chart_patterns:
                ptype = p.get("type", "") if isinstance(p, dict) else str(p)
                ptf = p.get("timeframe", "") if isinstance(p, dict) else ""
                ptype_lower = ptype.lower()
                # Look for diagonal/trendline breakout on 15M or M5
                if any(k in ptype_lower for k in ("diagonal", "trendline", "wedge_break", "triangle_break")):
                    if ptf in ("M15", "M5", ""):
                        diagonal_breakout_detected = True
                        confidence += 15.0
                        met.append(f"Paso 5: Rompimiento de diagonal en 15M detectado ({ptype})")
                        break

        # Also check structure breaks as proxy for diagonal breakout
        if not diagonal_breakout_detected:
            structure_breaks = getattr(analysis, 'structure_breaks', [])
            for sb in structure_breaks[-5:]:
                if isinstance(sb, dict):
                    sb_dir = sb.get("direction", "")
                    sb_type = sb.get("type", "")
                    expected_dir = "bullish" if direction == "BUY" else "bearish"
                    if sb_dir == expected_dir and sb_type in ("BOS", "CHOCH"):
                        diagonal_breakout_detected = True
                        confidence += 12.0
                        met.append(f"Paso 5: Rompimiento estructural {sb_type} {sb_dir} (proxy para diagonal)")
                        break

        # GREEN entry is diagonal-ONLY per the mentorship: "copiar la diagonal
        # de 1H a 15M y ejecutar en rompimiento+cierre+confirmacion de ese nivel"
        # NO EMA fallback — if no diagonal exists, no trade.
        if not diagonal_breakout_detected:
            failed.append(
                "Paso 5: Sin rompimiento de diagonal en M15/M5 - GREEN requiere "
                "diagonal (NO fallback a EMAs per mentorship)"
            )

        # --- Paso 6: SL y TP ---
        sl = self.get_sl_placement(analysis, direction, entry_price)
        tp_levels = self.get_tp_levels(analysis, direction, entry_price)
        tp1 = tp_levels.get("tp1", 0.0)
        tp_max = tp_levels.get("tp_max")

        if sl == 0.0 or tp1 == 0.0:
            failed.append("Paso 6: No se pudo calcular SL o TP")
            return None

        # Validar que TP esté en el lado correcto de la entrada
        if direction == "BUY" and tp1 <= entry_price:
            failed.append(f"Paso 7: TP1 ({tp1:.5f}) debe estar encima de entrada ({entry_price:.5f}) para BUY")
            return None
        if direction == "SELL" and tp1 >= entry_price:
            failed.append(f"Paso 7: TP1 ({tp1:.5f}) debe estar debajo de entrada ({entry_price:.5f}) para SELL")
            return None

        risk = abs(entry_price - sl)
        reward = abs(tp1 - entry_price)
        if risk > 0:
            rr = reward / risk
            # GREEN busca minimo 2:1 (potencial hasta 10:1 R:R)
            green_min_rr = max(settings.min_rr_green, settings.min_rr_ratio)
            if rr < green_min_rr - 1e-9:
                failed.append(f"R:R insuficiente: {rr:.2f}:1 (Green busca minimo {green_min_rr}:1, ideal 5-10:1)")
                return None
            met.append(f"R:R valido: {rr:.2f}:1")
            if rr >= 5.0:
                confidence += 10.0
                met.append(f"R:R excepcional: {rr:.2f}:1 (Green puede lograr hasta 10:1)")
            elif rr >= 3.0:
                confidence += 5.0
                met.append(f"R:R bueno para Green: {rr:.2f}:1")
        else:
            return None

        if tp_max:
            reward_max = abs(tp_max - entry_price)
            if risk > 0:
                rr_max = reward_max / risk
                met.append(f"R:R maximo potencial: {rr_max:.2f}:1")

        # TradingLab Crypto: Green Fractal - same pattern on multiple TFs = stronger signal
        fractal_bonus = 0.0
        # Check if weekly, daily AND 4H all show same direction pattern
        htf_aligns = analysis.htf_trend.value == ("bullish" if direction == "BUY" else "bearish")
        ltf_aligns = analysis.ltf_trend.value == ("bullish" if direction == "BUY" else "bearish")
        if htf_aligns and ltf_aligns:
            fractal_bonus = 10.0
            met.append("Green Fractal: patron alineado en multiples timeframes (+10%)")
        confidence += fractal_bonus

        if confidence < self.min_confidence:
            return None

        explanation_es = (
            f"Estrategia GREEN - La mas lucrativa (hasta 10:1 R:R)\n"
            f"Direccion semanal: {'ALCISTA' if direction == 'BUY' else 'BAJISTA'}\n"
            f"Patron diario en correccion semanal + entrada en 15M/5M\n"
            f"Entrada: {entry_price:.5f} | SL: {sl:.5f} (ajustado al minimo 1H)\n"
            f"TP1: {tp1:.5f}"
            + (f" | TP_max: {tp_max:.5f}" if tp_max else "") + "\n"
            f"R:R: {rr:.2f}:1 | Confianza: {confidence:.0f}%\n"
            f"Detalles:\n" + "\n".join(f"  + {m}" for m in met)
        )
        if failed:
            explanation_es += "\n" + "\n".join(f"  - {f}" for f in failed)

        # Crypto instruments use EMA 50 trailing, NOT fixed TP exits
        # Mentorship: "crypto should use EMA 50 trailing on weekly chart"
        is_crypto = _is_crypto_instrument(analysis.instrument)
        if is_crypto:
            met.append(
                "CRYPTO: TP levels are REFERENCE only — position managed with EMA 50 trailing, "
                "NOT hard TP exits (per mentorship)"
            )

        # Determine timeframes used based on instrument type and trading style
        green_tf = self._get_green_timeframes(analysis.instrument)
        tf_list = list(dict.fromkeys([  # unique, ordered
            green_tf["direction"], green_tf["pattern"],
            green_tf["diagonal"], green_tf["execution"],
        ]))

        return SetupSignal(
            strategy=self.color,
            strategy_variant="GREEN",
            instrument=analysis.instrument,
            direction=direction,
            entry_price=entry_price,
            stop_loss=sl,
            take_profit_1=tp1,
            take_profit_max=tp_max,
            confidence=confidence,
            reasoning=f"GREEN: {green_tf['direction']} trend + {green_tf['pattern']} corrective pattern. Entry on {green_tf['execution']} first break. Tight SL for high R:R.",
            explanation_es=explanation_es,
            elliott_wave_phase="Correccion semanal -> impulso",
            timeframes_analyzed=tf_list,
            risk_reward_ratio=rr,
            conditions_met=met,
            conditions_failed=failed,
            trailing_tp_only=is_crypto,
        )

    def get_sl_placement(self, analysis: AnalysisResult, direction: str, entry_price: float) -> float:
        """
        Green SL placement depends on green_sl_mode config:

        - "advanced" (default): SL below last swing before diagonal break.
          Tight SL for high R:R — the mentorship method.
        - "beginner": SL below pattern minimum (wider, simpler).
          Uses the lowest low / highest high of the corrective pattern.

        TradingLab: Use 1H swing lows/highs (NOT daily S/R levels).
        Previous 1H swing low/high only, NO Fibonacci.
        """
        # Check green_sl_mode from config
        sl_mode = "advanced"
        try:
            sl_mode = settings.green_sl_mode
        except Exception:
            pass

        # Use swing_lows/swing_highs which come from 1H analysis (not daily S/R)
        swing_lows = getattr(analysis, 'swing_lows', [])
        swing_highs = getattr(analysis, 'swing_highs', [])
        ema_1h_50 = _ema_val(analysis, "EMA_H1_50")

        # Fallback: use key_levels supports/resistances if no swing data
        supports = analysis.key_levels.get("supports", []) if analysis.key_levels else []
        resistances = analysis.key_levels.get("resistances", []) if analysis.key_levels else []

        if sl_mode == "beginner":
            # Beginner mode: SL below pattern minimum (wider, simpler)
            if direction == "BUY":
                all_lows = swing_lows + supports
                below = [s for s in all_lows if s < entry_price]
                if below:
                    return min(below)  # Widest SL = pattern minimum
                return entry_price * 0.99  # 1% fallback (wider than advanced)
            else:
                all_highs = swing_highs + resistances
                above = [s for s in all_highs if s > entry_price]
                if above:
                    return max(above)  # Widest SL = pattern maximum
                return entry_price * 1.01

        # Advanced mode (default): SL below last swing before diagonal
        if direction == "BUY":
            # 1H swing lows below entry = SL placement
            below = [sl for sl in swing_lows if sl < entry_price]
            if below:
                return max(below)  # Tightest SL from 1H swing lows for high R:R
            # Fallback to key_levels supports
            support_below = [s for s in supports if s < entry_price]
            if support_below:
                return max(support_below)
            # Fallback: ligeramente debajo de EMA 1H si disponible
            if ema_1h_50 and ema_1h_50 < entry_price:
                return ema_1h_50 * 0.999
            return entry_price * 0.995  # 0.5% tight SL
        else:
            # 1H swing highs above entry = SL placement
            above = [sh for sh in swing_highs if sh > entry_price]
            if above:
                return min(above)  # Tightest SL from 1H swing highs for high R:R
            # Fallback to key_levels resistances
            resistance_above = [r for r in resistances if r > entry_price]
            if resistance_above:
                return min(resistance_above)
            if ema_1h_50 and ema_1h_50 > entry_price:
                return ema_1h_50 * 1.001
            return entry_price * 1.005

    def get_tp_levels(self, analysis: AnalysisResult, direction: str, entry_price: float) -> Dict[str, float]:
        """
        TP en maximo/minimo diario anterior.
        TP_max en el segundo nivel (para capturar R:R mas altos).

        CRYPTO NOTE: For crypto instruments, these TP levels are REFERENCE levels
        only, NOT hard exit points. The mentorship says crypto should use EMA 50
        trailing on weekly chart, NOT fixed TPs. The levels are still calculated
        for R:R validation and as visual reference, but the position manager will
        skip hard TP1 close and continue trailing with EMA 50 instead.
        """
        supports = analysis.key_levels.get("supports", [])
        resistances = analysis.key_levels.get("resistances", [])
        result: Dict[str, float] = {}

        if direction == "BUY":
            above = sorted([r for r in resistances if r > entry_price])
            if above:
                result["tp1"] = above[0]  # Primer nivel de resistencia
                if len(above) > 1:
                    result["tp_max"] = above[1]  # Segundo nivel diario S/R (daily previous high)
        else:
            below = sorted([s for s in supports if s < entry_price], reverse=True)
            if below:
                result["tp1"] = below[0]  # Primer nivel de soporte
                if len(below) > 1:
                    result["tp_max"] = below[1]  # Segundo nivel diario S/R (daily previous low)

        # Tambien considerar extensiones Fibonacci para TP_max
        fib_1272 = analysis.fibonacci_levels.get("ext_1.272")
        fib_1618 = analysis.fibonacci_levels.get("ext_1.618")
        if direction == "BUY":
            # Para BUY, las extensiones superiores
            fib_0 = analysis.fibonacci_levels.get("0.0")  # swing high
            if fib_0 and fib_0 > entry_price:
                if "tp_max" not in result or fib_0 > result.get("tp_max", 0):
                    result["tp_max"] = fib_0
        else:
            if fib_1618 and fib_1618 < entry_price:
                if "tp_max" not in result or fib_1618 < result.get("tp_max", float("inf")):
                    result["tp_max"] = fib_1618

        return result


# ===========================================================================
# Registro de estrategias
# ===========================================================================

ALL_STRATEGIES: List[BaseStrategy] = [
    BlueStrategy(),
    RedStrategy(),
    PinkStrategy(),
    WhiteStrategy(),
    BlackStrategy(),
    GreenStrategy(),
]

# Mapa por color para acceso directo
STRATEGY_MAP: Dict[StrategyColor, BaseStrategy] = {s.color: s for s in ALL_STRATEGIES}


def detect_all_setups(
    analysis: AnalysisResult,
    enabled_strategies: Optional[Dict[str, object]] = None,
) -> List[SetupSignal]:
    """
    Ejecutar deteccion de estrategias sobre un analisis.
    Retorna lista de SetupSignals ordenada por confianza (mayor primero).

    Args:
        analysis: Resultado del analisis multi-timeframe.
        enabled_strategies: Filtro opcional. Dict con colores habilitados:
            {"BLUE": True, "BLUE_A": True, "BLUE_B": False, "BLUE_C": True,
             "RED": True, "PINK": False, "WHITE": True, "BLACK": True, "GREEN": True}
            Si es None, se ejecutan todas las estrategias.
            Para BLUE, se puede habilitar la estrategia general o variantes especificas.

    Orden de evaluacion (del curso):
    1. BLUE  - Cambio tendencia 1H
    2. RED   - Cambio tendencia 4H
    3. PINK  - Patron correctivo
    4. WHITE - Post-Pink
    5. BLACK - Contratendencia
    6. GREEN - Semanal/Diaria/15M
    """
    signals: List[SetupSignal] = []

    # TradingLab: GREEN is the ONLY strategy for crypto instruments.
    # Skip BLUE, RED, PINK, WHITE, BLACK for crypto.
    is_crypto = _is_crypto_instrument(analysis.instrument)
    if is_crypto:
        logger.info(
            f"[CRYPTO] {analysis.instrument} detected as crypto - "
            f"only GREEN strategy will be evaluated"
        )

    for strategy in ALL_STRATEGIES:
        color = strategy.color.value  # e.g. "BLUE", "RED"

        # TradingLab: For crypto, only evaluate GREEN
        if is_crypto and strategy.color != StrategyColor.GREEN:
            continue

        # Filter by enabled strategies
        if enabled_strategies is not None:
            if not enabled_strategies.get(color, False):
                continue

        try:
            signal = strategy.detect(analysis)
            if signal is None:
                continue

            # For BLUE, check if the specific variant is enabled
            if color == "BLUE" and enabled_strategies is not None:
                variant = signal.strategy_variant  # "BLUE_A", "BLUE_B", "BLUE_C"
                # If specific variants are configured, check them
                has_variant_config = any(
                    k in enabled_strategies for k in ("BLUE_A", "BLUE_B", "BLUE_C")
                )
                if has_variant_config and not enabled_strategies.get(variant, False):
                    logger.debug(
                        f"[BLUE] Variante {variant} deshabilitada, descartando setup"
                    )
                    continue

            signals.append(signal)
            logger.info(
                f"[{strategy.color.value}] Setup encontrado: {signal.instrument} "
                f"{signal.direction} | Confianza: {signal.confidence:.0f}% "
                f"| R:R: {abs(signal.take_profit_1 - signal.entry_price) / max(abs(signal.entry_price - signal.stop_loss), 0.00001):.2f}:1"
            )
        except Exception as e:
            logger.error(f"Error en estrategia {strategy.color.value}: {e}")

    # Ordenar por confianza descendente
    signals.sort(key=lambda s: s.confidence, reverse=True)
    return signals


def _apply_elliott_wave_priority(
    analysis: AnalysisResult,
    setups: List[SetupSignal],
) -> List[SetupSignal]:
    """
    Re-score setups based on the current Elliott Wave phase.

    GREEN is excluded from wave bonuses (crypto-only strategy, not wave-specific).

    From Trading Plan 2024 (corrected):
    - Wave 1: BLACK +12 — counter-trend anticipation (highest priority)
    - Wave 2: BLUE +8, WHITE +3 — conservative pullback (reduce tp_max)
    - Wave 3: RED +10, BLUE +5, WHITE +5 — strongest impulse
    - Wave 4: PINK +8, BLUE +5, WHITE +3 — conservative pullback
    - Wave 5: PINK +10, WHITE +8, RED +5 — PINK designed for Wave 4->5
    - Wave A/B/C: BLACK +5 — corrective = counter-trend opportunity
    """
    if not setups:
        return setups

    ew = getattr(analysis, 'elliott_wave_detail', None) or {}
    wave_count = str(ew.get("wave_count", "")).strip()

    if not wave_count:
        return setups

    # Define confidence bonuses/penalties per wave
    # GREEN removed from wave mappings: it's crypto-only, not wave-specific.
    # BLACK has highest score in Wave 1 (counter-trend anticipation).
    # Wave 5 primarily favors PINK (designed for Wave 4->5).
    # WHITE added to wave mappings where appropriate.
    wave_bonuses: Dict[str, Dict[str, float]] = {
        "1": {"BLACK": 12},
        "2": {"BLUE": 8, "WHITE": 3},
        "3": {"RED": 10, "BLUE": 5, "WHITE": 5},
        "4": {"PINK": 8, "BLUE": 5, "WHITE": 3},
        "5": {"PINK": 10, "RED": 5, "WHITE": 8},
        "A": {"BLACK": 5},
        "B": {"BLACK": 5},
        "C": {"BLACK": 5},
    }

    # Default penalty for strategies not prioritized in the current wave
    default_penalty: Dict[str, float] = {
        "1": -5,
        "2": -5,
        "3": 0,
        "4": -5,
        "5": 0,
        "A": -3,
        "B": -3,
        "C": -3,
    }

    # Conservative waves reduce tp_max expectations
    conservative_waves = {"2", "4"}

    bonuses = wave_bonuses.get(wave_count, {})
    penalty = default_penalty.get(wave_count, 0)

    for setup in setups:
        color = setup.strategy.value  # e.g. "GREEN", "BLUE", etc.
        bonus = bonuses.get(color, penalty)
        setup.confidence = max(0, min(100, setup.confidence + bonus))

        # Add wave context to conditions_met for visibility
        bonus_label = f"+{bonus}" if bonus >= 0 else str(bonus)
        setup.conditions_met.append(
            f"Elliott Wave {wave_count}: {color} priority {bonus_label}"
        )

        # For conservative waves, reduce tp_max to encourage smaller targets
        if wave_count in conservative_waves and setup.take_profit_max is not None:
            # Pull tp_max closer to tp1 (midpoint between tp1 and original tp_max)
            midpoint = (setup.take_profit_1 + setup.take_profit_max) / 2.0
            setup.take_profit_max = midpoint
            setup.conditions_met.append(
                f"Wave {wave_count} conservative: tp_max reduced to {midpoint:.5f}"
            )

    logger.info(
        f"Elliott Wave priority applied (wave={wave_count}): "
        f"bonuses={bonuses}, default_penalty={penalty}"
    )

    return setups


def get_best_setup(
    analysis: AnalysisResult,
    enabled_strategies: Optional[Dict[str, object]] = None,
) -> Optional[SetupSignal]:
    """Retorna el mejor setup (mayor confianza) o None si no hay ninguno."""
    signals = detect_all_setups(analysis, enabled_strategies)

    # TradingLab: "La green es la UNICA estrategia que vamos a aplicar en cripto."
    # Safety filter: even if detect_all_setups missed it, enforce GREEN-only for crypto.
    if _is_crypto_instrument(analysis.instrument):
        signals = [s for s in signals if s.strategy == StrategyColor.GREEN]

    # TradingLab: "Memecoins to be AVOIDED for strategy trading (too manipulated, no patterns)"
    # Block trade signals on memecoin symbols when monitor-only mode is enabled.
    if settings.memecoins_monitor_only and analysis.instrument in settings.memecoin_symbols:
        logger.info(
            f"[MEMECOIN] {analysis.instrument} is a memecoin — "
            f"monitor only, no trading signals (mentorship rule)"
        )
        return None

    # Apply Elliott Wave prioritization before selecting the best
    signals = _apply_elliott_wave_priority(analysis, signals)

    # Re-sort after wave priority adjustments
    signals.sort(key=lambda s: s.confidence, reverse=True)

    return signals[0] if signals else None
