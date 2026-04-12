"""
Tests for alerts.py — covering text helpers, masking, AlertConfig,
AlertManager config/dispatch, Discord colours, channel sends, and
Gmail OAuth2 token caching.
"""

import asyncio
import time
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from core.alerts import (
    _mask,
    _strip_emoji_tags,
    _html_to_telegram,
    _html_to_discord_md,
    _html_to_plain,
    _build_email_html,
    _SENSITIVE_FIELDS,
    AlertChannel,
    AlertConfig,
    AlertManager,
    DISCORD_EMBED_COLOUR,
)


# ──────────────────────────────────────────────────────────────────
# _mask
# ──────────────────────────────────────────────────────────────────

class TestMask:
    def test_empty_string(self):
        assert _mask("") == ""

    def test_short_value(self):
        assert _mask("abc") == "****"

    def test_exactly_4_chars(self):
        assert _mask("abcd") == "****"

    def test_longer_value(self):
        result = _mask("my_secret_key_1234")
        assert result.endswith("1234")
        assert result.startswith("*")
        assert len(result) == len("my_secret_key_1234")

    def test_5_char_value(self):
        result = _mask("12345")
        assert result == "*2345"  # 1 star + last 4


# ──────────────────────────────────────────────────────────────────
# _strip_emoji_tags
# ──────────────────────────────────────────────────────────────────

class TestStripEmojiTags:
    def test_returns_text_unchanged(self):
        assert _strip_emoji_tags("Hello World") == "Hello World"

    def test_emojis_preserved(self):
        text = "\U0001F4C8 Daily Summary"
        assert _strip_emoji_tags(text) == text


# ──────────────────────────────────────────────────────────────────
# _html_to_telegram
# ──────────────────────────────────────────────────────────────────

class TestHtmlToTelegram:
    def test_strips_span_tags(self):
        html = '<span style="color:red;">Hello</span>'
        result = _html_to_telegram(html)
        assert "<span" not in result
        assert "</span>" not in result
        assert "Hello" in result

    def test_preserves_bold_tags(self):
        html = '<b>Title</b> text'
        result = _html_to_telegram(html)
        assert "<b>" in result
        assert "Title" in result

    def test_complex_html(self):
        html = (
            '<span style="color:#5df4fe;font-size:18px;">EUR_USD</span>\n'
            '<span style="color:#28c775;">BUY</span>'
        )
        result = _html_to_telegram(html)
        assert "EUR_USD" in result
        assert "BUY" in result
        assert "<span" not in result


# ──────────────────────────────────────────────────────────────────
# _html_to_discord_md
# ──────────────────────────────────────────────────────────────────

class TestHtmlToDiscordMd:
    def test_bold_conversion(self):
        assert _html_to_discord_md("<b>Hello</b>") == "**Hello**"

    def test_italic_conversion(self):
        assert _html_to_discord_md("<i>Hello</i>") == "*Hello*"

    def test_code_conversion(self):
        assert _html_to_discord_md("<code>x</code>") == "`x`"

    def test_br_conversion(self):
        assert _html_to_discord_md("line1<br>line2") == "line1\nline2"
        assert _html_to_discord_md("line1<br/>line2") == "line1\nline2"

    def test_span_stripped(self):
        html = '<span style="color:red;">text</span>'
        result = _html_to_discord_md(html)
        assert "<span" not in result
        assert "text" in result


# ──────────────────────────────────────────────────────────────────
# _html_to_plain
# ──────────────────────────────────────────────────────────────────

class TestHtmlToPlain:
    def test_strips_all_tags(self):
        html = '<b>Hello</b> <i>World</i>'
        assert _html_to_plain(html) == "Hello World"

    def test_complex_html(self):
        html = '<span style="color:red;">text</span> <b>bold</b>'
        result = _html_to_plain(html)
        assert "text" in result
        assert "bold" in result
        assert "<" not in result


# ──────────────────────────────────────────────────────────────────
# _build_email_html
# ──────────────────────────────────────────────────────────────────

class TestBuildEmailHtml:
    def test_contains_title(self):
        html = _build_email_html("Test Title", "body text")
        assert "Test Title" in html

    def test_contains_body(self):
        html = _build_email_html("Title", "My body content")
        assert "My body content" in html

    def test_contains_atlas_branding(self):
        html = _build_email_html("Title", "Body")
        assert "Atlas" in html
        assert "TradingLab" in html


# ──────────────────────────────────────────────────────────────────
# _SENSITIVE_FIELDS
# ──────────────────────────────────────────────────────────────────

class TestSensitiveFields:
    def test_expected_fields(self):
        assert "telegram_bot_token" in _SENSITIVE_FIELDS
        assert "discord_webhook_url" in _SENSITIVE_FIELDS
        assert "email_password" in _SENSITIVE_FIELDS
        assert "gmail_client_secret" in _SENSITIVE_FIELDS
        assert "gmail_refresh_token" in _SENSITIVE_FIELDS

    def test_non_sensitive_not_included(self):
        assert "telegram_enabled" not in _SENSITIVE_FIELDS
        assert "email_recipient" not in _SENSITIVE_FIELDS


# ──────────────────────────────────────────────────────────────────
# AlertChannel enum
# ──────────────────────────────────────────────────────────────────

class TestAlertChannel:
    def test_values(self):
        assert AlertChannel.TELEGRAM.value == "telegram"
        assert AlertChannel.DISCORD.value == "discord"
        assert AlertChannel.EMAIL.value == "email"
        assert AlertChannel.GMAIL.value == "gmail"


# ──────────────────────────────────────────────────────────────────
# AlertConfig defaults
# ──────────────────────────────────────────────────────────────────

class TestAlertConfig:
    def test_defaults_all_disabled(self):
        cfg = AlertConfig()
        assert cfg.telegram_enabled is False
        assert cfg.discord_enabled is False
        assert cfg.email_enabled is False
        assert cfg.gmail_enabled is False

    def test_notification_types_default_on(self):
        cfg = AlertConfig()
        assert cfg.notify_trade_executed is True
        assert cfg.notify_setup_pending is True
        assert cfg.notify_setup_rejected is True
        assert cfg.notify_trade_closed is True
        assert cfg.notify_daily_summary is True

    def test_smtp_defaults(self):
        cfg = AlertConfig()
        assert cfg.email_smtp_server == "smtp.gmail.com"
        assert cfg.email_smtp_port == 587


# ──────────────────────────────────────────────────────────────────
# AlertManager initialization
# ──────────────────────────────────────────────────────────────────

class TestAlertManagerInit:
    def test_init_with_config(self):
        cfg = AlertConfig(telegram_enabled=True)
        mgr = AlertManager(config=cfg)
        assert mgr._config.telegram_enabled is True

    def test_init_default_loads_from_disk(self):
        with patch.object(AlertManager, '_load_config') as mock_load:
            mgr = AlertManager()
            mock_load.assert_called_once()


# ──────────────────────────────────────────────────────────────────
# AlertManager.get_config
# ──────────────────────────────────────────────────────────────────

class TestGetConfig:
    def test_masks_sensitive_fields(self):
        cfg = AlertConfig(
            telegram_bot_token="my_super_secret_token_123456",
            email_password="password_1234",
        )
        mgr = AlertManager(config=cfg)
        result = mgr.get_config()
        # Token should be masked
        assert result["telegram_bot_token"].endswith("3456")
        assert result["telegram_bot_token"].startswith("*")
        # Password should be masked
        assert result["email_password"].endswith("1234")

    def test_non_sensitive_fields_visible(self):
        cfg = AlertConfig(
            telegram_enabled=True,
            email_recipient="user@example.com",
        )
        mgr = AlertManager(config=cfg)
        result = mgr.get_config()
        assert result["telegram_enabled"] is True
        assert result["email_recipient"] == "user@example.com"


# ──────────────────────────────────────────────────────────────────
# AlertManager.update_config
# ──────────────────────────────────────────────────────────────────

class TestUpdateConfig:
    def test_replaces_config(self):
        mgr = AlertManager(config=AlertConfig())
        new_cfg = AlertConfig(telegram_enabled=True)
        with patch.object(mgr, '_save_config'):
            mgr.update_config(new_cfg)
        assert mgr._config.telegram_enabled is True


# ──────────────────────────────────────────────────────────────────
# AlertManager._discord_colour_for_type
# ──────────────────────────────────────────────────────────────────

class TestDiscordColour:
    def test_trade_executed_green(self):
        assert AlertManager._discord_colour_for_type("trade_executed") == 0x00FF9D

    def test_setup_pending_gold(self):
        assert AlertManager._discord_colour_for_type("setup_pending") == 0xFFD700

    def test_setup_rejected_red(self):
        assert AlertManager._discord_colour_for_type("setup_rejected") == 0xFB3048

    def test_trade_closed_blue(self):
        assert AlertManager._discord_colour_for_type("trade_closed") == 0x3498DB

    def test_daily_summary_purple(self):
        assert AlertManager._discord_colour_for_type("daily_summary") == 0x9B59B6

    def test_risk_alert_warning(self):
        assert AlertManager._discord_colour_for_type("risk_alert") == 0xFF6B6B

    def test_unknown_type_default(self):
        assert AlertManager._discord_colour_for_type("unknown_type") == DISCORD_EMBED_COLOUR


# ──────────────────────────────────────────────────────────────────
# AlertManager.send_alert — fan-out
# ──────────────────────────────────────────────────────────────────

class TestSendAlert:
    @pytest.mark.asyncio
    async def test_no_channels_enabled_logs_warning(self):
        cfg = AlertConfig()  # All disabled
        mgr = AlertManager(config=cfg)
        # Should not raise
        await mgr.send_alert("test", "Title", "Body")

    @pytest.mark.asyncio
    async def test_telegram_dispatched_when_enabled(self):
        cfg = AlertConfig(telegram_enabled=True)
        mgr = AlertManager(config=cfg)
        with patch.object(mgr, '_send_telegram', new_callable=AsyncMock) as mock_tg:
            await mgr.send_alert("test", "Title", "Body")
            mock_tg.assert_called_once_with("Title", "Body")

    @pytest.mark.asyncio
    async def test_discord_dispatched_when_enabled(self):
        cfg = AlertConfig(discord_enabled=True)
        mgr = AlertManager(config=cfg)
        with patch.object(mgr, '_send_discord', new_callable=AsyncMock) as mock_dc:
            await mgr.send_alert("test", "Title", "Body", {"key": "val"})
            mock_dc.assert_called_once_with("Title", "Body", "test", {"key": "val"})

    @pytest.mark.asyncio
    async def test_multiple_channels_dispatched(self):
        cfg = AlertConfig(telegram_enabled=True, discord_enabled=True)
        mgr = AlertManager(config=cfg)
        with patch.object(mgr, '_send_telegram', new_callable=AsyncMock) as mock_tg, \
             patch.object(mgr, '_send_discord', new_callable=AsyncMock) as mock_dc:
            await mgr.send_alert("test", "Title", "Body")
            mock_tg.assert_called_once()
            mock_dc.assert_called_once()


# ──────────────────────────────────────────────────────────────────
# High-level trade alerts — disabled notification
# ──────────────────────────────────────────────────────────────────

class TestHighLevelAlerts:
    @pytest.mark.asyncio
    async def test_trade_executed_skipped_when_disabled(self):
        cfg = AlertConfig(notify_trade_executed=False, telegram_enabled=True)
        mgr = AlertManager(config=cfg)
        with patch.object(mgr, 'send_alert', new_callable=AsyncMock) as mock:
            await mgr.send_trade_executed("EUR_USD", "BUY", 1.1, 1.09, 1.12, 2.0)
            mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_trade_executed_fires_when_enabled(self):
        cfg = AlertConfig(notify_trade_executed=True, telegram_enabled=True)
        mgr = AlertManager(config=cfg)
        with patch.object(mgr, 'send_alert', new_callable=AsyncMock) as mock:
            await mgr.send_trade_executed("EUR_USD", "BUY", 1.1, 1.09, 1.12, 2.0, "BLUE_A")
            mock.assert_called_once()
            assert mock.call_args[0][0] == "trade_executed"

    @pytest.mark.asyncio
    async def test_setup_pending_skipped_when_disabled(self):
        cfg = AlertConfig(notify_setup_pending=False)
        mgr = AlertManager(config=cfg)
        with patch.object(mgr, 'send_alert', new_callable=AsyncMock) as mock:
            await mgr.send_setup_pending("EUR_USD", "BUY", 1.1, 2.0)
            mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_setup_pending_fires_with_ai_section(self):
        cfg = AlertConfig(notify_setup_pending=True, telegram_enabled=True)
        mgr = AlertManager(config=cfg)
        with patch.object(mgr, 'send_alert', new_callable=AsyncMock) as mock:
            await mgr.send_setup_pending(
                "EUR_USD", "SELL", 1.1, 2.0,
                ai_score=85, ai_reasoning="Strong trend alignment",
            )
            mock.assert_called_once()
            body = mock.call_args[0][2]
            assert "85/100" in body

    @pytest.mark.asyncio
    async def test_setup_rejected_skipped_when_disabled(self):
        cfg = AlertConfig(notify_setup_rejected=False)
        mgr = AlertManager(config=cfg)
        with patch.object(mgr, 'send_alert', new_callable=AsyncMock) as mock:
            await mgr.send_setup_rejected("EUR_USD", "BUY")
            mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_trade_closed_skipped_when_disabled(self):
        cfg = AlertConfig(notify_trade_closed=False)
        mgr = AlertManager(config=cfg)
        with patch.object(mgr, 'send_alert', new_callable=AsyncMock) as mock:
            await mgr.send_trade_closed("EUR_USD", 100.0, 50.0, "TP_HIT")
            mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_trade_closed_fires_with_correct_type(self):
        cfg = AlertConfig(notify_trade_closed=True, telegram_enabled=True)
        mgr = AlertManager(config=cfg)
        with patch.object(mgr, 'send_alert', new_callable=AsyncMock) as mock:
            await mgr.send_trade_closed("EUR_USD", 100.0, 50.0, "TP_HIT", "RED")
            assert mock.call_args[0][0] == "trade_closed"

    @pytest.mark.asyncio
    async def test_daily_summary_skipped_when_disabled(self):
        cfg = AlertConfig(notify_daily_summary=False)
        mgr = AlertManager(config=cfg)
        with patch.object(mgr, 'send_alert', new_callable=AsyncMock) as mock:
            await mgr.send_daily_summary({})
            mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_daily_summary_calculates_win_rate(self):
        cfg = AlertConfig(notify_daily_summary=True, telegram_enabled=True)
        mgr = AlertManager(config=cfg)
        with patch.object(mgr, 'send_alert', new_callable=AsyncMock) as mock:
            await mgr.send_daily_summary({
                "total_pnl": 250.0, "trades_count": 10, "wins": 7, "losses": 3,
            })
            body = mock.call_args[0][2]
            assert "70.0%" in body

    @pytest.mark.asyncio
    async def test_position_update_fires(self):
        cfg = AlertConfig(telegram_enabled=True)
        mgr = AlertManager(config=cfg)
        with patch.object(mgr, 'send_alert', new_callable=AsyncMock) as mock:
            await mgr.send_position_update("EUR_USD", "TRAILING", 1.1050, 1.1000)
            assert mock.call_args[0][0] == "position_update"

    @pytest.mark.asyncio
    async def test_engine_status_fires(self):
        cfg = AlertConfig(telegram_enabled=True)
        mgr = AlertManager(config=cfg)
        with patch.object(mgr, 'send_alert', new_callable=AsyncMock) as mock:
            await mgr.send_engine_status("started", "Engine started successfully")
            assert mock.call_args[0][0] == "engine_status"

    @pytest.mark.asyncio
    async def test_risk_alert_fires(self):
        cfg = AlertConfig(telegram_enabled=True)
        mgr = AlertManager(config=cfg)
        with patch.object(mgr, 'send_alert', new_callable=AsyncMock) as mock:
            await mgr.send_risk_alert("DAILY_DD", "Daily drawdown exceeded", 5.5)
            assert mock.call_args[0][0] == "risk_alert"
            body = mock.call_args[0][2]
            assert "5.50%" in body


# ──────────────────────────────────────────────────────────────────
# Channel sends — missing config skips
# ──────────────────────────────────────────────────────────────────

class TestChannelSends:
    @pytest.mark.asyncio
    async def test_telegram_skipped_no_token(self):
        cfg = AlertConfig(telegram_bot_token="", telegram_chat_id="123")
        mgr = AlertManager(config=cfg)
        # Should not raise, just log warning
        await mgr._send_telegram("Title", "Body")

    @pytest.mark.asyncio
    async def test_telegram_skipped_no_chat_id(self):
        cfg = AlertConfig(telegram_bot_token="token", telegram_chat_id="")
        mgr = AlertManager(config=cfg)
        await mgr._send_telegram("Title", "Body")

    @pytest.mark.asyncio
    async def test_discord_skipped_no_webhook(self):
        cfg = AlertConfig(discord_webhook_url="")
        mgr = AlertManager(config=cfg)
        await mgr._send_discord("Title", "Body")

    @pytest.mark.asyncio
    async def test_email_skipped_incomplete_config(self):
        cfg = AlertConfig(email_username="", email_password="", email_recipient="")
        mgr = AlertManager(config=cfg)
        await mgr._send_email("Title", "Body")

    @pytest.mark.asyncio
    async def test_gmail_skipped_no_refresh_token(self):
        cfg = AlertConfig(gmail_refresh_token="", gmail_client_id="")
        mgr = AlertManager(config=cfg)
        await mgr._send_gmail("Title", "Body")

    @pytest.mark.asyncio
    async def test_gmail_skipped_no_sender(self):
        cfg = AlertConfig(
            gmail_refresh_token="token", gmail_client_id="id",
            gmail_sender="", gmail_recipient="user@x.com",
        )
        mgr = AlertManager(config=cfg)
        await mgr._send_gmail("Title", "Body")


# ──────────────────────────────────────────────────────────────────
# test_channel
# ──────────────────────────────────────────────────────────────────

class TestTestChannel:
    @pytest.mark.asyncio
    async def test_telegram_channel(self):
        mgr = AlertManager(config=AlertConfig())
        with patch.object(mgr, '_send_telegram', new_callable=AsyncMock) as mock:
            result = await mgr.test_channel(AlertChannel.TELEGRAM)
            mock.assert_called_once()
            assert result is True

    @pytest.mark.asyncio
    async def test_discord_channel(self):
        mgr = AlertManager(config=AlertConfig())
        with patch.object(mgr, '_send_discord', new_callable=AsyncMock) as mock:
            result = await mgr.test_channel(AlertChannel.DISCORD)
            mock.assert_called_once()
            assert result is True

    @pytest.mark.asyncio
    async def test_email_channel(self):
        mgr = AlertManager(config=AlertConfig())
        with patch.object(mgr, '_send_email', new_callable=AsyncMock) as mock:
            result = await mgr.test_channel(AlertChannel.EMAIL)
            mock.assert_called_once()
            assert result is True

    @pytest.mark.asyncio
    async def test_gmail_channel(self):
        mgr = AlertManager(config=AlertConfig())
        with patch.object(mgr, '_send_gmail', new_callable=AsyncMock) as mock:
            result = await mgr.test_channel(AlertChannel.GMAIL)
            mock.assert_called_once()
            assert result is True

    @pytest.mark.asyncio
    async def test_channel_failure_returns_false(self):
        mgr = AlertManager(config=AlertConfig())
        with patch.object(mgr, '_send_telegram', new_callable=AsyncMock, side_effect=RuntimeError("fail")):
            result = await mgr.test_channel(AlertChannel.TELEGRAM)
            assert result is False


# ──────────────────────────────────────────────────────────────────
# Gmail OAuth2 token caching
# ──────────────────────────────────────────────────────────────────

class TestGmailAccessToken:
    @pytest.mark.asyncio
    async def test_cached_token_reused(self):
        cfg = AlertConfig(
            gmail_client_id="id", gmail_client_secret="secret",
            gmail_refresh_token="refresh", gmail_sender="a@b.com", gmail_recipient="c@d.com",
        )
        mgr = AlertManager(config=cfg)
        mgr._gmail_access_token = "cached_token"
        mgr._gmail_token_expires_at = time.time() + 3000  # Not expired
        token = await mgr._get_gmail_access_token()
        assert token == "cached_token"

    @pytest.mark.asyncio
    async def test_expired_token_refreshed(self):
        cfg = AlertConfig(
            gmail_client_id="id", gmail_client_secret="secret",
            gmail_refresh_token="refresh", gmail_sender="a@b.com", gmail_recipient="c@d.com",
        )
        mgr = AlertManager(config=cfg)
        mgr._gmail_access_token = "old_token"
        mgr._gmail_token_expires_at = time.time() - 100  # Expired

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "new_token"}

        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False

        with patch.object(mgr, '_get_http', return_value=mock_http):
            token = await mgr._get_gmail_access_token()
        assert token == "new_token"
        assert mgr._gmail_token_expires_at > time.time()

    @pytest.mark.asyncio
    async def test_refresh_failure_returns_none(self):
        cfg = AlertConfig(
            gmail_client_id="id", gmail_client_secret="secret",
            gmail_refresh_token="refresh", gmail_sender="a@b.com", gmail_recipient="c@d.com",
        )
        mgr = AlertManager(config=cfg)
        mgr._gmail_access_token = None
        mgr._gmail_token_expires_at = 0.0

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Invalid grant"

        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False

        with patch.object(mgr, '_get_http', return_value=mock_http):
            token = await mgr._get_gmail_access_token()
        assert token is None


# ──────────────────────────────────────────────────────────────────
# _safe_send
# ──────────────────────────────────────────────────────────────────

class TestSafeSend:
    @pytest.mark.asyncio
    async def test_swallows_exception(self):
        mgr = AlertManager(config=AlertConfig())

        async def failing_coro():
            raise RuntimeError("boom")

        # Should not raise
        await mgr._safe_send(failing_coro())

    @pytest.mark.asyncio
    async def test_passes_success(self):
        mgr = AlertManager(config=AlertConfig())

        async def ok_coro():
            return "ok"

        await mgr._safe_send(ok_coro())


# ──────────────────────────────────────────────────────────────────
# HTTP client lifecycle
# ──────────────────────────────────────────────────────────────────

class TestHttpClient:
    def test_get_http_creates_client(self):
        mgr = AlertManager(config=AlertConfig())
        client = mgr._get_http()
        assert client is not None
        # Same client returned on second call
        assert mgr._get_http() is client

    @pytest.mark.asyncio
    async def test_close_shuts_down(self):
        mgr = AlertManager(config=AlertConfig())
        _ = mgr._get_http()
        await mgr.close()
        assert mgr._http.is_closed
