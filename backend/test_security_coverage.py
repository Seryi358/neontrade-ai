"""
Tests for security.py — covering API key auth, rate limiting, IP whitelist.
"""

import pytest
import time
from unittest.mock import patch, MagicMock
from core.security import SecurityConfig, RateLimiter, PUBLIC_ENDPOINTS


# ──────────────────────────────────────────────────────────────────
# SecurityConfig
# ──────────────────────────────────────────────────────────────────

class TestSecurityConfig:
    def test_generate_and_validate_key(self):
        """Generated key should validate successfully."""
        config = SecurityConfig.__new__(SecurityConfig)
        config.api_keys = {}
        config.ip_whitelist = []
        config.rate_limit_rpm = 120
        config.rate_limit_enabled = True
        config.auth_enabled = True

        with patch.object(config, 'save'):
            raw_key = config.generate_api_key("test")

        assert raw_key.startswith("nt_")
        assert config.validate_key(raw_key) is True

    def test_invalid_key_rejected(self):
        config = SecurityConfig.__new__(SecurityConfig)
        config.api_keys = {"somehash": "label"}
        config.auth_enabled = True
        assert config.validate_key("wrong_key") is False

    def test_auth_disabled_always_validates(self):
        config = SecurityConfig.__new__(SecurityConfig)
        config.api_keys = {"somehash": "label"}
        config.auth_enabled = False
        assert config.validate_key("anything") is True

    def test_no_keys_fails_closed(self):
        """Audit A5: no keys + auth_enabled=True → fail-closed (reject).

        Previous behavior returned True (open-access). The security module now
        rejects requests when no API keys are configured, to prevent
        accidental open-access deployments.
        """
        config = SecurityConfig.__new__(SecurityConfig)
        config.api_keys = {}
        config.auth_enabled = True
        assert config.validate_key("anything") is False

    def test_revoke_key(self):
        config = SecurityConfig.__new__(SecurityConfig)
        config.api_keys = {"hash123": "test"}
        with patch.object(config, 'save'):
            assert config.revoke_key("hash123") is True
        assert "hash123" not in config.api_keys

    def test_revoke_nonexistent_key(self):
        config = SecurityConfig.__new__(SecurityConfig)
        config.api_keys = {}
        assert config.revoke_key("nonexistent") is False

    def test_hash_key_deterministic(self):
        h1 = SecurityConfig._hash_key("test_key_123")
        h2 = SecurityConfig._hash_key("test_key_123")
        assert h1 == h2

    def test_hash_key_different_for_different_inputs(self):
        h1 = SecurityConfig._hash_key("key_a")
        h2 = SecurityConfig._hash_key("key_b")
        assert h1 != h2

    def test_check_ip_empty_whitelist_allows_all(self):
        config = SecurityConfig.__new__(SecurityConfig)
        config.ip_whitelist = []
        assert config.check_ip("192.168.1.1") is True
        assert config.check_ip("10.0.0.1") is True

    def test_check_ip_whitelist_blocks_unknown(self):
        config = SecurityConfig.__new__(SecurityConfig)
        config.ip_whitelist = ["192.168.1.1", "10.0.0.1"]
        assert config.check_ip("192.168.1.1") is True
        assert config.check_ip("172.16.0.1") is False


# ──────────────────────────────────────────────────────────────────
# RateLimiter
# ──────────────────────────────────────────────────────────────────

class TestRateLimiter:
    def test_allows_within_limit(self):
        rl = RateLimiter()
        allowed, retry = rl.check("192.168.1.1", 10)
        assert allowed is True
        assert retry == 0

    def test_blocks_after_exceeding_limit(self):
        rl = RateLimiter()
        # Make 10 requests (the limit)
        for _ in range(10):
            rl.check("192.168.1.1", 10)
        # 11th should be blocked
        allowed, retry = rl.check("192.168.1.1", 10)
        assert allowed is False
        assert retry > 0

    def test_different_ips_independent(self):
        rl = RateLimiter()
        for _ in range(10):
            rl.check("192.168.1.1", 10)
        # IP 1 is at limit
        allowed1, _ = rl.check("192.168.1.1", 10)
        # IP 2 should be fine
        allowed2, _ = rl.check("192.168.1.2", 10)
        assert allowed1 is False
        assert allowed2 is True

    def test_blocked_ip_eventually_unblocks(self):
        rl = RateLimiter()
        rl.block_duration = 0.02  # Very short block for testing
        for _ in range(5):
            rl.check("192.168.1.1", 5)
        allowed, _ = rl.check("192.168.1.1", 5)
        assert allowed is False
        time.sleep(0.03)
        # After block expires, the IP is unblocked but the sliding window
        # still has entries from the last 60s. Clear them to simulate time passing.
        rl._requests["192.168.1.1"] = []
        allowed, _ = rl.check("192.168.1.1", 5)
        assert allowed is True

    def test_cleanup_removes_stale(self):
        rl = RateLimiter()
        rl._requests["old_ip"] = [time.time() - 200]  # 200s old
        rl._requests["new_ip"] = [time.time()]
        rl.cleanup()
        assert "old_ip" not in rl._requests
        assert "new_ip" in rl._requests


# ──────────────────────────────────────────────────────────────────
# PUBLIC_ENDPOINTS
# ──────────────────────────────────────────────────────────────────

class TestPublicEndpoints:
    def test_health_is_public(self):
        assert "/health" in PUBLIC_ENDPOINTS

    def test_docs_is_public(self):
        assert "/docs" in PUBLIC_ENDPOINTS
