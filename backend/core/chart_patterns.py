"""
NeonTrade AI - Advanced Chart Pattern Detection
Detects classic chart patterns from price data using swing point analysis.

Patterns detected:
- Double Top / Double Bottom
- Head & Shoulders / Inverse Head & Shoulders
- Ascending / Descending / Symmetrical Triangle
- Rising / Falling Wedge
- Bull / Bear Flag
- Cup & Handle
"""

from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass
import pandas as pd
import numpy as np
from loguru import logger


@dataclass
class ChartPattern:
    """A detected chart pattern."""
    name: str            # e.g. "DOUBLE_TOP", "HEAD_AND_SHOULDERS"
    direction: str       # "bullish" or "bearish"
    confidence: float    # 0-100
    start_idx: int       # Index where pattern starts
    end_idx: int         # Index where pattern ends (current)
    neckline: float      # Key breakout level
    target: float        # Projected price target
    description: str     # Human-readable description (Spanish)


def detect_chart_patterns(df: pd.DataFrame, lookback: int = 100) -> List[ChartPattern]:
    """
    Detect all chart patterns in the given OHLC DataFrame.
    Returns list of detected patterns sorted by confidence.
    """
    if df.empty or len(df) < 30:
        return []

    patterns: List[ChartPattern] = []
    recent = df.tail(lookback) if len(df) > lookback else df

    # Find swing highs and lows
    swing_highs = _find_swing_highs(recent, window=5)
    swing_lows = _find_swing_lows(recent, window=5)

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return patterns

    # Detect each pattern type
    p = _detect_double_top(recent, swing_highs, swing_lows)
    if p:
        patterns.append(p)

    p = _detect_double_bottom(recent, swing_highs, swing_lows)
    if p:
        patterns.append(p)

    p = _detect_head_and_shoulders(recent, swing_highs, swing_lows)
    if p:
        patterns.append(p)

    p = _detect_inverse_head_and_shoulders(recent, swing_highs, swing_lows)
    if p:
        patterns.append(p)

    p = _detect_ascending_triangle(recent, swing_highs, swing_lows)
    if p:
        patterns.append(p)

    p = _detect_descending_triangle(recent, swing_highs, swing_lows)
    if p:
        patterns.append(p)

    p = _detect_symmetrical_triangle(recent, swing_highs, swing_lows)
    if p:
        patterns.append(p)

    p = _detect_rising_wedge(recent, swing_highs, swing_lows)
    if p:
        patterns.append(p)

    p = _detect_falling_wedge(recent, swing_highs, swing_lows)
    if p:
        patterns.append(p)

    p = _detect_bull_flag(recent, swing_highs, swing_lows)
    if p:
        patterns.append(p)

    p = _detect_bear_flag(recent, swing_highs, swing_lows)
    if p:
        patterns.append(p)

    p = _detect_cup_and_handle(recent, swing_highs, swing_lows)
    if p:
        patterns.append(p)

    # Channels (from Gráficas de Patrones PDF)
    p = _detect_ascending_channel(recent, swing_highs, swing_lows)
    if p:
        patterns.append(p)

    p = _detect_descending_channel(recent, swing_highs, swing_lows)
    if p:
        patterns.append(p)

    patterns.sort(key=lambda x: x.confidence, reverse=True)
    return patterns


# ── Swing Point Detection ──────────────────────────────────────────────

def _find_swing_highs(df: pd.DataFrame, window: int = 5) -> List[Tuple[int, float]]:
    """Find swing high points. Returns [(index_position, price), ...]"""
    highs = []
    data = df.reset_index(drop=True)
    for i in range(window, len(data) - window):
        is_high = True
        for j in range(1, window + 1):
            if data["high"].iloc[i] <= data["high"].iloc[i - j] or \
               data["high"].iloc[i] <= data["high"].iloc[i + j]:
                is_high = False
                break
        if is_high:
            highs.append((i, data["high"].iloc[i]))
    return highs


def _find_swing_lows(df: pd.DataFrame, window: int = 5) -> List[Tuple[int, float]]:
    """Find swing low points. Returns [(index_position, price), ...]"""
    lows = []
    data = df.reset_index(drop=True)
    for i in range(window, len(data) - window):
        is_low = True
        for j in range(1, window + 1):
            if data["low"].iloc[i] >= data["low"].iloc[i - j] or \
               data["low"].iloc[i] >= data["low"].iloc[i + j]:
                is_low = False
                break
        if is_low:
            lows.append((i, data["low"].iloc[i]))
    return lows


def _price_tolerance(price: float, pct: float = 0.003) -> float:
    """Calculate tolerance for price comparison (default 0.3%)."""
    return abs(price * pct)


# ── Double Top ─────────────────────────────────────────────────────────

def _detect_double_top(
    df: pd.DataFrame,
    swing_highs: List[Tuple[int, float]],
    swing_lows: List[Tuple[int, float]],
) -> Optional[ChartPattern]:
    """
    Double Top: Two peaks at approximately the same level with a valley between.
    Bearish reversal pattern.
    """
    if len(swing_highs) < 2:
        return None

    data = df.reset_index(drop=True)

    # Check last two swing highs
    for i in range(len(swing_highs) - 1, 0, -1):
        h2_idx, h2_price = swing_highs[i]
        h1_idx, h1_price = swing_highs[i - 1]

        # Peaks should be at similar levels (within 0.5%)
        tol = _price_tolerance(h1_price, 0.005)
        if abs(h2_price - h1_price) > tol:
            continue

        # There should be a meaningful dip between them
        if h2_idx - h1_idx < 5:
            continue

        # Find the lowest point between the two peaks (neckline)
        between = data.iloc[h1_idx:h2_idx + 1]
        neckline = between["low"].min()

        # The dip should be meaningful (at least 30% of the pattern height)
        pattern_height = max(h1_price, h2_price) - neckline
        if pattern_height < _price_tolerance(h1_price, 0.005):
            continue

        # Current price should be near or below the neckline for confirmation
        current_price = data["close"].iloc[-1]
        target = neckline - pattern_height

        confidence = 60.0
        # Bonus if price broke below neckline
        if current_price < neckline:
            confidence += 20.0
        # Bonus if peaks are very close in price
        if abs(h2_price - h1_price) < tol * 0.5:
            confidence += 10.0

        return ChartPattern(
            name="DOUBLE_TOP",
            direction="bearish",
            confidence=min(confidence, 95.0),
            start_idx=h1_idx,
            end_idx=len(data) - 1,
            neckline=neckline,
            target=target,
            description=f"Doble Techo detectado en {h1_price:.5f}/{h2_price:.5f}. "
                        f"Linea de cuello: {neckline:.5f}. Objetivo: {target:.5f}",
        )

    return None


# ── Double Bottom ──────────────────────────────────────────────────────

def _detect_double_bottom(
    df: pd.DataFrame,
    swing_highs: List[Tuple[int, float]],
    swing_lows: List[Tuple[int, float]],
) -> Optional[ChartPattern]:
    """
    Double Bottom: Two valleys at approximately the same level with a peak between.
    Bullish reversal pattern.
    """
    if len(swing_lows) < 2:
        return None

    data = df.reset_index(drop=True)

    for i in range(len(swing_lows) - 1, 0, -1):
        l2_idx, l2_price = swing_lows[i]
        l1_idx, l1_price = swing_lows[i - 1]

        tol = _price_tolerance(l1_price, 0.005)
        if abs(l2_price - l1_price) > tol:
            continue

        if l2_idx - l1_idx < 5:
            continue

        between = data.iloc[l1_idx:l2_idx + 1]
        neckline = between["high"].max()

        pattern_height = neckline - min(l1_price, l2_price)
        if pattern_height < _price_tolerance(l1_price, 0.005):
            continue

        current_price = data["close"].iloc[-1]
        target = neckline + pattern_height

        confidence = 60.0
        if current_price > neckline:
            confidence += 20.0
        if abs(l2_price - l1_price) < tol * 0.5:
            confidence += 10.0

        return ChartPattern(
            name="DOUBLE_BOTTOM",
            direction="bullish",
            confidence=min(confidence, 95.0),
            start_idx=l1_idx,
            end_idx=len(data) - 1,
            neckline=neckline,
            target=target,
            description=f"Doble Suelo detectado en {l1_price:.5f}/{l2_price:.5f}. "
                        f"Linea de cuello: {neckline:.5f}. Objetivo: {target:.5f}",
        )

    return None


# ── Head and Shoulders ─────────────────────────────────────────────────

def _detect_head_and_shoulders(
    df: pd.DataFrame,
    swing_highs: List[Tuple[int, float]],
    swing_lows: List[Tuple[int, float]],
) -> Optional[ChartPattern]:
    """
    Head & Shoulders: Three peaks where the middle one is the highest.
    Bearish reversal pattern.
    """
    if len(swing_highs) < 3:
        return None

    data = df.reset_index(drop=True)

    for i in range(len(swing_highs) - 1, 1, -1):
        rs_idx, rs_price = swing_highs[i]       # Right shoulder
        h_idx, h_price = swing_highs[i - 1]      # Head
        ls_idx, ls_price = swing_highs[i - 2]    # Left shoulder

        # Head must be higher than both shoulders
        if h_price <= rs_price or h_price <= ls_price:
            continue

        # Shoulders should be at similar levels (within 1%)
        tol = _price_tolerance(ls_price, 0.01)
        if abs(rs_price - ls_price) > tol:
            continue

        # Pattern should span reasonable distance
        if rs_idx - ls_idx < 10:
            continue

        # Find neckline (connect the two troughs between shoulders and head)
        trough1_data = data.iloc[ls_idx:h_idx + 1]
        trough2_data = data.iloc[h_idx:rs_idx + 1]
        trough1 = trough1_data["low"].min() if not trough1_data.empty else 0
        trough1_idx = trough1_data["low"].idxmin() if not trough1_data.empty else ls_idx
        trough2 = trough2_data["low"].min() if not trough2_data.empty else 0
        trough2_idx = trough2_data["low"].idxmin() if not trough2_data.empty else rs_idx
        neckline = (trough1 + trough2) / 2

        pattern_height = h_price - neckline
        if pattern_height < _price_tolerance(h_price, 0.005):
            continue

        target = neckline - pattern_height
        current_price = data["close"].iloc[-1]

        confidence = 65.0
        if current_price < neckline:
            confidence += 20.0
        if abs(rs_price - ls_price) < tol * 0.3:
            confidence += 10.0

        # Calculate neckline slope for type classification (Gráficas de Patrones.pdf)
        neckline_slope = (trough2 - trough1) / max(1, trough2_idx - trough1_idx)
        slope_pct = neckline_slope / neckline * 100 if neckline > 0 else 0

        # Classify neckline type
        if abs(slope_pct) < 0.5:  # Nearly flat
            neckline_type = 1  # Tipo 1: Plano
            type_desc = "neckline plano"
        elif neckline_slope > 0:  # Ascending
            neckline_type = 2  # Tipo 2: Ascendente (less bearish)
            type_desc = "neckline ascendente (menos bajista)"
            confidence -= 5  # Less reliable per course
        else:  # Descending
            neckline_type = 3  # Tipo 3: Descendente (most bearish, most reliable)
            type_desc = "neckline descendente (más bajista y confiable)"
            confidence += 5  # More reliable per course

        return ChartPattern(
            name=f"HEAD_AND_SHOULDERS_TYPE_{neckline_type}",
            direction="bearish",
            confidence=min(confidence, 95.0),
            start_idx=ls_idx,
            end_idx=len(data) - 1,
            neckline=neckline,
            target=target,
            description=f"Hombro-Cabeza-Hombro (Tipo {neckline_type}, {type_desc}): "
                        f"Cabeza {h_price:.5f}, "
                        f"Hombros {ls_price:.5f}/{rs_price:.5f}. "
                        f"Cuello: {neckline:.5f}. Objetivo: {target:.5f}",
        )

    return None


# ── Inverse Head and Shoulders ─────────────────────────────────────────

def _detect_inverse_head_and_shoulders(
    df: pd.DataFrame,
    swing_highs: List[Tuple[int, float]],
    swing_lows: List[Tuple[int, float]],
) -> Optional[ChartPattern]:
    """
    Inverse H&S: Three troughs where the middle is the lowest.
    Bullish reversal pattern.
    """
    if len(swing_lows) < 3:
        return None

    data = df.reset_index(drop=True)

    for i in range(len(swing_lows) - 1, 1, -1):
        rs_idx, rs_price = swing_lows[i]
        h_idx, h_price = swing_lows[i - 1]
        ls_idx, ls_price = swing_lows[i - 2]

        if h_price >= rs_price or h_price >= ls_price:
            continue

        tol = _price_tolerance(ls_price, 0.01)
        if abs(rs_price - ls_price) > tol:
            continue

        if rs_idx - ls_idx < 10:
            continue

        peak1_data = data.iloc[ls_idx:h_idx + 1]
        peak2_data = data.iloc[h_idx:rs_idx + 1]
        peak1 = peak1_data["high"].max() if not peak1_data.empty else 0
        peak1_idx = peak1_data["high"].idxmax() if not peak1_data.empty else ls_idx
        peak2 = peak2_data["high"].max() if not peak2_data.empty else 0
        peak2_idx = peak2_data["high"].idxmax() if not peak2_data.empty else rs_idx
        neckline = (peak1 + peak2) / 2

        pattern_height = neckline - h_price
        if pattern_height < _price_tolerance(h_price, 0.005):
            continue

        target = neckline + pattern_height
        current_price = data["close"].iloc[-1]

        confidence = 65.0
        if current_price > neckline:
            confidence += 20.0
        if abs(rs_price - ls_price) < tol * 0.3:
            confidence += 10.0

        # Calculate neckline slope for type classification (Gráficas de Patrones.pdf)
        neckline_slope = (peak2 - peak1) / max(1, peak2_idx - peak1_idx)
        slope_pct = neckline_slope / neckline * 100 if neckline > 0 else 0

        # Classify neckline type (inverted logic for Inverse H&S)
        if abs(slope_pct) < 0.5:  # Nearly flat
            neckline_type = 1  # Tipo 1: Plano
            type_desc = "neckline plano"
        elif neckline_slope > 0:  # Ascending - more bullish and reliable for inverse
            neckline_type = 2  # Tipo 2: Ascendente (more bullish)
            type_desc = "neckline ascendente (más alcista y confiable)"
            confidence += 5  # More reliable per course
        else:  # Descending - less bullish for inverse
            neckline_type = 3  # Tipo 3: Descendente (less bullish)
            type_desc = "neckline descendente (menos alcista)"
            confidence -= 5  # Less reliable per course

        return ChartPattern(
            name=f"INVERSE_HEAD_AND_SHOULDERS_TYPE_{neckline_type}",
            direction="bullish",
            confidence=min(confidence, 95.0),
            start_idx=ls_idx,
            end_idx=len(data) - 1,
            neckline=neckline,
            target=target,
            description=f"HCH Invertido (Tipo {neckline_type}, {type_desc}): "
                        f"Cabeza {h_price:.5f}, "
                        f"Hombros {ls_price:.5f}/{rs_price:.5f}. "
                        f"Cuello: {neckline:.5f}. Objetivo: {target:.5f}",
        )

    return None


# ── Ascending Triangle ─────────────────────────────────────────────────

def _detect_ascending_triangle(
    df: pd.DataFrame,
    swing_highs: List[Tuple[int, float]],
    swing_lows: List[Tuple[int, float]],
) -> Optional[ChartPattern]:
    """
    Ascending Triangle: Flat resistance + rising support (higher lows).
    Bullish continuation pattern.
    """
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return None

    data = df.reset_index(drop=True)
    recent_highs = swing_highs[-3:] if len(swing_highs) >= 3 else swing_highs[-2:]
    recent_lows = swing_lows[-3:] if len(swing_lows) >= 3 else swing_lows[-2:]

    # Check flat resistance (highs at similar levels)
    high_prices = [h[1] for h in recent_highs]
    high_range = max(high_prices) - min(high_prices)
    avg_high = sum(high_prices) / len(high_prices)

    if high_range > _price_tolerance(avg_high, 0.005):
        return None

    # Check rising lows (each low higher than the previous)
    low_prices = [l[1] for l in recent_lows]
    rising = all(low_prices[i] < low_prices[i + 1] for i in range(len(low_prices) - 1))
    if not rising:
        return None

    neckline = avg_high  # Resistance line
    pattern_height = neckline - min(low_prices)
    target = neckline + pattern_height

    confidence = 65.0
    current_price = data["close"].iloc[-1]
    if current_price > neckline:
        confidence += 20.0
    if len(recent_highs) >= 3:
        confidence += 5.0

    return ChartPattern(
        name="ASCENDING_TRIANGLE",
        direction="bullish",
        confidence=min(confidence, 95.0),
        start_idx=min(recent_highs[0][0], recent_lows[0][0]),
        end_idx=len(data) - 1,
        neckline=neckline,
        target=target,
        description=f"Triangulo Ascendente: Resistencia plana en {neckline:.5f}, "
                    f"soportes ascendentes. Objetivo: {target:.5f}",
    )


# ── Descending Triangle ───────────────────────────────────────────────

def _detect_descending_triangle(
    df: pd.DataFrame,
    swing_highs: List[Tuple[int, float]],
    swing_lows: List[Tuple[int, float]],
) -> Optional[ChartPattern]:
    """
    Descending Triangle: Flat support + falling resistance (lower highs).
    Bearish continuation pattern.
    """
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return None

    data = df.reset_index(drop=True)
    recent_highs = swing_highs[-3:] if len(swing_highs) >= 3 else swing_highs[-2:]
    recent_lows = swing_lows[-3:] if len(swing_lows) >= 3 else swing_lows[-2:]

    # Check flat support
    low_prices = [l[1] for l in recent_lows]
    low_range = max(low_prices) - min(low_prices)
    avg_low = sum(low_prices) / len(low_prices)

    if low_range > _price_tolerance(avg_low, 0.005):
        return None

    # Check falling highs
    high_prices = [h[1] for h in recent_highs]
    falling = all(high_prices[i] > high_prices[i + 1] for i in range(len(high_prices) - 1))
    if not falling:
        return None

    neckline = avg_low
    pattern_height = max(high_prices) - neckline
    target = neckline - pattern_height

    confidence = 65.0
    current_price = data["close"].iloc[-1]
    if current_price < neckline:
        confidence += 20.0
    if len(recent_lows) >= 3:
        confidence += 5.0

    return ChartPattern(
        name="DESCENDING_TRIANGLE",
        direction="bearish",
        confidence=min(confidence, 95.0),
        start_idx=min(recent_highs[0][0], recent_lows[0][0]),
        end_idx=len(data) - 1,
        neckline=neckline,
        target=target,
        description=f"Triangulo Descendente: Soporte plano en {neckline:.5f}, "
                    f"resistencias descendentes. Objetivo: {target:.5f}",
    )


# ── Symmetrical Triangle ──────────────────────────────────────────────

def _detect_symmetrical_triangle(
    df: pd.DataFrame,
    swing_highs: List[Tuple[int, float]],
    swing_lows: List[Tuple[int, float]],
) -> Optional[ChartPattern]:
    """
    Symmetrical Triangle: Converging trendlines (lower highs + higher lows).
    Can break either way — direction = trend before the pattern.
    """
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return None

    data = df.reset_index(drop=True)
    recent_highs = swing_highs[-3:] if len(swing_highs) >= 3 else swing_highs[-2:]
    recent_lows = swing_lows[-3:] if len(swing_lows) >= 3 else swing_lows[-2:]

    high_prices = [h[1] for h in recent_highs]
    low_prices = [l[1] for l in recent_lows]

    # Lower highs
    lower_highs = all(high_prices[i] > high_prices[i + 1] for i in range(len(high_prices) - 1))
    # Higher lows
    higher_lows = all(low_prices[i] < low_prices[i + 1] for i in range(len(low_prices) - 1))

    if not (lower_highs and higher_lows):
        return None

    # Determine likely breakout direction from prior trend
    ema_20 = data["close"].ewm(span=20).mean()
    ema_50 = data["close"].ewm(span=50).mean()
    start_idx = min(recent_highs[0][0], recent_lows[0][0])

    if start_idx > 0:
        prior_trend = "bullish" if ema_20.iloc[start_idx] > ema_50.iloc[start_idx] else "bearish"
    else:
        prior_trend = "bullish"

    midpoint = (high_prices[-1] + low_prices[-1]) / 2
    pattern_height = high_prices[0] - low_prices[0]
    target = midpoint + pattern_height if prior_trend == "bullish" else midpoint - pattern_height

    confidence = 55.0
    if len(recent_highs) >= 3 and len(recent_lows) >= 3:
        confidence += 10.0

    # Determine triangle type: continuation vs reversal (Gráficas de Patrones.pdf)
    # Estimate the apex (convergence point) from the trendlines
    end_idx = len(data) - 1
    high_idx_span = recent_highs[-1][0] - recent_highs[0][0]
    low_idx_span = recent_lows[-1][0] - recent_lows[0][0]
    avg_span = max(1, (high_idx_span + low_idx_span) / 2)
    # How far into the triangle has the pattern developed?
    triangle_progress = (end_idx - start_idx) / max(1, avg_span) if avg_span > 0 else 0

    direction_es = "alcista" if prior_trend == "bullish" else "bajista"

    if triangle_progress > 0.67:  # Past 2/3 - more likely reversal
        pattern_name = "REVERSAL_TRIANGLE"
        description = (f"Triángulo de reversión {direction_es} — se desarrolló más allá "
                       f"de 2/3 del patrón, sugiere cambio de tendencia. "
                       f"Objetivo: {target:.5f}")
    else:  # Breaks around 2/3 - continuation
        pattern_name = "CONTINUATION_TRIANGLE"
        description = (f"Triángulo de continuación {direction_es} — ruptura en ~2/3 "
                       f"del patrón, confirma tendencia dominante. "
                       f"Objetivo: {target:.5f}")

    return ChartPattern(
        name=pattern_name,
        direction=prior_trend,
        confidence=min(confidence, 90.0),
        start_idx=start_idx,
        end_idx=end_idx,
        neckline=midpoint,
        target=target,
        description=description,
    )


# ── Rising Wedge ──────────────────────────────────────────────────────

def _detect_rising_wedge(
    df: pd.DataFrame,
    swing_highs: List[Tuple[int, float]],
    swing_lows: List[Tuple[int, float]],
) -> Optional[ChartPattern]:
    """
    Rising Wedge: Both highs and lows rising, but highs converging toward lows.
    Bearish reversal pattern.
    """
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return None

    data = df.reset_index(drop=True)
    recent_highs = swing_highs[-3:] if len(swing_highs) >= 3 else swing_highs[-2:]
    recent_lows = swing_lows[-3:] if len(swing_lows) >= 3 else swing_lows[-2:]

    high_prices = [h[1] for h in recent_highs]
    low_prices = [l[1] for l in recent_lows]

    # Both rising
    rising_highs = all(high_prices[i] < high_prices[i + 1] for i in range(len(high_prices) - 1))
    rising_lows = all(low_prices[i] < low_prices[i + 1] for i in range(len(low_prices) - 1))

    if not (rising_highs and rising_lows):
        return None

    # Converging: the rate of rise for lows is faster than highs
    if len(high_prices) >= 2 and len(low_prices) >= 2:
        high_rise = high_prices[-1] - high_prices[0]
        low_rise = low_prices[-1] - low_prices[0]
        # Lows rising faster means convergence
        if low_rise <= high_rise:
            return None

    neckline = low_prices[-1]
    # TradingLab AT Básico: wedge target = start of the wedge (el inicio de la cuña)
    target = low_prices[0]

    confidence = 60.0
    current_price = data["close"].iloc[-1]
    if current_price < neckline:
        confidence += 20.0

    return ChartPattern(
        name="RISING_WEDGE",
        direction="bearish",
        confidence=min(confidence, 90.0),
        start_idx=min(recent_highs[0][0], recent_lows[0][0]),
        end_idx=len(data) - 1,
        neckline=neckline,
        target=target,
        description=f"Cuna Ascendente: Maximos y minimos subiendo con convergencia. "
                    f"Patron bajista. Objetivo (inicio de cuna): {target:.5f}",
    )


# ── Falling Wedge ─────────────────────────────────────────────────────

def _detect_falling_wedge(
    df: pd.DataFrame,
    swing_highs: List[Tuple[int, float]],
    swing_lows: List[Tuple[int, float]],
) -> Optional[ChartPattern]:
    """
    Falling Wedge: Both highs and lows falling, but lows converging toward highs.
    Bullish reversal pattern.
    """
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return None

    data = df.reset_index(drop=True)
    recent_highs = swing_highs[-3:] if len(swing_highs) >= 3 else swing_highs[-2:]
    recent_lows = swing_lows[-3:] if len(swing_lows) >= 3 else swing_lows[-2:]

    high_prices = [h[1] for h in recent_highs]
    low_prices = [l[1] for l in recent_lows]

    # Both falling
    falling_highs = all(high_prices[i] > high_prices[i + 1] for i in range(len(high_prices) - 1))
    falling_lows = all(low_prices[i] > low_prices[i + 1] for i in range(len(low_prices) - 1))

    if not (falling_highs and falling_lows):
        return None

    # Converging: highs falling faster than lows
    if len(high_prices) >= 2 and len(low_prices) >= 2:
        high_drop = high_prices[0] - high_prices[-1]
        low_drop = low_prices[0] - low_prices[-1]
        if high_drop <= low_drop:
            return None

    neckline = high_prices[-1]
    # TradingLab AT Básico: wedge target = start of the wedge (el inicio de la cuña)
    target = high_prices[0]

    confidence = 60.0
    current_price = data["close"].iloc[-1]
    if current_price > neckline:
        confidence += 20.0

    return ChartPattern(
        name="FALLING_WEDGE",
        direction="bullish",
        confidence=min(confidence, 90.0),
        start_idx=min(recent_highs[0][0], recent_lows[0][0]),
        end_idx=len(data) - 1,
        neckline=neckline,
        target=target,
        description=f"Cuna Descendente: Maximos y minimos bajando con convergencia. "
                    f"Patron alcista. Objetivo (inicio de cuna): {target:.5f}",
    )


# ── Bull Flag ──────────────────────────────────────────────────────────

def _detect_bull_flag(
    df: pd.DataFrame,
    swing_highs: List[Tuple[int, float]],
    swing_lows: List[Tuple[int, float]],
) -> Optional[ChartPattern]:
    """
    Bull Flag: Strong upward move (pole) followed by slight downward consolidation (flag).
    Bullish continuation pattern.
    """
    if len(df) < 20:
        return None

    data = df.reset_index(drop=True)
    n = len(data)

    # Look for a strong move up (pole) in the first part
    pole_end = int(n * 0.6)
    pole_data = data.iloc[:pole_end]

    if pole_data.empty:
        return None

    pole_low = pole_data["low"].min()
    pole_high = pole_data["high"].max()
    pole_range = pole_high - pole_low

    if pole_range < _price_tolerance(pole_high, 0.01):
        return None

    # The pole should be predominantly bullish
    pole_start_price = pole_data["close"].iloc[0]
    pole_end_price = pole_data["close"].iloc[-1]
    if pole_end_price <= pole_start_price:
        return None

    # Flag: consolidation after the pole (slight pullback)
    flag_data = data.iloc[pole_end:]
    if flag_data.empty or len(flag_data) < 3:
        return None

    flag_high = flag_data["high"].max()
    flag_low = flag_data["low"].min()
    flag_range = flag_high - flag_low

    # Flag should be smaller than pole (less than 50% retracement)
    if flag_range > pole_range * 0.5:
        return None

    # Flag should trend slightly down or sideways
    flag_start = flag_data["close"].iloc[0]
    flag_end = flag_data["close"].iloc[-1]
    if flag_end > flag_start + pole_range * 0.1:
        return None

    neckline = flag_high
    target = neckline + pole_range

    confidence = 60.0
    if flag_range < pole_range * 0.3:
        confidence += 10.0
    current_price = data["close"].iloc[-1]
    if current_price > neckline:
        confidence += 15.0

    return ChartPattern(
        name="BULL_FLAG",
        direction="bullish",
        confidence=min(confidence, 90.0),
        start_idx=0,
        end_idx=n - 1,
        neckline=neckline,
        target=target,
        description=f"Bandera Alcista: Asta de {pole_range:.5f} pips seguida de consolidacion. "
                    f"Objetivo: {target:.5f}",
    )


# ── Bear Flag ──────────────────────────────────────────────────────────

def _detect_bear_flag(
    df: pd.DataFrame,
    swing_highs: List[Tuple[int, float]],
    swing_lows: List[Tuple[int, float]],
) -> Optional[ChartPattern]:
    """
    Bear Flag: Strong downward move (pole) followed by slight upward consolidation (flag).
    Bearish continuation pattern.
    """
    if len(df) < 20:
        return None

    data = df.reset_index(drop=True)
    n = len(data)

    pole_end = int(n * 0.6)
    pole_data = data.iloc[:pole_end]

    if pole_data.empty:
        return None

    pole_low = pole_data["low"].min()
    pole_high = pole_data["high"].max()
    pole_range = pole_high - pole_low

    if pole_range < _price_tolerance(pole_high, 0.01):
        return None

    # Pole should be predominantly bearish
    pole_start_price = pole_data["close"].iloc[0]
    pole_end_price = pole_data["close"].iloc[-1]
    if pole_end_price >= pole_start_price:
        return None

    # Flag: slight upward consolidation
    flag_data = data.iloc[pole_end:]
    if flag_data.empty or len(flag_data) < 3:
        return None

    flag_high = flag_data["high"].max()
    flag_low = flag_data["low"].min()
    flag_range = flag_high - flag_low

    if flag_range > pole_range * 0.5:
        return None

    flag_start = flag_data["close"].iloc[0]
    flag_end = flag_data["close"].iloc[-1]
    if flag_end < flag_start - pole_range * 0.1:
        return None

    neckline = flag_low
    target = neckline - pole_range

    confidence = 60.0
    if flag_range < pole_range * 0.3:
        confidence += 10.0
    current_price = data["close"].iloc[-1]
    if current_price < neckline:
        confidence += 15.0

    return ChartPattern(
        name="BEAR_FLAG",
        direction="bearish",
        confidence=min(confidence, 90.0),
        start_idx=0,
        end_idx=n - 1,
        neckline=neckline,
        target=target,
        description=f"Bandera Bajista: Asta de {pole_range:.5f} pips seguida de consolidacion alcista. "
                    f"Objetivo: {target:.5f}",
    )


# ── Cup and Handle ────────────────────────────────────────────────────

def _detect_cup_and_handle(
    df: pd.DataFrame,
    swing_highs: List[Tuple[int, float]],
    swing_lows: List[Tuple[int, float]],
) -> Optional[ChartPattern]:
    """
    Cup & Handle: U-shaped recovery followed by small consolidation.
    Bullish continuation pattern.
    """
    if len(df) < 30 or len(swing_highs) < 2 or len(swing_lows) < 1:
        return None

    data = df.reset_index(drop=True)
    n = len(data)

    # Look for a U shape: price drops, forms a rounded bottom, recovers
    # Use the last 60-80% of data for the cup
    cup_size = int(n * 0.7)
    cup_data = data.iloc[:cup_size]

    if len(cup_data) < 20:
        return None

    # Cup rim: the starting high
    cup_start_high = cup_data["high"].iloc[:5].max()
    # Cup bottom
    cup_bottom_idx = cup_data["low"].idxmin()
    cup_bottom = cup_data["low"].min()
    # Cup end: should recover close to the starting high
    cup_end_high = cup_data["high"].iloc[-5:].max()

    # Cup should be meaningful
    cup_depth = cup_start_high - cup_bottom
    if cup_depth < _price_tolerance(cup_start_high, 0.01):
        return None

    # Recovery should be at least 80% of the cup depth
    recovery = cup_end_high - cup_bottom
    if recovery < cup_depth * 0.8:
        return None

    # Handle: small consolidation after the cup
    handle_data = data.iloc[cup_size:]
    if handle_data.empty or len(handle_data) < 3:
        return None

    handle_low = handle_data["low"].min()
    handle_depth = cup_end_high - handle_low

    # Handle should be shallow (less than 50% of cup depth)
    if handle_depth > cup_depth * 0.5:
        return None

    neckline = max(cup_start_high, cup_end_high)
    target = neckline + cup_depth

    confidence = 60.0
    current_price = data["close"].iloc[-1]
    if current_price > neckline:
        confidence += 20.0
    # Bonus for round bottom shape
    mid_idx = (0 + cup_size) // 2
    if cup_bottom_idx > n * 0.2 and cup_bottom_idx < n * 0.6:
        confidence += 10.0

    return ChartPattern(
        name="CUP_AND_HANDLE",
        direction="bullish",
        confidence=min(confidence, 90.0),
        start_idx=0,
        end_idx=n - 1,
        neckline=neckline,
        target=target,
        description=f"Copa y Asa: Copa de {cup_depth:.5f} de profundidad con asa pequeña. "
                    f"Cuello: {neckline:.5f}. Objetivo: {target:.5f}",
    )


# ── Ascending Channel (from Gráficas de Patrones PDF) ────────────────

def _detect_ascending_channel(
    df: pd.DataFrame,
    swing_highs: List[Tuple[int, float]],
    swing_lows: List[Tuple[int, float]],
) -> Optional[ChartPattern]:
    """
    Ascending Channel (Canal Ascendente): Parallel rising trendlines.
    Price moves between rising support and rising resistance.
    Bearish breakout expected (price breaks lower trendline).
    """
    if len(swing_highs) < 3 or len(swing_lows) < 3:
        return None

    data = df.reset_index(drop=True)
    recent_highs = swing_highs[-4:] if len(swing_highs) >= 4 else swing_highs[-3:]
    recent_lows = swing_lows[-4:] if len(swing_lows) >= 4 else swing_lows[-3:]

    high_prices = [h[1] for h in recent_highs]
    low_prices = [l[1] for l in recent_lows]

    # Both highs and lows should be rising
    rising_highs = all(high_prices[i] < high_prices[i + 1] for i in range(len(high_prices) - 1))
    rising_lows = all(low_prices[i] < low_prices[i + 1] for i in range(len(low_prices) - 1))

    if not (rising_highs and rising_lows):
        return None

    # Lines should be roughly parallel (similar slope)
    high_slope = (high_prices[-1] - high_prices[0]) / max(1, recent_highs[-1][0] - recent_highs[0][0])
    low_slope = (low_prices[-1] - low_prices[0]) / max(1, recent_lows[-1][0] - recent_lows[0][0])

    if high_slope == 0 or low_slope == 0:
        return None

    slope_ratio = min(high_slope, low_slope) / max(high_slope, low_slope) if max(high_slope, low_slope) > 0 else 0
    if slope_ratio < 0.4:  # Lines must be somewhat parallel
        return None

    neckline = low_prices[-1]  # Lower trendline (support to break)
    # TradingLab AT Básico: channel target = start of the channel (el inicio del canal)
    target = low_prices[0]

    confidence = 60.0
    if len(recent_highs) >= 4 and len(recent_lows) >= 4:
        confidence += 10.0
    if slope_ratio > 0.7:
        confidence += 10.0

    return ChartPattern(
        name="ASCENDING_CHANNEL",
        direction="bearish",
        confidence=min(confidence, 90.0),
        start_idx=min(recent_highs[0][0], recent_lows[0][0]),
        end_idx=len(data) - 1,
        neckline=neckline,
        target=target,
        description=f"Canal Ascendente: Lineas paralelas ascendentes. "
                    f"Soporte: {neckline:.5f}. Objetivo (inicio canal): {target:.5f}",
    )


# ── Descending Channel (from Gráficas de Patrones PDF) ───────────────

def _detect_descending_channel(
    df: pd.DataFrame,
    swing_highs: List[Tuple[int, float]],
    swing_lows: List[Tuple[int, float]],
) -> Optional[ChartPattern]:
    """
    Descending Channel (Canal Descendente): Parallel falling trendlines.
    Bullish breakout expected (price breaks upper trendline).
    """
    if len(swing_highs) < 3 or len(swing_lows) < 3:
        return None

    data = df.reset_index(drop=True)
    recent_highs = swing_highs[-4:] if len(swing_highs) >= 4 else swing_highs[-3:]
    recent_lows = swing_lows[-4:] if len(swing_lows) >= 4 else swing_lows[-3:]

    high_prices = [h[1] for h in recent_highs]
    low_prices = [l[1] for l in recent_lows]

    # Both should be falling
    falling_highs = all(high_prices[i] > high_prices[i + 1] for i in range(len(high_prices) - 1))
    falling_lows = all(low_prices[i] > low_prices[i + 1] for i in range(len(low_prices) - 1))

    if not (falling_highs and falling_lows):
        return None

    # Parallel check
    high_slope = abs(high_prices[-1] - high_prices[0]) / max(1, recent_highs[-1][0] - recent_highs[0][0])
    low_slope = abs(low_prices[-1] - low_prices[0]) / max(1, recent_lows[-1][0] - recent_lows[0][0])

    if high_slope == 0 or low_slope == 0:
        return None

    slope_ratio = min(high_slope, low_slope) / max(high_slope, low_slope) if max(high_slope, low_slope) > 0 else 0
    if slope_ratio < 0.4:
        return None

    neckline = high_prices[-1]  # Upper trendline (resistance to break)
    # TradingLab AT Básico: channel target = start of the channel (el inicio del canal)
    target = high_prices[0]

    confidence = 60.0
    if len(recent_highs) >= 4 and len(recent_lows) >= 4:
        confidence += 10.0
    if slope_ratio > 0.7:
        confidence += 10.0

    return ChartPattern(
        name="DESCENDING_CHANNEL",
        direction="bullish",
        confidence=min(confidence, 90.0),
        start_idx=min(recent_highs[0][0], recent_lows[0][0]),
        end_idx=len(data) - 1,
        neckline=neckline,
        target=target,
        description=f"Canal Descendente: Lineas paralelas descendentes. "
                    f"Resistencia: {neckline:.5f}. Objetivo (inicio canal): {target:.5f}",
    )


def get_pattern_names() -> List[str]:
    """Return list of all detectable pattern names."""
    return [
        "DOUBLE_TOP", "DOUBLE_BOTTOM",
        "HEAD_AND_SHOULDERS_TYPE_1", "HEAD_AND_SHOULDERS_TYPE_2", "HEAD_AND_SHOULDERS_TYPE_3",
        "INVERSE_HEAD_AND_SHOULDERS_TYPE_1", "INVERSE_HEAD_AND_SHOULDERS_TYPE_2", "INVERSE_HEAD_AND_SHOULDERS_TYPE_3",
        "ASCENDING_TRIANGLE", "DESCENDING_TRIANGLE",
        "CONTINUATION_TRIANGLE", "REVERSAL_TRIANGLE",
        "RISING_WEDGE", "FALLING_WEDGE",
        "BULL_FLAG", "BEAR_FLAG",
        "CUP_AND_HANDLE",
        "ASCENDING_CHANNEL", "DESCENDING_CHANNEL",
    ]
