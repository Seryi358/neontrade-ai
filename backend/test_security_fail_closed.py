"""
Test: Security fail-closed when no API keys configured (audit A5).

Previously: `validate_key()` returned True when `api_keys` was empty,
leaving the app open-access. This is a CRITICAL security issue.

After fix: empty `api_keys` with `auth_enabled=True` → validate_key returns False.
Exception: `auth_enabled=False` (dev mode) → validate_key still returns True.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.security import SecurityConfig


def _make_config(auth_enabled: bool, api_keys: dict) -> SecurityConfig:
    """Build a SecurityConfig without hitting disk."""
    cfg = SecurityConfig.__new__(SecurityConfig)
    cfg.api_keys = dict(api_keys)
    cfg.ip_whitelist = []
    cfg.rate_limit_rpm = 120
    cfg.rate_limit_enabled = True
    cfg.auth_enabled = auth_enabled
    return cfg


def test_empty_keys_auth_enabled_returns_false():
    """No API keys + auth_enabled=True → MUST fail closed (return False)."""
    cfg = _make_config(auth_enabled=True, api_keys={})
    assert cfg.validate_key("anything") is False
    assert cfg.validate_key("") is False


def test_matching_key_returns_true():
    """Valid key with auth_enabled=True → returns True."""
    cfg = _make_config(auth_enabled=True, api_keys={})
    raw_key = "nt_test_sample_key_for_validation_12345"
    key_hash = SecurityConfig._hash_key(raw_key)
    cfg.api_keys[key_hash] = "test"
    assert cfg.validate_key(raw_key) is True


def test_auth_disabled_returns_true_unchanged():
    """auth_enabled=False (dev mode) → returns True (unchanged behavior)."""
    cfg = _make_config(auth_enabled=False, api_keys={})
    assert cfg.validate_key("anything") is True
    assert cfg.validate_key("") is True


def test_wrong_key_returns_false():
    """Invalid key with keys configured → returns False."""
    cfg = _make_config(auth_enabled=True, api_keys={})
    raw_key = "nt_test_sample_key_for_validation_12345"
    key_hash = SecurityConfig._hash_key(raw_key)
    cfg.api_keys[key_hash] = "test"
    assert cfg.validate_key("wrong_key") is False
