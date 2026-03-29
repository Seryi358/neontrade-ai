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


# Finnhub impact mapping: they return 1/2/3, we normalise to our labels.
_FINNHUB_IMPACT_MAP = {
    1: "low",
    2: "medium",
    3: "high",
}


class EconomicCalendar:
    """Fetches and manages economic calendar events."""

    def __init__(self):
        self._events: List[EconomicEvent] = []
        self._last_fetch: Optional[datetime] = None

    async def fetch_today_events(self):
        """Fetch today's economic events from the Finnhub economic calendar.

        Endpoint: GET https://finnhub.io/api/v1/calendar/economic
        Query params: from (YYYY-MM-DD), to (YYYY-MM-DD), token.

        Falls back gracefully if the API key is missing or the request fails.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if not settings.finnhub_api_key:
            logger.warning(
                "FINNHUB_API_KEY not set — economic calendar will be empty. "
                "Set the key in .env to enable news-aware trading."
            )
            self._events = []
            self._last_fetch = datetime.now(timezone.utc)
            return

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://finnhub.io/api/v1/calendar/economic",
                    params={
                        "from": today,
                        "to": today,
                        "token": settings.finnhub_api_key,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            raw_events = data.get("economicCalendar", [])
            parsed: List[EconomicEvent] = []

            for item in raw_events:
                # Each item has: country, event, impact, time (HH:MM),
                # actual, estimate, prev, unit, currency (not always present)
                event_time_str = item.get("time", "")
                event_date_str = item.get("date", today)

                # Build a UTC datetime from date + time
                try:
                    if event_time_str:
                        dt = datetime.strptime(
                            f"{event_date_str} {event_time_str}",
                            "%Y-%m-%d %H:%M:%S",
                        ).replace(tzinfo=timezone.utc)
                    else:
                        dt = datetime.strptime(
                            event_date_str, "%Y-%m-%d"
                        ).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue

                # Finnhub uses country code; map to currency where possible
                currency = item.get("country", "").upper()

                impact_raw = item.get("impact", 1)
                impact = _FINNHUB_IMPACT_MAP.get(impact_raw, "low")

                forecast_val = item.get("estimate")
                previous_val = item.get("prev")
                actual_val = item.get("actual")

                parsed.append(EconomicEvent(
                    title=item.get("event", "Unknown event"),
                    currency=currency,
                    impact=impact,
                    datetime_utc=dt,
                    forecast=str(forecast_val) if forecast_val is not None else None,
                    previous=str(previous_val) if previous_val is not None else None,
                    actual=str(actual_val) if actual_val is not None else None,
                ))

            self._events = parsed
            self._last_fetch = datetime.now(timezone.utc)
            logger.info(
                f"Fetched {len(parsed)} economic calendar events for {today} "
                f"({sum(1 for e in parsed if e.impact == 'high')} high-impact)"
            )

        except httpx.HTTPStatusError as e:
            logger.error(
                f"Finnhub calendar API returned {e.response.status_code}: "
                f"{e.response.text[:200]}"
            )
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
            # Swing trading uses relaxed news buffers (mentorship: "podemos ejecutar")
            if settings.trading_style == "swing":
                within_minutes = settings.avoid_news_minutes_before_swing
            else:
                within_minutes = settings.avoid_news_minutes_before

        # News impact filter (mentorship: Interest Rates, NFP, CPI, GDP are key)
        impact_filter = getattr(settings, 'news_impact_filter', 'high')

        now = datetime.now(timezone.utc)
        check_until = now + timedelta(minutes=within_minutes)

        for event in self._events:
            # Filter by impact level
            if impact_filter == "high" and event.impact != "high":
                continue
            elif impact_filter == "medium" and event.impact not in ("high", "medium"):
                continue
            # "all" = no filter
            if event.currency not in currencies:
                continue
            if now <= event.datetime_utc <= check_until:
                logger.warning(
                    f"{'High' if event.impact == 'high' else event.impact.title()} "
                    f"impact event in {within_minutes}min: "
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
            # Swing trading uses relaxed news buffers
            if settings.trading_style == "swing":
                within_minutes = settings.avoid_news_minutes_after_swing
            else:
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
