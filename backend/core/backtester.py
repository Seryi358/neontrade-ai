"""
NeonTrade AI - Backtesting Engine
Walk-forward historical simulation of trading strategies.

Fetches multi-timeframe candle history from the broker (Capital.com API),
replays it bar-by-bar on H1 resolution, fires the strategy detection
pipeline at each bar, simulates entries with slippage/spread, tracks
positions through the 5-phase management system, and computes equity
curve, drawdown, Sharpe ratio, profit factor, and per-strategy stats.

Usage:
    from core.backtester import Backtester, BacktestConfig

    bt = Backtester(broker_client)
    result = await bt.run(BacktestConfig(
        instrument="EUR_USD",
        start_date="2025-01-01",
        end_date="2025-06-01",
        initial_balance=10_000,
        enabled_strategies={"BLUE": True, "RED": True, "GREEN": True},
    ))
"""

from __future__ import annotations

import asyncio
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger

from broker.base import CandleData
from core.market_analyzer import (
    AnalysisResult,
    MarketAnalyzer,
    MarketCondition,
    Trend,
)
from core.position_manager import ManagedPosition, PositionPhase
from strategies.base import SetupSignal, get_best_setup


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BacktestConfig:
    """Configuration for a single backtest run."""

    instrument: str
    start_date: str  # ISO format YYYY-MM-DD
    end_date: str  # ISO format YYYY-MM-DD
    initial_balance: float = 10_000.0
    risk_per_trade: float = 0.01  # 1 %
    slippage_pips: float = 0.5
    spread_pips: float = 1.0
    enabled_strategies: Dict[str, bool] = field(default_factory=dict)
    # Optional: override minimum R:R filter
    min_rr_ratio: float = 1.5
    # Maximum number of concurrent open positions
    max_concurrent_positions: int = 3
    # Cooldown bars after a trade closes before another can open
    cooldown_bars: int = 2


class TradeOutcome(Enum):
    WIN = "win"
    LOSS = "loss"
    BREAK_EVEN = "break_even"


@dataclass
class BacktestTrade:
    """Record of a single simulated trade."""

    trade_id: str
    instrument: str
    strategy: str  # e.g. "BLUE_A", "RED", "GREEN"
    direction: str  # "BUY" or "SELL"
    entry_price: float
    entry_time: str
    exit_price: float = 0.0
    exit_time: str = ""
    stop_loss: float = 0.0
    take_profit_1: float = 0.0
    take_profit_max: Optional[float] = None
    units: int = 0
    pnl: float = 0.0
    pnl_pips: float = 0.0
    risk_reward_achieved: float = 0.0
    outcome: TradeOutcome = TradeOutcome.LOSS
    exit_reason: str = ""
    max_favorable_excursion: float = 0.0  # best unrealised P&L (pips)
    max_adverse_excursion: float = 0.0  # worst unrealised P&L (pips)
    phase_at_exit: str = "INITIAL"
    confidence: float = 0.0
    bars_held: int = 0


@dataclass
class BacktestResult:
    """Aggregated results of a completed backtest."""

    config: BacktestConfig
    trades: List[BacktestTrade]
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    break_even_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    profit_factor: float = 0.0
    avg_rr_achieved: float = 0.0
    final_balance: float = 0.0
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)
    by_strategy: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    by_instrument: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    duration_days: int = 0
    avg_bars_held: float = 0.0
    best_trade_pnl: float = 0.0
    worst_trade_pnl: float = 0.0
    # Mentorship: "minimum 100 trades before evaluating the system"
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _pip_value(instrument: str) -> float:
    """Return the pip size for a given instrument."""
    from strategies.base import _is_crypto_instrument
    pair = instrument.upper().replace("/", "_")
    if _is_crypto_instrument(instrument):
        return 1.0  # Crypto: 1 pip = $1 move (no fractional pip concept)
    if "JPY" in pair:
        return 0.01
    return 0.0001


def _pips(instrument: str, price_distance: float) -> float:
    """Convert a raw price distance to pips."""
    pv = _pip_value(instrument)
    if pv == 0:
        return 0.0
    return price_distance / pv


def _price_from_pips(instrument: str, pips: float) -> float:
    """Convert pips to a raw price distance."""
    return pips * _pip_value(instrument)


# ---------------------------------------------------------------------------
# Simulated position (extends ManagedPosition logic for backtest)
# ---------------------------------------------------------------------------

class _SimulatedPosition:
    """
    Lightweight position tracker that mirrors the 5-phase management
    system from ``core.position_manager`` but operates entirely in-memory
    on bar data, without calling the broker.
    """

    def __init__(
        self,
        trade: BacktestTrade,
        instrument: str,
    ):
        self.trade = trade
        self.instrument = instrument
        self.phase = PositionPhase.INITIAL
        self.current_sl = trade.stop_loss
        self.highest_price = trade.entry_price
        self.lowest_price = trade.entry_price
        self.bars_elapsed = 0
        self.closed = False

    # ------------------------------------------------------------------
    # Phase thresholds (mirror position_manager.py constants)
    # ------------------------------------------------------------------
    _PHASE1_THRESHOLD = 0.20   # 20 % to TP1 -> move SL to structure
    _BE_THRESHOLD = 0.50       # Backtester uses 50% to TP1 as BE trigger (simplified); live uses 1% unrealized profit
    _TRAILING_THRESHOLD = 0.70 # 70 % to TP1 -> start trailing
    _TRAIL_PCT = 0.40          # fallback trailing distance (% of TP dist)
    _AGGRESSIVE_TRAIL_PCT = 0.20

    # ------------------------------------------------------------------

    def _profit(self, price: float) -> float:
        if self.trade.direction == "BUY":
            return price - self.trade.entry_price
        return self.trade.entry_price - price

    def _distance_to_tp1(self) -> float:
        return abs(self.trade.take_profit_1 - self.trade.entry_price)

    # ------------------------------------------------------------------

    def update(self, bar_high: float, bar_low: float, bar_close: float):
        """
        Process one bar.  Returns True if the position was closed by
        SL or TP hit during this bar, False otherwise.
        """
        if self.closed:
            return True

        self.bars_elapsed += 1

        # Track extremes
        if self.trade.direction == "BUY":
            self.highest_price = max(self.highest_price, bar_high)
            self.lowest_price = min(self.lowest_price, bar_low)
        else:
            self.lowest_price = min(self.lowest_price, bar_low)
            self.highest_price = max(self.highest_price, bar_high)

        # MFE / MAE tracking (in pips)
        if self.trade.direction == "BUY":
            mfe_price = self.highest_price - self.trade.entry_price
            mae_price = self.trade.entry_price - self.lowest_price
        else:
            mfe_price = self.trade.entry_price - self.lowest_price
            mae_price = self.highest_price - self.trade.entry_price
        self.trade.max_favorable_excursion = max(
            self.trade.max_favorable_excursion,
            _pips(self.instrument, mfe_price),
        )
        self.trade.max_adverse_excursion = max(
            self.trade.max_adverse_excursion,
            _pips(self.instrument, mae_price),
        )

        # ── Check SL hit ────────────────────────────────────────────
        if self._check_sl_hit(bar_high, bar_low):
            self._close(self.current_sl, "SL_HIT")
            return True

        # ── Check TP hit (use take_profit_max if available) ─────────
        if self._check_tp_hit(bar_high, bar_low):
            tp_target = self.trade.take_profit_max or self.trade.take_profit_1
            self._close(tp_target, "TP_HIT")
            return True

        # ── Phase management (on bar close) ─────────────────────────
        self._advance_phase(bar_close)

        return False

    def _check_sl_hit(self, bar_high: float, bar_low: float) -> bool:
        if self.trade.direction == "BUY":
            return bar_low <= self.current_sl
        return bar_high >= self.current_sl

    def _check_tp_hit(self, bar_high: float, bar_low: float) -> bool:
        tp = self.trade.take_profit_max or self.trade.take_profit_1
        if self.trade.direction == "BUY":
            return bar_high >= tp
        return bar_low <= tp

    def _advance_phase(self, bar_close: float):
        """Run through the 5-phase management on bar close."""
        dist = self._distance_to_tp1()
        if dist == 0:
            return
        profit = self._profit(bar_close)
        progress = profit / dist  # fraction of distance to TP1

        if self.phase == PositionPhase.INITIAL:
            if progress >= self._PHASE1_THRESHOLD:
                # Move SL closer: halfway between original SL and entry
                if self.trade.direction == "BUY":
                    new_sl = self.trade.stop_loss + (
                        self.trade.entry_price - self.trade.stop_loss
                    ) * 0.5
                else:
                    new_sl = self.trade.stop_loss - (
                        self.trade.stop_loss - self.trade.entry_price
                    ) * 0.5
                self.current_sl = new_sl
                self.phase = PositionPhase.SL_MOVED

        elif self.phase == PositionPhase.SL_MOVED:
            if progress >= self._BE_THRESHOLD:
                spread_buffer = abs(
                    self.trade.entry_price - self.trade.stop_loss
                ) * 0.02
                if self.trade.direction == "BUY":
                    self.current_sl = self.trade.entry_price + spread_buffer
                else:
                    self.current_sl = self.trade.entry_price - spread_buffer
                self.phase = PositionPhase.BREAK_EVEN

        elif self.phase == PositionPhase.BREAK_EVEN:
            if progress >= self._TRAILING_THRESHOLD:
                self.phase = PositionPhase.TRAILING_TO_TP1

        elif self.phase == PositionPhase.TRAILING_TO_TP1:
            # Check if TP1 reached -> aggressive
            tp1_reached = (
                (bar_close >= self.trade.take_profit_1)
                if self.trade.direction == "BUY"
                else (bar_close <= self.trade.take_profit_1)
            )
            if tp1_reached:
                self.phase = PositionPhase.BEYOND_TP1
            else:
                self._trail(bar_close, self._TRAIL_PCT)

        elif self.phase == PositionPhase.BEYOND_TP1:
            self._trail(bar_close, self._AGGRESSIVE_TRAIL_PCT)

    def _trail(self, price: float, trail_pct: float):
        """Move SL as a fraction of TP distance behind current price."""
        trail_dist = self._distance_to_tp1() * trail_pct
        if self.trade.direction == "BUY":
            new_sl = price - trail_dist
            if new_sl > self.current_sl:
                self.current_sl = new_sl
        else:
            new_sl = price + trail_dist
            if new_sl < self.current_sl:
                self.current_sl = new_sl

    def _close(self, exit_price: float, reason: str):
        """Fill exit fields on the trade record."""
        self.closed = True
        self.trade.exit_price = exit_price
        self.trade.exit_reason = reason
        self.trade.bars_held = self.bars_elapsed
        self.trade.phase_at_exit = self.phase.value

        # P&L calculation
        if self.trade.direction == "BUY":
            raw_pnl_price = exit_price - self.trade.entry_price
        else:
            raw_pnl_price = self.trade.entry_price - exit_price

        self.trade.pnl_pips = _pips(self.instrument, raw_pnl_price)
        self.trade.pnl = raw_pnl_price * abs(self.trade.units)

        # R:R achieved
        risk_distance = abs(self.trade.entry_price - self.trade.stop_loss)
        if risk_distance > 0:
            self.trade.risk_reward_achieved = raw_pnl_price / risk_distance
        else:
            self.trade.risk_reward_achieved = 0.0

        # Outcome
        be_threshold = _price_from_pips(self.instrument, 0.5)  # 0.5 pip
        if raw_pnl_price > be_threshold:
            self.trade.outcome = TradeOutcome.WIN
        elif raw_pnl_price < -be_threshold:
            self.trade.outcome = TradeOutcome.LOSS
        else:
            self.trade.outcome = TradeOutcome.BREAK_EVEN

    def force_close(self, price: float, reason: str = "END_OF_DATA"):
        """Force-close at end of backtest period."""
        if not self.closed:
            self._close(price, reason)


# ---------------------------------------------------------------------------
# Backtest analysis broker adapter
# ---------------------------------------------------------------------------

class _HistoricalBrokerAdapter:
    """
    Thin adapter that presents sliced historical data as if the broker
    were being queried live.  This lets us reuse ``MarketAnalyzer``
    exactly as it works in production.
    """

    def __init__(
        self,
        candle_store: Dict[str, pd.DataFrame],
        current_index: int,
        instrument: str,
    ):
        self._store = candle_store
        self._idx = current_index
        self._instrument = instrument

    async def get_candles(
        self,
        instrument: str,
        granularity: str = "H1",
        count: int = 100,
    ) -> List[CandleData]:
        """Return candles up to (and including) the current bar index."""
        key = f"{instrument}_{granularity}"
        df = self._store.get(key)
        if df is None or df.empty:
            return []

        # Slice: everything up to and including current_index rows
        # The caller (MarketAnalyzer) expects the *last* `count` candles.
        sliced = df.iloc[: self._idx + 1].tail(count)

        result: List[CandleData] = []
        for ts, row in sliced.iterrows():
            result.append(
                CandleData(
                    time=str(ts),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row.get("volume", 0)),
                    complete=True,
                )
            )
        return result

    async def get_pip_value(self, instrument: str) -> float:
        return _pip_value(instrument)

    async def get_current_price(self, instrument: str):
        """Not used by the analyzer but included for completeness."""
        from broker.base import PriceData

        key = f"{instrument}_H1"
        df = self._store.get(key)
        if df is not None and not df.empty:
            row = df.iloc[min(self._idx, len(df) - 1)]
            mid = float(row["close"])
            spread = _price_from_pips(instrument, 1.0)
            return PriceData(
                bid=mid - spread / 2,
                ask=mid + spread / 2,
                spread=spread,
                time=str(df.index[min(self._idx, len(df) - 1)]),
            )
        raise ValueError(f"No data for {instrument}")


# ---------------------------------------------------------------------------
# Main backtester
# ---------------------------------------------------------------------------

class Backtester:
    """
    Walk-forward backtesting engine for NeonTrade AI strategies.

    Workflow
    --------
    1. Fetch historical candle data for every required timeframe.
    2. Align all timeframes to the H1 index (the simulation clock).
    3. At each H1 bar:
       a. Build a ``_HistoricalBrokerAdapter`` sliced to that point.
       b. Run ``MarketAnalyzer.full_analysis()`` exactly as in production.
       c. Run ``get_best_setup()`` to detect a strategy signal.
       d. If a signal fires, open a simulated position (with slippage).
       e. For every open position, feed the current H1 bar through the
          5-phase management system and check for SL / TP hits.
    4. After the walk-forward, compute performance metrics.
    """

    # Timeframe definitions and lookback counts (mirrors MarketAnalyzer)
    _TIMEFRAMES: Dict[str, int] = {
        "W": 52,
        "D": 120,
        "H4": 200,
        "H1": 200,
        "M15": 200,
        "M5": 200,
    }

    # How many H1 bars each higher-timeframe candle spans (approximate)
    _TF_TO_H1_BARS: Dict[str, int] = {
        "W": 120,   # ~5 days * 24h
        "D": 24,
        "H4": 4,
        "H1": 1,
        "M15": 1,   # multiple M15 bars per H1 -- we resample
        "M5": 1,
    }

    def __init__(self, broker_client):
        """
        Parameters
        ----------
        broker_client : BaseBroker
            A live broker client used *only* to fetch historical candle
            data before the simulation starts.
        """
        self.broker = broker_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, config: BacktestConfig) -> BacktestResult:
        """Execute a single-instrument backtest."""
        logger.info(
            f"[Backtest] Starting {config.instrument} "
            f"from {config.start_date} to {config.end_date} "
            f"| balance={config.initial_balance} risk={config.risk_per_trade:.2%}"
        )

        # 1. Fetch all historical data
        candle_store = await self._fetch_all_candles(config)

        # 2. Build H1 index (the simulation clock)
        h1_key = f"{config.instrument}_H1"
        h1_df = candle_store.get(h1_key)
        if h1_df is None or h1_df.empty:
            logger.error(f"[Backtest] No H1 data for {config.instrument}")
            return self._empty_result(config)

        # Filter H1 bars to the requested date range
        # Ensure timezone compatibility: strip tz if index is naive
        start_dt = pd.Timestamp(config.start_date)
        end_dt = pd.Timestamp(config.end_date)
        if h1_df.index.tz is not None:
            start_dt = start_dt.tz_localize("UTC")
            end_dt = end_dt.tz_localize("UTC")
        elif str(h1_df.index.dtype).startswith("datetime64"):
            # Index is naive, use naive timestamps
            pass
        h1_mask = (h1_df.index >= start_dt) & (h1_df.index <= end_dt)
        h1_range = h1_df.loc[h1_mask]

        if h1_range.empty:
            logger.warning(
                f"[Backtest] No H1 bars in range {config.start_date} - {config.end_date}"
            )
            return self._empty_result(config)

        # We need the absolute index positions in the *full* dataframe so
        # that the adapter can slice correctly (including lookback).
        h1_indices = [
            h1_df.index.get_loc(ts) for ts in h1_range.index
        ]

        # Map each H1 timestamp to its absolute-index position in
        # each higher-timeframe dataframe for adapter slicing.
        tf_index_maps: Dict[str, pd.DataFrame] = {}
        for tf in self._TIMEFRAMES:
            tf_key = f"{config.instrument}_{tf}"
            tf_df = candle_store.get(tf_key)
            if tf_df is not None and not tf_df.empty:
                tf_index_maps[tf] = tf_df

        # 3. Walk forward
        balance = config.initial_balance
        equity_curve: List[Dict[str, Any]] = []
        trades: List[BacktestTrade] = []
        open_positions: List[_SimulatedPosition] = []
        cooldown_remaining = 0
        peak_balance = balance

        # Analysis frequency: run the full analyzer every N H1 bars to
        # keep the backtest tractable.  4 bars = every 4 hours.
        analysis_interval = 4
        last_analysis: Optional[AnalysisResult] = None
        last_signal: Optional[SetupSignal] = None

        total_bars = len(h1_indices)
        log_every = max(total_bars // 20, 1)  # log ~20 progress updates

        for step, h1_abs_idx in enumerate(h1_indices):
            bar = h1_df.iloc[h1_abs_idx]
            bar_time = str(h1_df.index[h1_abs_idx])
            bar_high = float(bar["high"])
            bar_low = float(bar["low"])
            bar_close = float(bar["close"])

            # ── 3a. Update open positions ────────────────────────────
            newly_closed: List[_SimulatedPosition] = []
            for pos in open_positions:
                closed = pos.update(bar_high, bar_low, bar_close)
                if closed:
                    pos.trade.exit_time = bar_time
                    newly_closed.append(pos)

            for pos in newly_closed:
                balance += pos.trade.pnl
                trades.append(pos.trade)
                open_positions.remove(pos)

            # Bug fix R27: reset cooldown after trade closes (was never set)
            if newly_closed:
                cooldown_remaining = config.cooldown_bars

            # ── 3b. Run analysis periodically ────────────────────────
            run_analysis = (step % analysis_interval == 0)
            if run_analysis:
                # Build adapter that gives the analyzer a view of data
                # up to the *current* bar for every timeframe.
                tf_idx_map = self._build_tf_index_map(
                    config.instrument,
                    h1_df.index[h1_abs_idx],
                    candle_store,
                )
                adapter = _HistoricalBrokerAdapter(
                    candle_store,
                    current_index=h1_abs_idx,
                    instrument=config.instrument,
                )
                # Override get_candles to slice each TF independently
                adapter._tf_idx_map = tf_idx_map  # type: ignore[attr-defined]
                adapter._get_candles_original = adapter.get_candles  # type: ignore[attr-defined]
                adapter.get_candles = self._make_tf_aware_get_candles(  # type: ignore[method-assign]
                    candle_store, tf_idx_map, config.instrument,
                )

                try:
                    analyzer = MarketAnalyzer(adapter)
                    last_analysis = await analyzer.full_analysis(config.instrument)
                except Exception as exc:
                    logger.debug(f"[Backtest] Analysis error at {bar_time}: {exc}")
                    last_analysis = None

                if last_analysis is not None:
                    try:
                        last_signal = get_best_setup(
                            last_analysis,
                            config.enabled_strategies or None,
                        )
                    except Exception as exc:
                        logger.debug(f"[Backtest] Strategy error at {bar_time}: {exc}")
                        last_signal = None

            # ── 3c. Attempt entry ────────────────────────────────────
            # R29 fix: enforce trading hours and Friday rules from mentorship
            _allow_new_trade = True
            try:
                from datetime import datetime as _dt
                _bar_dt = _dt.fromisoformat(bar_time.replace("Z", "+00:00")) if isinstance(bar_time, str) else None
                if _bar_dt:
                    _h = _bar_dt.hour
                    _wd = _bar_dt.weekday()  # 0=Mon, 4=Fri
                    # Trading hours: 07:00-22:00 UTC (London+NY)
                    if _h < 7 or _h >= 22:
                        _allow_new_trade = False
                    # Friday: no new trades after 18:00 UTC
                    if _wd == 4 and _h >= 18:
                        _allow_new_trade = False
                    # Friday EOD: force-close all open positions at 22:00 UTC
                    # TradingLab: no weekend exposure — close everything before market close
                    if _wd == 4 and _h >= 22 and open_positions:
                        for pos in list(open_positions):
                            pos.force_close(bar_close, "FRIDAY_CLOSE")
                            pos.trade.exit_time = bar_time
                            balance += pos.trade.pnl
                            trades.append(pos.trade)
                            cooldown_remaining = config.cooldown_bars
                        open_positions.clear()
                        logger.debug(f"[Backtest] Friday EOD close at {bar_time}")
            except Exception as e:
                logger.warning(f"Failed to parse bar time for session/Friday check: {e}. Blocking new trade as safety.")
                _allow_new_trade = False

            if (
                last_signal is not None
                and cooldown_remaining <= 0
                and _allow_new_trade
                and len(open_positions) < config.max_concurrent_positions
            ):
                new_pos = self._try_open_position(
                    signal=last_signal,
                    config=config,
                    balance=balance,
                    bar_time=bar_time,
                    bar_close=bar_close,
                )
                if new_pos is not None:
                    open_positions.append(new_pos)
                    last_signal = None  # consume the signal

            # Decrement cooldown AFTER entry check so cooldown_bars=2
            # actually blocks the next 2 bars (fix off-by-one).
            if cooldown_remaining > 0:
                cooldown_remaining -= 1

            # ── 3d. Equity curve ─────────────────────────────────────
            unrealised = 0.0
            for pos in open_positions:
                if pos.trade.direction == "BUY":
                    unrealised += (bar_close - pos.trade.entry_price) * abs(
                        pos.trade.units
                    )
                else:
                    unrealised += (pos.trade.entry_price - bar_close) * abs(
                        pos.trade.units
                    )

            equity = balance + unrealised
            equity_curve.append(
                {"date": bar_time, "balance": round(balance, 2), "equity": round(equity, 2)}
            )

            # Drawdown tracking
            if equity > peak_balance:
                peak_balance = equity

            # Progress logging
            if step % log_every == 0:
                pct = (step / total_bars) * 100
                logger.info(
                    f"[Backtest] {config.instrument} {pct:.0f}% "
                    f"| bar {step}/{total_bars} | balance={balance:.2f} "
                    f"| open={len(open_positions)} | trades={len(trades)}"
                )

        # ── 4. Force-close any remaining positions at last bar ───────
        if open_positions:
            last_close = float(h1_df.iloc[h1_indices[-1]]["close"])
            last_time = str(h1_df.index[h1_indices[-1]])
            for pos in open_positions:
                pos.force_close(last_close, "END_OF_BACKTEST")
                pos.trade.exit_time = last_time
                balance += pos.trade.pnl
                trades.append(pos.trade)

        # ── 5. Compute metrics ───────────────────────────────────────
        result = self._compute_metrics(config, trades, equity_curve, balance)

        logger.info(
            f"[Backtest] Finished {config.instrument} | "
            f"Trades={result.total_trades} W/L={result.winning_trades}/"
            f"{result.losing_trades} WR={result.win_rate:.1f}% "
            f"PnL={result.total_pnl:.2f} PF={result.profit_factor:.2f} "
            f"Sharpe={result.sharpe_ratio:.2f} MaxDD={result.max_drawdown_pct:.1f}%"
        )

        return result

    async def run_multi(
        self, configs: List[BacktestConfig]
    ) -> List[BacktestResult]:
        """
        Run backtests for multiple instruments / configurations in
        parallel (limited concurrency to avoid API rate limits).
        """
        semaphore = asyncio.Semaphore(3)

        async def _run_one(cfg: BacktestConfig) -> BacktestResult:
            async with semaphore:
                return await self.run(cfg)

        results = await asyncio.gather(*[_run_one(c) for c in configs])
        return list(results)

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------

    async def _fetch_all_candles(
        self, config: BacktestConfig
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch historical candle data for every timeframe the analyzer
        needs, converted to DataFrames keyed by ``{instrument}_{tf}``.

        We request a generous lookback before ``start_date`` so that
        technical indicators (EMAs, Fib, etc.) are warmed up by the time
        the simulation window begins.
        """
        store: Dict[str, pd.DataFrame] = {}

        for tf, default_count in self._TIMEFRAMES.items():
            # Request enough data to cover the backtest period PLUS
            # a warm-up window equal to the default lookback count.
            try:
                count = 1000  # API max; covers lookback + simulation window
                raw_candles = await self.broker.get_candles(
                    config.instrument, tf, count
                )
                df = self._candles_to_df(raw_candles)
                key = f"{config.instrument}_{tf}"
                store[key] = df
                logger.debug(
                    f"[Backtest] Fetched {len(df)} {tf} candles for {config.instrument}"
                )
            except Exception as exc:
                logger.warning(
                    f"[Backtest] Failed to fetch {tf} candles for "
                    f"{config.instrument}: {exc}"
                )
                store[f"{config.instrument}_{tf}"] = pd.DataFrame()

            # Small delay to avoid rate-limiting
            await asyncio.sleep(0.3)

        return store

    @staticmethod
    def _candles_to_df(candles: List[CandleData]) -> pd.DataFrame:
        """Convert list of CandleData to a time-indexed DataFrame."""
        if not candles:
            return pd.DataFrame()

        rows = []
        for c in candles:
            if not c.complete:
                continue
            # CLAUDE.md Rule #9: Skip candles with all-zero OHLC (broker returns empty data)
            if c.open == 0 and c.high == 0 and c.low == 0 and c.close == 0:
                continue
            rows.append(
                {
                    "time": pd.Timestamp(c.time),
                    "open": float(c.open),
                    "high": float(c.high),
                    "low": float(c.low),
                    "close": float(c.close),
                    "volume": int(c.volume),
                }
            )
        df = pd.DataFrame(rows)
        if not df.empty:
            df.set_index("time", inplace=True)
            df.sort_index(inplace=True)
        return df

    # ------------------------------------------------------------------
    # Adapter helpers
    # ------------------------------------------------------------------

    def _build_tf_index_map(
        self,
        instrument: str,
        current_h1_time: pd.Timestamp,
        candle_store: Dict[str, pd.DataFrame],
    ) -> Dict[str, int]:
        """
        For each timeframe, find the last bar index whose timestamp is
        <= the current H1 bar timestamp.  This ensures higher-timeframe
        data does not leak future information.
        """
        result: Dict[str, int] = {}
        for tf in self._TIMEFRAMES:
            key = f"{instrument}_{tf}"
            df = candle_store.get(key)
            if df is None or df.empty:
                result[key] = 0
                continue
            # Find the last index <= current H1 time
            mask = df.index <= current_h1_time
            if mask.any():
                result[key] = int(mask.sum()) - 1
            else:
                result[key] = 0
        return result

    @staticmethod
    def _make_tf_aware_get_candles(
        candle_store: Dict[str, pd.DataFrame],
        tf_idx_map: Dict[str, int],
        instrument: str,
    ):
        """
        Return an async function that slices the correct timeframe
        dataframe up to the right index, preventing look-ahead bias.
        """

        async def _get_candles(
            inst: str,
            granularity: str = "H1",
            count: int = 100,
        ) -> List[CandleData]:
            key = f"{inst}_{granularity}"
            df = candle_store.get(key)
            if df is None or df.empty:
                return []

            max_idx = tf_idx_map.get(key, len(df) - 1)
            sliced = df.iloc[: max_idx + 1].tail(count)

            result: List[CandleData] = []
            for ts, row in sliced.iterrows():
                result.append(
                    CandleData(
                        time=str(ts),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=int(row.get("volume", 0)),
                        complete=True,
                    )
                )
            return result

        return _get_candles

    # ------------------------------------------------------------------
    # Position opening
    # ------------------------------------------------------------------

    def _try_open_position(
        self,
        signal: SetupSignal,
        config: BacktestConfig,
        balance: float,
        bar_time: str,
        bar_close: float,
    ) -> Optional[_SimulatedPosition]:
        """
        Validate the signal, apply slippage/spread, compute position
        size, and return a ``_SimulatedPosition`` or None.
        """
        direction = signal.direction
        entry_raw = signal.entry_price
        sl = signal.stop_loss
        tp1 = signal.take_profit_1
        tp_max = signal.take_profit_max

        # ── Sanity checks ────────────────────────────────────────────
        # Use bar close as a reality check for entry price.  If the
        # signal's entry_price is far from the current bar close, snap
        # it to bar_close (as a market order would fill near current).
        price_tolerance = _price_from_pips(config.instrument, 20)
        if abs(entry_raw - bar_close) > price_tolerance:
            entry_raw = bar_close

        # ── Apply slippage + spread ──────────────────────────────────
        slip = _price_from_pips(config.instrument, config.slippage_pips)
        spread = _price_from_pips(config.instrument, config.spread_pips)

        if direction == "BUY":
            entry_price = entry_raw + slip + spread / 2
        else:
            entry_price = entry_raw - slip - spread / 2

        # ── Validate R:R ─────────────────────────────────────────────
        risk_dist = abs(entry_price - sl)
        reward_dist = abs(tp1 - entry_price)
        if risk_dist == 0:
            return None
        rr = reward_dist / risk_dist
        # Strategy-specific R:R minimums per TradingLab mentorship
        strategy_name = (signal.strategy_variant or signal.strategy.value).upper()
        if "BLACK" in strategy_name:
            effective_min_rr = 2.0  # Counter-trend requires higher R:R
        elif "GREEN" in strategy_name:
            effective_min_rr = 2.0  # Crypto/Elliott requires higher R:R
        elif strategy_name == "BLUE_C":
            effective_min_rr = 2.0  # Blue C: "mínimo 2 a 1, incluso 3 a 1"
        else:
            effective_min_rr = config.min_rr_ratio
        if rr < effective_min_rr:
            logger.debug(
                f"[Backtest] Signal rejected: R:R {rr:.2f} < {effective_min_rr} ({strategy_name})"
            )
            return None

        # ── SL must be on the correct side ───────────────────────────
        if direction == "BUY" and sl >= entry_price:
            return None
        if direction == "SELL" and sl <= entry_price:
            return None

        # ── TP must be on the correct side ───────────────────────────
        if direction == "BUY" and tp1 <= entry_price:
            return None
        if direction == "SELL" and tp1 >= entry_price:
            return None

        # ── Position size ────────────────────────────────────────────
        risk_amount = balance * config.risk_per_trade
        pv = _pip_value(config.instrument)
        sl_pips = risk_dist / pv if pv > 0 else 0
        if sl_pips <= 0:
            return None
        cost_per_unit = sl_pips * pv
        if cost_per_unit <= 0:
            return None
        units = int(risk_amount / cost_per_unit)
        if units <= 0:
            return None

        if direction == "SELL":
            units = -units

        # ── Build trade record ───────────────────────────────────────
        trade = BacktestTrade(
            trade_id=str(uuid.uuid4())[:8],
            instrument=config.instrument,
            strategy=signal.strategy_variant or signal.strategy.value,
            direction=direction,
            entry_price=entry_price,
            entry_time=bar_time,
            stop_loss=sl,
            take_profit_1=tp1,
            take_profit_max=tp_max,
            units=units,
            confidence=signal.confidence,
        )

        return _SimulatedPosition(trade, config.instrument)

    # ------------------------------------------------------------------
    # Metrics computation
    # ------------------------------------------------------------------

    def _compute_metrics(
        self,
        config: BacktestConfig,
        trades: List[BacktestTrade],
        equity_curve: List[Dict[str, Any]],
        final_balance: float,
    ) -> BacktestResult:
        total = len(trades)
        wins = [t for t in trades if t.outcome == TradeOutcome.WIN]
        losses = [t for t in trades if t.outcome == TradeOutcome.LOSS]
        bes = [t for t in trades if t.outcome == TradeOutcome.BREAK_EVEN]

        win_rate = (len(wins) / total * 100) if total > 0 else 0.0
        total_pnl = sum(t.pnl for t in trades)

        # ── Drawdown ─────────────────────────────────────────────────
        max_dd, max_dd_pct = self._calc_drawdown(equity_curve)

        # ── Sharpe ratio (annualised, assuming H1 bars) ──────────────
        sharpe = self._calc_sharpe(trades)

        # ── Sortino ratio ────────────────────────────────────────────
        sortino = self._calc_sortino(trades)

        # ── Profit factor ────────────────────────────────────────────
        gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

        # ── Avg R:R achieved ─────────────────────────────────────────
        rr_vals = [t.risk_reward_achieved for t in trades]
        avg_rr = (sum(rr_vals) / len(rr_vals)) if rr_vals else 0.0

        # ── Avg bars held ────────────────────────────────────────────
        bars_vals = [t.bars_held for t in trades]
        avg_bars = (sum(bars_vals) / len(bars_vals)) if bars_vals else 0.0

        # ── Best / worst trade ───────────────────────────────────────
        pnl_vals = [t.pnl for t in trades]
        best_pnl = max(pnl_vals) if pnl_vals else 0.0
        worst_pnl = min(pnl_vals) if pnl_vals else 0.0

        # ── Per-strategy breakdown ───────────────────────────────────
        by_strategy = self._breakdown_by_key(trades, key_fn=lambda t: t.strategy)

        # ── Per-instrument breakdown ─────────────────────────────────
        by_instrument = self._breakdown_by_key(trades, key_fn=lambda t: t.instrument)

        # ── Duration ─────────────────────────────────────────────────
        try:
            start = pd.Timestamp(config.start_date)
            end = pd.Timestamp(config.end_date)
            duration = (end - start).days
        except Exception as e:
            logger.warning(f"Failed to parse backtest date range ({config.start_date} - {config.end_date}): {e}. Duration set to 0.")
            duration = 0

        # ── Warnings (mentorship validation) ────────────────────────────
        # Mentorship: "minimum 100 trades before evaluating the system"
        warnings: List[str] = []
        if total < 100:
            warnings.append(
                f"Insufficient sample size: {total} trades. "
                f"The mentorship requires a minimum of 100 trades per strategy "
                f"before evaluating system performance. Results may not be "
                f"statistically significant."
            )
        # Also check per-strategy trade counts
        for strat_name, strat_stats in by_strategy.items():
            strat_total = strat_stats.get("total_trades", 0)
            if 0 < strat_total < 100:
                warnings.append(
                    f"Strategy '{strat_name}' has only {strat_total} trades. "
                    f"Minimum 100 trades recommended before evaluating."
                )

        return BacktestResult(
            config=config,
            trades=trades,
            total_trades=total,
            winning_trades=len(wins),
            losing_trades=len(losses),
            break_even_trades=len(bes),
            win_rate=win_rate,
            total_pnl=round(total_pnl, 2),
            max_drawdown=round(max_dd, 2),
            max_drawdown_pct=round(max_dd_pct, 2),
            sharpe_ratio=round(sharpe, 2),
            sortino_ratio=round(sortino, 2),
            profit_factor=round(profit_factor, 2),
            avg_rr_achieved=round(avg_rr, 2),
            final_balance=round(final_balance, 2),
            equity_curve=equity_curve,
            by_strategy=by_strategy,
            by_instrument=by_instrument,
            duration_days=duration,
            avg_bars_held=round(avg_bars, 1),
            best_trade_pnl=round(best_pnl, 2),
            worst_trade_pnl=round(worst_pnl, 2),
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Statistical helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _calc_drawdown(
        equity_curve: List[Dict[str, Any]],
    ) -> Tuple[float, float]:
        """Return (max_drawdown_absolute, max_drawdown_percent)."""
        if not equity_curve:
            return 0.0, 0.0

        peak = equity_curve[0]["equity"]
        max_dd = 0.0
        max_dd_pct = 0.0

        for point in equity_curve:
            eq = point["equity"]
            if eq > peak:
                peak = eq
            dd = peak - eq
            dd_pct = (dd / peak * 100) if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

        return max_dd, max_dd_pct

    @staticmethod
    def _calc_sharpe(trades: List[BacktestTrade], risk_free_rate: float = 0.0) -> float:
        """
        Annualised Sharpe ratio based on per-trade returns.
        Annualisation uses 252 trading days (standard convention).
        Trades-per-day is estimated from the actual backtest data span,
        so the ratio does not inflate as total trade count grows.
        """
        if len(trades) < 2:
            return 0.0

        returns = [t.pnl for t in trades]
        mean_ret = np.mean(returns)
        std_ret = np.std(returns, ddof=1)

        if std_ret == 0:
            return 0.0

        # Estimate trades per year from actual data span
        try:
            first_entry = pd.Timestamp(trades[0].entry_time)
            last_entry = pd.Timestamp(trades[-1].entry_time)
            span_days = max((last_entry - first_entry).total_seconds() / 86400, 1)
            trades_per_year = len(returns) / span_days * 252
        except Exception:
            trades_per_year = 252  # fallback: ~1 trade/day

        sharpe = (mean_ret - risk_free_rate) / std_ret * math.sqrt(trades_per_year)
        return float(sharpe)

    @staticmethod
    def _calc_sortino(trades: List[BacktestTrade], risk_free_rate: float = 0.0) -> float:
        """Sortino ratio: like Sharpe but only penalises downside vol."""
        if len(trades) < 2:
            return 0.0

        returns = [t.pnl for t in trades]
        mean_ret = np.mean(returns)
        downside = [r for r in returns if r < 0]

        if not downside:
            return float("inf") if mean_ret > 0 else 0.0

        downside_std = np.std(downside, ddof=1)
        if downside_std == 0:
            return 0.0

        # Same time-based annualization as Sharpe
        try:
            first_entry = pd.Timestamp(trades[0].entry_time)
            last_entry = pd.Timestamp(trades[-1].entry_time)
            span_days = max((last_entry - first_entry).total_seconds() / 86400, 1)
            trades_per_year = len(returns) / span_days * 252
        except Exception:
            trades_per_year = 252

        sortino = (mean_ret - risk_free_rate) / downside_std * math.sqrt(trades_per_year)
        return float(sortino)

    @staticmethod
    def _breakdown_by_key(
        trades: List[BacktestTrade],
        key_fn,
    ) -> Dict[str, Dict[str, Any]]:
        """Group trades by an arbitrary key and compute stats per group."""
        groups: Dict[str, List[BacktestTrade]] = {}
        for t in trades:
            k = key_fn(t)
            groups.setdefault(k, []).append(t)

        result: Dict[str, Dict[str, Any]] = {}
        for key, group in groups.items():
            w = [t for t in group if t.outcome == TradeOutcome.WIN]
            l = [t for t in group if t.outcome == TradeOutcome.LOSS]
            total_pnl = sum(t.pnl for t in group)
            gp = sum(t.pnl for t in group if t.pnl > 0)
            gl = abs(sum(t.pnl for t in group if t.pnl < 0))
            pf = (gp / gl) if gl > 0 else float("inf")
            rr_vals = [t.risk_reward_achieved for t in group]
            avg_rr = (sum(rr_vals) / len(rr_vals)) if rr_vals else 0.0
            wr = (len(w) / len(group) * 100) if group else 0.0

            result[key] = {
                "total_trades": len(group),
                "winning_trades": len(w),
                "losing_trades": len(l),
                "win_rate": round(wr, 1),
                "total_pnl": round(total_pnl, 2),
                "profit_factor": round(pf, 2),
                "avg_rr_achieved": round(avg_rr, 2),
            }

        return result

    # ------------------------------------------------------------------

    @staticmethod
    def _empty_result(config: BacktestConfig) -> BacktestResult:
        return BacktestResult(
            config=config,
            trades=[],
            final_balance=config.initial_balance,
        )
