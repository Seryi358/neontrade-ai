"""
Tests for Gmail-only alert delivery.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.alerts import (
    _SENSITIVE_FIELDS,
    _build_email_html,
    _html_to_plain,
    _mask,
    AlertChannel,
    AlertConfig,
    AlertManager,
)


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


class TestHtmlHelpers:
    def test_html_to_plain_strips_tags(self):
        assert _html_to_plain("<b>Hello</b> <i>World</i>") == "Hello World"

    def test_email_html_contains_title_and_body(self):
        html = _build_email_html("Test Title", "body text")
        assert "Test Title" in html
        assert "body text" in html

    def test_email_html_uses_atlas_branding(self):
        html = _build_email_html("Title", "Body")
        assert "Atlas" in html

    def test_email_html_normalizes_fenced_body(self):
        html = _build_email_html("Title", "```html\n<p>Checklist</p>\n```")
        assert "```html" not in html
        assert "<p>" not in html
        assert "Checklist" in html


class TestSensitiveFields:
    def test_gmail_secrets_are_sensitive(self):
        assert _SENSITIVE_FIELDS == {"gmail_client_secret", "gmail_refresh_token"}


class TestAlertChannel:
    def test_gmail_only(self):
        assert [channel.value for channel in AlertChannel] == ["gmail"]


class TestAlertConfig:
    def test_defaults(self):
        cfg = AlertConfig()
        assert cfg.gmail_enabled is False
        assert cfg.gmail_sender == ""
        assert cfg.gmail_recipient == ""
        assert cfg.notify_trade_executed is True
        assert cfg.notify_setup_pending is True
        assert cfg.notify_setup_rejected is True
        assert cfg.notify_trade_closed is True
        assert cfg.notify_daily_summary is True


class TestAlertManagerConfig:
    def test_init_with_config(self):
        cfg = AlertConfig(gmail_enabled=True)
        mgr = AlertManager(config=cfg)
        assert mgr._config.gmail_enabled is True

    def test_init_default_loads_from_disk(self):
        with patch.object(AlertManager, "_load_config") as mock_load:
            AlertManager()
            mock_load.assert_called_once()

    def test_masks_sensitive_fields(self):
        cfg = AlertConfig(
            gmail_client_secret="client_secret_1234",
            gmail_refresh_token="refresh_token_5678",
            gmail_sender="sender@example.com",
        )
        mgr = AlertManager(config=cfg)
        result = mgr.get_config()
        assert result["gmail_client_secret"].endswith("1234")
        assert result["gmail_refresh_token"].endswith("5678")
        assert result["gmail_sender"] == "sender@example.com"

    def test_update_config_replaces_config(self):
        mgr = AlertManager(config=AlertConfig())
        new_cfg = AlertConfig(gmail_enabled=True)
        with patch.object(mgr, "_save_config"):
            mgr.update_config(new_cfg)
        assert mgr._config.gmail_enabled is True


class TestSendAlert:
    @pytest.mark.asyncio
    async def test_disabled_gmail_skips(self):
        mgr = AlertManager(config=AlertConfig(gmail_enabled=False))
        with patch.object(mgr, "_send_gmail", new_callable=AsyncMock) as mock:
            await mgr.send_alert("test", "Title", "Body")
            mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_enabled_gmail_dispatches(self):
        mgr = AlertManager(config=AlertConfig(gmail_enabled=True))
        with patch.object(mgr, "_send_gmail", new_callable=AsyncMock) as mock:
            await mgr.send_alert("test", "Title", "Body")
            mock.assert_called_once_with("Title", "Body")


class TestHighLevelAlerts:
    @pytest.mark.asyncio
    async def test_trade_executed_skipped_when_disabled(self):
        cfg = AlertConfig(notify_trade_executed=False, gmail_enabled=True)
        mgr = AlertManager(config=cfg)
        with patch.object(mgr, "send_alert", new_callable=AsyncMock) as mock:
            await mgr.send_trade_executed("EUR_USD", "BUY", 1.1, 1.09, 1.12, 2.0)
            mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_trade_executed_fires(self):
        cfg = AlertConfig(notify_trade_executed=True, gmail_enabled=True)
        mgr = AlertManager(config=cfg)
        with patch.object(mgr, "send_alert", new_callable=AsyncMock) as mock:
            await mgr.send_trade_executed("EUR_USD", "BUY", 1.1, 1.09, 1.12, 2.0, "BLUE_A")
            mock.assert_called_once()
            assert mock.call_args[0][0] == "trade_executed"

    @pytest.mark.asyncio
    async def test_setup_pending_includes_ai_section(self):
        mgr = AlertManager(config=AlertConfig(gmail_enabled=True))
        with patch.object(mgr, "send_alert", new_callable=AsyncMock) as mock:
            await mgr.send_setup_pending(
                "EUR_USD", "SELL", 1.1, 2.0,
                ai_score=85, ai_reasoning="Strong trend alignment",
            )
            body = mock.call_args[0][2]
            assert "IA informativa" in body
            assert "85/100" not in body

    @pytest.mark.asyncio
    async def test_trade_closed_fires(self):
        mgr = AlertManager(config=AlertConfig(gmail_enabled=True))
        with patch.object(mgr, "send_alert", new_callable=AsyncMock) as mock:
            await mgr.send_trade_closed("EUR_USD", 100.0, 50.0, "TP_HIT", "RED")
            assert mock.call_args[0][0] == "trade_closed"

    @pytest.mark.asyncio
    async def test_daily_summary_calculates_win_rate(self):
        mgr = AlertManager(config=AlertConfig(gmail_enabled=True))
        with patch.object(mgr, "send_alert", new_callable=AsyncMock) as mock:
            await mgr.send_daily_summary({
                "total_pnl": 250.0, "trades_count": 10, "wins": 7, "losses": 3,
            })
            assert "70.0%" in mock.call_args[0][2]

    @pytest.mark.asyncio
    async def test_position_update_fires(self):
        mgr = AlertManager(config=AlertConfig(gmail_enabled=True))
        with patch.object(mgr, "send_alert", new_callable=AsyncMock) as mock:
            await mgr.send_position_update("EUR_USD", "TRAILING", 1.1050, 1.1000)
            assert mock.call_args[0][0] == "position_update"

    @pytest.mark.asyncio
    async def test_engine_status_fires(self):
        mgr = AlertManager(config=AlertConfig(gmail_enabled=True))
        with patch.object(mgr, "send_alert", new_callable=AsyncMock) as mock:
            await mgr.send_engine_status("started", "Engine started successfully")
            assert mock.call_args[0][0] == "engine_status"

    @pytest.mark.asyncio
    async def test_risk_alert_fires(self):
        mgr = AlertManager(config=AlertConfig(gmail_enabled=True))
        with patch.object(mgr, "send_alert", new_callable=AsyncMock) as mock:
            await mgr.send_risk_alert("DAILY_DD", "Daily drawdown exceeded", 5.5)
            assert mock.call_args[0][0] == "risk_alert"
            assert "5.50%" in mock.call_args[0][2]


class TestGmailSend:
    @pytest.mark.asyncio
    async def test_gmail_skipped_no_sender(self):
        cfg = AlertConfig(
            gmail_refresh_token="token",
            gmail_client_id="id",
            gmail_client_secret="secret",
            gmail_sender="",
            gmail_recipient="user@example.com",
        )
        mgr = AlertManager(config=cfg)
        await mgr._send_gmail("Title", "Body")

    @pytest.mark.asyncio
    async def test_gmail_success_posts_message(self):
        cfg = AlertConfig(
            gmail_refresh_token="refresh",
            gmail_client_id="id",
            gmail_client_secret="secret",
            gmail_sender="sender@example.com",
            gmail_recipient="dest@example.com",
        )
        mgr = AlertManager(config=cfg)
        mgr._gmail_access_token = "access"
        mgr._gmail_token_expires_at = time.time() + 3000

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False

        with patch.object(mgr, "_get_http", return_value=mock_http):
            await mgr._send_gmail("Title", "Body")
        assert mock_http.post.call_count == 1


class TestTestChannel:
    @pytest.mark.asyncio
    async def test_gmail_channel(self):
        mgr = AlertManager(config=AlertConfig(
            gmail_sender="sender@example.com",
            gmail_recipient="dest@example.com",
            gmail_client_id="cid",
            gmail_client_secret="csecret",
            gmail_refresh_token="refresh",
        ))
        with patch.object(mgr, "_send_gmail", new_callable=AsyncMock) as mock:
            result = await mgr.test_channel(AlertChannel.GMAIL)
            mock.assert_called_once()
            assert result is True

    @pytest.mark.asyncio
    async def test_gmail_channel_failure_returns_false(self):
        mgr = AlertManager(config=AlertConfig(
            gmail_sender="sender@example.com",
            gmail_recipient="dest@example.com",
            gmail_client_id="cid",
            gmail_client_secret="csecret",
            gmail_refresh_token="refresh",
        ))
        with patch.object(mgr, "_send_gmail", new_callable=AsyncMock, side_effect=RuntimeError("fail")):
            result = await mgr.test_channel(AlertChannel.GMAIL)
            assert result is False

    @pytest.mark.asyncio
    async def test_gmail_channel_incomplete_config_returns_false(self):
        mgr = AlertManager(config=AlertConfig())
        result = await mgr.test_channel(AlertChannel.GMAIL)
        assert result is False


class TestGmailAccessToken:
    @pytest.mark.asyncio
    async def test_cached_token_reused(self):
        mgr = AlertManager(config=AlertConfig(
            gmail_client_id="id",
            gmail_client_secret="secret",
            gmail_refresh_token="refresh",
        ))
        mgr._gmail_access_token = "cached_token"
        mgr._gmail_token_expires_at = time.time() + 3000
        assert await mgr._get_gmail_access_token() == "cached_token"

    @pytest.mark.asyncio
    async def test_expired_token_refreshed(self):
        mgr = AlertManager(config=AlertConfig(
            gmail_client_id="id",
            gmail_client_secret="secret",
            gmail_refresh_token="refresh",
        ))
        mgr._gmail_access_token = "old_token"
        mgr._gmail_token_expires_at = time.time() - 100

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "new_token"}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False

        with patch.object(mgr, "_get_http", return_value=mock_http):
            token = await mgr._get_gmail_access_token()
        assert token == "new_token"
        assert mgr._gmail_token_expires_at > time.time()

    @pytest.mark.asyncio
    async def test_refresh_failure_returns_none(self):
        mgr = AlertManager(config=AlertConfig(
            gmail_client_id="id",
            gmail_client_secret="secret",
            gmail_refresh_token="refresh",
        ))
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False

        with patch.object(mgr, "_get_http", return_value=mock_http):
            token = await mgr._get_gmail_access_token()
        assert token is None


class TestSafeSend:
    @pytest.mark.asyncio
    async def test_swallows_exception(self):
        mgr = AlertManager(config=AlertConfig())

        async def failing_coro():
            raise RuntimeError("boom")

        await mgr._safe_send(failing_coro())


class TestHttpClient:
    def test_get_http_creates_client(self):
        mgr = AlertManager(config=AlertConfig())
        client = mgr._get_http()
        assert client is not None
        assert mgr._get_http() is client

    @pytest.mark.asyncio
    async def test_close_shuts_down(self):
        mgr = AlertManager(config=AlertConfig())
        _ = mgr._get_http()
        await mgr.close()
        assert mgr._http.is_closed
