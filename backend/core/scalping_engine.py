"""
NeonTrade AI - Scalping Engine
From TradingLab Workshop de Scalping.

Scalping temporal hierarchy (compressed from day trading):
- H1: Main direction (like Daily in day trading) -> MACD + EMA 50 + SMA 200
- M15: Structure (like 4H in day trading) -> EMA 50
- M5: Confirmation (like 1H in day trading) -> EMA 50 + MACD + Volume
- M1: Execution (like 5M in day trading) -> EMA 50 + MACD

Position Management:
- Method 1 (fast): Exit when price closes below EMA 50 on M1 (~7-10% profit)
- Method 2 (slow): Exit when price closes below EMA 50 on M5 (~10%+ profit)

Risk: 0.5% per trade (from config), max daily DD 5%, max total DD 10%
"""

from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
import pandas as pd
import numpy as np
from loguru import logger

from strategies.base import SetupSignal, StrategyColor, get_best_setup
from core.market_analyzer import AnalysisResult, Trend, MarketCondition


# ── Scalping Timeframe Mapping ────────────────────────────────────
# Day Trading -> Scalping compression
# Daily       -> H1 (main direction)
# H4          -> M15 (structure)
# H1          -> M5 (confirmation / setup)
# M5/M2       -> M1 (execution)

SCALPING_TIMEFRAMES = {
    "direction": "H1",       # Main direction (replaces Daily)
    "structure": "M15",      # Structure (replaces H4)
    "confirmation": "M5",    # Confirmation (replaces H1)
    "execution": "M1",       # Execution (replaces M5)
}


@dataclass
class ScalpingData:
    """Container for scalping-specific analysis data."""
    instrument: str
    # EMA 50 per timeframe
    ema50_h1: Optional[float] = None
    ema50_m15: Optional[float] = None
    ema50_m5: Optional[float] = None
    ema50_m1: Optional[float] = None
    # MACD per timeframe (H1 direction, M5 confirmation, M1 execution)
    macd_h1: Optional[Dict[str, float]] = None
    macd_m5: Optional[Dict[str, float]] = None
    macd_m1: Optional[Dict[str, float]] = None
    # SMA 200 on H1 (long-term filter)
    sma200_h1: Optional[float] = None
    # Volume on M5
    volume_m5: Optional[Dict[str, float]] = None
    # Current prices per timeframe (latest close)
    close_h1: Optional[float] = None
    close_m15: Optional[float] = None
    close_m5: Optional[float] = None
    close_m1: Optional[float] = None
    # H1 direction
    h1_direction: Optional[str] = None  # "BUY" or "SELL"
    # Raw candle DataFrames for strategy detection
    candles: Dict[str, pd.DataFrame] = field(default_factory=dict)


class ScalpingAnalyzer:
    """
    Scalping analysis engine that compresses the 6 color strategies
    to lower timeframes following the TradingLab Scalping Workshop.
    """

    def __init__(self, broker_client):
        self.broker = broker_client
        # Track scalping setups found per session
        self._scalping_setups_found: int = 0
        self._scalping_setups_executed: int = 0

    # ── Main Analysis ────────────────────────────────────────────────

    async def analyze_scalping(self, instrument: str) -> ScalpingData:
        """
        Fetch M1 candles and compute scalping indicators across
        H1 / M15 / M5 / M1 timeframes.

        Returns a ScalpingData object with all computed values.
        """
        # Fetch candles for each scalping timeframe
        timeframe_counts = {
            "H1": 250,     # Need 200+ for SMA 200
            "M15": 200,    # Structure analysis
            "M5": 200,     # Confirmation
            "M1": 200,     # Execution
        }

        candles: Dict[str, pd.DataFrame] = {}
        for tf, count in timeframe_counts.items():
            try:
                raw = await self.broker.get_candles(instrument, tf, count)
                candles[tf] = self._candles_to_dataframe(raw)
            except Exception as e:
                logger.warning(
                    f"Scalping: failed to get {tf} candles for {instrument}: {e}"
                )
                candles[tf] = pd.DataFrame()

        data = ScalpingData(instrument=instrument, candles=candles)

        # ── EMA 50 on all timeframes ──
        for tf, attr in [("H1", "ema50_h1"), ("M15", "ema50_m15"),
                         ("M5", "ema50_m5"), ("M1", "ema50_m1")]:
            df = candles.get(tf, pd.DataFrame())
            if not df.empty and len(df) >= 50:
                ema = df["close"].ewm(span=50).mean()
                setattr(data, attr, float(ema.iloc[-1]))

        # ── MACD on H1, M5, M1 ──
        for tf, attr in [("H1", "macd_h1"), ("M5", "macd_m5"), ("M1", "macd_m1")]:
            df = candles.get(tf, pd.DataFrame())
            macd = self._calculate_macd(df)
            if macd:
                setattr(data, attr, macd)

        # ── SMA 200 on H1 ──
        h1_df = candles.get("H1", pd.DataFrame())
        if not h1_df.empty and len(h1_df) >= 200:
            sma = h1_df["close"].rolling(200).mean()
            if not sma.empty and not pd.isna(sma.iloc[-1]):
                data.sma200_h1 = float(sma.iloc[-1])

        # ── Volume analysis on M5 ──
        m5_df = candles.get("M5", pd.DataFrame())
        if not m5_df.empty and len(m5_df) >= 20:
            vol = m5_df["volume"]
            avg_vol = vol.rolling(20).mean().iloc[-1]
            current_vol = vol.iloc[-1]
            data.volume_m5 = {
                "current": float(current_vol),
                "average": float(avg_vol) if not pd.isna(avg_vol) else 0.0,
                "ratio": float(current_vol / avg_vol) if avg_vol and not pd.isna(avg_vol) and avg_vol > 0 else 0.0,
            }

        # ── Current close prices ──
        for tf, attr in [("H1", "close_h1"), ("M15", "close_m15"),
                         ("M5", "close_m5"), ("M1", "close_m1")]:
            df = candles.get(tf, pd.DataFrame())
            if not df.empty:
                setattr(data, attr, float(df["close"].iloc[-1]))

        # ── H1 direction determination ──
        # Direction based on MACD + EMA 50 + SMA 200 on H1
        data.h1_direction = self._determine_h1_direction(data)

        return data

    def _determine_h1_direction(self, data: ScalpingData) -> Optional[str]:
        """
        Determine the main scalping direction from H1 indicators.
        Requires:
        - MACD bullish/bearish on H1
        - Price above/below EMA 50 on H1
        - Price above/below SMA 200 on H1 (strong filter)
        """
        if data.close_h1 is None or data.ema50_h1 is None:
            return None

        price_above_ema50 = data.close_h1 > data.ema50_h1
        macd_bullish = data.macd_h1 and data.macd_h1.get("bullish", False)

        # SMA 200 filter (if available, strengthens signal)
        sma_filter = None
        if data.sma200_h1 is not None:
            sma_filter = data.close_h1 > data.sma200_h1

        if price_above_ema50 and macd_bullish:
            # Strong buy if also above SMA 200
            if sma_filter is None or sma_filter:
                return "BUY"
        elif not price_above_ema50 and not macd_bullish:
            # Strong sell if also below SMA 200
            if sma_filter is None or not sma_filter:
                return "SELL"

        return None

    # ── Setup Detection (Compressed Strategies) ───────────────────────

    def detect_scalping_setup(
        self,
        analysis: AnalysisResult,
        scalp_data: ScalpingData,
    ) -> Optional[SetupSignal]:
        """
        Apply the same 6 color strategies but with compressed timeframes.

        The scalping temporal hierarchy remaps:
        - H1 direction   replaces Daily direction
        - M15 EMA 50     replaces H4 EMA 50 break
        - M5 structure    replaces H1 structure
        - M1 execution    replaces M5 execution

        We build a synthetic AnalysisResult with scalping timeframe data
        and run it through the standard strategy detection.
        """
        if scalp_data.h1_direction is None:
            logger.debug(
                f"Scalping: no H1 direction for {scalp_data.instrument} — skipping"
            )
            return None

        # Build a synthetic AnalysisResult that maps scalping timeframes
        # to what the strategies expect
        scalp_analysis = self._build_scalping_analysis(analysis, scalp_data)
        if scalp_analysis is None:
            return None

        # Run strategy detection on the synthetic analysis
        signal = get_best_setup(scalp_analysis)
        if signal is None:
            return None

        # Tag as scalping setup
        signal.reasoning = f"[SCALPING] {signal.reasoning}"
        signal.explanation_es = f"[SCALPING] {signal.explanation_es}"
        signal.timeframes_analyzed = ["H1", "M15", "M5", "M1"]

        # Validate scalping-specific conditions
        if not self._validate_scalping_conditions(scalp_data, signal.direction):
            logger.debug(
                f"Scalping: conditions not met for {signal.instrument} "
                f"{signal.direction}"
            )
            return None

        self._scalping_setups_found += 1
        logger.info(
            f"Scalping setup: {signal.strategy_variant} on {signal.instrument} "
            f"{signal.direction} | Confidence: {signal.confidence:.0f}%"
        )

        return signal

    def _build_scalping_analysis(
        self,
        base_analysis: AnalysisResult,
        scalp_data: ScalpingData,
    ) -> Optional[AnalysisResult]:
        """
        Build a synthetic AnalysisResult with scalping timeframe mappings.

        Maps:
        - HTF trend from H1 (not Weekly as in day trading)
        - LTF trend from M5 (not H1 as in day trading)
        - EMA values remapped: H4 EMAs -> M15 EMAs, H1 EMAs -> M5 EMAs
        - MACD values remapped similarly
        """
        candles = scalp_data.candles

        # Determine HTF trend from H1 (replaces Weekly)
        h1_df = candles.get("H1", pd.DataFrame())
        if h1_df.empty:
            return None

        # Use H1 for HTF direction
        if scalp_data.h1_direction == "BUY":
            htf_trend = Trend.BULLISH
        elif scalp_data.h1_direction == "SELL":
            htf_trend = Trend.BEARISH
        else:
            htf_trend = Trend.RANGING

        # LTF trend from M5
        m5_df = candles.get("M5", pd.DataFrame())
        ltf_trend = Trend.RANGING
        if not m5_df.empty and scalp_data.ema50_m5 is not None:
            m5_close = float(m5_df["close"].iloc[-1])
            if m5_close > scalp_data.ema50_m5:
                ltf_trend = Trend.BULLISH
            else:
                ltf_trend = Trend.BEARISH

        convergence = (htf_trend == ltf_trend and htf_trend != Trend.RANGING)

        # Build EMA values remapped for scalping:
        # Strategies look at "EMA_H4_50", "EMA_H1_50", "EMA_D_50", etc.
        # We remap: D -> H1, H4 -> M15, H1 -> M5, M5 -> M1
        ema_values = dict(base_analysis.ema_values)  # start with base

        # Scalping remaps
        if scalp_data.ema50_h1 is not None:
            ema_values["EMA_D_50"] = scalp_data.ema50_h1    # H1 -> Daily slot
            ema_values["EMA_D_20"] = scalp_data.ema50_h1    # fallback
        if scalp_data.ema50_m15 is not None:
            ema_values["EMA_H4_50"] = scalp_data.ema50_m15  # M15 -> H4 slot
            ema_values["EMA_H4_20"] = scalp_data.ema50_m15
        if scalp_data.ema50_m5 is not None:
            ema_values["EMA_H1_50"] = scalp_data.ema50_m5   # M5 -> H1 slot
            ema_values["EMA_H1_20"] = scalp_data.ema50_m5
        if scalp_data.ema50_m1 is not None:
            ema_values["EMA_M5_20"] = scalp_data.ema50_m1   # M1 -> M5 slot

        # Build MACD values remapped for scalping
        macd_values = dict(base_analysis.macd_values)
        if scalp_data.macd_h1:
            macd_values["D"] = scalp_data.macd_h1    # H1 MACD -> Daily slot
        if scalp_data.macd_m5:
            macd_values["H1"] = scalp_data.macd_m5   # M5 MACD -> H1 slot
        if scalp_data.macd_m1:
            macd_values["M5"] = scalp_data.macd_m1   # M1 MACD -> M5 slot

        # SMA values remapped
        sma_values = dict(base_analysis.sma_values)
        if scalp_data.sma200_h1 is not None:
            sma_values["SMA_D_200"] = scalp_data.sma200_h1  # H1 SMA -> Daily slot

        # Volume analysis remapped
        volume_analysis = dict(base_analysis.volume_analysis)
        if scalp_data.volume_m5:
            volume_analysis["M5"] = scalp_data.volume_m5

        # Current price from M1
        current_price = scalp_data.close_m1 or scalp_data.close_m5

        # Detect condition from H1 (replaces Daily condition)
        htf_condition = MarketCondition.NEUTRAL

        # Last candles: remap M5 -> H1 slot, M1 -> M5 slot
        last_candles = dict(base_analysis.last_candles)
        m5_candles = candles.get("M5", pd.DataFrame())
        if not m5_candles.empty and len(m5_candles) >= 3:
            tail = m5_candles.tail(3)
            last_candles["H1"] = [
                {"open": row["open"], "high": row["high"],
                 "low": row["low"], "close": row["close"],
                 "volume": row.get("volume", 0)}
                for _, row in tail.iterrows()
            ]
        m1_candles = candles.get("M1", pd.DataFrame())
        if not m1_candles.empty and len(m1_candles) >= 3:
            tail = m1_candles.tail(3)
            last_candles["M5"] = [
                {"open": row["open"], "high": row["high"],
                 "low": row["low"], "close": row["close"],
                 "volume": row.get("volume", 0)}
                for _, row in tail.iterrows()
            ]

        scalp_result = AnalysisResult(
            instrument=scalp_data.instrument,
            htf_trend=htf_trend,
            htf_condition=htf_condition,
            ltf_trend=ltf_trend,
            htf_ltf_convergence=convergence,
            key_levels=base_analysis.key_levels,
            ema_values=ema_values,
            fibonacci_levels=base_analysis.fibonacci_levels,
            candlestick_patterns=base_analysis.candlestick_patterns,
            chart_patterns=base_analysis.chart_patterns,
            macd_values=macd_values,
            sma_values=sma_values,
            rsi_values=base_analysis.rsi_values,
            rsi_divergence=base_analysis.rsi_divergence,
            order_blocks=base_analysis.order_blocks,
            structure_breaks=base_analysis.structure_breaks,
            score=base_analysis.score,
            volume_analysis=volume_analysis,
            last_candles=last_candles,
            current_price=current_price,
            session=base_analysis.session,
        )

        return scalp_result

    def _validate_scalping_conditions(
        self, scalp_data: ScalpingData, direction: str
    ) -> bool:
        """
        Validate scalping-specific entry conditions:
        1. M15 EMA 50 break confirms structure (price on correct side)
        2. M5 MACD confirms direction
        3. M1 MACD confirms execution timing
        4. Volume on M5 above average (confirmation)
        """
        # Condition 1: M15 structure - price must be on correct side of EMA 50
        if scalp_data.close_m15 is not None and scalp_data.ema50_m15 is not None:
            if direction == "BUY" and scalp_data.close_m15 < scalp_data.ema50_m15:
                return False
            if direction == "SELL" and scalp_data.close_m15 > scalp_data.ema50_m15:
                return False

        # Condition 2: M5 MACD should agree with direction
        if scalp_data.macd_m5:
            macd_bullish = scalp_data.macd_m5.get("bullish", False)
            if direction == "BUY" and not macd_bullish:
                return False
            if direction == "SELL" and macd_bullish:
                return False

        # Condition 3: M1 MACD should agree (execution timing)
        if scalp_data.macd_m1:
            macd_bullish = scalp_data.macd_m1.get("bullish", False)
            if direction == "BUY" and not macd_bullish:
                return False
            if direction == "SELL" and macd_bullish:
                return False

        # Condition 4: Volume confirmation on M5 (at least 0.8x average)
        if scalp_data.volume_m5:
            vol_ratio = scalp_data.volume_m5.get("ratio", 0)
            if vol_ratio < 0.8:
                logger.debug(
                    f"Scalping: low volume on M5 for {scalp_data.instrument} "
                    f"(ratio={vol_ratio:.2f})"
                )
                return False

        return True

    # ── Exit Signal Detection ────────────────────────────────────────

    def get_scalping_exit_signal(
        self,
        scalp_data: ScalpingData,
        direction: str,
        method: str = "fast",
    ) -> bool:
        """
        Check if a scalping exit signal is triggered.

        Methods:
        - "fast": Exit when price closes below/above EMA 50 on M1
                  Targets ~7-10% profit, tighter management
        - "slow": Exit when price closes below/above EMA 50 on M5
                  Targets ~10%+ profit, gives more room

        Args:
            scalp_data: Current scalping analysis data
            direction: Current position direction ("BUY" or "SELL")
            method: Exit method - "fast" (M1) or "slow" (M5)

        Returns:
            True if exit signal is triggered
        """
        if method == "fast":
            # Fast exit: M1 close vs EMA 50 on M1
            close = scalp_data.close_m1
            ema = scalp_data.ema50_m1
            tf_label = "M1"
        else:
            # Slow exit: M5 close vs EMA 50 on M5
            close = scalp_data.close_m5
            ema = scalp_data.ema50_m5
            tf_label = "M5"

        if close is None or ema is None:
            return False

        if direction == "BUY":
            # For long positions, exit if price closes below EMA 50
            if close < ema:
                logger.info(
                    f"Scalping EXIT ({method}): {scalp_data.instrument} BUY "
                    f"- price {close:.5f} closed below EMA 50 {ema:.5f} on {tf_label}"
                )
                return True
        elif direction == "SELL":
            # For short positions, exit if price closes above EMA 50
            if close > ema:
                logger.info(
                    f"Scalping EXIT ({method}): {scalp_data.instrument} SELL "
                    f"- price {close:.5f} closed above EMA 50 {ema:.5f} on {tf_label}"
                )
                return True

        return False

    # ── Status ───────────────────────────────────────────────────────

    def get_scalping_status(self) -> Dict[str, Any]:
        """Get current scalping module status."""
        return {
            "setups_found": self._scalping_setups_found,
            "setups_executed": self._scalping_setups_executed,
            "timeframe_mapping": SCALPING_TIMEFRAMES,
        }

    # ── Internal Helpers ─────────────────────────────────────────────

    def _calculate_macd(
        self, df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> Optional[Dict[str, float]]:
        """Calculate MACD for a DataFrame."""
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

    def _candles_to_dataframe(self, candles) -> pd.DataFrame:
        """Convert CandleData objects to pandas DataFrame."""
        if not candles:
            return pd.DataFrame()

        rows = []
        for c in candles:
            if hasattr(c, "open"):
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
                if not c.get("complete", True):
                    continue
                mid = c.get("mid", {})
                rows.append({
                    "time": pd.Timestamp(c.get("time", "")),
                    "open": float(mid.get("o", 0)),
                    "high": float(mid.get("h", 0)),
                    "low": float(mid.get("l", 0)),
                    "close": float(mid.get("c", 0)),
                    "volume": int(c.get("volume", 0)),
                })

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        if "time" in df.columns:
            df.set_index("time", inplace=True)
        return df
