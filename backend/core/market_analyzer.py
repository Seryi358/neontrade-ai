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
    # TradingLab AT Básico: Consolidation = extended deceleration
    # (correction in time, not price — price stays in a narrow range)
    CONSOLIDATING = "consolidating"


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
    # MACD divergence detection (required for Black strategy and Scalping)
    macd_divergence: Optional[str] = None  # "bullish", "bearish", or None
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
    # Session detail: distinguishes TOKYO vs SYDNEY within ASIAN block
    session_detail: Optional[str] = None
    # Elliott Wave detail from daily candle analysis
    elliott_wave_detail: Dict[str, Any] = field(default_factory=dict)
    # Pivot Points (P, S1, R1) from daily data — mentorship only uses these three
    pivot_points: Dict[str, float] = field(default_factory=dict)
    # Premium/Discount zone: dict with zone, position, swing levels, sweet_spot, or None
    premium_discount_zone: Optional[Dict[str, Any]] = None
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
    # Swing highs/lows from H1 structure detection (used by PINK/WHITE TP calc)
    swing_highs: List[float] = field(default_factory=list)
    swing_lows: List[float] = field(default_factory=list)


class MarketAnalyzer:
    """Multi-timeframe market analysis engine."""

    def __init__(self, broker_client):
        self.broker = broker_client
        # Instance-level cache for SMT divergence: stores last swing high/low per instrument
        self._smt_cache: Dict[str, Dict] = {}

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
            "M2": 200,   # ~6.6 hours of 2m, needed for CPA Day Trading (Alex: "2 minutos")
            "M1": 200,   # ~3.3 hours, needed for scalping position management
        }

        for tf, count in timeframes.items():
            try:
                raw = await self.broker.get_candles(instrument, tf, count)
                candles[tf] = self._candles_to_dataframe(raw)
            except Exception as e:
                # M2 is expected to fail on Capital.com (no MINUTE_2 resolution)
                # Use debug level to avoid flooding logs with known 404s
                if tf == "M2":
                    logger.debug(f"M2 candles unavailable for {instrument} (expected, using M1 fallback)")
                else:
                    logger.error(f"Failed to get {tf} candles for {instrument}: {e}")
                candles[tf] = pd.DataFrame()

                # M2 fallback: use M1 candles for M2 EMA computation
                if tf == "M2" and "M1" in candles and not candles["M1"].empty:
                    candles["M2"] = candles["M1"].copy()
            # Throttle between timeframe fetches to avoid broker rate limits
            await asyncio.sleep(0.3)

        # Derive Monthly candles from Weekly data (Capital.com has no MONTH resolution)
        # Needed for swing MTFA direction chart (TradingLab: Monthly = directional for swing)
        try:
            w_df = candles.get("W", pd.DataFrame())
            if not w_df.empty:
                w_copy = w_df.copy()
                # Weekly DF has time in the index (set_index("time") during _candles_to_dataframe)
                # so use the index directly for month grouping
                if isinstance(w_copy.index, pd.DatetimeIndex):
                    # Strip timezone before converting to Period to avoid pandas warning
                    w_copy["month"] = w_copy.index.tz_localize(None).to_period("M") if w_copy.index.tz else w_copy.index.to_period("M")
                elif "date" in w_copy.columns:
                    w_copy["month"] = pd.to_datetime(w_copy["date"]).dt.to_period("M")
                else:
                    w_copy["month"] = pd.to_datetime(w_copy.index).to_period("M")
                agg_dict = {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                }
                if "date" in w_copy.columns:
                    agg_dict["date"] = "last"
                monthly = w_copy.groupby("month").agg(agg_dict).reset_index(drop=True)
                if "volume" in w_copy.columns:
                    vol = w_copy.groupby("month")["volume"].sum().reset_index(drop=True)
                    monthly["volume"] = vol
                candles["M"] = monthly
            else:
                candles["M"] = pd.DataFrame()
        except Exception as e:
            logger.warning(f"Failed to derive Monthly candles from Weekly: {e}")
            candles["M"] = pd.DataFrame()

        # Step 2: HTF Analysis (direction TF depends on trading style per TradingLab MTFA)
        # Swing: Monthly is the direction TF
        # Day Trading: Daily is the direction TF
        # Scalping: H1 is the direction TF
        from config import settings
        _style = getattr(settings, "trading_style", "day_trading")
        if _style == "swing":
            htf_trend = self._detect_trend(candles.get("M", pd.DataFrame()))
        elif _style == "scalping":
            htf_trend = self._detect_trend(candles.get("H1", pd.DataFrame()))
        else:  # day_trading (default)
            htf_trend = self._detect_trend(candles.get("D", pd.DataFrame()))
        htf_condition = self._detect_condition(candles.get("D", pd.DataFrame()))

        # Step 2b: H4 Analysis (MTFA bridge: strategy selection + RSI overbought/oversold)
        # TradingLab MTFA: H4 is the critical intermediate timeframe where you determine
        # which strategy to apply and check RSI overbought/oversold conditions.
        h4_trend = self._detect_trend(candles.get("H4", pd.DataFrame()))
        h4_condition = self._detect_condition(candles.get("H4", pd.DataFrame()))

        # Step 3: LTF Analysis (H1 structure + execution)
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

        # Step 8: MACD (H1, M15 + Daily from TradingLab)
        # M5 MACD removed: mentorship says "en cinco minutos no utilizo MACD ni
        # RSI porque lo veo ya demasiado volatil". M5 MACD only available via
        # scalping engine explicit opt-in (scalping_engine.py).
        macd_values = {}
        for tf in ("D", "H1", "M15"):
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

        # MACD divergence on H1 (mentorship: "MACD divergence on 1H is always present in Black strategy")
        macd_divergence = self._detect_macd_divergence(
            candles.get("H1", pd.DataFrame())
        )

        # Step 11: BOS/CHOCH first (needed by OB detection)
        structure_breaks = self._detect_structure_breaks(
            candles.get("H1", pd.DataFrame())
        )

        # Step 12: Order Blocks (from SMC workshop) - linked to structure breaks
        order_blocks = self._detect_order_blocks(
            candles.get("H1", pd.DataFrame()), structure_breaks
        )

        # Step 12b: Extract swing highs/lows from H1 (used by PINK/WHITE TP calc)
        swing_highs_list: List[float] = []
        swing_lows_list: List[float] = []
        h1_df = candles.get("H1", pd.DataFrame())
        if not h1_df.empty and len(h1_df) >= 5:
            h1_data = h1_df.reset_index(drop=True)
            for i in range(2, len(h1_data) - 2):
                if (h1_data["high"].iloc[i] > h1_data["high"].iloc[i-1] and
                        h1_data["high"].iloc[i] > h1_data["high"].iloc[i+1]):
                    swing_highs_list.append(float(h1_data["high"].iloc[i]))
                if (h1_data["low"].iloc[i] < h1_data["low"].iloc[i-1] and
                        h1_data["low"].iloc[i] < h1_data["low"].iloc[i+1]):
                    swing_lows_list.append(float(h1_data["low"].iloc[i]))

        # Step 13a: Volume analysis on H1, M15 and M5 (TradingLab course)
        volume_analysis = {}
        for tf in ("H1", "M15", "M5"):
            df = candles.get(tf, pd.DataFrame())
            if not df.empty:
                vol_data = self._analyze_volume(df)
                if vol_data:
                    volume_analysis[tf] = vol_data

        # Step 13b: Extract convenience fields
        # EMA_W_8: mentorship Class 3 — weekly close below EMA 8 signals corrective move
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
        session, session_detail = self._detect_session()

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
            # Check if last close is below both BMSB bands
            last_below = last_weekly_close < sma_20 and last_weekly_close < ema_21
            # 2-close confirmation: need at least 2 consecutive weekly closes
            # below both SMA 20 and EMA 21 to confirm bearish (per mentorship).
            bearish_confirmed = False
            if last_below and len(weekly_closes) >= 2:
                prev_weekly_close = weekly_closes[-2]
                # Recalculate SMA 20 and EMA 21 as of the previous week
                if len(weekly_closes) >= 21:
                    prev_sma_20 = sum(weekly_closes[-21:-1]) / 20
                    prev_ema_21 = weekly_closes[0]
                    for price_val in weekly_closes[1:-1]:
                        prev_ema_21 = (price_val - prev_ema_21) * multiplier + prev_ema_21
                    bearish_confirmed = (
                        prev_weekly_close < prev_sma_20
                        and prev_weekly_close < prev_ema_21
                    )
            bmsb = {
                "sma_20": sma_20,
                "ema_21": ema_21,
                "bullish": last_weekly_close > sma_20 and last_weekly_close > ema_21,
                "bearish": bearish_confirmed,
                "bearish_warning": last_below and not bearish_confirmed,
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
            macd_divergence=macd_divergence,
            order_blocks=order_blocks,
            structure_breaks=structure_breaks,
            score=score,
            volume_analysis=volume_analysis,
            ema_w8=ema_w8_val,
            sma_d200=sma_d200_val,
            last_candles=last_candles,
            current_price=current_price,
            session=session,
            session_detail=session_detail,
            elliott_wave=f"Wave {elliott_wave_detail.get('wave_count', '?')}" if elliott_wave_detail else None,
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
            swing_highs=swing_highs_list,
            swing_lows=swing_lows_list,
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
        """
        Detect trend using structure-based swing analysis (primary) with
        EMA 20/50 as confirmation and SMA 200 as long-term filter.

        Structure rules:
          - Higher Highs + Higher Lows = BULLISH
          - Lower Highs + Lower Lows = BEARISH
          - Mixed = RANGING (unless EMA/SMA override)

        EMA 20/50 confirmation: must agree with structure for a definitive call.
        SMA 200: long-term trend filter (price above = bullish bias, below = bearish).
        """
        if df.empty or len(df) < 50:
            return Trend.RANGING

        data = df.reset_index(drop=True)

        # ── Step 1: Swing high/low analysis (primary) ──
        swing_highs: List[Tuple[int, float]] = []
        swing_lows: List[Tuple[int, float]] = []
        for i in range(2, len(data) - 2):
            if (data["high"].iloc[i] > data["high"].iloc[i - 1] and
                data["high"].iloc[i] > data["high"].iloc[i + 1]):
                swing_highs.append((i, float(data["high"].iloc[i])))
            if (data["low"].iloc[i] < data["low"].iloc[i - 1] and
                data["low"].iloc[i] < data["low"].iloc[i + 1]):
                swing_lows.append((i, float(data["low"].iloc[i])))

        structure_trend = Trend.RANGING
        if len(swing_highs) >= 2 and len(swing_lows) >= 2:
            hh = swing_highs[-1][1] > swing_highs[-2][1]  # higher high
            hl = swing_lows[-1][1] > swing_lows[-2][1]    # higher low
            lh = swing_highs[-1][1] < swing_highs[-2][1]  # lower high
            ll = swing_lows[-1][1] < swing_lows[-2][1]    # lower low

            if hh and hl:
                structure_trend = Trend.BULLISH
            elif lh and ll:
                structure_trend = Trend.BEARISH

        # ── Step 2: EMA 20/50 confirmation ──
        ema_20 = df["close"].ewm(span=20).mean()
        ema_50 = df["close"].ewm(span=50).mean()
        current_price = float(df["close"].iloc[-1])
        ema20_val = float(ema_20.iloc[-1])
        ema50_val = float(ema_50.iloc[-1])

        ema_bullish = current_price > ema20_val > ema50_val
        ema_bearish = current_price < ema20_val < ema50_val

        # ── Step 3: SMA 200 long-term filter ──
        sma_200_bullish = False
        sma_200_bearish = False
        if len(df) >= 200:
            sma_200 = float(df["close"].rolling(200).mean().iloc[-1])
            sma_200_bullish = current_price > sma_200
            sma_200_bearish = current_price < sma_200

        # ── Step 4: Combine signals ──
        # Structure is primary; EMA confirms; SMA 200 is the long-term filter
        if structure_trend == Trend.BULLISH:
            # Structure says bullish — confirmed if EMA agrees or SMA 200 agrees
            if ema_bullish or sma_200_bullish:
                return Trend.BULLISH
            # Structure bullish but no confirmation — still bullish (structure wins)
            return Trend.BULLISH
        elif structure_trend == Trend.BEARISH:
            if ema_bearish or sma_200_bearish:
                return Trend.BEARISH
            return Trend.BEARISH
        else:
            # Structure is ranging — fall back to EMA + SMA 200
            if ema_bullish and sma_200_bullish:
                return Trend.BULLISH
            elif ema_bearish and sma_200_bearish:
                return Trend.BEARISH
            return Trend.RANGING

    def _detect_condition(self, df: pd.DataFrame) -> MarketCondition:
        """
        Detect market condition: overbought/oversold AND acceleration/deceleration.

        Acceleration/deceleration is critical for BLUE, RED, BLACK strategy detection:
        - ACCELERATING: candles getting larger, price moving away from EMA 50
        - DECELERATING: candles getting smaller, price approaching EMA 50

        Priority: overbought/oversold extremes take precedence, then accel/decel,
        then neutral.
        """
        if df.empty or len(df) < 50:
            return MarketCondition.NEUTRAL

        # ── RSI for overbought/oversold (Wilder's smoothing, matches TradingView) ──
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()

        # Bug fix R26: handle both gain and loss = 0 (no movement) → RSI=50 (neutral)
        last_gain = float(gain.iloc[-1]) if not gain.empty else 0.0
        last_loss = float(loss.iloc[-1]) if not loss.empty else 0.0
        if last_gain == 0 and last_loss == 0:
            current_rsi = 50.0  # No movement = neutral, not overbought
        else:
            rs = gain / loss.replace(0, np.nan)
            rsi = 100 - (100 / (1 + rs))
            rsi = rsi.fillna(100.0)
            current_rsi = float(rsi.iloc[-1])

        # Bug fix R26: Don't return early on overbought/oversold — check deceleration
        # too, since BLACK strategy needs both overbought AND deceleration.
        # Store RSI state and continue to accel/decel detection.
        rsi_condition = None
        if current_rsi > 70:
            rsi_condition = MarketCondition.OVERBOUGHT
        elif current_rsi < 30:
            rsi_condition = MarketCondition.OVERSOLD

        # ── Acceleration / Deceleration detection ──
        # Metric 1: Candle body size trend (last 5 vs previous 5)
        if len(df) < 10:
            return MarketCondition.NEUTRAL

        bodies = (df["close"] - df["open"]).abs()
        recent_bodies = bodies.iloc[-5:]
        prev_bodies = bodies.iloc[-10:-5]
        avg_recent_body = float(recent_bodies.mean())
        avg_prev_body = float(prev_bodies.mean())

        # Metric 2: Distance from EMA 50 (expanding = accel, contracting = decel)
        ema_50 = df["close"].ewm(span=50).mean()
        recent_dist = float((df["close"].iloc[-5:] - ema_50.iloc[-5:]).abs().mean())
        prev_dist = float((df["close"].iloc[-10:-5] - ema_50.iloc[-10:-5]).abs().mean())

        # Combine both metrics
        body_expanding = avg_recent_body > avg_prev_body * 1.15  # 15% larger
        body_contracting = avg_recent_body < avg_prev_body * 0.85  # 15% smaller
        dist_expanding = recent_dist > prev_dist * 1.1  # moving away from EMA 50
        dist_contracting = recent_dist < prev_dist * 0.9  # approaching EMA 50

        # ACCELERATING: candles getting larger AND/OR moving away from EMA 50
        if body_expanding and dist_expanding:
            return MarketCondition.ACCELERATING
        elif body_expanding or dist_expanding:
            # One signal is enough if the other is not contradicting
            if not body_contracting and not dist_contracting:
                return MarketCondition.ACCELERATING

        # DECELERATING: candles getting smaller AND/OR approaching EMA 50
        if body_contracting and dist_contracting:
            # Check for CONSOLIDATING (TradingLab AT Básico):
            # Consolidation = extended deceleration where price stays in a
            # narrow range relative to its recent movement (correction in time,
            # not in price). If last 10 candles are range-bound, it's consolidation.
            if len(df) >= 15:
                recent_range = float(df["high"].iloc[-10:].max() - df["low"].iloc[-10:].min())
                prior_range = float(df["high"].iloc[-20:-10].max() - df["low"].iloc[-20:-10].min()) if len(df) >= 20 else recent_range
                # Narrow range + small bodies = consolidation (correction in time)
                if prior_range > 0 and recent_range < prior_range * 0.5:
                    return MarketCondition.CONSOLIDATING
            return MarketCondition.DECELERATING
        elif body_contracting or dist_contracting:
            if not body_expanding and not dist_expanding:
                return MarketCondition.DECELERATING

        # Bug fix R26: If RSI detected overbought/oversold but we also found
        # deceleration above, that was returned. If we reach here (no accel/decel),
        # return the RSI condition (overbought/oversold) or NEUTRAL.
        if rsi_condition is not None:
            return rsi_condition

        return MarketCondition.NEUTRAL

    def _find_key_levels(self, candles: Dict[str, pd.DataFrame]) -> Dict[str, List]:
        """
        Find support, resistance, and Fair Value Gap (FVG) levels.

        S/R levels include zone width (not just exact prices), touch count,
        and recency weighting for prioritization.
        """
        levels: Dict[str, List] = {
            "supports": [],
            "resistances": [],
            "fvg": [],          # backward-compatible: list of midpoint floats
            "fvg_zones": [],    # full FVG data model (Gap 7)
        }

        daily = candles.get("D", pd.DataFrame())
        if daily.empty:
            return levels

        total_candles = len(daily)

        # Find swing highs and lows from daily with index for recency
        raw_resistances: List[Tuple[float, int]] = []  # (price, index)
        raw_supports: List[Tuple[float, int]] = []
        for i in range(2, len(daily) - 2):
            # Swing high
            if (daily["high"].iloc[i] > daily["high"].iloc[i-1] and
                daily["high"].iloc[i] > daily["high"].iloc[i-2] and
                daily["high"].iloc[i] > daily["high"].iloc[i+1] and
                daily["high"].iloc[i] > daily["high"].iloc[i+2]):
                raw_resistances.append((float(daily["high"].iloc[i]), i))

            # Swing low
            if (daily["low"].iloc[i] < daily["low"].iloc[i-1] and
                daily["low"].iloc[i] < daily["low"].iloc[i-2] and
                daily["low"].iloc[i] < daily["low"].iloc[i+1] and
                daily["low"].iloc[i] < daily["low"].iloc[i+2]):
                raw_supports.append((float(daily["low"].iloc[i]), i))

        # Cluster nearby levels into zones with touch count and recency
        def _cluster_levels(
            raw_levels: List[Tuple[float, int]],
            zone_tolerance: float = 0.002,
        ) -> List[Dict]:
            """
            Cluster raw price levels within zone_tolerance (0.2%) into zones.
            Returns list of dicts with price, zone_high, zone_low, touches, recency_score.
            """
            if not raw_levels:
                return []
            sorted_levels = sorted(raw_levels, key=lambda x: x[0])
            clusters: List[List[Tuple[float, int]]] = []
            current_cluster = [sorted_levels[0]]

            for price, idx in sorted_levels[1:]:
                cluster_avg = sum(p for p, _ in current_cluster) / len(current_cluster)
                if cluster_avg > 0 and abs(price - cluster_avg) / cluster_avg <= zone_tolerance:
                    current_cluster.append((price, idx))
                else:
                    clusters.append(current_cluster)
                    current_cluster = [(price, idx)]
            clusters.append(current_cluster)

            result = []
            for cluster in clusters:
                prices = [p for p, _ in cluster]
                indices = [idx for _, idx in cluster]
                avg_price = sum(prices) / len(prices)
                zone_high = max(prices)
                zone_low = min(prices)
                touches = len(cluster)
                # Recency: higher score for more recent levels (0.0 to 1.0)
                max_idx = max(indices)
                recency_score = max_idx / total_candles if total_candles > 0 else 0.5
                result.append({
                    "price": round(avg_price, 5),
                    "zone_high": round(zone_high, 5),
                    "zone_low": round(zone_low, 5),
                    "touches": touches,
                    "recency": round(recency_score, 3),
                })
            return result

        support_zones = _cluster_levels(raw_supports)
        resistance_zones = _cluster_levels(raw_resistances)

        # Sort by combined score: touches * recency (most relevant first)
        for zone in support_zones:
            zone["score"] = round(zone["touches"] * zone["recency"], 3)
        for zone in resistance_zones:
            zone["score"] = round(zone["touches"] * zone["recency"], 3)

        support_zones.sort(key=lambda z: z["score"], reverse=True)
        resistance_zones.sort(key=lambda z: z["score"], reverse=True)

        # Store as plain floats for backward compatibility with strategies/base.py
        # (strategies expect sorted lists of float prices, not zone dicts)
        levels["supports"] = [z["price"] for z in support_zones[:10]]
        levels["resistances"] = [z["price"] for z in resistance_zones[:10]]
        # Also store full zone data for advanced SMC analysis
        levels["support_zones"] = support_zones[:10]
        levels["resistance_zones"] = resistance_zones[:10]

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

        # --- M15 FVG detection (critical for entry timing per workshop) ---
        m15 = candles.get("M15", pd.DataFrame())
        if not m15.empty:
            for i in range(2, len(m15)):
                # Bullish FVG: candle[i] low > candle[i-2] high
                if m15["low"].iloc[i] > m15["high"].iloc[i-2]:
                    high_boundary = float(m15["low"].iloc[i])
                    low_boundary = float(m15["high"].iloc[i-2])
                    midpoint = (high_boundary + low_boundary) / 2
                    levels["fvg"].append(midpoint)
                    fvg_zones.append({
                        "high": high_boundary,
                        "low": low_boundary,
                        "mid": midpoint,
                        "direction": "bullish",
                        "filled": False,
                        "timeframe": "M15",
                        "index": i,
                    })
                # Bearish FVG: candle[i] high < candle[i-2] low
                elif m15["high"].iloc[i] < m15["low"].iloc[i-2]:
                    high_boundary = float(m15["low"].iloc[i-2])
                    low_boundary = float(m15["high"].iloc[i])
                    midpoint = (high_boundary + low_boundary) / 2
                    levels["fvg"].append(midpoint)
                    fvg_zones.append({
                        "high": high_boundary,
                        "low": low_boundary,
                        "mid": midpoint,
                        "direction": "bearish",
                        "filled": False,
                        "timeframe": "M15",
                        "index": i,
                    })

            # Check M15 FVG fills
            m15_fvgs = [f for f in fvg_zones if f.get("timeframe") == "M15"]
            for fvg in m15_fvgs:
                fvg_idx = fvg["index"]
                for j in range(fvg_idx + 1, len(m15)):
                    candle_low = float(m15["low"].iloc[j])
                    candle_high = float(m15["high"].iloc[j])

                    if fvg["direction"] == "bullish":
                        if candle_low <= fvg["low"]:
                            fvg["filled"] = True
                            break
                    else:
                        if candle_high >= fvg["high"]:
                            fvg["filled"] = True
                            break

                    if not fvg.get("reacted"):
                        if fvg["direction"] == "bullish" and candle_low <= fvg["high"]:
                            fvg["reacted"] = True
                        elif fvg["direction"] == "bearish" and candle_high >= fvg["low"]:
                            fvg["reacted"] = True

                    if not fvg.get("partially_filled"):
                        if fvg["direction"] == "bullish" and candle_low <= fvg["mid"]:
                            fvg["partially_filled"] = True
                        elif fvg["direction"] == "bearish" and candle_high >= fvg["mid"]:
                            fvg["partially_filled"] = True

        # Keep only recent FVG levels (S/R already limited in clustering above)
        levels["fvg"] = levels["fvg"][-20:]
        levels["fvg_zones"] = fvg_zones[-20:]

        return levels

    @staticmethod
    def verify_sr_breakout(
        df: pd.DataFrame,
        level: float,
        direction: str = "bullish",
    ) -> Dict[str, bool]:
        """
        TradingLab AT Básico — 3-step S/R breakout verification:
          1) BREAK:   price crosses the level
          2) CLOSE:   candle closes beyond the level
          3) CONFIRM: next candle continues in the breakout direction

        A failed step-3 (false breakout) is itself a powerful reversal signal.

        Args:
            df: OHLC DataFrame (needs at least 2 recent candles).
            level: the S/R price level.
            direction: "bullish" (breaks above resistance) or "bearish" (breaks below support).

        Returns:
            Dict with keys: broke, closed, confirmed, false_breakout.
        """
        result = {"broke": False, "closed": False, "confirmed": False, "false_breakout": False}
        if df.empty or len(df) < 2:
            return result

        prev = df.iloc[-2]
        last = df.iloc[-1]

        if direction == "bullish":
            # Step 1: price crossed above
            result["broke"] = float(prev["high"]) > level
            # Step 2: candle closed above
            result["closed"] = float(prev["close"]) > level
            # Step 3: next candle continues bullish (higher close)
            if result["closed"]:
                result["confirmed"] = float(last["close"]) > float(prev["close"])
                if not result["confirmed"] and float(last["close"]) < level:
                    result["false_breakout"] = True
        else:  # bearish
            result["broke"] = float(prev["low"]) < level
            result["closed"] = float(prev["close"]) < level
            if result["closed"]:
                result["confirmed"] = float(last["close"]) < float(prev["close"])
                if not result["confirmed"] and float(last["close"]) > level:
                    result["false_breakout"] = True

        return result

    def _verify_sr_breakout(
        self,
        candles: pd.DataFrame,
        level: float,
        direction: str,
    ) -> Dict[str, Any]:
        """
        Alex's three-step S/R breakout verification (AT Basico):
          1) BREAK:   Price crosses the S/R level (wick or body)
          2) CLOSE:   A candle closes beyond the level (not just wick)
          3) CONFIRM: The NEXT candle continues in the breakout direction

        Uses the last 5 candles to check for recent breakout attempts.
        A break without close/confirm is flagged as a false breakout —
        itself a powerful reversal signal per the mentorship.

        Args:
            candles: OHLC DataFrame (needs at least 2 candles).
            level: The support/resistance price level.
            direction: "BUY" (break above resistance) or "SELL" (break below support).

        Returns:
            Dict with verified, step_1_break, step_2_close, step_3_confirm, false_breakout.
        """
        result: Dict[str, Any] = {
            "verified": False,
            "step_1_break": False,
            "step_2_close": False,
            "step_3_confirm": False,
            "false_breakout": False,
        }

        if candles.empty or len(candles) < 2:
            return result

        # Use last 5 candles (or fewer if not available)
        recent = candles.tail(5)
        if len(recent) < 2:
            return result

        direction_upper = direction.upper()

        if direction_upper == "BUY":
            # Step 1: Any candle's high crossed above the level
            for i in range(len(recent) - 1):
                if float(recent.iloc[i]["high"]) > level:
                    result["step_1_break"] = True
                    # Step 2: That candle closed above the level
                    if float(recent.iloc[i]["close"]) > level:
                        result["step_2_close"] = True
                        # Step 3: The next candle continues upward
                        next_idx = i + 1
                        if next_idx < len(recent):
                            next_close = float(recent.iloc[next_idx]["close"])
                            prev_close = float(recent.iloc[i]["close"])
                            if next_close > prev_close:
                                result["step_3_confirm"] = True
                                result["verified"] = True
                                return result
                    break  # Only check the first break attempt
        else:  # SELL
            # Step 1: Any candle's low crossed below the level
            for i in range(len(recent) - 1):
                if float(recent.iloc[i]["low"]) < level:
                    result["step_1_break"] = True
                    # Step 2: That candle closed below the level
                    if float(recent.iloc[i]["close"]) < level:
                        result["step_2_close"] = True
                        # Step 3: The next candle continues downward
                        next_idx = i + 1
                        if next_idx < len(recent):
                            next_close = float(recent.iloc[next_idx]["close"])
                            prev_close = float(recent.iloc[i]["close"])
                            if next_close < prev_close:
                                result["step_3_confirm"] = True
                                result["verified"] = True
                                return result
                    break  # Only check the first break attempt

        # If we broke but didn't fully verify, it's a false breakout
        if result["step_1_break"] and not result["verified"]:
            result["false_breakout"] = True

        return result

    def _calculate_emas(self, candles: Dict[str, pd.DataFrame]) -> Dict[str, float]:
        """Calculate EMA values for multiple timeframes."""
        emas = {}
        ema_configs = {
            "M": [20],     # EMA 20 Monthly — swing trading direction filter (derived from W)
            "W": [8, 50],  # EMA 8 Weekly: mentorship Class 3 (trend/close signal)
            "D": [20, 50],
            "H4": [20, 50],  # EMA 20 added per mentorship: "las tres medias en todos los gráficos"
            "H1": [20, 50],  # EMA 20 for small pullback detection on H1
            "M15": [5, 20, 50],
            "M5": [2, 5, 20, 50],
            # M2: Capital.com supports MINUTE_2 — needed for CPA Day Trading
            # Alex: "el corto plazo agresivo son 2 minutos"
            "M2": [5, 50],
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
                    ema_value = ema.iloc[-1]
                    if pd.isna(ema_value):
                        continue  # Skip NaN EMAs instead of storing them
                    emas[key] = ema_value

        return emas

    def _calculate_fibonacci(self, df: pd.DataFrame) -> Dict[str, float]:
        """
        Calculate Fibonacci retracement and extension levels from the most
        recent significant impulse swing (not a generic 60-day range).

        Identifies swing highs/lows, finds the last significant impulse move,
        and calculates Fibonacci from that specific swing. Includes both
        bearish (downward) and bullish (upward) extension projections.
        """
        if df.empty or len(df) < 20:
            return {}

        data = df.reset_index(drop=True)

        # Find swing highs and lows (5-bar pivots for significance)
        swing_points: List[Tuple[int, float, str]] = []
        for i in range(2, len(data) - 2):
            if (data["high"].iloc[i] > data["high"].iloc[i - 1] and
                data["high"].iloc[i] > data["high"].iloc[i - 2] and
                data["high"].iloc[i] > data["high"].iloc[i + 1] and
                data["high"].iloc[i] > data["high"].iloc[i + 2]):
                swing_points.append((i, float(data["high"].iloc[i]), "H"))
            if (data["low"].iloc[i] < data["low"].iloc[i - 1] and
                data["low"].iloc[i] < data["low"].iloc[i - 2] and
                data["low"].iloc[i] < data["low"].iloc[i + 1] and
                data["low"].iloc[i] < data["low"].iloc[i + 2]):
                swing_points.append((i, float(data["low"].iloc[i]), "L"))

        swing_points.sort(key=lambda s: s[0])

        swing_high = None
        swing_low = None
        impulse_direction = None  # "bearish" (H->L) or "bullish" (L->H)

        if len(swing_points) >= 2:
            # Find the most recent significant impulse swing
            for k in range(len(swing_points) - 1, 0, -1):
                curr = swing_points[k]
                prev = swing_points[k - 1]
                if curr[2] != prev[2]:
                    diff_candidate = abs(curr[1] - prev[1])
                    mid_price = (curr[1] + prev[1]) / 2
                    # Require minimum significance: at least 0.3% range
                    if mid_price > 0 and diff_candidate / mid_price < 0.003:
                        continue
                    if curr[2] == "L" and prev[2] == "H":
                        swing_high = prev[1]
                        swing_low = curr[1]
                        impulse_direction = "bearish"
                    elif curr[2] == "H" and prev[2] == "L":
                        swing_high = curr[1]
                        swing_low = prev[1]
                        impulse_direction = "bullish"
                    break

        # Fallback to simple high/low if no significant impulse found
        if swing_high is None or swing_low is None:
            recent = df.tail(60)
            swing_high = float(recent["high"].max())
            swing_low = float(recent["low"].min())

        diff = swing_high - swing_low
        if diff <= 0:
            return {}

        levels: Dict[str, float] = {
            # Retracement levels (from swing high down)
            "0.0": swing_high,
            "0.236": swing_high - diff * 0.236,
            "0.382": swing_high - diff * 0.382,
            "0.5": swing_high - diff * 0.5,
            "0.618": swing_high - diff * 0.618,
            "0.750": swing_high - diff * 0.750,
            "0.786": swing_high - diff * 0.786,
            "1.0": swing_low,
            # Bearish extensions (below swing low)
            "ext_bear_0.618": swing_low - diff * 0.618,
            "ext_bear_1.0": swing_low - diff * 1.0,
            "ext_bear_1.272": swing_low - diff * 1.272,
            "ext_bear_1.618": swing_low - diff * 1.618,
            # Bullish extensions (above swing high)
            "ext_bull_0.618": swing_high + diff * 0.618,
            "ext_bull_1.0": swing_high + diff * 1.0,
            "ext_bull_1.272": swing_high + diff * 1.272,
            "ext_bull_1.618": swing_high + diff * 1.618,
            # Backward-compatible aliases (legacy format used by strategies)
            "ext_0.618": swing_low - diff * 0.618,
            "ext_1.0": swing_low - diff * 1.0,
            "ext_1.272": swing_low - diff * 1.272,
            "ext_1.618": swing_low - diff * 1.618,
        }

        # Include impulse direction metadata for downstream consumers
        if impulse_direction:
            levels["_impulse_direction"] = 1.0 if impulse_direction == "bullish" else -1.0

        return levels

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

        # NOTE: HAMMER and SHOOTING_STAR removed — they are the same concept as
        # LOW_TEST and HIGH_TEST (mentorship terminology). Keeping only LOW_TEST
        # and HIGH_TEST below to avoid double-counting.

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
                body3 > 0 and wick_upper3 > body3 * 1.5 and
                body2 > 0 and wick_upper2 > body2 * 1.5):
                patterns.append("TWEEZER_TOP")

        # Tweezer Bottom - two consecutive candles with similar lows at support
        wick_lower2 = min(c2["close"], c2["open"]) - c2["low"]
        if total_range2 > 0:
            if (abs(c3["low"] - c2["low"]) < total_range3 * 0.1 and
                body3 > 0 and wick_lower3 > body3 * 1.5 and
                body2 > 0 and wick_lower2 > body2 * 1.5):
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
            ["LOW_TEST", "ENGULFING_BULLISH", "MORNING_STAR"])
        reversal_bearish = any(p in patterns for p in
            ["HIGH_TEST", "ENGULFING_BEARISH", "EVENING_STAR"])

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
        Used on D, H1, M15 for standard analysis. M5 MACD only via scalping engine.
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
        # Wilder's smoothing (same as TradingView RSI, NOT Cutler's SMA-based RSI)
        # ewm(alpha=1/period) is equivalent to Wilder's exponential smoothing
        gain = delta.where(delta > 0, 0).ewm(alpha=1/period, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()

        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        # When both gain=0 AND loss=0 (flat market), RSI should be 50 (neutral),
        # not 100. Only fill with 100 when gain>0 but loss=0 (pure uptrend).
        both_zero = (gain == 0) & (loss == 0)
        rsi = rsi.fillna(100.0)  # Default: loss=0 means all gains → RSI=100
        rsi[both_zero] = 50.0    # Override: flat market → neutral RSI
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

        # Calculate RSI (Wilder's smoothing, matches TradingView)
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi = rsi.fillna(100.0)

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

    def _detect_macd_divergence(self, df: pd.DataFrame) -> Optional[str]:
        """
        Detect MACD histogram divergence on H1.
        Required for Black strategy and Scalping (mentorship: "MACD divergence
        on 1H is always present in Black strategy").

        Bullish divergence: price makes lower low, MACD histogram makes higher low.
        Bearish divergence: price makes higher high, MACD histogram makes lower high.
        """
        if df.empty or len(df) < 30:
            return None

        # Calculate MACD histogram (12, 26, 9)
        ema12 = df["close"].ewm(span=12, adjust=False).mean()
        ema26 = df["close"].ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        histogram = macd_line - signal_line

        # Look at last 20 candles for swing points
        recent_price = df.tail(20)
        recent_hist = histogram.tail(20)

        if len(recent_price) < 10:
            return None

        data = recent_price.reset_index(drop=True)
        hist_data = recent_hist.reset_index(drop=True)

        # Find price swing lows and MACD histogram at those points
        price_lows = []
        for i in range(2, len(data) - 2):
            if (data["low"].iloc[i] < data["low"].iloc[i-1] and
                data["low"].iloc[i] < data["low"].iloc[i-2] and
                data["low"].iloc[i] < data["low"].iloc[i+1] and
                data["low"].iloc[i] < data["low"].iloc[i+2]):
                hist_val = hist_data.iloc[i] if i < len(hist_data) else None
                if hist_val is not None and not pd.isna(hist_val):
                    price_lows.append((i, data["low"].iloc[i], hist_val))

        # Check bullish divergence (price lower low, histogram higher low)
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
                hist_val = hist_data.iloc[i] if i < len(hist_data) else None
                if hist_val is not None and not pd.isna(hist_val):
                    price_highs.append((i, data["high"].iloc[i], hist_val))

        # Check bearish divergence (price higher high, histogram lower high)
        if len(price_highs) >= 2:
            prev_high = price_highs[-2]
            curr_high = price_highs[-1]
            if curr_high[1] > prev_high[1] and curr_high[2] < prev_high[2]:
                return "bearish"

        return None

    # ── Order Blocks (from SMC workshop ch416-418) ───────────────────

    def _detect_order_blocks(
        self, df: pd.DataFrame, structure_breaks: Optional[List[Dict]] = None
    ) -> List[Dict]:
        """
        Detect Order Blocks from H1 candles.
        An Order Block is the last candle(s) opposite to an impulse move.
        Where institutions accumulated orders before price moved.

        Per the workshop, OBs form at structure-break points: the impulse after
        the OB candidate must have produced a BOS or CHOCH.  When structure_breaks
        is provided, candidates whose impulse candle index does not correspond to
        any known BOS/CHOCH are filtered out.
        """
        if df.empty or len(df) < 10:
            return []

        # Build a set of indices near structure breaks for OB validation.
        # Allow +-3 bar window since impulse and break may not align exactly.
        break_indices: set = set()
        if structure_breaks:
            for sb in structure_breaks:
                sb_idx = sb.get("index", 0)
                for _off in range(-3, 4):
                    break_indices.add(sb_idx + _off)

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
                    # Verify impulse produced a BOS/CHOCH (if structure data available)
                    if break_indices and i not in break_indices:
                        continue
                    # Extend OB to include prior small contrary candles (dojis)
                    # "la última vela o CONJUNTO DE VELAS contrarias"
                    ob_high = data["high"].iloc[i-1]
                    ob_low = data["low"].iloc[i-1]
                    ob_start_idx = i - 1
                    candle_range = data["high"].iloc[i-1] - data["low"].iloc[i-1]
                    for ext in range(1, 3):  # check up to 2 prior candles
                        ext_idx = i - 1 - ext
                        if ext_idx < 0:
                            break
                        ext_body = abs(data["close"].iloc[ext_idx] - data["open"].iloc[ext_idx])
                        ext_range = data["high"].iloc[ext_idx] - data["low"].iloc[ext_idx]
                        is_small = ext_body < candle_range * 0.5 if candle_range > 0 else False
                        is_bearish = data["close"].iloc[ext_idx] < data["open"].iloc[ext_idx]
                        # Include if small (doji-like) or also bearish (contrary)
                        if is_small or is_bearish:
                            ob_high = max(ob_high, data["high"].iloc[ext_idx])
                            ob_low = min(ob_low, data["low"].iloc[ext_idx])
                            ob_start_idx = ext_idx
                        else:
                            break
                    order_blocks.append({
                        "type": "bullish_ob",
                        "high": ob_high,
                        "low": ob_low,
                        "mid": (ob_high + ob_low) / 2,
                        "index": ob_start_idx,
                    })

            # Bearish Order Block: bullish candle(s) followed by strong bearish impulse
            if (data["close"].iloc[i] < data["open"].iloc[i] and  # current bearish
                data["close"].iloc[i-1] > data["open"].iloc[i-1]):  # previous bullish
                impulse_size = data["open"].iloc[i] - data["close"].iloc[i]
                ob_size = data["close"].iloc[i-1] - data["open"].iloc[i-1]
                # Filtro de calidad: impulso mínimo 1.5x OB (no especificado en mentoría)
                if impulse_size > ob_size * 1.5:
                    # Verify impulse produced a BOS/CHOCH (if structure data available)
                    if break_indices and i not in break_indices:
                        continue
                    # Extend OB to include prior small contrary candles (dojis)
                    ob_high = data["high"].iloc[i-1]
                    ob_low = data["low"].iloc[i-1]
                    ob_start_idx = i - 1
                    candle_range = data["high"].iloc[i-1] - data["low"].iloc[i-1]
                    for ext in range(1, 3):  # check up to 2 prior candles
                        ext_idx = i - 1 - ext
                        if ext_idx < 0:
                            break
                        ext_body = abs(data["close"].iloc[ext_idx] - data["open"].iloc[ext_idx])
                        ext_range = data["high"].iloc[ext_idx] - data["low"].iloc[ext_idx]
                        is_small = ext_body < candle_range * 0.5 if candle_range > 0 else False
                        is_bullish = data["close"].iloc[ext_idx] > data["open"].iloc[ext_idx]
                        # Include if small (doji-like) or also bullish (contrary)
                        if is_small or is_bullish:
                            ob_high = max(ob_high, data["high"].iloc[ext_idx])
                            ob_low = min(ob_low, data["low"].iloc[ext_idx])
                            ob_start_idx = ext_idx
                        else:
                            break
                    order_blocks.append({
                        "type": "bearish_ob",
                        "high": ob_high,
                        "low": ob_low,
                        "mid": (ob_high + ob_low) / 2,
                        "index": ob_start_idx,
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
        # BOS requires established trend context: at least 1 prior HH (established
        # trend after CHOCH). The workshop counts the FIRST break after a CHOCH as
        # BOS, so only 1 prior HH/LL is needed to confirm the trend is established.
        # CHOCH = price breaks the LAST swing low in uptrend (bearish) or
        #         LAST swing high in downtrend (bullish)

        for j in range(max(2, len(swing_highs) - 5), len(swing_highs)):
            if j < 2:
                continue
            prev_high = swing_highs[j - 1][1]
            curr_high = swing_highs[j][1]

            if curr_high > prev_high:
                # Potential BOS bullish: new higher high
                # Require established uptrend: at least 1 prior HH
                prior_hh_count = 0
                for k in range(1, j):
                    if swing_highs[k][1] > swing_highs[k - 1][1]:
                        prior_hh_count += 1
                if prior_hh_count >= 1:
                    breaks.append({
                        "type": "BOS",
                        "direction": "bullish",
                        "level": prev_high,
                        "index": swing_highs[j][0],
                    })

        for j in range(max(2, len(swing_lows) - 5), len(swing_lows)):
            if j < 2:
                continue
            prev_low = swing_lows[j - 1][1]
            curr_low = swing_lows[j][1]

            if curr_low < prev_low:
                # Potential BOS bearish: new lower low
                # Require established downtrend: at least 1 prior LL
                prior_ll_count = 0
                for k in range(1, j):
                    if swing_lows[k][1] < swing_lows[k - 1][1]:
                        prior_ll_count += 1
                if prior_ll_count >= 1:
                    breaks.append({
                        "type": "BOS",
                        "direction": "bearish",
                        "level": prev_low,
                        "index": swing_lows[j][0],
                    })

        # CHOCH detection: price breaks through the last swing low (bearish)
        # or last swing high (bullish), signaling a trend change.
        # Bearish CHOCH: in uptrend (HH sequence), price breaks below the
        # last swing low => the structure changed.
        # Bullish CHOCH: in downtrend (LL sequence), price breaks above the
        # last swing high => the structure changed.

        for j in range(max(2, len(swing_highs) - 5), len(swing_highs)):
            if j < 2:
                continue
            curr_high_idx = swing_highs[j][0]
            curr_high_val = swing_highs[j][1]

            # Check for bearish CHOCH: was there an uptrend (HH) and did
            # price break below the last swing low?
            if (swing_highs[j - 1][1] > swing_highs[j - 2][1]):
                # Previous highs were making HH => uptrend context
                # Find the last swing low before this swing high
                last_swing_low = None
                for si, sv in swing_lows:
                    if si < curr_high_idx:
                        last_swing_low = (si, sv)
                if last_swing_low is not None:
                    # Check if any candle after the swing high broke below
                    # that last swing low
                    for k in range(curr_high_idx + 1, len(data)):
                        if float(data["low"].iloc[k]) < last_swing_low[1]:
                            breaks.append({
                                "type": "CHOCH",
                                "direction": "bearish",
                                "level": last_swing_low[1],
                                "index": k,
                            })
                            break

        for j in range(max(2, len(swing_lows) - 5), len(swing_lows)):
            if j < 2:
                continue
            curr_low_idx = swing_lows[j][0]
            curr_low_val = swing_lows[j][1]

            # Check for bullish CHOCH: was there a downtrend (LL) and did
            # price break above the last swing high?
            if (swing_lows[j - 1][1] < swing_lows[j - 2][1]):
                # Previous lows were making LL => downtrend context
                # Find the last swing high before this swing low
                last_swing_high = None
                for si, sv in swing_highs:
                    if si < curr_low_idx:
                        last_swing_high = (si, sv)
                if last_swing_high is not None:
                    # Check if any candle after the swing low broke above
                    # that last swing high
                    for k in range(curr_low_idx + 1, len(data)):
                        if float(data["high"].iloc[k]) > last_swing_high[1]:
                            breaks.append({
                                "type": "CHOCH",
                                "direction": "bullish",
                                "level": last_swing_high[1],
                                "index": k,
                            })
                            break

        # Sort by index and return most recent
        breaks.sort(key=lambda b: b.get("index", 0))
        return breaks[-10:]

    # ── Trading Session Detection ─────────────────────────────────────

    def _detect_session(self) -> tuple:
        """
        Return the currently active trading session and sub-session detail.

        Sessions (corrected per mentorship):
          ASIAN     : 00:00-08:00 UTC
            - SYDNEY sub-session: 21:00-06:00 UTC (overlaps into ASIAN)
            - TOKYO  sub-session: 00:00-09:00 UTC
            - 21:00-00:00 is Sydney-only (mapped to OFF_HOURS for main session)
            - 00:00-06:00 is Sydney+Tokyo overlap
            - 06:00-08:00 is Tokyo-only
          LONDON    : 08:00-16:00 UTC (full London session)
          OVERLAP   : 13:00-17:00 UTC (London+NY overlap - highest volatility)
          NEW_YORK  : 13:00-21:00 UTC (full NY session)
          OFF_HOURS : 21:00-00:00 UTC (includes Sydney open)

        Note: OVERLAP is a subset of both LONDON and NEW_YORK.
        Priority: OVERLAP > LONDON > NEW_YORK (overlap has highest volatility).

        Returns:
            Tuple of (session: str, session_detail: str).
            session_detail distinguishes TOKYO vs SYDNEY within the ASIAN block.
        """
        utc_hour = datetime.now(timezone.utc).hour

        if 0 <= utc_hour < 8:
            # ASIAN block with Sydney/Tokyo distinction
            if utc_hour < 6:
                # 00:00-06:00: Sydney + Tokyo overlap
                detail = "ASIAN_SYDNEY_TOKYO"
            else:
                # 06:00-08:00: Tokyo only (Sydney closed at 06:00)
                detail = "ASIAN_TOKYO"
            return ("ASIAN", detail)
        elif 13 <= utc_hour < 17:
            # Overlap takes priority (subset of both London and NY)
            return ("OVERLAP", "LONDON_NY_OVERLAP")
        elif 8 <= utc_hour < 13:
            # London-only hours (before NY opens)
            return ("LONDON", "LONDON")
        elif 17 <= utc_hour < 21:
            # NY-only hours (after London closes)
            return ("NEW_YORK", "NEW_YORK")
        else:
            # 21:00-00:00: Off-hours but Sydney is already open
            return ("OFF_HOURS", "SYDNEY_PRE_ASIAN")

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

        # ── Step 4: Count waves and record wave boundaries ──
        # Walk through filtered swings and count alternating impulse/correction
        # legs relative to the detected trend.
        # wave_points stores the swing value at each wave boundary:
        #   key = wave number (1,2,3,...), value = (index, price)
        wave_count = 0
        phase = "impulse"
        prev_swing = filtered[0]
        in_impulse = True
        wave_points: Dict[int, Tuple[int, float]] = {0: (prev_swing[0], prev_swing[1])}

        for s in filtered[1:]:
            if uptrend or (not downtrend):
                # Uptrend logic (default when ranging)
                if s[2] == "H" and in_impulse:
                    if s[1] >= prev_swing[1]:
                        # Impulse leg continues / completes
                        wave_count += 1
                        in_impulse = False  # next expect correction
                        wave_points[wave_count] = (s[0], s[1])
                elif s[2] == "L" and not in_impulse:
                    # Correction leg
                    wave_count += 1
                    in_impulse = True  # next expect impulse
                    wave_points[wave_count] = (s[0], s[1])
                    if wave_count > 5:
                        # Switch to corrective phase
                        phase = "corrective"
            else:
                # Downtrend logic (mirrored)
                if s[2] == "L" and in_impulse:
                    if s[1] <= prev_swing[1]:
                        wave_count += 1
                        in_impulse = False
                        wave_points[wave_count] = (s[0], s[1])
                elif s[2] == "H" and not in_impulse:
                    wave_count += 1
                    in_impulse = True
                    wave_points[wave_count] = (s[0], s[1])
                    if wave_count > 5:
                        phase = "corrective"

            prev_swing = s

        # ── Step 4b: Calculate wave_lengths (absolute price movement per wave) ──
        wave_lengths: Dict[str, float] = {}
        for w in range(1, min(wave_count, 10) + 1):
            if w in wave_points and (w - 1) in wave_points:
                wave_lengths[str(w)] = abs(wave_points[w][1] - wave_points[w - 1][1])

        # ── Step 4c: Validate Elliott cardinal rules ──
        invalid_structure = False

        # Rule 1: Wave 2 cannot retrace beyond Wave 1 start
        if 0 in wave_points and 1 in wave_points and 2 in wave_points:
            w0_price = wave_points[0][1]  # Wave 1 start
            w2_price = wave_points[2][1]  # Wave 2 end
            if uptrend or (not downtrend):
                # Bullish: Wave 2 low must stay above Wave 1 start (w0)
                if w2_price < w0_price:
                    invalid_structure = True
                    wave_count = min(wave_count, 1)
            else:
                # Bearish: Wave 2 high must stay below Wave 1 start (w0)
                if w2_price > w0_price:
                    invalid_structure = True
                    wave_count = min(wave_count, 1)

        # Rule 2: Wave 3 is never the shortest impulse wave
        w1_len = wave_lengths.get("1", 0)
        w3_len = wave_lengths.get("3", 0)
        w5_len = wave_lengths.get("5", 0)
        if w3_len > 0 and w1_len > 0 and w5_len > 0:
            if w3_len < w1_len and w3_len < w5_len:
                invalid_structure = True
                wave_count = min(wave_count, 2)

        # Rule 3: Wave 4 cannot enter Wave 1 territory
        if 1 in wave_points and 4 in wave_points:
            w1_price = wave_points[1][1]  # Wave 1 end (top for bullish)
            w4_price = wave_points[4][1]  # Wave 4 end (low for bullish)
            if uptrend or (not downtrend):
                # Bullish: Wave 4 low must be above Wave 1 high
                if w4_price < w1_price:
                    invalid_structure = True
                    wave_count = min(wave_count, 3)
            else:
                # Bearish: Wave 4 high must be below Wave 1 low
                if w4_price > w1_price:
                    invalid_structure = True
                    wave_count = min(wave_count, 3)

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
            "wave_lengths": wave_lengths,
            "invalid_structure": invalid_structure,
        }

    # ── Pivot Points (TradingLab ch12) ─────────────────────────────────

    def _calculate_pivot_points(self, df: pd.DataFrame) -> Dict[str, float]:
        """
        Calculate Standard Pivot Points from the previous daily candle.

        P  = (H + L + C) / 3
        R1 = 2*P - L
        S1 = 2*P - H

        Mentorship: Alex only uses P, S1, R1. S2/R2 are optional and not displayed.
        These act as intraday S/R levels used by institutional traders.
        """
        if df.empty or len(df) < 2:
            return {}

        # Use the single previous completed daily candle (iloc[-2] since -1 is current incomplete day)
        candle = df.iloc[-2]
        h, l, c = float(candle["high"]), float(candle["low"]), float(candle["close"])
        p = (h + l + c) / 3.0

        # Mentorship: Alex only uses P, S1, R1 (S2/R2 optional, not displayed)
        return {
            "P": round(p, 5),
            "R1": round(2 * p - l, 5),
            "S1": round(2 * p - h, 5),
        }

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
            # AND with momentum convergence approaching the OB (workshop
            # defining characteristic).
            if not liquidity_swept:
                # Step 3b: Momentum check — verify price showed decreasing
                # highs (for bearish OB mitigation) or increasing lows (for
                # bullish OB mitigation) as it approached the OB before breaking.
                has_momentum_convergence = False
                # Look at candles between OB and break for the pattern
                approach_start = max(ob_idx + 1, break_idx - 6)
                approach_end = break_idx

                if approach_end - approach_start >= 2:
                    if ob_type == "bearish_ob":
                        # Price approaching from below: check for increasing lows
                        approach_lows = [
                            float(data["low"].iloc[k])
                            for k in range(approach_start, approach_end)
                        ]
                        increasing = sum(
                            1 for k in range(1, len(approach_lows))
                            if approach_lows[k] > approach_lows[k - 1]
                        )
                        has_momentum_convergence = increasing >= len(approach_lows) // 2
                    elif ob_type == "bullish_ob":
                        # Price approaching from above: check for decreasing highs
                        approach_highs = [
                            float(data["high"].iloc[k])
                            for k in range(approach_start, approach_end)
                        ]
                        decreasing = sum(
                            1 for k in range(1, len(approach_highs))
                            if approach_highs[k] < approach_highs[k - 1]
                        )
                        has_momentum_convergence = decreasing >= len(approach_highs) // 2
                else:
                    # Too few candles to check, allow it
                    has_momentum_convergence = True

                if has_momentum_convergence:
                    # Role flip: like Breaker Blocks, the failed OB flips direction.
                    # Bullish OB broken down -> becomes bearish resistance
                    # Bearish OB broken up -> becomes bullish support
                    if ob_type == "bullish_ob":
                        flipped_type = "bearish"  # Was bullish support, now bearish resistance
                    else:
                        flipped_type = "bullish"  # Was bearish resistance, now bullish support

                    mitigation_blocks.append({
                        "type": f"mitigation_{ob_type}",
                        "flipped_direction": flipped_type,
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
        Detect Breaker Blocks: order blocks where price swept liquidity
        (took the previous swing extreme) and THEN broke through the OB.

        From mentorship: "el precio rompe el máximo anterior, toma la liquidez
        del máximo anterior, retrocede y no respeta este order block."

        Requirements:
        1. Price must have swept liquidity (new high/low beyond previous swing
           extreme) BEFORE the OB was broken.
        2. Then a candle body broke through the OB.
        3. The OB flips direction (bullish OB becomes bearish resistance, etc.).
        """
        if df.empty or not order_blocks:
            return []

        breaker_blocks = []
        data = df.reset_index(drop=True)

        # Pre-compute swing highs and swing lows for liquidity sweep check
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

            # Step 1: Find the break candle (body broke through the OB)
            break_idx = None
            for j in range(ob_idx + 2, len(data)):
                candle_open = float(data["open"].iloc[j])
                candle_close = float(data["close"].iloc[j])
                body_high = max(candle_open, candle_close)
                body_low = min(candle_open, candle_close)

                if ob_type == "bullish_ob" and candle_close < ob_low:
                    # Workshop: "body breaks through" = close beyond OB boundary
                    break_idx = j
                    break
                elif ob_type == "bearish_ob" and candle_close > ob_high:
                    # Workshop: "body breaks through" = close beyond OB boundary
                    break_idx = j
                    break

            if break_idx is None:
                continue  # OB was never broken

            # Step 2: Check that liquidity was swept BEFORE the break
            # For bullish OB broken downward: price must have made a new high
            # above the previous swing high (swept buy-side liquidity) before
            # reversing and breaking the OB.
            # For bearish OB broken upward: price must have made a new low
            # below the previous swing low (swept sell-side liquidity) before
            # reversing and breaking the OB.
            liquidity_swept = False

            if ob_type == "bullish_ob":
                # Find the swing high before the OB
                prev_swing_high = None
                for si, sv in swing_highs:
                    if si < ob_idx:
                        prev_swing_high = sv
                # Check if price went above that swing high between OB and break
                if prev_swing_high is not None:
                    for k in range(ob_idx, break_idx):
                        if float(data["high"].iloc[k]) > prev_swing_high:
                            liquidity_swept = True
                            break

            elif ob_type == "bearish_ob":
                # Find the swing low before the OB
                prev_swing_low = None
                for si, sv in swing_lows:
                    if si < ob_idx:
                        prev_swing_low = sv
                # Check if price went below that swing low between OB and break
                if prev_swing_low is not None:
                    for k in range(ob_idx, break_idx):
                        if float(data["low"].iloc[k]) < prev_swing_low:
                            liquidity_swept = True
                            break

            # Step 3: Only classify as Breaker Block if liquidity was swept
            if not liquidity_swept:
                continue

            if ob_type == "bullish_ob":
                breaker_blocks.append({
                    "type": "bearish",  # Flipped: was bullish, now resistance
                    "high": ob_high,
                    "low": ob_low,
                    "mid": (ob_high + ob_low) / 2,
                    "original_type": ob_type,
                    "break_index": break_idx,
                    "liquidity_swept": True,
                })
            elif ob_type == "bearish_ob":
                breaker_blocks.append({
                    "type": "bullish",  # Flipped: was bearish, now support
                    "high": ob_high,
                    "low": ob_low,
                    "mid": (ob_high + ob_low) / 2,
                    "original_type": ob_type,
                    "break_index": break_idx,
                    "liquidity_swept": True,
                })

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

        session, _session_detail = self._detect_session()
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
            # Check accumulation quality: Asian session should show
            # lateral/consolidation behavior.  If Asian range is too wide
            # (high volatility), it is not proper "accumulation".
            # Compare Asian range to average daily range of last 10 days.
            is_proper_accumulation = True
            if not data.empty and len(data) >= 10:
                recent_daily_ranges = [
                    float(data["high"].iloc[-k] - data["low"].iloc[-k])
                    for k in range(1, min(11, len(data)))
                ]
                avg_daily_range = sum(recent_daily_ranges) / len(recent_daily_ranges)
                # Asian range should be less than 40% of avg daily range
                # to qualify as consolidation/lateral movement
                if avg_daily_range > 0 and asian_range > avg_daily_range * 0.4:
                    is_proper_accumulation = False

            if is_proper_accumulation:
                result["phase"] = "accumulation"
            else:
                result["phase"] = "accumulation_wide"
                result["accumulation_quality"] = "poor"
        elif session == "LONDON":
            result["phase"] = "manipulation"
            # Capture the London manipulation price range as entry zone
            london_start = now.replace(hour=8, minute=0, second=0, microsecond=0)
            london_candles = data[data.index >= london_start]
            if not london_candles.empty:
                result["manipulation_zone_high"] = float(london_candles["high"].max())
                result["manipulation_zone_low"] = float(london_candles["low"].min())
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

            if not london_candles.empty:
                london_high = float(london_candles["high"].max())
                london_low = float(london_candles["low"].min())
                # Provide London manipulation zone for entry reference
                result["manipulation_zone_high"] = london_high
                result["manipulation_zone_low"] = london_low

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
            self._smt_cache[instrument] = {
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
        self._smt_cache[instrument] = current_data

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
            corr_data = self._smt_cache.get(corr_inst)
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

        # --- London session High / Low (08:00-16:00 UTC) ---
        if not h1.empty and isinstance(h1.index, pd.DatetimeIndex):
            now_liq = datetime.now(timezone.utc)
            london_start = now_liq.replace(hour=8, minute=0, second=0, microsecond=0)
            london_end = now_liq.replace(hour=16, minute=0, second=0, microsecond=0)
            london_candles = h1[
                (h1.index >= london_start) & (h1.index < london_end)
            ]
            if london_candles.empty:
                from datetime import timedelta as _td_liq
                london_start_y = london_start - _td_liq(days=1)
                london_end_y = london_end - _td_liq(days=1)
                london_candles = h1[
                    (h1.index >= london_start_y) & (h1.index < london_end_y)
                ]
            if not london_candles.empty:
                london_high = float(london_candles["high"].max())
                london_low = float(london_candles["low"].min())
                pools.append({"level": london_high, "type": "london_high", "strength": 1})
                pools.append({"level": london_low, "type": "london_low", "strength": 1})

        # --- New York session High / Low (13:00-21:00 UTC) ---
        if not h1.empty and isinstance(h1.index, pd.DatetimeIndex):
            now_liq = datetime.now(timezone.utc)
            ny_start = now_liq.replace(hour=13, minute=0, second=0, microsecond=0)
            ny_end = now_liq.replace(hour=21, minute=0, second=0, microsecond=0)
            ny_candles = h1[
                (h1.index >= ny_start) & (h1.index < ny_end)
            ]
            if ny_candles.empty:
                from datetime import timedelta as _td_liq
                ny_start_y = ny_start - _td_liq(days=1)
                ny_end_y = ny_end - _td_liq(days=1)
                ny_candles = h1[
                    (h1.index >= ny_start_y) & (h1.index < ny_end_y)
                ]
            if not ny_candles.empty:
                ny_high = float(ny_candles["high"].max())
                ny_low = float(ny_candles["low"].min())
                pools.append({"level": ny_high, "type": "ny_high", "strength": 1})
                pools.append({"level": ny_low, "type": "ny_low", "strength": 1})

        # --- S/R levels from key_levels as liquidity targets ---
        for res in key_levels.get("resistances", []):
            # S/R levels can be zone dicts or plain floats
            level = res["price"] if isinstance(res, dict) else float(res)
            pools.append({"level": level, "type": "resistance", "strength": 1})
        for sup in key_levels.get("supports", []):
            level = sup["price"] if isinstance(sup, dict) else float(sup)
            pools.append({"level": level, "type": "support", "strength": 1})

        # --- Trendline Liquidity Zones ---
        # Detect diagonal trendlines connecting swing lows (uptrend) or swing
        # highs (downtrend). Where multiple swing points align along a line,
        # stops cluster and form trendline liquidity.
        if len(swing_lows) >= 3:
            # Ascending trendline: connect the last 3+ swing lows
            # Use simple linear regression on the most recent swing lows
            recent_sl = swing_lows[-5:] if len(swing_lows) >= 5 else swing_lows[-3:]
            # Check if they form an ascending line (each higher than previous)
            ascending = all(
                recent_sl[k] > recent_sl[k - 1]
                for k in range(1, len(recent_sl))
            )
            if ascending and len(recent_sl) >= 3:
                # Project the trendline to the current bar
                # Use first and last points for the line
                x1, y1 = 0, recent_sl[0]
                x2, y2 = len(recent_sl) - 1, recent_sl[-1]
                slope = (y2 - y1) / (x2 - x1) if x2 != x1 else 0
                # Project forward: estimate where trendline is NOW
                # Use the index distance from last swing low to end of data
                if not daily.empty:
                    bars_ahead = len(daily) - 1  # rough projection
                    projected_level = y2 + slope * 2  # 2 bars ahead
                    pools.append({
                        "level": projected_level,
                        "type": "trendline_support",
                        "strength": len(recent_sl),
                        "slope": slope,
                    })

        if len(swing_highs) >= 3:
            # Descending trendline: connect the last 3+ swing highs
            recent_sh = swing_highs[-5:] if len(swing_highs) >= 5 else swing_highs[-3:]
            descending = all(
                recent_sh[k] < recent_sh[k - 1]
                for k in range(1, len(recent_sh))
            )
            if descending and len(recent_sh) >= 3:
                x1, y1 = 0, recent_sh[0]
                x2, y2 = len(recent_sh) - 1, recent_sh[-1]
                slope = (y2 - y1) / (x2 - x1) if x2 != x1 else 0
                if not daily.empty:
                    projected_level = y2 + slope * 2
                    pools.append({
                        "level": projected_level,
                        "type": "trendline_resistance",
                        "strength": len(recent_sh),
                        "slope": slope,
                    })

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
                if ptype in ("equal_highs", "pdh", "asian_high",
                             "london_high", "ny_high", "resistance",
                             "trendline_resistance"):
                    if recent_high > lvl and current_price < lvl and prev_close < lvl:
                        sweep = {"level": lvl, "direction": "swept_highs"}
                        break

                # Swept lows: wick went below level but close came back above
                if ptype in ("equal_lows", "pdl", "asian_low",
                             "london_low", "ny_low", "support",
                             "trendline_support"):
                    if recent_low < lvl and current_price > lvl and prev_close > lvl:
                        sweep = {"level": lvl, "direction": "swept_lows"}
                        break

        return pools, sweep

    # ── Premium / Discount Zone Detection (TradingLab SMC) ────────────

    def _detect_premium_discount(
        self, df: pd.DataFrame, current_price: Optional[float]
    ) -> Optional[Dict[str, Any]]:
        """
        Detect whether price is in the Premium or Discount zone relative to the
        most recent impulse swing, using Fibonacci levels (0, 0.5, 1).

        From mentorship:
        - Identify the most recent impulse swing (significant high-to-low or
          low-to-high move).
        - Calculate premium/discount relative to THAT specific swing, not the
          global range.
        - The 50-70% retracement zone is the "sweet spot" where institutions
          typically place orders (optimal entry area).

        Returns dict with zone, position, swing_high, swing_low, equilibrium,
        sweet_spot_high, sweet_spot_low, or None.
        """
        if df.empty or len(df) < 20 or current_price is None:
            return None

        data = df.reset_index(drop=True)

        # Find swing highs and lows to identify the most recent impulse
        swing_points: List[Tuple[int, float, str]] = []
        for i in range(2, len(data) - 2):
            if (data["high"].iloc[i] > data["high"].iloc[i - 1] and
                data["high"].iloc[i] > data["high"].iloc[i - 2] and
                data["high"].iloc[i] > data["high"].iloc[i + 1] and
                data["high"].iloc[i] > data["high"].iloc[i + 2]):
                swing_points.append((i, float(data["high"].iloc[i]), "H"))
            if (data["low"].iloc[i] < data["low"].iloc[i - 1] and
                data["low"].iloc[i] < data["low"].iloc[i - 2] and
                data["low"].iloc[i] < data["low"].iloc[i + 1] and
                data["low"].iloc[i] < data["low"].iloc[i + 2]):
                swing_points.append((i, float(data["low"].iloc[i]), "L"))

        swing_points.sort(key=lambda s: s[0])

        if len(swing_points) < 2:
            return None

        # Find the most recent significant impulse swing
        # Walk backwards through swing points to find the last H->L or L->H pair
        impulse_high = None
        impulse_low = None

        for k in range(len(swing_points) - 1, 0, -1):
            curr = swing_points[k]
            prev = swing_points[k - 1]
            if curr[2] != prev[2]:
                # Alternating swing types => impulse leg
                if curr[2] == "L" and prev[2] == "H":
                    # Bearish impulse: high to low
                    impulse_high = prev[1]
                    impulse_low = curr[1]
                elif curr[2] == "H" and prev[2] == "L":
                    # Bullish impulse: low to high
                    impulse_high = curr[1]
                    impulse_low = prev[1]
                break

        if impulse_high is None or impulse_low is None:
            return None

        rng = impulse_high - impulse_low
        if rng <= 0:
            return None

        # Fibonacci levels relative to this impulse swing
        equilibrium = impulse_low + rng * 0.5
        # Sweet spot: 50-75% retracement (institutional order zone)
        # TradingLab uses 0.618 and 0.75 Fibonacci levels
        sweet_spot_high = impulse_low + rng * 0.75
        sweet_spot_low = impulse_low + rng * 0.5

        # Position within the swing (0.0 = swing low, 1.0 = swing high)
        position = (current_price - impulse_low) / rng

        if position > 0.5:
            zone = "premium"
        else:
            zone = "discount"

        in_sweet_spot = 0.5 <= position <= 0.75

        return {
            "zone": zone,
            "position": round(float(position), 4),
            "swing_high": impulse_high,
            "swing_low": impulse_low,
            "equilibrium": equilibrium,
            "sweet_spot_high": sweet_spot_high,
            "sweet_spot_low": sweet_spot_low,
            "in_sweet_spot": in_sweet_spot,
        }
