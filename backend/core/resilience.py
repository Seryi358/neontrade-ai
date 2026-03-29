"""
NeonTrade AI - Resilience Utilities
Retry with exponential backoff, circuit breaker, and TTL cache for broker calls.
"""

import asyncio
import time
import functools
from typing import Optional, TypeVar, Callable, Any
from loguru import logger

T = TypeVar("T")


# ── Retry with Exponential Backoff ────────────────────────────────

def retry_async(
    max_retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 10.0,
    exceptions: tuple = (Exception,),
):
    """
    Decorator for async functions: retries on failure with exponential backoff.

    Usage:
        @retry_async(max_retries=3, base_delay=0.5)
        async def call_broker_api():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    # Check for 429 Rate Limit — respect Retry-After header
                    retry_after = None
                    if hasattr(e, 'response') and e.response is not None:
                        status = getattr(e.response, 'status_code', 0)
                        if status == 429:
                            retry_after_hdr = e.response.headers.get('Retry-After')
                            if retry_after_hdr:
                                try:
                                    retry_after = float(retry_after_hdr)
                                except (ValueError, TypeError):
                                    retry_after = None

                    if attempt < max_retries:
                        if retry_after is not None:
                            delay = min(retry_after + 0.5, 30.0)
                        else:
                            delay = min(base_delay * (2 ** attempt), max_delay)
                        logger.warning(
                            f"[Retry] {func.__name__} attempt {attempt + 1}/{max_retries} "
                            f"failed: {e}. Retrying in {delay:.1f}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"[Retry] {func.__name__} failed after {max_retries + 1} attempts: {e}"
                        )
            raise last_exc
        return wrapper
    return decorator


# ── Circuit Breaker ───────────────────────────────────────────────

class CircuitBreaker:
    """
    Prevents repeated calls to a failing service.

    States:
    - CLOSED: normal operation, calls go through
    - OPEN: service is down, calls fail fast
    - HALF_OPEN: trying one call to see if service recovered
    """

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        name: str = "default",
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.name = name
        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._success_count = 0

    @property
    def state(self) -> str:
        if self._state == self.OPEN:
            if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                self._state = self.HALF_OPEN
                logger.info(f"[CircuitBreaker:{self.name}] -> HALF_OPEN (attempting recovery)")
        return self._state

    def record_success(self):
        self._failure_count = 0
        self._success_count += 1
        if self._state == self.HALF_OPEN:
            self._state = self.CLOSED
            logger.info(f"[CircuitBreaker:{self.name}] -> CLOSED (recovered)")

    def record_failure(self):
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            self._state = self.OPEN
            logger.warning(
                f"[CircuitBreaker:{self.name}] -> OPEN after {self._failure_count} failures. "
                f"Blocking calls for {self.recovery_timeout}s"
            )

    def reset(self):
        """Reset circuit breaker to CLOSED state (e.g. before a new scan cycle)."""
        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0
        self._success_count = 0
        logger.info(f"[CircuitBreaker:{self.name}] -> RESET to CLOSED")

    @property
    def is_open(self) -> bool:
        return self.state == self.OPEN


# ── TTL Cache ─────────────────────────────────────────────────────

class TTLCache:
    """Simple async-safe TTL cache for expensive broker calls."""

    def __init__(self, ttl_seconds: float = 30.0):
        self.ttl = ttl_seconds
        self._cache: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            ts, value = self._cache[key]
            if time.monotonic() - ts < self.ttl:
                return value
            del self._cache[key]
        return None

    def set(self, key: str, value: Any):
        self._cache[key] = (time.monotonic(), value)

    def invalidate(self, key: str):
        self._cache.pop(key, None)

    def clear(self):
        self._cache.clear()


# ── Global instances ──────────────────────────────────────────────
broker_circuit_breaker = CircuitBreaker(
    failure_threshold=5,   # Open after 5 consecutive failures (was 50 — far too high)
    recovery_timeout=30.0,
    name="broker",
)

balance_cache = TTLCache(ttl_seconds=30.0)
