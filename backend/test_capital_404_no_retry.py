"""
Tests for Capital.com 4xx no-retry whitelist on the `_get` path (audit A9).

Background: the audit found 63 404 warnings in 12 min, each retried 3x.
_post/_put/_delete already skip retries on permanent 4xx via
`_is_permanent_error`. `_get` did not, so it wasted API quota and could
trigger secondary 429 throttling. This test locks in the fix: 400/404/422
must fail fast (1 attempt only) while 5xx and network errors still retry.
"""
import httpx
import pytest

from broker.capital_client import CapitalClient
from core.resilience import broker_circuit_breaker


@pytest.fixture(autouse=True)
def _reset_circuit_breaker():
    """Reset the circuit breaker between tests so failures don't leak."""
    broker_circuit_breaker.reset()
    yield
    broker_circuit_breaker.reset()


def _make_client():
    """Build a CapitalClient with a pre-populated session (no auth call)."""
    client = CapitalClient(
        api_key="KEY", password="PW", identifier="u@t", environment="demo",
    )
    # Pre-populate session so _ensure_session is a no-op (within TTL).
    from datetime import datetime, timezone
    client._cst = "CST"
    client._security_token = "XST"
    client._session_time = datetime.now(timezone.utc)
    return client


class _FakeResponse:
    def __init__(self, status_code=200, json_body=None, headers=None):
        self.status_code = status_code
        self._json = json_body if json_body is not None else {}
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}", request=None, response=self,
            )

    def json(self):
        return self._json


# ── Tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_404_raises_immediately_without_retry():
    """A 404 response must raise after exactly 1 attempt — no retries."""
    client = _make_client()
    calls = []

    async def fake_get(path, headers=None, params=None):
        calls.append(path)
        return _FakeResponse(status_code=404)

    client._client.get = fake_get

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await client._get("/api/v1/markets/NONEXISTENT")

    assert exc_info.value.response.status_code == 404
    assert len(calls) == 1, f"Expected 1 call, got {len(calls)}"


@pytest.mark.asyncio
async def test_400_raises_immediately_without_retry():
    """400 is also permanent — fail fast."""
    client = _make_client()
    calls = []

    async def fake_get(path, headers=None, params=None):
        calls.append(path)
        return _FakeResponse(status_code=400)

    client._client.get = fake_get

    with pytest.raises(httpx.HTTPStatusError):
        await client._get("/api/v1/bad-request")

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_422_raises_immediately_without_retry():
    """422 unprocessable — fail fast."""
    client = _make_client()
    calls = []

    async def fake_get(path, headers=None, params=None):
        calls.append(path)
        return _FakeResponse(status_code=422)

    client._client.get = fake_get

    with pytest.raises(httpx.HTTPStatusError):
        await client._get("/api/v1/unprocessable")

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_403_raises_immediately_without_retry():
    """403 forbidden — fail fast (consistent with _post/_put/_delete)."""
    client = _make_client()
    calls = []

    async def fake_get(path, headers=None, params=None):
        calls.append(path)
        return _FakeResponse(status_code=403)

    client._client.get = fake_get

    with pytest.raises(httpx.HTTPStatusError):
        await client._get("/api/v1/forbidden")

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_500_still_retries():
    """5xx remains transient — must still retry 3 more times (4 attempts total)."""
    client = _make_client()
    calls = []

    async def fake_get(path, headers=None, params=None):
        calls.append(path)
        return _FakeResponse(status_code=500)

    client._client.get = fake_get

    # Patch asyncio.sleep to avoid real delays
    import asyncio as _asyncio

    async def no_sleep(_):
        return

    original_sleep = _asyncio.sleep
    _asyncio.sleep = no_sleep
    try:
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await client._get("/api/v1/server-error")
    finally:
        _asyncio.sleep = original_sleep

    assert exc_info.value.response.status_code == 500
    # _get does 1 initial + 3 retries = 4 total
    assert len(calls) == 4, f"Expected 4 attempts for 500, got {len(calls)}"


@pytest.mark.asyncio
async def test_429_still_retries():
    """429 rate-limit is retryable (with backoff/Retry-After)."""
    client = _make_client()
    calls = []

    async def fake_get(path, headers=None, params=None):
        calls.append(path)
        return _FakeResponse(status_code=429, headers={"Retry-After": "0"})

    client._client.get = fake_get

    import asyncio as _asyncio

    async def no_sleep(_):
        return

    original_sleep = _asyncio.sleep
    _asyncio.sleep = no_sleep
    try:
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await client._get("/api/v1/rate-limited")
    finally:
        _asyncio.sleep = original_sleep

    assert exc_info.value.response.status_code == 429
    assert len(calls) == 4, f"Expected 4 attempts for 429, got {len(calls)}"


@pytest.mark.asyncio
async def test_404_records_at_most_one_circuit_breaker_failure():
    """A permanent 4xx must not accumulate multiple CB failures in one call.
    (_post/_put/_delete already record exactly 1; _get must behave the same
    so scanning unknown symbols doesn't trip the breaker faster than the
    real broker-outage case.)
    """
    client = _make_client()

    async def fake_get(path, headers=None, params=None):
        return _FakeResponse(status_code=404)

    client._client.get = fake_get

    initial_failures = broker_circuit_breaker._failure_count
    with pytest.raises(httpx.HTTPStatusError):
        await client._get("/api/v1/markets/GHOST")
    delta = broker_circuit_breaker._failure_count - initial_failures

    assert delta <= 1, f"Expected ≤1 CB failure for 404, got {delta}"
