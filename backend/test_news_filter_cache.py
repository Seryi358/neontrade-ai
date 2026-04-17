"""
Test: News filter calendar is persisted to disk so that a transient outage of
FairEconomy + TradingEconomics does not leave the bot with zero events —
which was causing trading during NFP/FOMC (audit A11).

Behavior after fix:
  1. Successful fetch → events are cached in memory AND persisted to disk.
  2. Subsequent fetch failure → reuse disk cache if <48h old.
  3. Disk cache missing/stale → fall back to hardcoded RECURRING high-impact events.
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.news_filter import NewsFilter, NewsEvent, TradingStyle


@pytest.fixture
def tmp_cache(tmp_path, monkeypatch):
    """Redirect the news cache path to a tmp dir for the duration of the test."""
    from core import news_filter as nf_mod
    cache_path = tmp_path / "news_cache.json"
    monkeypatch.setattr(nf_mod, "NEWS_CACHE_PATH", cache_path)
    return cache_path


@pytest.mark.asyncio
async def test_successful_fetch_persists_to_disk(tmp_cache):
    """When fetch succeeds, events are saved to disk."""
    nf = NewsFilter(trading_style=TradingStyle.DAY_TRADING)
    now = datetime.now(timezone.utc)
    fake_event = NewsEvent(
        time=now + timedelta(hours=2),
        currency="USD",
        impact="high",
        title="Non-Farm Payrolls",
    )

    async def ok_faireconomy(_now):
        return [fake_event]

    async def ok_trading_econ(_now):
        return []

    with patch.object(nf, "_fetch_from_faireconomy", side_effect=ok_faireconomy):
        with patch.object(nf, "_fetch_from_trading_economics", side_effect=ok_trading_econ):
            await nf._refresh_calendar(now)

    assert tmp_cache.exists(), "Successful fetch must persist calendar to disk"
    data = json.loads(tmp_cache.read_text("utf-8"))
    assert "events" in data
    assert "saved_at" in data
    assert len(data["events"]) == 1
    assert data["events"][0]["title"] == "Non-Farm Payrolls"
    assert data["events"][0]["currency"] == "USD"
    assert data["events"][0]["impact"] == "high"

    await nf.close()


@pytest.mark.asyncio
async def test_failed_fetch_reuses_recent_disk_cache(tmp_cache):
    """When both sources fail but disk cache is <48h old, reuse it."""
    nf = NewsFilter(trading_style=TradingStyle.DAY_TRADING)
    now = datetime.now(timezone.utc)

    # Write a fresh disk cache (2h old)
    saved_at = now - timedelta(hours=2)
    event_time = now + timedelta(hours=1)
    cache_payload = {
        "saved_at": saved_at.isoformat(),
        "events": [
            {
                "time": event_time.isoformat(),
                "currency": "USD",
                "impact": "high",
                "title": "FOMC Rate Decision (cached)",
            }
        ],
    }
    tmp_cache.write_text(json.dumps(cache_payload), encoding="utf-8")

    async def failing_fetch(_now):
        raise RuntimeError("network down")

    with patch.object(nf, "_fetch_from_faireconomy", side_effect=failing_fetch):
        with patch.object(nf, "_fetch_from_trading_economics", side_effect=failing_fetch):
            await nf._refresh_calendar(now)

    assert len(nf._cached_events) == 1
    assert nf._cached_events[0].title == "FOMC Rate Decision (cached)"

    await nf.close()


@pytest.mark.asyncio
async def test_failed_fetch_ignores_stale_disk_cache(tmp_cache):
    """Disk cache >48h old must NOT be used; fall back to recurring events."""
    nf = NewsFilter(trading_style=TradingStyle.DAY_TRADING)
    now = datetime.now(timezone.utc)

    # Write a stale disk cache (72h old)
    saved_at = now - timedelta(hours=72)
    cache_payload = {
        "saved_at": saved_at.isoformat(),
        "events": [
            {
                "time": (now + timedelta(hours=1)).isoformat(),
                "currency": "USD",
                "impact": "high",
                "title": "Stale event",
            }
        ],
    }
    tmp_cache.write_text(json.dumps(cache_payload), encoding="utf-8")

    async def failing_fetch(_now):
        raise RuntimeError("network down")

    with patch.object(nf, "_fetch_from_faireconomy", side_effect=failing_fetch):
        with patch.object(nf, "_fetch_from_trading_economics", side_effect=failing_fetch):
            await nf._refresh_calendar(now)

    titles = [e.title for e in nf._cached_events]
    assert "Stale event" not in titles

    await nf.close()


@pytest.mark.asyncio
async def test_failed_fetch_no_disk_cache_falls_back_to_recurring(tmp_cache):
    """No disk cache + both sources fail → use hardcoded recurring events."""
    nf = NewsFilter(trading_style=TradingStyle.DAY_TRADING)
    # Force a date known to have a recurring event (first Friday — NFP).
    # 2026-05-01 is a Friday and day<=7 → matches `first_friday`.
    now = datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.utc)

    assert not tmp_cache.exists()

    async def failing_fetch(_now):
        raise RuntimeError("network down")

    with patch.object(nf, "_fetch_from_faireconomy", side_effect=failing_fetch):
        with patch.object(nf, "_fetch_from_trading_economics", side_effect=failing_fetch):
            await nf._refresh_calendar(now)

    # Should have at least NFP + Unemployment Rate
    assert len(nf._cached_events) >= 1
    titles = " | ".join(e.title for e in nf._cached_events).lower()
    assert "non-farm payrolls" in titles or "nfp" in titles

    await nf.close()
