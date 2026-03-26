"""
NeonTrade AI - Economic Calendar / News Filter
Checks for upcoming high-impact economic events to avoid trading during news.

Data sources (in priority order):
  1. FairEconomy  - Free ForexFactory calendar mirror (primary, no API key needed)
  2. Trading Economics - Free calendar scraping (secondary fallback)
  3. Known recurring events - Hard-coded NFP/CPI schedule (final fallback)

Supplementary:
  - NewsAPI.org - Forex news headlines for the UI (does NOT block trades)

Rules from Trading Plan:
- Don't trade 30 min before major news
- Don't trade 15 min after major news
"""

import httpx
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple
from dataclasses import dataclass
from loguru import logger


@dataclass
class NewsEvent:
    """An economic news event."""
    time: datetime
    currency: str
    impact: str  # "high", "medium", "low"
    title: str


# Known recurring high-impact events and their typical UTC hours.
# These happen on roughly predictable schedules.
RECURRING_HIGH_IMPACT = [
    # US events (usually 13:30 or 15:00 UTC)
    {"currency": "USD", "title": "Non-Farm Payrolls", "day": "first_friday", "hour": 13, "minute": 30},
    {"currency": "USD", "title": "CPI", "day": "mid_month", "hour": 13, "minute": 30},
    {"currency": "USD", "title": "FOMC Rate Decision", "day": "fomc", "hour": 19, "minute": 0},
    {"currency": "USD", "title": "Fed Chair Press Conference", "day": "fomc", "hour": 19, "minute": 30},
    # EUR events
    {"currency": "EUR", "title": "ECB Rate Decision", "day": "ecb", "hour": 13, "minute": 15},
    # GBP events
    {"currency": "GBP", "title": "BOE Rate Decision", "day": "boe", "hour": 12, "minute": 0},
]

# Currencies in our watchlist
WATCHED_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF"}

# FairEconomy endpoints (ForexFactory mirror — free, no API key)
_FAIRECONOMY_THIS_WEEK = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
_FAIRECONOMY_NEXT_WEEK = "https://nfs.faireconomy.media/ff_calendar_nextweek.json"

# FairEconomy impact values
_FE_HIGH_IMPACT = {"High"}
_FE_MEDIUM_IMPACT = {"Medium"}


class NewsFilter:
    """Checks for upcoming high-impact news events."""

    def __init__(
        self,
        minutes_before: int = 30,
        minutes_after: int = 15,
        finnhub_key: str = "",
        newsapi_key: str = "",
    ):
        self.minutes_before = minutes_before
        self.minutes_after = minutes_after
        self.newsapi_key = newsapi_key
        self._cached_events: List[NewsEvent] = []
        self._cache_date: Optional[str] = None
        self._http = httpx.AsyncClient(timeout=10.0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def has_upcoming_news(self, instrument: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """
        Check if there's a high-impact news event near the current time.
        Returns (has_news, event_description).
        """
        now = datetime.now(timezone.utc)

        # Refresh calendar cache once per day
        today = now.strftime("%Y-%m-%d")
        if self._cache_date != today:
            await self._refresh_calendar(now)
            self._cache_date = today

        # Filter by instrument currencies if provided
        currencies = WATCHED_CURRENCIES
        if instrument:
            parts = instrument.replace("/", "_").split("_")
            currencies = set(p.upper() for p in parts if len(p) == 3)

        # Check if any high-impact event is within our window
        for event in self._cached_events:
            if event.impact != "high":
                continue

            if currencies and event.currency not in currencies:
                continue

            time_until = (event.time - now).total_seconds() / 60  # minutes
            time_since = (now - event.time).total_seconds() / 60

            # Within the danger zone?
            if -self.minutes_after <= time_until <= self.minutes_before:
                desc = f"{event.currency} {event.title} @ {event.time.strftime('%H:%M')} UTC"
                return True, desc

            if 0 <= time_since <= self.minutes_after:
                desc = f"{event.currency} {event.title} (just happened @ {event.time.strftime('%H:%M')} UTC)"
                return True, desc

        return False, None

    async def should_close_for_news(self, instrument: str) -> Tuple[bool, str]:
        """Check if an existing position on this instrument should be closed due to upcoming news.
        Trading Plan: 'Cerrar trades antes de noticias importantes'
        Only triggers for HIGH impact events within the danger window."""
        now = datetime.now(timezone.utc)

        # Refresh calendar cache once per day
        today = now.strftime("%Y-%m-%d")
        if self._cache_date != today:
            await self._refresh_calendar(now)
            self._cache_date = today

        currencies = self._extract_currencies(instrument)

        for event in self._cached_events:
            if event.impact != "high":
                continue
            # Check if this event affects the instrument
            if event.currency.upper() not in currencies:
                continue
            minutes_until = (event.time - now).total_seconds() / 60
            if 0 < minutes_until <= self.minutes_before:
                return True, f"High-impact news: {event.title} in {int(minutes_until)}min"

        return False, ""

    @staticmethod
    def _extract_currencies(instrument: str) -> set:
        """Extract the two currency codes from a pair name like 'EUR_USD' -> {'EUR', 'USD'}."""
        parts = instrument.replace("/", "_").split("_")
        return {p.upper() for p in parts if len(p) == 3}

    async def get_todays_events(self) -> List[dict]:
        """Get all events for today (for the frontend calendar view)."""
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")
        if self._cache_date != today:
            await self._refresh_calendar(now)
            self._cache_date = today

        return [
            {
                "time": e.time.isoformat(),
                "currency": e.currency,
                "impact": e.impact,
                "title": e.title,
            }
            for e in self._cached_events
        ]

    async def get_news_headlines(self, limit: int = 10) -> List[dict]:
        """
        Get recent forex news headlines from NewsAPI.org.

        This is supplementary information for the UI -- it does NOT affect
        trade blocking decisions.

        Returns a list of dicts:
            [{"title": ..., "source": ..., "url": ..., "published": ..., "summary": ...}, ...]
        """
        if not self.newsapi_key:
            logger.debug("NewsAPI key not configured -- skipping headlines fetch")
            return []

        try:
            return await self._fetch_headlines_from_newsapi(limit)
        except Exception as e:
            logger.warning(f"Failed to fetch news headlines: {e}")
            return []

    async def close(self):
        """Close HTTP client."""
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Calendar refresh (tries sources in priority order)
    # ------------------------------------------------------------------

    async def _refresh_calendar(self, now: datetime):
        """Fetch today's economic calendar. Tries sources in priority order."""
        self._cached_events = []

        # 1) PRIMARY: FairEconomy (ForexFactory mirror — free, no key)
        try:
            events = await self._fetch_from_faireconomy(now)
            if events:
                self._cached_events = events
                logger.info(f"Loaded {len(events)} news events from FairEconomy for today")
                return
        except Exception as e:
            logger.debug(f"FairEconomy calendar fetch failed: {e}")

        # 2) SECONDARY: Trading Economics
        try:
            events = await self._fetch_from_trading_economics(now)
            if events:
                self._cached_events = events
                logger.info(f"Loaded {len(events)} news events from Trading Economics for today")
                return
        except Exception as e:
            logger.debug(f"Trading Economics calendar fetch failed: {e}")

        # 3) FINAL FALLBACK: known recurring high-impact schedule
        self._cached_events = self._generate_known_events(now)
        logger.info(f"Using {len(self._cached_events)} known recurring events as fallback")

    # ------------------------------------------------------------------
    # Source 1: FairEconomy (primary — free, no API key)
    # ------------------------------------------------------------------

    async def _fetch_from_faireconomy(self, now: datetime) -> List[NewsEvent]:
        """
        Fetch economic calendar from FairEconomy (ForexFactory mirror).

        Endpoints (no API key required):
          - This week: https://nfs.faireconomy.media/ff_calendar_thisweek.json
          - Next week: https://nfs.faireconomy.media/ff_calendar_nextweek.json

        Returns events for today only (filtered from the weekly data).
        """
        events: List[NewsEvent] = []
        today = now.date()

        # Fetch this week's calendar
        urls = [_FAIRECONOMY_THIS_WEEK]
        # If it's Friday or later, also fetch next week for look-ahead
        if now.weekday() >= 4:
            urls.append(_FAIRECONOMY_NEXT_WEEK)

        for url in urls:
            try:
                resp = await self._http.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; NeonTradeAI/2.0)"},
                )
                if resp.status_code != 200:
                    logger.debug(f"FairEconomy returned status {resp.status_code} for {url}")
                    continue

                data = resp.json()

                for item in data:
                    # Filter by impact: only high and medium
                    raw_impact = item.get("impact", "Low")
                    if raw_impact in _FE_HIGH_IMPACT:
                        impact = "high"
                    elif raw_impact in _FE_MEDIUM_IMPACT:
                        impact = "medium"
                    else:
                        continue

                    # Filter by watched currencies
                    currency = item.get("country", "").upper()
                    if currency not in WATCHED_CURRENCIES:
                        continue

                    # Parse event time (ISO-8601 with timezone offset)
                    date_str = item.get("date", "")
                    if not date_str:
                        continue

                    try:
                        event_time = datetime.fromisoformat(date_str)
                        # Ensure timezone-aware (convert to UTC)
                        if event_time.tzinfo is None:
                            event_time = event_time.replace(tzinfo=timezone.utc)
                        else:
                            event_time = event_time.astimezone(timezone.utc)
                    except (ValueError, AttributeError):
                        continue

                    # Only keep today's events
                    if event_time.date() != today:
                        continue

                    events.append(NewsEvent(
                        time=event_time,
                        currency=currency,
                        impact=impact,
                        title=item.get("title", "Unknown"),
                    ))

            except Exception as e:
                logger.debug(f"FairEconomy fetch error for {url}: {e}")
                continue

        return events

    # ------------------------------------------------------------------
    # Source 2: Trading Economics (secondary fallback)
    # ------------------------------------------------------------------

    async def _fetch_from_trading_economics(self, now: datetime) -> List[NewsEvent]:
        """Fetch from Trading Economics free calendar API."""
        events: List[NewsEvent] = []
        today = now.strftime("%Y-%m-%d")

        try:
            resp = await self._http.get(
                "https://economic-calendar.tradingeconomics.com/api/calendar",
                params={"day": today},
                headers={"User-Agent": "NeonTradeAI/1.0"},
            )
            if resp.status_code == 200:
                data = resp.json()
                for item in data:
                    importance = item.get("importance", 0)
                    if importance < 2:  # Only medium and high
                        continue

                    currency = item.get("currency", "").upper()
                    if currency not in WATCHED_CURRENCIES:
                        continue

                    event_time_str = item.get("date", "")
                    try:
                        event_time = datetime.fromisoformat(event_time_str.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        continue

                    events.append(NewsEvent(
                        time=event_time,
                        currency=currency,
                        impact="high" if importance >= 3 else "medium",
                        title=item.get("event", "Unknown"),
                    ))
        except Exception:
            pass

        return events

    # ------------------------------------------------------------------
    # Source 3: Known recurring events (final fallback)
    # ------------------------------------------------------------------

    def _generate_known_events(self, now: datetime) -> List[NewsEvent]:
        """Generate events from known recurring schedule as fallback."""
        events = []
        today = now.date()
        weekday = now.weekday()  # 0=Monday

        # NFP: First Friday of the month
        if weekday == 4 and today.day <= 7:
            events.append(NewsEvent(
                time=datetime(today.year, today.month, today.day, 13, 30, tzinfo=timezone.utc),
                currency="USD",
                impact="high",
                title="Non-Farm Payrolls (estimated)",
            ))

        # US CPI: Usually around 10th-14th of month
        if 10 <= today.day <= 14 and weekday < 5:
            events.append(NewsEvent(
                time=datetime(today.year, today.month, today.day, 13, 30, tzinfo=timezone.utc),
                currency="USD",
                impact="high",
                title="CPI (estimated window)",
            ))

        return events

    # ------------------------------------------------------------------
    # NewsAPI.org headlines (supplementary)
    # ------------------------------------------------------------------

    async def _fetch_headlines_from_newsapi(self, limit: int) -> List[dict]:
        """
        Fetch recent forex news headlines from NewsAPI.org.

        Endpoint: GET https://newsapi.org/v2/everything
        Requires a free API key from newsapi.org.
        """
        resp = await self._http.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": "forex trading",
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": limit,
                "apiKey": self.newsapi_key,
            },
        )

        if resp.status_code != 200:
            logger.debug(f"NewsAPI returned status {resp.status_code}")
            return []

        data = resp.json()
        articles = data.get("articles", [])

        headlines: List[dict] = []
        for article in articles[:limit]:
            headlines.append({
                "title": article.get("title", ""),
                "source": article.get("source", {}).get("name", "Unknown"),
                "url": article.get("url", ""),
                "published": article.get("publishedAt", ""),
                "summary": article.get("description", "") or "",
            })

        return headlines
