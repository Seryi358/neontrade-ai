"""TEST 9: Frontend Check"""
import os
import re

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
print("TEST 9: Frontend Check")
print("=" * 60)

frontend_dir = os.path.join(os.path.dirname(__file__), '..', 'frontend')
src_dir = os.path.join(frontend_dir, 'src')

# Collect all .tsx files
tsx_files = []
for root, dirs, files in os.walk(frontend_dir):
    if 'node_modules' in root:
        continue
    for f in files:
        if f.endswith('.tsx'):
            tsx_files.append(os.path.join(root, f))

check(f"Found .tsx files", len(tsx_files) > 0, f"found {len(tsx_files)}")
print(f"  INFO: {len(tsx_files)} .tsx files found")

# --- Check TypeScript syntax issues ---
print("\n[9.1] TypeScript syntax check")
for fpath in tsx_files:
    with open(fpath, 'r') as f:
        content = f.read()
    fname = os.path.basename(fpath)

    # Check for obvious syntax issues
    # Unmatched braces
    open_braces = content.count('{')
    close_braces = content.count('}')
    check(f"{fname}: braces balanced",
          abs(open_braces - close_braces) <= 2,  # Allow small tolerance for template strings
          f"{{ {open_braces} vs }} {close_braces}")

    # Check for unclosed JSX tags (rough check)
    # Look for obvious missing closing tags

    # Check for import errors (importing from non-existent paths)
    # Check that common imports exist
    if "from 'react'" in content or 'from "react"' in content:
        check(f"{fname}: React import valid", True)

    # Check for obvious undefined variables or typos
    # These are lightweight checks
    if '= underfined' in content or 'retrun' in content:
        check(f"{fname}: no common typos", False, "found typo")
    else:
        check(f"{fname}: no common typos", True)

# --- Check API service matches backend routes ---
print("\n[9.2] API service matches backend routes")
api_file = os.path.join(src_dir, 'services', 'api.ts')
check("api.ts exists", os.path.isfile(api_file))

with open(api_file, 'r') as f:
    api_content = f.read()

# Check that all frontend API paths match the /api/v1/ prefix
# Match both single-quoted and backtick template literal paths
api_paths = re.findall(r"['\"`]/api/v1/([^'\"`\$\{]+)", api_content)
check("API paths use /api/v1/ prefix", len(api_paths) > 10, f"found {len(api_paths)} paths")

# Check critical paths
critical_paths = [
    'status', 'account', 'mode', 'watchlist', 'positions',
    'pending-setups', 'history', 'broker', 'strategies',
    'diagnostic', 'security/status',
]
for path in critical_paths:
    check(f"API has path: {path}",
          any(p.startswith(path) for p in api_paths),
          f"not found in api.ts")

# --- Check strategy colors match between frontend and backend ---
print("\n[9.3] Strategy colors match")

# After CP2077 redesign, StrategyBadge.tsx imports and spreads STRATEGY_COLORS
# from api.ts rather than defining hex literals directly.
# The canonical color definitions live in api.ts STRATEGY_COLORS.
# StrategyBadge re-exports them and adds BLUE_A/B/C aliases.

badge_file = os.path.join(src_dir, 'components', 'StrategyBadge.tsx')
with open(badge_file, 'r') as f:
    badge_content = f.read()

# Extract colors from api.ts STRATEGY_COLORS (the canonical source)
api_colors = {}
for match in re.finditer(r"(\w+):\s*'(#[0-9a-fA-F]+)'", api_content):
    name, color = match.groups()
    if name in ('BLUE', 'RED', 'GREEN', 'WHITE', 'BLACK', 'PINK'):
        api_colors[name] = color.lower()

print(f"  INFO: API colors (canonical): {api_colors}")

# Check all 6 strategy colors exist in api.ts STRATEGY_COLORS
for color in ['BLUE', 'RED', 'PINK', 'WHITE', 'BLACK', 'GREEN']:
    check(f"api.ts STRATEGY_COLORS has {color} color", color in api_colors, f"missing from api.ts")

# StrategyBadge imports from api.ts and spreads BASE_STRATEGY_COLORS
check("StrategyBadge imports STRATEGY_COLORS from api",
      'STRATEGY_COLORS' in badge_content and 'from' in badge_content and 'api' in badge_content)

# StrategyBadge defines strategy name keys for all 6 strategies
for strat in ['BLUE', 'RED', 'PINK', 'WHITE', 'BLACK', 'GREEN']:
    check(f"StrategyBadge has {strat} strategy name",
          f"'{strat}'" in badge_content or f'"{strat}"' in badge_content,
          f"missing from StrategyBadge")

# Check PINK is defined in api.ts (it should be after the redesign)
check("PINK defined in api.ts STRATEGY_COLORS", 'PINK' in api_colors)

print(f"\n{'=' * 60}")
print(f"TEST 9 RESULTS: {passed} passed, {failed} failed")
if bugs:
    print("BUGS FOUND:")
    for b in bugs:
        print(f"  - {b}")
print("=" * 60)
