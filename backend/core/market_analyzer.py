"""
NeonTrade AI - Market Analyzer
Multi-timeframe analysis engine following Trading Plan methodology.

HTF Analysis (Weekly/Daily):
1. Check weekly/monthly for important levels
2. Detect weekly trend
3. Daily: adjust S/R, confirm/deny weekly analysis
4. Check daily overbought/oversold + acceleration/deceleration
5. Relate daily chart with Elliott Wave theory

LTF Analysis (4H, 1H, 15m, 5m, 2m):
1. 4H -> determine which strategy can be executed
2. 1H -> profile structure, find support/confirmation zones
3. 15m -> adjust patterns, hourly levels, intraday zones
4. 5m/2m -> find optimal entry execution
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import pandas as pd
import numpy as np
from loguru import logger

from core.chart_patterns import detect_chart_patterns, ChartPattern


class Trend(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGING = "ranging"


class MarketCondition(Enum):
    OVERBOUGHT = "overbought"
    OVERSOLD = "oversold"
    NEUTRAL = "neutral"
    ACCELERATING = "accelerating"
    DECELERATING = "decelerating"


@dataclass
class AnalysisResult:
    """Complete analysis for an instrument."""
    instrument: str
    htf_trend: Trend
    htf_condition: MarketCondition
    ltf_trend: Trend
    htf_ltf_convergence: bool  # True if HTF and LTF agree
    key_levels: Dict[str, List[float]]  # supports, resistances, FVGs
    ema_values: Dict[str, float]
    fibonacci_levels: Dict[str, float]
    candlestick_patterns: List[str]
    chart_patterns: List[Dict] = field(default_factory=list)  # Advanced chart patterns
    # MACD values per timeframe (from scalping workshop)
    macd_values: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # SMA200 per timeframe (from scalping workshop - key for H1)
    sma_values: Dict[str, float] = field(default_factory=dict)
    # RSI per timeframe (for divergence detection in Black strategy)
    rsi_values: Dict[str, float] = field(default_factory=dict)
    # RSI divergence detection (required for Black strategy)
    rsi_divergence: Optional[str] = None  # "bullish", "bearish", or None
    # Order Blocks (from SMC workshop)
    order_blocks: List[Dict] = field(default_factory=list)
    # BOS/CHOCH detection (from SMC workshop)
    structure_breaks: List[Dict] = field(default_factory=list)
    # Elliott Wave estimate
    elliott_wave: Optional[str] = None
    score: float = 0.0  # Overall trade quality score (0-100)


class MarketAnalyzer:
    """Multi-timeframe market analysis engine."""

    def __init__(self, broker_client):
        self.broker = broker_client

    async def full_analysis(self, instrument: str) -> AnalysisResult:
        """
        Run complete multi-timeframe analysis on an instrument.
        This is the main analysis pipeline from the Trading Plan.
        """
        # Step 1: Get candle data for all timeframes
        candles = {}
        timeframes = {
            "W": 52,     # 1 year of weekly
            "D": 120,    # ~6 months daily
            "H4": 200,   # ~33 days of 4H
            "H1": 200,   # ~8 days of 1H
            "M15": 200,  # ~2 days of 15m
            "M5": 200,   # ~17 hours of 5m
        }

        for tf, count in timeframes.items():
            try:
                raw = await self.broker.get_candles(instrument, tf, count)
                candles[tf] = self._candles_to_dataframe(raw)
            except Exception as e:
                logger.error(f"Failed to get {tf} candles for {instrument}: {e}")
                candles[tf] = pd.DataFrame()

        # Step 2: HTF Analysis
        htf_trend = self._detect_trend(candles.get("W", pd.DataFrame()))
        htf_condition = self._detect_condition(candles.get("D", pd.DataFrame()))

        # Step 3: LTF Analysis
        ltf_trend = self._detect_trend(candles.get("H1", pd.DataFrame()))

        # Step 4: Key levels
        key_levels = self._find_key_levels(candles)

        # Step 5: EMAs
        ema_values = self._calculate_emas(candles)

        # Step 6: Fibonacci
        fib_levels = self._calculate_fibonacci(candles.get("D", pd.DataFrame()))

        # Step 7: Candlestick patterns (all from Formación de Velas PDF)
        patterns = self._detect_candlestick_patterns(candles.get("H1", pd.DataFrame()))

        # Step 7b: Advanced chart patterns
        chart_pats = []
        try:
            h4_df = candles.get("H4", pd.DataFrame())
            detected = detect_chart_patterns(h4_df, lookback=100)
            chart_pats = [
                {
                    "name": p.name,
                    "direction": p.direction,
                    "confidence": p.confidence,
                    "neckline": p.neckline,
                    "target": p.target,
                    "description": p.description,
                }
                for p in detected
            ]
        except Exception as e:
            logger.debug(f"Chart pattern detection failed for {instrument}: {e}")

        # Step 8: MACD (from scalping workshop - H1, M15, M5)
        macd_values = {}
        for tf in ("H1", "M15", "M5"):
            df = candles.get(tf, pd.DataFrame())
            if not df.empty:
                macd_data = self._calculate_macd(df)
                if macd_data:
                    macd_values[tf] = macd_data

        # Step 9: SMA200 (from scalping workshop - critical on H1)
        sma_values = {}
        for tf in ("H1", "D"):
            df = candles.get(tf, pd.DataFrame())
            if not df.empty and len(df) >= 200:
                sma200 = df["close"].rolling(200).mean()
                if not sma200.empty and not pd.isna(sma200.iloc[-1]):
                    sma_values[f"SMA_{tf}_200"] = float(sma200.iloc[-1])

        # Step 10: RSI per timeframe + divergence detection
        rsi_values = {}
        for tf in ("D", "H4", "H1"):
            df = candles.get(tf, pd.DataFrame())
            if not df.empty:
                rsi = self._calculate_rsi(df)
                if rsi is not None:
                    rsi_values[tf] = float(rsi)

        # RSI divergence on H4 (required for Black strategy)
        rsi_divergence = self._detect_rsi_divergence(
            candles.get("H4", pd.DataFrame())
        )

        # Step 11: Order Blocks (from SMC workshop)
        order_blocks = self._detect_order_blocks(candles.get("H1", pd.DataFrame()))

        # Step 12: BOS/CHOCH (from SMC workshop)
        structure_breaks = self._detect_structure_breaks(
            candles.get("H1", pd.DataFrame())
        )

        # Step 13: HTF/LTF convergence
        convergence = htf_trend == ltf_trend

        # Step 14: Score
        score = self._calculate_trade_score(
            htf_trend, ltf_trend, convergence, htf_condition, patterns, chart_pats
        )

        return AnalysisResult(
            instrument=instrument,
            htf_trend=htf_trend,
            htf_condition=htf_condition,
            ltf_trend=ltf_trend,
            htf_ltf_convergence=convergence,
            key_levels=key_levels,
            ema_values=ema_values,
            fibonacci_levels=fib_levels,
            candlestick_patterns=patterns,
            chart_patterns=chart_pats,
            macd_values=macd_values,
            sma_values=sma_values,
            rsi_values=rsi_values,
            rsi_divergence=rsi_divergence,
            order_blocks=order_blocks,
            structure_breaks=structure_breaks,
            score=score,
        )

    def _candles_to_dataframe(self, candles) -> pd.DataFrame:
        """Convert CandleData objects (or legacy dicts) to pandas DataFrame."""
        if not candles:
            return pd.DataFrame()

        rows = []
        for c in candles:
            # Support both CandleData dataclass and legacy dict format
            if hasattr(c, "open"):
                # CandleData dataclass from BaseBroker
                if not c.complete:
                    continue
                rows.append({
                    "time": pd.Timestamp(c.time),
                    "open": float(c.open),
                    "high": float(c.high),
                    "low": float(c.low),
                    "close": float(c.close),
                    "volume": int(c.volume),
                })
            else:
                # Legacy OANDA raw dict format
                if not c.get("complete", True):
                    continue
                mid = c.get("mid", {})
                rows.append({
                    "time": pd.Timestamp(c["time"]),
                    "open": float(mid.get("o", 0)),
                    "high": float(mid.get("h", 0)),
                    "low": float(mid.get("l", 0)),
                    "close": float(mid.get("c", 0)),
                    "volume": int(c.get("volume", 0)),
                })
        df = pd.DataFrame(rows)
        if not df.empty:
            df.set_index("time", inplace=True)
        return df

    def _detect_trend(self, df: pd.DataFrame) -> Trend:
        """Detect trend using EMA crossover and price structure."""
        if df.empty or len(df) < 50:
            return Trend.RANGING

        ema_20 = df["close"].ewm(span=20).mean()
        ema_50 = df["close"].ewm(span=50).mean()

        current_price = df["close"].iloc[-1]
        ema20_val = ema_20.iloc[-1]
        ema50_val = ema_50.iloc[-1]

        if current_price > ema20_val > ema50_val:
            return Trend.BULLISH
        elif current_price < ema20_val < ema50_val:
            return Trend.BEARISH
        return Trend.RANGING

    def _detect_condition(self, df: pd.DataFrame) -> MarketCondition:
        """Detect overbought/oversold using RSI-like calculation."""
        if df.empty or len(df) < 14:
            return MarketCondition.NEUTRAL

        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()

        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1]

        if current_rsi > 70:
            return MarketCondition.OVERBOUGHT
        elif current_rsi < 30:
            return MarketCondition.OVERSOLD
        return MarketCondition.NEUTRAL

    def _find_key_levels(self, candles: Dict[str, pd.DataFrame]) -> Dict[str, List[float]]:
        """Find support, resistance, and Fair Value Gap (FVG) levels."""
        levels: Dict[str, List[float]] = {
            "supports": [],
            "resistances": [],
            "fvg": [],
        }

        daily = candles.get("D", pd.DataFrame())
        if daily.empty:
            return levels

        # Find swing highs and lows from daily
        for i in range(2, len(daily) - 2):
            # Swing high
            if (daily["high"].iloc[i] > daily["high"].iloc[i-1] and
                daily["high"].iloc[i] > daily["high"].iloc[i-2] and
                daily["high"].iloc[i] > daily["high"].iloc[i+1] and
                daily["high"].iloc[i] > daily["high"].iloc[i+2]):
                levels["resistances"].append(daily["high"].iloc[i])

            # Swing low
            if (daily["low"].iloc[i] < daily["low"].iloc[i-1] and
                daily["low"].iloc[i] < daily["low"].iloc[i-2] and
                daily["low"].iloc[i] < daily["low"].iloc[i+1] and
                daily["low"].iloc[i] < daily["low"].iloc[i+2]):
                levels["supports"].append(daily["low"].iloc[i])

        # Find FVGs (Fair Value Gaps) from 1H
        h1 = candles.get("H1", pd.DataFrame())
        if not h1.empty:
            for i in range(2, len(h1)):
                # Bullish FVG: candle[i] low > candle[i-2] high
                if h1["low"].iloc[i] > h1["high"].iloc[i-2]:
                    fvg_mid = (h1["low"].iloc[i] + h1["high"].iloc[i-2]) / 2
                    levels["fvg"].append(fvg_mid)
                # Bearish FVG: candle[i] high < candle[i-2] low
                elif h1["high"].iloc[i] < h1["low"].iloc[i-2]:
                    fvg_mid = (h1["high"].iloc[i] + h1["low"].iloc[i-2]) / 2
                    levels["fvg"].append(fvg_mid)

        # Keep only recent levels
        levels["supports"] = sorted(levels["supports"])[-10:]
        levels["resistances"] = sorted(levels["resistances"])[-10:]
        levels["fvg"] = levels["fvg"][-20:]

        return levels

    def _calculate_emas(self, candles: Dict[str, pd.DataFrame]) -> Dict[str, float]:
        """Calculate EMA values for multiple timeframes."""
        emas = {}
        ema_configs = {
            "H4": [20, 50],
            "H1": [20, 50],
            "M5": [2, 5, 20],
        }

        for tf, periods in ema_configs.items():
            df = candles.get(tf, pd.DataFrame())
            if df.empty:
                continue
            for period in periods:
                key = f"EMA_{tf}_{period}"
                ema = df["close"].ewm(span=period).mean()
                if not ema.empty:
                    emas[key] = ema.iloc[-1]

        return emas

    def _calculate_fibonacci(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate Fibonacci retracement and extension levels from daily swing."""
        if df.empty or len(df) < 20:
            return {}

        recent = df.tail(60)
        swing_high = recent["high"].max()
        swing_low = recent["low"].min()
        diff = swing_high - swing_low

        return {
            "0.0": swing_high,
            "0.236": swing_high - diff * 0.236,
            "0.382": swing_high - diff * 0.382,
            "0.5": swing_high - diff * 0.5,
            "0.618": swing_high - diff * 0.618,
            "0.786": swing_high - diff * 0.786,
            "1.0": swing_low,
            "1.272": swing_low - diff * 0.272,  # Extension
            "1.618": swing_low - diff * 0.618,  # Extension
        }

    def _detect_candlestick_patterns(self, df: pd.DataFrame) -> List[str]:
        """Detect common candlestick patterns from the course PDFs."""
        patterns = []
        if df.empty or len(df) < 3:
            return patterns

        # Last 3 candles
        c1 = df.iloc[-3]  # oldest
        c2 = df.iloc[-2]
        c3 = df.iloc[-1]  # newest

        body3 = abs(c3["close"] - c3["open"])
        wick_upper3 = c3["high"] - max(c3["close"], c3["open"])
        wick_lower3 = min(c3["close"], c3["open"]) - c3["low"]
        total_range3 = c3["high"] - c3["low"]

        if total_range3 == 0:
            return patterns

        # Doji
        if body3 / total_range3 < 0.1:
            patterns.append("DOJI")

        # Hammer (bullish reversal)
        if (wick_lower3 > body3 * 2 and
            wick_upper3 < body3 * 0.5 and
            c3["close"] > c3["open"]):
            patterns.append("HAMMER")

        # Shooting Star (bearish reversal)
        if (wick_upper3 > body3 * 2 and
            wick_lower3 < body3 * 0.5 and
            c3["close"] < c3["open"]):
            patterns.append("SHOOTING_STAR")

        # Engulfing Bullish
        if (c2["close"] < c2["open"] and  # c2 bearish
            c3["close"] > c3["open"] and  # c3 bullish
            c3["open"] <= c2["close"] and
            c3["close"] >= c2["open"]):
            patterns.append("ENGULFING_BULLISH")

        # Engulfing Bearish
        if (c2["close"] > c2["open"] and  # c2 bullish
            c3["close"] < c3["open"] and  # c3 bearish
            c3["open"] >= c2["close"] and
            c3["close"] <= c2["open"]):
            patterns.append("ENGULFING_BEARISH")

        # Morning Star (3-candle bullish reversal)
        body1 = abs(c1["close"] - c1["open"])
        body2 = abs(c2["close"] - c2["open"])
        if (c1["close"] < c1["open"] and   # c1 bearish
            body2 < body1 * 0.3 and         # c2 small body
            c3["close"] > c3["open"] and    # c3 bullish
            c3["close"] > (c1["open"] + c1["close"]) / 2):  # c3 closes above c1 midpoint
            patterns.append("MORNING_STAR")

        # Evening Star (3-candle bearish reversal)
        if (c1["close"] > c1["open"] and   # c1 bullish
            body2 < body1 * 0.3 and         # c2 small body
            c3["close"] < c3["open"] and    # c3 bearish
            c3["close"] < (c1["open"] + c1["close"]) / 2):
            patterns.append("EVENING_STAR")

        # ── Patterns from "Formación de Velas.pdf" ──

        # High Test (HT) - bearish reversal: long upper wick, close near open/low
        if (wick_upper3 > total_range3 * 0.6 and
            body3 < total_range3 * 0.3 and
            wick_lower3 < total_range3 * 0.2):
            patterns.append("HIGH_TEST")

        # Low Test (LT) - bullish reversal: long lower wick, close near open/high
        if (wick_lower3 > total_range3 * 0.6 and
            body3 < total_range3 * 0.3 and
            wick_upper3 < total_range3 * 0.2):
            patterns.append("LOW_TEST")

        # Tweezer Top - two consecutive candles with similar highs at resistance
        body2 = abs(c2["close"] - c2["open"])
        total_range2 = c2["high"] - c2["low"]
        wick_upper2 = c2["high"] - max(c2["close"], c2["open"])
        if total_range2 > 0:
            if (abs(c3["high"] - c2["high"]) < total_range3 * 0.1 and
                wick_upper3 > body3 * 1.5 and
                wick_upper2 > body2 * 1.5):
                patterns.append("TWEEZER_TOP")

        # Tweezer Bottom - two consecutive candles with similar lows at support
        wick_lower2 = min(c2["close"], c2["open"]) - c2["low"]
        if total_range2 > 0:
            if (abs(c3["low"] - c2["low"]) < total_range3 * 0.1 and
                wick_lower3 > body3 * 1.5 and
                wick_lower2 > body2 * 1.5):
                patterns.append("TWEEZER_BOTTOM")

        # Inside Bar Bullish - c3 entirely within c2 range, bullish bias
        if (c3["high"] <= c2["high"] and c3["low"] >= c2["low"]):
            if c3["close"] > c3["open"]:
                patterns.append("INSIDE_BAR_BULLISH")
            else:
                patterns.append("INSIDE_BAR_BEARISH")

        return patterns

    def _calculate_trade_score(
        self,
        htf_trend: Trend,
        ltf_trend: Trend,
        convergence: bool,
        condition: MarketCondition,
        patterns: List[str],
        chart_patterns: List[Dict] = None,
    ) -> float:
        """
        Calculate a trade quality score from 0-100.
        Higher = better opportunity.
        """
        score = 0.0

        # HTF/LTF convergence is a strong positive (+30)
        if convergence:
            score += 30.0
        elif htf_trend != Trend.RANGING and ltf_trend != Trend.RANGING:
            # Both trending but divergent (-10 penalty)
            if htf_trend != ltf_trend:
                score -= 10.0

        # Trending market is better than ranging (+15 HTF, +10 LTF)
        if htf_trend != Trend.RANGING:
            score += 15.0
        if ltf_trend != Trend.RANGING:
            score += 10.0

        # Market condition bonus (+15 for extreme + confirmation)
        reversal_bullish = any(p in patterns for p in
            ["HAMMER", "ENGULFING_BULLISH", "MORNING_STAR"])
        reversal_bearish = any(p in patterns for p in
            ["SHOOTING_STAR", "ENGULFING_BEARISH", "EVENING_STAR"])

        if condition == MarketCondition.OVERSOLD and reversal_bullish:
            score += 20.0
        elif condition == MarketCondition.OVERBOUGHT and reversal_bearish:
            score += 20.0
        elif condition == MarketCondition.OVERSOLD or condition == MarketCondition.OVERBOUGHT:
            score += 5.0  # Extreme without confirmation

        # Pattern presence bonus (+5 each, max +15)
        pattern_bonus = min(len(patterns) * 5.0, 15.0)
        score += pattern_bonus

        # Ranging market penalty
        if htf_trend == Trend.RANGING and ltf_trend == Trend.RANGING:
            score -= 10.0

        # Advanced chart pattern bonus (+5-15 depending on confidence)
        if chart_patterns:
            best_pattern = max(chart_patterns, key=lambda p: p.get("confidence", 0))
            pattern_conf = best_pattern.get("confidence", 0)
            if pattern_conf >= 70:
                score += 15.0
            elif pattern_conf >= 50:
                score += 10.0
            else:
                score += 5.0

        return max(0.0, min(score, 100.0))

    # ── MACD (from scalping workshop ch403) ──────────────────────────

    def _calculate_macd(
        self, df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> Optional[Dict[str, float]]:
        """
        Calculate MACD (Moving Average Convergence Divergence).
        Used in scalping: H1 direction, M5 setup validation, M1 execution.
        """
        if df.empty or len(df) < slow + signal:
            return None

        ema_fast = df["close"].ewm(span=fast).mean()
        ema_slow = df["close"].ewm(span=slow).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal).mean()
        histogram = macd_line - signal_line

        return {
            "macd": float(macd_line.iloc[-1]),
            "signal": float(signal_line.iloc[-1]),
            "histogram": float(histogram.iloc[-1]),
            "bullish": bool(macd_line.iloc[-1] > signal_line.iloc[-1]),
        }

    # ── RSI Calculation ──────────────────────────────────────────────

    def _calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> Optional[float]:
        """Calculate RSI for a given dataframe."""
        if df.empty or len(df) < period + 1:
            return None

        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()

        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        val = rsi.iloc[-1]
        return val if not pd.isna(val) else None

    # ── RSI Divergence (required for Black strategy, ch15.14) ────────

    def _detect_rsi_divergence(self, df: pd.DataFrame) -> Optional[str]:
        """
        Detect RSI divergence on H4 (required confirmation for Black strategy).
        Bullish divergence: price makes lower low, RSI makes higher low.
        Bearish divergence: price makes higher high, RSI makes lower high.
        """
        if df.empty or len(df) < 30:
            return None

        # Calculate RSI
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))

        # Look at last 20 candles for swing points
        recent_price = df.tail(20)
        recent_rsi = rsi.tail(20)

        if len(recent_price) < 10:
            return None

        data = recent_price.reset_index(drop=True)
        rsi_data = recent_rsi.reset_index(drop=True)

        # Find price swing lows and RSI at those points
        price_lows = []
        for i in range(2, len(data) - 2):
            if (data["low"].iloc[i] < data["low"].iloc[i-1] and
                data["low"].iloc[i] < data["low"].iloc[i-2] and
                data["low"].iloc[i] < data["low"].iloc[i+1] and
                data["low"].iloc[i] < data["low"].iloc[i+2]):
                rsi_val = rsi_data.iloc[i] if i < len(rsi_data) else None
                if rsi_val is not None and not pd.isna(rsi_val):
                    price_lows.append((i, data["low"].iloc[i], rsi_val))

        # Check bullish divergence (price lower low, RSI higher low)
        if len(price_lows) >= 2:
            prev_low = price_lows[-2]
            curr_low = price_lows[-1]
            if curr_low[1] < prev_low[1] and curr_low[2] > prev_low[2]:
                return "bullish"

        # Find price swing highs
        price_highs = []
        for i in range(2, len(data) - 2):
            if (data["high"].iloc[i] > data["high"].iloc[i-1] and
                data["high"].iloc[i] > data["high"].iloc[i-2] and
                data["high"].iloc[i] > data["high"].iloc[i+1] and
                data["high"].iloc[i] > data["high"].iloc[i+2]):
                rsi_val = rsi_data.iloc[i] if i < len(rsi_data) else None
                if rsi_val is not None and not pd.isna(rsi_val):
                    price_highs.append((i, data["high"].iloc[i], rsi_val))

        # Check bearish divergence (price higher high, RSI lower high)
        if len(price_highs) >= 2:
            prev_high = price_highs[-2]
            curr_high = price_highs[-1]
            if curr_high[1] > prev_high[1] and curr_high[2] < prev_high[2]:
                return "bearish"

        return None

    # ── Order Blocks (from SMC workshop ch416-418) ───────────────────

    def _detect_order_blocks(self, df: pd.DataFrame) -> List[Dict]:
        """
        Detect Order Blocks from H1 candles.
        An Order Block is the last candle(s) opposite to an impulse move.
        Where institutions accumulated orders before price moved.
        """
        if df.empty or len(df) < 10:
            return []

        order_blocks = []
        data = df.reset_index(drop=True)

        for i in range(3, len(data) - 1):
            # Bullish Order Block: bearish candle(s) followed by strong bullish impulse
            if (data["close"].iloc[i] > data["open"].iloc[i] and  # current bullish
                data["close"].iloc[i-1] < data["open"].iloc[i-1]):  # previous bearish
                impulse_size = data["close"].iloc[i] - data["open"].iloc[i]
                ob_size = data["open"].iloc[i-1] - data["close"].iloc[i-1]
                # Impulse must be significantly larger than the OB candle
                if impulse_size > ob_size * 1.5:
                    order_blocks.append({
                        "type": "bullish_ob",
                        "high": data["high"].iloc[i-1],
                        "low": data["low"].iloc[i-1],
                        "mid": (data["high"].iloc[i-1] + data["low"].iloc[i-1]) / 2,
                        "index": i - 1,
                    })

            # Bearish Order Block: bullish candle(s) followed by strong bearish impulse
            if (data["close"].iloc[i] < data["open"].iloc[i] and  # current bearish
                data["close"].iloc[i-1] > data["open"].iloc[i-1]):  # previous bullish
                impulse_size = data["open"].iloc[i] - data["close"].iloc[i]
                ob_size = data["close"].iloc[i-1] - data["open"].iloc[i-1]
                if impulse_size > ob_size * 1.5:
                    order_blocks.append({
                        "type": "bearish_ob",
                        "high": data["high"].iloc[i-1],
                        "low": data["low"].iloc[i-1],
                        "mid": (data["high"].iloc[i-1] + data["low"].iloc[i-1]) / 2,
                        "index": i - 1,
                    })

        # Keep only recent order blocks (last 10)
        return order_blocks[-10:]

    # ── BOS/CHOCH Detection (from SMC workshop ch413) ────────────────

    def _detect_structure_breaks(self, df: pd.DataFrame) -> List[Dict]:
        """
        Detect Break of Structure (BOS) and Change of Character (CHOCH).
        BOS: price breaks previous high/low continuing trend.
        CHOCH: price stops making HH/HL (or LL/LH) — trend reversal signal.
        """
        if df.empty or len(df) < 20:
            return []

        breaks = []
        data = df.reset_index(drop=True)

        # Find swing points
        swing_highs = []
        swing_lows = []
        for i in range(2, len(data) - 2):
            if (data["high"].iloc[i] > data["high"].iloc[i-1] and
                data["high"].iloc[i] > data["high"].iloc[i+1]):
                swing_highs.append((i, data["high"].iloc[i]))
            if (data["low"].iloc[i] < data["low"].iloc[i-1] and
                data["low"].iloc[i] < data["low"].iloc[i+1]):
                swing_lows.append((i, data["low"].iloc[i]))

        if len(swing_highs) < 3 or len(swing_lows) < 3:
            return breaks

        # Analyze last few swing points for BOS and CHOCH
        for j in range(max(2, len(swing_highs) - 5), len(swing_highs)):
            if j < 1:
                continue
            prev_high = swing_highs[j - 1][1]
            curr_high = swing_highs[j][1]

            if curr_high > prev_high:
                # BOS bullish: new higher high
                breaks.append({
                    "type": "BOS",
                    "direction": "bullish",
                    "level": prev_high,
                    "index": swing_highs[j][0],
                })
            elif curr_high < prev_high * 0.998:
                # Potential CHOCH: lower high after uptrend
                # Check if previous was making higher highs
                if j >= 2 and swing_highs[j-1][1] > swing_highs[j-2][1]:
                    breaks.append({
                        "type": "CHOCH",
                        "direction": "bearish",
                        "level": curr_high,
                        "index": swing_highs[j][0],
                    })

        for j in range(max(2, len(swing_lows) - 5), len(swing_lows)):
            if j < 1:
                continue
            prev_low = swing_lows[j - 1][1]
            curr_low = swing_lows[j][1]

            if curr_low < prev_low:
                # BOS bearish: new lower low
                breaks.append({
                    "type": "BOS",
                    "direction": "bearish",
                    "level": prev_low,
                    "index": swing_lows[j][0],
                })
            elif curr_low > prev_low * 1.002:
                # Potential CHOCH: higher low after downtrend
                if j >= 2 and swing_lows[j-1][1] < swing_lows[j-2][1]:
                    breaks.append({
                        "type": "CHOCH",
                        "direction": "bullish",
                        "level": curr_low,
                        "index": swing_lows[j][0],
                    })

        return breaks[-10:]
