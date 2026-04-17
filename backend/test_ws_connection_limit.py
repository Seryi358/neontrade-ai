"""
Test: WebSocket connection limit is atomic (audit M7).

Previously the check `len(active_connections) >= MAX_WS_CONNECTIONS` was
separated from the subsequent `append()` by an `await`, creating a TOCTOU
race. Under burst load this allowed the manager to exceed the cap.

After fix: asyncio.Lock serializes check-and-append, so exactly
MAX_WS_CONNECTIONS clients get accepted even when `MAX+5` arrive concurrently.
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def _yield_then_return(*_a, **_kw):
    """Accept/close shim that actually yields the event loop, exposing races."""
    await asyncio.sleep(0)
    return None


def _fake_ws():
    """Build a WebSocket stub whose accept/close yield to the event loop.

    Using a plain AsyncMock doesn't yield, so a TOCTOU race between the
    capacity check and the append wouldn't be observable. Forcing
    `asyncio.sleep(0)` inside accept mimics the real network round-trip and
    allows the scheduler to interleave concurrent connect() calls.
    """
    ws = MagicMock()
    ws.accept = AsyncMock(side_effect=_yield_then_return)
    ws.close = AsyncMock(side_effect=_yield_then_return)
    return ws


@pytest.mark.asyncio
async def test_connection_limit_is_atomic():
    """Launch MAX+5 concurrent connect() calls and assert exactly MAX succeed."""
    from main import ConnectionManager, MAX_WS_CONNECTIONS

    mgr = ConnectionManager()
    overflow = 5
    clients = [_fake_ws() for _ in range(MAX_WS_CONNECTIONS + overflow)]

    results = await asyncio.gather(*[mgr.connect(ws) for ws in clients])

    accepted = sum(1 for r in results if r is True)
    rejected = sum(1 for r in results if r is False)

    assert accepted == MAX_WS_CONNECTIONS, (
        f"Expected {MAX_WS_CONNECTIONS} accepted, got {accepted} "
        f"(rejected={rejected}). Lock is not serializing check-and-append."
    )
    assert rejected == overflow
    assert len(mgr.active_connections) == MAX_WS_CONNECTIONS


@pytest.mark.asyncio
async def test_disconnect_under_lock():
    """Disconnect is also lock-protected and idempotent."""
    from main import ConnectionManager

    mgr = ConnectionManager()
    ws = _fake_ws()
    assert await mgr.connect(ws) is True
    assert len(mgr.active_connections) == 1

    # Disconnect twice concurrently — must not raise.
    await asyncio.gather(mgr.disconnect(ws), mgr.disconnect(ws))
    assert len(mgr.active_connections) == 0


@pytest.mark.asyncio
async def test_has_lock_attribute():
    """ConnectionManager must expose an asyncio.Lock named _lock."""
    from main import ConnectionManager

    mgr = ConnectionManager()
    assert isinstance(mgr._lock, asyncio.Lock)
