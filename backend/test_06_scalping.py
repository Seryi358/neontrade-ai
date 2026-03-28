"""TEST 6: Scalping Engine Tests"""
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
print("TEST 6: Scalping Engine Tests")
print("=" * 60)

from core.scalping_engine import ScalpingAnalyzer, ScalpingData, SCALPING_TIMEFRAMES

class MockBroker:
    async def get_candles(self, instrument, granularity, count):
        return []

broker = MockBroker()
analyzer = ScalpingAnalyzer(broker)
check("ScalpingAnalyzer instantiation", analyzer is not None)

# --- M1 validation uses EMA 50 break (not MACD) ---
print("\n[6.1] M1 validation uses EMA 50 break")
import inspect
source = inspect.getsource(analyzer._validate_scalping_conditions)

# The condition 3 should use EMA 50 break, not MACD
check("M1 validation uses ema50_m1",
      "ema50_m1" in source)
check("M1 validation checks EMA 50 break (close vs EMA)",
      "close_m1" in source and "ema50_m1" in source)

# Verify the actual condition: price must be on correct side of M1 EMA 50
# For BUY: close_m1 >= ema50_m1, for SELL: close_m1 <= ema50_m1
check("M1 BUY check is price < ema50 = fail",
      'direction == "BUY" and scalp_data.close_m1 < scalp_data.ema50_m1' in source)
check("M1 SELL check is price > ema50 = fail",
      'direction == "SELL" and scalp_data.close_m1 > scalp_data.ema50_m1' in source)

# Verify M1 does NOT use MACD for execution trigger
# The function now makes MACD optional (confidence penalty, not rejection)
check("Comment confirms MACD on M5 is optional",
      "optional" in source.lower() and "macd" in source.lower())

# --- Test _validate_scalping_conditions with mock data ---
print("\n[6.2] Scalping validation with mock data")

# BUY direction, price above all EMAs + H1/M5 deceleration
data_buy = ScalpingData(instrument="EUR_USD")
data_buy.close_m15 = 1.1010
data_buy.ema50_m15 = 1.1000
data_buy.close_m1 = 1.1015
data_buy.ema50_m1 = 1.1005
data_buy.macd_m5 = {"bullish": True, "line": 0.001, "signal": 0.0005}
data_buy.volume_m5 = {"ratio": 1.2, "current": 1200, "average": 1000}
# Workshop Steps 2 & 5 require H1 and M5 deceleration (now hard requirements).
# Mock _detect_deceleration to always return a valid result for this test.
original_detect = analyzer._detect_deceleration
analyzer._detect_deceleration = lambda df, direction, lookback=5: {"adj": 5, "reason": "mock deceleration"}

result = analyzer._validate_scalping_conditions(data_buy, "BUY")
analyzer._detect_deceleration = original_detect  # restore
# Now returns Dict with "valid" key instead of bool
check("BUY with all conditions met = valid", result["valid"] is True)

# BUY direction, M1 price below EMA 50 = should fail
data_buy_fail = ScalpingData(instrument="EUR_USD")
data_buy_fail.close_m15 = 1.1010
data_buy_fail.ema50_m15 = 1.1000
data_buy_fail.close_m1 = 1.0990  # Below M1 EMA 50
data_buy_fail.ema50_m1 = 1.1005
data_buy_fail.macd_m5 = {"bullish": True}
data_buy_fail.volume_m5 = {"ratio": 1.2}

result_fail = analyzer._validate_scalping_conditions(data_buy_fail, "BUY")
check("BUY with M1 below EMA 50 = invalid", result_fail["valid"] is False)

# --- Scalping timeframe mapping ---
print("\n[6.3] Scalping timeframe mapping")
check("Direction timeframe is H1", SCALPING_TIMEFRAMES["direction"] == "H1")
check("Structure timeframe is M15", SCALPING_TIMEFRAMES["structure"] == "M15")
check("Confirmation timeframe is M5", SCALPING_TIMEFRAMES["confirmation"] == "M5")
check("Execution timeframe is M1", SCALPING_TIMEFRAMES["execution"] == "M1")

print(f"\n{'=' * 60}")
print(f"TEST 6 RESULTS: {passed} passed, {failed} failed")
if bugs:
    print("BUGS FOUND:")
    for b in bugs:
        print(f"  - {b}")
print("=" * 60)
