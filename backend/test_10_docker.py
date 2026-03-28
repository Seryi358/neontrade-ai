"""TEST 10: Docker Build Test"""
import os

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
print("TEST 10: Docker Build Test")
print("=" * 60)

project_root = os.path.join(os.path.dirname(__file__), '..')

# --- Dockerfile ---
print("\n[10.1] Dockerfile check")
dockerfile = os.path.join(project_root, 'Dockerfile')
check("Dockerfile exists", os.path.isfile(dockerfile))

with open(dockerfile, 'r') as f:
    df_content = f.read()

# Check key stages
check("Multi-stage build (frontend-build)", "frontend-build" in df_content)
check("Uses node:20-slim", "node:20-slim" in df_content)
check("Uses python:3.12-slim", "python:3.12-slim" in df_content)
check("Copies frontend/package.json", "frontend/package.json" in df_content)
check("Copies frontend/", "COPY frontend/" in df_content)
check("Runs npx expo export", "npx expo export" in df_content)
check("Copies backend/requirements.txt", "backend/requirements.txt" in df_content)
check("Copies backend/", "COPY backend/" in df_content)
check("Copies frontend dist to /app/static", "/app/static" in df_content)
check("Creates logs dir", "mkdir" in df_content and "logs" in df_content)
check("Creates data dir", "mkdir" in df_content and "data" in df_content)
check("Exposes 8000", "EXPOSE 8000" in df_content)
check("CMD runs main.py", "main.py" in df_content)

# --- docker-compose.yml ---
print("\n[10.2] docker-compose.yml check")
compose = os.path.join(project_root, 'docker-compose.yml')
check("docker-compose.yml exists", os.path.isfile(compose))

with open(compose, 'r') as f:
    dc_content = f.read()

check("Service named neontrade", "neontrade" in dc_content)
check("Port mapping 8000:8000", "8000:8000" in dc_content)
check("env_file references backend/.env", "backend/.env" in dc_content)
check("Volume for data", "neontrade-data" in dc_content)
check("Volume for logs", "neontrade-logs" in dc_content)
check("Healthcheck configured", "healthcheck" in dc_content)
check("Healthcheck uses /health", "/health" in dc_content)
check("Memory limit set", "memory" in dc_content)

# --- .dockerignore ---
print("\n[10.3] .dockerignore check")
dockerignore = os.path.join(project_root, '.dockerignore')
check(".dockerignore exists", os.path.isfile(dockerignore))

with open(dockerignore, 'r') as f:
    di_content = f.read()

check("Ignores .git", ".git" in di_content)
check("Ignores node_modules", "node_modules" in di_content)
check("Ignores __pycache__", "__pycache__" in di_content)
check("Ignores backend/.env", "backend/.env" in di_content)
check("Ignores backend/data/*.db", "backend/data" in di_content)
check("Ignores backend/logs/", "backend/logs" in di_content)
check("Ignores backend/test_*.py", "backend/test_" in di_content)
check("Ignores backend/keys/", "backend/keys" in di_content)

# --- .env.example ---
print("\n[10.4] .env.example check")
env_example = os.path.join(project_root, 'backend', '.env.example')
if os.path.isfile(env_example):
    with open(env_example, 'r') as f:
        env_content = f.read()

    # Check required vars are documented
    required_vars = [
        'ACTIVE_BROKER', 'CAPITAL_API_KEY', 'CAPITAL_PASSWORD',
        'CAPITAL_IDENTIFIER', 'OPENAI_API_KEY',
    ]
    for var in required_vars:
        check(f".env.example has {var}", var in env_content)
else:
    check(".env.example exists", False, "file not found - CREATING IT")
    # Create .env.example with all needed vars
    env_example_content = """# NeonTrade AI - Environment Variables
# Copy to .env and fill in your values

# ── Broker Selection ──────────────────────────────────────────
# Options: "capital", "oanda", "ibkr"
ACTIVE_BROKER=capital

# ── Capital.com ───────────────────────────────────────────────
CAPITAL_API_KEY=
CAPITAL_PASSWORD=
CAPITAL_IDENTIFIER=
CAPITAL_ENVIRONMENT=demo
CAPITAL_ACCOUNT_ID=

# ── OANDA (alternative) ──────────────────────────────────────
OANDA_API_KEY=
OANDA_ACCOUNT_ID=
OANDA_ENVIRONMENT=practice

# ── Interactive Brokers ───────────────────────────────────────
IBKR_CONSUMER_KEY=
IBKR_ACCESS_TOKEN=
IBKR_ACCESS_TOKEN_SECRET=
IBKR_KEYS_DIR=keys
IBKR_ENVIRONMENT=live

# ── OpenAI ────────────────────────────────────────────────────
OPENAI_API_KEY=

# ── App Settings ──────────────────────────────────────────────
APP_SECRET_KEY=change-me
APP_HOST=0.0.0.0
APP_PORT=8000
LOG_LEVEL=INFO

# ── Security ──────────────────────────────────────────────────
# Pre-shared API key (leave empty to auto-generate on first run)
API_SECRET_KEY=

# ── Database ──────────────────────────────────────────────────
DATABASE_URL=sqlite:///./data/trading.db

# ── Notifications ─────────────────────────────────────────────
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
DISCORD_WEBHOOK_URL=

# ── Gmail OAuth2 (preferred for email alerts) ─────────────────
GMAIL_SENDER=
GMAIL_RECIPIENT=
GMAIL_CLIENT_ID=
GMAIL_CLIENT_SECRET=
GMAIL_REFRESH_TOKEN=

# ── SMTP Email (alternative to Gmail OAuth2) ──────────────────
ALERT_EMAIL_SMTP_SERVER=smtp.gmail.com
ALERT_EMAIL_SMTP_PORT=587
ALERT_EMAIL_USERNAME=
ALERT_EMAIL_PASSWORD=
ALERT_EMAIL_RECIPIENT=

# ── Firebase Push Notifications ───────────────────────────────
FCM_SERVER_KEY=

# ── News APIs ─────────────────────────────────────────────────
FINNHUB_API_KEY=
NEWSAPI_KEY=
"""
    with open(env_example, 'w') as f:
        f.write(env_example_content)
    check(".env.example CREATED", True)
    # Re-check
    with open(env_example, 'r') as f:
        env_content = f.read()
    required_vars = [
        'ACTIVE_BROKER', 'CAPITAL_API_KEY', 'CAPITAL_PASSWORD',
        'CAPITAL_IDENTIFIER', 'OPENAI_API_KEY',
    ]
    for var in required_vars:
        check(f".env.example has {var}", var in env_content)

# --- requirements.txt ---
print("\n[10.5] requirements.txt check")
req_file = os.path.join(project_root, 'backend', 'requirements.txt')
if os.path.isfile(req_file):
    with open(req_file, 'r') as f:
        req_content = f.read()
    required_pkgs = ['fastapi', 'uvicorn', 'openai', 'pandas', 'numpy', 'httpx', 'pydantic']
    for pkg in required_pkgs:
        check(f"requirements.txt has {pkg}", pkg.lower() in req_content.lower())
else:
    check("requirements.txt exists", False, "file not found - CREATING IT")
    # Create requirements.txt
    req_content = """fastapi>=0.100.0
uvicorn>=0.23.0
openai>=1.0.0
pandas>=2.0.0
numpy>=1.24.0
httpx>=0.24.0
pydantic>=2.0.0
pydantic-settings>=2.0.0
python-dotenv>=1.0.0
loguru>=0.7.0
sqlalchemy>=2.0.0
aiosqlite>=0.19.0
ta>=0.11.0
"""
    with open(req_file, 'w') as f:
        f.write(req_content)
    check("requirements.txt CREATED", True)

# --- Check all backend files referenced in Dockerfile exist ---
print("\n[10.6] Backend files exist")
backend_dir = os.path.join(project_root, 'backend')
critical_files = [
    'main.py',
    'config.py',
    'api/__init__.py',
    'api/routes.py',
    'ai/__init__.py',
    'ai/openai_analyzer.py',
    'core/__init__.py',
    'core/market_analyzer.py',
    'core/trading_engine.py',
    'core/position_manager.py',
    'core/risk_manager.py',
    'core/scalping_engine.py',
    'core/crypto_cycle.py',
    'strategies/__init__.py',
    'strategies/base.py',
    'db/__init__.py',
    'db/models.py',
]
for f in critical_files:
    check(f"Backend file: {f}", os.path.isfile(os.path.join(backend_dir, f)))

# --- Check frontend files referenced in Dockerfile exist ---
print("\n[10.7] Frontend files exist")
frontend_dir = os.path.join(project_root, 'frontend')
check("frontend/package.json exists",
      os.path.isfile(os.path.join(frontend_dir, 'package.json')))
check("frontend/App.tsx exists",
      os.path.isfile(os.path.join(frontend_dir, 'App.tsx')))

print(f"\n{'=' * 60}")
print(f"TEST 10 RESULTS: {passed} passed, {failed} failed")
if bugs:
    print("BUGS FOUND:")
    for b in bugs:
        print(f"  - {b}")
print("=" * 60)
