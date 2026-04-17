"""
Test: /logs endpoint targets today's file using UTC (audit M8).

Loguru rotates by `{time:YYYY-MM-DD}` which is UTC when system clock is UTC
(container default). When the API uses local-time `datetime.now()`, the
filename it searches for can be off-by-one across midnight boundaries,
returning the wrong file or "No log file found" even when logs exist.

The fix pins the filename-date to UTC to match loguru's rotation.
"""

import os
import sys
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _make_app():
    from api.routes import router
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


def test_logs_endpoint_uses_utc_date(tmp_path, monkeypatch):
    """The `/logs` endpoint must build the candidate filename from UTC date.

    We freeze "now" at 23:30 local (UTC offset +5h → 04:30 UTC next day),
    drop a log file with the UTC date, and expect the endpoint to find it.
    """
    # Arrange: create a logs dir with a UTC-dated file
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    # Pick a fixed UTC date and write a file whose name matches that date.
    utc_today_str = "2026-04-17"
    log_path = log_dir / f"atlas_{utc_today_str}.log"
    log_path.write_text("test log line\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    # Mock datetime in routes to return a time where local != UTC date.
    class _FrozenDateTime:
        @staticmethod
        def now(tz=None):
            # Fixed instant: 2026-04-17T23:30 UTC
            return datetime(2026, 4, 17, 23, 30, 0, tzinfo=timezone.utc)

        # Forward other attributes
        def __getattr__(self, name):
            return getattr(datetime, name)

    app = _make_app()
    client = TestClient(app)

    with patch("api.routes.datetime", _FrozenDateTime):
        resp = client.get("/api/v1/logs", params={"lines": 10})

    assert resp.status_code == 200
    body = resp.json()
    assert "file" in body, f"Expected `file` in response, got: {body}"
    assert utc_today_str in body["file"], (
        f"Expected log filename to include UTC date {utc_today_str!r}, got: {body['file']}"
    )


def test_logs_endpoint_imports_timezone():
    """Sanity check: routes.py imports `timezone` alongside `datetime`."""
    import inspect
    import api.routes as routes_mod
    source = inspect.getsource(routes_mod)
    assert "from datetime import datetime, timezone" in source or (
        "datetime" in source and "timezone" in source
    ), "routes.py must import `timezone` for UTC-aware log filenames"
