"""
NeonTrade AI - Trade Journal
Implements the complete TradingLab trade tracking system from Registro de trades.xlsx.

Fields tracked:
- Month, Trade #, Date, Asset, $ P/L, % P&L
- Result classification: TP (>= +0.1%), SL (<= -0.1%), BE (between)
- Running balance, P&L accumulated from initial capital
- Maximum balance (peak), Drawdown %, Drawdown $
- Winning streak tracking, Max winning streak
- Win rate (total), Win rate excluding BE
"""

import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional
from loguru import logger


class TradeJournal:
    """
    Complete trade journal following the TradingLab 'Registro de trades.xlsx' format.
    Tracks every closed trade with full statistics: win rate, drawdown, streaks,
    monthly returns, profit factor, and more.
    """

    def __init__(self, initial_capital: float):
        self._initial_capital = initial_capital
        self._data_path = os.path.join("data", "trade_journal.json")
        self._trades: List[Dict] = []
        self._current_balance = initial_capital
        self._peak_balance = initial_capital
        self._max_drawdown_pct = 0.0
        self._max_drawdown_dollars = 0.0
        self._current_winning_streak = 0
        self._max_winning_streak = 0
        self._max_streak_pct = 0.0  # cumulative % of the max winning streak
        self._trade_counter = 0
        self._load()

    # ── Record a completed trade ──────────────────────────────────

    def record_trade(
        self,
        trade_id: str,
        instrument: str,
        pnl_dollars: float,
        entry_price: float,
        exit_price: float,
        strategy: str,
        direction: str,
    ):
        """Record a completed trade into the journal."""
        now = datetime.now(timezone.utc)
        self._trade_counter += 1

        # Calculate P&L percentage based on balance before this trade
        balance_before = self._current_balance
        pnl_pct = (pnl_dollars / balance_before * 100) if balance_before > 0 else 0.0

        # Update balance
        self._current_balance += pnl_dollars

        # Update peak balance
        if self._current_balance > self._peak_balance:
            self._peak_balance = self._current_balance

        # Drawdown calculation
        if self._peak_balance > 0:
            drawdown_dollars = self._peak_balance - self._current_balance
            drawdown_pct = (drawdown_dollars / self._peak_balance) * 100
        else:
            drawdown_dollars = 0.0
            drawdown_pct = 0.0

        if drawdown_pct > self._max_drawdown_pct:
            self._max_drawdown_pct = drawdown_pct
        if drawdown_dollars > self._max_drawdown_dollars:
            self._max_drawdown_dollars = drawdown_dollars

        # Classify result
        result = self._classify_result(pnl_pct)

        # Winning streak tracking
        if result == "TP":
            self._current_winning_streak += 1
            # Track cumulative % for current streak
            if not hasattr(self, '_current_streak_pct'):
                self._current_streak_pct = 0.0
            self._current_streak_pct += pnl_pct
            if self._current_winning_streak > self._max_winning_streak:
                self._max_winning_streak = self._current_winning_streak
                self._max_streak_pct = self._current_streak_pct
        else:
            self._current_winning_streak = 0
            self._current_streak_pct = 0.0

        # P&L accumulated from initial capital
        pnl_accumulated_pct = (
            (self._current_balance - self._initial_capital)
            / self._initial_capital * 100
        ) if self._initial_capital > 0 else 0.0

        trade_record = {
            "trade_number": self._trade_counter,
            "trade_id": trade_id,
            "date": now.isoformat(),
            "month": now.strftime("%Y-%m"),
            "instrument": instrument,
            "direction": direction,
            "strategy": strategy,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl_dollars": round(pnl_dollars, 2),
            "pnl_pct": round(pnl_pct, 4),
            "result": result,
            "balance_after": round(self._current_balance, 2),
            "peak_balance": round(self._peak_balance, 2),
            "drawdown_pct": round(drawdown_pct, 4),
            "drawdown_dollars": round(drawdown_dollars, 2),
            "pnl_accumulated_pct": round(pnl_accumulated_pct, 4),
            "winning_streak": self._current_winning_streak,
        }

        self._trades.append(trade_record)
        self._save()

        logger.info(
            f"Trade Journal: #{self._trade_counter} {instrument} {direction} "
            f"| P&L: ${pnl_dollars:+.2f} ({pnl_pct:+.2f}%) | Result: {result} "
            f"| Balance: ${self._current_balance:.2f} | DD: {drawdown_pct:.2f}%"
        )

    # ── Statistics ────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Return comprehensive trading statistics following Registro de trades.xlsx."""
        if not self._trades:
            return {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "break_evens": 0,
                "win_rate": 0.0,
                "win_rate_excl_be": 0.0,
                "current_balance": round(self._current_balance, 2),
                "initial_capital": round(self._initial_capital, 2),
                "peak_balance": round(self._peak_balance, 2),
                "current_drawdown_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "max_drawdown_dollars": 0.0,
                "current_winning_streak": 0,
                "max_winning_streak": 0,
                "max_streak_pct": 0.0,
                "avg_win_pct": 0.0,
                "avg_loss_pct": 0.0,
                "profit_factor": 0.0,
                "monthly_returns": {},
                "pnl_accumulated_pct": 0.0,
            }

        wins = [t for t in self._trades if t["result"] == "TP"]
        losses = [t for t in self._trades if t["result"] == "SL"]
        break_evens = [t for t in self._trades if t["result"] == "BE"]

        total = len(self._trades)
        win_count = len(wins)
        loss_count = len(losses)
        be_count = len(break_evens)

        # Win rate
        win_rate = (win_count / total * 100) if total > 0 else 0.0

        # Win rate excluding BE
        non_be_total = win_count + loss_count
        win_rate_excl_be = (win_count / non_be_total * 100) if non_be_total > 0 else 0.0

        # Average win/loss percentages
        avg_win_pct = (
            sum(t["pnl_pct"] for t in wins) / win_count
        ) if win_count > 0 else 0.0

        avg_loss_pct = (
            sum(t["pnl_pct"] for t in losses) / loss_count
        ) if loss_count > 0 else 0.0

        # Profit factor = gross profits / gross losses
        gross_profits = sum(t["pnl_dollars"] for t in wins) if wins else 0.0
        gross_losses = abs(sum(t["pnl_dollars"] for t in losses)) if losses else 0.0
        profit_factor = (gross_profits / gross_losses) if gross_losses > 0 else (
            float('inf') if gross_profits > 0 else 0.0
        )

        # Current drawdown
        current_dd_dollars = self._peak_balance - self._current_balance
        current_dd_pct = (
            (current_dd_dollars / self._peak_balance * 100)
            if self._peak_balance > 0 else 0.0
        )

        # Monthly returns
        monthly_returns: Dict[str, float] = {}
        monthly_start_balance: Dict[str, float] = {}
        for t in self._trades:
            month = t["month"]
            if month not in monthly_returns:
                monthly_returns[month] = 0.0
                # Find balance at start of month (balance before first trade of the month)
                monthly_start_balance[month] = t["balance_after"] - t["pnl_dollars"]
            monthly_returns[month] += t["pnl_dollars"]

        # Convert monthly P&L dollars to percentage
        monthly_returns_pct: Dict[str, float] = {}
        for month, pnl in monthly_returns.items():
            start_bal = monthly_start_balance.get(month, self._initial_capital)
            if start_bal > 0:
                monthly_returns_pct[month] = round(pnl / start_bal * 100, 4)
            else:
                monthly_returns_pct[month] = 0.0

        # P&L accumulated from initial capital
        pnl_accumulated_pct = (
            (self._current_balance - self._initial_capital)
            / self._initial_capital * 100
        ) if self._initial_capital > 0 else 0.0

        return {
            "total_trades": total,
            "wins": win_count,
            "losses": loss_count,
            "break_evens": be_count,
            "win_rate": round(win_rate, 2),
            "win_rate_excl_be": round(win_rate_excl_be, 2),
            "current_balance": round(self._current_balance, 2),
            "initial_capital": round(self._initial_capital, 2),
            "peak_balance": round(self._peak_balance, 2),
            "current_drawdown_pct": round(current_dd_pct, 4),
            "max_drawdown_pct": round(self._max_drawdown_pct, 4),
            "max_drawdown_dollars": round(self._max_drawdown_dollars, 2),
            "current_winning_streak": self._current_winning_streak,
            "max_winning_streak": self._max_winning_streak,
            "max_streak_pct": round(self._max_streak_pct, 4),
            "avg_win_pct": round(avg_win_pct, 4),
            "avg_loss_pct": round(avg_loss_pct, 4),
            "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else 999.99,
            "monthly_returns": monthly_returns_pct,
            "pnl_accumulated_pct": round(pnl_accumulated_pct, 4),
        }

    # ── Trade History ─────────────────────────────────────────────

    def get_trades(self, limit: int = 50, offset: int = 0) -> list:
        """Return trade history with pagination, most recent first."""
        sorted_trades = list(reversed(self._trades))
        return sorted_trades[offset:offset + limit]

    # ── Classification ────────────────────────────────────────────

    def _classify_result(self, pnl_pct: float) -> str:
        """Classify trade result per TradingLab rules.
        TP: >= +0.1%, SL: <= -0.1%, BE: between."""
        if pnl_pct >= 0.1:
            return "TP"
        elif pnl_pct <= -0.1:
            return "SL"
        else:
            return "BE"

    # ── Persistence ───────────────────────────────────────────────

    def _save(self):
        """Persist journal to JSON file."""
        try:
            os.makedirs(os.path.dirname(self._data_path), exist_ok=True)
            data = {
                "initial_capital": self._initial_capital,
                "current_balance": self._current_balance,
                "peak_balance": self._peak_balance,
                "max_drawdown_pct": self._max_drawdown_pct,
                "max_drawdown_dollars": self._max_drawdown_dollars,
                "current_winning_streak": self._current_winning_streak,
                "max_winning_streak": self._max_winning_streak,
                "max_streak_pct": self._max_streak_pct,
                "trade_counter": self._trade_counter,
                "trades": self._trades,
            }
            with open(self._data_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Trade journal save failed: {e}")

    def _load(self):
        """Load journal from JSON file if it exists."""
        try:
            if os.path.exists(self._data_path):
                with open(self._data_path, "r") as f:
                    data = json.load(f)
                self._trades = data.get("trades", [])
                self._current_balance = data.get("current_balance", self._initial_capital)
                self._peak_balance = data.get("peak_balance", self._initial_capital)
                self._max_drawdown_pct = data.get("max_drawdown_pct", 0.0)
                self._max_drawdown_dollars = data.get("max_drawdown_dollars", 0.0)
                self._current_winning_streak = data.get("current_winning_streak", 0)
                self._max_winning_streak = data.get("max_winning_streak", 0)
                self._max_streak_pct = data.get("max_streak_pct", 0.0)
                self._trade_counter = data.get("trade_counter", len(self._trades))
                self._current_streak_pct = 0.0
                logger.info(
                    f"Trade journal loaded: {len(self._trades)} trades, "
                    f"balance=${self._current_balance:.2f}"
                )
        except Exception as e:
            logger.warning(f"Trade journal load failed (starting fresh): {e}")
            self._trades = []
