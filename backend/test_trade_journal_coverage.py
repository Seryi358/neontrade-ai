"""
Tests for TradeJournal untested paths:
- Streak % persistence across save/load (bug fix verification)
- mark_trade_discretionary()
- ASR (update_asr + get_asr_stats)
- Missed trades (record, get, stats)
- Freshness check
- R:R achieved calculation
- update_journal_notes()
"""

import json
import os
import tempfile
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from core.trade_journal import TradeJournal


@pytest.fixture
def journal(tmp_path):
    """Create a TradeJournal with temp data paths (no stale data loaded)."""
    with patch.object(TradeJournal, "_load"):
        j = TradeJournal(initial_capital=10000.0)
    j._data_path = str(tmp_path / "trade_journal.json")
    j._missed_trades_path = str(tmp_path / "missed_trades.json")
    return j


def _record_tp(journal, trade_id="t1", pnl=100.0, strategy="BLUE_A"):
    """Helper: record a TP trade."""
    journal.record_trade(
        trade_id=trade_id,
        instrument="EUR_USD",
        pnl_dollars=pnl,
        entry_price=1.1000,
        exit_price=1.1050,
        strategy=strategy,
        direction="BUY",
        sl=1.0950,
        tp=1.1100,
    )


def _record_sl(journal, trade_id="t2", pnl=-100.0, strategy="BLUE_A"):
    """Helper: record a SL trade."""
    journal.record_trade(
        trade_id=trade_id,
        instrument="EUR_USD",
        pnl_dollars=pnl,
        entry_price=1.1000,
        exit_price=1.0950,
        strategy=strategy,
        direction="BUY",
        sl=1.0950,
        tp=1.1100,
    )


# ── Streak % Persistence ─────────────────────────────────────────

class TestStreakPersistence:
    """Verify the bug fix: current_streak_pct persists across save/load."""

    def test_winning_streak_pct_saved_and_loaded(self, journal, tmp_path):
        _record_tp(journal, "t1", 100.0)
        _record_tp(journal, "t2", 150.0)

        # Save journal state
        journal._save()

        # Create a new journal instance loading from same file
        j2 = TradeJournal(initial_capital=10000.0)
        j2._data_path = str(tmp_path / "trade_journal.json")
        j2._missed_trades_path = str(tmp_path / "missed_trades.json")
        j2._load()

        assert j2._current_winning_streak == 2
        assert j2._current_streak_pct > 0.0
        # Must match original
        assert abs(j2._current_streak_pct - journal._current_streak_pct) < 0.0001

    def test_losing_streak_pct_saved_and_loaded(self, journal, tmp_path):
        _record_sl(journal, "t1", -100.0)
        _record_sl(journal, "t2", -80.0)

        journal._save()

        j2 = TradeJournal(initial_capital=10000.0)
        j2._data_path = str(tmp_path / "trade_journal.json")
        j2._missed_trades_path = str(tmp_path / "missed_trades.json")
        j2._load()

        assert j2._current_losing_streak == 2
        assert j2._current_losing_streak_pct > 0.0
        assert abs(j2._current_losing_streak_pct - journal._current_losing_streak_pct) < 0.0001

    def test_streak_reset_on_opposite_result(self, journal):
        _record_tp(journal, "t1", 100.0)
        _record_tp(journal, "t2", 100.0)
        assert journal._current_winning_streak == 2
        assert journal._current_streak_pct > 0.0

        # Losing trade resets winning streak
        _record_sl(journal, "t3", -100.0)
        assert journal._current_winning_streak == 0
        assert journal._current_streak_pct == 0.0
        assert journal._current_losing_streak == 1


# ── R:R Achieved Calculation ──────────────────────────────────────

class TestRRAchieved:
    def test_rr_buy_trade(self, journal):
        journal.record_trade(
            trade_id="rr1",
            instrument="EUR_USD",
            pnl_dollars=200.0,
            entry_price=1.1000,
            exit_price=1.1100,
            strategy="RED",
            direction="BUY",
            sl=1.0950,  # risk = 0.0050
        )
        trade = journal._trades[-1]
        # reward = 1.1100 - 1.1000 = 0.0100, risk = 0.0050
        assert trade["rr_achieved"] == pytest.approx(2.0, abs=0.01)

    def test_rr_sell_trade(self, journal):
        journal.record_trade(
            trade_id="rr2",
            instrument="EUR_USD",
            pnl_dollars=100.0,
            entry_price=1.1000,
            exit_price=1.0900,
            strategy="RED",
            direction="SELL",
            sl=1.1050,  # risk = 0.0050
        )
        trade = journal._trades[-1]
        # reward = 1.1000 - 1.0900 = 0.0100, risk = 0.0050
        assert trade["rr_achieved"] == pytest.approx(2.0, abs=0.01)

    def test_rr_none_without_sl(self, journal):
        journal.record_trade(
            trade_id="rr3",
            instrument="EUR_USD",
            pnl_dollars=100.0,
            entry_price=1.1000,
            exit_price=1.1100,
            strategy="RED",
            direction="BUY",
        )
        assert journal._trades[-1]["rr_achieved"] is None


# ── Mark Discretionary ────────────────────────────────────────────

class TestMarkDiscretionary:
    def test_mark_existing_trade(self, journal):
        _record_tp(journal, "disc1")
        result = journal.mark_trade_discretionary("disc1", "Gut feeling on MACD divergence")
        assert result is True
        trade = journal._trades[-1]
        assert trade["is_discretionary"] is True
        assert trade["discretionary_notes"] == "Gut feeling on MACD divergence"

    def test_mark_nonexistent_trade(self, journal):
        result = journal.mark_trade_discretionary("nonexistent", "notes")
        assert result is False


# ── Journal Notes Update ──────────────────────────────────────────

class TestJournalNotes:
    def test_update_notes(self, journal):
        _record_tp(journal, "notes1")
        result = journal.update_journal_notes(
            "notes1",
            trade_summary="Good Blue A setup with strong confluence",
            management_notes="Moved SL to BE at 1:1",
            screenshots=["entry.png", "exit.png"],
            emotional_notes_pre="Calm, followed plan",
            emotional_notes_during="Slight anxiety at pullback",
            emotional_notes_post="Satisfied with execution",
        )
        assert result is True
        trade = journal._trades[-1]
        assert trade["trade_summary"] == "Good Blue A setup with strong confluence"
        assert trade["management_notes"] == "Moved SL to BE at 1:1"
        assert trade["screenshots"] == ["entry.png", "exit.png"]
        assert trade["emotional_notes_pre"] == "Calm, followed plan"

    def test_update_notes_partial(self, journal):
        _record_tp(journal, "notes2")
        journal.update_journal_notes("notes2", trade_summary="Quick scalp")
        trade = journal._trades[-1]
        assert trade["trade_summary"] == "Quick scalp"
        # Other fields should not have been set by this partial update
        assert "management_notes" not in trade or trade.get("management_notes", "") == ""

    def test_update_notes_nonexistent_trade(self, journal):
        result = journal.update_journal_notes("nonexistent", trade_summary="test")
        assert result is False


# ── ASR (After Session Review) ────────────────────────────────────

class TestASR:
    def test_update_asr(self, journal):
        _record_tp(journal, "asr1")
        result = journal.update_asr(
            "asr1",
            htf_correct=True,
            ltf_correct=True,
            strategy_correct=True,
            sl_correct=True,
            tp_correct=False,
            management_correct=True,
            would_enter_again=True,
            lessons="TP was too aggressive — should have used previous swing",
            error_type="tp_placement",
        )
        assert result is True
        trade = journal._trades[-1]
        assert trade["asr_completed"] is True
        assert trade["asr_htf_correct"] is True
        assert trade["asr_tp_correct"] is False
        assert trade["asr_lessons"] == "TP was too aggressive — should have used previous swing"

    def test_update_asr_nonexistent(self, journal):
        result = journal.update_asr("nonexistent", htf_correct=True)
        assert result is False

    def test_asr_stats_empty(self, journal):
        stats = journal.get_asr_stats()
        assert stats["total"] == 0
        assert stats["asr_completed"] == 0

    def test_asr_stats_with_trades(self, journal):
        _record_tp(journal, "s1")
        _record_tp(journal, "s2")
        _record_sl(journal, "s3")

        # Complete ASR for s1 (perfect) and s2 (not perfect)
        journal.update_asr(
            "s1",
            htf_correct=True, ltf_correct=True, strategy_correct=True,
            sl_correct=True, tp_correct=True, management_correct=True,
        )
        journal.update_asr(
            "s2",
            htf_correct=True, ltf_correct=False, strategy_correct=True,
            sl_correct=True, tp_correct=True, management_correct=True,
        )
        # s3 has no ASR

        stats = journal.get_asr_stats()
        assert stats["total"] == 3
        assert stats["asr_completed"] == 2
        assert stats["asr_completion_rate"] == pytest.approx(66.7, abs=0.1)
        assert stats["perfect_execution_count"] == 1
        assert stats["perfect_execution_rate"] == 50.0


# ── Missed Trades ─────────────────────────────────────────────────

class TestMissedTrades:
    def test_record_missed_trade(self, journal):
        journal.record_missed_trade(
            instrument="GBP_USD",
            strategy="RED",
            direction="SELL",
            confidence=0.85,
            reason_skipped="news filter",
        )
        assert len(journal._missed_trades) == 1
        mt = journal._missed_trades[0]
        assert mt["instrument"] == "GBP_USD"
        assert mt["strategy"] == "RED"
        assert mt["reason_skipped"] == "news filter"
        assert mt["confidence"] == 0.85

    def test_get_missed_trades_pagination(self, journal):
        for i in range(10):
            journal.record_missed_trade(
                instrument=f"PAIR_{i}",
                strategy="BLUE_A",
                direction="BUY",
                confidence=0.7,
                reason_skipped="low confidence",
            )
        # Most recent first
        result = journal.get_missed_trades(limit=3, offset=0)
        assert len(result) == 3
        assert result[0]["instrument"] == "PAIR_9"  # Most recent

        result2 = journal.get_missed_trades(limit=3, offset=3)
        assert result2[0]["instrument"] == "PAIR_6"

    def test_missed_trade_stats(self, journal):
        journal.record_missed_trade("EUR_USD", "BLUE_A", "BUY", 0.6, "low confidence")
        journal.record_missed_trade("GBP_USD", "RED", "SELL", 0.8, "news filter")
        journal.record_missed_trade("AUD_USD", "BLUE_A", "BUY", 0.55, "low confidence")

        stats = journal.get_missed_trade_stats()
        assert stats["total_missed"] == 3
        assert stats["by_reason"]["low confidence"] == 2
        assert stats["by_reason"]["news filter"] == 1
        assert stats["by_strategy"]["BLUE_A"] == 2
        assert stats["by_strategy"]["RED"] == 1

    def test_missed_trades_persistence(self, journal, tmp_path):
        journal.record_missed_trade("EUR_USD", "BLUE_A", "BUY", 0.7, "max positions")

        # Reload
        j2 = TradeJournal(initial_capital=10000.0)
        j2._data_path = str(tmp_path / "trade_journal.json")
        j2._missed_trades_path = str(tmp_path / "missed_trades.json")
        j2._load()

        assert len(j2._missed_trades) == 1
        assert j2._missed_trades[0]["instrument"] == "EUR_USD"


# ── Freshness Check ───────────────────────────────────────────────

class TestFreshnessCheck:
    def test_fresh_trade_no_warning(self, journal):
        trade = {"date": datetime.now(timezone.utc).isoformat()}
        result = journal._check_journal_freshness(trade)
        assert result is None

    def test_stale_trade_warning(self, journal):
        old_time = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
        trade = {"date": old_time}
        result = journal._check_journal_freshness(trade)
        assert result is not None
        assert "24h" in result

    def test_no_date_no_warning(self, journal):
        trade = {}
        result = journal._check_journal_freshness(trade)
        assert result is None

    def test_naive_datetime_handled(self, journal):
        # Naive datetime (no timezone info) — should still work
        old_time = (datetime.now() - timedelta(hours=30)).isoformat()
        trade = {"date": old_time}
        result = journal._check_journal_freshness(trade)
        assert result is not None


# ── Classification Edge Cases ─────────────────────────────────────

class TestClassification:
    def test_be_classification(self, journal):
        # Between -0.1% and +0.1%
        assert journal._classify_result(0.05) == "BE"
        assert journal._classify_result(-0.05) == "BE"
        assert journal._classify_result(0.0) == "BE"

    def test_tp_classification(self, journal):
        assert journal._classify_result(0.1) == "TP"
        assert journal._classify_result(5.0) == "TP"

    def test_sl_classification(self, journal):
        assert journal._classify_result(-0.1) == "SL"
        assert journal._classify_result(-3.0) == "SL"
