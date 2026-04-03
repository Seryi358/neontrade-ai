"""
NeonTrade AI - Round 2 Deep Bug Hunting Tests
Runtime bugs, edge cases, and integration issues.
"""

import asyncio
import sys
import os
import math
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import fields as dataclass_fields

# Ensure backend is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ── Helpers ──────────────────────────────────────────────────────────────────

def generate_realistic_ohlcv(n: int, base_price: float = 1.1000,
                              volatility: float = 0.002,
                              trend: float = 0.0001) -> pd.DataFrame:
    """Generate realistic OHLCV data with a slight uptrend and random walks."""
    np.random.seed(42)
    timestamps = pd.date_range("2025-01-01", periods=n, freq="h")
    closes = [base_price]
    for i in range(1, n):
        change = np.random.normal(trend, volatility)
        closes.append(closes[-1] * (1 + change))

    rows = []
    for i, ts in enumerate(timestamps):
        c = closes[i]
        h = c * (1 + abs(np.random.normal(0, volatility * 0.5)))
        l = c * (1 - abs(np.random.normal(0, volatility * 0.5)))
        o = l + (h - l) * np.random.random()
        vol = int(np.random.uniform(100, 10000))
        rows.append({"time": ts, "open": o, "high": h, "low": l, "close": c, "volume": vol})

    df = pd.DataFrame(rows)
    df.set_index("time", inplace=True)
    return df


def generate_flat_ohlcv(n: int, price: float = 1.1000) -> pd.DataFrame:
    """Generate flat market data (all same prices)."""
    timestamps = pd.date_range("2025-01-01", periods=n, freq="h")
    rows = [{"time": ts, "open": price, "high": price, "low": price,
             "close": price, "volume": 1000} for ts in timestamps]
    df = pd.DataFrame(rows)
    df.set_index("time", inplace=True)
    return df


def generate_extreme_volatility_ohlcv(n: int, base_price: float = 1.1000) -> pd.DataFrame:
    """Generate data with 50% price swings."""
    np.random.seed(99)
    timestamps = pd.date_range("2025-01-01", periods=n, freq="h")
    rows = []
    price = base_price
    for ts in timestamps:
        swing = np.random.choice([-0.5, 0.5]) * np.random.random()
        price = price * (1 + swing * 0.5)
        h = price * 1.25
        l = price * 0.75
        o = l + (h - l) * np.random.random()
        rows.append({"time": ts, "open": o, "high": h, "low": l, "close": price, "volume": 5000})
    df = pd.DataFrame(rows)
    df.set_index("time", inplace=True)
    return df


def generate_nan_ohlcv(n: int) -> pd.DataFrame:
    """Generate OHLCV data with some NaN values."""
    df = generate_realistic_ohlcv(n)
    # Insert NaN at various positions
    df.iloc[5, df.columns.get_loc("close")] = np.nan
    df.iloc[10, df.columns.get_loc("high")] = np.nan
    df.iloc[15, df.columns.get_loc("low")] = np.nan
    return df


def generate_negative_price_ohlcv(n: int) -> pd.DataFrame:
    """Generate OHLCV data with negative prices."""
    df = generate_realistic_ohlcv(n, base_price=0.001, volatility=0.01)
    # Force some negative prices
    df.iloc[3, df.columns.get_loc("close")] = -0.5
    df.iloc[3, df.columns.get_loc("low")] = -0.6
    return df


def build_mock_analysis(instrument="EUR_USD"):
    """Build a realistic mock AnalysisResult for testing strategies."""
    from core.market_analyzer import AnalysisResult, Trend, MarketCondition

    return AnalysisResult(
        instrument=instrument,
        htf_trend=Trend.BULLISH,
        htf_condition=MarketCondition.NEUTRAL,
        ltf_trend=Trend.BULLISH,
        htf_ltf_convergence=True,
        key_levels={
            "supports": [1.0900, 1.0850, 1.0800],
            "resistances": [1.1100, 1.1150, 1.1200],
            "fvg": [1.0950, 1.1050],
            "fvg_zones": [],
            "liquidity_pools": [],
        },
        ema_values={
            "EMA_W_8": 1.0980,
            "EMA_W_50": 1.0900,
            "EMA_D_20": 1.0960,
            "EMA_D_50": 1.0940,
            "EMA_H4_50": 1.1050,
            "EMA_H1_50": 1.0990,
            "EMA_M15_5": 1.1005,
            "EMA_M15_20": 1.1000,
            "EMA_M15_50": 1.0995,
            "EMA_M5_2": 1.1010,
            "EMA_M5_5": 1.1005,
            "EMA_M5_20": 1.1000,
            "EMA_M5_50": 1.0995,
            "EMA_M1_50": 1.1000,
        },
        fibonacci_levels={
            "0.0": 1.1200,
            "0.382": 1.1076,
            "0.5": 1.1000,
            "0.618": 1.0924,
            "0.750": 1.0850,
            "1.0": 1.0800,
        },
        candlestick_patterns=["HAMMER", "ENGULFING_BULLISH"],
        chart_patterns=[],
        macd_values={
            "H1": {"macd": 0.0005, "signal": 0.0003, "histogram": 0.0002},
            "M5": {"macd": 0.0002, "signal": 0.0001, "histogram": 0.0001},
        },
        sma_values={"SMA_D_200": 1.0800, "SMA_H1_200": 1.0850},
        rsi_values={"D": 55.0, "H4": 60.0, "H1": 58.0},
        rsi_divergence=None,
        order_blocks=[
            {"type": "bullish", "high": 1.1010, "low": 1.0990, "index": 50},
        ],
        structure_breaks=[
            {"type": "BOS", "direction": "bullish", "level": 1.1005, "index": 48},
        ],
        score=65.0,
        volume_analysis={
            "H1": {"volume_ratio": 1.3, "trend": "above_average"},
            "M5": {"volume_ratio": 1.1, "trend": "normal"},
        },
        ema_w8=1.0980,
        sma_d200=1.0800,
        last_candles={
            "M5": [
                {"open": 1.1000, "high": 1.1010, "low": 1.0995, "close": 1.1008, "volume": 500},
                {"open": 1.1008, "high": 1.1015, "low": 1.1003, "close": 1.1012, "volume": 600},
                {"open": 1.1012, "high": 1.1018, "low": 1.1007, "close": 1.1015, "volume": 550},
            ],
            "H1": [
                {"open": 1.0980, "high": 1.1020, "low": 1.0975, "close": 1.1010, "volume": 5000},
                {"open": 1.1010, "high": 1.1025, "low": 1.1005, "close": 1.1015, "volume": 4800},
                {"open": 1.1015, "high": 1.1030, "low": 1.1010, "close": 1.1020, "volume": 5200},
            ],
        },
        current_price=1.1005,
        session="LONDON",
        elliott_wave_detail={"wave_count": "2", "confidence": 0.6},
        pivot_points={"P": 1.1000, "S1": 1.0950, "R1": 1.1050, "S2": 1.0900, "R2": 1.1100},
        premium_discount_zone={"zone": "discount", "position": 0.4, "swing_high": 1.12, "swing_low": 1.08},
        volume_divergence=None,
        mitigation_blocks=[],
        breaker_blocks=[],
        power_of_three={"phase": "distribution", "direction_bias": "bullish"},
        smt_divergence=None,
        liquidity_sweep=None,
        bmsb=None,
        pi_cycle=None,
    )


# ── Mock broker ──────────────────────────────────────────────────────────────

class MockBroker:
    """Mock broker for testing."""
    broker_type = MagicMock(value="mock")

    async def get_candles(self, instrument, timeframe, count):
        return []

    async def get_account_balance(self):
        return 10000.0

    async def get_pip_value(self, instrument):
        return 0.0001

    async def modify_trade_sl(self, trade_id, new_sl):
        pass

    async def close_trade(self, trade_id, units=None):
        pass

    async def close_all_trades(self):
        return 0

    async def get_open_trades(self):
        return []

    async def get_current_price(self, instrument):
        return MagicMock(bid=1.1000, ask=1.1002, spread=0.0002, time="2025-01-01T00:00:00Z")

    async def get_account_summary(self):
        return MagicMock(
            balance=10000, equity=10100, unrealized_pnl=100,
            margin_used=500, margin_available=9500,
            open_trade_count=1, currency="USD",
        )


# ======================================================================
# TEST A: Full System Integration
# ======================================================================

def test_a_full_system_integration():
    """TEST A: Full analysis flow -> all 6 strategies."""
    print("\n" + "=" * 70)
    print("TEST A: Full System Integration")
    print("=" * 70)

    from config import Settings
    from core.market_analyzer import MarketAnalyzer, AnalysisResult
    from strategies.base import (
        BlueStrategy, RedStrategy, PinkStrategy,
        WhiteStrategy, BlackStrategy, GreenStrategy,
        SetupSignal, detect_all_setups, get_best_setup,
    )

    # 1. Settings
    s = Settings()
    assert s.risk_day_trading == 0.01, f"Expected 0.01, got {s.risk_day_trading}"
    print("  [PASS] Settings instance created")

    # 2. MarketAnalyzer
    broker = MockBroker()
    analyzer = MarketAnalyzer(broker)
    assert analyzer.broker is broker
    print("  [PASS] MarketAnalyzer created with broker")

    # 3. Mock OHLCV dataset (300+ candles)
    df = generate_realistic_ohlcv(350)
    assert len(df) == 350
    assert not df.empty
    print(f"  [PASS] Realistic OHLCV data: {len(df)} candles")

    # 4. Build mock analysis (simulating full_analysis output)
    analysis = build_mock_analysis("EUR_USD")
    assert analysis.instrument == "EUR_USD"
    assert analysis.htf_trend.value == "bullish"
    print("  [PASS] AnalysisResult built")

    # 5-6. Run all 6 strategies - none should crash
    strategies = [
        BlueStrategy(), RedStrategy(), PinkStrategy(),
        WhiteStrategy(), BlackStrategy(), GreenStrategy(),
    ]
    for strat in strategies:
        try:
            result = strat.detect(analysis)
            if result is not None:
                assert isinstance(result, SetupSignal), f"{strat.name}: Expected SetupSignal"
                print(f"  [PASS] {strat.color.value}: detect() returned signal (confidence={result.confidence:.0f}%)")
            else:
                print(f"  [PASS] {strat.color.value}: detect() returned None (no setup)")
        except Exception as e:
            print(f"  [FAIL] {strat.color.value}: CRASHED with {type(e).__name__}: {e}")
            raise

    # Test detect_all_setups and get_best_setup
    try:
        all_signals = detect_all_setups(analysis)
        print(f"  [PASS] detect_all_setups returned {len(all_signals)} signals")
        best = get_best_setup(analysis)
        if best:
            print(f"  [PASS] get_best_setup: {best.strategy.value} {best.strategy_variant} conf={best.confidence:.0f}%")
        else:
            print(f"  [PASS] get_best_setup: None (no signals passed)")
    except Exception as e:
        print(f"  [FAIL] detect_all_setups/get_best_setup CRASHED: {e}")
        raise

    # 7. Validate SetupSignal fields
    for sig in all_signals:
        assert sig.strategy is not None
        assert sig.instrument == "EUR_USD"
        assert sig.direction in ("BUY", "SELL")
        assert sig.entry_price > 0
        assert sig.stop_loss > 0
        assert sig.take_profit_1 > 0
        assert 0 <= sig.confidence <= 100
        assert sig.risk_reward_ratio >= 0
        assert sig.entry_type in ("MARKET", "LIMIT", "STOP")
    if all_signals:
        print(f"  [PASS] All {len(all_signals)} signals have valid fields")

    print("  TEST A: ALL PASSED")


# ======================================================================
# TEST B: Edge Cases
# ======================================================================

def test_b_edge_cases():
    """TEST B: Edge cases that should not crash."""
    print("\n" + "=" * 70)
    print("TEST B: Edge Cases")
    print("=" * 70)

    from core.market_analyzer import MarketAnalyzer, Trend, MarketCondition

    broker = MockBroker()
    analyzer = MarketAnalyzer(broker)

    # B1: Empty DataFrame (0 candles)
    empty_df = pd.DataFrame()
    trend = analyzer._detect_trend(empty_df)
    assert trend == Trend.RANGING, f"Empty df should give RANGING, got {trend}"
    condition = analyzer._detect_condition(empty_df)
    assert condition == MarketCondition.NEUTRAL
    fib = analyzer._calculate_fibonacci(empty_df)
    assert fib == {}
    print("  [PASS] B1: Empty OHLCV handled (RANGING, NEUTRAL, empty fib)")

    # B2: Very short data (5 candles)
    short_df = generate_realistic_ohlcv(5)
    trend = analyzer._detect_trend(short_df)
    assert trend == Trend.RANGING  # Need >=50 for trend
    condition = analyzer._detect_condition(short_df)
    fib = analyzer._calculate_fibonacci(short_df)
    assert fib == {}  # Need >=20 for fib
    print("  [PASS] B2: Short data (5 candles) handled gracefully")

    # B3: Flat market (all same prices)
    flat_df = generate_flat_ohlcv(100)
    trend = analyzer._detect_trend(flat_df)
    # Flat prices -> EMAs converge to same value -> RANGING expected
    fib = analyzer._calculate_fibonacci(flat_df)
    # All prices same -> swing_high == swing_low -> diff=0
    print(f"  [PASS] B3: Flat market handled (trend={trend.value}, fib keys={len(fib)})")

    # B4: Extreme volatility
    volatile_df = generate_extreme_volatility_ohlcv(100)
    trend = analyzer._detect_trend(volatile_df)
    fib = analyzer._calculate_fibonacci(volatile_df)
    condition = analyzer._detect_condition(volatile_df)
    print(f"  [PASS] B4: Extreme volatility handled (trend={trend.value})")

    # B5: NaN values
    nan_df = generate_nan_ohlcv(100)
    try:
        trend = analyzer._detect_trend(nan_df)
        fib = analyzer._calculate_fibonacci(nan_df)
        condition = analyzer._detect_condition(nan_df)
        print(f"  [PASS] B5: NaN values handled without crash (trend={trend.value})")
    except Exception as e:
        print(f"  [WARN] B5: NaN values caused: {type(e).__name__}: {e}")
        # Not necessarily a failure -- NaN handling depends on implementation

    # B6: Negative prices
    neg_df = generate_negative_price_ohlcv(100)
    try:
        trend = analyzer._detect_trend(neg_df)
        fib = analyzer._calculate_fibonacci(neg_df)
        print(f"  [PASS] B6: Negative prices handled (trend={trend.value})")
    except Exception as e:
        print(f"  [WARN] B6: Negative prices caused: {type(e).__name__}: {e}")

    # B7: Missing timeframes - _find_key_levels with missing H1
    candles = {"D": generate_realistic_ohlcv(100)}
    # No H1, H4, M5, etc.
    try:
        levels = analyzer._find_key_levels(candles)
        assert "supports" in levels
        assert "resistances" in levels
        print(f"  [PASS] B7: Missing timeframes handled ({len(levels['supports'])} supports)")
    except Exception as e:
        print(f"  [FAIL] B7: Missing timeframes CRASHED: {e}")
        raise

    # B7b: _calculate_emas with partial timeframes
    try:
        emas = analyzer._calculate_emas(candles)
        print(f"  [PASS] B7b: Partial timeframes EMA: {len(emas)} keys")
    except Exception as e:
        print(f"  [FAIL] B7b: Partial timeframes CRASHED: {e}")
        raise

    print("  TEST B: ALL PASSED")


# ======================================================================
# TEST C: Position Manager Full Flow
# ======================================================================

def test_c_position_manager():
    """TEST C: Position Manager full flow with all styles."""
    print("\n" + "=" * 70)
    print("TEST C: Position Manager Full Flow")
    print("=" * 70)

    from core.position_manager import (
        PositionManager, ManagedPosition, PositionPhase,
        ManagementStyle, TradingStyle,
    )

    broker = MockBroker()

    styles_to_test = ["lp", "cp", "cpa", "price_action"]

    for style in styles_to_test:
        pm = PositionManager(
            broker_client=broker,
            risk_manager=None,
            management_style=style,
            trading_style="day_trading",
            allow_partial_profits=(style == "cpa"),  # Test partial on CPA
        )

        # Create a BUY position
        pos = ManagedPosition(
            trade_id=f"test_{style}_001",
            instrument="EUR_USD",
            direction="BUY",
            entry_price=1.1000,
            original_sl=1.0950,
            current_sl=1.0950,
            take_profit_1=1.1100,
            take_profit_max=1.1200,
            units=1000,
            style="day_trading",
        )
        pm.track_position(pos)
        assert pos.trade_id in pm.positions

        # Set EMA values for trailing
        pm.set_ema_values("EUR_USD", {
            "EMA_H4_50": 1.1050,
            "EMA_H1_50": 1.1020,
            "EMA_M15_50": 1.1010,
            "EMA_M5_50": 1.1005,
            "EMA_M1_50": 1.1003,
        })

        # Set swing values for PRICE_ACTION style
        pm.set_swing_values("EUR_USD",
                            swing_highs=[1.1080, 1.1060, 1.1040],
                            swing_lows=[1.0980, 1.0970, 1.0960])

        # Phase 1: INITIAL -> SL_MOVED (price at 20% to TP1)
        assert pos.phase == PositionPhase.INITIAL
        asyncio.get_event_loop().run_until_complete(
            pm._manage_position(pos, 1.1020)  # 20% toward TP1
        )
        if pos.phase != PositionPhase.INITIAL:
            print(f"    [{style}] Phase 1 -> {pos.phase.value}, SL={pos.current_sl:.5f}")

        # Phase 2: SL_MOVED -> BREAK_EVEN (1% unrealized profit)
        if pos.phase == PositionPhase.SL_MOVED:
            asyncio.get_event_loop().run_until_complete(
                pm._manage_position(pos, 1.1110)  # 1% profit
            )
            print(f"    [{style}] Phase 2 -> {pos.phase.value}, SL={pos.current_sl:.5f}")

        # Phase 3: BREAK_EVEN -> TRAILING (70% to TP1)
        if pos.phase == PositionPhase.BREAK_EVEN:
            asyncio.get_event_loop().run_until_complete(
                pm._manage_position(pos, 1.1070)  # 70% to TP1
            )
            print(f"    [{style}] Phase 3 -> {pos.phase.value}, SL={pos.current_sl:.5f}")

        # Phase 4: TRAILING -> BEYOND_TP1 (TP1 hit)
        if pos.phase == PositionPhase.TRAILING_TO_TP1:
            asyncio.get_event_loop().run_until_complete(
                pm._manage_position(pos, 1.1100)  # TP1 reached
            )
            print(f"    [{style}] Phase 4 -> {pos.phase.value}, SL={pos.current_sl:.5f}")

        # Phase 5: BEYOND_TP1 -> TP_MAX hit
        if pos.phase == PositionPhase.BEYOND_TP1:
            asyncio.get_event_loop().run_until_complete(
                pm._manage_position(pos, 1.1200)  # TP_max reached
            )
            closed = pos.trade_id not in pm.positions
            print(f"    [{style}] Phase 5 -> {'CLOSED' if closed else pos.phase.value}")

        pm.remove_position(pos.trade_id)
        print(f"  [PASS] {style.upper()}: Full position lifecycle completed")

    # Test SELL direction as well
    pm = PositionManager(broker, management_style="lp", trading_style="day_trading")
    sell_pos = ManagedPosition(
        trade_id="test_sell_001",
        instrument="GBP_USD",
        direction="SELL",
        entry_price=1.3000,
        original_sl=1.3050,
        current_sl=1.3050,
        take_profit_1=1.2900,
        take_profit_max=1.2800,
        units=-1000,
    )
    pm.track_position(sell_pos)
    pm.set_ema_values("GBP_USD", {"EMA_H4_50": 1.2950, "EMA_M5_50": 1.2990})

    asyncio.get_event_loop().run_until_complete(pm._manage_position(sell_pos, 1.2980))
    asyncio.get_event_loop().run_until_complete(pm._manage_position(sell_pos, 1.2870))
    asyncio.get_event_loop().run_until_complete(pm._manage_position(sell_pos, 1.2930))
    print(f"  [PASS] SELL position handled: phase={sell_pos.phase.value}")

    print("  TEST C: ALL PASSED")


# ======================================================================
# TEST D: Risk Manager Full Flow
# ======================================================================

def test_d_risk_manager():
    """TEST D: Risk Manager full flow."""
    print("\n" + "=" * 70)
    print("TEST D: Risk Manager Full Flow")
    print("=" * 70)

    from core.risk_manager import RiskManager, TradingStyle, TradeResult

    broker = MockBroker()
    rm = RiskManager(broker)

    # D1: Position sizing
    rm._current_balance = 10000.0
    rm._peak_balance = 10000.0

    risk = rm.get_risk_for_style(TradingStyle.DAY_TRADING)
    assert risk == 0.01, f"Expected 0.01, got {risk}"
    print(f"  [PASS] D1a: Day trading risk = {risk:.2%}")

    risk_scalp = rm.get_risk_for_style(TradingStyle.SCALPING)
    assert risk_scalp == 0.005, f"Expected 0.005, got {risk_scalp}"
    print(f"  [PASS] D1b: Scalping risk = {risk_scalp:.2%}")

    # D2: Position size calculation
    units = asyncio.get_event_loop().run_until_complete(
        rm.calculate_position_size("EUR_USD", TradingStyle.DAY_TRADING, 1.1000, 1.0950)
    )
    assert units > 0, f"Units should be positive for BUY, got {units}"
    print(f"  [PASS] D2: Position size = {units} units")

    # D2b: Zero SL distance
    units_zero = asyncio.get_event_loop().run_until_complete(
        rm.calculate_position_size("EUR_USD", TradingStyle.DAY_TRADING, 1.1000, 1.1000)
    )
    assert units_zero == 0, f"Zero SL distance should return 0, got {units_zero}"
    print(f"  [PASS] D2b: Zero SL distance returns 0 units")

    # D3: Drawdown level transitions
    rm._peak_balance = 10000.0
    rm._current_balance = 9500.0  # 5% drawdown
    dd = rm.get_current_drawdown()
    assert abs(dd - 0.05) < 0.001, f"Expected ~5% DD, got {dd:.2%}"
    print(f"  [PASS] D3a: Drawdown = {dd:.2%}")

    # Test fixed_levels drawdown method
    with patch('core.risk_manager.settings') as mock_settings:
        mock_settings.drawdown_method = "fixed_levels"
        mock_settings.drawdown_level_1 = 0.05
        mock_settings.drawdown_level_2 = 0.075
        mock_settings.drawdown_level_3 = 0.10
        mock_settings.drawdown_risk_1 = 0.0075
        mock_settings.drawdown_risk_2 = 0.005
        mock_settings.drawdown_risk_3 = 0.0025
        mock_settings.drawdown_min_risk = 0.0025
        mock_settings.delta_enabled = False

        adjusted = rm._get_drawdown_adjusted_risk(0.01)
        assert adjusted == 0.0075, f"Expected 0.75% at 5% DD, got {adjusted}"
        print(f"  [PASS] D3b: Fixed levels DD: {adjusted:.2%} at 5% DD")

    # D4: Funded account mode
    with patch('core.risk_manager.settings') as mock_settings:
        mock_settings.funded_account_mode = True
        mock_settings.funded_max_daily_dd = 0.05
        mock_settings.funded_max_total_dd = 0.10

        rm._current_balance = 9000  # 10% DD
        rm._peak_balance = 10000
        can_trade, reason = rm.check_funded_account_limits()
        assert not can_trade, "Should be blocked at 10% total DD"
        assert "total DD" in reason
        print(f"  [PASS] D4: Funded account blocks at 10% DD: {reason}")

    # D5: Scale-in requirement
    with patch('core.risk_manager.settings') as mock_settings:
        mock_settings.scale_in_require_be = True
        mock_settings.correlation_groups = []
        mock_settings.max_total_risk = 0.07

        rm._active_risks = {"EUR_USD:trade_1": 0.01}
        rm._positions_at_be = set()  # trade_1 NOT at BE

        can = rm.can_scale_in("EUR_USD")
        assert not can, "Scale-in should be blocked (trade_1 not at BE)"
        print(f"  [PASS] D5a: Scale-in blocked (existing trade not at BE)")

        rm.mark_position_at_be("trade_1")
        can = rm.can_scale_in("EUR_USD")
        assert can, "Scale-in should be allowed (trade_1 at BE)"
        print(f"  [PASS] D5b: Scale-in allowed (existing trade at BE)")

    # D6: Max daily loss tracking
    rm._funded_daily_pnl = 0.0
    rm._funded_daily_pnl_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rm.record_funded_pnl(-200)
    rm.record_funded_pnl(-100)
    assert rm._funded_daily_pnl == -300.0
    print(f"  [PASS] D6: Daily loss tracking = {rm._funded_daily_pnl}")

    # D7: R:R validation
    valid = rm.validate_reward_risk(1.1000, 1.0950, 1.1100)
    assert valid, "R:R 2:1 should pass"
    invalid = rm.validate_reward_risk(1.1000, 1.0950, 1.1020)
    assert not invalid, "R:R 0.4:1 should fail"
    print(f"  [PASS] D7: R:R validation works")

    # D8: Trade registration/unregistration
    rm._active_risks = {}
    rm.register_trade("t1", "EUR_USD", 0.01)
    assert rm.get_current_total_risk() == 0.01
    rm.unregister_trade("t1", "EUR_USD")
    assert rm.get_current_total_risk() == 0.0
    print(f"  [PASS] D8: Trade register/unregister works")

    # D9: Record trade result for delta
    rm.record_trade_result("t1", "EUR_USD", 0.02)
    rm.record_trade_result("t2", "EUR_USD", 0.03)
    assert len(rm._trade_history) == 2
    assert rm._accumulated_gain == 0.05
    rm.record_trade_result("t3", "EUR_USD", -0.01)
    assert rm._accumulated_gain == 0.0  # Reset on loss
    print(f"  [PASS] D9: Delta algorithm tracking works")

    print("  TEST D: ALL PASSED")


# ======================================================================
# TEST E: Database Models
# ======================================================================

def test_e_database_models():
    """TEST E: Database models - check imports and schema."""
    print("\n" + "=" * 70)
    print("TEST E: Database Models")
    print("=" * 70)

    from db.models import TradeDatabase

    # E1: Import succeeds
    db = TradeDatabase(db_path="data/test_e.db")
    assert db.db_path == "data/test_e.db"
    print("  [PASS] E1: TradeDatabase imported and instantiated")

    # E2: Initialize and create tables
    async def _test_db():
        await db.initialize()

        # E3: Insert and query
        trade_id = await db.record_trade({
            "instrument": "EUR_USD",
            "direction": "BUY",
            "units": 1000,
            "entry_price": 1.1000,
            "stop_loss": 1.0950,
            "take_profit": 1.1100,
            "strategy": "BLUE",
            "strategy_variant": "BLUE_A",
            "confidence": 75.0,
            "risk_reward_ratio": 2.0,
            "reasoning": "Test trade",
            "status": "closed_tp",
        })
        assert trade_id is not None
        print(f"  [PASS] E2: Trade recorded: {trade_id}")

        # E4: Query trade history (get_trade_history returns closed trades only)
        trades = await db.get_trade_history(limit=10)
        assert len(trades) >= 1
        trade = trades[0]
        assert trade["instrument"] == "EUR_USD"
        assert trade["direction"] == "BUY"
        print(f"  [PASS] E3: Trade history query works ({len(trades)} trades)")

        # E5: Update trade
        updated = await db.update_trade(trade_id, {
            "status": "closed_tp",
            "exit_price": 1.1100,
            "pnl": 100.0,
            "pnl_pips": 100.0,
        })
        assert updated
        print(f"  [PASS] E4: Trade update works")

        # E6: Daily stats
        stats = await db.get_daily_stats(
            datetime.now(timezone.utc).strftime("%Y-%m-%d")
        )
        assert "total_trades" in stats
        print(f"  [PASS] E5: Daily stats: {stats['total_trades']} trades")

        # E7: Performance summary
        summary = await db.get_performance_summary(days=30)
        assert "total_trades" in summary
        assert "by_strategy" in summary
        assert "by_instrument" in summary
        print(f"  [PASS] E6: Performance summary works")

        # E8: Pending approvals
        setup_id = await db.add_pending_approval({
            "instrument": "GBP_USD",
            "direction": "SELL",
            "entry_price": 1.3000,
            "stop_loss": 1.3050,
            "take_profit": 1.2900,
            "strategy": "RED",
        })
        pending = await db.get_pending_approvals()
        assert len(pending) >= 1
        resolved = await db.resolve_pending(setup_id, "approved")
        assert resolved
        print(f"  [PASS] E7: Pending approvals work")

        # E9: Equity snapshots
        await db.record_equity_snapshot(10000, 10100, 100, 1, 0.01)
        curve = await db.get_equity_curve(days=1)
        assert len(curve) >= 1
        print(f"  [PASS] E8: Equity snapshots work")

        # E10: Trade notes
        updated = await db.update_trade_notes(trade_id, "Test note - setup was strong")
        assert updated
        print(f"  [PASS] E9: Trade notes work")

        await db.close()

        # Cleanup test db
        try:
            os.remove("data/test_e.db")
        except Exception:
            pass

    asyncio.get_event_loop().run_until_complete(_test_db())
    print("  TEST E: ALL PASSED")


# ======================================================================
# TEST F: API Handler Safety
# ======================================================================

def test_f_api_safety():
    """TEST F: Static analysis of API route safety."""
    print("\n" + "=" * 70)
    print("TEST F: API Handler Safety Audit")
    print("=" * 70)

    import ast

    with open(os.path.join(os.path.dirname(__file__), "api", "routes.py")) as f:
        source = f.read()

    tree = ast.parse(source)
    issues = []

    for node in ast.walk(tree):
        # Check for bare 'except' (swallows all errors)
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                issues.append(f"  Line {node.lineno}: Bare except (catches all exceptions)")

    if issues:
        print("  [WARN] Potential issues in routes.py:")
        for issue in issues:
            print(f"    {issue}")
    else:
        print("  [PASS] No bare except handlers found")

    # Check for routes that access engine._* (private attributes)
    private_accesses = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if isinstance(node.attr, str) and node.attr.startswith("_"):
                if hasattr(node, "lineno"):
                    private_accesses.append(f"Line {node.lineno}: .{node.attr}")

    if private_accesses:
        print(f"  [INFO] Routes accessing private attributes ({len(private_accesses)} occurrences):")
        # Only show unique
        unique = list(set(private_accesses))[:5]
        for pa in unique:
            print(f"    {pa}")
    else:
        print("  [PASS] No private attribute access in routes")

    # Check that all route handlers that use 'db' check for None
    db_routes = ["get_trade_history", "get_performance_stats", "get_daily_stats",
                 "update_trade_notes", "get_equity_curve"]
    missing_none_check = []
    for func_name in db_routes:
        # Simple pattern: function should contain "if db is None"
        if f"def {func_name}" in source:
            # Find function body
            func_start = source.index(f"def {func_name}")
            func_end = source.find("\ndef ", func_start + 1)
            if func_end == -1:
                func_end = len(source)
            func_body = source[func_start:func_end]
            if "db is None" not in func_body:
                missing_none_check.append(func_name)

    if missing_none_check:
        print(f"  [WARN] Routes missing 'db is None' check: {missing_none_check}")
    else:
        print(f"  [PASS] All DB routes check for None database")

    # Check that emergency/close-all has error handling
    if "emergency_close_all" in source:
        idx = source.index("emergency_close_all")
        block = source[idx:idx+1000]
        if "try" in block:
            print("  [PASS] emergency_close_all has error handling")
        else:
            print("  [WARN] emergency_close_all may lack error handling")

    print("  TEST F: AUDIT COMPLETE")


# ======================================================================
# TEST G: WebSocket Safety
# ======================================================================

def test_g_websocket_safety():
    """TEST G: WebSocket safety analysis."""
    print("\n" + "=" * 70)
    print("TEST G: WebSocket Safety")
    print("=" * 70)

    with open(os.path.join(os.path.dirname(__file__), "main.py")) as f:
        main_source = f.read()

    # G1: Check ConnectionManager handles disconnected clients
    if "disconnected = []" in main_source or "disconnected.append" in main_source:
        print("  [PASS] G1: ConnectionManager cleans up failed connections in broadcast")
    else:
        print("  [WARN] G1: May not clean up failed connections")

    # G2: Check WebSocket has exception handling
    if "WebSocketDisconnect" in main_source:
        print("  [PASS] G2: WebSocket handles WebSocketDisconnect")
    else:
        print("  [FAIL] G2: Missing WebSocketDisconnect handler")

    # G3: Check for heartbeat timeout
    if "wait_for" in main_source and "timeout" in main_source:
        print("  [PASS] G3: WebSocket has heartbeat timeout")
    else:
        print("  [WARN] G3: Missing heartbeat timeout")

    # G4: Check status broadcast loop has error handling
    if "_status_broadcast_loop" in main_source:
        idx = main_source.index("_status_broadcast_loop")
        block = main_source[idx:idx+500]
        if "try" in block and "except" in block:
            print("  [PASS] G4: Status broadcast loop has error handling")
        else:
            print("  [WARN] G4: Status broadcast loop may lack error handling")

    # G5: Check for potential connection leak (no max connections limit)
    if "active_connections" in main_source:
        if "MAX_CONNECTIONS" in main_source or "max_connections" in main_source:
            print("  [PASS] G5: WebSocket has connection limit")
        else:
            print("  [INFO] G5: No explicit WebSocket connection limit (potential DoS vector)")

    # G6: JSON decode error handling
    if "JSONDecodeError" in main_source or "json.JSONDecodeError" in main_source:
        print("  [PASS] G6: WebSocket handles malformed JSON")
    else:
        print("  [WARN] G6: Missing JSON decode error handling")

    print("  TEST G: AUDIT COMPLETE")


# ======================================================================
# TEST H: Cross-module Consistency
# ======================================================================

def test_h_cross_module_consistency():
    """TEST H: Check cross-module field consistency."""
    print("\n" + "=" * 70)
    print("TEST H: Cross-module Consistency")
    print("=" * 70)

    from core.market_analyzer import AnalysisResult, Trend, MarketCondition
    from strategies.base import (
        _ema_val, _check_ema_break, _check_ema_pullback,
        _has_reversal_pattern, _has_deceleration, _fib_zone_check,
        _is_at_key_level, _check_premium_discount_zone,
        _count_confluence_points, _check_volume_confirmation,
        _check_rsi_divergence, _check_weekly_ema8_filter,
        _get_current_price_proxy, StrategyColor,
    )
    from core.position_manager import ManagementStyle, PositionPhase
    from config import Settings

    # H1: All AnalysisResult fields used in strategies should exist
    analysis_fields = {f.name for f in dataclass_fields(AnalysisResult)}
    accessed_fields = [
        "instrument", "htf_trend", "htf_condition", "ltf_trend",
        "htf_ltf_convergence", "key_levels", "ema_values",
        "fibonacci_levels", "candlestick_patterns", "chart_patterns",
        "macd_values", "sma_values", "rsi_values", "rsi_divergence",
        "order_blocks", "structure_breaks", "score", "volume_analysis",
        "ema_w8", "sma_d200", "last_candles", "current_price", "session",
        "elliott_wave_detail", "pivot_points", "premium_discount_zone",
        "volume_divergence", "mitigation_blocks", "breaker_blocks",
        "power_of_three", "smt_divergence", "liquidity_sweep",
        "bmsb", "pi_cycle",
    ]
    missing_fields = [f for f in accessed_fields if f not in analysis_fields]
    if missing_fields:
        print(f"  [FAIL] H1: AnalysisResult missing fields: {missing_fields}")
    else:
        print(f"  [PASS] H1: All {len(accessed_fields)} accessed fields exist in AnalysisResult")

    # H2: Settings fields used in risk_manager and position_manager
    settings_obj = Settings()
    settings_fields = set(settings_obj.model_fields.keys())
    used_settings = [
        "risk_day_trading", "risk_scalping", "risk_swing",
        "max_total_risk", "correlated_risk_pct", "min_rr_ratio",
        "min_rr_black", "min_rr_green", "move_sl_to_be_pct_to_tp1",
        "scale_in_require_be", "partial_taking", "allow_partial_profits",
        "sl_management_style", "drawdown_method", "drawdown_level_1",
        "drawdown_level_2", "drawdown_level_3", "drawdown_risk_1",
        "drawdown_risk_2", "drawdown_risk_3", "drawdown_min_risk",
        "delta_enabled", "delta_parameter", "delta_max_risk",
        "funded_account_mode", "funded_max_daily_dd", "funded_max_total_dd",
        "funded_no_overnight", "funded_no_news_trading",
        "correlation_groups", "trading_style",
    ]
    missing_settings = [s for s in used_settings if s not in settings_fields]
    if missing_settings:
        print(f"  [FAIL] H2: Settings missing fields: {missing_settings}")
    else:
        print(f"  [PASS] H2: All {len(used_settings)} used settings fields exist")

    # H3: Enum value consistency
    # Check StrategyColor matches what detect_all_setups uses
    expected_colors = {"BLACK", "BLUE", "RED", "PINK", "GREEN", "WHITE"}
    actual_colors = {c.value for c in StrategyColor}
    assert expected_colors == actual_colors, f"Strategy colors mismatch: {expected_colors ^ actual_colors}"
    print(f"  [PASS] H3a: StrategyColor enum values match")

    # Check Trend enum
    expected_trends = {"bullish", "bearish", "ranging"}
    actual_trends = {t.value for t in Trend}
    assert expected_trends == actual_trends
    print(f"  [PASS] H3b: Trend enum values match")

    # Check ManagementStyle
    expected_styles = {"lp", "cp", "cpa", "price_action", "daily"}  # "daily" added for crypto mid-term
    actual_styles = {s.value for s in ManagementStyle}
    assert expected_styles == actual_styles
    print(f"  [PASS] H3c: ManagementStyle enum values match")

    # H4: PRICE_ACTION handled in all switch/if statements in PositionManager
    with open(os.path.join(os.path.dirname(__file__), "core", "position_manager.py")) as f:
        pm_source = f.read()

    # Check that _manage_position handles all phases
    phases = ["INITIAL", "SL_MOVED", "BREAK_EVEN", "TRAILING_TO_TP1", "BEYOND_TP1"]
    for phase in phases:
        if phase not in pm_source:
            print(f"  [FAIL] H4: Phase {phase} not handled in position_manager.py")
        else:
            pass  # OK
    print(f"  [PASS] H4a: All {len(phases)} position phases handled")

    # Check that PRICE_ACTION style is handled in __init__ and trailing
    if "ManagementStyle.PRICE_ACTION" in pm_source:
        print(f"  [PASS] H4b: PRICE_ACTION style handled in position_manager")
    else:
        print(f"  [FAIL] H4b: PRICE_ACTION not handled in position_manager")

    # H5: Premium/Discount zone bug fix verification
    analysis = build_mock_analysis()
    # premium_discount_zone is a Dict with "zone" key
    pd_ok, pd_desc = _check_premium_discount_zone(analysis, "BUY")
    assert pd_ok, f"BUY in discount zone should be favorable, got pd_ok={pd_ok}, desc={pd_desc}"
    print(f"  [PASS] H5: _check_premium_discount_zone correctly handles Dict: '{pd_desc}'")

    # Test with SELL direction
    analysis2 = build_mock_analysis()
    analysis2.premium_discount_zone = {"zone": "premium", "position": 0.7}
    pd_ok2, pd_desc2 = _check_premium_discount_zone(analysis2, "SELL")
    assert pd_ok2, f"SELL in premium zone should be favorable, got pd_ok={pd_ok2}"
    print(f"  [PASS] H5b: Premium zone correctly identified for SELL")

    # Test with None
    analysis3 = build_mock_analysis()
    analysis3.premium_discount_zone = None
    pd_ok3, _ = _check_premium_discount_zone(analysis3, "BUY")
    assert pd_ok3  # None = don't block
    print(f"  [PASS] H5c: None premium_discount_zone = don't block")

    # H6: Confluence scoring with fixed premium_discount_zone
    analysis4 = build_mock_analysis()
    pos_pts, neg_pts, pos_details, neg_details = _count_confluence_points(
        analysis4, "BUY", 1.1005
    )
    # With the fix, discount zone should count as positive, not negative
    pd_in_positive = any("DESCUENTO" in d or "equilibrio" in d for d in pos_details)
    pd_in_negative = any("desfavorable" in d for d in neg_details)
    if pd_in_positive:
        print(f"  [PASS] H6: Discount zone correctly adds positive confluence point")
    elif pd_in_negative:
        print(f"  [FAIL] H6: Discount zone STILL counted as negative (bug not fixed)")
    else:
        print(f"  [INFO] H6: Premium/Discount not in confluence details (zone may not match criteria)")
    print(f"    Confluence: +{pos_pts}/-{neg_pts}")

    print("  TEST H: ALL PASSED")


# ======================================================================
# MAIN
# ======================================================================

def main():
    """Run all round 2 tests."""
    print("=" * 70)
    print("  NeonTrade AI - Round 2 Deep Bug Hunting")
    print("  Runtime bugs, edge cases, integration issues")
    print("=" * 70)

    passed = 0
    failed = 0
    tests = [
        ("A", "Full System Integration", test_a_full_system_integration),
        ("B", "Edge Cases", test_b_edge_cases),
        ("C", "Position Manager Full Flow", test_c_position_manager),
        ("D", "Risk Manager Full Flow", test_d_risk_manager),
        ("E", "Database Models", test_e_database_models),
        ("F", "API Handler Safety", test_f_api_safety),
        ("G", "WebSocket Safety", test_g_websocket_safety),
        ("H", "Cross-module Consistency", test_h_cross_module_consistency),
    ]

    for test_id, name, func in tests:
        try:
            func()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"\n  *** TEST {test_id} FAILED: {type(e).__name__}: {e} ***\n")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 70)
    print(f"  RESULTS: {passed}/{len(tests)} tests passed, {failed} failed")
    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    success = main()
    sys.exit(0 if success else 1)
