"""TEST 3: Position Manager Tests"""
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
print("TEST 3: Position Manager Tests")
print("=" * 60)

from core.position_manager import (
    PositionManager, ManagedPosition, ManagementStyle,
    TradingStyle, PositionPhase, _EMA_TIMEFRAME_GRID,
)

# --- ManagementStyle.PRICE_ACTION exists ---
print("\n[3.1] ManagementStyle.PRICE_ACTION exists")
check("PRICE_ACTION in ManagementStyle", hasattr(ManagementStyle, 'PRICE_ACTION'))
check("PRICE_ACTION value", ManagementStyle.PRICE_ACTION.value == "price_action")

# --- All management styles ---
check("LP style exists", ManagementStyle.LP.value == "lp")
check("CP style exists", ManagementStyle.CP.value == "cp")
check("CPA style exists", ManagementStyle.CPA.value == "cpa")

# --- Create PositionManager ---
print("\n[3.2] Create PositionManager")

class MockBroker:
    async def modify_trade_sl(self, trade_id, new_sl):
        pass
    async def close_trade(self, trade_id, units=None):
        pass

broker = MockBroker()
pm = PositionManager(broker, management_style="lp", trading_style="day_trading")
check("PositionManager LP instantiation", pm is not None)
check("PM management style is LP", pm.management_style == ManagementStyle.LP)
check("PM trading style is DAY_TRADING", pm.trading_style == TradingStyle.DAY_TRADING)

# --- PRICE_ACTION style ---
pm_pa = PositionManager(broker, management_style="price_action", trading_style="swing")
check("PM PRICE_ACTION instantiation", pm_pa.management_style == ManagementStyle.PRICE_ACTION)
check("PM PRICE_ACTION base_ema_key is None", pm_pa._base_ema_key is None)
check("PM PRICE_ACTION has CPA ema key", pm_pa._cpa_ema_key is not None)

# --- Partial profit configuration ---
print("\n[3.3] Partial profit configuration")
pm_partial = PositionManager(broker, allow_partial_profits=True)
check("allow_partial_profits=True", pm_partial.allow_partial_profits is True)
pm_no_partial = PositionManager(broker, allow_partial_profits=False)
check("allow_partial_profits=False (default)", pm_no_partial.allow_partial_profits is False)
pm_default = PositionManager(broker)
check("allow_partial_profits default is False", pm_default.allow_partial_profits is False)

# --- All management style mappings are valid ---
print("\n[3.4] EMA timeframe grid mappings")
expected_keys = [
    (ManagementStyle.LP, TradingStyle.SWING),
    (ManagementStyle.LP, TradingStyle.DAY_TRADING),
    (ManagementStyle.LP, TradingStyle.SCALPING),
    (ManagementStyle.CP, TradingStyle.SWING),
    (ManagementStyle.CP, TradingStyle.DAY_TRADING),
    (ManagementStyle.CP, TradingStyle.SCALPING),
    (ManagementStyle.CPA, TradingStyle.SWING),
    (ManagementStyle.CPA, TradingStyle.DAY_TRADING),
    (ManagementStyle.CPA, TradingStyle.SCALPING),
]
for key in expected_keys:
    check(f"EMA grid has {key[0].value}/{key[1].value}",
          key in _EMA_TIMEFRAME_GRID,
          f"missing from grid")

# All values should be non-empty EMA key strings
for key, val in _EMA_TIMEFRAME_GRID.items():
    check(f"EMA grid value for {key[0].value}/{key[1].value} is valid string",
          isinstance(val, str) and val.startswith("EMA_"),
          f"got {val}")

# --- Test all style combinations can create PositionManager ---
print("\n[3.5] All style combinations instantiate correctly")
for ms in ['lp', 'cp']:
    for ts in ['scalping', 'day_trading', 'swing']:
        try:
            pm_test = PositionManager(broker, management_style=ms, trading_style=ts)
            check(f"PM {ms}/{ts} OK", pm_test._base_ema_key is not None)
        except Exception as e:
            check(f"PM {ms}/{ts} OK", False, str(e))

# price_action style
for ts in ['scalping', 'day_trading', 'swing']:
    try:
        pm_test = PositionManager(broker, management_style="price_action", trading_style=ts)
        check(f"PM price_action/{ts} OK", pm_test._base_ema_key is None)
    except Exception as e:
        check(f"PM price_action/{ts} OK", False, str(e))

# --- ManagedPosition creation ---
print("\n[3.6] ManagedPosition dataclass")
pos = ManagedPosition(
    trade_id="test-001",
    instrument="EUR_USD",
    direction="BUY",
    entry_price=1.1000,
    original_sl=1.0950,
    current_sl=1.0950,
    take_profit_1=1.1100,
)
check("ManagedPosition created", pos.trade_id == "test-001")
check("ManagedPosition default phase is INITIAL", pos.phase == PositionPhase.INITIAL)
check("ManagedPosition has units field", hasattr(pos, 'units'))

# --- Track position ---
pm.track_position(pos)
check("Position tracked", "test-001" in pm.positions)

print(f"\n{'=' * 60}")
print(f"TEST 3 RESULTS: {passed} passed, {failed} failed")
if bugs:
    print("BUGS FOUND:")
    for b in bugs:
        print(f"  - {b}")
print("=" * 60)
