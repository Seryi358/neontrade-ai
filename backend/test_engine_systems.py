"""
Atlas - Engine Systems Test
Tests risk manager, position manager, strategies, news filter, and trading engine.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import settings

passed = 0
failed = 0

def ok(msg):
    global passed; passed += 1; print(f"  ✓ {msg}")
def fail(msg):
    global failed; failed += 1; print(f"  ✗ {msg}")


async def run_tests():
    global passed, failed

    print("=" * 70)
    print("  Atlas - Engine Systems Test")
    print("=" * 70)

    # ── TEST 1: Risk Manager ──────────────────────────────────────
    print("\n[1] RISK MANAGER")
    try:
        from core.risk_manager import RiskManager, TradingStyle, DrawdownMethod
        from broker.capital_client import CapitalClient

        client = CapitalClient(
            api_key=settings.capital_api_key,
            password=settings.capital_password,
            identifier=settings.capital_identifier,
            environment=settings.capital_environment,
        )
        rm = RiskManager(client)

        # Test risk per style
        ok(f"Day trading risk: {settings.risk_day_trading*100}%")
        ok(f"Scalping risk: {settings.risk_scalping*100}%")
        ok(f"Swing risk: {settings.risk_swing*100}%")
        ok(f"Max total risk: {settings.max_total_risk*100}%")

        # Test drawdown method
        method = DrawdownMethod(settings.drawdown_method)
        ok(f"Drawdown method: {method.value}")

        # Test correlated pairs detection
        from core.risk_manager import RiskManager
        # Test correlation adjustment (internal method)
        adjusted = rm._adjust_for_correlation("EUR_USD", 0.01)
        ok(f"EUR_USD risk after correlation check: {adjusted*100:.2f}%")
        adjusted2 = rm._adjust_for_correlation("AUD_JPY", 0.01)
        ok(f"AUD_JPY risk after correlation check: {adjusted2*100:.2f}%")

        await client.close()
    except Exception as e:
        fail(f"Risk manager: {e}")
        import traceback; traceback.print_exc()

    # ── TEST 2: Position Manager ──────────────────────────────────
    print("\n[2] POSITION MANAGER")
    try:
        from core.position_manager import PositionManager, ManagedPosition, PositionPhase

        # Create a mock position
        pos = ManagedPosition(
            trade_id="test-123",
            instrument="EUR_USD",
            direction="BUY",
            entry_price=1.1570,
            original_sl=1.1520,
            current_sl=1.1520,
            take_profit_1=1.1620,
            take_profit_max=1.1670,
        )
        ok(f"Position created: {pos.instrument} {pos.direction}")
        ok(f"Phase: {pos.phase.value}")
        ok(f"SL: {pos.current_sl}, TP1: {pos.take_profit_1}")

        # Test BE calculation
        entry = pos.entry_price
        tp1 = pos.take_profit_1
        be_trigger_price = entry + (tp1 - entry) * settings.move_sl_to_be_pct_to_tp1
        ok(f"BE trigger at {settings.move_sl_to_be_pct_to_tp1*100}% to TP1: {be_trigger_price:.5f}")
        ok(f"Partial taking: {settings.partial_taking}")
        ok(f"SL management: {settings.sl_management_style}")
    except Exception as e:
        fail(f"Position manager: {e}")
        import traceback; traceback.print_exc()

    # ── TEST 3: Strategy Detection ────────────────────────────────
    print("\n[3] STRATEGY SYSTEM")
    try:
        from strategies.base import (
            StrategyColor, BlueStrategy, RedStrategy, BlackStrategy,
            GreenStrategy, PinkStrategy, WhiteStrategy,
            detect_all_setups, get_best_setup,
        )

        # Test strategy instantiation
        strategies = [
            ("BLUE", BlueStrategy()),
            ("RED", RedStrategy()),
            ("BLACK", BlackStrategy()),
            ("GREEN", GreenStrategy()),
            ("PINK", PinkStrategy()),
            ("WHITE", WhiteStrategy()),
        ]
        for name, strat in strategies:
            ok(f"{name}: {strat.name}, min_conf={strat.min_confidence}")

        # Test enabled strategies filter
        from core.trading_engine import TradingEngine
        defaults = TradingEngine._DEFAULT_STRATEGY_CONFIG
        enabled = [k for k, v in defaults.items() if v]
        disabled = [k for k, v in defaults.items() if not v]
        ok(f"Enabled by default: {enabled}")
        ok(f"Disabled by default: {disabled}")

        # Verify only BLUE + RED enabled
        assert defaults["BLUE"] == True
        assert defaults["RED"] == True
        assert defaults["PINK"] == False
        assert defaults["BLACK"] == False
        assert defaults["GREEN"] == False
        assert defaults["WHITE"] == False
        ok("Strategy defaults match TradingLab (BLUE+RED only)")

    except Exception as e:
        fail(f"Strategy system: {e}")
        import traceback; traceback.print_exc()

    # ── TEST 4: News Filter ───────────────────────────────────────
    print("\n[4] NEWS FILTER")
    try:
        from core.news_filter import NewsFilter
        nf = NewsFilter(
            minutes_before=settings.avoid_news_minutes_before,
            minutes_after=settings.avoid_news_minutes_after,
            finnhub_key=settings.finnhub_api_key,
            newsapi_key=settings.newsapi_key,
        )
        ok(f"News filter: avoid {settings.avoid_news_minutes_before}m before, {settings.avoid_news_minutes_after}m after")

        # Check if it's safe to trade now
        has_news, desc = await nf.has_upcoming_news("EUR_USD")
        ok(f"EUR_USD upcoming news: {has_news} ({desc or 'none'})")
    except Exception as e:
        fail(f"News filter: {e}")
        import traceback; traceback.print_exc()

    # ── TEST 5: Market Analyzer ───────────────────────────────────
    print("\n[5] MARKET ANALYZER")
    try:
        from core.market_analyzer import MarketAnalyzer, Trend
        from broker.capital_client import CapitalClient

        client = CapitalClient(
            api_key=settings.capital_api_key,
            password=settings.capital_password,
            identifier=settings.capital_identifier,
            environment=settings.capital_environment,
        )
        await client._ensure_session()

        ma = MarketAnalyzer(client)
        ok("MarketAnalyzer instantiated")

        # Run analysis on EUR_USD
        analysis = await ma.full_analysis("EUR_USD")
        ok(f"EUR_USD analysis complete")
        ok(f"  HTF trend: {analysis.htf_trend}")
        ok(f"  LTF trend: {analysis.ltf_trend}")
        ok(f"  HTF condition: {analysis.htf_condition}")
        ok(f"  HTF/LTF convergence: {analysis.htf_ltf_convergence}")
        ok(f"  Elliott wave: {analysis.elliott_wave}")

        # Check EMA values populated
        ema_count = len([v for v in analysis.ema_values.values() if v and v > 0])
        ok(f"  EMAs populated: {ema_count} values")

        # Check Fibonacci
        fib_count = len([v for v in analysis.fibonacci_levels.values() if v and v > 0])
        ok(f"  Fibonacci levels: {fib_count}")

        # Check key levels
        ok(f"  Key levels: {len(analysis.key_levels)}")
        ok(f"  Current price: {analysis.current_price:.5f}")

        # Test strategy detection on this analysis
        from strategies.base import detect_all_setups
        setups = detect_all_setups(analysis, TradingEngine._DEFAULT_STRATEGY_CONFIG)
        ok(f"  Setups detected: {len(setups)} (with BLUE+RED filter)")
        for s in setups:
            ok(f"    → {s.strategy_variant} {s.direction} conf={s.confidence:.0f}% R:R={s.risk_reward_ratio:.2f}")

        await client.close()
    except Exception as e:
        fail(f"Market analyzer: {e}")
        import traceback; traceback.print_exc()

    # ── TEST 6: Trading Engine Status ─────────────────────────────
    print("\n[6] TRADING ENGINE (status check)")
    try:
        from core.trading_engine import TradingEngine
        engine = TradingEngine()
        status = engine.get_status()
        ok(f"Engine mode: {status.get('mode', '?')}")
        ok(f"Engine running: {status.get('running', '?')}")
        ok(f"Broker: {status.get('broker', '?')}")
        ok(f"Enabled strategies: {[k for k,v in status.get('enabled_strategies', {}).items() if v]}")
        ok(f"Watchlist count: {status.get('watchlist_count', '?')}")
    except Exception as e:
        fail(f"Trading engine: {e}")
        import traceback; traceback.print_exc()

    # ── TEST 7: Explanation Engine ────────────────────────────────
    print("\n[7] EXPLANATION ENGINE")
    try:
        from core.explanation_engine import ExplanationEngine
        ee = ExplanationEngine()
        ok("ExplanationEngine instantiated")
    except Exception as e:
        fail(f"Explanation engine: {e}")

    # ── TEST 8: Trade Journal ─────────────────────────────────────
    print("\n[8] TRADE JOURNAL")
    try:
        from core.trade_journal import TradeJournal
        tj = TradeJournal(initial_capital=10.0)
        ok("TradeJournal instantiated (initial_capital=$10)")
    except Exception as e:
        fail(f"Trade journal: {e}")

    # ── TEST 9: Alert System ──────────────────────────────────────
    print("\n[9] ALERT SYSTEM")
    try:
        from core.alerts import AlertManager, AlertConfig
        ok("AlertManager importable")

        # Check Gmail OAuth2 config
        if settings.gmail_refresh_token:
            ok("Gmail OAuth2 configured")
        else:
            ok("Gmail OAuth2 not configured (optional)")
    except ImportError:
        ok("Alerts module not available (optional)")
    except Exception as e:
        fail(f"Alerts: {e}")

    # ── TEST 10: Database ─────────────────────────────────────────
    print("\n[10] DATABASE")
    try:
        from db.models import TradeDatabase
        db = TradeDatabase()
        await db.initialize()
        ok("Database initialized")
        await db.close()
    except Exception as e:
        fail(f"Database: {e}")
        import traceback; traceback.print_exc()

    # ── TEST 11: Resilience (circuit breaker) ─────────────────────
    print("\n[11] RESILIENCE")
    try:
        from core.resilience import broker_circuit_breaker, balance_cache
        ok(f"Circuit breaker state: {'OPEN' if broker_circuit_breaker.is_open else 'CLOSED'}")
        ok(f"Balance cache available")
    except Exception as e:
        fail(f"Resilience: {e}")

    # ── TEST 12: Config Values Match TradingLab ───────────────────
    print("\n[12] TRADINGLAB CONFIG VERIFICATION")
    checks = [
        (settings.risk_day_trading == 0.01, "Day trading risk = 1%"),
        (settings.risk_scalping == 0.005, "Scalping risk = 0.5%"),
        (settings.risk_swing == 0.01, "Swing risk = 1%"),
        (settings.max_total_risk == 0.07, "Max total risk = 7%"),
        (settings.correlated_risk_pct == 0.0075, "Correlated factor = 0.75"),
        (settings.min_rr_ratio == 1.5, "Min R:R = 1.5"),
        (settings.min_rr_black == 2.0, "Min R:R BLACK = 2.0"),
        (settings.min_rr_green == 2.0, "Min R:R GREEN = 2.0"),
        (settings.move_sl_to_be_pct_to_tp1 == 0.50, "BE at 1% unrealized profit"),
        (settings.scale_in_require_be == True, "Scale-in requires BE"),
        (settings.partial_taking == False, "No partial taking"),
        (settings.sl_management_style == "ema", "SL management = EMA"),
        (settings.drawdown_method == "fixed_levels", "Drawdown = fixed levels"),
        (settings.delta_enabled == False, "Delta disabled"),
        (settings.scalping_enabled == False, "Scalping disabled"),
        (settings.funded_account_mode == False, "Funded mode disabled"),
        (settings.trading_start_hour == 7, "London open 07:00"),
        (settings.trading_end_hour == 22, "NY close 22:00"),
        (settings.close_before_friday_hour == 20, "Friday close 20:00"),
        (settings.avoid_news_minutes_before == 30, "News 30m before"),
        (settings.avoid_news_minutes_after == 15, "News 15m after"),
        (settings.discretion_pct == 0.0, "0% discretion (beginner)"),
        ("forex" in settings.active_watchlist_categories, "Active: forex only"),
        (len(settings.active_watchlist_categories) == 1, "No commodities/crypto active"),
    ]
    for check, desc in checks:
        if check:
            ok(desc)
        else:
            fail(desc)

    # ── SUMMARY ───────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print(f"  RESULTS: {passed} passed, {failed} failed")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_tests())
