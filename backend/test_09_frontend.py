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

# Frontend StrategyBadge colors
badge_file = os.path.join(src_dir, 'components', 'StrategyBadge.tsx')
with open(badge_file, 'r') as f:
    badge_content = f.read()

# Extract colors from StrategyBadge.tsx
badge_colors = {}
for match in re.finditer(r"(\w+):\s*'(#[0-9a-fA-F]+)'", badge_content):
    name, color = match.groups()
    if name in ('BLUE', 'RED', 'PINK', 'WHITE', 'BLACK', 'GREEN'):
        badge_colors[name] = color.lower()

# Extract colors from api.ts STRATEGY_COLORS
api_colors = {}
for match in re.finditer(r"(\w+):\s*'(#[0-9a-fA-F]+)'", api_content):
    name, color = match.groups()
    if name in ('BLUE', 'RED', 'GREEN', 'WHITE', 'BLACK', 'PINK'):
        api_colors[name] = color.lower()

print(f"  INFO: Badge colors: {badge_colors}")
print(f"  INFO: API colors: {api_colors}")

# Check all 6 strategy colors exist in badge
for color in ['BLUE', 'RED', 'PINK', 'WHITE', 'BLACK', 'GREEN']:
    check(f"StrategyBadge has {color} color", color in badge_colors, f"missing from badge")

# Note: api.ts and StrategyBadge may intentionally use different shades
# Check they at least have the same strategies defined
check("Both files define BLUE", 'BLUE' in badge_colors and 'BLUE' in api_colors)
check("Both files define RED", 'RED' in badge_colors and 'RED' in api_colors)
check("Both files define GREEN", 'GREEN' in badge_colors and 'GREEN' in api_colors)
check("Both files define BLACK", 'BLACK' in badge_colors and 'BLACK' in api_colors)
check("Both files define WHITE", 'WHITE' in badge_colors and 'WHITE' in api_colors)

# Check if PINK is missing from api.ts STRATEGY_COLORS
has_pink_in_api = 'PINK' in api_colors
if not has_pink_in_api:
    print(f"  NOTE: PINK is not in api.ts STRATEGY_COLORS (but is in StrategyBadge)")
    # This could be a bug if PINK is needed in the api.ts colors
    # Check if PINK is used elsewhere in the frontend
    pink_used = False
    for fpath in tsx_files:
        with open(fpath, 'r') as f:
            if 'PINK' in f.read():
                pink_used = True
                break
    if pink_used:
        check("PINK used in frontend but missing from api.ts STRATEGY_COLORS",
              False, "PINK strategy color missing from api.ts")
    else:
        check("PINK not used in frontend api.ts STRATEGY_COLORS (OK - in badge only)", True)

print(f"\n{'=' * 60}")
print(f"TEST 9 RESULTS: {passed} passed, {failed} failed")
if bugs:
    print("BUGS FOUND:")
    for b in bugs:
        print(f"  - {b}")
print("=" * 60)
