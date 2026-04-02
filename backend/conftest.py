"""Global pytest conftest — restores risk_config.json and settings singleton
after any test that might mutate them via API calls."""
import json
import os
import copy
import pytest

# Legacy standalone scripts that call sys.exit() at module level are not
# pytest-compatible. Exclude them from collection so they can still be run
# directly (python3 <file>) but don't cause INTERNALERROR during pytest.
collect_ignore = [
    # Legacy standalone scripts that call sys.exit() at module level
    "test_final_integration.py",
    "test_round4_comprehensive.py",
    "test_round10_ultimate.py",
    # Live integration tests — require real broker credentials and network access
    "test_live_broker.py",
    "test_live_comprehensive.py",
    "test_live_e2e_simulation.py",
    "test_live_stress.py",
]


_RISK_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "risk_config.json")

# Settings keys that API tests can mutate
_RISK_KEYS = [
    "risk_day_trading", "risk_scalping", "risk_swing", "max_total_risk",
    "correlated_risk_pct", "min_rr_ratio", "min_rr_black", "min_rr_green",
    "drawdown_method", "delta_enabled", "delta_parameter", "delta_max_risk",
    "scale_in_require_be", "move_sl_to_be_pct_to_tp1",
    "active_watchlist_categories", "trading_style",
    "position_management_style", "partial_taking", "allow_partial_profits",
    "sl_management_style", "be_trigger_method",
]


@pytest.fixture(autouse=True)
def _restore_settings_and_risk_config():
    """Save and restore the settings singleton and risk_config.json around each test."""
    from config import settings

    # Snapshot current settings
    saved = {}
    for key in _RISK_KEYS:
        if hasattr(settings, key):
            val = getattr(settings, key)
            saved[key] = copy.deepcopy(val) if isinstance(val, (list, dict)) else val

    # Snapshot risk_config.json
    saved_json = None
    if os.path.exists(_RISK_CONFIG_PATH):
        try:
            with open(_RISK_CONFIG_PATH) as f:
                saved_json = json.load(f)
        except Exception:
            saved_json = {}

    yield

    # Restore settings
    for key, val in saved.items():
        try:
            setattr(settings, key, val)
        except Exception:
            pass

    # Restore risk_config.json
    if saved_json is not None:
        try:
            with open(_RISK_CONFIG_PATH, "w") as f:
                json.dump(saved_json, f, indent=2)
        except Exception:
            pass

    # Clear balance cache so tests with different mock balances don't bleed into each other
    try:
        from core.resilience import balance_cache
        balance_cache.clear()
    except Exception:
        pass
