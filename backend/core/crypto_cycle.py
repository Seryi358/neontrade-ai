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
    halving_phase: str = "unknown"  # pre_halving, post_halving, mid_cycle
    btc_rsi_14: Optional[float] = None  # RSI 14 on BTC daily
    ema8_weekly_broken: bool = False  # True if BTC weekly close < EMA 8
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

    async def get_cycle_status(self) -> CryptoMarketCycle:
        """Get current crypto market cycle status. Cached for 1 hour."""
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
        self._determine_market_phase(cycle)

        cycle.last_updated = now.isoformat()
        self._cache = cycle
        self._cache_time = now
        return cycle

    async def _analyze_dominance(self, cycle: CryptoMarketCycle):
        """Estimate BTC dominance trend from relative price performance."""
        if not self.broker:
            return
        try:
            # Get BTC and a basket of alts performance
            btc_candles = await self.broker.get_candles("BTC_USD", granularity="D", count=30)
            eth_candles = await self.broker.get_candles("ETH_USD", granularity="D", count=30)

            if btc_candles and eth_candles and len(btc_candles) >= 20 and len(eth_candles) >= 20:
                btc_perf_7d = (btc_candles[-1].close - btc_candles[-7].close) / btc_candles[-7].close
                eth_perf_7d = (eth_candles[-1].close - eth_candles[-7].close) / eth_candles[-7].close
                btc_perf_30d = (btc_candles[-1].close - btc_candles[0].close) / btc_candles[0].close
                eth_perf_30d = (eth_candles[-1].close - eth_candles[0].close) / eth_candles[0].close

                # If alts outperform BTC significantly, dominance is falling (altseason)
                if eth_perf_7d > btc_perf_7d + 0.03:  # ETH outperforms by 3%+
                    cycle.btc_dominance_trend = "falling"
                    cycle.altcoin_season = True
                elif btc_perf_7d > eth_perf_7d + 0.03:
                    cycle.btc_dominance_trend = "rising"
                    cycle.altcoin_season = False
                else:
                    cycle.btc_dominance_trend = "stable"
                    cycle.altcoin_season = False
        except Exception as e:
            logger.debug(f"Dominance analysis failed: {e}")

    async def _analyze_btc_eth(self, cycle: CryptoMarketCycle):
        """Analyze BTC/ETH ratio for capital rotation."""
        if not self.broker:
            return
        try:
            btc_price = await self.broker.get_current_price("BTC_USD")
            eth_price = await self.broker.get_current_price("ETH_USD")
            if btc_price and eth_price and eth_price.bid > 0:
                cycle.btc_eth_ratio = btc_price.bid / eth_price.bid
                # Compare with historical average (~15-20)
                if cycle.btc_eth_ratio > 20:
                    cycle.btc_eth_trend = "btc_leading"
                elif cycle.btc_eth_ratio < 12:
                    cycle.btc_eth_trend = "eth_leading"
                else:
                    cycle.btc_eth_trend = "neutral"
        except Exception as e:
            logger.debug(f"BTC/ETH analysis failed: {e}")

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
                cycle.halving_phase = "post_halving"  # 0-25%: post-halving accumulation
            elif progress < 0.50:
                cycle.halving_phase = "expansion"  # 25-50%: bull run typically
            elif progress < 0.75:
                cycle.halving_phase = "distribution"  # 50-75%: market top area
            else:
                cycle.halving_phase = "pre_halving"  # 75-100%: pre-halving, often bear/accumulation

    async def _analyze_rsi(self, cycle: CryptoMarketCycle):
        """RSI 14 on BTC daily for cycle top/bottom detection."""
        if not self.broker:
            return
        try:
            candles = await self.broker.get_candles("BTC_USD", granularity="D", count=30)
            if not candles or len(candles) < 15:
                return
            closes = [c.close for c in candles]
            # Calculate RSI 14
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
            if rsi > 80:
                cycle.market_phase = "distribution"  # Potential top
            elif rsi < 25:
                cycle.market_phase = "accumulation"  # Potential bottom
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

    def _determine_market_phase(self, cycle: CryptoMarketCycle):
        """Determine overall market phase from combined signals."""
        signals = []
        if cycle.btc_dominance_trend == "falling":
            signals.append("bull")  # Falling dominance = risk-on = bullish
        elif cycle.btc_dominance_trend == "rising":
            signals.append("bear")  # Rising dominance = risk-off = bearish

        if cycle.halving_phase in ("post_halving", "expansion"):
            signals.append("bull")
        elif cycle.halving_phase in ("distribution", "pre_halving"):
            signals.append("bear")

        if cycle.altcoin_season:
            signals.append("bull")

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

    async def should_trade_crypto(self) -> tuple:
        """Should we be actively trading crypto right now?
        Returns (bool, reason)."""
        cycle = await self.get_cycle_status()
        if cycle.market_phase == "bear_market":
            return False, f"Bear market detected (dominance={cycle.btc_dominance_trend}, halving={cycle.halving_phase})"
        reason = f"Market phase: {cycle.market_phase}"
        if cycle.ema8_weekly_broken:
            reason += " | WARNING: BTC weekly close below EMA 8 (bearish signal)"
        return True, reason

    async def close(self):
        await self._http.aclose()
