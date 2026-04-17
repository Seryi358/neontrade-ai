"""
Tests for Capital.com session token disk caching (audit finding C5).

Background: Capital.com rate-limits ~10 login/hour. With 65 redeploys in 48h,
Atlas was hitting 429 on auth. Fix: persist CST + X-SECURITY-TOKEN to disk
with a 9-minute TTL (1 min buffer under Capital's 10-min expiry) so new
processes can reuse a live session.
"""
import json
import os
import time

import pytest


def _build_client(monkeypatch, tmp_path):
    """Create a CapitalClient with the session cache redirected to tmp_path."""
    cache_file = tmp_path / "capital_session.json"
    monkeypatch.setenv("ATLAS_SESSION_CACHE", str(cache_file))

    # Reload module so SESSION_CACHE_PATH picks up the env var
    import importlib
    from broker import capital_client as cc
    importlib.reload(cc)

    client = cc.CapitalClient(
        api_key="KEY",
        password="PW",
        identifier="user@test",
        environment="demo",
    )
    return client, cache_file, cc


class _Recorder:
    """Records calls to `_client.post`/`_client.get`/`_client.put` on the CapitalClient."""

    def __init__(self):
        self.post_calls = []
        self.get_calls = []
        self.put_calls = []


def _install_recorder(client, recorder, *, session_ok=True):
    """Patch the internal httpx AsyncClient to record calls instead of hitting network."""

    class _FakeResponse:
        def __init__(self, headers=None, json_body=None, status_code=200):
            self.headers = headers or {}
            self._json = json_body if json_body is not None else {}
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                import httpx
                raise httpx.HTTPStatusError(
                    f"HTTP {self.status_code}", request=None, response=self,
                )

        def json(self):
            return self._json

    async def fake_post(path, headers=None, json=None):
        recorder.post_calls.append({"path": path, "headers": headers, "json": json})
        if path == "/api/v1/session":
            if not session_ok:
                return _FakeResponse(status_code=429)
            return _FakeResponse(
                headers={"CST": "NEW_CST", "X-SECURITY-TOKEN": "NEW_XST"},
                json_body={},
            )
        return _FakeResponse()

    async def fake_get(path, headers=None, params=None):
        recorder.get_calls.append({"path": path, "headers": headers, "params": params})
        if path == "/api/v1/accounts":
            return _FakeResponse(
                json_body={"accounts": [{"accountId": "ACC_X", "accountType": "CFD",
                                         "balance": {"balance": 100}}]},
            )
        if path == "/api/v1/session":
            return _FakeResponse(json_body={"accountId": "ACC_X"})
        return _FakeResponse(json_body={})

    async def fake_put(path, headers=None, json=None):
        recorder.put_calls.append({"path": path, "headers": headers, "json": json})
        return _FakeResponse(json_body={})

    client._client.post = fake_post
    client._client.get = fake_get
    client._client.put = fake_put


# ── Tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_session_reuse_from_fresh_cache(monkeypatch, tmp_path):
    """If a fresh (<9min) cache exists, _create_session must NOT call the auth endpoint."""
    cache_file = tmp_path / "capital_session.json"
    cache_file.write_text(json.dumps({
        "cst": "CACHED_CST",
        "xst": "CACHED_XST",
        "account_id": "ACC_FROM_CACHE",
        "timestamp": time.time(),  # fresh
    }))
    monkeypatch.setenv("ATLAS_SESSION_CACHE", str(cache_file))

    import importlib
    from broker import capital_client as cc
    importlib.reload(cc)

    client = cc.CapitalClient(
        api_key="KEY", password="PW", identifier="u@t", environment="demo",
    )
    recorder = _Recorder()
    _install_recorder(client, recorder)

    await client._create_session()

    # Cache hit: no POST to /session, tokens loaded from file
    assert all(c["path"] != "/api/v1/session" for c in recorder.post_calls), \
        "Expected no auth POST when cache is fresh"
    assert client._cst == "CACHED_CST"
    assert client._security_token == "CACHED_XST"
    assert client._active_account_id == "ACC_FROM_CACHE"
    assert client._session_time is not None


@pytest.mark.asyncio
async def test_session_cache_expired_triggers_reauth(monkeypatch, tmp_path):
    """Cache older than TTL (9min) must NOT be reused — a real auth must run."""
    cache_file = tmp_path / "capital_session.json"
    cache_file.write_text(json.dumps({
        "cst": "OLD_CST",
        "xst": "OLD_XST",
        "account_id": "ACC_OLD",
        "timestamp": time.time() - 10 * 60,  # 10 minutes old (>9min TTL)
    }))
    monkeypatch.setenv("ATLAS_SESSION_CACHE", str(cache_file))

    import importlib
    from broker import capital_client as cc
    importlib.reload(cc)

    client = cc.CapitalClient(
        api_key="KEY", password="PW", identifier="u@t", environment="demo",
    )
    recorder = _Recorder()
    _install_recorder(client, recorder)

    await client._create_session()

    assert any(c["path"] == "/api/v1/session" for c in recorder.post_calls), \
        "Expected auth POST when cache is expired"
    assert client._cst == "NEW_CST"
    assert client._security_token == "NEW_XST"


@pytest.mark.asyncio
async def test_session_cache_missing_triggers_auth(monkeypatch, tmp_path):
    """No cache file on disk → must authenticate and populate the cache."""
    monkeypatch.setenv("ATLAS_SESSION_CACHE", str(tmp_path / "missing.json"))

    import importlib
    from broker import capital_client as cc
    importlib.reload(cc)

    client = cc.CapitalClient(
        api_key="KEY", password="PW", identifier="u@t", environment="demo",
    )
    recorder = _Recorder()
    _install_recorder(client, recorder)

    await client._create_session()

    assert any(c["path"] == "/api/v1/session" for c in recorder.post_calls), \
        "Expected auth POST when cache file does not exist"
    assert client._cst == "NEW_CST"


@pytest.mark.asyncio
async def test_successful_auth_writes_cache(monkeypatch, tmp_path):
    """After a successful auth, the cache file must contain the new tokens."""
    cache_file = tmp_path / "capital_session.json"
    monkeypatch.setenv("ATLAS_SESSION_CACHE", str(cache_file))

    import importlib
    from broker import capital_client as cc
    importlib.reload(cc)

    client = cc.CapitalClient(
        api_key="KEY", password="PW", identifier="u@t", environment="demo",
    )
    recorder = _Recorder()
    _install_recorder(client, recorder)

    await client._create_session()

    assert cache_file.exists(), "Cache file should be written after successful auth"
    payload = json.loads(cache_file.read_text())
    assert payload["cst"] == "NEW_CST"
    assert payload["xst"] == "NEW_XST"
    # timestamp should be recent
    assert abs(payload["timestamp"] - time.time()) < 5


@pytest.mark.asyncio
async def test_cache_corrupted_falls_back_to_auth(monkeypatch, tmp_path):
    """A malformed cache file must not break startup — fall back to auth."""
    cache_file = tmp_path / "capital_session.json"
    cache_file.write_text("not-json{")
    monkeypatch.setenv("ATLAS_SESSION_CACHE", str(cache_file))

    import importlib
    from broker import capital_client as cc
    importlib.reload(cc)

    client = cc.CapitalClient(
        api_key="KEY", password="PW", identifier="u@t", environment="demo",
    )
    recorder = _Recorder()
    _install_recorder(client, recorder)

    await client._create_session()

    assert any(c["path"] == "/api/v1/session" for c in recorder.post_calls)
    assert client._cst == "NEW_CST"


@pytest.mark.asyncio
async def test_missing_tokens_in_cache_triggers_auth(monkeypatch, tmp_path):
    """Cache with missing CST/XST keys must be treated as unusable → auth."""
    cache_file = tmp_path / "capital_session.json"
    cache_file.write_text(json.dumps({"timestamp": time.time()}))  # no tokens
    monkeypatch.setenv("ATLAS_SESSION_CACHE", str(cache_file))

    import importlib
    from broker import capital_client as cc
    importlib.reload(cc)

    client = cc.CapitalClient(
        api_key="KEY", password="PW", identifier="u@t", environment="demo",
    )
    recorder = _Recorder()
    _install_recorder(client, recorder)

    await client._create_session()

    assert any(c["path"] == "/api/v1/session" for c in recorder.post_calls)
    assert client._cst == "NEW_CST"
