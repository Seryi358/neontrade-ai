"""Per-instrument timeframe routing for swing_for_equities flag.

Regression coverage for the Phase 8 refactor that propagated `instrument`
through `_get_trading_style` and `_tf_ema`. With the flag on, US equities
in `equities_watchlist` route to the SWING pyramid (W direction → D pattern
→ H1 entry → M15 exec) regardless of the global `trading_style`. Forex,
crypto, etc. continue to follow the global style.
"""
import pytest
from config import settings
from strategies.base import _get_trading_style, _tf_ema


@pytest.fixture(autouse=True)
def restore_settings():
    """Snapshot+restore settings around each test so the global trading_style
    and swing_for_equities don't leak between tests."""
    original_style = settings.trading_style
    original_flag = settings.swing_for_equities
    yield
    settings.trading_style = original_style
    settings.swing_for_equities = original_flag


def test_forex_uses_global_day_trading_when_flag_off():
    settings.trading_style = "day_trading"
    settings.swing_for_equities = False
    assert _get_trading_style("EUR_USD") == "day_trading"
    assert _tf_ema("setup", 50, "EUR_USD") == "EMA_H1_50"
    assert _tf_ema("confirm", 50, "EUR_USD") == "EMA_H4_50"


def test_equity_follows_global_when_flag_off():
    settings.trading_style = "day_trading"
    settings.swing_for_equities = False
    assert _get_trading_style("JPM") == "day_trading"
    assert _tf_ema("setup", 50, "JPM") == "EMA_H1_50"


def test_equity_routes_to_swing_when_flag_on():
    settings.trading_style = "day_trading"
    settings.swing_for_equities = True
    assert "JPM" in settings.equities_watchlist
    assert _get_trading_style("JPM") == "swing"
    assert _tf_ema("setup", 50, "JPM") == "EMA_D_50"
    assert _tf_ema("confirm", 50, "JPM") == "EMA_W_50"
    assert _tf_ema("exec", 50, "JPM") == "EMA_H1_50"
    assert _tf_ema("direction", 50, "JPM") == "EMA_M_50"


def test_forex_does_not_leak_to_swing_when_flag_on():
    settings.trading_style = "day_trading"
    settings.swing_for_equities = True
    # Forex should still follow the global day_trading even with flag on.
    assert _get_trading_style("EUR_USD") == "day_trading"
    assert _tf_ema("setup", 50, "EUR_USD") == "EMA_H1_50"


def test_crypto_does_not_leak_to_swing_when_flag_on():
    settings.trading_style = "day_trading"
    settings.swing_for_equities = True
    assert _get_trading_style("BTC_USD") == "day_trading"
    assert _tf_ema("exec", 50, "BTC_USD") == "EMA_M5_50"


def test_no_instrument_falls_back_to_global():
    settings.trading_style = "swing"
    settings.swing_for_equities = True
    assert _get_trading_style() == "swing"
    assert _get_trading_style(None) == "swing"


def test_scalping_global_with_equity_override():
    settings.trading_style = "scalping"
    settings.swing_for_equities = True
    # Equity overrides global scalping → swing
    assert _get_trading_style("JPM") == "swing"
    # Forex still scalping
    assert _get_trading_style("EUR_USD") == "scalping"
    assert _tf_ema("exec", 50, "EUR_USD") == "EMA_M1_50"
