"""
NeonTrade AI - Economic Calendar / News Filter
Checks for upcoming high/medium-impact economic events to avoid trading during news.

Data sources (in priority order):
  1. FairEconomy  - Free ForexFactory calendar mirror (primary, no API key needed)
  2. Trading Economics - Free calendar scraping (secondary fallback)
  3. Known recurring events - Hard-coded NFP/CPI schedule (final fallback)

Supplementary:
  - NewsAPI.org - Forex news headlines for the UI (does NOT block trades)

Rules from Mentorship (style-dependent):
- SCALPING:    Do NOT trade during news. Period. Spread and slippage make it
               impossible. Block at least 60 min before and 60 min after.
- DAY TRADING: Do not open new positions 30 min before / 15 min after.
               Existing positions should be moved to break-even.
- SWING:       Exercise extreme caution, but can potentially execute.
               15 min before / 5 min after.

Most Important Events (highest impact):
- Interest Rates / FOMC / ECB / BOE decisions (8 times/year)
- Unemployment Rate (monthly)
- GDP (quarterly)
- CPI / Inflation (monthly)
- Non-Farm Payrolls (monthly)
"""

import httpx
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from loguru import logger


class TradingStyle(str, Enum):
    """Trading style — determines news-window strictness."""
    SCALPING = "scalping"
    DAY_TRADING = "day_trading"
    SWING = "swing"


# Per-style danger windows (minutes_before, minutes_after)
NEWS_WINDOWS: Dict[TradingStyle, Tuple[int, int]] = {
    # Mentorship: "Do NOT trade during news. Period." for scalping
    TradingStyle.SCALPING: (60, 60),
    # Mentorship: Don't open new positions; move existing to break-even
    TradingStyle.DAY_TRADING: (30, 15),
    # Mentorship: Exercise extreme caution but can potentially execute
    TradingStyle.SWING: (15, 5),
}


@dataclass
class NewsEvent:
    """An economic news event."""
    time: datetime
    currency: str
    impact: str  # "high", "medium", "low"
    title: str


# Titles that mark the MOST important events from the mentorship.
# These are the ones that move the market hardest and should never be ignored.
CRITICAL_EVENT_KEYWORDS: List[str] = [
    "interest rate",
    "rate decision",
    "fomc",
    "ecb rate",
    "boe rate",
    "unemployment rate",
    "gdp",
    "cpi",
    "inflation",
    "non-farm payrolls",
    "nonfarm payrolls",
    "non farm payrolls",
    "nfp",
    # Fed / central bank speeches — mentorship: these move markets significantly
    "fed chair",
    "powell",
    "fed speech",
    "fomc press conference",
    "ecb press conference",
    "boe press conference",
]


def is_critical_event(title: str) -> bool:
    """Return True if *title* matches one of the most-important mentorship events."""
    lower = title.lower()
    return any(kw in lower for kw in CRITICAL_EVENT_KEYWORDS)


# Known recurring high-impact events and their typical UTC hours.
# These happen on roughly predictable schedules.
RECURRING_HIGH_IMPACT = [
    # US events (usually 13:30 or 15:00 UTC)
    {"currency": "USD", "title": "Non-Farm Payrolls", "day": "first_friday", "hour": 13, "minute": 30},
    {"currency": "USD", "title": "CPI", "day": "mid_month", "hour": 13, "minute": 30},
    {"currency": "USD", "title": "FOMC Rate Decision", "day": "fomc", "hour": 19, "minute": 0},
    {"currency": "USD", "title": "Fed Chair Press Conference", "day": "fomc", "hour": 19, "minute": 30},
    {"currency": "USD", "title": "Unemployment Rate", "day": "first_friday", "hour": 13, "minute": 30},
    {"currency": "USD", "title": "GDP", "day": "gdp", "hour": 13, "minute": 30},
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
    """Checks for upcoming high-impact news events.

    The danger window around news is determined by the *trading_style*:
      - SCALPING:    60 min before / 60 min after  (spread + slippage = impossible)
      - DAY_TRADING: 30 min before / 15 min after  (no new positions; move to BE)
      - SWING:       15 min before /  5 min after   (extreme caution)

    You can also override the window via explicit *minutes_before* / *minutes_after*
    parameters, but the recommended approach is to pass a *trading_style*.
    """

    def __init__(
        self,
        trading_style: TradingStyle = TradingStyle.DAY_TRADING,
        minutes_before: Optional[int] = None,
        minutes_after: Optional[int] = None,
        finnhub_key: str = "",
        newsapi_key: str = "",
    ):
        self.trading_style = trading_style

        # Use the style-specific window unless explicitly overridden
        default_before, default_after = NEWS_WINDOWS[trading_style]
        self.minutes_before = minutes_before if minutes_before is not None else default_before
        self.minutes_after = minutes_after if minutes_after is not None else default_after

        self.newsapi_key = newsapi_key
        self._cached_events: List[NewsEvent] = []
        self._cache_date: Optional[str] = None
        self._http = httpx.AsyncClient(timeout=10.0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def has_upcoming_news(
        self,
        instrument: Optional[str] = None,
        trading_style: Optional[TradingStyle] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if there's a high-impact news event near the current time.

        Parameters
        ----------
        instrument : str, optional
            Currency pair (e.g. "EUR_USD").  When provided, only events
            affecting those currencies are considered.
        trading_style : TradingStyle, optional
            Override the instance-level style for this single check.
            Useful when the same NewsFilter serves multiple strategies.

        Returns (has_news, event_description).
        """
        now = datetime.now(timezone.utc)

        # Refresh calendar cache once per day
        today = now.strftime("%Y-%m-%d")
        if self._cache_date != today:
            await self._refresh_calendar(now)
            self._cache_date = today

        # Resolve which window to use.
        # If the caller passes an explicit style override, use its default window.
        # Otherwise, use the instance's configured windows (which may be custom
        # overrides from the constructor, not just the style defaults).
        style = trading_style or self.trading_style
        if trading_style is not None:
            win_before, win_after = NEWS_WINDOWS[style]
        else:
            win_before, win_after = self.minutes_before, self.minutes_after

        # Filter by instrument currencies if provided
        currencies = WATCHED_CURRENCIES
        if instrument:
            parts = instrument.replace("/", "_").split("_")
            currencies = set(p.upper() for p in parts if len(p) == 3)

        # Check if any high/medium-impact event is within our window
        # Mentorship: filter "dos y de tres" (2-star and 3-star = medium + high)
        for event in self._cached_events:
            if event.impact not in ("high", "medium"):
                continue

            if currencies and event.currency not in currencies:
                continue

            time_until = (event.time - now).total_seconds() / 60  # minutes
            time_since = (now - event.time).total_seconds() / 60

            # Within the danger zone (before or after the event)?
            if -win_after <= time_until <= win_before:
                # Distinguish "upcoming" vs "just happened" for clearer messaging
                if time_until >= 0:
                    timing = f"in {time_until:.0f}min @ {event.time.strftime('%H:%M')} UTC"
                else:
                    timing = f"just happened @ {event.time.strftime('%H:%M')} UTC ({time_since:.0f}min ago)"
                reason = self._style_reason(style, event)
                desc = (
                    f"[{style.value.upper()}] {event.currency} {event.title} "
                    f"({timing}) — {reason}"
                )
                return True, desc

        return False, None

    # ------------------------------------------------------------------
    # Style-specific advice string
    # ------------------------------------------------------------------

    @staticmethod
    def _style_reason(style: TradingStyle, event: NewsEvent) -> str:
        """Return a human-readable reason why the filter blocked, per style."""
        critical = is_critical_event(event.title)
        if style == TradingStyle.SCALPING:
            return (
                "Do NOT trade during news (spread + slippage). "
                "Scalping is blocked."
            )
        elif style == TradingStyle.DAY_TRADING:
            extra = " This is a CRITICAL event." if critical else ""
            return (
                "No new positions. Move existing trades to break-even."
                + extra
            )
        else:  # SWING
            extra = " This is a CRITICAL event — consider staying out." if critical else ""
            return "Exercise extreme caution." + extra

    async def should_close_for_news(
        self,
        instrument: str,
        trading_style: Optional[TradingStyle] = None,
    ) -> Tuple[bool, str]:
        """Check if an existing position on this instrument should be closed
        (or moved to break-even) due to upcoming news.

        Trading Plan: 'Cerrar trades antes de noticias importantes'
        Only triggers for HIGH impact events within the danger window.

        For SCALPING the recommendation is always to close.
        For DAY_TRADING the recommendation is to move to break-even.
        For SWING positions can generally stay open with caution.
        """
        now = datetime.now(timezone.utc)

        # Refresh calendar cache once per day
        today = now.strftime("%Y-%m-%d")
        if self._cache_date != today:
            await self._refresh_calendar(now)
            self._cache_date = today

        style = trading_style or self.trading_style
        if trading_style is not None:
            win_before, _win_after = NEWS_WINDOWS[style]
        else:
            win_before, _win_after = self.minutes_before, self.minutes_after

        currencies = self._extract_currencies(instrument)

        for event in self._cached_events:
            if event.impact not in ("high", "medium"):
                continue
            # Check if this event affects the instrument
            if event.currency.upper() not in currencies:
                continue
            minutes_until = (event.time - now).total_seconds() / 60
            if 0 < minutes_until <= win_before:
                reason = self._style_reason(style, event)
                impact_label = event.impact.title()
                return True, (
                    f"{impact_label}-impact news: {event.title} in {int(minutes_until)}min — {reason}"
                )

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
            logger.warning(f"FairEconomy calendar fetch failed: {e}")

        # 2) SECONDARY: Trading Economics
        try:
            events = await self._fetch_from_trading_economics(now)
            if events:
                self._cached_events = events
                logger.info(f"Loaded {len(events)} news events from Trading Economics for today")
                return
        except Exception as e:
            logger.warning(f"Trading Economics calendar fetch failed: {e}")

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
                logger.warning(f"FairEconomy fetch error for {url}: {e}")
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
                        # Ensure timezone-aware (same as FairEconomy handler)
                        if event_time.tzinfo is None:
                            event_time = event_time.replace(tzinfo=timezone.utc)
                        else:
                            event_time = event_time.astimezone(timezone.utc)
                    except (ValueError, AttributeError):
                        continue

                    events.append(NewsEvent(
                        time=event_time,
                        currency=currency,
                        impact="high" if importance >= 3 else "medium",
                        title=item.get("event", "Unknown"),
                    ))
        except Exception as e:
            logger.warning(f"Failed to fetch news from external source: {e}")

        return events

    # ------------------------------------------------------------------
    # Source 3: Known recurring events (final fallback)
    # ------------------------------------------------------------------

    def _generate_known_events(self, now: datetime) -> List[NewsEvent]:
        """Generate events from known recurring schedule as fallback.

        Covers the five most-important mentorship events:
          - Non-Farm Payrolls (first Friday)
          - Unemployment Rate  (first Friday, same release as NFP)
          - CPI / Inflation    (around 10th-14th)
          - GDP                (around 25th-28th, quarterly)
          - Interest Rate decisions are covered via FOMC/ECB/BOE entries
            in RECURRING_HIGH_IMPACT but also generated here for safety.
        """
        events = []
        today = now.date()
        weekday = now.weekday()  # 0=Monday

        # NFP + Unemployment Rate: First Friday of the month
        if weekday == 4 and today.day <= 7:
            events.append(NewsEvent(
                time=datetime(today.year, today.month, today.day, 13, 30, tzinfo=timezone.utc),
                currency="USD",
                impact="high",
                title="Non-Farm Payrolls (estimated)",
            ))
            events.append(NewsEvent(
                time=datetime(today.year, today.month, today.day, 13, 30, tzinfo=timezone.utc),
                currency="USD",
                impact="high",
                title="Unemployment Rate (estimated)",
            ))

        # US CPI / Inflation: Usually around 10th-14th of month
        if 10 <= today.day <= 14 and weekday < 5:
            events.append(NewsEvent(
                time=datetime(today.year, today.month, today.day, 13, 30, tzinfo=timezone.utc),
                currency="USD",
                impact="high",
                title="CPI / Inflation (estimated window)",
            ))

        # US GDP: Quarterly, typically released around the 25th-28th
        if 25 <= today.day <= 28 and weekday < 5 and today.month in (1, 4, 7, 10):
            events.append(NewsEvent(
                time=datetime(today.year, today.month, today.day, 13, 30, tzinfo=timezone.utc),
                currency="USD",
                impact="high",
                title="GDP (estimated quarterly window)",
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
