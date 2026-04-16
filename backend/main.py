"""
Atlas - Main Entry Point
FastAPI server + Trading Engine orchestration.
WebSocket with typed events for real-time frontend updates.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger
import sys
import os

from config import settings
from core.trading_engine import TradingEngine
from core.security import SecurityMiddleware, security_config
from api.routes import router as api_router


# ── Logging ──────────────────────────────────────────────────────
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | "
           "<level>{level: <8}</level> | "
           "<cyan>{name}</cyan>:<cyan>{function}</cyan> | "
           "{message}",
    level=settings.log_level,
)

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)
os.makedirs("data", exist_ok=True)

logger.add(
    "logs/atlas_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="30 days",
    level="DEBUG",
)


# ── Trading Engine Instance ──────────────────────────────────────
engine = TradingEngine()

# ── Database Instance ────────────────────────────────────────────
db = None  # Initialized in lifespan


# ── WebSocket Manager ────────────────────────────────────────────
MAX_WS_CONNECTIONS = 50


class ConnectionManager:
    """Manages WebSocket connections and broadcasts events."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    @property
    def is_full(self) -> bool:
        return len(self.active_connections) >= MAX_WS_CONNECTIONS

    async def connect(self, websocket: WebSocket) -> bool:
        """Accept and register a WebSocket. Returns False if limit reached."""
        if len(self.active_connections) >= MAX_WS_CONNECTIONS:
            await websocket.close(code=4003, reason="Connection limit reached")
            logger.warning(f"WS connection rejected: limit of {MAX_WS_CONNECTIONS} reached")
            return False
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WS client connected. Total: {len(self.active_connections)}")
        return True

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WS client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, event_type: str, data: dict):
        """Broadcast a typed event to all connected clients."""
        message = {"type": event_type, "data": data}
        disconnected = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"WS broadcast failed for a client ({e!r}), removing dead connection")
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

    async def send_personal(self, websocket: WebSocket, event_type: str, data: dict):
        """Send a typed event to a specific client."""
        try:
            await websocket.send_json({"type": event_type, "data": data})
        except Exception as e:
            logger.warning(f"WS send_personal failed ({event_type}): {e!r}")
            try:
                await websocket.close()
            except Exception:
                pass
            self.disconnect(websocket)


ws_manager = ConnectionManager()


# ── App Lifecycle ────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start trading engine on app startup, stop on shutdown."""
    global db
    logger.info("=" * 60)
    logger.info("  Atlas v3.0 - Liquid Glass - Starting Up")
    logger.info("=" * 60)

    # Startup diagnostics (mask secrets but confirm they exist)
    logger.info("Config check: broker={}, identifier={}, api_key={}, password={}",
                settings.active_broker,
                "SET" if settings.capital_identifier else "EMPTY",
                "SET" if settings.capital_api_key else "EMPTY",
                "SET" if settings.capital_password else "EMPTY")
    logger.info("Config check: openai={}, finnhub={}, gmail={}",
                "SET" if settings.openai_api_key else "EMPTY",
                "SET" if settings.finnhub_api_key else "EMPTY",
                "SET" if getattr(settings, 'gmail_refresh_token', '') else "EMPTY")

    # Initialize database
    try:
        from db.models import TradeDatabase
        db = TradeDatabase()
        await db.initialize()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning(f"Database init failed (non-critical): {e}")
        db = None

    # Inject WebSocket broadcaster into engine
    engine._ws_broadcast = ws_manager.broadcast
    engine._db = db

    # Start the trading engine in background
    engine_task = asyncio.create_task(engine.start())

    # Start WebSocket status broadcast loop
    status_task = asyncio.create_task(_status_broadcast_loop())

    # Start periodic cleanup (rate limiter + old DB data)
    cleanup_task = asyncio.create_task(_periodic_cleanup())

    yield

    # Shutdown — cancel tasks and await them to prevent CancelledError warnings
    logger.info("Atlas shutting down...")
    await engine.stop()
    engine_task.cancel()
    status_task.cancel()
    cleanup_task.cancel()
    for task in (engine_task, status_task, cleanup_task):
        try:
            await task
        except asyncio.CancelledError:
            pass

    try:
        broker = engine.broker
        if broker:
            await broker.close()
    except Exception as e:
        logger.warning(f"Error closing broker: {e}")

    if db:
        await db.close()

    logger.info("Shutdown complete")


async def _status_broadcast_loop():
    """Periodically broadcast engine status to all WebSocket clients."""
    while True:
        try:
            if ws_manager.active_connections:
                status = engine.get_status()
                await ws_manager.broadcast("engine_status", status)
        except Exception as e:
            logger.warning(f"Status broadcast error: {e}")
        await asyncio.sleep(3)


_last_db_cleanup_date: str = ""


async def _periodic_cleanup():
    """Periodic cleanup of rate limiter and old data."""
    global _last_db_cleanup_date
    while True:
        await asyncio.sleep(300)  # Every 5 minutes
        try:
            from core.security import rate_limiter
            rate_limiter.cleanup()
        except Exception as e:
            logger.warning(f"Rate limiter cleanup failed: {e!r}")

        # DB retention cleanup — once per day
        try:
            from datetime import datetime, timezone as tz
            today = datetime.now(tz.utc).strftime("%Y-%m-%d")
            if db is not None and today != _last_db_cleanup_date:
                await db.cleanup_old_data(days=90)
                _last_db_cleanup_date = today
                logger.info("DB retention cleanup completed (90-day policy)")
        except Exception as e:
            logger.warning(f"DB cleanup error: {e}")


# ── FastAPI App ──────────────────────────────────────────────────
app = FastAPI(
    title="Atlas",
    description="AI-Powered Trading System - TradingLab Strategies",
    version="3.0.0",
    lifespan=lifespan,
)

# CORS for frontend (React Native / Expo Web / Electron / Remote)
# Allow same-origin (static frontend served by this backend) + localhost dev
# Also allow all origins for EasyPanel deploys where the URL varies
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow any origin (API key auth handles security)
    allow_credentials=False,  # Using X-API-Key header, not cookies
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)

# Security middleware: API key auth, rate limiting, IP whitelist, headers
app.add_middleware(SecurityMiddleware, security_config=security_config)

# API routes
app.include_router(api_router, prefix="/api/v1")


# ── WebSocket ────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time trading updates.

    Event types sent to clients:
    - engine_status: Periodic engine status (every 3s)
    - new_setup: A new trading setup detected (Manual mode)
    - trade_executed: A trade was executed
    - trade_closed: A trade was closed
    - position_update: SL/TP moved, phase changed
    - analysis_update: New analysis completed for an instrument
    - alert: Important alerts (risk limit, friday close, etc.)

    Commands from clients:
    - {"action": "approve", "setup_id": "..."}
    - {"action": "reject", "setup_id": "..."}
    - {"action": "set_mode", "mode": "AUTO"|"MANUAL"}
    - {"action": "subscribe", "instruments": ["EUR_USD", ...]}
    """
    # Atomic check-and-accept to prevent TOCTOU race on connection limit
    if not await ws_manager.connect(websocket):
        return

    # BUG-08 fix: authenticate via first message instead of URL query param
    # (query params leak into logs, browser history, and Referer headers)
    if security_config.auth_enabled and security_config.api_keys:
        # Also accept legacy query param for backward compat (deprecate later)
        api_key = websocket.query_params.get("api_key", "")
        if not api_key:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=10)
                auth_data = json.loads(raw)
                if auth_data.get("action") == "auth":
                    api_key = auth_data.get("api_key", "")
            except (asyncio.TimeoutError, json.JSONDecodeError, Exception):
                pass
        if not security_config.validate_key(api_key):
            await ws_manager.send_personal(websocket, "error", {"message": "Authentication required"})
            await websocket.close(code=4001, reason="Invalid API key")
            ws_manager.disconnect(websocket)
            return

    try:
        # Send initial status
        status = engine.get_status()
        await ws_manager.send_personal(websocket, "engine_status", status)

        # Listen for commands from client
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                data = json.loads(raw)
                await _handle_ws_command(websocket, data)
            except asyncio.TimeoutError:
                # Send heartbeat
                await ws_manager.send_personal(websocket, "heartbeat", {"ts": "ok"})
            except json.JSONDecodeError:
                await ws_manager.send_personal(
                    websocket, "error", {"message": "Invalid JSON"}
                )
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)
        try:
            await websocket.close(code=1011, reason="Internal error")
        except Exception as e:
            logger.debug(f"WS close after error failed: {e!r}")


async def _handle_ws_command(websocket: WebSocket, data: dict):
    """Handle a command received via WebSocket."""
    action = data.get("action")

    if action == "approve":
        setup_id = data.get("setup_id")
        if setup_id and hasattr(engine, 'approve_setup'):
            try:
                success = await engine.approve_setup(setup_id)
                await ws_manager.send_personal(websocket, "setup_response", {
                    "setup_id": setup_id,
                    "approved": success,
                })
            except Exception as e:
                logger.error(f"WS approve_setup failed for {setup_id}: {e}")
                await ws_manager.send_personal(websocket, "error", {
                    "message": f"Approve failed: {e}",
                })

    elif action == "reject":
        setup_id = data.get("setup_id")
        if setup_id and hasattr(engine, 'reject_setup'):
            try:
                engine.reject_setup(setup_id)
                await ws_manager.send_personal(websocket, "setup_response", {
                    "setup_id": setup_id,
                    "rejected": True,
                })
            except Exception as e:
                logger.error(f"WS reject_setup failed for {setup_id}: {e}")
                await ws_manager.send_personal(websocket, "error", {
                    "message": f"Reject failed: {e}",
                })

    elif action == "set_mode":
        mode = data.get("mode", "AUTO").upper()
        if mode not in ("AUTO", "MANUAL"):
            await ws_manager.send_personal(websocket, "error", {
                "message": f"Invalid mode: {mode}. Must be AUTO or MANUAL.",
            })
        elif hasattr(engine, 'set_mode'):
            engine.set_mode(mode)
            await ws_manager.broadcast("mode_changed", {"mode": mode})

    elif action == "subscribe":
        # Client wants updates for specific instruments
        instruments = data.get("instruments", [])
        await ws_manager.send_personal(websocket, "subscribed", {
            "instruments": instruments,
        })

    else:
        await ws_manager.send_personal(websocket, "error", {
            "message": f"Unknown action: {action}",
        })


# ── Health Check ─────────────────────────────────────────────────
@app.get("/health")
async def health():
    mode = getattr(engine, 'mode', None)
    broker = engine.broker
    broker_type = getattr(broker, 'broker_type', None)
    return {
        "status": "online",
        "engine_running": engine._running,
        "mode": mode.value if mode else "AUTO",
        "broker": broker_type.value if broker_type else "capital",
        "database": db is not None,
        "websocket_clients": len(ws_manager.active_connections),
        "version": "1.0.0",
    }


# ── Serve Frontend (Expo Web static build) ──────────────────────
# In Docker the frontend is at /app/static. Locally it's at ../frontend/dist.
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.isdir(_static_dir):
    _static_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

if os.path.isdir(_static_dir):
    from fastapi.responses import HTMLResponse, FileResponse

    # Read index.html once and inject API key for auto-auth
    _index_html_path = os.path.join(_static_dir, "index.html")
    _index_html_raw = ""
    if os.path.isfile(_index_html_path):
        with open(_index_html_path, "r") as f:
            _index_html_raw = f.read()

    def _get_index_html() -> str:
        """Return index.html with auto-injected API key for same-origin auth.
        Key is base64-encoded to avoid plaintext exposure in HTML source."""
        import base64
        api_key = settings.api_secret_key or ""
        if api_key:
            encoded = base64.b64encode(api_key.encode()).decode()
            injection = f'<script>window.__ATLAS_API_KEY__=atob("{encoded}");</script>'
        else:
            injection = ""
        return _index_html_raw.replace("</head>", f"{injection}</head>")

    # Serve static assets (JS, CSS, fonts, images)
    _expo_dir = os.path.join(_static_dir, "_expo")
    _assets_dir = os.path.join(_static_dir, "assets")
    if os.path.isdir(_expo_dir):
        app.mount("/_expo", StaticFiles(directory=_expo_dir), name="expo_static")
    if os.path.isdir(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="frontend_assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve the SPA index.html for any non-API route (catch-all)."""
        # Security: prevent path traversal by resolving and validating the path
        if full_path:
            file_path = os.path.realpath(os.path.join(_static_dir, full_path))
            static_real = os.path.realpath(_static_dir)
            # Ensure resolved path is within the static directory
            if file_path.startswith(static_real + os.sep) and os.path.isfile(file_path):
                return FileResponse(file_path)
        # Otherwise serve index.html with injected API key
        return HTMLResponse(_get_index_html())

    logger.info(f"Frontend served from: {_static_dir}")
else:
    logger.warning("No frontend build found — API-only mode")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=False,
        log_level="info",
    )
