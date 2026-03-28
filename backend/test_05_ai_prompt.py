"""TEST 5: AI Prompt Tests"""
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
print("TEST 5: AI Prompt Tests")
print("=" * 60)

try:
    from ai.openai_analyzer import TRADINGLAB_SYSTEM_PROMPT
    check("System prompt imported", len(TRADINGLAB_SYSTEM_PROMPT) > 100)
except ImportError:
    print("  SKIP: openai not installed — skipping AI prompt tests")
    TRADINGLAB_SYSTEM_PROMPT = None
    print(f"\n{'=' * 60}")
    print(f"TEST 5 RESULTS: 0 passed, 0 failed (skipped)")
    print("=" * 60)
    sys.exit(0)

# --- CRYPTO SPECIALIZATION section ---
print("\n[5.1] CRYPTO SPECIALIZATION section")
check("Contains 'CRYPTO SPECIALIZATION'",
      "CRYPTO SPECIALIZATION" in TRADINGLAB_SYSTEM_PROMPT)

# --- BMSB, Pi Cycle, EMA 8 weekly ---
print("\n[5.2] Key crypto indicators mentioned")
check("Mentions BMSB", "BMSB" in TRADINGLAB_SYSTEM_PROMPT)
check("Mentions Pi Cycle", "Pi Cycle" in TRADINGLAB_SYSTEM_PROMPT)
check("Mentions EMA 8 Weekly", "EMA 8 Weekly" in TRADINGLAB_SYSTEM_PROMPT or "EMA 8 weekly" in TRADINGLAB_SYSTEM_PROMPT)

# --- GREEN is the ONLY crypto strategy ---
print("\n[5.3] GREEN is ONLY crypto strategy")
check("Says GREEN is ONLY strategy for crypto",
      "GREEN is the ONLY" in TRADINGLAB_SYSTEM_PROMPT or
      "GREEN is the only" in TRADINGLAB_SYSTEM_PROMPT)

# --- Limit orders require 4 confluences ---
print("\n[5.4] Limit order requirements")
check("Limit entry requires 4 levels",
      "4 levels" in TRADINGLAB_SYSTEM_PROMPT or
      "4 levels converge" in TRADINGLAB_SYSTEM_PROMPT or
      "ONLY when 4 levels" in TRADINGLAB_SYSTEM_PROMPT)

# --- Partial profits described as optional/configurable ---
print("\n[5.5] Partial profits description")
check("Partial profits described as optional",
      "optional" in TRADINGLAB_SYSTEM_PROMPT.lower() and
      "partial" in TRADINGLAB_SYSTEM_PROMPT.lower())
check("Partial profits described as configurable",
      "configurable" in TRADINGLAB_SYSTEM_PROMPT.lower())

print(f"\n{'=' * 60}")
print(f"TEST 5 RESULTS: {passed} passed, {failed} failed")
if bugs:
    print("BUGS FOUND:")
    for b in bugs:
        print(f"  - {b}")
print("=" * 60)
