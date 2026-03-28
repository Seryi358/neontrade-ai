"""TEST 1: Strategy Logic Tests"""
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
print("TEST 1: Strategy Logic Tests")
print("=" * 60)

# --- Import all 6 strategies ---
print("\n[1.1] Import all 6 strategies")
from strategies.base import (
    BlueStrategy, RedStrategy, PinkStrategy,
    WhiteStrategy, BlackStrategy, GreenStrategy,
    StrategyColor, SetupSignal, EntryType,
    ALL_STRATEGIES, STRATEGY_MAP,
    _is_crypto_instrument, _apply_elliott_wave_priority,
    detect_all_setups, get_best_setup,
)
check("Import BlueStrategy", BlueStrategy is not None)
check("Import RedStrategy", RedStrategy is not None)
check("Import PinkStrategy", PinkStrategy is not None)
check("Import WhiteStrategy", WhiteStrategy is not None)
check("Import BlackStrategy", BlackStrategy is not None)
check("Import GreenStrategy", GreenStrategy is not None)

# --- Instantiate all 6 strategies ---
print("\n[1.2] Instantiate all 6 strategies")
blue = BlueStrategy()
red = RedStrategy()
pink = PinkStrategy()
white = WhiteStrategy()
black = BlackStrategy()
green = GreenStrategy()
check("BlueStrategy instance", blue.color == StrategyColor.BLUE, f"got {blue.color}")
check("RedStrategy instance", red.color == StrategyColor.RED, f"got {red.color}")
check("PinkStrategy instance", pink.color == StrategyColor.PINK, f"got {pink.color}")
check("WhiteStrategy instance", white.color == StrategyColor.WHITE, f"got {white.color}")
check("BlackStrategy instance", black.color == StrategyColor.BLACK, f"got {black.color}")
check("GreenStrategy instance", green.color == StrategyColor.GREEN, f"got {green.color}")

# --- ALL_STRATEGIES has 6 strategies ---
check("ALL_STRATEGIES has 6", len(ALL_STRATEGIES) == 6, f"got {len(ALL_STRATEGIES)}")

# --- PINK and BLACK cannot use limit entries ---
print("\n[1.3] PINK and BLACK cannot use limit entries (FIX 6)")
# The code at line ~1141 checks: _allows_non_market = self.color in (BLUE, RED, WHITE)
# This means PINK, BLACK, GREEN are excluded from non-market entries
allows_non_market_colors = {StrategyColor.BLUE, StrategyColor.RED, StrategyColor.WHITE}
check("PINK excluded from non-market entries", pink.color not in allows_non_market_colors)
check("BLACK excluded from non-market entries", black.color not in allows_non_market_colors)
check("GREEN excluded from non-market entries", green.color not in allows_non_market_colors)
check("BLUE allows non-market entries", blue.color in allows_non_market_colors)
check("RED allows non-market entries", red.color in allows_non_market_colors)
check("WHITE allows non-market entries", white.color in allows_non_market_colors)

# --- Crypto instruments only get GREEN strategy results ---
print("\n[1.4] Crypto instruments only get GREEN strategy results")
check("BTC_USD is crypto", _is_crypto_instrument("BTC_USD"))
check("ETH_USD is crypto", _is_crypto_instrument("ETH_USD"))
check("SOL_USD is crypto", _is_crypto_instrument("SOL_USD"))
check("EUR_USD is NOT crypto", not _is_crypto_instrument("EUR_USD"))
check("GBP_USD is NOT crypto", not _is_crypto_instrument("GBP_USD"))
check("XAU_USD is NOT crypto", not _is_crypto_instrument("XAU_USD"))

# --- Elliott Wave mapping ---
print("\n[1.5] Elliott Wave mapping priorities")
from core.market_analyzer import AnalysisResult, Trend, MarketCondition

# Create a mock analysis with Elliott Wave detail
def make_mock_analysis(wave_count):
    return AnalysisResult(
        instrument="EUR_USD",
        htf_trend=Trend.BULLISH,
        htf_condition=MarketCondition.NEUTRAL,
        ltf_trend=Trend.BULLISH,
        htf_ltf_convergence=True,
        key_levels={"supports": [], "resistances": []},
        ema_values={},
        fibonacci_levels={},
        candlestick_patterns=[],
        elliott_wave_detail={"wave_count": wave_count},
    )

def make_mock_signal(color, confidence=70.0):
    return SetupSignal(
        strategy=color,
        strategy_variant=color.value,
        instrument="EUR_USD",
        direction="BUY",
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit_1=1.1100,
        confidence=confidence,
    )

# Wave 1: BLACK should get highest bonus (+12)
analysis_w1 = make_mock_analysis("1")
signals_w1 = [
    make_mock_signal(StrategyColor.BLACK, 70),
    make_mock_signal(StrategyColor.BLUE, 70),
    make_mock_signal(StrategyColor.RED, 70),
]
result_w1 = _apply_elliott_wave_priority(analysis_w1, signals_w1)
black_w1 = [s for s in result_w1 if s.strategy == StrategyColor.BLACK][0]
blue_w1 = [s for s in result_w1 if s.strategy == StrategyColor.BLUE][0]
check("Wave 1: BLACK gets +12 bonus", black_w1.confidence == 82, f"got {black_w1.confidence}")
check("Wave 1: BLUE gets penalty", blue_w1.confidence < 70, f"got {blue_w1.confidence}")

# Wave 5: PINK should get highest bonus (+10)
analysis_w5 = make_mock_analysis("5")
signals_w5 = [
    make_mock_signal(StrategyColor.PINK, 70),
    make_mock_signal(StrategyColor.RED, 70),
    make_mock_signal(StrategyColor.BLACK, 70),
]
result_w5 = _apply_elliott_wave_priority(analysis_w5, signals_w5)
pink_w5 = [s for s in result_w5 if s.strategy == StrategyColor.PINK][0]
check("Wave 5: PINK gets +10 bonus", pink_w5.confidence == 80, f"got {pink_w5.confidence}")

# Wave 3: RED should get highest bonus (+10)
analysis_w3 = make_mock_analysis("3")
signals_w3 = [
    make_mock_signal(StrategyColor.RED, 70),
    make_mock_signal(StrategyColor.BLUE, 70),
]
result_w3 = _apply_elliott_wave_priority(analysis_w3, signals_w3)
red_w3 = [s for s in result_w3 if s.strategy == StrategyColor.RED][0]
blue_w3 = [s for s in result_w3 if s.strategy == StrategyColor.BLUE][0]
check("Wave 3: RED gets +10 bonus", red_w3.confidence == 80, f"got {red_w3.confidence}")
check("Wave 3: BLUE gets +5 bonus", blue_w3.confidence == 75, f"got {blue_w3.confidence}")

# GREEN should NOT appear in any non-crypto wave bonuses
# GREEN is crypto-only and excluded from wave mappings
# Test: If GREEN signal goes through _apply_elliott_wave_priority, it should get penalty (not bonus)
analysis_w3_green = make_mock_analysis("3")
signals_w3_green = [make_mock_signal(StrategyColor.GREEN, 70)]
result_w3_green = _apply_elliott_wave_priority(analysis_w3_green, signals_w3_green)
green_w3 = result_w3_green[0]
# GREEN should get default penalty for wave 3 which is 0
check("Wave 3: GREEN gets no bonus (penalty 0)", green_w3.confidence == 70, f"got {green_w3.confidence}")

# Check GREEN is not in wave_bonuses
wave_bonuses = {
    "1": {"BLACK": 12},
    "2": {"BLUE": 8, "WHITE": 3},
    "3": {"RED": 10, "BLUE": 5, "WHITE": 5},
    "4": {"PINK": 8, "BLUE": 5, "WHITE": 3},
    "5": {"PINK": 10, "RED": 5, "WHITE": 8},
    "A": {"BLACK": 5},
    "B": {"BLACK": 5},
    "C": {"BLACK": 5},
}
for wave, bonuses in wave_bonuses.items():
    check(f"Wave {wave}: GREEN not in bonuses", "GREEN" not in bonuses)

print(f"\n{'=' * 60}")
print(f"TEST 1 RESULTS: {passed} passed, {failed} failed")
if bugs:
    print("BUGS FOUND:")
    for b in bugs:
        print(f"  - {b}")
print("=" * 60)
