"""
Atlas - Risk Manager
Implements all risk management rules from the TradingLab Trading Plan.

Rules:
- 1% risk per Day Trade
- 1% risk per Scalping trade (TradingLab universal; users can lower)
- 1% risk per Swing Trade (NON-NEGOTIABLE — same as day trading per mentorship)
- Max 7% total risk at any time
- Correlated pairs: 0.75% each instead of full risk
- No trading before major news
- Close positions before Friday market close
- Minimum R:R ratio of 1.5 to TP1 (2.0 for BLACK and GREEN)

Drawdown Management (ch18.7):
- Fixed 1%: always use base risk
- Variable: adjust based on win rate
- Fixed levels (Trading Plan PDF calc): 1% -> 0.75% at -4.12% DD -> 0.50% at -6.18% DD -> 0.25% at -8.23% DD
  (Mentorship round numbers: -5% -> 0.75%, -7.5% -> 0.50%, -10% -> 0.25%)

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
    units: float  # float for fractional crypto lots (e.g. 0.001 BTC)
    stop_loss: float
    take_profit_1: float
    take_profit_max: Optional[float]
    reward_risk_ratio: float
    entry_price: float
    direction: str  # "BUY" or "SELL"
    entry_type: str = "MARKET"  # MARKET, LIMIT, or STOP
    limit_price: Optional[float] = None  # Price for limit/stop orders
    trailing_tp_only: bool = False  # True for crypto GREEN: skip hard TP1, use EMA 50 trailing
    strategy_variant: Optional[str] = None  # e.g. "GREEN", "BLUE_A", "RED"


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
        # Start-of-day balance for funded account DD calculation
        # Most prop firms calculate daily DD from start-of-day equity (or highest equity of day)
        self._funded_start_of_day_balance: float = 0.0
        # Initial funded account balance — set once on first balance update when funded mode is active.
        # Used for accurate profit target calculation instead of deriving from peak/DD.
        self._funded_initial_balance: float = 0.0
        # Reentry tracking (Esp. Criptomonedas - Reentradas Efectivas)
        # Track stop-outs per instrument to reduce risk on reentries
        # Rules from mentorship:
        #   - Re-enter only while "la esencia" (setup essence) is maintained
        #   - Reduce position size on reentry (1% -> 0.5% -> 0.25%)
        #   - Maximum ~3 reentries per setup/move
        self._reentry_counts: Dict[str, int] = {}  # instrument -> count of consecutive stop-outs
        self._reentry_timestamps: Dict[str, str] = {}  # instrument -> last stop-out ISO timestamp
        self._deal_size_cache: Dict[str, tuple] = {}  # instrument -> (min_size, increment)

    # ── Leverage by Asset Class ───────────────────────────────────────

    def _get_leverage_for_instrument(self, instrument: str) -> int:
        """Return the leverage ratio for an instrument based on its asset class.

        Capital.com defaults for the user's retail account:
        forex 100:1, indices 100:1, commodities 100:1,
        stocks 20:1, crypto 20:1, bonds/rates 200:1.
        """
        from strategies.base import _is_crypto_instrument
        inst = instrument.upper()
        if _is_crypto_instrument(instrument):
            return settings.leverage_crypto
        # Commodities (metals)
        if inst.startswith(("XAU", "XAG", "XPT", "XPD")):
            return settings.leverage_commodities
        # Indices (common Capital.com tickers)
        if any(inst.startswith(x) for x in ("US500", "US100", "US30", "UK100", "DE40", "FR40", "JP225", "HK50", "SPX", "NDX", "DJI", "NAS100", "SPX500")):
            return settings.leverage_indices
        # Bonds / rates — US Treasury ETFs and bond futures symbols
        if inst in {"TLT", "IEF", "SHY", "TBT", "TMF", "AGG", "BND", "LQD", "HYG"} or inst.startswith(("BUND", "UB_", "ZB_", "ZN_", "ZF_", "ZT_")):
            return settings.leverage_bonds
        # Forex: classic A_B pattern (EUR_USD) or 6-letter ticker (EURUSD)
        if "_" in inst:
            parts = inst.split("_")
            if len(parts) == 2 and all(len(p) == 3 and p.isalpha() for p in parts):
                return settings.leverage_forex
        if len(inst) == 6 and inst.isalpha():
            return settings.leverage_forex
        # Individual stocks / equity ETFs: alphabetic ticker 1-5 chars
        if inst.isalpha() and 1 <= len(inst) <= 5:
            return settings.leverage_stocks
        # Unknown class — fall back to forex default
        return settings.leverage_forex

    # ── Deal Size Rules (from broker API) ────────────────────────────

    async def _get_deal_size_rules(self, instrument: str) -> tuple:
        """Get minimum deal size and size increment from broker for an instrument.
        Caches results to avoid repeated API calls.
        Returns (min_size, increment) — e.g. (100, 100) for forex, (0.0001, 0.0001) for BTC."""
        if instrument in self._deal_size_cache:
            return self._deal_size_cache[instrument]

        # Default fallback values if broker query fails
        from strategies.base import _is_crypto_instrument
        if _is_crypto_instrument(instrument):
            default = (0.001, 0.001)
        else:
            default = (100, 100)  # Capital.com forex minimum is 100 units

        try:
            # Query broker for actual dealing rules
            if hasattr(self.broker, '_resolve_epic') and hasattr(self.broker, '_get'):
                epic = await self.broker._resolve_epic(instrument)
                data = await self.broker._get(f'/api/v1/markets/{epic}')
                rules = data.get('dealingRules', {})
                min_val = float(rules.get('minDealSize', {}).get('value', default[0]))
                incr_val = float(rules.get('minSizeIncrement', {}).get('value', default[1]))
                result = (min_val, incr_val)
                self._deal_size_cache[instrument] = result
                logger.debug(f"Deal rules for {instrument}: min={min_val}, increment={incr_val}")
                return result
        except Exception as e:
            logger.debug(f"Failed to get deal rules for {instrument}, using defaults: {e}")

        self._deal_size_cache[instrument] = default
        return default

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

        # Set funded initial balance once (first valid balance when funded mode is on)
        if (self._funded_initial_balance == 0.0
                and self._current_balance > 0
                and settings.funded_account_mode):
            self._funded_initial_balance = self._current_balance
            logger.info(f"Funded initial balance set: ${self._current_balance:.2f}")

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

            # Apply configured minimum risk floor, then 25% of base as fallback
            min_risk = settings.drawdown_min_risk if isinstance(settings.drawdown_min_risk, (int, float)) else 0.0
            return max(adjusted, base_risk * 0.25, min_risk)

        if method == "fixed_levels":
            # Fixed levels from Trading Plan spreadsheet
            min_risk = settings.drawdown_min_risk if isinstance(settings.drawdown_min_risk, (int, float)) else 0.0
            if dd >= settings.drawdown_level_3:
                adjusted = max(settings.drawdown_risk_3, min_risk) if min_risk > 0 else settings.drawdown_risk_3
                logger.warning(
                    f"Drawdown {dd:.2%} >= Level 3 ({settings.drawdown_level_3:.2%}). "
                    f"Risk reduced to {adjusted:.2%}"
                )
                return adjusted
            elif dd >= settings.drawdown_level_2:
                adjusted = max(settings.drawdown_risk_2, min_risk) if min_risk > 0 else settings.drawdown_risk_2
                logger.warning(
                    f"Drawdown {dd:.2%} >= Level 2 ({settings.drawdown_level_2:.2%}). "
                    f"Risk reduced to {adjusted:.2%}"
                )
                return adjusted
            elif dd >= settings.drawdown_level_1:
                adjusted = max(settings.drawdown_risk_1, min_risk) if min_risk > 0 else settings.drawdown_risk_1
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

        # Fixed risk levels from TradingLab Delta+ algorithm
        # Level 0 = base, Level 1 = 1.5%, Level 2 = 2.0%, Level 3 = max 2.0%
        level_risks = {
            0: base_risk,           # 1.0% (no bonus)
            1: 0.015,               # 1.5%
            2: 0.020,               # 2.0%
            3: 0.020,               # 2.0% (capped — TradingLab max is 2%)
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
        # Only add positive PnL here; negative PnL is handled exclusively in the loss branch
        # to avoid double-counting losses (BUG-01 fix).
        if pnl_percent >= 0:
            self._accumulated_gain += pnl_percent
            self._delta_accumulated_gain += pnl_percent

        # Mentorship: delta works on accumulated P&L vs thresholds, not per-trade reset.
        # Only drop to the previous level rather than full reset on any loss.
        if pnl_percent < 0:
            self._delta_accumulated_gain = max(0.0, self._delta_accumulated_gain + pnl_percent)
            self._accumulated_gain = max(0.0, self._accumulated_gain + pnl_percent)
            # Recalculate current level based on remaining accumulated gain
            delta_threshold = (self._max_historical_dd or 0.05) * settings.delta_parameter
            if delta_threshold > 0 and self._delta_accumulated_gain >= delta_threshold * 2:
                self._current_delta_risk = 0.01  # Stay at level 2 (2%)
            elif delta_threshold > 0 and self._delta_accumulated_gain >= delta_threshold:
                self._current_delta_risk = 0.005  # Drop to level 1 (1.5%)
            else:
                self._current_delta_risk = 0.0  # Back to base level
            logger.info(
                f"Delta algorithm: loss absorbed, accumulated_gain={self._delta_accumulated_gain:.4f}, "
                f"delta_risk={self._current_delta_risk:.4f}"
            )

        # Reentry tracking — increment consecutive stop-out count for this instrument
        if pnl_percent < 0:
            self._reentry_counts[instrument] = self._reentry_counts.get(instrument, 0) + 1
            self._reentry_timestamps[instrument] = datetime.now(timezone.utc).isoformat()
            logger.info(f"Reentry tracker: {instrument} stop-out #{self._reentry_counts[instrument]}")
        else:
            # Winning trade resets the reentry counter for this instrument
            self._reentry_counts.pop(instrument, None)
            self._reentry_timestamps.pop(instrument, None)

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

    def get_reentry_count(self, instrument: str) -> int:
        """Get the number of consecutive stop-outs on this instrument.
        Used by strategies to check reentry status.
        Mentorship: max ~3 reentries per setup/move."""
        return self._reentry_counts.get(instrument, 0)

    def get_reentry_risk_multiplier(self, instrument: str) -> float:
        """Get risk multiplier for reentries on this instrument.
        From Esp. Criptomonedas - Reentradas Efectivas:
        - 1st entry: 1.0x (full risk)
        - Subsequent: reads from settings.reentry_risk_N
        - Beyond max_reentries_per_setup: BLOCKED (returns 0.0)
        Forex: no progressive risk reduction per mentorship (just enforce BE requirement)."""
        from strategies.base import _is_crypto_instrument
        count = self.get_reentry_count(instrument)

        # Forex: no progressive risk reduction — only BE requirement applies
        if not _is_crypto_instrument(instrument):
            return 1.0  # Forex: no progressive risk reduction per mentorship

        # Crypto: progressive risk reduction on reentries
        max_reentries = settings.max_reentries_per_setup
        if count == 0:
            return 1.0
        elif count >= max_reentries:
            return 0.0  # Blocked: max reentries exceeded
        elif count == 1:
            return settings.reentry_risk_1
        elif count == 2:
            return settings.reentry_risk_2
        else:
            return settings.reentry_risk_3

    def get_risk_for_style(self, style: TradingStyle, instrument: str = "") -> float:
        """Get the risk percentage for a trading style, adjusted for drawdown, delta, and reentries."""
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

        # Apply reentry risk reduction (Esp. Criptomonedas - Reentradas Efectivas)
        if instrument:
            reentry_mult = self.get_reentry_risk_multiplier(instrument)
            if reentry_mult == 0.0:
                logger.warning(f"Reentry BLOCKED for {instrument}: max reentries exceeded (3+)")
                return 0.0
            elif reentry_mult < 1.0:
                final_risk *= reentry_mult
                logger.info(f"Reentry risk reduction for {instrument}: {reentry_mult}x -> {final_risk:.4f}")

        # TradingLab: never exceed 2% per trade (absolute hard cap)
        final_risk = min(final_risk, settings.delta_max_risk)

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

        risk = self.get_risk_for_style(style, instrument)
        if risk == 0.0:
            logger.warning(f"Cannot take trade on {instrument}: max reentries exceeded")
            return False
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
        reduce risk to a fixed 0.75% each (TradingLab Trading Plan).
        Mentorship: "entrar con el 0,75% de riesgo en cada uno"
        This is a fixed absolute value, not a multiplier of the adjusted risk.
        """
        active_instruments = set()
        for trade_id, risk in self._active_risks.items():
            parts = trade_id.split(":")
            if len(parts) > 1:
                active_instruments.add(parts[0])

        # Check all correlation groups (forex, indices, crypto)
        all_groups = (
            settings.correlation_groups
            + getattr(settings, 'indices_correlation_groups', [])
            + getattr(settings, 'crypto_correlation_groups', [])
        )

        for group in all_groups:
            if instrument in group:
                for active_inst in active_instruments:
                    if active_inst in group and active_inst != instrument:
                        # Fixed 0.75% per correlated trade (mentorship rule)
                        # But never exceed the drawdown-adjusted risk passed in
                        corr_risk = settings.correlated_risk_pct  # 0.0075 = 0.75%
                        adjusted = min(corr_risk, base_risk)
                        logger.info(
                            f"Correlation detected: {instrument} <-> {active_inst}. "
                            f"Risk capped to {adjusted:.2%} (corr={corr_risk:.2%}, "
                            f"base={base_risk:.2%})"
                        )
                        return adjusted
        return base_risk

    async def calculate_position_size(
        self,
        instrument: str,
        style: TradingStyle,
        entry_price: float,
        stop_loss: float,
    ) -> float:
        """
        Calculate the number of units to trade based on risk percentage.

        Alex's formula (ch18.4): Position Size (USD) = Risk$ / %SL_distance × 100
        Example: $10 risk, 4.17% SL distance → 10 / 4.17 × 100 = $240 position
        In code: units = risk_amount / sl_distance (equivalent, gives base-asset units)
        """
        cached_balance = balance_cache.get("account_balance")
        if cached_balance is not None:
            balance = cached_balance
        else:
            balance = await self.broker.get_account_balance()
            balance_cache.set("account_balance", balance)

        if balance <= 0:
            logger.warning(f"Cannot size position for {instrument}: balance is {balance}")
            return 0

        risk_percent = self.get_risk_for_style(style, instrument)
        risk_percent = self._adjust_for_correlation(instrument, risk_percent)

        risk_amount = balance * risk_percent
        sl_distance = abs(entry_price - stop_loss)

        if sl_distance == 0:
            logger.error(f"SL distance is 0 for {instrument}")
            return 0

        # For Capital.com CFDs (no pip_value needed): 1 unit = 1 unit of base currency
        # P&L = units * price_change, so units = risk_amount / sl_distance_in_price
        # The pip_value from broker is pip SIZE (e.g., 0.0001), NOT dollar-per-pip,
        # so we must NOT multiply by it. Direct division gives correct CFD units.
        # Example: $100 risk, 0.0050 SL distance = 20,000 units
        raw_units = risk_amount / sl_distance

        # Get broker minimum deal size and increment for this instrument
        min_units, size_increment = await self._get_deal_size_rules(instrument)

        # Round to the broker's size increment
        if size_increment > 0:
            units = round(raw_units / size_increment) * size_increment
            # Ensure proper decimal places based on increment
            if size_increment >= 1:
                units = int(units)
            else:
                decimals = len(str(size_increment).rstrip('0').split('.')[-1]) if '.' in str(size_increment) else 0
                units = round(units, max(decimals, 2))
        else:
            units = round(raw_units, 6) if raw_units < 100 else int(raw_units)

        if units <= 0:
            logger.debug(f"Position size too small for {instrument}: {units} units")
            return 0

        # Enforce minimum deal size from broker
        if abs(units) < min_units:
            logger.warning(
                f"Position size {units} below broker minimum {min_units} for {instrument}. "
                f"Balance ${balance:.2f} at {risk_percent:.2%} risk (${risk_amount:.2f}) "
                f"with SL distance {sl_distance:.5f} produces {raw_units:.2f} units. "
                f"Need at least {min_units} units to trade this instrument."
            )
            return 0

        # Margin check: verify position doesn't exceed available margin with leverage
        leverage = self._get_leverage_for_instrument(instrument)
        margin_required = abs(units) * entry_price / leverage
        available_margin = balance * 0.90  # keep 10% margin buffer
        if margin_required > available_margin:
            # Reduce units to fit within margin
            max_units_by_margin = (available_margin * leverage) / entry_price
            if size_increment > 0:
                max_units_by_margin = int(max_units_by_margin / size_increment) * size_increment
            if max_units_by_margin < min_units:
                logger.warning(
                    f"Insufficient margin for {instrument}: need ${margin_required:.2f}, "
                    f"available ${available_margin:.2f} (leverage {leverage}:1)"
                )
                return 0
            logger.info(
                f"Position size reduced by margin constraint: {units} -> {max_units_by_margin} "
                f"(margin ${margin_required:.2f} > available ${available_margin:.2f})"
            )
            units = max_units_by_margin

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
        strategy: str = "",
    ) -> bool:
        """
        Validate that the trade meets minimum R:R ratio.
        Strategy-specific minimums (from TradingLab mentoría):
        - BLACK -> settings.min_rr_black (2.0) — counter-trend, mandatory 2:1
        - GREEN -> settings.min_rr_green (2.0) — crypto swing, mandatory 2:1
        - BLUE_C -> 2.0 — mentoría says 2:1 min for Blue C
        - All others -> settings.min_rr_ratio (1.5) — general minimum
        Range: 1.5:1 to 2.5:1 per ch18.3.
        """
        if entry_price is None or stop_loss is None or take_profit_1 is None:
            return False

        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit_1 - entry_price)

        if risk == 0:
            return False

        # Determine strategy-specific minimum R:R
        strategy_upper = strategy.upper() if strategy else ""
        if strategy_upper == "BLACK":
            min_rr = settings.min_rr_black
        elif strategy_upper == "GREEN":
            min_rr = settings.min_rr_green
        elif strategy_upper == "BLUE_C":
            min_rr = 2.0  # Mentoría: Blue C requires 2:1 minimum
        else:
            min_rr = settings.min_rr_ratio

        rr_ratio = reward / risk
        # Use small epsilon for floating-point comparison to avoid rejecting
        # trades that are exactly at the minimum ratio (e.g., 2.0 computed as 1.9999...)
        if rr_ratio < min_rr - 1e-9:
            logger.warning(
                f"R:R ratio {rr_ratio:.2f} is below minimum {min_rr} "
                f"for strategy '{strategy_upper or 'DEFAULT'}'. Trade rejected."
            )
            return False

        logger.info(
            f"R:R ratio: {rr_ratio:.2f} (min: {min_rr}, "
            f"strategy: {strategy_upper or 'DEFAULT'})"
        )
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

    def unregister_all_trades(self):
        """Remove all active trades from risk tracking (e.g., funded overnight close)."""
        count = len(self._active_risks)
        self._active_risks.clear()
        self._positions_at_be.clear()
        logger.info(f"All {count} trades unregistered. Total risk: 0.00%")

    # ── Funded Account Mode (Workshop Cuentas Fondeadas) ────────

    def check_funded_account_limits(self) -> Tuple[bool, str]:
        """
        Check funded account drawdown limits.
        Returns (can_trade, reason).
        If funded mode is off, always returns (True, "").
        """
        if not settings.funded_account_mode:
            return (True, "")

        # Block trading if balance is zero or negative
        if self._current_balance <= 0:
            return (
                False,
                f"Funded: balance is ${self._current_balance:.2f} — cannot trade",
            )

        # Reset daily PnL tracker if the day changed
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._funded_daily_pnl_date != today:
            self._funded_daily_pnl = 0.0
            self._funded_daily_pnl_date = today
            # Snapshot start-of-day balance for accurate DD calculation
            self._funded_start_of_day_balance = self._current_balance

        # Use start-of-day balance for daily DD (most prop firms use this method)
        # Workshop: Instant Funding has NO daily DD limit — skip this check.
        # Guard: if sod_balance is 0 (balance not yet initialized), allow trading
        sod_balance = self._funded_start_of_day_balance or self._current_balance
        if sod_balance <= 0:
            return (True, "")  # Balance not yet initialized — don't block on stale data
        if settings.funded_evaluation_type != "instant" and sod_balance > 0:
            # Auto-apply correct DD limits based on evaluation type
            # Workshop: 1-phase/sprint = 4% daily / 6% total (tighter than 2-phase 5%/10%)
            if settings.funded_evaluation_type in ("1phase", "sprint"):
                effective_daily_dd = min(settings.funded_max_daily_dd, 0.04)
            else:
                effective_daily_dd = settings.funded_max_daily_dd
            daily_dd_limit = effective_daily_dd * sod_balance
            if self._funded_daily_pnl < 0 and abs(self._funded_daily_pnl) >= daily_dd_limit:
                return (
                    False,
                    f"Funded: daily DD limit reached "
                    f"({abs(self._funded_daily_pnl):.2f} >= {daily_dd_limit:.2f})",
                )

        # Check total DD: overall drawdown vs funded max total DD
        # Phase 2 may have a tighter DD limit (e.g. BitFunded: 10% → 8%)
        total_dd = self.get_current_drawdown()
        # Auto-apply correct total DD based on evaluation type
        if settings.funded_evaluation_type in ("1phase", "sprint"):
            effective_total_dd = min(settings.funded_max_total_dd, 0.06)
        else:
            effective_total_dd = settings.funded_max_total_dd
        if (settings.funded_current_phase == 2
                and getattr(settings, 'funded_max_total_dd_phase2', 0) > 0):
            effective_total_dd = settings.funded_max_total_dd_phase2
        if total_dd >= effective_total_dd:
            return (
                False,
                f"Funded: total DD limit reached "
                f"({total_dd:.2%} >= {effective_total_dd:.2%})",
            )

        # Enforce funded account restrictions (normal accounts only)
        now = datetime.now(timezone.utc)

        # News restriction: block new trades during news windows
        if getattr(settings, 'funded_no_news_trading', False):
            # Delegates to news_filter; caller must check externally
            pass  # handled by trading_engine's news check

        # Weekend restriction: block trades on Saturday/Sunday
        if getattr(settings, 'funded_no_weekend', False):
            if now.weekday() >= 5:  # Saturday=5, Sunday=6
                return (False, "Funded (normal): no weekend trading allowed")

        # Overnight restriction: block trades outside session hours (DST-adjusted)
        if getattr(settings, 'funded_no_overnight', False):
            offset = self._dst_offset(now)
            start = settings.trading_start_hour + offset
            end = settings.trading_end_hour + offset
            if now.hour < start or now.hour >= end:
                return (
                    False,
                    f"Funded (normal): no overnight trading "
                    f"(current hour {now.hour} UTC, session {start}-{end} UTC, DST offset={offset})",
                )

        return (True, "")

    @staticmethod
    def _dst_offset(now: datetime) -> int:
        """Return UTC hour offset for EST vs EDT (same logic as trading_engine)."""
        try:
            from zoneinfo import ZoneInfo
            et = now.astimezone(ZoneInfo("America/New_York"))
            return 0 if et.dst() else 1
        except Exception:
            return 0

    def record_funded_pnl(self, pnl_amount: float):
        """
        Accumulate daily P&L for funded account tracking.
        Called when a trade closes.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._funded_daily_pnl_date != today:
            self._funded_daily_pnl = 0.0
            self._funded_daily_pnl_date = today
            # Snapshot start-of-day balance — must match check_funded_account_limits
            self._funded_start_of_day_balance = self._current_balance

        self._funded_daily_pnl += pnl_amount
        logger.info(
            f"Funded PnL updated: {pnl_amount:+.2f} | "
            f"Daily total: {self._funded_daily_pnl:+.2f}"
        )

        # Check phase advancement on trade close (not on status read)
        if settings.funded_account_mode:
            profit_target = 0.0
            if settings.funded_current_phase == 1:
                profit_target = settings.funded_profit_target_phase1
            elif settings.funded_current_phase == 2:
                profit_target = settings.funded_profit_target_phase2
            if profit_target > 0 and self._funded_initial_balance > 0:
                current_profit_pct = (self._current_balance - self._funded_initial_balance) / self._funded_initial_balance
                profit_progress = (current_profit_pct / profit_target * 100) if profit_target > 0 else 0
                self._check_funded_phase_advancement(profit_target, profit_progress)

    def _check_funded_phase_advancement(self, profit_target: float, profit_progress: float) -> bool:
        """Check and apply funded account phase transitions.
        Called from record_funded_pnl (on trade close), NOT from get_funded_status."""
        if profit_target <= 0 or profit_progress < 100.0:
            return False
        if settings.funded_current_phase == 1:
            settings.funded_current_phase = 2
            logger.info(
                f"FUNDED ACCOUNT: Phase 1 profit target ({profit_target:.0%}) MET! "
                f"Auto-advancing to Phase 2."
            )
            return True
        elif settings.funded_current_phase == 2:
            settings.funded_current_phase = 3
            logger.info(
                f"FUNDED ACCOUNT: Phase 2 profit target ({profit_target:.0%}) MET! "
                f"Advancing to REAL ACCOUNT (Phase 3). Congratulations!"
            )
            return True
        return False

    def get_funded_status(self) -> Dict:
        """Get funded account status for API."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._funded_daily_pnl_date != today:
            daily_pnl = 0.0
        else:
            daily_pnl = self._funded_daily_pnl

        sod_balance = self._funded_start_of_day_balance or self._current_balance
        # Instant Funding has NO daily DD limit
        if settings.funded_evaluation_type == "instant":
            daily_dd_limit = 0.0  # No daily DD limit for Instant Funding
        else:
            daily_dd_limit = (
                settings.funded_max_daily_dd * sod_balance
                if sod_balance > 0 else 0.0
            )
        total_dd = self.get_current_drawdown()

        # Profit target tracking for evaluation phases
        profit_target = 0.0
        if settings.funded_current_phase == 1:
            profit_target = settings.funded_profit_target_phase1
        elif settings.funded_current_phase == 2:
            profit_target = settings.funded_profit_target_phase2

        # Calculate profit progress using tracked initial balance
        profit_progress = 0.0
        if self._funded_initial_balance > 0 and profit_target > 0:
            current_profit_pct = (self._current_balance - self._funded_initial_balance) / self._funded_initial_balance
            profit_progress = (current_profit_pct / profit_target * 100) if profit_target > 0 else 0

        # Phase advancement now happens in record_funded_pnl (on trade close),
        # not here — this method is read-only for the GET API endpoint.

        can_trade, reason = self.check_funded_account_limits()

        return {
            "enabled": settings.funded_account_mode,
            "account_type": settings.funded_account_type,
            "evaluation_type": settings.funded_evaluation_type,
            "current_phase": settings.funded_current_phase,
            "can_trade": can_trade,
            "blocked_reason": reason,
            "daily_pnl": round(daily_pnl, 2),
            "daily_dd_used_pct": round(
                (abs(daily_pnl) / daily_dd_limit * 100) if daily_dd_limit > 0 and daily_pnl < 0 else 0.0,
                2,
            ),
            "daily_dd_limit": round(settings.funded_max_daily_dd * 100, 2),
            "daily_dd_limit_amount": round(daily_dd_limit, 2),
            "start_of_day_balance": round(sod_balance, 2),
            "total_dd_pct": round(total_dd * 100, 2),
            "total_dd_limit": round(
                (settings.funded_max_total_dd_phase2
                 if settings.funded_current_phase == 2
                 and getattr(settings, 'funded_max_total_dd_phase2', 0) > 0
                 else settings.funded_max_total_dd) * 100, 2
            ),
            "profit_target_pct": round(profit_target * 100, 2),
            "profit_progress_pct": round(profit_progress, 2),
            "no_overnight": settings.funded_no_overnight,
            "no_news_trading": settings.funded_no_news_trading,
            "no_weekend": settings.funded_no_weekend,
            "phase_advanced": False,  # Phase advancement now happens on trade close, not status read
        }

    @staticmethod
    def calculate_recovery_pct(drawdown_pct: float) -> float:
        """Calculate % gain needed to recover from a drawdown.
        Alex's recovery math: loss of X% requires gain of X/(1-X/100) %.
        E.g., -10% needs +11.1%, -50% needs +100%.
        """
        if drawdown_pct <= 0:
            return 0.0
        dd_decimal = drawdown_pct / 100.0
        if dd_decimal >= 1.0:
            return float('inf')
        return round((dd_decimal / (1.0 - dd_decimal)) * 100, 2)

    # Standard recovery reference table from Alex's mentorship
    RECOVERY_TABLE = [
        (5, 5.26), (10, 11.11), (15, 17.65), (20, 25.0),
        (25, 33.33), (30, 42.86), (40, 66.67), (50, 100.0),
        (60, 150.0), (75, 300.0),
    ]

    # DD alert thresholds — warn the user at these levels
    DD_ALERT_THRESHOLDS = [5, 10, 15]

    def get_dd_alert_level(self) -> Optional[str]:
        """Return alert severity if DD exceeds thresholds, else None."""
        dd_pct = self.get_current_drawdown() * 100
        if dd_pct >= 15:
            return "critical"
        if dd_pct >= 10:
            return "high"
        if dd_pct >= 5:
            return "warning"
        return None

    def get_risk_status(self) -> Dict:
        """Get comprehensive risk status for API/frontend."""
        dd = self.get_current_drawdown()
        dd_pct = round(dd * 100, 2)
        base_day = settings.risk_day_trading
        adjusted_day = self.get_risk_for_style(TradingStyle.DAY_TRADING)

        wins = sum(1 for t in self._trade_history[-50:] if t.is_win)
        total = min(len(self._trade_history), 50)
        win_rate = wins / total if total > 0 else 0.0

        # Recovery math
        recovery_pct = self.calculate_recovery_pct(dd_pct)
        # Clamp inf (dd_pct >= 100% case) to a large but JSON-safe number
        import math
        if isinstance(recovery_pct, float) and (math.isinf(recovery_pct) or math.isnan(recovery_pct)):
            recovery_pct = 99999.0
        dd_alert = self.get_dd_alert_level()
        loss_dollars = round(self._peak_balance - self._current_balance, 2) if self._peak_balance > 0 else 0.0

        return {
            "current_drawdown": dd_pct,
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
            # Recovery math fields
            "recovery_pct_needed": recovery_pct,
            "loss_dollars": loss_dollars,
            "dd_alert_level": dd_alert,
            "recovery_table": self.RECOVERY_TABLE,
        }
