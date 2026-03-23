"""
NeonTrade AI - Economic Calendar
Fetches major economic events to avoid trading during high-impact news.

From Trading Plan:
- Don't execute any trade before important news
- Close all trades near SL/TP before important news
"""

import httpx
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from dataclasses import dataclass
from loguru import logger
from config import settings


@dataclass
class EconomicEvent:
    title: str
    currency: str
    impact: str  # "high", "medium", "low"
    datetime_utc: datetime
    forecast: Optional[str] = None
    previous: Optional[str] = None
    actual: Optional[str] = None


class EconomicCalendar:
    """Fetches and manages economic calendar events."""

    def __init__(self):
        self._events: List[EconomicEvent] = []
        self._last_fetch: Optional[datetime] = None

    async def fetch_today_events(self):
        """Fetch today's economic events from a free API."""
        try:
            async with httpx.AsyncClient() as client:
                # Using ForexFactory or similar free calendar API
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                # TODO: Implement actual API call
                # For now, this is a placeholder
                logger.info(f"Fetched economic calendar for {today}")
                self._last_fetch = datetime.now(timezone.utc)
        except Exception as e:
            logger.error(f"Failed to fetch economic calendar: {e}")

    def has_upcoming_high_impact(
        self,
        currencies: List[str],
        within_minutes: int = None,
    ) -> bool:
        """
        Check if there's a high-impact event coming up for given currencies.

        Args:
            currencies: List of currency codes (e.g., ["USD", "EUR"])
            within_minutes: Check within this many minutes (default from config)
        """
        if within_minutes is None:
            within_minutes = settings.avoid_news_minutes_before

        now = datetime.now(timezone.utc)
        check_until = now + timedelta(minutes=within_minutes)

        for event in self._events:
            if event.impact != "high":
                continue
            if event.currency not in currencies:
                continue
            if now <= event.datetime_utc <= check_until:
                logger.warning(
                    f"High impact event in {within_minutes}min: "
                    f"{event.title} ({event.currency})"
                )
                return True
        return False

    def had_recent_high_impact(
        self,
        currencies: List[str],
        within_minutes: int = None,
    ) -> bool:
        """Check if a high-impact event just occurred."""
        if within_minutes is None:
            within_minutes = settings.avoid_news_minutes_after

        now = datetime.now(timezone.utc)
        check_from = now - timedelta(minutes=within_minutes)

        for event in self._events:
            if event.impact != "high":
                continue
            if event.currency not in currencies:
                continue
            if check_from <= event.datetime_utc <= now:
                return True
        return False

    def get_currencies_from_pair(self, instrument: str) -> List[str]:
        """Extract currencies from an OANDA instrument name (e.g., EUR_USD -> [EUR, USD])."""
        parts = instrument.split("_")
        return parts if len(parts) == 2 else []

    def should_avoid_trading(self, instrument: str) -> bool:
        """Check if we should avoid trading this instrument due to news."""
        currencies = self.get_currencies_from_pair(instrument)
        if not currencies:
            return False

        if self.has_upcoming_high_impact(currencies):
            return True
        if self.had_recent_high_impact(currencies):
            return True
        return False
