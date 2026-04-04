"""
Tests for resilience.py — covering retry, circuit breaker, and TTL cache.
"""

import pytest
import asyncio
import time
from unittest.mock import patch
from core.resilience import retry_async, CircuitBreaker, TTLCache


# ──────────────────────────────────────────────────────────────────
# retry_async
# ──────────────────────────────────────────────────────────────────

class TestRetryAsync:
    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        call_count = 0

        @retry_async(max_retries=3, base_delay=0.01)
        async def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await succeed()
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure_then_succeeds(self):
        call_count = 0

        @retry_async(max_retries=3, base_delay=0.01)
        async def fail_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("transient")
            return "recovered"

        result = await fail_twice()
        assert result == "recovered"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self):
        @retry_async(max_retries=2, base_delay=0.01)
        async def always_fail():
            raise RuntimeError("permanent")

        with pytest.raises(RuntimeError, match="permanent"):
            await always_fail()

    @pytest.mark.asyncio
    async def test_only_catches_specified_exceptions(self):
        @retry_async(max_retries=3, base_delay=0.01, exceptions=(ValueError,))
        async def type_error():
            raise TypeError("wrong type")

        with pytest.raises(TypeError):
            await type_error()

    @pytest.mark.asyncio
    async def test_respects_429_retry_after(self):
        """429 with Retry-After header should use that delay."""
        call_count = 0

        class FakeResponse:
            status_code = 429
            headers = {"Retry-After": "0.05"}

        class RateLimitError(Exception):
            def __init__(self):
                super().__init__("429")
                self.response = FakeResponse()

        @retry_async(max_retries=1, base_delay=0.01, max_delay=1.0)
        async def rate_limited():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RateLimitError()
            return "ok"

        result = await rate_limited()
        assert result == "ok"
        assert call_count == 2


# ──────────────────────────────────────────────────────────────────
# CircuitBreaker
# ──────────────────────────────────────────────────────────────────

class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10.0)
        assert cb.state == CircuitBreaker.CLOSED
        assert not cb.is_open

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        assert cb.is_open

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb._failure_count == 0
        cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED

    def test_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        time.sleep(0.02)
        assert cb.state == CircuitBreaker.HALF_OPEN

    def test_half_open_to_closed_on_success(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == CircuitBreaker.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED

    def test_reset(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        cb.reset()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb._failure_count == 0


# ──────────────────────────────────────────────────────────────────
# TTLCache
# ──────────────────────────────────────────────────────────────────

class TestTTLCache:
    def test_set_and_get(self):
        cache = TTLCache(ttl_seconds=10.0)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_expired_entry_returns_none(self):
        cache = TTLCache(ttl_seconds=0.01)
        cache.set("key1", "value1")
        time.sleep(0.02)
        assert cache.get("key1") is None

    def test_get_nonexistent_returns_none(self):
        cache = TTLCache()
        assert cache.get("nonexistent") is None

    def test_invalidate(self):
        cache = TTLCache()
        cache.set("key1", "value1")
        cache.invalidate("key1")
        assert cache.get("key1") is None

    def test_invalidate_nonexistent_no_error(self):
        cache = TTLCache()
        cache.invalidate("nonexistent")  # Should not raise

    def test_clear(self):
        cache = TTLCache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None
