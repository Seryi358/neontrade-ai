"""
Atlas - API Routes
REST endpoints for the frontend app.
Supports: Auto/Manual modes, trade history, explanations, broker selection.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from enum import Enum
from loguru import logger

router = APIRouter()


# ── Request / Response Models ────────────────────────────────────

class TradingModeRequest(BaseModel):
    mode: str  # "AUTO" or "MANUAL"


class SetupApprovalRequest(BaseModel):
    setup_id: str


class StrategyConfigRequest(BaseModel):
    BLUE: Optional[bool] = None
    BLUE_A: Optional[bool] = None
    BLUE_B: Optional[bool] = None
    BLUE_C: Optional[bool] = None
    RED: Optional[bool] = None
    PINK: Optional[bool] = None
    WHITE: Optional[bool] = None
    BLACK: Optional[bool] = None
    GREEN: Optional[bool] = None


class BrokerSelectionRequest(BaseModel):
    broker: str  # "oanda", "tagmarkets", etc.
    api_key: Optional[str] = None
    account_id: Optional[str] = None
    environment: Optional[str] = "practice"


class TradeResponse(BaseModel):
    trade_id: str
    instrument: str
    direction: str
    entry_price: float
    current_sl: float
    take_profit: float
    phase: str
    unrealized_pnl: Optional[float] = None
    strategy: Optional[str] = None


# ── Engine Status ─────────────────────────────────────────────────
# Note: response_model is NOT used on the endpoint (to avoid stripping
# dynamic fields), but EngineStatusResponse is kept as a schema reference
# for tests and documentation.

class EngineStatusResponse(BaseModel):
    """Schema reference for the /status endpoint response."""
    running: bool = False
    mode: str = "AUTO"
    broker: str = "capital"
    open_positions: int = 0
    pending_setups: int = 0
    total_risk: float = 0.0
    watchlist_count: int = 0
    startup_error: str = ""
    scanned_instruments: int = 0
    positions: List[Dict] = []
    daily_activity: Dict = {}

@router.get("/status")
async def get_status():
    """Get current trading engine status."""
    from main import engine
    status = engine.get_status()
    mode = getattr(engine, 'mode', None)
    mode_str = mode.value if mode else "AUTO"
    pending = getattr(engine, 'pending_setups', [])
    broker_name = getattr(engine.broker, 'broker_type', None)
    broker_str = broker_name.value if broker_name else "capital"

    return {
        "running": status["running"],
        "mode": mode_str,
        "broker": broker_str,
        "open_positions": status["open_positions"],
        "pending_setups": len(pending),
        "total_risk": status["total_risk"],
        "watchlist_count": status["watchlist_count"],
        "startup_error": status.get("startup_error", ""),
        "scanned_instruments": status.get("scanned_instruments", 0),
        # Include dynamic fields that frontend needs
        "positions": status.get("positions", []),
        "daily_activity": status.get("daily_activity", {}),
    }


# ── Daily Activity (Proof of Life) ────────────────────────────────

@router.get("/daily-activity")
async def get_daily_activity():
    """
    Get today's engine activity counters.
    This is the 'proof of life' — shows scans completed, setups found/executed,
    even if 0 trades happened. If scans_completed > 0, the engine was alive.
    """
    from main import engine
    status = engine.get_status()
    activity = status.get("daily_activity", {})
    return {
        "date": activity.get("date", ""),
        "scans_completed": activity.get("scans_completed", 0),
        "setups_found": activity.get("setups_found", 0),
        "setups_executed": activity.get("setups_executed", 0),
        "setups_filtered": activity.get("setups_filtered", 0),
        "errors": activity.get("errors", 0),
        "engine_running": status["running"],
        "pairs_analyzed": len(status.get("last_scan", {})),
        "open_positions": status["open_positions"],
        "explanation": (
            "If scans_completed > 0, the engine was active today. "
            "0 trades is normal if no high-quality setups were found. "
            "Expect 0-5 trades per day depending on market conditions."
        ),
    }


# ── Visual Dashboard (V1-V10) ──────────────────────────────────────

@router.get("/engine-state")
async def get_engine_state():
    """Consolidated visual state for UI (news banner, engine dot, timeline, countdown).

    Returns:
      - running, paused_reason (str|None), paused_reason_text, resumes_at_utc
      - session: "london" | "london_ny_overlap" | "ny" | "asia" | "quiet"
      - news: {active: {...}|null, next: {...}|null}
      - consecutive_losses_today, setups_executed_today, max_trades_per_day
      - now_utc, trading_hours_utc
    """
    from main import engine
    return engine.get_engine_state()


@router.get("/watchlist-status")
async def get_watchlist_status():
    """Per-instrument status chips for the Market tab (V4).

    Each entry has: instrument, score, htf_trend, ltf_trend, convergence,
    status (setup_queued | ready_waiting | forming | weak | no_pattern),
    status_text. Sorted by score desc.
    """
    from main import engine
    return engine.get_watchlist_status()


# ── Broker Diagnostic ──────────────────────────────────────────────

@router.get("/diagnostic")
async def run_diagnostic():
    """
    Step-by-step broker diagnostic. Tests session, epic resolution, and candle fetch.
    Use this to debug why data is empty.
    """
    from main import engine
    from core.resilience import broker_circuit_breaker
    broker = engine.broker
    results = {
        "engine_running": engine.running,
        "startup_error": engine.startup_error,
        "scanned_instruments": len(engine.last_scan_results),
        "broker_type": getattr(broker, 'broker_type', None),
        "circuit_breaker": {
            "state": broker_circuit_breaker.state,
            "failure_count": broker_circuit_breaker._failure_count,
            "threshold": broker_circuit_breaker.failure_threshold,
        },
        # Instruments the broker rejected during warm_epic_cache. The scan
        # loop skips these so they don't waste 4 API calls/cycle each.
        "epic_blocklist": (
            broker.get_epic_blocklist()
            if hasattr(broker, "get_epic_blocklist")
            else []
        ),
        "steps": [],
    }
    if results["broker_type"]:
        results["broker_type"] = results["broker_type"].value

    # Step 1: Session
    try:
        await broker._ensure_session()
        cst = getattr(broker, '_cst', None)
        sec_tok = getattr(broker, '_security_token', None)
        results["steps"].append({
            "step": "1_session",
            "ok": bool(cst and sec_tok),
            "detail": f"CST={'SET' if cst else 'EMPTY'}, SecurityToken={'SET' if sec_tok else 'EMPTY'}",
        })
    except Exception as e:
        results["steps"].append({"step": "1_session", "ok": False, "detail": str(e)})
        return results

    # Step 2: Account
    try:
        summary = await broker.get_account_summary()
        results["steps"].append({
            "step": "2_account",
            "ok": True,
            "detail": f"Balance: {summary.balance} {summary.currency}",
        })
    except Exception as e:
        results["steps"].append({"step": "2_account", "ok": False, "detail": str(e)})

    # Step 3: Resolve EUR_USD epic
    epic = None
    try:
        epic = await broker._resolve_epic("EUR_USD")
        results["steps"].append({
            "step": "3_resolve_epic",
            "ok": True,
            "detail": f"EUR_USD -> '{epic}'",
        })
    except Exception as e:
        results["steps"].append({"step": "3_resolve_epic", "ok": False, "detail": str(e)})

    # Step 4: Fetch 5 candles (H1)
    try:
        candles = await broker.get_candles("EUR_USD", "H1", 5)
        if candles:
            last = candles[-1]
            results["steps"].append({
                "step": "4_candles_H1",
                "ok": True,
                "detail": f"{len(candles)} candles. Last: O={last.open} H={last.high} L={last.low} C={last.close} T={last.time}",
            })
        else:
            results["steps"].append({
                "step": "4_candles_H1",
                "ok": False,
                "detail": "Empty candle list returned (0 candles)",
            })
    except Exception as e:
        results["steps"].append({"step": "4_candles_H1", "ok": False, "detail": str(e)})

    # Step 5: Raw API response for debugging
    try:
        if epic:
            raw = await broker._get(f"/api/v1/prices/{epic}", params={
                "resolution": "HOUR",
                "max": 2,
            })
            prices = raw.get("prices", [])
            results["steps"].append({
                "step": "5_raw_api",
                "ok": len(prices) > 0,
                "detail": f"{len(prices)} raw prices. Keys: {list(raw.keys())}",
                "sample": prices[0] if prices else raw,
            })
    except Exception as e:
        results["steps"].append({"step": "5_raw_api", "ok": False, "detail": str(e)})

    # Step 6: Check scan results
    scan_sample = {}
    for inst, analysis in list(engine.last_scan_results.items())[:3]:
        scan_sample[inst] = {"score": analysis.score, "htf_trend": analysis.htf_trend.value}
    results["steps"].append({
        "step": "6_scan_results",
        "ok": len(engine.last_scan_results) > 0,
        "detail": f"{len(engine.last_scan_results)} instruments scanned",
        "sample": scan_sample,
    })

    return results


# ── Trading Mode ──────────────────────────────────────────────────

@router.get("/mode")
async def get_mode():
    """Get current trading mode (AUTO or MANUAL)."""
    from main import engine
    mode = getattr(engine, 'mode', None)
    return {
        "mode": mode.value if mode else "AUTO",
        "description": "Atlas opera automáticamente" if (not mode or mode.value == "AUTO")
                       else "Atlas sugiere operaciones para tu aprobación",
    }


@router.post("/mode")
async def set_mode(request: TradingModeRequest):
    """Switch between AUTO and MANUAL trading modes.

    Persists the choice to ``data/risk_config.json`` so it survives container
    restarts (added 2026-04-22 after a redeploy reverted Sergio's AUTO mode
    silently — _load_risk_overrides now also applies engine_mode at startup).
    """
    from main import engine
    from config import settings as _s
    mode_upper = request.mode.upper()
    if mode_upper not in ("AUTO", "MANUAL"):
        raise HTTPException(400, "Mode must be 'AUTO' or 'MANUAL'")

    if hasattr(engine, 'set_mode'):
        engine.set_mode(mode_upper)
    _s.engine_mode = mode_upper

    # Persist to risk_config.json (atomic, preserves other keys)
    import json, os, tempfile
    _backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    risk_path = os.path.join(_backend_dir, "data", "risk_config.json")
    overrides: dict = {}
    if os.path.exists(risk_path):
        try:
            with open(risk_path) as f:
                overrides = json.load(f)
            if not isinstance(overrides, dict):
                overrides = {}
        except Exception as e:
            logger.warning(f"risk_config.json unreadable ({e}); aborting mode save")
            raise HTTPException(500, "Config file corrupted — manual fix required before saving")
    overrides["engine_mode"] = mode_upper
    os.makedirs(os.path.dirname(risk_path), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(risk_path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(overrides, f, indent=2)
        os.replace(tmp_path, risk_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return {
        "mode": mode_upper,
        "message": "Modo cambiado a AUTOMÁTICO" if mode_upper == "AUTO"
                   else "Modo cambiado a MANUAL - aprobarás cada operación",
    }


# ── Manual Mode: Pending Setups ──────────────────────────────────

@router.get("/pending-setups")
async def get_pending_setups():
    """Get all pending trade setups waiting for user approval (Manual Mode)."""
    from main import engine
    if hasattr(engine, 'get_pending_setups'):
        return engine.get_pending_setups()
    return []


@router.post("/pending-setups/approve-all")
async def approve_all_setups():
    """Approve all pending setups at once."""
    from main import engine
    if hasattr(engine, 'approve_all_pending'):
        count = await engine.approve_all_pending()
        return {"status": "approved_all", "count": count,
                "message": f"{count} operaciones aprobadas y ejecutadas"}
    raise HTTPException(501, "Manual mode not available")


@router.post("/pending-setups/reject-all")
async def reject_all_setups():
    """Reject all pending setups."""
    from main import engine
    if hasattr(engine, 'pending_setups'):
        pending = [s for s in engine.pending_setups if getattr(s, 'status', 'pending') == "pending"]
        count = 0
        for setup in pending:
            try:
                if engine.reject_setup(setup.id):
                    count += 1
            except Exception as e:
                logger.warning(f"Failed to reject setup {setup.id}: {e}")
        return {"status": "rejected_all", "count": count}
    return {"status": "ok", "count": 0}


@router.post("/pending-setups/{setup_id}/approve")
async def approve_setup(setup_id: str):
    """Approve a pending trade setup for execution."""
    from main import engine
    if hasattr(engine, 'approve_setup'):
        success = await engine.approve_setup(setup_id)
        if success:
            return {"status": "approved", "setup_id": setup_id,
                    "message": "Operación aprobada y ejecutada"}
        raise HTTPException(404, f"Setup {setup_id} not found or expired")
    raise HTTPException(501, "Manual mode not available")


@router.post("/pending-setups/{setup_id}/reject")
async def reject_setup(setup_id: str):
    """Reject a pending trade setup."""
    from main import engine
    if hasattr(engine, 'reject_setup'):
        success = engine.reject_setup(setup_id)
        if success:
            return {"status": "rejected", "setup_id": setup_id,
                    "message": "Operación rechazada"}
        raise HTTPException(404, f"Setup {setup_id} not found")
    raise HTTPException(501, "Manual mode not available")


# ── Positions ─────────────────────────────────────────────────────

@router.get("/positions")
async def get_positions():
    """Get all open positions with details."""
    from main import engine
    status = engine.get_status()
    return status["positions"]


@router.post("/positions/sync")
async def sync_positions_from_broker():
    """Force a reconciliation between broker open trades and local
    position_manager state. Useful when the engine is paused (out-of-hours)
    but the broker still holds positions, or after a redeploy that lost
    in-memory state. Returns the position list AFTER the sync.
    """
    from main import engine
    if engine is None or not hasattr(engine, "_sync_positions_from_broker"):
        raise HTTPException(503, "Engine not ready for sync")
    try:
        await engine._sync_positions_from_broker()
    except Exception as e:
        logger.error(f"Manual position sync failed: {e}")
        raise HTTPException(500, f"Sync failed: {e}")
    status = engine.get_status()
    return {
        "status": "synced",
        "open_positions": len(status["positions"]),
        "positions": status["positions"],
    }


# ── Analysis & Explanations ──────────────────────────────────────

# RT-12 fix: literal /analysis MUST come before parameterized /analysis/{instrument}
@router.get("/analysis")
async def get_all_analyses():
    """Get latest analysis summary for all scanned instruments."""
    from main import engine
    results = []
    for inst, analysis in engine.last_scan_results.items():
        entry = {
            "instrument": inst,
            "score": analysis.score,
            "htf_trend": analysis.htf_trend.value,
            "ltf_trend": analysis.ltf_trend.value,
            "convergence": analysis.htf_ltf_convergence,
            "condition": analysis.htf_condition.value,
            "patterns": analysis.candlestick_patterns,
        }
        # Add strategy detection if available
        if inst in engine.latest_explanations:
            expl = engine.latest_explanations[inst]
            entry["strategy_detected"] = expl.strategy_detected
            entry["confidence_level"] = expl.confidence_level
            entry["recommendation"] = expl.recommendation
        results.append(entry)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


@router.get("/analysis/{instrument}")
async def get_analysis(instrument: str):
    """Get latest analysis for a specific instrument with full explanation."""
    from main import engine
    results = engine.last_scan_results
    if instrument not in results:
        # Build a descriptive message depending on engine state
        if not engine.running and engine.startup_error:
            msg = f"Motor detenido — error de broker: {engine.startup_error[:100]}"
        elif not engine.running:
            msg = "Motor no iniciado — esperando conexión al broker..."
        elif len(results) == 0:
            msg = "Escaneo inicial en progreso — analizando pares..."
        else:
            msg = f"Análisis no disponible para {instrument} — esperando próximo escaneo"
        # Return a default empty analysis instead of 404
        return {
            "instrument": instrument,
            "score": 0,
            "htf_trend": "unknown",
            "ltf_trend": "unknown",
            "convergence": False,
            "condition": "unknown",
            "key_levels": {},
            "ema_values": {},
            "fibonacci": {},
            "patterns": [],
            "elliott_wave": None,
            "message": msg,
        }

    analysis = results[instrument]

    response = {
        "instrument": instrument,
        "score": analysis.score,
        "htf_trend": analysis.htf_trend.value,
        "ltf_trend": analysis.ltf_trend.value,
        "convergence": analysis.htf_ltf_convergence,
        "condition": analysis.htf_condition.value,
        "key_levels": analysis.key_levels,
        "ema_values": analysis.ema_values,
        "fibonacci": analysis.fibonacci_levels,
        "patterns": analysis.candlestick_patterns,
        "chart_patterns": getattr(analysis, 'chart_patterns', []),
        "elliott_wave": getattr(analysis, 'elliott_wave', None),
        # New indicators from course material
        "macd": getattr(analysis, 'macd_values', {}),
        "sma": getattr(analysis, 'sma_values', {}),
        "rsi": getattr(analysis, 'rsi_values', {}),
        "rsi_divergence": getattr(analysis, 'rsi_divergence', None),
        "order_blocks": getattr(analysis, 'order_blocks', []),
        "structure_breaks": getattr(analysis, 'structure_breaks', []),
        "pivot_points": getattr(analysis, 'pivot_points', {}),
    }

    # Add detailed explanation if available
    if instrument in engine.latest_explanations:
        explanation = engine.latest_explanations[instrument]

        # Map each per-TF string list ("levels") into the structured
        # key_levels object the frontend expects. Levels read "Soporte en
        # 1.0234" / "Resistencia en 1.0456" — we partition by keyword.
        def _partition_levels(levels_list):
            supports, resistances = [], []
            for lvl in (levels_list or []):
                if not isinstance(lvl, str):
                    continue
                lower = lvl.lower()
                # Extract first numeric token
                import re as _re
                m = _re.search(r"[-+]?\d+\.?\d*", lvl)
                if not m:
                    continue
                try:
                    value = float(m.group())
                except ValueError:
                    continue
                if "resist" in lower or "supply" in lower or "techo" in lower:
                    resistances.append(value)
                elif "sopor" in lower or "demand" in lower or "piso" in lower:
                    supports.append(value)
            return {"support": supports, "resistance": resistances}

        # Frontend expects `strategy_steps` as {description, met}[]. Our
        # generator produces flat strings — zip each step with the
        # conditions_met list when possible (else default to True, since
        # these are the steps that drove strategy_detected).
        met_set = {s.strip().lower() for s in (explanation.conditions_met or []) if isinstance(s, str)}
        steps_structured = []
        for s in (explanation.strategy_steps or []):
            if isinstance(s, dict):
                steps_structured.append({
                    "description": s.get("description", ""),
                    "met": bool(s.get("met", True)),
                })
            else:
                steps_structured.append({
                    "description": str(s),
                    "met": any(str(s).strip().lower() in m or m in str(s).strip().lower() for m in met_set) if met_set else True,
                })

        strategy_color_map = {
            "BLUE": "BLUE", "BLUE_A": "BLUE", "BLUE_B": "BLUE", "BLUE_C": "BLUE",
            "RED": "RED", "PINK": "PINK", "WHITE": "WHITE", "BLACK": "BLACK",
            "GREEN": "GREEN",
        }
        strategy_name = explanation.strategy_detected or ""
        strategy_color = strategy_color_map.get(strategy_name.upper().replace(" ", "_"), "")

        response["explanation"] = {
            "overall_bias": explanation.overall_bias,
            "confidence_level": explanation.confidence_level,
            "timeframe_analysis": [
                {
                    "timeframe": tf.timeframe,
                    "trend": tf.trend,
                    "observations": tf.key_observations,
                    # Keep legacy `levels` for any existing consumer, plus
                    # the structured `key_levels` the frontend expects.
                    "levels": tf.levels,
                    "key_levels": _partition_levels(tf.levels),
                    "patterns": tf.patterns,
                    "conclusion": tf.conclusion,
                }
                for tf in explanation.timeframe_analysis
            ],
            "strategy_detected": explanation.strategy_detected,
            "strategy_steps": steps_structured,
            "conditions_met": explanation.conditions_met,
            "conditions_missing": explanation.conditions_missing,
            "entry_explanation": explanation.entry_explanation,
            "sl_explanation": explanation.sl_explanation,
            "tp_explanation": explanation.tp_explanation,
            "risk_assessment": explanation.risk_assessment,
            "recommendation": explanation.recommendation,
        }
        # Top-level convenience fields the frontend reads directly.
        response["confidence"] = explanation.confidence_level
        if strategy_name:
            response["strategy"] = {
                "name": strategy_name,
                "color": strategy_color,
                "steps": steps_structured,
                "entry_explanation": explanation.entry_explanation,
                "sl_explanation": explanation.sl_explanation,
                "tp_explanation": explanation.tp_explanation,
                "risk_assessment": explanation.risk_assessment,
            }
        else:
            response["strategy"] = None

    return response


# ── Watchlist ────────────────────────────────────────────────────

@router.get("/watchlist")
async def get_watchlist():
    """Get watchlist with latest scan results."""
    from main import engine
    from config import settings, get_active_watchlist

    watchlist = []
    for instrument in get_active_watchlist():
        entry = {
            "instrument": instrument,
            "score": None,  # null until AI validates — no fake technical scores
            "trend": "unknown",
            "convergence": False,
            "patterns": [],
            "strategy_detected": None,
        }
        if instrument in engine.last_scan_results:
            analysis = engine.last_scan_results[instrument]
            # Always show technical score so the UI has data to display
            # When AI validates a setup, the score is overwritten with the AI score
            entry["score"] = analysis.score
            entry["trend"] = analysis.htf_trend.value
            entry["convergence"] = analysis.htf_ltf_convergence
            entry["patterns"] = analysis.candlestick_patterns
            entry["condition"] = analysis.htf_condition.value

            if instrument in engine.latest_explanations:
                expl = engine.latest_explanations[instrument]
                entry["strategy_detected"] = expl.strategy_detected
                entry["confidence_level"] = expl.confidence_level

            # Add strategy checklist summary (which strategies pass/fail HTF)
            try:
                from strategies.base import get_strategy_checklist
                checklist = get_strategy_checklist(analysis, engine._enabled_strategies)
                entry["strategy_checklist"] = [
                    {
                        "strategy": c["strategy"],
                        "name": c["name"],
                        "htf_passed": c["htf_passed"],
                        "setup_found": c["setup_found"],
                        "met_count": len(c["steps_met"]),
                        "failed_count": len(c["steps_failed"]),
                        "top_failure": c["steps_failed"][0] if c["steps_failed"] else None,
                    }
                    for c in checklist
                ]
            except Exception:
                pass

        watchlist.append(entry)

    watchlist.sort(key=lambda x: x["score"] if x["score"] is not None else -1, reverse=True)
    return watchlist


@router.get("/watchlist/{instrument}/strategies")
async def get_instrument_strategy_checklist(instrument: str):
    """Get step-by-step strategy checklist for a specific instrument.
    Shows which steps of each strategy are met/failed — even when no setup is detected."""
    from main import engine
    from strategies.base import get_strategy_checklist

    if instrument not in engine.last_scan_results:
        raise HTTPException(404, f"No analysis data for {instrument}. Wait for next scan cycle.")

    analysis = engine.last_scan_results[instrument]
    checklist = get_strategy_checklist(analysis, engine._enabled_strategies)
    return {
        "instrument": instrument,
        "score": analysis.score,
        "htf_trend": analysis.htf_trend.value if hasattr(analysis.htf_trend, 'value') else str(analysis.htf_trend),
        "ltf_trend": analysis.ltf_trend.value if hasattr(analysis.ltf_trend, 'value') else str(analysis.ltf_trend),
        "strategies": checklist,
    }


# ── Account ──────────────────────────────────────────────────────

@router.get("/account")
async def get_account():
    """Get account summary from the active broker."""
    from main import engine
    broker = engine.broker
    try:
        summary = await broker.get_account_summary()
        return {
            "balance": summary.balance,
            "equity": summary.equity,
            "unrealized_pnl": summary.unrealized_pnl,
            "margin_used": summary.margin_used,
            "margin_available": summary.margin_available,
            "open_trade_count": summary.open_trade_count,
            "currency": summary.currency,
        }
    except Exception as e:
        raise HTTPException(500, f"Error al obtener cuenta: {str(e)}")


# ── Engine Control ───────────────────────────────────────────────

@router.post("/engine/start")
async def start_engine():
    """Start the trading engine."""
    from main import engine
    import asyncio
    if not engine.running:
        engine.startup_error = ""  # Clear previous error
        # Use the engine's GC-safe registry so the start task can't be
        # collected mid-run under memory pressure (Python event loops hold
        # only weak refs to tasks).
        engine._spawn_bg(engine.start(), name="engine_start")
        return {"status": "starting", "message": "Motor de trading iniciando..."}
    return {"status": "already_running", "message": "El motor ya está en ejecución"}


@router.post("/engine/stop")
async def stop_engine():
    """Stop the trading engine."""
    from main import engine
    await engine.stop()
    return {"status": "stopped", "message": "Motor de trading detenido"}


@router.post("/emergency/close-all")
async def emergency_close_all():
    """Emergency: close all open trades immediately."""
    from main import engine
    broker = engine.broker
    try:
        count = await broker.close_all_trades()
    except Exception as e:
        logger.error(f"Emergency close-all broker call failed: {e}")
        raise HTTPException(503, f"Error al cerrar posiciones: {str(e)}")

    # Record trade results with actual PnL before clearing state (CLAUDE.md Rule #4, BUG-06 fix)
    if hasattr(engine, 'risk_manager') and hasattr(engine, 'position_manager'):
        rm = engine.risk_manager
        pm = engine.position_manager
        balance = getattr(rm, '_current_balance', 1.0) or 1.0
        for composite_key, risk_pct in list(rm._active_risks.items()):
            # _active_risks is keyed as "instrument:trade_id"; split to recover both
            parts = composite_key.split(":", 1)
            if len(parts) == 2:
                inst, real_trade_id = parts[0], parts[1]
            else:
                inst, real_trade_id = "unknown", composite_key
            try:
                # Compute actual PnL from position entry price and last known price
                pnl_pct = 0.0
                pos = pm.positions.get(real_trade_id)
                if pos is not None:
                    try:
                        price_data = await broker.get_current_price(pos.instrument)
                        close_price = price_data.bid if pos.direction == "BUY" else price_data.ask
                        pnl_per_unit = (close_price - pos.entry_price) if pos.direction == "BUY" else (pos.entry_price - close_price)
                        pnl_dollars = pnl_per_unit * abs(pos.units) if pos.units else 0.0
                        pnl_pct = pnl_dollars / balance if balance > 0 else 0.0
                    except Exception as pe:
                        logger.warning(f"Could not compute PnL for {real_trade_id}: {pe}")
                rm.record_trade_result(real_trade_id, inst, pnl_pct)
            except Exception as e:
                logger.warning(f"Failed to record emergency close for {composite_key}: {e}")

    # Re-sync state from broker instead of blindly clearing
    try:
        open_trades = await broker.get_open_trades()
        if not open_trades:
            if hasattr(engine, 'position_manager'):
                engine.position_manager.positions.clear()
            if hasattr(engine, 'risk_manager'):
                engine.risk_manager._active_risks.clear()
    except Exception as e:
        logger.warning(f"Post-emergency state sync failed: {e}")
    return {
        "status": "all_trades_closed",
        "count": count,
        "message": f"Emergencia: {count} operaciones cerradas",
    }


# ── Trade History ────────────────────────────────────────────────

@router.get("/history")
async def get_trade_history(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    instrument: Optional[str] = None,
    strategy: Optional[str] = None,
):
    """Get trade history with optional filters."""
    from main import db
    if db is None:
        return []
    try:
        trades = await db.get_trade_history(
            limit=limit, offset=offset,
            instrument=instrument, strategy=strategy,
        )
        for t in trades:
            t["strategy_color"] = t.get("strategy", "")
        return trades
    except Exception as e:
        raise HTTPException(500, f"Error al obtener historial: {str(e)}")


@router.get("/history/stats")
async def get_performance_stats(days: int = Query(30, ge=1, le=365)):
    """Get trading performance statistics."""
    from main import db
    if db is None:
        return {
            "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
            "win_rate": 0, "total_pnl": 0, "avg_risk_reward": 0,
            "best_trade": 0, "worst_trade": 0,
        }
    try:
        return await db.get_performance_summary(days=days)
    except Exception as e:
        raise HTTPException(500, f"Error al obtener estadísticas: {str(e)}")


@router.get("/history/daily")
async def get_daily_stats(date: Optional[str] = None):
    """Get daily trading statistics."""
    from datetime import datetime, timezone
    from main import db
    if db is None:
        return {
            "date": date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
            "total_pnl": 0.0, "total_pips": 0.0, "max_drawdown": 0.0,
            "best_trade_pnl": 0.0, "worst_trade_pnl": 0.0,
        }
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        return await db.get_daily_stats(date)
    except Exception as e:
        raise HTTPException(500, f"Error al obtener stats diarios: {str(e)}")


# ── Trade Notes ──────────────────────────────────────────────────

class TradeNotesRequest(BaseModel):
    notes: str


@router.put("/history/{trade_id}/notes")
async def update_trade_notes(trade_id: str, request: TradeNotesRequest):
    """Update journal notes for a specific trade."""
    from main import db
    if db is None:
        raise HTTPException(503, "Database not available")
    try:
        updated = await db.update_trade_notes(trade_id, request.notes)
        if not updated:
            raise HTTPException(404, f"Trade {trade_id} not found")
        return {
            "trade_id": trade_id,
            "notes": request.notes,
            "message": "Notas actualizadas",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error al actualizar notas: {str(e)}")


# ── Equity Curve ─────────────────────────────────────────────────

@router.get("/equity-curve")
async def get_equity_curve(days: int = Query(30, ge=1, le=365)):
    """Get equity curve data (snapshots) for the last N days."""
    from main import db
    if db is None:
        return []
    try:
        return await db.get_equity_curve(days=days)
    except Exception as e:
        raise HTTPException(500, f"Error al obtener curva de equity: {str(e)}")


# ── Broker Selection ─────────────────────────────────────────────

@router.get("/broker")
async def get_current_broker():
    """Get info about the currently active broker."""
    from main import engine
    broker = engine.broker
    broker_type = getattr(broker, 'broker_type', None)

    # Check if broker session is active (non-blocking — just check tokens)
    connected = False
    try:
        cst = getattr(broker, '_cst', None)
        sec = getattr(broker, '_security_token', None)
        connected = bool(cst and sec)
        # Also check if engine is running as a proxy for "connected"
        if not connected and engine.running:
            connected = True
    except Exception:
        connected = False

    return {
        "broker": broker_type.value if broker_type else "capital",
        "connected": connected,
        "available_brokers": [
            {
                "id": "capital",
                "name": "Capital.com",
                "description": "Multi-activo: Forex, Acciones, Índices, Materias Primas. API REST gratuita.",
                "safe_in_colombia": True,
                "demo_available": True,
                "implemented": True,
            },
            {
                "id": "icmarkets",
                "name": "IC Markets",
                "description": "ECN broker australiano con spreads bajos.",
                "safe_in_colombia": True,
                "demo_available": True,
                "implemented": False,
            },
            {
                "id": "pepperstone",
                "name": "Pepperstone",
                "description": "Broker australiano regulado con MT4/MT5.",
                "safe_in_colombia": True,
                "demo_available": True,
                "implemented": False,
            },
        ],
    }


@router.post("/broker")
async def set_broker(request: BrokerSelectionRequest):
    """Switch the active broker. Requires restart to take effect."""
    supported = {"capital", "ibkr"}
    if request.broker.lower() not in supported:
        # 400 Bad Request: client sent a value outside the supported set.
        # 501 is for missing server implementations, not input validation.
        raise HTTPException(
            400,
            f"Broker '{request.broker}' no soportado. "
            f"Disponibles: capital, ibkr.",
        )
    return {
        "broker": request.broker,
        "status": "pending_restart",
        "message": f"Broker {request.broker} seleccionado. Cambia ACTIVE_BROKER={request.broker.lower()} en las variables de entorno y haz re-deploy para aplicar.",
    }


# ── Candle Data (for charts) ────────────────────────────────────

@router.get("/candles/{instrument}")
async def get_candles(
    instrument: str,
    granularity: str = Query("H1", description="Timeframe: M5, M15, H1, H4, D, W"),
    count: int = Query(200, ge=10, le=5000),
):
    """Get candlestick data for charting."""
    from main import engine
    broker = engine.broker
    try:
        candles = await broker.get_candles(instrument, granularity, count)
        return [
            {
                "time": c.time,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
                "complete": c.complete,
            }
            for c in candles
        ]
    except ConnectionError as e:
        raise HTTPException(503, f"Broker desconectado: {str(e)}")
    except Exception as e:
        error_msg = str(e)
        lower = error_msg.lower()
        if "auth" in lower or "session" in lower:
            raise HTTPException(503, f"Error de autenticación con broker: {error_msg}")
        # Invalid instrument → 404
        not_found_indicators = ['not found', 'invalid', 'unknown', 'no such', 'epic',
                                '404', 'does not exist', 'bad request', '400']
        if any(ind in lower for ind in not_found_indicators):
            raise HTTPException(404, f"Instrument '{instrument}' not found")
        raise HTTPException(500, f"Error al obtener velas: {error_msg}")


@router.get("/admin/search-markets")
async def admin_search_markets(term: str, limit: int = 20):
    """Search Capital.com's market catalog by free-text term. Used to
    research the correct epic for blocklisted instruments — e.g. Capital.com
    offers a "Nasdaq 100" epic under "US100" not "USTEC".

    Returns lightweight market records (epic, name, type, bid, offer) so the
    operator can visually pick the right one and update
    ``_EPIC_MAP_OVERRIDE``. This endpoint is authenticated via the standard
    X-API-Key so only Sergio can hit it.
    """
    from main import engine
    broker = engine.broker
    try:
        data = await broker._get("/api/v1/markets", params={"searchTerm": term, "limit": limit})
    except Exception as e:
        raise HTTPException(500, f"Search failed: {e}")
    markets = data.get("markets", [])
    return [
        {
            "epic": m.get("epic"),
            "name": m.get("instrumentName"),
            "type": m.get("instrumentType"),
            "symbol": m.get("symbol"),
            "bid": m.get("bid"),
            "offer": m.get("offer"),
            "streaming": m.get("streamingPricesAvailable"),
            "market_status": m.get("marketStatus"),
            "expiry": m.get("expiry"),
        }
        for m in markets
    ]


@router.post("/admin/blocklist/remove")
async def admin_unblocklist(instrument: str):
    """Remove an instrument from the in-memory epic blocklist. Use after
    adding a correct override so `_resolve_epic` can re-cache cleanly.
    Does NOT clear the cache — that happens on the next resolution."""
    from main import engine
    broker = engine.broker
    if not hasattr(broker, "_epic_blocklist"):
        raise HTTPException(503, "Broker does not expose blocklist")
    existed = instrument in broker._epic_blocklist
    broker._epic_blocklist.discard(instrument)
    broker._epic_cache.pop(instrument, None)
    return {"instrument": instrument, "was_blocklisted": existed, "cleared": True}


@router.get("/price/{instrument}")
async def get_price(instrument: str):
    """Get current bid/ask price for an instrument."""
    from main import engine
    broker = engine.broker
    try:
        price = await broker.get_current_price(instrument)
        return {
            "instrument": instrument,
            "bid": price.bid,
            "ask": price.ask,
            "spread": price.spread,
            "time": price.time,
        }
    except Exception as e:
        err_msg = str(e).lower()
        # Not found errors → 404 (detect various patterns)
        not_found_indicators = ['not found', 'invalid', 'unknown', 'no such', 'epic',
                                '404', 'does not exist', 'bad request', '400']
        if any(ind in err_msg for ind in not_found_indicators):
            raise HTTPException(404, f"Instrument '{instrument}' not found")
        raise HTTPException(500, f"Error al obtener precio: {str(e)}")


# ── Strategy Selection ────────────────────────────────────────────

@router.get("/strategies/config")
async def get_strategy_config():
    """Get the current strategy enablement configuration."""
    from main import engine
    return engine.get_enabled_strategies()


@router.put("/strategies/config")
async def set_strategy_config(request: StrategyConfigRequest):
    """Update which strategies are enabled for trading.

    Send only the fields you want to change, or send all fields for a full update.
    Example: {"BLUE": true, "BLUE_A": true, "BLUE_B": false, "BLUE_C": true, "RED": true}
    """
    from main import engine
    # Build update dict from non-None fields
    update = {k: v for k, v in request.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(400, "No strategies specified")

    # Merge with current config
    current = engine.get_enabled_strategies()
    current.update(update)
    engine.set_enabled_strategies(current)

    enabled = [k for k, v in current.items() if v]
    return {
        "config": current,
        "enabled": enabled,
        "message": f"Estrategias actualizadas. Activas: {', '.join(enabled)}",
    }


# ── Strategies Info ──────────────────────────────────────────────

@router.get("/strategies")
async def get_strategies_info():
    """Get info about all available trading strategies."""
    return [
        {
            "color": "BLUE",
            "name": "Cambio de tendencia en 1H",
            "description": "Detecta cambios de tendencia en gráfico horario. 3 variantes (A/B/C). "
                           "TP en EMA 50 de 4H.",
            "wave": "Onda 1-2 de Elliott",
            "risk_reward_avg": 1.65,
            "variants": ["BLUE_A (Doble suelo)", "BLUE_B (Estándar)", "BLUE_C (Rechazo EMA 4H)"],
            "steps": 7,
        },
        {
            "color": "RED",
            "name": "Cambio de tendencia en 4H",
            "description": "Evolución de Blue. Detecta cambios de tendencia en gráfico de 4 horas. "
                           "TP en máximo anterior o extensión Fibonacci.",
            "wave": "Onda 2-3 de Elliott",
            "risk_reward_avg": 2.0,
            "variants": [],
            "steps": 7,
        },
        {
            "color": "PINK",
            "name": "Patrón correctivo de continuación",
            "description": "Detecta patrones correctivos (cuña/triángulo/canal) en 1H dentro de "
                           "una tendencia establecida en 4H.",
            "wave": "Onda 4→5 de Elliott",
            "risk_reward_avg": 1.8,
            "variants": [],
            "steps": 6,
        },
        {
            "color": "WHITE",
            "name": "Continuación post-Pink",
            "description": "Entrada después de una configuración Pink completada. "
                           "Impulso + pullback en 1H.",
            "wave": "Onda 3 de Onda 5 de Elliott",
            "risk_reward_avg": 1.5,
            "variants": [],
            "steps": 6,
        },
        {
            "color": "BLACK",
            "name": "Anticipación contratendencia",
            "description": "Estrategia contra tendencia. Requiere soporte/resistencia diario, "
                           "sobrecompra/sobreventa en 4H, patrón de reversión en 1H. R:R mínimo 2:1.",
            "wave": "Onda 1 de Elliott (nuevo ciclo)",
            "risk_reward_avg": 2.8,
            "variants": [],
            "steps": 7,
        },
        {
            "color": "GREEN",
            "name": "Dirección semanal + patrón diario",
            "description": "La más lucrativa. Usa dirección semanal, corrección en diario, "
                           "y entrada precisa en 15M. Puede lograr R:R de 10:1.",
            "wave": "Corrección semanal completada",
            "risk_reward_avg": 5.0,
            "variants": [],
            "steps": 6,
        },
    ]


# ── Notifications (for Electron native notifications) ─────────

@router.get("/notifications")
async def get_notifications():
    """Get unread notifications for native OS notifications."""
    from main import engine
    if hasattr(engine, 'get_unread_notifications'):
        return engine.get_unread_notifications()
    return []


# ── Engine Logs (last N lines from loguru file) ────────────────

@router.get("/logs")
async def get_engine_logs(
    lines: int = Query(100, ge=10, le=5000),
    tail: int = Query(0, ge=0, le=5000),
    date: Optional[str] = Query(None, description="YYYY-MM-DD (UTC) — defaults to today"),
    grep: Optional[str] = Query(None, description="Case-insensitive substring filter"),
):
    """Get the last N lines of engine logs for debugging.

    Audit M8: use UTC when building today's filename so it matches loguru's
    ``{time:YYYY-MM-DD}`` rotation (UTC in containers).

    Improvements:
    - ``date`` param (UTC, YYYY-MM-DD) to retrieve a specific day's rotated log.
    - ``grep`` param for a case-insensitive substring filter (applied before tail).
    - ``tail`` alias for ``lines`` (whichever is higher wins, default 100).
    - ``lines`` cap raised to 5000 to allow deep forensic pulls.
    """
    import os
    import re

    effective = max(lines, tail)
    target_date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Validate date format (YYYY-MM-DD) to prevent path injection
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", target_date):
        return {"error": f"Invalid date format: {target_date!r}. Expected YYYY-MM-DD."}

    log_dirs = ["logs", "/app/logs"]
    for log_dir in log_dirs:
        if not os.path.isdir(log_dir):
            continue
        # Priority: exact date match; if missing, fall back to newest .log
        candidates = [os.path.join(log_dir, f"atlas_{target_date}.log")]
        try:
            for f in sorted(os.listdir(log_dir), reverse=True):
                if f.endswith(".log"):
                    candidates.append(os.path.join(log_dir, f))
        except Exception:
            pass
        for lp in candidates:
            if os.path.isfile(lp):
                try:
                    with open(lp, "r") as f:
                        all_lines = f.readlines()
                    if grep:
                        needle = grep.lower()
                        filtered = [l for l in all_lines if needle in l.lower()]
                    else:
                        filtered = all_lines
                    return {
                        "file": lp,
                        "total_lines": len(all_lines),
                        "filtered_lines": len(filtered) if grep else None,
                        "returned_lines": min(effective, len(filtered)),
                        "date_requested": target_date,
                        "lines": [l.rstrip() for l in filtered[-effective:]],
                    }
                except Exception as e:
                    return {"error": str(e), "file": lp}

    return {"error": "No log file found", "searched": log_dirs, "date_requested": target_date}


# ── Economic Calendar ───────────────────────────────────────────

@router.get("/calendar")
async def get_economic_calendar():
    """Get today's economic events that affect trading."""
    from main import engine
    try:
        if hasattr(engine, 'news_filter') and engine.news_filter:
            events = await engine.news_filter.get_todays_events()
            has_news, desc = await engine.news_filter.has_upcoming_news()
            return {
                "events": events,
                "news_active": has_news,
                "current_warning": desc or "",
            }
    except Exception as e:
        logger.warning(f"Calendar endpoint error: {e}")
    return {"events": [], "news_active": False, "current_warning": ""}


# ── News Headlines ─────────────────────────────────────────────

@router.get("/news")
async def get_news_headlines(limit: int = Query(10, ge=1, le=50)):
    """Get recent forex news headlines."""
    from main import engine
    if hasattr(engine, 'news_filter') and hasattr(engine.news_filter, 'get_news_headlines'):
        return await engine.news_filter.get_news_headlines(limit=limit)
    return []


# ── Risk Configuration ─────────────────────────────────────────

class RiskConfigRequest(BaseModel):
    risk_day_trading: Optional[float] = None
    risk_scalping: Optional[float] = None
    risk_swing: Optional[float] = None
    max_total_risk: Optional[float] = None
    correlated_risk_pct: Optional[float] = None
    min_rr_ratio: Optional[float] = None
    move_sl_to_be_pct_to_tp1: Optional[float] = None
    # Drawdown management (ch18.7)
    drawdown_method: Optional[str] = None  # "fixed_1pct", "variable", "fixed_levels"
    # Delta algorithm (ch18.8)
    delta_enabled: Optional[bool] = None
    delta_parameter: Optional[float] = None
    # Scale-in
    scale_in_require_be: Optional[bool] = None


# ── Trading Profiles ─────────────────────────────────────────────

@router.get("/profiles")
async def get_profiles():
    """List available trading profile presets."""
    from config import TRADING_PROFILES, settings
    profiles = []
    for profile_id, profile in TRADING_PROFILES.items():
        profiles.append({
            "id": profile_id,
            "name": profile["name"],
            "description": profile["description"],
        })
    return {"profiles": profiles}


class ApplyProfileRequest(BaseModel):
    profile_id: str


@router.post("/profiles/apply")
async def apply_profile(request: ApplyProfileRequest):
    """Apply a trading profile preset — updates all settings at once."""
    from config import apply_trading_profile, TRADING_PROFILES
    from main import engine
    if request.profile_id not in TRADING_PROFILES:
        available = list(TRADING_PROFILES.keys())
        raise HTTPException(400, f"Perfil '{request.profile_id}' no existe. Disponibles: {available}")

    applied = apply_trading_profile(request.profile_id)
    profile = TRADING_PROFILES[request.profile_id]

    # Also update watchlist categories if the profile specifies them
    from config import settings
    if "active_watchlist_categories" in applied:
        settings.active_watchlist_categories = applied["active_watchlist_categories"]
    if engine is not None:
        if "enabled_strategies" in applied:
            engine.set_enabled_strategies(applied["enabled_strategies"])
        if "scalping_enabled" in applied:
            engine.toggle_scalping(bool(applied["scalping_enabled"]))

    return {
        "profile": request.profile_id,
        "name": profile["name"],
        "applied_settings": len(applied),
        "message": f"Perfil '{profile['name']}' aplicado correctamente ({len(applied)} ajustes)",
    }


class ApplyFundedPresetRequest(BaseModel):
    preset_id: str


@router.post("/funded/apply-preset")
async def apply_funded_preset_endpoint(request: ApplyFundedPresetRequest):
    """Apply a funded account preset (FTMO, Bitfunded, etc.)."""
    from config import apply_funded_preset, FUNDED_ACCOUNT_PRESETS
    if request.preset_id not in FUNDED_ACCOUNT_PRESETS:
        available = list(FUNDED_ACCOUNT_PRESETS.keys())
        raise HTTPException(400, f"Preset '{request.preset_id}' no existe. Disponibles: {available}")

    applied = apply_funded_preset(request.preset_id)
    preset = FUNDED_ACCOUNT_PRESETS[request.preset_id]

    return {
        "preset": request.preset_id,
        "name": preset["name"],
        "applied_settings": len(applied),
        "message": f"Preset '{preset['name']}' aplicado correctamente ({len(applied)} ajustes)",
    }


@router.get("/funded/presets")
async def list_funded_presets():
    """List available funded account presets."""
    from config import FUNDED_ACCOUNT_PRESETS
    return {
        preset_id: {
            "name": preset["name"],
            "description": preset["description"],
        }
        for preset_id, preset in FUNDED_ACCOUNT_PRESETS.items()
    }


@router.get("/risk-config")
async def get_risk_config():
    """Get current risk management configuration."""
    from config import settings
    return {
        "risk_day_trading": settings.risk_day_trading,
        "risk_scalping": settings.risk_scalping,
        "risk_swing": settings.risk_swing,
        "max_total_risk": round(settings.max_total_risk, 4),
        "correlated_risk_pct": settings.correlated_risk_pct,
        "min_rr_ratio": settings.min_rr_ratio,
        # Strategy-specific R:R minimums (per TradingLab — BLACK/GREEN ≥ 2.0)
        "min_rr_black": getattr(settings, "min_rr_black", 2.0),
        "min_rr_green": getattr(settings, "min_rr_green", 2.0),
        "min_rr_blue_c": getattr(settings, "min_rr_blue_c", 2.0),
        "move_sl_to_be_pct_to_tp1": settings.move_sl_to_be_pct_to_tp1,
        "trading_start_hour": settings.trading_start_hour,
        "trading_end_hour": settings.trading_end_hour,
        "close_before_friday_hour": settings.close_before_friday_hour,
        "avoid_news_minutes_before": settings.avoid_news_minutes_before,
        "avoid_news_minutes_after": settings.avoid_news_minutes_after,
        "avoid_news_minutes_before_swing": settings.avoid_news_minutes_before_swing,
        "avoid_news_minutes_after_swing": settings.avoid_news_minutes_after_swing,
        "news_impact_filter": settings.news_impact_filter,
        "crypto_position_mgmt_style": settings.crypto_position_mgmt_style,
        # Drawdown management (ch18.7)
        "drawdown_method": settings.drawdown_method,
        "drawdown_level_1": settings.drawdown_level_1,
        "drawdown_level_2": settings.drawdown_level_2,
        "drawdown_level_3": settings.drawdown_level_3,
        "drawdown_risk_1": settings.drawdown_risk_1,
        "drawdown_risk_2": settings.drawdown_risk_2,
        "drawdown_risk_3": settings.drawdown_risk_3,
        # Delta algorithm (ch18.8)
        "delta_enabled": settings.delta_enabled,
        "delta_parameter": settings.delta_parameter,
        "delta_max_risk": settings.delta_max_risk,
        # Position management
        "be_trigger_method": settings.be_trigger_method,
        "position_management_style": settings.position_management_style,
        # Scale-in rule
        "scale_in_require_be": settings.scale_in_require_be,
        # Friday trading cutoff
        "no_new_trades_friday_hour": settings.no_new_trades_friday_hour,
    }


@router.get("/risk-status")
async def get_risk_status():
    """Get live risk status including drawdown and delta algorithm state."""
    from main import engine
    if engine is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    try:
        risk_mgr = engine.risk_manager
        await risk_mgr.update_balance_tracking()
        return risk_mgr.get_risk_status()
    except Exception as e:
        logger.error(f"Risk status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/risk-config")
async def set_risk_config(request: RiskConfigRequest):
    """Update risk management configuration at runtime."""
    from config import settings
    import json, os, tempfile

    updates = {}
    if request.risk_day_trading is not None:
        if not (0.001 <= request.risk_day_trading <= 0.10):
            raise HTTPException(400, "risk_day_trading debe estar entre 0.1% y 10%")
        settings.risk_day_trading = request.risk_day_trading
        updates["risk_day_trading"] = request.risk_day_trading

    if request.risk_scalping is not None:
        if not (0.001 <= request.risk_scalping <= 0.05):
            raise HTTPException(400, "risk_scalping debe estar entre 0.1% y 5%")
        settings.risk_scalping = request.risk_scalping
        updates["risk_scalping"] = request.risk_scalping

    if request.risk_swing is not None:
        if not (0.005 <= request.risk_swing <= 0.10):
            raise HTTPException(400, "risk_swing debe estar entre 0.5% y 10%")
        settings.risk_swing = request.risk_swing
        updates["risk_swing"] = request.risk_swing

    if request.max_total_risk is not None:
        # BUG-08 fix: hard cap at 10% to prevent catastrophic risk exposure
        if request.max_total_risk > 0.10:
            raise HTTPException(400, "max_total_risk no puede superar 10% (0.10) — límite de seguridad")
        if not (0.01 <= request.max_total_risk <= 0.10):
            raise HTTPException(400, "max_total_risk debe estar entre 1% y 10%")
        settings.max_total_risk = request.max_total_risk
        updates["max_total_risk"] = request.max_total_risk

    if request.correlated_risk_pct is not None:
        if not (0.001 <= request.correlated_risk_pct <= 0.05):
            raise HTTPException(400, "correlated_risk_pct debe estar entre 0.1% y 5%")
        settings.correlated_risk_pct = request.correlated_risk_pct
        updates["correlated_risk_pct"] = request.correlated_risk_pct

    if request.min_rr_ratio is not None:
        if not (0.5 <= request.min_rr_ratio <= 5.0):
            raise HTTPException(400, "min_rr_ratio debe estar entre 0.5 y 5.0")
        settings.min_rr_ratio = request.min_rr_ratio
        updates["min_rr_ratio"] = request.min_rr_ratio

    if request.move_sl_to_be_pct_to_tp1 is not None:
        if not (0.1 <= request.move_sl_to_be_pct_to_tp1 <= 0.9):
            raise HTTPException(400, "move_sl_to_be_pct_to_tp1 debe estar entre 10% y 90% del recorrido a TP1")
        settings.move_sl_to_be_pct_to_tp1 = request.move_sl_to_be_pct_to_tp1
        updates["move_sl_to_be_pct_to_tp1"] = request.move_sl_to_be_pct_to_tp1

    # Drawdown management (ch18.7)
    if request.drawdown_method is not None:
        valid_methods = ("fixed_1pct", "variable", "fixed_levels")
        if request.drawdown_method not in valid_methods:
            raise HTTPException(400, f"drawdown_method debe ser uno de: {valid_methods}")
        settings.drawdown_method = request.drawdown_method
        updates["drawdown_method"] = request.drawdown_method

    # Delta algorithm (ch18.8)
    if request.delta_enabled is not None:
        settings.delta_enabled = request.delta_enabled
        updates["delta_enabled"] = request.delta_enabled

    if request.delta_parameter is not None:
        if not (0.1 <= request.delta_parameter <= 0.95):
            raise HTTPException(400, "delta_parameter debe estar entre 0.10 y 0.95")
        settings.delta_parameter = request.delta_parameter
        updates["delta_parameter"] = request.delta_parameter

    # Scale-in
    if request.scale_in_require_be is not None:
        settings.scale_in_require_be = request.scale_in_require_be
        updates["scale_in_require_be"] = request.scale_in_require_be

    if not updates:
        raise HTTPException(400, "No se especificaron cambios")

    # Persist to data/risk_config.json
    _backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(_backend_dir, "data", "risk_config.json")
    existing = {}
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                existing = json.load(f)
        except Exception:
            pass
    existing.update(updates)
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(config_path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(existing, f, indent=2)
        os.replace(tmp_path, config_path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return {
        "updated": updates,
        "message": f"Configuración de riesgo actualizada: {', '.join(updates.keys())}",
    }


# ── Alert Configuration ────────────────────────────────────────

class AlertConfigRequest(BaseModel):
    telegram_enabled: Optional[bool] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    discord_enabled: Optional[bool] = None
    discord_webhook_url: Optional[str] = None
    email_enabled: Optional[bool] = None
    email_smtp_server: Optional[str] = None
    email_smtp_port: Optional[int] = None
    email_username: Optional[str] = None
    email_password: Optional[str] = None
    email_recipient: Optional[str] = None
    gmail_enabled: Optional[bool] = None
    gmail_sender: Optional[str] = None
    gmail_recipient: Optional[str] = None
    gmail_client_id: Optional[str] = None
    gmail_client_secret: Optional[str] = None
    gmail_refresh_token: Optional[str] = None
    notify_trade_executed: Optional[bool] = None
    notify_setup_pending: Optional[bool] = None
    notify_setup_rejected: Optional[bool] = None
    notify_trade_closed: Optional[bool] = None
    notify_daily_summary: Optional[bool] = None


@router.get("/alerts/config")
async def get_alert_config():
    """Get current alert/notification channel configuration."""
    from main import engine
    if hasattr(engine, 'alert_manager'):
        return engine.alert_manager.get_config()
    return {"telegram_enabled": False, "discord_enabled": False, "email_enabled": False, "gmail_enabled": False}


@router.put("/alerts/config")
async def set_alert_config(request: AlertConfigRequest):
    """Update alert channel configuration."""
    from main import engine
    if not hasattr(engine, 'alert_manager'):
        raise HTTPException(501, "Alert manager not available")

    from core.alerts import AlertConfig, _SENSITIVE_FIELDS
    current = engine.alert_manager._config

    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    for key, value in updates.items():
        if hasattr(current, key):
            # Skip masked values (e.g. "*****abcd") to prevent overwriting real secrets
            if key in _SENSITIVE_FIELDS and isinstance(value, str) and value.startswith("*"):
                continue
            setattr(current, key, value)

    engine.alert_manager.update_config(current)
    return {
        "config": engine.alert_manager.get_config(),
        "message": f"Configuración de alertas actualizada",
    }


@router.post("/alerts/test/{channel}")
async def test_alert_channel(channel: str):
    """Send a test notification to verify channel configuration."""
    from main import engine
    if not hasattr(engine, 'alert_manager'):
        raise HTTPException(501, "Alert manager not available")

    from core.alerts import AlertChannel
    try:
        ch = AlertChannel(channel.lower())
    except ValueError:
        raise HTTPException(400, f"Canal no válido: {channel}. Usa: telegram, discord, email, gmail")

    success = await engine.alert_manager.test_channel(ch)
    if success:
        return {"status": "ok", "message": f"Mensaje de prueba enviado a {channel}"}
    raise HTTPException(500, f"Error al enviar mensaje de prueba a {channel}")


# ── Backtesting ────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    instrument: str = Field(..., min_length=1, max_length=32)
    start_date: str  # ISO format YYYY-MM-DD
    end_date: str    # ISO format YYYY-MM-DD
    initial_balance: float = Field(10000.0, gt=0, le=1_000_000_000)
    risk_per_trade: float = Field(0.01, gt=0, le=0.10)
    slippage_pips: float = Field(0.5, ge=0, le=50)
    spread_pips: float = Field(1.0, ge=0, le=50)
    enabled_strategies: Optional[Dict[str, bool]] = None


@router.post("/backtest")
async def run_backtest(request: BacktestRequest):
    """Run a backtest on historical data for a specific instrument."""
    from main import engine
    from datetime import datetime

    # Validate date format before running backtest (returns 422 instead of 500)
    try:
        start_dt = datetime.strptime(request.start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(request.end_date, "%Y-%m-%d")
        if end_dt <= start_dt:
            raise HTTPException(422, "end_date must be after start_date")
    except ValueError as ve:
        raise HTTPException(422, f"Invalid date format (expected YYYY-MM-DD): {ve}")

    try:
        from core.backtester import Backtester, BacktestConfig
    except ImportError as e:
        raise HTTPException(501, f"Backtester not available: {e}")

    try:
        config = BacktestConfig(
            instrument=request.instrument,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_balance=request.initial_balance,
            risk_per_trade=request.risk_per_trade,
            slippage_pips=request.slippage_pips,
            spread_pips=request.spread_pips,
            enabled_strategies=request.enabled_strategies or engine.get_enabled_strategies(),
        )

        backtester = Backtester(engine.broker)
        # Bug fix R27: run backtest with timeout to prevent blocking event loop
        import asyncio
        try:
            result = await asyncio.wait_for(backtester.run(config), timeout=120.0)
        except asyncio.TimeoutError:
            raise HTTPException(408, "Backtest timed out after 120 seconds. Try a shorter period.")
        import math
        def _safe(v):
            if isinstance(v, float) and (math.isinf(v) or math.isnan(v)):
                return 0.0
            if isinstance(v, dict):
                return {k: _safe(vv) for k, vv in v.items()}
            if isinstance(v, list):
                return [_safe(vv) for vv in v]
            return v
        return {
            "total_trades": result.total_trades,
            "winning_trades": result.winning_trades,
            "losing_trades": result.losing_trades,
            "break_even_trades": result.break_even_trades,
            "win_rate": _safe(result.win_rate),
            "total_pnl": _safe(result.total_pnl),
            "max_drawdown": _safe(result.max_drawdown),
            "max_drawdown_pct": _safe(result.max_drawdown_pct),
            "sharpe_ratio": _safe(result.sharpe_ratio),
            "sortino_ratio": _safe(result.sortino_ratio),
            "profit_factor": _safe(result.profit_factor),
            "avg_rr_achieved": _safe(result.avg_rr_achieved),
            "final_balance": _safe(result.final_balance),
            "duration_days": result.duration_days,
            "avg_bars_held": _safe(result.avg_bars_held),
            "best_trade_pnl": _safe(result.best_trade_pnl),
            "worst_trade_pnl": _safe(result.worst_trade_pnl),
            "warnings": list(result.warnings or []),
            "equity_curve": _safe(result.equity_curve),
            "by_strategy": _safe(result.by_strategy),
            "by_instrument": _safe(result.by_instrument),
            "trades": [
                {
                    "instrument": t.instrument,
                    "strategy": t.strategy,
                    "direction": t.direction,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "pnl": t.pnl,
                    "pnl_pips": t.pnl_pips,
                    "rr_achieved": t.risk_reward_achieved,
                    "exit_reason": t.exit_reason,
                    "entry_time": t.entry_time,
                    "exit_time": t.exit_time,
                }
                for t in result.trades
            ],
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Error en backtest: {str(e)}")


# ── Scalping Module (Workshop de Scalping) ──────────────────────

class ScalpingToggleRequest(BaseModel):
    enabled: bool


@router.post("/scalping/toggle")
async def toggle_scalping(request: ScalpingToggleRequest):
    """Enable or disable scalping mode.

    Persists the choice to ``data/risk_config.json`` so it survives container
    restarts (added 2026-04-23 after a redeploy reverted scalping_enabled
    silently — _load_risk_overrides already accepts the key in
    _ALLOWED_RISK_KEYS but the previous endpoint only mutated memory).
    """
    from main import engine
    from config import settings as _s
    if not hasattr(engine, 'toggle_scalping'):
        raise HTTPException(501, "Scalping module not available")
    engine.toggle_scalping(request.enabled)
    _s.scalping_enabled = request.enabled

    # Persist to risk_config.json (atomic, preserves other keys)
    import json, os, tempfile
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    risk_path = os.path.join(backend_dir, "data", "risk_config.json")
    overrides: dict = {}
    if os.path.exists(risk_path):
        try:
            with open(risk_path) as f:
                overrides = json.load(f)
            if not isinstance(overrides, dict):
                overrides = {}
        except Exception as e:
            logger.warning(f"risk_config.json unreadable ({e}); aborting scalping save")
            raise HTTPException(500, "Config file corrupted")
    overrides["scalping_enabled"] = bool(request.enabled)
    os.makedirs(os.path.dirname(risk_path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(risk_path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(overrides, f, indent=2)
        os.replace(tmp, risk_path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    status = "activado" if request.enabled else "desactivado"
    return {
        "scalping_enabled": request.enabled,
        "scan_interval": engine.scan_interval,
        "message": f"Modo scalping {status}",
    }


@router.get("/scalping/status")
async def get_scalping_status():
    """Get current scalping module status.

    Returns:
    - enabled: whether scalping mode is active
    - daily_dd: today's scalping drawdown as fraction
    - total_dd: total scalping drawdown from peak
    - limits: configured max daily and total DD
    - setups_found: scalping setups detected this session
    """
    from main import engine
    from config import settings

    scalping_status = {}
    if hasattr(engine, 'scalping_analyzer') and engine.scalping_analyzer:
        scalping_status = engine.scalping_analyzer.get_scalping_status()

    return {
        "enabled": settings.scalping_enabled,
        "daily_dd": getattr(engine, '_scalping_daily_dd', 0.0),
        "total_dd": getattr(engine, '_scalping_total_dd', 0.0),
        "max_daily_dd": settings.scalping_max_daily_dd,
        "max_total_dd": settings.scalping_max_total_dd,
        "scan_interval": getattr(engine, '_scan_interval', 120),
        "scalping_scan_interval": getattr(engine, '_scalping_scan_interval', 30),
        "dd_limits_ok": (
            getattr(engine, '_scalping_daily_dd', 0.0) <= settings.scalping_max_daily_dd
            and getattr(engine, '_scalping_total_dd', 0.0) <= settings.scalping_max_total_dd
        ),
        "timeframe_mapping": {
            "direction": "H1 (replaces Daily)",
            "structure": "M15 (replaces H4)",
            "confirmation": "M5 (replaces H1)",
            "execution": "M1 (replaces M5)",
        },
        **scalping_status,
    }


# ── Security Management ──────────────────────────────────────────

@router.post("/security/generate-key")
async def generate_api_key(label: str = "default"):
    """Generate a new API key. Returns the raw key ONCE - save it immediately."""
    from core.security import security_config
    raw_key = security_config.generate_api_key(label)
    return {
        "api_key": raw_key,
        "label": label,
        "message": "Guarda esta API key - no se mostrara de nuevo. "
                   "Usala en el header X-API-Key para autenticarte.",
    }


@router.get("/security/status")
async def get_security_status():
    """Get current security configuration (no secrets exposed)."""
    from core.security import security_config
    return {
        "auth_enabled": security_config.auth_enabled,
        "rate_limit_enabled": security_config.rate_limit_enabled,
        "rate_limit_rpm": security_config.rate_limit_rpm,
        "api_keys_count": len(security_config.api_keys),
        "api_keys": [
            {"hash_prefix": h[:12] + "...", "label": label}
            for h, label in security_config.api_keys.items()
        ],
        "ip_whitelist": security_config.ip_whitelist,
    }


class SecurityUpdateRequest(BaseModel):
    auth_enabled: Optional[bool] = None
    rate_limit_enabled: Optional[bool] = None
    rate_limit_rpm: Optional[int] = None
    ip_whitelist: Optional[List[str]] = None


@router.put("/security/config")
async def update_security_config(request: SecurityUpdateRequest):
    """Update security settings."""
    from core.security import security_config
    if request.auth_enabled is not None:
        security_config.auth_enabled = request.auth_enabled
    if request.rate_limit_enabled is not None:
        security_config.rate_limit_enabled = request.rate_limit_enabled
    if request.rate_limit_rpm is not None:
        if request.rate_limit_rpm < 10:
            raise HTTPException(400, "rate_limit_rpm must be >= 10")
        security_config.rate_limit_rpm = request.rate_limit_rpm
    if request.ip_whitelist is not None:
        security_config.ip_whitelist = request.ip_whitelist
    security_config.save()
    return {"message": "Configuracion de seguridad actualizada"}


@router.delete("/security/revoke-key/{key_hash_prefix}")
async def revoke_api_key(key_hash_prefix: str):
    """Revoke an API key by its hash prefix (first 12 chars)."""
    from core.security import security_config
    for full_hash in list(security_config.api_keys.keys()):
        if full_hash.startswith(key_hash_prefix):
            label = security_config.api_keys[full_hash]
            security_config.revoke_key(full_hash)
            return {"message": f"API key '{label}' revocada", "revoked": True}
    raise HTTPException(404, "API key no encontrada")


# ── Funded Account Mode ──────────────────────────────────────────

class FundedToggleRequest(BaseModel):
    enabled: bool


@router.post("/funded/toggle")
async def toggle_funded_mode(request: FundedToggleRequest):
    """Enable or disable funded account mode."""
    from config import settings as _settings
    old_value = _settings.funded_account_mode
    _settings.funded_account_mode = request.enabled
    return {
        "funded_account_mode": request.enabled,
        "previous": old_value,
        "message": (
            "Modo cuenta fondeada ACTIVADO — DD diario y total limitados"
            if request.enabled
            else "Modo cuenta fondeada DESACTIVADO — operación normal"
        ),
    }


@router.get("/funded/status")
async def get_funded_status():
    """Get funded account status including DD limits and usage."""
    from main import engine
    from config import settings as _settings
    if engine is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    try:
        risk_mgr = engine.risk_manager
        await risk_mgr.update_balance_tracking()
        return risk_mgr.get_funded_status()
    except Exception as e:
        logger.error(f"Funded status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Trade Journal ──────────────────────────────────────────────────

@router.get("/journal/stats")
async def get_journal_stats():
    """Get comprehensive trade journal statistics (TradingLab Registro de trades)."""
    from main import engine
    if engine is None or not hasattr(engine, 'trade_journal') or engine.trade_journal is None:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "break_evens": 0,
            "win_rate": 0.0,
            "win_rate_excl_be": 0.0,
            "current_balance": 0.0,
            "initial_capital": 0.0,
            "peak_balance": 0.0,
            "current_drawdown_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "max_drawdown_dollars": 0.0,
            "current_winning_streak": 0,
            "max_winning_streak": 0,
            "max_streak_pct": 0.0,
            "avg_win_pct": 0.0,
            "avg_loss_pct": 0.0,
            "profit_factor": 0.0,
            "monthly_returns": {},
            "pnl_accumulated_pct": 0.0,
            "accumulator": 1.0,
            "dd_by_year": {},
            "message": "Trade journal not initialized - engine must be started first",
        }
    return engine.trade_journal.get_stats()


class EmotionalNotesRequest(BaseModel):
    emotional_notes_pre: Optional[str] = None
    emotional_notes_during: Optional[str] = None
    emotional_notes_post: Optional[str] = None


@router.put("/journal/trades/{trade_id}/emotional-notes")
async def update_emotional_notes(trade_id: str, req: EmotionalNotesRequest):
    """Update emotional journal notes for a trade (Psychology Manual)."""
    from main import engine
    if not hasattr(engine, 'trade_journal') or engine.trade_journal is None:
        raise HTTPException(503, "Trade journal not initialized")

    # Find and update the trade
    for trade in engine.trade_journal._trades:
        if trade.get("trade_id") == trade_id:
            if req.emotional_notes_pre is not None:
                trade["emotional_notes_pre"] = req.emotional_notes_pre
            if req.emotional_notes_during is not None:
                trade["emotional_notes_during"] = req.emotional_notes_during
            if req.emotional_notes_post is not None:
                trade["emotional_notes_post"] = req.emotional_notes_post
            engine.trade_journal._save()
            return {"status": "updated", "trade_id": trade_id}

    raise HTTPException(404, f"Trade {trade_id} not found")


@router.get("/journal/trades")
async def get_journal_trades(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Get trade journal history with pagination."""
    from main import engine
    if engine is None or not hasattr(engine, 'trade_journal') or engine.trade_journal is None:
        return []
    trades = engine.trade_journal.get_trades(limit=limit, offset=offset)
    if engine.screenshot_generator is None:
        return trades
    enriched = []
    for trade in trades:
        row = dict(trade)
        row["_screenshots"] = engine.screenshot_generator.get_screenshot_path(
            trade.get("trade_id", "")
        )
        enriched.append(row)
    return enriched


# ── Journal Notes Update (Documentación/02_Journaling) ─────────────
# Alex: "lo mínimo es explicar el estilo, las 4 temporalidades,
# SL, TP, R:R, captura, gestión de la posición y resultado"

class JournalNotesRequest(BaseModel):
    trade_summary: Optional[str] = None
    management_notes: Optional[str] = None
    screenshots: Optional[List[str]] = None


@router.put("/journal/trades/{trade_id}/notes")
async def update_journal_notes(trade_id: str, req: JournalNotesRequest):
    """Update visual journaling notes for a trade (TradingLab Journaling).

    Notes should be written ASAP after the trade to capture emotional state.
    Screenshots should include entry, exit, and optionally 'now' for ASR context.
    """
    from main import engine
    if engine is None or not hasattr(engine, 'trade_journal') or engine.trade_journal is None:
        raise HTTPException(503, "Trade journal not initialized")

    success = engine.trade_journal.update_journal_notes(
        trade_id=trade_id,
        trade_summary=req.trade_summary,
        management_notes=req.management_notes,
        screenshots=req.screenshots,
    )
    if not success:
        raise HTTPException(404, f"Trade {trade_id} not found")
    return {"status": "updated", "trade_id": trade_id}


# ── ASR (Auto Self Review) - Documentación/03_ASR ──────────────────
# Alex: "correcto o incorrecto no viene relacionado con el resultado
# del trade, viene relacionado con vuestro plan de trading"

class ASRRequest(BaseModel):
    htf_correct: Optional[bool] = None
    ltf_correct: Optional[bool] = None
    strategy_correct: Optional[bool] = None
    sl_correct: Optional[bool] = None
    tp_correct: Optional[bool] = None
    management_correct: Optional[bool] = None
    would_enter_again: Optional[bool] = None
    lessons: Optional[str] = None


@router.post("/self-improvement/asr/{trade_id}")
async def trigger_auto_asr(trade_id: str):
    """Manually trigger AutoASR generation for an existing closed trade.

    Useful for backfilling ASR on trades that closed before
    ``settings.auto_asr_enabled`` was turned on, or for re-running ASR
    after fixing the prompt. Requires ``OPENAI_API_KEY`` and an
    initialized OpenAIAnalyzer + TradeJournal on the engine.
    """
    from main import engine
    from config import settings as _s
    import os as _os
    if engine is None:
        raise HTTPException(503, "Engine not initialized")
    if engine.ai_analyzer is None or engine.trade_journal is None:
        raise HTTPException(503, "AI analyzer or trade journal not initialized")
    record = next(
        (t for t in engine.trade_journal.get_trades(9999) if t.get("trade_id") == trade_id),
        None,
    )
    if record is None:
        raise HTTPException(404, f"Trade {trade_id} not found in journal")

    # Merge the richer DB history record (has reasoning, strategy_variant,
    # risk_reward_ratio, stop_loss, take_profit) so the AutoASR prompt has
    # real execution context — without this the JPM backfill filled only
    # `asr_lessons` because the journal fields were mostly null.
    try:
        from main import db as _db
        if _db is not None:
            hist = await _db.get_trade_history(limit=200)
            db_row = next((h for h in hist if h.get("id") == trade_id), None)
            if db_row:
                for k in (
                    "reasoning", "strategy_variant", "risk_reward_ratio",
                    "confidence", "stop_loss", "take_profit", "mode",
                    "opened_at", "closed_at", "status", "pnl_pips",
                ):
                    v = db_row.get(k)
                    if v not in (None, ""):
                        record.setdefault(k, v)
                # Also surface DB entry/exit if journal had them null
                if record.get("entry_price") in (None, 0):
                    record["entry_price"] = db_row.get("entry_price")
                if record.get("exit_price") in (None, 0):
                    record["exit_price"] = db_row.get("exit_price")
    except Exception as _e:
        logger.debug(f"AutoASR backfill: could not merge DB record for {trade_id}: {_e}")

    from core.self_improvement import AutoASRGenerator, find_close_screenshot
    journal_path = getattr(engine.trade_journal, "_data_path", "data/trade_journal.json")
    screenshots_dir = _os.path.join(_os.path.dirname(_os.path.abspath(journal_path)), "screenshots")
    shot = find_close_screenshot(screenshots_dir, trade_id)
    gen = AutoASRGenerator(
        openai_client=engine.ai_analyzer.client,
        trade_journal=engine.trade_journal,
        model=getattr(_s, "auto_asr_model", "gpt-4o"),
    )
    result = await gen.generate_asr(record, screenshot_path=shot)
    return {
        "trade_id": result.trade_id,
        "success": result.success,
        "fields_filled": result.fields_filled,
        "vision_used": result.vision_used,
        "error": result.error,
    }


@router.post("/self-improvement/config")
async def update_self_improvement_config(
    auto_asr_enabled: Optional[bool] = None,
    auto_asr_model: Optional[str] = None,
    swing_for_equities: Optional[bool] = None,
    self_improvement_tuning_mode: Optional[str] = None,
):
    """Mutate self-improvement runtime toggles and persist them so they
    survive container restarts. Each field is optional; only provided
    fields are touched. ``self_improvement_tuning_mode`` accepts
    ``off`` | ``proposals`` | ``auto``.
    """
    from config import settings as _s
    updates: Dict[str, object] = {}
    if auto_asr_enabled is not None:
        updates["auto_asr_enabled"] = bool(auto_asr_enabled)
    if auto_asr_model is not None:
        if not auto_asr_model:
            raise HTTPException(400, "auto_asr_model cannot be empty")
        updates["auto_asr_model"] = str(auto_asr_model)
    if swing_for_equities is not None:
        updates["swing_for_equities"] = bool(swing_for_equities)
    if self_improvement_tuning_mode is not None:
        if self_improvement_tuning_mode not in ("off", "proposals", "auto"):
            raise HTTPException(400, "tuning_mode must be off|proposals|auto")
        updates["self_improvement_tuning_mode"] = self_improvement_tuning_mode
    if not updates:
        raise HTTPException(400, "No fields provided")

    # Apply in-memory + persist to risk_config.json
    import json, os, tempfile
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    risk_path = os.path.join(backend_dir, "data", "risk_config.json")
    overrides: dict = {}
    if os.path.exists(risk_path):
        try:
            with open(risk_path) as f:
                overrides = json.load(f)
            if not isinstance(overrides, dict):
                overrides = {}
        except Exception as e:
            raise HTTPException(500, f"risk_config.json corrupted: {e}")
    for k, v in updates.items():
        setattr(_s, k, v)
        overrides[k] = v
    os.makedirs(os.path.dirname(risk_path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(risk_path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(overrides, f, indent=2)
        os.replace(tmp, risk_path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    return {"status": "updated", "applied": updates}


@router.get("/self-improvement/proposals")
async def list_tuning_proposals(status: Optional[str] = None):
    """List tuning proposals. Optional filter by status."""
    from core.self_improvement import ProposalStore
    store = ProposalStore()
    return [p.to_dict() for p in store.list_all(status=status)]


@router.post("/self-improvement/proposals/{proposal_id}/approve")
async def approve_tuning_proposal(proposal_id: str):
    """Approve and apply a pending tuning proposal."""
    from core.self_improvement import ProposalStore, apply_proposal
    from main import engine
    from config import settings as _s
    store = ProposalStore()
    proposal = store.get(proposal_id)
    if proposal is None:
        raise HTTPException(404, "Proposal not found")
    if proposal.status != "pending":
        raise HTTPException(400, f"Proposal is {proposal.status}, only pending can be approved")
    persist = engine._make_tuning_persist_fn() if hasattr(engine, "_make_tuning_persist_fn") else None
    if persist is None:
        raise HTTPException(503, "Engine not ready to apply proposal")
    if not apply_proposal(_s, proposal, persist):
        raise HTTPException(500, "Failed to apply proposal")
    store._save()
    return proposal.to_dict()


@router.post("/self-improvement/proposals/{proposal_id}/reject")
async def reject_tuning_proposal(proposal_id: str):
    """Reject a pending proposal (no mutation, just marks rejected)."""
    from core.self_improvement import ProposalStore
    store = ProposalStore()
    proposal = store.get(proposal_id)
    if proposal is None:
        raise HTTPException(404, "Proposal not found")
    if proposal.status != "pending":
        raise HTTPException(400, f"Proposal is {proposal.status}")
    proposal.status = "rejected"
    store._save()
    return proposal.to_dict()


@router.post("/self-improvement/proposals/{proposal_id}/rollback")
async def rollback_tuning_proposal(proposal_id: str):
    """Restore the original value of an already-applied proposal."""
    from core.self_improvement import ProposalStore, rollback_proposal
    from main import engine
    from config import settings as _s
    store = ProposalStore()
    proposal = store.get(proposal_id)
    if proposal is None:
        raise HTTPException(404, "Proposal not found")
    if proposal.status != "applied":
        raise HTTPException(400, f"Proposal is {proposal.status}, only applied can be rolled back")
    persist = engine._make_tuning_persist_fn() if hasattr(engine, "_make_tuning_persist_fn") else None
    if persist is None:
        raise HTTPException(503, "Engine not ready to rollback proposal")
    if not rollback_proposal(_s, proposal, persist):
        raise HTTPException(500, "Failed to rollback proposal")
    store._save()
    return proposal.to_dict()


@router.get("/self-improvement/status")
async def self_improvement_status():
    """Report whether self-improvement features are wired up and enabled."""
    from main import engine
    from config import settings as _s
    return {
        "auto_asr_enabled": getattr(_s, "auto_asr_enabled", False),
        "auto_asr_model": getattr(_s, "auto_asr_model", "gpt-4o"),
        "openai_configured": bool((getattr(_s, "openai_api_key", "") or "").strip()),
        "ai_analyzer_ready": (engine is not None and engine.ai_analyzer is not None),
        "trade_journal_ready": (engine is not None and engine.trade_journal is not None),
        "swing_for_equities": getattr(_s, "swing_for_equities", False),
        "equities_correlation_groups_count": len(getattr(_s, "equities_correlation_groups", [])),
        "tuning_mode": getattr(_s, "self_improvement_tuning_mode", "off"),
        "tuning_min_trades": getattr(_s, "self_improvement_min_trades", 10),
        "engine_mode_default": getattr(_s, "engine_mode", "AUTO"),
    }


@router.put("/journal/trades/{trade_id}/asr")
async def update_trade_asr(trade_id: str, req: ASRRequest):
    """Submit ASR (Auto Self Review) checklist for a trade.

    Should be done with emotional distance (not immediately after the trade).
    Evaluates execution quality AGAINST the trading plan, not against result.
    """
    from main import engine
    if engine is None or not hasattr(engine, 'trade_journal') or engine.trade_journal is None:
        raise HTTPException(503, "Trade journal not initialized")

    # Reject empty payloads with 400 — prevents false completions
    if all(
        v is None
        for v in (req.htf_correct, req.ltf_correct, req.strategy_correct,
                  req.sl_correct, req.tp_correct, req.management_correct,
                  req.would_enter_again, req.lessons)
    ):
        raise HTTPException(400, "ASR payload is empty — provide at least one field")

    success = engine.trade_journal.update_asr(
        trade_id=trade_id,
        htf_correct=req.htf_correct,
        ltf_correct=req.ltf_correct,
        strategy_correct=req.strategy_correct,
        sl_correct=req.sl_correct,
        tp_correct=req.tp_correct,
        management_correct=req.management_correct,
        would_enter_again=req.would_enter_again,
        lessons=req.lessons,
    )
    if not success:
        raise HTTPException(404, f"Trade {trade_id} not found")
    return {"status": "updated", "trade_id": trade_id, "asr_completed": True}


@router.get("/journal/asr-stats")
async def get_asr_stats():
    """Get ASR completion statistics.

    Proceso de Revisión: track how many trades have been reviewed
    and what percentage had perfect execution per the trading plan.
    """
    from main import engine
    if engine is None or not hasattr(engine, 'trade_journal') or engine.trade_journal is None:
        return {
            "total": 0,
            "asr_completed": 0,
            "asr_completion_rate": 0.0,
            "perfect_execution_count": 0,
            "perfect_execution_rate": 0.0,
        }
    return engine.trade_journal.get_asr_stats()


# ── Watchlist Categories ────────────────────────────────────────────

class WatchlistCategoriesRequest(BaseModel):
    categories: List[str]  # ["forex", "forex_exotic", "commodities", "indices", "equities", "crypto", "market_view"]


@router.get("/watchlist/categories")
async def get_watchlist_categories():
    """Get available watchlist categories and their instruments."""
    from config import settings
    return {
        "active_categories": settings.active_watchlist_categories,
        "available": {
            "forex": {"count": len(settings.forex_watchlist), "instruments": settings.forex_watchlist},
            "forex_exotic": {"count": len(settings.forex_exotic_watchlist), "instruments": settings.forex_exotic_watchlist},
            "commodities": {"count": len(settings.commodities_watchlist), "instruments": settings.commodities_watchlist},
            "indices": {"count": len(settings.indices_watchlist), "instruments": settings.indices_watchlist},
            "equities": {"count": len(settings.equities_watchlist), "instruments": settings.equities_watchlist},
            "crypto": {"count": len(settings.crypto_watchlist), "instruments": settings.crypto_watchlist},
            "market_view": {"count": len(settings.market_view_symbols), "instruments": settings.market_view_symbols},
        },
        "allocation": {
            "trading_pct": settings.allocation_trading_pct,
            "forex_pct": settings.allocation_forex_pct,
            "crypto_pct": settings.allocation_crypto_pct,
        }
    }


@router.put("/watchlist/categories")
async def update_watchlist_categories(req: WatchlistCategoriesRequest):
    """Update active watchlist categories."""
    from config import settings
    valid = {"forex", "forex_exotic", "commodities", "indices", "equities", "crypto", "market_view"}
    for cat in req.categories:
        if cat not in valid:
            raise HTTPException(400, f"Invalid category: {cat}. Valid: {', '.join(valid)}")
    settings.active_watchlist_categories = req.categories
    # Persist to risk_config.json atomically — preserves other keys on JSON errors
    import json, os, tempfile
    _backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    risk_path = os.path.join(_backend_dir, "data", "risk_config.json")
    overrides = {}
    if os.path.exists(risk_path):
        try:
            with open(risk_path) as f:
                overrides = json.load(f)
            if not isinstance(overrides, dict):
                overrides = {}
        except Exception as e:
            # Keep existing file untouched on parse error — don't wipe other keys
            logger.warning(f"risk_config.json unreadable ({e}); aborting watchlist save to avoid data loss")
            raise HTTPException(500, "Config file corrupted — manual fix required before saving")
    overrides["active_watchlist_categories"] = req.categories
    os.makedirs(os.path.dirname(risk_path), exist_ok=True)
    dir_name = os.path.dirname(risk_path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(overrides, f, indent=2)
        os.replace(tmp_path, risk_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return {"status": "updated", "active_categories": req.categories}


@router.get("/watchlist/full")
async def get_full_watchlist():
    """Get the combined active watchlist based on enabled categories."""
    from config import settings
    instruments = []
    category_map = {
        "forex": settings.forex_watchlist,
        "forex_exotic": settings.forex_exotic_watchlist,
        "commodities": settings.commodities_watchlist,
        "indices": settings.indices_watchlist,
        "equities": settings.equities_watchlist,
        "crypto": settings.crypto_watchlist,
        "market_view": settings.market_view_symbols,
    }
    for cat in settings.active_watchlist_categories:
        if cat in category_map:
            instruments.extend(category_map[cat])
    # Deduplicate preserving order
    seen = set()
    unique = []
    for inst in instruments:
        if inst not in seen:
            seen.add(inst)
            unique.append(inst)
    return {"instruments": unique, "count": len(unique)}


# ── Trade Screenshots ──────────────────────────────────────────────

@router.get("/screenshots/{trade_id}")
async def get_trade_screenshots(trade_id: str):
    """Get screenshot file paths for a trade."""
    import re
    if not re.match(r'^[\w\-\.]+$', trade_id) or '..' in trade_id:
        raise HTTPException(400, "Invalid trade_id")
    from main import engine
    if engine is None or engine.screenshot_generator is None:
        return {"trade_id": trade_id, "screenshots": [], "files": []}
    paths = engine.screenshot_generator.get_screenshot_path(trade_id)
    import os
    return {
        "trade_id": trade_id,
        "screenshots": paths,
        "files": [os.path.basename(p) for p in paths],
    }


@router.post("/screenshots/{trade_id}/regenerate")
async def regenerate_trade_screenshots(
    trade_id: str,
    strategy: Optional[str] = Query(None, description="Override strategy label (e.g. BLACK/BLUE_A)"),
    original_sl: Optional[float] = Query(None, description="Override SL used for R:R calc (useful when position is now at BE)"),
    original_tp: Optional[float] = Query(None, description="Override TP1 for R:R calc"),
    original_tp_max: Optional[float] = Query(None, description="Override TP_max line on chart"),
):
    """Regenerate the open + close screenshots for an existing trade with the
    current screenshot_generator (fresh broker candles + correct strategy
    name). Old screenshots are kept; new ones are appended to the
    `data/screenshots/` directory with a fresh timestamp.

    Critical for the TradingLab mentorship deliverable: existing trades
    closed before the screenshot generator was fixed have placeholder
    "No chart data available" cards. This endpoint lets us produce a
    proper chart retroactively from the journal record.
    """
    from main import engine
    import re
    if not re.match(r'^[\w\-\.]+$', trade_id) or '..' in trade_id:
        raise HTTPException(400, "Invalid trade_id")
    if engine is None or engine.screenshot_generator is None:
        raise HTTPException(503, "Screenshot generator not initialized")

    # Look up trade — prefer DB history (has SL/TP populated) over journal
    # (which stores sl/tp as null for trades recorded before the schema
    # was fully wired). Fallback to open positions for trades still live.
    record = None
    from main import db as _db
    if _db is not None:
        try:
            hist = await _db.get_trade_history(limit=200)
            db_row = next((t for t in hist if t.get("id") == trade_id), None)
            if db_row:
                record = {
                    "trade_id": db_row["id"],
                    "instrument": db_row["instrument"],
                    "direction": db_row["direction"],
                    "strategy": db_row.get("strategy_variant") or db_row.get("strategy") or "UNKNOWN",
                    "entry_price": db_row["entry_price"],
                    "exit_price": db_row.get("exit_price"),
                    "sl": db_row.get("stop_loss"),
                    "tp": db_row.get("take_profit"),
                    "pnl_dollars": db_row.get("pnl"),
                    "pnl_pct": None,
                    "result": db_row.get("status", "").replace("closed_", "").upper(),
                }
        except Exception:
            pass
    # Overlay journal fields if we also have them (pnl_pct etc.)
    if engine.trade_journal:
        for t in engine.trade_journal.get_trades(9999):
            if t.get("trade_id") == trade_id:
                if record is None:
                    record = dict(t)
                else:
                    # Merge: keep DB sl/tp, pull journal pnl_pct/result
                    if record.get("pnl_pct") is None and t.get("pnl_pct") is not None:
                        record["pnl_pct"] = t["pnl_pct"]
                    if not record.get("result") and t.get("result"):
                        record["result"] = t["result"]
                break
    # Fallback to live open positions — prefer original_sl over current_sl
    # so the R:R label is meaningful even when a trade is already at BE.
    if record is None and hasattr(engine, 'position_manager'):
        pos = engine.position_manager.positions.get(trade_id)
        if pos is not None:
            record = {
                "trade_id": trade_id,
                "instrument": pos.instrument,
                "direction": pos.direction,
                "strategy": getattr(pos, "strategy_variant", None) or "UNKNOWN",
                "entry_price": pos.entry_price,
                "exit_price": None,
                "sl": pos.original_sl or pos.current_sl,
                "tp": pos.take_profit_1,
                "tp_max": pos.take_profit_max,
                "pnl_dollars": 0,
                "pnl_pct": 0,
                "result": "OPEN",
            }
    if record is None:
        raise HTTPException(404, f"Trade {trade_id} not found")

    # Apply operator overrides. Useful for retrofilling mentorship-exam
    # screenshots when the live record lost strategy/sl/tp during a restart.
    if strategy is not None:
        record["strategy"] = strategy
    if original_sl is not None:
        record["sl"] = original_sl
    if original_tp is not None:
        record["tp"] = original_tp
    if original_tp_max is not None:
        record["tp_max"] = original_tp_max

    inst = record["instrument"]
    direction = record["direction"]
    strategy = record.get("strategy") or "UNKNOWN"
    entry = record.get("entry_price") or 0
    sl = record.get("sl") or 0
    tp1 = record.get("tp") or 0
    tp_max = record.get("tp_max")
    exit_price = record.get("exit_price")
    pnl_pct = record.get("pnl_pct") or 0

    # Fetch fresh candles from broker
    candles = []
    ema_vals = None
    try:
        raw = await engine.broker.get_candles(inst, "H1", 100)
        candles = [
            {"time": c.time, "open": c.open, "high": c.high, "low": c.low, "close": c.close}
            for c in (raw or [])
        ]
    except Exception as e:
        logger.warning(f"regenerate: candles fetch failed for {inst}: {e}")
    # Try to grab live EMAs from last_scan_results
    if inst in engine.last_scan_results:
        ema_vals = getattr(engine.last_scan_results[inst], 'ema_values', None)

    new_paths = []
    # Always regenerate OPEN
    try:
        p = await engine.screenshot_generator.capture_trade_open(
            trade_id=trade_id,
            instrument=inst,
            direction=direction,
            entry_price=entry,
            sl=sl,
            tp1=tp1,
            tp_max=tp_max,
            strategy=strategy,
            confidence=1.0,
            candles=candles,
            ema_values=ema_vals,
        )
        if p:
            new_paths.append(p)
    except Exception as e:
        logger.error(f"regenerate open failed: {e}")
    # Regenerate CLOSE only if trade was closed
    if exit_price is not None:
        try:
            result_label = (record.get("result") or
                            ("TP" if (record.get("pnl_dollars") or 0) > 0
                             else ("SL" if (record.get("pnl_dollars") or 0) < 0 else "BE")))
            p = await engine.screenshot_generator.capture_trade_close(
                trade_id=trade_id,
                instrument=inst,
                direction=direction,
                entry_price=entry,
                close_price=exit_price,
                pnl_pct=pnl_pct,
                result=result_label,
                candles=candles,
            )
            if p:
                new_paths.append(p)
        except Exception as e:
            logger.error(f"regenerate close failed: {e}")
    return {
        "trade_id": trade_id,
        "regenerated_paths": new_paths,
        "candles_used": len(candles),
        "strategy": strategy,
    }


@router.get("/screenshots/{trade_id}/image/{filename}")
async def get_screenshot_image(trade_id: str, filename: str):
    """Serve a screenshot image file."""
    from fastapi.responses import FileResponse
    import os
    # Security: only allow alphanumeric + underscores + dashes + dots, block traversal
    import re
    if not re.match(r'^[\w\-\.]+$', trade_id) or '..' in trade_id:
        raise HTTPException(400, "Invalid trade_id")
    if not re.match(r'^[\w\-\.]+$', filename) or '..' in filename:
        raise HTTPException(400, "Invalid filename")
    filepath = os.path.join("data", "screenshots", filename)
    if not os.path.exists(filepath):
        raise HTTPException(404, "Screenshot not found")
    return FileResponse(filepath, media_type="image/png")


# ── Monthly Review ─────────────────────────────────────────────────

@router.post("/monthly-review/generate")
async def generate_monthly_review(month: str = Query(..., description="YYYY-MM format")):
    """Generate a monthly review report for the specified month."""
    from main import engine
    import re
    if not re.match(r'^\d{4}-\d{2}$', month):
        raise HTTPException(400, "Month must be in YYYY-MM format")
    if engine is None:
        raise HTTPException(503, "Engine not initialized")

    # Get trades for the month from journal
    all_trades = []
    if hasattr(engine, 'trade_journal') and engine.trade_journal:
        all_trades = engine.trade_journal.get_trades(limit=9999)

    # Filter trades for the requested month
    month_trades = []
    for t in all_trades:
        # Try month field first, then fall back to date/open_time/timestamp
        trade_month = t.get("month", "")
        if trade_month == month:
            month_trades.append(t)
            continue
        ts = t.get("date") or t.get("open_time") or t.get("timestamp", "")
        if isinstance(ts, str) and ts.startswith(month):
            month_trades.append(t)

    if not hasattr(engine, 'monthly_review') or engine.monthly_review is None:
        raise HTTPException(503, "Monthly review generator not available")

    report = engine.monthly_review.generate_report(
        trades=month_trades,
        month=month,
    )
    return report.to_dict()


@router.get("/monthly-review/{month}")
async def get_monthly_review(month: str):
    """Get a previously generated monthly review."""
    import re
    if not re.match(r'^\d{4}-\d{2}$', month):
        raise HTTPException(400, "Month must be in YYYY-MM format")
    from main import engine
    if engine is None or not hasattr(engine, 'monthly_review') or engine.monthly_review is None:
        raise HTTPException(503, "Monthly review not available")
    report = engine.monthly_review.load_report(month)
    if not report:
        raise HTTPException(404, f"No report found for {month}")
    return report


@router.get("/monthly-review")
async def list_monthly_reviews():
    """List all available monthly reviews."""
    from main import engine
    if engine is None or not hasattr(engine, 'monthly_review') or engine.monthly_review is None:
        return {"reports": []}
    return {"reports": engine.monthly_review.list_reports()}


# ── Weekly Review (ASR - Auto Self Review) ───────────

@router.get("/weekly-review")
async def get_weekly_review(
    week: Optional[str] = Query(
        None,
        description="ISO week in YYYY-Www format (e.g. 2026-W13). Defaults to current week.",
    ),
):
    """
    Generate a weekly analysis report (ASR - Auto Self Review).

    The mentorship teaches ASR as a critical weekly practice to review
    performance, identify patterns, and make adjustments.
    """
    from main import engine
    from datetime import datetime, timezone, timedelta

    if engine is None or not hasattr(engine, 'trade_journal') or engine.trade_journal is None:
        return {
            "week": week or "unknown",
            "total_trades": 0,
            "message": "Trade journal not initialized",
        }

    # Determine the ISO week to analyze
    now = datetime.now(timezone.utc)
    if week:
        # Parse YYYY-Www format
        import re
        match = re.match(r'^(\d{4})-W(\d{2})$', week)
        if not match:
            raise HTTPException(400, "Week must be in YYYY-Www format (e.g. 2026-W13)")
        iso_year = int(match.group(1))
        iso_week = int(match.group(2))
        if iso_week < 1 or iso_week > 53:
            raise HTTPException(400, "Week number must be between 1 and 53")
    else:
        iso_year, iso_week, _ = now.isocalendar()
        week = f"{iso_year}-W{iso_week:02d}"

    # Calculate the Monday and Sunday of the target week
    # ISO week 1 starts on the Monday of the week containing the year's first Thursday
    jan4 = datetime(iso_year, 1, 4, tzinfo=timezone.utc)
    # Monday of ISO week 1
    week1_monday = jan4 - timedelta(days=jan4.weekday())
    week_monday = week1_monday + timedelta(weeks=iso_week - 1)
    week_sunday = week_monday + timedelta(days=6, hours=23, minutes=59, seconds=59)

    week_start_str = week_monday.strftime("%Y-%m-%d")
    week_end_str = week_sunday.strftime("%Y-%m-%d")

    # Get all trades and filter for the target week
    all_trades = engine.trade_journal.get_trades(limit=9999)
    week_trades = []
    for t in all_trades:
        ts = t.get("date") or t.get("open_time") or t.get("timestamp", "")
        if isinstance(ts, str) and len(ts) >= 10:
            trade_date_str = ts[:10]  # YYYY-MM-DD
            if week_start_str <= trade_date_str <= week_end_str:
                week_trades.append(t)

    # Build the weekly summary
    total = len(week_trades)
    wins = [t for t in week_trades if t.get("result") == "TP"]
    losses = [t for t in week_trades if t.get("result") == "SL"]
    be_trades = [t for t in week_trades if t.get("result") == "BE"]

    win_count = len(wins)
    loss_count = len(losses)
    total_pnl = sum(t.get("pnl_dollars", 0.0) or 0.0 for t in week_trades)

    win_rate = (win_count / total * 100) if total > 0 else 0.0

    # Best and worst trade
    best_trade = None
    worst_trade = None
    if week_trades:
        best_t = max(week_trades, key=lambda t: t.get("pnl_dollars", 0.0) or 0.0)
        worst_t = min(week_trades, key=lambda t: t.get("pnl_dollars", 0.0) or 0.0)
        best_trade = {
            "trade_id": best_t.get("trade_id"),
            "instrument": best_t.get("instrument"),
            "pnl_dollars": best_t.get("pnl_dollars", 0.0),
            "strategy": best_t.get("strategy"),
        }
        worst_trade = {
            "trade_id": worst_t.get("trade_id"),
            "instrument": worst_t.get("instrument"),
            "pnl_dollars": worst_t.get("pnl_dollars", 0.0),
            "strategy": worst_t.get("strategy"),
        }

    # P&L by strategy
    pnl_by_strategy: Dict[str, dict] = {}
    for t in week_trades:
        strat = t.get("strategy", "UNKNOWN")
        if strat not in pnl_by_strategy:
            pnl_by_strategy[strat] = {"trades": 0, "pnl": 0.0, "wins": 0}
        pnl_by_strategy[strat]["trades"] += 1
        pnl_by_strategy[strat]["pnl"] += t.get("pnl_dollars", 0.0) or 0.0
        if t.get("result") == "TP":
            pnl_by_strategy[strat]["wins"] += 1
    # Add win_rate to each strategy
    for data in pnl_by_strategy.values():
        data["pnl"] = round(data["pnl"], 2)
        data["win_rate"] = round(
            (data["wins"] / data["trades"] * 100) if data["trades"] > 0 else 0.0, 2
        )

    # P&L by instrument
    pnl_by_instrument: Dict[str, dict] = {}
    for t in week_trades:
        inst = t.get("instrument", "UNKNOWN")
        if inst not in pnl_by_instrument:
            pnl_by_instrument[inst] = {"trades": 0, "pnl": 0.0, "wins": 0}
        pnl_by_instrument[inst]["trades"] += 1
        pnl_by_instrument[inst]["pnl"] += t.get("pnl_dollars", 0.0) or 0.0
        if t.get("result") == "TP":
            pnl_by_instrument[inst]["wins"] += 1
    for data in pnl_by_instrument.values():
        data["pnl"] = round(data["pnl"], 2)
        data["win_rate"] = round(
            (data["wins"] / data["trades"] * 100) if data["trades"] > 0 else 0.0, 2
        )

    # Average R:R achieved
    rr_values = [
        t.get("rr_achieved") for t in week_trades
        if t.get("rr_achieved") is not None
    ]
    avg_rr_achieved = round(sum(rr_values) / len(rr_values), 4) if rr_values else 0.0

    # ASR completion for this week's trades
    asr_completed_count = sum(1 for t in week_trades if t.get("asr_completed", False))
    asr_completion_rate = round(asr_completed_count / total * 100, 1) if total > 0 else 0.0
    # Identify common ASR errors this week
    asr_error_fields = {
        "asr_htf_correct": "Análisis HTF incorrecto",
        "asr_ltf_correct": "Análisis LTF incorrecto",
        "asr_strategy_correct": "Estrategia mal ejecutada",
        "asr_sl_correct": "SL mal colocado",
        "asr_tp_correct": "TP incorrecto",
        "asr_management_correct": "Gestión de posición incorrecta",
    }
    asr_errors = []
    for field_key, label in asr_error_fields.items():
        error_count = sum(
            1 for t in week_trades
            if t.get("asr_completed") and t.get(field_key) is False
        )
        if error_count > 0:
            asr_errors.append(f"{label} ({error_count} trades)")

    # Analysis note
    if total == 0:
        analysis_note = (
            f"No se ejecutaron trades en la semana {week}. "
            "Verificar si las condiciones del plan de trading se cumplieron."
        )
    elif win_rate >= 65:
        analysis_note = (
            f"Semana positiva con win rate de {win_rate:.1f}%. "
            "Mantener disciplina y consistencia."
        )
    elif win_rate >= 50:
        analysis_note = (
            f"Semana aceptable con win rate de {win_rate:.1f}%. "
            "Revisar trades perdedores para identificar mejoras."
        )
    else:
        analysis_note = (
            f"Semana con win rate bajo ({win_rate:.1f}%). "
            "Revisar entradas, confluencias y gestión emocional. "
            "Considerar reducir tamaño o pausar si hay racha perdedora."
        )

    return {
        "week": week,
        "period": {"start": week_start_str, "end": week_end_str},
        "total_trades": total,
        "wins": win_count,
        "losses": loss_count,
        "break_evens": len(be_trades),
        "win_rate": round(win_rate, 2),
        "total_pnl": round(total_pnl, 2),
        "best_trade": best_trade,
        "worst_trade": worst_trade,
        "pnl_by_strategy": pnl_by_strategy,
        "pnl_by_instrument": pnl_by_instrument,
        "avg_rr_achieved": avg_rr_achieved,
        "asr_completed": asr_completed_count,
        "asr_completion_rate": asr_completion_rate,
        "asr_common_errors": asr_errors,
        "analysis_note": analysis_note,
    }


# ── Discretionary Trade Tracking ───────────────────────────────────

class DiscretionaryRequest(BaseModel):
    is_discretionary: bool = True
    discretionary_notes: Optional[str] = ""


@router.put("/journal/trades/{trade_id}/discretionary")
async def mark_trade_discretionary(trade_id: str, req: DiscretionaryRequest):
    """Mark a trade as discretionary with notes. Trading Plan: annotate discretionary decisions."""
    from main import engine
    if engine is None or not hasattr(engine, 'trade_journal') or engine.trade_journal is None:
        raise HTTPException(503, "Trade journal not available")

    success = engine.trade_journal.mark_trade_discretionary(
        trade_id=trade_id,
        notes=req.discretionary_notes or "",
    )
    if not success:
        raise HTTPException(404, f"Trade {trade_id} not found")
    return {"status": "updated", "trade_id": trade_id, "is_discretionary": req.is_discretionary}


# ── Crypto Market Cycle (Esp. Criptomonedas) ────────────────────────

@router.get("/missed-trades")
async def get_missed_trades(limit: int = 50, offset: int = 0):
    """Get missed trade opportunities."""
    from main import engine
    if engine is None or not hasattr(engine, 'trade_journal') or engine.trade_journal is None:
        raise HTTPException(503, "Trade journal not initialized")
    return engine.trade_journal.get_missed_trades(limit=limit, offset=offset)


@router.get("/missed-trades/stats")
async def get_missed_trade_stats():
    """Get missed trade statistics."""
    from main import engine
    if engine is None or not hasattr(engine, 'trade_journal') or engine.trade_journal is None:
        raise HTTPException(503, "Trade journal not initialized")
    return engine.trade_journal.get_missed_trade_stats()


@router.get("/crypto/cycle")
async def get_crypto_cycle():
    """
    Get crypto market cycle status: BTC dominance, halving phase, BMSB,
    Pi Cycle, altcoin season, rotation phase.
    From TradingLab Esp. Criptomonedas modules 6-8.
    """
    from main import engine
    if engine is None:
        raise HTTPException(503, "Engine not available")

    # Get cycle data from the crypto cycle analyzer
    crypto_analyzer = getattr(engine, '_crypto_cycle_analyzer', None)
    if crypto_analyzer is None:
        # Try to create one from the trading engine
        try:
            from core.crypto_cycle import CryptoCycleAnalyzer
            crypto_analyzer = CryptoCycleAnalyzer(engine.broker)
        except Exception as e:
            return {
                "error": f"Crypto cycle analyzer not available: {e}",
                "btc_dominance": None,
                "market_phase": "unknown",
            }

    try:
        # Get latest scan results for BMSB/Pi Cycle data
        bmsb_data = None
        pi_cycle_data = None
        from strategies.base import _is_crypto_instrument
        for inst, result in engine.last_scan_results.items():
            if _is_crypto_instrument(inst):
                bmsb_data = getattr(result, 'bmsb', None)
                pi_cycle_data = getattr(result, 'pi_cycle', None)
                break

        cycle = await crypto_analyzer.get_cycle_status(
            bmsb=bmsb_data,
            pi_cycle=pi_cycle_data,
        )

        return {
            "btc_dominance": cycle.btc_dominance,
            "btc_dominance_trend": cycle.btc_dominance_trend,
            "market_phase": cycle.market_phase,
            "altcoin_season": cycle.altcoin_season,
            "btc_eth_ratio": cycle.btc_eth_ratio,
            "btc_eth_trend": cycle.btc_eth_trend,
            "eth_outperforming_btc": cycle.eth_outperforming_btc,
            "rotation_phase": cycle.rotation_phase,
            "halving_phase": cycle.halving_phase,
            "halving_phase_description": cycle.halving_phase_description,
            "halving_sentiment": cycle.halving_sentiment,
            "btc_rsi_14": cycle.btc_rsi_14,
            "ema8_weekly_broken": cycle.ema8_weekly_broken,
            "bmsb_status": cycle.bmsb_status,
            "bmsb_consecutive_bearish_closes": cycle.bmsb_consecutive_bearish_closes,
            "pi_cycle_status": cycle.pi_cycle_status,
            "sma_d200_position": cycle.sma_d200_position,
            "usdt_dominance_rising": cycle.usdt_dominance_rising,
            "golden_cross": cycle.golden_cross,
            "death_cross": cycle.death_cross,
            "rsi_diagonal_bearish": cycle.rsi_diagonal_bearish,
            "rsi_diagonal_bullish": cycle.rsi_diagonal_bullish,
            "last_updated": cycle.last_updated,
        }
    except Exception as e:
        logger.error(f"Crypto cycle endpoint error: {e}")
        return {
            "error": str(e),
            "btc_dominance": None,
            "market_phase": "unknown",
        }


@router.get("/crypto/indicators")
async def get_crypto_indicators():
    """
    Get crypto-specific indicator values: BMSB, Pi Cycle, EMA 8 Weekly,
    SMA 200 Daily, RSI 14 for BTC.
    From TradingLab Esp. Criptomonedas Module 8.
    """
    from main import engine
    if engine is None:
        raise HTTPException(503, "Engine not available")

    indicators = {
        "bmsb": None,
        "pi_cycle": None,
        "ema8_weekly": None,
        "sma200_daily": None,
        "ema50_daily": None,
        "rsi_14_daily": None,
    }

    # Search scan results for BTC data
    from strategies.base import _is_crypto_instrument
    for inst, result in engine.last_scan_results.items():
        if _is_crypto_instrument(inst):
            indicators["bmsb"] = getattr(result, 'bmsb', None)
            indicators["pi_cycle"] = getattr(result, 'pi_cycle', None)
            indicators["ema8_weekly"] = getattr(result, 'ema_w8', None)
            indicators["sma200_daily"] = getattr(result, 'sma_d200', None)
            indicators["ema50_daily"] = result.ema_values.get("EMA_D_50")
            indicators["rsi_14_daily"] = result.rsi_values.get("D")
            break

    return indicators


@router.get("/crypto/allocation")
async def get_crypto_allocation():
    """
    Get capital allocation breakdown per TradingLab Trading Plan.
    70% trading (70% forex, 20% other, 10% crypto), 20% stocks/ETFs, 10% crypto long-term.
    """
    from config import settings
    return {
        "trading_pct": settings.allocation_trading_pct,
        "forex_pct": settings.allocation_forex_pct,
        "crypto_pct": settings.allocation_crypto_pct,
        "investment_pct": settings.allocation_investment_pct,
        "investment_stocks_pct": settings.allocation_investment_pct * 0.70,  # 70% of investment in VT/S&P500
        "investment_crypto_pct": settings.allocation_crypto_longterm_pct,
        "crypto_default_strategy": settings.crypto_default_strategy,
        "crypto_position_mgmt_style": settings.crypto_position_mgmt_style,
        "memecoins_monitor_only": settings.memecoins_monitor_only,
    }


# ── Exam Submission (TradingLab Final Exam) ─────────────────────────

class ExamRequest(BaseModel):
    trade_ids: List[str]  # 3 trade IDs for TradingLab exam


def _pick_exam_screenshot(paths: List[str]) -> Optional[str]:
    """Prefer close screenshots, then open screenshots, then newest fallback."""
    if not paths:
        return None
    close_shots = [p for p in paths if "_close_" in p]
    open_shots = [p for p in paths if "_open_" in p]
    pool = close_shots or open_shots or paths
    return sorted(pool)[-1]


def _exam_gaps_for_trade(trade: dict, screenshot_paths: List[str]) -> List[str]:
    gaps: List[str] = []
    if not screenshot_paths:
        gaps.append("screenshot")
    if not (trade.get("reasoning") or trade.get("ai_analysis")):
        gaps.append("reasoning")
    if not trade.get("closed_at"):
        gaps.append("closed_trade")
    return gaps


def _merge_exam_journal_data(trade: dict, engine_obj) -> dict:
    """Overlay journal notes/ASR fields onto a DB trade row."""
    merged = dict(trade)
    if engine_obj is None or getattr(engine_obj, "trade_journal", None) is None:
        return merged
    journal_row = next(
        (
            t for t in engine_obj.trade_journal.get_trades(limit=9999)
            if t.get("trade_id") == trade.get("id")
        ),
        None,
    )
    if not journal_row:
        return merged
    for key in (
        "trade_summary",
        "management_notes",
        "screenshots",
        "emotional_notes_pre",
        "emotional_notes_during",
        "emotional_notes_post",
        "asr_completed",
        "asr_htf_correct",
        "asr_ltf_correct",
        "asr_strategy_correct",
        "asr_sl_correct",
        "asr_tp_correct",
        "asr_management_correct",
        "asr_would_enter_again",
        "asr_lessons",
        "asr_error_type",
        "trading_style",
        "timeframes_used",
        "duration_minutes",
    ):
        if key in journal_row:
            merged[key] = journal_row.get(key)
    if not merged.get("trade_summary"):
        merged["trade_summary"] = merged.get("reasoning") or merged.get("ai_analysis") or ""
    return merged


@router.post("/exam/generate")
async def generate_exam_report(req: ExamRequest):
    """Generate a TradingLab exam report with 3 trades.
    Each trade includes: chart screenshot, HTF/LTF analysis, strategy identification,
    risk calculation, and rule checklist."""
    from main import db, engine
    import base64

    if db is None:
        raise HTTPException(503, "Database not available")
    # Mentorship deliverable is exactly 3 trades.
    if len(req.trade_ids) != 3:
        raise HTTPException(400, "Exactly 3 trade IDs are required for exam submission")

    trades = []
    for tid in req.trade_ids:
        # Get trade from DB
        cursor = await db._db.execute(
            "SELECT * FROM trades WHERE id = ?", [tid]
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(404, f"Trade {tid} not found")
        trade = _merge_exam_journal_data(dict(row), engine)

        # Live scan state is supplemental only; the persisted trade row is the
        # primary source of truth for exam evidence.
        analysis = engine.last_scan_results.get(trade.get("instrument", ""), None) if engine else None

        screenshot_paths: List[str] = []
        if engine is not None and engine.screenshot_generator is not None:
            screenshot_paths = engine.screenshot_generator.get_screenshot_path(tid)

        gaps = _exam_gaps_for_trade(trade, screenshot_paths)
        if gaps:
            raise HTTPException(
                400,
                f"Trade {tid} is not exam-ready. Missing: {', '.join(gaps)}",
            )

        screenshot_b64 = None
        chosen = _pick_exam_screenshot(screenshot_paths)
        if chosen:
            from pathlib import Path
            shot_path = Path(chosen)
            if shot_path.exists():
                screenshot_b64 = base64.b64encode(shot_path.read_bytes()).decode()

        # Compute derived metrics the mentorship exam wants to see
        _entry = trade.get("entry_price") or 0
        _exit = trade.get("exit_price") or 0
        _sl = trade.get("stop_loss") or 0
        _tp = trade.get("take_profit") or 0
        _dir = (trade.get("direction") or "").upper()
        _risk_dist = abs(_entry - _sl) if (_entry and _sl) else 0
        _rr_planned = 0.0
        if _risk_dist > 0 and _tp and _entry:
            tp_dist = abs(_tp - _entry)
            _rr_planned = round(tp_dist / _risk_dist, 2)
        _rr_achieved = 0.0
        if _risk_dist > 0 and _exit and _entry:
            if _dir == "BUY":
                realized = _exit - _entry
            else:
                realized = _entry - _exit
            _rr_achieved = round(realized / _risk_dist, 2)
        # Risk-in-dollars: if units and SL distance are known. We don't have
        # per-trade account balance at the time of open, so Risk % is
        # expressed vs. the recorded pnl magnitude.
        _risk_dollars = _risk_dist * abs(trade.get("units") or 0)

        # Build trade analysis for exam
        exam_trade = {
            "trade_id": tid,
            "instrument": trade.get("instrument", "Unknown"),
            "direction": trade.get("direction", "Unknown"),
            "strategy": trade.get("strategy", "Unknown"),
            "strategy_variant": trade.get("strategy_variant", ""),
            "entry_price": _entry,
            "exit_price": _exit,
            "stop_loss": _sl,
            "take_profit": _tp,
            "pnl": trade.get("pnl", 0),
            "status": trade.get("status", ""),
            "opened_at": trade.get("opened_at", ""),
            "closed_at": trade.get("closed_at", ""),
            "units": trade.get("units", 0),
            "risk_reward_ratio": trade.get("risk_reward_ratio") or _rr_planned,
            "rr_achieved": _rr_achieved,
            "risk_dollars": round(_risk_dollars, 2) if _risk_dollars else 0,
            "confidence": trade.get("confidence") or 0,
            "ai_analysis": trade.get("ai_analysis", ""),
            "reasoning": trade.get("reasoning", ""),
            "trade_summary": trade.get("trade_summary", ""),
            "management_notes": trade.get("management_notes", ""),
            "emotional_notes_pre": trade.get("emotional_notes_pre", ""),
            "emotional_notes_during": trade.get("emotional_notes_during", ""),
            "emotional_notes_post": trade.get("emotional_notes_post", ""),
            "asr_completed": bool(trade.get("asr_completed")),
            "asr_lessons": trade.get("asr_lessons", ""),
            "asr_would_enter_again": trade.get("asr_would_enter_again"),
            "screenshot_b64": screenshot_b64,
            "screenshot_files": screenshot_paths,
            "htf_analysis": None,
            "ltf_analysis": None,
        }
        if not exam_trade["management_notes"]:
            exam_trade["management_notes"] = (
                f"Cierre {trade.get('status', 'closed')} con {exam_trade['rr_achieved']:+.2f}R "
                f"y P&L ${abs(exam_trade['pnl'] or 0):.2f}."
            )

        # Add analysis details if available
        if analysis:
            exam_trade["htf_analysis"] = {
                "trend": str(getattr(analysis, 'htf_trend', 'N/A')),
                "condition": str(getattr(analysis, 'htf_condition', 'N/A')),
                "score": getattr(analysis, 'score', 0),
            }
            exam_trade["ltf_analysis"] = {
                "trend": str(getattr(analysis, 'ltf_trend', 'N/A')),
                "convergence": getattr(analysis, 'htf_ltf_convergence', False),
            }

        trades.append(exam_trade)

    # Build HTML report
    html = _build_exam_html(trades)
    return {"html": html, "trades": trades}


@router.get("/exam/trades")
async def get_exam_eligible_trades():
    """Get all closed trades eligible for exam submission."""
    from main import db, engine
    if db is None:
        return []
    trades = await db.get_trade_history(limit=200, offset=0)
    eligible = []
    for trade in trades:
        if trade.get("status", "") == "open":
            continue
        row = _merge_exam_journal_data(dict(trade), engine)
        screenshot_paths: List[str] = []
        if engine is not None and engine.screenshot_generator is not None:
            screenshot_paths = engine.screenshot_generator.get_screenshot_path(
                trade.get("id", "")
            )
        row["exam_screenshots"] = screenshot_paths
        row["exam_gaps"] = _exam_gaps_for_trade(trade, screenshot_paths)
        row["exam_ready"] = len(row["exam_gaps"]) == 0
        eligible.append(row)
    eligible.sort(
        key=lambda t: (
            not t.get("exam_ready", False),
            t.get("closed_at") or t.get("opened_at") or "",
        )
    )
    return eligible


def _build_exam_html(trades: list) -> str:
    """Build Apple-style HTML report for TradingLab exam submission."""
    from datetime import datetime, timezone
    import html

    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

    def _esc(text: object) -> str:
        return html.escape(str(text or "")).replace("\n", "<br>")

    def _fmt_price(v: float, inst: str) -> str:
        # JPY pairs use 3 decimals; crypto/indices can be >0.01 per tick
        # so 2 decimals is fine; default 5 decimals for forex majors.
        if not v:
            return "—"
        upper = (inst or "").upper()
        if "JPY" in upper:
            return f"{v:.3f}"
        if any(k in upper for k in ("BTC", "ETH", "XAU", "SPX", "NAS", "US30", "GER40", "UK100")):
            return f"{v:,.2f}"
        return f"{v:.5f}"

    trade_sections = ""
    for i, t in enumerate(trades, 1):
        pnl = t.get("pnl", 0) or 0
        pnl_color = "#34C759" if pnl >= 0 else "#FF3B30"
        pnl_sign = "+" if pnl >= 0 else ""
        raw_status = (t.get("status", "") or "").replace("closed_", "").upper()
        status = raw_status or "CLOSED"
        direction = t.get("direction", "")
        dir_color = "#34C759" if direction.upper() == "BUY" else "#FF3B30"
        inst = t.get("instrument", "")
        rr_planned = t.get("risk_reward_ratio", 0) or 0
        rr_achieved = t.get("rr_achieved", 0) or 0
        risk_dollars = t.get("risk_dollars", 0) or 0
        confidence = t.get("confidence") or 0

        # Screenshot image
        img_html = ""
        if t.get("screenshot_b64"):
            img_html = f'<img src="data:image/png;base64,{t["screenshot_b64"]}" style="width:100%;border-radius:12px;margin-bottom:16px;" alt="Chart">'

        # Analysis details
        htf_html = ""
        if t.get("htf_analysis"):
            htf = t["htf_analysis"]
            htf_html = f'''
            <div style="margin-bottom:8px;">
                <span style="font-size:12px;font-weight:600;color:#86868b;letter-spacing:0.5px;">HTF ANALYSIS</span><br>
                <span style="font-size:14px;color:#1d1d1f;">Trend: {htf.get("trend", "N/A")} | Condition: {htf.get("condition", "N/A")} | Score: {htf.get("score", 0)}/100</span>
            </div>'''

        ltf_html = ""
        if t.get("ltf_analysis"):
            ltf = t["ltf_analysis"]
            conv = "Yes" if ltf.get("convergence") else "No"
            ltf_html = f'''
            <div style="margin-bottom:8px;">
                <span style="font-size:12px;font-weight:600;color:#86868b;letter-spacing:0.5px;">LTF ANALYSIS</span><br>
                <span style="font-size:14px;color:#1d1d1f;">Trend: {ltf.get("trend", "N/A")} | Convergence: {conv}</span>
            </div>'''

        reasoning_html = ""
        if t.get("reasoning"):
            reasoning_html = f'''
            <div style="margin-top:12px;background:#f9f9f9;border-radius:10px;padding:12px;">
                <span style="font-size:12px;font-weight:600;color:#86868b;">POR QUÉ SE EJECUTÓ</span><br>
                <span style="font-size:13px;color:#1d1d1f;line-height:1.7;">{_esc(t.get("reasoning", ""))}</span>
            </div>'''

        summary_html = ""
        if t.get("trade_summary"):
            summary_html = f'''
            <div style="margin-top:12px;background:#f9f9f9;border-radius:10px;padding:12px;">
                <span style="font-size:12px;font-weight:600;color:#86868b;">RESUMEN DEL TRADE</span><br>
                <span style="font-size:13px;color:#1d1d1f;line-height:1.7;">{_esc(t.get("trade_summary", ""))}</span>
            </div>'''

        management_html = ""
        if t.get("management_notes"):
            management_html = f'''
            <div style="margin-top:12px;background:#f9f9f9;border-radius:10px;padding:12px;">
                <span style="font-size:12px;font-weight:600;color:#86868b;">GESTIÓN DE POSICIÓN</span><br>
                <span style="font-size:13px;color:#1d1d1f;line-height:1.7;">{_esc(t.get("management_notes", ""))}</span>
            </div>'''

        asr_html = ""
        if t.get("asr_completed") or t.get("asr_lessons"):
            would_reenter = t.get("asr_would_enter_again")
            would_reenter_label = "Sí" if would_reenter is True else "No" if would_reenter is False else "N/A"
            asr_html = f'''
            <div style="margin-top:12px;background:#f9f9f9;border-radius:10px;padding:12px;">
                <span style="font-size:12px;font-weight:600;color:#86868b;">ASR</span><br>
                <span style="font-size:13px;color:#1d1d1f;line-height:1.7;">Completado: {"Sí" if t.get("asr_completed") else "No"} &middot; ¿Volvería a entrar?: {would_reenter_label}</span>
                {f'<br><span style="font-size:13px;color:#86868b;line-height:1.7;">{_esc(t.get("asr_lessons", ""))}</span>' if t.get("asr_lessons") else ''}
            </div>'''

        trade_sections += f'''
        <div style="background:#ffffff;border-radius:16px;padding:24px;margin-bottom:16px;box-shadow:0 2px 12px rgba(0,0,0,0.06);">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                <span style="font-size:12px;font-weight:600;color:#86868b;">TRADE {i} OF {len(trades)}</span>
                <span style="font-size:12px;font-weight:600;color:{pnl_color};background:{pnl_color}18;padding:4px 10px;border-radius:8px;">{status}</span>
            </div>

            <div style="font-size:24px;font-weight:700;color:#1d1d1f;letter-spacing:-0.3px;margin-bottom:4px;">{t.get("instrument", "")}</div>
            <div style="margin-bottom:16px;">
                <span style="font-size:14px;font-weight:600;color:{dir_color};">{direction.upper()}</span>
                <span style="font-size:14px;color:#86868b;margin-left:8px;">{t.get("strategy", "")} {t.get("strategy_variant", "")}</span>
            </div>

            {img_html}

            <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:8px;margin-bottom:16px;">
                <div style="background:#f9f9f9;border-radius:10px;padding:10px;text-align:center;">
                    <div style="font-size:10px;font-weight:500;color:#aeaeb2;margin-bottom:2px;">ENTRY</div>
                    <div style="font-size:14px;font-weight:600;color:#1d1d1f;">{_fmt_price(t.get("entry_price", 0), inst)}</div>
                </div>
                <div style="background:#f9f9f9;border-radius:10px;padding:10px;text-align:center;">
                    <div style="font-size:10px;font-weight:500;color:#aeaeb2;margin-bottom:2px;">SL</div>
                    <div style="font-size:14px;font-weight:600;color:#FF3B30;">{_fmt_price(t.get("stop_loss", 0), inst)}</div>
                </div>
                <div style="background:#f9f9f9;border-radius:10px;padding:10px;text-align:center;">
                    <div style="font-size:10px;font-weight:500;color:#aeaeb2;margin-bottom:2px;">TP</div>
                    <div style="font-size:14px;font-weight:600;color:#34C759;">{_fmt_price(t.get("take_profit", 0), inst)}</div>
                </div>
                <div style="background:#f9f9f9;border-radius:10px;padding:10px;text-align:center;">
                    <div style="font-size:10px;font-weight:500;color:#aeaeb2;margin-bottom:2px;">P&amp;L</div>
                    <div style="font-size:14px;font-weight:600;color:{pnl_color};">{pnl_sign}${abs(pnl):.2f}</div>
                </div>
            </div>

            <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:8px;margin-bottom:16px;">
                <div style="background:#f9f9f9;border-radius:10px;padding:10px;text-align:center;">
                    <div style="font-size:10px;font-weight:500;color:#aeaeb2;margin-bottom:2px;">R:R PLAN</div>
                    <div style="font-size:14px;font-weight:600;color:#1d1d1f;">{rr_planned:.2f}:1</div>
                </div>
                <div style="background:#f9f9f9;border-radius:10px;padding:10px;text-align:center;">
                    <div style="font-size:10px;font-weight:500;color:#aeaeb2;margin-bottom:2px;">R:R HECHO</div>
                    <div style="font-size:14px;font-weight:600;color:{'#34C759' if rr_achieved>=0 else '#FF3B30'};">{rr_achieved:+.2f}R</div>
                </div>
                <div style="background:#f9f9f9;border-radius:10px;padding:10px;text-align:center;">
                    <div style="font-size:10px;font-weight:500;color:#aeaeb2;margin-bottom:2px;">RIESGO</div>
                    <div style="font-size:14px;font-weight:600;color:#1d1d1f;">${risk_dollars:,.2f}</div>
                </div>
                <div style="background:#f9f9f9;border-radius:10px;padding:10px;text-align:center;">
                    <div style="font-size:10px;font-weight:500;color:#aeaeb2;margin-bottom:2px;">CONFIANZA</div>
                    <div style="font-size:14px;font-weight:600;color:#1d1d1f;">{(confidence*100 if 0<=confidence<=1 else confidence):.0f}%</div>
                </div>
            </div>

            {htf_html}
            {ltf_html}

            <div style="margin-top:8px;">
                <span style="font-size:12px;font-weight:600;color:#86868b;letter-spacing:0.5px;">GESTIÓN</span><br>
                <span style="font-size:14px;color:#1d1d1f;">Units: {t.get("units", 0)} &middot; Abierto: {t.get("opened_at", "—")} &middot; Cerrado: {t.get("closed_at", "—")}</span>
            </div>

            {reasoning_html}
            {summary_html}
            {management_html}
            {asr_html}
            {f'<div style="margin-top:12px;background:#f9f9f9;border-radius:10px;padding:12px;"><span style="font-size:12px;font-weight:600;color:#86868b;">AI ANALYSIS</span><br><span style="font-size:13px;color:#86868b;line-height:1.6;">{_esc(t.get("ai_analysis", ""))}</span></div>' if t.get("ai_analysis") else ""}
        </div>'''

    return f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Atlas - TradingLab Exam</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; font-family: -apple-system, 'SF Pro Display', 'Helvetica Neue', sans-serif; }}
  body {{ background: #f2f2f7; color: #1d1d1f; padding: 24px; }}
  @media print {{ body {{ padding: 0; }} }}
</style>
</head>
<body>
<div style="max-width:700px;margin:0 auto;">
    <div style="text-align:center;margin-bottom:32px;">
        <div style="font-size:12px;font-weight:600;color:#86868b;letter-spacing:0.5px;text-transform:uppercase;margin-bottom:8px;">TradingLab Final Exam</div>
        <div style="font-size:34px;font-weight:700;color:#1d1d1f;letter-spacing:-0.5px;">Trade Analysis Report</div>
        <div style="font-size:15px;color:#86868b;margin-top:8px;">Generated by Atlas &middot; {ts}</div>
    </div>

    {trade_sections}

    <div style="text-align:center;padding:24px;color:#aeaeb2;font-size:12px;">
        Atlas &middot; TradingLab Mentorship &middot; {ts}
    </div>
</div>
</body>
</html>'''
