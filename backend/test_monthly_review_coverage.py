"""
Tests for monthly_review.py — MonthlyReport dataclass, timestamp parsing,
session classification, streaks, drawdown, emotional patterns, recommendations,
report generation, persistence, and text formatting.
"""

import json
import os
import pytest
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from core.monthly_review import MonthlyReport, MonthlyReviewGenerator


@pytest.fixture
def gen(tmp_path):
    """Generator with a temp data directory."""
    return MonthlyReviewGenerator(data_dir=str(tmp_path))


def _trade(
    pnl=100.0, pnl_pct=1.0, result="TP", strategy="BLUE",
    instrument="EUR_USD", open_time="2025-03-10T10:00:00Z",
    is_discretionary=False, discretionary_notes="",
    emotional_notes_pre="", emotional_notes_post="",
    rr_achieved=2.0, dd_level_hit=None, delta_adjustment=False,
    correlated_pair=None, simultaneous_risk=0.0,
    asr_completed=False, month="2025-03", **asr_fields,
):
    """Helper to build a trade dict."""
    t = {
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "result": result,
        "strategy": strategy,
        "instrument": instrument,
        "open_time": open_time,
        "month": month,
        "is_discretionary": is_discretionary,
        "discretionary_notes": discretionary_notes,
        "emotional_notes_pre": emotional_notes_pre,
        "emotional_notes_post": emotional_notes_post,
        "rr_achieved": rr_achieved,
        "dd_level_hit": dd_level_hit,
        "delta_adjustment": delta_adjustment,
        "correlated_pair": correlated_pair,
        "simultaneous_risk": simultaneous_risk,
        "asr_completed": asr_completed,
    }
    t.update(asr_fields)
    return t


# ──────────────────────────────────────────────────────────────────
# MonthlyReport dataclass
# ──────────────────────────────────────────────────────────────────

class TestMonthlyReport:
    def test_defaults(self):
        r = MonthlyReport(month="2025-03", generated_at="now")
        assert r.total_trades == 0
        assert r.win_rate == 0.0
        assert r.by_strategy == {}
        assert r.recommendations == []

    def test_to_dict(self):
        r = MonthlyReport(month="2025-03", generated_at="now")
        d = r.to_dict()
        assert isinstance(d, dict)
        assert d["month"] == "2025-03"
        assert "by_strategy" in d


# ──────────────────────────────────────────────────────────────────
# _parse_timestamp
# ──────────────────────────────────────────────────────────────────

class TestParseTimestamp:
    def test_iso_with_z(self, gen):
        dt = gen._parse_timestamp("2025-03-10T14:30:00Z")
        assert dt is not None
        assert dt.hour == 14

    def test_iso_with_offset(self, gen):
        dt = gen._parse_timestamp("2025-03-10T14:30:00+00:00")
        assert dt is not None
        assert dt.hour == 14

    def test_datetime_object(self, gen):
        now = datetime.now(timezone.utc)
        dt = gen._parse_timestamp(now)
        assert dt is now

    def test_date_only(self, gen):
        dt = gen._parse_timestamp("2025-03-10")
        assert dt is not None
        assert dt.day == 10

    def test_datetime_with_space(self, gen):
        dt = gen._parse_timestamp("2025-03-10 14:30:00")
        assert dt is not None
        assert dt.minute == 30

    def test_unix_timestamp(self, gen):
        ts = datetime(2025, 3, 10, 12, 0, tzinfo=timezone.utc).timestamp()
        dt = gen._parse_timestamp(ts)
        assert dt is not None
        assert dt.day == 10

    def test_empty_string(self, gen):
        assert gen._parse_timestamp("") is None

    def test_none(self, gen):
        assert gen._parse_timestamp(None) is None

    def test_garbage_string(self, gen):
        assert gen._parse_timestamp("not a date") is None


# ──────────────────────────────────────────────────────────────────
# _get_day_name
# ──────────────────────────────────────────────────────────────────

class TestGetDayName:
    def test_monday(self, gen):
        # 2025-03-10 is a Monday
        assert gen._get_day_name("2025-03-10T10:00:00Z") == "Monday"

    def test_friday(self, gen):
        # 2025-03-14 is a Friday
        assert gen._get_day_name("2025-03-14T10:00:00Z") == "Friday"

    def test_invalid_returns_empty(self, gen):
        assert gen._get_day_name("invalid") == ""


# ──────────────────────────────────────────────────────────────────
# _get_session
# ──────────────────────────────────────────────────────────────────

class TestGetSession:
    def test_london_session(self, gen):
        assert gen._get_session("2025-03-10T09:00:00Z") == "London"

    def test_new_york_session(self, gen):
        assert gen._get_session("2025-03-10T15:00:00Z") == "New York"

    def test_off_hours(self, gen):
        assert gen._get_session("2025-03-10T03:00:00Z") == "Off-Hours"

    def test_london_boundary_start(self, gen):
        assert gen._get_session("2025-03-10T07:00:00Z") == "London"

    def test_new_york_boundary_start(self, gen):
        assert gen._get_session("2025-03-10T13:00:00Z") == "New York"

    def test_invalid_returns_empty(self, gen):
        assert gen._get_session("invalid") == ""


# ──────────────────────────────────────────────────────────────────
# _calculate_streaks
# ──────────────────────────────────────────────────────────────────

class TestCalculateStreaks:
    def test_no_trades(self, gen):
        assert gen._calculate_streaks([]) == (0, 0)

    def test_all_wins(self, gen):
        trades = [{"pnl_pct": 1.0}] * 5
        win, loss = gen._calculate_streaks(trades)
        assert win == 5
        assert loss == 0

    def test_all_losses(self, gen):
        trades = [{"pnl_pct": -1.0}] * 4
        win, loss = gen._calculate_streaks(trades)
        assert win == 0
        assert loss == 4

    def test_mixed_streaks(self, gen):
        trades = [
            {"pnl_pct": 1.0},  # win
            {"pnl_pct": 1.0},  # win
            {"pnl_pct": 1.0},  # win (streak 3)
            {"pnl_pct": -1.0},  # loss
            {"pnl_pct": -1.0},  # loss (streak 2)
            {"pnl_pct": 1.0},  # win
        ]
        win, loss = gen._calculate_streaks(trades)
        assert win == 3
        assert loss == 2

    def test_be_breaks_streak(self, gen):
        trades = [
            {"pnl_pct": 1.0},
            {"pnl_pct": 0.0},  # BE breaks streak
            {"pnl_pct": 1.0},
        ]
        win, loss = gen._calculate_streaks(trades)
        assert win == 1  # BE resets counter


# ──────────────────────────────────────────────────────────────────
# _calculate_max_drawdown
# ──────────────────────────────────────────────────────────────────

class TestCalculateMaxDrawdown:
    def test_no_trades(self, gen):
        assert gen._calculate_max_drawdown([], 10000) == 0.0

    def test_only_wins(self, gen):
        trades = [{"pnl": 100}, {"pnl": 200}]
        assert gen._calculate_max_drawdown(trades, 10000) == 0.0

    def test_single_drawdown(self, gen):
        trades = [
            {"pnl": 500},  # peak at 10500
            {"pnl": -1000},  # trough at 9500, DD = 1000/10500 = 9.52%
            {"pnl": 200},
        ]
        dd = gen._calculate_max_drawdown(trades, 10000)
        assert abs(dd - 9.52) < 0.1

    def test_zero_balance_start_uses_fallback(self, gen):
        trades = [{"pnl": -100}]
        dd = gen._calculate_max_drawdown(trades, 0)
        # Fallback is 10000, DD = 100/10000 = 1%
        assert abs(dd - 1.0) < 0.1


# ──────────────────────────────────────────────────────────────────
# _analyze_emotional_patterns
# ──────────────────────────────────────────────────────────────────

class TestAnalyzeEmotionalPatterns:
    def test_no_entries(self, gen):
        assert gen._analyze_emotional_patterns([]) == []

    def test_negative_emotions_detected(self, gen):
        entries = [
            {"pre": "Feeling stressed and anxious", "post": "", "pnl_pct": -1.0, "is_win": False, "is_loss": True},
            {"pre": "Very frustrated after last loss", "post": "", "pnl_pct": -0.5, "is_win": False, "is_loss": True},
        ]
        patterns = gen._analyze_emotional_patterns(entries)
        assert any("negative emotions" in p.lower() for p in patterns)

    def test_positive_emotions_detected(self, gen):
        entries = [
            {"pre": "Calm and focused today", "post": "", "pnl_pct": 1.0, "is_win": True, "is_loss": False},
            {"pre": "Feeling confident and disciplined", "post": "", "pnl_pct": 0.5, "is_win": True, "is_loss": False},
        ]
        patterns = gen._analyze_emotional_patterns(entries)
        assert any("positive" in p.lower() or "calm" in p.lower() for p in patterns)

    def test_revenge_trading_detected(self, gen):
        entries = [
            {"pre": "revenge trade after big loss", "post": "", "pnl_pct": -1.0, "is_win": False, "is_loss": True},
        ]
        patterns = gen._analyze_emotional_patterns(entries)
        assert any("revenge" in p.lower() for p in patterns)

    def test_fomo_detected(self, gen):
        entries = [
            {"pre": "FOMO — market is running", "post": "", "pnl_pct": -0.5, "is_win": False, "is_loss": True},
        ]
        patterns = gen._analyze_emotional_patterns(entries)
        assert any("fomo" in p.lower() for p in patterns)

    def test_spanish_emotions_detected(self, gen):
        entries = [
            {"pre": "Estresado por las noticias", "post": "", "pnl_pct": -1.0, "is_win": False, "is_loss": True},
            {"pre": "Ansioso, no dormí bien", "post": "", "pnl_pct": -0.5, "is_win": False, "is_loss": True},
        ]
        patterns = gen._analyze_emotional_patterns(entries)
        assert any("negative" in p.lower() for p in patterns)

    def test_correlation_pattern_pos_better(self, gen):
        """When positive state has higher win rate, it's flagged."""
        entries = [
            {"pre": "stressed", "post": "", "pnl_pct": -1.0, "is_win": False, "is_loss": True},
            {"pre": "anxious", "post": "", "pnl_pct": -0.5, "is_win": False, "is_loss": True},
            {"pre": "calm", "post": "", "pnl_pct": 1.0, "is_win": True, "is_loss": False},
            {"pre": "focused", "post": "", "pnl_pct": 0.5, "is_win": True, "is_loss": False},
        ]
        patterns = gen._analyze_emotional_patterns(entries)
        assert any("higher win rate" in p.lower() for p in patterns)


# ──────────────────────────────────────────────────────────────────
# _generate_recommendations
# ──────────────────────────────────────────────────────────────────

class TestGenerateRecommendations:
    def test_low_win_rate(self, gen):
        r = MonthlyReport(month="2025-03", generated_at="now")
        r.win_rate_excl_be = 0.40
        r.total_trades = 10
        recs = gen._generate_recommendations(r)
        assert any("50%" in rec for rec in recs)

    def test_high_win_rate(self, gen):
        r = MonthlyReport(month="2025-03", generated_at="now")
        r.win_rate_excl_be = 0.70
        r.total_trades = 10
        recs = gen._generate_recommendations(r)
        assert any("excelente" in rec.lower() for rec in recs)

    def test_best_worst_strategy(self, gen):
        r = MonthlyReport(month="2025-03", generated_at="now")
        r.by_strategy = {
            "BLUE": {"pnl": 500, "trades": 10, "wins": 8, "losses": 2, "be": 0},
            "RED": {"pnl": -200, "trades": 5, "wins": 1, "losses": 4, "be": 0},
        }
        recs = gen._generate_recommendations(r)
        assert any("BLUE" in rec for rec in recs)
        assert any("RED" in rec for rec in recs)

    def test_worst_day_recommendation(self, gen):
        r = MonthlyReport(month="2025-03", generated_at="now")
        r.by_day_of_week = {
            "Monday": {"pnl": -100, "trades": 3, "wins": 0},
        }
        recs = gen._generate_recommendations(r)
        assert any("Monday" in rec for rec in recs)

    def test_best_session_recommendation(self, gen):
        r = MonthlyReport(month="2025-03", generated_at="now")
        r.by_session = {
            "London": {"pnl": 300, "trades": 10, "wins": 7},
        }
        recs = gen._generate_recommendations(r)
        assert any("London" in rec for rec in recs)

    def test_discretionary_worse_than_systematic(self, gen):
        r = MonthlyReport(month="2025-03", generated_at="now")
        r.discretionary_trades = 5
        r.discretionary_win_rate = 0.30
        r.systematic_trades = 10
        r.systematic_win_rate = 0.60
        recs = gen._generate_recommendations(r)
        assert any("discrecionales" in rec.lower() for rec in recs)

    def test_low_profit_factor(self, gen):
        r = MonthlyReport(month="2025-03", generated_at="now")
        r.profit_factor = 1.1
        recs = gen._generate_recommendations(r)
        assert any("profit factor" in rec.lower() for rec in recs)

    def test_high_drawdown(self, gen):
        r = MonthlyReport(month="2025-03", generated_at="now")
        r.max_drawdown_pct = 7.5
        recs = gen._generate_recommendations(r)
        assert any("drawdown" in rec.lower() for rec in recs)

    def test_losing_streak(self, gen):
        r = MonthlyReport(month="2025-03", generated_at="now")
        r.max_losing_streak = 5
        recs = gen._generate_recommendations(r)
        assert any("pérdidas consecutivas" in rec for rec in recs)

    def test_revenge_trading_recommendation(self, gen):
        r = MonthlyReport(month="2025-03", generated_at="now")
        r.emotional_patterns = ["Revenge trading detected in 2 trade(s)."]
        recs = gen._generate_recommendations(r)
        assert any("revenge" in rec.lower() for rec in recs)

    def test_low_asr_completion(self, gen):
        r = MonthlyReport(month="2025-03", generated_at="now")
        r.asr_completion_rate = 0.50
        r.total_trades = 10
        recs = gen._generate_recommendations(r)
        assert any("asr" in rec.lower() for rec in recs)

    def test_correlated_trades_warning(self, gen):
        r = MonthlyReport(month="2025-03", generated_at="now")
        r.correlated_trades_count = 5
        recs = gen._generate_recommendations(r)
        assert any("correlated" in rec.lower() for rec in recs)

    def test_low_avg_rr(self, gen):
        r = MonthlyReport(month="2025-03", generated_at="now")
        r.avg_rr_achieved = 0.8
        recs = gen._generate_recommendations(r)
        assert any("r:r" in rec.lower() for rec in recs)

    def test_solid_month_no_issues(self, gen):
        r = MonthlyReport(month="2025-03", generated_at="now")
        r.win_rate_excl_be = 0.55
        recs = gen._generate_recommendations(r)
        assert any("solid" in rec.lower() for rec in recs)


# ──────────────────────────────────────────────────────────────────
# generate_report (full integration)
# ──────────────────────────────────────────────────────────────────

class TestGenerateReport:
    def test_empty_trades(self, gen):
        report = gen.generate_report([], "2025-03")
        assert report.total_trades == 0
        assert len(report.recommendations) >= 1

    def test_basic_report(self, gen):
        trades = [
            _trade(pnl=100, pnl_pct=1.0, result="TP", strategy="BLUE"),
            _trade(pnl=-50, pnl_pct=-0.5, result="SL", strategy="RED"),
            _trade(pnl=80, pnl_pct=0.8, result="TP", strategy="BLUE"),
        ]
        report = gen.generate_report(trades, "2025-03", balance_start=10000)
        assert report.total_trades == 3
        assert report.winning_trades == 2
        assert report.losing_trades == 1
        assert report.gross_profit == 180.0
        assert report.gross_loss == 50.0
        assert abs(report.net_pnl - 130.0) < 0.01
        assert abs(report.profit_factor - 3.6) < 0.01

    def test_by_strategy_breakdown(self, gen):
        trades = [
            _trade(pnl=100, pnl_pct=1.0, result="TP", strategy="BLUE"),
            _trade(pnl=-50, pnl_pct=-0.5, result="SL", strategy="RED"),
        ]
        report = gen.generate_report(trades, "2025-03")
        assert "BLUE" in report.by_strategy
        assert "RED" in report.by_strategy
        assert report.by_strategy["BLUE"]["wins"] == 1
        assert report.by_strategy["RED"]["losses"] == 1

    def test_by_instrument_breakdown(self, gen):
        trades = [
            _trade(instrument="EUR_USD", pnl=100, pnl_pct=1.0, result="TP"),
            _trade(instrument="GBP_USD", pnl=-50, pnl_pct=-0.5, result="SL"),
        ]
        report = gen.generate_report(trades, "2025-03")
        assert "EUR_USD" in report.by_instrument
        assert "GBP_USD" in report.by_instrument

    def test_by_day_of_week(self, gen):
        trades = [
            _trade(open_time="2025-03-10T10:00:00Z"),  # Monday
            _trade(open_time="2025-03-14T10:00:00Z", pnl=-50, pnl_pct=-0.5, result="SL"),  # Friday
        ]
        report = gen.generate_report(trades, "2025-03")
        assert "Monday" in report.by_day_of_week
        assert "Friday" in report.by_day_of_week

    def test_by_session(self, gen):
        trades = [
            _trade(open_time="2025-03-10T09:00:00Z"),  # London
            _trade(open_time="2025-03-10T16:00:00Z", pnl=-50, pnl_pct=-0.5, result="SL"),  # NY
        ]
        report = gen.generate_report(trades, "2025-03")
        assert "London" in report.by_session
        assert "New York" in report.by_session

    def test_discretionary_tracking(self, gen):
        trades = [
            _trade(is_discretionary=True, discretionary_notes="Manual entry"),
            _trade(is_discretionary=False),
        ]
        report = gen.generate_report(trades, "2025-03")
        assert report.discretionary_trades == 1
        assert report.systematic_trades == 1
        assert "Manual entry" in report.discretionary_notes_summary

    def test_be_trade_classification(self, gen):
        trades = [
            _trade(pnl=0.5, pnl_pct=0.0, result="BE"),
        ]
        report = gen.generate_report(trades, "2025-03")
        assert report.be_trades == 1

    def test_streaks_calculated(self, gen):
        trades = [
            _trade(pnl_pct=1.0),
            _trade(pnl_pct=1.0),
            _trade(pnl_pct=1.0),
            _trade(pnl_pct=-1.0, pnl=-50, result="SL"),
        ]
        report = gen.generate_report(trades, "2025-03")
        assert report.max_winning_streak == 3
        assert report.max_losing_streak == 1

    def test_rr_achieved_average(self, gen):
        trades = [
            _trade(rr_achieved=2.0),
            _trade(rr_achieved=3.0),
        ]
        report = gen.generate_report(trades, "2025-03")
        assert abs(report.avg_rr_achieved - 2.5) < 0.01

    def test_dd_level_hit_tracked(self, gen):
        trades = [
            _trade(dd_level_hit="level_1"),
            _trade(dd_level_hit=None),
        ]
        report = gen.generate_report(trades, "2025-03")
        assert "level_1" in report.dd_levels_hit

    def test_delta_adjustment_counted(self, gen):
        trades = [
            _trade(delta_adjustment=True),
            _trade(delta_adjustment=False),
        ]
        report = gen.generate_report(trades, "2025-03")
        assert report.delta_adjustments == 1

    def test_correlated_pair_counted(self, gen):
        trades = [
            _trade(correlated_pair="GBP_USD"),
            _trade(correlated_pair=None),
        ]
        report = gen.generate_report(trades, "2025-03")
        assert report.correlated_trades_count == 1

    def test_asr_completion(self, gen):
        trades = [
            _trade(asr_completed=True, asr_htf_correct=True, asr_ltf_correct=True,
                   asr_strategy_correct=True, asr_sl_correct=True, asr_tp_correct=True,
                   asr_management_correct=True),
            _trade(asr_completed=True, asr_htf_correct=False, asr_ltf_correct=True,
                   asr_strategy_correct=True, asr_sl_correct=True, asr_tp_correct=True,
                   asr_management_correct=True),
            _trade(asr_completed=False),
        ]
        report = gen.generate_report(trades, "2025-03")
        assert report.asr_completed_count == 2
        assert report.asr_perfect_execution_count == 1
        assert len(report.asr_common_errors) >= 1
        assert "HTF analysis" in report.asr_common_errors[0]

    def test_net_pnl_pct(self, gen):
        trades = [_trade(pnl=500, pnl_pct=5.0)]
        report = gen.generate_report(trades, "2025-03", balance_start=10000)
        assert abs(report.net_pnl_pct - 5.0) < 0.01

    def test_best_worst_trade(self, gen):
        trades = [
            _trade(pnl=200),
            _trade(pnl=-100, pnl_pct=-1.0, result="SL"),
            _trade(pnl=50),
        ]
        report = gen.generate_report(trades, "2025-03")
        assert report.best_trade_pnl == 200
        assert report.worst_trade_pnl == -100


# ──────────────────────────────────────────────────────────────────
# Persistence
# ──────────────────────────────────────────────────────────────────

class TestPersistence:
    def test_save_and_load(self, gen):
        trades = [_trade(pnl=100)]
        report = gen.generate_report(trades, "2025-03")
        loaded = gen.load_report("2025-03")
        assert loaded is not None
        assert loaded["month"] == "2025-03"
        assert loaded["total_trades"] == 1

    def test_load_nonexistent(self, gen):
        assert gen.load_report("2099-01") is None

    def test_list_reports(self, gen):
        gen.generate_report([_trade(month="2025-01")], "2025-01")
        gen.generate_report([_trade(month="2025-02")], "2025-02")
        reports = gen.list_reports()
        assert "2025-01" in reports
        assert "2025-02" in reports


# ──────────────────────────────────────────────────────────────────
# format_text_report
# ──────────────────────────────────────────────────────────────────

class TestFormatTextReport:
    def test_contains_header(self, gen):
        report = MonthlyReport(month="2025-03", generated_at="2025-04-01T00:00:00")
        text = gen.format_text_report(report)
        assert "MONTHLY TRADING REVIEW" in text
        assert "2025-03" in text

    def test_contains_performance_summary(self, gen):
        trades = [
            _trade(pnl=100, pnl_pct=1.0),
            _trade(pnl=-50, pnl_pct=-0.5, result="SL"),
        ]
        report = gen.generate_report(trades, "2025-03", balance_start=10000)
        text = gen.format_text_report(report)
        assert "PERFORMANCE SUMMARY" in text
        assert "Total Trades" in text
        assert "Win Rate" in text

    def test_contains_strategy_section(self, gen):
        trades = [_trade(strategy="BLUE"), _trade(strategy="RED", pnl=-50, pnl_pct=-0.5, result="SL")]
        report = gen.generate_report(trades, "2025-03")
        text = gen.format_text_report(report)
        assert "BY STRATEGY" in text
        assert "BLUE" in text

    def test_contains_day_of_week(self, gen):
        trades = [_trade(open_time="2025-03-10T10:00:00Z")]
        report = gen.generate_report(trades, "2025-03")
        text = gen.format_text_report(report)
        assert "BY DAY OF WEEK" in text
        assert "Monday" in text

    def test_contains_session(self, gen):
        trades = [_trade(open_time="2025-03-10T09:00:00Z")]
        report = gen.generate_report(trades, "2025-03")
        text = gen.format_text_report(report)
        assert "BY SESSION" in text
        assert "London" in text

    def test_contains_asr(self, gen):
        report = MonthlyReport(month="2025-03", generated_at="now", total_trades=5)
        text = gen.format_text_report(report)
        assert "ASR" in text

    def test_contains_recommendations(self, gen):
        report = MonthlyReport(month="2025-03", generated_at="now")
        report.recommendations = ["Test recommendation"]
        text = gen.format_text_report(report)
        assert "RECOMMENDATIONS" in text
        assert "Test recommendation" in text

    def test_contains_risk_management(self, gen):
        report = MonthlyReport(month="2025-03", generated_at="now")
        report.dd_levels_hit = ["level_1"]
        text = gen.format_text_report(report)
        assert "RISK MANAGEMENT" in text
        assert "level_1" in text

    def test_emotional_patterns_section(self, gen):
        report = MonthlyReport(month="2025-03", generated_at="now")
        report.emotional_patterns = ["FOMO mentioned in 2 trades"]
        text = gen.format_text_report(report)
        assert "EMOTIONAL PATTERNS" in text
        assert "FOMO" in text


# ──────────────────────────────────────────────────────────────────
# Emotion keyword lists
# ──────────────────────────────────────────────────────────────────

class TestEmotionKeywords:
    def test_negative_keywords_include_spanish(self):
        assert "estresado" in MonthlyReviewGenerator.NEGATIVE_EMOTION_KEYWORDS
        assert "frustrado" in MonthlyReviewGenerator.NEGATIVE_EMOTION_KEYWORDS
        assert "venganza" in MonthlyReviewGenerator.NEGATIVE_EMOTION_KEYWORDS

    def test_positive_keywords_include_spanish(self):
        assert "tranquilo" in MonthlyReviewGenerator.POSITIVE_EMOTION_KEYWORDS
        assert "disciplinado" in MonthlyReviewGenerator.POSITIVE_EMOTION_KEYWORDS

    def test_negative_keywords_include_english(self):
        assert "stressed" in MonthlyReviewGenerator.NEGATIVE_EMOTION_KEYWORDS
        assert "revenge" in MonthlyReviewGenerator.NEGATIVE_EMOTION_KEYWORDS
        assert "fomo" in MonthlyReviewGenerator.NEGATIVE_EMOTION_KEYWORDS

    def test_positive_keywords_include_english(self):
        assert "calm" in MonthlyReviewGenerator.POSITIVE_EMOTION_KEYWORDS
        assert "focused" in MonthlyReviewGenerator.POSITIVE_EMOTION_KEYWORDS
