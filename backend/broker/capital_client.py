"""
Atlas - Capital.com API Client
Implements BaseBroker interface for Capital.com REST API.

Capital.com uses session-based auth with CST + X-SECURITY-TOKEN headers.
Sessions expire after 10 minutes of inactivity - auto-refreshed.

API Docs: https://open-api.capital.com/
"""

import httpx
import asyncio
import json
import os
import time
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone, timedelta
from loguru import logger

from core.resilience import retry_async, broker_circuit_breaker

from broker.base import (
    BaseBroker,
    BrokerType,
    PriceData,
    CandleData,
    OrderResult,
    AccountSummary,
    TradeInfo,
)


# ── Session cache (audit C5) ─────────────────────────────────────
# Capital.com rate-limits ~10 logins/hour. With frequent redeploys we hit 429
# on auth. Persist CST + X-SECURITY-TOKEN to a JSON file on the atlas-data
# volume so newly-started processes can reuse a live session instead of
# re-authenticating. TTL is 9 min (1 min buffer under Capital's 10-min expiry).
SESSION_CACHE_PATH = os.environ.get(
    "ATLAS_SESSION_CACHE", "/app/data/capital_session.json",
)
SESSION_TTL_SECONDS = 540  # 9 minutes — buffer from Capital's 10-min expiry


# ── Granularity mapping (our format -> Capital.com format) ────
GRANULARITY_MAP = {
    # Our standard names -> Capital.com resolution
    "M1": "MINUTE",
    "M2": "MINUTE",      # Capital.com has no MINUTE_2; use M1 as proxy (market_analyzer derives M2 from M1)
    "M3": "MINUTE_3",
    "M5": "MINUTE_5",
    "M10": "MINUTE_10",
    "M15": "MINUTE_15",
    "M30": "MINUTE_30",
    "H1": "HOUR",
    "H2": "HOUR_2",
    "H3": "HOUR_3",
    "H4": "HOUR_4",
    "D": "DAY",
    "W": "WEEK",
}

# ── Instrument mapping (OANDA format -> Capital.com epic) ─────
# Capital.com uses different epic names for forex pairs.
# We'll discover these dynamically via the search endpoint,
# but keep common ones cached for speed.
INSTRUMENT_CACHE: Dict[str, str] = {}


class CapitalClient(BaseBroker):
    """Capital.com REST API client for trading operations."""

    def __init__(
        self,
        api_key: str,
        password: str,
        identifier: str,
        environment: str = "demo",
        account_id: Optional[str] = None,
    ):
        super().__init__(BrokerType.CAPITAL)

        self.api_key = api_key
        self.password = password
        self.identifier = identifier  # email address
        self._target_account_id = account_id  # specific account to use (None = auto-detect live)

        # Base URL
        if environment == "live":
            self.base_url = "https://api-capital.backend-capital.com"
        else:
            self.base_url = "https://demo-api-capital.backend-capital.com"

        # Session tokens
        self._cst: Optional[str] = None
        self._security_token: Optional[str] = None
        self._session_time: Optional[datetime] = None
        self._active_account_id: Optional[str] = None

        # Session lock to prevent concurrent session creation
        self._session_lock = asyncio.Lock()

        # HTTP client
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=30.0,
        )

        # Instrument epic cache (our_name -> capital_epic)
        self._epic_cache: Dict[str, str] = {}
        # Set of instruments that failed to resolve to a valid epic during
        # warm_epic_cache (e.g. 404 from Capital.com search or no candidate
        # passed the strict matching heuristic). The trading engine consults
        # `is_blocklisted` so the scan loop skips them entirely instead of
        # wasting 4 API calls per cycle on each one.
        self._epic_blocklist: set = set()

    # ── Session Management ────────────────────────────────────────

    async def _ensure_session(self):
        """Create or refresh session if needed (expires after 10 min)."""
        async with self._session_lock:
            now = datetime.now(timezone.utc)

            # Session valid for ~9 min (refresh before 10 min expiry)
            if (self._cst and self._security_token and self._session_time
                    and (now - self._session_time) < timedelta(minutes=9)):
                return

            await self._create_session()

    async def _create_session(self):
        """Authenticate, get CST + X-SECURITY-TOKEN, and switch to the correct account.

        Audit C5: before hitting the auth endpoint, try to reuse a cached
        session from disk (TTL 9 min). This avoids re-auth on every restart
        and keeps us under Capital.com's ~10 logins/hour rate limit.
        """
        # Fast path: reuse cached session if it's fresh and has both tokens.
        cached = self._load_cached_session()
        if cached and self._is_cache_fresh(cached):
            self._cst = cached.get("cst")
            self._security_token = cached.get("xst")
            self._active_account_id = cached.get("account_id")
            self._session_time = datetime.now(timezone.utc)
            logger.info("Capital.com session reused from cache")
            return

        try:
            resp = await self._client.post(
                "/api/v1/session",
                headers={"X-CAP-API-KEY": self.api_key},
                json={
                    "identifier": self.identifier,
                    "password": self.password,
                    "encryptedPassword": False,
                },
            )
            resp.raise_for_status()

            self._cst = resp.headers.get("CST")
            self._security_token = resp.headers.get("X-SECURITY-TOKEN")
            if not self._cst or not self._security_token:
                self._session_time = None
                raise ConnectionError("Session tokens missing from response")
            self._session_time = datetime.now(timezone.utc)

            logger.info("Capital.com session created successfully")

            # Switch to the correct account (avoid demo account)
            await self._select_account()

            # Persist for reuse by the next process.
            self._save_cached_session()

        except httpx.HTTPStatusError as e:
            # Clear stale tokens on auth failure
            self._cst = None
            self._security_token = None
            self._session_time = None
            error_msg = "Authentication failed"
            try:
                error_body = e.response.json()
                error_msg = error_body.get("errorCode", error_msg)
            except Exception:
                pass
            logger.error(f"Capital.com session failed: {error_msg}")
            raise ConnectionError(f"Capital.com auth failed: {error_msg}")

    # ── Session cache helpers (audit C5) ──────────────────────────

    @staticmethod
    def _load_cached_session() -> Optional[Dict[str, Any]]:
        """Load the cached session from disk, or None if missing/corrupt."""
        try:
            with open(SESSION_CACHE_PATH) as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return None
            # Require both tokens and a timestamp to consider the cache usable.
            if not data.get("cst") or not data.get("xst"):
                return None
            if "timestamp" not in data:
                return None
            return data
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def _is_cache_fresh(cached: Dict[str, Any]) -> bool:
        """True if the cached session is within the TTL window."""
        try:
            age = time.time() - float(cached.get("timestamp", 0))
        except (TypeError, ValueError):
            return False
        return 0 <= age < SESSION_TTL_SECONDS

    def _save_cached_session(self) -> None:
        """Write the current session tokens to the cache file (mode 600)."""
        try:
            os.makedirs(os.path.dirname(SESSION_CACHE_PATH) or ".", exist_ok=True)
            payload = {
                "cst": self._cst,
                "xst": self._security_token,
                "account_id": self._active_account_id,
                "timestamp": time.time(),
            }
            with open(SESSION_CACHE_PATH, "w") as f:
                json.dump(payload, f)
            # Tokens are sensitive — restrict to owner-read/write if the FS
            # supports it (Linux containers). POSIX-only call; ignore errors
            # on systems that don't support it.
            try:
                os.chmod(SESSION_CACHE_PATH, 0o600)
            except OSError:
                pass
        except OSError as e:
            # Cache write failures must NOT break auth — just log.
            logger.warning(f"Could not persist Capital.com session cache: {e}")

    @staticmethod
    def _invalidate_cached_session() -> None:
        """Remove the disk cache so the next _create_session re-auths.
        Called when the broker returns 401 — the cached tokens are stale.
        """
        try:
            os.remove(SESSION_CACHE_PATH)
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.debug(f"Could not remove session cache: {e}")

    async def _select_account(self):
        """Select the correct trading account after login.
        Capital.com creates both a live and a demo sub-account.
        The session may default to the demo one (marked 'preferred').
        We auto-detect the real account by picking the one with the
        lowest balance (the user's actual deposit, not virtual funds).
        """
        try:
            resp = await self._client.get(
                "/api/v1/accounts", headers=self._auth_headers()
            )
            resp.raise_for_status()
            accounts = resp.json().get("accounts", [])

            if not accounts:
                return

            # If a specific account ID was configured, use it
            if self._target_account_id:
                target = self._target_account_id
            else:
                # Auto-detect: prefer LIVE/CFD account by type field (BUG-02 fix).
                if len(accounts) == 1:
                    target = accounts[0]["accountId"]
                else:
                    # Try to find account by accountType field first
                    live_accounts = [
                        a for a in accounts
                        if a.get("accountType", a.get("type", "")).upper() in ("LIVE", "CFD")
                    ]
                    if live_accounts:
                        target = live_accounts[0]["accountId"]
                        logger.info(
                            f"Selected LIVE/CFD account {target} by accountType field "
                            f"(from {len(accounts)} sub-accounts)"
                        )
                    else:
                        # Fallback: the real account typically has the smaller balance
                        # (user deposit vs. virtual demo funds like ~$60k)
                        logger.warning(
                            "No accountType field found on accounts — falling back to "
                            "balance heuristic (lowest balance = real). Verify correct account!"
                        )
                        sorted_accts = sorted(
                            accounts,
                            key=lambda a: float(a.get("balance", {}).get("balance", 0)),
                        )
                        target = sorted_accts[0]["accountId"]
                        real_bal = float(sorted_accts[0].get("balance", {}).get("balance", 0))
                        demo_bal = float(sorted_accts[-1].get("balance", {}).get("balance", 0))
                        logger.info(
                            f"Detected {len(accounts)} sub-accounts: "
                            f"real=${real_bal:,.2f}, demo=${demo_bal:,.2f}"
                        )

            # Check if we're already on the right account
            session_resp = await self._client.get(
                "/api/v1/session", headers=self._auth_headers()
            )
            session_resp.raise_for_status()
            current_acct = session_resp.json().get("accountId")

            if current_acct != target:
                # Switch to the correct account
                switch_resp = await self._client.put(
                    "/api/v1/session",
                    headers=self._auth_headers(),
                    json={"accountId": target},
                )
                switch_resp.raise_for_status()
                logger.info(f"Switched to account {target}")
            else:
                logger.info(f"Already on correct account {target}")

            self._active_account_id = target

        except Exception as e:
            logger.warning(f"Account selection failed (will use default): {e}")

    def _auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for API requests."""
        return {
            "X-CAP-API-KEY": self.api_key,
            "CST": self._cst or "",
            "X-SECURITY-TOKEN": self._security_token or "",
            "Content-Type": "application/json",
        }

    async def _get(self, path: str, params: Optional[Dict] = None) -> Dict:
        """Authenticated GET request with retry and circuit breaker."""
        if broker_circuit_breaker.is_open:
            raise ConnectionError("Circuit breaker OPEN - broker unavailable")
        await self._ensure_session()
        last_exc = None
        for attempt in range(4):  # 1 initial + 3 retries
            try:
                resp = await self._client.get(
                    path, headers=self._auth_headers(), params=params,
                )
                resp.raise_for_status()
                broker_circuit_breaker.record_success()
                return resp.json()
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
                last_exc = e
                # Audit A9: permanent 4xx (400/403/404/422) must NOT be retried.
                # Retrying 63 404s × 3 in 12 min wastes API quota and can
                # trigger secondary 429s from Capital.com. Fail fast.
                if self._is_permanent_error(e):
                    broker_circuit_breaker.record_failure()
                    logger.warning(
                        f"[_get] {path}: {e.response.status_code} "
                        f"(non-retriable, failing fast)"
                    )
                    raise
                # Check for 429 Rate Limit — respect Retry-After header
                retry_after = None
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429:
                    retry_after_hdr = e.response.headers.get('Retry-After')
                    if retry_after_hdr:
                        try:
                            retry_after = float(retry_after_hdr)
                        except (ValueError, TypeError):
                            retry_after = None
                # Clear session on 401 so _ensure_session re-authenticates
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 401:
                    self._cst = None
                    self._security_token = None
                    self._session_time = None
                    self._invalidate_cached_session()
                    logger.warning(f"[_get] {path}: 401 Unauthorized — session invalidated, will re-auth")
                if attempt < 3:
                    delay = retry_after + 0.5 if retry_after else min(0.5 * (2 ** attempt), 10.0)
                    logger.warning(f"[_get] {path} attempt {attempt+1}/4 failed: {e}. Retry in {delay:.1f}s")
                    await asyncio.sleep(delay)
                    # Re-check session in case it expired
                    await self._ensure_session()
            except Exception as e:
                # Non-retryable error
                broker_circuit_breaker.record_failure()
                raise
        # All retries exhausted — record ONE failure to circuit breaker
        broker_circuit_breaker.record_failure()
        raise last_exc

    @staticmethod
    def _parse_retry_after(e: Exception) -> Optional[float]:
        """Return the Retry-After header value in seconds, if the error is a 429."""
        if not isinstance(e, httpx.HTTPStatusError) or e.response.status_code != 429:
            return None
        hdr = e.response.headers.get("Retry-After")
        if not hdr:
            return None
        try:
            return float(hdr)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _is_permanent_error(e: Exception) -> bool:
        """Client-side errors (400/403/404/422) are permanent — retry wastes API
        quota and can trigger secondary 429 throttles. 401 is handled separately
        (session refresh). 429 + 5xx are retryable."""
        if not isinstance(e, httpx.HTTPStatusError):
            return False
        code = e.response.status_code
        return code in (400, 403, 404, 422)

    async def _post(self, path: str, json_data: Optional[Dict] = None) -> httpx.Response:
        """Authenticated POST request with retry and circuit breaker."""
        if broker_circuit_breaker.is_open:
            raise ConnectionError("Circuit breaker OPEN - broker unavailable")
        await self._ensure_session()
        last_exc = None
        for attempt in range(3):  # 1 initial + 2 retries
            try:
                resp = await self._client.post(
                    path, headers=self._auth_headers(), json=json_data or {},
                )
                resp.raise_for_status()
                broker_circuit_breaker.record_success()
                return resp
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
                last_exc = e
                # Permanent 4xx — don't retry, fail fast.
                if self._is_permanent_error(e):
                    broker_circuit_breaker.record_failure()
                    raise
                retry_after = self._parse_retry_after(e)
                # Clear session on 401 so _ensure_session re-authenticates
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 401:
                    self._cst = None
                    self._security_token = None
                    self._session_time = None
                    self._invalidate_cached_session()
                    logger.warning(f"[_post] {path}: 401 Unauthorized — session invalidated, will re-auth")
                if attempt < 2:
                    delay = retry_after + 0.5 if retry_after else min(0.5 * (2 ** attempt), 10.0)
                    logger.warning(f"[_post] {path} attempt {attempt+1}/3 failed: {e}. Retry in {delay:.1f}s")
                    await asyncio.sleep(delay)
                    await self._ensure_session()
            except Exception as e:
                broker_circuit_breaker.record_failure()
                raise
        broker_circuit_breaker.record_failure()
        raise last_exc

    async def _put(self, path: str, json_data: Optional[Dict] = None) -> httpx.Response:
        """Authenticated PUT request with retry, 401 re-auth, and circuit breaker."""
        if broker_circuit_breaker.is_open:
            raise ConnectionError("Circuit breaker OPEN — broker unavailable (PUT)")
        await self._ensure_session()
        last_exc = None
        for attempt in range(3):
            try:
                resp = await self._client.put(
                    path, headers=self._auth_headers(), json=json_data or {},
                )
                resp.raise_for_status()
                broker_circuit_breaker.record_success()
                return resp
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
                last_exc = e
                if self._is_permanent_error(e):
                    broker_circuit_breaker.record_failure()
                    raise
                retry_after = self._parse_retry_after(e)
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 401:
                    self._cst = None
                    self._security_token = None
                    self._session_time = None
                    self._invalidate_cached_session()
                    logger.warning(f"[_put] {path}: 401 Unauthorized — session invalidated, will re-auth")
                if attempt < 2:
                    delay = retry_after + 0.5 if retry_after else min(0.5 * (2 ** attempt), 5.0)
                    logger.warning(f"[_put] {path} attempt {attempt+1}/3 failed: {e}. Retry in {delay:.1f}s")
                    await asyncio.sleep(delay)
                    await self._ensure_session()
            except Exception as e:
                broker_circuit_breaker.record_failure()
                raise
        broker_circuit_breaker.record_failure()
        raise last_exc

    async def _delete(self, path: str, json_data: Optional[Dict] = None) -> httpx.Response:
        """Authenticated DELETE request with retry, 401 re-auth, and circuit breaker."""
        if broker_circuit_breaker.is_open:
            raise ConnectionError("Circuit breaker OPEN — broker unavailable (DELETE)")
        await self._ensure_session()
        last_exc = None
        for attempt in range(3):
            try:
                resp = await self._client.request(
                    "DELETE", path, headers=self._auth_headers(), json=json_data,
                )
                resp.raise_for_status()
                broker_circuit_breaker.record_success()
                return resp
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
                last_exc = e
                # 404 on DELETE usually means "already closed" — the caller
                # (close_trade) handles that explicitly. Don't retry permanent
                # 4xx here either.
                if self._is_permanent_error(e):
                    broker_circuit_breaker.record_failure()
                    raise
                retry_after = self._parse_retry_after(e)
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 401:
                    self._cst = None
                    self._security_token = None
                    self._session_time = None
                    self._invalidate_cached_session()
                    logger.warning(f"[_delete] {path}: 401 Unauthorized — session invalidated, will re-auth")
                if attempt < 2:
                    delay = retry_after + 0.5 if retry_after else min(0.5 * (2 ** attempt), 5.0)
                    logger.warning(f"[_delete] {path} attempt {attempt+1}/3 failed: {e}. Retry in {delay:.1f}s")
                    await asyncio.sleep(delay)
                    await self._ensure_session()
            except Exception as e:
                broker_circuit_breaker.record_failure()
                raise
        broker_circuit_breaker.record_failure()
        raise last_exc

    # ── Instrument Resolution ────────────────────────────────────

    # Known instruments that the Capital.com search returns ambiguous matches
    # for. Each maps our canonical instrument to the broker-side epic. Without
    # this map the previous "shortest epic wins" fallback resolved e.g.
    # BCO_USD -> BTC_USD (returned $78,345 instead of ~$85), BA -> wrong share
    # ($21 instead of $200+), and various commodities to decimal-shifted
    # decoys. Add entries here as they are confirmed against Capital.com.
    _EPIC_MAP_OVERRIDE: Dict[str, str] = {
        # Energies / commodities — Capital.com epics (verified live 2026-04-22).
        "BCO_USD":     "OIL_BRENT",     # Brent crude
        "WTICO_USD":   "OIL_CRUDE",     # WTI crude
        "NATGAS_USD":  "NATURALGAS",
        "WHEAT_USD":   "WHEAT",
        "CORN_USD":    "CORN",
        "SOYBN_USD":   "SOYBEAN",
        # SUGAR_USD removed: probe rejected "SUGAR" — Capital.com does not
        # offer it under that epic. Search heuristic will blocklist instead.
        "XAU_USD":     "GOLD",
        "XAG_USD":     "SILVER",
        "XPT_USD":     "PLATINUM",
        "XPD_USD":     "PALLADIUM",
        "XCU_USD":     "COPPER",
        # Indices — only the verified ones remain. NAS100/US2000/DE30/FR40/CN50
        # were guesses (USTEC/RUSSELL/GERMANY40/FRANCE40/CHINA50) and the probe
        # rejected them. The search heuristic will auto-blocklist if Capital.com
        # doesn't offer them at all.
        "US30_USD":    "US30",
        "SPX500_USD":  "US500",
        "UK100_GBP":   "UK100",
        "JP225_USD":   "J225",
        "AU200_AUD":   "AU200",
        "HK33_HKD":    "HK50",
        # NOTE: the 17 US share ETFs (BITO/CGC/GBTC/IGV/IHAK/IZRL/KBE/KRBN/
        # MSOS/NERD/POTX/PPA/PRNT/PSJ/PXQ/VFF/YEXT) were tentatively mapped
        # to their ticker literals but live tests on 2026-04-22 returned
        # "Instrument not found" from Capital.com — broker does not offer
        # them under those epics. Reverted to rely on the strict search
        # filter + auto-blocklist path (they'll land in `_epic_blocklist`
        # during warm_epic_cache and be skipped in the scan loop).
    }

    @staticmethod
    def _epic_matches_instrument(epic: str, instrument: str) -> bool:
        """Heuristic safety check: an epic returned by search must "look like"
        the instrument we asked for. Specifically: when our instrument has a
        clear non-currency root token (e.g. BCO_USD has root "BCO", BAC has
        root "BAC"), the epic MUST contain that root case-insensitively. This
        blocks the catastrophic case where searching "BCO/USD" returned BTC.
        Forex pairs (both 3-letter ISO) skip the check because the canonical
        forex epics (EURUSD/GBPUSD/etc.) follow a deterministic shape.
        """
        if not epic:
            return False
        epic_up = epic.upper()
        # Forex: both halves are 3-letter ISO currencies → trust the search
        parts = instrument.replace("/", "_").split("_")
        if len(parts) == 2 and all(len(p) == 3 and p.isalpha() for p in parts):
            return True
        # Single-token (stock/ETF) → epic must contain the literal ticker
        if len(parts) == 1:
            return parts[0].upper() in epic_up
        # Multi-token where the first part is NOT a 3-letter ISO currency:
        # require the first token (the asset root, e.g. "BCO", "NAS100") in
        # the epic so we don't accidentally match the suffix currency.
        first = parts[0].upper()
        if not (len(first) == 3 and first.isalpha()):
            return first in epic_up
        return True

    async def _resolve_epic(self, instrument: str) -> str:
        """
        Convert our instrument name (e.g., EUR_USD) to Capital.com epic.
        Capital.com uses names like 'EURUSD' for forex.
        Prefers spot/CFD instruments over forwards/futures.

        Hardened 2026-04-22 after subagent audit found the previous fallback
        ("shortest epic wins") silently rerouted BCO_USD → BTC_USD (1000× wrong
        notional). Now: hardcoded override map first, then exact-epic match,
        then strict instrument-aware filter on search results.
        """
        if instrument in self._epic_cache:
            return self._epic_cache[instrument]

        # Override map: known broker-side epic for instruments where the search
        # heuristic is unreliable (commodities, indices).
        override = self._EPIC_MAP_OVERRIDE.get(instrument)
        if override:
            self._epic_cache[instrument] = override
            return override

        # Try common forex format: EUR_USD -> EURUSD
        epic_guess = instrument.replace("_", "").replace("/", "")

        # Search the API to confirm
        try:
            data = await self._get("/api/v1/markets", params={
                "searchTerm": instrument.replace("_", "/"),
                "limit": 20,
            })
            markets = data.get("markets", [])
            if markets:
                # Prefer exact epic match (spot instrument)
                for m in markets:
                    if m["epic"] == epic_guess:
                        self._epic_cache[instrument] = epic_guess
                        return epic_guess

                # Filter to candidates that actually look like our instrument
                candidates = [m for m in markets if self._epic_matches_instrument(m["epic"], instrument)]
                if not candidates:
                    logger.warning(
                        f"_resolve_epic: search for {instrument!r} returned "
                        f"{len(markets)} markets but NONE match the instrument "
                        f"root token. Refusing to cache an ambiguous epic. "
                        f"Sample epics: {[m['epic'] for m in markets[:5]]}"
                    )
                    # Do NOT cache the bad guess — let later attempts retry.
                    return epic_guess

                # Among the matching candidates, prefer:
                # 1. exact case-insensitive match to our guess
                # 2. CURRENCIES type for forex / SHARES for stocks / OPTIONS off
                # 3. shortest epic (spot, not forwards)
                best = None
                for m in candidates:
                    epic = m["epic"]
                    inst_type = m.get("instrumentType", "")
                    if epic.upper() == epic_guess.upper():
                        best = epic
                        break
                    if inst_type == "CURRENCIES" and best is None:
                        best = epic
                    elif inst_type == "SHARES" and best is None:
                        best = epic
                    elif best is None or len(epic) < len(best):
                        best = epic

                if best:
                    self._epic_cache[instrument] = best
                    return best
        except Exception as e:
            logger.debug(f"Market search failed for {instrument}: {e}")

        # Fallback to our guess (don't cache - might be wrong, retry next time)
        return epic_guess

    async def _probe_epic(self, epic: str) -> bool:
        """Verify ``epic`` actually exists on Capital.com via market details.
        Returns True if broker accepts it, False on 404 / other error.
        Used by `warm_epic_cache` to validate `_EPIC_MAP_OVERRIDE` entries
        so a wrong override doesn't silently route trades to a non-existent
        instrument (lesson learned from the BITO/CGC/etc. equity guesses).
        """
        try:
            await self._get(f"/api/v1/markets/{epic}")
            return True
        except Exception as e:
            logger.debug(f"_probe_epic({epic!r}) failed: {e}")
            return False

    async def warm_epic_cache(self, instruments: List[str]) -> None:
        """Pre-resolve all instrument epics with throttling.
        Call this BEFORE the initial scan to avoid burst API calls
        from interleaved search + candle requests.

        Side-effect: instruments that fail to resolve (404 from search, or no
        candidate passed `_epic_matches_instrument`) are added to
        `self._epic_blocklist` so the scan loop can skip them entirely.
        """
        uncached = [i for i in instruments if i not in self._epic_cache and i not in self._epic_blocklist]
        if not uncached:
            return
        logger.info(f"Warming epic cache for {len(uncached)} instruments...")
        for inst in uncached:
            try:
                resolved = await self._resolve_epic(inst)
                # _resolve_epic returns the epic_guess on failure WITHOUT caching it,
                # so an entry in the cache means resolution succeeded.
                if inst not in self._epic_cache:
                    self._epic_blocklist.add(inst)
                    logger.warning(
                        f"Epic warmup blocklisted {inst!r}: no valid epic resolved "
                        f"(guessed {resolved!r}; instrument will be skipped in scans)"
                    )
                else:
                    # Validate that the cached epic actually exists on the broker.
                    # Required for `_EPIC_MAP_OVERRIDE` entries — search-resolved
                    # epics are already validated by their search response, but
                    # override map entries skip search entirely and would
                    # silently route to a non-existent epic on a wrong guess.
                    cached_epic = self._epic_cache[inst]
                    if cached_epic == self._EPIC_MAP_OVERRIDE.get(inst):
                        await asyncio.sleep(0.2)
                        if not await self._probe_epic(cached_epic):
                            del self._epic_cache[inst]
                            self._epic_blocklist.add(inst)
                            logger.warning(
                                f"Epic warmup blocklisted {inst!r}: override "
                                f"{cached_epic!r} not recognised by broker — "
                                f"remove from _EPIC_MAP_OVERRIDE or fix the value"
                            )
            except Exception as e:
                self._epic_blocklist.add(inst)
                logger.debug(f"Epic warmup failed for {inst}: {e}")
            await asyncio.sleep(0.5)
        logger.info(
            f"Epic cache warmed: {len(self._epic_cache)} cached, "
            f"{len(self._epic_blocklist)} blocklisted"
        )

    def is_blocklisted(self, instrument: str) -> bool:
        """True if ``instrument`` failed to resolve and should be skipped in scans."""
        return instrument in self._epic_blocklist

    def get_epic_blocklist(self) -> List[str]:
        """Snapshot of currently blocklisted instruments (for /diagnostic, /watchlist endpoints)."""
        return sorted(self._epic_blocklist)

    def _denormalize_instrument(self, epic: str) -> str:
        """Convert Capital.com epic back to our format (e.g., EURUSD -> EUR_USD)."""
        # Reverse lookup from cache
        for our_name, cached_epic in self._epic_cache.items():
            if cached_epic == epic:
                return our_name

        # Try to split 6-char forex epics: EURUSD -> EUR_USD
        if len(epic) == 6 and epic.isalpha():
            return f"{epic[:3]}_{epic[3:]}"

        return epic

    # ── Account ──────────────────────────────────────────────────

    async def get_account_summary(self) -> AccountSummary:
        """Get account balance, equity, margin, etc. Uses the active account."""
        data = await self._get("/api/v1/accounts")
        accounts = data.get("accounts", [])
        if not accounts:
            raise ValueError("No accounts found")

        # Find the active account by ID, fallback to first
        acct = accounts[0]
        if self._active_account_id:
            for a in accounts:
                if a.get("accountId") == self._active_account_id:
                    acct = a
                    break
        balance = float(acct.get("balance", {}).get("balance", 0))
        deposit = float(acct.get("balance", {}).get("deposit", 0))
        pnl = float(acct.get("balance", {}).get("profitLoss", 0))
        available = float(acct.get("balance", {}).get("available", 0))

        # Get open positions count
        try:
            positions = await self._get("/api/v1/positions")
            open_count = len(positions.get("positions", []))
        except Exception:
            open_count = 0

        return AccountSummary(
            balance=balance,
            equity=balance + pnl,
            unrealized_pnl=pnl,
            margin_used=deposit,
            margin_available=available,
            open_trade_count=open_count,
            currency=acct.get("currency", "USD"),
        )

    async def get_account_balance(self) -> float:
        """Get current account balance."""
        summary = await self.get_account_summary()
        return summary.balance

    # ── Market Data ──────────────────────────────────────────────

    async def get_candles(
        self,
        instrument: str,
        granularity: str = "H1",
        count: int = 100,
    ) -> List[CandleData]:
        """Get candlestick data for an instrument."""
        epic = await self._resolve_epic(instrument)
        resolution = GRANULARITY_MAP.get(granularity, "HOUR")

        # Capital.com uses max parameter for count
        data = await self._get(f"/api/v1/prices/{epic}", params={
            "resolution": resolution,
            "max": min(count, 1000),  # Capital.com max is 1000
        })

        prices = data.get("prices", [])
        result: List[CandleData] = []

        for p in prices:
            # Capital.com returns separate bid/ask OHLC - use mid
            # Normalize time format: "2024/01/15 14:00:00" -> "2024-01-15T14:00:00Z"
            raw_time = p.get("snapshotTime", "")
            snap_time = raw_time.replace("/", "-").replace(" ", "T")
            if snap_time and not snap_time.endswith("Z"):
                snap_time += "Z"
            # Use bid prices (or average bid/ask)
            o_data = p.get("openPrice", {})
            h_data = p.get("highPrice", {})
            l_data = p.get("lowPrice", {})
            c_data = p.get("closePrice", {})

            # Mid price = (bid + ask) / 2
            o = (float(o_data.get("bid", 0)) + float(o_data.get("ask", 0))) / 2
            h = (float(h_data.get("bid", 0)) + float(h_data.get("ask", 0))) / 2
            l = (float(l_data.get("bid", 0)) + float(l_data.get("ask", 0))) / 2
            c = (float(c_data.get("bid", 0)) + float(c_data.get("ask", 0))) / 2

            # Skip candles with invalid OHLC (all zeros = missing data from broker)
            if o == 0 and h == 0 and l == 0 and c == 0:
                continue

            vol = int(p.get("lastTradedVolume", 0))

            result.append(CandleData(
                time=snap_time,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=vol,
                complete=True,  # Will mark last candle incomplete below
            ))

        # Bug fix R26: Mark last candle as incomplete (currently forming).
        # Capital.com API doesn't flag this, but the last candle in any
        # resolution is the currently-forming candle. market_analyzer filters
        # out incomplete candles to avoid oscillating indicator values.
        if result:
            last = result[-1]
            result[-1] = CandleData(
                time=last.time, open=last.open, high=last.high,
                low=last.low, close=last.close, volume=last.volume,
                complete=False,
            )

        return result

    async def get_current_price(self, instrument: str) -> PriceData:
        """Get current bid/ask price for an instrument."""
        epic = await self._resolve_epic(instrument)

        # Get last 1 candle at MINUTE resolution for current price
        data = await self._get(f"/api/v1/prices/{epic}", params={
            "resolution": "MINUTE",
            "max": 1,
        })

        prices = data.get("prices", [])
        if not prices:
            raise ValueError(f"No price data for {instrument}")

        latest = prices[-1]
        bid = float(latest.get("closePrice", {}).get("bid", 0))
        ask = float(latest.get("closePrice", {}).get("ask", 0))

        # BUG-07 fix: reject zero/None prices instead of propagating silently
        if not bid or not ask:
            raise ValueError(
                f"Invalid price data for {instrument}: bid={bid}, ask={ask}. "
                f"Market may be closed or data unavailable."
            )

        return PriceData(
            bid=bid,
            ask=ask,
            spread=ask - bid,
            time=latest.get("snapshotTime", ""),
        )

    async def get_prices_bulk(self, instruments: List[str]) -> Dict[str, PriceData]:
        """Get current prices for multiple instruments."""
        # Capital.com doesn't have a bulk price endpoint,
        # so we fetch individually with concurrency limit
        result: Dict[str, PriceData] = {}
        semaphore = asyncio.Semaphore(5)  # Max 5 concurrent requests

        async def fetch_one(inst: str):
            async with semaphore:
                try:
                    price = await self.get_current_price(inst)
                    result[inst] = price
                except Exception as e:
                    logger.debug(f"Failed to get price for {inst}: {e}")

        await asyncio.gather(*(fetch_one(inst) for inst in instruments))
        return result

    # ── Orders ───────────────────────────────────────────────────

    async def place_market_order(
        self,
        instrument: str,
        units: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> OrderResult:
        """
        Place a market order.
        units > 0 = BUY, units < 0 = SELL
        Capital.com accepts fractional sizes (e.g., 0.001 for crypto).
        """
        if units == 0:
            return OrderResult(success=False, trade_id=None, units=0, error="Cannot place order with 0 units")
        if broker_circuit_breaker.is_open:
            return OrderResult(success=False, trade_id=None, units=units, error="Circuit breaker OPEN — broker unavailable")

        epic = await self._resolve_epic(instrument)
        direction = "BUY" if units > 0 else "SELL"
        size = abs(units)

        order_data: Dict[str, Any] = {
            "epic": epic,
            "direction": direction,
            "size": size,
        }

        if stop_loss is not None:
            order_data["stopLevel"] = stop_loss
        if take_profit is not None:
            order_data["profitLevel"] = take_profit

        try:
            # Single attempt only - retrying POST can duplicate orders
            await self._ensure_session()
            resp = await self._client.post(
                "/api/v1/positions", headers=self._auth_headers(), json=order_data,
            )
            resp.raise_for_status()
            broker_circuit_breaker.record_success()
            raw = resp.json()

            deal_ref = raw.get("dealReference")
            logger.info(
                f"Market order placed: {instrument} {direction} {size} units | "
                f"SL={stop_loss} TP={take_profit} | Ref={deal_ref}"
            )

            # Confirm the deal
            if deal_ref:
                return await self._confirm_deal(deal_ref, units, instrument)

            # No dealReference — order did not go through
            logger.error(f"Market order: no dealReference in response — treating as failure")
            return OrderResult(
                success=False,
                trade_id=None,
                units=units,
                error="No dealReference returned by broker",
                raw_response=raw,
            )

        except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
            broker_circuit_breaker.record_failure()
            error_msg = str(e)
            if isinstance(e, httpx.HTTPStatusError):
                if e.response.status_code == 401:
                    self._cst = None
                    self._security_token = None
                    self._session_time = None
                    self._invalidate_cached_session()
                try:
                    error_body = e.response.json()
                    error_msg = error_body.get("errorCode", error_msg)
                except Exception:
                    pass
            logger.error(f"Market order failed: {error_msg}")
            return OrderResult(success=False, units=units, error=error_msg)

    async def place_limit_order(
        self,
        instrument: str,
        units: float,
        price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        expiry_hours: int = 24,
    ) -> OrderResult:
        """Place a limit order at a specific price."""
        if units == 0:
            return OrderResult(success=False, trade_id=None, units=0, error="Cannot place order with 0 units")
        if broker_circuit_breaker.is_open:
            return OrderResult(success=False, trade_id=None, units=units, error="Circuit breaker OPEN — broker unavailable")

        epic = await self._resolve_epic(instrument)
        direction = "BUY" if units > 0 else "SELL"
        size = abs(units)

        expiry = (datetime.now(timezone.utc) + timedelta(hours=expiry_hours))
        # Capital.com spec: goodTillDate is YYYY-MM-DDTHH:MM:SS (UTC implicit).
        # A trailing Z triggers error.invalid.daterange and rejects the order.
        expiry_str = expiry.strftime("%Y-%m-%dT%H:%M:%S")

        order_data: Dict[str, Any] = {
            "epic": epic,
            "direction": direction,
            "size": size,
            "level": price,
            "type": "LIMIT",
            "goodTillDate": expiry_str,
        }

        if stop_loss is not None:
            order_data["stopLevel"] = stop_loss
        if take_profit is not None:
            order_data["profitLevel"] = take_profit

        try:
            # Single attempt only - retrying POST can duplicate orders
            await self._ensure_session()
            resp = await self._client.post(
                "/api/v1/workingorders", headers=self._auth_headers(), json=order_data,
            )
            resp.raise_for_status()
            broker_circuit_breaker.record_success()
            raw = resp.json()
            deal_ref = raw.get("dealReference")

            logger.info(
                f"Limit order placed: {instrument} {direction} @ {price} | "
                f"{size} units | Ref={deal_ref}"
            )

            if deal_ref:
                return await self._confirm_deal(deal_ref, units, instrument)

            # No dealReference — order did not go through
            logger.error(f"Limit order: no dealReference in response — treating as failure")
            return OrderResult(
                success=False,
                trade_id=None,
                units=units,
                error="No dealReference returned by broker",
                raw_response=raw,
            )

        except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
            broker_circuit_breaker.record_failure()
            error_msg = str(e)
            if isinstance(e, httpx.HTTPStatusError):
                if e.response.status_code == 401:
                    self._cst = None
                    self._security_token = None
                    self._session_time = None
                    self._invalidate_cached_session()
                try:
                    error_msg = e.response.json().get("errorCode", error_msg)
                except Exception:
                    pass
            logger.error(f"Limit order failed: {error_msg}")
            return OrderResult(success=False, units=units, error=error_msg)

    async def place_stop_order(
        self,
        instrument: str,
        units: float,
        stop_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        expiry_hours: int = 24,
    ) -> OrderResult:
        """Place a stop order that triggers when price reaches the stop level.
        BUY stop: placed above current price (breakout above resistance).
        SELL stop: placed below current price (breakdown below support).
        units > 0 = BUY, units < 0 = SELL.
        """
        if units == 0:
            return OrderResult(success=False, trade_id=None, units=0, error="Cannot place order with 0 units")
        if broker_circuit_breaker.is_open:
            return OrderResult(success=False, trade_id=None, units=units, error="Circuit breaker OPEN — broker unavailable")

        epic = await self._resolve_epic(instrument)
        direction = "BUY" if units > 0 else "SELL"
        size = abs(units)

        expiry = (datetime.now(timezone.utc) + timedelta(hours=expiry_hours))
        # Capital.com spec: goodTillDate is YYYY-MM-DDTHH:MM:SS (UTC implicit).
        # A trailing Z triggers error.invalid.daterange and rejects the order.
        expiry_str = expiry.strftime("%Y-%m-%dT%H:%M:%S")

        order_data: Dict[str, Any] = {
            "epic": epic,
            "direction": direction,
            "size": size,
            "level": stop_price,
            "type": "STOP",
            "goodTillDate": expiry_str,
        }

        if stop_loss is not None:
            order_data["stopLevel"] = stop_loss
        if take_profit is not None:
            order_data["profitLevel"] = take_profit

        try:
            # Single attempt only - retrying POST can duplicate orders
            await self._ensure_session()
            if broker_circuit_breaker.is_open:
                raise ConnectionError("Circuit breaker OPEN")
            resp = await self._client.post(
                "/api/v1/workingorders",
                headers=self._auth_headers(),
                json=order_data,
            )
            resp.raise_for_status()
            broker_circuit_breaker.record_success()
            raw = resp.json()
            deal_ref = raw.get("dealReference")

            logger.info(
                f"Stop order placed: {instrument} {direction} @ {stop_price} | "
                f"{size} units | SL={stop_loss} TP={take_profit} | Ref={deal_ref}"
            )

            if deal_ref:
                return await self._confirm_deal(deal_ref, units, instrument)

            # No dealReference — order did not go through
            logger.error(f"Stop order: no dealReference in response — treating as failure")
            return OrderResult(
                success=False,
                trade_id=None,
                units=units,
                error="No dealReference returned by broker",
                raw_response=raw,
            )

        except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
            broker_circuit_breaker.record_failure()
            error_msg = str(e)
            if isinstance(e, httpx.HTTPStatusError):
                if e.response.status_code == 401:
                    self._cst = None
                    self._security_token = None
                    self._session_time = None
                    self._invalidate_cached_session()
                try:
                    error_msg = e.response.json().get("errorCode", error_msg)
                except Exception:
                    pass
            logger.error(f"Stop order failed: {error_msg}")
            return OrderResult(success=False, units=units, error=error_msg)

    async def _confirm_deal(self, deal_reference: str, units: float, instrument: str = "") -> OrderResult:
        """Confirm a deal was executed using the dealReference."""
        await asyncio.sleep(0.5)  # Brief delay for deal processing
        try:
            data = await self._get(f"/api/v1/confirms/{deal_reference}")

            status = data.get("dealStatus", "")
            deal_id = data.get("dealId")
            level = data.get("level")
            affected = data.get("affectedDeals", [])

            if status == "ACCEPTED":
                trade_id = affected[0]["dealId"] if affected else deal_id
                if not trade_id:
                    # Capital.com accepted but gave no trade ID — try to find from open positions
                    logger.warning(
                        f"Order ACCEPTED but no dealId returned for {instrument}. "
                        "Falling back to position search by instrument — may match wrong trade if multiple positions exist."
                    )
                    try:
                        raw = await self._get("/api/v1/positions")
                        candidates = [
                            p for p in raw.get("positions", [])
                            if self._denormalize_instrument(
                                p.get("market", {}).get("epic", p.get("position", {}).get("epic", ""))
                            ) == instrument
                        ]
                        # Sort by creation date descending to pick the most recent position
                        candidates.sort(
                            key=lambda p: p.get("position", {}).get("createdDateUTC", ""),
                            reverse=True,
                        )
                        if candidates:
                            trade_id = candidates[0].get("position", {}).get("dealId", "")
                            logger.info(f"Found trade ID from open positions (most recent): {trade_id}")
                    except Exception as e:
                        logger.error(f"Failed to search open positions for trade ID: {e}")
                return OrderResult(
                    success=True if trade_id else False,
                    trade_id=trade_id,
                    fill_price=float(level) if level else None,
                    units=units,
                    raw_response=data,
                    error="Order accepted but no trade ID found" if not trade_id else None,
                )
            else:
                reason = data.get("reason", "UNKNOWN")
                return OrderResult(
                    success=False,
                    trade_id=deal_id,
                    units=units,
                    error=f"Deal {status}: {reason}",
                    raw_response=data,
                )
        except Exception as e:
            logger.error(f"Deal confirmation failed: {e}")
            return OrderResult(
                success=False,
                trade_id=deal_reference,
                units=units,
                error=f"Deal confirmation failed: {e}",
            )

    # ── Trade Management ─────────────────────────────────────────

    async def get_open_trades(self) -> List[TradeInfo]:
        """Get all currently open positions."""
        data = await self._get("/api/v1/positions")
        positions = data.get("positions", [])

        result: List[TradeInfo] = []
        for p in positions:
            pos = p.get("position", {})
            market = p.get("market", {})

            direction = pos.get("direction", "BUY")
            size = float(pos.get("size", 0))
            units = size if direction == "BUY" else -size

            entry = float(pos.get("level", 0))
            current_bid = float(market.get("bid", entry))
            current_ask = float(market.get("offer", entry))
            # BUY closes at bid, SELL closes at ask (exit price = opposite side of spread)
            current = current_bid if direction == "BUY" else current_ask

            pnl = float(pos.get("profit", 0))

            sl = pos.get("stopLevel")
            tp = pos.get("profitLevel")

            instrument = self._denormalize_instrument(
                market.get("epic", pos.get("epic", ""))
            )

            result.append(TradeInfo(
                trade_id=pos.get("dealId", ""),
                instrument=instrument,
                direction=direction,
                units=units,
                entry_price=entry,
                current_price=current,
                unrealized_pnl=pnl,
                stop_loss=float(sl) if sl else None,
                take_profit=float(tp) if tp else None,
            ))

        return result

    async def _fetch_position_levels(self, trade_id: str) -> tuple:
        """Return (stopLevel, profitLevel) for a position, or (None, None) on miss."""
        try:
            data = await self._get(f"/api/v1/positions/{trade_id}")
            pos = data.get("position", {}) if isinstance(data, dict) else {}
            sl = pos.get("stopLevel")
            tp = pos.get("profitLevel")
            return (
                float(sl) if sl is not None else None,
                float(tp) if tp is not None else None,
            )
        except Exception as e:
            logger.warning(f"Failed to fetch current levels for {trade_id}: {e}")
            return None, None

    async def modify_trade_sl(self, trade_id: str, stop_loss: float) -> bool:
        """Move stop loss on an existing position, preserving the current TP."""
        try:
            # Capital.com's PUT /positions/{dealId} replaces the level block.
            # Always send both stopLevel and profitLevel to avoid accidentally
            # clearing the unmodified side.
            _sl_current, tp_current = await self._fetch_position_levels(trade_id)
            body = {"stopLevel": stop_loss}
            if tp_current is not None:
                body["profitLevel"] = tp_current
            await self._put(f"/api/v1/positions/{trade_id}", json_data=body)
            logger.info(f"Position {trade_id} SL moved to {stop_loss} (TP preserved={tp_current})")
            return True
        except Exception as e:
            logger.error(f"Failed to modify SL for {trade_id}: {e}")
            return False

    async def modify_trade_tp(self, trade_id: str, take_profit: float) -> bool:
        """Modify take profit on an existing position, preserving the current SL."""
        try:
            sl_current, _tp_current = await self._fetch_position_levels(trade_id)
            body = {"profitLevel": take_profit}
            if sl_current is not None:
                body["stopLevel"] = sl_current
            await self._put(f"/api/v1/positions/{trade_id}", json_data=body)
            logger.info(f"Position {trade_id} TP moved to {take_profit} (SL preserved={sl_current})")
            return True
        except Exception as e:
            logger.error(f"Failed to modify TP for {trade_id}: {e}")
            return False

    async def close_trade(self, trade_id: str) -> bool:
        """Close a specific position."""
        try:
            await self._delete(f"/api/v1/positions/{trade_id}")
            logger.info(f"Position {trade_id} closed")
            return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(f"Trade {trade_id} already closed (404)")
                return True
            logger.error(f"Failed to close position {trade_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to close position {trade_id}: {e}")
            return False

    # ── Instrument Info ──────────────────────────────────────────

    async def get_instrument_info(self, instrument: str) -> Dict[str, Any]:
        """Get instrument details using resolved epic (spot preferred)."""
        epic = await self._resolve_epic(instrument)
        try:
            # Use the specific market detail endpoint with resolved epic
            data = await self._get(f"/api/v1/markets/{epic}")
            result = data.get("instrument", {})
            # Merge dealing rules and snapshot into result for convenience
            result["dealingRules"] = data.get("dealingRules", {})
            result["snapshot"] = data.get("snapshot", {})
            result["epic"] = epic
            return result
        except Exception as e:
            logger.debug(f"Market detail lookup failed for {epic}, falling back to search: {e}")
        # Fallback to search
        try:
            data = await self._get("/api/v1/markets", params={
                "searchTerm": instrument.replace("_", "/"),
                "limit": 10,
            })
            for m in data.get("markets", []):
                if m.get("epic") == epic:
                    return m
            markets = data.get("markets", [])
            if markets:
                return markets[0]
        except Exception as e:
            logger.warning(f"Market search also failed for {instrument}: {e}")
        return {"epic": epic, "instrumentName": instrument}

    async def get_pip_value(self, instrument: str) -> float:
        """Get the pip value for an instrument."""
        pair = instrument.upper().replace("/", "_")
        if "JPY" in pair:
            return 0.01
        if pair in ("XAU_USD", "GOLD"):
            return 0.1
        if pair in ("XAG_USD", "SILVER"):
            return 0.01
        from strategies.base import _is_crypto_instrument
        if _is_crypto_instrument(pair):
            return 1.0
        if any(pair.startswith(idx) for idx in ("US30", "US2000", "NAS100", "SPX500", "DE30", "FR40", "UK100", "JP225", "AU200", "HK33", "CN50")):
            return 1.0
        return 0.0001

    # ── Cleanup ──────────────────────────────────────────────────

    async def close(self):
        """Close the session and HTTP client."""
        try:
            if self._cst:
                await self._client.delete(
                    "/api/v1/session",
                    headers=self._auth_headers(),
                )
        except Exception:
            pass
        await self._client.aclose()
        logger.info("Capital.com client closed")

    # ── Helpers ───────────────────────────────────────────────────

    def normalize_instrument(self, instrument: str) -> str:
        """Normalize instrument name. We use underscore format internally."""
        return instrument.replace("/", "_").upper()
