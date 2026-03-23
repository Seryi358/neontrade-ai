"""
NeonTrade AI - Position Manager
Manages open positions: SL movement, BE, trailing stops.

From Trading Plan:
- Move SL above/below previous high/low when price starts moving in favor
- Move to Break Even (BE) when price is 50% of the way to TP1
- After TP1, use Short Term Aggressive management with shortest EMAs
- Use EMA 2m and EMA 5m for day trading position management
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
    """Manages all open positions according to the Trading Plan rules."""

    def __init__(self, broker_client, risk_manager=None):
        self.broker = broker_client
        self.risk_manager = risk_manager  # Reference for scale-in BE tracking
        self.positions: Dict[str, ManagedPosition] = {}
        # EMA values from last market analysis (injected by trading engine)
        self._latest_emas: Dict[str, Dict[str, float]] = {}

    def set_ema_values(self, instrument: str, emas: Dict[str, float]):
        """Update EMA values for an instrument (called by trading engine after analysis)."""
        self._latest_emas[instrument] = emas

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
        Phase 2: Move to Break Even when price is 50% to TP1.
        """
        distance_to_tp1 = abs(pos.take_profit_1 - pos.entry_price)
        current_profit = (
            (current_price - pos.entry_price) if pos.direction == "BUY"
            else (pos.entry_price - current_price)
        )

        # Move to BE when at 50% to TP1
        if current_profit >= distance_to_tp1 * 0.50:
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
            logger.info(f"{pos.trade_id}: Phase -> TRAILING_TO_TP1")

    async def _handle_trailing_phase(self, pos: ManagedPosition, current_price: float):
        """
        Phase 4: Trail SL using EMA 5 on M5 timeframe.
        EMA acts as dynamic support/resistance — SL follows it toward TP1.
        """
        # Check if TP1 has been reached
        if pos.direction == "BUY" and current_price >= pos.take_profit_1:
            pos.phase = PositionPhase.BEYOND_TP1
            logger.info(f"{pos.trade_id}: TP1 REACHED -> Phase AGGRESSIVE")
            return
        elif pos.direction == "SELL" and current_price <= pos.take_profit_1:
            pos.phase = PositionPhase.BEYOND_TP1
            logger.info(f"{pos.trade_id}: TP1 REACHED -> Phase AGGRESSIVE")
            return

        # Get EMA values for this instrument
        emas = self._latest_emas.get(pos.instrument, {})
        ema_m5_5 = emas.get("EMA_M5_5")

        if ema_m5_5 is not None:
            # Trail SL to EMA 5 on M5 (with small buffer)
            pip_buffer = abs(pos.take_profit_1 - pos.entry_price) * 0.02

            if pos.direction == "BUY":
                new_sl = ema_m5_5 - pip_buffer
                # Only move SL up, never down
                if new_sl > pos.current_sl:
                    await self._update_sl(pos, new_sl)
                    logger.debug(
                        f"{pos.trade_id}: Trailing SL -> {new_sl:.5f} (EMA5 M5={ema_m5_5:.5f})"
                    )
            else:
                new_sl = ema_m5_5 + pip_buffer
                # Only move SL down, never up
                if new_sl < pos.current_sl:
                    await self._update_sl(pos, new_sl)
                    logger.debug(
                        f"{pos.trade_id}: Trailing SL -> {new_sl:.5f} (EMA5 M5={ema_m5_5:.5f})"
                    )
        else:
            # Fallback: trail with percentage if no EMA data available
            self._trail_with_percentage(pos, current_price, trail_pct=0.4)

    async def _handle_aggressive_phase(self, pos: ManagedPosition, current_price: float):
        """
        Phase 5: Beyond TP1 - Short Term Aggressive management.
        Use EMA 2 on M5 for tight trailing — maximize profit beyond TP1.
        Close if price crosses EMA 2 against the trade.
        """
        emas = self._latest_emas.get(pos.instrument, {})
        ema_m5_2 = emas.get("EMA_M5_2")

        if ema_m5_2 is not None:
            # Aggressive trailing with EMA 2 on M5 (tightest EMA)
            pip_buffer = abs(pos.take_profit_1 - pos.entry_price) * 0.01

            if pos.direction == "BUY":
                new_sl = ema_m5_2 - pip_buffer
                if new_sl > pos.current_sl:
                    await self._update_sl(pos, new_sl)
                    logger.debug(
                        f"{pos.trade_id}: AGGRESSIVE trail SL -> {new_sl:.5f} "
                        f"(EMA2 M5={ema_m5_2:.5f})"
                    )
            else:
                new_sl = ema_m5_2 + pip_buffer
                if new_sl < pos.current_sl:
                    await self._update_sl(pos, new_sl)
                    logger.debug(
                        f"{pos.trade_id}: AGGRESSIVE trail SL -> {new_sl:.5f} "
                        f"(EMA2 M5={ema_m5_2:.5f})"
                    )
        else:
            # Fallback: tight percentage trail
            self._trail_with_percentage(pos, current_price, trail_pct=0.2)

    def _trail_with_percentage(self, pos: ManagedPosition, current_price: float, trail_pct: float):
        """Fallback trailing: move SL to lock in a percentage of unrealized profit."""
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
                # Schedule async update (can't await from sync method)
                pos.current_sl = new_sl
                logger.debug(f"{pos.trade_id}: Fallback trail SL -> {new_sl:.5f}")
        else:
            new_sl = current_price + trail_distance
            if new_sl < pos.current_sl:
                pos.current_sl = new_sl
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
