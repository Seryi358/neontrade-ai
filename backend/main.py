"""
NeonTrade AI - Main Entry Point
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
    "logs/neontrade_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="30 days",
    level="DEBUG",
)


# ── Trading Engine Instance ──────────────────────────────────────
engine = TradingEngine()

# ── Database Instance ────────────────────────────────────────────
db = None  # Initialized in lifespan


# ── WebSocket Manager ────────────────────────────────────────────
class ConnectionManager:
    """Manages WebSocket connections and broadcasts events."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WS client connected. Total: {len(self.active_connections)}")

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
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

    async def send_personal(self, websocket: WebSocket, event_type: str, data: dict):
        """Send a typed event to a specific client."""
        await websocket.send_json({"type": event_type, "data": data})


ws_manager = ConnectionManager()


# ── App Lifecycle ────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start trading engine on app startup, stop on shutdown."""
    global db
    logger.info("=" * 60)
    logger.info("  NeonTrade AI v1.0 - Starting Up")
    logger.info("=" * 60)

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

    yield

    # Shutdown
    logger.info("NeonTrade AI shutting down...")
    await engine.stop()
    engine_task.cancel()
    status_task.cancel()

    broker = engine.broker
    await broker.close()

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
            logger.debug(f"Status broadcast error: {e}")
        await asyncio.sleep(3)


# ── FastAPI App ──────────────────────────────────────────────────
app = FastAPI(
    title="NeonTrade AI",
    description="Cyberpunk AI-Powered Forex Trading System - Powered by TradingLab Strategies",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for frontend (React Native / Expo Web / Electron / Remote)
# Allow all origins since this is a private trading bot accessed via Electron
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

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
    await ws_manager.connect(websocket)

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


async def _handle_ws_command(websocket: WebSocket, data: dict):
    """Handle a command received via WebSocket."""
    action = data.get("action")

    if action == "approve":
        setup_id = data.get("setup_id")
        if setup_id and hasattr(engine, 'approve_setup'):
            success = await engine.approve_setup(setup_id)
            await ws_manager.send_personal(websocket, "setup_response", {
                "setup_id": setup_id,
                "approved": success,
            })

    elif action == "reject":
        setup_id = data.get("setup_id")
        if setup_id and hasattr(engine, 'reject_setup'):
            engine.reject_setup(setup_id)
            await ws_manager.send_personal(websocket, "setup_response", {
                "setup_id": setup_id,
                "rejected": True,
            })

    elif action == "set_mode":
        mode = data.get("mode", "AUTO").upper()
        if hasattr(engine, 'set_mode'):
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
        "broker": broker_type.value if broker_type else "oanda",
        "database": db is not None,
        "websocket_clients": len(ws_manager.active_connections),
        "version": "1.0.0",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=False,
        log_level="info",
    )
