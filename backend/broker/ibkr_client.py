"""
NeonTrade AI - Interactive Brokers (IBKR) Web API Client
Implements BaseBroker interface using IBKR OAuth 1.0a REST API.

Auth flow (OAuth 1.0a with Live Session Token):
1. Decrypt access_token_secret with RSA private encryption key
2. Generate DH key pair from our DH parameters
3. Call /oauth/live_session_token signed with RSA-SHA256
4. Compute DH shared secret -> derive Live Session Token (LST)
5. All subsequent requests signed with HMAC-SHA256 using LST

API Base: https://api.ibkr.com/v1/api
OAuth:    https://www.interactivebrokers.com/campus/ibkr-api-page/oauth-1-0a-extended/
"""

import asyncio
import base64
import hashlib
import hmac as hmac_mod
import os
import struct
import time
import urllib.parse
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
from loguru import logger
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding, utils as asym_utils

from broker.base import (
    BaseBroker,
    BrokerType,
    PriceData,
    CandleData,
    OrderResult,
    AccountSummary,
    TradeInfo,
)


# ── Granularity mapping (our format -> IBKR format) ─────────
GRANULARITY_MAP = {
    "M1": ("1min", "1d"),
    "M5": ("5mins", "1d"),
    "M15": ("15mins", "2d"),
    "M30": ("30mins", "5d"),
    "H1": ("1hour", "1w"),
    "H4": ("4hours", "1M"),
    "D": ("1day", "6M"),
    "W": ("1week", "2Y"),
}


class IBKRClient(BaseBroker):
    """Interactive Brokers REST API client via OAuth 1.0a."""

    BASE_URL = "https://api.ibkr.com/v1/api"
    OAUTH_BASE = "https://api.ibkr.com/v1/api"

    def __init__(
        self,
        consumer_key: str,
        access_token: str,
        access_token_secret: str,
        keys_dir: str = "keys",
        environment: str = "live",
    ):
        super().__init__(BrokerType.IBKR)

        self.consumer_key = consumer_key
        self.access_token = access_token
        self.access_token_secret_enc = access_token_secret
        self.environment = environment
        self.keys_dir = Path(keys_dir)

        # Load RSA keys
        self._signing_key = self._load_private_key("private_signature.pem")
        self._encryption_key = self._load_private_key("private_encryption.pem")
        self._dh_param_pem = self._load_file("dhparam.pem")

        # Live Session Token (computed via DH exchange with IBKR)
        self._lst: Optional[bytes] = None
        self._lst_expiry: Optional[datetime] = None

        # Decrypted access token secret
        self._access_secret_bytes: Optional[bytes] = None

        # Account ID (discovered on first call)
        self._account_id: Optional[str] = None

        # Contract ID cache (symbol -> conid)
        self._conid_cache: Dict[str, int] = {}

        # HTTP client
        self._client = httpx.AsyncClient(timeout=30.0)

        # Decrypt the access token secret on init
        self._decrypt_access_token_secret()

        logger.info(f"IBKR client initialized | Environment: {environment}")

    # ── Key Loading ────────────────────────────────────────────

    def _load_private_key(self, filename: str):
        """Load an RSA private key from PEM file."""
        path = self.keys_dir / filename
        with open(path, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=None)

    def _load_file(self, filename: str) -> bytes:
        """Load raw file content."""
        path = self.keys_dir / filename
        with open(path, "rb") as f:
            return f.read()

    # ── Access Token Secret Decryption ─────────────────────────

    def _decrypt_access_token_secret(self):
        """
        Decrypt the access_token_secret using RSA private encryption key.
        IBKR encrypts it with our public encryption key during OAuth setup.
        """
        enc_bytes = base64.b64decode(self.access_token_secret_enc)

        try:
            self._access_secret_bytes = self._encryption_key.decrypt(
                enc_bytes,
                asym_padding.PKCS1v15(),
            )
            logger.info("Access token secret decrypted successfully")
        except Exception as e:
            logger.warning(
                f"RSA decryption failed ({e}), treating access_token_secret as plaintext"
            )
            self._access_secret_bytes = enc_bytes

    # ── Live Session Token (DH Exchange) ───────────────────────

    def _parse_dh_params(self):
        """Parse p and g from DH parameters PEM file using OpenSSL CLI."""
        import subprocess
        import re

        result = subprocess.run(
            ["openssl", "dhparam", "-in", str(self.keys_dir / "dhparam.pem"), "-text", "-noout"],
            capture_output=True, text=True,
        )
        text = result.stdout

        # Parse prime (P:) — multiline hex with colons
        # Find everything between "P:" (or "prime:") and "G:" (or "generator:")
        p_match = re.search(
            r"(?:prime|P):\s*\n((?:\s+[0-9a-f:]+\n)+)",
            text, re.IGNORECASE,
        )
        if not p_match:
            raise ValueError(f"Cannot parse DH prime. OpenSSL output:\n{text[:500]}")
        p_hex = p_match.group(1).replace(":", "").replace(" ", "").replace("\n", "")
        p = int(p_hex, 16)

        # Parse generator
        g_match = re.search(r"(?:generator|G):\s*(\d+)", text, re.IGNORECASE)
        g = int(g_match.group(1)) if g_match else 2

        logger.debug(f"DH params loaded: p={p.bit_length()} bits, g={g}")
        return p, g

    async def _compute_lst(self):
        """
        Compute the Live Session Token via DH key exchange with IBKR.

        Flow:
        1. Parse DH params (p, g), generate DH key pair manually
        2. POST /oauth/live_session_token signed with RSA-SHA256
        3. Compute DH shared secret
        4. Derive LST = HMAC-SHA1(prepend, decrypted_access_token_secret)
        """
        import secrets

        # Parse DH parameters
        p, g = self._parse_dh_params()

        # Generate DH key pair manually (avoids OpenSSL DH bugs)
        dh_private = secrets.randbelow(p - 2) + 2  # random in [2, p-1]
        dh_public = pow(g, dh_private, p)

        # Encode our DH public key
        byte_length = (dh_public.bit_length() + 7) // 8
        dh_pub_bytes = dh_public.to_bytes(byte_length, byteorder="big")
        dh_challenge = base64.b64encode(dh_pub_bytes).decode("ascii")

        # Build the OAuth-signed request to /oauth/live_session_token
        url = f"{self.OAUTH_BASE}/oauth/live_session_token"
        timestamp = str(int(time.time()))
        nonce = base64.b64encode(os.urandom(16)).decode("ascii").rstrip("=")

        oauth_params = {
            "oauth_consumer_key": self.consumer_key,
            "oauth_token": self.access_token,
            "oauth_signature_method": "RSA-SHA256",
            "oauth_timestamp": timestamp,
            "oauth_nonce": nonce,
            "oauth_version": "1.0",
            "diffie_hellman_challenge": dh_challenge,
        }

        # Build signature base string
        base_string = self._build_base_string("POST", url, oauth_params)

        # Sign with RSA-SHA256 using private signing key
        signature = self._signing_key.sign(
            base_string.encode("utf-8"),
            asym_padding.PKCS1v15(),
            hashes.SHA256(),
        )
        oauth_params["oauth_signature"] = base64.b64encode(signature).decode("ascii")

        # Build Authorization header
        auth_header = self._build_auth_header(oauth_params)

        # Make the request (form-encoded, not JSON)
        try:
            resp = await self._client.post(
                url,
                headers={
                    "Authorization": auth_header,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"diffie_hellman_challenge": dh_challenge},
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            body = ""
            try:
                body = e.response.text
            except Exception:
                pass
            raise ConnectionError(
                f"IBKR LST request failed ({e.response.status_code}): {body}"
            )

        # Extract IBKR's DH response
        dh_response_b64 = data.get("diffie_hellman_response", "")
        lst_signature = data.get("live_session_token_signature", "")

        if not dh_response_b64:
            raise ConnectionError(f"No DH response from IBKR: {data}")

        # Decode IBKR's DH public key
        ibkr_dh_pub_bytes = base64.b64decode(dh_response_b64)
        ibkr_dh_public = int.from_bytes(ibkr_dh_pub_bytes, byteorder="big")

        # Compute shared secret: ibkr_public ^ our_private mod p
        shared_secret = pow(ibkr_dh_public, dh_private, p)
        shared_bytes_len = (shared_secret.bit_length() + 7) // 8
        shared_bytes = shared_secret.to_bytes(shared_bytes_len, byteorder="big")

        # Prepend = first 16 bytes of hex(shared_secret)
        shared_hex = shared_bytes.hex()
        prepend = bytes.fromhex(shared_hex[:32])  # 16 bytes = 32 hex chars

        # LST = HMAC-SHA1(prepend, decrypted_access_token_secret)
        self._lst = hmac_mod.new(
            prepend,
            self._access_secret_bytes,
            hashlib.sha1,
        ).digest()

        # Verify: HMAC-SHA1(LST, consumer_key) should match lst_signature
        verify = hmac_mod.new(
            self._lst,
            self.consumer_key.encode("utf-8"),
            hashlib.sha1,
        ).digest()
        verify_b64 = base64.b64encode(verify).decode("ascii")

        if verify_b64 == lst_signature:
            logger.info("IBKR Live Session Token verified successfully")
        else:
            logger.warning(
                f"LST verification mismatch. Expected: {lst_signature}, Got: {verify_b64}. "
                f"Proceeding anyway — auth may still work."
            )

        self._lst_expiry = datetime.now(timezone.utc) + timedelta(hours=23)

    async def _ensure_lst(self):
        """Ensure we have a valid Live Session Token."""
        now = datetime.now(timezone.utc)
        if self._lst and self._lst_expiry and now < self._lst_expiry:
            return
        await self._compute_lst()

    # ── OAuth Signature Helpers ────────────────────────────────

    def _build_base_string(
        self, method: str, url: str, params: Dict[str, str]
    ) -> str:
        """Build OAuth 1.0a signature base string."""
        # Remove oauth_signature if present
        sign_params = {k: v for k, v in params.items() if k != "oauth_signature"}

        sorted_params = sorted(sign_params.items())
        param_string = "&".join(
            f"{urllib.parse.quote(str(k), safe='')}"
            f"={urllib.parse.quote(str(v), safe='')}"
            for k, v in sorted_params
        )

        return (
            f"{method.upper()}&"
            f"{urllib.parse.quote(url, safe='')}&"
            f"{urllib.parse.quote(param_string, safe='')}"
        )

    def _build_auth_header(self, oauth_params: Dict[str, str]) -> str:
        """Build OAuth Authorization header string."""
        # Only include oauth_* params in the header (not extra params like diffie_hellman_challenge)
        header_params = {k: v for k, v in oauth_params.items() if k.startswith("oauth_")}
        return "OAuth " + ", ".join(
            f'{k}="{urllib.parse.quote(str(v), safe="")}"'
            for k, v in sorted(header_params.items())
        )

    def _sign_request(
        self,
        method: str,
        url: str,
        params: Optional[Dict] = None,
    ) -> Dict[str, str]:
        """
        Generate OAuth 1.0a Authorization header signed with HMAC-SHA256.
        Uses the Live Session Token (LST) as the HMAC key.
        """
        timestamp = str(int(time.time()))
        nonce = base64.b64encode(os.urandom(16)).decode("ascii").rstrip("=")

        oauth_params = {
            "oauth_consumer_key": self.consumer_key,
            "oauth_token": self.access_token,
            "oauth_signature_method": "HMAC-SHA256",
            "oauth_timestamp": timestamp,
            "oauth_nonce": nonce,
            "oauth_version": "1.0",
        }

        # Include query params in signature
        all_params = dict(oauth_params)
        if params:
            all_params.update({str(k): str(v) for k, v in params.items()})

        # Build and sign
        base_string = self._build_base_string(method, url, all_params)

        signature = hmac_mod.new(
            self._lst,
            base_string.encode("utf-8"),
            hashlib.sha256,
        ).digest()

        oauth_params["oauth_signature"] = base64.b64encode(signature).decode("ascii")

        return {"Authorization": self._build_auth_header(oauth_params)}

    # ── HTTP Helpers ───────────────────────────────────────────

    async def _get(self, path: str, params: Optional[Dict] = None) -> Any:
        """Authenticated GET request."""
        await self._ensure_lst()
        url = f"{self.BASE_URL}{path}"
        headers = self._sign_request("GET", url, params)
        resp = await self._client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()

    async def _post(self, path: str, json_data: Optional[Dict] = None) -> Any:
        """Authenticated POST request."""
        await self._ensure_lst()
        url = f"{self.BASE_URL}{path}"
        headers = self._sign_request("POST", url)
        headers["Content-Type"] = "application/json"
        resp = await self._client.post(url, headers=headers, json=json_data or {})
        resp.raise_for_status()
        return resp.json()

    async def _delete(self, path: str) -> Any:
        """Authenticated DELETE request."""
        await self._ensure_lst()
        url = f"{self.BASE_URL}{path}"
        headers = self._sign_request("DELETE", url)
        resp = await self._client.delete(url, headers=headers)
        resp.raise_for_status()
        return resp.json()

    # ── Account Discovery ─────────────────────────────────────

    async def _ensure_account_id(self):
        """Discover the account ID on first use."""
        if self._account_id:
            return

        data = await self._get("/portfolio/accounts")
        if isinstance(data, list) and data:
            self._account_id = data[0].get("accountId") or data[0].get("id")
            logger.info(f"IBKR account discovered: {self._account_id}")
        else:
            raise ValueError(f"No IBKR accounts found: {data}")

    # ── Contract Resolution ───────────────────────────────────

    async def _resolve_conid(self, instrument: str) -> int:
        """Convert instrument name (e.g., EUR_USD) to IBKR contract ID."""
        if instrument in self._conid_cache:
            return self._conid_cache[instrument]

        search_symbol = instrument.replace("_", ".")

        try:
            data = await self._get("/iserver/secdef/search", params={
                "symbol": search_symbol,
                "secType": "CASH",
            })
            if isinstance(data, list) and data:
                conid = data[0].get("conid")
                if conid:
                    self._conid_cache[instrument] = int(conid)
                    return int(conid)

            # Try without secType (stocks, indices, etc.)
            symbol = instrument.replace("_", "")
            data = await self._get("/iserver/secdef/search", params={
                "symbol": symbol,
            })
            if isinstance(data, list) and data:
                conid = data[0].get("conid")
                if conid:
                    self._conid_cache[instrument] = int(conid)
                    return int(conid)

        except Exception as e:
            logger.error(f"Failed to resolve conid for {instrument}: {e}")

        raise ValueError(f"Cannot resolve contract ID for {instrument}")

    # ── Account ──────────────────────────────────────────────

    async def get_account_summary(self) -> AccountSummary:
        """Get account balance, equity, margin, etc."""
        await self._ensure_account_id()

        data = await self._get(f"/portfolio/{self._account_id}/summary")

        def _val(key: str) -> float:
            v = data.get(key, {})
            if isinstance(v, dict):
                return float(v.get("amount", 0))
            return float(v or 0)

        return AccountSummary(
            balance=_val("totalcashvalue"),
            equity=_val("netliquidation"),
            unrealized_pnl=_val("unrealizedpnl"),
            margin_used=_val("initmarginreq"),
            margin_available=_val("availablefunds"),
            open_trade_count=0,
            currency=data.get("totalcashvalue", {}).get("currency", "USD")
            if isinstance(data.get("totalcashvalue"), dict) else "USD",
        )

    async def get_account_balance(self) -> float:
        """Get current account balance."""
        summary = await self.get_account_summary()
        return summary.balance

    # ── Market Data ──────────────────────────────────────────

    async def get_candles(
        self,
        instrument: str,
        granularity: str = "H1",
        count: int = 100,
    ) -> List[CandleData]:
        """Get candlestick data for an instrument."""
        conid = await self._resolve_conid(instrument)
        bar_size, period = GRANULARITY_MAP.get(granularity, ("1hour", "1w"))

        data = await self._get("/iserver/marketdata/history", params={
            "conid": conid,
            "period": period,
            "bar": bar_size,
        })

        result: List[CandleData] = []
        for bar in data.get("data", []):
            ts = bar.get("t", 0)
            dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            result.append(CandleData(
                time=dt.isoformat(),
                open=float(bar.get("o", 0)),
                high=float(bar.get("h", 0)),
                low=float(bar.get("l", 0)),
                close=float(bar.get("c", 0)),
                volume=int(bar.get("v", 0)),
                complete=True,
            ))

        if len(result) > count:
            result = result[-count:]

        return result

    async def get_current_price(self, instrument: str) -> PriceData:
        """Get current bid/ask price for an instrument."""
        conid = await self._resolve_conid(instrument)

        data = await self._get("/iserver/marketdata/snapshot", params={
            "conids": str(conid),
            "fields": "84,85,86",
        })

        if isinstance(data, list) and data:
            snap = data[0]
            bid = float(snap.get("84", snap.get("bid", 0)) or 0)
            ask = float(snap.get("85", snap.get("ask", 0)) or 0)
            return PriceData(
                bid=bid,
                ask=ask,
                spread=ask - bid if ask and bid else 0,
                time=datetime.now(timezone.utc).isoformat(),
            )

        raise ValueError(f"No price data for {instrument}")

    async def get_prices_bulk(self, instruments: List[str]) -> Dict[str, PriceData]:
        """Get current prices for multiple instruments."""
        conid_map: Dict[int, str] = {}
        for inst in instruments:
            try:
                conid = await self._resolve_conid(inst)
                conid_map[conid] = inst
            except Exception:
                continue

        if not conid_map:
            return {}

        conids_str = ",".join(str(c) for c in conid_map.keys())
        data = await self._get("/iserver/marketdata/snapshot", params={
            "conids": conids_str,
            "fields": "84,85",
        })

        result: Dict[str, PriceData] = {}
        if isinstance(data, list):
            for snap in data:
                conid = snap.get("conid")
                inst = conid_map.get(conid)
                if not inst:
                    continue
                bid = float(snap.get("84", 0) or 0)
                ask = float(snap.get("85", 0) or 0)
                result[inst] = PriceData(
                    bid=bid, ask=ask,
                    spread=ask - bid if ask and bid else 0,
                    time=datetime.now(timezone.utc).isoformat(),
                )

        return result

    # ── Orders ───────────────────────────────────────────────

    async def place_market_order(
        self,
        instrument: str,
        units: int,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> OrderResult:
        """Place a market order. units > 0 = BUY, units < 0 = SELL."""
        await self._ensure_account_id()
        conid = await self._resolve_conid(instrument)

        side = "BUY" if units > 0 else "SELL"
        quantity = abs(units)

        orders = [{
            "acctId": self._account_id,
            "conid": conid,
            "orderType": "MKT",
            "side": side,
            "quantity": quantity,
            "tif": "GTC",
        }]

        if stop_loss is not None:
            sl_side = "SELL" if side == "BUY" else "BUY"
            orders.append({
                "acctId": self._account_id,
                "conid": conid,
                "orderType": "STP",
                "side": sl_side,
                "quantity": quantity,
                "price": stop_loss,
                "tif": "GTC",
                "isClose": True,
            })

        if take_profit is not None:
            tp_side = "SELL" if side == "BUY" else "BUY"
            orders.append({
                "acctId": self._account_id,
                "conid": conid,
                "orderType": "LMT",
                "side": tp_side,
                "quantity": quantity,
                "price": take_profit,
                "tif": "GTC",
                "isClose": True,
            })

        try:
            data = await self._post(
                f"/iserver/account/{self._account_id}/orders",
                json_data={"orders": orders},
            )

            if isinstance(data, list) and data:
                first = data[0]
                # Auto-confirm if needed
                if first.get("id") and first.get("message"):
                    confirm = await self._post(
                        f"/iserver/reply/{first['id']}",
                        json_data={"confirmed": True},
                    )
                    if isinstance(confirm, list) and confirm:
                        first = confirm[0]

                order_id = first.get("order_id") or first.get("orderId")
                status = first.get("order_status", "")
                logger.info(f"IBKR order: {instrument} {side} {quantity} | ID={order_id}")

                return OrderResult(
                    success=status not in ("Rejected", "Cancelled"),
                    trade_id=str(order_id) if order_id else None,
                    units=units,
                    raw_response=first,
                )

            return OrderResult(success=False, units=units, error=str(data))

        except httpx.HTTPStatusError as e:
            error_msg = e.response.text if hasattr(e, 'response') else str(e)
            logger.error(f"IBKR order failed: {error_msg}")
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
        await self._ensure_account_id()
        conid = await self._resolve_conid(instrument)

        side = "BUY" if units > 0 else "SELL"
        quantity = abs(units)

        try:
            data = await self._post(
                f"/iserver/account/{self._account_id}/orders",
                json_data={"orders": [{
                    "acctId": self._account_id,
                    "conid": conid,
                    "orderType": "LMT",
                    "side": side,
                    "quantity": quantity,
                    "price": price,
                    "tif": "GTC",
                }]},
            )

            if isinstance(data, list) and data:
                first = data[0]
                if first.get("id") and first.get("message"):
                    confirm = await self._post(
                        f"/iserver/reply/{first['id']}",
                        json_data={"confirmed": True},
                    )
                    if isinstance(confirm, list) and confirm:
                        first = confirm[0]

                order_id = first.get("order_id") or first.get("orderId")
                return OrderResult(
                    success=True,
                    trade_id=str(order_id) if order_id else None,
                    units=units,
                    raw_response=first,
                )

            return OrderResult(success=False, units=units, error=str(data))

        except httpx.HTTPStatusError as e:
            return OrderResult(success=False, units=units, error=str(e))

    # ── Trade Management ─────────────────────────────────────

    async def get_open_trades(self) -> List[TradeInfo]:
        """Get all currently open positions."""
        await self._ensure_account_id()

        data = await self._get(f"/portfolio/{self._account_id}/positions/0")

        result: List[TradeInfo] = []
        if not isinstance(data, list):
            return result

        for p in data:
            pos_qty = float(p.get("position", 0))
            if pos_qty == 0:
                continue

            conid = p.get("conid", 0)
            instrument = p.get("contractDesc", str(conid))
            for name, cached in self._conid_cache.items():
                if cached == conid:
                    instrument = name
                    break

            result.append(TradeInfo(
                trade_id=str(conid),
                instrument=instrument,
                direction="BUY" if pos_qty > 0 else "SELL",
                units=int(pos_qty),
                entry_price=float(p.get("avgCost", 0)),
                current_price=float(p.get("mktPrice", 0)),
                unrealized_pnl=float(p.get("unrealizedPnl", 0)),
            ))

        return result

    async def modify_trade_sl(self, trade_id: str, stop_loss: float) -> bool:
        """Modify stop loss on an existing trade.

        IBKR REST API does not support modifying bracket orders on open
        positions in a single call.  The proper approach is to cancel the
        existing STP child order and place a new one, but the /iserver
        endpoints do not expose child-order IDs for positions.

        Until IBKR adds first-class SL modification support, this method
        logs a warning and returns False so callers can handle it
        gracefully (e.g. skip the modification or alert the user).
        """
        logger.warning(
            f"IBKR SL modification is not yet supported via the REST API. "
            f"trade_id={trade_id}, requested_sl={stop_loss}. "
            f"Please adjust the stop-loss manually in Trader Workstation."
        )
        raise NotImplementedError(
            "IBKR REST API does not support SL modification on open positions. "
            "Use Trader Workstation or the Client Portal to adjust stop-loss orders."
        )

    async def modify_trade_tp(self, trade_id: str, take_profit: float) -> bool:
        """Modify take profit on an existing trade.

        IBKR REST API does not support modifying bracket orders on open
        positions in a single call.  The proper approach is to cancel the
        existing LMT child order and place a new one, but the /iserver
        endpoints do not expose child-order IDs for positions.

        Until IBKR adds first-class TP modification support, this method
        logs a warning and returns False so callers can handle it
        gracefully (e.g. skip the modification or alert the user).
        """
        logger.warning(
            f"IBKR TP modification is not yet supported via the REST API. "
            f"trade_id={trade_id}, requested_tp={take_profit}. "
            f"Please adjust the take-profit manually in Trader Workstation."
        )
        raise NotImplementedError(
            "IBKR REST API does not support TP modification on open positions. "
            "Use Trader Workstation or the Client Portal to adjust take-profit orders."
        )

    async def close_trade(self, trade_id: str) -> bool:
        """Close a specific position by placing an opposite market order."""
        await self._ensure_account_id()

        try:
            conid = int(trade_id)
            positions = await self._get(
                f"/portfolio/{self._account_id}/positions/0"
            )

            for p in positions if isinstance(positions, list) else []:
                if p.get("conid") == conid:
                    pos_qty = float(p.get("position", 0))
                    if pos_qty == 0:
                        return True

                    side = "SELL" if pos_qty > 0 else "BUY"
                    data = await self._post(
                        f"/iserver/account/{self._account_id}/orders",
                        json_data={"orders": [{
                            "acctId": self._account_id,
                            "conid": conid,
                            "orderType": "MKT",
                            "side": side,
                            "quantity": abs(pos_qty),
                            "tif": "GTC",
                            "isClose": True,
                        }]},
                    )

                    if isinstance(data, list) and data:
                        first = data[0]
                        if first.get("id") and first.get("message"):
                            await self._post(
                                f"/iserver/reply/{first['id']}",
                                json_data={"confirmed": True},
                            )

                    logger.info(f"IBKR position {conid} close order placed")
                    return True

            return False

        except Exception as e:
            logger.error(f"Failed to close IBKR position {trade_id}: {e}")
            return False

    # ── Instrument Info ──────────────────────────────────────

    async def get_pip_value(self, instrument: str) -> float:
        """Get pip value for an instrument.

        TradingLab units of measure (Lesson 8):
        - Forex: pip = 0.0001 (4th decimal), JPY pairs = 0.01 (2nd decimal)
        - Gold (XAU): pip = 0.1, Silver (XAG): pip = 0.01
        - Indices: point = 1.0
        - Crypto: point = 1.0
        """
        pair = instrument.upper().replace("/", "_")
        if "JPY" in pair:
            return 0.01
        if pair in ("XAU_USD", "GOLD"):
            return 0.1
        if pair in ("XAG_USD", "SILVER"):
            return 0.01
        if any(pair.startswith(c) for c in (
            "BTC", "ETH", "SOL", "ADA", "DOT", "LINK", "AVAX", "MATIC",
            "UNI", "ATOM", "XRP", "DOGE", "LTC", "BNB", "FTM", "ALGO",
            "XLM", "EOS", "XTZ", "VET",
        )):
            return 1.0
        if any(pair.startswith(idx) for idx in (
            "US30", "US2000", "NAS100", "SPX500", "DE30", "FR40",
            "UK100", "JP225", "AU200", "HK33", "CN50",
        )):
            return 1.0
        return 0.0001

    async def get_instrument_info(self, instrument: str) -> Dict[str, Any]:
        """Get instrument details."""
        conid = await self._resolve_conid(instrument)
        try:
            data = await self._get(f"/iserver/contract/{conid}/info")
            return data if isinstance(data, dict) else {"conid": conid}
        except Exception:
            return {"conid": conid, "symbol": instrument}

    # ── Cleanup ──────────────────────────────────────────────

    async def close(self):
        """Close the HTTP client and logout."""
        try:
            await self._client.post(
                f"{self.BASE_URL}/logout",
                headers=self._sign_request("POST", f"{self.BASE_URL}/logout"),
            )
        except Exception:
            pass
        await self._client.aclose()
        logger.info("IBKR client closed")

    def normalize_instrument(self, instrument: str) -> str:
        """Normalize instrument name."""
        return instrument.replace("/", "_").replace(".", "_").upper()
