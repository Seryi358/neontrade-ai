"""
Tests for backtester.py — covering helpers, simulated position 5-phase
management, metrics calculation, position opening validation, and dataclasses.
"""

import math
import pytest
import numpy as np
import pandas as pd
from dataclasses import asdict
from unittest.mock import patch, MagicMock, AsyncMock

from core.backtester import (
    _pip_value,
    _pips,
    _price_from_pips,
    _SimulatedPosition,
    _HistoricalBrokerAdapter,
    BacktestConfig,
    BacktestTrade,
    BacktestResult,
    Backtester,
    TradeOutcome,
)
from core.position_manager import PositionPhase
from broker.base import CandleData


# ──────────────────────────────────────────────────────────────────
# Helper functions: _pip_value, _pips, _price_from_pips
# ──────────────────────────────────────────────────────────────────

class TestPipValue:
    def test_standard_forex_pair(self):
        assert _pip_value("EUR_USD") == 0.0001

    def test_jpy_pair(self):
        assert _pip_value("USD_JPY") == 0.01

    def test_jpy_pair_with_slash(self):
        assert _pip_value("USD/JPY") == 0.01

    def test_crypto_instrument(self):
        with patch("strategies.base._is_crypto_instrument", return_value=True):
            assert _pip_value("BTC_USD") == 1.0

    def test_non_jpy_non_crypto(self):
        with patch("strategies.base._is_crypto_instrument", return_value=False):
            assert _pip_value("GBP_CHF") == 0.0001


class TestPips:
    def test_standard_pair(self):
        result = _pips("EUR_USD", 0.0050)
        assert abs(result - 50.0) < 0.01

    def test_jpy_pair(self):
        result = _pips("USD_JPY", 1.50)
        assert abs(result - 150.0) < 0.01

    def test_zero_distance(self):
        assert _pips("EUR_USD", 0.0) == 0.0


class TestPriceFromPips:
    def test_standard_pair(self):
        result = _price_from_pips("EUR_USD", 50.0)
        assert abs(result - 0.0050) < 1e-8

    def test_jpy_pair(self):
        result = _price_from_pips("USD_JPY", 100.0)
        assert abs(result - 1.0) < 1e-8

    def test_round_trip(self):
        """pips -> price -> pips should round-trip."""
        original_pips = 25.0
        price = _price_from_pips("EUR_USD", original_pips)
        back = _pips("EUR_USD", price)
        assert abs(back - original_pips) < 0.01


# ──────────────────────────────────────────────────────────────────
# _SimulatedPosition
# ──────────────────────────────────────────────────────────────────

def _make_trade(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100, tp_max=None):
    return BacktestTrade(
        trade_id="test01",
        instrument="EUR_USD",
        strategy="BLUE_A",
        direction=direction,
        entry_price=entry,
        entry_time="2025-01-01T10:00:00",
        stop_loss=sl,
        take_profit_1=tp1,
        take_profit_max=tp_max,
        units=1000 if direction == "BUY" else -1000,
    )


class TestSimulatedPositionInit:
    def test_initial_phase(self):
        trade = _make_trade()
        pos = _SimulatedPosition(trade, "EUR_USD")
        assert pos.phase == PositionPhase.INITIAL
        assert not pos.closed
        assert pos.bars_elapsed == 0

    def test_sl_set_from_trade(self):
        trade = _make_trade(sl=1.0940)
        pos = _SimulatedPosition(trade, "EUR_USD")
        assert pos.current_sl == 1.0940

    def test_highest_lowest_init_to_entry(self):
        trade = _make_trade(entry=1.1050)
        pos = _SimulatedPosition(trade, "EUR_USD")
        assert pos.highest_price == 1.1050
        assert pos.lowest_price == 1.1050


class TestSimulatedPositionSLHit:
    def test_buy_sl_hit(self):
        trade = _make_trade(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100)
        pos = _SimulatedPosition(trade, "EUR_USD")
        # Bar low touches SL
        closed = pos.update(bar_high=1.1010, bar_low=1.0945, bar_close=1.0960)
        assert closed is True
        assert pos.closed
        assert trade.exit_reason == "SL_HIT"
        assert trade.outcome == TradeOutcome.LOSS

    def test_sell_sl_hit(self):
        trade = _make_trade(direction="SELL", entry=1.1000, sl=1.1050, tp1=1.0900)
        pos = _SimulatedPosition(trade, "EUR_USD")
        # Bar high touches SL
        closed = pos.update(bar_high=1.1055, bar_low=1.0990, bar_close=1.1020)
        assert closed is True
        assert trade.exit_reason == "SL_HIT"


class TestSimulatedPositionTPHit:
    def test_buy_tp_hit(self):
        trade = _make_trade(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100)
        pos = _SimulatedPosition(trade, "EUR_USD")
        # Bar high reaches TP
        closed = pos.update(bar_high=1.1105, bar_low=1.1000, bar_close=1.1080)
        assert closed is True
        assert trade.exit_reason == "TP_HIT"
        assert trade.outcome == TradeOutcome.WIN

    def test_sell_tp_hit(self):
        trade = _make_trade(direction="SELL", entry=1.1000, sl=1.1050, tp1=1.0900)
        pos = _SimulatedPosition(trade, "EUR_USD")
        # Bar low reaches TP
        closed = pos.update(bar_high=1.1010, bar_low=1.0895, bar_close=1.0910)
        assert closed is True
        assert trade.exit_reason == "TP_HIT"

    def test_tp_max_used_when_set(self):
        trade = _make_trade(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100, tp_max=1.1200)
        pos = _SimulatedPosition(trade, "EUR_USD")
        # Bar high reaches tp_max
        closed = pos.update(bar_high=1.1205, bar_low=1.1000, bar_close=1.1180)
        assert closed is True
        assert trade.exit_price == 1.1200  # tp_max, not tp1


class TestSimulatedPositionPhases:
    def test_phase1_sl_moved(self):
        """Price moves 20%+ toward TP1 -> phase transitions to SL_MOVED."""
        trade = _make_trade(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100)
        pos = _SimulatedPosition(trade, "EUR_USD")
        # 20% of distance to TP1 = 0.0020 -> price at 1.1020
        # Bar doesn't hit SL or TP, close is at 1.1025 (25% progress)
        pos.update(bar_high=1.1030, bar_low=1.0980, bar_close=1.1025)
        assert pos.phase == PositionPhase.SL_MOVED
        # SL should have moved closer (halfway between original SL and entry)
        expected_sl = 1.0950 + (1.1000 - 1.0950) * 0.5  # 1.0975
        assert abs(pos.current_sl - expected_sl) < 1e-8

    def test_phase2_break_even(self):
        """After SL_MOVED, profit >= 1x risk distance -> BREAK_EVEN."""
        trade = _make_trade(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100)
        pos = _SimulatedPosition(trade, "EUR_USD")
        # First: get to SL_MOVED
        pos.update(bar_high=1.1030, bar_low=1.0980, bar_close=1.1025)
        assert pos.phase == PositionPhase.SL_MOVED
        # Risk distance = 0.0050. Profit needs to be >= 0.0050 (price at 1.1050+)
        pos.update(bar_high=1.1060, bar_low=1.1020, bar_close=1.1055)
        assert pos.phase == PositionPhase.BREAK_EVEN
        # SL should be near entry + small buffer
        assert pos.current_sl > 1.0999  # Above entry (BE)

    def test_phase3_trailing(self):
        """After BREAK_EVEN, progress >= 70% to TP1 -> TRAILING_TO_TP1."""
        trade = _make_trade(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100)
        pos = _SimulatedPosition(trade, "EUR_USD")
        # Phase 1: SL_MOVED (20%+ progress)
        pos.update(bar_high=1.1030, bar_low=1.0980, bar_close=1.1025)
        # Phase 2: BREAK_EVEN (1x risk = 0.0050 profit)
        pos.update(bar_high=1.1060, bar_low=1.1020, bar_close=1.1055)
        # Phase 3: 70% of TP distance = 0.0070 -> price at 1.1070
        pos.update(bar_high=1.1080, bar_low=1.1060, bar_close=1.1075)
        assert pos.phase == PositionPhase.TRAILING_TO_TP1

    def test_phase4_beyond_tp1(self):
        """After TRAILING, price reaches TP1 -> BEYOND_TP1."""
        trade = _make_trade(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100, tp_max=1.1200)
        pos = _SimulatedPosition(trade, "EUR_USD")
        pos.update(bar_high=1.1030, bar_low=1.0980, bar_close=1.1025)  # SL_MOVED
        pos.update(bar_high=1.1060, bar_low=1.1020, bar_close=1.1055)  # BE
        pos.update(bar_high=1.1080, bar_low=1.1060, bar_close=1.1075)  # TRAILING
        # Close above TP1 but below TP_max
        pos.update(bar_high=1.1110, bar_low=1.1070, bar_close=1.1105)
        assert pos.phase == PositionPhase.BEYOND_TP1

    def test_sell_phase_sl_moved(self):
        """SELL direction: price falls 20%+ toward TP1 -> SL_MOVED."""
        trade = _make_trade(direction="SELL", entry=1.1000, sl=1.1050, tp1=1.0900)
        pos = _SimulatedPosition(trade, "EUR_USD")
        # 20% of distance = 0.0020 -> price at 1.0980
        pos.update(bar_high=1.1010, bar_low=1.0970, bar_close=1.0975)
        assert pos.phase == PositionPhase.SL_MOVED
        # SL should move closer: halfway from 1.1050 toward 1.1000
        expected_sl = 1.1050 - (1.1050 - 1.1000) * 0.5  # 1.1025
        assert abs(pos.current_sl - expected_sl) < 1e-8


class TestSimulatedPositionTrailing:
    def test_trailing_moves_sl_up_for_buy(self):
        """In TRAILING phase, SL should follow price upward."""
        trade = _make_trade(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100, tp_max=1.1200)
        pos = _SimulatedPosition(trade, "EUR_USD")
        pos.phase = PositionPhase.TRAILING_TO_TP1
        pos.current_sl = 1.1000  # At BE
        # Trail distance = TP distance * 0.40 = 0.0100 * 0.40 = 0.0040
        pos._trail(1.1080, pos._TRAIL_PCT)  # price=1.1080
        # new_sl = 1.1080 - 0.0040 = 1.1040
        assert abs(pos.current_sl - 1.1040) < 1e-8

    def test_trailing_never_moves_sl_backward_for_buy(self):
        pos = _SimulatedPosition(
            _make_trade(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100),
            "EUR_USD",
        )
        pos.current_sl = 1.1050
        # Price drops — new_sl would be lower, so SL should not move
        pos._trail(1.1060, pos._TRAIL_PCT)  # new_sl = 1.1060 - 0.0040 = 1.1020 < 1.1050
        assert pos.current_sl == 1.1050  # Unchanged

    def test_aggressive_trail_tighter(self):
        trade = _make_trade(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100)
        pos = _SimulatedPosition(trade, "EUR_USD")
        pos.current_sl = 1.1000
        # Aggressive trail: 20% of TP distance = 0.0020
        pos._trail(1.1120, pos._AGGRESSIVE_TRAIL_PCT)  # new_sl = 1.1120 - 0.0020 = 1.1100
        assert abs(pos.current_sl - 1.1100) < 1e-8


class TestSimulatedPositionClose:
    def test_close_calculates_pnl(self):
        trade = _make_trade(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100)
        pos = _SimulatedPosition(trade, "EUR_USD")
        pos._close(1.1100, "TP_HIT")
        assert trade.pnl == (1.1100 - 1.1000) * abs(trade.units)
        assert trade.outcome == TradeOutcome.WIN

    def test_close_loss_outcome(self):
        trade = _make_trade(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100)
        pos = _SimulatedPosition(trade, "EUR_USD")
        pos._close(1.0950, "SL_HIT")
        assert trade.pnl == (1.0950 - 1.1000) * abs(trade.units)
        assert trade.outcome == TradeOutcome.LOSS

    def test_close_break_even_outcome(self):
        trade = _make_trade(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100)
        pos = _SimulatedPosition(trade, "EUR_USD")
        # Close within 0.5 pip of entry -> break even
        pos._close(1.10002, "SL_HIT")  # 0.02 pip from entry
        assert trade.outcome == TradeOutcome.BREAK_EVEN

    def test_sell_close_pnl(self):
        trade = _make_trade(direction="SELL", entry=1.1000, sl=1.1050, tp1=1.0900)
        trade.units = -1000
        pos = _SimulatedPosition(trade, "EUR_USD")
        pos._close(1.0900, "TP_HIT")
        assert trade.pnl == (1.1000 - 1.0900) * 1000  # 10.0
        assert trade.outcome == TradeOutcome.WIN

    def test_close_sets_bars_held(self):
        trade = _make_trade()
        pos = _SimulatedPosition(trade, "EUR_USD")
        pos.bars_elapsed = 15
        pos._close(1.1100, "TP_HIT")
        assert trade.bars_held == 15

    def test_close_sets_phase_at_exit(self):
        trade = _make_trade()
        pos = _SimulatedPosition(trade, "EUR_USD")
        pos.phase = PositionPhase.TRAILING_TO_TP1
        pos._close(1.1100, "TP_HIT")
        assert trade.phase_at_exit == "trailing"

    def test_tp_hit_no_slippage(self):
        """TP hits are limit orders — no slippage applied."""
        trade = _make_trade(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100)
        pos = _SimulatedPosition(trade, "EUR_USD", slippage_pips=2.0, spread_pips=1.0)
        pos._close(1.1100, "TP_HIT")
        assert trade.exit_price == 1.1100  # No slippage

    def test_sl_hit_has_slippage(self):
        """SL hits are market orders — slippage applied."""
        trade = _make_trade(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100)
        pos = _SimulatedPosition(trade, "EUR_USD", slippage_pips=2.0, spread_pips=1.0)
        pos._close(1.0950, "SL_HIT")
        # BUY exit: price - slip - spread/2 = 1.0950 - 0.0002 - 0.00005
        expected = 1.0950 - _price_from_pips("EUR_USD", 2.0) - _price_from_pips("EUR_USD", 1.0) / 2
        assert abs(trade.exit_price - expected) < 1e-8

    def test_rr_achieved(self):
        trade = _make_trade(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100)
        pos = _SimulatedPosition(trade, "EUR_USD")
        pos._close(1.1100, "TP_HIT")
        # risk = 0.0050, reward = 0.0100, R:R = 2.0
        assert abs(trade.risk_reward_achieved - 2.0) < 0.01


class TestSimulatedPositionForceClose:
    def test_force_close_end_of_data(self):
        trade = _make_trade(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100)
        pos = _SimulatedPosition(trade, "EUR_USD")
        pos.force_close(1.1050, "END_OF_DATA")
        assert pos.closed
        assert trade.exit_reason == "END_OF_DATA"
        assert trade.pnl > 0  # Made some profit

    def test_force_close_already_closed_noop(self):
        trade = _make_trade()
        pos = _SimulatedPosition(trade, "EUR_USD")
        pos._close(1.1100, "TP_HIT")
        original_exit = trade.exit_price
        pos.force_close(1.0900, "END_OF_DATA")  # Should be no-op
        assert trade.exit_price == original_exit  # Unchanged


class TestSimulatedPositionMFEMAE:
    def test_mfe_tracked(self):
        trade = _make_trade(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100)
        pos = _SimulatedPosition(trade, "EUR_USD")
        pos.update(bar_high=1.1060, bar_low=1.0990, bar_close=1.1040)
        # MFE = (1.1060 - 1.1000) / 0.0001 = 60 pips
        assert trade.max_favorable_excursion >= 59.0

    def test_mae_tracked(self):
        trade = _make_trade(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100)
        pos = _SimulatedPosition(trade, "EUR_USD")
        pos.update(bar_high=1.1010, bar_low=1.0960, bar_close=1.0980)
        # MAE = (1.1000 - 1.0960) / 0.0001 = 40 pips
        assert trade.max_adverse_excursion >= 39.0


class TestSimulatedPositionUpdate:
    def test_already_closed_returns_true(self):
        trade = _make_trade()
        pos = _SimulatedPosition(trade, "EUR_USD")
        pos.closed = True
        result = pos.update(1.1010, 1.0990, 1.1000)
        assert result is True

    def test_normal_bar_returns_false(self):
        trade = _make_trade(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100)
        pos = _SimulatedPosition(trade, "EUR_USD")
        result = pos.update(bar_high=1.1010, bar_low=1.0990, bar_close=1.1005)
        assert result is False
        assert pos.bars_elapsed == 1


# ──────────────────────────────────────────────────────────────────
# _HistoricalBrokerAdapter
# ──────────────────────────────────────────────────────────────────

class TestHistoricalBrokerAdapter:
    def _make_store(self):
        dates = pd.date_range("2025-01-01", periods=20, freq="h")
        df = pd.DataFrame(
            {
                "open": [1.1 + i * 0.001 for i in range(20)],
                "high": [1.1 + i * 0.001 + 0.001 for i in range(20)],
                "low": [1.1 + i * 0.001 - 0.001 for i in range(20)],
                "close": [1.1 + i * 0.001 for i in range(20)],
                "volume": [100] * 20,
            },
            index=dates,
        )
        return {"EUR_USD_H1": df}

    @pytest.mark.asyncio
    async def test_get_candles_returns_sliced(self):
        store = self._make_store()
        adapter = _HistoricalBrokerAdapter(store, current_index=9, instrument="EUR_USD")
        candles = await adapter.get_candles("EUR_USD", "H1", count=5)
        assert len(candles) == 5
        # Should be the last 5 of the first 10 bars
        assert candles[-1].close == store["EUR_USD_H1"].iloc[9]["close"]

    @pytest.mark.asyncio
    async def test_get_candles_empty_store(self):
        adapter = _HistoricalBrokerAdapter({}, current_index=5, instrument="EUR_USD")
        candles = await adapter.get_candles("EUR_USD", "H1", count=10)
        assert candles == []

    @pytest.mark.asyncio
    async def test_get_pip_value(self):
        adapter = _HistoricalBrokerAdapter({}, current_index=0, instrument="EUR_USD")
        pv = await adapter.get_pip_value("EUR_USD")
        assert pv == 0.0001

    @pytest.mark.asyncio
    async def test_get_current_price(self):
        store = self._make_store()
        adapter = _HistoricalBrokerAdapter(store, current_index=5, instrument="EUR_USD")
        price = await adapter.get_current_price("EUR_USD")
        assert price.bid < price.ask
        assert price.spread > 0


# ──────────────────────────────────────────────────────────────────
# BacktestConfig defaults
# ──────────────────────────────────────────────────────────────────

class TestBacktestConfig:
    def test_defaults(self):
        cfg = BacktestConfig(instrument="EUR_USD", start_date="2025-01-01", end_date="2025-06-01")
        assert cfg.initial_balance == 10_000.0
        assert cfg.risk_per_trade == 0.01
        assert cfg.slippage_pips == 0.5
        assert cfg.spread_pips == 1.0
        assert cfg.min_rr_ratio == 1.5
        assert cfg.max_concurrent_positions == 3
        assert cfg.cooldown_bars == 2
        assert cfg.max_trades_per_day == 0
        assert cfg.scale_in_require_be is True

    def test_drawdown_levels(self):
        cfg = BacktestConfig(instrument="EUR_USD", start_date="2025-01-01", end_date="2025-06-01")
        # Fibonacci-based drawdown levels per TradingLab
        assert abs(cfg.dd_level_1 - 0.0412) < 1e-4
        assert abs(cfg.dd_level_2 - 0.0618) < 1e-4
        assert abs(cfg.dd_level_3 - 0.0823) < 1e-4


# ──────────────────────────────────────────────────────────────────
# BacktestTrade defaults
# ──────────────────────────────────────────────────────────────────

class TestBacktestTrade:
    def test_defaults(self):
        t = BacktestTrade(
            trade_id="t1",
            instrument="EUR_USD",
            strategy="BLUE_A",
            direction="BUY",
            entry_price=1.1000,
            entry_time="2025-01-01T10:00:00",
        )
        assert t.exit_price == 0.0
        assert t.outcome == TradeOutcome.LOSS
        assert t.pnl == 0.0
        assert t.bars_held == 0
        assert t.max_favorable_excursion == 0.0
        assert t.max_adverse_excursion == 0.0


# ──────────────────────────────────────────────────────────────────
# BacktestResult defaults
# ──────────────────────────────────────────────────────────────────

class TestBacktestResult:
    def test_defaults(self):
        cfg = BacktestConfig(instrument="EUR_USD", start_date="2025-01-01", end_date="2025-06-01")
        r = BacktestResult(config=cfg, trades=[])
        assert r.total_trades == 0
        assert r.win_rate == 0.0
        assert r.sharpe_ratio == 0.0
        assert r.equity_curve == []
        assert r.warnings == []


# ──────────────────────────────────────────────────────────────────
# Backtester._candles_to_df
# ──────────────────────────────────────────────────────────────────

class TestCandlesToDf:
    def test_empty_input(self):
        df = Backtester._candles_to_df([])
        assert df.empty

    def test_normal_candles(self):
        candles = [
            CandleData(time="2025-01-01T10:00:00", open=1.1, high=1.11, low=1.09, close=1.105, volume=100, complete=True),
            CandleData(time="2025-01-01T11:00:00", open=1.105, high=1.115, low=1.095, close=1.11, volume=150, complete=True),
        ]
        df = Backtester._candles_to_df(candles)
        assert len(df) == 2
        assert "open" in df.columns
        assert "close" in df.columns

    def test_skip_incomplete_candles(self):
        candles = [
            CandleData(time="2025-01-01T10:00:00", open=1.1, high=1.11, low=1.09, close=1.105, volume=100, complete=True),
            CandleData(time="2025-01-01T11:00:00", open=1.105, high=1.115, low=1.095, close=1.11, volume=150, complete=False),
        ]
        df = Backtester._candles_to_df(candles)
        assert len(df) == 1  # Incomplete candle skipped

    def test_skip_zero_ohlc_candles(self):
        """Rule #9: skip all-zero OHLC candles."""
        candles = [
            CandleData(time="2025-01-01T10:00:00", open=1.1, high=1.11, low=1.09, close=1.105, volume=100, complete=True),
            CandleData(time="2025-01-01T11:00:00", open=0, high=0, low=0, close=0, volume=0, complete=True),
        ]
        df = Backtester._candles_to_df(candles)
        assert len(df) == 1

    def test_sorted_by_time(self):
        candles = [
            CandleData(time="2025-01-01T12:00:00", open=1.11, high=1.12, low=1.10, close=1.115, volume=100, complete=True),
            CandleData(time="2025-01-01T10:00:00", open=1.1, high=1.11, low=1.09, close=1.105, volume=100, complete=True),
        ]
        df = Backtester._candles_to_df(candles)
        assert df.index[0] < df.index[1]  # Sorted ascending


# ──────────────────────────────────────────────────────────────────
# Backtester._calc_drawdown
# ──────────────────────────────────────────────────────────────────

class TestCalcDrawdown:
    def test_empty_curve(self):
        dd, dd_pct = Backtester._calc_drawdown([])
        assert dd == 0.0
        assert dd_pct == 0.0

    def test_no_drawdown(self):
        curve = [{"equity": 10000}, {"equity": 10100}, {"equity": 10200}]
        dd, dd_pct = Backtester._calc_drawdown(curve)
        assert dd == 0.0
        assert dd_pct == 0.0

    def test_simple_drawdown(self):
        curve = [
            {"equity": 10000},
            {"equity": 10500},  # Peak
            {"equity": 10000},  # Drawdown of 500
            {"equity": 10200},
        ]
        dd, dd_pct = Backtester._calc_drawdown(curve)
        assert dd == 500.0
        assert abs(dd_pct - (500 / 10500 * 100)) < 0.01

    def test_multiple_drawdowns_picks_max(self):
        curve = [
            {"equity": 10000},
            {"equity": 10500},
            {"equity": 10200},  # DD1: 300
            {"equity": 11000},  # New peak
            {"equity": 10000},  # DD2: 1000 (larger)
        ]
        dd, dd_pct = Backtester._calc_drawdown(curve)
        assert dd == 1000.0


# ──────────────────────────────────────────────────────────────────
# Backtester._calc_sharpe
# ──────────────────────────────────────────────────────────────────

class TestCalcSharpe:
    def test_fewer_than_2_trades(self):
        trade = _make_trade()
        trade.pnl = 100
        assert Backtester._calc_sharpe([trade]) == 0.0

    def test_zero_std_returns_zero(self):
        trades = []
        for i in range(5):
            t = _make_trade()
            t.pnl = 100.0
            t.entry_time = f"2025-01-{i + 1:02d}T10:00:00"
            trades.append(t)
        assert Backtester._calc_sharpe(trades) == 0.0

    def test_positive_sharpe(self):
        trades = []
        pnls = [100, 50, 80, -20, 60, 30, 90, -10, 70, 40]
        for i, pnl in enumerate(pnls):
            t = _make_trade()
            t.pnl = pnl
            t.entry_time = f"2025-01-{i + 1:02d}T10:00:00"
            trades.append(t)
        sharpe = Backtester._calc_sharpe(trades)
        assert sharpe > 0  # Net positive returns should give positive Sharpe


# ──────────────────────────────────────────────────────────────────
# Backtester._calc_sortino
# ──────────────────────────────────────────────────────────────────

class TestCalcSortino:
    def test_fewer_than_2_trades(self):
        assert Backtester._calc_sortino([_make_trade()]) == 0.0

    def test_no_downside_positive_mean(self):
        trades = []
        for i in range(5):
            t = _make_trade()
            t.pnl = 50.0 + i * 10
            t.entry_time = f"2025-01-{i + 1:02d}T10:00:00"
            trades.append(t)
        sortino = Backtester._calc_sortino(trades)
        assert sortino == 999.0  # capped for JSON safety

    def test_mixed_returns(self):
        trades = []
        pnls = [100, -30, 80, -20, 60]
        for i, pnl in enumerate(pnls):
            t = _make_trade()
            t.pnl = pnl
            t.entry_time = f"2025-01-{i + 1:02d}T10:00:00"
            trades.append(t)
        sortino = Backtester._calc_sortino(trades)
        assert sortino > 0


# ──────────────────────────────────────────────────────────────────
# Backtester._breakdown_by_key
# ──────────────────────────────────────────────────────────────────

class TestBreakdownByKey:
    def test_empty_trades(self):
        result = Backtester._breakdown_by_key([], key_fn=lambda t: t.strategy)
        assert result == {}

    def test_grouped_stats(self):
        trades = []
        for strat, pnl, outcome in [
            ("BLUE_A", 100, TradeOutcome.WIN),
            ("BLUE_A", -50, TradeOutcome.LOSS),
            ("RED", 80, TradeOutcome.WIN),
        ]:
            t = _make_trade()
            t.strategy = strat
            t.pnl = pnl
            t.outcome = outcome
            trades.append(t)

        result = Backtester._breakdown_by_key(trades, key_fn=lambda t: t.strategy)
        assert "BLUE_A" in result
        assert "RED" in result
        assert result["BLUE_A"]["total_trades"] == 2
        assert result["BLUE_A"]["winning_trades"] == 1
        assert result["BLUE_A"]["losing_trades"] == 1
        assert result["RED"]["total_trades"] == 1
        assert result["RED"]["win_rate"] == 100.0

    def test_profit_factor_no_losses(self):
        trades = []
        t = _make_trade()
        t.strategy = "GREEN"
        t.pnl = 100
        t.outcome = TradeOutcome.WIN
        trades.append(t)
        result = Backtester._breakdown_by_key(trades, key_fn=lambda t: t.strategy)
        assert result["GREEN"]["profit_factor"] == float("inf")


# ──────────────────────────────────────────────────────────────────
# Backtester._empty_result
# ──────────────────────────────────────────────────────────────────

class TestEmptyResult:
    def test_returns_initial_balance(self):
        cfg = BacktestConfig(instrument="EUR_USD", start_date="2025-01-01", end_date="2025-06-01", initial_balance=5000)
        result = Backtester._empty_result(cfg)
        assert result.final_balance == 5000.0
        assert result.trades == []
        assert result.total_trades == 0


# ──────────────────────────────────────────────────────────────────
# Backtester._compute_metrics
# ──────────────────────────────────────────────────────────────────

class TestComputeMetrics:
    def _make_bt(self):
        return Backtester(broker_client=MagicMock())

    def test_basic_metrics(self):
        bt = self._make_bt()
        cfg = BacktestConfig(instrument="EUR_USD", start_date="2025-01-01", end_date="2025-03-01")

        trades = []
        for i, (pnl, outcome) in enumerate([
            (100, TradeOutcome.WIN),
            (-50, TradeOutcome.LOSS),
            (80, TradeOutcome.WIN),
            (0.001, TradeOutcome.BREAK_EVEN),
        ]):
            t = _make_trade()
            t.pnl = pnl
            t.outcome = outcome
            t.entry_time = f"2025-01-{i + 1:02d}T10:00:00"
            t.risk_reward_achieved = pnl / 50 if pnl != 0 else 0
            t.bars_held = 10 + i
            trades.append(t)

        curve = [{"date": "2025-01-01", "balance": 10000, "equity": 10000}]
        result = bt._compute_metrics(cfg, trades, curve, 10130.001)

        assert result.total_trades == 4
        assert result.winning_trades == 2
        assert result.losing_trades == 1
        assert result.break_even_trades == 1
        assert result.win_rate == 50.0
        assert result.total_pnl == round(130.001, 2)
        assert result.final_balance == 10130.0

    def test_warnings_under_100_trades(self):
        bt = self._make_bt()
        cfg = BacktestConfig(instrument="EUR_USD", start_date="2025-01-01", end_date="2025-03-01")
        trades = [_make_trade()]
        trades[0].pnl = 100
        trades[0].outcome = TradeOutcome.WIN
        trades[0].entry_time = "2025-01-01T10:00:00"
        result = bt._compute_metrics(cfg, trades, [], 10100.0)
        assert len(result.warnings) >= 1
        assert "100 trades" in result.warnings[0]

    def test_duration_days(self):
        bt = self._make_bt()
        cfg = BacktestConfig(instrument="EUR_USD", start_date="2025-01-01", end_date="2025-03-01")
        result = bt._compute_metrics(cfg, [], [], 10000.0)
        assert result.duration_days == 59  # Jan(31) + Feb(28)


# ──────────────────────────────────────────────────────────────────
# Backtester._try_open_position
# ──────────────────────────────────────────────────────────────────

class TestTryOpenPosition:
    def _make_bt(self):
        return Backtester(broker_client=MagicMock())

    def _make_signal(self, direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100, strategy="BLUE_A"):
        from strategies.base import SetupSignal, StrategyColor
        signal = MagicMock(spec=SetupSignal)
        signal.direction = direction
        signal.entry_price = entry
        signal.stop_loss = sl
        signal.take_profit_1 = tp1
        signal.take_profit_max = None
        signal.strategy_variant = strategy
        signal.strategy = MagicMock()
        signal.strategy.value = strategy
        signal.confidence = 0.75
        return signal

    def test_valid_signal_opens_position(self):
        bt = self._make_bt()
        cfg = BacktestConfig(instrument="EUR_USD", start_date="2025-01-01", end_date="2025-06-01")
        signal = self._make_signal()
        pos = bt._try_open_position(
            signal=signal, config=cfg, balance=10000, bar_time="2025-01-01T10:00:00",
            bar_close=1.1000, peak_balance=10000,
        )
        assert pos is not None
        assert pos.trade.direction == "BUY"
        assert pos.trade.units > 0

    def test_sl_wrong_side_buy_rejected(self):
        bt = self._make_bt()
        cfg = BacktestConfig(instrument="EUR_USD", start_date="2025-01-01", end_date="2025-06-01")
        # SL above entry for BUY
        signal = self._make_signal(direction="BUY", entry=1.1000, sl=1.1100, tp1=1.1200)
        pos = bt._try_open_position(
            signal=signal, config=cfg, balance=10000, bar_time="2025-01-01T10:00:00",
            bar_close=1.1000, peak_balance=10000,
        )
        assert pos is None

    def test_sl_wrong_side_sell_rejected(self):
        bt = self._make_bt()
        cfg = BacktestConfig(instrument="EUR_USD", start_date="2025-01-01", end_date="2025-06-01")
        # SL below entry for SELL
        signal = self._make_signal(direction="SELL", entry=1.1000, sl=1.0900, tp1=1.0800)
        pos = bt._try_open_position(
            signal=signal, config=cfg, balance=10000, bar_time="2025-01-01T10:00:00",
            bar_close=1.1000, peak_balance=10000,
        )
        assert pos is None

    def test_tp_wrong_side_rejected(self):
        bt = self._make_bt()
        cfg = BacktestConfig(instrument="EUR_USD", start_date="2025-01-01", end_date="2025-06-01")
        # TP below entry for BUY
        signal = self._make_signal(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.0900)
        pos = bt._try_open_position(
            signal=signal, config=cfg, balance=10000, bar_time="2025-01-01T10:00:00",
            bar_close=1.1000, peak_balance=10000,
        )
        assert pos is None

    def test_low_rr_rejected(self):
        bt = self._make_bt()
        cfg = BacktestConfig(instrument="EUR_USD", start_date="2025-01-01", end_date="2025-06-01", min_rr_ratio=2.0)
        # Risk = 50 pips, reward = 60 pips -> R:R = 1.2 < 2.0
        signal = self._make_signal(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1060)
        pos = bt._try_open_position(
            signal=signal, config=cfg, balance=10000, bar_time="2025-01-01T10:00:00",
            bar_close=1.1000, peak_balance=10000,
        )
        assert pos is None

    def test_black_strategy_requires_2_rr(self):
        bt = self._make_bt()
        cfg = BacktestConfig(instrument="EUR_USD", start_date="2025-01-01", end_date="2025-06-01", min_rr_ratio=1.5)
        # R:R = 1.6 which passes 1.5 but fails BLACK's 2.0 requirement
        signal = self._make_signal(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1080, strategy="BLACK")
        pos = bt._try_open_position(
            signal=signal, config=cfg, balance=10000, bar_time="2025-01-01T10:00:00",
            bar_close=1.1000, peak_balance=10000,
        )
        assert pos is None

    def test_sell_position_has_negative_units(self):
        bt = self._make_bt()
        cfg = BacktestConfig(instrument="EUR_USD", start_date="2025-01-01", end_date="2025-06-01")
        signal = self._make_signal(direction="SELL", entry=1.1000, sl=1.1050, tp1=1.0900)
        pos = bt._try_open_position(
            signal=signal, config=cfg, balance=10000, bar_time="2025-01-01T10:00:00",
            bar_close=1.1000, peak_balance=10000,
        )
        assert pos is not None
        assert pos.trade.units < 0

    def test_drawdown_reduces_risk(self):
        bt = self._make_bt()
        cfg = BacktestConfig(instrument="EUR_USD", start_date="2025-01-01", end_date="2025-06-01")
        signal = self._make_signal()

        # Normal risk position
        pos_normal = bt._try_open_position(
            signal=signal, config=cfg, balance=10000, bar_time="2025-01-01T10:00:00",
            bar_close=1.1000, peak_balance=10000,
        )

        # In drawdown (-5% DD exceeds dd_level_1=4.12%)
        pos_dd = bt._try_open_position(
            signal=signal, config=cfg, balance=9500, bar_time="2025-01-01T10:00:00",
            bar_close=1.1000, peak_balance=10000,
        )

        assert pos_normal is not None
        assert pos_dd is not None
        # Drawdown position should have smaller size
        assert abs(pos_dd.trade.units) < abs(pos_normal.trade.units)

    def test_zero_balance_rejected(self):
        """Zero balance means zero risk amount -> zero units -> rejected."""
        bt = self._make_bt()
        cfg = BacktestConfig(instrument="EUR_USD", start_date="2025-01-01", end_date="2025-06-01")
        signal = self._make_signal()
        pos = bt._try_open_position(
            signal=signal, config=cfg, balance=0, bar_time="2025-01-01T10:00:00",
            bar_close=1.1000, peak_balance=10000,
        )
        assert pos is None

    def test_entry_snapped_to_bar_close_when_far(self):
        bt = self._make_bt()
        cfg = BacktestConfig(instrument="EUR_USD", start_date="2025-01-01", end_date="2025-06-01")
        # Signal entry is 50 pips from bar_close (beyond 20-pip tolerance)
        signal = self._make_signal(direction="BUY", entry=1.1050, sl=1.0950, tp1=1.1200)
        pos = bt._try_open_position(
            signal=signal, config=cfg, balance=10000, bar_time="2025-01-01T10:00:00",
            bar_close=1.1000, peak_balance=10000,
        )
        if pos is not None:
            # Entry should be near bar_close, not at signal's 1.1050
            assert abs(pos.trade.entry_price - 1.1000) < 0.0020


# ──────────────────────────────────────────────────────────────────
# Backtester._build_tf_index_map
# ──────────────────────────────────────────────────────────────────

class TestBuildTfIndexMap:
    def test_maps_tf_indices(self):
        bt = Backtester(broker_client=MagicMock())
        dates = pd.date_range("2025-01-01", periods=20, freq="h")
        store = {
            "EUR_USD_H1": pd.DataFrame(
                {"close": range(20)},
                index=dates,
            ),
        }
        # Current H1 time is the 10th bar
        result = bt._build_tf_index_map("EUR_USD", dates[9], store)
        assert result["EUR_USD_H1"] == 9

    def test_empty_df_returns_zero(self):
        bt = Backtester(broker_client=MagicMock())
        store = {"EUR_USD_H1": pd.DataFrame()}
        result = bt._build_tf_index_map("EUR_USD", pd.Timestamp("2025-01-01"), store)
        assert result["EUR_USD_H1"] == 0

    def test_no_bars_before_timestamp_returns_zero(self):
        bt = Backtester(broker_client=MagicMock())
        dates = pd.date_range("2025-01-02", periods=5, freq="h")
        store = {
            "EUR_USD_H1": pd.DataFrame({"close": range(5)}, index=dates),
        }
        # Query time before all bars
        result = bt._build_tf_index_map("EUR_USD", pd.Timestamp("2025-01-01"), store)
        assert result["EUR_USD_H1"] == 0


# ──────────────────────────────────────────────────────────────────
# TradeOutcome enum
# ──────────────────────────────────────────────────────────────────

class TestTradeOutcome:
    def test_values(self):
        assert TradeOutcome.WIN.value == "win"
        assert TradeOutcome.LOSS.value == "loss"
        assert TradeOutcome.BREAK_EVEN.value == "break_even"
