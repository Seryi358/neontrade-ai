"""TEST 7: Config Tests"""
import sys
sys.path.insert(0, '.')

passed = 0
failed = 0
bugs = []

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        print(f"  FAIL: {name} {detail}")
        bugs.append(f"{name}: {detail}")

print("=" * 60)
print("TEST 7: Config Tests")
print("=" * 60)

from config import Settings

# Create fresh settings (without env file)
settings = Settings()

# --- allow_partial_profits field ---
print("\n[7.1] allow_partial_profits field")
check("allow_partial_profits exists", hasattr(settings, 'allow_partial_profits'))
check("allow_partial_profits default is False", settings.allow_partial_profits is False)

# --- All config fields have valid defaults ---
print("\n[7.2] Key config fields and defaults")
check("active_broker default", settings.active_broker == "capital")
check("trading_style default", settings.trading_style == "day_trading")
check("risk_day_trading default 1%", settings.risk_day_trading == 0.01)
check("risk_scalping default 0.5%", settings.risk_scalping == 0.005)
check("max_total_risk default 7%", settings.max_total_risk == 0.07)
check("min_rr_ratio default", settings.min_rr_ratio == 1.5)
check("min_rr_black default", settings.min_rr_black == 2.0)
check("min_rr_green default", settings.min_rr_green == 2.0)
check("move_sl_to_be_pct_to_tp1 default 1%", settings.move_sl_to_be_pct_to_tp1 == 0.50)
check("scale_in_require_be default True", settings.scale_in_require_be is True)
check("partial_taking default False", settings.partial_taking is False)
check("sl_management_style default 'ema'", settings.sl_management_style == "ema")

# --- Trading hours ---
print("\n[7.3] Trading hours")
check("trading_start_hour default 7", settings.trading_start_hour == 7)
check("trading_end_hour default 22", settings.trading_end_hour == 22)
check("close_before_friday_hour default 20", settings.close_before_friday_hour == 20)

# --- Watchlists ---
print("\n[7.4] Watchlists")
check("forex_watchlist has entries", len(settings.forex_watchlist) > 0)
check("crypto_watchlist has entries", len(settings.crypto_watchlist) > 0)
check("indices_watchlist has entries", len(settings.indices_watchlist) > 0)
check("crypto_default_strategy is GREEN", settings.crypto_default_strategy == "GREEN")
check("active_watchlist_categories default ['forex']",
      settings.active_watchlist_categories == ["forex"])

# --- Capital allocation ---
print("\n[7.5] Capital allocation")
check("allocation_trading_pct 70%", settings.allocation_trading_pct == 0.70)
check("allocation_crypto_pct 10%", settings.allocation_crypto_pct == 0.10)
check("allocation_investment_pct 20%", settings.allocation_investment_pct == 0.20)

# --- Correlation groups ---
print("\n[7.6] Correlation groups")
check("correlation_groups has entries", len(settings.correlation_groups) > 0)
check("correlated_risk_pct default 0.75", settings.correlated_risk_pct == 0.0075)

# --- Drawdown settings ---
print("\n[7.7] Drawdown settings")
check("drawdown_method default 'fixed_1pct'", settings.drawdown_method == "fixed_1pct")
check("drawdown_min_risk default 0.25%", settings.drawdown_min_risk == 0.0025)
check("delta_enabled default False", settings.delta_enabled is False)

# --- Scalping settings ---
print("\n[7.8] Scalping settings")
check("scalping_enabled default False", settings.scalping_enabled is False)
check("scalping_max_daily_dd default 5%", settings.scalping_max_daily_dd == 0.05)

# --- Funded account ---
print("\n[7.9] Funded account settings")
check("funded_account_mode default False", settings.funded_account_mode is False)
check("funded_max_daily_dd default 5%", settings.funded_max_daily_dd == 0.05)
check("funded_no_overnight default False", settings.funded_no_overnight is False)

# --- EMAs ---
print("\n[7.10] EMA settings")
check("ema_1h default 50", settings.ema_1h == 50)
check("ema_4h default 50", settings.ema_4h == 50)
check("ema_daily default 20", settings.ema_daily == 20)
check("sma_daily default 200", settings.sma_daily == 200)

# --- Discretion ---
check("discretion_pct default 0%", settings.discretion_pct == 0.0)

print(f"\n{'=' * 60}")
print(f"TEST 7 RESULTS: {passed} passed, {failed} failed")
if bugs:
    print("BUGS FOUND:")
    for b in bugs:
        print(f"  - {b}")
print("=" * 60)
