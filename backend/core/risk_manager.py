"""
NeonTrade AI - Risk Manager
Implements all risk management rules from the TradingLab Trading Plan.

Rules:
- 1% risk per Day Trade
- 0.5% risk per Scalping trade
- 3% risk per Swing Trade
- Max 7% total risk at any time
- Correlated pairs: 0.75% each instead of full risk
- No trading before major news
- Close positions before Friday market close
- Minimum R:R ratio of 0.80 to TP1

Drawdown Management (ch18.7):
- Fixed 1%: always use base risk
- Variable: adjust based on win rate
- Fixed levels: 1% -> 0.75% at -4.12% DD -> 0.50% at -6.18% DD -> 0.25% at -8.24% DD

Delta Risk Algorithm (ch18.8):
- Increase risk during winning streaks
- Delta parameter 0.60 recommended
- Progression: 1% -> 1.5% -> 2% based on accumulated gains

Scale-In Rule (Trading Plan):
- Don't enter a subsequent trade unless Break Even is set on the first trade
"""

from enum import Enum
from typing import Optional, List, Dict
from dataclasses import dataclass, field
from loguru import logger
from config import settings
from core.resilience import balance_cache


class TradingStyle(Enum):
    DAY_TRADING = "day_trading"
    SCALPING = "scalping"
    SWING = "swing"


class DrawdownMethod(Enum):
    FIXED_1PCT = "fixed_1pct"      # Always use base 1%
    VARIABLE = "variable"           # Adjust based on win rate
    FIXED_LEVELS = "fixed_levels"   # Step-down at DD thresholds


@dataclass
class TradeRisk:
    instrument: str
    style: TradingStyle
    risk_percent: float
    units: int
    stop_loss: float
    take_profit_1: float
    take_profit_max: Optional[float]
    reward_risk_ratio: float
    entry_price: float
    direction: str  # "BUY" or "SELL"
    entry_type: str = "MARKET"  # MARKET, LIMIT, or STOP
    limit_price: Optional[float] = None  # Price for limit/stop orders


@dataclass
class TradeResult:
    """Record of a completed trade for delta algorithm tracking."""
    trade_id: str
    instrument: str
    pnl_percent: float  # P&L as percentage of account
    is_win: bool


class RiskManager:
    """Manages all risk calculations and validations."""

    def __init__(self, broker_client):
        self.broker = broker_client
        self._active_risks: Dict[str, float] = {}  # trade_id -> risk_percent
        self._active_instruments: Dict[str, str] = {}  # trade_id -> instrument
        # Drawdown tracking
        self._peak_balance: float = 0.0
        self._current_balance: float = 0.0
        # Delta algorithm tracking
        self._trade_history: List[TradeResult] = []
        self._accumulated_gain: float = 0.0  # Running gain since last risk increase
        self._current_delta_risk: float = 0.0  # Additional risk from delta
        # Scale-in tracking: positions that have reached Break Even
        self._positions_at_be: set = set()  # trade_ids at BE or beyond

    # ── Drawdown Management (ch18.7) ────────────────────────────────

    async def update_balance_tracking(self):
        """Update peak balance and current balance for drawdown calculation."""
        cached_balance = balance_cache.get("account_balance")
        if cached_balance is not None:
            self._current_balance = cached_balance
        else:
            self._current_balance = await self.broker.get_account_balance()
            balance_cache.set("account_balance", self._current_balance)

        if self._current_balance > self._peak_balance:
            self._peak_balance = self._current_balance

    def get_current_drawdown(self) -> float:
        """Get current drawdown as a positive decimal (e.g., 0.05 = 5% DD)."""
        if self._peak_balance <= 0:
            return 0.0
        dd = (self._peak_balance - self._current_balance) / self._peak_balance
        return max(0.0, dd)

    def _get_drawdown_adjusted_risk(self, base_risk: float) -> float:
        """
        Adjust risk based on current drawdown using the configured method.
        From TradingLab ch18.7 - Three methods:
        1. Fixed 1%: no adjustment
        2. Variable: based on win rate
        3. Fixed levels: step-down at specific DD thresholds
        """
        method = settings.drawdown_method

        if method == "fixed_1pct":
            return base_risk

        dd = self.get_current_drawdown()

        if method == "variable":
            # Variable method: reduce proportionally based on win rate
            if not self._trade_history:
                return base_risk
            wins = sum(1 for t in self._trade_history[-50:] if t.is_win)
            total = min(len(self._trade_history), 50)
            win_rate = wins / total if total > 0 else 0.5
            # Below 40% win rate, reduce risk proportionally
            if win_rate < 0.40:
                factor = win_rate / 0.40  # 0.0 - 1.0
                return base_risk * max(0.25, factor)
            return base_risk

        if method == "fixed_levels":
            # Fixed levels from Trading Plan spreadsheet
            if dd >= settings.drawdown_level_3:
                adjusted = settings.drawdown_risk_3
                logger.warning(
                    f"Drawdown {dd:.2%} >= Level 3 ({settings.drawdown_level_3:.2%}). "
                    f"Risk reduced to {adjusted:.2%}"
                )
                return adjusted
            elif dd >= settings.drawdown_level_2:
                adjusted = settings.drawdown_risk_2
                logger.warning(
                    f"Drawdown {dd:.2%} >= Level 2 ({settings.drawdown_level_2:.2%}). "
                    f"Risk reduced to {adjusted:.2%}"
                )
                return adjusted
            elif dd >= settings.drawdown_level_1:
                adjusted = settings.drawdown_risk_1
                logger.info(
                    f"Drawdown {dd:.2%} >= Level 1 ({settings.drawdown_level_1:.2%}). "
                    f"Risk reduced to {adjusted:.2%}"
                )
                return adjusted

        return base_risk

    # ── Delta Risk Algorithm (ch18.8) ───────────────────────────────

    def _get_delta_bonus(self, base_risk: float) -> float:
        """
        Calculate additional risk from delta algorithm during winning streaks.
        From TradingLab ch18.8:
        - Delta 0.60: need ~5.56% accumulated gain to increase from 1% to 1.5%
        - Formula: next_level_gain = (base_risk * 0.5) / delta_parameter
        """
        if not settings.delta_enabled:
            return 0.0

        if self._accumulated_gain <= 0:
            return 0.0

        delta = settings.delta_parameter
        if delta <= 0:
            return 0.0

        # Each level adds 0.5% risk
        risk_increment = base_risk * 0.5
        gain_per_level = risk_increment / delta

        # How many levels have we earned
        levels = int(self._accumulated_gain / gain_per_level)
        bonus = levels * risk_increment

        # Cap at max delta risk
        bonus = min(bonus, settings.delta_max_risk - base_risk)
        bonus = max(0.0, bonus)

        if bonus > 0:
            logger.info(
                f"Delta algorithm: +{bonus:.2%} risk bonus "
                f"(accumulated gain: {self._accumulated_gain:.2%}, "
                f"levels: {levels})"
            )

        return bonus

    def record_trade_result(self, trade_id: str, instrument: str, pnl_percent: float):
        """
        Record a completed trade for delta algorithm and win-rate tracking.
        Called when a trade is closed.
        """
        result = TradeResult(
            trade_id=trade_id,
            instrument=instrument,
            pnl_percent=pnl_percent,
            is_win=pnl_percent > 0,
        )
        self._trade_history.append(result)

        # Update accumulated gain for delta
        self._accumulated_gain += pnl_percent

        # Reset accumulated gain on loss (delta resets on losing trade)
        if pnl_percent < 0:
            self._accumulated_gain = 0.0
            self._current_delta_risk = 0.0
            logger.info("Delta algorithm: reset after losing trade")

        # Keep history manageable
        if len(self._trade_history) > 200:
            self._trade_history = self._trade_history[-100:]

    # ── Scale-In Rule (Trading Plan) ────────────────────────────────

    def mark_position_at_be(self, trade_id: str):
        """Mark a position as having reached Break Even or beyond."""
        self._positions_at_be.add(trade_id)

    def can_scale_in(self, instrument: str) -> bool:
        """
        Check if a new trade is allowed given the scale-in rule.
        From Trading Plan: don't enter a subsequent strategy trade
        unless Break Even is set on the first trade.
        """
        if not settings.scale_in_require_be:
            return True

        # Check if there are active trades on the same instrument
        for key, risk in self._active_risks.items():
            parts = key.split(":")
            if len(parts) > 1 and parts[0] == instrument:
                trade_id = parts[1]
                if trade_id not in self._positions_at_be:
                    logger.warning(
                        f"Scale-in blocked for {instrument}: "
                        f"existing trade {trade_id} has not reached BE"
                    )
                    return False
        return True

    # ── Core Risk Methods ───────────────────────────────────────────

    def get_risk_for_style(self, style: TradingStyle) -> float:
        """Get the risk percentage for a trading style, adjusted for drawdown and delta."""
        risk_map = {
            TradingStyle.DAY_TRADING: settings.risk_day_trading,
            TradingStyle.SCALPING: settings.risk_scalping,
            TradingStyle.SWING: settings.risk_swing,
        }
        base_risk = risk_map[style]

        # Apply drawdown adjustment (may reduce risk)
        adjusted_risk = self._get_drawdown_adjusted_risk(base_risk)

        # Apply delta bonus (may increase risk during winning streaks)
        delta_bonus = self._get_delta_bonus(adjusted_risk)
        final_risk = adjusted_risk + delta_bonus

        # Never exceed style maximum * 3 (hard cap)
        final_risk = min(final_risk, base_risk * 3)

        return final_risk

    def get_current_total_risk(self) -> float:
        """Get the total risk currently deployed."""
        return sum(self._active_risks.values())

    def can_take_trade(self, style: TradingStyle, instrument: str) -> bool:
        """Check if we can take a new trade without exceeding max risk."""
        # Scale-in check
        if not self.can_scale_in(instrument):
            return False

        risk = self.get_risk_for_style(style)
        # Check for correlated pairs
        risk = self._adjust_for_correlation(instrument, risk)

        current_risk = self.get_current_total_risk()
        if current_risk + risk > settings.max_total_risk:
            logger.warning(
                f"Cannot take trade on {instrument}: "
                f"current risk {current_risk:.2%} + {risk:.2%} "
                f"> max {settings.max_total_risk:.2%}"
            )
            return False
        return True

    def _adjust_for_correlation(self, instrument: str, base_risk: float) -> float:
        """
        If there's already an open trade on a correlated pair,
        reduce risk to 0.75% (correlation factor).
        """
        active_instruments = set()
        # This will be populated from open trades
        for trade_id, risk in self._active_risks.items():
            parts = trade_id.split(":")
            if len(parts) > 1:
                active_instruments.add(parts[0])

        for group in settings.correlation_groups:
            if instrument in group:
                for active_inst in active_instruments:
                    if active_inst in group and active_inst != instrument:
                        adjusted = base_risk * settings.correlated_risk_factor
                        logger.info(
                            f"Correlation detected: {instrument} <-> {active_inst}. "
                            f"Risk adjusted from {base_risk:.2%} to {adjusted:.2%}"
                        )
                        return adjusted
        return base_risk

    async def calculate_position_size(
        self,
        instrument: str,
        style: TradingStyle,
        entry_price: float,
        stop_loss: float,
    ) -> int:
        """
        Calculate the number of units to trade based on risk percentage.

        Formula: units = (balance * risk%) / (|entry - SL| / pip_value)
        From TradingLab ch18.4: Position Size = (Risk Amount / SL_distance%) * 100
        """
        cached_balance = balance_cache.get("account_balance")
        if cached_balance is not None:
            balance = cached_balance
        else:
            balance = await self.broker.get_account_balance()
            balance_cache.set("account_balance", balance)

        risk_percent = self.get_risk_for_style(style)
        risk_percent = self._adjust_for_correlation(instrument, risk_percent)

        risk_amount = balance * risk_percent
        pip_value = await self.broker.get_pip_value(instrument)
        sl_distance = abs(entry_price - stop_loss)

        if sl_distance == 0:
            logger.error(f"SL distance is 0 for {instrument}")
            return 0

        if pip_value <= 0:
            logger.error(f"Invalid pip value ({pip_value}) for {instrument}")
            return 0

        # Calculate units
        sl_pips = sl_distance / pip_value
        if sl_pips <= 0:
            logger.error(f"Invalid SL pips ({sl_pips}) for {instrument}")
            return 0

        cost_per_unit = sl_pips * pip_value
        if cost_per_unit <= 0:
            logger.error(f"Invalid cost per unit for {instrument}")
            return 0

        units = int(risk_amount / cost_per_unit)

        # Cap maximum position size to prevent broker rejections
        MAX_UNITS = 10_000_000
        if abs(units) > MAX_UNITS:
            logger.warning(f"Position size {units} capped to {MAX_UNITS} for {instrument}")
            units = MAX_UNITS

        # Direction
        if entry_price > stop_loss:
            pass  # BUY - units positive
        else:
            units = -units  # SELL - units negative

        logger.info(
            f"Position size for {instrument}: {units} units | "
            f"Balance: {balance:.2f} | Risk: {risk_percent:.2%} ({risk_amount:.2f}) | "
            f"SL distance: {sl_pips:.1f} pips"
        )
        return units

    def validate_reward_risk(
        self,
        entry_price: float,
        stop_loss: float,
        take_profit_1: float,
    ) -> bool:
        """
        Validate that the trade meets minimum R:R ratio.
        Minimum R:R to TP1 must be >= 0.80 (from Trading Plan).
        """
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit_1 - entry_price)

        if risk == 0:
            return False

        rr_ratio = reward / risk
        if rr_ratio < settings.min_rr_ratio:
            logger.warning(
                f"R:R ratio {rr_ratio:.2f} is below minimum {settings.min_rr_ratio}. "
                f"Trade rejected."
            )
            return False

        logger.info(f"R:R ratio: {rr_ratio:.2f} (min: {settings.min_rr_ratio})")
        return True

    def register_trade(self, trade_id: str, instrument: str, risk_percent: float):
        """Register an active trade's risk."""
        key = f"{instrument}:{trade_id}"
        self._active_risks[key] = risk_percent
        logger.info(
            f"Trade registered: {key} with {risk_percent:.2%} risk. "
            f"Total risk: {self.get_current_total_risk():.2%}"
        )

    def unregister_trade(self, trade_id: str, instrument: str):
        """Remove a closed trade from risk tracking."""
        key = f"{instrument}:{trade_id}"
        if key in self._active_risks:
            del self._active_risks[key]
            logger.info(
                f"Trade unregistered: {key}. "
                f"Total risk: {self.get_current_total_risk():.2%}"
            )
        # Clean up BE tracking
        self._positions_at_be.discard(trade_id)

    def get_risk_status(self) -> Dict:
        """Get comprehensive risk status for API/frontend."""
        dd = self.get_current_drawdown()
        base_day = settings.risk_day_trading
        adjusted_day = self.get_risk_for_style(TradingStyle.DAY_TRADING)

        wins = sum(1 for t in self._trade_history[-50:] if t.is_win)
        total = min(len(self._trade_history), 50)
        win_rate = wins / total if total > 0 else 0.0

        return {
            "current_drawdown": round(dd * 100, 2),
            "peak_balance": round(self._peak_balance, 2),
            "current_balance": round(self._current_balance, 2),
            "drawdown_method": settings.drawdown_method,
            "base_risk_day": round(base_day * 100, 2),
            "adjusted_risk_day": round(adjusted_day * 100, 2),
            "delta_enabled": settings.delta_enabled,
            "delta_accumulated_gain": round(self._accumulated_gain * 100, 2),
            "total_active_risk": round(self.get_current_total_risk() * 100, 2),
            "max_total_risk": round(settings.max_total_risk * 100, 2),
            "recent_win_rate": round(win_rate * 100, 1),
            "recent_trades": total,
        }
