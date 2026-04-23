"""
Atlas - Position Manager
Manages open positions: SL movement, BE, trailing stops.

From TradingLab Mentorship - Position Management Styles (all based on EMA 50):

FOREX/EQUITIES/INDICES (Trading Mastery module):
  Style LP (Long-term) — PRIMARY timeframes:
    - Swing: trail with Daily EMA 50 (optional wider: Weekly)
    - Day Trading: trail with H1 EMA 50 (optional wider: H4)
    - Scalping: trail with M5 EMA 50 (per Workshop de Scalping)

  Style CP (Short-term) — PRIMARY timeframes:
    - Swing: trail with H1 EMA 50 (optional wider: H4)
    - Day Trading: trail with M5 EMA 50 (optional wider: M15)
    - Scalping: trail with M1 EMA 50

CRYPTO (Esp. Criptomonedas module — wider due to volatility):
  Style LP (Long-term) — PRIMARY timeframes:
    - Swing: trail with Weekly EMA 50
    - Day Trading: trail with H4 EMA 50
    - Scalping: trail with M15 EMA 50

  Style DAILY (Mid-term) — Daily EMA 50:
    - Swing: trail with Daily EMA 50
    - Day Trading: trail with H4 EMA 50 (fallback from Daily)
    - Scalping: trail with M15 EMA 50 (fallback from Daily)
    - Sits between LP (Weekly) and CP (H1) for crypto

  Style CP (Short-term) — PRIMARY timeframes:
    - Swing: trail with H1 EMA 50
    - Day Trading: trail with M15 EMA 50
    - Scalping: trail with M1 EMA 50

Style CPA (Short-term Aggressive) — same for all assets:
  - Swing: trail with M15 EMA 50
  - Day Trading: trail with M2 EMA 50 (M5 if M2 unavailable)
  - Scalping: trail with M1 EMA 50 (30s not available)
  - CPA is NOT standalone — only used combined with LP/CP at key levels

Hybrid approach (recommended):
  - Run LP or CP as base style
  - At key levels (previous highs, Fib extensions, major resistance), switch to CPA
  - Close partial position if CPA triggers exit, continue LP/CP with remaining

Partial profit taking: configurable via allow_partial_profits parameter.
The mentorship teaches partials as a valid option — especially for crypto
("formulas hibridas: 50% TP + 50% trail"). The CPA section explicitly
recommends partial closes at key levels. Default is False but can be enabled.

Give space to the EMA — buffer slightly below/above, never place SL exactly on it.
"""

from typing import Dict, Optional, List, Callable, Awaitable
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
    """TradingLab position management styles."""
    LP = "lp"              # Long-term: wider EMA timeframes, gives trades more room
    DAILY = "daily"        # Daily: crypto-specific mid-term — Daily EMA 50 trailing
    CP = "cp"              # Short-term: tighter EMA timeframes, locks profit sooner
    CPA = "cpa"            # Short-term Aggressive: tightest EMAs, only at key levels
    PRICE_ACTION = "price_action"  # Trail SL using previous swing highs/lows (alternative to EMA)


class TradingStyle(Enum):
    """Trading style determines which timeframe EMA 50 to use."""
    SCALPING = "scalping"
    DAY_TRADING = "day_trading"
    SWING = "swing"


# EMA 50 timeframe grid per management style and trading style
# Maps (ManagementStyle, TradingStyle) -> EMA key suffix for _latest_emas
# All values reference EMA 50 on the given timeframe
#
# FOREX/EQUITIES/INDICES — from Trading Mastery position management module
# Mentorship grid (4-timeframe box per style):
#   Swing:       Weekly -> Daily  -> H1   -> M15
#   Day Trading: H4     -> H1    -> M5   -> M2/M5
#   Scalping:    M15    -> M5    -> M1   -> 30s/M1
# LP = second box (PRIMARY), CP = third box, CPA = fourth box
_EMA_TIMEFRAME_GRID: Dict[tuple, str] = {
    # LP (Long-term): Swing=Daily, Day=H1, Scalp=M5
    # Workshop de Scalping, Gestión: "¿Cuál sería el largo plazo? El gráfico de cinco minutos."
    # Grid: Scalping M15->M5->M1->M1, LP = second box = M5
    (ManagementStyle.LP, TradingStyle.SWING): "EMA_D_50",
    (ManagementStyle.LP, TradingStyle.DAY_TRADING): "EMA_H1_50",
    (ManagementStyle.LP, TradingStyle.SCALPING): "EMA_M5_50",
    # DAILY (mid-term): Daily EMA 50 only appropriate for swing.
    # For day_trading and scalping, fall back to LP-equivalent timeframes
    # since Daily EMA 50 is too wide for intraday styles.
    (ManagementStyle.DAILY, TradingStyle.SWING): "EMA_D_50",
    (ManagementStyle.DAILY, TradingStyle.DAY_TRADING): "EMA_H1_50",
    (ManagementStyle.DAILY, TradingStyle.SCALPING): "EMA_M5_50",
    # CP (Short-term): Swing=H1, Day=M5 EMA 5 (PDF pg.5), Scalp=M1
    # Trading Plan PDF pg.5: "A partir de aquí usaré siempre las dos medias
    # móviles más cortas en cada estilo de trading para gestionar mis
    # posiciones (EMA2m y EMA5m para el Day trading)".
    # -> Trail principal post-BE para CP/day_trading = EMA 5 en M5.
    #    EMA 2 en M5 se consulta vía _get_aggressive_exit_ema_key() como
    #    señal de emergency exit (la más corta de las dos cortas).
    (ManagementStyle.CP, TradingStyle.SWING): "EMA_H1_50",
    (ManagementStyle.CP, TradingStyle.DAY_TRADING): "EMA_M5_5",
    (ManagementStyle.CP, TradingStyle.SCALPING): "EMA_M1_50",
    # CPA (Short-term Aggressive): Swing=M15, Day=M2, Scalp=M1
    # Alex: "el corto plazo agresivo son 2 minutos" for day trading
    (ManagementStyle.CPA, TradingStyle.SWING): "EMA_M15_50",
    # M2 EMAs derived from M1 data (Capital.com has no MINUTE_2 resolution)
    (ManagementStyle.CPA, TradingStyle.DAY_TRADING): "EMA_M2_50",
    (ManagementStyle.CPA, TradingStyle.SCALPING): "EMA_M1_50",
}

# AGGRESSIVE EXIT EMA grid — PDF pg.5: "las dos medias móviles más cortas".
# For day trading this means EMA 2 in M5 (the shorter of the two "dos más
# cortas" pair EMA 2 + EMA 5). Used in AGGRESSIVE/BEYOND_TP1 phase as the
# emergency-exit signal: a ruptura of EMA 2 closes the trade even if the
# trail EMA 5 is still intact.
# For styles where "dos más cortas" is not explicitly defined in the PDF
# we approximate by using the shortest structurally-shorter EMA available.
_AGGRESSIVE_EXIT_EMA_GRID: Dict[tuple, str] = {
    # Day trading (PDF pg.5 explicit): EMA 2 en M5
    (ManagementStyle.LP, TradingStyle.DAY_TRADING): "EMA_M5_2",
    (ManagementStyle.DAILY, TradingStyle.DAY_TRADING): "EMA_M5_2",
    (ManagementStyle.CP, TradingStyle.DAY_TRADING): "EMA_M5_2",
    (ManagementStyle.CPA, TradingStyle.DAY_TRADING): "EMA_M5_2",
    # Swing and scalping: fall back to CPA EMA (existing behaviour);
    # PDF doesn't specify an EMA 2 equivalent for these styles, so we keep
    # the legacy CPA EMA 50 as the aggressive-exit signal.
    (ManagementStyle.LP, TradingStyle.SWING): "EMA_M15_50",
    (ManagementStyle.CP, TradingStyle.SWING): "EMA_M15_50",
    (ManagementStyle.DAILY, TradingStyle.SWING): "EMA_M15_50",
    (ManagementStyle.CPA, TradingStyle.SWING): "EMA_M15_50",
    (ManagementStyle.LP, TradingStyle.SCALPING): "EMA_M1_50",
    (ManagementStyle.CP, TradingStyle.SCALPING): "EMA_M1_50",
    (ManagementStyle.DAILY, TradingStyle.SCALPING): "EMA_M1_50",
    (ManagementStyle.CPA, TradingStyle.SCALPING): "EMA_M1_50",
}


# CRYPTO — from Esp. Criptomonedas position management module
# Crypto uses wider timeframes due to higher volatility:
# Alex: "las criptomonedas son activos volátiles" — the "optional wider"
# timeframes from Trading Mastery become the PRIMARY for crypto.
# Only LP and CP differ; CPA is the same across all asset classes.
_EMA_TIMEFRAME_GRID_CRYPTO: Dict[tuple, str] = {
    # LP (Long-term): Swing=Weekly, Day=H4, Scalp=M15
    (ManagementStyle.LP, TradingStyle.SWING): "EMA_W_50",
    (ManagementStyle.LP, TradingStyle.DAY_TRADING): "EMA_H4_50",
    (ManagementStyle.LP, TradingStyle.SCALPING): "EMA_M15_50",
    # DAILY (mid-term crypto): Daily EMA 50 — between LP (Weekly) and CP (H1)
    # Mentorship: DAILY style is designed for swing trading; for day_trading and scalping
    # it falls back to more appropriate timeframes (H4 and M15 respectively) since
    # Daily EMA 50 is too wide for intraday styles.
    (ManagementStyle.DAILY, TradingStyle.SWING): "EMA_D_50",
    (ManagementStyle.DAILY, TradingStyle.DAY_TRADING): "EMA_H4_50",
    (ManagementStyle.DAILY, TradingStyle.SCALPING): "EMA_M15_50",
    # CP (Short-term): Swing=H1, Day=M15, Scalp=M1
    (ManagementStyle.CP, TradingStyle.SWING): "EMA_H1_50",
    (ManagementStyle.CP, TradingStyle.DAY_TRADING): "EMA_M15_50",
    (ManagementStyle.CP, TradingStyle.SCALPING): "EMA_M1_50",
    # CPA (Short-term Aggressive): SAME as forex — Swing=M15, Day=M2, Scalp=M1
    # Mentorship: "CPA is the same across all asset classes"
    (ManagementStyle.CPA, TradingStyle.SWING): "EMA_M15_50",
    (ManagementStyle.CPA, TradingStyle.DAY_TRADING): "EMA_M2_50",
    (ManagementStyle.CPA, TradingStyle.SCALPING): "EMA_M1_50",
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
    units: float = 0.0              # Position size (signed: +BUY, -SELL), float for crypto fractional lots
    style: str = "day_trading"     # Trading style: "day_trading", "swing", "scalping"
    strategy_variant: Optional[str] = None  # e.g. "GREEN", "BLUE_A", "RED" — for strategy-specific logic
    trailing_tp_only: bool = False  # True for crypto GREEN: skip hard TP1 close, use EMA 50 trailing
    htf_context: str = "pullback"  # "pullback" (quick exit via CP, target TP1) or "run" (extended target via LP, target TP_max)
    phase: PositionPhase = PositionPhase.INITIAL
    highest_price: float = 0.0    # For BUY: highest since entry
    lowest_price: float = float('inf')  # For SELL: lowest since entry
    cpa_temporary: bool = False   # True when CPA was triggered by key level proximity (can revert to LP/CP)
    cpa_revert_level: float = 0   # Key level that triggered temporary CPA; if price breaks through cleanly, revert
    pre_cpa_phase: Optional[str] = None  # Phase before CPA was triggered (for reverting)
    _half_risk_applied: bool = False  # Track 50% risk reduction step before BE
    # Iter-29 / Audit A4: the swing level that price must break through after BE
    # before trailing is activated. Captured when the position reaches BE and
    # pulled from `_latest_swings` (BUY: nearest swing high above entry;
    # SELL: nearest swing low below entry). None = no swing data at BE time
    # (legacy behaviour — trailing activates as soon as EMA is favorable).
    #
    # Mentorship "Trading Mastery Short Term":
    #   "ahí tenemos ya el 1%, break-even... a partir de aquí vamos a esperar
    #    y empezaremos a gestionar con la media móvil... Hasta que no se rompa,
    #    evidentemente, este máximo anterior, no vamos a utilizarla"
    swing_to_break: Optional[float] = None
    swing_broken: bool = False  # Latches True once price has broken swing_to_break
    # Idempotency guards: flipped True the moment this position enters any
    # close path (tick-driven or broker-sync-driven). Later tick/sync passes
    # check this before duplicating DB writes, journal entries, WS broadcasts,
    # and email alerts.
    _closing: bool = False
    _tp1_partial_done: bool = False  # Prevent repeat partial-close on retry ticks
    no_ema_ticks: int = 0            # Consecutive ticks missing EMA data (emergency threshold)


class PositionManager:
    """
    Manages all open positions according to TradingLab mentorship rules.

    5-phase structure:
      Phase 1 (INITIAL)    - Move SL to previous swing high/low (structural level)
      Phase 2 (SL_MOVED)   - Move to Break Even at 1% unrealized profit
      Phase 3 (BREAK_EVEN) - Transition to trailing once EMA 50 is favorable
      Phase 4 (TRAILING)   - Trail SL with EMA 50 on style-appropriate timeframe
      Phase 5 (AGGRESSIVE) - Beyond TP1, switch to CPA EMA for tighter trailing

    Management style (LP/CP) determines which EMA 50 timeframe is used in
    phases 4 and 5. At key levels, CPA is used for tighter trailing.
    """

    # Crypto detection uses the canonical function from strategies.base
    # which checks against settings.crypto_watchlist (100+ instruments)

    def __init__(
        self,
        broker_client,
        risk_manager=None,
        management_style: str = "cp",
        trading_style: str = "day_trading",
        allow_partial_profits: bool = False,
    ):
        self.broker = broker_client
        self.risk_manager = risk_manager
        self.positions: Dict[str, ManagedPosition] = {}
        # EMA values from last market analysis (injected by trading engine)
        self._latest_emas: Dict[str, Dict[str, float]] = {}
        # Swing high/low values for PRICE_ACTION trailing (injected by trading engine)
        self._latest_swings: Dict[str, Dict[str, List[float]]] = {}

        # Callback for trade close events (DB persistence + journal recording).
        # PositionManager doesn't own _db or trade_journal; TradingEngine registers
        # a handler so that TP_max and emergency-exit closes are persisted identically
        # to externally-detected closes.
        self._on_trade_closed: Optional[
            Callable[..., Awaitable[None]]
        ] = None

        # Callback for stop-loss change events (persists each move to the trades
        # row so the audit log can reconstruct the SL timeline). Without this
        # the journal `stop_loss` column kept the original SL forever, hiding
        # the truth that the JPM trade closed at a tightened SL not the entry SL.
        self._on_sl_changed: Optional[
            Callable[..., Awaitable[None]]
        ] = None

        # Partial profit taking: Alex doesn't use it but the mentorship
        # teaches it as optional and CPA recommends partial closes at key levels.
        self.allow_partial_profits = allow_partial_profits

        # Management style configuration
        self.management_style = ManagementStyle(management_style.lower())
        self.trading_style = TradingStyle(trading_style.lower())

        # Resolve default EMA keys from the forex grid (overridden per-instrument for crypto)
        if self.management_style == ManagementStyle.PRICE_ACTION:
            self._base_ema_key = None
            self._cpa_ema_key = _EMA_TIMEFRAME_GRID[
                (ManagementStyle.CPA, self.trading_style)
            ]
        else:
            self._base_ema_key = _EMA_TIMEFRAME_GRID[
                (self.management_style, self.trading_style)
            ]
            self._cpa_ema_key = _EMA_TIMEFRAME_GRID[
                (ManagementStyle.CPA, self.trading_style)
            ]

        # Crypto-specific EMA keys (wider timeframes due to volatility)
        if self.management_style == ManagementStyle.PRICE_ACTION:
            self._crypto_base_ema_key = None
            self._crypto_cpa_ema_key = _EMA_TIMEFRAME_GRID_CRYPTO[
                (ManagementStyle.CPA, self.trading_style)
            ]
        else:
            self._crypto_base_ema_key = _EMA_TIMEFRAME_GRID_CRYPTO[
                (self.management_style, self.trading_style)
            ]
            self._crypto_cpa_ema_key = _EMA_TIMEFRAME_GRID_CRYPTO[
                (ManagementStyle.CPA, self.trading_style)
            ]

        logger.info(
            f"PositionManager initialized: style={self.management_style.value}, "
            f"trading={self.trading_style.value}, "
            f"base_ema={self._base_ema_key}, cpa_ema={self._cpa_ema_key}, "
            f"crypto_base_ema={self._crypto_base_ema_key}, "
            f"crypto_cpa_ema={self._crypto_cpa_ema_key}, "
            f"partial_profits={self.allow_partial_profits}"
        )

    def set_on_sl_changed(
        self,
        callback: Callable[..., Awaitable[None]],
    ):
        """Register a callback fired after each successful broker SL update.

        Signature:
            async def on_sl_changed(
                trade_id: str, instrument: str, direction: str,
                old_sl: float, new_sl: float, phase: str,
            ) -> None
        """
        self._on_sl_changed = callback

    def set_on_trade_closed(
        self,
        callback: Callable[..., Awaitable[None]],
    ):
        """Register a callback invoked whenever PositionManager closes a trade.

        Signature expected by the callback:
            async def on_trade_closed(
                trade_id: str,
                instrument: str,
                direction: str,
                entry_price: float,
                exit_price: float,
                pnl_dollars: float,
                units: float,
                reason: str,
                strategy_variant: Optional[str] = None,
            ) -> None
        """
        self._on_trade_closed = callback

    async def _notify_trade_closed(
        self,
        pos: "ManagedPosition",
        exit_price: float,
        pnl_dollars: float,
        reason: str,
    ):
        """Fire the on_trade_closed callback if registered.

        Errors are logged as WARNING (CLAUDE.md Rule 6) but never propagate
        — a failed DB/journal write must not prevent position cleanup.

        Idempotency: once any path (tick-driven or sync-driven) has claimed
        this position for close, refuse to re-dispatch — prevents double DB
        updates, duplicate journal entries, duplicate WS/email alerts, and
        double record_trade_result (delta algorithm would double-credit).
        """
        if getattr(pos, "_closing", False):
            logger.debug(
                f"_notify_trade_closed suppressed for {pos.trade_id}: already closed by another path"
            )
            return
        pos._closing = True
        if self._on_trade_closed is None:
            return
        try:
            await self._on_trade_closed(
                trade_id=pos.trade_id,
                instrument=pos.instrument,
                direction=pos.direction,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                pnl_dollars=pnl_dollars,
                units=abs(pos.units) if pos.units else 0.0,
                reason=reason,
                strategy_variant=getattr(pos, "strategy_variant", None),
                style=getattr(pos, "style", None),
            )
        except TypeError:
            # Back-compat: callback may not accept `style` kwarg yet.
            await self._on_trade_closed(
                trade_id=pos.trade_id,
                instrument=pos.instrument,
                direction=pos.direction,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                pnl_dollars=pnl_dollars,
                units=abs(pos.units) if pos.units else 0.0,
                reason=reason,
                strategy_variant=getattr(pos, "strategy_variant", None),
            )
        except Exception as cb_err:
            logger.warning(
                f"on_trade_closed callback failed for {pos.trade_id}: {cb_err}"
            )

    def _is_crypto(self, instrument: str) -> bool:
        """Check if an instrument is a crypto pair.
        Uses the canonical _is_crypto_instrument from strategies.base
        which checks against settings.crypto_watchlist."""
        from strategies.base import _is_crypto_instrument
        return _is_crypto_instrument(instrument)

    def _get_base_ema_key(self, instrument: str) -> Optional[str]:
        """Get the base EMA key for trailing, using crypto-specific wider
        timeframes when the instrument is a crypto pair.

        Crypto uses wider EMA timeframes per Esp. Criptomonedas module:
        LP: Swing=Weekly (vs Daily), Day=H4 (vs H1)
        CP: Day=M15 (vs M5)
        """
        if self._is_crypto(instrument):
            return self._crypto_base_ema_key
        return self._base_ema_key

    def _get_cpa_ema_key(self, instrument: str) -> str:
        """Get the CPA EMA key, using crypto-specific grid when applicable."""
        if self._is_crypto(instrument):
            return self._crypto_cpa_ema_key
        return self._cpa_ema_key

    def _get_aggressive_exit_ema_key(self, instrument: str) -> str:
        """Get the AGGRESSIVE EXIT EMA key — the "shortest of the two shortest"
        EMA used to fire an emergency exit during the BEYOND_TP1/AGGRESSIVE phase.

        PDF pg.5 (Trading Plan): for Day Trading this is EMA 2 on M5. A break
        of this very-short EMA signals momentum loss and closes the trade
        even if the longer trail EMA 5 is still intact.

        Falls back to CPA EMA key when no explicit aggressive-exit mapping
        exists for the (management_style, trading_style) pair — preserving
        the legacy behaviour for styles the PDF doesn't address explicitly.
        """
        # Aggressive exit EMA is style-specific (not asset-specific). The
        # PDF rule "dos medias más cortas" is an intraday-structure rule
        # and applies regardless of whether the instrument is crypto or
        # forex, since the underlying timeframe (M5) is the same.
        key = _AGGRESSIVE_EXIT_EMA_GRID.get(
            (self.management_style, self.trading_style)
        )
        if key is not None:
            return key
        # Fallback for management styles not in the grid (e.g. PRICE_ACTION):
        # reuse the CPA EMA key for that asset.
        return self._get_cpa_ema_key(instrument)

    def set_cpa_trigger(self, trade_id: str, reason: str, temporary: bool = False, revert_level: float = 0):
        """Signal that CPA (aggressive trailing) should activate for a position.

        Called by trading_engine when it detects conditions that warrant
        switching to aggressive management mid-trade:
          - double top/bottom forming near position's TP
          - high-impact news approaching
          - Friday close approaching (weekend gap risk)
          - price indecision near key levels
          - price approaching key reference levels (temporary CPA)

        Alex: "en momentos donde estemos llegando a puntos determinantes,
        como soportes o resistencias, en momentos donde vayan a haber noticias,
        o en momentos donde vaya a finalizar la semana"

        Args:
            trade_id: The trade to switch to CPA
            reason: Human-readable reason for the trigger
            temporary: If True, CPA can revert to previous style if price breaks through
            revert_level: The key level; if price moves >1% past it, revert to previous style
        """
        pos = self.positions.get(trade_id)
        if pos is None:
            return

        # Only trigger CPA on positions in BE or trailing-to-TP1 phase
        # (INITIAL/SL_MOVED = too early, BEYOND_TP1 = already aggressive)
        if pos.phase not in (PositionPhase.BREAK_EVEN, PositionPhase.TRAILING_TO_TP1):
            reason_str = "already aggressive" if pos.phase == PositionPhase.BEYOND_TP1 else "too early"
            logger.debug(
                f"{trade_id}: CPA trigger '{reason}' ignored — phase {pos.phase.value} ({reason_str})"
            )
            return

        cpa_key = self._get_cpa_ema_key(pos.instrument)
        pos.pre_cpa_phase = pos.phase.value
        pos.phase = PositionPhase.BEYOND_TP1
        pos.cpa_temporary = temporary
        pos.cpa_revert_level = revert_level
        logger.info(
            f"{trade_id}: CPA AUTO-TRIGGER '{reason}' — switching to aggressive trailing "
            f"(CPA: {cpa_key}, temporary={temporary})"
        )

    def set_ema_values(self, instrument: str, emas: Dict[str, float]):
        """Update EMA values for an instrument (called by trading engine after analysis)."""
        self._latest_emas[instrument] = emas

    def set_swing_values(self, instrument: str, swing_highs: List[float], swing_lows: List[float]):
        """Update swing high/low values for PRICE_ACTION trailing.

        The mentorship teaches managing SL via previous swing highs/lows as an
        alternative to EMA trailing. After each completed pullback, the SL is
        moved to the most recent swing high (for SELL) or swing low (for BUY).

        Args:
            instrument: The trading instrument
            swing_highs: Recent swing high prices (most recent first)
            swing_lows: Recent swing low prices (most recent first)
        """
        self._latest_swings[instrument] = {
            "highs": swing_highs,
            "lows": swing_lows,
        }

    def _get_trail_ema(self, instrument: str, ema_key: str) -> Optional[float]:
        """
        Look up an EMA value for an instrument.
        Returns None if the requested EMA is not available — callers handle
        this with percentage-based fallback trailing which is well-calibrated
        per phase (40% normal, 20% aggressive).

        NOTE: Previously had a static fallback chain (H4→H1→M15→M5) that was
        style-blind — e.g. CPA scalping requesting M1 would fall back to H4,
        defeating tight trailing.  Removed: returning None is safer than
        returning an EMA from a drastically different timeframe.
        """
        emas = self._latest_emas.get(instrument, {})
        return emas.get(ema_key)

    def _ema_buffer(self, pos: ManagedPosition, aggressive: bool = False) -> float:
        """
        Calculate buffer distance to give space to the EMA.
        The SL should NOT sit exactly on the EMA — give it room to breathe.
        Aggressive phase uses a smaller buffer.
        """
        trade_range = abs(pos.take_profit_1 - pos.entry_price)
        if aggressive:
            return trade_range * 0.01  # 1% of trade range for CPA / beyond-TP1
        else:
            return trade_range * 0.02  # 2% of trade range for base trailing

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
            if price_data is None:
                logger.warning(f"{trade_id}: price_data is None for {pos.instrument} — skipping update")
                continue

            current_price = (
                price_data.ask if pos.direction == "SELL"
                else price_data.bid
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
        Trading Plan: "Pondré el SL por encima o debajo del máximo o mínimo anterior"
        Move SL to the nearest previous swing low (BUY) or swing high (SELL)
        that sits between the original SL and entry price — i.e. the structural
        level that price has just broken out of.

        Trigger: profit exceeds 30% of initial risk distance (conservative proxy
        for "price leaving the pattern structure").

        Fallback: if no swing data is available, reduce risk by 50% of the
        original SL-to-entry distance (legacy behaviour).
        """
        if pos.entry_price == 0:
            logger.error(f"{pos.trade_id}: entry_price is 0 — skipping initial phase to avoid bogus transition")
            return
        risk_distance = abs(pos.entry_price - pos.original_sl)
        current_profit = (
            (current_price - pos.entry_price) if pos.direction == "BUY"
            else (pos.entry_price - current_price)
        )

        # When price has moved ~30% of risk distance, move SL to structure
        if current_profit > risk_distance * 0.30:
            new_sl = None
            swings = self._latest_swings.get(pos.instrument, {})

            if pos.direction == "BUY":
                # Look for the nearest swing low between original SL and entry
                swing_lows = swings.get("lows", [])
                valid = [
                    sl for sl in swing_lows
                    if pos.original_sl < sl < pos.entry_price
                ]
                if valid:
                    # Pick the highest valid swing low (closest to entry = least risk)
                    new_sl = max(valid)
                    logger.debug(
                        f"{pos.trade_id}: structural SL from swing low {new_sl:.5f}"
                    )
            else:
                # SELL: look for the nearest swing high between entry and original SL
                swing_highs = swings.get("highs", [])
                valid = [
                    sh for sh in swing_highs
                    if pos.entry_price < sh < pos.original_sl
                ]
                if valid:
                    # Pick the lowest valid swing high (closest to entry = least risk)
                    new_sl = min(valid)
                    logger.debug(
                        f"{pos.trade_id}: structural SL from swing high {new_sl:.5f}"
                    )

            # Fallback: no usable swing data — cut risk by 50%
            if new_sl is None:
                if pos.direction == "BUY":
                    new_sl = pos.original_sl + (pos.entry_price - pos.original_sl) * 0.5
                else:
                    new_sl = pos.original_sl - (pos.original_sl - pos.entry_price) * 0.5
                logger.debug(
                    f"{pos.trade_id}: no swing data, fallback 50% risk cut -> {new_sl:.5f}"
                )

            if await self._update_sl(pos, new_sl):
                pos.phase = PositionPhase.SL_MOVED
                logger.info(f"{pos.trade_id}: Phase -> SL_MOVED ({new_sl:.5f})")

    async def _handle_sl_moved_phase(self, pos: ManagedPosition, current_price: float):
        """
        Phase 2: Move to Break Even.

        Two trigger methods (configured via be_trigger_method):
          "risk_distance" (Alex's preference): BE when profit >= 1x initial risk distance
            Alex: "cuando ya tengo un 1% de ganancia, pongo el break-even"
            For 1% risk this means BE at 1% profit — the R:R 1:1 point.
          "pct_to_tp1": BE at a percentage of distance to TP1
            Trading Plan PDF: "Cuando estemos por la mitad del beneficio hasta el TP1, pondré el BE"

        For a standard 2:1 R:R trade at 1% risk, both methods coincide.
        """
        from config import settings
        distance_to_tp1 = abs(pos.take_profit_1 - pos.entry_price)
        risk_distance = abs(pos.entry_price - pos.original_sl)
        current_profit = (
            (current_price - pos.entry_price) if pos.direction == "BUY"
            else (pos.entry_price - current_price)
        )

        # Intermediate step: at 50% of BE threshold, reduce risk by 50%
        # Mentorship transcription: "antes del break-even, al 50% de beneficio, muevo el SL
        # para eliminar el 50% del riesgo" — progressive risk reduction before full BE.
        # NOTE: Mentorship says this should trigger when "price exits the structure"
        # (structural event). Current implementation uses 50% of BE distance as a proxy.
        # A structural trigger would require pattern boundary detection, which is complex.
        # The profit-based proxy is a reasonable approximation for automated trading.
        half_be_profit = risk_distance * 0.5
        if current_profit >= half_be_profit and not getattr(pos, '_half_risk_applied', False):
            # Move SL to reduce 50% of remaining risk
            if pos.direction == "BUY":
                half_sl = pos.current_sl + (pos.entry_price - pos.current_sl) * 0.5
                if half_sl > pos.current_sl:
                    if await self._update_sl(pos, half_sl):
                        pos._half_risk_applied = True
                        logger.info(f"{pos.trade_id}: 50% risk reduction -> SL {half_sl:.5f}")
            else:
                half_sl = pos.current_sl - (pos.current_sl - pos.entry_price) * 0.5
                if half_sl < pos.current_sl:
                    if await self._update_sl(pos, half_sl):
                        pos._half_risk_applied = True
                        logger.info(f"{pos.trade_id}: 50% risk reduction -> SL {half_sl:.5f}")

        # Calculate BE threshold based on configured method
        if settings.be_trigger_method == "risk_distance":
            # Alex's rule: BE when unrealized profit >= 1x risk distance (e.g., 1% profit at 1% risk)
            be_threshold = risk_distance
        else:
            # Trading Plan PDF rule: BE at X% of distance to TP1
            be_threshold = distance_to_tp1 * settings.move_sl_to_be_pct_to_tp1
        if be_threshold <= 0:
            logger.warning(f"{pos.trade_id}: be_threshold is {be_threshold}, skipping BE transition")
            return
        if current_profit >= be_threshold:
            # BE = entry price (+ small buffer for spread)
            spread_buffer = abs(pos.entry_price - pos.original_sl) * 0.02
            if pos.direction == "BUY":
                new_sl = pos.entry_price + spread_buffer
            else:
                new_sl = pos.entry_price - spread_buffer

            if await self._update_sl(pos, new_sl):
                pos.phase = PositionPhase.BREAK_EVEN
                # Iter-29 / Audit A4: capture the swing high/low that price
                # must break through before trailing is activated. Once BE
                # fires, `swing_to_break` is frozen for the life of the trade.
                # If no swing data is available at this moment we leave it as
                # None and the legacy EMA-favorable gate will take over.
                if pos.swing_to_break is None:
                    pos.swing_to_break = self._pick_swing_to_break(
                        pos, current_price
                    )
                if pos.swing_to_break is not None:
                    logger.info(
                        f"{pos.trade_id}: Phase -> BREAK_EVEN — "
                        f"awaiting swing break at {pos.swing_to_break:.5f}"
                    )
                else:
                    logger.info(
                        f"{pos.trade_id}: Phase -> BREAK_EVEN "
                        f"(no swing data — legacy EMA-favorable trailing gate)"
                    )
                # Notify risk manager for scale-in rule
                if self.risk_manager is not None:
                    self.risk_manager.mark_position_at_be(pos.trade_id)

    def _pick_swing_to_break(
        self,
        pos: ManagedPosition,
        current_price: float,
    ) -> Optional[float]:
        """Pick the swing high/low that price must break before trailing starts.

        Mentorship (Trading Mastery Short Term): after BE, we wait for price
        to take out the previous swing high (BUY) or swing low (SELL) before
        switching to EMA trailing.

        For BUY: the NEAREST swing high that still sits ABOVE current_price
        (i.e. the next resistance level to be taken out).
        For SELL: the NEAREST swing low that still sits BELOW current_price.

        Returns None if no swing data is available.
        """
        swings = self._latest_swings.get(pos.instrument, {})
        if not swings:
            return None

        if pos.direction == "BUY":
            highs = [sh for sh in swings.get("highs", []) if sh > current_price]
            if not highs:
                return None
            # Nearest above = lowest of the highs above current_price
            return min(highs)

        # SELL
        lows = [sl for sl in swings.get("lows", []) if sl < current_price]
        if not lows:
            return None
        # Nearest below = highest of the lows below current_price
        return max(lows)

    def _swing_break_confirmed(
        self,
        pos: ManagedPosition,
        current_price: float,
    ) -> bool:
        """Return True if the swing that was awaited at BE has been broken.

        Once confirmed, latches `pos.swing_broken = True` so subsequent ticks
        don't re-evaluate (and don't lose the condition if the swing level is
        re-tested later).
        """
        if pos.swing_broken:
            return True
        if pos.swing_to_break is None:
            # No swing data was recorded at BE — fall back to legacy EMA gate.
            return False
        if pos.direction == "BUY":
            broken = current_price > pos.swing_to_break
        else:
            broken = current_price < pos.swing_to_break
        if broken:
            pos.swing_broken = True
            logger.info(
                f"{pos.trade_id}: swing broken at {current_price:.5f} "
                f"(level={pos.swing_to_break:.5f}) — trailing gate opens"
            )
        return broken

    async def _handle_be_phase(self, pos: ManagedPosition, current_price: float):
        """
        Phase 3: After BE, transition to EMA trailing.
        Trading Plan PDF: "A partir de aqui usaré siempre las dos medias móviles más cortas"

        Iter-29 / Audit A4 — Trading Mastery Short Term says trailing does
        NOT activate immediately at BE; we must first wait for price to
        break the previous swing high (BUY) or swing low (SELL):
          "Hasta que no se rompa, evidentemente, este máximo anterior,
           no vamos a utilizarla"

        Gate ordering:
          1. If `swing_to_break` was captured at BE time, require price to
             break it before transitioning to trailing (primary gate).
          2. If no swing data exists, fall back to the legacy EMA-favorable
             gate (prevents the position from getting stuck in BE when
             upstream swing data is unavailable).
        """
        base_key = self._get_base_ema_key(pos.instrument)

        # For PRICE_ACTION style there is no base EMA — but we STILL honour
        # the swing-break gate if present (the mentorship rule is style-
        # independent). If no swing data, transition immediately as before.
        if base_key is None:
            if pos.swing_to_break is not None and not self._swing_break_confirmed(
                pos, current_price
            ):
                return  # still waiting for swing break
            pos.phase = PositionPhase.TRAILING_TO_TP1
            logger.info(
                f"{pos.trade_id}: Phase -> TRAILING_TO_TP1 "
                f"(style={self.management_style.value}, ema=PRICE_ACTION)"
            )
            return

        # Primary gate (PDF / Short Term mentorship): swing must break first.
        if pos.swing_to_break is not None:
            if not self._swing_break_confirmed(pos, current_price):
                return  # hold in BE until swing taken out

        ema_value = self._get_trail_ema(pos.instrument, base_key)

        if ema_value is None:
            # No EMA data available — transition immediately (don't block trailing
            # just because EMA hasn't been calculated yet; price is already at BE+)
            pos.phase = PositionPhase.TRAILING_TO_TP1
            logger.info(
                f"{pos.trade_id}: Phase -> TRAILING_TO_TP1 "
                f"(style={self.management_style.value}, ema={base_key}, "
                f"ema_value=N/A — no data, transitioning immediately)"
            )
            return

        # EMA 50 must be favorable: acting as support (BUY) or resistance (SELL)
        # Check against CURRENT price, not entry: a BUY with EMA between entry
        # and current_price means EMA is acting as support — that's favorable.
        # Using entry_price caused positions to get stuck in BE when the EMA
        # naturally rose above entry in a profitable BUY trade.
        ema_favorable = (
            (ema_value >= current_price) if pos.direction == "SELL"
            else (ema_value <= current_price)
        )
        if ema_favorable:
            pos.phase = PositionPhase.TRAILING_TO_TP1
            logger.info(
                f"{pos.trade_id}: Phase -> TRAILING_TO_TP1 "
                f"(style={self.management_style.value}, ema={base_key}, "
                f"ema_value={ema_value:.5f})"
            )

    async def _handle_trailing_phase(self, pos: ManagedPosition, current_price: float):
        """
        Phase 4: Trail SL using EMA 50 or swing highs/lows depending on
        the configured management style (LP/CP or PRICE_ACTION).

        EMA styles: EMA 50 acts as dynamic support/resistance.
        PRICE_ACTION: SL trails behind previous swing highs (SELL) or
        swing lows (BUY) after each completed pullback.

        Partial profits: if allow_partial_profits is True, partial position
        can be closed at TP1. Otherwise trail full position.
        Give space to the EMA — buffer below/above, never exactly on it.
        """
        # HTF context determines TP target and management style:
        # "run" (daily reversal pattern like H&S, double top): use LP, target TP_max
        # "pullback" (simple pullback): use CP (default), target TP1
        if pos.htf_context == "run" and pos.take_profit_max:
            tp_target = pos.take_profit_max
        else:
            tp_target = pos.take_profit_1

        # Check if TP target has been reached -> switch to aggressive (CPA) trailing
        tp1_reached = (
            (pos.direction == "BUY" and current_price >= tp_target) or
            (pos.direction == "SELL" and current_price <= tp_target)
        )
        if tp1_reached:
            # GREEN/crypto trailing_tp_only: Do NOT hard-close at TP1.
            # Mentorship: crypto uses EMA 50 trailing on weekly chart, NOT fixed TPs.
            # TP1 is a reference level only — continue trailing with EMA 50.
            if pos.trailing_tp_only:
                logger.info(
                    f"{pos.trade_id}: TP1 level reached but trailing_tp_only=True "
                    f"(GREEN/crypto) — skipping hard close, continuing EMA 50 trailing. "
                    f"TP1={pos.take_profit_1:.5f}, price={current_price:.5f}"
                )
                # Do NOT switch to CPA or close — just continue trailing in this phase.
                # The position will only exit via trailing SL hit (EMA 50 break).
                # Fall through to the normal trailing logic below.
            else:
                # Standard behavior: partial profit at TP1 + switch to aggressive trailing.
                # Idempotency guard: if the partial for this TP1 already fired on
                # an earlier tick (or a retry), DO NOT partial again — would
                # close 50% of the remainder each tick.
                if (
                    self.allow_partial_profits
                    and pos.units != 0
                    and not getattr(pos, "_tp1_partial_done", False)
                ):
                    partial_units = pos.units / 2  # Close half (use true division for crypto fractional units)
                    if partial_units != 0:
                        try:
                            ok = await self.broker.close_trade_partial(pos.trade_id, percent=50)
                            if ok:
                                pos.units -= partial_units
                                pos._tp1_partial_done = True
                                # Rule #4: record partial close PnL for delta/reentry tracking
                                if self.risk_manager:
                                    pnl_per_unit = (current_price - pos.entry_price) if pos.direction == "BUY" else (pos.entry_price - current_price)
                                    partial_pnl = pnl_per_unit * abs(partial_units)
                                    balance = getattr(self.risk_manager, '_current_balance', 1.0) or 1.0
                                    self.risk_manager.record_trade_result(
                                        f"{pos.trade_id}_partial", pos.instrument, partial_pnl / balance
                                    )
                                logger.info(
                                    f"{pos.trade_id}: PARTIAL PROFIT at TP1 — closed ~50%, "
                                    f"remaining {pos.units} units"
                                )
                            else:
                                # Broker doesn't support partial (or rejected it).
                                # Hold position, do NOT transition to aggressive —
                                # otherwise we'd switch to tight CPA trailing on
                                # the full size, which is not what partial_profits
                                # users intend.
                                logger.warning(
                                    f"{pos.trade_id}: Partial close returned False — "
                                    f"holding full size, NOT transitioning to AGGRESSIVE"
                                )
                                return
                        except Exception as e:
                            logger.error(f"{pos.trade_id}: Failed partial close at TP1: {e}")
                            return

                cpa_key = self._get_cpa_ema_key(pos.instrument)
                pos.phase = PositionPhase.BEYOND_TP1
                logger.info(
                    f"{pos.trade_id}: TP1 REACHED -> Phase AGGRESSIVE "
                    f"(switching to CPA: {cpa_key})"
                )
                return

        # PRICE_ACTION style: trail with swing highs/lows
        if self.management_style == ManagementStyle.PRICE_ACTION:
            await self._trail_with_price_action(pos, current_price)
            return

        # EMA-based styles (LP/CP): get the EMA 50 value
        # Use crypto-specific wider timeframes for crypto instruments
        # HTF context "run" overrides to LP EMA for wider trailing (more room)
        if pos.htf_context == "run" and self.management_style != ManagementStyle.PRICE_ACTION:
            is_crypto = self._is_crypto(pos.instrument)
            grid = _EMA_TIMEFRAME_GRID_CRYPTO if is_crypto else _EMA_TIMEFRAME_GRID
            base_key = grid.get(
                (ManagementStyle.LP, self.trading_style),
                self._get_base_ema_key(pos.instrument),
            )
        else:
            base_key = self._get_base_ema_key(pos.instrument)
        trail_ema = self._get_trail_ema(pos.instrument, base_key)

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
                        f"({self.management_style.value} {base_key}={trail_ema:.5f})"
                    )
            else:
                new_sl = trail_ema + buffer
                # Only move SL down, never up
                if new_sl < pos.current_sl:
                    await self._update_sl(pos, new_sl)
                    logger.debug(
                        f"{pos.trade_id}: Trailing SL -> {new_sl:.5f} "
                        f"({self.management_style.value} {base_key}={trail_ema:.5f})"
                    )
        else:
            # Fallback: trail with percentage if no EMA data available
            await self._trail_with_percentage(pos, current_price, trail_pct=0.4)

    async def _handle_aggressive_phase(self, pos: ManagedPosition, current_price: float):
        """
        Phase 5: Beyond TP1 — switch to CPA (Short-term Aggressive) trailing.

        Uses the CPA EMA 50 timeframe for tighter trailing to maximize profit.
        Position closes at TP_max or via trailing SL hit.

        If CPA was triggered temporarily (key level proximity), revert to previous
        management style once price breaks cleanly through the key level (>1% beyond).
        Alex: "if price breaks through cleanly, remove CPA and continue with long-term."
        """
        # Revert temporary CPA if price has broken cleanly past the key level
        if pos.cpa_temporary and pos.cpa_revert_level > 0:
            if pos.direction == "BUY":
                # For BUY: price breaking above the key level means it cleared resistance
                beyond = current_price > pos.cpa_revert_level * 1.01
            else:
                # For SELL: price breaking below the key level means it cleared support
                beyond = current_price < pos.cpa_revert_level * 0.99

            if beyond:
                # Revert to previous phase (TRAILING or BREAK_EVEN)
                prev_phase = pos.pre_cpa_phase or PositionPhase.TRAILING_TO_TP1.value
                pos.phase = PositionPhase(prev_phase)
                pos.cpa_temporary = False
                pos.cpa_revert_level = 0
                pos.pre_cpa_phase = None
                logger.info(
                    f"{pos.trade_id}: CPA REVERTED — price broke cleanly past key level "
                    f"(price={current_price:.5f}). Returning to {pos.phase.value} management."
                )
                return  # Let the next update cycle handle with the restored phase

        # Check if TP_max has been reached -> close full position
        if pos.take_profit_max:
            tp_max_reached = (
                (pos.direction == "BUY" and current_price >= pos.take_profit_max) or
                (pos.direction == "SELL" and current_price <= pos.take_profit_max)
            )
            if tp_max_reached:
                try:
                    ok = await self.broker.close_trade(pos.trade_id)
                    if not ok:
                        logger.error(f"{pos.trade_id}: broker.close_trade returned False at TP_max — position remains tracked")
                        return
                    pnl_per_unit = (current_price - pos.entry_price) if pos.direction == "BUY" else (pos.entry_price - current_price)
                    pnl = pnl_per_unit * abs(pos.units) if pos.units else 0.0
                    logger.info(
                        f"{pos.trade_id}: TP_MAX REACHED ({pos.take_profit_max:.5f}) — "
                        f"CLOSED at {current_price:.5f} | PnL=${pnl:.2f}"
                    )
                    if self.risk_manager:
                        self.risk_manager.unregister_trade(pos.trade_id, pos.instrument)
                        balance = getattr(self.risk_manager, '_current_balance', 1.0) or 1.0
                        self.risk_manager.record_trade_result(pos.trade_id, pos.instrument, pnl / balance)
                    # Persist to DB + trade journal via callback
                    await self._notify_trade_closed(pos, current_price, pnl, "tp_max")
                    self.remove_position(pos.trade_id)
                    return
                except Exception as e:
                    logger.error(f"{pos.trade_id}: Failed to close at TP_max: {e}")

        # Resolve CPA EMA key based on instrument type (crypto uses different grid)
        cpa_key = self._get_cpa_ema_key(pos.instrument)

        # Emergency exit — PDF pg.5 rule: "dos medias móviles más cortas".
        # For day trading this means EMA 2 + EMA 5 on M5. The SHORTEST of the
        # pair (EMA_M5_2 via _get_aggressive_exit_ema_key) is the primary
        # emergency-exit signal: a clean break of the 2-period EMA against
        # the position closes immediately. The 5-period EMA is the trail and
        # is also checked as a confirmation — if both are broken, exit too.
        aggressive_exit_key = self._get_aggressive_exit_ema_key(pos.instrument)
        ema_aggressive_exit = self._get_trail_ema(pos.instrument, aggressive_exit_key)
        ema_m5_2 = self._get_trail_ema(pos.instrument, "EMA_M5_2")
        ema_m5_5 = self._get_trail_ema(pos.instrument, "EMA_M5_5")

        if ema_m5_2 is not None and ema_m5_5 is not None:
            # EMA data is present — reset the no-EMA tick counter.
            if hasattr(pos, "no_ema_ticks") and pos.no_ema_ticks:
                pos.no_ema_ticks = 0
            if pos.direction == "BUY":
                both_broken = current_price < ema_m5_2 and current_price < ema_m5_5
            else:
                both_broken = current_price > ema_m5_2 and current_price > ema_m5_5

            # Primary PDF-pg.5 signal: break of the shortest EMA (EMA_M5_2 for
            # day trading) alone is enough to close.
            aggressive_broken = False
            if ema_aggressive_exit is not None:
                if pos.direction == "BUY":
                    aggressive_broken = current_price < ema_aggressive_exit
                else:
                    aggressive_broken = current_price > ema_aggressive_exit

            if both_broken or aggressive_broken:
                try:
                    ok = await self.broker.close_trade(pos.trade_id)
                    if not ok:
                        logger.error(f"{pos.trade_id}: broker.close_trade returned False at emergency exit — position remains tracked")
                        return
                    pnl_per_unit = (current_price - pos.entry_price) if pos.direction == "BUY" else (pos.entry_price - current_price)
                    pnl = pnl_per_unit * abs(pos.units) if pos.units else 0.0
                    reason_detail = (
                        "both EMA M5 2 and EMA M5 5 broken" if both_broken
                        else f"shortest EMA {aggressive_exit_key} broken (PDF pg.5)"
                    )
                    logger.warning(
                        f"{pos.trade_id}: EMERGENCY EXIT — {reason_detail} "
                        f"against {pos.direction} at {current_price:.5f} | PnL=${pnl:.2f}"
                    )
                    if self.risk_manager:
                        self.risk_manager.unregister_trade(pos.trade_id, pos.instrument)
                        balance = getattr(self.risk_manager, '_current_balance', 1.0) or 1.0
                        self.risk_manager.record_trade_result(pos.trade_id, pos.instrument, pnl / balance)
                    # Persist to DB + trade journal via callback
                    await self._notify_trade_closed(pos, current_price, pnl, "emergency_exit")
                    self.remove_position(pos.trade_id)
                    return
                except Exception as e:
                    logger.error(f"{pos.trade_id}: Failed emergency exit: {e}")
        else:
            # Proxy: use CPA EMA as a rough substitute for the M5 short EMAs
            proxy_ema = self._get_trail_ema(pos.instrument, cpa_key)
            if proxy_ema is not None:
                if pos.direction == "BUY":
                    proxy_broken = current_price < proxy_ema
                else:
                    proxy_broken = current_price > proxy_ema

                if proxy_broken:
                    logger.warning(
                        f"{pos.trade_id}: AGGRESSIVE phase — CPA EMA proxy broken against "
                        f"{pos.direction} (price={current_price:.5f}, CPA={proxy_ema:.5f}). "
                        f"Consider closing. (Limitation: EMA_M5_2/EMA_M5_5 not available)"
                    )
            else:
                # A transient feed gap (one missed scan tick) must NOT flat-close
                # a profitable trade. The position still has its current_sl at
                # the broker. Only escalate to emergency close after N consecutive
                # scan ticks with no EMA data, so a brief outage doesn't panic-
                # exit the trade. The stop loss still guards the downside.
                pos.no_ema_ticks = getattr(pos, "no_ema_ticks", 0) + 1
                threshold = int(getattr(self, "_emergency_no_ema_ticks", 5))
                if pos.no_ema_ticks < threshold:
                    logger.warning(
                        f"{pos.trade_id}: AGGRESSIVE phase — no EMA data for {pos.instrument} "
                        f"(tick {pos.no_ema_ticks}/{threshold}); holding existing SL, skipping trail update."
                    )
                    return
                logger.error(
                    f"{pos.trade_id}: EMERGENCY — no EMA data for {pos.instrument} "
                    f"on {pos.no_ema_ticks} consecutive ticks. Closing as safety measure."
                )
                try:
                    ok = await self.broker.close_trade(pos.trade_id)
                    if not ok:
                        logger.error(f"{pos.trade_id}: broker.close_trade returned False at emergency_no_ema — position remains tracked")
                        return
                    pnl_per_unit = (current_price - pos.entry_price) if pos.direction == "BUY" else (pos.entry_price - current_price)
                    pnl = pnl_per_unit * abs(pos.units) if pos.units else 0.0
                    if self.risk_manager:
                        self.risk_manager.unregister_trade(pos.trade_id, pos.instrument)
                        balance = getattr(self.risk_manager, '_current_balance', 1.0) or 1.0
                        self.risk_manager.record_trade_result(pos.trade_id, pos.instrument, pnl / balance)
                    await self._notify_trade_closed(pos, current_price, pnl, "emergency_no_ema")
                    self.remove_position(pos.trade_id)
                    return
                except Exception as e:
                    logger.error(f"{pos.trade_id}: Failed emergency_no_ema exit: {e}")

        # Use CPA EMA 50 for aggressive trailing beyond TP1
        aggressive_ema = self._get_trail_ema(pos.instrument, cpa_key)

        if aggressive_ema is not None:
            # Tighter buffer in aggressive phase, but still give EMA some space
            buffer = self._ema_buffer(pos, aggressive=True)

            if pos.direction == "BUY":
                new_sl = aggressive_ema - buffer
                if new_sl > pos.current_sl:
                    await self._update_sl(pos, new_sl)
                    logger.debug(
                        f"{pos.trade_id}: AGGRESSIVE trail SL -> {new_sl:.5f} "
                        f"(CPA {cpa_key}={aggressive_ema:.5f})"
                    )
            else:
                new_sl = aggressive_ema + buffer
                if new_sl < pos.current_sl:
                    await self._update_sl(pos, new_sl)
                    logger.debug(
                        f"{pos.trade_id}: AGGRESSIVE trail SL -> {new_sl:.5f} "
                        f"(CPA {cpa_key}={aggressive_ema:.5f})"
                    )
        else:
            # Fallback: tight percentage trail
            await self._trail_with_percentage(pos, current_price, trail_pct=0.2)

    async def _trail_with_price_action(self, pos: ManagedPosition, current_price: float):
        """Trail SL using previous swing highs/lows (PRICE_ACTION style).

        The mentorship teaches this as an alternative to EMA trailing:
        after each completed pullback, move SL to the most recent swing
        high (for SELL positions) or swing low (for BUY positions).

        This method is more subjective than EMA trailing but can give
        trades more room in strongly trending markets with deep pullbacks.
        """
        swings = self._latest_swings.get(pos.instrument, {})
        if not swings:
            # Fallback to percentage trailing if no swing data
            await self._trail_with_percentage(pos, current_price, trail_pct=0.4)
            return

        buffer = self._ema_buffer(pos, aggressive=False)

        if pos.direction == "BUY":
            swing_lows = swings.get("lows", [])
            if swing_lows:
                # Use the most recent swing low that is below current price
                valid_lows = [sl for sl in swing_lows if sl < current_price]
                if valid_lows:
                    new_sl = valid_lows[-1] - buffer  # Most recent swing low minus buffer (BUG-04 fix)
                    if new_sl > pos.current_sl:
                        await self._update_sl(pos, new_sl)
                        logger.debug(
                            f"{pos.trade_id}: PRICE_ACTION trail SL -> {new_sl:.5f} "
                            f"(swing low={valid_lows[-1]:.5f})"
                        )
        else:  # SELL
            swing_highs = swings.get("highs", [])
            if swing_highs:
                # Use the most recent swing high that is above current price
                valid_highs = [sh for sh in swing_highs if sh > current_price]
                if valid_highs:
                    new_sl = valid_highs[-1] + buffer  # Most recent swing high plus buffer (BUG-04 fix)
                    if new_sl < pos.current_sl:
                        await self._update_sl(pos, new_sl)
                        logger.debug(
                            f"{pos.trade_id}: PRICE_ACTION trail SL -> {new_sl:.5f} "
                            f"(swing high={valid_highs[-1]:.5f})"
                        )

    async def _trail_with_percentage(self, pos: ManagedPosition, current_price: float, trail_pct: float):
        """Fallback trailing: move SL to lock in a percentage of unrealized profit. Syncs with broker."""
        distance_to_tp1 = abs(pos.take_profit_1 - pos.entry_price)
        if distance_to_tp1 == 0:
            logger.warning(f"{pos.trade_id}: take_profit_1 == entry_price — skipping percentage trail to avoid zero distance")
            return
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

    async def _update_sl(self, pos: ManagedPosition, new_sl: float) -> bool:
        """Update stop loss on the broker. Returns True if successful.
        Safety: rejects SL moves in the wrong direction (BUY: down, SELL: up)."""
        # Direction guard — SL must only move favorably (reduce risk)
        if pos.current_sl and pos.current_sl != 0:
            if pos.direction == "BUY" and new_sl < pos.current_sl:
                logger.warning(
                    f"{pos.trade_id}: Blocked SL move DOWN for BUY: {pos.current_sl:.5f} -> {new_sl:.5f}"
                )
                return False
            if pos.direction == "SELL" and new_sl > pos.current_sl:
                logger.warning(
                    f"{pos.trade_id}: Blocked SL move UP for SELL: {pos.current_sl:.5f} -> {new_sl:.5f}"
                )
                return False
        old_sl = pos.current_sl
        try:
            result = await self.broker.modify_trade_sl(pos.trade_id, new_sl)
            if result:
                pos.current_sl = new_sl
                # Persist the new SL so the audit log reflects reality.
                # Errors are swallowed to never block trading on an audit failure.
                if self._on_sl_changed is not None:
                    try:
                        await self._on_sl_changed(
                            trade_id=pos.trade_id,
                            instrument=pos.instrument,
                            direction=pos.direction,
                            old_sl=old_sl,
                            new_sl=new_sl,
                            phase=getattr(pos.phase, "value", str(pos.phase)),
                        )
                    except Exception as cb_err:
                        logger.warning(
                            f"on_sl_changed callback failed for {pos.trade_id}: {cb_err}"
                        )
                return True
            else:
                logger.warning(f"Broker rejected SL update for {pos.trade_id}: {pos.current_sl} -> {new_sl}")
                return False
        except Exception as e:
            logger.error(f"Failed to update SL for {pos.trade_id}: {e}")
            return False

    def remove_position(self, trade_id: str):
        """Stop tracking a closed position."""
        if trade_id in self.positions:
            del self.positions[trade_id]
            logger.info(f"Position {trade_id} removed from tracking")
