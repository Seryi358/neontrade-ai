"""
Atlas - Gmail OAuth2 Notifications Module.

Gmail is the only external notification channel in this deployment.
"""

import asyncio
import base64
import html
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from pathlib import Path
from typing import Dict, Optional

import httpx
from loguru import logger


CONFIG_PATH = Path(__file__).resolve().parent.parent / "data" / "alert_config.json"


def _h(val) -> str:
    if val is None:
        return ""
    return html.escape(str(val), quote=True)


def _normalize_dynamic_html(body: str) -> str:
    result = str(body or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not result:
        return ""
    result = re.sub(r"^\s*```(?:html)?\s*", "", result, flags=re.IGNORECASE)
    result = re.sub(r"\s*```\s*$", "", result)
    result = re.sub(r"(?is)<!DOCTYPE[^>]*>", "", result)
    result = re.sub(r"(?is)<head[^>]*>.*?</head>", "", result)
    result = re.sub(r"(?is)</?(?:html|body)[^>]*>", "", result)
    result = re.sub(r"(?i)<li[^>]*>\s*", "- ", result)
    result = re.sub(r"(?i)</li>\s*", "<br>", result)
    result = re.sub(r"(?i)</?(?:ul|ol)[^>]*>", "", result)
    result = re.sub(r"(?i)</?(?:p|div)[^>]*>", "<br>", result)
    result = re.sub(r"(?i)(<br\s*/?>\s*){3,}", "<br><br>", result)
    return result.strip()


def _body_to_email_html(body: str) -> str:
    normalized = _normalize_dynamic_html(body)
    if not normalized:
        return ""
    if re.search(r"<[a-z][^>]*>", normalized, flags=re.IGNORECASE):
        return normalized.replace("\n", "<br>\n")
    return html.escape(normalized, quote=False).replace("\n", "<br>\n")


def _html_to_plain(html_text: str) -> str:
    plain = _normalize_dynamic_html(html_text)
    plain = plain.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    plain = re.sub(r"<[^>]+>", "", plain)
    plain = html.unescape(plain)
    plain = re.sub(r"\n{3,}", "\n\n", plain)
    return plain.strip()


class AlertChannel(Enum):
    GMAIL = "gmail"


@dataclass
class AlertConfig:
    gmail_enabled: bool = False
    gmail_sender: str = ""
    gmail_recipient: str = ""
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""

    notify_trade_executed: bool = True
    notify_setup_pending: bool = True
    notify_setup_rejected: bool = True
    notify_trade_closed: bool = True
    notify_daily_summary: bool = True


_SENSITIVE_FIELDS = {"gmail_client_secret", "gmail_refresh_token"}


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "****"
    return "*" * (len(value) - 4) + value[-4:]


class AlertManager:
    """Manages Gmail OAuth2 notification delivery."""

    def __init__(self, config: Optional[AlertConfig] = None):
        self._config = config or AlertConfig()
        self._http: Optional[httpx.AsyncClient] = None
        self._gmail_access_token: Optional[str] = None
        self._gmail_token_expires_at: float = 0.0
        self._gmail_refresh_lock: asyncio.Lock = asyncio.Lock()
        if config is None:
            self._load_config()

    def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=15.0)
        return self._http

    async def close(self):
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()

    def _load_config(self):
        try:
            if CONFIG_PATH.exists():
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                for key, value in data.items():
                    if hasattr(self._config, key):
                        setattr(self._config, key, value)
                logger.info("Gmail alert config loaded from {}", CONFIG_PATH)
        except Exception as exc:
            logger.warning("Could not load Gmail alert config: {}", exc)

    def _save_config(self):
        try:
            import os
            import tempfile

            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(asdict(self._config), indent=2)
            fd, tmp_path = tempfile.mkstemp(dir=str(CONFIG_PATH.parent), suffix=".tmp")
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
        except Exception as exc:
            logger.warning("Could not save Gmail alert config: {}", exc)

    def update_config(self, config: AlertConfig):
        self._config = config
        self._save_config()

    def get_config(self) -> dict:
        raw = asdict(self._config)
        for field_name in _SENSITIVE_FIELDS:
            raw[field_name] = _mask(raw.get(field_name, ""))
        return raw

    async def send_alert(
        self,
        alert_type: str,
        title: str,
        body: str,
        data: Optional[dict] = None,
    ):
        if not self._config.gmail_enabled:
            logger.warning("Gmail alerts disabled - skipping '{}'", alert_type)
            return
        await self._safe_send(self._send_gmail(title, body))

    async def _safe_send(self, coro):
        try:
            await coro
        except Exception as exc:
            logger.error("Gmail alert send failed: {}", exc)

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
        body = (
            f"<b>Instrumento:</b> {_h(instrument)}\n"
            f"<b>Dirección:</b> {_h(direction.upper())}\n"
            f"<b>Estrategia:</b> {_h(strategy)}\n"
            f"<b>Entry:</b> {entry}\n"
            f"<b>SL:</b> {sl}\n"
            f"<b>TP:</b> {tp}\n"
            f"<b>R:R:</b> {rr:.2f}:1"
        )
        await self.send_alert("trade_executed", f"Trade Executed - {instrument}", body)

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
        parts = [
            "<b>Setup detectado</b>",
            f"<b>Instrumento:</b> {_h(instrument)}",
            f"<b>Dirección:</b> {_h(direction.upper())}",
            f"<b>Estrategia:</b> {_h(strategy)}" if strategy else "",
            f"<b>Entry:</b> {entry:.5f}",
            f"<b>SL:</b> {sl:.5f}" if sl else "",
            f"<b>TP:</b> {tp:.5f}" if tp else "",
            f"<b>R:R:</b> {rr:.2f}:1",
        ]
        if ai_score or ai_reasoning:
            parts.extend([
                "",
                "<b>IA informativa, no decisoria</b>",
                f"<b>Opinión IA:</b> {_h(ai_recommendation)}" if ai_recommendation else "",
                _h(ai_reasoning[:400] + ("..." if len(ai_reasoning) > 400 else "")) if ai_reasoning else "",
            ])
        if reasoning:
            parts.append("")
            parts.append("<b>Checklist TradingLab</b>")
            parts.extend(_h(line.strip()) for line in reasoning.split("\n") if line.strip())
        await self.send_alert("setup_pending", f"Setup Detected - {instrument}", "\n".join(p for p in parts if p))

    async def send_setup_rejected(
        self,
        instrument: str,
        direction: str,
        strategy: str = "",
        ai_score: int = 0,
        ai_recommendation: str = "",
        ai_reasoning: str = "",
    ):
        if not self._config.notify_setup_rejected:
            return
        body = (
            f"<b>Instrumento:</b> {_h(instrument)}\n"
            f"<b>Dirección:</b> {_h(direction.upper())}\n"
            f"<b>Estrategia:</b> {_h(strategy)}\n"
            f"<b>Contexto:</b> {_h(ai_reasoning)}"
        )
        await self.send_alert("setup_rejected", f"Setup Rejected - {instrument}", body)

    async def send_setup_expired(
        self,
        instrument: str,
        direction: str,
        strategy: str = "",
        setup_id: str = "",
        expiry_minutes: int = 0,
    ):
        if not self._config.notify_setup_pending:
            return
        body = (
            f"<b>Instrumento:</b> {_h(instrument)}\n"
            f"<b>Dirección:</b> {_h(direction.upper())}\n"
            f"<b>Estrategia:</b> {_h(strategy)}\n"
            f"<b>Expiró después de:</b> {expiry_minutes} min"
        )
        await self.send_alert("setup_expired", f"Setup Expired - {instrument}", body)

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
        sign = "+" if pnl >= 0 else ""
        body = (
            f"<b>Instrumento:</b> {_h(instrument)}\n"
            f"<b>Estrategia:</b> {_h(strategy)}\n"
            f"<b>P&L:</b> {sign}${pnl:.2f}\n"
            f"<b>Pips:</b> {sign}{pips:.1f}\n"
            f"<b>Razón:</b> {_h(reason)}"
        )
        await self.send_alert("trade_closed", f"Trade Closed - {instrument}", body)

    async def send_daily_summary(self, stats: dict):
        if not self._config.notify_daily_summary:
            return
        total_pnl = stats.get("total_pnl", 0.0)
        trades = stats.get("trades_count", 0)
        wins = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        scans = stats.get("scans_completed", 0)
        setups_found = stats.get("setups_found", 0)
        setups_executed = stats.get("setups_executed", 0)
        scan_errors = stats.get("scan_errors", 0)
        win_rate = (wins / trades * 100) if trades else 0.0
        sign = "+" if total_pnl >= 0 else ""
        body = (
            f"<b>Fecha:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
            f"<b>Total P&L:</b> {sign}{total_pnl:.2f}\n"
            f"<b>Trades:</b> {trades} | <b>Wins:</b> {wins} | <b>Losses:</b> {losses}\n"
            f"<b>Win rate:</b> {win_rate:.1f}%\n\n"
            f"<b>Actividad del engine</b>\n"
            f"<b>Scans:</b> {scans}\n"
            f"<b>Setups encontrados:</b> {setups_found}\n"
            f"<b>Setups ejecutados:</b> {setups_executed}\n"
            f"<b>Errores:</b> {scan_errors}"
        )
        await self.send_alert("daily_summary", "Daily Summary", body)

    async def send_position_update(
        self,
        instrument: str,
        phase: str,
        current_sl: float,
        entry_price: float,
    ):
        body = (
            f"<b>Instrumento:</b> {_h(instrument)}\n"
            f"<b>Fase:</b> {_h(phase)}\n"
            f"<b>SL actual:</b> {current_sl}\n"
            f"<b>Entry:</b> {entry_price}"
        )
        await self.send_alert("position_update", f"Position Update - {instrument}", body)

    async def send_engine_status(self, status: str, message: str):
        body = (
            f"<b>Status:</b> {_h(status.upper())}\n"
            f"<b>Mensaje:</b> {_h(message)}\n"
            f"<b>Hora:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        await self.send_alert("engine_status", f"Engine {status.capitalize()}", body)

    async def send_risk_alert(
        self,
        alert_type: str,
        message: str,
        current_risk: float,
    ):
        body = (
            f"<b>Tipo:</b> {_h(alert_type)}\n"
            f"<b>Mensaje:</b> {_h(message)}\n"
            f"<b>Riesgo actual:</b> {current_risk:.2f}%"
        )
        await self.send_alert("risk_alert", f"Risk Alert - {alert_type}", body)

    async def test_channel(self, channel: AlertChannel) -> bool:
        if channel != AlertChannel.GMAIL:
            return False
        cfg = self._config
        if not (
            cfg.gmail_refresh_token
            and cfg.gmail_client_id
            and cfg.gmail_client_secret
            and cfg.gmail_sender
            and cfg.gmail_recipient
        ):
            logger.warning("Gmail test skipped - incomplete Gmail config")
            return False
        try:
            await self._send_gmail(
                "Test Notification",
                f"Gmail OAuth2 configurado correctamente.\n\nUTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}",
            )
            return True
        except Exception as exc:
            logger.error("Gmail test failed: {}", exc)
            return False

    async def _send_gmail(self, title: str, body: str):
        cfg = self._config
        if not cfg.gmail_sender or not cfg.gmail_recipient:
            logger.warning("Gmail alert skipped - missing sender or recipient")
            return
        html_body = _build_email_html(title, body)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = title
        msg["From"] = cfg.gmail_sender
        msg["To"] = cfg.gmail_recipient
        msg.attach(MIMEText(_html_to_plain(body), "plain"))
        msg.attach(MIMEText(html_body, "html"))
        raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

        access_token = await self._get_gmail_access_token()
        if not access_token:
            raise RuntimeError("Failed to obtain Gmail access token")

        resp = await self._get_http().post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"raw": raw_message},
        )
        if resp.status_code in (401, 403):
            self._gmail_access_token = None
            self._gmail_token_expires_at = 0.0
            access_token = await self._get_gmail_access_token()
            if not access_token:
                raise RuntimeError("Gmail token refresh failed after auth error")
            resp = await self._get_http().post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"raw": raw_message},
            )
        if resp.status_code != 200:
            raise RuntimeError(f"Gmail API returned {resp.status_code}")
        logger.info("Gmail alert sent: {}", title)

    async def _get_gmail_access_token(self) -> Optional[str]:
        if self._gmail_access_token and time.time() < self._gmail_token_expires_at:
            return self._gmail_access_token

        async with self._gmail_refresh_lock:
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
            if resp.status_code != 200:
                logger.error("Gmail token refresh failed: status {}", resp.status_code)
                self._gmail_access_token = None
                self._gmail_token_expires_at = 0.0
                return None
            try:
                self._gmail_access_token = resp.json().get("access_token")
            except (ValueError, KeyError) as exc:
                logger.error("Gmail token refresh returned malformed JSON: {}", exc)
                self._gmail_access_token = None
                self._gmail_token_expires_at = 0.0
                return None
            if not self._gmail_access_token:
                logger.error("Gmail token refresh returned no access token")
                self._gmail_token_expires_at = 0.0
                return None
            self._gmail_token_expires_at = time.time() + 3500
            return self._gmail_access_token


def _build_email_html(title: str, body: str) -> str:
    body_html = _body_to_email_html(body)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""\
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light only">
<title>Atlas</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f7;font-family:-apple-system,'SF Pro Display','Helvetica Neue',Arial,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f7;">
<tr><td align="center" style="padding:32px 16px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:rgba(255,255,255,0.92);border:1px solid #e5e5ea;border-radius:18px;overflow:hidden;">
<tr><td style="padding:30px 32px 8px 32px;color:#86868b;font-size:12px;font-weight:600;letter-spacing:0.5px;text-transform:uppercase;">Atlas</td></tr>
<tr><td style="padding:0 32px 18px 32px;color:#1d1d1f;font-size:26px;font-weight:700;line-height:1.15;">{_h(title)}</td></tr>
<tr><td style="padding:0 32px;"><div style="height:1px;background:#e5e5ea;"></div></td></tr>
<tr><td style="padding:24px 32px 28px 32px;color:#1d1d1f;font-size:15px;line-height:1.7;">{body_html}</td></tr>
<tr><td style="padding:0 32px;"><div style="height:1px;background:#e5e5ea;"></div></td></tr>
<tr><td style="padding:16px 32px 24px 32px;color:#aeaeb2;font-size:12px;">{ts}</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""
