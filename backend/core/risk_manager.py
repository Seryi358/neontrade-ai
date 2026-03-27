"""
NeonTrade AI - Risk Manager
Implements all risk management rules from the TradingLab Trading Plan.

Rules:
- 1% risk per Day Trade
- 0.5% risk per Scalping trade
- 1% risk per Swing Trade
- Max 7% total risk at any time
- Correlated pairs: 0.75% each instead of full risk
- No trading before major news
- Close positions before Friday market close
- Minimum R:R ratio of 2.0 to TP1

Drawdown Management (ch18.7):
- Fixed 1%: always use base risk
- Variable: adjust based on win rate
- Fixed levels: 1% -> 0.75% at -5% DD -> 0.50% at -7.5% DD -> 0.25% at -10% DD

Delta Risk Algorithm (ch18.8):
- Increase risk during winning streaks
- Delta parameter 0.60 recommended
- Progression: 1% -> 1.5% -> 2% based on accumulated gains

Scale-In Rule (Trading Plan):
- Don't enter a subsequent trade unless Break Even is set on the first trade
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Tuple
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
        self._delta_accumulated_gain: float = 0.0  # Alias used by delta bonus
        self._current_delta_risk: float = 0.0  # Additional risk from delta
        # Historical max drawdown tracking (for variable DD and delta algorithms)
        self._max_historical_dd: float = 0.0
        # Scale-in tracking: positions that have reached Break Even
        self._positions_at_be: set = set()  # trade_ids at BE or beyond
        # Funded account tracking
        self._funded_daily_pnl: float = 0.0
        self._funded_daily_pnl_date: str = ""

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

        # Track historical max drawdown for variable DD and delta algorithms
        current_dd = self.get_current_drawdown()
        self._max_historical_dd = max(self._max_historical_dd, current_dd)

    def get_current_drawdown(self) -> float:
        """Get current drawdown as a positive decimal (e.g., 0.05 = 5% DD)."""
        if self._peak_balance <= 0:
            return 0.0
        dd = (self._peak_balance - self._current_balance) / self._peak_balance
        return max(0.0, dd)

    def _calculate_recent_win_rate(self) -> float:
        """Calculate win rate from the last 50 trades."""
        if not self._trade_history:
            return 0.5  # Default when no history
        recent = self._trade_history[-50:]
        total = len(recent)
        wins = sum(1 for t in recent if t.is_win)
        return wins / total if total > 0 else 0.5

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
            # Variable method from TradingLab Excel (Drawdown- sheet)
            # Uses winrate x base_risk x multiplier at each DD level
            win_rate = self._calculate_recent_win_rate()
            # Need historical max DD to determine levels
            max_dd_hist = self._max_historical_dd or dd or 0.05  # fallback 5%

            if max_dd_hist <= 0:
                return base_risk

            # Determine which level we're at based on DD relative to historical max
            dd_ratio = dd / max_dd_hist if max_dd_hist > 0 else 0

            if dd_ratio >= 1.0:  # At or beyond max DD
                adjusted = win_rate * base_risk * 1.0
            elif dd_ratio >= 0.75:  # Level 2
                adjusted = win_rate * base_risk * 1.33
            elif dd_ratio >= 0.50:  # Level 1
                adjusted = win_rate * base_risk * 1.66
            else:  # No significant DD
                return base_risk

            # Minimum 25% of base risk
            return max(adjusted, base_risk * 0.25)

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
        """Delta risk algorithm from TradingLab Excel (Delta+ sheet).
        Increases risk during winning streaks using fixed levels."""
        if not settings.delta_enabled:
            return 0.0

        # Calculate accumulated gain from winning streak
        accumulated = self._delta_accumulated_gain
        if accumulated <= 0:
            return 0.0

        # Delta parameter determines how quickly we advance levels
        delta = settings.delta_parameter  # 0.6 recommended
        max_dd = self._max_historical_dd or 0.05  # fallback
        delta_threshold = max_dd * delta  # gain needed per level

        if delta_threshold <= 0:
            return 0.0

        # Determine current level based on accumulated gains
        level = min(int(accumulated / delta_threshold), 3)

        # Fixed risk levels from Excel (Delta+ sheet)
        # Level 0 = base, Level 1 = 1.5%, Level 2 = 2.0%, Level 3 = 3.0%
        level_risks = {
            0: base_risk,           # 1.0% (no bonus)
            1: 0.015,               # 1.5%
            2: 0.020,               # 2.0%
            3: 0.030,               # 3.0%
        }

        target_risk = level_risks.get(level, base_risk)
        bonus = max(0, target_risk - base_risk)

        # Cap at delta_max_risk
        max_bonus = settings.delta_max_risk - base_risk
        return min(bonus, max(0, max_bonus))

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
        self._delta_accumulated_gain += pnl_percent

        # Reset accumulated gain on loss (delta resets on losing trade)
        if pnl_percent < 0:
            self._accumulated_gain = 0.0
            self._delta_accumulated_gain = 0.0
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
        # Funded account check
        funded_ok, funded_reason = self.check_funded_account_limits()
        if not funded_ok:
            logger.warning(f"Cannot take trade on {instrument}: {funded_reason}")
            return False

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

        # Mentoría TradingLab: Position Size = Risk Amount / SL Distance
        # sl_distance is in price terms, units represent position size
        if sl_distance <= 0:
            logger.error(f"Invalid SL distance ({sl_distance}) for {instrument}")
            return 0

        units = int(risk_amount / sl_distance)

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
            f"SL distance: {sl_distance:.5f}"
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
        Minimum R:R to TP1 must be >= 2.0 (from Trading Plan).
        """
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit_1 - entry_price)

        if risk == 0:
            return False

        rr_ratio = reward / risk
        # Use small epsilon for floating-point comparison to avoid rejecting
        # trades that are exactly at the minimum ratio (e.g., 2.0 computed as 1.9999...)
        if rr_ratio < settings.min_rr_ratio - 1e-9:
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

    # ── Funded Account Mode (Workshop Cuentas Fondeadas) ────────

    def check_funded_account_limits(self) -> Tuple[bool, str]:
        """
        Check funded account drawdown limits.
        Returns (can_trade, reason).
        If funded mode is off, always returns (True, "").
        """
        if not settings.funded_account_mode:
            return (True, "")

        # Reset daily PnL tracker if the day changed
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._funded_daily_pnl_date != today:
            self._funded_daily_pnl = 0.0
            self._funded_daily_pnl_date = today

        # Check daily DD: realized daily loss vs max daily DD
        if self._current_balance > 0:
            daily_dd_limit = settings.funded_max_daily_dd * self._current_balance
            if self._funded_daily_pnl < 0 and abs(self._funded_daily_pnl) >= daily_dd_limit:
                return (
                    False,
                    f"Funded: daily DD limit reached "
                    f"({abs(self._funded_daily_pnl):.2f} >= {daily_dd_limit:.2f})",
                )

        # Check total DD: overall drawdown vs funded max total DD
        total_dd = self.get_current_drawdown()
        if total_dd >= settings.funded_max_total_dd:
            return (
                False,
                f"Funded: total DD limit reached "
                f"({total_dd:.2%} >= {settings.funded_max_total_dd:.2%})",
            )

        return (True, "")

    def record_funded_pnl(self, pnl_amount: float):
        """
        Accumulate daily P&L for funded account tracking.
        Called when a trade closes.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._funded_daily_pnl_date != today:
            self._funded_daily_pnl = 0.0
            self._funded_daily_pnl_date = today

        self._funded_daily_pnl += pnl_amount
        logger.info(
            f"Funded PnL updated: {pnl_amount:+.2f} | "
            f"Daily total: {self._funded_daily_pnl:+.2f}"
        )

    def get_funded_status(self) -> Dict:
        """Get funded account status for API."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._funded_daily_pnl_date != today:
            daily_pnl = 0.0
        else:
            daily_pnl = self._funded_daily_pnl

        daily_dd_limit = (
            settings.funded_max_daily_dd * self._current_balance
            if self._current_balance > 0 else 0.0
        )
        total_dd = self.get_current_drawdown()

        can_trade, reason = self.check_funded_account_limits()

        return {
            "enabled": settings.funded_account_mode,
            "can_trade": can_trade,
            "blocked_reason": reason,
            "daily_pnl": round(daily_pnl, 2),
            "daily_dd_used_pct": round(
                (abs(daily_pnl) / daily_dd_limit * 100) if daily_dd_limit > 0 and daily_pnl < 0 else 0.0,
                2,
            ),
            "daily_dd_limit": round(settings.funded_max_daily_dd * 100, 2),
            "daily_dd_limit_amount": round(daily_dd_limit, 2),
            "total_dd_pct": round(total_dd * 100, 2),
            "total_dd_limit": round(settings.funded_max_total_dd * 100, 2),
            "no_overnight": settings.funded_no_overnight,
            "no_news_trading": settings.funded_no_news_trading,
        }

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
