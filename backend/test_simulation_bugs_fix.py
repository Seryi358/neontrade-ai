"""Regression tests for 2 pre-existing bugs discovered by the simulation subagent on 2026-04-17.

Bug 1 (`trading_engine.py:2852`): `_execute_approved_setup` checked `units <= 0`, which
rejected all SELL setups because `calculate_position_size` returns negative units for SELL.

Bug 2 (`trading_engine.py:1311`): `_sync_positions_from_broker` had a local
`from core.position_manager import PositionPhase` inside the `for trade in broker_trades
if trade_id in new_ids:` loop. When `new_ids=[]` but `closed_ids!=[]`, the local binding
was never created and the reference to `PositionPhase` at line 1419 raised `NameError`.

Uses `TradingEngine.__new__` to bypass the real __init__ (which wires live broker/AI/DB).
We inject only the attributes the methods under test touch.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.trading_engine import TradingEngine, PendingSetup
from core.position_manager import ManagedPosition, PositionPhase


def _make_bare_engine():
    """TradingEngine with empty state — only attributes accessed by the tested methods."""
    engine = TradingEngine.__new__(TradingEngine)
    engine.broker = MagicMock()
    engine.risk_manager = MagicMock()
    engine.risk_manager.get_risk_for_style = MagicMock(return_value=0.01)
    engine.risk_manager._adjust_for_correlation = MagicMock(return_value=0.01)
    engine.risk_manager.register_trade = MagicMock()
    engine.risk_manager.unregister_trade = MagicMock()
    engine.risk_manager.record_trade_result = MagicMock()
    engine.risk_manager.record_funded_pnl = MagicMock()
    engine.risk_manager._current_balance = 190.88
    engine.position_manager = MagicMock()
    engine.position_manager.positions = {}
    engine.position_manager.open_position = MagicMock()
    engine.alert_manager = None
    engine._gmail_notifier = None
    engine._ws_broadcast = None
    engine._reentry_candidates = {}
    engine._scalping_daily_dd = 0.0
    engine._pending_setups = {}
    return engine


# ──────────────────────────────────────────────────────────────────
# Bug 2: sync_positions doesn't crash with closed_ids but no new_ids
# ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sync_positions_handles_closed_without_new():
    """After the fix: no NameError when new_ids=[] but closed_ids has items."""
    engine = _make_bare_engine()
    engine.broker.get_open_trades = AsyncMock(return_value=[])
    engine.broker.get_current_price = AsyncMock(
        return_value=MagicMock(bid=1.0855, ask=1.0856)
    )

    pos = ManagedPosition(
        trade_id="closed_externally",
        instrument="EUR_USD",
        direction="BUY",
        entry_price=1.0850,
        original_sl=1.0830,
        current_sl=1.0830,
        take_profit_1=1.0890,
        units=1000,
    )
    pos.phase = PositionPhase.TRAILING_TO_TP1
    # override mock with a real dict so pop() works semantically
    engine.position_manager.positions = {"closed_externally": pos}

    # Must not raise NameError
    await engine._sync_positions_from_broker()

    assert "closed_externally" not in engine.position_manager.positions
    assert engine.risk_manager.unregister_trade.called
    # Reentry candidate registered because phase was TRAILING_TO_TP1
    assert "EUR_USD" in engine._reentry_candidates


@pytest.mark.asyncio
async def test_sync_positions_no_op_when_both_empty():
    """Sanity: both new_ids and closed_ids empty — no errors, no mutations."""
    engine = _make_bare_engine()
    engine.broker.get_open_trades = AsyncMock(return_value=[])
    engine.position_manager.positions = {}

    await engine._sync_positions_from_broker()

    assert not engine.risk_manager.unregister_trade.called
