"""
NeonTrade AI - Alerts & Notifications Module
Sends trade alerts and summaries to Telegram, Discord, Email, and Gmail OAuth2.

Channels:
- Telegram: Bot API with HTML parse mode
- Discord: Webhook with rich embeds
- Email (SMTP): SMTP with HTML formatting
- Gmail (OAuth2): Google API with OAuth2 refresh token

All sends are fire-and-forget so a notification failure never blocks trading.
"""

import asyncio
import base64
import json
import smtplib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from loguru import logger

# ── Constants ────────────────────────────────────────────────────

CONFIG_PATH = Path(__file__).resolve().parent.parent / "data" / "alert_config.json"
GMAIL_TOKEN_PATH = Path(__file__).resolve().parent.parent / "data" / "gmail_token.json"

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# Colour used in Discord embeds (NeonTrade brand green)
DISCORD_EMBED_COLOUR = 0x00FF9D


# ── Enums & Config ──────────────────────────────────────────────

class AlertChannel(Enum):
    TELEGRAM = "telegram"
    DISCORD = "discord"
    EMAIL = "email"
    GMAIL = "gmail"


@dataclass
class AlertConfig:
    """Configuration for all notification channels."""

    # Telegram
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Discord
    discord_enabled: bool = False
    discord_webhook_url: str = ""

    # Email (SMTP)
    email_enabled: bool = False
    email_smtp_server: str = "smtp.gmail.com"
    email_smtp_port: int = 587
    email_username: str = ""
    email_password: str = ""  # App password for Gmail
    email_recipient: str = ""

    # Gmail OAuth2 (preferred for Gmail accounts)
    gmail_enabled: bool = False
    gmail_sender: str = ""
    gmail_recipient: str = ""
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""

    # What to notify about
    notify_trade_executed: bool = True
    notify_setup_pending: bool = True
    notify_trade_closed: bool = True
    notify_daily_summary: bool = True


# Fields whose values should be masked when returned via API.
_SENSITIVE_FIELDS = {
    "telegram_bot_token",
    "discord_webhook_url",
    "email_password",
    "gmail_client_secret",
    "gmail_refresh_token",
}


def _mask(value: str) -> str:
    """Show only the last 4 characters of a secret, or '****' if shorter."""
    if not value:
        return ""
    if len(value) <= 4:
        return "****"
    return "*" * (len(value) - 4) + value[-4:]


# ── AlertManager ────────────────────────────────────────────────

class AlertManager:
    """Manages alert delivery across Telegram, Discord, and Email."""

    def __init__(self, config: Optional[AlertConfig] = None):
        self._config: AlertConfig = config or AlertConfig()
        self._http: Optional[httpx.AsyncClient] = None

        # Try to load persisted config from disk (overridden by explicit arg)
        if config is None:
            self._load_config()

    # ── HTTP client lifecycle ────────────────────────────────────

    def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=15.0)
        return self._http

    async def close(self):
        """Shut down the HTTP client."""
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()

    # ── Config persistence ───────────────────────────────────────

    def _load_config(self):
        """Load config from JSON on disk (if present)."""
        try:
            if CONFIG_PATH.exists():
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                for key, value in data.items():
                    if hasattr(self._config, key):
                        setattr(self._config, key, value)
                logger.info("Alert config loaded from {}", CONFIG_PATH)
        except Exception as exc:
            logger.warning("Could not load alert config: {}", exc)

    def _save_config(self):
        """Persist current config to JSON."""
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(
                json.dumps(asdict(self._config), indent=2),
                encoding="utf-8",
            )
            logger.debug("Alert config saved to {}", CONFIG_PATH)
        except Exception as exc:
            logger.warning("Could not save alert config: {}", exc)

    # ── Public config helpers ────────────────────────────────────

    def update_config(self, config: AlertConfig):
        """Replace the current config and persist it."""
        self._config = config
        self._save_config()

    def get_config(self) -> dict:
        """Return config with sensitive fields masked."""
        raw = asdict(self._config)
        for field_name in _SENSITIVE_FIELDS:
            if field_name in raw:
                raw[field_name] = _mask(raw[field_name])
        return raw

    # ── Generic send (fan-out to enabled channels) ───────────────

    async def send_alert(
        self,
        alert_type: str,
        title: str,
        body: str,
        data: Optional[dict] = None,
    ):
        """Fire-and-forget dispatch to every enabled channel."""
        tasks: List[asyncio.Task] = []

        if self._config.telegram_enabled:
            tasks.append(asyncio.create_task(
                self._safe_send(self._send_telegram(title, body))
            ))

        if self._config.discord_enabled:
            tasks.append(asyncio.create_task(
                self._safe_send(self._send_discord(title, body, alert_type, data))
            ))

        if self._config.email_enabled:
            tasks.append(asyncio.create_task(
                self._safe_send(self._send_email(title, body))
            ))

        if self._config.gmail_enabled:
            tasks.append(asyncio.create_task(
                self._safe_send(self._send_gmail(title, body))
            ))

        if not tasks:
            logger.debug("No alert channels enabled – skipping '{}'", alert_type)
            return

        # Await all but swallow individual failures
        await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    async def _safe_send(coro):
        """Wrapper that catches and logs any exception from a send coroutine."""
        try:
            await coro
        except Exception as exc:
            logger.error("Alert send failed: {}", exc)

    # ── High-level trade alerts ──────────────────────────────────

    async def send_trade_executed(
        self,
        instrument: str,
        direction: str,
        entry: float,
        sl: float,
        tp: float,
        rr: float,
    ):
        if not self._config.notify_trade_executed:
            return

        direction_emoji = "\U0001F7E2" if direction.upper() == "BUY" else "\U0001F534"  # green / red circle
        title = f"{direction_emoji} Trade Executed: {instrument}"
        body = (
            f"<b>Instrument:</b> {instrument}\n"
            f"<b>Direction:</b> {direction.upper()}\n"
            f"<b>Entry:</b> {entry}\n"
            f"<b>Stop Loss:</b> {sl}\n"
            f"<b>Take Profit:</b> {tp}\n"
            f"<b>R:R Ratio:</b> {rr:.2f}"
        )
        data = {
            "instrument": instrument,
            "direction": direction,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "rr": rr,
        }
        await self.send_alert("trade_executed", title, body, data)

    async def send_setup_pending(
        self,
        instrument: str,
        direction: str,
        entry: float,
        rr: float,
    ):
        if not self._config.notify_setup_pending:
            return

        title = f"\U0001F50E Setup Pending: {instrument}"  # magnifying glass
        body = (
            f"<b>Instrument:</b> {instrument}\n"
            f"<b>Direction:</b> {direction.upper()}\n"
            f"<b>Pending Entry:</b> {entry}\n"
            f"<b>Expected R:R:</b> {rr:.2f}"
        )
        data = {
            "instrument": instrument,
            "direction": direction,
            "entry": entry,
            "rr": rr,
        }
        await self.send_alert("setup_pending", title, body, data)

    async def send_trade_closed(
        self,
        instrument: str,
        pnl: float,
        pips: float,
        reason: str,
    ):
        if not self._config.notify_trade_closed:
            return

        result_emoji = "\U00002705" if pnl >= 0 else "\U0000274C"  # check / cross
        title = f"{result_emoji} Trade Closed: {instrument}"
        sign = "+" if pnl >= 0 else ""
        body = (
            f"<b>Instrument:</b> {instrument}\n"
            f"<b>P&L:</b> {sign}{pnl:.2f}\n"
            f"<b>Pips:</b> {sign}{pips:.1f}\n"
            f"<b>Reason:</b> {reason}"
        )
        data = {
            "instrument": instrument,
            "pnl": pnl,
            "pips": pips,
            "reason": reason,
        }
        await self.send_alert("trade_closed", title, body, data)

    async def send_daily_summary(self, stats: dict):
        if not self._config.notify_daily_summary:
            return

        total_pnl = stats.get("total_pnl", 0.0)
        trades = stats.get("trades_count", 0)
        wins = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        win_rate = (wins / trades * 100) if trades > 0 else 0.0
        best = stats.get("best_trade", "N/A")
        worst = stats.get("worst_trade", "N/A")

        pnl_emoji = "\U0001F4C8" if total_pnl >= 0 else "\U0001F4C9"  # chart up / down
        title = f"{pnl_emoji} Daily Summary"
        sign = "+" if total_pnl >= 0 else ""
        body = (
            f"<b>Date:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
            f"<b>Total P&L:</b> {sign}{total_pnl:.2f}\n"
            f"<b>Trades:</b> {trades}  |  "
            f"<b>Wins:</b> {wins}  |  <b>Losses:</b> {losses}\n"
            f"<b>Win Rate:</b> {win_rate:.1f}%\n"
            f"<b>Best:</b> {best}\n"
            f"<b>Worst:</b> {worst}"
        )
        await self.send_alert("daily_summary", title, body, stats)

    # ── Test a single channel ────────────────────────────────────

    async def test_channel(self, channel: AlertChannel) -> bool:
        """Send a test message to *one* channel. Returns True on success."""
        title = "\U0001F6CE\uFE0F NeonTrade AI - Test Notification"
        body = (
            "If you can see this message, your notification channel "
            "is configured correctly.\n\n"
            f"<b>Timestamp:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        try:
            if channel == AlertChannel.TELEGRAM:
                await self._send_telegram(title, body)
            elif channel == AlertChannel.DISCORD:
                await self._send_discord(title, body, "test")
            elif channel == AlertChannel.EMAIL:
                await self._send_email(title, body)
            elif channel == AlertChannel.GMAIL:
                await self._send_gmail(title, body)
            else:
                logger.warning("Unknown alert channel: {}", channel)
                return False
            return True
        except Exception as exc:
            logger.error("Test alert to {} failed: {}", channel.value, exc)
            return False

    # ── Telegram ─────────────────────────────────────────────────

    async def _send_telegram(self, title: str, body: str):
        """Send an HTML-formatted message via the Telegram Bot API."""
        token = self._config.telegram_bot_token
        chat_id = self._config.telegram_chat_id
        if not token or not chat_id:
            logger.warning("Telegram alert skipped – missing bot_token or chat_id")
            return

        text = f"<b>{_strip_emoji_tags(title)}</b>\n\n{body}"
        url = TELEGRAM_API.format(token=token)

        resp = await self._get_http().post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Telegram API returned {resp.status_code}: {resp.text}"
            )
        logger.debug("Telegram alert sent: {}", title)

    # ── Discord ──────────────────────────────────────────────────

    async def _send_discord(
        self,
        title: str,
        body: str,
        alert_type: str = "",
        data: Optional[dict] = None,
    ):
        """Send a rich embed via a Discord webhook."""
        url = self._config.discord_webhook_url
        if not url:
            logger.warning("Discord alert skipped – missing webhook_url")
            return

        # Convert HTML tags to Discord markdown
        description = _html_to_discord_md(body)

        colour = self._discord_colour_for_type(alert_type)

        embed = {
            "title": _strip_emoji_tags(title),
            "description": description,
            "color": colour,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": "NeonTrade AI"},
        }

        payload = {
            "username": "NeonTrade AI",
            "embeds": [embed],
        }

        resp = await self._get_http().post(url, json=payload)
        if resp.status_code not in (200, 204):
            raise RuntimeError(
                f"Discord webhook returned {resp.status_code}: {resp.text}"
            )
        logger.debug("Discord alert sent: {}", title)

    @staticmethod
    def _discord_colour_for_type(alert_type: str) -> int:
        colours = {
            "trade_executed": 0x00FF9D,   # green
            "setup_pending": 0xFFD700,    # gold
            "trade_closed": 0x3498DB,     # blue
            "daily_summary": 0x9B59B6,    # purple
            "test": 0x00FF9D,             # green
        }
        return colours.get(alert_type, DISCORD_EMBED_COLOUR)

    # ── Email ────────────────────────────────────────────────────

    async def _send_email(self, title: str, body: str):
        """Send an HTML email over SMTP (run in executor to avoid blocking)."""
        cfg = self._config
        if not cfg.email_username or not cfg.email_password or not cfg.email_recipient:
            logger.warning("Email alert skipped – incomplete SMTP config")
            return

        plain_title = _strip_emoji_tags(title)
        html_body = _build_email_html(plain_title, body)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = plain_title
        msg["From"] = cfg.email_username
        msg["To"] = cfg.email_recipient
        msg.attach(MIMEText(_html_to_plain(body), "plain"))
        msg.attach(MIMEText(html_body, "html"))

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._smtp_send, msg)
        logger.debug("Email alert sent: {}", plain_title)

    def _smtp_send(self, msg: MIMEMultipart):
        """Blocking SMTP send – intended to be called from run_in_executor."""
        cfg = self._config
        with smtplib.SMTP(cfg.email_smtp_server, cfg.email_smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(cfg.email_username, cfg.email_password)
            server.sendmail(cfg.email_username, cfg.email_recipient, msg.as_string())

    # ── Gmail OAuth2 ──────────────────────────────────────────────

    async def _send_gmail(self, title: str, body: str):
        """Send an email via Gmail API using OAuth2 refresh token."""
        cfg = self._config
        if not cfg.gmail_refresh_token or not cfg.gmail_client_id:
            logger.warning("Gmail alert skipped – missing OAuth2 credentials")
            return

        plain_title = _strip_emoji_tags(title)
        html_body = _build_email_html(plain_title, body)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = plain_title
        msg["From"] = cfg.gmail_sender
        msg["To"] = cfg.gmail_recipient
        msg.attach(MIMEText(_html_to_plain(body), "plain"))
        msg.attach(MIMEText(html_body, "html"))

        raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

        # Get fresh access token using refresh token
        access_token = await self._get_gmail_access_token()
        if not access_token:
            raise RuntimeError("Failed to obtain Gmail access token")

        # Send via Gmail API
        resp = await self._get_http().post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"raw": raw_message},
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Gmail API returned {resp.status_code}: {resp.text}"
            )
        logger.debug("Gmail alert sent: {}", plain_title)

    async def _get_gmail_access_token(self) -> Optional[str]:
        """Exchange refresh token for a fresh access token."""
        cfg = self._config
        resp = await self._get_http().post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": cfg.gmail_client_id,
                "client_secret": cfg.gmail_client_secret,
                "refresh_token": cfg.gmail_refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if resp.status_code == 200:
            return resp.json().get("access_token")
        logger.error("Gmail token refresh failed: {} {}", resp.status_code, resp.text)
        return None


# ── Text helpers (module-private) ────────────────────────────────

def _strip_emoji_tags(text: str) -> str:
    """Return *text* unchanged – emojis are plain Unicode and safe everywhere."""
    return text


def _html_to_discord_md(html: str) -> str:
    """Minimal HTML-to-Discord-Markdown conversion."""
    md = html
    md = md.replace("<b>", "**").replace("</b>", "**")
    md = md.replace("<i>", "*").replace("</i>", "*")
    md = md.replace("<code>", "`").replace("</code>", "`")
    md = md.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    return md


def _html_to_plain(html: str) -> str:
    """Strip HTML tags for the plain-text email fallback."""
    import re
    return re.sub(r"<[^>]+>", "", html)


def _build_email_html(title: str, body: str) -> str:
    """Wrap *body* (already contains <b> etc.) in a styled HTML email."""
    # Replace newlines with <br> for email rendering
    body_html = body.replace("\n", "<br>\n")
    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0d1117;font-family:
  -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0d1117;">
    <tr><td align="center" style="padding:24px 0;">
      <table width="560" cellpadding="0" cellspacing="0"
             style="background:#161b22;border-radius:12px;border:1px solid #30363d;">
        <!-- Header -->
        <tr><td style="padding:24px 32px 12px 32px;">
          <h2 style="margin:0;color:#00ff9d;font-size:20px;">{title}</h2>
        </td></tr>
        <!-- Body -->
        <tr><td style="padding:12px 32px 24px 32px;color:#c9d1d9;font-size:14px;line-height:1.6;">
          {body_html}
        </td></tr>
        <!-- Footer -->
        <tr><td style="padding:12px 32px 20px 32px;border-top:1px solid #30363d;
                        color:#8b949e;font-size:11px;">
          NeonTrade AI &middot; {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
