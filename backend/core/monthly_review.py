"""
NeonTrade AI - Monthly Review Generator
Trading Plan: "Mensualmente: revisar todos los trades ejecutados y conclusiones para optimización"

Generates comprehensive monthly reports with:
- Performance summary (P&L, win rate, drawdown)
- By-strategy breakdown (which strategies performed best/worst)
- By-instrument breakdown
- By-day-of-week analysis
- By-session analysis (London vs NY)
- Discretionary vs systematic trade comparison
- Emotional pattern analysis (from journal notes)
- Risk management review (DD levels hit, delta adjustments)
- Recommendations for next month
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from loguru import logger
import json
import os


@dataclass
class MonthlyReport:
    """Complete monthly review report."""
    month: str  # "2024-03"
    generated_at: str

    # Summary
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    be_trades: int = 0
    win_rate: float = 0.0
    win_rate_excl_be: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_pnl: float = 0.0
    net_pnl_pct: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    best_trade_pnl: float = 0.0
    worst_trade_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_rr_achieved: float = 0.0
    max_winning_streak: int = 0
    max_losing_streak: int = 0

    # By strategy
    by_strategy: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # by_strategy = {"BLUE": {"trades": 5, "wins": 3, "pnl": 120.5, "win_rate": 0.6}, ...}

    # By instrument
    by_instrument: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # By day of week
    by_day_of_week: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # by_day_of_week = {"Monday": {"trades": 3, "pnl": 50.0}, ...}

    # By session
    by_session: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # by_session = {"London": {"trades": 5, "pnl": 80}, "New York": {"trades": 3, "pnl": 40}}

    # Discretionary analysis
    discretionary_trades: int = 0
    discretionary_win_rate: float = 0.0
    systematic_trades: int = 0
    systematic_win_rate: float = 0.0
    discretionary_notes_summary: List[str] = field(default_factory=list)

    # Emotional patterns
    emotional_patterns: List[str] = field(default_factory=list)
    # e.g., ["Trades taken while stressed had 30% lower win rate", ...]

    # ASR (Auto Self Review) completion
    asr_completed_count: int = 0
    asr_completion_rate: float = 0.0
    asr_perfect_execution_count: int = 0
    asr_common_errors: List[str] = field(default_factory=list)

    # Risk management
    dd_levels_hit: List[str] = field(default_factory=list)
    delta_adjustments: int = 0
    correlated_trades_count: int = 0
    max_simultaneous_risk: float = 0.0

    # Recommendations
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to serializable dict."""
        import dataclasses
        return dataclasses.asdict(self)


class MonthlyReviewGenerator:
    """Generates comprehensive monthly trading reviews."""

    # Keywords indicating negative emotional states
    NEGATIVE_EMOTION_KEYWORDS = [
        "stressed", "anxious", "frustrated", "angry", "revenge",
        "fomo", "fear", "impatient", "tired", "bored",
        "overconfident", "greedy", "desperate", "nervous",
    ]

    # Keywords indicating positive/neutral emotional states
    POSITIVE_EMOTION_KEYWORDS = [
        "calm", "focused", "confident", "disciplined", "patient",
        "clear", "prepared", "relaxed",
    ]

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.reports_dir = os.path.join(data_dir, "monthly_reports")
        os.makedirs(self.reports_dir, exist_ok=True)

    def generate_report(
        self,
        trades: List[Dict],
        month: str,
        balance_start: float = 0,
        balance_end: float = 0,
    ) -> MonthlyReport:
        """
        Generate a complete monthly report from trade records.

        Args:
            trades: List of trade dicts from TradeJournal.
                    Expected keys per trade: pnl, pnl_pct, result ("TP"/"SL"/"BE"),
                    strategy, instrument, open_time/timestamp, is_discretionary,
                    discretionary_notes, emotional_notes_pre, emotional_notes_post,
                    rr_achieved, dd_level_hit, delta_adjustment, correlated_pair.
            month: "YYYY-MM" format
            balance_start: Balance at start of month
            balance_end: Balance at end of month

        Returns:
            MonthlyReport with all computed metrics and recommendations.
        """
        report = MonthlyReport(
            month=month,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        if not trades:
            report.recommendations.append(
                "No trades executed this month. Review if trading plan conditions were met."
            )
            self._save_report(report)
            return report

        # ── Accumulators for emotional analysis ───────────────────────────
        emotional_entries: List[Dict[str, Any]] = []
        # Each entry: {"pre": str, "post": str, "pnl_pct": float, "result": str}

        rr_values: List[float] = []

        # ── Main iteration over trades ────────────────────────────────────
        report.total_trades = len(trades)

        for trade in trades:
            pnl = trade.get("pnl_dollars", trade.get("pnl", 0.0)) or 0.0
            pnl_pct = trade.get("pnl_pct", 0.0) or 0.0
            result = trade.get("result", "")
            strategy = trade.get("strategy", "UNKNOWN")
            instrument = trade.get("instrument", "UNKNOWN")

            # ── Win / Loss / BE classification ────────────────────────────
            is_win = result == "TP" or pnl_pct >= 0.1
            is_loss = result == "SL" or pnl_pct <= -0.1

            if is_win:
                report.winning_trades += 1
                report.gross_profit += pnl
            elif is_loss:
                report.losing_trades += 1
                report.gross_loss += abs(pnl)
            else:
                report.be_trades += 1

            # ── Best / worst trade ────────────────────────────────────────
            if pnl > report.best_trade_pnl:
                report.best_trade_pnl = pnl
            if pnl < report.worst_trade_pnl:
                report.worst_trade_pnl = pnl

            # ── R:R achieved ──────────────────────────────────────────────
            rr = trade.get("rr_achieved")
            if rr is not None:
                rr_values.append(float(rr))

            # ── By strategy ───────────────────────────────────────────────
            if strategy not in report.by_strategy:
                report.by_strategy[strategy] = {
                    "trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "be": 0,
                    "pnl": 0.0,
                    "pnl_pct": 0.0,
                }
            strat = report.by_strategy[strategy]
            strat["trades"] += 1
            strat["pnl"] += pnl
            strat["pnl_pct"] += pnl_pct
            if is_win:
                strat["wins"] += 1
            elif is_loss:
                strat["losses"] += 1
            else:
                strat["be"] += 1

            # ── By instrument ─────────────────────────────────────────────
            if instrument not in report.by_instrument:
                report.by_instrument[instrument] = {
                    "trades": 0,
                    "wins": 0,
                    "pnl": 0.0,
                }
            inst = report.by_instrument[instrument]
            inst["trades"] += 1
            inst["pnl"] += pnl
            if is_win:
                inst["wins"] += 1

            # ── By day of week ────────────────────────────────────────────
            trade_date = trade.get("open_time") or trade.get("date", trade.get("timestamp", ""))
            day_name = self._get_day_name(trade_date)
            if day_name:
                if day_name not in report.by_day_of_week:
                    report.by_day_of_week[day_name] = {
                        "trades": 0,
                        "wins": 0,
                        "pnl": 0.0,
                    }
                dow = report.by_day_of_week[day_name]
                dow["trades"] += 1
                dow["pnl"] += pnl
                if is_win:
                    dow["wins"] += 1

            # ── By session (London 07-15 UTC, NY 13-21 UTC) ──────────────
            session = self._get_session(trade_date)
            if session:
                if session not in report.by_session:
                    report.by_session[session] = {
                        "trades": 0,
                        "wins": 0,
                        "pnl": 0.0,
                    }
                sess = report.by_session[session]
                sess["trades"] += 1
                sess["pnl"] += pnl
                if is_win:
                    sess["wins"] += 1

            # ── Discretionary tracking ────────────────────────────────────
            is_discretionary = trade.get("is_discretionary", False)
            if is_discretionary:
                report.discretionary_trades += 1
                notes = trade.get("discretionary_notes", "")
                if notes:
                    report.discretionary_notes_summary.append(notes)
            else:
                report.systematic_trades += 1

            # ── Emotional data collection ─────────────────────────────────
            emotional_pre = trade.get("emotional_notes_pre", "") or ""
            emotional_post = trade.get("emotional_notes_post", "") or ""
            if emotional_pre or emotional_post:
                emotional_entries.append(
                    {
                        "pre": emotional_pre,
                        "post": emotional_post,
                        "pnl_pct": pnl_pct,
                        "is_win": is_win,
                        "is_loss": is_loss,
                    }
                )

            # ── Risk management data ──────────────────────────────────────
            dd_hit = trade.get("dd_level_hit")
            if dd_hit:
                report.dd_levels_hit.append(str(dd_hit))

            if trade.get("delta_adjustment"):
                report.delta_adjustments += 1

            if trade.get("correlated_pair"):
                report.correlated_trades_count += 1

            sim_risk = trade.get("simultaneous_risk", 0.0)
            if sim_risk and sim_risk > report.max_simultaneous_risk:
                report.max_simultaneous_risk = sim_risk

        # ── ASR completion analysis ──────────────────────────────────────
        asr_error_counts: Dict[str, int] = {
            "HTF analysis": 0,
            "LTF analysis": 0,
            "Strategy execution": 0,
            "SL placement": 0,
            "TP placement": 0,
            "Position management": 0,
        }
        asr_field_map = {
            "asr_htf_correct": "HTF analysis",
            "asr_ltf_correct": "LTF analysis",
            "asr_strategy_correct": "Strategy execution",
            "asr_sl_correct": "SL placement",
            "asr_tp_correct": "TP placement",
            "asr_management_correct": "Position management",
        }
        for trade in trades:
            if trade.get("asr_completed"):
                report.asr_completed_count += 1
                all_correct = True
                for field_name, label in asr_field_map.items():
                    if trade.get(field_name) is False:
                        asr_error_counts[label] += 1
                        all_correct = False
                if all_correct:
                    report.asr_perfect_execution_count += 1

        if report.total_trades > 0:
            report.asr_completion_rate = (
                report.asr_completed_count / report.total_trades
            )

        # Surface most common ASR errors
        for label, count in sorted(
            asr_error_counts.items(), key=lambda x: x[1], reverse=True
        ):
            if count > 0:
                report.asr_common_errors.append(
                    f"{label}: {count} error(s) in "
                    f"{report.asr_completed_count} reviewed trades"
                )

        # ── Derived summary metrics ───────────────────────────────────────
        total_decided = report.winning_trades + report.losing_trades
        if total_decided > 0:
            report.win_rate_excl_be = report.winning_trades / total_decided
        if report.total_trades > 0:
            report.win_rate = report.winning_trades / report.total_trades
        if report.gross_loss > 0:
            report.profit_factor = report.gross_profit / report.gross_loss
        report.net_pnl = report.gross_profit - report.gross_loss
        if balance_start > 0:
            report.net_pnl_pct = (report.net_pnl / balance_start) * 100
        if report.winning_trades > 0:
            report.avg_win = report.gross_profit / report.winning_trades
        if report.losing_trades > 0:
            report.avg_loss = report.gross_loss / report.losing_trades
        if rr_values:
            report.avg_rr_achieved = sum(rr_values) / len(rr_values)

        # ── Max drawdown from equity curve ────────────────────────────────
        report.max_drawdown_pct = self._calculate_max_drawdown(trades, balance_start)

        # ── Win rates per breakdown group ─────────────────────────────────
        for group in [
            report.by_strategy,
            report.by_instrument,
            report.by_day_of_week,
            report.by_session,
        ]:
            for _key, data in group.items():
                if data["trades"] > 0:
                    data["win_rate"] = data["wins"] / data["trades"]

        # ── Discretionary vs systematic win rates ─────────────────────────
        disc_wins = sum(
            1
            for t in trades
            if t.get("is_discretionary")
            and (t.get("result") == "TP" or (t.get("pnl_pct", 0) or 0) >= 0.1)
        )
        if report.discretionary_trades > 0:
            report.discretionary_win_rate = disc_wins / report.discretionary_trades

        sys_wins = sum(
            1
            for t in trades
            if not t.get("is_discretionary")
            and (t.get("result") == "TP" or (t.get("pnl_pct", 0) or 0) >= 0.1)
        )
        if report.systematic_trades > 0:
            report.systematic_win_rate = sys_wins / report.systematic_trades

        # ── Streaks ───────────────────────────────────────────────────────
        report.max_winning_streak, report.max_losing_streak = self._calculate_streaks(
            trades
        )

        # ── Emotional pattern analysis ────────────────────────────────────
        report.emotional_patterns = self._analyze_emotional_patterns(emotional_entries)

        # ── Generate recommendations ──────────────────────────────────────
        report.recommendations = self._generate_recommendations(report)

        # ── Persist ───────────────────────────────────────────────────────
        self._save_report(report)

        logger.info(
            f"Monthly report generated for {month}: "
            f"{report.total_trades} trades, net P&L ${report.net_pnl:.2f}, "
            f"win rate {report.win_rate:.1%}"
        )

        return report

    # ──────────────────────────────────────────────────────────────────────
    # Helper: timestamp parsing
    # ──────────────────────────────────────────────────────────────────────

    def _parse_timestamp(self, ts: Any) -> Optional[datetime]:
        """Parse a variety of timestamp formats into a datetime object."""
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, str) and ts.strip():
            # Try Python's built-in ISO parser first (handles +00:00, Z, etc.)
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
            # Fallback to manual format parsing
            formats = [
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(ts[:26], fmt)
                except (ValueError, IndexError):
                    continue
        if isinstance(ts, (int, float)):
            try:
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            except (OSError, ValueError, OverflowError):
                pass
        return None

    def _get_day_name(self, timestamp: Any) -> str:
        """Return the English weekday name for *timestamp*."""
        dt = self._parse_timestamp(timestamp)
        if dt:
            return dt.strftime("%A")  # Monday, Tuesday, etc.
        return ""

    def _get_session(self, timestamp: Any) -> str:
        """Classify the timestamp into a trading session."""
        dt = self._parse_timestamp(timestamp)
        if dt:
            hour = dt.hour
            if 7 <= hour < 13:
                return "London"
            elif 13 <= hour < 21:
                return "New York"
            else:
                return "Off-Hours"
        return ""

    # ──────────────────────────────────────────────────────────────────────
    # Helper: streaks
    # ──────────────────────────────────────────────────────────────────────

    def _calculate_streaks(self, trades: List[Dict]):
        """Return (max_winning_streak, max_losing_streak)."""
        max_win, max_loss = 0, 0
        cur_win, cur_loss = 0, 0
        for t in trades:
            pnl_pct = t.get("pnl_pct", 0) or 0
            if pnl_pct >= 0.1:
                cur_win += 1
                cur_loss = 0
                max_win = max(max_win, cur_win)
            elif pnl_pct <= -0.1:
                cur_loss += 1
                cur_win = 0
                max_loss = max(max_loss, cur_loss)
            else:
                cur_win = 0
                cur_loss = 0
        return max_win, max_loss

    # ──────────────────────────────────────────────────────────────────────
    # Helper: max drawdown
    # ──────────────────────────────────────────────────────────────────────

    def _calculate_max_drawdown(
        self, trades: List[Dict], balance_start: float
    ) -> float:
        """
        Calculate maximum drawdown percentage from the trade sequence.

        Walks the equity curve built from cumulative PnL and finds the
        largest peak-to-trough decline as a percentage of the peak.
        """
        if not trades:
            return 0.0

        # Build equity curve
        equity = balance_start if balance_start > 0 else 10_000.0  # fallback
        peak = equity
        max_dd_pct = 0.0

        for t in trades:
            pnl = t.get("pnl_dollars", t.get("pnl", 0.0)) or 0.0
            equity += pnl
            if equity > peak:
                peak = equity
            if peak > 0:
                dd_pct = ((peak - equity) / peak) * 100
                if dd_pct > max_dd_pct:
                    max_dd_pct = dd_pct

        return round(max_dd_pct, 2)

    # ──────────────────────────────────────────────────────────────────────
    # Helper: emotional pattern analysis
    # ──────────────────────────────────────────────────────────────────────

    def _analyze_emotional_patterns(
        self, entries: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Detect patterns between emotional state and trade outcomes.

        Looks at pre-trade emotional notes and correlates with win/loss.
        """
        patterns: List[str] = []

        if not entries:
            return patterns

        # Split trades by detected emotional tone
        negative_trades: List[Dict] = []
        positive_trades: List[Dict] = []

        for entry in entries:
            text = (entry.get("pre", "") + " " + entry.get("post", "")).lower()
            has_negative = any(kw in text for kw in self.NEGATIVE_EMOTION_KEYWORDS)
            has_positive = any(kw in text for kw in self.POSITIVE_EMOTION_KEYWORDS)

            if has_negative:
                negative_trades.append(entry)
            elif has_positive:
                positive_trades.append(entry)

        # Compare win rates
        if len(negative_trades) >= 2:
            neg_wins = sum(1 for e in negative_trades if e["is_win"])
            neg_wr = neg_wins / len(negative_trades) if negative_trades else 0
            patterns.append(
                f"Trades with negative emotions: {len(negative_trades)} trades, "
                f"{neg_wr:.0%} win rate."
            )

        if len(positive_trades) >= 2:
            pos_wins = sum(1 for e in positive_trades if e["is_win"])
            pos_wr = pos_wins / len(positive_trades) if positive_trades else 0
            patterns.append(
                f"Trades with positive/calm emotions: {len(positive_trades)} trades, "
                f"{pos_wr:.0%} win rate."
            )

        if len(negative_trades) >= 2 and len(positive_trades) >= 2:
            neg_wr = sum(1 for e in negative_trades if e["is_win"]) / len(
                negative_trades
            )
            pos_wr = sum(1 for e in positive_trades if e["is_win"]) / len(
                positive_trades
            )
            diff = pos_wr - neg_wr
            if diff > 0.05:
                patterns.append(
                    f"Positive emotional state correlated with {diff:.0%} higher win rate."
                )
            elif diff < -0.05:
                patterns.append(
                    f"Unexpectedly, negative emotional state correlated with "
                    f"{abs(diff):.0%} higher win rate. Investigate further."
                )

        # Detect revenge trading pattern (multiple losses followed by more losses)
        revenge_count = 0
        for entry in entries:
            text = (entry.get("pre", "") + " " + entry.get("post", "")).lower()
            if "revenge" in text:
                revenge_count += 1
        if revenge_count > 0:
            patterns.append(
                f"Revenge trading detected in {revenge_count} trade(s). "
                f"This is a high-risk behaviour to eliminate."
            )

        # Detect FOMO
        fomo_count = sum(
            1
            for e in entries
            if "fomo" in (e.get("pre", "") + " " + e.get("post", "")).lower()
        )
        if fomo_count > 0:
            fomo_losses = sum(
                1
                for e in entries
                if "fomo" in (e.get("pre", "") + " " + e.get("post", "")).lower()
                and e["is_loss"]
            )
            patterns.append(
                f"FOMO mentioned in {fomo_count} trade(s), "
                f"{fomo_losses} of which were losses."
            )

        return patterns

    # ──────────────────────────────────────────────────────────────────────
    # Recommendations engine
    # ──────────────────────────────────────────────────────────────────────

    def _generate_recommendations(self, report: MonthlyReport) -> List[str]:
        """Generate actionable recommendations from the report data."""
        recs: List[str] = []

        # Win rate analysis
        if report.win_rate_excl_be < 0.50:
            recs.append(
                "Win rate below 50%. Review entry criteria and confluence requirements."
            )
        elif report.win_rate_excl_be >= 0.65:
            recs.append(
                "Excellent win rate! Consider if risk can be slightly increased "
                "via Delta algorithm."
            )

        # Best / worst strategy
        if report.by_strategy:
            best = max(
                report.by_strategy.items(), key=lambda x: x[1].get("pnl", 0)
            )
            worst = min(
                report.by_strategy.items(), key=lambda x: x[1].get("pnl", 0)
            )
            if best[1]["pnl"] > 0:
                recs.append(
                    f"Best performing strategy: {best[0]} "
                    f"(P&L: ${best[1]['pnl']:.2f}). Focus on similar setups."
                )
            if worst[1]["pnl"] < 0:
                recs.append(
                    f"Worst performing strategy: {worst[0]} "
                    f"(P&L: ${worst[1]['pnl']:.2f}). "
                    f"Review if conditions are being met strictly."
                )

        # Day analysis
        if report.by_day_of_week:
            worst_day = min(
                report.by_day_of_week.items(), key=lambda x: x[1].get("pnl", 0)
            )
            if worst_day[1]["pnl"] < 0:
                recs.append(
                    f"Worst day: {worst_day[0]}. "
                    f"Consider reducing exposure on this day."
                )

        # Session analysis
        if report.by_session:
            best_session = max(
                report.by_session.items(), key=lambda x: x[1].get("pnl", 0)
            )
            recs.append(
                f"Best session: {best_session[0]} "
                f"({best_session[1]['trades']} trades, "
                f"${best_session[1]['pnl']:.2f})."
            )

        # Discretionary vs systematic
        if report.discretionary_trades > 0 and report.systematic_trades > 0:
            if report.discretionary_win_rate < report.systematic_win_rate - 0.1:
                recs.append(
                    "Discretionary trades underperforming systematic ones. "
                    "Stick more closely to the system."
                )
            elif report.discretionary_win_rate > report.systematic_win_rate + 0.1:
                recs.append(
                    "Discretionary decisions adding value. "
                    "Document the patterns for future integration."
                )

        # Profit factor
        if 0 < report.profit_factor < 1.2:
            recs.append(
                "Profit factor is thin. Tighten SL or improve entry timing "
                "to increase average win."
            )

        # Drawdown
        if report.max_drawdown_pct > 5.0:
            recs.append(
                f"Max drawdown reached {report.max_drawdown_pct:.1f}%. "
                f"Review risk sizing and consider using Fixed Levels method."
            )

        # Losing streak warning
        if report.max_losing_streak >= 4:
            recs.append(
                f"Max losing streak of {report.max_losing_streak} trades. "
                f"Ensure the DD protection protocol pauses trading after 3 "
                f"consecutive losses as per the plan."
            )

        # Emotional patterns
        if report.emotional_patterns:
            for pattern in report.emotional_patterns:
                if "revenge" in pattern.lower():
                    recs.append(
                        "Eliminate revenge trading. Add a mandatory cooldown "
                        "period after losses."
                    )
                    break

        # ASR completion
        if report.asr_completion_rate < 0.80 and report.total_trades >= 3:
            recs.append(
                f"ASR completion rate is {report.asr_completion_rate:.0%}. "
                f"Alex: 'si no haces ASR no vas a poder revisar y encontrar "
                f"esos errores'. Review every trade."
            )
        if report.asr_common_errors:
            top_error = report.asr_common_errors[0]
            recs.append(
                f"Most common execution error: {top_error}. "
                f"Focus ASR sessions on this area."
            )

        # Correlated trades
        if report.correlated_trades_count > 3:
            recs.append(
                f"{report.correlated_trades_count} correlated trades detected. "
                f"Review exposure limits for correlated instruments."
            )

        # Average R:R
        if report.avg_rr_achieved > 0 and report.avg_rr_achieved < 1.0:
            recs.append(
                f"Average R:R achieved is {report.avg_rr_achieved:.2f}. "
                f"Consider holding winners longer or tightening stop losses."
            )

        if not recs:
            recs.append(
                "Solid month! Continue following the Trading Plan consistently."
            )

        return recs

    # ──────────────────────────────────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────────────────────────────────

    def _save_report(self, report: MonthlyReport) -> None:
        """Persist the report as a JSON file."""
        path = os.path.join(self.reports_dir, f"review_{report.month}.json")
        try:
            with open(path, "w") as f:
                json.dump(report.to_dict(), f, indent=2, default=str)
            logger.info(f"Monthly report saved: {path}")
        except Exception as e:
            logger.error(f"Failed to save monthly report: {e}")

    def load_report(self, month: str) -> Optional[Dict]:
        """Load a previously saved monthly report."""
        path = os.path.join(self.reports_dir, f"review_{month}.json")
        if os.path.exists(path):
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load report {path}: {e}")
        return None

    def list_reports(self) -> List[str]:
        """List available monthly reports (returns list of 'YYYY-MM' strings)."""
        reports: List[str] = []
        if os.path.exists(self.reports_dir):
            for f in sorted(os.listdir(self.reports_dir)):
                if f.startswith("review_") and f.endswith(".json"):
                    reports.append(f.replace("review_", "").replace(".json", ""))
        return reports

    # ──────────────────────────────────────────────────────────────────────
    # Text report generation
    # ──────────────────────────────────────────────────────────────────────

    def format_text_report(self, report: MonthlyReport) -> str:
        """
        Format a MonthlyReport into a human-readable text summary.

        Useful for logging, Telegram notifications, or console output.
        """
        lines: List[str] = []
        sep = "=" * 60

        lines.append(sep)
        lines.append(f"  MONTHLY TRADING REVIEW - {report.month}")
        lines.append(f"  Generated: {report.generated_at}")
        lines.append(sep)

        # Performance summary
        lines.append("")
        lines.append("--- PERFORMANCE SUMMARY ---")
        lines.append(f"  Total Trades:      {report.total_trades}")
        lines.append(f"  Wins / Losses / BE: {report.winning_trades} / {report.losing_trades} / {report.be_trades}")
        lines.append(f"  Win Rate:          {report.win_rate:.1%}")
        lines.append(f"  Win Rate (ex BE):  {report.win_rate_excl_be:.1%}")
        lines.append(f"  Gross Profit:      ${report.gross_profit:.2f}")
        lines.append(f"  Gross Loss:        ${report.gross_loss:.2f}")
        lines.append(f"  Net P&L:           ${report.net_pnl:.2f} ({report.net_pnl_pct:+.2f}%)")
        lines.append(f"  Profit Factor:     {report.profit_factor:.2f}")
        lines.append(f"  Max Drawdown:      {report.max_drawdown_pct:.2f}%")
        lines.append(f"  Best Trade:        ${report.best_trade_pnl:.2f}")
        lines.append(f"  Worst Trade:       ${report.worst_trade_pnl:.2f}")
        lines.append(f"  Avg Win:           ${report.avg_win:.2f}")
        lines.append(f"  Avg Loss:          ${report.avg_loss:.2f}")
        lines.append(f"  Avg R:R Achieved:  {report.avg_rr_achieved:.2f}")
        lines.append(f"  Win Streak (max):  {report.max_winning_streak}")
        lines.append(f"  Loss Streak (max): {report.max_losing_streak}")

        # By strategy
        if report.by_strategy:
            lines.append("")
            lines.append("--- BY STRATEGY ---")
            for name, data in sorted(
                report.by_strategy.items(), key=lambda x: x[1]["pnl"], reverse=True
            ):
                wr = data.get("win_rate", 0)
                lines.append(
                    f"  {name:15s}  trades={data['trades']:3d}  "
                    f"W/L/BE={data['wins']}/{data['losses']}/{data['be']}  "
                    f"WR={wr:.0%}  P&L=${data['pnl']:+.2f}"
                )

        # By instrument
        if report.by_instrument:
            lines.append("")
            lines.append("--- BY INSTRUMENT ---")
            for name, data in sorted(
                report.by_instrument.items(), key=lambda x: x[1]["pnl"], reverse=True
            ):
                wr = data.get("win_rate", 0)
                lines.append(
                    f"  {name:15s}  trades={data['trades']:3d}  "
                    f"wins={data['wins']}  WR={wr:.0%}  P&L=${data['pnl']:+.2f}"
                )

        # By day of week
        if report.by_day_of_week:
            lines.append("")
            lines.append("--- BY DAY OF WEEK ---")
            day_order = [
                "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                "Saturday", "Sunday",
            ]
            for day in day_order:
                if day in report.by_day_of_week:
                    data = report.by_day_of_week[day]
                    wr = data.get("win_rate", 0)
                    lines.append(
                        f"  {day:12s}  trades={data['trades']:3d}  "
                        f"wins={data['wins']}  WR={wr:.0%}  P&L=${data['pnl']:+.2f}"
                    )

        # By session
        if report.by_session:
            lines.append("")
            lines.append("--- BY SESSION ---")
            for name, data in sorted(
                report.by_session.items(), key=lambda x: x[1]["pnl"], reverse=True
            ):
                wr = data.get("win_rate", 0)
                lines.append(
                    f"  {name:12s}  trades={data['trades']:3d}  "
                    f"wins={data['wins']}  WR={wr:.0%}  P&L=${data['pnl']:+.2f}"
                )

        # Discretionary vs systematic
        if report.discretionary_trades > 0 or report.systematic_trades > 0:
            lines.append("")
            lines.append("--- DISCRETIONARY vs SYSTEMATIC ---")
            lines.append(
                f"  Systematic:    {report.systematic_trades} trades, "
                f"WR={report.systematic_win_rate:.0%}"
            )
            lines.append(
                f"  Discretionary: {report.discretionary_trades} trades, "
                f"WR={report.discretionary_win_rate:.0%}"
            )

        # ASR completion
        lines.append("")
        lines.append("--- ASR (AUTO SELF REVIEW) ---")
        lines.append(
            f"  Completed:     {report.asr_completed_count}/{report.total_trades} "
            f"({report.asr_completion_rate:.0%})"
        )
        lines.append(
            f"  Perfect Exec:  {report.asr_perfect_execution_count}"
        )
        if report.asr_common_errors:
            lines.append("  Common errors:")
            for err in report.asr_common_errors:
                lines.append(f"    - {err}")

        # Emotional patterns
        if report.emotional_patterns:
            lines.append("")
            lines.append("--- EMOTIONAL PATTERNS ---")
            for p in report.emotional_patterns:
                lines.append(f"  * {p}")

        # Risk management
        lines.append("")
        lines.append("--- RISK MANAGEMENT ---")
        if report.dd_levels_hit:
            lines.append(f"  DD levels hit: {', '.join(report.dd_levels_hit)}")
        else:
            lines.append("  No DD levels hit.")
        lines.append(f"  Delta adjustments: {report.delta_adjustments}")
        lines.append(f"  Correlated trades: {report.correlated_trades_count}")
        lines.append(
            f"  Max simultaneous risk: {report.max_simultaneous_risk:.2f}%"
        )

        # Recommendations
        if report.recommendations:
            lines.append("")
            lines.append("--- RECOMMENDATIONS ---")
            for i, rec in enumerate(report.recommendations, 1):
                lines.append(f"  {i}. {rec}")

        lines.append("")
        lines.append(sep)

        return "\n".join(lines)
