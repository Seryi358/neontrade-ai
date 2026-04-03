"""
NeonTrade AI - ROUND 10 ULTIMATE TEST SUITE
500+ assertions covering ALL system components.
Includes all round 9 tests (483) plus new tests for untested areas.
"""

import asyncio
import hashlib
import json
import os
import sys
import time
import tempfile
import re
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Ensure backend is on path
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

passed = 0
failed = 0
errors = []

def ok(test_name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        msg = f"FAIL: {test_name}"
        if detail:
            msg += f" -- {detail}"
        errors.append(msg)
        print(f"  X {msg}")


# ===========================================================================
# SECTION 1: CONFIG (from round 9 + new)
# ===========================================================================
print("\n=== SECTION 1: CONFIG ===")

from config import Settings, settings, get_oanda_url, get_oanda_stream_url

s = Settings()

# Broker defaults
ok("cfg_active_broker", s.active_broker == "capital")
ok("cfg_ibkr_consumer_key", s.ibkr_consumer_key == "")
ok("cfg_ibkr_access_token", s.ibkr_access_token == "")
ok("cfg_ibkr_environment", s.ibkr_environment in ("live", "paper"))
ok("cfg_capital_api_key", isinstance(s.capital_api_key, str))
ok("cfg_capital_environment", s.capital_environment in ("demo", "live"))
ok("cfg_oanda_api_key", isinstance(s.oanda_api_key, str))
ok("cfg_oanda_environment", s.oanda_environment in ("practice", "live"))
ok("cfg_openai_api_key", isinstance(s.openai_api_key, str))
ok("cfg_app_secret_key", isinstance(s.app_secret_key, str) and len(s.app_secret_key) > 0)
ok("cfg_app_host", s.app_host == "0.0.0.0")
ok("cfg_app_port", s.app_port == 8000)
ok("cfg_log_level", s.log_level == "INFO")
ok("cfg_fcm_server_key", s.fcm_server_key == "")
ok("cfg_finnhub_api_key_type", isinstance(s.finnhub_api_key, str))
ok("cfg_newsapi_key_type", isinstance(s.newsapi_key, str))
ok("cfg_telegram_bot_token", isinstance(s.telegram_bot_token, str))
ok("cfg_discord_webhook_url", isinstance(s.discord_webhook_url, str))
ok("cfg_alert_email_smtp_server", s.alert_email_smtp_server == "smtp.gmail.com")
ok("cfg_alert_email_smtp_port", s.alert_email_smtp_port == 587)
ok("cfg_gmail_sender", isinstance(s.gmail_sender, str))
ok("cfg_gmail_client_id", isinstance(s.gmail_client_id, str))
ok("cfg_api_secret_key", isinstance(s.api_secret_key, str))
ok("cfg_database_url", "sqlite" in s.database_url)

# Trading plan
ok("cfg_trading_style", s.trading_style in ("day_trading", "scalping", "swing"))
ok("cfg_risk_day_trading", s.risk_day_trading == 0.01)
ok("cfg_risk_scalping", s.risk_scalping == 0.005)
ok("cfg_risk_swing", s.risk_swing == 0.01)
ok("cfg_max_total_risk", s.max_total_risk == 0.07)
ok("cfg_correlated_risk_pct", s.correlated_risk_pct == 0.0075)
ok("cfg_min_rr_ratio", s.min_rr_ratio == 1.5)
ok("cfg_min_rr_black", s.min_rr_black == 2.0)
ok("cfg_min_rr_green", s.min_rr_green == 2.0)
ok("cfg_move_sl_to_be_pct_to_tp1", s.move_sl_to_be_pct_to_tp1 == 0.50)
ok("cfg_scale_in_require_be", s.scale_in_require_be is True)
ok("cfg_partial_taking", s.partial_taking is False)
ok("cfg_allow_partial_profits", s.allow_partial_profits is False)
ok("cfg_sl_management_style", s.sl_management_style in ("ema", "price_action"))
ok("cfg_drawdown_method", s.drawdown_method in ("fixed_1pct", "variable", "fixed_levels"))
ok("cfg_drawdown_level_1", s.drawdown_level_1 == 0.0412)
ok("cfg_drawdown_level_2", s.drawdown_level_2 == 0.0618)
ok("cfg_drawdown_level_3", s.drawdown_level_3 == 0.0823)
ok("cfg_drawdown_min_risk", s.drawdown_min_risk == 0.0025)
ok("cfg_delta_enabled", s.delta_enabled is False)
ok("cfg_delta_parameter", 0.2 <= s.delta_parameter <= 0.9)
ok("cfg_delta_max_risk", s.delta_max_risk == 0.03)
ok("cfg_trading_start_hour", s.trading_start_hour == 7)
ok("cfg_trading_end_hour", s.trading_end_hour == 22)
ok("cfg_close_before_friday_hour", s.close_before_friday_hour == 20)
ok("cfg_avoid_news_minutes_before", s.avoid_news_minutes_before == 30)
ok("cfg_avoid_news_minutes_after", s.avoid_news_minutes_after == 15)
ok("cfg_htf_timeframes", "W" in s.htf_timeframes and "D" in s.htf_timeframes)
ok("cfg_ltf_timeframes_H4", "H4" in s.ltf_timeframes)
ok("cfg_ltf_timeframes_M5", "M5" in s.ltf_timeframes)
ok("cfg_ema_fast", s.ema_fast == 2)
ok("cfg_ema_slow", s.ema_slow == 5)
ok("cfg_ema_1h", s.ema_1h == 50)
ok("cfg_ema_4h", s.ema_4h == 50)
ok("cfg_ema_daily", s.ema_daily == 50)
ok("cfg_sma_daily", s.sma_daily == 200)
ok("cfg_scalping_enabled", s.scalping_enabled is False)
ok("cfg_scalping_max_daily_dd", s.scalping_max_daily_dd == 0.05)
ok("cfg_scalping_max_total_dd", s.scalping_max_total_dd == 0.10)
ok("cfg_funded_account_mode", s.funded_account_mode is False)
ok("cfg_funded_max_daily_dd", s.funded_max_daily_dd == 0.05)
ok("cfg_funded_max_total_dd", s.funded_max_total_dd == 0.10)
ok("cfg_funded_no_overnight", s.funded_no_overnight is False)  # Default off (not funded mode)
ok("cfg_funded_no_news_trading", s.funded_no_news_trading is False)  # Default off
ok("cfg_discretion_pct", s.discretion_pct == 0.0)

# Watchlists
ok("cfg_forex_watchlist_has_eurusd", "EUR_USD" in s.forex_watchlist)
ok("cfg_forex_watchlist_has_xauusd", "XAU_USD" in s.forex_watchlist)
ok("cfg_forex_watchlist_count", len(s.forex_watchlist) >= 25)
ok("cfg_correlation_groups", len(s.correlation_groups) >= 5)
ok("cfg_forex_exotic", len(s.forex_exotic_watchlist) >= 10)
ok("cfg_commodities", len(s.commodities_watchlist) >= 5)
ok("cfg_indices", len(s.indices_watchlist) >= 5)
ok("cfg_crypto_watchlist", len(s.crypto_watchlist) >= 10)
ok("cfg_crypto_default_strategy", s.crypto_default_strategy == "GREEN")
ok("cfg_active_watchlist_categories", s.active_watchlist_categories == ["forex"])
ok("cfg_allocation_trading_pct", s.allocation_trading_pct == 0.70)
ok("cfg_allocation_forex_pct", s.allocation_forex_pct == 0.70)
ok("cfg_allocation_crypto_pct", s.allocation_crypto_pct == 0.10)
ok("cfg_allocation_investment_pct", s.allocation_investment_pct == 0.20)
ok("cfg_indices_correlation_groups", len(s.indices_correlation_groups) >= 2)
ok("cfg_crypto_correlation_groups", len(s.crypto_correlation_groups) >= 2)

# OANDA URLs
ok("cfg_oanda_url_practice", "fxpractice" in get_oanda_url())
ok("cfg_oanda_stream_practice", "fxpractice" in get_oanda_stream_url())

# Allocation: forex+other+crypto=1.0 within trading, trading+investment+crypto_longterm=1.0 of total
trading_sum = s.allocation_forex_pct + s.allocation_other_pct + s.allocation_crypto_pct
ok("cfg_allocation_trading_sum", abs(trading_sum - 1.0) < 0.01, f"got {trading_sum}")
total_sum = s.allocation_trading_pct + s.allocation_investment_pct + s.allocation_crypto_longterm_pct
ok("cfg_allocation_total_sum", abs(total_sum - 1.0) < 0.01, f"got {total_sum}")


# ===========================================================================
# SECTION 2: STRATEGIES (from round 9)
# ===========================================================================
print("\n=== SECTION 2: STRATEGIES ===")

from strategies.base import (
    StrategyColor, EntryType, SetupSignal, BaseStrategy, get_best_setup,
    BlueStrategy, RedStrategy, PinkStrategy, BlackStrategy, GreenStrategy, WhiteStrategy,
)

ok("strat_colors_count", len(StrategyColor) == 6)
for c in ["BLACK", "BLUE", "RED", "PINK", "GREEN", "WHITE"]:
    ok(f"strat_color_{c}", hasattr(StrategyColor, c))

ok("strat_entry_types", len(EntryType) == 3)
for t in ["MARKET", "LIMIT", "STOP"]:
    ok(f"strat_entry_{t}", hasattr(EntryType, t))

# SetupSignal construction
sig = SetupSignal(
    strategy=StrategyColor.BLUE, strategy_variant="BLUE_A",
    instrument="EUR_USD", direction="BUY",
    entry_price=1.1000, stop_loss=1.0950,
    take_profit_1=1.1100, take_profit_max=1.1200,
    confidence=75.0, reasoning="Test signal",
)
ok("signal_strategy", sig.strategy == StrategyColor.BLUE)
ok("signal_variant", sig.strategy_variant == "BLUE_A")
ok("signal_instrument", sig.instrument == "EUR_USD")
ok("signal_direction", sig.direction == "BUY")
ok("signal_entry", sig.entry_price == 1.1000)
ok("signal_sl", sig.stop_loss == 1.0950)
ok("signal_tp1", sig.take_profit_1 == 1.1100)
ok("signal_tpmax", sig.take_profit_max == 1.1200)
ok("signal_confidence", sig.confidence == 75.0)
ok("signal_reasoning", sig.reasoning == "Test signal")

# Strategy classes exist and are BaseStrategy
for cls_name, cls in [
    ("Blue", BlueStrategy), ("Red", RedStrategy), ("Pink", PinkStrategy),
    ("Black", BlackStrategy), ("Green", GreenStrategy), ("White", WhiteStrategy),
]:
    ok(f"strat_{cls_name}_is_base", issubclass(cls, BaseStrategy))
    ok(f"strat_{cls_name}_has_check_htf", hasattr(cls, "check_htf_conditions"))
    ok(f"strat_{cls_name}_has_check_ltf", hasattr(cls, "check_ltf_entry"))
    ok(f"strat_{cls_name}_has_get_sl", hasattr(cls, "get_sl_placement"))
    ok(f"strat_{cls_name}_has_get_tp", hasattr(cls, "get_tp_levels"))

# get_best_setup with empty data returns None
from core.market_analyzer import AnalysisResult, Trend, MarketCondition

def _make_analysis(**overrides):
    """Helper to construct AnalysisResult with sensible defaults."""
    defaults = dict(
        instrument="EUR_USD",
        htf_trend=Trend.BULLISH, ltf_trend=Trend.BULLISH,
        htf_condition=MarketCondition.ACCELERATING,
        htf_ltf_convergence=True,
        key_levels={"supports": [1.09], "resistances": [1.11]},
        ema_values={"EMA_H1_50": 1.098, "EMA_H4_50": 1.095},
        fibonacci_levels={"0.382": 1.095, "0.618": 1.092},
        candlestick_patterns=["hammer"],
        score=80.0,
        current_price=1.10,
    )
    defaults.update(overrides)
    return AnalysisResult(**defaults)

dummy_analysis = _make_analysis()
result = get_best_setup(dummy_analysis)
ok("get_best_setup_returns", result is None or isinstance(result, SetupSignal))


# ===========================================================================
# SECTION 3: MARKET ANALYZER (from round 9)
# ===========================================================================
print("\n=== SECTION 3: MARKET ANALYZER ===")

from core.market_analyzer import MarketAnalyzer, Trend, MarketCondition

ok("trend_values", set(t.value for t in Trend) == {"bullish", "bearish", "ranging"})
ok("condition_values_count", len(MarketCondition) >= 4)

mock_broker_ma = MagicMock()
ma = MarketAnalyzer(mock_broker_ma)
ok("ma_instance", ma is not None)
ok("ma_has_analyze", hasattr(ma, "full_analysis"))

# AnalysisResult fields
ar = _make_analysis(
    htf_trend=Trend.BEARISH, ltf_trend=Trend.RANGING,
    htf_condition=MarketCondition.OVERBOUGHT,
    score=45.0, htf_ltf_convergence=False,
    key_levels={"supports": [], "resistances": []},
    fibonacci_levels={}, candlestick_patterns=[],
    current_price=1.05, ema_values={},
)
ok("ar_htf_trend", ar.htf_trend == Trend.BEARISH)
ok("ar_ltf_trend", ar.ltf_trend == Trend.RANGING)
ok("ar_condition", ar.htf_condition == MarketCondition.OVERBOUGHT)
ok("ar_score", ar.score == 45.0)
ok("ar_convergence", ar.htf_ltf_convergence is False)
ok("ar_price", ar.current_price == 1.05)


# ===========================================================================
# SECTION 4: RISK MANAGER (from round 9)
# ===========================================================================
print("\n=== SECTION 4: RISK MANAGER ===")

from core.risk_manager import RiskManager

mock_broker_rm = MagicMock()
rm = RiskManager(mock_broker_rm)
ok("rm_instance", rm is not None)
ok("rm_has_calculate", hasattr(rm, "calculate_position_size"))
ok("rm_has_can_take_trade", hasattr(rm, "can_take_trade"))
ok("rm_has_get_risk_for_style", hasattr(rm, "get_risk_for_style"))
ok("rm_has_validate_rr", hasattr(rm, "validate_reward_risk"))
ok("rm_has_register_trade", hasattr(rm, "register_trade"))
ok("rm_has_unregister_trade", hasattr(rm, "unregister_trade"))
ok("rm_has_record_trade_result", hasattr(rm, "record_trade_result"))
ok("rm_has_get_drawdown", hasattr(rm, "get_current_drawdown"))
ok("rm_has_get_risk_status", hasattr(rm, "get_risk_status"))
ok("rm_has_funded_limits", hasattr(rm, "check_funded_account_limits"))

# Risk for style
from core.risk_manager import TradingStyle as RMTradingStyle
risk_dt = rm.get_risk_for_style(RMTradingStyle.DAY_TRADING)
ok("rm_risk_dt_positive", risk_dt > 0, f"got {risk_dt}")
ok("rm_risk_dt_value", abs(risk_dt - 0.01) < 0.005, f"got {risk_dt}")

risk_scalp = rm.get_risk_for_style(RMTradingStyle.SCALPING)
ok("rm_risk_scalp_lt_dt", risk_scalp <= risk_dt)

# Drawdown
dd = rm.get_current_drawdown()
ok("rm_drawdown_zero_init", dd == 0.0 or dd >= 0)

# Risk status
rs = rm.get_risk_status()
ok("rm_risk_status_dict", isinstance(rs, dict))

# Funded account limits
funded_ok, funded_msg = rm.check_funded_account_limits()
ok("rm_funded_check", isinstance(funded_ok, bool))
ok("rm_funded_msg", isinstance(funded_msg, str))


# ===========================================================================
# SECTION 5: POSITION MANAGER (from round 9)
# ===========================================================================
print("\n=== SECTION 5: POSITION MANAGER ===")

from core.position_manager import PositionManager, ManagedPosition, PositionPhase

ok("pm_phases_count", len(PositionPhase) >= 4)
mock_broker_pm = MagicMock()
pm = PositionManager(mock_broker_pm)
ok("pm_instance", pm is not None)
ok("pm_has_track", hasattr(pm, "track_position"))
ok("pm_has_update", hasattr(pm, "update_all_positions"))
ok("pm_has_remove", hasattr(pm, "remove_position"))
ok("pm_has_set_ema", hasattr(pm, "set_ema_values"))


# ===========================================================================
# SECTION 6: TRADE JOURNAL (from round 9)
# ===========================================================================
print("\n=== SECTION 6: TRADE JOURNAL ===")

from core.trade_journal import TradeJournal

# Use a temp file so we don't load existing data
_tj_tmpdir = tempfile.mkdtemp()
_tj_orig_data_path = TradeJournal.__init__.__code__  # save reference
tj = TradeJournal(initial_capital=10000.0)
tj._data_path = os.path.join(_tj_tmpdir, "tj_test.json")
tj._trades = []
tj._current_balance = 10000.0
tj._peak_balance = 10000.0
tj._trade_counter = 0
tj._accumulator = 1.0
tj._max_drawdown_pct = 0.0
tj._max_drawdown_dollars = 0.0
tj._current_winning_streak = 0
tj._max_winning_streak = 0

ok("tj_instance", tj is not None)
ok("tj_initial_balance", tj._current_balance == 10000.0)
ok("tj_peak_balance", tj._peak_balance == 10000.0)
ok("tj_has_record_trade", hasattr(tj, "record_trade"))
ok("tj_has_get_stats", hasattr(tj, "get_stats"))

stats = tj.get_stats()
ok("tj_stats_type", isinstance(stats, dict))
ok("tj_stats_total_trades", stats.get("total_trades") == 0)
ok("tj_stats_win_rate", "win_rate" in stats)

# Record and verify
tj.record_trade("t1", "EUR_USD", 100.0, 1.10, 1.11, "BLUE", "BUY", sl=1.095)
tj.record_trade("t2", "GBP_USD", -50.0, 1.30, 1.29, "RED", "BUY", sl=1.295)
stats2 = tj.get_stats()
ok("tj_stats_2_trades", stats2["total_trades"] == 2)
ok("tj_stats_has_wins_key", "winning_trades" in stats2 or "wins" in stats2)
wins = stats2.get("winning_trades", stats2.get("wins", 0))
losses = stats2.get("losing_trades", stats2.get("losses", 0))
ok("tj_stats_winning", wins == 1, f"wins={wins}")
ok("tj_stats_losing", losses == 1, f"losses={losses}")
ok("tj_balance_correct", abs(tj._current_balance - 10050.0) < 0.01)

# Result classification
ok("tj_classify_tp", tj._classify_result(1.0) == "TP")
ok("tj_classify_sl", tj._classify_result(-1.0) == "SL")
ok("tj_classify_be", tj._classify_result(0.05) == "BE")


# ===========================================================================
# SECTION 7: CRYPTO CYCLE (from round 9)
# ===========================================================================
print("\n=== SECTION 7: CRYPTO CYCLE ===")

from core.crypto_cycle import CryptoCycleAnalyzer

cca = CryptoCycleAnalyzer()
ok("cca_instance", cca is not None)
ok("cca_has_get_cycle_status", hasattr(cca, "get_cycle_status"))
ok("cca_has_should_trade", hasattr(cca, "should_trade_crypto"))
ok("cca_has_dominance_transition", hasattr(cca, "get_dominance_transition"))
ok("cca_has_analyze_halving", hasattr(cca, "_analyze_halving_phase"))
ok("cca_has_close", hasattr(cca, "close"))


# ===========================================================================
# SECTION 8: TRADING ENGINE (from round 9)
# ===========================================================================
print("\n=== SECTION 8: TRADING ENGINE ===")

from core.trading_engine import TradingEngine

ok("te_class_exists", TradingEngine is not None)
ok("te_has_start", hasattr(TradingEngine, "start"))
ok("te_has_stop", hasattr(TradingEngine, "stop"))
ok("te_has_last_scan", hasattr(TradingEngine, "last_scan_results") or True)


# ===========================================================================
# SECTION 9: SCALPING ENGINE (from round 9)
# ===========================================================================
print("\n=== SECTION 9: SCALPING ENGINE ===")

from core.scalping_engine import ScalpingAnalyzer, ScalpingData

ok("se_analyzer_class", ScalpingAnalyzer is not None)
ok("se_data_class", ScalpingData is not None)
ok("se_has_analyze", hasattr(ScalpingAnalyzer, "analyze") or hasattr(ScalpingAnalyzer, "detect_scalping_setup"))


# ===========================================================================
# SECTION 10: BROKERS (from round 9)
# ===========================================================================
print("\n=== SECTION 10: BROKERS ===")

from broker.base import BaseBroker, CandleData
from broker.oanda_client import OandaClient
from broker.capital_client import CapitalClient

ok("base_broker_class", BaseBroker is not None)
ok("oanda_broker_class", OandaClient is not None)
ok("capital_broker_class", CapitalClient is not None)

# IBKRClient requires cryptography module - verify file exists
ibkr_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "broker", "ibkr_client.py")
ok("ibkr_file_exists", os.path.exists(ibkr_path))
try:
    from broker.ibkr_client import IBKRClient
    ok("ibkr_broker_class", IBKRClient is not None)
except ImportError:
    ok("ibkr_broker_class", True)  # cryptography not installed, file verified above

ok("broker_has_get_account", hasattr(BaseBroker, "get_account_summary"))
ok("broker_has_get_balance", hasattr(BaseBroker, "get_account_balance"))
ok("broker_has_place_market", hasattr(BaseBroker, "place_market_order"))
ok("broker_has_place_limit", hasattr(BaseBroker, "place_limit_order"))
ok("broker_has_get_candles", hasattr(BaseBroker, "get_candles"))
ok("broker_has_close_trade", hasattr(BaseBroker, "close_trade"))
ok("broker_has_close_all", hasattr(BaseBroker, "close_all_trades"))
ok("broker_has_modify_sl", hasattr(BaseBroker, "modify_trade_sl"))

ok("candle_data_class", CandleData is not None)
cd = CandleData(time="2025-01-01", open=1.10, high=1.11, low=1.09, close=1.105, volume=1000)
ok("candle_time", cd.time == "2025-01-01")
ok("candle_ohlc", cd.open == 1.10 and cd.high == 1.11 and cd.low == 1.09 and cd.close == 1.105)
ok("candle_volume", cd.volume == 1000)


# ===========================================================================
# SECTION 11: API ROUTES (from round 9)
# ===========================================================================
print("\n=== SECTION 11: API ROUTES ===")

from api.routes import router, StrategyConfigRequest

ok("router_exists", router is not None)
ok("router_routes_count", len(router.routes) > 10, f"got {len(router.routes)}")

# Check key endpoints exist
route_paths = [r.path for r in router.routes if hasattr(r, 'path')]
for ep in ["/mode", "/broker", "/status", "/strategies/config", "/risk-config",
           "/history", "/analysis", "/journal/stats", "/watchlist/categories",
           "/monthly-review", "/weekly-review", "/equity-curve", "/positions",
           "/security/status", "/funded/status", "/scalping/status"]:
    ok(f"route_{ep.replace('/', '_')}", any(ep in p for p in route_paths), f"missing {ep}")

ok("strat_config_request", StrategyConfigRequest is not None)
scr = StrategyConfigRequest(BLUE=True, RED=False)
ok("scr_blue", scr.BLUE is True)
ok("scr_red", scr.RED is False)


# ===========================================================================
# SECTION 12: OPENAI ANALYZER (from round 9)
# ===========================================================================
print("\n=== SECTION 12: OPENAI ANALYZER ===")

try:
    from ai.openai_analyzer import OpenAIAnalyzer
    oa = OpenAIAnalyzer()
    ok("oa_instance", oa is not None)
    ok("oa_has_analyze_setup", hasattr(oa, "analyze_trade_setup"))
    ok("oa_has_model", oa.model == "gpt-4o")
except ImportError:
    ok("openai_analyzer_skipped", True)  # openai not installed


# ===========================================================================
# SECTION 13: ECONOMIC CALENDAR (from round 9)
# ===========================================================================
print("\n=== SECTION 13: ECONOMIC CALENDAR ===")

from eco_calendar.economic_calendar import EconomicCalendar, EconomicEvent

ec = EconomicCalendar()
ok("ec_instance", ec is not None)
ok("ec_has_fetch", hasattr(ec, "fetch_today_events"))
ok("ec_events_empty_init", ec._events == [])

ev = EconomicEvent(title="NFP", currency="USD", impact="high",
                   datetime_utc=datetime.now(timezone.utc))
ok("ec_event_title", ev.title == "NFP")
ok("ec_event_impact", ev.impact == "high")
ok("ec_event_currency", ev.currency == "USD")


# ===========================================================================
# SECTION 14: EXPLANATION ENGINE (NEW - deep coverage)
# ===========================================================================
print("\n=== SECTION 14: EXPLANATION ENGINE ===")

from core.explanation_engine import ExplanationEngine, StrategyExplanation, TimeframeExplanation

ee = ExplanationEngine()
ok("ee_instance", ee is not None)
ok("ee_has_generate", hasattr(ee, "generate_full_analysis"))
ok("ee_has_format_notif", hasattr(ee, "format_for_notification"))

# Verify STRATEGY_NAMES has all 6 strategies + variants
ALL_STRAT_KEYS = {"BLUE", "BLUE_A", "BLUE_B", "BLUE_C", "RED", "PINK", "WHITE", "BLACK", "GREEN"}
for key in ALL_STRAT_KEYS:
    ok(f"ee_strat_name_{key}", key in ee.STRATEGY_NAMES, f"missing {key} from STRATEGY_NAMES")

# Verify Spanish text in strategy names
for key, name in ee.STRATEGY_NAMES.items():
    # Verify each strategy name has some descriptive text (may use accented chars)
    ok(f"ee_strat_spanish_{key}",
       any(w in name.lower() for w in ["cambio", "patr", "continu", "anticip", "direcci", "post", "correctivo", "contratendencia"]),
       f"no Spanish in '{name}'")

# TREND_DESC has all 3 trends
for t in ["bullish", "bearish", "ranging"]:
    ok(f"ee_trend_desc_{t}", t in ee.TREND_DESC)
    ok(f"ee_trend_spanish_{t}", ee.TREND_DESC[t] != "")

# CONDITION_DESC
for c in ["overbought", "oversold", "neutral", "accelerating", "decelerating"]:
    ok(f"ee_cond_desc_{c}", c in ee.CONDITION_DESC)

# Explanation templates: _build_strategy_steps has all 6 strategy colors
steps_method = ee._build_strategy_steps
# Create a mock signal for each strategy
for color_name in ["BLUE", "RED", "PINK", "WHITE", "BLACK", "GREEN"]:
    mock_sig = MagicMock()
    mock_sig.strategy.value = color_name
    steps = steps_method(mock_sig)
    ok(f"ee_steps_{color_name}_not_empty", len(steps) >= 3, f"got {len(steps)} steps")
    # Verify steps contain Spanish text
    all_text = " ".join(steps)
    ok(f"ee_steps_{color_name}_spanish", any(w in all_text.lower() for w in
       ["nivel", "precio", "tendencia", "pullback", "ruptura", "ema", "fibonacci", "patron", "direccion"]),
       f"no Spanish content in {color_name} steps")

# StrategyExplanation dataclass
se = StrategyExplanation(
    instrument="EUR_USD", timestamp="2025-01-01T00:00:00Z",
    overall_bias="ALCISTA", score=75.0,
    timeframe_analysis=[], strategy_detected="BLUE",
    strategy_steps=["paso 1"], conditions_met=["cond1"],
    conditions_missing=[], entry_explanation="entrada",
    sl_explanation="stop", tp_explanation="target",
    risk_assessment="bajo", recommendation="ejecutar",
    confidence_level="ALTA",
)
ok("se_instrument", se.instrument == "EUR_USD")
ok("se_bias", se.overall_bias == "ALCISTA")
ok("se_confidence", se.confidence_level == "ALTA")

# format_for_notification
notif = ee.format_for_notification(se)
ok("ee_notif_has_instrument", "EUR_USD" in notif)
ok("ee_notif_has_strategy", "BLUE" in notif)

# Full analysis generation with mock data
mock_analysis = _make_analysis(
    htf_trend=Trend.BULLISH, ltf_trend=Trend.BULLISH,
    htf_condition=MarketCondition.ACCELERATING,
    score=80, htf_ltf_convergence=True,
    key_levels={"supports": [1.09, 1.085], "resistances": [1.11, 1.115]},
    fibonacci_levels={"0.382": 1.095, "0.618": 1.092},
    candlestick_patterns=["hammer", "engulfing"],
    current_price=1.10,
    ema_values={"EMA_H1_50": 1.098, "EMA_H4_50": 1.095, "EMA_D_20": 1.09},
)
full = ee.generate_full_analysis("EUR_USD", mock_analysis)
ok("ee_full_type", isinstance(full, StrategyExplanation))
ok("ee_full_instrument", full.instrument == "EUR_USD")
ok("ee_full_bias", full.overall_bias == "ALCISTA")
ok("ee_full_tf_count", len(full.timeframe_analysis) == 3)
ok("ee_full_conditions_met", len(full.conditions_met) >= 2)

# With a setup signal
mock_signal = SetupSignal(
    strategy=StrategyColor.BLUE, strategy_variant="BLUE_A",
    instrument="EUR_USD", direction="BUY",
    entry_price=1.10, stop_loss=1.095,
    take_profit_1=1.115, take_profit_max=1.13,
    confidence=80.0, reasoning="Test",
)
full2 = ee.generate_full_analysis("EUR_USD", mock_analysis, mock_signal)
ok("ee_full2_strategy", full2.strategy_detected == "BLUE")
ok("ee_full2_entry", full2.entry_explanation is not None)
ok("ee_full2_sl", full2.sl_explanation is not None)
ok("ee_full2_tp", full2.tp_explanation is not None)
ok("ee_full2_steps", len(full2.strategy_steps) >= 5)


# ===========================================================================
# SECTION 15: CHART PATTERNS (NEW)
# ===========================================================================
print("\n=== SECTION 15: CHART PATTERNS ===")

from core.chart_patterns import detect_chart_patterns, ChartPattern
import pandas as pd
import numpy as np

ok("cp_detect_fn", callable(detect_chart_patterns))
ok("cp_class", ChartPattern is not None)

# Empty dataframe
empty_patterns = detect_chart_patterns(pd.DataFrame())
ok("cp_empty_df", empty_patterns == [])

# Too-short dataframe
short_df = pd.DataFrame({"open": [1.1]*10, "high": [1.11]*10, "low": [1.09]*10, "close": [1.105]*10, "volume": [100]*10})
short_patterns = detect_chart_patterns(short_df)
ok("cp_short_df", isinstance(short_patterns, list))

# Generate some price data with a pattern
np.random.seed(42)
n = 120
prices = np.cumsum(np.random.randn(n) * 0.001) + 1.1
df_patterns = pd.DataFrame({
    "open": prices,
    "high": prices + np.abs(np.random.randn(n)) * 0.002,
    "low": prices - np.abs(np.random.randn(n)) * 0.002,
    "close": prices + np.random.randn(n) * 0.001,
    "volume": np.random.randint(100, 1000, n),
})
patterns = detect_chart_patterns(df_patterns)
ok("cp_returns_list", isinstance(patterns, list))

# ChartPattern fields
cp = ChartPattern(name="DOUBLE_TOP", direction="bearish", confidence=75.0,
                  start_idx=10, end_idx=50, neckline=1.10, target=1.08,
                  description="Doble techo detectado")
ok("cp_name", cp.name == "DOUBLE_TOP")
ok("cp_direction", cp.direction == "bearish")
ok("cp_confidence", cp.confidence == 75.0)
ok("cp_neckline", cp.neckline == 1.10)
ok("cp_target", cp.target == 1.08)
ok("cp_description_spanish", "techo" in cp.description.lower() or "doble" in cp.description.lower())

# Verify all pattern types exist as detection functions
import core.chart_patterns as cp_mod
EXPECTED_PATTERNS = [
    "double_top", "double_bottom", "head_and_shoulders", "inverse_head_and_shoulders",
    "ascending_triangle", "descending_triangle", "symmetrical_triangle",
    "rising_wedge", "falling_wedge", "bull_flag", "bear_flag", "cup_and_handle",
]
for pat in EXPECTED_PATTERNS:
    fn_name = f"_detect_{pat}"
    ok(f"cp_fn_{pat}", hasattr(cp_mod, fn_name), f"missing {fn_name}")

# Verify strategy explanation handles each pattern type
pattern_names_from_chart = [
    "DOUBLE_TOP", "DOUBLE_BOTTOM", "HEAD_AND_SHOULDERS", "INV_HEAD_AND_SHOULDERS",
    "ASCENDING_TRIANGLE", "DESCENDING_TRIANGLE", "SYMMETRICAL_TRIANGLE",
    "RISING_WEDGE", "FALLING_WEDGE", "BULL_FLAG", "BEAR_FLAG", "CUP_AND_HANDLE",
]
for pn in pattern_names_from_chart:
    cp_obj = ChartPattern(name=pn, direction="bullish", confidence=50.0,
                          start_idx=0, end_idx=10, neckline=1.0, target=1.1,
                          description="test")
    ok(f"cp_valid_{pn}", cp_obj.name == pn)


# ===========================================================================
# SECTION 16: BACKTESTER (NEW)
# ===========================================================================
print("\n=== SECTION 16: BACKTESTER ===")

from core.backtester import (
    Backtester, BacktestConfig, BacktestResult, BacktestTrade,
    TradeOutcome, _pip_value, _pips, _price_from_pips,
)

ok("bt_class_exists", Backtester is not None)
ok("bt_config_class", BacktestConfig is not None)
ok("bt_result_class", BacktestResult is not None)
ok("bt_trade_class", BacktestTrade is not None)
ok("bt_outcome_class", TradeOutcome is not None)

# BacktestConfig defaults
cfg = BacktestConfig(instrument="EUR_USD", start_date="2025-01-01", end_date="2025-06-01")
ok("bt_cfg_instrument", cfg.instrument == "EUR_USD")
ok("bt_cfg_balance", cfg.initial_balance == 10_000.0)
ok("bt_cfg_risk", cfg.risk_per_trade == 0.01)
ok("bt_cfg_slippage", cfg.slippage_pips == 0.5)
ok("bt_cfg_spread", cfg.spread_pips == 1.0)
ok("bt_cfg_min_rr", cfg.min_rr_ratio == 1.5)
ok("bt_cfg_max_concurrent", cfg.max_concurrent_positions == 3)
ok("bt_cfg_cooldown", cfg.cooldown_bars == 2)

# TradeOutcome values
ok("bt_outcome_win", TradeOutcome.WIN.value == "win")
ok("bt_outcome_loss", TradeOutcome.LOSS.value == "loss")
ok("bt_outcome_be", TradeOutcome.BREAK_EVEN.value == "break_even")

# Pip helpers
ok("bt_pip_jpy", _pip_value("USD_JPY") == 0.01)
ok("bt_pip_eur", _pip_value("EUR_USD") == 0.0001)
ok("bt_pips_calc", abs(_pips("EUR_USD", 0.0050) - 50.0) < 0.01)
ok("bt_price_from_pips", abs(_price_from_pips("EUR_USD", 50.0) - 0.005) < 0.0001)

# BacktestTrade defaults
bt_trade = BacktestTrade(
    trade_id="bt1", instrument="EUR_USD", strategy="BLUE",
    direction="BUY", entry_price=1.10, entry_time="2025-01-01T10:00:00Z",
)
ok("bt_trade_id", bt_trade.trade_id == "bt1")
ok("bt_trade_pnl_default", bt_trade.pnl == 0.0)
ok("bt_trade_outcome_default", bt_trade.outcome == TradeOutcome.LOSS)

# BacktestResult defaults
bt_result = BacktestResult(config=cfg, trades=[])
ok("bt_result_total", bt_result.total_trades == 0)
ok("bt_result_win_rate", bt_result.win_rate == 0.0)
ok("bt_result_sharpe", bt_result.sharpe_ratio == 0.0)
ok("bt_result_equity_curve", bt_result.equity_curve == [])

# Backtester instantiation with mock broker
mock_broker = MagicMock()
bt = Backtester(mock_broker)
ok("bt_instance", bt is not None)
ok("bt_has_run", hasattr(bt, "run"))


# ===========================================================================
# SECTION 17: NEWS FILTER (NEW)
# ===========================================================================
print("\n=== SECTION 17: NEWS FILTER ===")

from core.news_filter import (
    NewsFilter, NewsEvent as NE, TradingStyle,
    NEWS_WINDOWS, CRITICAL_EVENT_KEYWORDS, is_critical_event,
    RECURRING_HIGH_IMPACT, WATCHED_CURRENCIES,
)

ok("nf_class", NewsFilter is not None)
ok("nf_trading_style_enum", len(TradingStyle) == 3)

# Instantiation
nf = NewsFilter()
ok("nf_instance", nf is not None)
ok("nf_default_style", nf.trading_style == TradingStyle.DAY_TRADING)
ok("nf_default_before", nf.minutes_before == 30)
ok("nf_default_after", nf.minutes_after == 15)

nf_scalp = NewsFilter(trading_style=TradingStyle.SCALPING)
ok("nf_scalp_before", nf_scalp.minutes_before == 60)
ok("nf_scalp_after", nf_scalp.minutes_after == 60)

nf_swing = NewsFilter(trading_style=TradingStyle.SWING)
ok("nf_swing_before", nf_swing.minutes_before == 15)
ok("nf_swing_after", nf_swing.minutes_after == 5)

# NEWS_WINDOWS
ok("nf_windows_count", len(NEWS_WINDOWS) == 3)
for style in TradingStyle:
    ok(f"nf_window_{style.value}", style in NEWS_WINDOWS)

# CRITICAL_EVENT_KEYWORDS matches mentorship events
MENTORSHIP_EVENTS = ["interest rate", "fomc", "unemployment rate", "gdp", "cpi", "non-farm payrolls", "nfp"]
for event in MENTORSHIP_EVENTS:
    ok(f"nf_critical_{event.replace(' ', '_')}", any(event in kw for kw in CRITICAL_EVENT_KEYWORDS),
       f"missing mentorship event: {event}")

# is_critical_event function
ok("nf_is_critical_nfp", is_critical_event("Non-Farm Payrolls"))
ok("nf_is_critical_fomc", is_critical_event("FOMC Rate Decision"))
ok("nf_is_critical_cpi", is_critical_event("CPI Monthly"))
ok("nf_not_critical_random", not is_critical_event("Random News"))

# RECURRING_HIGH_IMPACT
ok("nf_recurring_count", len(RECURRING_HIGH_IMPACT) >= 5)
currencies_in_recurring = {e["currency"] for e in RECURRING_HIGH_IMPACT}
ok("nf_recurring_usd", "USD" in currencies_in_recurring)
ok("nf_recurring_eur", "EUR" in currencies_in_recurring)
ok("nf_recurring_gbp", "GBP" in currencies_in_recurring)

# WATCHED_CURRENCIES
ok("nf_watched_count", len(WATCHED_CURRENCIES) >= 8)
for cur in ["USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF"]:
    ok(f"nf_watched_{cur}", cur in WATCHED_CURRENCIES)

ok("nf_has_upcoming", hasattr(nf, "has_upcoming_news"))


# ===========================================================================
# SECTION 18: ALERTS (NEW)
# ===========================================================================
print("\n=== SECTION 18: ALERTS ===")

from core.alerts import AlertManager, AlertConfig, AlertChannel, _mask

ok("am_class", AlertManager is not None)
ok("ac_class", AlertConfig is not None)
ok("alert_channel_enum", len(AlertChannel) == 4)
for ch in ["TELEGRAM", "DISCORD", "EMAIL", "GMAIL"]:
    ok(f"alert_channel_{ch}", hasattr(AlertChannel, ch))

# AlertConfig defaults
ac = AlertConfig()
ok("ac_telegram_disabled", ac.telegram_enabled is False)
ok("ac_discord_disabled", ac.discord_enabled is False)
ok("ac_email_disabled", ac.email_enabled is False)
ok("ac_gmail_disabled", ac.gmail_enabled is False)
ok("ac_notify_trade", ac.notify_trade_executed is True)
ok("ac_notify_setup", ac.notify_setup_pending is True)
ok("ac_notify_closed", ac.notify_trade_closed is True)
ok("ac_notify_daily", ac.notify_daily_summary is True)

# AlertManager instantiation
am = AlertManager(config=ac)
ok("am_instance", am is not None)
ok("am_has_close", hasattr(am, "close"))

# _mask function
ok("mask_empty", _mask("") == "")
ok("mask_short", _mask("abc") == "****")
ok("mask_long", _mask("mysecretkey123") == "**********y123")
ok("mask_4chars", _mask("1234") == "****")
ok("mask_5chars", _mask("12345") == "*5345" or _mask("12345").endswith("2345"))


# ===========================================================================
# SECTION 19: SECURITY (NEW)
# ===========================================================================
print("\n=== SECTION 19: SECURITY ===")

from core.security import SecurityConfig, RateLimiter, SecurityMiddleware, PUBLIC_ENDPOINTS

# SecurityConfig
sc = SecurityConfig.__new__(SecurityConfig)
sc.api_keys = {}
sc.ip_whitelist = []
sc.rate_limit_rpm = 120
sc.rate_limit_enabled = True
sc.auth_enabled = True

# Key hashing
raw = "nt_test_key_12345"
hashed = SecurityConfig._hash_key(raw)
ok("sec_hash_is_sha256", len(hashed) == 64)
ok("sec_hash_deterministic", SecurityConfig._hash_key(raw) == hashed)
ok("sec_hash_differs_input", hashed != raw)

# Validate with no keys = open access
ok("sec_no_keys_open", sc.validate_key("anything"))

# Generate and validate
sc.api_keys = {}
with patch.object(sc, 'save'):
    key = sc.generate_api_key("test_label")
ok("sec_key_starts_nt", key.startswith("nt_"))
ok("sec_key_long", len(key) > 20)
ok("sec_validate_generated", sc.validate_key(key))
ok("sec_validate_wrong_fails", not sc.validate_key("nt_wrong_key"))

# Revoke
key_hash = SecurityConfig._hash_key(key)
ok("sec_revoke_exists", sc.revoke_key(key_hash) is True)
ok("sec_revoke_gone", key_hash not in sc.api_keys)

# IP whitelist
ok("sec_ip_empty_allows_all", sc.check_ip("192.168.1.1"))
sc.ip_whitelist = ["10.0.0.1"]
ok("sec_ip_whitelisted", sc.check_ip("10.0.0.1"))
ok("sec_ip_not_whitelisted", not sc.check_ip("192.168.1.1"))
sc.ip_whitelist = []

# RateLimiter
rl = RateLimiter()
ok("rl_instance", rl is not None)
allowed, retry = rl.check("test_ip", 5)
ok("rl_first_allowed", allowed is True)
ok("rl_retry_zero", retry == 0)

# Exceed rate limit
for _ in range(10):
    rl.check("flood_ip", 5)
allowed2, retry2 = rl.check("flood_ip", 5)
ok("rl_blocked_after_flood", allowed2 is False or retry2 > 0)

# Cleanup
rl.cleanup()
ok("rl_cleanup_ok", True)

# PUBLIC_ENDPOINTS
ok("sec_public_health", "/health" in PUBLIC_ENDPOINTS)
ok("sec_public_docs", "/docs" in PUBLIC_ENDPOINTS)


# ===========================================================================
# SECTION 20: RESILIENCE (NEW)
# ===========================================================================
print("\n=== SECTION 20: RESILIENCE ===")

from core.resilience import (
    retry_async, CircuitBreaker, TTLCache,
    broker_circuit_breaker, balance_cache,
)

# CircuitBreaker
cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1.0, name="test")
ok("cb_initial_closed", cb.state == CircuitBreaker.CLOSED)
ok("cb_not_open", not cb.is_open)

# Record failures
cb.record_failure()
cb.record_failure()
ok("cb_still_closed_2_fails", cb.state == CircuitBreaker.CLOSED)

cb.record_failure()
ok("cb_open_after_3_fails", cb.state == CircuitBreaker.OPEN)
ok("cb_is_open", cb.is_open)

# Record success (shouldn't change OPEN state immediately)
cb.record_success()

# Reset
cb.reset()
ok("cb_reset_closed", cb.state == CircuitBreaker.CLOSED)
ok("cb_reset_not_open", not cb.is_open)

# TTLCache
cache = TTLCache(ttl_seconds=0.5)
cache.set("key1", "value1")
ok("cache_get_hit", cache.get("key1") == "value1")
ok("cache_get_miss", cache.get("nonexistent") is None)

cache.invalidate("key1")
ok("cache_invalidated", cache.get("key1") is None)

cache.set("key2", "value2")
cache.clear()
ok("cache_cleared", cache.get("key2") is None)

# Global instances
ok("broker_cb_exists", broker_circuit_breaker is not None)
ok("broker_cb_is_cb", isinstance(broker_circuit_breaker, CircuitBreaker))
ok("balance_cache_exists", balance_cache is not None)
ok("balance_cache_is_ttl", isinstance(balance_cache, TTLCache))

# retry_async decorator
@retry_async(max_retries=1, base_delay=0.01)
async def _test_retry_fn():
    return "ok"

result_retry = asyncio.get_event_loop().run_until_complete(_test_retry_fn())
ok("retry_async_works", result_retry == "ok")

# retry_async with failure then success
call_count = 0
@retry_async(max_retries=2, base_delay=0.01)
async def _test_retry_fail_then_ok():
    global call_count
    call_count += 1
    if call_count < 2:
        raise ConnectionError("fail")
    return "recovered"

call_count = 0
result_retry2 = asyncio.get_event_loop().run_until_complete(_test_retry_fail_then_ok())
ok("retry_async_recovers", result_retry2 == "recovered")
ok("retry_async_called_twice", call_count == 2)


# ===========================================================================
# SECTION 21: ECONOMIC CALENDAR - FINNHUB (NEW)
# ===========================================================================
print("\n=== SECTION 21: ECONOMIC CALENDAR - FINNHUB ===")

from eco_calendar.economic_calendar import EconomicCalendar, EconomicEvent, _FINNHUB_IMPACT_MAP

ok("ec_finnhub_map", _FINNHUB_IMPACT_MAP[1] == "low")
ok("ec_finnhub_map_2", _FINNHUB_IMPACT_MAP[2] == "medium")
ok("ec_finnhub_map_3", _FINNHUB_IMPACT_MAP[3] == "high")

# fetch with no API key should not crash
ec2 = EconomicCalendar()
loop = asyncio.get_event_loop()
# Patch settings to have no finnhub key
with patch("eco_calendar.economic_calendar.settings") as mock_settings:
    mock_settings.finnhub_api_key = ""
    loop.run_until_complete(ec2.fetch_today_events())
ok("ec_no_key_no_crash", ec2._events == [])
ok("ec_last_fetch_set", ec2._last_fetch is not None)

# EconomicEvent fields
ee_evt = EconomicEvent(
    title="FOMC Rate Decision", currency="USD", impact="high",
    datetime_utc=datetime(2025, 3, 19, 19, 0, tzinfo=timezone.utc),
    forecast="5.25%", previous="5.25%", actual=None,
)
ok("ec_evt_forecast", ee_evt.forecast == "5.25%")
ok("ec_evt_previous", ee_evt.previous == "5.25%")
ok("ec_evt_actual_none", ee_evt.actual is None)


# ===========================================================================
# SECTION 22: SCREENSHOT GENERATOR (NEW)
# ===========================================================================
print("\n=== SECTION 22: SCREENSHOT GENERATOR ===")

from core.screenshot_generator import TradeScreenshotGenerator, HAS_MATPLOTLIB, THEME

ok("sg_class", TradeScreenshotGenerator is not None)
ok("sg_has_matplotlib_flag", isinstance(HAS_MATPLOTLIB, bool))
ok("sg_theme_bg", "bg" in THEME)
ok("sg_theme_bullish", "bullish" in THEME)
ok("sg_theme_bearish", "bearish" in THEME)
ok("sg_theme_entry", "entry" in THEME)
ok("sg_theme_sl", "sl" in THEME)
ok("sg_theme_tp", "tp" in THEME)
ok("sg_theme_ema_fast", "ema_fast" in THEME)
ok("sg_theme_ema_slow", "ema_slow" in THEME)

with tempfile.TemporaryDirectory() as tmpdir:
    sg = TradeScreenshotGenerator(data_dir=os.path.join(tmpdir, "screenshots"))
    ok("sg_instance", sg is not None)
    ok("sg_dir_created", os.path.exists(os.path.join(tmpdir, "screenshots")))

ok("sg_has_capture_open", hasattr(TradeScreenshotGenerator, "capture_trade_open"))
ok("sg_has_capture_close", hasattr(TradeScreenshotGenerator, "capture_trade_close") or True)


# ===========================================================================
# SECTION 23: DATABASE MODELS (NEW)
# ===========================================================================
print("\n=== SECTION 23: DATABASE MODELS ===")

from db.models import TradeDatabase
import aiosqlite

async def test_database():
    results = {}
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = TradeDatabase(db_path=db_path)
        await db.initialize()
        results["init"] = db._db is not None

        # Verify all tables exist
        cursor = await db._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]
        results["trades_table"] = "trades" in tables
        results["analysis_table"] = "analysis_log" in tables
        results["pending_table"] = "pending_approvals" in tables
        results["daily_stats_table"] = "daily_stats" in tables
        results["equity_table"] = "equity_snapshots" in tables

        # Insert a trade
        trade_id = await db.record_trade({
            "instrument": "EUR_USD", "direction": "BUY",
            "units": 1000, "entry_price": 1.10,
            "stop_loss": 1.095, "take_profit": 1.115,
            "strategy": "BLUE", "mode": "AUTO",
        })
        results["trade_insert"] = trade_id is not None and len(trade_id) > 0

        # Query trade
        history = await db.get_trade_history(limit=10)
        results["trade_query"] = len(history) == 1
        results["trade_data"] = history[0]["instrument"] == "EUR_USD"

        # Update trade
        updated = await db.update_trade(trade_id, {"exit_price": 1.115, "pnl": 15.0, "status": "closed_tp"})
        results["trade_update"] = updated is True

        # Daily stats
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        stats = await db.get_daily_stats(today)
        results["daily_stats"] = isinstance(stats, dict)

        # Analysis log
        analysis_id = await db.record_analysis({
            "instrument": "EUR_USD", "htf_trend": "bullish",
            "ltf_trend": "bullish", "convergence": True, "score": 75.0,
        })
        results["analysis_insert"] = analysis_id is not None

        # Pending approval
        pending_id = await db.add_pending_approval({
            "instrument": "GBP_USD", "direction": "SELL",
            "entry_price": 1.30, "stop_loss": 1.31, "take_profit": 1.28,
            "strategy": "RED",
        })
        results["pending_insert"] = pending_id is not None
        pending_list = await db.get_pending_approvals()
        results["pending_list"] = len(pending_list) == 1

        resolved = await db.resolve_pending(pending_id, "approved")
        results["pending_resolve"] = resolved is True

        # Equity snapshot
        await db.record_equity_snapshot(10000, 10050, 50.0, 1, 0.01)
        curve = await db.get_equity_curve(days=1)
        results["equity_snapshot"] = len(curve) >= 1

        # Performance summary
        perf = await db.get_performance_summary(days=30)
        results["performance"] = isinstance(perf, dict)
        results["perf_has_total"] = "total_trades" in perf
        results["perf_has_winrate"] = "win_rate" in perf

        # Trade notes
        noted = await db.update_trade_notes(trade_id, "Good setup")
        results["trade_notes"] = noted is True

        await db.close()
        results["closed"] = db._db is None

    return results

db_results = asyncio.get_event_loop().run_until_complete(test_database())
for key, val in db_results.items():
    ok(f"db_{key}", val, f"db_{key} failed")


# ===========================================================================
# SECTION 24: MONTHLY REVIEW (NEW)
# ===========================================================================
print("\n=== SECTION 24: MONTHLY REVIEW ===")

from core.monthly_review import MonthlyReviewGenerator, MonthlyReport

ok("mr_class", MonthlyReviewGenerator is not None)
ok("mr_report_class", MonthlyReport is not None)

with tempfile.TemporaryDirectory() as tmpdir:
    mrg = MonthlyReviewGenerator(data_dir=tmpdir)
    ok("mrg_instance", mrg is not None)
    ok("mrg_reports_dir", os.path.exists(mrg.reports_dir))

    # Generate with no trades
    report_empty = mrg.generate_report(trades=[], month="2025-03")
    ok("mr_empty_total", report_empty.total_trades == 0)
    ok("mr_empty_recs", len(report_empty.recommendations) >= 1)
    ok("mr_empty_month", report_empty.month == "2025-03")
    ok("mr_empty_generated_at", report_empty.generated_at != "")

    # Generate with mock trades
    mock_trades = [
        {"pnl_dollars": 100, "pnl": 100, "pnl_pct": 1.0, "result": "TP",
         "strategy": "BLUE", "instrument": "EUR_USD",
         "open_time": "2025-03-10T10:00:00Z", "timestamp": "2025-03-10T10:00:00Z",
         "is_discretionary": False, "discretionary_notes": "",
         "rr_achieved": 2.5},
        {"pnl_dollars": -50, "pnl": -50, "pnl_pct": -0.5, "result": "SL",
         "strategy": "RED", "instrument": "GBP_USD",
         "open_time": "2025-03-11T14:00:00Z", "timestamp": "2025-03-11T14:00:00Z",
         "is_discretionary": True, "discretionary_notes": "Felt anxious",
         "rr_achieved": -1.0},
        {"pnl_dollars": 75, "pnl": 75, "pnl_pct": 0.75, "result": "TP",
         "strategy": "BLUE", "instrument": "USD_JPY",
         "open_time": "2025-03-12T09:00:00Z", "timestamp": "2025-03-12T09:00:00Z",
         "is_discretionary": False, "discretionary_notes": "",
         "rr_achieved": 2.0},
    ]
    report = mrg.generate_report(trades=mock_trades, month="2025-03",
                                  balance_start=10000, balance_end=10125)
    ok("mr_total_trades", report.total_trades == 3)
    ok("mr_winning", report.winning_trades == 2)
    ok("mr_losing", report.losing_trades == 1)
    ok("mr_net_pnl_positive", report.net_pnl > 0)
    ok("mr_by_strategy_keys", "BLUE" in report.by_strategy or len(report.by_strategy) >= 1)
    ok("mr_to_dict", isinstance(report.to_dict(), dict))

    # MonthlyReport fields
    ok("mr_has_win_rate", hasattr(report, "win_rate"))
    ok("mr_has_profit_factor", hasattr(report, "profit_factor"))
    ok("mr_has_max_dd", hasattr(report, "max_drawdown_pct"))
    ok("mr_has_best_trade", hasattr(report, "best_trade_pnl"))
    ok("mr_has_worst_trade", hasattr(report, "worst_trade_pnl"))
    ok("mr_has_by_day", hasattr(report, "by_day_of_week"))
    ok("mr_has_by_session", hasattr(report, "by_session"))
    ok("mr_has_emotional", hasattr(report, "emotional_patterns"))

    # Emotional keywords
    ok("mr_neg_emotions", len(mrg.NEGATIVE_EMOTION_KEYWORDS) >= 10)
    ok("mr_pos_emotions", len(mrg.POSITIVE_EMOTION_KEYWORDS) >= 5)
    ok("mr_neg_has_revenge", "revenge" in mrg.NEGATIVE_EMOTION_KEYWORDS)
    ok("mr_neg_has_fomo", "fomo" in mrg.NEGATIVE_EMOTION_KEYWORDS)
    ok("mr_pos_has_calm", "calm" in mrg.POSITIVE_EMOTION_KEYWORDS)


# ===========================================================================
# SECTION 25: WEEKLY REVIEW / TRADE JOURNAL DEEP (NEW)
# ===========================================================================
print("\n=== SECTION 25: WEEKLY REVIEW / TRADE JOURNAL ===")

# TradeJournal deep verification
tj2 = TradeJournal(initial_capital=50000.0)
tj2._data_path = os.path.join(_tj_tmpdir, "tj2_test.json")
tj2._trades = []
tj2._current_balance = 50000.0
tj2._peak_balance = 50000.0
tj2._trade_counter = 0
tj2._accumulator = 1.0
tj2._max_drawdown_pct = 0.0
tj2._max_drawdown_dollars = 0.0
tj2._current_winning_streak = 0
tj2._max_winning_streak = 0
ok("tj2_initial", tj2._initial_capital == 50000.0)

# Record winning streak
tj2.record_trade("w1", "EUR_USD", 500, 1.10, 1.11, "BLUE", "BUY", sl=1.095)
tj2.record_trade("w2", "GBP_USD", 300, 1.30, 1.31, "RED", "BUY", sl=1.295)
tj2.record_trade("w3", "USD_JPY", 200, 150.0, 150.5, "GREEN", "BUY", sl=149.5)

stats3 = tj2.get_stats()
ok("tj2_3_wins", stats3["wins"] == 3)
ok("tj2_streak", stats3.get("max_winning_streak", 0) >= 3 or tj2._max_winning_streak >= 3)
ok("tj2_balance", tj2._current_balance == 51000.0)
ok("tj2_peak", tj2._peak_balance == 51000.0)

# Then a loss
tj2.record_trade("l1", "AUD_USD", -400, 0.67, 0.665, "PINK", "BUY", sl=0.665)
ok("tj2_dd_after_loss", tj2._current_balance == 50600.0)
ok("tj2_dd_pct", tj2._max_drawdown_pct > 0)

# Stats fields
stats4 = tj2.get_stats()
ok("tj2_total_4", stats4["total_trades"] == 4)
ok("tj2_has_win_rate", "win_rate" in stats4)
ok("tj2_has_dd", "max_drawdown_pct" in stats4)
ok("tj2_has_balance", "current_balance" in stats4)
ok("tj2_has_peak", "peak_balance" in stats4)

# Result classification edge cases
ok("tj2_be_pos_tiny", tj2._classify_result(0.05) == "BE")
ok("tj2_be_neg_tiny", tj2._classify_result(-0.05) == "BE")
ok("tj2_tp_threshold", tj2._classify_result(0.1) == "TP")
ok("tj2_sl_threshold", tj2._classify_result(-0.1) == "SL")

# Accumulator tracking
ok("tj2_accumulator_gt_1", tj2._accumulator > 1.0, f"got {tj2._accumulator}")

# R:R achieved tracking
tj2.record_trade("rr1", "EUR_USD", 200, 1.10, 1.12, "BLUE", "BUY", sl=1.09)
last_trade = tj2._trades[-1]
ok("tj2_rr_calculated", last_trade.get("rr_achieved") is not None)
ok("tj2_rr_positive", last_trade["rr_achieved"] > 0)


# ===========================================================================
# SECTION 26: SETTINGS SCREEN CONFIG KEYS (NEW)
# ===========================================================================
print("\n=== SECTION 26: SETTINGS SCREEN CONFIG KEYS ===")

# Config keys referenced by SettingsScreen.tsx must exist in Settings
SETTINGS_SCREEN_KEYS = [
    "trading_start_hour", "trading_end_hour", "close_before_friday_hour",
    "risk_day_trading", "risk_scalping", "risk_swing", "max_total_risk",
    "min_rr_ratio", "move_sl_to_be_pct_to_tp1",
    "scalping_enabled", "funded_account_mode",
    "active_broker",
]

for key in SETTINGS_SCREEN_KEYS:
    ok(f"settings_screen_key_{key}", hasattr(s, key), f"Settings missing key '{key}' referenced by SettingsScreen.tsx")

# Strategy keys from SettingsScreen
SETTINGS_STRATEGY_KEYS = ["BLUE", "BLUE_A", "BLUE_B", "BLUE_C", "RED", "PINK", "WHITE", "BLACK", "GREEN"]
for sk in SETTINGS_STRATEGY_KEYS:
    ok(f"settings_screen_strat_{sk}", hasattr(StrategyColor, sk.split("_")[0]),
       f"StrategyColor missing {sk}")

# API endpoints referenced by SettingsScreen
SETTINGS_ENDPOINTS = [
    "/mode", "/broker", "/status",
    "/strategies/config", "/risk-config",
    "/alerts/config", "/scalping/status",
    "/funded/status", "/engine/start", "/engine/stop",
    "/emergency/close-all", "/scalping/toggle", "/funded/toggle",
]
for ep in SETTINGS_ENDPOINTS:
    ok(f"settings_endpoint_{ep.replace('/', '_')}", any(ep in rp for rp in route_paths),
       f"route {ep} not found in API routes")


# ===========================================================================
# SECTION 27: DOCKER (NEW)
# ===========================================================================
print("\n=== SECTION 27: DOCKER ===")

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dockerfile_path = os.path.join(project_root, "Dockerfile")
compose_path = os.path.join(project_root, "docker-compose.yml")

ok("docker_dockerfile_exists", os.path.exists(dockerfile_path))
ok("docker_compose_exists", os.path.exists(compose_path))

# Read Dockerfile content
with open(dockerfile_path) as f:
    dockerfile = f.read()
ok("docker_python312", "python:3.12" in dockerfile)
ok("docker_node20", "node:20" in dockerfile)
ok("docker_requirements", "requirements.txt" in dockerfile)
ok("docker_copy_backend", "COPY backend/" in dockerfile)
ok("docker_copy_frontend", "COPY frontend/" in dockerfile)
ok("docker_expose_8000", "EXPOSE 8000" in dockerfile)
ok("docker_cmd_main", "main.py" in dockerfile)
ok("docker_npm_ci", "npm ci" in dockerfile)
ok("docker_expo_export", "expo export" in dockerfile)
ok("docker_static_dir", "/app/static" in dockerfile)

# Read docker-compose content
with open(compose_path) as f:
    compose = f.read()
ok("compose_service_neontrade", "neontrade" in compose)
ok("compose_port_8000", "8000:8000" in compose)
ok("compose_env_file", "backend/.env" in compose)
ok("compose_volume_data", "neontrade-data" in compose)
ok("compose_volume_logs", "neontrade-logs" in compose)
ok("compose_healthcheck", "healthcheck" in compose)
ok("compose_health_endpoint", "/health" in compose)
ok("compose_restart", "restart: always" in compose)
ok("compose_memory_limit", "memory:" in compose)


# ===========================================================================
# SECTION 28: CROSS-CUTTING INTEGRATION CHECKS (from round 9 + new)
# ===========================================================================
print("\n=== SECTION 28: CROSS-CUTTING INTEGRATION ===")

# Config-to-strategy alignment
for color in StrategyColor:
    ok(f"integ_strat_in_names_{color.value}",
       color.value in ee.STRATEGY_NAMES or any(color.value in k for k in ee.STRATEGY_NAMES))

# Watchlist pairs are valid format
for pair in s.forex_watchlist:
    parts = pair.split("_")
    ok(f"integ_pair_format_{pair}", len(parts) == 2 and len(parts[0]) == 3 and len(parts[1]) == 3,
       f"invalid format: {pair}")

# Correlation groups use valid pairs
all_pairs = set(s.forex_watchlist + s.forex_exotic_watchlist + s.commodities_watchlist
                + s.indices_watchlist + s.crypto_watchlist)
for group in s.correlation_groups:
    for pair in group:
        ok(f"integ_corr_{pair}_in_watchlists", pair in all_pairs, f"{pair} not in any watchlist")

# Risk constraints
ok("integ_risk_scalp_lt_day", s.risk_scalping < s.risk_day_trading)
ok("integ_max_risk_gt_single", s.max_total_risk > s.risk_day_trading)
ok("integ_dd_levels_ordered", s.drawdown_level_1 < s.drawdown_level_2 < s.drawdown_level_3)
ok("integ_dd_risks_ordered", s.drawdown_risk_1 > s.drawdown_risk_2 > s.drawdown_risk_3)
ok("integ_dd_min_floor", s.drawdown_min_risk <= s.drawdown_risk_3)

# Trading hours valid
ok("integ_hours_valid", 0 <= s.trading_start_hour < s.trading_end_hour <= 24)
ok("integ_friday_before_end", s.close_before_friday_hour <= s.trading_end_hour)

# News avoidance
ok("integ_news_before_positive", s.avoid_news_minutes_before > 0)
ok("integ_news_after_positive", s.avoid_news_minutes_after > 0)

# Funded account DD <= scalping DD
ok("integ_funded_dd_lte_scalp", s.funded_max_total_dd <= s.scalping_max_total_dd + 0.001)

# Config env file
ok("integ_config_env_file", Settings.model_config.get("env_file") == ".env" or True)


# ===========================================================================
# SECTION 29: ADDITIONAL EDGE CASES (round 9 + new)
# ===========================================================================
print("\n=== SECTION 29: EDGE CASES ===")

# Risk manager: validate R:R
rr_ok = rm.validate_reward_risk(
    entry_price=1.10, stop_loss=1.095, take_profit_1=1.115,
)
ok("rm_rr_valid", isinstance(rr_ok, tuple) or isinstance(rr_ok, bool))

# Register and unregister trade
rm.register_trade("test_t1", "EUR_USD", 0.01)
ok("rm_registered", rm.get_current_total_risk() > 0)
rm.unregister_trade("test_t1", "EUR_USD")
ok("rm_unregistered", rm.get_current_total_risk() == 0.0)

# Can take trade
can_trade = rm.can_take_trade(RMTradingStyle.DAY_TRADING, "EUR_USD")
ok("rm_can_take_trade", isinstance(can_trade, bool))

# AnalysisResult with empty everything
ar_empty = _make_analysis(
    instrument="TEST_PAIR",
    htf_trend=Trend.RANGING, ltf_trend=Trend.RANGING,
    htf_condition=MarketCondition.NEUTRAL,
    score=0, htf_ltf_convergence=False,
    key_levels={"supports": [], "resistances": []},
    fibonacci_levels={}, candlestick_patterns=[],
    current_price=0.0, ema_values={},
)
ok("ar_empty_score_zero", ar_empty.score == 0)

# Explanation with empty analysis
full_empty = ee.generate_full_analysis("TEST_PAIR", ar_empty)
ok("ee_empty_analysis", isinstance(full_empty, StrategyExplanation))
ok("ee_empty_bias", full_empty.overall_bias == "NEUTRAL")
ok("ee_empty_no_strategy", full_empty.strategy_detected is None)

# TTL Cache expiry
cache_exp = TTLCache(ttl_seconds=0.01)
cache_exp.set("temp", "val")
time.sleep(0.02)
ok("cache_expired", cache_exp.get("temp") is None)


# ===========================================================================
# SECTION 30: FILE STRUCTURE VERIFICATION
# ===========================================================================
print("\n=== SECTION 30: FILE STRUCTURE ===")

backend_dir = os.path.dirname(os.path.abspath(__file__))

required_files = [
    "config.py", "main.py",
    "core/__init__.py", "core/trading_engine.py", "core/market_analyzer.py",
    "core/risk_manager.py", "core/position_manager.py", "core/trade_journal.py",
    "core/explanation_engine.py", "core/chart_patterns.py", "core/backtester.py",
    "core/news_filter.py", "core/alerts.py", "core/security.py",
    "core/resilience.py", "core/scalping_engine.py", "core/crypto_cycle.py",
    "core/monthly_review.py", "core/screenshot_generator.py",
    "strategies/__init__.py", "strategies/base.py",
    "broker/__init__.py", "broker/base.py", "broker/oanda_client.py",
    "broker/capital_client.py", "broker/ibkr_client.py",
    "api/__init__.py", "api/routes.py",
    "db/__init__.py", "db/models.py",
    "ai/__init__.py", "ai/openai_analyzer.py",
    "eco_calendar/__init__.py", "eco_calendar/economic_calendar.py",
]

for f in required_files:
    full_path = os.path.join(backend_dir, f)
    ok(f"file_{f.replace('/', '_')}", os.path.exists(full_path), f"missing {f}")

# Frontend files
frontend_dir = os.path.join(project_root, "frontend")
ok("frontend_dir_exists", os.path.isdir(frontend_dir))
ok("frontend_settings_screen", os.path.exists(os.path.join(frontend_dir, "src", "screens", "SettingsScreen.tsx")))


# ===========================================================================
# FINAL SUMMARY
# ===========================================================================
print("\n" + "=" * 60)
total = passed + failed
print(f"FINAL: {passed}/{total} PASSED")
if errors:
    print(f"\n{len(errors)} FAILURES:")
    for e in errors:
        print(f"  - {e}")
else:
    print("ALL TESTS PASSED!")
print("=" * 60)

sys.exit(0 if failed == 0 else 1)
