"""
Atlas - Abstract Broker Interface
Enables multi-broker support (OANDA, TagMarkets, etc.)
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from enum import Enum
from loguru import logger


class BrokerType(Enum):
    IBKR = "ibkr"
    CAPITAL = "capital"
    OANDA = "oanda"
    # Future brokers
    ICMARKETS = "icmarkets"
    PEPPERSTONE = "pepperstone"


@dataclass
class PriceData:
    """Standardized price data across brokers."""
    bid: float
    ask: float
    spread: float
    time: str


@dataclass
class CandleData:
    """Standardized candle data across brokers."""
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    complete: bool = True


@dataclass
class OrderResult:
    """Standardized order result across brokers."""
    success: bool
    trade_id: Optional[str] = None
    fill_price: Optional[float] = None
    units: float = 0
    error: Optional[str] = None
    raw_response: Optional[Dict] = None


@dataclass
class AccountSummary:
    """Standardized account summary across brokers."""
    balance: float
    equity: float
    unrealized_pnl: float
    margin_used: float
    margin_available: float
    open_trade_count: int
    currency: str


@dataclass
class TradeInfo:
    """Standardized open trade info across brokers."""
    trade_id: str
    instrument: str
    direction: str  # "BUY" or "SELL"
    units: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class BaseBroker(ABC):
    """
    Abstract base class for all broker implementations.
    Every broker must implement these methods to be compatible with Atlas.
    """

    def __init__(self, broker_type: BrokerType):
        self.broker_type = broker_type

    # ── Account ──────────────────────────────────────────────────

    @abstractmethod
    async def get_account_summary(self) -> AccountSummary:
        """Get account balance, equity, margin, etc."""
        pass

    @abstractmethod
    async def get_account_balance(self) -> float:
        """Get current account balance."""
        pass

    # ── Market Data ──────────────────────────────────────────────

    @abstractmethod
    async def get_candles(
        self,
        instrument: str,
        granularity: str,
        count: int = 100,
    ) -> List[CandleData]:
        """Get candlestick data for an instrument."""
        pass

    @abstractmethod
    async def get_current_price(self, instrument: str) -> PriceData:
        """Get current bid/ask price for an instrument."""
        pass

    @abstractmethod
    async def get_prices_bulk(self, instruments: List[str]) -> Dict[str, PriceData]:
        """Get current prices for multiple instruments."""
        pass

    # ── Orders ───────────────────────────────────────────────────

    @abstractmethod
    async def place_market_order(
        self,
        instrument: str,
        units: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> OrderResult:
        """Place a market order. units > 0 = BUY, units < 0 = SELL."""
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    async def place_stop_order(
        self,
        instrument: str,
        units: float,
        stop_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> OrderResult:
        """Place a stop order (pending order triggered at stop_price).
        units > 0 = BUY stop, units < 0 = SELL stop."""
        pass

    async def warm_epic_cache(self, instruments: List[str]):
        """Pre-cache instrument metadata. Override for brokers that need it."""
        pass  # Default no-op, Capital.com overrides

    # ── Trade Management ─────────────────────────────────────────

    @abstractmethod
    async def get_open_trades(self) -> List[TradeInfo]:
        """Get all currently open trades."""
        pass

    @abstractmethod
    async def modify_trade_sl(self, trade_id: str, stop_loss: float) -> bool:
        """Move stop loss on an existing trade."""
        pass

    @abstractmethod
    async def modify_trade_tp(self, trade_id: str, take_profit: float) -> bool:
        """Modify take profit on an existing trade."""
        pass

    @abstractmethod
    async def close_trade(self, trade_id: str) -> bool:
        """Close a specific trade."""
        pass

    async def close_trade_partial(self, trade_id: str, percent: int = 50) -> bool:
        """Close a percentage of a trade (partial close). Default implementation closes fully."""
        # Most brokers don't support partial close natively via simple API.
        # Override in broker-specific clients if supported.
        # Default: log warning and skip (full close handled by SL/TP)
        logger.warning(
            f"Partial close not implemented for this broker — "
            f"trade {trade_id} will be managed by trailing SL instead"
        )
        return False

    async def close_all_trades(self) -> int:
        """Close all open trades. Returns count closed."""
        trades = await self.get_open_trades()
        closed = 0
        for trade in trades:
            if await self.close_trade(trade.trade_id):
                closed += 1
        return closed

    # ── Instrument Info ──────────────────────────────────────────

    @abstractmethod
    async def get_pip_value(self, instrument: str) -> float:
        """Get the pip value for an instrument (e.g., 0.0001 for EUR_USD)."""
        pass

    @abstractmethod
    async def get_instrument_info(self, instrument: str) -> Dict[str, Any]:
        """Get instrument details (pip size, min trade size, etc.)."""
        pass

    # ── Cleanup ──────────────────────────────────────────────────

    @abstractmethod
    async def close(self):
        """Close connections and clean up resources."""
        pass

    # ── Helpers ───────────────────────────────────────────────────

    def normalize_instrument(self, instrument: str) -> str:
        """Normalize instrument name for this broker (e.g., EUR/USD vs EUR_USD)."""
        return instrument

    def __repr__(self):
        return f"<{self.__class__.__name__} broker={self.broker_type.value}>"
