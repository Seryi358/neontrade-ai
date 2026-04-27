"""
Tests for news_filter.py — covering critical filtering logic.
Focus: NEWS_WINDOWS per style, is_critical_event, _extract_currencies,
       has_upcoming_news (within/outside danger window, instrument filter,
       style override), should_close_for_news, _style_reason, _generate_known_events,
       get_todays_events, get_news_headlines.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from core.news_filter import (
    NewsFilter, NewsEvent, TradingStyle, NEWS_WINDOWS,
    is_critical_event, CRITICAL_EVENT_KEYWORDS,
)


@pytest.fixture
def nf():
    """Create a NewsFilter with day_trading style."""
    return NewsFilter(trading_style=TradingStyle.DAY_TRADING)


def _event(minutes_from_now=0, currency="USD", impact="high", title="CPI"):
    """Create a NewsEvent at `minutes_from_now` from now."""
    t = datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)
    return NewsEvent(time=t, currency=currency, impact=impact, title=title)


# ──────────────────────────────────────────────────────────────────
# NEWS_WINDOWS constants
# ──────────────────────────────────────────────────────────────────

class TestNewsWindows:
    def test_scalping_window(self):
        """Scalping: 45 min before, 30 min after (mentorship 60/60 reduced to
        compromise — original 60/60 blocked the last hour daily)."""
        assert NEWS_WINDOWS[TradingStyle.SCALPING] == (45, 30)

    def test_day_trading_window(self):
        """Day trading: 30 min before, 15 min after."""
        assert NEWS_WINDOWS[TradingStyle.DAY_TRADING] == (30, 15)

    def test_swing_window(self):
        """Swing: 15 min before, 5 min after."""
        assert NEWS_WINDOWS[TradingStyle.SWING] == (15, 5)


# ──────────────────────────────────────────────────────────────────
# is_critical_event
# ──────────────────────────────────────────────────────────────────

class TestIsCriticalEvent:
    def test_nfp_is_critical(self):
        assert is_critical_event("Non-Farm Payrolls") is True

    def test_fomc_is_critical(self):
        assert is_critical_event("FOMC Rate Decision") is True

    def test_cpi_is_critical(self):
        assert is_critical_event("US CPI inflation report") is True

    def test_ecb_rate_is_critical(self):
        assert is_critical_event("ECB Rate Decision") is True

    def test_gdp_is_critical(self):
        assert is_critical_event("Gross Domestic Product GDP") is True

    def test_powell_is_critical(self):
        assert is_critical_event("Fed Chair Powell Speech") is True

    def test_random_event_not_critical(self):
        assert is_critical_event("PMI Flash Services") is False

    def test_case_insensitive(self):
        assert is_critical_event("non-farm payrolls") is True
        assert is_critical_event("NON-FARM PAYROLLS") is True


# ──────────────────────────────────────────────────────────────────
# _extract_currencies
# ──────────────────────────────────────────────────────────────────

class TestExtractCurrencies:
    def test_underscore_pair(self):
        result = NewsFilter._extract_currencies("EUR_USD")
        assert result == {"EUR", "USD"}

    def test_slash_pair(self):
        result = NewsFilter._extract_currencies("GBP/JPY")
        assert result == {"GBP", "JPY"}

    def test_crypto_pair(self):
        """Crypto pairs like BTC_USD should extract both."""
        result = NewsFilter._extract_currencies("BTC_USD")
        assert result == {"BTC", "USD"}


# ──────────────────────────────────────────────────────────────────
# NewsFilter __init__
# ──────────────────────────────────────────────────────────────────

class TestInit:
    def test_default_day_trading_window(self):
        nf = NewsFilter(trading_style=TradingStyle.DAY_TRADING)
        assert nf.minutes_before == 30
        assert nf.minutes_after == 15

    def test_scalping_window(self):
        nf = NewsFilter(trading_style=TradingStyle.SCALPING)
        assert nf.minutes_before == 45
        assert nf.minutes_after == 30

    def test_custom_override(self):
        """Explicit minutes should override style defaults."""
        nf = NewsFilter(
            trading_style=TradingStyle.SCALPING,
            minutes_before=10,
            minutes_after=5,
        )
        assert nf.minutes_before == 10
        assert nf.minutes_after == 5


# ──────────────────────────────────────────────────────────────────
# has_upcoming_news
# ──────────────────────────────────────────────────────────────────

class TestHasUpcomingNews:
    @pytest.mark.asyncio
    async def test_event_within_window_returns_true(self, nf):
        """High-impact event 15 min away (within 30min day_trading window) should block."""
        nf._cached_events = [_event(minutes_from_now=15)]
        nf._cache_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        has_news, desc = await nf.has_upcoming_news()
        assert has_news is True
        assert "CPI" in desc

    @pytest.mark.asyncio
    async def test_event_outside_window_returns_false(self, nf):
        """High-impact event 60 min away (outside 30min day_trading window) should pass."""
        nf._cached_events = [_event(minutes_from_now=60)]
        nf._cache_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        has_news, desc = await nf.has_upcoming_news()
        assert has_news is False
        assert desc == ""

    @pytest.mark.asyncio
    async def test_low_impact_ignored(self, nf):
        """Low-impact events should not trigger blocking."""
        nf._cached_events = [_event(minutes_from_now=10, impact="low")]
        nf._cache_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        has_news, _ = await nf.has_upcoming_news()
        assert has_news is False

    @pytest.mark.asyncio
    async def test_instrument_filter(self, nf):
        """EUR event should not block GBP_JPY trading."""
        nf._cached_events = [_event(minutes_from_now=10, currency="EUR")]
        nf._cache_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        has_news, _ = await nf.has_upcoming_news(instrument="GBP_JPY")
        assert has_news is False

    @pytest.mark.asyncio
    async def test_instrument_filter_matches(self, nf):
        """EUR event SHOULD block EUR_USD trading."""
        nf._cached_events = [_event(minutes_from_now=10, currency="EUR")]
        nf._cache_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        has_news, _ = await nf.has_upcoming_news(instrument="EUR_USD")
        assert has_news is True

    @pytest.mark.asyncio
    async def test_style_override_scalping(self, nf):
        """Scalping uses same 30min window as day_trading."""
        # Event 20 min away — inside both windows
        nf._cached_events = [_event(minutes_from_now=20)]
        nf._cache_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Default day_trading style — should block (20 < 30)
        has_news_dt, _ = await nf.has_upcoming_news()
        assert has_news_dt is True

        # Override to scalping — should also block (20 < 30)
        has_news_sc, desc = await nf.has_upcoming_news(trading_style=TradingStyle.SCALPING)
        assert has_news_sc is True
        assert "SCALPING" in desc

    @pytest.mark.asyncio
    async def test_event_just_happened(self, nf):
        """Event that just happened (-5 min) should still block within after-window."""
        nf._cached_events = [_event(minutes_from_now=-5)]
        nf._cache_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        has_news, desc = await nf.has_upcoming_news()
        assert has_news is True
        assert "just happened" in desc

    @pytest.mark.asyncio
    async def test_event_long_past_not_blocked(self, nf):
        """Event 60 min ago should NOT block (day_trading after-window is 15min)."""
        nf._cached_events = [_event(minutes_from_now=-60)]
        nf._cache_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        has_news, _ = await nf.has_upcoming_news()
        assert has_news is False

    @pytest.mark.asyncio
    async def test_no_events_returns_false(self, nf):
        """No cached events should return False."""
        nf._cached_events = []
        nf._cache_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        has_news, _ = await nf.has_upcoming_news()
        assert has_news is False


# ──────────────────────────────────────────────────────────────────
# should_close_for_news
# ──────────────────────────────────────────────────────────────────

class TestShouldCloseForNews:
    @pytest.mark.asyncio
    async def test_upcoming_high_impact_triggers(self, nf):
        """High-impact event 10 min away should recommend closing."""
        nf._cached_events = [_event(minutes_from_now=10, currency="USD")]
        nf._cache_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        should_close, reason = await nf.should_close_for_news("EUR_USD")
        assert should_close is True
        assert "CPI" in reason

    @pytest.mark.asyncio
    async def test_unrelated_currency_no_close(self, nf):
        """EUR event should not trigger close for AUD_CAD."""
        nf._cached_events = [_event(minutes_from_now=10, currency="EUR")]
        nf._cache_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        should_close, _ = await nf.should_close_for_news("AUD_CAD")
        assert should_close is False

    @pytest.mark.asyncio
    async def test_past_event_no_close(self, nf):
        """Event that already happened should NOT trigger should_close_for_news.
        (should_close only looks at upcoming: 0 < minutes_until <= win_before)"""
        nf._cached_events = [_event(minutes_from_now=-5, currency="USD")]
        nf._cache_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        should_close, _ = await nf.should_close_for_news("EUR_USD")
        assert should_close is False


# ──────────────────────────────────────────────────────────────────
# _style_reason
# ──────────────────────────────────────────────────────────────────

class TestStyleReason:
    def test_scalping_reason(self):
        event = _event(title="CPI")
        reason = NewsFilter._style_reason(TradingStyle.SCALPING, event)
        assert "Do NOT trade" in reason
        assert "Scalping" in reason

    def test_day_trading_critical_reason(self):
        event = _event(title="Non-Farm Payrolls")
        reason = NewsFilter._style_reason(TradingStyle.DAY_TRADING, event)
        assert "No new positions" in reason
        assert "CRITICAL" in reason

    def test_day_trading_non_critical_reason(self):
        event = _event(title="PMI Services")
        reason = NewsFilter._style_reason(TradingStyle.DAY_TRADING, event)
        assert "No new positions" in reason
        assert "CRITICAL" not in reason

    def test_swing_critical_reason(self):
        event = _event(title="FOMC Rate Decision")
        reason = NewsFilter._style_reason(TradingStyle.SWING, event)
        assert "caution" in reason
        assert "CRITICAL" in reason

    def test_swing_non_critical_reason(self):
        event = _event(title="PMI Manufacturing")
        reason = NewsFilter._style_reason(TradingStyle.SWING, event)
        assert "caution" in reason
        assert "CRITICAL" not in reason


# ──────────────────────────────────────────────────────────────────
# _generate_known_events (fallback)
# ──────────────────────────────────────────────────────────────────

class TestGenerateKnownEvents:
    def test_first_friday_generates_nfp(self, nf):
        """First Friday of the month should generate NFP + Unemployment Rate."""
        # 2025-01-03 is a Friday and day <= 7
        first_friday = datetime(2025, 1, 3, 12, 0, tzinfo=timezone.utc)
        events = nf._generate_known_events(first_friday)
        titles = [e.title for e in events]
        assert any("Non-Farm" in t for t in titles)
        assert any("Unemployment" in t for t in titles)

    def test_second_friday_no_nfp(self, nf):
        """Second Friday should NOT generate NFP."""
        second_friday = datetime(2025, 1, 10, 12, 0, tzinfo=timezone.utc)
        events = nf._generate_known_events(second_friday)
        titles = [e.title for e in events]
        assert not any("Non-Farm" in t for t in titles)

    def test_mid_month_weekday_generates_cpi(self, nf):
        """Weekday 10th-14th should generate CPI."""
        mid_month = datetime(2025, 1, 13, 12, 0, tzinfo=timezone.utc)  # Monday
        events = nf._generate_known_events(mid_month)
        titles = [e.title for e in events]
        assert any("CPI" in t for t in titles)

    def test_weekend_mid_month_no_cpi(self, nf):
        """Weekend mid-month should NOT generate CPI."""
        # 2025-01-11 is Saturday
        weekend_mid = datetime(2025, 1, 11, 12, 0, tzinfo=timezone.utc)
        events = nf._generate_known_events(weekend_mid)
        titles = [e.title for e in events]
        assert not any("CPI" in t for t in titles)

    def test_gdp_last_thursday_of_quarter_month(self, nf):
        """Fallback GDP should align with the last Thursday of quarter months."""
        gdp_day = datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)  # Thursday
        events = nf._generate_known_events(gdp_day)
        titles = [e.title for e in events]
        assert any("GDP" in t for t in titles)

    def test_non_release_quarter_month_weekday_no_gdp(self, nf):
        """Nearby weekdays should not trigger a false GDP block."""
        non_release_day = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)  # Monday
        events = nf._generate_known_events(non_release_day)
        titles = [e.title for e in events]
        assert not any("GDP" in t for t in titles)


# ──────────────────────────────────────────────────────────────────
# get_todays_events
# ──────────────────────────────────────────────────────────────────

class TestGetTodaysEvents:
    @pytest.mark.asyncio
    async def test_returns_serializable_dicts(self, nf):
        """Should return list of dicts with time, currency, impact, title."""
        nf._cached_events = [_event(minutes_from_now=60, title="GDP")]
        nf._cache_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        result = await nf.get_todays_events()
        assert len(result) == 1
        assert "time" in result[0]
        assert result[0]["title"] == "GDP"
        assert result[0]["impact"] == "high"


# ──────────────────────────────────────────────────────────────────
# get_news_headlines
# ──────────────────────────────────────────────────────────────────

class TestGetNewsHeadlines:
    @pytest.mark.asyncio
    async def test_no_api_key_returns_empty(self, nf):
        """Without NewsAPI key, should return empty list."""
        nf.newsapi_key = ""
        result = await nf.get_news_headlines()
        assert result == []

    @pytest.mark.asyncio
    async def test_with_api_key_calls_fetch(self, nf):
        """With API key, should attempt to fetch headlines."""
        nf.newsapi_key = "test-key"
        with patch.object(nf, '_fetch_headlines_from_newsapi', new_callable=AsyncMock, return_value=[{"title": "Test"}]) as mock_fetch:
            result = await nf.get_news_headlines(limit=5)
        mock_fetch.assert_called_once_with(5)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_fetch_failure_returns_empty(self, nf):
        """Fetch failure should return empty list, not raise."""
        nf.newsapi_key = "test-key"
        with patch.object(nf, '_fetch_headlines_from_newsapi', new_callable=AsyncMock, side_effect=Exception("timeout")):
            result = await nf.get_news_headlines()
        assert result == []
