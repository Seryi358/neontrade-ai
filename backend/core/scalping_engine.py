"""
Atlas - Scalping Engine
From TradingLab Workshop de Scalping.

Scalping temporal hierarchy (compressed from day trading):
- H1: Main direction (like Daily in day trading) -> MACD + EMA 50 + SMA 200
- M15: Structure (like 4H in day trading) -> EMA 50
- M5: Confirmation (like 1H in day trading) -> EMA 50 + MACD + Volume
- M1: Execution (like 5M in day trading) -> EMA 50 break (diagonal/trendline)

Position Management (TradingLab Scalping Workshop, Section 7):
- Method 1 (fixed_tp): Set TP at Fibonacci Extension levels and walk away (safest, default)
- Method 2 (fast): Exit when price closes below EMA 50 on M1 (~7-10% profit)
- Method 3 (slow): Exit when price closes below EMA 50 on M5 (~10%+ profit)

Risk: 1% per trade (from config.py settings.risk_scalping — TradingLab mentorship 1% universal)

NOTE: The 1% per-trade risk is read from settings.risk_scalping at runtime.
The 5% daily drawdown and 10% total drawdown limits are Atlas defaults
matching funded account rules for safety. The TradingLab Scalping
Workshop says "in scalping you must risk less" but defers the exact
percentage to future upgrades. Users can lower risk_scalping via API.
"""

from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
import pandas as pd
import numpy as np
from loguru import logger

from config import settings
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
    # H1 MACD divergence (Gap 11)
    h1_macd_divergence: Optional[str] = None  # "bullish", "bearish", or None
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
                ema = df["close"].ewm(span=50, adjust=False).mean()
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

        # ── H1 MACD divergence detection (Gap 11) ──
        h1_df = candles.get("H1", pd.DataFrame())
        data.h1_macd_divergence = self._detect_macd_divergence(h1_df)

        # ── H1 direction determination ──
        # Direction based on MACD + EMA 50 + SMA 200 on H1
        data.h1_direction = self._determine_h1_direction(data)

        return data

    def _determine_h1_direction(
        self,
        data: ScalpingData,
        analysis: Optional["AnalysisResult"] = None,
    ) -> Optional[str]:
        """
        Determine the main scalping direction from H1 indicators.

        Core indicators:
        - MACD bullish/bearish on H1
        - Price above/below EMA 50 on H1
        - Price above/below SMA 200 on H1 (strong filter)
        - MACD divergence on H1 (Gap 11: confluence factor)

        Additional confluence (improves confidence, not hard blocks):
        - Support/resistance level proximity check
        - Pattern detection consideration (if available from analysis)
        - RSI divergence on H1 (workshop: "much more evident" on H1)
        """
        if data.close_h1 is None or data.ema50_h1 is None:
            return None

        price_above_ema50 = data.close_h1 > data.ema50_h1
        macd_bullish = data.macd_h1 and data.macd_h1.get("bullish", False)

        # SMA 200 filter (if available, strengthens signal)
        sma_filter = None
        if data.sma200_h1 is not None:
            sma_filter = data.close_h1 > data.sma200_h1

        # Gap 11: MACD divergence as additional confluence
        divergence = data.h1_macd_divergence

        # ── Additional confluence factors (scoring, not hard blocks) ──
        # These factors accumulate a confidence score that can tip ambiguous
        # situations toward a direction or strengthen existing signals.
        buy_confluence = 0
        sell_confluence = 0

        # S/R proximity check: if price is near a support level, it favors
        # BUY (bounce); near resistance, it favors SELL (rejection).
        if analysis is not None and analysis.key_levels:
            supports = analysis.key_levels.get("supports", [])
            resistances = analysis.key_levels.get("resistances", [])
            price = data.close_h1
            sr_proximity_pct = 0.005  # within 0.5% of level

            for s in supports:
                if s > 0 and abs(price - s) / s < sr_proximity_pct:
                    buy_confluence += 1
                    logger.debug(
                        f"Scalping H1: price near support {s:.5f} — "
                        f"BUY confluence +1"
                    )
                    break

            for r in resistances:
                if r > 0 and abs(price - r) / r < sr_proximity_pct:
                    sell_confluence += 1
                    logger.debug(
                        f"Scalping H1: price near resistance {r:.5f} — "
                        f"SELL confluence +1"
                    )
                    break

        # Pattern detection consideration (if available from analysis)
        if analysis is not None and analysis.chart_patterns:
            for pattern in analysis.chart_patterns:
                p_name = pattern.get("name", "").lower() if isinstance(pattern, dict) else str(pattern).lower()
                p_direction = pattern.get("direction", "").upper() if isinstance(pattern, dict) else ""
                if p_direction == "BUY" or any(
                    k in p_name for k in ("double bottom", "inverse head", "bull")
                ):
                    buy_confluence += 1
                elif p_direction == "SELL" or any(
                    k in p_name for k in ("double top", "head and shoulders", "bear")
                ):
                    sell_confluence += 1

        # MACD divergence on H1 — workshop emphasizes this is "much more
        # evident" on H1 than on lower timeframes.
        # NOTE: The Scalping Workshop mentions MACD divergence (NOT RSI) on H1.
        # RSI is NOT part of the Scalping Workshop indicator set.
        if analysis is not None and hasattr(analysis, 'macd_divergence') and analysis.macd_divergence:
            macd_div = analysis.macd_divergence
            if isinstance(macd_div, dict):
                h1_macd_div = macd_div.get("H1") or macd_div.get("D")  # D slot = H1 in scalping remap
            elif isinstance(macd_div, str):
                h1_macd_div = macd_div
            else:
                h1_macd_div = None

            if h1_macd_div:
                div_str = str(h1_macd_div).lower()
                if "bullish" in div_str:
                    buy_confluence += 2  # MACD div on H1 is strong signal
                    logger.info(
                        f"Scalping H1: MACD bullish divergence on "
                        f"{data.instrument} — BUY confluence +2"
                    )
                elif "bearish" in div_str:
                    sell_confluence += 2
                    logger.info(
                        f"Scalping H1: MACD bearish divergence on "
                        f"{data.instrument} — SELL confluence +2"
                    )

        # SMA 200 on H1 as dynamic S/R confluence — workshop says SMA 200 on H1
        # is "incredibly used" as dynamic support/resistance.
        if data.sma200_h1 is not None and data.close_h1 is not None:
            sma200_proximity_pct = 0.003  # within 0.3% of SMA 200
            dist_to_sma200 = abs(data.close_h1 - data.sma200_h1)
            if data.sma200_h1 > 0 and dist_to_sma200 / data.sma200_h1 < sma200_proximity_pct:
                # Price near SMA 200 — acts as dynamic S/R
                if data.close_h1 > data.sma200_h1:
                    buy_confluence += 1  # bouncing off SMA 200 as support
                    logger.debug(
                        f"Scalping H1: price near SMA 200 ({data.sma200_h1:.5f}) "
                        f"as dynamic support — BUY confluence +1"
                    )
                else:
                    sell_confluence += 1  # rejected at SMA 200 as resistance
                    logger.debug(
                        f"Scalping H1: price near SMA 200 ({data.sma200_h1:.5f}) "
                        f"as dynamic resistance — SELL confluence +1"
                    )

        # ── Primary direction logic (unchanged core) ──
        if price_above_ema50 and macd_bullish:
            if sma_filter is None or sma_filter:
                if divergence == "bearish":
                    # Bearish MACD divergence warns against BUY, but if
                    # other confluence strongly favors BUY, allow it
                    if buy_confluence >= 2:
                        logger.info(
                            f"Scalping H1: bearish MACD divergence on "
                            f"{data.instrument} overridden by strong BUY "
                            f"confluence ({buy_confluence} factors)"
                        )
                        return "BUY"
                    logger.info(
                        f"Scalping H1: bearish MACD divergence detected on "
                        f"{data.instrument} — weakening BUY direction"
                    )
                    return None
                return "BUY"
        elif not price_above_ema50 and not macd_bullish:
            if sma_filter is None or not sma_filter:
                if divergence == "bullish":
                    if sell_confluence >= 2:
                        logger.info(
                            f"Scalping H1: bullish MACD divergence on "
                            f"{data.instrument} overridden by strong SELL "
                            f"confluence ({sell_confluence} factors)"
                        )
                        return "SELL"
                    logger.info(
                        f"Scalping H1: bullish MACD divergence detected on "
                        f"{data.instrument} — weakening SELL direction"
                    )
                    return None
                return "SELL"

        # Gap 11: divergence can provide direction when standard conditions
        # are ambiguous (e.g. price near EMA 50 with no clear MACD)
        if divergence == "bullish" and (sma_filter is None or sma_filter):
            logger.info(
                f"Scalping H1: bullish MACD divergence provides BUY bias "
                f"on {data.instrument}"
            )
            return "BUY"
        if divergence == "bearish" and (sma_filter is None or not sma_filter):
            logger.info(
                f"Scalping H1: bearish MACD divergence provides SELL bias "
                f"on {data.instrument}"
            )
            return "SELL"

        # Additional confluence can tip ambiguous situations
        if buy_confluence >= 2 and sell_confluence == 0:
            logger.info(
                f"Scalping H1: strong BUY confluence ({buy_confluence} factors) "
                f"provides direction on {data.instrument} despite ambiguous "
                f"EMA/MACD"
            )
            return "BUY"
        if sell_confluence >= 2 and buy_confluence == 0:
            logger.info(
                f"Scalping H1: strong SELL confluence ({sell_confluence} factors) "
                f"provides direction on {data.instrument} despite ambiguous "
                f"EMA/MACD"
            )
            return "SELL"

        return None

    # ── Setup Detection (Compressed Strategies) ───────────────────────

    def detect_scalping_setup(
        self,
        analysis: AnalysisResult,
        scalp_data: ScalpingData,
        enabled_strategies: Optional[Dict[str, object]] = None,
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
        # Re-evaluate H1 direction with full analysis context for better
        # confluence (S/R proximity, patterns, RSI divergence on H1).
        # This enriches the initial direction determined in analyze_scalping()
        # which runs without an AnalysisResult.
        enriched_direction = self._determine_h1_direction(
            scalp_data, analysis=analysis
        )
        if enriched_direction is not None:
            scalp_data.h1_direction = enriched_direction

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
        signal = get_best_setup(scalp_analysis, enabled_strategies)
        if signal is None:
            return None

        # TradingLab Scalping Workshop (Section 10): Three options for BLUE:
        # 1. "aggressive" — trade all BLUEs regardless
        # 2. "skip_all" — skip all BLUEs entirely
        # 3. "clean_only" — only trade clean BLUEs with 80%+ confidence (recommended, but rare)
        # Configurable via settings.scalping_blue_mode (default: "clean_only")
        if signal.strategy == StrategyColor.BLUE or signal.strategy_variant in ("BLUE_A", "BLUE_B", "BLUE_C"):
            blue_mode = getattr(settings, 'scalping_blue_mode', 'clean_only')
            if blue_mode == "skip_all":
                logger.debug(f"Scalping: BLUE setup skipped (scalping_blue_mode='skip_all')")
                return None
            elif blue_mode == "clean_only":
                if signal.confidence < 80:
                    logger.debug(f"Scalping: BLUE setup rejected (confidence {signal.confidence:.0f}% < 80%, mode='clean_only')")
                    return None
            # else: "aggressive" — accept all BLUEs

        # Tag as scalping setup
        signal.reasoning = f"[SCALPING] {signal.reasoning}"
        signal.explanation_es = f"[SCALPING] {signal.explanation_es}"
        signal.timeframes_analyzed = ["H1", "M15", "M5", "M1"]

        # Enforce 0.618 Fibonacci SL for scalping (mentorship rule)
        signal = self._enforce_fibonacci_sl(signal, scalp_analysis)

        # Validate scalping-specific conditions
        validation = self._validate_scalping_conditions(scalp_data, signal.direction)
        if not validation["valid"]:
            logger.debug(
                f"Scalping: conditions not met for {signal.instrument} "
                f"{signal.direction}"
            )
            return None

        # Apply confidence adjustments from optional indicators and
        # deceleration detection
        if validation["confidence_adj"] != 0:
            original_conf = signal.confidence
            signal.confidence = max(0, min(100, signal.confidence + validation["confidence_adj"]))
            adj_reasons = "; ".join(validation["reasons"])
            logger.info(
                f"Scalping confidence adjusted for {signal.instrument}: "
                f"{original_conf:.0f}% -> {signal.confidence:.0f}% ({adj_reasons})"
            )

        # Override TP to nearest swing high/low if closer (Workshop: "safest"
        # TP for scalping is recent highs/lows on H1)
        signal = self._apply_swing_tp_override(signal, scalp_data)

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

        Strategy code uses _tf_ema() which returns NATIVE scalping keys:
          _tf_ema("direction", 50) = "EMA_H1_50"  -> H1 EMA 50
          _tf_ema("confirm", 50)   = "EMA_M15_50" -> M15 EMA 50
          _tf_ema("setup", 50)     = "EMA_M5_50"  -> M5 EMA 50
          _tf_ema("exec", 50)      = "EMA_M1_50"  -> M1 EMA 50

        We must set these native keys so the strategy reads the correct data.
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

        # Build EMA values with NATIVE scalping keys for _tf_ema() lookups
        ema_values = dict(base_analysis.ema_values)  # start with base

        if scalp_data.ema50_h1 is not None:
            ema_values["EMA_H1_50"] = scalp_data.ema50_h1    # _tf_ema("direction") = EMA_H1_50
            ema_values["EMA_D_50"] = scalp_data.ema50_h1     # Legacy day-trading slot
            ema_values["EMA_D_20"] = scalp_data.ema50_h1     # fallback
        if scalp_data.ema50_m15 is not None:
            ema_values["EMA_M15_50"] = scalp_data.ema50_m15  # _tf_ema("confirm") = EMA_M15_50
            ema_values["EMA_H4_50"] = scalp_data.ema50_m15   # Legacy day-trading slot
        if scalp_data.ema50_m5 is not None:
            ema_values["EMA_M5_50"] = scalp_data.ema50_m5    # _tf_ema("setup") = EMA_M5_50
            ema_values["EMA_M5_20"] = scalp_data.ema50_m5    # fallback for setup TF
            ema_values["EMA_M5_5"] = scalp_data.ema50_m5     # price proxy for setup TF
        if scalp_data.ema50_m1 is not None:
            ema_values["EMA_M1_50"] = scalp_data.ema50_m1    # _tf_ema("exec") = EMA_M1_50

        # Build MACD values with native scalping timeframe keys
        macd_values = dict(base_analysis.macd_values)
        if scalp_data.macd_h1:
            macd_values["H1"] = scalp_data.macd_h1    # H1 direction MACD
            macd_values["D"] = scalp_data.macd_h1     # Legacy day-trading slot
        if scalp_data.macd_m5:
            macd_values["M5"] = scalp_data.macd_m5    # M5 setup MACD
        if scalp_data.macd_m1:
            macd_values["M1"] = scalp_data.macd_m1    # M1 execution MACD

        # SMA values — H1 SMA 200 as long-term filter
        sma_values = dict(base_analysis.sma_values)
        if scalp_data.sma200_h1 is not None:
            sma_values["SMA_D_200"] = scalp_data.sma200_h1  # Legacy slot (used directly)
            sma_values["SMA_H1_200"] = scalp_data.sma200_h1 # Native key

        # Volume analysis
        volume_analysis = dict(base_analysis.volume_analysis)
        if scalp_data.volume_m5:
            volume_analysis["M5"] = scalp_data.volume_m5

        # Current price from M1
        current_price = scalp_data.close_m1 or scalp_data.close_m5

        # ── Detect H1 condition (replaces Daily condition) ──
        # Check for deceleration patterns on H1 candles instead of hardcoding NEUTRAL
        htf_condition = MarketCondition.NEUTRAL
        if not h1_df.empty and len(h1_df) >= 5:
            last_5 = h1_df.tail(5)
            bodies = abs(last_5["close"] - last_5["open"])
            if len(bodies) >= 3:
                recent_body = float(bodies.iloc[-1])
                prev_avg_body = float(bodies.iloc[-4:-1].mean())
                # Shrinking candle bodies = deceleration
                if prev_avg_body > 0 and recent_body < prev_avg_body * 0.5:
                    htf_condition = MarketCondition.DECELERATING

        # ── Compute H1 key levels from swing highs/lows ──
        # Daily S/R levels are too far from scalping entries; use H1 swings
        key_levels = dict(base_analysis.key_levels)
        if not h1_df.empty and len(h1_df) >= 10:
            h1_supports = []
            h1_resistances = []
            lookback = min(50, len(h1_df) - 2)
            lows = h1_df["low"].values
            highs = h1_df["high"].values
            for i in range(len(h1_df) - lookback, len(h1_df) - 1):
                if i < 1:
                    continue
                if lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
                    h1_supports.append(float(lows[i]))
                if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
                    h1_resistances.append(float(highs[i]))
            # Merge with base levels (H1 levels take precedence by being closer to price)
            base_supports = key_levels.get("supports", [])
            base_resistances = key_levels.get("resistances", [])
            if h1_supports:
                key_levels["supports"] = sorted(set(h1_supports + base_supports))
            if h1_resistances:
                key_levels["resistances"] = sorted(set(h1_resistances + base_resistances))

        # ── Compute H1 swing highs/lows for strategy use ──
        h1_swing_highs = []
        h1_swing_lows = []
        if not h1_df.empty and len(h1_df) >= 10:
            lookback = min(50, len(h1_df) - 2)
            for i in range(len(h1_df) - lookback, len(h1_df) - 1):
                if i < 1:
                    continue
                if lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
                    h1_swing_lows.append(float(lows[i]))
                if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
                    h1_swing_highs.append(float(highs[i]))

        # ── Detect H1 candlestick patterns for deceleration ──
        h1_candle_patterns = list(base_analysis.candlestick_patterns)
        if not h1_df.empty and len(h1_df) >= 3:
            last = h1_df.iloc[-1]
            prev = h1_df.iloc[-2]
            body = abs(last["close"] - last["open"])
            upper_wick = last["high"] - max(last["open"], last["close"])
            lower_wick = min(last["open"], last["close"]) - last["low"]
            candle_range = last["high"] - last["low"]

            if candle_range > 0:
                body_ratio = body / candle_range
                # Doji: very small body relative to range
                if body_ratio < 0.15:
                    h1_candle_patterns.append("DOJI")
                # Low test (hammer): long lower wick, small upper wick
                elif lower_wick > body * 2 and upper_wick < body:
                    h1_candle_patterns.append("LOW_TEST")
                # High test (shooting star): long upper wick, small lower wick
                elif upper_wick > body * 2 and lower_wick < body:
                    h1_candle_patterns.append("HIGH_TEST")

            # Engulfing patterns
            prev_body = abs(prev["close"] - prev["open"])
            if prev_body > 0 and body > prev_body * 1.2:
                if prev["close"] < prev["open"] and last["close"] > last["open"]:
                    h1_candle_patterns.append("ENGULFING_BULLISH")
                elif prev["close"] > prev["open"] and last["close"] < last["open"]:
                    h1_candle_patterns.append("ENGULFING_BEARISH")

        # Last candles: set native timeframe keys for scalping (10 candles for RCC/deceleration)
        last_candles = dict(base_analysis.last_candles)
        m5_candles_df = candles.get("M5", pd.DataFrame())
        if not m5_candles_df.empty and len(m5_candles_df) >= 10:
            tail = m5_candles_df.tail(10)
            m5_candle_list = [
                {"open": row["open"], "high": row["high"],
                 "low": row["low"], "close": row["close"],
                 "volume": row.get("volume", 0)}
                for _, row in tail.iterrows()
            ]
            last_candles["M5"] = m5_candle_list    # Native M5 key
            last_candles["H1"] = m5_candle_list    # Legacy slot (setup TF)
        m1_candles_df = candles.get("M1", pd.DataFrame())
        if not m1_candles_df.empty and len(m1_candles_df) >= 10:
            tail = m1_candles_df.tail(10)
            m1_candle_list = [
                {"open": row["open"], "high": row["high"],
                 "low": row["low"], "close": row["close"],
                 "volume": row.get("volume", 0)}
                for _, row in tail.iterrows()
            ]
            last_candles["M1"] = m1_candle_list    # Native M1 key
        h1_candles_df = candles.get("H1", pd.DataFrame())
        if not h1_candles_df.empty and len(h1_candles_df) >= 3:
            tail = h1_candles_df.tail(3)
            last_candles["H1_raw"] = [
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
            key_levels=key_levels,
            ema_values=ema_values,
            fibonacci_levels=base_analysis.fibonacci_levels,
            candlestick_patterns=h1_candle_patterns,
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
            # Pass through weekly EMA8 from base analysis (needed by strategy filters)
            ema_w8=base_analysis.ema_w8,
            swing_highs=h1_swing_highs if h1_swing_highs else base_analysis.swing_highs,
            swing_lows=h1_swing_lows if h1_swing_lows else base_analysis.swing_lows,
            elliott_wave=base_analysis.elliott_wave,
        )

        return scalp_result

    def _validate_scalping_conditions(
        self, scalp_data: ScalpingData, direction: str
    ) -> Dict[str, Any]:
        """
        Validate scalping-specific entry conditions and return a confidence
        adjustment instead of a binary pass/fail for optional indicators.

        Hard requirements (reject if failed):
        1. M15 EMA 50 break confirms structure (price on correct side)
        3. M1 EMA 50 break confirms execution timing
        5. Deceleration on H1 and M5 (Workshop Steps 3 and 6)

        Soft/optional indicators (reduce confidence, do not reject):
        2. M5 MACD agreement — the mentor says "I don't usually use MACD
           on M5" and it's "not obligatory." Disagreement reduces confidence
           by 10-15 points instead of rejecting.
        4. Volume on M5 — important but not a hard gate per workshop.

        Returns:
            Dict with:
              - valid (bool): False only if a hard requirement fails.
              - confidence_adj (int): Confidence adjustment (negative = penalty).
              - reasons (list[str]): Explanation of adjustments applied.
        """
        result = {"valid": True, "confidence_adj": 0, "reasons": []}

        # Condition 1: M15 EMA 50 BREAKOUT confirmation (Workshop Step 3)
        # Workshop: "Confirm the EMA 50 on the 15-minute chart HAS BEEN BROKEN"
        # This requires a recent crossover, not just current positioning.
        # Check: (a) price is on correct side AND (b) a recent breakout occurred.
        if scalp_data.close_m15 is not None and scalp_data.ema50_m15 is not None:
            # (a) Price must be on correct side
            if direction == "BUY" and scalp_data.close_m15 < scalp_data.ema50_m15:
                result["valid"] = False
                return result
            if direction == "SELL" and scalp_data.close_m15 > scalp_data.ema50_m15:
                result["valid"] = False
                return result

            # (b) Detect recent M15 EMA 50 breakout (crossover within last N candles)
            m15_df = scalp_data.candles.get("M15", pd.DataFrame())
            if not m15_df.empty and len(m15_df) >= 10:
                closes = m15_df["close"].values
                # Calculate EMA 50 for recent M15 candles to find crossover
                if len(closes) >= 52:
                    ema_values = pd.Series(closes).ewm(span=50, adjust=False).mean().values
                    # Check last 8 candles for a crossover
                    recent_breakout = False
                    lookback = min(8, len(ema_values) - 1)
                    for i in range(-lookback, 0):
                        prev_close = closes[i - 1]
                        curr_close = closes[i]
                        prev_ema = ema_values[i - 1]
                        curr_ema = ema_values[i]
                        if direction == "BUY":
                            # Breakout up: was below, now above
                            if prev_close < prev_ema and curr_close > curr_ema:
                                recent_breakout = True
                                break
                        else:  # SELL
                            # Breakout down: was above, now below
                            if prev_close > prev_ema and curr_close < curr_ema:
                                recent_breakout = True
                                break

                    if not recent_breakout:
                        logger.debug(
                            f"Scalping: M15 EMA 50 not recently broken for "
                            f"{scalp_data.instrument} {direction} — "
                            f"workshop requires a breakout, not just positioning"
                        )
                        result["valid"] = False
                        return result

        # Condition 2: M5 MACD — OPTIONAL, not a hard requirement.
        # Per the mentor: "I don't usually use MACD on M5" / "not obligatory."
        # Disagreement reduces confidence by 10-15 points instead of rejecting.
        if scalp_data.macd_m5:
            macd_bullish = scalp_data.macd_m5.get("bullish", False)
            macd_disagrees = (
                (direction == "BUY" and not macd_bullish)
                or (direction == "SELL" and macd_bullish)
            )
            if macd_disagrees:
                penalty = -12  # 10-15 range, use midpoint
                result["confidence_adj"] += penalty
                result["reasons"].append(
                    f"M5 MACD disagrees with {direction} direction "
                    f"(confidence {penalty}pts — optional indicator)"
                )
                logger.debug(
                    f"Scalping: M5 MACD disagrees on {scalp_data.instrument} "
                    f"{direction} — applying {penalty}pt confidence penalty "
                    f"(not rejecting, MACD on M5 is optional per mentor)"
                )

        # Condition 3: M1 execution trigger — breakout + confirmation (Workshop Step 6)
        # Workshop: "Requires both: breakout + confirmation (not just the breakout candle)"
        # Workshop: "Does it have to be the EMA? No. We look for a trend change —
        #            sometimes EMA, sometimes diagonal."
        # Two valid breakout types: EMA 50 OR diagonal/trendline break
        m1_ema_breakout = False
        m1_diagonal_breakout = False

        if scalp_data.close_m1 is not None and scalp_data.ema50_m1 is not None:
            # (a) Check EMA 50 breakout on M1
            if direction == "BUY" and scalp_data.close_m1 > scalp_data.ema50_m1:
                m1_ema_breakout = True
            elif direction == "SELL" and scalp_data.close_m1 < scalp_data.ema50_m1:
                m1_ema_breakout = True

        # (b) Check diagonal/trendline breakout on M1
        # Workshop: "buscamos un cambio de tendencia — a veces EMA, a veces diagonal"
        m1_df = scalp_data.candles.get("M1", pd.DataFrame())
        if not m1_df.empty and len(m1_df) >= 10:
            highs = m1_df["high"].values
            lows = m1_df["low"].values
            closes = m1_df["close"].values

            # Detect diagonal/trendline break: 3+ descending highs then break above
            # (bullish) or 3+ ascending lows then break below (bearish)
            if direction == "BUY" and len(highs) >= 5:
                # Look for descending trendline on recent M1 highs (last 10-20 candles)
                lookback = min(20, len(highs) - 1)
                recent_highs = highs[-lookback:-1]  # Exclude current candle
                if len(recent_highs) >= 3:
                    # Simple linear regression on highs to detect descending trendline
                    x = np.arange(len(recent_highs))
                    coeffs = np.polyfit(x, recent_highs, 1) if len(x) > 1 else [0, recent_highs[-1]]
                    if coeffs[0] < 0:  # Descending trendline exists
                        # Project trendline to current candle (next index after fitted data)
                        projected = np.polyval(coeffs, len(x))
                        if closes[-1] > projected:  # Current close breaks above trendline
                            m1_diagonal_breakout = True
                            result["reasons"].append(
                                "M1 diagonal/trendline breakout detected (descending trendline broken)"
                            )
            elif direction == "SELL" and len(lows) >= 5:
                lookback = min(20, len(lows) - 1)
                recent_lows = lows[-lookback:-1]
                if len(recent_lows) >= 3:
                    x = np.arange(len(recent_lows))
                    coeffs = np.polyfit(x, recent_lows, 1) if len(x) > 1 else [0, recent_lows[-1]]
                    if coeffs[0] > 0:  # Ascending trendline exists
                        # Project trendline to current candle (next index after fitted data)
                        projected = np.polyval(coeffs, len(x))
                        if closes[-1] < projected:  # Current close breaks below trendline
                            m1_diagonal_breakout = True
                            result["reasons"].append(
                                "M1 diagonal/trendline breakout detected (ascending trendline broken)"
                            )

        # Must have at least ONE breakout type (EMA or diagonal)
        if not m1_ema_breakout and not m1_diagonal_breakout:
            result["valid"] = False
            return result

        if m1_ema_breakout and m1_diagonal_breakout:
            result["confidence_adj"] += 10
            result["reasons"].append("M1 double breakout: EMA 50 + diagonal (strong confirmation)")

        # (c) Breakout confirmation: verify consecutive candle closes for EMA breakout
        # Workshop: "we do NOT execute at breakout alone, we execute when there
        # is breakout AND confirmation."
        # - EMA 50 break + confirmation candle: full confidence
        # - EMA 50 break + NO confirmation but diagonal break exists: -15 penalty
        # - NO EMA break AND NO diagonal break: REJECT (hard gate)
        if m1_ema_breakout and not m1_df.empty and len(m1_df) >= 3:
            closes = m1_df["close"].values
            if len(closes) >= 52:
                ema_vals = pd.Series(closes).ewm(span=50, adjust=False).mean().values
                prev_close = closes[-2]
                prev_ema = ema_vals[-2]
                confirmation_failed = (
                    (direction == "BUY" and prev_close < prev_ema)
                    or (direction == "SELL" and prev_close > prev_ema)
                )
                if confirmation_failed:
                    if m1_diagonal_breakout:
                        # Diagonal break provides partial confirmation — penalty only
                        result["confidence_adj"] -= 15
                        result["reasons"].append(
                            "M1 EMA 50 breakout not yet confirmed (need 2 consecutive closes), "
                            "but diagonal breakout provides partial confirmation"
                        )
                    else:
                        # No confirmation AND no diagonal break — hard reject
                        result["valid"] = False
                        result["reasons"].append(
                            "REJECTED: M1 EMA 50 breakout without confirmation candle "
                            "and no diagonal breakout — workshop requires breakout + confirmation"
                        )
                        return result

        # Condition 4: Volume on M5 — Workshop says volume is "important" on M5
        # but does NOT make it a hard entry requirement. Treat as confluence
        # scoring: low volume reduces confidence, does not reject.
        if scalp_data.volume_m5:
            vol_ratio = scalp_data.volume_m5.get("ratio", 0)
            if vol_ratio < 0.8:
                penalty = -10
                result["confidence_adj"] += penalty
                result["reasons"].append(
                    f"M5 volume low ({vol_ratio:.2f}x avg) — "
                    f"confidence {penalty}pts (workshop: important, not required)"
                )
                logger.debug(
                    f"Scalping: low volume on M5 for {scalp_data.instrument} "
                    f"(ratio={vol_ratio:.2f}) — applying {penalty}pt penalty"
                )
            elif vol_ratio > 1.5:
                bonus = 5
                result["confidence_adj"] += bonus
                result["reasons"].append(
                    f"M5 volume strong ({vol_ratio:.2f}x avg) — confidence +{bonus}pts"
                )

        # Deceleration detection on H1 and M5 (Workshop steps 2 and 5)
        # Workshop Step 2: H1 deceleration "must" occur — HARD requirement for RED setups.
        # Workshop Step 5: M5 deceleration — "Do NOT enter without it" — HARD requirement.
        h1_decel = self._detect_deceleration(
            scalp_data.candles.get("H1", pd.DataFrame()), direction
        )
        if h1_decel:
            result["confidence_adj"] += h1_decel["adj"]
            result["reasons"].append(f"H1 deceleration: {h1_decel['reason']}")
        else:
            # Workshop Step 2: H1 deceleration is REQUIRED (hard rejection)
            logger.debug(
                f"Scalping: H1 deceleration NOT detected for {scalp_data.instrument} "
                f"{direction} — workshop requires this (Step 2)"
            )
            result["valid"] = False
            return result

        m5_decel = self._detect_deceleration(
            scalp_data.candles.get("M5", pd.DataFrame()), direction
        )
        if m5_decel:
            result["confidence_adj"] += m5_decel["adj"]
            result["reasons"].append(f"M5 deceleration: {m5_decel['reason']}")
        else:
            # Workshop Step 5: M5 deceleration is REQUIRED — "Do NOT enter" without it
            logger.debug(
                f"Scalping: M5 deceleration NOT detected for {scalp_data.instrument} "
                f"{direction} — workshop requires this (Step 5)"
            )
            result["valid"] = False
            return result

        return result

    # ── Deceleration Detection (Workshop Steps 2 & 5) ─────────────────

    def _detect_deceleration(
        self,
        df: pd.DataFrame,
        direction: str,
        lookback: int = 5,
    ) -> Optional[Dict[str, Any]]:
        """
        Detect deceleration of the PULLBACK on a timeframe by checking
        for decreasing candle body sizes and increasing absorption wicks
        over the last 3-5 candles.

        Workshop steps 2 (H1) and 5 (M5) require detecting "desaceleración
        y giro" (deceleration and reversal) of the pullback as a required
        confirmation before entry. This is a POSITIVE signal — the pullback
        is losing steam, confirming the trade setup.

        Pullback deceleration indicators:
        - Decreasing candle body sizes (pullback momentum fading)
        - For BUY: increasing lower wicks = buying pressure absorbing
          the bearish pullback (market pushing back up)
        - For SELL: increasing upper wicks = selling pressure absorbing
          the bullish pullback (market pushing back down)

        Args:
            df: OHLCV DataFrame for the timeframe.
            direction: "BUY" or "SELL" — the current trade direction.
            lookback: Number of recent candles to examine (3-5).

        Returns:
            Dict with 'adj' (positive confidence boost) and 'reason',
            or None if no deceleration detected.
        """
        if df.empty or len(df) < lookback:
            return None

        tail = df.tail(lookback)
        bodies = abs(tail["close"] - tail["open"]).values
        upper_wicks = (tail["high"] - tail[["close", "open"]].max(axis=1)).values
        lower_wicks = (tail[["close", "open"]].min(axis=1) - tail["low"]).values

        # Check for decreasing body sizes: compare first half vs second half
        mid = lookback // 2
        first_bodies = bodies[:mid]
        second_bodies = bodies[mid:]

        avg_first_body = float(np.mean(first_bodies)) if len(first_bodies) > 0 else 0
        avg_second_body = float(np.mean(second_bodies)) if len(second_bodies) > 0 else 0

        bodies_decreasing = (
            avg_first_body > 0
            and avg_second_body < avg_first_body * 0.7  # 30%+ decrease
        )

        # Check for increasing absorption wicks that fight the pullback
        if direction == "BUY":
            # For BUY: increasing lower wicks = buying pressure absorbing
            # the bearish pullback (good — pullback losing steam)
            wicks = lower_wicks
        else:
            # For SELL: increasing upper wicks = selling pressure absorbing
            # the bullish pullback (good — pullback losing steam)
            wicks = upper_wicks

        first_wicks = wicks[:mid]
        second_wicks = wicks[mid:]
        avg_first_wick = float(np.mean(first_wicks)) if len(first_wicks) > 0 else 0
        avg_second_wick = float(np.mean(second_wicks)) if len(second_wicks) > 0 else 0

        wicks_increasing = (
            avg_first_wick > 0
            and avg_second_wick > avg_first_wick * 1.3  # 30%+ increase
        )

        if bodies_decreasing and wicks_increasing:
            # Strong pullback deceleration — highly confirms setup
            return {
                "adj": +10,
                "reason": (
                    f"pullback decelerating: body sizes shrinking "
                    f"({avg_first_body:.5f} -> {avg_second_body:.5f}) and "
                    f"absorption wicks increasing ({avg_first_wick:.5f} -> "
                    f"{avg_second_wick:.5f}) over last {lookback} candles"
                ),
            }
        elif bodies_decreasing:
            # Mild pullback deceleration
            return {
                "adj": +5,
                "reason": (
                    f"pullback decelerating: body sizes shrinking "
                    f"({avg_first_body:.5f} -> {avg_second_body:.5f}) "
                    f"over last {lookback} candles"
                ),
            }
        elif wicks_increasing:
            # Absorption wicks increasing
            return {
                "adj": +5,
                "reason": (
                    f"pullback absorption: wicks increasing "
                    f"({avg_first_wick:.5f} -> {avg_second_wick:.5f}) "
                    f"over last {lookback} candles"
                ),
            }

        return None

    # ── TP Override to Nearest Swing High/Low (Workshop) ─────────────

    def _apply_swing_tp_override(
        self,
        signal: SetupSignal,
        scalp_data: ScalpingData,
        swing_lookback: int = 50,
    ) -> SetupSignal:
        """
        Override TP1 to the nearest swing high (for BUY) or swing low
        (for SELL) from M15 or H1 timeframes, if it is closer than the
        strategy-generated TP.

        Workshop says the "safest" TP for scalping is recent highs/lows.
        The workshop context is the pullback zone analysis on 15-min and
        5-min charts, so M15 swing points are preferred. H1 is the bias
        chart — its swing points may be too far for scalping targets.

        Priority: check M15 first, then H1 as fallback.

        Args:
            signal: The SetupSignal with strategy-generated TP.
            scalp_data: ScalpingData with candles.
            swing_lookback: Number of candles to scan for swing points.

        Returns:
            The signal, potentially with TP1 overridden.
        """
        # Try M15 first (closer to scalping context), then H1 as fallback
        m15_df = scalp_data.candles.get("M15", pd.DataFrame())
        h1_df = scalp_data.candles.get("H1", pd.DataFrame())

        if not m15_df.empty and len(m15_df) >= 5:
            recent = m15_df.tail(swing_lookback)
            tf_label = "M15"
        elif not h1_df.empty and len(h1_df) >= 5:
            recent = h1_df.tail(swing_lookback)
            tf_label = "H1"
        else:
            return signal

        if signal.direction == "BUY":
            # Find swing highs: candles where high > neighbors
            swing_levels = []
            highs = recent["high"].values
            for i in range(1, len(highs) - 1):
                if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
                    swing_levels.append(float(highs[i]))

            # Only consider swing highs above entry price
            candidates = [s for s in swing_levels if s > signal.entry_price]
            if not candidates:
                return signal

            nearest_swing = min(candidates)  # nearest swing high above entry

            # Override TP1 if the swing high is closer (safer)
            if hasattr(signal, "take_profit_1") and signal.take_profit_1 is not None:
                if nearest_swing < signal.take_profit_1:
                    original_tp = signal.take_profit_1
                    signal.take_profit_1 = nearest_swing
                    # Recalculate R:R
                    sl_distance = abs(signal.entry_price - signal.stop_loss)
                    tp_distance = abs(signal.take_profit_1 - signal.entry_price)
                    if sl_distance > 0:
                        signal.risk_reward_ratio = tp_distance / sl_distance
                    logger.info(
                        f"Scalping TP override: {signal.instrument} BUY TP1 "
                        f"{original_tp:.5f} -> {nearest_swing:.5f} (nearest"
                        f"swing high on {tf_label}, R:R {signal.risk_reward_ratio:.2f}:1)"
                    )

        elif signal.direction == "SELL":
            # Find swing lows: candles where low < neighbors
            swing_levels = []
            lows = recent["low"].values
            for i in range(1, len(lows) - 1):
                if lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
                    swing_levels.append(float(lows[i]))

            # Only consider swing lows below entry price
            candidates = [s for s in swing_levels if s < signal.entry_price]
            if not candidates:
                return signal

            nearest_swing = max(candidates)  # nearest swing low below entry

            # Override TP1 if the swing low is closer (safer)
            if hasattr(signal, "take_profit_1") and signal.take_profit_1 is not None:
                if nearest_swing > signal.take_profit_1:
                    original_tp = signal.take_profit_1
                    signal.take_profit_1 = nearest_swing
                    sl_distance = abs(signal.entry_price - signal.stop_loss)
                    tp_distance = abs(signal.take_profit_1 - signal.entry_price)
                    if sl_distance > 0:
                        signal.risk_reward_ratio = tp_distance / sl_distance
                    logger.info(
                        f"Scalping TP override: {signal.instrument} SELL TP1 "
                        f"{original_tp:.5f} -> {nearest_swing:.5f} (nearest"
                        f"swing low on {tf_label}, R:R {signal.risk_reward_ratio:.2f}:1)"
                    )

        return signal

    def _enforce_fibonacci_sl(
        self, signal: SetupSignal, analysis: AnalysisResult
    ) -> SetupSignal:
        """
        Enforce the 0.618 Fibonacci retracement level as SL for scalping.

        The mentorship explicitly states: "Stop Loss at the 0.618 Fibonacci
        retracement of the impulse move on the 15-minute chart."

        KNOWN LIMITATION: Fibonacci levels come from the analysis pipeline which uses
        Daily/H4 for day trading. For scalping accuracy, these should be recomputed
        from the M15 impulse move (swing low to swing high of the M15 EMA 50 break).
        The current approach uses whatever Fibonacci the analysis provides, which may
        be from a higher timeframe than ideal for scalping precision.
        Future improvement: add _compute_scalping_fibonacci(m15_candles) method.
        """
        fib_618 = (analysis.fibonacci_levels or {}).get("0.618")
        if fib_618 is None or fib_618 <= 0:
            return signal

        original_sl = signal.stop_loss

        if signal.direction == "BUY":
            # For BUY, SL must be below entry. Fib 0.618 should be below entry.
            if fib_618 < signal.entry_price:
                signal.stop_loss = fib_618
            else:
                return signal
        else:  # SELL
            # For SELL, SL must be above entry. Fib 0.618 should be above entry.
            if fib_618 > signal.entry_price:
                signal.stop_loss = fib_618
            else:
                return signal

        if signal.stop_loss != original_sl:
            # Recalculate R:R with the new SL
            sl_distance = abs(signal.entry_price - signal.stop_loss)
            tp_distance = abs(signal.take_profit_1 - signal.entry_price)
            signal.risk_reward_ratio = (
                tp_distance / sl_distance if sl_distance > 0 else 0.0
            )
            logger.info(
                f"Scalping SL enforced to Fib 0.618 ({fib_618:.5f}) for "
                f"{signal.instrument} {signal.direction} "
                f"(was {original_sl:.5f}, R:R now {signal.risk_reward_ratio:.2f}:1)"
            )

        return signal

    # ── Exit Signal Detection ────────────────────────────────────────

    def get_scalping_exit_signal(
        self,
        scalp_data: ScalpingData,
        direction: str,
        method: str = "fixed_tp",
        ema_buffer_pct: float = 0.001,
    ) -> Dict[str, Any]:
        """
        Check if a scalping exit signal is triggered using gradual trailing SL
        instead of a binary exit (Gap 12).

        Instead of exiting immediately when price crosses EMA 50, this method:
        1. Trails the SL behind EMA 50 with a small buffer as price advances.
        2. Only triggers a hard exit when the full candle body closes
           aggressively through EMA 50 (not just a wick touch).

        Methods (TradingLab Scalping Workshop, Section 7):
        - "fixed_tp": Method 1 — Hold until TP is hit (set at Fibonacci Extension).
                      No trailing logic. Safest and instructor's default.
        - "fast": Method 2 — Trail / exit based on EMA 50 on M1 (~7-10% profit)
        - "slow": Method 3 — Trail / exit based on EMA 50 on M5 (~10%+ profit)

        Args:
            scalp_data: Current scalping analysis data
            direction: Current position direction ("BUY" or "SELL")
            method: Exit method - "fixed_tp", "fast" (M1), or "slow" (M5)
            ema_buffer_pct: Buffer as fraction of EMA for trailing SL
                            (default 0.1% = 0.001)

        Returns:
            Dict with:
              - should_exit (bool): True only on aggressive close through EMA
              - new_trailing_sl (float | None): Suggested trailing SL level
              - reason (str): Human-readable explanation
        """
        # Method 1 (fixed_tp): No trailing — just hold until TP or SL hits.
        # Workshop: "Set TP at Fibonacci Extension levels and walk away"
        if method == "fixed_tp":
            return {
                "should_exit": False,
                "new_trailing_sl": None,
                "reason": "Method 1 (fixed_tp): holding until TP/SL hit — no trailing",
            }

        if method == "fast":
            close = scalp_data.close_m1
            ema = scalp_data.ema50_m1
            tf_label = "M1"
            tf_key = "M1"
        else:
            close = scalp_data.close_m5
            ema = scalp_data.ema50_m5
            tf_label = "M5"
            tf_key = "M5"

        if close is None or ema is None:
            return {"should_exit": False, "new_trailing_sl": None, "reason": ""}

        # Get the last candle to inspect body vs wick
        candle_df = scalp_data.candles.get(tf_key, pd.DataFrame())
        candle_open = None
        if not candle_df.empty:
            candle_open = float(candle_df["open"].iloc[-1])

        buffer = ema * ema_buffer_pct

        if direction == "BUY":
            trailing_sl = ema - buffer  # SL trails below EMA 50

            # Check for aggressive bearish close: full candle body below EMA
            body_closed_below = (
                candle_open is not None
                and close < ema
                and candle_open < ema
            )

            if body_closed_below:
                logger.info(
                    f"Scalping EXIT ({method}): {scalp_data.instrument} BUY "
                    f"- candle body [{candle_open:.5f}->{close:.5f}] closed "
                    f"aggressively below EMA 50 {ema:.5f} on {tf_label}"
                )
                return {
                    "should_exit": True,
                    "new_trailing_sl": None,
                    "reason": (
                        f"Aggressive close below EMA 50 on {tf_label}: "
                        f"body [{candle_open:.5f}->{close:.5f}], "
                        f"EMA={ema:.5f}"
                    ),
                }

            # Price still favourable — trail the SL behind EMA 50
            if close > ema:
                return {
                    "should_exit": False,
                    "new_trailing_sl": trailing_sl,
                    "reason": (
                        f"Trailing SL to {trailing_sl:.5f} "
                        f"(EMA 50 {ema:.5f} - {ema_buffer_pct:.1%} buffer) "
                        f"on {tf_label}"
                    ),
                }

            # Wick touch only (close below but open above) — tighten SL,
            # do not exit yet
            return {
                "should_exit": False,
                "new_trailing_sl": trailing_sl,
                "reason": (
                    f"Wick touch below EMA 50 on {tf_label} — tightening SL "
                    f"to {trailing_sl:.5f}, waiting for aggressive close"
                ),
            }

        elif direction == "SELL":
            trailing_sl = ema + buffer  # SL trails above EMA 50

            # Check for aggressive bullish close: full candle body above EMA
            body_closed_above = (
                candle_open is not None
                and close > ema
                and candle_open > ema
            )

            if body_closed_above:
                logger.info(
                    f"Scalping EXIT ({method}): {scalp_data.instrument} SELL "
                    f"- candle body [{candle_open:.5f}->{close:.5f}] closed "
                    f"aggressively above EMA 50 {ema:.5f} on {tf_label}"
                )
                return {
                    "should_exit": True,
                    "new_trailing_sl": None,
                    "reason": (
                        f"Aggressive close above EMA 50 on {tf_label}: "
                        f"body [{candle_open:.5f}->{close:.5f}], "
                        f"EMA={ema:.5f}"
                    ),
                }

            # Price still favourable — trail the SL behind EMA 50
            if close < ema:
                return {
                    "should_exit": False,
                    "new_trailing_sl": trailing_sl,
                    "reason": (
                        f"Trailing SL to {trailing_sl:.5f} "
                        f"(EMA 50 {ema:.5f} + {ema_buffer_pct:.1%} buffer) "
                        f"on {tf_label}"
                    ),
                }

            # Wick touch only — tighten SL, do not exit yet
            return {
                "should_exit": False,
                "new_trailing_sl": trailing_sl,
                "reason": (
                    f"Wick touch above EMA 50 on {tf_label} — tightening SL "
                    f"to {trailing_sl:.5f}, waiting for aggressive close"
                ),
            }

        return {"should_exit": False, "new_trailing_sl": None, "reason": ""}

    # ── Status ───────────────────────────────────────────────────────

    def get_scalping_status(self) -> Dict[str, Any]:
        """Get current scalping module status."""
        return {
            "setups_found": self._scalping_setups_found,
            "setups_executed": self._scalping_setups_executed,
            "timeframe_mapping": SCALPING_TIMEFRAMES,
        }

    # ── Limit Entry Confluence (Gap 13) ─────────────────────────────

    def check_limit_entry_confluence(
        self,
        analysis: AnalysisResult,
        direction: str,
        entry_price: float,
        scalp_data: Optional[ScalpingData] = None,
        zone_threshold: float = 0.003,
    ) -> Dict[str, Any]:
        """
        Check if 4 confluence levels align for a limit order entry (Gap 13).

        The workshop requires 4 parameters for a valid limit entry:
        1. EMA 50 M5
        2. EMA 50 M15
        3. Fibonacci level (0.382-0.618)
        4. One extra level (S/R, diagonal, or other)

        If all 4 align within a narrow zone (default 0.3% of zone center),
        suggest a limit entry at the zone center instead of a market entry.

        Args:
            analysis: The AnalysisResult with fibonacci / key levels.
            direction: "BUY" or "SELL".
            entry_price: The current market price for reference.
            scalp_data: ScalpingData with EMA values (if available).
            zone_threshold: Maximum zone width as a fraction of the center
                            (default 0.003 = 0.3%).

        Returns:
            Dict with:
              - use_limit (bool): True if a limit entry is recommended.
              - limit_price (float): Suggested limit price (zone center).
              - confluences (list): List of (label, value) tuples.
        """
        levels: List[tuple] = []

        # 1. EMA 50 M5
        ema_m5 = None
        if scalp_data and scalp_data.ema50_m5 is not None:
            ema_m5 = scalp_data.ema50_m5
        elif "EMA_H1_50" in analysis.ema_values:
            # Scalping remap: M5 -> H1 slot
            ema_m5 = analysis.ema_values["EMA_H1_50"]
        if ema_m5 is not None:
            levels.append(("EMA_M5", ema_m5))

        # 2. EMA 50 M15
        ema_m15 = None
        if scalp_data and scalp_data.ema50_m15 is not None:
            ema_m15 = scalp_data.ema50_m15
        elif "EMA_H4_50" in analysis.ema_values:
            # Scalping remap: M15 -> H4 slot
            ema_m15 = analysis.ema_values["EMA_H4_50"]
        if ema_m15 is not None:
            levels.append(("EMA_M15", ema_m15))

        # 3. Fibonacci level (pick the closest level in the 0.382-0.618 range)
        fib_levels = analysis.fibonacci_levels or {}
        best_fib = None
        best_fib_dist = float("inf")
        for fib_key, fib_val in fib_levels.items():
            # Accept levels whose key indicates 0.382-0.618 range
            try:
                fib_ratio = float(fib_key)
            except (ValueError, TypeError):
                # Try extracting from string like "fib_0.382"
                for token in str(fib_key).split("_"):
                    try:
                        fib_ratio = float(token)
                        break
                    except ValueError:
                        continue
                else:
                    continue
            if 0.382 <= fib_ratio <= 0.618:
                dist = abs(fib_val - entry_price)
                if dist < best_fib_dist:
                    best_fib_dist = dist
                    best_fib = fib_val
        if best_fib is not None:
            levels.append(("Fib", best_fib))

        # 4. One extra level: nearest support (for BUY) or resistance (for SELL)
        key_levels = analysis.key_levels or {}
        sr_level = None
        if direction == "BUY":
            supports = key_levels.get("supports", [])
            if supports:
                # Nearest support at or below entry_price
                below = [s for s in supports if s <= entry_price]
                if below:
                    sr_level = max(below)
                else:
                    sr_level = min(supports, key=lambda s: abs(s - entry_price))
        else:
            resistances = key_levels.get("resistances", [])
            if resistances:
                # Nearest resistance at or above entry_price
                above = [r for r in resistances if r >= entry_price]
                if above:
                    sr_level = min(above)
                else:
                    sr_level = min(
                        resistances, key=lambda r: abs(r - entry_price)
                    )
        if sr_level is not None:
            levels.append(("S/R", sr_level))

        # Evaluate confluence zone
        if len(levels) >= 4:
            values = [lv[1] for lv in levels]
            zone_center = sum(values) / len(values)
            if zone_center > 0:
                zone_width = (max(values) - min(values)) / zone_center
                if zone_width < zone_threshold:
                    logger.info(
                        f"Scalping LIMIT confluence on {analysis.instrument}: "
                        f"{len(levels)} levels within {zone_width:.4%} — "
                        f"zone center {zone_center:.5f}"
                    )
                    return {
                        "use_limit": True,
                        "limit_price": zone_center,
                        "confluences": levels,
                    }

        return {"use_limit": False, "limit_price": None, "confluences": levels}

    # ── Internal Helpers ─────────────────────────────────────────────

    def _detect_macd_divergence(
        self, df: pd.DataFrame, lookback: int = 30
    ) -> Optional[str]:
        """
        Detect MACD histogram divergence from price on a given DataFrame
        (Gap 11).

        Bullish divergence: price makes a lower low but MACD histogram
                            makes a higher low.
        Bearish divergence: price makes a higher high but MACD histogram
                            makes a lower high.

        Args:
            df: OHLCV DataFrame (typically H1 candles).
            lookback: Number of recent candles to scan for swing points.

        Returns:
            "bullish", "bearish", or None.
        """
        if df.empty or len(df) < 35:
            return None

        macd_data = self._calculate_macd(df)
        if macd_data is None:
            return None

        # Recompute full histogram series for swing detection
        ema_fast = df["close"].ewm(span=12, adjust=False).mean()
        ema_slow = df["close"].ewm(span=26, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        histogram = macd_line - signal_line

        # Work on the last `lookback` candles
        price_series = df["close"].iloc[-lookback:]
        hist_series = histogram.iloc[-lookback:]
        low_series = df["low"].iloc[-lookback:]
        high_series = df["high"].iloc[-lookback:]

        # Find local lows (for bullish divergence)
        # A local low: lower than the candle before and after
        lows_idx = []
        for i in range(1, len(low_series) - 1):
            if (low_series.iloc[i] < low_series.iloc[i - 1]
                    and low_series.iloc[i] < low_series.iloc[i + 1]):
                lows_idx.append(i)

        # Find local highs (for bearish divergence)
        highs_idx = []
        for i in range(1, len(high_series) - 1):
            if (high_series.iloc[i] > high_series.iloc[i - 1]
                    and high_series.iloc[i] > high_series.iloc[i + 1]):
                highs_idx.append(i)

        # Check bullish divergence: compare the two most recent lows
        if len(lows_idx) >= 2:
            prev_low_i = lows_idx[-2]
            curr_low_i = lows_idx[-1]
            price_lower_low = low_series.iloc[curr_low_i] < low_series.iloc[prev_low_i]
            hist_higher_low = hist_series.iloc[curr_low_i] > hist_series.iloc[prev_low_i]
            if price_lower_low and hist_higher_low:
                logger.debug(
                    "MACD bullish divergence: price lower low but histogram higher low"
                )
                return "bullish"

        # Check bearish divergence: compare the two most recent highs
        if len(highs_idx) >= 2:
            prev_high_i = highs_idx[-2]
            curr_high_i = highs_idx[-1]
            price_higher_high = high_series.iloc[curr_high_i] > high_series.iloc[prev_high_i]
            hist_lower_high = hist_series.iloc[curr_high_i] < hist_series.iloc[prev_high_i]
            if price_higher_high and hist_lower_high:
                logger.debug(
                    "MACD bearish divergence: price higher high but histogram lower high"
                )
                return "bearish"

        return None

    def _calculate_macd(
        self, df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> Optional[Dict[str, float]]:
        """Calculate MACD for a DataFrame."""
        if df.empty or len(df) < slow + signal:
            return None

        ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line

        macd_last = macd_line.iloc[-1]
        signal_last = signal_line.iloc[-1]
        hist_last = histogram.iloc[-1]
        if pd.isna(macd_last) or pd.isna(signal_last) or pd.isna(hist_last):
            return None

        return {
            "macd": float(macd_last),
            "signal": float(signal_last),
            "histogram": float(hist_last),
            "bullish": bool(macd_last > signal_last),
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
        # Filter out zero-OHLC candles (broker returns empty data that corrupts indicators)
        # Same check as market_analyzer._candles_to_dataframe Rule #9
        if not df.empty:
            valid = (df[['open', 'high', 'low', 'close']] != 0).all(axis=1)
            df = df[valid]
        return df
