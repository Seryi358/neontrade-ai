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

from typing import Any, Dict, List, Optional, Tuple
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import pandas as pd
import numpy as np
from loguru import logger

from core.chart_patterns import detect_chart_patterns, ChartPattern

# Negatively correlated pairs: when one goes up, the other goes down.
# For SMT divergence, the comparison logic must be inverted for these pairs.
NEGATIVE_CORRELATIONS = {
    "EUR_USD": "DXY",
    "GBP_USD": "DXY",
    "AUD_USD": "DXY",
    "NZD_USD": "DXY",
    "DXY": "EUR_USD",  # reverse mapping
}


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
    key_levels: Dict[str, List]  # supports, resistances, FVGs, fvg_zones, liquidity_pools
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
    # TradingLab course additions
    volume_analysis: Dict[str, Any] = field(default_factory=dict)
    ema_w8: Optional[float] = None
    sma_d200: Optional[float] = None
    # Last closed candles per timeframe (for RCC confirmation)
    last_candles: Dict[str, List[Dict]] = field(default_factory=dict)
    # Current price (latest ask/bid midpoint from M5 close)
    current_price: Optional[float] = None
    # Active trading session (ASIAN, LONDON, OVERLAP, NEW_YORK, OFF_HOURS)
    session: Optional[str] = None
    # Elliott Wave detail from daily candle analysis
    elliott_wave_detail: Dict[str, Any] = field(default_factory=dict)
    # Pivot Points (P, S1, S2, R1, R2) from daily data
    pivot_points: Dict[str, float] = field(default_factory=dict)
    # Premium/Discount zone: "premium", "discount", "equilibrium", or None
    premium_discount_zone: Optional[str] = None
    # Volume divergence: "bullish", "bearish", or None
    volume_divergence: Optional[str] = None
    # Mitigation Blocks: order blocks that have been partially filled
    mitigation_blocks: List[Dict] = field(default_factory=list)
    # Breaker Blocks: order blocks that price broke through (type flipped)
    breaker_blocks: List[Dict] = field(default_factory=list)
    # Power of Three / AMD: current session phase and direction bias
    power_of_three: Dict[str, Any] = field(default_factory=dict)
    # SMT Divergence: "bullish", "bearish", or None
    smt_divergence: Optional[str] = None
    # Liquidity sweep detection: {"level": float, "direction": "swept_highs"|"swept_lows"}
    liquidity_sweep: Optional[Dict[str, Any]] = None
    # BMSB (Bull Market Support Band) - TradingLab Crypto Module 8
    bmsb: Optional[Dict] = None
    # Pi Cycle Top/Bottom - TradingLab Crypto Module 8
    pi_cycle: Optional[Dict] = None


class MarketAnalyzer:
    """Multi-timeframe market analysis engine."""

    # Class-level cache for SMT divergence: stores last swing high/low per instrument
    _smt_cache: Dict[str, Dict] = {}

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
            "D": 500,    # ~2 years daily (covers Pi Cycle's 471 requirement)
            "H4": 200,   # ~33 days of 4H
            "H1": 200,   # ~8 days of 1H
            "M15": 200,  # ~2 days of 15m
            "M5": 200,   # ~17 hours of 5m
            "M1": 200,   # ~3.3 hours, needed for scalping position management
            # M2 not supported by Capital.com API — M5 used as fallback
        }

        for tf, count in timeframes.items():
            try:
                raw = await self.broker.get_candles(instrument, tf, count)
                candles[tf] = self._candles_to_dataframe(raw)
            except Exception as e:
                logger.error(f"Failed to get {tf} candles for {instrument}: {e}")
                candles[tf] = pd.DataFrame()
            # Throttle between timeframe fetches to avoid broker rate limits
            await asyncio.sleep(0.3)

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

        # Step 8: MACD (from scalping workshop - H1, M15, M5 + Daily from TradingLab)
        macd_values = {}
        for tf in ("D", "H1", "M15", "M5"):
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

        # Step 13a: Volume analysis on H1 and M5 (TradingLab course)
        volume_analysis = {}
        for tf in ("H1", "M5"):
            df = candles.get(tf, pd.DataFrame())
            if not df.empty:
                vol_data = self._analyze_volume(df)
                if vol_data:
                    volume_analysis[tf] = vol_data

        # Step 13b: Extract EMA_W_8 and SMA_D_200 for convenience fields
        ema_w8_val = ema_values.get("EMA_W_8")
        sma_d200_val = sma_values.get("SMA_D_200")

        # Step 14: HTF/LTF convergence
        convergence = htf_trend == ltf_trend

        # Step 15: Score
        score = self._calculate_trade_score(
            htf_trend, ltf_trend, convergence, htf_condition, patterns, chart_pats
        )

        # Step 16: Last closed candles per timeframe (for RCC confirmation)
        last_candles = {}
        for tf in ("M5", "H1", "H4"):
            df = candles.get(tf, pd.DataFrame())
            if not df.empty and len(df) >= 3:
                tail = df.tail(3)
                last_candles[tf] = [
                    {"open": float(r["open"]), "high": float(r["high"]),
                     "low": float(r["low"]), "close": float(r["close"]),
                     "volume": int(r.get("volume", 0))}
                    for _, r in tail.iterrows()
                ]

        # Step 17: Current price from latest M5 close
        m5_df = candles.get("M5", pd.DataFrame())
        current_price = float(m5_df.iloc[-1]["close"]) if not m5_df.empty else None

        # Step 18: Trading session detection
        session = self._detect_session()

        # Step 19: Elliott Wave counting from daily candles
        elliott_wave_detail = self._count_elliott_waves(
            candles.get("D", pd.DataFrame())
        )

        # Step 20: Pivot Points from daily candles
        pivot_points = self._calculate_pivot_points(
            candles.get("D", pd.DataFrame())
        )

        # Step 21: Premium/Discount zone detection
        premium_discount_zone = self._detect_premium_discount(
            candles.get("D", pd.DataFrame()), current_price
        )

        # Step 22: Volume divergence detection on H1
        volume_divergence = self._detect_volume_divergence(
            candles.get("H1", pd.DataFrame())
        )

        # Step 23: Mitigation Blocks (order blocks revisited by price)
        mitigation_blocks = self._detect_mitigation_blocks(
            candles.get("H1", pd.DataFrame()), order_blocks
        )

        # Step 24: Breaker Blocks (order blocks that price broke through)
        breaker_blocks = self._detect_breaker_blocks(
            candles.get("H1", pd.DataFrame()), order_blocks
        )

        # Step 25: Power of Three / AMD session phase detection
        power_of_three = self._detect_power_of_three(
            candles.get("H1", pd.DataFrame()), current_price
        )

        # Step 26: SMT Divergence (correlated asset swing comparison)
        smt_divergence = self._detect_smt_divergence(
            instrument, candles.get("H1", pd.DataFrame())
        )

        # Step 27: Liquidity Pools & sweep detection (Gap 6)
        liquidity_pools, liquidity_sweep = self._detect_liquidity_pools(
            candles, key_levels, power_of_three, current_price
        )
        key_levels["liquidity_pools"] = liquidity_pools

        # Step 28: BMSB (Bull Market Support Band) - TradingLab Crypto Module 8
        # SMA 20 + EMA 21 on Weekly
        bmsb = None
        w_df = candles.get("W", pd.DataFrame())
        if not w_df.empty and len(w_df) >= 21 and current_price is not None:
            weekly_closes = w_df["close"].tolist()
            sma_20 = sum(weekly_closes[-20:]) / 20
            # EMA 21
            ema_21 = weekly_closes[0]
            multiplier = 2 / (21 + 1)
            for price_val in weekly_closes[1:]:
                ema_21 = (price_val - ema_21) * multiplier + ema_21
            last_weekly_close = weekly_closes[-1]
            bmsb = {
                "sma_20": sma_20,
                "ema_21": ema_21,
                "bullish": last_weekly_close > sma_20 and last_weekly_close > ema_21,
                "bearish": last_weekly_close < sma_20 and last_weekly_close < ema_21,
                "last_close": last_weekly_close,
            }

        # Step 29: Pi Cycle Top/Bottom - TradingLab Crypto Module 8
        # Pi Cycle Top: SMA 111 crosses above 2x SMA 350
        # Pi Cycle Bottom: SMA 150 crosses below SMA 471
        pi_cycle = None
        daily_df = candles.get("D", pd.DataFrame())
        if not daily_df.empty and len(daily_df) >= 471:
            daily_closes = daily_df["close"].tolist()
            sma_111 = sum(daily_closes[-111:]) / 111
            sma_350 = sum(daily_closes[-350:]) / 350
            sma_350_2x = sma_350 * 2
            sma_150 = sum(daily_closes[-150:]) / 150
            sma_471 = sum(daily_closes[-471:]) / 471
            pi_cycle = {
                "sma_111": sma_111,
                "sma_350_2x": sma_350_2x,
                "near_top": sma_111 > sma_350_2x * 0.98,  # Within 2% of cross
                "near_bottom": sma_150 < sma_471 * 1.02,
            }

        result = AnalysisResult(
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
            volume_analysis=volume_analysis,
            ema_w8=ema_w8_val,
            sma_d200=sma_d200_val,
            last_candles=last_candles,
            current_price=current_price,
            session=session,
            elliott_wave_detail=elliott_wave_detail,
            pivot_points=pivot_points,
            premium_discount_zone=premium_discount_zone,
            volume_divergence=volume_divergence,
            mitigation_blocks=mitigation_blocks,
            breaker_blocks=breaker_blocks,
            power_of_three=power_of_three,
            smt_divergence=smt_divergence,
            liquidity_sweep=liquidity_sweep,
            bmsb=bmsb,
            pi_cycle=pi_cycle,
        )
        return result

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

    def _find_key_levels(self, candles: Dict[str, pd.DataFrame]) -> Dict[str, List]:
        """Find support, resistance, and Fair Value Gap (FVG) levels."""
        levels: Dict[str, List] = {
            "supports": [],
            "resistances": [],
            "fvg": [],          # backward-compatible: list of midpoint floats
            "fvg_zones": [],    # full FVG data model (Gap 7)
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

        # Find FVGs (Fair Value Gaps) from 1H — full data model (Gap 7)
        h1 = candles.get("H1", pd.DataFrame())
        fvg_zones: List[Dict] = []
        if not h1.empty:
            for i in range(2, len(h1)):
                # Bullish FVG: candle[i] low > candle[i-2] high
                if h1["low"].iloc[i] > h1["high"].iloc[i-2]:
                    high_boundary = float(h1["low"].iloc[i])
                    low_boundary = float(h1["high"].iloc[i-2])
                    midpoint = (high_boundary + low_boundary) / 2
                    levels["fvg"].append(midpoint)
                    fvg_zones.append({
                        "high": high_boundary,
                        "low": low_boundary,
                        "mid": midpoint,
                        "direction": "bullish",
                        "filled": False,
                        "timeframe": "H1",
                        "index": i,
                    })
                # Bearish FVG: candle[i] high < candle[i-2] low
                elif h1["high"].iloc[i] < h1["low"].iloc[i-2]:
                    high_boundary = float(h1["low"].iloc[i-2])
                    low_boundary = float(h1["high"].iloc[i])
                    midpoint = (high_boundary + low_boundary) / 2
                    levels["fvg"].append(midpoint)
                    fvg_zones.append({
                        "high": high_boundary,
                        "low": low_boundary,
                        "mid": midpoint,
                        "direction": "bearish",
                        "filled": False,
                        "timeframe": "H1",
                        "index": i,
                    })

            # Check if FVGs have been filled by subsequent price action
            for fvg in fvg_zones:
                fvg_idx = fvg["index"]
                for j in range(fvg_idx + 1, len(h1)):
                    candle_low = float(h1["low"].iloc[j])
                    candle_high = float(h1["high"].iloc[j])

                    if fvg["direction"] == "bullish":
                        # Bullish FVG filled if price comes back down through it
                        if candle_low <= fvg["low"]:
                            fvg["filled"] = True
                            break
                    else:
                        # Bearish FVG filled if price comes back up through it
                        if candle_high >= fvg["high"]:
                            fvg["filled"] = True
                            break

                    # Check if price touched the start of the FVG (reaction point)
                    if not fvg.get("reacted"):
                        if fvg["direction"] == "bullish" and candle_low <= fvg["high"]:
                            fvg["reacted"] = True
                        elif fvg["direction"] == "bearish" and candle_high >= fvg["low"]:
                            fvg["reacted"] = True

                    # Check if price reached 50% (partial fill)
                    if not fvg.get("partially_filled"):
                        if fvg["direction"] == "bullish" and candle_low <= fvg["mid"]:
                            fvg["partially_filled"] = True
                        elif fvg["direction"] == "bearish" and candle_high >= fvg["mid"]:
                            fvg["partially_filled"] = True

            # IFVG detection: inverted FVGs (FVG broken by candle body = flip direction)
            for fvg in fvg_zones:
                if fvg.get("inverted"):
                    continue
                fvg_idx = fvg["index"]
                for j in range(fvg_idx + 1, len(h1)):
                    candle_open = float(h1["open"].iloc[j])
                    candle_close = float(h1["close"].iloc[j])
                    body_high = max(candle_open, candle_close)
                    body_low = min(candle_open, candle_close)

                    if fvg["direction"] == "bullish":
                        # Bullish FVG broken by bearish body closing below FVG low
                        if body_high < fvg["low"]:
                            fvg["inverted"] = True
                            fvg["direction"] = "bearish"  # flip
                            break
                    else:
                        # Bearish FVG broken by bullish body closing above FVG high
                        if body_low > fvg["high"]:
                            fvg["inverted"] = True
                            fvg["direction"] = "bullish"  # flip
                            break

        # Keep only recent levels
        levels["supports"] = sorted(levels["supports"])[-10:]
        levels["resistances"] = sorted(levels["resistances"])[-10:]
        levels["fvg"] = levels["fvg"][-20:]
        levels["fvg_zones"] = fvg_zones[-20:]

        return levels

    def _calculate_emas(self, candles: Dict[str, pd.DataFrame]) -> Dict[str, float]:
        """Calculate EMA values for multiple timeframes."""
        emas = {}
        ema_configs = {
            "W": [8, 50],
            "D": [20, 50],
            "H4": [50],
            "H1": [50],
            "M15": [5, 20, 50],
            "M5": [2, 5, 20, 50],
            # M2 removed: candles are never fetched (not supported by broker API)
            "M1": [50],  # EMA 50 for scalping CP/CPA management
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
            "0.382": swing_high - diff * 0.382,
            "0.5": swing_high - diff * 0.5,
            "0.618": swing_high - diff * 0.618,
            "0.750": swing_high - diff * 0.750,
            "1.0": swing_low,
            "ext_0.618": swing_low - diff * 0.618,  # Extension
            "ext_1.0": swing_low - diff * 1.0,  # Extension
            "ext_1.272": swing_low - diff * 1.272,  # Extension
            "ext_1.618": swing_low - diff * 1.618,  # Extension
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

        # ── Three Drives Pattern (Power of Three / AMD) ──
        # Detect when price makes 3 roughly equal pushes to a level.
        # Requires more candles; use the full dataframe.
        if len(df) >= 20:
            self._detect_three_drives(df, patterns)

        return patterns

    def _detect_three_drives(self, df: pd.DataFrame, patterns: List[str]) -> None:
        """
        Detect Three Drives pattern: 3 roughly equal pushes in the same direction.
        Bullish three drives: 3 successive lower lows with roughly equal spacing.
        Bearish three drives: 3 successive higher highs with roughly equal spacing.
        """
        data = df.tail(20).reset_index(drop=True)
        if len(data) < 10:
            return

        # Find swing lows for bullish three drives (reversal)
        swing_lows = []
        for i in range(1, len(data) - 1):
            if (data["low"].iloc[i] < data["low"].iloc[i - 1] and
                data["low"].iloc[i] < data["low"].iloc[i + 1]):
                swing_lows.append((i, float(data["low"].iloc[i])))

        if len(swing_lows) >= 3:
            last3 = swing_lows[-3:]
            # Check 3 successive lower lows
            if last3[0][1] > last3[1][1] > last3[2][1]:
                # Check roughly equal drive sizes (within 50%)
                drive1 = last3[0][1] - last3[1][1]
                drive2 = last3[1][1] - last3[2][1]
                if drive1 > 0 and drive2 > 0:
                    ratio = drive1 / drive2
                    if 0.5 <= ratio <= 2.0:
                        patterns.append("THREE_DRIVES_BULLISH")

        # Find swing highs for bearish three drives (reversal)
        swing_highs = []
        for i in range(1, len(data) - 1):
            if (data["high"].iloc[i] > data["high"].iloc[i - 1] and
                data["high"].iloc[i] > data["high"].iloc[i + 1]):
                swing_highs.append((i, float(data["high"].iloc[i])))

        if len(swing_highs) >= 3:
            last3 = swing_highs[-3:]
            # Check 3 successive higher highs
            if last3[0][1] < last3[1][1] < last3[2][1]:
                drive1 = last3[1][1] - last3[0][1]
                drive2 = last3[2][1] - last3[1][1]
                if drive1 > 0 and drive2 > 0:
                    ratio = drive1 / drive2
                    if 0.5 <= ratio <= 2.0:
                        patterns.append("THREE_DRIVES_BEARISH")

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

    # ── Volume Analysis (TradingLab course) ────────────────────────

    def _analyze_volume(
        self, candles: pd.DataFrame, period: int = 20
    ) -> Dict[str, Any]:
        """
        Analyze volume relative to its recent average.
        Returns avg volume, current volume, ratio, and whether above average.
        """
        if candles.empty or "volume" not in candles.columns or len(candles) < period:
            return {}

        volumes = candles["volume"].tail(period)
        avg_vol = float(volumes.mean())
        current_vol = int(candles["volume"].iloc[-1])
        ratio = current_vol / avg_vol if avg_vol > 0 else 0.0

        return {
            "avg_volume": avg_vol,
            "current_volume": current_vol,
            "volume_ratio": float(ratio),
            "above_average": bool(current_vol > avg_vol),
        }

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
                # Filtro de calidad: impulso mínimo 1.5x OB (no especificado en mentoría)
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
                # Tolerancia implementación: 0.2% (mentoría no especifica tolerancia exacta)
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
                # Tolerancia implementación: 0.2% (mentoría no especifica tolerancia exacta)
                # Potential CHOCH: higher low after downtrend
                if j >= 2 and swing_lows[j-1][1] < swing_lows[j-2][1]:
                    breaks.append({
                        "type": "CHOCH",
                        "direction": "bullish",
                        "level": curr_low,
                        "index": swing_lows[j][0],
                    })

        return breaks[-10:]

    # ── Trading Session Detection ─────────────────────────────────────

    def _detect_session(self) -> str:
        """
        Return the currently active trading session based on UTC hour.

        Sessions:
          ASIAN     : 00:00-08:00 UTC (Tokyo/Sydney)
          LONDON    : 08:00-12:00 UTC
          OVERLAP   : 12:00-16:00 UTC (London+NY overlap - highest volatility)
          NEW_YORK  : 16:00-21:00 UTC
          OFF_HOURS : 21:00-00:00 UTC
        """
        utc_hour = datetime.now(timezone.utc).hour

        if 0 <= utc_hour < 8:
            return "ASIAN"
        elif 8 <= utc_hour < 12:
            return "LONDON"
        elif 12 <= utc_hour < 16:
            return "OVERLAP"
        elif 16 <= utc_hour < 21:
            return "NEW_YORK"
        else:
            return "OFF_HOURS"

    # ── Basic Elliott Wave Counting ───────────────────────────────────

    def _count_elliott_waves(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Estimate the current Elliott Wave position from daily candles.

        Algorithm:
        1. Find swing highs and lows (5-bar pivots).
        2. Determine major trend direction from swing points.
        3. Count alternating impulse / correction legs:
           - Uptrend: HH + HL = impulse, LH + LL = correction
           - Downtrend: LL + LH = impulse, HL + HH = correction
        4. Map wave count to strategy colour suggestion:
           Wave 1  -> BLACK   (first impulse after reversal)
           Wave 2  -> BLUE    (first correction, 1-2 setup)
           Wave 3  -> RED     (strongest impulse, 2-3 setup)
           Wave 4  -> PINK    (second correction, 4->5 setup)
           Wave 5  -> WHITE/GREEN (final impulse)
           A/B/C   -> corrective strategy mapping

        Returns dict with wave_count, phase, suggested_strategy.
        """
        if df.empty or len(df) < 30:
            return {}

        data = df.reset_index(drop=True)

        # ── Step 1: Find swing highs and lows (5-bar pivots) ──
        swing_highs: List[Tuple[int, float]] = []
        swing_lows: List[Tuple[int, float]] = []

        for i in range(2, len(data) - 2):
            if (data["high"].iloc[i] > data["high"].iloc[i - 1] and
                data["high"].iloc[i] > data["high"].iloc[i - 2] and
                data["high"].iloc[i] > data["high"].iloc[i + 1] and
                data["high"].iloc[i] > data["high"].iloc[i + 2]):
                swing_highs.append((i, float(data["high"].iloc[i])))

            if (data["low"].iloc[i] < data["low"].iloc[i - 1] and
                data["low"].iloc[i] < data["low"].iloc[i - 2] and
                data["low"].iloc[i] < data["low"].iloc[i + 1] and
                data["low"].iloc[i] < data["low"].iloc[i + 2]):
                swing_lows.append((i, float(data["low"].iloc[i])))

        if len(swing_highs) < 3 or len(swing_lows) < 3:
            return {}

        # ── Step 2: Merge swing points chronologically ──
        swings: List[Tuple[int, float, str]] = []
        for idx, val in swing_highs:
            swings.append((idx, val, "H"))
        for idx, val in swing_lows:
            swings.append((idx, val, "L"))
        swings.sort(key=lambda s: s[0])

        # Remove consecutive same-type entries (keep extreme)
        filtered: List[Tuple[int, float, str]] = [swings[0]]
        for s in swings[1:]:
            if s[2] == filtered[-1][2]:
                # Same type: keep the more extreme value
                if s[2] == "H" and s[1] > filtered[-1][1]:
                    filtered[-1] = s
                elif s[2] == "L" and s[1] < filtered[-1][1]:
                    filtered[-1] = s
            else:
                filtered.append(s)

        if len(filtered) < 5:
            return {}

        # ── Step 3: Determine trend direction from recent swings ──
        recent = filtered[-6:]  # last ~3 pairs of H/L
        highs_in_recent = [v for _, v, t in recent if t == "H"]
        lows_in_recent = [v for _, v, t in recent if t == "L"]

        uptrend = False
        downtrend = False

        if len(highs_in_recent) >= 2 and len(lows_in_recent) >= 2:
            hh = highs_in_recent[-1] > highs_in_recent[-2]
            hl = lows_in_recent[-1] > lows_in_recent[-2]
            ll = lows_in_recent[-1] < lows_in_recent[-2]
            lh = highs_in_recent[-1] < highs_in_recent[-2]

            if hh and hl:
                uptrend = True
            elif ll and lh:
                downtrend = True

        # ── Step 4: Count waves ──
        # Walk through filtered swings and count alternating impulse/correction
        # legs relative to the detected trend.
        wave_count = 0
        phase = "impulse"
        prev_swing = filtered[0]
        in_impulse = True

        for s in filtered[1:]:
            if uptrend or (not downtrend):
                # Uptrend logic (default when ranging)
                if s[2] == "H" and in_impulse:
                    if s[1] >= prev_swing[1]:
                        # Impulse leg continues / completes
                        wave_count += 1
                        in_impulse = False  # next expect correction
                elif s[2] == "L" and not in_impulse:
                    # Correction leg
                    wave_count += 1
                    in_impulse = True  # next expect impulse
                    if wave_count > 5:
                        # Switch to corrective phase
                        phase = "corrective"
            else:
                # Downtrend logic (mirrored)
                if s[2] == "L" and in_impulse:
                    if s[1] <= prev_swing[1]:
                        wave_count += 1
                        in_impulse = False
                elif s[2] == "H" and not in_impulse:
                    wave_count += 1
                    in_impulse = True
                    if wave_count > 5:
                        phase = "corrective"

            prev_swing = s

        # ── Step 5: Map to Elliott label and strategy colour ──
        strategy_map_impulse = {
            1: "BLACK",
            2: "BLUE",
            3: "RED",
            4: "PINK",
            5: "WHITE/GREEN",
        }
        strategy_map_corrective = {
            "A": "BLACK",
            "B": "BLUE",
            "C": "RED",
        }

        if phase == "impulse":
            # Clamp to 1-5 range
            effective_wave = max(1, min(wave_count, 5))
            wave_label = str(effective_wave)
            suggested = strategy_map_impulse.get(effective_wave, "BLACK")
        else:
            # Corrective: waves beyond 5 map to A, B, C
            corrective_idx = (wave_count - 5) if wave_count > 5 else wave_count
            corrective_idx = max(1, min(corrective_idx, 3))
            labels = {1: "A", 2: "B", 3: "C"}
            wave_label = labels.get(corrective_idx, "A")
            suggested = strategy_map_corrective.get(wave_label, "BLACK")

        return {
            "wave_count": wave_label,
            "phase": phase,
            "suggested_strategy": suggested,
        }

    # ── Pivot Points (TradingLab ch12) ─────────────────────────────────

    def _calculate_pivot_points(self, df: pd.DataFrame) -> Dict[str, float]:
        """
        Calculate Standard Pivot Points from the previous daily candle.

        P  = (H + L + C) / 3
        R1 = 2*P - L
        S1 = 2*P - H
        R2 = P + (H - L)
        S2 = P - (H - L)

        These act as intraday S/R levels used by institutional traders.
        """
        if df.empty or len(df) < 2:
            return {}

        # Average over the last 5 completed sessions for smoother pivots
        sessions = min(5, len(df) - 1)
        if sessions < 1:
            return {}

        totals = {"P": 0.0, "R1": 0.0, "S1": 0.0, "R2": 0.0, "S2": 0.0}
        for i in range(sessions):
            candle = df.iloc[-(i + 2)]  # Skip current incomplete candle
            h, l, c = float(candle["high"]), float(candle["low"]), float(candle["close"])
            p = (h + l + c) / 3.0
            totals["P"] += p
            totals["R1"] += 2 * p - l
            totals["S1"] += 2 * p - h
            totals["R2"] += p + (h - l)
            totals["S2"] += p - (h - l)

        return {k: round(v / sessions, 5) for k, v in totals.items()}

    # ── Volume Divergence Detection (TradingLab Gap #6) ──────────────

    def _detect_volume_divergence(self, df: pd.DataFrame) -> Optional[str]:
        """
        Detect volume divergence on the last 10 candles.
        - Bearish divergence: price making higher highs but volume decreasing.
        - Bullish divergence (selling exhaustion): price making lower lows but volume decreasing.
        Returns "bullish", "bearish", or None.
        """
        if df.empty or len(df) < 10:
            return None

        recent = df.tail(10).reset_index(drop=True)

        # Find highest high in first half vs second half
        first_half = recent.iloc[:5]
        second_half = recent.iloc[5:]

        fh_high = float(first_half["high"].max())
        sh_high = float(second_half["high"].max())
        fh_low = float(first_half["low"].min())
        sh_low = float(second_half["low"].min())

        fh_vol = float(first_half["volume"].mean()) if "volume" in first_half.columns else 0
        sh_vol = float(second_half["volume"].mean()) if "volume" in second_half.columns else 0

        if fh_vol <= 0 or sh_vol <= 0:
            return None

        # Bearish divergence: higher highs + decreasing volume
        if sh_high > fh_high and sh_vol < fh_vol * 0.85:
            return "bearish"

        # Bullish divergence (selling exhaustion): lower lows + decreasing volume
        if sh_low < fh_low and sh_vol < fh_vol * 0.85:
            return "bullish"

        return None

    # ── Mitigation Block Detection (TradingLab Gap #7) ─────────────

    def _detect_mitigation_blocks(
        self, df: pd.DataFrame, order_blocks: List[Dict]
    ) -> List[Dict]:
        """
        Detect Mitigation Blocks (corrected per SMC workshop definition - Gap 8).

        A Mitigation Block is an Order Block that price broke through WITHOUT a
        prior liquidity sweep.  In other words:
        1. Price closed beyond the OB (broke it).
        2. Before that break, the previous swing high/low was NOT taken.
        3. If liquidity WAS swept before the break, it is a Breaker Block instead
           (handled by _detect_breaker_blocks).
        """
        if df.empty or not order_blocks:
            return []

        mitigation_blocks = []
        data = df.reset_index(drop=True)

        # Pre-compute swing highs and swing lows for the whole series
        swing_highs: List[Tuple[int, float]] = []
        swing_lows: List[Tuple[int, float]] = []
        for i in range(2, len(data) - 2):
            if (data["high"].iloc[i] > data["high"].iloc[i - 1] and
                    data["high"].iloc[i] > data["high"].iloc[i + 1]):
                swing_highs.append((i, float(data["high"].iloc[i])))
            if (data["low"].iloc[i] < data["low"].iloc[i - 1] and
                    data["low"].iloc[i] < data["low"].iloc[i + 1]):
                swing_lows.append((i, float(data["low"].iloc[i])))

        for ob in order_blocks:
            ob_idx = ob.get("index", 0)
            ob_high = ob.get("high", 0)
            ob_low = ob.get("low", 0)
            ob_type = ob.get("type", "")

            if ob_high == 0 or ob_low == 0:
                continue

            # Step 1: Check if price broke through this OB
            break_idx = None
            for j in range(ob_idx + 2, len(data)):
                candle_open = float(data["open"].iloc[j])
                candle_close = float(data["close"].iloc[j])
                body_low = min(candle_open, candle_close)
                body_high = max(candle_open, candle_close)

                if ob_type == "bullish_ob" and body_low < ob_low:
                    break_idx = j
                    break
                elif ob_type == "bearish_ob" and body_high > ob_high:
                    break_idx = j
                    break

            if break_idx is None:
                continue  # OB was never broken — not a mitigation block

            # Step 2: Check if liquidity was swept BEFORE the break
            liquidity_swept = False

            if ob_type == "bullish_ob":
                # For a bullish OB break-down, check if previous swing low
                # was taken (lower low made) before the break
                prev_swing_low = None
                for si, sv in swing_lows:
                    if si < ob_idx:
                        prev_swing_low = sv
                # Check if any candle between OB and break went below prev swing low
                if prev_swing_low is not None:
                    for j in range(ob_idx, break_idx):
                        if float(data["low"].iloc[j]) < prev_swing_low:
                            liquidity_swept = True
                            break

            elif ob_type == "bearish_ob":
                # For a bearish OB break-up, check if previous swing high
                # was taken (higher high made) before the break
                prev_swing_high = None
                for si, sv in swing_highs:
                    if si < ob_idx:
                        prev_swing_high = sv
                # Check if any candle between OB and break went above prev swing high
                if prev_swing_high is not None:
                    for j in range(ob_idx, break_idx):
                        if float(data["high"].iloc[j]) > prev_swing_high:
                            liquidity_swept = True
                            break

            # Step 3: Mitigation Block = broken OB WITHOUT prior liquidity sweep
            if not liquidity_swept:
                mitigation_blocks.append({
                    "type": f"mitigation_{ob_type}",
                    "high": ob_high,
                    "low": ob_low,
                    "mid": (ob_high + ob_low) / 2,
                    "original_index": ob_idx,
                    "break_index": break_idx,
                })

        return mitigation_blocks[-10:]

    # ── Breaker Block Detection (SMC Workshop) ──────────────────────────

    def _detect_breaker_blocks(
        self, df: pd.DataFrame, order_blocks: List[Dict]
    ) -> List[Dict]:
        """
        Detect Breaker Blocks: order blocks that price BROKE THROUGH with a candle body.
        When a bullish OB is broken to the downside, it flips to bearish (resistance).
        When a bearish OB is broken to the upside, it flips to bullish (support).
        """
        if df.empty or not order_blocks:
            return []

        breaker_blocks = []
        data = df.reset_index(drop=True)

        for ob in order_blocks:
            ob_idx = ob.get("index", 0)
            ob_high = ob.get("high", 0)
            ob_low = ob.get("low", 0)
            ob_type = ob.get("type", "")

            if ob_high == 0 or ob_low == 0:
                continue

            # Check if any subsequent candle's body broke through the OB
            for j in range(ob_idx + 2, len(data)):
                candle_open = float(data["open"].iloc[j])
                candle_close = float(data["close"].iloc[j])
                body_high = max(candle_open, candle_close)
                body_low = min(candle_open, candle_close)

                if ob_type == "bullish_ob":
                    # Bullish OB broken: candle body closes below the OB low
                    if body_low < ob_low and body_high < ob_low:
                        # Entire body below OB low → broken through
                        breaker_blocks.append({
                            "type": "bearish",  # Flipped: was bullish, now resistance
                            "high": ob_high,
                            "low": ob_low,
                            "mid": (ob_high + ob_low) / 2,
                            "original_type": ob_type,
                            "break_index": j,
                        })
                        break
                elif ob_type == "bearish_ob":
                    # Bearish OB broken: candle body closes above the OB high
                    if body_low > ob_high and body_high > ob_high:
                        # Entire body above OB high → broken through
                        breaker_blocks.append({
                            "type": "bullish",  # Flipped: was bearish, now support
                            "high": ob_high,
                            "low": ob_low,
                            "mid": (ob_high + ob_low) / 2,
                            "original_type": ob_type,
                            "break_index": j,
                        })
                        break

        return breaker_blocks[-10:]

    # ── Power of Three / AMD Detection (SMC Workshop) ─────────────────

    def _detect_power_of_three(
        self, df: pd.DataFrame, current_price: Optional[float]
    ) -> Dict[str, Any]:
        """
        Detect Power of Three (AMD) session phases:
        - ASIAN (00:00-08:00 UTC) = Accumulation (lateral, low volatility)
        - LONDON (08:00-12:00 UTC) = Manipulation (strong impulse, often fake)
        - NY (12:00-21:00 UTC) = Distribution (real move direction)

        Nota: los horarios son aproximaciones para el patrón AMD.
        Las sesiones reales varían con DST (EST/EDT):
          Asian/Tokyo: ~00:00-09:00 UTC (EST) / ~23:00-08:00 UTC (EDT)
          London: ~08:00-17:00 UTC (EST) / ~07:00-16:00 UTC (EDT)
          New York: ~13:00-22:00 UTC (EST) / ~12:00-21:00 UTC (EDT)

        Returns dict with phase, session, asian_range, direction_bias.
        """
        if df.empty or len(df) < 10:
            return {}

        session = self._detect_session()
        data = df.copy()

        # Ensure we have a time-based index
        if not isinstance(data.index, pd.DatetimeIndex):
            return {"phase": "unknown", "session": session}

        # Get today's Asian session candles (00:00-08:00 UTC)
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        asian_end = now.replace(hour=8, minute=0, second=0, microsecond=0)

        # Filter candles to today's Asian session
        asian_candles = data[
            (data.index >= today_start) & (data.index < asian_end)
        ]

        if asian_candles.empty:
            # Try yesterday's Asian session if today's hasn't started yet
            from datetime import timedelta
            yesterday_start = today_start - timedelta(days=1)
            yesterday_asian_end = asian_end - timedelta(days=1)
            asian_candles = data[
                (data.index >= yesterday_start) & (data.index < yesterday_asian_end)
            ]

        if asian_candles.empty:
            return {"phase": "unknown", "session": session}

        asian_high = float(asian_candles["high"].max())
        asian_low = float(asian_candles["low"].min())
        asian_range = asian_high - asian_low
        asian_mid = (asian_high + asian_low) / 2

        result: Dict[str, Any] = {
            "session": session,
            "asian_high": asian_high,
            "asian_low": asian_low,
            "asian_range": asian_range,
            "direction_bias": None,
        }

        if session == "ASIAN":
            result["phase"] = "accumulation"
        elif session == "LONDON":
            result["phase"] = "manipulation"
            # Check if price broke the Asian range aggressively
            if current_price is not None:
                if current_price > asian_high:
                    # London broke above Asian range → likely manipulation up
                    # Real direction may be DOWN (manipulation = fake move)
                    result["direction_bias"] = "bearish"
                    result["manipulation_direction"] = "up"
                elif current_price < asian_low:
                    # London broke below Asian range → likely manipulation down
                    # Real direction may be UP
                    result["direction_bias"] = "bullish"
                    result["manipulation_direction"] = "down"
        elif session in ("OVERLAP", "NEW_YORK"):
            result["phase"] = "distribution"
            # Check if price reversed from London manipulation
            # Get London candles (08:00-12:00 UTC)
            london_start = now.replace(hour=8, minute=0, second=0, microsecond=0)
            london_end = now.replace(hour=12, minute=0, second=0, microsecond=0)
            london_candles = data[
                (data.index >= london_start) & (data.index < london_end)
            ]

            if not london_candles.empty and current_price is not None:
                london_high = float(london_candles["high"].max())
                london_low = float(london_candles["low"].min())

                # London went above Asian high, now NY reversing back down
                if london_high > asian_high and current_price < asian_mid:
                    result["direction_bias"] = "bearish"
                # London went below Asian low, now NY reversing back up
                elif london_low < asian_low and current_price > asian_mid:
                    result["direction_bias"] = "bullish"
                # NY continuing above Asian range (genuine breakout)
                elif current_price > asian_high:
                    result["direction_bias"] = "bullish"
                # NY continuing below Asian range (genuine breakdown)
                elif current_price < asian_low:
                    result["direction_bias"] = "bearish"
        else:
            result["phase"] = "off_hours"

        return result

    # ── SMT Divergence Detection (SMC Workshop) ──────────────────────

    def _detect_smt_divergence(
        self, instrument: str, df: pd.DataFrame
    ) -> Optional[str]:
        """
        Detect Smart Money Technique (SMT) divergence by comparing swing
        highs/lows of correlated pairs.

        When correlated assets make divergent swing structures, it signals
        weakness in the current move:
        - Instrument makes higher high but correlated pair doesn't → bearish
        - Instrument makes lower low but correlated pair doesn't → bullish
        """
        if df.empty or len(df) < 20:
            return None

        data = df.reset_index(drop=True)

        # Find recent swing highs and lows
        swing_highs: List[Tuple[int, float]] = []
        swing_lows: List[Tuple[int, float]] = []

        for i in range(2, len(data) - 2):
            if (data["high"].iloc[i] > data["high"].iloc[i - 1] and
                data["high"].iloc[i] > data["high"].iloc[i + 1]):
                swing_highs.append((i, float(data["high"].iloc[i])))
            if (data["low"].iloc[i] < data["low"].iloc[i - 1] and
                data["low"].iloc[i] < data["low"].iloc[i + 1]):
                swing_lows.append((i, float(data["low"].iloc[i])))

        if len(swing_highs) < 2 or len(swing_lows) < 2:
            # Store what we have and return
            MarketAnalyzer._smt_cache[instrument] = {
                "last_swing_high": swing_highs[-1][1] if swing_highs else None,
                "last_swing_low": swing_lows[-1][1] if swing_lows else None,
                "prev_swing_high": swing_highs[-2][1] if len(swing_highs) >= 2 else None,
                "prev_swing_low": swing_lows[-2][1] if len(swing_lows) >= 2 else None,
            }
            return None

        # Store current instrument's swing data in class-level cache
        current_data = {
            "last_swing_high": swing_highs[-1][1],
            "last_swing_low": swing_lows[-1][1],
            "prev_swing_high": swing_highs[-2][1],
            "prev_swing_low": swing_lows[-2][1],
        }
        MarketAnalyzer._smt_cache[instrument] = current_data

        # Determine if current instrument made higher high or lower low
        made_higher_high = current_data["last_swing_high"] > current_data["prev_swing_high"]
        made_lower_low = current_data["last_swing_low"] < current_data["prev_swing_low"]

        # Find correlated pair from config
        try:
            from config import settings
            correlated_instruments = []
            for group in settings.correlation_groups:
                if instrument in group:
                    correlated_instruments = [p for p in group if p != instrument]
                    break
        except Exception:
            return None

        if not correlated_instruments:
            return None

        # Check against cached data for correlated instruments
        for corr_inst in correlated_instruments:
            corr_data = MarketAnalyzer._smt_cache.get(corr_inst)
            if not corr_data:
                continue

            corr_prev_high = corr_data.get("prev_swing_high")
            corr_last_high = corr_data.get("last_swing_high")
            corr_prev_low = corr_data.get("prev_swing_low")
            corr_last_low = corr_data.get("last_swing_low")

            if corr_prev_high is None or corr_last_high is None:
                continue
            if corr_prev_low is None or corr_last_low is None:
                continue

            corr_made_higher_high = corr_last_high > corr_prev_high
            corr_made_lower_low = corr_last_low < corr_prev_low

            # Gap 9: For negatively correlated pairs (e.g. EUR/USD vs DXY),
            # invert the comparison — they should move opposite, so SAME
            # direction = divergence.
            is_negative = (
                NEGATIVE_CORRELATIONS.get(instrument) == corr_inst
                or NEGATIVE_CORRELATIONS.get(corr_inst) == instrument
            )

            if is_negative:
                # Negative correlation: divergence = both moving same way
                # Bearish SMT: instrument HH AND correlated also HH (should be LL)
                if made_higher_high and corr_made_higher_high:
                    logger.debug(
                        f"SMT Divergence BEARISH (neg-corr): {instrument} HH "
                        f"and {corr_inst} also HH (should diverge)"
                    )
                    return "bearish"
                # Bullish SMT: instrument LL AND correlated also LL (should be HH)
                if made_lower_low and corr_made_lower_low:
                    logger.debug(
                        f"SMT Divergence BULLISH (neg-corr): {instrument} LL "
                        f"and {corr_inst} also LL (should diverge)"
                    )
                    return "bullish"
            else:
                # Positive correlation (original logic):
                # Bearish SMT: instrument makes higher high but correlated doesn't
                if made_higher_high and not corr_made_higher_high:
                    logger.debug(
                        f"SMT Divergence BEARISH: {instrument} made HH but "
                        f"{corr_inst} did not"
                    )
                    return "bearish"

                # Bullish SMT: instrument makes lower low but correlated doesn't
                if made_lower_low and not corr_made_lower_low:
                    logger.debug(
                        f"SMT Divergence BULLISH: {instrument} made LL but "
                        f"{corr_inst} did not"
                    )
                    return "bullish"

        return None

    # ── Liquidity Pool Detection (SMC Workshop - Gap 6) ────────────────

    def _detect_liquidity_pools(
        self,
        candles: Dict[str, pd.DataFrame],
        key_levels: Dict[str, List],
        power_of_three: Dict[str, Any],
        current_price: Optional[float],
    ) -> Tuple[List[Dict], Optional[Dict[str, Any]]]:
        """
        Detect Liquidity Pools and sweep-then-reverse events.

        Liquidity pools form at:
        - Equal highs (multiple swing highs within 0.1% of each other)
        - Equal lows  (multiple swing lows within 0.1% of each other)
        - Previous Day High / Low (PDH / PDL)
        - Asian session high / low (from Power of Three data)

        Returns:
            (liquidity_pools, liquidity_sweep)
            - liquidity_pools: list of dicts with level, type, strength
            - liquidity_sweep: None or {"level": float, "direction": str}
        """
        pools: List[Dict] = []
        sweep: Optional[Dict[str, Any]] = None

        daily = candles.get("D", pd.DataFrame())
        h1 = candles.get("H1", pd.DataFrame())

        # --- Equal Highs / Equal Lows from daily swing points ---
        swing_highs: List[float] = []
        swing_lows: List[float] = []

        if not daily.empty:
            for i in range(2, len(daily) - 2):
                if (daily["high"].iloc[i] > daily["high"].iloc[i - 1] and
                        daily["high"].iloc[i] > daily["high"].iloc[i - 2] and
                        daily["high"].iloc[i] > daily["high"].iloc[i + 1] and
                        daily["high"].iloc[i] > daily["high"].iloc[i + 2]):
                    swing_highs.append(float(daily["high"].iloc[i]))
                if (daily["low"].iloc[i] < daily["low"].iloc[i - 1] and
                        daily["low"].iloc[i] < daily["low"].iloc[i - 2] and
                        daily["low"].iloc[i] < daily["low"].iloc[i + 1] and
                        daily["low"].iloc[i] < daily["low"].iloc[i + 2]):
                    swing_lows.append(float(daily["low"].iloc[i]))

        # Cluster equal highs (within 0.1% tolerance)
        tolerance = 0.001  # 0.1%
        used: set = set()
        for i, h in enumerate(swing_highs):
            if i in used:
                continue
            cluster = [h]
            for j in range(i + 1, len(swing_highs)):
                if j in used:
                    continue
                if abs(swing_highs[j] - h) / max(h, 1e-10) <= tolerance:
                    cluster.append(swing_highs[j])
                    used.add(j)
            if len(cluster) >= 2:
                avg_level = sum(cluster) / len(cluster)
                pools.append({
                    "level": avg_level,
                    "type": "equal_highs",
                    "strength": len(cluster),
                })

        used = set()
        for i, lo in enumerate(swing_lows):
            if i in used:
                continue
            cluster = [lo]
            for j in range(i + 1, len(swing_lows)):
                if j in used:
                    continue
                if abs(swing_lows[j] - lo) / max(lo, 1e-10) <= tolerance:
                    cluster.append(swing_lows[j])
                    used.add(j)
            if len(cluster) >= 2:
                avg_level = sum(cluster) / len(cluster)
                pools.append({
                    "level": avg_level,
                    "type": "equal_lows",
                    "strength": len(cluster),
                })

        # --- Previous Day High / Low (PDH / PDL) ---
        if not daily.empty and len(daily) >= 2:
            prev_day = daily.iloc[-2]
            pdh = float(prev_day["high"])
            pdl = float(prev_day["low"])
            pools.append({"level": pdh, "type": "pdh", "strength": 1})
            pools.append({"level": pdl, "type": "pdl", "strength": 1})

        # --- Asian session High / Low (if Power of Three data available) ---
        asian_high = power_of_three.get("asian_high")
        asian_low = power_of_three.get("asian_low")
        if asian_high is not None:
            pools.append({"level": asian_high, "type": "asian_high", "strength": 1})
        if asian_low is not None:
            pools.append({"level": asian_low, "type": "asian_low", "strength": 1})

        # --- Sweep-then-reverse detection ---
        # Check if the most recent H1 candles swept a liquidity level and reversed
        if not h1.empty and len(h1) >= 3 and current_price is not None and pools:
            recent_high = float(h1.iloc[-1]["high"])
            recent_low = float(h1.iloc[-1]["low"])
            prev_close = float(h1.iloc[-2]["close"])

            for pool in pools:
                lvl = pool["level"]
                ptype = pool["type"]

                # Swept highs: wick went above level but close came back below
                if ptype in ("equal_highs", "pdh", "asian_high"):
                    if recent_high > lvl and current_price < lvl and prev_close < lvl:
                        sweep = {"level": lvl, "direction": "swept_highs"}
                        break

                # Swept lows: wick went below level but close came back above
                if ptype in ("equal_lows", "pdl", "asian_low"):
                    if recent_low < lvl and current_price > lvl and prev_close > lvl:
                        sweep = {"level": lvl, "direction": "swept_lows"}
                        break

        return pools, sweep

    # ── Premium / Discount Zone Detection (TradingLab SMC) ────────────

    def _detect_premium_discount(
        self, df: pd.DataFrame, current_price: Optional[float]
    ) -> Optional[str]:
        """
        Detect whether price is in the Premium or Discount zone.

        From TradingLab SMC:
        - Use the recent daily swing range (high to low over last 20-60 candles).
        - Binary split at 50% of the Fibonacci range:
          * Premium  : above 50% (favor SELL setups)
          * Discount : below 50% (favor BUY setups)

        Returns "premium", "discount", or None.
        """
        if df.empty or len(df) < 20 or current_price is None:
            return None

        recent = df.tail(60)
        swing_high = float(recent["high"].max())
        swing_low = float(recent["low"].min())
        rng = swing_high - swing_low

        if rng <= 0:
            return None

        # Binary split at 50% of swing range (Fibonacci midpoint)
        # position = 0.0 at swing_low, 1.0 at swing_high
        position = (current_price - swing_low) / rng  # 0=low, 1=high

        if position > 0.5:
            return "premium"
        else:
            return "discount"
