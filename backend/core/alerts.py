"""
Atlas - Alerts & Notifications Module
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
import html
import json
import smtplib
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from loguru import logger


def _h(val) -> str:
    """HTML-escape a value before interpolating into alert bodies.

    User-injected fields (instrument, strategy, direction, reason,
    ai_reasoning, setup_id) could contain &lt;, &gt;, &amp; or quotes that break
    the email body or inject markup. None → empty string.
    """
    if val is None:
        return ""
    return html.escape(str(val), quote=True)

# ── Constants ────────────────────────────────────────────────────

CONFIG_PATH = Path(__file__).resolve().parent.parent / "data" / "alert_config.json"
GMAIL_TOKEN_PATH = Path(__file__).resolve().parent.parent / "data" / "gmail_token.json"

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# Colour used in Discord embeds (Atlas brand green)
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
    notify_setup_rejected: bool = True
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

        # Gmail OAuth2 token cache
        self._gmail_access_token: Optional[str] = None
        self._gmail_token_expires_at: float = 0.0
        self._gmail_refresh_lock: asyncio.Lock = asyncio.Lock()

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
        """Persist current config to JSON atomically."""
        try:
            import os, tempfile
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(asdict(self._config), indent=2)
            dir_name = str(CONFIG_PATH.parent)
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(payload)
                os.replace(tmp_path, str(CONFIG_PATH))
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
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
            logger.warning("No alert channels enabled – skipping '{}'", alert_type)
            return

        # Await all but swallow individual failures
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_send(self, coro):
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
        strategy: str = "",
    ):
        if not self._config.notify_trade_executed:
            return

        dir_color = "#34C759" if direction.upper() == "BUY" else "#FF3B30"
        _instr = _h(instrument)
        _dir = _h(direction.upper())
        _strat = _h(strategy)
        title = f"TRADE EXECUTED // {_instr}"
        body = (
            f'<span style="color:#1d1d1f;font-size:20px;font-weight:700;letter-spacing:-0.3px;">'
            f'{_instr}</span>\n'
            f'<span style="color:{dir_color};font-size:16px;font-weight:600;">'
            f'{_dir}</span> '
            f'<span style="color:#86868b;">// {_strat}</span>\n\n'
            f'<span style="color:#86868b;">ENTRY</span> '
            f'<span style="color:#1d1d1f;font-weight:600;">{entry}</span>\n'
            f'<span style="color:#FF3B30;">SL</span> '
            f'<span style="color:#1d1d1f;">{sl}</span>\n'
            f'<span style="color:#34C759;">TP</span> '
            f'<span style="color:#1d1d1f;">{tp}</span>\n'
            f'<span style="color:#86868b;">R:R</span> '
            f'<span style="color:#FF9500;font-weight:600;">{rr:.2f}:1</span>'
        )
        data = {
            "instrument": instrument,
            "direction": direction,
            "strategy": strategy,
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
        sl: float = 0,
        tp: float = 0,
        strategy: str = "",
        ai_score: int = 0,
        ai_recommendation: str = "",
        ai_reasoning: str = "",
        reasoning: str = "",
    ):
        if not self._config.notify_setup_pending:
            return

        _instr = _h(instrument)
        _dir = _h(direction.upper())
        _strat = _h(strategy)
        title = f"SETUP DETECTED // {_instr}"
        dir_color = "#34C759" if direction.upper() == "BUY" else "#FF3B30"

        # Build rich email body with strategy details and AI opinion
        parts = [
            f'<b>PENDING APPROVAL</b>\n',
            f'<b>{_instr}</b>',
            f'<b>{_dir}</b>\n',
            f'<b>Estrategia:</b> {_strat}' if strategy else '',
            f'<b>Entry:</b> {entry:.5f}',
            f'<b>SL:</b> {sl:.5f}' if sl else '',
            f'<b>TP:</b> {tp:.5f}' if tp else '',
            f'<b>R:R:</b> {rr:.2f}:1\n',
        ]

        # IA analysis section — INFORMATIVE ONLY.
        # Per mentorship 0% discretion rule, technical analysis decides the trade.
        # IA provides narrative context to aid your learning; it does NOT approve/reject.
        if ai_score or ai_reasoning:
            parts.append(f'<b>--- ANÁLISIS IA (informativo) ---</b>')
            if ai_score:
                parts.append(f'<b>Score IA:</b> {ai_score}/100')
            if ai_reasoning:
                # Truncate to 400 chars for email
                reason_short = ai_reasoning[:400] + ('...' if len(ai_reasoning) > 400 else '')
                parts.append(f'<b>Comentario IA:</b> {_h(reason_short)}')
            parts.append('')

        # Strategy checklist
        if reasoning:
            parts.append(f'<b>--- CHECKLIST ---</b>')
            for line in reasoning.split('\n'):
                if line.strip():
                    parts.append(_h(line.strip()))
            parts.append('')

        parts.append(f'<b>OPEN APP TO APPROVE OR REJECT</b>')

        body = '\n'.join(p for p in parts if p)

        data = {
            "instrument": instrument,
            "direction": direction,
            "entry": entry,
            "rr": rr,
            "strategy": strategy,
            "ai_score": ai_score,
        }
        await self.send_alert("setup_pending", title, body, data)

    async def send_setup_rejected(
        self,
        instrument: str,
        direction: str,
        strategy: str = "",
        ai_score: int = 0,
        ai_recommendation: str = "",
        ai_reasoning: str = "",
    ):
        """Notify user that a setup was rejected (manually or by quality gates).

        NOTE: As of 2026-04-17, IA does NOT reject setups (mentorship 0% discretion
        rule). This channel is kept for future manual/admin rejections. ai_* params
        are passed through as narrative context only, never as the reason.
        """
        if not self._config.notify_setup_rejected:
            return

        _instr = _h(instrument)
        _dir = _h(direction.upper())
        _strat = _h(strategy)
        _ai_reason = _h(ai_reasoning)
        title = f"SETUP REJECTED // {_instr}"
        body = (
            f'<span style="color:#1d1d1f;font-size:20px;font-weight:700;letter-spacing:-0.3px;">'
            f'{_instr}</span>\n'
            f'<span style="color:#86868b;">{_dir}</span> '
            f'<span style="color:#86868b;">// {_strat}</span>\n\n'
            f'<span style="color:#86868b;">Análisis IA (informativo):</span>\n'
            f'<span style="color:#86868b;">{_ai_reason}</span>'
        )
        data = {
            "instrument": instrument,
            "direction": direction,
            "strategy": strategy,
            "ai_score": ai_score,
            "ai_recommendation": ai_recommendation,
        }
        await self.send_alert("setup_rejected", title, body, data)

    async def send_setup_expired(
        self,
        instrument: str,
        direction: str,
        strategy: str = "",
        setup_id: str = "",
        expiry_minutes: int = 0,
    ):
        """Notify user that a pending setup timed out without action."""
        if not self._config.notify_setup_pending:
            return
        _instr = _h(instrument)
        _dir = _h(direction.upper())
        _strat = _h(strategy)
        title = f"SETUP EXPIRED // {_instr}"
        body = (
            f'<span style="color:#1d1d1f;font-size:20px;font-weight:700;letter-spacing:-0.3px;">'
            f'{_instr}</span>\n'
            f'<span style="color:#86868b;">{_dir}</span> '
            f'<span style="color:#86868b;">// {_strat}</span>\n\n'
            f'<span style="color:#FF9500;font-weight:600;">Expired</span> '
            f'<span style="color:#86868b;">after {expiry_minutes} min without approval</span>'
        )
        data = {
            "instrument": instrument,
            "direction": direction,
            "strategy": strategy,
            "setup_id": setup_id,
            "expiry_minutes": expiry_minutes,
        }
        await self.send_alert("setup_expired", title, body, data)

    async def send_trade_closed(
        self,
        instrument: str,
        pnl: float,
        pips: float,
        reason: str,
        strategy: str = "",
    ):
        if not self._config.notify_trade_closed:
            return

        pnl_color = "#34C759" if pnl >= 0 else "#FF3B30"
        result_label = "WIN" if pnl > 0 else ("BREAK EVEN" if pnl == 0 else "LOSS")
        sign = "+" if pnl >= 0 else ""
        _instr = _h(instrument)
        _strat = _h(strategy)
        _reason = _h(reason)
        title = f"TRADE CLOSED // {_instr}"
        body = (
            f'<span style="color:#1d1d1f;font-size:20px;font-weight:700;letter-spacing:-0.3px;">'
            f'{_instr}</span> '
            f'<span style="color:#86868b;">// {_strat}</span>\n\n'
            f'<span style="color:{pnl_color};font-size:22px;font-weight:700;">'
            f'{sign}${pnl:.2f}</span> '
            f'<span style="color:{pnl_color};font-size:13px;">{result_label}</span>\n'
            f'<span style="color:#86868b;">PIPS</span> '
            f'<span style="color:#1d1d1f;">{sign}{pips:.1f}</span>\n'
            f'<span style="color:#86868b;">REASON</span> '
            f'<span style="color:#1d1d1f;">{_reason}</span>'
        )
        data = {
            "instrument": instrument,
            "strategy": strategy,
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

        title = "Daily Summary"
        sign = "+" if total_pnl >= 0 else ""

        # Activity proof stats
        scans = stats.get("scans_completed", 0)
        setups_found = stats.get("setups_found", 0)
        setups_executed = stats.get("setups_executed", 0)
        setups_skipped = stats.get("setups_filtered", stats.get("setups_skipped_ai", 0))
        scan_errors = stats.get("scan_errors", 0)

        body = (
            f"<b>Date:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n\n"
            f"<b>--- Trading Results ---</b>\n"
            f"<b>Total P&L:</b> {sign}{total_pnl:.2f}\n"
            f"<b>Trades:</b> {trades}  |  "
            f"<b>Wins:</b> {wins}  |  <b>Losses:</b> {losses}\n"
            f"<b>Win Rate:</b> {win_rate:.1f}%\n"
            f"<b>Best:</b> {best}\n"
            f"<b>Worst:</b> {worst}\n\n"
            f"<b>--- Engine Activity (Proof of Life) ---</b>\n"
            f"<b>Scan cycles completed:</b> {scans}\n"
            f"<b>Setups found by strategies:</b> {setups_found}\n"
            f"<b>Setups executed:</b> {setups_executed}\n"
            f"<b>Setups filtered (score &lt; 50):</b> {setups_skipped}\n"
            f"<b>Scan errors:</b> {scan_errors}\n\n"
            f"<i>If scans > 0, the engine was alive and scanning all day.</i>"
        )
        await self.send_alert("daily_summary", title, body, stats)

    async def send_position_update(
        self,
        instrument: str,
        phase: str,
        current_sl: float,
        entry_price: float,
    ):
        """Notify about SL moves and phase changes on an open position."""
        title = f"Position Update: {instrument}"
        body = (
            f"<b>Instrument:</b> {instrument}\n"
            f"<b>Phase:</b> {phase}\n"
            f"<b>Current SL:</b> {current_sl}\n"
            f"<b>Entry Price:</b> {entry_price}"
        )
        data = {
            "instrument": instrument,
            "phase": phase,
            "current_sl": current_sl,
            "entry_price": entry_price,
        }
        await self.send_alert("position_update", title, body, data)

    async def send_engine_status(self, status: str, message: str):
        """Notify about engine start, stop, or error events."""
        title = f"Engine {status.capitalize()}"
        body = (
            f"<b>Status:</b> {status.upper()}\n"
            f"<b>Message:</b> {message}\n"
            f"<b>Time:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        data = {"status": status, "message": message}
        await self.send_alert("engine_status", title, body, data)

    async def send_risk_alert(
        self,
        alert_type: str,
        message: str,
        current_risk: float,
    ):
        """Notify about risk threshold warnings."""
        title = f"Risk Alert: {alert_type}"
        body = (
            f"<b>Alert Type:</b> {alert_type}\n"
            f"<b>Message:</b> {message}\n"
            f"<b>Current Risk:</b> {current_risk:.2f}%"
        )
        data = {
            "alert_type": alert_type,
            "message": message,
            "current_risk": current_risk,
        }
        await self.send_alert("risk_alert", title, body, data)

    # ── Test a single channel ────────────────────────────────────

    async def test_channel(self, channel: AlertChannel) -> bool:
        """Send a test message to *one* channel. Returns True on success."""
        title = "Test Notification"
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

        clean_body = _html_to_telegram(body)
        text = f"<b>{_strip_emoji_tags(title)}</b>\n\n{clean_body}"
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
                f"Telegram API returned {resp.status_code}"
            )
        logger.info("Telegram alert sent: {}", title)

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
            "footer": {"text": "Trading Dashboard"},
        }

        payload = {
            "username": "Trading Dashboard",
            "embeds": [embed],
        }

        resp = await self._get_http().post(url, json=payload)
        if resp.status_code not in (200, 204):
            raise RuntimeError(
                f"Discord webhook returned {resp.status_code}"
            )
        logger.info("Discord alert sent: {}", title)

    @staticmethod
    def _discord_colour_for_type(alert_type: str) -> int:
        colours = {
            "trade_executed": 0x00FF9D,   # green
            "setup_pending": 0xFFD700,    # gold
            "setup_rejected": 0xFB3048,   # red
            "trade_closed": 0x3498DB,     # blue
            "daily_summary": 0x9B59B6,    # purple
            "position_update": 0x9B59B6,  # purple
            "risk_alert": 0xFF6B6B,       # red/orange warning
            "engine_status": 0x3498DB,    # blue
            "orphaned_trade": 0xFF6B6B,   # red warning
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
        logger.info("Email alert sent: {}", plain_title)

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
        if not cfg.gmail_refresh_token or not cfg.gmail_client_id or not cfg.gmail_client_secret:
            logger.warning("Gmail alert skipped – missing OAuth2 credentials")
            return
        if not cfg.gmail_sender or not cfg.gmail_recipient:
            logger.warning("Gmail alert skipped – missing gmail_sender or gmail_recipient")
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

        # Send via Gmail API — retry once after forced refresh if token revoked (401/403)
        resp = await self._get_http().post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"raw": raw_message},
        )
        if resp.status_code in (401, 403):
            logger.warning(
                f"Gmail API returned {resp.status_code}; invalidating cached token and retrying"
            )
            # Force refresh on next _get_gmail_access_token call
            self._gmail_access_token = None
            self._gmail_token_expires_at = 0.0
            access_token = await self._get_gmail_access_token()
            if not access_token:
                raise RuntimeError("Gmail token refresh failed after 401 — check refresh token")
            resp = await self._get_http().post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"raw": raw_message},
            )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Gmail API returned {resp.status_code}"
            )
        logger.info("Gmail alert sent: {}", plain_title)

    async def _get_gmail_access_token(self) -> Optional[str]:
        """Return a cached access token, refreshing only when expired."""
        # Return cached token if still valid (100s safety margin before 3600s expiry)
        if self._gmail_access_token and time.time() < self._gmail_token_expires_at:
            return self._gmail_access_token

        # Serialize refresh attempts to prevent concurrent token races
        async with self._gmail_refresh_lock:
            # Re-check after acquiring lock (another coroutine may have refreshed)
            if self._gmail_access_token and time.time() < self._gmail_token_expires_at:
                return self._gmail_access_token

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
                try:
                    self._gmail_access_token = resp.json().get("access_token")
                except (ValueError, KeyError) as e:
                    logger.error(f"Gmail token refresh returned 200 but malformed JSON: {e}")
                    self._gmail_access_token = None
                    self._gmail_token_expires_at = 0.0
                    return None
                if not self._gmail_access_token:
                    logger.error("Gmail token refresh returned 200 but no access_token in response")
                    self._gmail_token_expires_at = 0.0
                    return None
                self._gmail_token_expires_at = time.time() + 3500  # cache for ~58 min
                logger.info("Gmail access token refreshed, expires in 3500s")
                return self._gmail_access_token

            logger.error("Gmail token refresh failed: status {}", resp.status_code)
            self._gmail_access_token = None
            self._gmail_token_expires_at = 0.0
            return None


# ── Text helpers (module-private) ────────────────────────────────

def _strip_emoji_tags(text: str) -> str:
    """Return *text* unchanged – emojis are plain Unicode and safe everywhere."""
    return text


def _html_to_telegram(html: str) -> str:
    """Strip tags unsupported by Telegram Bot API HTML mode.

    Telegram only supports: <b>, <i>, <u>, <s>, <code>, <pre>, <a>, <tg-spoiler>, <blockquote>.
    All <span> and style attributes must be stripped. Keep text content.
    """
    import re
    # Remove <span ...> opening tags (keep inner text)
    result = re.sub(r'<span[^>]*>', '', html)
    # Remove </span> closing tags
    result = result.replace('</span>', '')
    return result


def _html_to_discord_md(html: str) -> str:
    """Minimal HTML-to-Discord-Markdown conversion."""
    import re
    md = html
    # Strip <span> tags first (keep inner text)
    md = re.sub(r'<span[^>]*>', '', md)
    md = md.replace('</span>', '')
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
    """Wrap *body* in an Apple-style minimalist HTML email.

    Style: clean, white background, SF Pro font stack, generous whitespace,
    subtle gray borders, Apple system colors for accents.
    Inspired by apple.com communications and Apple Card notifications.

    Gmail dark mode: forced light-only color scheme so colors stay consistent.
    """
    body_html = body.replace("\n", "<br>\n")
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    return f"""\
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light only">
<meta name="supported-color-schemes" content="light only">
<title>Trading Dashboard</title>
<!--[if mso]><style>*{{font-family:'Segoe UI',Helvetica,Arial,sans-serif !important;}}</style><![endif]-->
<style>
  :root {{ color-scheme: light only; }}
  @media only screen and (max-width: 600px) {{
    .nt-outer {{ width: 100% !important; }}
    .nt-card {{ width: 100% !important; }}
    .nt-pad {{ padding-left: 20px !important; padding-right: 20px !important; }}
  }}
</style>
</head>
<body class="body" style="margin:0;padding:0;background-color:#f5f5f7;-webkit-text-size-adjust:100%;font-family:-apple-system,'SF Pro Display','Helvetica Neue',Helvetica,Arial,sans-serif;">
<u></u>
<div style="background-color:#f5f5f7;width:100%;margin:0;padding:0;">
<table role="presentation" class="nt-outer" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f5f5f7;">
<tr><td align="center" style="padding:32px 16px;">

<table role="presentation" class="nt-card" width="600" cellpadding="0" cellspacing="0"
       style="max-width:600px;width:100%;background-color:#ffffff;border-radius:16px;border-collapse:separate;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.06);">

  <!-- header -->
  <tr><td class="nt-pad" style="padding:32px 32px 0 32px;">
    <span style="font-family:-apple-system,'SF Pro Display','Helvetica Neue',Helvetica,Arial,sans-serif;font-size:12px;font-weight:600;color:#86868b;letter-spacing:0.5px;text-transform:uppercase;">
      Trading Dashboard</span>
  </td></tr>

  <!-- title -->
  <tr><td class="nt-pad" style="padding:8px 32px 16px 32px;">
    <span style="font-family:-apple-system,'SF Pro Display','Helvetica Neue',Helvetica,Arial,sans-serif;font-size:28px;font-weight:700;color:#1d1d1f;letter-spacing:-0.3px;line-height:1.15;">
      {title}</span>
  </td></tr>

  <!-- divider -->
  <tr><td class="nt-pad" style="padding:0 32px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr><td style="height:1px;background-color:#e5e5ea;font-size:0;">&nbsp;</td></tr>
    </table>
  </td></tr>

  <!-- body -->
  <tr><td class="nt-pad" style="padding:24px 32px 28px 32px;font-family:-apple-system,'SF Pro Text','Helvetica Neue',Helvetica,Arial,sans-serif;color:#1d1d1f;font-size:15px;line-height:1.7;font-weight:400;">
    {body_html}
  </td></tr>

  <!-- footer divider -->
  <tr><td class="nt-pad" style="padding:0 32px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr><td style="height:1px;background-color:#e5e5ea;font-size:0;">&nbsp;</td></tr>
    </table>
  </td></tr>

  <!-- footer -->
  <tr><td class="nt-pad" style="padding:16px 32px 24px 32px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="font-family:-apple-system,'SF Pro Text','Helvetica Neue',Helvetica,Arial,sans-serif;font-size:12px;font-weight:400;color:#aeaeb2;">
          Trading Dashboard</td>
        <td align="right" style="font-family:-apple-system,'SF Pro Text','Helvetica Neue',Helvetica,Arial,sans-serif;font-size:12px;font-weight:400;color:#aeaeb2;">
          {ts}</td>
      </tr>
    </table>
  </td></tr>

</table>

</td></tr>
</table>
</div>
</body>
</html>"""
