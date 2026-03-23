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
    ):
        super().__init__(BrokerType.CAPITAL)

        self.api_key = api_key
        self.password = password
        self.identifier = identifier  # email address

        # Base URL
        if environment == "live":
            self.base_url = "https://api-capital.backend-capital.com"
        else:
            self.base_url = "https://demo-api-capital.backend-capital.com"

        # Session tokens
        self._cst: Optional[str] = None
        self._security_token: Optional[str] = None
        self._session_time: Optional[datetime] = None

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
        now = datetime.now(timezone.utc)

        # Session valid for ~9 min (refresh before 10 min expiry)
        if (self._cst and self._security_token and self._session_time
                and (now - self._session_time) < timedelta(minutes=9)):
            return

        await self._create_session()

    async def _create_session(self):
        """Authenticate and get CST + X-SECURITY-TOKEN."""
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

    def _auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for API requests."""
        return {
            "X-CAP-API-KEY": self.api_key,
            "CST": self._cst or "",
            "X-SECURITY-TOKEN": self._security_token or "",
            "Content-Type": "application/json",
        }

    @retry_async(max_retries=3, base_delay=0.5, exceptions=(httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException))
    async def _get(self, path: str, params: Optional[Dict] = None) -> Dict:
        """Authenticated GET request with retry."""
        if broker_circuit_breaker.is_open:
            raise ConnectionError("Circuit breaker OPEN - broker unavailable")
        await self._ensure_session()
        try:
            resp = await self._client.get(
                path, headers=self._auth_headers(), params=params,
            )
            resp.raise_for_status()
            broker_circuit_breaker.record_success()
            return resp.json()
        except Exception as e:
            broker_circuit_breaker.record_failure()
            raise

    @retry_async(max_retries=2, base_delay=0.5, exceptions=(httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException))
    async def _post(self, path: str, json_data: Optional[Dict] = None) -> httpx.Response:
        """Authenticated POST request with retry."""
        if broker_circuit_breaker.is_open:
            raise ConnectionError("Circuit breaker OPEN - broker unavailable")
        await self._ensure_session()
        try:
            resp = await self._client.post(
                path, headers=self._auth_headers(), json=json_data or {},
            )
            resp.raise_for_status()
            broker_circuit_breaker.record_success()
            return resp
        except Exception as e:
            broker_circuit_breaker.record_failure()
            raise

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

        # Fallback to our guess
        self._epic_cache[instrument] = epic_guess
        return epic_guess

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
        """Get account balance, equity, margin, etc."""
        data = await self._get("/api/v1/accounts")
        accounts = data.get("accounts", [])
        if not accounts:
            raise ValueError("No accounts found")

        acct = accounts[0]  # Use first account
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
            snap_time = p.get("snapshotTime", "")
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
        units: int,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> OrderResult:
        """
        Place a market order.
        units > 0 = BUY, units < 0 = SELL
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
            resp = await self._post("/api/v1/positions", json_data=order_data)
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
            resp = await self._post("/api/v1/workingorders", json_data=order_data)
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
            logger.warning(f"Deal confirmation failed: {e}")
            return OrderResult(
                success=True,  # Assume success if confirm endpoint fails
                trade_id=deal_reference,
                units=units,
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
            units = int(size) if direction == "BUY" else -int(size)

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
        """Get instrument details from market search."""
        epic = await self._resolve_epic(instrument)
        try:
            data = await self._get("/api/v1/markets", params={
                "searchTerm": instrument.replace("_", "/"),
                "limit": 1,
            })
            markets = data.get("markets", [])
            if markets:
                return markets[0]
        except Exception:
            pass
        return {"epic": epic, "instrumentName": instrument}

    async def get_pip_value(self, instrument: str) -> float:
        """Get the pip value for an instrument."""
        # Standard forex pip values
        pair = instrument.upper().replace("/", "_")
        if "JPY" in pair:
            return 0.01
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
