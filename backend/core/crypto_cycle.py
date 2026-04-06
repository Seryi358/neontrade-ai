"""
NeonTrade AI - Crypto Market Cycle Analyzer
Tracks BTC dominance, altcoin season, and market cycle phases.
Concepts from TradingLab Crypto Specialization Module 6.
"""

import httpx
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional, Dict, List
from loguru import logger


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
    btc_rsi_14_daily: Optional[float] = None  # RSI 14 on BTC daily (secondary — short-term momentum)
    btc_rsi_14: Optional[float] = None  # RSI 14 on BTC weekly (primary — mentorship: "dos semanas o 14 días" for cycle analysis)
    ema8_weekly_broken: bool = False  # True if BTC weekly close < EMA 8
    bmsb_status: Optional[str] = None  # "bullish", "bearish", or None
    bmsb_consecutive_bearish_closes: int = 0  # Weekly closes below BMSB (need 2+ for confirmed bearish)
    pi_cycle_status: Optional[str] = None  # "near_top", "near_bottom", or None
    sma_d200_position: Optional[str] = None  # "above" = bullish, "below" = bearish (price vs SMA 200 Daily)
    dominance_transition: Optional[Dict[str, str]] = None  # From get_dominance_transition()
    crypto_trailing_ema50: Optional[float] = None  # EMA 50 value for trailing stop
    using_fixed_tp_warning: bool = False  # True if fixed TPs detected instead of EMA trailing
    # USDT.D tracking — critical for distinguishing true altseason from risk-off.
    # Mentorship: "If USDT.D is rising while BTC.D falls, money going to stablecoins (NOT altcoins)"
    usdt_dominance_rising: Optional[bool] = None  # True = risk-off, False = capital flowing to alts
    # Golden Cross / Death Cross (Esp. Criptomonedas Section 8 - SMA 200 Daily)
    golden_cross: bool = False  # SMA 50 crossed above SMA 200 (strong bullish signal)
    death_cross: bool = False   # SMA 50 crossed below SMA 200 (strong bearish signal)
    # RSI Diagonal Trendline Analysis (Esp. Criptomonedas Section 8)
    # Alex: drawing diagonals on RSI peaks/troughs is MORE reliable than fixed levels
    rsi_diagonal_bearish: bool = False  # RSI peaks forming descending trendline (distribution)
    rsi_diagonal_bullish: bool = False  # RSI troughs forming ascending trendline (accumulation)
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
        self._cache_bmsb: Optional[Dict] = None
        self._cache_pi_cycle: Optional[Dict] = None
        self._http = httpx.AsyncClient(timeout=10.0)
        # Track consecutive weekly closes below BMSB for confirmation logic.
        # The mentorship emphasizes needing a weekly CLOSE below BMSB plus
        # confirmation (at least 2 consecutive weekly closes) before declaring
        # bearish. A single wick below doesn't count.
        self._bmsb_bearish_streak: int = 0

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
        if (self._cache and self._cache_time
                and (now - self._cache_time).total_seconds() < 3600
                and self._cache_bmsb == bmsb and self._cache_pi_cycle == pi_cycle):
            return self._cache

        cycle = CryptoMarketCycle()

        # BTC/ETH analysis FIRST — sets eth_outperforming_btc which
        # _analyze_dominance needs for altcoin season detection.
        await self._analyze_btc_eth(cycle)

        # BTC Dominance via broker price data (BTC market cap / total crypto market cap)
        # We approximate using BTC vs major alts price action.
        # Must run AFTER _analyze_btc_eth so eth_outperforming_btc is available.
        await self._analyze_dominance(cycle)

        # Estimate USDT.D direction from BTC+ETH combined performance
        # (uses _btc_perf_7d/_eth_perf_7d set by _analyze_dominance)
        self._estimate_usdt_dominance(cycle)

        # Re-apply USDT.D filter to altcoin_season now that estimation is done.
        # _analyze_dominance couldn't check this because USDT.D wasn't computed yet.
        if cycle.usdt_dominance_rising is True and cycle.altcoin_season:
            cycle.altcoin_season = False
            logger.info(
                "Altcoin season overridden: USDT.D rising — "
                "money flowing to stablecoins, not alts"
            )

        # Rotation phase needs BOTH eth_outperforming_btc (from _analyze_btc_eth)
        # AND btc_dominance_trend + altcoin_season (from _analyze_dominance).
        # Must run after both to avoid stale defaults.
        self._determine_rotation_phase(cycle)

        self._analyze_halving_phase(cycle)
        await self._analyze_rsi(cycle)
        await self._check_ema8_weekly(cycle)
        await self._check_sma200_daily(cycle)

        # Incorporate BMSB and Pi Cycle from market_analyzer AnalysisResult
        self._apply_bmsb(cycle, bmsb)
        self._apply_pi_cycle(cycle, pi_cycle)

        self._determine_market_phase(cycle)

        cycle.last_updated = now.isoformat()
        self._cache = cycle
        self._cache_time = now
        self._cache_bmsb = bmsb
        self._cache_pi_cycle = pi_cycle
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
                    # Fallback: infer altcoin season from relative performance.
                    # Falling dominance alone does NOT mean altseason -- money
                    # could be rotating to USDT (risk-off). Require BOTH falling
                    # dominance AND ETH outperforming BTC as confirmation that
                    # capital is flowing into alts, not stablecoins.
                    # Mentorship: "If USDT.D is rising while BTC.D falls, money
                    # going to stablecoins (NOT altcoins) - bearish signal."
                    # When usdt_dominance_rising is available (from external feed),
                    # use it to filter false altseason signals.
                    if cycle.usdt_dominance_rising is True:
                        # USDT.D rising = risk-off, NOT altseason
                        cycle.altcoin_season = False
                    else:
                        cycle.altcoin_season = (
                            cycle.btc_dominance_trend == "falling"
                            and cycle.eth_outperforming_btc
                        )

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

        except Exception as e:
            logger.debug(f"BTC/ETH analysis failed: {e}")

    def _determine_rotation_phase(self, cycle: CryptoMarketCycle):
        """Determine capital rotation phase from combined signals.

        Must run AFTER both _analyze_btc_eth (sets eth_outperforming_btc)
        and _analyze_dominance (sets btc_dominance_trend, altcoin_season).

        Capital rotation sequence (TradingLab Crypto Specialization):
          BTC -> ETH -> Large cap alts -> Small cap alts -> Memecoins
        """
        if cycle.btc_dominance_trend == "rising":
            cycle.rotation_phase = "btc"  # Money flowing into BTC
        elif cycle.eth_outperforming_btc and cycle.btc_dominance_trend == "falling":
            # ETH outperforming + falling dominance = rotation to ETH/alts
            if cycle.altcoin_season:
                cycle.rotation_phase = "large_alts"  # Broad alt rotation
            else:
                cycle.rotation_phase = "eth"  # Early rotation to ETH
        elif cycle.altcoin_season:
            # Late-cycle: distinguish small_alts vs memecoins.
            # When dominance is falling fast AND ETH is no longer leading
            # (ETH/BTC flat or falling while alts pump), we're in the
            # final memecoin speculation phase.
            if not cycle.eth_outperforming_btc and cycle.btc_dominance_trend == "falling":
                cycle.rotation_phase = "memecoins"  # Final euphoria phase
            else:
                cycle.rotation_phase = "small_alts"  # Late-cycle alt speculation
        elif cycle.btc_dominance_trend != "unknown":
            cycle.rotation_phase = "btc"  # Default when dominance data available
        # If btc_dominance_trend is still "unknown", leave rotation_phase as "unknown"

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
            # Mentorship: BTC.D rising + BTC stable = consolidation, not fleeing
            altcoin_outlook = "stable_to_slightly_down"
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

            # The year AFTER the halving is the "explosion" year (mentorship).
            # 2024 halving was April, so 2025 is the peak year. We extend the
            # post_halving/very_bullish phase to ~33% of the cycle to cover
            # most of that first year after halving.
            if progress < 0.33:
                cycle.halving_phase = "post_halving"
                cycle.halving_phase_description = "Explosion phase - most bullish (year after halving)"
                cycle.halving_sentiment = "very_bullish"
            elif progress < 0.55:
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
        """RSI 14 on BTC for cycle top/bottom detection.

        From the mentorship (Alex): "lo que me gusta más es para 14 semanas,
        poner, perdón 14 semanas no, dos semanas o 14 días". Alex explicitly
        specifies the 2-WEEK (14-day) chart timeframe for cycle analysis.
        Weekly RSI 14 is the best available proxy (most brokers don't offer 2W
        candles). Daily RSI 14 is kept as a secondary short-term supplement.

        Diagonal analysis note: RSI on the weekly timeframe can also be used to
        draw diagonal trendlines on the RSI itself. A break of a rising RSI
        diagonal while price is at highs can signal cycle exhaustion before
        RSI reaches the extreme 80+ level.
        """
        if not self.broker:
            return
        try:
            # PRIMARY: Weekly RSI 14 (mentorship: "dos semanas o 14 días" — cycle-level)
            # Weekly approximates 2W; most brokers don't provide 2W candles directly.
            candles = await self.broker.get_candles("BTC_USD", granularity="W", count=30)
            if candles and len(candles) >= 15:
                closes = [c.close for c in candles]
                weekly_rsi = self._compute_rsi_14(closes)
                if weekly_rsi is not None:
                    cycle.btc_rsi_14 = weekly_rsi
                    logger.info(f"BTC Weekly RSI 14 (primary — cycle): {weekly_rsi:.1f}")

            # SECONDARY: Daily RSI 14 (short-term momentum supplement)
            daily_candles = await self.broker.get_candles("BTC_USD", granularity="D", count=30)
            if daily_candles and len(daily_candles) >= 15:
                daily_closes = [c.close for c in daily_candles]
                daily_rsi = self._compute_rsi_14(daily_closes)
                if daily_rsi is not None:
                    cycle.btc_rsi_14_daily = daily_rsi

            if not candles or len(candles) < 15:
                return
            closes = [c.close for c in candles]

            # Use weekly RSI as primary for market phase decisions, fall back to daily
            rsi = cycle.btc_rsi_14 if cycle.btc_rsi_14 is not None else cycle.btc_rsi_14_daily

            # RSI Diagonal Trendline Analysis (Esp. Criptomonedas Section 8)
            # Alex: "ha sido capaz de enlazar de forma muy clara diferentes
            # estructuras de máximos" — drawing descending diagonals on RSI peaks
            # across multiple cycles is MORE useful than fixed overbought/oversold.
            # Detect: if RSI peaks are forming a descending trendline (each peak
            # lower than the last), this signals distribution even if RSI < 80.
            rsi_series = self._calculate_rsi_series(closes)
            if len(rsi_series) >= 10:
                # Find RSI peaks (local maxima in last 20 weekly candles)
                peaks = []
                for i in range(1, len(rsi_series) - 1):
                    if rsi_series[i] > rsi_series[i - 1] and rsi_series[i] > rsi_series[i + 1]:
                        peaks.append((i, rsi_series[i]))

                if len(peaks) >= 3:
                    # Check if RSI peaks form a descending trendline
                    recent_peaks = peaks[-4:]  # Last 4 peaks
                    peak_values = [p[1] for p in recent_peaks]
                    descending = all(
                        peak_values[i] > peak_values[i + 1]
                        for i in range(len(peak_values) - 1)
                    )
                    if descending and peak_values[-1] < peak_values[0] * 0.9:
                        cycle.rsi_diagonal_bearish = True
                        logger.info(
                            f"RSI DIAGONAL BEARISH: peaks declining "
                            f"{[f'{p:.1f}' for p in peak_values]} — "
                            f"distribution signal (Alex: 'enlazar máximos decrecientes')"
                        )
                    else:
                        cycle.rsi_diagonal_bearish = False

                    # Also check ascending trendline on RSI troughs (accumulation)
                    troughs = []
                    for i in range(1, len(rsi_series) - 1):
                        if rsi_series[i] < rsi_series[i - 1] and rsi_series[i] < rsi_series[i + 1]:
                            troughs.append((i, rsi_series[i]))
                    if len(troughs) >= 3:
                        recent_troughs = troughs[-4:]
                        trough_values = [t[1] for t in recent_troughs]
                        ascending = all(
                            trough_values[i] < trough_values[i + 1]
                            for i in range(len(trough_values) - 1)
                        )
                        if ascending and trough_values[-1] > trough_values[0] * 1.1:
                            cycle.rsi_diagonal_bullish = True
                            logger.info(
                                f"RSI DIAGONAL BULLISH: troughs rising "
                                f"{[f'{t:.1f}' for t in trough_values]} — "
                                f"accumulation signal"
                            )
                        else:
                            cycle.rsi_diagonal_bullish = False

            # NOTE: RSI extreme levels are factored into _determine_market_phase()
            # via the voting system (btc_rsi_14 field). No need to set market_phase
            # here — it would be overwritten by _determine_market_phase() anyway.
        except Exception as e:
            logger.debug(f"RSI analysis failed: {e}")

    def _estimate_usdt_dominance(self, cycle: CryptoMarketCycle):
        """Estimate USDT dominance direction from BTC+ETH combined performance.

        From mentorship: "If USDT.D is rising while BTC.D falls, money going to
        stablecoins (NOT altcoins) — bearish signal."

        Without direct USDT.D data, we approximate:
        - If BTC AND ETH both falling → capital likely flowing to stablecoins → USDT.D rising
        - If BTC AND ETH both rising → capital leaving stablecoins → USDT.D falling
        - Mixed → inconclusive, leave as None
        """
        btc_perf = getattr(cycle, '_btc_perf_7d', None)
        eth_perf = getattr(cycle, '_eth_perf_7d', None)
        if btc_perf is None or eth_perf is None:
            return

        # Both assets declining significantly → money going to stablecoins
        if btc_perf < -0.02 and eth_perf < -0.02:
            cycle.usdt_dominance_rising = True
            logger.info(
                f"USDT.D estimated RISING: BTC {btc_perf:+.2%}, ETH {eth_perf:+.2%} "
                f"— both declining, capital likely flowing to stablecoins"
            )
        # Both assets rising significantly → money leaving stablecoins
        elif btc_perf > 0.02 and eth_perf > 0.02:
            cycle.usdt_dominance_rising = False
            logger.info(
                f"USDT.D estimated FALLING: BTC {btc_perf:+.2%}, ETH {eth_perf:+.2%} "
                f"— both rising, capital leaving stablecoins"
            )
        # Mixed or flat → inconclusive
        else:
            cycle.usdt_dominance_rising = None

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

    async def _check_sma200_daily(self, cycle: CryptoMarketCycle):
        """Check BTC price position relative to SMA 200 Daily.

        From TradingLab mentorship: "above SMA 200 daily = bullish, below = bearish."
        This is a fundamental macro indicator for determining overall market bias.
        SMA 200 on the daily chart is the most widely watched moving average in
        all of finance — institutional traders, funds, and algorithms all use it
        as the dividing line between bull and bear markets.
        """
        if not self.broker:
            return
        try:
            candles = await self.broker.get_candles("BTC_USD", granularity="D", count=210)
            if not candles or len(candles) < 200:
                return
            closes = [c.close for c in candles]
            # Calculate SMA 200 from daily close prices
            sma_200 = sum(closes[-200:]) / 200
            current_price = closes[-1]
            if current_price > sma_200:
                cycle.sma_d200_position = "above"
            else:
                cycle.sma_d200_position = "below"
            # Golden Cross / Death Cross detection (Esp. Criptomonedas Section 8)
            # Golden Cross = SMA 50 crosses ABOVE SMA 200 (strong bullish)
            # Death Cross = SMA 50 crosses BELOW SMA 200 (strong bearish)
            if len(closes) >= 201:
                sma_50 = sum(closes[-50:]) / 50
                sma_50_prev = sum(closes[-51:-1]) / 50
                sma_200_prev = sum(closes[-201:-1]) / 200
                if sma_50 > sma_200 and sma_50_prev <= sma_200_prev:
                    cycle.golden_cross = True
                    cycle.death_cross = False
                    logger.info("GOLDEN CROSS detected: SMA 50 crossed above SMA 200 Daily")
                elif sma_50 < sma_200 and sma_50_prev >= sma_200_prev:
                    cycle.golden_cross = False
                    cycle.death_cross = True
                    logger.info("DEATH CROSS detected: SMA 50 crossed below SMA 200 Daily")
                else:
                    cycle.golden_cross = False
                    cycle.death_cross = False

            logger.debug(
                f"SMA 200 Daily: {sma_200:.2f} | BTC price: {current_price:.2f} "
                f"| Position: {cycle.sma_d200_position}"
            )
        except Exception as e:
            logger.debug(f"SMA 200 Daily check failed: {e}")

    def _apply_bmsb(self, cycle: CryptoMarketCycle, bmsb: Optional[Dict]):
        """Apply Bull Market Support Band status to cycle.

        BMSB (TradingLab Crypto Module 8): SMA 20 + EMA 21 on Weekly.
        Price above both = bullish (bull market intact).
        Price below both = bearish (bull market support lost).

        CONFIRMATION RULE (mentorship): Need a weekly CLOSE below BMSB plus
        at least one more weekly close below it (2 consecutive closes minimum)
        before declaring bearish. This filters out false breakdowns / wicks.
        """
        if not bmsb:
            return
        if bmsb.get("bullish"):
            self._bmsb_bearish_streak = 0  # Reset streak on bullish close
            cycle.bmsb_status = "bullish"
            cycle.bmsb_consecutive_bearish_closes = 0
        elif bmsb.get("bearish"):
            self._bmsb_bearish_streak += 1
            cycle.bmsb_consecutive_bearish_closes = self._bmsb_bearish_streak
            if self._bmsb_bearish_streak >= 2:
                # Confirmed bearish: 2+ consecutive weekly closes below BMSB
                cycle.bmsb_status = "bearish"
            else:
                # First weekly close below BMSB -- not yet confirmed.
                # Treat as warning, not full bearish signal.
                cycle.bmsb_status = "warning"
                logger.info(
                    "BMSB: first weekly close below support band -- "
                    "need 1 more weekly close for bearish confirmation"
                )

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
        """Determine overall market phase from combined signals.

        Signal weighting:
        - RSI 14 weekly, BMSB, SMA 200 Daily: 1.0 vote each (most reliable per mentorship)
        - Pi Cycle: 0.5 vote (less reliable than RSI 14 and BMSB per mentorship)
        - Dominance, halving, altseason, dominance transition: 1.0 vote each
        """
        bull_votes = 0.0
        bear_votes = 0.0

        if cycle.btc_dominance_trend == "falling":
            bull_votes += 1.0  # Falling dominance = risk-on = bullish
        elif cycle.btc_dominance_trend == "rising":
            bear_votes += 1.0  # Rising dominance = risk-off = bearish

        if cycle.halving_phase in ("post_halving", "expansion"):
            bull_votes += 1.0
        elif cycle.halving_phase == "distribution":
            bear_votes += 1.0
        # pre_halving is neutral to slightly bullish (accumulation, price starts
        # rising before halving) -- do NOT count it as bearish

        if cycle.altcoin_season:
            bull_votes += 1.0

        # BMSB: Bull Market Support Band (SMA 20 + EMA 21 weekly) -- full weight
        if cycle.bmsb_status == "bullish":
            bull_votes += 1.0
        elif cycle.bmsb_status == "bearish":
            bear_votes += 1.0

        # Pi Cycle Top/Bottom indicator -- LESS reliable than RSI 14 and BMSB
        # (mentorship emphasis), so count as 0.5 votes instead of full vote
        if cycle.pi_cycle_status == "near_top":
            bear_votes += 0.5  # Distribution / cycle top
        elif cycle.pi_cycle_status == "near_bottom":
            bull_votes += 0.5  # Accumulation / cycle bottom

        # SMA 200 Daily: fundamental macro filter (mentorship: above = bullish, below = bearish)
        if cycle.sma_d200_position == "above":
            bull_votes += 1.0
        elif cycle.sma_d200_position == "below":
            bear_votes += 1.0

        # RSI 14 weekly: primary cycle indicator (mentorship: "most reliable")
        # Extreme RSI values signal cycle tops/bottoms.
        if cycle.btc_rsi_14 is not None:
            if cycle.btc_rsi_14 > 80:
                bear_votes += 1.0  # Overbought — distribution / cycle top risk
            elif cycle.btc_rsi_14 < 30:
                bull_votes += 1.0  # Oversold — accumulation / cycle bottom opportunity

        # Integrate dominance transition analysis (BTC.D trend + BTC price trend)
        transition = self.get_dominance_transition(cycle)
        cycle.dominance_transition = transition
        alt_outlook = transition.get("altcoin_outlook", "neutral")
        if alt_outlook in ("up_significantly", "capital_rotating_to_alts"):
            bull_votes += 1.0  # Strong altcoin signal = bullish market
        elif alt_outlook in ("down_much_more",):
            bear_votes += 1.0  # Alts dumping hard = bearish

        if bull_votes >= 2.0:
            cycle.market_phase = "bull_run"
        elif bear_votes >= 2.0:
            cycle.market_phase = "bear_market"
        elif bull_votes >= 1.0 and bear_votes == 0:
            cycle.market_phase = "accumulation"
        else:
            cycle.market_phase = "distribution"

    @staticmethod
    def _compute_rsi_14(closes: list) -> Optional[float]:
        """Compute a single RSI 14 value from a list of close prices.

        Returns the most recent RSI 14, or None if insufficient data.
        Used for both daily (primary) and weekly (secondary) RSI calculations.
        """
        if len(closes) < 15:
            return None
        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))
        if len(gains) < 14:
            return None
        avg_gain = sum(gains[:14]) / 14
        avg_loss = sum(losses[:14]) / 14
        for i in range(14, len(gains)):
            avg_gain = (avg_gain * 13 + gains[i]) / 14
            avg_loss = (avg_loss * 13 + losses[i]) / 14
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _calculate_rsi_series(closes: list, period: int = 14) -> list:
        """Calculate RSI for each point in the series (for diagonal analysis)."""
        if len(closes) < period + 1:
            return []
        rsi_values = []
        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            if avg_loss == 0:
                rsi_values.append(100.0)
            else:
                rs = avg_gain / avg_loss
                rsi_values.append(100 - (100 / (1 + rs)))
        return rsi_values

    async def get_crypto_trailing_ema(
        self,
        symbol: str = "BTC_USD",
        style: str = "long_term",
    ) -> Optional[float]:
        """Return the EMA 50 value for crypto trailing stop management.

        The mentorship teaches FOUR crypto position management modes
        (Esp. Criptomonedas position management section):

        1. "long_term" (default): Weekly EMA 50 trailing — safest, keeps you
           in major bull runs. Close when weekly candle closes below EMA 50.
        2. "daily": Daily EMA 50 trailing — mid-term, between LP and CP.
           Mentorship: "dynamic support in bull, resistance in bear."
        3. "short_term": H1 EMA 50 trailing — faster exits, captures ~7-10% moves.
           Close when H1 candle closes below EMA 50.
        4. "aggressive": M15 EMA 50 trailing / reference TP + M15 validation.
           Set TP1 at key level, then trail with M15 EMA 50. When price reaches
           TP zone, drop to M15 to check if reversing.

        Args:
            symbol: Crypto instrument to calculate EMA for.
            style: Management style ("long_term", "short_term", "aggressive").

        Returns:
            The current EMA 50 value on the appropriate timeframe, or None.
        """
        if not self.broker:
            return None

        # Map style to timeframe (from mentorship — 4 modes)
        style_tf_map = {
            "long_term": "W",     # Weekly EMA 50 (safest, default)
            "daily": "D",         # Daily EMA 50 (mid-term — between LP and CP for crypto)
            "short_term": "H1",   # H1 EMA 50 (~7-10% moves)
            "aggressive": "M15",  # M15 EMA 50 / reference TP + M15 validation
        }
        granularity = style_tf_map.get(style, "W")
        count = 60 if granularity == "W" else 200

        try:
            candles = await self.broker.get_candles(symbol, granularity=granularity, count=count)
            if not candles or len(candles) < 50:
                return None
            closes = [c.close for c in candles]
            # Calculate EMA 50
            ema = closes[0]
            multiplier = 2 / (50 + 1)
            for p in closes[1:]:
                ema = (p - ema) * multiplier + ema
            return ema
        except Exception as e:
            logger.debug(f"EMA 50 trailing ({style}/{granularity}) calculation failed: {e}")
            return None

    async def should_trade_crypto(
        self,
        bmsb: Optional[Dict] = None,
        pi_cycle: Optional[Dict] = None,
        using_fixed_tp: bool = False,
    ) -> tuple:
        """Should we be actively trading crypto right now?
        Returns (bool, reason).

        Args:
            bmsb: BMSB dict from AnalysisResult (keys: bullish, bearish).
            pi_cycle: Pi Cycle dict from AnalysisResult (keys: near_top, near_bottom).
            using_fixed_tp: If True, indicates the caller is using fixed TP levels
                instead of EMA 50 trailing (triggers a warning).
        """
        cycle = await self.get_cycle_status(bmsb=bmsb, pi_cycle=pi_cycle)

        # Populate EMA 50 trailing stop value on the cycle object
        ema50 = await self.get_crypto_trailing_ema("BTC_USD")
        cycle.crypto_trailing_ema50 = ema50

        # Warn if fixed TPs are being used instead of EMA trailing
        if using_fixed_tp:
            cycle.using_fixed_tp_warning = True

        if cycle.market_phase == "bear_market":
            return False, f"Bear market detected (dominance={cycle.btc_dominance_trend}, halving={cycle.halving_phase})"
        reason = f"Market phase: {cycle.market_phase}"
        if cycle.ema8_weekly_broken:
            reason += " | WARNING: BTC weekly close below EMA 8 (bearish signal)"
        if cycle.bmsb_status == "bearish":
            reason += " | WARNING: BMSB bearish (price below SMA20+EMA21 weekly, confirmed with 2+ closes)"
        elif cycle.bmsb_status == "warning":
            reason += " | CAUTION: BMSB first close below support band (awaiting confirmation)"
        if cycle.pi_cycle_status == "near_top":
            reason += " | WARNING: Pi Cycle near top (distribution risk)"
        if using_fixed_tp:
            reason += (
                " | WARNING: Using fixed TPs instead of EMA 50 trailing stop. "
                "Mentorship recommends EMA 50 weekly as trailing stop for crypto "
                "positions -- fixed TPs leave money on the table in bull runs."
            )
        if cycle.usdt_dominance_rising is True:
            reason += " | WARNING: USDT.D rising — money flowing to stablecoins (risk-off, NOT altseason)"
        if cycle.sma_d200_position == "below":
            reason += " | WARNING: BTC below SMA 200 Daily (bearish macro bias)"
        elif cycle.sma_d200_position == "above":
            reason += " | BTC above SMA 200 Daily (bullish macro bias)"
        if ema50 is not None:
            reason += f" | EMA 50 weekly trailing stop: {ema50:.2f}"
        return True, reason

    async def close(self):
        await self._http.aclose()
