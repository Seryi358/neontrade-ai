"""
Atlas - Security Module
API Key authentication, rate limiting, IP whitelist, and security headers.

All endpoints require a valid API key via header: X-API-Key
Rate limiting prevents brute force attacks.
Optional IP whitelist restricts access to known addresses.
"""

import hashlib
import hmac
import json
import os
import secrets
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger

# ── Constants ────────────────────────────────────────────────────

SECURITY_CONFIG_PATH = Path(__file__).resolve().parent.parent / "data" / "security.json"

# Endpoints that do NOT require authentication
PUBLIC_ENDPOINTS = {
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
}


# ── Security Config ──────────────────────────────────────────────

class SecurityConfig:
    """Manages API keys, IP whitelist, and rate limit settings."""

    def __init__(self):
        self.api_keys: dict[str, str] = {}  # hash -> label
        self.ip_whitelist: list[str] = []     # empty = allow all
        self.rate_limit_rpm: int = 120        # requests per minute
        self.rate_limit_enabled: bool = True
        self.auth_enabled: bool = True
        self._load()

    def _load(self):
        """Load security config from disk."""
        try:
            if SECURITY_CONFIG_PATH.exists():
                data = json.loads(SECURITY_CONFIG_PATH.read_text("utf-8"))
                self.api_keys = data.get("api_keys", {})
                self.ip_whitelist = data.get("ip_whitelist", [])
                self.rate_limit_rpm = data.get("rate_limit_rpm", 120)
                self.rate_limit_enabled = data.get("rate_limit_enabled", True)
                self.auth_enabled = data.get("auth_enabled", True)
                logger.info("Security config loaded: {} API keys, {} IPs whitelisted",
                            len(self.api_keys), len(self.ip_whitelist))
        except Exception as exc:
            logger.warning("Could not load security config: {}", exc)

    def save(self):
        """Persist security config to disk."""
        try:
            SECURITY_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            SECURITY_CONFIG_PATH.write_text(json.dumps({
                "api_keys": self.api_keys,
                "ip_whitelist": self.ip_whitelist,
                "rate_limit_rpm": self.rate_limit_rpm,
                "rate_limit_enabled": self.rate_limit_enabled,
                "auth_enabled": self.auth_enabled,
            }, indent=2), "utf-8")
        except Exception as exc:
            logger.warning("Could not save security config: {}", exc)

    def generate_api_key(self, label: str = "default") -> str:
        """Generate a new API key, store its hash, return the raw key."""
        raw_key = f"nt_{secrets.token_urlsafe(48)}"
        key_hash = self._hash_key(raw_key)
        self.api_keys[key_hash] = label
        self.save()
        logger.info("New API key generated: label={}", label)
        return raw_key

    def validate_key(self, raw_key: str) -> bool:
        """Check if a raw API key matches any stored hash."""
        if not self.auth_enabled:
            return True
        if not self.api_keys:
            return True  # No keys configured = open access (first run)
        key_hash = self._hash_key(raw_key)
        return any(hmac.compare_digest(key_hash, h) for h in self.api_keys)

    def revoke_key(self, key_hash: str) -> bool:
        """Revoke an API key by its hash."""
        if key_hash in self.api_keys:
            del self.api_keys[key_hash]
            self.save()
            return True
        return False

    def check_ip(self, client_ip: str) -> bool:
        """Check if client IP is allowed. Empty whitelist = all allowed."""
        if not self.ip_whitelist:
            return True
        return client_ip in self.ip_whitelist

    @staticmethod
    def _hash_key(raw_key: str) -> str:
        """SHA-256 hash of the API key (never store raw keys)."""
        return hashlib.sha256(raw_key.encode()).hexdigest()


# ── Rate Limiter ─────────────────────────────────────────────────

class RateLimiter:
    """In-memory sliding window rate limiter per IP."""

    def __init__(self):
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._blocked: dict[str, float] = {}  # IP -> unblock time
        self.block_duration = 300  # 5 min block after exceeding limit

    def check(self, client_ip: str, limit_rpm: int) -> tuple[bool, int]:
        """
        Check if request is allowed.
        Returns (allowed, retry_after_seconds).
        """
        now = time.time()

        # Check if IP is blocked
        if client_ip in self._blocked:
            if now < self._blocked[client_ip]:
                retry_after = int(self._blocked[client_ip] - now)
                return False, retry_after
            else:
                del self._blocked[client_ip]

        # Clean old entries (older than 60s)
        window = [t for t in self._requests[client_ip] if now - t < 60]
        self._requests[client_ip] = window

        if len(window) >= limit_rpm:
            # Block this IP
            self._blocked[client_ip] = now + self.block_duration
            logger.warning("Rate limit exceeded for IP {}, blocked for {}s",
                           client_ip, self.block_duration)
            return False, self.block_duration

        self._requests[client_ip].append(now)
        return True, 0

    def cleanup(self):
        """Remove stale entries (call periodically)."""
        now = time.time()
        stale_ips = [ip for ip, times in self._requests.items()
                     if not times or now - times[-1] > 120]
        for ip in stale_ips:
            del self._requests[ip]


# ── Security Middleware ──────────────────────────────────────────

class SecurityMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware that enforces:
    1. Security headers on all responses
    2. IP whitelist check
    3. API key authentication
    4. Rate limiting
    """

    def __init__(self, app, security_config: SecurityConfig):
        super().__init__(app)
        self.config = security_config
        self.rate_limiter = rate_limiter  # Use module-level singleton for cleanup access

    async def dispatch(self, request: Request, call_next):
        client_ip = self._get_client_ip(request)
        path = request.url.path

        # 1. Always add security headers
        # 2. Skip auth for public endpoints, static assets, and WebSocket upgrades
        is_public = (
            path in PUBLIC_ENDPOINTS
            or path.startswith("/docs/")
            or path.startswith("/redoc/")
            or path.startswith("/_expo/")
            or path.startswith("/assets/")
        )
        # Only skip auth for actual WebSocket path, NOT just Upgrade header
        # (prevents auth bypass via fake Upgrade header on API endpoints)
        is_websocket = path == "/ws" and request.headers.get("upgrade", "").lower() == "websocket"
        # Serve frontend SPA for non-API paths (no auth needed for UI)
        is_frontend = not path.startswith("/api/") and not path.startswith("/ws") and not is_public

        if not is_public and not is_websocket and not is_frontend:
            # IP whitelist check
            if not self.config.check_ip(client_ip):
                logger.warning("Blocked request from non-whitelisted IP: {}", client_ip)
                return JSONResponse(
                    status_code=403,
                    content={"detail": "IP not authorized"},
                )

            # Rate limiting
            if self.config.rate_limit_enabled:
                allowed, retry_after = self.rate_limiter.check(
                    client_ip, self.config.rate_limit_rpm
                )
                if not allowed:
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Too many requests"},
                        headers={"Retry-After": str(retry_after)},
                    )

            # API key authentication
            if self.config.auth_enabled and self.config.api_keys:
                api_key = request.headers.get("X-API-Key", "")
                if not api_key:
                    api_key = request.query_params.get("api_key", "")

                if not self.config.validate_key(api_key):
                    logger.warning("Invalid API key from IP: {}", client_ip)
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Invalid or missing API key"},
                    )

        # Process request
        response = await call_next(request)

        # Add security headers to all responses
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Cache-Control: don't cache API responses, but allow caching for static assets
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        elif path.startswith("/_expo") or path.startswith("/assets"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"

        return response

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """Get real client IP, respecting proxy headers."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        return request.client.host if request.client else "unknown"


# ── Singleton ────────────────────────────────────────────────────

security_config = SecurityConfig()

# Module-level rate limiter instance for periodic cleanup from main.py
rate_limiter = RateLimiter()

# Auto-register API key from env (API_SECRET_KEY) if no keys exist yet
def _bootstrap_env_key():
    """If API_SECRET_KEY is set in env and no keys exist, register it."""
    from config import settings
    env_key = getattr(settings, 'api_secret_key', '')
    if env_key and not security_config.api_keys:
        key_hash = SecurityConfig._hash_key(env_key)
        security_config.api_keys[key_hash] = "env_bootstrap"
        security_config.save()
        logger.info("API key registered from API_SECRET_KEY env var")

_bootstrap_env_key()
