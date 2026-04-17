"""
Test: matplotlib screenshot rendering does not block the event loop (audit M9).

Before the fix `capture_trade_open` / `capture_trade_close` called the
matplotlib helpers directly. Those helpers are synchronous and can take
hundreds of milliseconds, freezing the trading engine's heartbeat and broker
polling loop.

After the fix the helpers are wrapped in `run_in_executor`, which offloads
them to a thread and lets other coroutines (heartbeats, WS broadcasts) tick
concurrently. The tests below install a slow synchronous render step and
verify that a parallel "heartbeat" coroutine continues to advance while the
screenshot is being generated.
"""

import asyncio
import os
import sys
import time
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


@pytest.mark.asyncio
async def test_capture_trade_open_does_not_block_heartbeat(tmp_path):
    from core.screenshot_generator import TradeScreenshotGenerator, HAS_MATPLOTLIB

    if not HAS_MATPLOTLIB:
        pytest.skip("matplotlib not installed")

    gen = TradeScreenshotGenerator(data_dir=str(tmp_path))

    # Install a slow synchronous render that would block the loop if called
    # directly. 200 ms is long enough that a sync call would miss 10+ 10-ms
    # heartbeat ticks.
    heartbeat_ticks = 0

    def slow_info_card(filepath, trade_info):
        time.sleep(0.2)
        # Touch the output file so `capture_trade_open` logs a success.
        with open(filepath, "wb") as f:
            f.write(b"x")

    async def heartbeat():
        nonlocal heartbeat_ticks
        while True:
            heartbeat_ticks += 1
            await asyncio.sleep(0.01)

    hb_task = asyncio.create_task(heartbeat())

    with patch.object(gen, "_generate_info_card", side_effect=slow_info_card):
        # candles=None forces the info-card branch
        path = await gen.capture_trade_open(
            trade_id="t1",
            instrument="EURUSD",
            direction="BUY",
            entry_price=1.1,
            sl=1.09,
            tp1=1.12,
            tp_max=1.13,
            strategy="test",
            confidence=0.9,
            candles=None,
        )

    hb_task.cancel()
    try:
        await hb_task
    except asyncio.CancelledError:
        pass

    assert path, "capture_trade_open should return the saved filepath"
    # With executor offload, the heartbeat should have ticked ~15-20 times
    # during the 200 ms render. Without offload it would be ~0-1.
    assert heartbeat_ticks >= 5, (
        f"Event loop was blocked during screenshot: heartbeat ticked only "
        f"{heartbeat_ticks} times (expected ≥5). Rendering is not offloaded."
    )


@pytest.mark.asyncio
async def test_capture_trade_close_does_not_block_heartbeat(tmp_path):
    from core.screenshot_generator import TradeScreenshotGenerator, HAS_MATPLOTLIB

    if not HAS_MATPLOTLIB:
        pytest.skip("matplotlib not installed")

    gen = TradeScreenshotGenerator(data_dir=str(tmp_path))
    heartbeat_ticks = 0

    def slow_info_card(filepath, trade_info):
        time.sleep(0.2)
        with open(filepath, "wb") as f:
            f.write(b"x")

    async def heartbeat():
        nonlocal heartbeat_ticks
        while True:
            heartbeat_ticks += 1
            await asyncio.sleep(0.01)

    hb_task = asyncio.create_task(heartbeat())

    with patch.object(gen, "_generate_info_card", side_effect=slow_info_card):
        path = await gen.capture_trade_close(
            trade_id="t2",
            instrument="EURUSD",
            direction="BUY",
            entry_price=1.1,
            close_price=1.12,
            pnl_pct=1.82,
            result="TP",
            candles=None,
        )

    hb_task.cancel()
    try:
        await hb_task
    except asyncio.CancelledError:
        pass

    assert path
    assert heartbeat_ticks >= 5, (
        f"Event loop blocked during close screenshot: heartbeat ticked "
        f"{heartbeat_ticks} times."
    )
