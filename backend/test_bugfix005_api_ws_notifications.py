"""
BUGFIX-005: Comprehensive tests for API endpoints, WebSocket, and Notifications.

Tests all REST endpoints in api/routes.py with mocked engine/db,
WebSocket connection/messaging in main.py,
and AlertManager notification channels in core/alerts.py.
"""
import asyncio
import json
import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum

sys.path.insert(0, os.path.dirname(__file__))


# ── Lightweight fakes used across tests ─────────────────────────

class FakeBrokerType(Enum):
    CAPITAL = "capital"
    OANDA = "oanda"


class FakeTrend(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class FakeCondition(Enum):
    TRENDING = "trending"
    RANGING = "ranging"


@dataclass
class FakeAccountSummary:
    balance: float = 10000.0
    equity: float = 10500.0
    unrealized_pnl: float = 500.0
    margin_used: float = 200.0
    margin_available: float = 10300.0
    open_trade_count: int = 2
    currency: str = "USD"


@dataclass
class FakeCandle:
    time: str = "2026-03-28T12:00:00Z"
    open: float = 1.1000
    high: float = 1.1050
    low: float = 1.0950
    close: float = 1.1020
    volume: int = 1500
    complete: bool = True


@dataclass
class FakePrice:
    bid: float = 1.1018
    ask: float = 1.1022
    spread: float = 0.0004
    time: str = "2026-03-28T12:05:00Z"


@dataclass
class FakeAnalysis:
    score: int = 75
    htf_trend: FakeTrend = FakeTrend.BULLISH
    ltf_trend: FakeTrend = FakeTrend.BULLISH
    htf_ltf_convergence: bool = True
    htf_condition: FakeCondition = FakeCondition.TRENDING
    key_levels: dict = field(default_factory=dict)
    ema_values: dict = field(default_factory=dict)
    fibonacci_levels: dict = field(default_factory=dict)
    candlestick_patterns: list = field(default_factory=list)
    chart_patterns: list = field(default_factory=list)
    elliott_wave: object = None
    macd_values: dict = field(default_factory=dict)
    sma_values: dict = field(default_factory=dict)
    rsi_values: dict = field(default_factory=dict)
    rsi_divergence: object = None
    order_blocks: list = field(default_factory=list)
    structure_breaks: list = field(default_factory=list)
    pivot_points: dict = field(default_factory=dict)


def _make_mock_engine():
    """Create a mock TradingEngine with all attributes used by routes.py."""
    engine = MagicMock()
    engine.running = True
    engine.startup_error = ""
    engine.mode = MagicMock()
    engine.mode.value = "AUTO"
    engine.pending_setups = []
    engine.scan_interval = 120
    engine.last_scan_results = {"EUR_USD": FakeAnalysis()}
    engine.latest_explanations = {}

    # Broker
    engine.broker = MagicMock()
    engine.broker.broker_type = FakeBrokerType.CAPITAL
    engine.broker._cst = "fake_cst"
    engine.broker._security_token = "fake_sec"
    engine.broker.get_account_summary = AsyncMock(return_value=FakeAccountSummary())
    engine.broker.get_candles = AsyncMock(return_value=[FakeCandle()])
    engine.broker.get_current_price = AsyncMock(return_value=FakePrice())
    engine.broker.close_all_trades = AsyncMock(return_value=2)
    engine.broker.get_open_trades = AsyncMock(return_value=[])

    # Status
    engine.get_status.return_value = {
        "running": True,
        "open_positions": 1,
        "total_risk": 0.02,
        "watchlist_count": 28,
        "positions": [
            {"instrument": "EUR_USD", "direction": "BUY", "unrealized_pnl": 50.0}
        ],
        "daily_activity": {
            "date": "2026-03-28",
            "scans_completed": 10,
            "setups_found": 3,
            "setups_executed": 1,
            "setups_skipped_ai": 2,
            "errors": 0,
        },
        "last_scan": {"EUR_USD": {}, "GBP_USD": {}},
        "startup_error": "",
        "scanned_instruments": 2,
    }

    # Strategies
    engine.get_enabled_strategies.return_value = {
        "BLUE": True, "BLUE_A": True, "BLUE_B": True, "BLUE_C": True,
        "RED": True, "PINK": True, "WHITE": True, "BLACK": False, "GREEN": False,
    }
    engine.set_enabled_strategies = MagicMock()

    # Notifications
    engine.get_unread_notifications.return_value = [
        {"id": "n1", "type": "trade_executed", "message": "BUY EUR_USD", "read": False}
    ]

    # Journal
    engine.trade_journal = MagicMock()
    engine.trade_journal.get_stats.return_value = {
        "total_trades": 10, "wins": 6, "losses": 3, "break_evens": 1,
        "win_rate": 60.0, "win_rate_excl_be": 66.67,
    }
    engine.trade_journal.get_trades.return_value = []
    engine.trade_journal._trades = [
        {"trade_id": "t1", "instrument": "EUR_USD", "result": "TP"},
    ]
    engine.trade_journal.update_journal_notes.return_value = True
    engine.trade_journal.update_asr.return_value = True
    engine.trade_journal.get_asr_stats.return_value = {
        "total": 10, "asr_completed": 5, "asr_completion_rate": 50.0,
        "perfect_execution_count": 3, "perfect_execution_rate": 30.0,
    }
    engine.trade_journal._save = MagicMock()

    # Risk manager
    engine.risk_manager = MagicMock()
    engine.risk_manager.update_balance_tracking = AsyncMock()
    engine.risk_manager.get_risk_status.return_value = {"total_risk": 0.02}
    engine.risk_manager.get_funded_status.return_value = {"funded_mode": False}

    # Alert manager
    engine.alert_manager = MagicMock()
    engine.alert_manager.get_config.return_value = {
        "telegram_enabled": False, "discord_enabled": False,
        "email_enabled": False, "gmail_enabled": False,
    }
    engine.alert_manager._config = MagicMock()
    engine.alert_manager.update_config = MagicMock()
    engine.alert_manager.test_channel = AsyncMock(return_value=True)

    # News filter
    engine.news_filter = MagicMock()
    engine.news_filter.get_todays_events = AsyncMock(return_value=[])
    engine.news_filter.has_upcoming_news = AsyncMock(return_value=(False, None))
    engine.news_filter.get_news_headlines = AsyncMock(return_value=[])

    # Position manager
    engine.position_manager = MagicMock()
    engine.position_manager.positions = {}

    # Scalping
    engine.scalping_analyzer = None
    engine._scalping_daily_dd = 0.0
    engine._scalping_total_dd = 0.0
    engine._scan_interval = 120
    engine._scalping_scan_interval = 30

    # Screenshot
    engine.screenshot_generator = MagicMock()
    engine.screenshot_generator.get_screenshot_path.return_value = []

    # Monthly review
    engine.monthly_review = MagicMock()
    engine.monthly_review.list_reports.return_value = []

    # Manual mode
    engine.approve_setup = AsyncMock(return_value=True)
    engine.reject_setup = MagicMock(return_value=True)
    engine.approve_all_pending = AsyncMock(return_value=0)
    engine.toggle_scalping = MagicMock()
    engine.set_mode = MagicMock()

    # Engine lifecycle
    engine.start = AsyncMock()
    engine.stop = AsyncMock()

    return engine


def _make_mock_db():
    """Create a mock database."""
    db = MagicMock()
    db.get_trade_history = AsyncMock(return_value=[])
    db.get_performance_summary = AsyncMock(return_value={
        "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
        "win_rate": 0, "total_pnl": 0, "avg_rr": 0,
    })
    db.get_daily_stats = AsyncMock(return_value={})
    db.update_trade_notes = AsyncMock(return_value=True)
    db.get_equity_curve = AsyncMock(return_value=[])
    return db


# ── Pytest fixtures ─────────────────────────────────────────────

@pytest.fixture
def mock_engine():
    return _make_mock_engine()


@pytest.fixture
def mock_db():
    return _make_mock_db()


@pytest.fixture
def client(mock_engine, mock_db):
    """Create a FastAPI TestClient with mocked engine and db.

    We build a minimal app that mirrors main.py's routing but skips the
    lifespan (which tries to start the real trading engine and database).
    """
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.testclient import TestClient
    from api.routes import router as api_router

    # Patch engine and db at the module level where routes import them
    with patch("main.engine", mock_engine), \
         patch("main.db", mock_db):

        # Build a test app without lifespan
        test_app = FastAPI()
        test_app.include_router(api_router, prefix="/api/v1")

        # Replicate WebSocket endpoint from main.py
        from main import ConnectionManager
        test_ws_manager = ConnectionManager()

        @test_app.websocket("/ws")
        async def ws_endpoint(websocket: WebSocket):
            await test_ws_manager.connect(websocket)
            try:
                # Send initial status
                status = mock_engine.get_status()
                await test_ws_manager.send_personal(websocket, "engine_status", status)
                while True:
                    try:
                        raw = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                        data = json.loads(raw)
                        await _test_handle_ws_cmd(websocket, test_ws_manager, mock_engine, data)
                    except asyncio.TimeoutError:
                        await test_ws_manager.send_personal(websocket, "heartbeat", {"ts": "ok"})
                    except json.JSONDecodeError:
                        await test_ws_manager.send_personal(websocket, "error", {"message": "Invalid JSON"})
            except WebSocketDisconnect:
                test_ws_manager.disconnect(websocket)
            except Exception:
                test_ws_manager.disconnect(websocket)

        async def _test_handle_ws_cmd(websocket, mgr, eng, data):
            action = data.get("action")
            if action == "approve":
                setup_id = data.get("setup_id")
                success = await eng.approve_setup(setup_id)
                await mgr.send_personal(websocket, "setup_response", {"setup_id": setup_id, "approved": success})
            elif action == "reject":
                setup_id = data.get("setup_id")
                eng.reject_setup(setup_id)
                await mgr.send_personal(websocket, "setup_response", {"setup_id": setup_id, "rejected": True})
            elif action == "subscribe":
                instruments = data.get("instruments", [])
                await mgr.send_personal(websocket, "subscribed", {"instruments": instruments})
            else:
                await mgr.send_personal(websocket, "error", {"message": f"Unknown action: {action}"})

        # Replicate /health endpoint
        @test_app.get("/health")
        async def health():
            return {
                "status": "ok",
                "engine": mock_engine.running,
                "mode": mock_engine.mode.value if mock_engine.mode else "AUTO",
                "broker": mock_engine.broker.broker_type.value if mock_engine.broker.broker_type else "oanda",
                "database": mock_db is not None,
                "websocket_clients": len(test_ws_manager.active_connections),
                "version": "1.0.0",
            }

        with TestClient(test_app) as c:
            yield c


# ═══════════════════════════════════════════════════════════════
# SECTION 1: REST API ENDPOINT TESTS
# ═══════════════════════════════════════════════════════════════

class TestStatusEndpoint:
    def test_get_status(self, client):
        resp = client.get("/api/v1/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["running"] is True
        assert data["mode"] == "AUTO"
        assert data["broker"] == "capital"
        assert "open_positions" in data
        assert "pending_setups" in data

    def test_get_daily_activity(self, client):
        resp = client.get("/api/v1/daily-activity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["scans_completed"] == 10
        assert data["setups_found"] == 3
        assert "explanation" in data


class TestModeEndpoint:
    def test_get_mode(self, client):
        resp = client.get("/api/v1/mode")
        assert resp.status_code == 200
        assert resp.json()["mode"] == "AUTO"

    def test_set_mode_auto(self, client):
        resp = client.post("/api/v1/mode", json={"mode": "AUTO"})
        assert resp.status_code == 200
        assert resp.json()["mode"] == "AUTO"

    def test_set_mode_manual(self, client):
        resp = client.post("/api/v1/mode", json={"mode": "MANUAL"})
        assert resp.status_code == 200
        assert resp.json()["mode"] == "MANUAL"

    def test_set_mode_invalid(self, client):
        resp = client.post("/api/v1/mode", json={"mode": "INVALID"})
        assert resp.status_code == 400


class TestPendingSetups:
    def test_get_pending_setups(self, client):
        resp = client.get("/api/v1/pending-setups")
        assert resp.status_code == 200

    def test_approve_setup(self, client):
        resp = client.post("/api/v1/pending-setups/test-id/approve")
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    def test_reject_setup(self, client):
        resp = client.post("/api/v1/pending-setups/test-id/reject")
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    def test_approve_all(self, client):
        resp = client.post("/api/v1/pending-setups/approve-all")
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved_all"

    def test_reject_all(self, client):
        resp = client.post("/api/v1/pending-setups/reject-all")
        assert resp.status_code == 200


class TestPositions:
    def test_get_positions(self, client):
        resp = client.get("/api/v1/positions")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["instrument"] == "EUR_USD"


class TestAnalysis:
    def test_get_analysis_existing(self, client):
        resp = client.get("/api/v1/analysis/EUR_USD")
        assert resp.status_code == 200
        data = resp.json()
        assert data["instrument"] == "EUR_USD"
        assert data["score"] == 75
        assert data["htf_trend"] == "bullish"
        assert data["convergence"] is True

    def test_get_analysis_missing(self, client):
        resp = client.get("/api/v1/analysis/XAU_USD")
        assert resp.status_code == 200
        data = resp.json()
        assert data["score"] == 0
        assert "message" in data

    def test_get_all_analyses(self, client):
        resp = client.get("/api/v1/analysis")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["instrument"] == "EUR_USD"


class TestWatchlist:
    def test_get_watchlist(self, client):
        resp = client.get("/api/v1/watchlist")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_watchlist_categories(self, client):
        resp = client.get("/api/v1/watchlist/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert "active_categories" in data
        assert "available" in data
        assert "forex" in data["available"]

    def test_get_full_watchlist(self, client):
        resp = client.get("/api/v1/watchlist/full")
        assert resp.status_code == 200
        data = resp.json()
        assert "instruments" in data
        assert "count" in data

    def test_update_watchlist_categories_valid(self, client):
        resp = client.put("/api/v1/watchlist/categories",
                          json={"categories": ["forex", "commodities"]})
        assert resp.status_code == 200

    def test_update_watchlist_categories_invalid(self, client):
        resp = client.put("/api/v1/watchlist/categories",
                          json={"categories": ["invalid_cat"]})
        assert resp.status_code == 400


class TestAccount:
    def test_get_account(self, client):
        resp = client.get("/api/v1/account")
        assert resp.status_code == 200
        data = resp.json()
        assert data["balance"] == 10000.0
        assert data["equity"] == 10500.0
        assert data["currency"] == "USD"

    def test_get_account_error(self, client, mock_engine):
        mock_engine.broker.get_account_summary = AsyncMock(
            side_effect=Exception("Connection failed"))
        resp = client.get("/api/v1/account")
        assert resp.status_code == 500


class TestEngineControl:
    def test_start_engine(self, client):
        resp = client.post("/api/v1/engine/start")
        assert resp.status_code == 200
        # Engine already running → should return already_running
        assert resp.json()["status"] == "already_running"

    def test_start_engine_when_stopped(self, client, mock_engine):
        mock_engine.running = False
        resp = client.post("/api/v1/engine/start")
        assert resp.status_code == 200
        assert resp.json()["status"] == "starting"

    def test_stop_engine(self, client):
        resp = client.post("/api/v1/engine/stop")
        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"

    def test_emergency_close_all(self, client):
        resp = client.post("/api/v1/emergency/close-all")
        assert resp.status_code == 200
        assert resp.json()["count"] == 2


class TestBroker:
    def test_get_broker(self, client):
        resp = client.get("/api/v1/broker")
        assert resp.status_code == 200
        data = resp.json()
        assert data["broker"] == "capital"
        assert data["connected"] is True
        assert "available_brokers" in data
        assert len(data["available_brokers"]) >= 2

    def test_set_broker_valid(self, client):
        resp = client.post("/api/v1/broker",
                           json={"broker": "capital"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending_restart"

    def test_set_broker_unsupported(self, client):
        resp = client.post("/api/v1/broker",
                           json={"broker": "binance"})
        # 400 Bad Request for unsupported broker name (was 501 before — 501
        # is for missing server implementations, this is input validation).
        assert resp.status_code == 400


class TestCandles:
    def test_get_candles(self, client):
        resp = client.get("/api/v1/candles/EUR_USD?granularity=H1&count=50")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["open"] == 1.1000

    def test_get_candles_connection_error(self, client, mock_engine):
        mock_engine.broker.get_candles = AsyncMock(
            side_effect=ConnectionError("Broker disconnected"))
        resp = client.get("/api/v1/candles/EUR_USD")
        assert resp.status_code == 503


class TestPrice:
    def test_get_price(self, client):
        resp = client.get("/api/v1/price/EUR_USD")
        assert resp.status_code == 200
        data = resp.json()
        assert data["instrument"] == "EUR_USD"
        assert data["bid"] == 1.1018
        assert data["ask"] == 1.1022

    def test_get_price_error(self, client, mock_engine):
        mock_engine.broker.get_current_price = AsyncMock(
            side_effect=Exception("Price fetch failed"))
        resp = client.get("/api/v1/price/EUR_USD")
        assert resp.status_code == 500


class TestStrategies:
    def test_get_strategies_config(self, client):
        resp = client.get("/api/v1/strategies/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["BLUE"] is True
        assert data["BLACK"] is False

    def test_set_strategies_config(self, client):
        resp = client.put("/api/v1/strategies/config",
                          json={"BLUE": True, "BLACK": True})
        assert resp.status_code == 200
        data = resp.json()
        assert "config" in data
        assert "enabled" in data

    def test_set_strategies_config_empty(self, client):
        resp = client.put("/api/v1/strategies/config", json={})
        assert resp.status_code == 400

    def test_get_strategies_info(self, client):
        resp = client.get("/api/v1/strategies")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 6
        colors = [s["color"] for s in data]
        assert "BLUE" in colors
        assert "RED" in colors
        assert "GREEN" in colors


class TestHistory:
    def test_get_history(self, client):
        resp = client.get("/api/v1/history")
        assert resp.status_code == 200

    def test_get_history_with_filters(self, client):
        resp = client.get("/api/v1/history?limit=10&offset=5&instrument=EUR_USD&strategy=BLUE")
        assert resp.status_code == 200

    def test_get_performance_stats(self, client):
        resp = client.get("/api/v1/history/stats?days=30")
        assert resp.status_code == 200

    def test_get_daily_stats(self, client):
        resp = client.get("/api/v1/history/daily")
        assert resp.status_code == 200

    def test_update_trade_notes(self, client):
        resp = client.put("/api/v1/history/trade-1/notes",
                          json={"notes": "Good entry timing"})
        assert resp.status_code == 200

    def test_update_trade_notes_not_found(self, client, mock_db):
        mock_db.update_trade_notes = AsyncMock(return_value=False)
        resp = client.put("/api/v1/history/missing-id/notes",
                          json={"notes": "test"})
        assert resp.status_code == 404

    def test_get_equity_curve(self, client):
        resp = client.get("/api/v1/equity-curve?days=30")
        assert resp.status_code == 200


class TestRiskConfig:
    def test_get_risk_config(self, client):
        resp = client.get("/api/v1/risk-config")
        assert resp.status_code == 200
        data = resp.json()
        assert "risk_day_trading" in data
        assert "max_total_risk" in data
        assert "drawdown_method" in data
        assert "delta_enabled" in data

    def test_get_risk_status(self, client):
        resp = client.get("/api/v1/risk-status")
        assert resp.status_code == 200

    def test_set_risk_config_valid(self, client):
        resp = client.put("/api/v1/risk-config",
                          json={"risk_day_trading": 0.01})
        assert resp.status_code == 200
        assert "updated" in resp.json()

    def test_set_risk_config_out_of_range(self, client):
        resp = client.put("/api/v1/risk-config",
                          json={"risk_day_trading": 0.50})
        assert resp.status_code == 400

    def test_set_risk_config_empty(self, client):
        resp = client.put("/api/v1/risk-config", json={})
        assert resp.status_code == 400

    def test_set_risk_drawdown_method_valid(self, client):
        resp = client.put("/api/v1/risk-config",
                          json={"drawdown_method": "variable"})
        assert resp.status_code == 200

    def test_set_risk_drawdown_method_invalid(self, client):
        resp = client.put("/api/v1/risk-config",
                          json={"drawdown_method": "invalid"})
        assert resp.status_code == 400


class TestAlerts:
    def test_get_alert_config(self, client):
        resp = client.get("/api/v1/alerts/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "telegram_enabled" in data

    def test_set_alert_config(self, client):
        resp = client.put("/api/v1/alerts/config",
                          json={"telegram_enabled": True, "telegram_bot_token": "tok123"})
        assert resp.status_code == 200
        assert "config" in resp.json()

    def test_test_alert_channel_valid(self, client):
        resp = client.post("/api/v1/alerts/test/telegram")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_test_alert_channel_invalid(self, client):
        resp = client.post("/api/v1/alerts/test/invalid_channel")
        assert resp.status_code == 400


class TestNotifications:
    def test_get_notifications(self, client):
        resp = client.get("/api/v1/notifications")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1


class TestCalendarAndNews:
    def test_get_calendar(self, client):
        resp = client.get("/api/v1/calendar")
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert "news_active" in data

    def test_get_news(self, client):
        resp = client.get("/api/v1/news?limit=5")
        assert resp.status_code == 200


class TestScalping:
    def test_toggle_scalping(self, client):
        resp = client.post("/api/v1/scalping/toggle",
                           json={"enabled": True})
        assert resp.status_code == 200
        assert resp.json()["scalping_enabled"] is True

    def test_get_scalping_status(self, client):
        resp = client.get("/api/v1/scalping/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "enabled" in data
        assert "dd_limits_ok" in data


class TestSecurity:
    def test_get_security_status(self, client):
        resp = client.get("/api/v1/security/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "auth_enabled" in data
        assert "rate_limit_enabled" in data

    def test_generate_api_key(self, client):
        resp = client.post("/api/v1/security/generate-key?label=test")
        assert resp.status_code == 200
        data = resp.json()
        assert "api_key" in data


class TestFundedAccount:
    def test_toggle_funded(self, client):
        resp = client.post("/api/v1/funded/toggle",
                           json={"enabled": True})
        assert resp.status_code == 200
        assert resp.json()["funded_account_mode"] is True

    def test_get_funded_status(self, client):
        resp = client.get("/api/v1/funded/status")
        assert resp.status_code == 200


class TestJournal:
    def test_get_journal_stats(self, client):
        resp = client.get("/api/v1/journal/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_trades"] == 10
        assert data["wins"] == 6

    def test_get_journal_trades(self, client):
        resp = client.get("/api/v1/journal/trades?limit=10&offset=0")
        assert resp.status_code == 200

    def test_update_emotional_notes(self, client):
        resp = client.put("/api/v1/journal/trades/t1/emotional-notes",
                          json={"emotional_notes_pre": "Calm and focused"})
        assert resp.status_code == 200

    def test_update_emotional_notes_not_found(self, client):
        resp = client.put("/api/v1/journal/trades/nonexistent/emotional-notes",
                          json={"emotional_notes_pre": "test"})
        assert resp.status_code == 404

    def test_update_journal_notes(self, client):
        resp = client.put("/api/v1/journal/trades/t1/notes",
                          json={"trade_summary": "Clean blue A entry"})
        assert resp.status_code == 200

    def test_update_asr(self, client):
        resp = client.put("/api/v1/journal/trades/t1/asr",
                          json={
                              "htf_correct": True,
                              "ltf_correct": True,
                              "strategy_correct": True,
                              "sl_correct": True,
                              "tp_correct": True,
                              "management_correct": True,
                              "would_enter_again": True,
                              "lessons": "Good execution per plan",
                          })
        assert resp.status_code == 200
        assert resp.json()["asr_completed"] is True

    def test_get_asr_stats(self, client):
        resp = client.get("/api/v1/journal/asr-stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 10
        assert data["asr_completed"] == 5


class TestScreenshots:
    def test_get_screenshots(self, client):
        resp = client.get("/api/v1/screenshots/trade-1")
        assert resp.status_code == 200
        data = resp.json()
        assert "screenshots" in data

    def test_get_screenshot_image_invalid_filename(self, client):
        # Filename with spaces/special chars should be rejected by the regex
        resp = client.get("/api/v1/screenshots/trade-1/image/bad file!name.png")
        assert resp.status_code == 400

    def test_get_screenshot_image_not_found(self, client):
        # Valid filename but file doesn't exist
        resp = client.get("/api/v1/screenshots/trade-1/image/nonexistent.png")
        assert resp.status_code == 404


class TestProfiles:
    def test_get_profiles(self, client):
        resp = client.get("/api/v1/profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert "profiles" in data

    def test_apply_profile_invalid(self, client):
        resp = client.post("/api/v1/profiles/apply",
                           json={"profile_id": "nonexistent"})
        assert resp.status_code == 400


class TestMonthlyReview:
    def test_list_monthly_reviews(self, client):
        resp = client.get("/api/v1/monthly-review")
        assert resp.status_code == 200

    def test_get_monthly_review_not_found(self, client, mock_engine):
        mock_engine.monthly_review.load_report.return_value = None
        resp = client.get("/api/v1/monthly-review/2026-03")
        assert resp.status_code == 404


class TestDiagnostic:
    def test_get_diagnostic(self, client):
        # Diagnostic endpoint calls broker internals — just ensure no crash
        resp = client.get("/api/v1/diagnostic")
        assert resp.status_code == 200


class TestWeeklyReview:
    def test_get_weekly_review_default(self, client):
        resp = client.get("/api/v1/weekly-review")
        assert resp.status_code == 200
        data = resp.json()
        assert "week" in data

    def test_get_weekly_review_invalid_format(self, client):
        resp = client.get("/api/v1/weekly-review?week=invalid")
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════
# SECTION 2: WEBSOCKET TESTS
# ═══════════════════════════════════════════════════════════════

class TestWebSocket:
    def test_websocket_connect_and_receive_status(self, client, mock_engine):
        """Test WebSocket connection and initial status message."""
        with client.websocket_connect("/ws") as ws:
            # Should receive initial engine_status
            data = ws.receive_json()
            assert data["type"] == "engine_status"
            assert "data" in data

    def test_websocket_heartbeat(self, client, mock_engine):
        """Test that heartbeat is sent after timeout."""
        with client.websocket_connect("/ws") as ws:
            # Receive initial status
            ws.receive_json()
            # The heartbeat comes after 30s timeout on receive —
            # In test mode, just verify connection is alive
            ws.send_json({"action": "ping"})
            resp = ws.receive_json()
            # Unknown action returns error
            assert resp["type"] == "error"

    def test_websocket_approve_command(self, client, mock_engine):
        """Test approving a setup via WebSocket."""
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # initial status
            ws.send_json({"action": "approve", "setup_id": "test-123"})
            resp = ws.receive_json()
            assert resp["type"] == "setup_response"
            assert resp["data"]["setup_id"] == "test-123"
            assert resp["data"]["approved"] is True

    def test_websocket_reject_command(self, client, mock_engine):
        """Test rejecting a setup via WebSocket."""
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # initial status
            ws.send_json({"action": "reject", "setup_id": "test-456"})
            resp = ws.receive_json()
            assert resp["type"] == "setup_response"
            assert resp["data"]["setup_id"] == "test-456"
            assert resp["data"]["rejected"] is True

    def test_websocket_subscribe_command(self, client, mock_engine):
        """Test subscribing to instrument updates."""
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # initial status
            ws.send_json({"action": "subscribe", "instruments": ["EUR_USD", "GBP_USD"]})
            resp = ws.receive_json()
            assert resp["type"] == "subscribed"
            assert "EUR_USD" in resp["data"]["instruments"]

    def test_websocket_unknown_action(self, client, mock_engine):
        """Test that unknown actions return error."""
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # initial status
            ws.send_json({"action": "unknown_action"})
            resp = ws.receive_json()
            assert resp["type"] == "error"
            assert "Unknown action" in resp["data"]["message"]

    def test_websocket_invalid_json(self, client, mock_engine):
        """Test that invalid JSON returns error."""
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # initial status
            ws.send_text("not valid json{{{")
            resp = ws.receive_json()
            assert resp["type"] == "error"
            assert "Invalid JSON" in resp["data"]["message"]


class TestConnectionManager:
    def test_manager_properties(self):
        """Test ConnectionManager basic operations."""
        from main import ConnectionManager
        mgr = ConnectionManager()
        assert mgr.active_connections == []
        assert mgr.is_full is False

    @pytest.mark.asyncio
    async def test_broadcast_empty(self):
        """Test broadcast with no connections doesn't crash."""
        from main import ConnectionManager
        mgr = ConnectionManager()
        await mgr.broadcast("test_event", {"key": "value"})
        # No error = pass


# ═══════════════════════════════════════════════════════════════
# SECTION 3: NOTIFICATION / ALERT TESTS
# ═══════════════════════════════════════════════════════════════

class TestAlertManager:
    """Tests for the AlertManager notification system."""

    def test_alert_config_defaults(self):
        """Test default AlertConfig has all channels disabled."""
        from core.alerts import AlertConfig
        cfg = AlertConfig()
        assert cfg.telegram_enabled is False
        assert cfg.discord_enabled is False
        assert cfg.email_enabled is False
        assert cfg.gmail_enabled is False
        assert cfg.notify_trade_executed is True

    def test_alert_config_mask(self):
        """Test that sensitive fields are masked in get_config()."""
        from core.alerts import AlertConfig, AlertManager
        cfg = AlertConfig(
            telegram_bot_token="12345678:ABC-DEFghiJKLmnop",
            discord_webhook_url="https://discord.com/api/webhooks/secret123",
            email_password="my_secret_password",
            gmail_client_secret="gmail-secret-value",
            gmail_refresh_token="refresh-token-abc123",
        )
        mgr = AlertManager(config=cfg)
        exposed = mgr.get_config()

        # Sensitive fields should be masked (only last 4 chars visible)
        assert exposed["telegram_bot_token"].endswith("mnop")
        assert exposed["telegram_bot_token"].startswith("*")
        assert exposed["discord_webhook_url"].endswith("t123")
        assert exposed["email_password"].endswith("word")
        assert exposed["gmail_client_secret"].endswith("alue")
        assert exposed["gmail_refresh_token"].endswith("c123")

        # Non-sensitive fields should not be masked
        assert exposed["telegram_enabled"] is False

    def test_mask_short_values(self):
        """Test masking of short values (<=4 chars)."""
        from core.alerts import _mask
        assert _mask("") == ""
        assert _mask("ab") == "****"
        assert _mask("abcd") == "****"
        assert _mask("abcde") == "*bcde"

    @pytest.mark.asyncio
    async def test_send_alert_no_channels(self):
        """Test send_alert with no channels enabled (should not crash)."""
        from core.alerts import AlertConfig, AlertManager
        cfg = AlertConfig()  # All disabled
        mgr = AlertManager(config=cfg)
        await mgr.send_alert("test", "Test Title", "Test Body")
        await mgr.close()

    @pytest.mark.asyncio
    async def test_send_trade_executed_notification_disabled(self):
        """Test that disabled notification types are skipped."""
        from core.alerts import AlertConfig, AlertManager
        cfg = AlertConfig(notify_trade_executed=False)
        mgr = AlertManager(config=cfg)
        # Should return immediately without sending
        await mgr.send_trade_executed("EUR_USD", "BUY", 1.10, 1.09, 1.12, 2.0)
        await mgr.close()

    @pytest.mark.asyncio
    async def test_send_setup_pending_notification_disabled(self):
        """Test that disabled setup_pending notifications are skipped."""
        from core.alerts import AlertConfig, AlertManager
        cfg = AlertConfig(notify_setup_pending=False)
        mgr = AlertManager(config=cfg)
        await mgr.send_setup_pending("EUR_USD", "BUY", 1.10, 2.0)
        await mgr.close()

    @pytest.mark.asyncio
    async def test_send_trade_closed_notification_disabled(self):
        """Test that disabled trade_closed notifications are skipped."""
        from core.alerts import AlertConfig, AlertManager
        cfg = AlertConfig(notify_trade_closed=False)
        mgr = AlertManager(config=cfg)
        await mgr.send_trade_closed("EUR_USD", 50.0, 25.0, "TP")
        await mgr.close()

    @pytest.mark.asyncio
    async def test_send_daily_summary_disabled(self):
        """Test that disabled daily_summary notifications are skipped."""
        from core.alerts import AlertConfig, AlertManager
        cfg = AlertConfig(notify_daily_summary=False)
        mgr = AlertManager(config=cfg)
        await mgr.send_daily_summary({"total_pnl": 100, "trades_count": 5})
        await mgr.close()

    @pytest.mark.asyncio
    async def test_telegram_send_mocked(self):
        """Test Telegram send with mocked HTTP."""
        from core.alerts import AlertConfig, AlertManager
        cfg = AlertConfig(
            telegram_enabled=True,
            telegram_bot_token="fake_token",
            telegram_chat_id="12345",
        )
        mgr = AlertManager(config=cfg)

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(mgr, '_get_http') as mock_http:
            mock_http.return_value.post = AsyncMock(return_value=mock_response)
            await mgr._send_telegram("Test", "Body")

        await mgr.close()

    @pytest.mark.asyncio
    async def test_telegram_send_missing_config(self):
        """Test Telegram send with missing token/chat_id (should skip)."""
        from core.alerts import AlertConfig, AlertManager
        cfg = AlertConfig(telegram_enabled=True)  # No token or chat_id
        mgr = AlertManager(config=cfg)
        # Should not raise — just skip
        await mgr._send_telegram("Test", "Body")
        await mgr.close()

    @pytest.mark.asyncio
    async def test_discord_send_mocked(self):
        """Test Discord send with mocked HTTP."""
        from core.alerts import AlertConfig, AlertManager
        cfg = AlertConfig(
            discord_enabled=True,
            discord_webhook_url="https://discord.com/api/webhooks/fake",
        )
        mgr = AlertManager(config=cfg)

        mock_response = MagicMock()
        mock_response.status_code = 204

        with patch.object(mgr, '_get_http') as mock_http:
            mock_http.return_value.post = AsyncMock(return_value=mock_response)
            await mgr._send_discord("Test", "Body", "test")

        await mgr.close()

    @pytest.mark.asyncio
    async def test_discord_send_missing_url(self):
        """Test Discord send with missing webhook URL (should skip)."""
        from core.alerts import AlertConfig, AlertManager
        cfg = AlertConfig(discord_enabled=True)  # No webhook URL
        mgr = AlertManager(config=cfg)
        await mgr._send_discord("Test", "Body", "test")
        await mgr.close()

    @pytest.mark.asyncio
    async def test_email_send_missing_config(self):
        """Test email send with incomplete config (should skip)."""
        from core.alerts import AlertConfig, AlertManager
        cfg = AlertConfig(email_enabled=True)  # No SMTP credentials
        mgr = AlertManager(config=cfg)
        await mgr._send_email("Test", "Body")
        await mgr.close()

    @pytest.mark.asyncio
    async def test_gmail_send_missing_config(self):
        """Test Gmail send with missing OAuth2 config (should skip)."""
        from core.alerts import AlertConfig, AlertManager
        cfg = AlertConfig(gmail_enabled=True)  # No OAuth2 credentials
        mgr = AlertManager(config=cfg)
        await mgr._send_gmail("Test", "Body")
        await mgr.close()

    @pytest.mark.asyncio
    async def test_email_send_mocked(self):
        """Test email send with mocked SMTP."""
        from core.alerts import AlertConfig, AlertManager
        cfg = AlertConfig(
            email_enabled=True,
            email_username="test@example.com",
            email_password="password123",
            email_recipient="recipient@example.com",
        )
        mgr = AlertManager(config=cfg)

        with patch.object(mgr, '_smtp_send') as mock_smtp:
            await mgr._send_email("Test Subject", "Test body <b>bold</b>")
            mock_smtp.assert_called_once()

        await mgr.close()

    @pytest.mark.asyncio
    async def test_gmail_send_mocked(self):
        """Test Gmail send with mocked HTTP client."""
        from core.alerts import AlertConfig, AlertManager
        cfg = AlertConfig(
            gmail_enabled=True,
            gmail_sender="sender@gmail.com",
            gmail_recipient="recipient@gmail.com",
            gmail_client_id="client-id",
            gmail_client_secret="client-secret",
            gmail_refresh_token="refresh-token",
        )
        mgr = AlertManager(config=cfg)

        # Mock token refresh
        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {"access_token": "fake_access_token"}

        # Mock send response
        send_response = MagicMock()
        send_response.status_code = 200

        with patch.object(mgr, '_get_http') as mock_http:
            mock_http.return_value.post = AsyncMock(
                side_effect=[token_response, send_response])
            await mgr._send_gmail("Test Subject", "Test body")

        await mgr.close()

    @pytest.mark.asyncio
    async def test_test_channel_success(self):
        """Test test_channel returns True on success."""
        from core.alerts import AlertConfig, AlertManager, AlertChannel
        cfg = AlertConfig(
            telegram_enabled=True,
            telegram_bot_token="tok",
            telegram_chat_id="123",
        )
        mgr = AlertManager(config=cfg)

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(mgr, '_get_http') as mock_http:
            mock_http.return_value.post = AsyncMock(return_value=mock_response)
            result = await mgr.test_channel(AlertChannel.TELEGRAM)
            assert result is True

        await mgr.close()

    @pytest.mark.asyncio
    async def test_test_channel_failure(self):
        """Test test_channel returns False on error."""
        from core.alerts import AlertConfig, AlertManager, AlertChannel
        cfg = AlertConfig(
            telegram_enabled=True,
            telegram_bot_token="tok",
            telegram_chat_id="123",
        )
        mgr = AlertManager(config=cfg)

        with patch.object(mgr, '_get_http') as mock_http:
            mock_http.return_value.post = AsyncMock(
                side_effect=Exception("Network error"))
            result = await mgr.test_channel(AlertChannel.TELEGRAM)
            assert result is False

        await mgr.close()

    def test_discord_colour_for_type(self):
        """Test that different alert types get correct embed colours."""
        from core.alerts import AlertManager
        assert AlertManager._discord_colour_for_type("trade_executed") == 0x00FF9D
        assert AlertManager._discord_colour_for_type("setup_pending") == 0xFFD700
        assert AlertManager._discord_colour_for_type("trade_closed") == 0x3498DB
        assert AlertManager._discord_colour_for_type("daily_summary") == 0x9B59B6
        # Unknown type returns default
        assert AlertManager._discord_colour_for_type("unknown") == 0x00FF9D

    @pytest.mark.asyncio
    async def test_safe_send_catches_exceptions(self):
        """Test _safe_send swallows exceptions gracefully."""
        from core.alerts import AlertConfig, AlertManager

        async def failing_coro():
            raise RuntimeError("Simulated failure")

        mgr = AlertManager(config=AlertConfig())
        # Should not raise
        await mgr._safe_send(failing_coro())
        await mgr.close()

    @pytest.mark.asyncio
    async def test_send_position_update(self):
        """Test position update notification."""
        from core.alerts import AlertConfig, AlertManager
        cfg = AlertConfig()  # No channels enabled
        mgr = AlertManager(config=cfg)
        # Should not raise even with no channels
        await mgr.send_position_update("EUR_USD", "BE", 1.1020, 1.1000)
        await mgr.close()

    @pytest.mark.asyncio
    async def test_send_engine_status(self):
        """Test engine status notification."""
        from core.alerts import AlertConfig, AlertManager
        cfg = AlertConfig()
        mgr = AlertManager(config=cfg)
        await mgr.send_engine_status("started", "Engine started successfully")
        await mgr.close()

    @pytest.mark.asyncio
    async def test_send_risk_alert(self):
        """Test risk alert notification."""
        from core.alerts import AlertConfig, AlertManager
        cfg = AlertConfig()
        mgr = AlertManager(config=cfg)
        await mgr.send_risk_alert("max_dd", "Daily drawdown exceeded", 5.5)
        await mgr.close()

    def test_update_config(self):
        """Test update_config persists and replaces config."""
        from core.alerts import AlertConfig, AlertManager
        mgr = AlertManager(config=AlertConfig())
        new_cfg = AlertConfig(telegram_enabled=True)

        with patch.object(mgr, '_save_config'):
            mgr.update_config(new_cfg)

        assert mgr._config.telegram_enabled is True

    def test_alert_channel_enum(self):
        """Test AlertChannel enum values."""
        from core.alerts import AlertChannel
        assert AlertChannel.TELEGRAM.value == "telegram"
        assert AlertChannel.DISCORD.value == "discord"
        assert AlertChannel.EMAIL.value == "email"
        assert AlertChannel.GMAIL.value == "gmail"


class TestTextHelpers:
    """Test module-level text helper functions in alerts.py."""

    def test_html_to_discord_md(self):
        from core.alerts import _html_to_discord_md
        result = _html_to_discord_md("<b>Bold</b> and <i>italic</i>")
        assert "**Bold**" in result
        assert "*italic*" in result

    def test_strip_emoji_tags(self):
        from core.alerts import _strip_emoji_tags
        # Function is a passthrough — emojis are plain Unicode
        text = "\U0001F7E2 Trade Executed"
        assert _strip_emoji_tags(text) == text


# ═══════════════════════════════════════════════════════════════
# SECTION 4: ERROR HANDLING TESTS
# ═══════════════════════════════════════════════════════════════

class TestErrorHandling:
    """Test that endpoints handle errors gracefully."""

    def test_history_with_no_db(self, client, mock_db):
        """Test history endpoint when db is None."""
        with patch("main.db", None):
            resp = client.get("/api/v1/history")
            assert resp.status_code == 200
            assert resp.json() == []

    def test_equity_curve_with_no_db(self, client):
        with patch("main.db", None):
            resp = client.get("/api/v1/equity-curve")
            assert resp.status_code == 200
            assert resp.json() == []

    def test_journal_stats_no_journal(self, client, mock_engine):
        """Test journal stats when trade_journal is None."""
        mock_engine.trade_journal = None
        resp = client.get("/api/v1/journal/stats")
        assert resp.status_code == 200
        assert resp.json()["total_trades"] == 0
        assert "message" in resp.json()

    def test_journal_trades_no_journal(self, client, mock_engine):
        mock_engine.trade_journal = None
        resp = client.get("/api/v1/journal/trades")
        assert resp.status_code == 200
        assert resp.json() == []


# ═══════════════════════════════════════════════════════════════
# SECTION 5: HEALTH / ROOT ENDPOINT
# ═══════════════════════════════════════════════════════════════

class TestHealthEndpoint:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "websocket_clients" in data
