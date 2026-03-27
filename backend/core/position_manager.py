"""
NeonTrade AI - Position Manager
Manages open positions: SL movement, BE, trailing stops.

From TradingLab Mentorship - Position Management Styles (all based on EMA 50):

Style LP (Long-term):
  - Swing: trail with Weekly EMA 50
  - Day Trading: trail with H4 EMA 50
  - Scalping: trail with M15 EMA 50

Style CP (Short-term):
  - Swing: trail with H1 EMA 50
  - Day Trading: trail with M15 EMA 50
  - Scalping: trail with M1 EMA 50

Style CPA (Short-term Aggressive):
  - Swing: trail with M15 EMA 50
  - Day Trading: trail with M2 EMA 50
  - Scalping: trail with M1 EMA 50 (30s not available)
  - CPA is NOT standalone — only used combined with LP/CP at key levels

Hybrid approach (recommended):
  - Run LP or CP as base style
  - At key levels (previous highs, Fib extensions, major resistance), switch to CPA
  - Close partial position if CPA triggers exit, continue LP/CP with remaining

Key rule: "No se toman parciales de ganancia" — no partial profit taking.
Give space to the EMA — buffer slightly below/above, never place SL exactly on it.
"""

from typing import Dict, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger


class PositionPhase(Enum):
    """Phases of position management."""
    INITIAL = "initial"              # Just entered, SL at original
    SL_MOVED = "sl_moved"            # SL moved to previous high/low
    BREAK_EVEN = "break_even"        # SL at entry (BE)
    TRAILING_TO_TP1 = "trailing"     # Trailing with EMAs toward TP1
    BEYOND_TP1 = "aggressive"        # Past TP1, aggressive trailing


class ManagementStyle(Enum):
    """TradingLab position management styles — all trail with EMA 50."""
    LP = "lp"    # Long-term: wider EMA timeframes, gives trades more room
    CP = "cp"    # Short-term: tighter EMA timeframes, locks profit sooner
    CPA = "cpa"  # Short-term Aggressive: tightest EMAs, only at key levels


class TradingStyle(Enum):
    """Trading style determines which timeframe EMA 50 to use."""
    SCALPING = "scalping"
    DAY_TRADING = "day_trading"
    SWING = "swing"


# EMA 50 timeframe grid per management style and trading style
# Maps (ManagementStyle, TradingStyle) -> EMA key suffix for _latest_emas
# All values reference EMA 50 on the given timeframe
_EMA_TIMEFRAME_GRID: Dict[tuple, str] = {
    # LP (Long-term): widest timeframes
    (ManagementStyle.LP, TradingStyle.SWING): "EMA_W_50",
    (ManagementStyle.LP, TradingStyle.DAY_TRADING): "EMA_H4_50",
    (ManagementStyle.LP, TradingStyle.SCALPING): "EMA_M15_50",
    # CP (Short-term): medium timeframes
    (ManagementStyle.CP, TradingStyle.SWING): "EMA_H1_50",
    (ManagementStyle.CP, TradingStyle.DAY_TRADING): "EMA_M15_50",
    (ManagementStyle.CP, TradingStyle.SCALPING): "EMA_M5_50",  # M1 not available, using M5 as fallback
    # CPA (Short-term Aggressive): tightest timeframes
    (ManagementStyle.CPA, TradingStyle.SWING): "EMA_M15_50",
    (ManagementStyle.CPA, TradingStyle.DAY_TRADING): "EMA_M2_50",
    (ManagementStyle.CPA, TradingStyle.SCALPING): "EMA_M5_50",  # M1 not available, using M5 as fallback
}


@dataclass
class ManagedPosition:
    """Tracks state of a managed position."""
    trade_id: str
    instrument: str
    direction: str              # "BUY" or "SELL"
    entry_price: float
    original_sl: float
    current_sl: float
    take_profit_1: float
    take_profit_max: Optional[float] = None
    phase: PositionPhase = PositionPhase.INITIAL
    highest_price: float = 0.0    # For BUY: highest since entry
    lowest_price: float = float('inf')  # For SELL: lowest since entry


class PositionManager:
    """
    Manages all open positions according to TradingLab mentorship rules.

    5-phase structure:
      Phase 1 (INITIAL)    - Move SL to structure after initial move
      Phase 2 (SL_MOVED)   - Move to Break Even at 1% unrealized profit
      Phase 3 (BREAK_EVEN) - Transition to trailing at 70% to TP1
      Phase 4 (TRAILING)   - Trail SL with EMA 50 on style-appropriate timeframe
      Phase 5 (AGGRESSIVE) - Beyond TP1, switch to CPA EMA for tighter trailing

    Management style (LP/CP) determines which EMA 50 timeframe is used in
    phases 4 and 5. At key levels, CPA is used for tighter trailing.
    """

    # Crypto instrument prefixes for EMA 50 trailing logic
    _CRYPTO_PREFIXES = (
        "BTC", "ETH", "SOL", "ADA", "DOT", "LINK", "AVAX", "MATIC",
        "UNI", "ATOM", "XRP", "DOGE", "LTC", "BNB",
        "FTM", "ALGO", "XLM", "EOS", "XTZ", "VET",
    )

    def __init__(
        self,
        broker_client,
        risk_manager=None,
        management_style: str = "lp",
        trading_style: str = "day_trading",
    ):
        self.broker = broker_client
        self.risk_manager = risk_manager
        self.positions: Dict[str, ManagedPosition] = {}
        # EMA values from last market analysis (injected by trading engine)
        self._latest_emas: Dict[str, Dict[str, float]] = {}

        # Management style configuration
        self.management_style = ManagementStyle(management_style.lower())
        self.trading_style = TradingStyle(trading_style.lower())

        # Resolve EMA keys from the grid
        self._base_ema_key = _EMA_TIMEFRAME_GRID[
            (self.management_style, self.trading_style)
        ]
        # CPA key for aggressive phase (beyond TP1) or key-level trailing
        self._cpa_ema_key = _EMA_TIMEFRAME_GRID[
            (ManagementStyle.CPA, self.trading_style)
        ]

        logger.info(
            f"PositionManager initialized: style={self.management_style.value}, "
            f"trading={self.trading_style.value}, "
            f"base_ema={self._base_ema_key}, cpa_ema={self._cpa_ema_key}"
        )

    def _is_crypto(self, instrument: str) -> bool:
        """Check if an instrument is a crypto pair."""
        return any(instrument.upper().startswith(p) for p in self._CRYPTO_PREFIXES)

    def set_ema_values(self, instrument: str, emas: Dict[str, float]):
        """Update EMA values for an instrument (called by trading engine after analysis)."""
        self._latest_emas[instrument] = emas

    def _get_trail_ema(self, instrument: str, ema_key: str) -> Optional[float]:
        """
        Look up an EMA value for an instrument, with fallback chain.
        Returns None if no EMA data is available.
        """
        emas = self._latest_emas.get(instrument, {})
        value = emas.get(ema_key)
        if value is not None:
            return value

        # Fallback: try common EMA 50 keys in descending specificity
        for fallback_key in ("EMA_H4_50", "EMA_H1_50", "EMA_M15_50", "EMA_M5_50"):
            value = emas.get(fallback_key)
            if value is not None:
                logger.debug(
                    f"{instrument}: {ema_key} not available, falling back to {fallback_key}"
                )
                return value
        return None

    def _ema_buffer(self, pos: ManagedPosition, aggressive: bool = False) -> float:
        """
        Calculate buffer distance to give space to the EMA.
        The SL should NOT sit exactly on the EMA — give it room to breathe.
        Aggressive phase uses a smaller buffer.
        """
        trade_range = abs(pos.take_profit_1 - pos.entry_price)
        if aggressive:
            # CPA / beyond-TP1: tighter buffer but still not zero
            return trade_range * 0.01
        else:
            # Base trailing: wider buffer to let EMA breathe
            return trade_range * 0.02

    def track_position(self, position: ManagedPosition):
        """Start tracking a new position."""
        self.positions[position.trade_id] = position
        logger.info(
            f"Tracking position {position.trade_id}: "
            f"{position.direction} {position.instrument} "
            f"@ {position.entry_price} | SL={position.original_sl} "
            f"| TP1={position.take_profit_1}"
        )

    async def update_all_positions(self, current_prices: Dict):
        """
        Called on every tick/candle close to update position management.
        This is the main loop that implements the Trading Plan rules.
        """
        for trade_id, pos in list(self.positions.items()):
            if pos.instrument not in current_prices:
                continue

            price_data = current_prices[pos.instrument]
            current_price = (
                price_data.bid if pos.direction == "SELL"
                else price_data.ask
            )

            # Update extreme prices
            if pos.direction == "BUY":
                pos.highest_price = max(pos.highest_price, current_price)
            else:
                pos.lowest_price = min(pos.lowest_price, current_price)

            # Run phase-based management
            await self._manage_position(pos, current_price)

    async def _manage_position(self, pos: ManagedPosition, current_price: float):
        """Apply Trading Plan position management rules."""

        if pos.phase == PositionPhase.INITIAL:
            await self._handle_initial_phase(pos, current_price)

        elif pos.phase == PositionPhase.SL_MOVED:
            await self._handle_sl_moved_phase(pos, current_price)

        elif pos.phase == PositionPhase.BREAK_EVEN:
            await self._handle_be_phase(pos, current_price)

        elif pos.phase == PositionPhase.TRAILING_TO_TP1:
            await self._handle_trailing_phase(pos, current_price)

        elif pos.phase == PositionPhase.BEYOND_TP1:
            await self._handle_aggressive_phase(pos, current_price)

    async def _handle_initial_phase(self, pos: ManagedPosition, current_price: float):
        """
        Phase 1: Price has started moving in our favor.
        Move SL to previous high/low.
        """
        distance_to_tp1 = abs(pos.take_profit_1 - pos.entry_price)
        current_profit = (
            (current_price - pos.entry_price) if pos.direction == "BUY"
            else (pos.entry_price - current_price)
        )

        # When price has moved ~20% toward TP1, move SL to structure
        if current_profit > distance_to_tp1 * 0.20:
            if pos.direction == "BUY":
                new_sl = pos.original_sl + (pos.entry_price - pos.original_sl) * 0.5
            else:
                new_sl = pos.original_sl - (pos.original_sl - pos.entry_price) * 0.5

            await self._update_sl(pos, new_sl)
            pos.phase = PositionPhase.SL_MOVED
            logger.info(f"{pos.trade_id}: Phase -> SL_MOVED ({new_sl:.5f})")

    async def _handle_sl_moved_phase(self, pos: ManagedPosition, current_price: float):
        """
        Phase 2: Move to Break Even when unrealized profit reaches 1%.
        TradingLab: "siempre que lleguemos al 1% pongo el break-even"
        """
        current_profit = (
            (current_price - pos.entry_price) if pos.direction == "BUY"
            else (pos.entry_price - current_price)
        )
        profit_pct = current_profit / pos.entry_price if pos.entry_price else 0

        # Move to BE when at 1% unrealized profit (TradingLab rule)
        if profit_pct >= 0.01:
            # BE = entry price (+ small buffer for spread)
            spread_buffer = abs(pos.entry_price - pos.original_sl) * 0.02
            if pos.direction == "BUY":
                new_sl = pos.entry_price + spread_buffer
            else:
                new_sl = pos.entry_price - spread_buffer

            await self._update_sl(pos, new_sl)
            pos.phase = PositionPhase.BREAK_EVEN
            logger.info(f"{pos.trade_id}: Phase -> BREAK_EVEN")
            # Notify risk manager for scale-in rule
            if self.risk_manager is not None:
                self.risk_manager.mark_position_at_be(pos.trade_id)

    async def _handle_be_phase(self, pos: ManagedPosition, current_price: float):
        """
        Phase 3: After BE, transition to trailing when at 70% to TP1.
        """
        distance_to_tp1 = abs(pos.take_profit_1 - pos.entry_price)
        current_profit = (
            (current_price - pos.entry_price) if pos.direction == "BUY"
            else (pos.entry_price - current_price)
        )

        # Start trailing when at 70% to TP1
        if current_profit >= distance_to_tp1 * 0.70:
            pos.phase = PositionPhase.TRAILING_TO_TP1
            logger.info(
                f"{pos.trade_id}: Phase -> TRAILING_TO_TP1 "
                f"(style={self.management_style.value}, ema={self._base_ema_key})"
            )

    async def _handle_trailing_phase(self, pos: ManagedPosition, current_price: float):
        """
        Phase 4: Trail SL using EMA 50 on the timeframe determined by the
        configured management style (LP/CP).

        EMA 50 acts as dynamic support/resistance — SL follows it toward TP1.
        No partial profit taking: "No se toman parciales de ganancia."
        Give space to the EMA — buffer below/above, never exactly on it.
        """
        # Check if TP1 has been reached -> switch to aggressive (CPA) trailing
        tp1_reached = (
            (pos.direction == "BUY" and current_price >= pos.take_profit_1) or
            (pos.direction == "SELL" and current_price <= pos.take_profit_1)
        )
        if tp1_reached:
            pos.phase = PositionPhase.BEYOND_TP1
            logger.info(
                f"{pos.trade_id}: TP1 REACHED -> Phase AGGRESSIVE "
                f"(switching to CPA: {self._cpa_ema_key})"
            )
            return

        # Get the EMA 50 value for the base management style
        trail_ema = self._get_trail_ema(pos.instrument, self._base_ema_key)

        if trail_ema is not None:
            # Give space to the EMA — do not place SL exactly on it
            buffer = self._ema_buffer(pos, aggressive=False)

            if pos.direction == "BUY":
                new_sl = trail_ema - buffer
                # Only move SL up, never down
                if new_sl > pos.current_sl:
                    await self._update_sl(pos, new_sl)
                    logger.debug(
                        f"{pos.trade_id}: Trailing SL -> {new_sl:.5f} "
                        f"({self.management_style.value} {self._base_ema_key}={trail_ema:.5f})"
                    )
            else:
                new_sl = trail_ema + buffer
                # Only move SL down, never up
                if new_sl < pos.current_sl:
                    await self._update_sl(pos, new_sl)
                    logger.debug(
                        f"{pos.trade_id}: Trailing SL -> {new_sl:.5f} "
                        f"({self.management_style.value} {self._base_ema_key}={trail_ema:.5f})"
                    )
        else:
            # Fallback: trail with percentage if no EMA data available
            await self._trail_with_percentage(pos, current_price, trail_pct=0.4)

    async def _handle_aggressive_phase(self, pos: ManagedPosition, current_price: float):
        """
        Phase 5: Beyond TP1 — switch to CPA (Short-term Aggressive) trailing.

        Uses the CPA EMA 50 timeframe for tighter trailing to maximize profit.
        No partial profits: only full close at TP_max or via trailing SL hit.
        "No se toman parciales de ganancia."
        """
        # Check if TP_max has been reached -> close full position
        if pos.take_profit_max:
            tp_max_reached = (
                (pos.direction == "BUY" and current_price >= pos.take_profit_max) or
                (pos.direction == "SELL" and current_price <= pos.take_profit_max)
            )
            if tp_max_reached:
                try:
                    await self.broker.close_trade(pos.trade_id)
                    logger.info(
                        f"{pos.trade_id}: TP_MAX REACHED ({pos.take_profit_max:.5f}) — "
                        f"CLOSED remaining position at {current_price:.5f}"
                    )
                    self.remove_position(pos.trade_id)
                    return
                except Exception as e:
                    logger.error(f"{pos.trade_id}: Failed to close at TP_max: {e}")

        # Use CPA EMA 50 for aggressive trailing beyond TP1
        aggressive_ema = self._get_trail_ema(pos.instrument, self._cpa_ema_key)

        if aggressive_ema is not None:
            # Tighter buffer in aggressive phase, but still give EMA some space
            buffer = self._ema_buffer(pos, aggressive=True)

            if pos.direction == "BUY":
                new_sl = aggressive_ema - buffer
                if new_sl > pos.current_sl:
                    await self._update_sl(pos, new_sl)
                    logger.debug(
                        f"{pos.trade_id}: AGGRESSIVE trail SL -> {new_sl:.5f} "
                        f"(CPA {self._cpa_ema_key}={aggressive_ema:.5f})"
                    )
            else:
                new_sl = aggressive_ema + buffer
                if new_sl < pos.current_sl:
                    await self._update_sl(pos, new_sl)
                    logger.debug(
                        f"{pos.trade_id}: AGGRESSIVE trail SL -> {new_sl:.5f} "
                        f"(CPA {self._cpa_ema_key}={aggressive_ema:.5f})"
                    )
        else:
            # Fallback: tight percentage trail
            await self._trail_with_percentage(pos, current_price, trail_pct=0.2)

    async def _trail_with_percentage(self, pos: ManagedPosition, current_price: float, trail_pct: float):
        """Fallback trailing: move SL to lock in a percentage of unrealized profit. Syncs with broker."""
        distance_to_tp1 = abs(pos.take_profit_1 - pos.entry_price)
        current_profit = (
            (current_price - pos.entry_price) if pos.direction == "BUY"
            else (pos.entry_price - current_price)
        )

        if current_profit <= 0:
            return

        trail_distance = distance_to_tp1 * trail_pct

        if pos.direction == "BUY":
            new_sl = current_price - trail_distance
            if new_sl > pos.current_sl:
                await self._update_sl(pos, new_sl)
                logger.debug(f"{pos.trade_id}: Fallback trail SL -> {new_sl:.5f}")
        else:
            new_sl = current_price + trail_distance
            if new_sl < pos.current_sl:
                await self._update_sl(pos, new_sl)
                logger.debug(f"{pos.trade_id}: Fallback trail SL -> {new_sl:.5f}")

    async def _update_sl(self, pos: ManagedPosition, new_sl: float):
        """Update stop loss on the broker."""
        try:
            await self.broker.modify_trade_sl(pos.trade_id, new_sl)
            pos.current_sl = new_sl
        except Exception as e:
            logger.error(f"Failed to update SL for {pos.trade_id}: {e}")

    def remove_position(self, trade_id: str):
        """Stop tracking a closed position."""
        if trade_id in self.positions:
            del self.positions[trade_id]
            logger.info(f"Position {trade_id} removed from tracking")
