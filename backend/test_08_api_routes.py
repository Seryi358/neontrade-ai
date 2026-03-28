"""TEST 8: API Routes Test"""
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
print("TEST 8: API Routes Test")
print("=" * 60)

# Import the router
from api.routes import router

# List all routes
print("\n[8.1] List all routes")
all_routes = []
for route in router.routes:
    methods = getattr(route, 'methods', set())
    path = getattr(route, 'path', '')
    name = getattr(route, 'name', '')
    endpoint = getattr(route, 'endpoint', None)
    all_routes.append({
        'path': path,
        'methods': methods,
        'name': name,
        'endpoint': endpoint,
    })
    print(f"  {methods} {path} -> {name}")

check("Routes found", len(all_routes) > 0, f"found {len(all_routes)}")

# --- Check expected routes exist ---
print("\n[8.2] Expected routes exist")
expected_paths = [
    "/status",
    "/mode",
    "/positions",
    "/analysis/{instrument}",
    "/analysis",
    "/watchlist",
    "/account",
    "/pending-setups",
    "/history",
    "/broker",
    "/candles/{instrument}",
    "/price/{instrument}",
    "/strategies/config",
    "/strategies",
    "/risk-config",
    "/risk-status",
    "/alerts/config",
    "/backtest",
    "/scalping/toggle",
    "/scalping/status",
    "/security/status",
    "/security/generate-key",
    "/funded/toggle",
    "/funded/status",
    "/journal/stats",
    "/journal/trades",
    "/watchlist/categories",
    "/watchlist/full",
    "/screenshots/{trade_id}",
    "/monthly-review",
    "/daily-activity",
    "/diagnostic",
    "/equity-curve",
    "/engine/start",
    "/engine/stop",
    "/emergency/close-all",
]

route_paths = [r['path'] for r in all_routes]
for expected in expected_paths:
    check(f"Route exists: {expected}", expected in route_paths,
          f"not found in routes")

# --- All route handlers can be found ---
print("\n[8.3] All route handlers are callable")
for route in all_routes:
    endpoint = route['endpoint']
    check(f"Handler for {route['path']} is callable",
          callable(endpoint),
          f"endpoint is {type(endpoint)}")

# --- Check that frontend API service matches ---
print("\n[8.4] Check critical routes match frontend API service")
# Frontend API methods and their expected backend paths
frontend_api_routes = {
    'getStatus': '/status',
    'getAccount': '/account',
    'getMode': '/mode',
    'getWatchlist': '/watchlist',
    'getPositions': '/positions',
    'getPendingSetups': '/pending-setups',
    'getHistory': '/history',
    'getBroker': '/broker',
    'getStrategies': '/strategies',
    'getDiagnostic': '/diagnostic',
    'getSecurityStatus': '/security/status',
    'getWatchlistCategories': '/watchlist/categories',
    'getFullWatchlist': '/watchlist/full',
}

for api_method, expected_path in frontend_api_routes.items():
    check(f"Frontend {api_method} -> {expected_path} exists",
          expected_path in route_paths)

print(f"\n{'=' * 60}")
print(f"TEST 8 RESULTS: {passed} passed, {failed} failed")
if bugs:
    print("BUGS FOUND:")
    for b in bugs:
        print(f"  - {b}")
print("=" * 60)
