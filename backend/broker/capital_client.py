"""
NeonTrade AI - Capital.com API Client
Implements BaseBroker interface for Capital.com REST API.

Capital.com uses session-based auth with CST + X-SECURITY-TOKEN headers.
Sessions expire after 10 minutes of inactivity - auto-refreshed.

API Docs: https://open-api.capital.com/
"""

import httpx
import asyncio
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


# ── Granularity mapping (our format -> Capital.com format) ────
GRANULARITY_MAP = {
    # Our standard names -> Capital.com resolution
    "M1": "MINUTE",
    "M2": "MINUTE_2",
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
        """Authenticate, get CST + X-SECURITY-TOKEN, and switch to the correct account."""
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
            self._session_time = datetime.now(timezone.utc)

            logger.info("Capital.com session created successfully")

            # Switch to the correct account (avoid demo account)
            await self._select_account()

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
                # Auto-detect: the real account typically has the smaller balance
                # (user deposit vs. virtual demo funds like ~$60k)
                # If there's only one account, use it
                if len(accounts) == 1:
                    target = accounts[0]["accountId"]
                else:
                    # Sort by balance ascending — the real account has less money
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
                # Check for 429 Rate Limit — respect Retry-After header
                retry_after = None
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429:
                    retry_after_hdr = e.response.headers.get('Retry-After')
                    if retry_after_hdr:
                        try:
                            retry_after = float(retry_after_hdr)
                        except (ValueError, TypeError):
                            retry_after = None
                if attempt < 3:
                    delay = retry_after + 0.5 if retry_after else min(0.5 * (2 ** attempt), 10.0)
                    logger.debug(f"[_get] {path} attempt {attempt+1}/4 failed: {e}. Retry in {delay:.1f}s")
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
                if attempt < 2:
                    delay = min(0.5 * (2 ** attempt), 10.0)
                    logger.debug(f"[_post] {path} attempt {attempt+1}/3 failed: {e}. Retry in {delay:.1f}s")
                    await asyncio.sleep(delay)
                    await self._ensure_session()
            except Exception as e:
                broker_circuit_breaker.record_failure()
                raise
        broker_circuit_breaker.record_failure()
        raise last_exc

    @retry_async(max_retries=2, base_delay=0.5, exceptions=(httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException))
    async def _put(self, path: str, json_data: Optional[Dict] = None) -> httpx.Response:
        """Authenticated PUT request with retry."""
        await self._ensure_session()
        resp = await self._client.put(
            path, headers=self._auth_headers(), json=json_data or {},
        )
        resp.raise_for_status()
        return resp

    @retry_async(max_retries=2, base_delay=0.5, exceptions=(httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException))
    async def _delete(self, path: str, json_data: Optional[Dict] = None) -> httpx.Response:
        """Authenticated DELETE request with retry."""
        await self._ensure_session()
        resp = await self._client.request(
            "DELETE", path, headers=self._auth_headers(), json=json_data,
        )
        resp.raise_for_status()
        return resp

    # ── Instrument Resolution ────────────────────────────────────

    async def _resolve_epic(self, instrument: str) -> str:
        """
        Convert our instrument name (e.g., EUR_USD) to Capital.com epic.
        Capital.com uses names like 'EURUSD' for forex.
        Prefers spot/CFD instruments over forwards/futures.
        """
        if instrument in self._epic_cache:
            return self._epic_cache[instrument]

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

                # Prefer CURRENCIES type for forex pairs, or shortest epic
                # (forwards/futures have suffixes like M2026, U2026)
                best = None
                for m in markets:
                    epic = m["epic"]
                    inst_type = m.get("instrumentType", "")
                    # Exact match on stripped name = spot instrument
                    if epic.upper() == epic_guess.upper():
                        best = epic
                        break
                    # For forex, prefer CURRENCIES type
                    if inst_type == "CURRENCIES" and best is None:
                        best = epic
                    # For stocks, prefer SHARES type
                    elif inst_type == "SHARES" and best is None:
                        best = epic
                    # Fallback: prefer shortest epic (spot, not forwards)
                    elif best is None or len(epic) < len(best):
                        best = epic

                if best:
                    self._epic_cache[instrument] = best
                    return best
        except Exception as e:
            logger.debug(f"Market search failed for {instrument}: {e}")

        # Fallback to our guess (don't cache - might be wrong, retry next time)
        return epic_guess

    async def warm_epic_cache(self, instruments: List[str]) -> None:
        """Pre-resolve all instrument epics with throttling.
        Call this BEFORE the initial scan to avoid burst API calls
        from interleaved search + candle requests."""
        uncached = [i for i in instruments if i not in self._epic_cache]
        if not uncached:
            return
        logger.info(f"Warming epic cache for {len(uncached)} instruments...")
        for inst in uncached:
            try:
                await self._resolve_epic(inst)
            except Exception as e:
                logger.debug(f"Epic warmup failed for {inst}: {e}")
            await asyncio.sleep(0.5)
        logger.info(f"Epic cache warmed: {len(self._epic_cache)} instruments cached")

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

            vol = int(p.get("lastTradedVolume", 0))

            result.append(CandleData(
                time=snap_time,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=vol,
                complete=True,  # Capital.com doesn't flag incomplete candles
            ))

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
            raw = resp.json()

            deal_ref = raw.get("dealReference")
            logger.info(
                f"Market order placed: {instrument} {direction} {size} units | "
                f"SL={stop_loss} TP={take_profit} | Ref={deal_ref}"
            )

            # Confirm the deal
            if deal_ref:
                return await self._confirm_deal(deal_ref, units)

            return OrderResult(
                success=True,
                trade_id=deal_ref,
                units=units,
                raw_response=raw,
            )

        except httpx.HTTPStatusError as e:
            error_msg = str(e)
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
        units: int,
        price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        expiry_hours: int = 24,
    ) -> OrderResult:
        """Place a limit order at a specific price."""
        epic = await self._resolve_epic(instrument)
        direction = "BUY" if units > 0 else "SELL"
        size = abs(units)

        expiry = (datetime.now(timezone.utc) + timedelta(hours=expiry_hours))
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
            raw = resp.json()
            deal_ref = raw.get("dealReference")

            logger.info(
                f"Limit order placed: {instrument} {direction} @ {price} | "
                f"{size} units | Ref={deal_ref}"
            )

            if deal_ref:
                return await self._confirm_deal(deal_ref, units)

            return OrderResult(
                success=True,
                trade_id=deal_ref,
                units=units,
                raw_response=raw,
            )

        except httpx.HTTPStatusError as e:
            error_msg = str(e)
            try:
                error_msg = e.response.json().get("errorCode", error_msg)
            except Exception:
                pass
            logger.error(f"Limit order failed: {error_msg}")
            return OrderResult(success=False, units=units, error=error_msg)

    async def place_stop_order(
        self,
        instrument: str,
        units: int,
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
        epic = await self._resolve_epic(instrument)
        direction = "BUY" if units > 0 else "SELL"
        size = abs(units)

        expiry = (datetime.now(timezone.utc) + timedelta(hours=expiry_hours))
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
            resp = await self._post("/api/v1/workingorders", json_data=order_data)
            raw = resp.json()
            deal_ref = raw.get("dealReference")

            logger.info(
                f"Stop order placed: {instrument} {direction} @ {stop_price} | "
                f"{size} units | SL={stop_loss} TP={take_profit} | Ref={deal_ref}"
            )

            if deal_ref:
                return await self._confirm_deal(deal_ref, units)

            return OrderResult(
                success=True,
                trade_id=deal_ref,
                units=units,
                raw_response=raw,
            )

        except httpx.HTTPStatusError as e:
            error_msg = str(e)
            try:
                error_msg = e.response.json().get("errorCode", error_msg)
            except Exception:
                pass
            logger.error(f"Stop order failed: {error_msg}")
            return OrderResult(success=False, units=units, error=error_msg)

    async def _confirm_deal(self, deal_reference: str, units: int) -> OrderResult:
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
                return OrderResult(
                    success=True,
                    trade_id=trade_id,
                    fill_price=float(level) if level else None,
                    units=units,
                    raw_response=data,
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
            current = current_bid if direction == "SELL" else current_ask

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

    async def modify_trade_sl(self, trade_id: str, stop_loss: float) -> bool:
        """Move stop loss on an existing position."""
        try:
            await self._put(f"/api/v1/positions/{trade_id}", json_data={
                "stopLevel": stop_loss,
            })
            logger.info(f"Position {trade_id} SL moved to {stop_loss}")
            return True
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to modify SL for {trade_id}: {e}")
            return False

    async def modify_trade_tp(self, trade_id: str, take_profit: float) -> bool:
        """Modify take profit on an existing position."""
        try:
            await self._put(f"/api/v1/positions/{trade_id}", json_data={
                "profitLevel": take_profit,
            })
            return True
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to modify TP for {trade_id}: {e}")
            return False

    async def close_trade(self, trade_id: str) -> bool:
        """Close a specific position."""
        try:
            await self._delete(f"/api/v1/positions/{trade_id}")
            logger.info(f"Position {trade_id} closed")
            return True
        except httpx.HTTPStatusError as e:
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
        except Exception:
            pass
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
        except Exception:
            pass
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
        if any(pair.startswith(c) for c in ("BTC", "ETH", "SOL", "ADA", "DOT", "LINK", "AVAX", "MATIC", "UNI", "ATOM", "XRP", "DOGE", "LTC", "BNB", "FTM", "ALGO", "XLM", "EOS", "XTZ", "VET")):
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
