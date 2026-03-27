"""
NeonTrade AI - Crypto Market Cycle Analyzer
Tracks BTC dominance, altcoin season, and market cycle phases.
Concepts from TradingLab Crypto Specialization Module 6.
"""

import httpx
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class CryptoMarketCycle:
    btc_dominance: Optional[float] = None  # BTC.D percentage
    btc_dominance_trend: str = "unknown"  # rising, falling, stable
    market_phase: str = "unknown"  # bull_run, bear_market, accumulation, distribution
    altcoin_season: bool = False  # True if altcoins outperforming BTC
    btc_eth_ratio: Optional[float] = None  # BTC/ETH price ratio
    btc_eth_trend: str = "unknown"  # btc_leading, eth_leading, neutral
    eth_outperforming_btc: bool = False  # True if ETH/BTC trend is rising
    rotation_phase: str = "unknown"  # btc, eth, large_alts, small_alts, memecoins
    halving_phase: str = "unknown"  # pre_halving, post_halving, expansion, distribution
    halving_phase_description: str = ""  # Human-readable phase description
    halving_sentiment: str = "neutral"  # very_bullish, bullish, bearish, neutral
    btc_rsi_14: Optional[float] = None  # RSI 14 on BTC weekly (approx 2-week chart)
    ema8_weekly_broken: bool = False  # True if BTC weekly close < EMA 8
    bmsb_status: Optional[str] = None  # "bullish", "bearish", or None
    pi_cycle_status: Optional[str] = None  # "near_top", "near_bottom", or None
    last_updated: Optional[str] = None


class CryptoCycleAnalyzer:
    """Analyzes crypto market cycles using BTC dominance and correlation data."""

    # BTC halving dates (approximate)
    HALVING_DATES = [
        datetime(2012, 11, 28, tzinfo=timezone.utc),
        datetime(2016, 7, 9, tzinfo=timezone.utc),
        datetime(2020, 5, 11, tzinfo=timezone.utc),
        datetime(2024, 4, 19, tzinfo=timezone.utc),  # Most recent
        datetime(2028, 4, 1, tzinfo=timezone.utc),    # Estimated next
    ]

    def __init__(self, broker=None):
        self.broker = broker
        self._cache: Optional[CryptoMarketCycle] = None
        self._cache_time: Optional[datetime] = None
        self._http = httpx.AsyncClient(timeout=10.0)

    async def get_cycle_status(
        self,
        bmsb: Optional[Dict] = None,
        pi_cycle: Optional[Dict] = None,
    ) -> CryptoMarketCycle:
        """Get current crypto market cycle status. Cached for 1 hour.

        Args:
            bmsb: BMSB dict from AnalysisResult (keys: bullish, bearish).
            pi_cycle: Pi Cycle dict from AnalysisResult (keys: near_top, near_bottom).
        """
        now = datetime.now(timezone.utc)
        if self._cache and self._cache_time and (now - self._cache_time).total_seconds() < 3600:
            return self._cache

        cycle = CryptoMarketCycle()

        # BTC Dominance via broker price data (BTC market cap / total crypto market cap)
        # We approximate using BTC vs major alts price action
        await self._analyze_dominance(cycle)
        await self._analyze_btc_eth(cycle)
        self._analyze_halving_phase(cycle)
        await self._analyze_rsi(cycle)
        await self._check_ema8_weekly(cycle)

        # Incorporate BMSB and Pi Cycle from market_analyzer AnalysisResult
        self._apply_bmsb(cycle, bmsb)
        self._apply_pi_cycle(cycle, pi_cycle)

        self._determine_market_phase(cycle)

        cycle.last_updated = now.isoformat()
        self._cache = cycle
        self._cache_time = now
        return cycle

    async def _analyze_dominance(self, cycle: CryptoMarketCycle):
        """Estimate BTC dominance (BTC.D) and trend from relative price performance.

        BTC Dominance thresholds (from TradingLab mentorship):
          - BTC.D > 50%: money primarily in Bitcoin, stability, low altcoin speculation
          - BTC.D < 40%: increased altcoin interest, more speculation, potential altseason
          - BTC.D 40-50%: neutral / transitional zone

        Altcoin season definition: begins when >75 of the top 100 coins
        outperform Bitcoin over the trailing period.  We approximate this
        with relative BTC-vs-alts performance since we don't have a full
        top-100 scanner here.

        DATA SOURCE LIMITATION: btc_dominance (BTC.D percentage) is not
        directly available from most broker APIs. To populate it, you need
        either:
          1. A crypto data API (CoinGecko, CoinMarketCap) that provides
             total crypto market cap and BTC market cap.
          2. A TradingView-style feed that supplies the BTC.D index.
        As a fallback, we approximate dominance direction from relative
        BTC vs ETH/alt performance (rising BTC outperformance = rising
        dominance). The btc_dominance float remains None when no direct
        data source is configured; downstream logic uses the trend instead.
        """
        if not self.broker:
            return
        try:
            # Get BTC and a basket of alts performance
            btc_candles = await self.broker.get_candles("BTC_USD", granularity="D", count=30)
            eth_candles = await self.broker.get_candles("ETH_USD", granularity="D", count=30)

            if btc_candles and eth_candles and len(btc_candles) >= 20 and len(eth_candles) >= 20:
                btc_perf_7d = (btc_candles[-1].close - btc_candles[-7].close) / btc_candles[-7].close
                eth_perf_7d = (eth_candles[-1].close - eth_candles[-7].close) / eth_candles[-7].close

                # Store on cycle object so get_dominance_transition() can access them
                cycle._btc_perf_7d = btc_perf_7d
                cycle._eth_perf_7d = eth_perf_7d

                # Determine BTC dominance trend from relative performance.
                # If alts outperform BTC significantly, dominance is falling.
                if eth_perf_7d > btc_perf_7d + 0.03:  # ETH outperforms by 3%+
                    cycle.btc_dominance_trend = "falling"
                elif btc_perf_7d > eth_perf_7d + 0.03:
                    cycle.btc_dominance_trend = "rising"
                else:
                    cycle.btc_dominance_trend = "stable"

                # If an actual BTC.D percentage is available, use mentorship thresholds.
                if cycle.btc_dominance is not None:
                    if cycle.btc_dominance > 50:
                        # BTC.D > 50%: money in Bitcoin, low altcoin speculation
                        cycle.btc_eth_trend = "btc_leading"
                        cycle.altcoin_season = False
                    elif cycle.btc_dominance < 40:
                        # BTC.D < 40%: altcoin interest rising, potential altseason
                        cycle.btc_eth_trend = "eth_leading"
                        cycle.altcoin_season = True
                    else:
                        # BTC.D 40-50%: neutral / transitional zone
                        cycle.btc_eth_trend = "neutral"
                        cycle.altcoin_season = False
                else:
                    # Fallback: infer altcoin season from relative performance
                    # (approximates the >75/100 coins outperforming BTC rule)
                    cycle.altcoin_season = (cycle.btc_dominance_trend == "falling")

        except Exception as e:
            logger.debug(f"Dominance analysis failed: {e}")

    async def _analyze_btc_eth(self, cycle: CryptoMarketCycle):
        """Analyze BTC/ETH ratio and capital rotation flow.

        Capital rotation model (TradingLab Crypto Specialization):
        Money flows in a predictable order during bull markets:
          BTC -> ETH -> Large cap alts -> Small cap alts -> Memecoins

        We track:
        - BTC/ETH ratio: if falling, ETH is outperforming BTC (rotation started)
        - rotation_phase: which stage of the rotation the market is in
        - eth_outperforming_btc: directional indicator for ETH/BTC trend
        """
        if not self.broker:
            return
        try:
            btc_price = await self.broker.get_current_price("BTC_USD")
            eth_price = await self.broker.get_current_price("ETH_USD")
            if btc_price and eth_price and eth_price.bid > 0:
                cycle.btc_eth_ratio = btc_price.bid / eth_price.bid

            # Determine ETH/BTC trend from recent candle data
            btc_candles = await self.broker.get_candles("BTC_USD", granularity="D", count=14)
            eth_candles = await self.broker.get_candles("ETH_USD", granularity="D", count=14)

            if (btc_candles and eth_candles
                    and len(btc_candles) >= 7 and len(eth_candles) >= 7):
                btc_perf = (btc_candles[-1].close - btc_candles[-7].close) / btc_candles[-7].close
                eth_perf = (eth_candles[-1].close - eth_candles[-7].close) / eth_candles[-7].close

                cycle.eth_outperforming_btc = eth_perf > btc_perf

                # Determine capital rotation phase based on dominance trend
                # and relative performance
                if cycle.btc_dominance_trend == "rising":
                    cycle.rotation_phase = "btc"  # Money flowing into BTC
                elif cycle.eth_outperforming_btc and cycle.btc_dominance_trend == "falling":
                    # ETH outperforming + falling dominance = rotation to ETH/alts
                    if cycle.altcoin_season:
                        cycle.rotation_phase = "large_alts"  # Broad alt rotation
                    else:
                        cycle.rotation_phase = "eth"  # Early rotation to ETH
                elif cycle.altcoin_season:
                    cycle.rotation_phase = "small_alts"  # Late-cycle alt speculation
                else:
                    cycle.rotation_phase = "btc"  # Default: money in BTC

        except Exception as e:
            logger.debug(f"BTC/ETH analysis failed: {e}")

    def get_dominance_transition(self, cycle: CryptoMarketCycle) -> Dict[str, str]:
        """Determine altcoin outlook from BTC dominance trend + BTC price trend.

        Dominance Transition Table (TradingLab mentorship):
          BTC.D up   + BTC up     = Altcoins down
          BTC.D up   + BTC down   = Altcoins down MUCH MORE
          BTC.D down + BTC up     = Altcoins up significantly (altseason)
          BTC.D down + BTC stable = Capital rotating to altcoins
          BTC.D down + BTC down   = Rare, altcoins may still fall

        Returns a dict with keys: dominance_trend, btc_trend, altcoin_outlook.
        """
        dom = cycle.btc_dominance_trend  # rising, falling, stable
        # Determine BTC price trend from recent candles (7d performance)
        btc_trend = "stable"
        if hasattr(cycle, "_btc_perf_7d"):
            perf = cycle._btc_perf_7d
            if perf > 0.02:
                btc_trend = "up"
            elif perf < -0.02:
                btc_trend = "down"

        altcoin_outlook = "neutral"
        if dom == "rising" and btc_trend == "up":
            altcoin_outlook = "down"
        elif dom == "rising" and btc_trend == "down":
            altcoin_outlook = "down_much_more"
        elif dom == "falling" and btc_trend == "up":
            altcoin_outlook = "up_significantly"  # Altseason
        elif dom == "falling" and btc_trend == "stable":
            altcoin_outlook = "capital_rotating_to_alts"
        elif dom == "falling" and btc_trend == "down":
            altcoin_outlook = "rare_alts_may_fall"
        elif dom == "rising" and btc_trend == "stable":
            altcoin_outlook = "down"
        # stable dominance cases
        elif dom == "stable":
            altcoin_outlook = "neutral"

        return {
            "dominance_trend": dom,
            "btc_trend": btc_trend,
            "altcoin_outlook": altcoin_outlook,
        }

    def _analyze_halving_phase(self, cycle: CryptoMarketCycle):
        """Determine position in the BTC halving cycle."""
        now = datetime.now(timezone.utc)
        last_halving = None
        next_halving = None
        for h in self.HALVING_DATES:
            if h <= now:
                last_halving = h
            else:
                next_halving = h
                break

        if last_halving and next_halving:
            cycle_length = (next_halving - last_halving).days
            days_since = (now - last_halving).days
            progress = days_since / cycle_length

            if progress < 0.25:
                cycle.halving_phase = "post_halving"
                cycle.halving_phase_description = "Explosion phase - most bullish"
                cycle.halving_sentiment = "very_bullish"
            elif progress < 0.50:
                cycle.halving_phase = "expansion"
                cycle.halving_phase_description = "Continued bull run"
                cycle.halving_sentiment = "bullish"
            elif progress < 0.75:
                cycle.halving_phase = "distribution"
                cycle.halving_phase_description = "Market top area"
                cycle.halving_sentiment = "bearish"
            else:
                # Pre-halving: accumulation phase where price starts rising
                # (historically, BTC bottoms well before the halving and
                # begins a new uptrend in anticipation of the supply cut)
                cycle.halving_phase = "pre_halving"
                cycle.halving_phase_description = "Accumulation, price starts rising"
                cycle.halving_sentiment = "bullish"

    async def _analyze_rsi(self, cycle: CryptoMarketCycle):
        """RSI 14 on BTC weekly for cycle top/bottom detection.

        From the mentorship (Alex): "lo que me gusta mas es para 14 semanas,
        perdon 14 semanas no, dos semanas o 14 dias". We use weekly candles
        with RSI period 14 to approximate the 2-week chart timeframe, which
        gives a cleaner cycle signal than daily RSI.

        Diagonal analysis note: RSI on this timeframe can also be used to
        draw diagonal trendlines on the RSI itself. A break of a rising RSI
        diagonal while price is at highs can signal cycle exhaustion before
        RSI reaches the extreme 80+ level.
        """
        if not self.broker:
            return
        try:
            # Use weekly candles (approximates 2-week chart for cycle analysis)
            candles = await self.broker.get_candles("BTC_USD", granularity="W", count=30)
            if not candles or len(candles) < 15:
                return
            closes = [c.close for c in candles]
            # Calculate RSI 14 on weekly closes
            gains, losses = [], []
            for i in range(1, len(closes)):
                diff = closes[i] - closes[i - 1]
                gains.append(max(diff, 0))
                losses.append(max(-diff, 0))
            if len(gains) < 14:
                return
            avg_gain = sum(gains[:14]) / 14
            avg_loss = sum(losses[:14]) / 14
            for i in range(14, len(gains)):
                avg_gain = (avg_gain * 13 + gains[i]) / 14
                avg_loss = (avg_loss * 13 + losses[i]) / 14
            if avg_loss == 0:
                rsi = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
            cycle.btc_rsi_14 = rsi
            # NOTE: Standard RSI thresholds are 70 (overbought) and 30 (oversold).
            # For BTC cycle analysis on weekly/2-week charts we use more extreme
            # levels (>80 / <25) because crypto markets on higher-timeframe charts
            # routinely sustain RSI above 70 during bull runs and below 30 during
            # prolonged bear markets. The extreme thresholds filter out noise and
            # only flag true cycle distribution tops and accumulation bottoms.
            if rsi > 80:
                cycle.market_phase = "distribution"  # Potential cycle top
            elif rsi < 25:
                cycle.market_phase = "accumulation"  # Potential cycle bottom
        except Exception as e:
            logger.debug(f"RSI analysis failed: {e}")

    async def _check_ema8_weekly(self, cycle: CryptoMarketCycle):
        """Check if BTC weekly close broke below EMA 8 (bearish signal)."""
        if not self.broker:
            return
        try:
            candles = await self.broker.get_candles("BTC_USD", granularity="W", count=10)
            if not candles or len(candles) < 9:
                return
            closes = [c.close for c in candles]
            # EMA 8
            ema = closes[0]
            multiplier = 2 / (8 + 1)
            for p in closes[1:]:
                ema = (p - ema) * multiplier + ema
            last_close = closes[-1]
            cycle.ema8_weekly_broken = last_close < ema
        except Exception as e:
            logger.debug(f"EMA 8 weekly check failed: {e}")

    def _apply_bmsb(self, cycle: CryptoMarketCycle, bmsb: Optional[Dict]):
        """Apply Bull Market Support Band status to cycle.

        BMSB (TradingLab Crypto Module 8): SMA 20 + EMA 21 on Weekly.
        Price above both = bullish (bull market intact).
        Price below both = bearish (bull market support lost).
        """
        if not bmsb:
            return
        if bmsb.get("bullish"):
            cycle.bmsb_status = "bullish"
        elif bmsb.get("bearish"):
            cycle.bmsb_status = "bearish"

    def _apply_pi_cycle(self, cycle: CryptoMarketCycle, pi_cycle: Optional[Dict]):
        """Apply Pi Cycle Top/Bottom indicator to cycle.

        Pi Cycle (TradingLab Crypto Module 8):
        - near_top: SMA 111 approaching 2x SMA 350 cross (cycle top).
        - near_bottom: SMA 150 approaching SMA 471 cross (cycle bottom).
        """
        if not pi_cycle:
            return
        if pi_cycle.get("near_top"):
            cycle.pi_cycle_status = "near_top"
        elif pi_cycle.get("near_bottom"):
            cycle.pi_cycle_status = "near_bottom"

    def _determine_market_phase(self, cycle: CryptoMarketCycle):
        """Determine overall market phase from combined signals."""
        signals = []
        if cycle.btc_dominance_trend == "falling":
            signals.append("bull")  # Falling dominance = risk-on = bullish
        elif cycle.btc_dominance_trend == "rising":
            signals.append("bear")  # Rising dominance = risk-off = bearish

        if cycle.halving_phase in ("post_halving", "expansion"):
            signals.append("bull")
        elif cycle.halving_phase == "distribution":
            signals.append("bear")
        # pre_halving is neutral to slightly bullish (accumulation, price starts
        # rising before halving) — do NOT count it as bearish

        if cycle.altcoin_season:
            signals.append("bull")

        # BMSB: Bull Market Support Band (SMA 20 + EMA 21 weekly)
        if cycle.bmsb_status == "bullish":
            signals.append("bull")
        elif cycle.bmsb_status == "bearish":
            signals.append("bear")

        # Pi Cycle Top/Bottom indicator
        if cycle.pi_cycle_status == "near_top":
            signals.append("bear")  # Distribution / cycle top
        elif cycle.pi_cycle_status == "near_bottom":
            signals.append("bull")  # Accumulation / cycle bottom

        bull_count = signals.count("bull")
        bear_count = signals.count("bear")

        if bull_count >= 2:
            cycle.market_phase = "bull_run"
        elif bear_count >= 2:
            cycle.market_phase = "bear_market"
        elif bull_count == 1 and bear_count == 0:
            cycle.market_phase = "accumulation"
        else:
            cycle.market_phase = "distribution"

    async def should_trade_crypto(
        self,
        bmsb: Optional[Dict] = None,
        pi_cycle: Optional[Dict] = None,
    ) -> tuple:
        """Should we be actively trading crypto right now?
        Returns (bool, reason).

        Args:
            bmsb: BMSB dict from AnalysisResult (keys: bullish, bearish).
            pi_cycle: Pi Cycle dict from AnalysisResult (keys: near_top, near_bottom).
        """
        cycle = await self.get_cycle_status(bmsb=bmsb, pi_cycle=pi_cycle)
        if cycle.market_phase == "bear_market":
            return False, f"Bear market detected (dominance={cycle.btc_dominance_trend}, halving={cycle.halving_phase})"
        reason = f"Market phase: {cycle.market_phase}"
        if cycle.ema8_weekly_broken:
            reason += " | WARNING: BTC weekly close below EMA 8 (bearish signal)"
        if cycle.bmsb_status == "bearish":
            reason += " | WARNING: BMSB bearish (price below SMA20+EMA21 weekly)"
        if cycle.pi_cycle_status == "near_top":
            reason += " | WARNING: Pi Cycle near top (distribution risk)"
        return True, reason

    async def close(self):
        await self._http.aclose()
