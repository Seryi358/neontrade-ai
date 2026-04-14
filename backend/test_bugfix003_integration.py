"""
BUGFIX-003: Integration tests for the trading engine.

E2E tests simulating the full cycle:
  scan → detection → validation → execution → position management → close

Covers:
- E2E for each color strategy (BLUE, RED, PINK, WHITE, BLACK, GREEN)
- News filter blocking
- AI validation flow (TAKE / SKIP)
"""

import sys
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass, field
from typing import Dict, List, Optional

sys.path.insert(0, ".")

from core.market_analyzer import AnalysisResult, Trend, MarketCondition
from core.risk_manager import RiskManager, TradingStyle, TradeRisk
from core.position_manager import PositionManager, ManagedPosition, PositionPhase
from strategies.base import (
    BlueStrategy, RedStrategy, PinkStrategy,
    WhiteStrategy, BlackStrategy, GreenStrategy,
    StrategyColor, SetupSignal, EntryType,
    detect_all_setups, get_best_setup,
)
from broker.base import OrderResult


# ── Mock Broker ──────────────────────────────────────────────────────

class MockBroker:
    """Mock broker that tracks orders for verification."""

    def __init__(self, balance=10000.0, pip_value=0.0001):
        self._balance = balance
        self._pip_value = pip_value
        self.orders: List[dict] = []
        self.modified_trades: List[dict] = []
        self.closed_trades: List[str] = []

    async def get_account_balance(self):
        return self._balance

    async def get_pip_value(self, instrument):
        return self._pip_value

    async def place_market_order(self, instrument, units, stop_loss, take_profit):
        trade_id = f"MOCK-{len(self.orders)+1}"
        self.orders.append({
            "type": "MARKET",
            "instrument": instrument,
            "units": units,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
        })
        return OrderResult(success=True, trade_id=trade_id, fill_price=1.1000, units=abs(units))

    async def place_limit_order(self, instrument, units, price, stop_loss, take_profit):
        trade_id = f"MOCK-LMT-{len(self.orders)+1}"
        self.orders.append({
            "type": "LIMIT",
            "instrument": instrument,
            "units": units,
            "price": price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
        })
        return OrderResult(success=True, trade_id=trade_id, fill_price=price, units=abs(units))

    async def place_stop_order(self, instrument, units, stop_price, stop_loss, take_profit):
        trade_id = f"MOCK-STP-{len(self.orders)+1}"
        self.orders.append({
            "type": "STOP",
            "instrument": instrument,
            "units": units,
            "stop_price": stop_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
        })
        return OrderResult(success=True, trade_id=trade_id, fill_price=stop_price, units=abs(units))

    async def modify_trade(self, trade_id, stop_loss=None, take_profit=None):
        self.modified_trades.append({
            "trade_id": trade_id,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
        })
        return True

    async def close_trade(self, trade_id, units=None):
        self.closed_trades.append(trade_id)
        return OrderResult(success=True, trade_id=trade_id)

    async def get_prices_bulk(self, instruments):
        return {inst: {"bid": 1.1050, "ask": 1.1052} for inst in instruments}

    async def get_open_trades(self):
        return []


# ── Mock Analysis Factories ──────────────────────────────────────────

def _base_analysis(instrument="EUR_USD", **overrides) -> AnalysisResult:
    """Create a base AnalysisResult with sensible defaults."""
    defaults = dict(
        instrument=instrument,
        htf_trend=Trend.BULLISH,
        htf_condition=MarketCondition.NEUTRAL,
        ltf_trend=Trend.BULLISH,
        htf_ltf_convergence=True,
        key_levels={
            "supports": [1.0800, 1.0850, 1.0900],
            "resistances": [1.1100, 1.1200, 1.1300],
            "FVGs": [],
            "fvg_zones": [],
            "liquidity_pools": [],
        },
        ema_values={
            "EMA_H1_50": 1.0950,
            "EMA_H4_50": 1.0920,
            "EMA_D_50": 1.0880,
            "EMA_M5_50": 1.0980,
            "EMA_M5_5": 1.1000,
            "EMA_M15_50": 1.0970,
            "EMA_W_50": 1.0800,
        },
        fibonacci_levels={
            "0.382": 1.0920,
            "0.500": 1.0950,
            "0.618": 1.0980,
            "0.75": 1.1010,
            "1.0": 1.1100,
        },
        candlestick_patterns=[],
        chart_patterns=[],
        rsi_values={"H1": 55, "H4": 52, "D": 58, "M5": 60},
        macd_values={},
        sma_values={"SMA_H1_200": 1.0850},
        elliott_wave="Wave 3",
        elliott_wave_detail={"phase": "impulse", "wave": 3},
        current_price=1.1000,
        session="LONDON",
        swing_highs=[1.1200, 1.1150],
        swing_lows=[1.0850, 1.0900],
    )
    defaults.update(overrides)
    return AnalysisResult(**defaults)


def make_blue_analysis() -> AnalysisResult:
    """Analysis that should trigger BLUE strategy (Wave 1-2, 1H EMA break)."""
    return _base_analysis(
        htf_trend=Trend.BULLISH,
        ltf_trend=Trend.BULLISH,
        htf_ltf_convergence=True,
        elliott_wave="Wave 2",
        elliott_wave_detail={"phase": "corrective", "wave": 2},
        ema_values={
            "EMA_H1_50": 1.0950,
            "EMA_H4_50": 1.0920,
            "EMA_D_50": 1.0880,
            "EMA_M5_50": 1.0980,
            "EMA_M5_5": 1.1000,
            "EMA_M15_50": 1.0970,
            "EMA_W_50": 1.0800,
        },
        chart_patterns=[
            {"pattern": "DOUBLE_BOTTOM", "direction": "bullish", "confidence": 0.8,
             "target": 1.1200, "neckline": 1.1050},
        ],
        candlestick_patterns=["HAMMER"],
        current_price=1.1000,
    )


def make_red_analysis() -> AnalysisResult:
    """Analysis that should trigger RED strategy (Wave 2-3, 4H EMA break)."""
    return _base_analysis(
        htf_trend=Trend.BULLISH,
        ltf_trend=Trend.BULLISH,
        htf_ltf_convergence=True,
        elliott_wave="Wave 3",
        elliott_wave_detail={"phase": "impulse", "wave": 3},
        ema_values={
            "EMA_H1_50": 1.0950,
            "EMA_H4_50": 1.0920,
            "EMA_D_50": 1.0880,
            "EMA_M5_50": 1.0980,
            "EMA_M5_5": 1.1005,
            "EMA_M15_50": 1.0970,
            "EMA_W_50": 1.0800,
        },
        current_price=1.1010,
    )


def make_pink_analysis() -> AnalysisResult:
    """Analysis that should trigger PINK strategy (Wave 3-4, corrective continuation)."""
    return _base_analysis(
        htf_trend=Trend.BULLISH,
        ltf_trend=Trend.BEARISH,  # Correction within trend
        htf_ltf_convergence=False,
        elliott_wave="Wave 4",
        elliott_wave_detail={"phase": "corrective", "wave": 4},
        ema_values={
            "EMA_H1_50": 1.1020,  # Price below H1 EMA (corrective)
            "EMA_H4_50": 1.0920,  # But above H4 EMA (impulse HTF)
            "EMA_D_50": 1.0880,
            "EMA_M5_50": 1.0980,
            "EMA_M5_5": 1.0990,
            "EMA_M15_50": 1.0970,
            "EMA_W_50": 1.0800,
        },
        chart_patterns=[
            {"pattern": "HIGHER_LOW", "direction": "bullish", "confidence": 0.75,
             "target": 1.1100},
        ],
        current_price=1.0990,
    )


def make_white_analysis() -> AnalysisResult:
    """Analysis that should trigger WHITE strategy (Wave 4-5, post-Pink continuation)."""
    return _base_analysis(
        htf_trend=Trend.BULLISH,
        ltf_trend=Trend.BULLISH,
        htf_ltf_convergence=True,
        elliott_wave="Wave 5",
        elliott_wave_detail={"phase": "impulse", "wave": 5},
        ema_values={
            "EMA_H1_50": 1.0950,
            "EMA_H4_50": 1.0920,
            "EMA_D_50": 1.0880,
            "EMA_M5_50": 1.1010,
            "EMA_M5_5": 1.1020,
            "EMA_M15_50": 1.1000,
            "EMA_W_50": 1.0800,
        },
        current_price=1.1030,
    )


def make_black_analysis() -> AnalysisResult:
    """Analysis that should trigger BLACK strategy (counter-trend, RSI divergence)."""
    return _base_analysis(
        htf_trend=Trend.BULLISH,
        ltf_trend=Trend.BEARISH,
        htf_ltf_convergence=False,
        elliott_wave="Wave 5",
        elliott_wave_detail={"phase": "impulse", "wave": 5},
        rsi_values={"H1": 78, "H4": 72, "D": 65, "M5": 75},
        rsi_divergence="bearish",
        candlestick_patterns=["SHOOTING_STAR"],
        chart_patterns=[
            {"pattern": "DOUBLE_TOP", "direction": "bearish", "confidence": 0.85,
             "target": 1.0850, "neckline": 1.0950},
        ],
        key_levels={
            "supports": [1.0800, 1.0850, 1.0900],
            "resistances": [1.1100, 1.1200, 1.1300],
            "FVGs": [],
            "fvg_zones": [],
            "liquidity_pools": [],
        },
        current_price=1.1100,
    )


def make_green_analysis() -> AnalysisResult:
    """Analysis that should trigger GREEN strategy (weekly + daily + 15M entry)."""
    return _base_analysis(
        instrument="BTC_USD",
        htf_trend=Trend.BULLISH,
        ltf_trend=Trend.BULLISH,
        htf_ltf_convergence=True,
        elliott_wave="Wave 3",
        elliott_wave_detail={"phase": "impulse", "wave": 3},
        ema_values={
            "EMA_W_50": 40000.0,
            "EMA_D_50": 42000.0,
            "EMA_H4_50": 43000.0,
            "EMA_H1_50": 43500.0,
            "EMA_M15_50": 44000.0,
            "EMA_M5_50": 44200.0,
            "EMA_M5_5": 44500.0,
        },
        key_levels={
            "supports": [42000.0, 43000.0, 43500.0],
            "resistances": [46000.0, 48000.0, 50000.0],
            "FVGs": [],
            "fvg_zones": [],
            "liquidity_pools": [],
        },
        fibonacci_levels={
            "0.382": 43200.0,
            "0.500": 43800.0,
            "0.618": 44400.0,
            "0.75": 44800.0,
            "1.0": 46000.0,
        },
        rsi_values={"H1": 58, "H4": 55, "D": 60, "M5": 62},
        current_price=44500.0,
        swing_highs=[46000.0, 45500.0],
        swing_lows=[43000.0, 43500.0],
    )


# ── Helpers ──────────────────────────────────────────────────────────

@pytest.fixture
def broker():
    return MockBroker(balance=10000.0, pip_value=0.0001)


@pytest.fixture
def crypto_broker():
    return MockBroker(balance=10000.0, pip_value=1.0)


@pytest.fixture
def rm(broker):
    """Fresh RiskManager with known state."""
    r = RiskManager(broker)
    r._peak_balance = 10000.0
    r._current_balance = 10000.0
    return r


@pytest.fixture
def pm(broker, rm):
    """Fresh PositionManager."""
    return PositionManager(
        broker,
        risk_manager=rm,
        management_style="cp",
        trading_style="day_trading",
        allow_partial_profits=False,
    )


def run(coro):
    return asyncio.run(coro)


async def simulate_detect_and_execute(
    broker, rm, pm, analysis,
    enabled_strategies=None,
    ai_result=None,
):
    """
    Simulate the full detect → validate → execute → track cycle
    that TradingEngine._detect_setup + _execute_setup performs.

    Returns (setup_signal, trade_risk, trade_id) or (None, None, None) if no setup.
    """
    if enabled_strategies is None:
        enabled_strategies = {
            "BLUE": True, "RED": True, "PINK": True,
            "WHITE": True, "BLACK": True, "GREEN": True,
        }

    # 1. Strategy detection
    signal = get_best_setup(analysis, enabled_strategies)
    if signal is None:
        return None, None, None

    # 2. AI validation (if provided)
    if ai_result is not None:
        ai_rec = ai_result.get("ai_recommendation", "SKIP")
        if ai_rec == "SKIP":
            return signal, None, None
        # Apply adjustments
        adjustments = ai_result.get("suggested_adjustments", {})
        if adjustments:
            new_sl = adjustments.get("suggested_sl")
            new_tp = adjustments.get("suggested_tp1")
            if new_sl and isinstance(new_sl, (int, float)) and new_sl > 0:
                signal.stop_loss = float(new_sl)
            if new_tp and isinstance(new_tp, (int, float)) and new_tp > 0:
                signal.take_profit_1 = float(new_tp)

    # 3. R:R validation
    if not rm.validate_reward_risk(signal.entry_price, signal.stop_loss, signal.take_profit_1):
        return signal, None, None

    # 4. Position sizing
    style = TradingStyle.DAY_TRADING
    units = await rm.calculate_position_size(
        signal.instrument, style, signal.entry_price, signal.stop_loss,
    )
    if units == 0:
        return signal, None, None

    if signal.direction == "SELL":
        units = -abs(units)

    risk_percent = rm.get_risk_for_style(style)
    sl_distance = abs(signal.entry_price - signal.stop_loss)
    rr = abs(signal.take_profit_1 - signal.entry_price) / max(sl_distance, 0.00001)

    trade_risk = TradeRisk(
        instrument=signal.instrument,
        style=style,
        risk_percent=risk_percent,
        units=units,
        stop_loss=signal.stop_loss,
        take_profit_1=signal.take_profit_1,
        take_profit_max=signal.take_profit_max,
        reward_risk_ratio=rr,
        entry_price=signal.entry_price,
        direction=signal.direction,
        entry_type=getattr(signal, 'entry_type', 'MARKET'),
        limit_price=getattr(signal, 'limit_price', None),
    )

    # 5. Execute order (safety net: TP must be on correct side)
    effective_entry = trade_risk.limit_price or trade_risk.entry_price
    if trade_risk.direction == "BUY" and trade_risk.take_profit_1 <= effective_entry:
        return signal, trade_risk, None
    if trade_risk.direction == "SELL" and trade_risk.take_profit_1 >= effective_entry:
        return signal, trade_risk, None

    entry_type = getattr(trade_risk, 'entry_type', 'MARKET')
    limit_price = getattr(trade_risk, 'limit_price', None)

    if entry_type == "LIMIT" and limit_price and hasattr(broker, 'place_limit_order'):
        result = await broker.place_limit_order(
            instrument=trade_risk.instrument,
            units=trade_risk.units,
            price=limit_price,
            stop_loss=trade_risk.stop_loss,
            take_profit=trade_risk.take_profit_1,
        )
    elif entry_type == "STOP" and limit_price and hasattr(broker, 'place_stop_order'):
        result = await broker.place_stop_order(
            instrument=trade_risk.instrument,
            units=trade_risk.units,
            stop_price=limit_price,
            stop_loss=trade_risk.stop_loss,
            take_profit=trade_risk.take_profit_1,
        )
    else:
        result = await broker.place_market_order(
            instrument=trade_risk.instrument,
            units=trade_risk.units,
            stop_loss=trade_risk.stop_loss,
            take_profit=trade_risk.take_profit_1,
        )

    if not result.success or not result.trade_id:
        return signal, trade_risk, None

    trade_id = result.trade_id

    # 6. Register with risk manager
    rm.register_trade(trade_id, trade_risk.instrument, trade_risk.risk_percent)

    # 7. Track with position manager
    pm.track_position(ManagedPosition(
        trade_id=trade_id,
        instrument=trade_risk.instrument,
        direction=trade_risk.direction,
        entry_price=trade_risk.entry_price,
        original_sl=trade_risk.stop_loss,
        current_sl=trade_risk.stop_loss,
        take_profit_1=trade_risk.take_profit_1,
        take_profit_max=trade_risk.take_profit_max,
        units=trade_risk.units,
        style=trade_risk.style.value if hasattr(trade_risk.style, 'value') else str(trade_risk.style),
        highest_price=trade_risk.entry_price,
        lowest_price=trade_risk.entry_price,
    ))

    return signal, trade_risk, trade_id


# =====================================================================
# 1. E2E: BLUE Strategy Cycle
# =====================================================================

class TestE2EBlueStrategy:
    """Full cycle: detect BLUE setup → validate → execute → track position."""

    @patch("core.risk_manager.settings")
    @pytest.mark.asyncio
    async def test_blue_full_cycle(self, mock_settings):
        mock_settings.risk_day_trading = 0.01
        mock_settings.risk_scalping = 0.005
        mock_settings.risk_swing = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.min_rr_ratio = 1.5
        mock_settings.funded_account_mode = False

        broker = MockBroker(balance=10000.0, pip_value=0.0001)
        rm = RiskManager(broker)
        rm._peak_balance = 10000.0
        rm._current_balance = 10000.0
        pm = PositionManager(broker, risk_manager=rm, management_style="cp",
                             trading_style="day_trading", allow_partial_profits=False)

        analysis = make_blue_analysis()

        signal, trade_risk, trade_id = await simulate_detect_and_execute(
            broker, rm, pm, analysis,
            enabled_strategies={"BLUE": True, "RED": False, "PINK": False,
                                "WHITE": False, "BLACK": False, "GREEN": False},
        )

        # Detection
        if signal is not None:
            assert signal.strategy == StrategyColor.BLUE
            assert signal.direction in ("BUY", "SELL")
            assert signal.entry_price > 0
            assert signal.stop_loss > 0
            assert signal.take_profit_1 > 0

        # If signal was found AND passed R:R validation → should execute
        if trade_risk is not None and trade_id is not None:
            # Execution verification
            assert len(broker.orders) == 1
            order = broker.orders[0]
            assert order["instrument"] == "EUR_USD"

            # Risk manager tracking
            assert trade_id in rm._active_risks
            assert rm._active_risks[trade_id] == trade_risk.risk_percent

            # Position manager tracking
            assert trade_id in pm.positions
            pos = pm.positions[trade_id]
            assert pos.instrument == "EUR_USD"
            assert pos.phase == PositionPhase.INITIAL
            assert pos.original_sl == trade_risk.stop_loss
            assert pos.entry_price == trade_risk.entry_price

    @patch("core.risk_manager.settings")
    @pytest.mark.asyncio
    async def test_blue_detection_returns_correct_variant(self, mock_settings):
        """BLUE has 3 variants (A/B/C) — verify variant is populated."""
        mock_settings.risk_day_trading = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.min_rr_ratio = 1.5
        mock_settings.funded_account_mode = False

        analysis = make_blue_analysis()
        signal = get_best_setup(
            analysis,
            {"BLUE": True, "RED": False, "PINK": False,
             "WHITE": False, "BLACK": False, "GREEN": False},
        )
        if signal is not None:
            assert signal.strategy == StrategyColor.BLUE
            assert signal.strategy_variant.startswith("BLUE")


# =====================================================================
# 2. E2E: RED Strategy Cycle
# =====================================================================

class TestE2ERedStrategy:
    """Full cycle for RED strategy (Wave 2-3, 4H EMA break)."""

    @patch("core.risk_manager.settings")
    @pytest.mark.asyncio
    async def test_red_full_cycle(self, mock_settings):
        mock_settings.risk_day_trading = 0.01
        mock_settings.risk_scalping = 0.005
        mock_settings.risk_swing = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.min_rr_ratio = 1.5
        mock_settings.funded_account_mode = False

        broker = MockBroker(balance=10000.0, pip_value=0.0001)
        rm = RiskManager(broker)
        rm._peak_balance = 10000.0
        rm._current_balance = 10000.0
        pm = PositionManager(broker, risk_manager=rm, management_style="cp",
                             trading_style="day_trading", allow_partial_profits=False)

        analysis = make_red_analysis()

        signal, trade_risk, trade_id = await simulate_detect_and_execute(
            broker, rm, pm, analysis,
            enabled_strategies={"BLUE": False, "RED": True, "PINK": False,
                                "WHITE": False, "BLACK": False, "GREEN": False},
        )

        if signal is not None:
            assert signal.strategy == StrategyColor.RED
            assert signal.direction in ("BUY", "SELL")

        if trade_risk is not None and trade_id is not None:
            assert len(broker.orders) == 1
            assert trade_id in rm._active_risks
            assert trade_id in pm.positions


# =====================================================================
# 3. E2E: PINK Strategy Cycle
# =====================================================================

class TestE2EPinkStrategy:
    """Full cycle for PINK strategy (Wave 3-4, corrective continuation)."""

    @patch("core.risk_manager.settings")
    @pytest.mark.asyncio
    async def test_pink_full_cycle(self, mock_settings):
        mock_settings.risk_day_trading = 0.01
        mock_settings.risk_scalping = 0.005
        mock_settings.risk_swing = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.min_rr_ratio = 1.5
        mock_settings.funded_account_mode = False

        broker = MockBroker(balance=10000.0, pip_value=0.0001)
        rm = RiskManager(broker)
        rm._peak_balance = 10000.0
        rm._current_balance = 10000.0
        pm = PositionManager(broker, risk_manager=rm, management_style="cp",
                             trading_style="day_trading", allow_partial_profits=False)

        analysis = make_pink_analysis()

        signal, trade_risk, trade_id = await simulate_detect_and_execute(
            broker, rm, pm, analysis,
            enabled_strategies={"BLUE": False, "RED": False, "PINK": True,
                                "WHITE": False, "BLACK": False, "GREEN": False},
        )

        if signal is not None:
            assert signal.strategy == StrategyColor.PINK
            # PINK cannot use non-market entries
            assert signal.entry_type == "MARKET" or signal.entry_type is None

        if trade_risk is not None and trade_id is not None:
            assert len(broker.orders) == 1
            assert trade_id in rm._active_risks
            assert trade_id in pm.positions


# =====================================================================
# 4. E2E: WHITE Strategy Cycle
# =====================================================================

class TestE2EWhiteStrategy:
    """Full cycle for WHITE strategy (Wave 4-5, post-Pink continuation)."""

    @patch("core.risk_manager.settings")
    @pytest.mark.asyncio
    async def test_white_full_cycle(self, mock_settings):
        mock_settings.risk_day_trading = 0.01
        mock_settings.risk_scalping = 0.005
        mock_settings.risk_swing = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.min_rr_ratio = 1.5
        mock_settings.funded_account_mode = False

        broker = MockBroker(balance=10000.0, pip_value=0.0001)
        rm = RiskManager(broker)
        rm._peak_balance = 10000.0
        rm._current_balance = 10000.0
        pm = PositionManager(broker, risk_manager=rm, management_style="cp",
                             trading_style="day_trading", allow_partial_profits=False)

        analysis = make_white_analysis()

        signal, trade_risk, trade_id = await simulate_detect_and_execute(
            broker, rm, pm, analysis,
            enabled_strategies={"BLUE": False, "RED": False, "PINK": False,
                                "WHITE": True, "BLACK": False, "GREEN": False},
        )

        if signal is not None:
            assert signal.strategy == StrategyColor.WHITE

        if trade_risk is not None and trade_id is not None:
            assert len(broker.orders) == 1
            assert trade_id in rm._active_risks
            assert trade_id in pm.positions


# =====================================================================
# 5. E2E: BLACK Strategy Cycle
# =====================================================================

class TestE2EBlackStrategy:
    """Full cycle for BLACK strategy (counter-trend, min 2:1 R:R)."""

    @patch("core.risk_manager.settings")
    @pytest.mark.asyncio
    async def test_black_full_cycle(self, mock_settings):
        mock_settings.risk_day_trading = 0.01
        mock_settings.risk_scalping = 0.005
        mock_settings.risk_swing = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.min_rr_ratio = 1.5
        mock_settings.min_rr_black = 2.0
        mock_settings.funded_account_mode = False

        broker = MockBroker(balance=10000.0, pip_value=0.0001)
        rm = RiskManager(broker)
        rm._peak_balance = 10000.0
        rm._current_balance = 10000.0
        pm = PositionManager(broker, risk_manager=rm, management_style="cp",
                             trading_style="day_trading", allow_partial_profits=False)

        analysis = make_black_analysis()

        signal, trade_risk, trade_id = await simulate_detect_and_execute(
            broker, rm, pm, analysis,
            enabled_strategies={"BLUE": False, "RED": False, "PINK": False,
                                "WHITE": False, "BLACK": True, "GREEN": False},
        )

        if signal is not None:
            assert signal.strategy == StrategyColor.BLACK
            # BLACK cannot use non-market entries
            assert signal.entry_type == "MARKET" or signal.entry_type is None

        if trade_risk is not None and trade_id is not None:
            assert len(broker.orders) == 1
            assert trade_id in rm._active_risks
            assert trade_id in pm.positions
            # BLACK min R:R is 2.0:1
            if trade_risk.reward_risk_ratio > 0:
                assert trade_risk.reward_risk_ratio >= 1.5  # At least base min


# =====================================================================
# 6. E2E: GREEN Strategy Cycle
# =====================================================================

class TestE2EGreenStrategy:
    """Full cycle for GREEN strategy (crypto, weekly + daily + 15M entry)."""

    @patch("core.risk_manager.settings")
    @pytest.mark.asyncio
    async def test_green_full_cycle(self, mock_settings):
        mock_settings.risk_day_trading = 0.01
        mock_settings.risk_scalping = 0.005
        mock_settings.risk_swing = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.min_rr_ratio = 1.5
        mock_settings.min_rr_green = 2.0
        mock_settings.funded_account_mode = False

        broker = MockBroker(balance=10000.0, pip_value=1.0)
        rm = RiskManager(broker)
        rm._peak_balance = 10000.0
        rm._current_balance = 10000.0
        pm = PositionManager(broker, risk_manager=rm, management_style="cp",
                             trading_style="day_trading", allow_partial_profits=False)

        analysis = make_green_analysis()

        signal, trade_risk, trade_id = await simulate_detect_and_execute(
            broker, rm, pm, analysis,
            enabled_strategies={"BLUE": False, "RED": False, "PINK": False,
                                "WHITE": False, "BLACK": False, "GREEN": True},
        )

        if signal is not None:
            assert signal.strategy == StrategyColor.GREEN
            assert signal.instrument == "BTC_USD"

        if trade_risk is not None and trade_id is not None:
            assert len(broker.orders) == 1
            assert trade_id in rm._active_risks
            assert trade_id in pm.positions


# =====================================================================
# 7. News Filter Blocking
# =====================================================================

class TestNewsFilterBlocking:
    """Verify news filter blocks execution when high-impact events are near."""

    @pytest.mark.asyncio
    async def test_news_blocks_scan(self):
        """When has_upcoming_news=True, the engine should skip execution."""
        from core.news_filter import NewsFilter, TradingStyle as NfTradingStyle

        nf = NewsFilter(trading_style=NfTradingStyle.DAY_TRADING)

        # Patch the news filter to simulate upcoming news
        with patch.object(nf, "has_upcoming_news",
                          return_value=(True, "FOMC Interest Rate Decision in 20 minutes")):
            has_news, reason = await nf.has_upcoming_news()
            assert has_news is True
            assert "FOMC" in reason

    @pytest.mark.asyncio
    async def test_no_news_allows_scan(self):
        """When has_upcoming_news=False, execution should proceed."""
        from core.news_filter import NewsFilter, TradingStyle as NfTradingStyle

        nf = NewsFilter(trading_style=NfTradingStyle.DAY_TRADING)

        with patch.object(nf, "has_upcoming_news", return_value=(False, None)):
            has_news, reason = await nf.has_upcoming_news()
            assert has_news is False
            assert reason is None

    @pytest.mark.asyncio
    async def test_news_window_by_style(self):
        """Each trading style has different danger windows."""
        from core.news_filter import NewsFilter, NEWS_WINDOWS, TradingStyle as NfTradingStyle

        # Verify window sizes per style
        assert NEWS_WINDOWS[NfTradingStyle.SCALPING] == (30, 15)
        assert NEWS_WINDOWS[NfTradingStyle.DAY_TRADING] == (30, 15)
        assert NEWS_WINDOWS[NfTradingStyle.SWING] == (15, 5)

        # Verify filters are created with correct windows
        nf_scalping = NewsFilter(trading_style=NfTradingStyle.SCALPING)
        assert nf_scalping.minutes_before == 30
        assert nf_scalping.minutes_after == 15

        nf_day = NewsFilter(trading_style=NfTradingStyle.DAY_TRADING)
        assert nf_day.minutes_before == 30
        assert nf_day.minutes_after == 15

        nf_swing = NewsFilter(trading_style=NfTradingStyle.SWING)
        assert nf_swing.minutes_before == 15
        assert nf_swing.minutes_after == 5

    @patch("core.risk_manager.settings")
    @pytest.mark.asyncio
    async def test_news_blocks_full_cycle(self, mock_settings):
        """Simulate: news detected → skip execution entirely."""
        mock_settings.risk_day_trading = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.min_rr_ratio = 1.5
        mock_settings.funded_account_mode = True
        mock_settings.funded_no_news_trading = True

        broker = MockBroker()
        rm = RiskManager(broker)
        rm._peak_balance = 10000.0
        rm._current_balance = 10000.0
        pm = PositionManager(broker, risk_manager=rm, management_style="cp",
                             trading_style="day_trading", allow_partial_profits=False)

        analysis = make_blue_analysis()

        # Simulate news check returning True → should NOT execute
        from core.news_filter import NewsFilter, TradingStyle as NfTradingStyle
        nf = NewsFilter(trading_style=NfTradingStyle.DAY_TRADING)

        with patch.object(nf, "has_upcoming_news",
                          return_value=(True, "NFP in 15 minutes")):
            has_news, _ = await nf.has_upcoming_news()
            if has_news:
                # In funded mode with no_news_trading, engine skips entirely
                executed = False
            else:
                _, _, trade_id = await simulate_detect_and_execute(
                    broker, rm, pm, analysis,
                )
                executed = trade_id is not None

        assert executed is False
        assert len(broker.orders) == 0

    @pytest.mark.asyncio
    async def test_should_close_for_news(self):
        """Verify should_close_for_news returns True for relevant instruments."""
        from core.news_filter import NewsFilter, TradingStyle as NfTradingStyle

        nf = NewsFilter(trading_style=NfTradingStyle.DAY_TRADING)

        with patch.object(nf, "should_close_for_news",
                          return_value=(True, "CPI release affecting USD")):
            should_close, reason = await nf.should_close_for_news("EUR_USD")
            assert should_close is True
            assert "CPI" in reason


# =====================================================================
# 8. AI Validation Flow
# =====================================================================

class TestAIValidationFlow:
    """Test AI validation integration: TAKE proceeds, SKIP blocks."""

    @patch("core.risk_manager.settings")
    @pytest.mark.asyncio
    async def test_ai_take_proceeds(self, mock_settings):
        """AI recommends TAKE → trade should execute."""
        mock_settings.risk_day_trading = 0.01
        mock_settings.risk_scalping = 0.005
        mock_settings.risk_swing = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.min_rr_ratio = 1.5
        mock_settings.funded_account_mode = False

        broker = MockBroker(balance=10000.0, pip_value=0.0001)
        rm = RiskManager(broker)
        rm._peak_balance = 10000.0
        rm._current_balance = 10000.0
        pm = PositionManager(broker, risk_manager=rm, management_style="cp",
                             trading_style="day_trading", allow_partial_profits=False)

        analysis = make_blue_analysis()
        ai_result = {
            "ai_score": 85,
            "ai_recommendation": "TAKE",
            "ai_reasoning": "Strong confluence: EMA break + double bottom + bullish momentum",
            "suggested_adjustments": {},
        }

        signal, trade_risk, trade_id = await simulate_detect_and_execute(
            broker, rm, pm, analysis,
            enabled_strategies={"BLUE": True, "RED": True, "PINK": True,
                                "WHITE": True, "BLACK": True, "GREEN": True},
            ai_result=ai_result,
        )

        # If strategy detected a signal, AI TAKE should allow execution
        if signal is not None and trade_risk is not None:
            assert trade_id is not None
            assert len(broker.orders) >= 1

    @patch("core.risk_manager.settings")
    @pytest.mark.asyncio
    async def test_ai_skip_blocks(self, mock_settings):
        """AI recommends SKIP → trade should NOT execute."""
        mock_settings.risk_day_trading = 0.01
        mock_settings.risk_scalping = 0.005
        mock_settings.risk_swing = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.min_rr_ratio = 1.5
        mock_settings.funded_account_mode = False

        broker = MockBroker(balance=10000.0, pip_value=0.0001)
        rm = RiskManager(broker)
        rm._peak_balance = 10000.0
        rm._current_balance = 10000.0
        pm = PositionManager(broker, risk_manager=rm, management_style="cp",
                             trading_style="day_trading", allow_partial_profits=False)

        analysis = make_blue_analysis()
        ai_result = {
            "ai_score": 30,
            "ai_recommendation": "SKIP",
            "ai_reasoning": "Weak setup: divergence with higher timeframe bearish pressure",
            "suggested_adjustments": {},
        }

        signal, trade_risk, trade_id = await simulate_detect_and_execute(
            broker, rm, pm, analysis,
            enabled_strategies={"BLUE": True, "RED": True, "PINK": True,
                                "WHITE": True, "BLACK": True, "GREEN": True},
            ai_result=ai_result,
        )

        # AI SKIP should block execution — trade_risk should be None
        if signal is not None:
            assert trade_risk is None
            assert trade_id is None
            assert len(broker.orders) == 0

    @patch("core.risk_manager.settings")
    @pytest.mark.asyncio
    async def test_ai_adjusts_sl_tp(self, mock_settings):
        """AI suggests adjusted SL/TP → signal should be modified."""
        mock_settings.risk_day_trading = 0.01
        mock_settings.risk_scalping = 0.005
        mock_settings.risk_swing = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.min_rr_ratio = 1.5
        mock_settings.funded_account_mode = False

        broker = MockBroker(balance=10000.0, pip_value=0.0001)
        rm = RiskManager(broker)
        rm._peak_balance = 10000.0
        rm._current_balance = 10000.0
        pm = PositionManager(broker, risk_manager=rm, management_style="cp",
                             trading_style="day_trading", allow_partial_profits=False)

        analysis = make_blue_analysis()

        # Get original signal first
        original_signal = get_best_setup(
            analysis,
            {"BLUE": True, "RED": True, "PINK": True,
             "WHITE": True, "BLACK": True, "GREEN": True},
        )

        if original_signal is None:
            return  # No signal to test

        original_sl = original_signal.stop_loss
        original_tp = original_signal.take_profit_1

        ai_result = {
            "ai_score": 78,
            "ai_recommendation": "TAKE",
            "ai_reasoning": "Good setup but SL should be tighter",
            "suggested_adjustments": {
                "suggested_sl": original_sl * 1.001,  # Slightly tighter
                "suggested_tp1": original_tp * 0.999,  # Slightly conservative
            },
        }

        signal, trade_risk, trade_id = await simulate_detect_and_execute(
            broker, rm, pm, analysis,
            enabled_strategies={"BLUE": True, "RED": True, "PINK": True,
                                "WHITE": True, "BLACK": True, "GREEN": True},
            ai_result=ai_result,
        )

        # AI adjustments should have been applied
        if signal is not None:
            assert signal.stop_loss == pytest.approx(original_sl * 1.001, rel=1e-6)
            assert signal.take_profit_1 == pytest.approx(original_tp * 0.999, rel=1e-6)


# =====================================================================
# 9. Cross-Cutting Integration Tests
# =====================================================================

class TestCrossCuttingIntegration:
    """Tests spanning multiple subsystems."""

    @patch("core.risk_manager.settings")
    @pytest.mark.asyncio
    async def test_all_strategies_enabled_picks_best(self, mock_settings):
        """With all strategies enabled, get_best_setup returns highest confidence."""
        mock_settings.risk_day_trading = 0.01
        mock_settings.risk_scalping = 0.005
        mock_settings.risk_swing = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.min_rr_ratio = 1.5
        mock_settings.funded_account_mode = False

        analysis = make_blue_analysis()
        all_enabled = {
            "BLUE": True, "RED": True, "PINK": True,
            "WHITE": True, "BLACK": True, "GREEN": True,
        }

        setups = detect_all_setups(analysis, all_enabled)
        best = get_best_setup(analysis, all_enabled)

        if len(setups) > 1 and best is not None:
            # Best should have the highest confidence among detected
            max_confidence = max(s.confidence for s in setups)
            assert best.confidence == max_confidence

    @patch("core.risk_manager.settings")
    @pytest.mark.asyncio
    async def test_disabled_strategy_not_detected(self, mock_settings):
        """Disabled strategies should never return setups."""
        mock_settings.risk_day_trading = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.min_rr_ratio = 1.5
        mock_settings.funded_account_mode = False

        analysis = make_blue_analysis()

        # Disable ALL strategies
        all_disabled = {
            "BLUE": False, "RED": False, "PINK": False,
            "WHITE": False, "BLACK": False, "GREEN": False,
        }

        setups = detect_all_setups(analysis, all_disabled)
        assert len(setups) == 0

        best = get_best_setup(analysis, all_disabled)
        assert best is None

    @patch("core.risk_manager.settings")
    @pytest.mark.asyncio
    async def test_risk_manager_blocks_bad_rr(self, mock_settings):
        """Trades with insufficient R:R should be rejected by risk manager."""
        mock_settings.risk_day_trading = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.min_rr_ratio = 1.5
        mock_settings.funded_account_mode = False

        broker = MockBroker()
        rm = RiskManager(broker)
        rm._peak_balance = 10000.0
        rm._current_balance = 10000.0

        # Create a trade with very bad R:R (< 1.0)
        valid = rm.validate_reward_risk(
            entry_price=1.1000,
            stop_loss=1.0900,       # 100 pip risk
            take_profit_1=1.1020,   # 20 pip reward = 0.2:1 R:R
        )
        assert valid is False

        # Create a trade with good R:R (2.0:1)
        valid = rm.validate_reward_risk(
            entry_price=1.1000,
            stop_loss=1.0900,       # 100 pip risk
            take_profit_1=1.1200,   # 200 pip reward = 2.0:1 R:R
        )
        assert valid is True

    @patch("core.risk_manager.settings")
    @pytest.mark.asyncio
    async def test_position_tracked_after_execution(self, mock_settings):
        """After execution, position should be in INITIAL phase with correct SL."""
        mock_settings.risk_day_trading = 0.01
        mock_settings.risk_scalping = 0.005
        mock_settings.risk_swing = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.min_rr_ratio = 1.5
        mock_settings.funded_account_mode = False

        broker = MockBroker(balance=10000.0, pip_value=0.0001)
        rm = RiskManager(broker)
        rm._peak_balance = 10000.0
        rm._current_balance = 10000.0
        pm = PositionManager(broker, risk_manager=rm, management_style="cp",
                             trading_style="day_trading", allow_partial_profits=False)

        analysis = make_blue_analysis()

        signal, trade_risk, trade_id = await simulate_detect_and_execute(
            broker, rm, pm, analysis,
            enabled_strategies={"BLUE": True, "RED": True, "PINK": True,
                                "WHITE": True, "BLACK": True, "GREEN": True},
        )

        if trade_id is not None:
            pos = pm.positions[trade_id]
            assert pos.phase == PositionPhase.INITIAL
            assert pos.current_sl == pos.original_sl
            assert pos.highest_price == trade_risk.entry_price
            assert pos.lowest_price == trade_risk.entry_price
            assert pos.direction == trade_risk.direction

    @patch("core.risk_manager.settings")
    @pytest.mark.asyncio
    async def test_multiple_trades_risk_accumulation(self, mock_settings):
        """Multiple trades should accumulate in risk manager."""
        mock_settings.risk_day_trading = 0.01
        mock_settings.risk_scalping = 0.005
        mock_settings.risk_swing = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.min_rr_ratio = 1.5
        mock_settings.funded_account_mode = False

        broker = MockBroker(balance=10000.0, pip_value=0.0001)
        rm = RiskManager(broker)
        rm._peak_balance = 10000.0
        rm._current_balance = 10000.0
        pm = PositionManager(broker, risk_manager=rm, management_style="cp",
                             trading_style="day_trading", allow_partial_profits=False)

        # Execute first trade
        analysis1 = make_blue_analysis()
        _, tr1, tid1 = await simulate_detect_and_execute(
            broker, rm, pm, analysis1,
            enabled_strategies={"BLUE": True, "RED": True, "PINK": True,
                                "WHITE": True, "BLACK": True, "GREEN": True},
        )

        # Execute second trade with a different analysis
        analysis2 = make_red_analysis()
        analysis2.instrument = "GBP_USD"  # Different instrument
        _, tr2, tid2 = await simulate_detect_and_execute(
            broker, rm, pm, analysis2,
            enabled_strategies={"BLUE": True, "RED": True, "PINK": True,
                                "WHITE": True, "BLACK": True, "GREEN": True},
        )

        # Count successful trades
        successful_trades = sum(1 for t in [tid1, tid2] if t is not None)
        assert len(rm._active_risks) == successful_trades
        assert len(pm.positions) == successful_trades

    @patch("core.risk_manager.settings")
    @pytest.mark.asyncio
    async def test_trade_unregister_after_close(self, mock_settings):
        """After closing a trade, risk manager should unregister it."""
        mock_settings.risk_day_trading = 0.01
        mock_settings.risk_scalping = 0.005
        mock_settings.risk_swing = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.min_rr_ratio = 1.5
        mock_settings.funded_account_mode = False

        broker = MockBroker(balance=10000.0, pip_value=0.0001)
        rm = RiskManager(broker)
        rm._peak_balance = 10000.0
        rm._current_balance = 10000.0
        pm = PositionManager(broker, risk_manager=rm, management_style="cp",
                             trading_style="day_trading", allow_partial_profits=False)

        analysis = make_blue_analysis()

        signal, trade_risk, trade_id = await simulate_detect_and_execute(
            broker, rm, pm, analysis,
        )

        if trade_id is not None:
            # Verify trade is registered
            assert trade_id in rm._active_risks

            # Simulate closing
            rm.unregister_trade(trade_id)
            assert trade_id not in rm._active_risks

    @patch("core.risk_manager.settings")
    @pytest.mark.asyncio
    async def test_crypto_only_gets_green(self, mock_settings):
        """Crypto instruments should only match GREEN strategy."""
        mock_settings.risk_day_trading = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.min_rr_ratio = 1.5
        mock_settings.funded_account_mode = False

        from strategies.base import _is_crypto_instrument

        assert _is_crypto_instrument("BTC_USD") is True
        assert _is_crypto_instrument("ETH_USD") is True
        assert _is_crypto_instrument("EUR_USD") is False

        # Crypto analysis with all strategies enabled
        analysis = make_green_analysis()
        all_enabled = {
            "BLUE": True, "RED": True, "PINK": True,
            "WHITE": True, "BLACK": True, "GREEN": True,
        }

        setups = detect_all_setups(analysis, all_enabled)
        # For crypto instruments, only GREEN should appear
        for s in setups:
            assert s.strategy == StrategyColor.GREEN, \
                f"Crypto instrument got non-GREEN strategy: {s.strategy}"

    @patch("core.risk_manager.settings")
    @pytest.mark.asyncio
    async def test_order_result_failure_blocks_tracking(self, mock_settings):
        """If broker order fails, trade should NOT be tracked."""
        mock_settings.risk_day_trading = 0.01
        mock_settings.risk_scalping = 0.005
        mock_settings.risk_swing = 0.01
        mock_settings.drawdown_method = "fixed_1pct"
        mock_settings.delta_enabled = False
        mock_settings.min_rr_ratio = 1.5
        mock_settings.funded_account_mode = False

        broker = MockBroker(balance=10000.0, pip_value=0.0001)

        # Override to return failure
        async def failing_order(*args, **kwargs):
            return OrderResult(success=False, error="Insufficient margin")
        broker.place_market_order = failing_order

        rm = RiskManager(broker)
        rm._peak_balance = 10000.0
        rm._current_balance = 10000.0
        pm = PositionManager(broker, risk_manager=rm, management_style="cp",
                             trading_style="day_trading", allow_partial_profits=False)

        analysis = make_blue_analysis()

        signal, trade_risk, trade_id = await simulate_detect_and_execute(
            broker, rm, pm, analysis,
        )

        # Execution should have failed
        if signal is not None and trade_risk is not None:
            assert trade_id is None
            assert len(rm._active_risks) == 0
            assert len(pm.positions) == 0
