"""
NeonTrade AI - Estrategias de Trading
Implementacion completa de las 6 estrategias del curso TradingLab.

Estrategias (por color):
- BLUE:  Cambio de tendencia en 1H (Onda Elliott 1-2) - 3 variantes A/B/C
- RED:   Cambio de tendencia en 4H (Onda Elliott 2-3)
- PINK:  Continuacion por patron correctivo (Onda Elliott 4->5)
- WHITE: Continuacion post-Pink (Onda 3 de Onda 5)
- BLACK: Contratendencia / Anticipacion (Onda Elliott 1) - Mayor riesgo, mejor R:R
- GREEN: Direccion semanal + Patron diario + Entrada 15M - Mas lucrativa (hasta 10:1 R:R)

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
    Verifica si el precio esta en zona Fibonacci 0.382-0.618.
    Retorna (bool, descripcion).
    """
    fib = analysis.fibonacci_levels
    fib_382 = fib.get("0.382")
    fib_618 = fib.get("0.618")
    fib_500 = fib.get("0.5")

    if fib_382 is None or fib_618 is None:
        return False, "No hay niveles Fibonacci disponibles"

    low = min(fib_382, fib_618)
    high = max(fib_382, fib_618)

    in_zone = low <= price <= high
    if in_zone:
        return True, f"Precio {price:.5f} en zona Fib 0.382-0.618 ({low:.5f} - {high:.5f})"
    return False, f"Precio {price:.5f} fuera de zona Fib ({low:.5f} - {high:.5f})"


def _has_deceleration(analysis: AnalysisResult) -> bool:
    """Detecta desaceleracion usando condicion HTF y patrones de velas."""
    if analysis.htf_condition in (MarketCondition.DECELERATING,):
        return True
    decel_patterns = {
        "DOJI", "HAMMER", "SHOOTING_STAR", "ENGULFING_BULLISH",
        "ENGULFING_BEARISH", "MORNING_STAR", "EVENING_STAR",
        "HIGH_TEST", "LOW_TEST", "TWEEZER_TOP", "TWEEZER_BOTTOM",
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
        "HAMMER", "ENGULFING_BULLISH", "MORNING_STAR",
        "LOW_TEST", "TWEEZER_BOTTOM", "INSIDE_BAR_BULLISH",
    }
    bearish_reversals = {
        "SHOOTING_STAR", "ENGULFING_BEARISH", "EVENING_STAR",
        "HIGH_TEST", "TWEEZER_TOP", "INSIDE_BAR_BEARISH",
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

    # Usamos la EMA H1 20 como proxy del precio actual si esta disponible
    current_price = _ema_val(analysis, "EMA_H1_20")
    if current_price is None:
        # Fallback: usar EMA M5 5
        current_price = _ema_val(analysis, "EMA_M5_5")
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
    TradingLab RCC: Ruptura + Cierre + Confirmación.
    Checks that the PREVIOUS completed M5 candle closed on the correct side of the EMA,
    confirming the breakout (not just a wick through).
    Returns True if RCC is confirmed.
    """
    ema_val = _ema_val(analysis, ema_key)
    if ema_val is None:
        return True  # Can't check, don't block

    m5_candles = getattr(analysis, 'last_candles', {}).get("M5", [])
    if len(m5_candles) < 2:
        return True  # Not enough data, don't block

    # The second-to-last candle is the last COMPLETED candle (confirmation candle)
    prev_candle = m5_candles[-2]
    prev_close = prev_candle["close"]

    if direction == "BUY":
        return prev_close > ema_val  # Closed above EMA = confirmed breakout
    else:
        return prev_close < ema_val  # Closed below EMA = confirmed breakdown


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
    """Mejor estimacion del precio actual usando EMAs de marcos bajos."""
    for key in ("EMA_M5_2", "EMA_M5_5", "EMA_M2_2", "EMA_M2_5", "EMA_M5_20", "EMA_H1_20"):
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
    divs = getattr(analysis, 'rsi_divergences', [])
    if not divs:
        return False, 0.0
    for div in divs:
        if direction == "BUY" and div.get("type") == "bullish":
            return True, 10.0
        if direction == "SELL" and div.get("type") == "bearish":
            return True, 10.0
    return False, 0.0


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
    zone = getattr(analysis, 'premium_discount_zone', None)
    if zone is None:
        return True, ""  # No data = don't block

    if direction == "BUY" and zone == "discount":
        return True, "Precio en zona de DESCUENTO (favorable para compra)"
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
    - Wave 2 should retrace 38.2%-61.8% of Wave 1
    - Wave 4 should retrace 23.6%-38.2% of Wave 3
    - Wave 3 is never the shortest impulse wave
    Returns (valid, description).
    """
    ew = getattr(analysis, 'elliott_wave_detail', {})
    if not ew:
        return True, ""  # No data = don't block

    wave_label = ew.get("wave_count", "")
    fib = analysis.fibonacci_levels
    price = analysis.current_price

    if not price or not fib:
        return True, ""

    fib_382 = fib.get("0.382")
    fib_618 = fib.get("0.618")
    fib_236 = fib.get("0.236")

    if wave_label == "2" and fib_382 and fib_618:
        # Wave 2: expect price in 38.2%-61.8% retracement zone
        low = min(fib_382, fib_618)
        high = max(fib_382, fib_618)
        if low <= price <= high:
            return True, f"Onda 2: Precio en zona Fib 38.2-61.8% (retroceso valido)"
        else:
            return False, f"Onda 2: Precio fuera de zona Fib 38.2-61.8%"

    elif wave_label == "4" and fib_236 and fib_382:
        # Wave 4: expect shallower retracement (23.6%-38.2%)
        low = min(fib_236, fib_382)
        high = max(fib_236, fib_382)
        if low <= price <= high:
            return True, f"Onda 4: Precio en zona Fib 23.6-38.2% (retroceso valido)"
        else:
            # Wave 4 can also go deeper, just warn
            return True, f"Onda 4: Retroceso profundo (fuera de 23.6-38.2%)"

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


def _check_smc_confluence(analysis, direction: str, entry_price: float) -> tuple[bool, float, str]:
    """
    Check Smart Money Concepts confluence: Order Blocks, FVG, BOS/CHOCH.
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

        if direction == "BUY" and ob_type == "bullish":
            if ob_low - tolerance <= entry_price <= ob_high + tolerance:
                bonus += 8.0
                details.append(f"Order Block alcista ({ob_low:.5f}-{ob_high:.5f})")
                break
        elif direction == "SELL" and ob_type == "bearish":
            if ob_low - tolerance <= entry_price <= ob_high + tolerance:
                bonus += 8.0
                details.append(f"Order Block bajista ({ob_low:.5f}-{ob_high:.5f})")
                break

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
    if direction == "BUY" and rsi_d < 40:
        pos_pts += 1
        pos_details.append(f"RSI diario favorable ({rsi_d:.0f})")
    elif direction == "SELL" and rsi_d > 60:
        pos_pts += 1
        pos_details.append(f"RSI diario favorable ({rsi_d:.0f})")
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

    # 9. MACD alignment
    macd_h1 = analysis.macd_values.get("H1", {})
    if macd_h1:
        if direction == "BUY" and macd_h1.get("bullish", False):
            pos_pts += 1
            pos_details.append("MACD H1 alcista")
        elif direction == "SELL" and not macd_h1.get("bullish", True):
            pos_pts += 1
            pos_details.append("MACD H1 bajista")
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
    for ema_key in ("EMA_H1_50", "EMA_H4_50", "EMA_H4_20"):
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


def _classify_blue_variant(analysis: AnalysisResult, direction: str) -> str:
    """
    Clasifica la variante Blue (A, B, C) revisando condiciones en 4H.
    A: Doble suelo/techo antes de rompimiento (mas efectiva)
    B: Sin patron, solo rompimiento (mas comun)
    C: Rechazo de EMA 4H antes del pullback (mas riesgosa)
    """
    ema_4h_50 = _ema_val(analysis, "EMA_H4_50")
    ema_4h_20 = _ema_val(analysis, "EMA_H4_20")
    patterns = analysis.candlestick_patterns

    # Variante A: doble suelo/techo (detectamos por patrones de reversal repetidos)
    bullish_reversal_count = sum(1 for p in patterns if p in ("HAMMER", "ENGULFING_BULLISH", "MORNING_STAR"))
    bearish_reversal_count = sum(1 for p in patterns if p in ("SHOOTING_STAR", "ENGULFING_BEARISH", "EVENING_STAR"))

    if direction == "BUY" and bullish_reversal_count >= 2:
        return "BLUE_A"
    if direction == "SELL" and bearish_reversal_count >= 2:
        return "BLUE_A"

    # Variante C: precio esta cerca de EMA 4H (rechazo de EMA 4H)
    price = _get_current_price_proxy(analysis)
    if price and ema_4h_50:
        dist = abs(price - ema_4h_50) / ema_4h_50 * 100
        if dist < 0.2:
            return "BLUE_C"

    # Variante B: default
    return "BLUE_B"


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
            if not _check_minimum_candle_count(analysis, "EMA_M5_5", signal.direction, 3):
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

            # TradingLab: Check for limit entry opportunity (3-level confluence)
            limit_ok, limit_price, limit_desc = _check_limit_entry_confluence(
                analysis, signal.direction, signal.entry_price
            )
            if limit_ok and limit_price:
                signal.entry_type = "LIMIT"
                signal.limit_price = limit_price
                signal.confidence = min(100.0, signal.confidence + 5.0)
                signal.conditions_met.append(limit_desc)

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

    Tres variantes:
    - Blue A: Doble suelo/techo antes del rompimiento (mas efectiva)
    - Blue B: Sin patron, solo rompimiento (mas comun)
    - Blue C: Rechazo de EMA 4H antes del pullback (mas riesgosa)

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

        # --- Paso 3: Cambio de tendencia en 1H (EMA 50 1H rota) ---
        ema_1h_break, ema_1h_desc = _check_ema_break(analysis, "EMA_H1_50", direction)
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

        # TradingLab: Volume confirmation on breakout
        vol_ok, vol_ratio = _check_volume_confirmation(analysis, "M5")
        if not vol_ok:
            return None  # No entry without volume confirmation

        # TradingLab: EMA 8 Weekly trend filter
        if not _check_weekly_ema8_filter(analysis, direction):
            return None  # Don't trade against weekly trend

        entry_price = _get_current_price_proxy(analysis)
        if entry_price is None:
            return None

        confidence = 0.0
        met: List[str] = []
        failed: List[str] = []

        # --- Paso 4: Pullback a EMA 50 1H + Fibonacci ---
        pb_ok, pb_desc = _check_ema_pullback(analysis, "EMA_H1_50", direction)
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
        ema_5m_break, ema_5m_desc = _check_ema_break(analysis, "EMA_M5_5", direction)
        ema_2m_break, ema_2m_desc = _check_ema_break(analysis, "EMA_M2_2", direction)

        if ema_5m_break:
            # TradingLab RCC: verify previous candle confirmed the breakout
            if _check_rcc_confirmation(analysis, "EMA_M5_5", direction):
                confidence += 10.0
                met.append(f"Paso 6: RCC confirmado en EMA 5M - {ema_5m_desc}")
            else:
                confidence += 3.0  # Breakout without confirmation = weaker
                met.append(f"Paso 6: Rompimiento EMA 5M sin confirmacion RCC")
        else:
            failed.append(f"Paso 6: {ema_5m_desc}")

        if ema_2m_break:
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

        if sl == 0.0 or tp1 == 0.0:
            failed.append("Paso 7: No se pudo calcular SL o TP")
            return None

        # Validar R:R minimo (config: min_rr_ratio para Blue)
        risk = abs(entry_price - sl)
        reward = abs(tp1 - entry_price)
        if risk > 0:
            rr = reward / risk
            if rr < settings.min_rr_ratio:
                failed.append(f"R:R insuficiente: {rr:.2f}:1 (minimo {settings.min_rr_ratio}:1)")
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
        SL debajo de Fib 0.618 o minimo anterior (el que sea mas bajo para BUY).
        SL encima de Fib 0.618 o maximo anterior (el que sea mas alto para SELL).
        """
        fib_618 = analysis.fibonacci_levels.get("0.618", 0.0)
        supports = analysis.key_levels.get("supports", [])
        resistances = analysis.key_levels.get("resistances", [])

        if direction == "BUY":
            candidates = [fib_618] if fib_618 > 0 else []
            # Minimo anterior (soporte mas cercano por debajo)
            below = [s for s in supports if s < entry_price]
            if below:
                candidates.append(max(below))
            if not candidates:
                # Fallback: 1% debajo de entrada
                return entry_price * 0.99
            # El mas bajo de los dos (proteccion maxima)
            return min(candidates)
        else:  # SELL
            candidates = [fib_618] if fib_618 > 0 else []
            above = [r for r in resistances if r > entry_price]
            if above:
                candidates.append(min(above))
            if not candidates:
                return entry_price * 1.01
            return max(candidates)

    def get_tp_levels(self, analysis: AnalysisResult, direction: str, entry_price: float) -> Dict[str, float]:
        """TP1 en EMA 50 4H. TP_max en siguiente resistencia/soporte mas alla de TP1."""
        ema_4h_50 = _ema_val(analysis, "EMA_H4_50")
        resistances = analysis.key_levels.get("resistances", [])
        supports = analysis.key_levels.get("supports", [])

        result: Dict[str, float] = {}
        if ema_4h_50 and ema_4h_50 > 0:
            result["tp1"] = ema_4h_50
        else:
            # Fallback: resistencia/soporte mas cercano
            if direction == "BUY":
                above = [r for r in resistances if r > entry_price]
                if above:
                    result["tp1"] = min(above)
            else:
                below = [s for s in supports if s < entry_price]
                if below:
                    result["tp1"] = max(below)

        # TP_max: next resistance/support beyond TP1
        tp1 = result.get("tp1")
        if tp1:
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

    7 Pasos:
    1. Nivel S/R diario
    2. Precio ataca y desacelera en diario
    3. Bajar a 4H: cambio de tendencia confirmado (EMA 50 4H rota + maximos mas altos + diagonales)
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

        # --- Paso 3: Cambio de tendencia en 4H (EMA 50 4H rota) ---
        ema_4h_break, ema_4h_desc = _check_ema_break(analysis, "EMA_H4_50", direction)
        if ema_4h_break:
            score += 20.0
            met.append(f"Paso 3: {ema_4h_desc}")
        else:
            failed.append(f"Paso 3: {ema_4h_desc}")
            # Sin rompimiento de EMA 50 4H, Red no es valida
            return False, score, met, failed

        # Convergencia HTF/LTF da puntos extra
        if analysis.htf_ltf_convergence:
            score += 10.0
            met.append("Convergencia HTF/LTF confirmada")

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

        # TradingLab: Volume confirmation on breakout
        vol_ok, vol_ratio = _check_volume_confirmation(analysis, "M5")
        if not vol_ok:
            return None  # No entry without volume confirmation

        # TradingLab: EMA 8 Weekly trend filter
        if not _check_weekly_ema8_filter(analysis, direction):
            return None  # Don't trade against weekly trend

        entry_price = _get_current_price_proxy(analysis)
        if entry_price is None:
            return None

        confidence = 0.0
        met: List[str] = []
        failed: List[str] = []

        # --- Paso 4: Pullback a EMA 50 1H + EMA 50 4H + Fibonacci ---
        pb_1h, pb_1h_desc = _check_ema_pullback(analysis, "EMA_H1_50", direction)
        pb_4h, pb_4h_desc = _check_ema_pullback(analysis, "EMA_H4_50", direction)

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
        ema_5m_break, ema_5m_desc = _check_ema_break(analysis, "EMA_M5_5", direction)
        if ema_5m_break:
            if _check_rcc_confirmation(analysis, "EMA_M5_5", direction):
                confidence += 10.0
                met.append(f"Paso 6: RCC confirmado - {ema_5m_desc}")
            else:
                confidence += 3.0
                met.append(f"Paso 6: Rompimiento sin RCC")
        else:
            failed.append(f"Paso 6: {ema_5m_desc}")

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

        risk = abs(entry_price - sl)
        reward = abs(tp1 - entry_price)
        if risk > 0:
            rr = reward / risk
            if rr < settings.min_rr_ratio:
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
            elliott_wave_phase="Onda 2-3",
            timeframes_analyzed=["D", "H4", "H1", "M5"],
            risk_reward_ratio=rr,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_sl_placement(self, analysis: AnalysisResult, direction: str, entry_price: float) -> float:
        """SL debajo de EMA 50 4H o minimo anterior (para BUY). Inverso para SELL."""
        ema_4h_50 = _ema_val(analysis, "EMA_H4_50")
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
        TP1: swing high/low reciente.
        TP_max: extension Fibonacci 1.272 o 1.618.
        """
        result: Dict[str, float] = {}
        supports = analysis.key_levels.get("supports", [])
        resistances = analysis.key_levels.get("resistances", [])

        if direction == "BUY":
            above = [r for r in resistances if r > entry_price]
            if above:
                result["tp1"] = min(above)
        else:
            below = [s for s in supports if s < entry_price]
            if below:
                result["tp1"] = max(below)

        # Extension Fibonacci
        fib_1272 = analysis.fibonacci_levels.get("1.272")
        fib_1618 = analysis.fibonacci_levels.get("1.618")
        if fib_1272:
            result["tp_max"] = fib_1272
        if fib_1618:
            result["tp_max"] = fib_1618  # Preferimos el mas ambicioso

        return result


# ===========================================================================
# PINK STRATEGY - Continuacion por Patron Correctivo (Onda Elliott 4->5)
# ===========================================================================

class PinkStrategy(BaseStrategy):
    """
    PINK Strategy - Continuacion por Patron Correctivo (Onda Elliott 4->5)

    6 Pasos:
    1. Nivel S/R diario O tendencia clara desarrollada
    2. Alineacion de tendencia en 4H y 1H
    3. EMA 50 4H rota y luego pullback a ella (EMA 4H NO rota de vuelta)
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
        if analysis.htf_ltf_convergence:
            score += 15.0
            met.append("Paso 2: Tendencia alineada en 4H y 1H (convergencia HTF/LTF)")
        else:
            failed.append("Paso 2: Tendencia NO alineada entre 4H y 1H")
            # No es descalificante pero importante

        # --- Paso 3: EMA 50 4H rota y luego pullback (EMA 4H NO rota de vuelta) ---
        # La EMA 50 4H debe haber sido rota previamente (precio al lado correcto)
        ema_4h_break, ema_4h_desc = _check_ema_break(analysis, "EMA_H4_50", direction)
        if ema_4h_break:
            score += 15.0
            met.append(f"Paso 3a: EMA 50 4H rota previamente - {ema_4h_desc}")

            # Verificar que estamos en pullback (cerca de la EMA pero sin cruzarla de vuelta)
            pb_ok, pb_desc = _check_ema_pullback(analysis, "EMA_H4_50", direction)
            if pb_ok:
                score += 10.0
                met.append(f"Paso 3b: Pullback a EMA 50 4H - {pb_desc}")
            else:
                met.append("Paso 3b: No en pullback a EMA 4H (puede estar en impulso)")
        else:
            failed.append(f"Paso 3: EMA 50 4H NO rota - {ema_4h_desc}")
            return False, score, met, failed

        passed = score >= 25.0
        return passed, score, met, failed

    def check_ltf_entry(self, analysis: AnalysisResult) -> Optional[SetupSignal]:
        direction = self._determine_direction(analysis)
        if direction is None:
            return None

        # TradingLab: Volume confirmation on breakout
        vol_ok, vol_ratio = _check_volume_confirmation(analysis, "M5")
        if not vol_ok:
            return None  # No entry without volume confirmation

        # TradingLab: EMA 8 Weekly trend filter
        if not _check_weekly_ema8_filter(analysis, direction):
            return None  # Don't trade against weekly trend

        entry_price = _get_current_price_proxy(analysis)
        if entry_price is None:
            return None

        confidence = 0.0
        met: List[str] = []
        failed: List[str] = []

        # --- Paso 4: EMA 50 1H se rompe en patron correctivo ---
        # Para Pink, la EMA 50 1H se rompe CONTRA la tendencia (patron correctivo)
        # Es decir, si la tendencia es BUY, la EMA 50 1H se rompe a la baja temporalmente
        opposite = "SELL" if direction == "BUY" else "BUY"
        ema_1h_break_opposite, desc = _check_ema_break(analysis, "EMA_H1_50", opposite)

        if ema_1h_break_opposite:
            confidence += 15.0
            met.append(f"Paso 4: EMA 50 1H rota en correccion - {desc}")
        else:
            # Si la EMA no esta rota en contra, verificar si esta muy cerca (inicio de correccion)
            price = _get_current_price_proxy(analysis)
            ema_1h = _ema_val(analysis, "EMA_H1_50")
            if price and ema_1h:
                dist = abs(price - ema_1h) / ema_1h * 100
                if dist < 0.3:
                    confidence += 8.0
                    met.append(f"Paso 4: Precio muy cerca de EMA 50 1H ({dist:.2f}%) - posible inicio de correccion")
                else:
                    failed.append(f"Paso 4: EMA 50 1H no rota en correccion y distante ({dist:.2f}%)")
                    return None
            else:
                return None

        # Verificar patron correctivo (usamos patrones de velas como proxy)
        # Patrones de consolidacion: DOJI frecuentes indican compresion
        doji_count = analysis.candlestick_patterns.count("DOJI")
        if doji_count > 0:
            confidence += 5.0
            met.append("Paso 4b: Patron de consolidacion detectado (DOJI = compresion)")

        # --- Paso 5: Ejecutar al final del patron en 5M (RCC) ---
        ema_5m_break, ema_5m_desc = _check_ema_break(analysis, "EMA_M5_5", direction)
        if ema_5m_break:
            if _check_rcc_confirmation(analysis, "EMA_M5_5", direction):
                confidence += 15.0
                met.append(f"Paso 5: RCC confirmado en 5M - {ema_5m_desc}")
            else:
                confidence += 5.0
                met.append(f"Paso 5: Rompimiento 5M sin RCC")
        else:
            failed.append(f"Paso 5: Sin rompimiento 5M - {ema_5m_desc}")

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

        risk = abs(entry_price - sl)
        reward = abs(tp1 - entry_price)
        if risk > 0:
            rr = reward / risk
            if rr < settings.min_rr_ratio:
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
        """SL debajo del minimo anterior (proteger el patron)."""
        supports = analysis.key_levels.get("supports", [])
        resistances = analysis.key_levels.get("resistances", [])

        if direction == "BUY":
            below = [s for s in supports if s < entry_price]
            if below:
                return max(below)
            return entry_price * 0.99
        else:
            above = [r for r in resistances if r > entry_price]
            if above:
                return min(above)
            return entry_price * 1.01

    def get_tp_levels(self, analysis: AnalysisResult, direction: str, entry_price: float) -> Dict[str, float]:
        """TP en maximo/minimo anterior (extremo del swing previo)."""
        supports = analysis.key_levels.get("supports", [])
        resistances = analysis.key_levels.get("resistances", [])
        result: Dict[str, float] = {}

        if direction == "BUY":
            above = [r for r in resistances if r > entry_price]
            if above:
                result["tp1"] = min(above)
                if len(above) > 1:
                    result["tp_max"] = sorted(above)[1]  # Segundo nivel
        else:
            below = [s for s in supports if s < entry_price]
            if below:
                result["tp1"] = max(below)
                if len(below) > 1:
                    result["tp_max"] = sorted(below, reverse=True)[1]

        return result


# ===========================================================================
# WHITE STRATEGY - Continuacion Post-Pink (Onda 3 de Onda 5)
# ===========================================================================

class WhiteStrategy(BaseStrategy):
    """
    WHITE Strategy - Continuacion Post-Pink (Onda 3 de Onda 5)

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

        if analysis.htf_ltf_convergence:
            score += 10.0
            met.append("Paso 1b: Convergencia HTF/LTF (indica tendencia consolidada)")
        else:
            failed.append("Paso 1b: Sin convergencia HTF/LTF")

        # --- Paso 2: Impulso + pullback en 1H ---
        # Verificar que EMA 50 1H esta en el lado correcto (tendencia ya rota previamente)
        ema_1h_ok, ema_1h_desc = _check_ema_break(analysis, "EMA_H1_50", direction)
        if ema_1h_ok:
            score += 10.0
            met.append(f"Paso 2: Tendencia 1H intacta - {ema_1h_desc}")
        else:
            failed.append(f"Paso 2: Tendencia 1H perdida - {ema_1h_desc}")
            return False, score, met, failed

        # EMA 50 4H tambien debe estar rota a favor
        ema_4h_ok, ema_4h_desc = _check_ema_break(analysis, "EMA_H4_50", direction)
        if ema_4h_ok:
            score += 10.0
            met.append(f"Paso 2b: EMA 50 4H a favor - {ema_4h_desc}")

        passed = score >= 20.0
        return passed, score, met, failed

    def check_ltf_entry(self, analysis: AnalysisResult) -> Optional[SetupSignal]:
        direction = self._determine_direction(analysis)
        if direction is None:
            return None

        # TradingLab: Volume confirmation on breakout
        vol_ok, vol_ratio = _check_volume_confirmation(analysis, "M5")
        if not vol_ok:
            return None  # No entry without volume confirmation

        # TradingLab: EMA 8 Weekly trend filter
        if not _check_weekly_ema8_filter(analysis, direction):
            return None  # Don't trade against weekly trend

        entry_price = _get_current_price_proxy(analysis)
        if entry_price is None:
            return None

        confidence = 0.0
        met: List[str] = []
        failed: List[str] = []

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
        ema_5m_break, ema_5m_desc = _check_ema_break(analysis, "EMA_M5_5", direction)
        if ema_5m_break:
            if _check_rcc_confirmation(analysis, "EMA_M5_5", direction):
                confidence += 10.0
                met.append(f"Paso 5: RCC confirmado - {ema_5m_desc}")
            else:
                confidence += 3.0
                met.append(f"Paso 5: Rompimiento sin RCC")
        else:
            failed.append(f"Paso 5: {ema_5m_desc}")

        ema_2m_break, ema_2m_desc = _check_ema_break(analysis, "EMA_M2_2", direction)
        if ema_2m_break:
            confidence += 5.0
            met.append(f"Paso 5b: Confirmacion EMA 2M - {ema_2m_desc}")

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

        risk = abs(entry_price - sl)
        reward = abs(tp1 - entry_price)
        if risk > 0:
            rr = reward / risk
            if rr < settings.min_rr_ratio:
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
        """SL encima del maximo anterior (SELL) o debajo del minimo anterior (BUY)."""
        supports = analysis.key_levels.get("supports", [])
        resistances = analysis.key_levels.get("resistances", [])

        if direction == "BUY":
            below = [s for s in supports if s < entry_price]
            if below:
                return max(below)
            return entry_price * 0.99
        else:
            above = [r for r in resistances if r > entry_price]
            if above:
                return min(above)
            return entry_price * 1.01

    def get_tp_levels(self, analysis: AnalysisResult, direction: str, entry_price: float) -> Dict[str, float]:
        """TP en el nivel objetivo de Pink (extremo del swing previo).
        TP_max = maximum/minimum of 4H impulse (approx via EMA H4 values or S/R levels)."""
        supports = analysis.key_levels.get("supports", [])
        resistances = analysis.key_levels.get("resistances", [])
        result: Dict[str, float] = {}

        if direction == "BUY":
            above = [r for r in resistances if r > entry_price]
            if above:
                sorted_above = sorted(above)
                result["tp1"] = sorted_above[0]
                if len(sorted_above) > 1:
                    result["tp_max"] = sorted_above[1]
        else:
            below = [s for s in supports if s < entry_price]
            if below:
                sorted_below = sorted(below, reverse=True)
                result["tp1"] = sorted_below[0]
                if len(sorted_below) > 1:
                    result["tp_max"] = sorted_below[1]

        # TP_max override: use max/min of 4H impulse if available from EMA values
        # Approximate the 4H impulse extreme using the highest/lowest EMA H4 values
        ema_h4_50 = _ema_val(analysis, "EMA_H4_50")
        ema_h4_20 = _ema_val(analysis, "EMA_H4_20")
        if ema_h4_50 and ema_h4_20:
            if direction == "BUY":
                # Impulse max: estimate using the spread between fast and slow EMA
                impulse_max = ema_h4_20 + abs(ema_h4_20 - ema_h4_50) * 2.0
                if "tp_max" not in result or impulse_max > result.get("tp_max", 0):
                    result["tp_max"] = impulse_max
            else:
                impulse_min = ema_h4_20 - abs(ema_h4_20 - ema_h4_50) * 2.0
                if "tp_max" not in result or impulse_min < result.get("tp_max", float("inf")):
                    result["tp_max"] = impulse_min

        return result


# ===========================================================================
# BLACK STRATEGY - Contratendencia / Anticipacion (Onda Elliott 1)
# ===========================================================================

class BlackStrategy(BaseStrategy):
    """
    BLACK Strategy - Contratendencia / Anticipacion (Onda Elliott 1)
    La mas riesgosa pero con mejor R:R promedio (2.80:1)

    7 Pasos:
    1. Nivel S/R diario (OBLIGATORIO, no negociable)
    2. Precio diario ataca el nivel con condicion de sobrecompra/sobreventa
    3. Desaceleracion/senales de reversal en diario
    4. 4H sobrecompra: precio lejos de EMA 50 4H + consolidacion/desaceleracion
    5. 1H: patron de reversal (triangulo/cuna). EMA 50 1H NO debe actuar como S/R dinamico.
       Verificar divergencia RSI en 4H
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

        # --- Paso 4: 4H sobrecomprado + precio lejos de EMA 50 4H ---
        ema_4h_50 = _ema_val(analysis, "EMA_H4_50")
        price = _get_current_price_proxy(analysis)

        if ema_4h_50 and price:
            distance_pct = abs(price - ema_4h_50) / ema_4h_50 * 100
            if distance_pct > 0.5:
                score += 10.0
                met.append(f"Paso 4: Precio lejos de EMA 50 4H ({distance_pct:.2f}%) - sobreextendido")
            else:
                failed.append(f"Paso 4: Precio cerca de EMA 50 4H ({distance_pct:.2f}%) - no sobreextendido")
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

        # TradingLab: Volume confirmation on breakout
        vol_ok, vol_ratio = _check_volume_confirmation(analysis, "M5")
        if not vol_ok:
            return None  # No entry without volume confirmation

        # TradingLab: EMA 8 Weekly trend filter
        if not _check_weekly_ema8_filter(analysis, direction):
            return None  # Don't trade against weekly trend

        entry_price = _get_current_price_proxy(analysis)
        if entry_price is None:
            return None

        confidence = 0.0
        met: List[str] = []
        failed: List[str] = []

        # --- Paso 5: Patron de reversal en 1H ---
        # EMA 50 1H NO debe actuar como S/R dinamico (precio debe estar lejos o cruzandola)
        ema_1h_50 = _ema_val(analysis, "EMA_H1_50")
        if ema_1h_50:
            dist_1h = abs(entry_price - ema_1h_50) / ema_1h_50 * 100
            if dist_1h > 0.3:
                confidence += 5.0
                met.append(f"Paso 5a: EMA 50 1H NO actua como S/R dinamico (distancia {dist_1h:.2f}%)")
            else:
                failed.append(f"Paso 5a: EMA 50 1H puede estar actuando como S/R (distancia {dist_1h:.2f}%)")

        # Patron de reversal en LTF
        has_reversal, rev_desc = _has_reversal_pattern(analysis, direction)
        if has_reversal:
            confidence += 15.0
            met.append(f"Paso 5b: {rev_desc}")
        else:
            failed.append(f"Paso 5b: {rev_desc}")

        # RSI Divergence on H4 (REQUIRED confirmation for Black - ch15.14)
        rsi_div = analysis.rsi_divergence
        if rsi_div:
            expected_div = "bullish" if direction == "BUY" else "bearish"
            if rsi_div == expected_div:
                confidence += 15.0
                met.append(f"Paso 5c: Divergencia RSI {rsi_div} detectada en 4H (CONFIRMACION)")
            else:
                failed.append(f"Paso 5c: Divergencia RSI {rsi_div} no coincide con {direction}")
        else:
            failed.append("Paso 5c: Sin divergencia RSI en 4H (confirmacion debil)")

        # Consolidacion (patron correctivo formandose)
        if "DOJI" in analysis.candlestick_patterns:
            confidence += 5.0
            met.append("Paso 5d: Consolidacion detectada (DOJI = compresion/indecision)")

        # --- Paso 6: Ejecutar en rompimiento 5M (RCC) ---
        ema_5m_break, ema_5m_desc = _check_ema_break(analysis, "EMA_M5_5", direction)
        if ema_5m_break:
            if _check_rcc_confirmation(analysis, "EMA_M5_5", direction):
                confidence += 10.0
                met.append(f"Paso 6: RCC confirmado - {ema_5m_desc}")
            else:
                confidence += 3.0
                met.append(f"Paso 6: Rompimiento sin RCC")
        else:
            failed.append(f"Paso 6: Sin rompimiento 5M - {ema_5m_desc}")

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

        if sl == 0.0 or tp1 == 0.0:
            failed.append("Paso 7: No se pudo calcular SL o TP")
            return None

        risk = abs(entry_price - sl)
        reward = abs(tp1 - entry_price)
        if risk > 0:
            rr = reward / risk
            # BLACK requiere MINIMO 2:1 o min_rr_ratio (el mayor de los dos)
            black_min_rr = max(2.0, settings.min_rr_ratio)
            if rr < black_min_rr:
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
        """SL encima del maximo anterior (SELL) o debajo del minimo anterior (BUY)."""
        supports = analysis.key_levels.get("supports", [])
        resistances = analysis.key_levels.get("resistances", [])

        if direction == "BUY":
            # SL debajo del minimo anterior
            below = [s for s in supports if s < entry_price]
            if below:
                return max(below)
            return entry_price * 0.985  # 1.5% fallback (tight for counter-trend)
        else:
            # SL encima del maximo anterior
            above = [r for r in resistances if r > entry_price]
            if above:
                return min(above)
            return entry_price * 1.015

    def get_tp_levels(self, analysis: AnalysisResult, direction: str, entry_price: float) -> Dict[str, float]:
        """TP en EMA 50 4H."""
        ema_4h_50 = _ema_val(analysis, "EMA_H4_50")
        result: Dict[str, float] = {}

        if ema_4h_50 and ema_4h_50 > 0:
            result["tp1"] = ema_4h_50
        else:
            # Fallback: nivel S/R intermedio
            supports = analysis.key_levels.get("supports", [])
            resistances = analysis.key_levels.get("resistances", [])
            if direction == "BUY":
                above = [r for r in resistances if r > entry_price]
                if above:
                    result["tp1"] = min(above)
            else:
                below = [s for s in supports if s < entry_price]
                if below:
                    result["tp1"] = max(below)

        return result


# ===========================================================================
# GREEN STRATEGY - Semanal + Patron Diario + Entrada 15M (Hasta 10:1 R:R)
# ===========================================================================

class GreenStrategy(BaseStrategy):
    """
    GREEN Strategy - Direccion Semanal + Patron Diario + Entrada 15M
    La mas lucrativa (hasta 10:1 R:R)

    6 Pasos:
    1. Direccion de tendencia semanal (alcista/bajista)
    2. Correccion semanal forma un patron diario (cuna/triangulo)
    3. Fibonacci, S/R, medias moviles como zonas de soporte dentro del patron
    4. Bajar a 1H: encontrar cambio de tendencia al FINAL del patron
       (rompimiento de diagonal, H&S, triangulo)
    5. Copiar nivel de 1H a 15M, ejecutar en PRIMER rompimiento+confirmacion en 15M
    6. SL debajo del minimo anterior de 1H (ajustado!). TP en maximo/minimo diario anterior
    """

    def __init__(self):
        super().__init__()
        self.color = StrategyColor.GREEN
        self.name = "GREEN - Semanal + Diario + 15M (Hasta 10:1 R:R)"
        self.min_confidence = 55.0

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
        # Una correccion se detecta cuando el LTF va contra el HTF temporalmente
        # o cuando el mercado esta en consolidacion despues de un impulso
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

        # --- Paso 3: Fibonacci, S/R, medias moviles como soporte dentro del patron ---
        fib_382 = analysis.fibonacci_levels.get("0.382")
        fib_618 = analysis.fibonacci_levels.get("0.618")
        ema_4h_50 = _ema_val(analysis, "EMA_H4_50")
        supports = analysis.key_levels.get("supports", [])
        resistances = analysis.key_levels.get("resistances", [])

        confluence_count = 0
        price = _get_current_price_proxy(analysis)

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

        passed = score >= 25.0
        return passed, score, met, failed

    def check_ltf_entry(self, analysis: AnalysisResult) -> Optional[SetupSignal]:
        direction = self._determine_direction(analysis)
        if direction is None:
            return None

        # TradingLab: Volume confirmation on breakout
        vol_ok, vol_ratio = _check_volume_confirmation(analysis, "M5")
        if not vol_ok:
            return None  # No entry without volume confirmation

        # TradingLab: EMA 8 Weekly trend filter
        if not _check_weekly_ema8_filter(analysis, direction):
            return None  # Don't trade against weekly trend

        entry_price = _get_current_price_proxy(analysis)
        if entry_price is None:
            return None

        confidence = 0.0
        met: List[str] = []
        failed: List[str] = []

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

        # --- Paso 5: Entrada en 15M (RCC: Ruptura + Cierre + Confirmación) ---
        ema_5m_break, ema_5m_desc = _check_ema_break(analysis, "EMA_M5_5", direction)
        ema_5m_20_break, ema_5m_20_desc = _check_ema_break(analysis, "EMA_M5_20", direction)

        if ema_5m_break and ema_5m_20_break:
            if _check_rcc_confirmation(analysis, "EMA_M5_5", direction):
                confidence += 15.0
                met.append(f"Paso 5: RCC confirmado (EMA 5 + EMA 20 de M5)")
            else:
                confidence += 8.0
                met.append(f"Paso 5: Rompimiento doble sin RCC")
        elif ema_5m_break:
            confidence += 5.0
            met.append(f"Paso 5: Rompimiento parcial - {ema_5m_desc}")
        else:
            failed.append(f"Paso 5: Sin rompimiento - {ema_5m_desc}")

        # --- Paso 6: SL y TP ---
        sl = self.get_sl_placement(analysis, direction, entry_price)
        tp_levels = self.get_tp_levels(analysis, direction, entry_price)
        tp1 = tp_levels.get("tp1", 0.0)
        tp_max = tp_levels.get("tp_max")

        if sl == 0.0 or tp1 == 0.0:
            failed.append("Paso 6: No se pudo calcular SL o TP")
            return None

        risk = abs(entry_price - sl)
        reward = abs(tp1 - entry_price)
        if risk > 0:
            rr = reward / risk
            # GREEN busca minimo 2:1 o min_rr_ratio (el mayor de los dos)
            green_min_rr = max(2.0, settings.min_rr_ratio)
            if rr < green_min_rr:
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
            reasoning=f"GREEN: Weekly trend + daily corrective pattern. Entry on 15M/5M first break. Tight SL for high R:R.",
            explanation_es=explanation_es,
            elliott_wave_phase="Correccion semanal -> impulso",
            timeframes_analyzed=["W", "D", "H4", "H1", "M15", "M5"],
            risk_reward_ratio=rr,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_sl_placement(self, analysis: AnalysisResult, direction: str, entry_price: float) -> float:
        """
        SL debajo del minimo anterior de 1H (ajustado para lograr alto R:R).
        Green usa SL muy ajustado, por eso logra R:R tan altos.
        """
        supports = analysis.key_levels.get("supports", [])
        resistances = analysis.key_levels.get("resistances", [])
        ema_1h_50 = _ema_val(analysis, "EMA_H1_50")

        if direction == "BUY":
            # SL debajo del minimo anterior de 1H (tight)
            below = [s for s in supports if s < entry_price]
            if below:
                nearest_support = max(below)
                # Usar el soporte mas cercano (tight SL)
                return nearest_support
            # Fallback: ligeramente debajo de EMA 1H si disponible
            if ema_1h_50 and ema_1h_50 < entry_price:
                return ema_1h_50 * 0.999
            return entry_price * 0.995  # 0.5% tight SL
        else:
            above = [r for r in resistances if r > entry_price]
            if above:
                nearest_resistance = min(above)
                return nearest_resistance
            if ema_1h_50 and ema_1h_50 > entry_price:
                return ema_1h_50 * 1.001
            return entry_price * 1.005

    def get_tp_levels(self, analysis: AnalysisResult, direction: str, entry_price: float) -> Dict[str, float]:
        """
        TP en maximo/minimo diario anterior.
        TP_max en el segundo nivel (para capturar R:R mas altos).
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
        fib_1272 = analysis.fibonacci_levels.get("1.272")
        fib_1618 = analysis.fibonacci_levels.get("1.618")
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

    for strategy in ALL_STRATEGIES:
        color = strategy.color.value  # e.g. "BLUE", "RED"

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


def get_best_setup(
    analysis: AnalysisResult,
    enabled_strategies: Optional[Dict[str, object]] = None,
) -> Optional[SetupSignal]:
    """Retorna el mejor setup (mayor confianza) o None si no hay ninguno."""
    signals = detect_all_setups(analysis, enabled_strategies)
    return signals[0] if signals else None
