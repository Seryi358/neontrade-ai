"""
NeonTrade AI - Trade Journal
Implements the complete TradingLab trade tracking system from Registro de trades.xlsx.

Numeric fields (from Excel Registro_de_trades.xlsx):
- Month, Trade #, Date, Asset, $ P/L, % P&L
- Result classification: TP (>= +0.1%), SL (<= -0.1%), BE (between)
- Running balance, P&L accumulated from initial capital
- Maximum balance (peak), Drawdown %, Drawdown $
- Winning streak tracking, Max winning streak
- Win rate (total), Win rate excluding BE

Visual journaling fields (from 04_Avanzado/03_Documentación/02_Journaling):
- trading_style, timeframes_used, tp_price, management_notes
- screenshots (entry + exit + "now"), trade_summary, duration_minutes

ASR (Auto Self Review) fields (from 04_Avanzado/03_Documentación/03_ASR):
- Checklist: HTF correct, LTF correct, strategy correct, SL correct,
  TP correct, position management correct
- Would enter again, lessons learned
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
        self._missed_trades_path = os.path.join("data", "missed_trades.json")
        self._trades: List[Dict] = []
        self._missed_trades: List[Dict] = []
        self._current_balance = initial_capital
        self._peak_balance = initial_capital
        self._max_drawdown_pct = 0.0
        self._max_drawdown_dollars = 0.0
        self._current_winning_streak = 0
        self._max_winning_streak = 0
        self._max_streak_pct = 0.0  # cumulative % of the max winning streak
        self._current_losing_streak = 0
        self._max_losing_streak = 0
        self._max_losing_streak_pct = 0.0  # cumulative % of the max losing streak
        self._current_streak_pct = 0.0  # cumulative % of current winning streak
        self._current_losing_streak_pct = 0.0  # cumulative % of current losing streak
        self._trade_counter = 0
        self._accumulator = 1.0  # Compound growth tracker (Excel column O)
        self._dd_by_year: Dict[str, float] = {}  # year -> max DD that year
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
        is_discretionary: bool = False,
        discretionary_notes: str = "",
        open_time: Optional[str] = None,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        trading_style: str = "",
        timeframes_used: Optional[List[str]] = None,
        duration_minutes: Optional[float] = None,
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

        # Winning and losing streak tracking
        if result == "TP":
            self._current_winning_streak += 1
            self._current_losing_streak = 0
            self._current_losing_streak_pct = 0.0
            self._current_streak_pct += pnl_pct
            if self._current_winning_streak > self._max_winning_streak:
                self._max_winning_streak = self._current_winning_streak
                self._max_streak_pct = self._current_streak_pct
        elif result == "SL":
            self._current_losing_streak += 1
            self._current_winning_streak = 0
            self._current_streak_pct = 0.0
            self._current_losing_streak_pct += abs(pnl_pct)
            if self._current_losing_streak > self._max_losing_streak:
                self._max_losing_streak = self._current_losing_streak
                self._max_losing_streak_pct = self._current_losing_streak_pct
        else:
            # BE: reset both streaks
            self._current_winning_streak = 0
            self._current_streak_pct = 0.0
            self._current_losing_streak = 0
            self._current_losing_streak_pct = 0.0

        # P&L accumulated from initial capital
        pnl_accumulated_pct = (
            (self._current_balance - self._initial_capital)
            / self._initial_capital * 100
        ) if self._initial_capital > 0 else 0.0

        # Compound accumulator (Registro de trades.xlsx column O)
        self._accumulator = (pnl_pct / 100 * self._accumulator) + self._accumulator

        # Historical DD by year tracking
        year = now.strftime("%Y")
        if year not in self._dd_by_year:
            self._dd_by_year[year] = 0.0
        self._dd_by_year[year] = max(self._dd_by_year[year], abs(drawdown_pct))

        # Calculate R:R achieved if SL is provided
        rr_achieved = None
        if sl is not None and entry_price and exit_price:
            direction_upper = direction.upper()
            if direction_upper == "BUY" and sl < entry_price:
                risk = entry_price - sl
                if risk > 0:
                    rr_achieved = round((exit_price - entry_price) / risk, 4)
            elif direction_upper == "SELL" and sl > entry_price:
                risk = sl - entry_price
                if risk > 0:
                    rr_achieved = round((entry_price - exit_price) / risk, 4)

        trade_record = {
            "trade_number": self._trade_counter,
            "trade_id": trade_id,
            "open_time": open_time,
            "date": now.isoformat(),
            "month": now.strftime("%Y-%m"),
            "instrument": instrument,
            "direction": direction,
            "strategy": strategy,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "sl": sl,
            "tp": tp,
            "rr_achieved": rr_achieved,
            "pnl_dollars": round(pnl_dollars, 2),
            "pnl_pct": round(pnl_pct, 4),
            "result": result,
            "balance_after": round(self._current_balance, 2),
            "peak_balance": round(self._peak_balance, 2),
            "drawdown_pct": round(drawdown_pct, 4),
            "drawdown_dollars": round(drawdown_dollars, 2),
            "pnl_accumulated_pct": round(pnl_accumulated_pct, 4),
            "winning_streak": self._current_winning_streak,
            "accumulator": round(self._accumulator, 6),
            # ── Visual journaling fields (Documentación/02_Journaling) ───
            # Alex: "lo mínimo es explicar el estilo, las 4 temporalidades,
            # SL, TP, R:R, captura, gestión de la posición y resultado"
            "trading_style": trading_style,           # scalping/day/swing
            "timeframes_used": timeframes_used or [],  # e.g. ["D", "4H", "1H", "5M"]
            "duration_minutes": duration_minutes,      # how long the trade lasted
            "trade_summary": "",                       # 2-3 line written summary
            "management_notes": "",                    # how position was managed
            "screenshots": [],                         # paths/refs: entry, exit, "now"
            # ── Emotional journal fields (Psychology Manual - 3-moment journaling) ──
            "emotional_notes_pre": "",    # Before/during analysis
            "emotional_notes_during": "",  # While position is open
            "emotional_notes_post": "",    # After trade closes
            # ── Discretionary tracking (Trading Plan: 80% from backtesting/data) ──
            "is_discretionary": is_discretionary,
            "discretionary_notes": discretionary_notes,
            # ── ASR fields (Documentación/03_ASR) ───────────────────────
            # Alex: "análisis de temporalidad grande y pequeña correctos,
            # estrategia ejecutada correctamente, SL en su sitio, TP correcto,
            # gestión de la posición correcta, parte emocional, ¿volverías a entrar?"
            "asr_completed": False,
            "asr_htf_correct": None,            # Was HTF analysis correct?
            "asr_ltf_correct": None,            # Was LTF analysis correct?
            "asr_strategy_correct": None,       # Was strategy executed correctly?
            "asr_sl_correct": None,             # Was SL in correct position?
            "asr_tp_correct": None,             # Was TP in correct position?
            "asr_management_correct": None,     # Was position managed correctly?
            "asr_would_enter_again": None,      # Would you enter again?
            "asr_lessons": "",                  # Lessons/comments/points to note
            "asr_error_type": None,             # Error taxonomy (ASR Ponencia): PERCEPTION, TECHNICAL, ROUTINE, EMOTIONAL
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
                "current_losing_streak": 0,
                "max_losing_streak": 0,
                "max_losing_streak_pct": 0.0,
                "avg_win_pct": 0.0,
                "avg_loss_pct": 0.0,
                "profit_factor": 0.0,
                "monthly_returns": {},
                "pnl_accumulated_pct": 0.0,
                "accumulator": self._accumulator,
                "dd_by_year": self._dd_by_year,
                "discretionary_count": 0,
                "systematic_count": 0,
                "discretionary_ratio_pct": 0.0,
                "discretionary_win_rate": 0.0,
                "systematic_win_rate": 0.0,
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

        # Monthly returns and trade count
        monthly_returns: Dict[str, float] = {}
        monthly_start_balance: Dict[str, float] = {}
        monthly_trade_count: Dict[str, int] = {}
        for t in self._trades:
            month = t["month"]
            if month not in monthly_returns:
                monthly_returns[month] = 0.0
                # Find balance at start of month (balance before first trade of the month)
                monthly_start_balance[month] = t["balance_after"] - t["pnl_dollars"]
            monthly_returns[month] += t["pnl_dollars"]
            monthly_trade_count[month] = monthly_trade_count.get(month, 0) + 1

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

        # Discretionary vs systematic breakdown
        # (Trading Plan: 80% decisions based on backtesting and objective data)
        discretionary_trades = [
            t for t in self._trades if t.get("is_discretionary", False)
        ]
        systematic_trades = [
            t for t in self._trades if not t.get("is_discretionary", False)
        ]
        disc_count = len(discretionary_trades)
        sys_count = len(systematic_trades)
        discretionary_ratio_pct = (
            (disc_count / total * 100) if total > 0 else 0.0
        )

        disc_wins = [t for t in discretionary_trades if t["result"] == "TP"]
        disc_total_decisive = len([
            t for t in discretionary_trades if t["result"] in ("TP", "SL")
        ])
        discretionary_win_rate = (
            (len(disc_wins) / disc_total_decisive * 100)
            if disc_total_decisive > 0 else 0.0
        )

        sys_wins = [t for t in systematic_trades if t["result"] == "TP"]
        sys_total_decisive = len([
            t for t in systematic_trades if t["result"] in ("TP", "SL")
        ])
        systematic_win_rate = (
            (len(sys_wins) / sys_total_decisive * 100)
            if sys_total_decisive > 0 else 0.0
        )

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
            "current_losing_streak": self._current_losing_streak,
            "max_losing_streak": self._max_losing_streak,
            "max_losing_streak_pct": round(self._max_losing_streak_pct, 4),
            "avg_win_pct": round(avg_win_pct, 4),
            "avg_loss_pct": round(avg_loss_pct, 4),
            "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else 999.99,
            "monthly_returns": monthly_returns_pct,
            "monthly_trade_count": monthly_trade_count,
            "pnl_accumulated_pct": round(pnl_accumulated_pct, 4),
            "accumulator": round(self._accumulator, 6),  # Compound growth factor
            "dd_by_year": self._dd_by_year,
            "discretionary_count": disc_count,
            "systematic_count": sys_count,
            "discretionary_ratio_pct": round(discretionary_ratio_pct, 2),
            "discretionary_win_rate": round(discretionary_win_rate, 2),
            "systematic_win_rate": round(systematic_win_rate, 2),
        }

    # ── Trade History ─────────────────────────────────────────────

    def get_trades(self, limit: int = 50, offset: int = 0) -> list:
        """Return trade history with pagination, most recent first."""
        sorted_trades = list(reversed(self._trades))
        return sorted_trades[offset:offset + limit]

    # ── Discretionary Tracking ─────────────────────────────────────

    def mark_trade_discretionary(self, trade_id: str, notes: str = "") -> bool:
        """Mark a trade as discretionary with optional notes.

        Trading Plan objective: 80% decisions based on backtesting and objective data.
        Each discretionary decision should be annotated to analyze patterns.

        Args:
            trade_id: The unique trade identifier.
            notes: Explanation of why the discretionary decision was made.

        Returns:
            True if the trade was found and updated, False otherwise.
        """
        for trade in self._trades:
            if trade["trade_id"] == trade_id:
                trade["is_discretionary"] = True
                trade["discretionary_notes"] = notes
                self._save()
                logger.info(
                    f"Trade {trade_id} marked as discretionary"
                    f"{': ' + notes if notes else ''}"
                )
                return True
        logger.warning(f"Trade {trade_id} not found for discretionary marking")
        return False

    # ── Journal Notes Update ────────────────────────────────────────

    def update_journal_notes(
        self,
        trade_id: str,
        trade_summary: Optional[str] = None,
        management_notes: Optional[str] = None,
        screenshots: Optional[List[str]] = None,
        emotional_notes_pre: Optional[str] = None,
        emotional_notes_during: Optional[str] = None,
        emotional_notes_post: Optional[str] = None,
    ) -> bool:
        """Update visual journaling notes for a trade.

        Per TradingLab Journaling lesson: notes should be written ASAP
        after the trade to avoid emotional bias. Screenshots should include
        entry, exit, and optionally a "now" view for ASR context.
        """
        for trade in self._trades:
            if trade["trade_id"] == trade_id:
                if trade_summary is not None:
                    trade["trade_summary"] = trade_summary
                if management_notes is not None:
                    trade["management_notes"] = management_notes
                if screenshots is not None:
                    trade["screenshots"] = screenshots
                if emotional_notes_pre is not None:
                    trade["emotional_notes_pre"] = emotional_notes_pre
                if emotional_notes_during is not None:
                    trade["emotional_notes_during"] = emotional_notes_during
                if emotional_notes_post is not None:
                    trade["emotional_notes_post"] = emotional_notes_post

                # Freshness check: Alex recommends journaling "del mismo momento"
                freshness_warning = self._check_journal_freshness(trade)
                if freshness_warning:
                    trade["freshness_warning"] = freshness_warning

                self._save()
                logger.info(f"Journal notes updated for trade {trade_id}")
                return True
        logger.warning(f"Trade {trade_id} not found for journal notes update")
        return False

    # ── ASR (Auto Self Review) ────────────────────────────────────

    def update_asr(
        self,
        trade_id: str,
        htf_correct: Optional[bool] = None,
        ltf_correct: Optional[bool] = None,
        strategy_correct: Optional[bool] = None,
        sl_correct: Optional[bool] = None,
        tp_correct: Optional[bool] = None,
        management_correct: Optional[bool] = None,
        would_enter_again: Optional[bool] = None,
        lessons: Optional[str] = None,
        error_type: Optional[str] = None,  # ASR error taxonomy: PERCEPTION, TECHNICAL, ROUTINE, EMOTIONAL
    ) -> bool:
        """Fill in the ASR (Auto Self Review) checklist for a completed trade.

        Per TradingLab ASR lesson: should be done with emotional distance
        (not immediately after the trade). Evaluates execution quality
        AGAINST the trading plan, not against the trade result.

        Alex: "correcto o incorrecto no viene relacionado con el resultado
        del trade, viene relacionado con vuestro plan de trading"
        """
        for trade in self._trades:
            if trade["trade_id"] == trade_id:
                if htf_correct is not None:
                    trade["asr_htf_correct"] = htf_correct
                if ltf_correct is not None:
                    trade["asr_ltf_correct"] = ltf_correct
                if strategy_correct is not None:
                    trade["asr_strategy_correct"] = strategy_correct
                if sl_correct is not None:
                    trade["asr_sl_correct"] = sl_correct
                if tp_correct is not None:
                    trade["asr_tp_correct"] = tp_correct
                if management_correct is not None:
                    trade["asr_management_correct"] = management_correct
                if would_enter_again is not None:
                    trade["asr_would_enter_again"] = would_enter_again
                if lessons is not None:
                    trade["asr_lessons"] = lessons
                if error_type is not None:
                    trade["asr_error_type"] = error_type
                trade["asr_completed"] = True

                # Freshness check: Alex recommends journaling "del mismo momento"
                freshness_warning = self._check_journal_freshness(trade)
                if freshness_warning:
                    trade["freshness_warning"] = freshness_warning

                self._save()
                logger.info(f"ASR completed for trade {trade_id}")
                return True
        logger.warning(f"Trade {trade_id} not found for ASR update")
        return False

    def get_asr_stats(self) -> dict:
        """Return ASR completion statistics.

        Proceso de Revisión: "cada vez que ejecuto un trade, lo anoto en el Journaling"
        and unusual situations get "un ASR intenso".
        """
        total = len(self._trades)
        if total == 0:
            return {"total": 0, "asr_completed": 0, "asr_completion_rate": 0.0}

        completed = sum(1 for t in self._trades if t.get("asr_completed", False))

        # Count how many ASR checklists had all items correct
        perfect_asr = 0
        checklist_fields = [
            "asr_htf_correct", "asr_ltf_correct", "asr_strategy_correct",
            "asr_sl_correct", "asr_tp_correct", "asr_management_correct",
        ]
        for t in self._trades:
            if t.get("asr_completed"):
                all_correct = all(
                    t.get(f) is True for f in checklist_fields
                )
                if all_correct:
                    perfect_asr += 1

        return {
            "total": total,
            "asr_completed": completed,
            "asr_completion_rate": round(completed / total * 100, 1),
            "perfect_execution_count": perfect_asr,
            "perfect_execution_rate": round(
                perfect_asr / completed * 100, 1
            ) if completed > 0 else 0.0,
        }

    # ── Missed Trades (Trades Not Taken) ─────────────────────────
    # Mentorship: reviewing missed opportunities is key for improvement.
    # Alex emphasizes analyzing setups you SAW but did NOT take,
    # and understanding why — fear, hesitation, filter too strict, etc.

    def record_missed_trade(
        self,
        instrument: str,
        strategy: str,
        direction: str,
        confidence: float,
        reason_skipped: str,
        timestamp: Optional[str] = None,
    ):
        """Record a setup that was detected but not executed.

        The mentorship emphasizes reviewing missed opportunities to identify
        patterns of hesitation, over-filtering, or fear. Each missed trade
        should include why it was skipped so the trader can review whether
        the skip was justified or a behavioral issue.

        Args:
            instrument: The trading pair (e.g. "EUR_USD", "BTC_USD").
            strategy: Strategy that generated the signal (e.g. "BLUE_A", "GREEN").
            direction: "BUY" or "SELL".
            confidence: Signal confidence score (0.0 - 1.0).
            reason_skipped: Why the trade was not taken (e.g. "news filter",
                "low confidence", "max positions reached", "manual skip").
            timestamp: ISO timestamp; defaults to current UTC time.
        """
        now = timestamp or datetime.now(timezone.utc).isoformat()
        record = {
            "timestamp": now,
            "instrument": instrument,
            "strategy": strategy,
            "direction": direction,
            "confidence": round(confidence, 4),
            "reason_skipped": reason_skipped,
        }
        self._missed_trades.append(record)
        self._save_missed_trades()

        logger.info(
            f"Missed trade recorded: {instrument} {direction} ({strategy}) "
            f"confidence={confidence:.2f} — reason: {reason_skipped}"
        )

    def get_missed_trades(self, limit: int = 50, offset: int = 0) -> List[Dict]:
        """Retrieve missed trades, most recent first.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip (for pagination).

        Returns:
            List of missed trade records.
        """
        sorted_missed = list(reversed(self._missed_trades))
        return sorted_missed[offset:offset + limit]

    def get_missed_trade_stats(self) -> Dict:
        """Return statistics on missed trades for self-review.

        Helps identify patterns: are you skipping too many trades?
        Are the skipped trades winning? (requires manual follow-up marking)
        """
        total = len(self._missed_trades)
        if total == 0:
            return {"total_missed": 0, "by_reason": {}, "by_strategy": {}}

        by_reason: Dict[str, int] = {}
        by_strategy: Dict[str, int] = {}
        for mt in self._missed_trades:
            reason = mt.get("reason_skipped", "unknown")
            by_reason[reason] = by_reason.get(reason, 0) + 1
            strat = mt.get("strategy", "unknown")
            by_strategy[strat] = by_strategy.get(strat, 0) + 1

        return {
            "total_missed": total,
            "by_reason": by_reason,
            "by_strategy": by_strategy,
        }

    def _save_missed_trades(self):
        """Persist missed trades to a separate JSON file."""
        try:
            dir_name = os.path.dirname(self._missed_trades_path)
            os.makedirs(dir_name, exist_ok=True)
            import tempfile
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(self._missed_trades, f, indent=2)
                os.replace(tmp_path, self._missed_trades_path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except Exception as e:
            logger.error(f"Missed trades save failed: {e}")

    def _load_missed_trades(self):
        """Load missed trades from JSON file if it exists."""
        try:
            if os.path.exists(self._missed_trades_path):
                with open(self._missed_trades_path, "r") as f:
                    self._missed_trades = json.load(f)
                logger.info(f"Loaded {len(self._missed_trades)} missed trade records")
        except Exception as e:
            logger.warning(f"Missed trades load failed: {e}")
            self._missed_trades = []

    # ── Freshness Check ────────────────────────────────────────────

    def _check_journal_freshness(self, trade: Dict) -> Optional[str]:
        """Check if journaling is happening too long after the trade closed.

        Alex recommends writing notes 'del mismo momento' to avoid emotional
        bias and revisionist thinking. If the trade closed more than 24 hours
        ago, return a warning message.

        Args:
            trade: The trade record dict (must have 'date' key with ISO timestamp).

        Returns:
            Warning string if stale, None if fresh.
        """
        close_time_str = trade.get("date")
        if not close_time_str:
            return None

        try:
            close_time = datetime.fromisoformat(close_time_str)
            # Ensure timezone-aware comparison
            if close_time.tzinfo is None:
                close_time = close_time.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            elapsed = now - close_time
            if elapsed.total_seconds() > 86400:  # 24 hours
                return (
                    "Journaling mas de 24h despues del cierre. "
                    "Alex recomienda escribir notas 'del mismo momento' "
                    "para evitar sesgo emocional."
                )
        except (ValueError, TypeError):
            pass

        return None

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
        """Persist journal to JSON file (atomic write to prevent corruption)."""
        try:
            dir_name = os.path.dirname(self._data_path)
            os.makedirs(dir_name, exist_ok=True)
            data = {
                "initial_capital": self._initial_capital,
                "current_balance": self._current_balance,
                "peak_balance": self._peak_balance,
                "max_drawdown_pct": self._max_drawdown_pct,
                "max_drawdown_dollars": self._max_drawdown_dollars,
                "current_winning_streak": self._current_winning_streak,
                "max_winning_streak": self._max_winning_streak,
                "max_streak_pct": self._max_streak_pct,
                "current_losing_streak": self._current_losing_streak,
                "max_losing_streak": self._max_losing_streak,
                "max_losing_streak_pct": self._max_losing_streak_pct,
                "current_streak_pct": self._current_streak_pct,
                "current_losing_streak_pct": self._current_losing_streak_pct,
                "trade_counter": self._trade_counter,
                "accumulator": self._accumulator,
                "dd_by_year": self._dd_by_year,
                "trades": self._trades,
            }
            import tempfile
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(data, f, indent=2)
                os.replace(tmp_path, self._data_path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except Exception as e:
            logger.error(f"Trade journal save failed: {e}")

    def _load(self):
        """Load journal from JSON file if it exists."""
        try:
            if os.path.exists(self._data_path):
                with open(self._data_path, "r") as f:
                    data = json.load(f)
                self._trades = data.get("trades", [])
                # Backfill fields for trades saved before these features
                for trade in self._trades:
                    trade.setdefault("is_discretionary", False)
                    trade.setdefault("discretionary_notes", "")
                    trade.setdefault("open_time", None)
                    trade.setdefault("rr_achieved", None)
                    trade.setdefault("sl", None)
                    trade.setdefault("tp", None)
                    # Visual journaling fields
                    trade.setdefault("trading_style", "")
                    trade.setdefault("timeframes_used", [])
                    trade.setdefault("duration_minutes", None)
                    trade.setdefault("trade_summary", "")
                    trade.setdefault("management_notes", "")
                    trade.setdefault("screenshots", [])
                    # ASR fields
                    trade.setdefault("asr_completed", False)
                    trade.setdefault("asr_htf_correct", None)
                    trade.setdefault("asr_ltf_correct", None)
                    trade.setdefault("asr_strategy_correct", None)
                    trade.setdefault("asr_sl_correct", None)
                    trade.setdefault("asr_tp_correct", None)
                    trade.setdefault("asr_management_correct", None)
                    trade.setdefault("asr_would_enter_again", None)
                    trade.setdefault("asr_lessons", "")
                    trade.setdefault("asr_error_type", None)
                self._current_balance = data.get("current_balance", self._initial_capital)
                self._peak_balance = data.get("peak_balance", self._initial_capital)
                self._max_drawdown_pct = data.get("max_drawdown_pct", 0.0)
                self._max_drawdown_dollars = data.get("max_drawdown_dollars", 0.0)
                self._current_winning_streak = data.get("current_winning_streak", 0)
                self._max_winning_streak = data.get("max_winning_streak", 0)
                self._max_streak_pct = data.get("max_streak_pct", 0.0)
                self._current_losing_streak = data.get("current_losing_streak", 0)
                self._max_losing_streak = data.get("max_losing_streak", 0)
                self._max_losing_streak_pct = data.get("max_losing_streak_pct", 0.0)
                self._trade_counter = data.get("trade_counter", len(self._trades))
                self._accumulator = data.get("accumulator", 1.0)
                self._dd_by_year = data.get("dd_by_year", {})
                self._current_streak_pct = data.get("current_streak_pct", 0.0)
                self._current_losing_streak_pct = data.get("current_losing_streak_pct", 0.0)
                logger.info(
                    f"Trade journal loaded: {len(self._trades)} trades, "
                    f"balance=${self._current_balance:.2f}"
                )
        except Exception as e:
            logger.warning(f"Trade journal load failed (starting fresh): {e}")
            self._trades = []

        # Load missed trades from separate file
        self._load_missed_trades()
