"""
NeonTrade AI - OANDA API v20 Client
Handles all communication with OANDA broker.
Implements BaseBroker abstract interface with standardized return types.
"""

import httpx
from typing import Optional, Dict, List, Any
from datetime import datetime
from loguru import logger
from config import settings, get_oanda_url, get_oanda_stream_url

from broker.base import (
    BaseBroker,
    BrokerType,
    PriceData,
    CandleData,
    OrderResult,
    AccountSummary,
    TradeInfo,
)


class OandaClient(BaseBroker):
    """OANDA REST API v20 client for trading operations."""

    def __init__(self):
        super().__init__(BrokerType.OANDA)
        self.api_url = get_oanda_url()
        self.stream_url = get_oanda_stream_url()
        self.account_id = settings.oanda_account_id
        self.headers = {
            "Authorization": f"Bearer {settings.oanda_api_key}",
            "Content-Type": "application/json",
        }
        self._client = httpx.AsyncClient(
            base_url=self.api_url,
            headers=self.headers,
            timeout=30.0,
        )

    # ── Account ──────────────────────────────────────────────────

    async def get_account_summary(self) -> AccountSummary:
        """Get account balance, equity, margin, open positions, etc."""
        resp = await self._client.get(
            f"/v3/accounts/{self.account_id}/summary"
        )
        resp.raise_for_status()
        acct = resp.json()["account"]
        return AccountSummary(
            balance=float(acct["balance"]),
            equity=float(acct.get("NAV", acct["balance"])),
            unrealized_pnl=float(acct.get("unrealizedPL", 0)),
            margin_used=float(acct.get("marginUsed", 0)),
            margin_available=float(acct.get("marginAvailable", 0)),
            open_trade_count=int(acct.get("openTradeCount", 0)),
            currency=acct["currency"],
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
        price: str = "MBA",  # Mid, Bid, Ask
    ) -> List[CandleData]:
        """
        Get candlestick data for an instrument.

        Granularities: S5, S10, S15, S30, M1, M2, M4, M5, M10, M15, M30,
                       H1, H2, H3, H4, H6, H8, H12, D, W, M

        Note: The `price` parameter is OANDA-specific (not in the base
        interface) and defaults to "MBA" (Mid, Bid, Ask).
        """
        resp = await self._client.get(
            f"/v3/instruments/{instrument}/candles",
            params={
                "granularity": granularity,
                "count": count,
                "price": price,
            },
        )
        resp.raise_for_status()
        raw_candles = resp.json()["candles"]

        result: List[CandleData] = []
        for c in raw_candles:
            # Prefer mid prices; fall back to bid then ask
            ohlc = c.get("mid") or c.get("bid") or c.get("ask") or {}
            result.append(CandleData(
                time=c["time"],
                open=float(ohlc.get("o", 0)),
                high=float(ohlc.get("h", 0)),
                low=float(ohlc.get("l", 0)),
                close=float(ohlc.get("c", 0)),
                volume=int(c.get("volume", 0)),
                complete=c.get("complete", True),
            ))
        return result

    async def get_current_price(self, instrument: str) -> PriceData:
        """Get current bid/ask price for an instrument."""
        resp = await self._client.get(
            f"/v3/accounts/{self.account_id}/pricing",
            params={"instruments": instrument},
        )
        resp.raise_for_status()
        price_data = resp.json()["prices"][0]
        bid = float(price_data["bids"][0]["price"])
        ask = float(price_data["asks"][0]["price"])
        return PriceData(
            bid=bid,
            ask=ask,
            spread=ask - bid,
            time=price_data["time"],
        )

    async def get_prices_bulk(self, instruments: List[str]) -> Dict[str, PriceData]:
        """Get current prices for multiple instruments at once."""
        instruments_str = ",".join(instruments)
        resp = await self._client.get(
            f"/v3/accounts/{self.account_id}/pricing",
            params={"instruments": instruments_str},
        )
        resp.raise_for_status()
        result: Dict[str, PriceData] = {}
        for price_data in resp.json()["prices"]:
            bid = float(price_data["bids"][0]["price"])
            ask = float(price_data["asks"][0]["price"])
            result[price_data["instrument"]] = PriceData(
                bid=bid,
                ask=ask,
                spread=ask - bid,
                time=price_data.get("time", ""),
            )
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
        order_data: Dict[str, Any] = {
            "order": {
                "type": "MARKET",
                "instrument": instrument,
                "units": str(units),
                "timeInForce": "FOK",
                "positionFill": "DEFAULT",
            }
        }
        if stop_loss is not None:
            order_data["order"]["stopLossOnFill"] = {
                "price": f"{stop_loss:.5f}",
                "timeInForce": "GTC",
            }
        if take_profit is not None:
            order_data["order"]["takeProfitOnFill"] = {
                "price": f"{take_profit:.5f}",
            }

        try:
            resp = await self._client.post(
                f"/v3/accounts/{self.account_id}/orders",
                json=order_data,
            )
            resp.raise_for_status()
            raw = resp.json()
            logger.info(
                f"Market order placed: {instrument} {units} units | "
                f"SL={stop_loss} TP={take_profit}"
            )
            return self._parse_order_response(raw, units)
        except httpx.HTTPStatusError as e:
            error_msg = str(e)
            try:
                error_msg = e.response.json().get("errorMessage", error_msg)
            except Exception:
                pass
            logger.error(f"Market order failed: {error_msg}")
            return OrderResult(
                success=False,
                units=units,
                error=error_msg,
            )

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
        from datetime import timedelta
        expiry = datetime.utcnow() + timedelta(hours=expiry_hours)

        order_data: Dict[str, Any] = {
            "order": {
                "type": "LIMIT",
                "instrument": instrument,
                "units": str(units),
                "price": f"{price:.5f}",
                "timeInForce": "GTD",
                "gtdTime": expiry.isoformat() + "Z",
                "positionFill": "DEFAULT",
            }
        }
        if stop_loss is not None:
            order_data["order"]["stopLossOnFill"] = {
                "price": f"{stop_loss:.5f}",
                "timeInForce": "GTC",
            }
        if take_profit is not None:
            order_data["order"]["takeProfitOnFill"] = {
                "price": f"{take_profit:.5f}",
            }

        try:
            resp = await self._client.post(
                f"/v3/accounts/{self.account_id}/orders",
                json=order_data,
            )
            resp.raise_for_status()
            raw = resp.json()
            logger.info(
                f"Limit order placed: {instrument} @ {price} | {units} units"
            )
            return self._parse_order_response(raw, units)
        except httpx.HTTPStatusError as e:
            error_msg = str(e)
            try:
                error_msg = e.response.json().get("errorMessage", error_msg)
            except Exception:
                pass
            logger.error(f"Limit order failed: {error_msg}")
            return OrderResult(
                success=False,
                units=units,
                error=error_msg,
            )

    async def place_stop_order(
        self,
        instrument: str,
        units: int,
        price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> OrderResult:
        """Place a stop order (breakout entry). OANDA-specific extension."""
        order_data: Dict[str, Any] = {
            "order": {
                "type": "STOP",
                "instrument": instrument,
                "units": str(units),
                "price": f"{price:.5f}",
                "timeInForce": "GTC",
                "positionFill": "DEFAULT",
            }
        }
        if stop_loss is not None:
            order_data["order"]["stopLossOnFill"] = {
                "price": f"{stop_loss:.5f}",
                "timeInForce": "GTC",
            }
        if take_profit is not None:
            order_data["order"]["takeProfitOnFill"] = {
                "price": f"{take_profit:.5f}",
            }

        try:
            resp = await self._client.post(
                f"/v3/accounts/{self.account_id}/orders",
                json=order_data,
            )
            resp.raise_for_status()
            raw = resp.json()
            return self._parse_order_response(raw, units)
        except httpx.HTTPStatusError as e:
            error_msg = str(e)
            try:
                error_msg = e.response.json().get("errorMessage", error_msg)
            except Exception:
                pass
            logger.error(f"Stop order failed: {error_msg}")
            return OrderResult(
                success=False,
                units=units,
                error=error_msg,
            )

    # ── Trade Management ─────────────────────────────────────────

    async def get_open_trades(self) -> List[TradeInfo]:
        """Get all currently open trades."""
        resp = await self._client.get(
            f"/v3/accounts/{self.account_id}/openTrades"
        )
        resp.raise_for_status()
        raw_trades = resp.json()["trades"]

        result: List[TradeInfo] = []
        for t in raw_trades:
            units = int(t["currentUnits"])
            result.append(TradeInfo(
                trade_id=t["id"],
                instrument=t["instrument"],
                direction="BUY" if units > 0 else "SELL",
                units=units,
                entry_price=float(t["price"]),
                current_price=float(t.get("unrealizedPL", 0)),
                unrealized_pnl=float(t.get("unrealizedPL", 0)),
                stop_loss=float(t["stopLossOrder"]["price"])
                    if t.get("stopLossOrder") else None,
                take_profit=float(t["takeProfitOrder"]["price"])
                    if t.get("takeProfitOrder") else None,
            ))
        return result

    async def get_open_positions(self) -> List[Dict]:
        """Get all open positions. OANDA-specific (not in base interface)."""
        resp = await self._client.get(
            f"/v3/accounts/{self.account_id}/openPositions"
        )
        resp.raise_for_status()
        return resp.json()["positions"]

    async def modify_trade_sl(self, trade_id: str, stop_loss: float) -> bool:
        """Move stop loss on an existing trade (for BE, trailing, etc.)."""
        try:
            resp = await self._client.put(
                f"/v3/accounts/{self.account_id}/trades/{trade_id}/orders",
                json={
                    "stopLoss": {
                        "price": f"{stop_loss:.5f}",
                        "timeInForce": "GTC",
                    }
                },
            )
            resp.raise_for_status()
            logger.info(f"Trade {trade_id} SL moved to {stop_loss}")
            return True
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to modify SL for trade {trade_id}: {e}")
            return False

    async def modify_trade_tp(self, trade_id: str, take_profit: float) -> bool:
        """Modify take profit on an existing trade."""
        try:
            resp = await self._client.put(
                f"/v3/accounts/{self.account_id}/trades/{trade_id}/orders",
                json={
                    "takeProfit": {
                        "price": f"{take_profit:.5f}",
                    }
                },
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to modify TP for trade {trade_id}: {e}")
            return False

    async def close_trade(self, trade_id: str) -> bool:
        """Close a specific trade."""
        try:
            resp = await self._client.put(
                f"/v3/accounts/{self.account_id}/trades/{trade_id}/close",
            )
            resp.raise_for_status()
            logger.info(f"Trade {trade_id} closed")
            return True
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to close trade {trade_id}: {e}")
            return False

    # Note: close_all_trades() is inherited from BaseBroker.
    # It iterates get_open_trades() and calls close_trade() for each,
    # returning the count of successfully closed trades (int).

    # ── Instrument Info ──────────────────────────────────────────

    async def get_instrument_info(self, instrument: str) -> Dict[str, Any]:
        """Get instrument details (pip size, min trade size, etc.)."""
        resp = await self._client.get(
            f"/v3/accounts/{self.account_id}/instruments",
            params={"instruments": instrument},
        )
        resp.raise_for_status()
        return resp.json()["instruments"][0]

    async def get_pip_value(self, instrument: str) -> float:
        """Get the pip location for an instrument (e.g., 0.0001 for EUR_USD)."""
        info = await self.get_instrument_info(instrument)
        return 10 ** int(info["pipLocation"])

    # ── Cleanup ──────────────────────────────────────────────────

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()

    # ── Helpers (OANDA-specific) ─────────────────────────────────

    def normalize_instrument(self, instrument: str) -> str:
        """OANDA uses underscore-separated instrument names (EUR_USD)."""
        return instrument.replace("/", "_")

    def _parse_order_response(self, raw: Dict, units: int) -> OrderResult:
        """Parse OANDA order response into a standardized OrderResult."""
        # Successful fill
        fill = raw.get("orderFillTransaction")
        if fill:
            trade_id = None
            opened = fill.get("tradeOpened")
            if opened:
                trade_id = opened.get("tradeID")
            return OrderResult(
                success=True,
                trade_id=trade_id,
                fill_price=float(fill.get("price", 0)),
                units=units,
                error=None,
                raw_response=raw,
            )

        # Order created but not yet filled (limit / stop orders)
        order_create = raw.get("orderCreateTransaction")
        if order_create:
            return OrderResult(
                success=True,
                trade_id=None,
                fill_price=None,
                units=units,
                error=None,
                raw_response=raw,
            )

        # Cancelled / rejected
        cancel = raw.get("orderCancelTransaction")
        reason = cancel.get("reason", "UNKNOWN") if cancel else "UNKNOWN"
        return OrderResult(
            success=False,
            trade_id=None,
            fill_price=None,
            units=units,
            error=f"Order rejected: {reason}",
            raw_response=raw,
        )
