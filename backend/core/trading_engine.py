"""
Atlas - Trading Engine
Main orchestrator that ties everything together.

Flow:
1. Scan watchlist on schedule (every 2 minutes during market hours)
2. Run multi-timeframe analysis on each pair
3. Detect strategy setups (BLACK, BLUE, RED, GREEN, WHITE)
4. Validate risk management
5. Execute trades (AUTO) or queue for approval (MANUAL)
6. Manage open positions
7. Handle Friday close / news avoidance
"""

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import List, Optional, Dict, Callable
from dataclasses import dataclass, field, asdict
from loguru import logger

from core.risk_manager import RiskManager, TradingStyle, TradeRisk
from core.position_manager import PositionManager, ManagedPosition, PositionPhase
from core.market_analyzer import MarketAnalyzer, AnalysisResult, Trend
from core.explanation_engine import ExplanationEngine, StrategyExplanation
from core.news_filter import NewsFilter
from core.trade_journal import TradeJournal
from strategies.base import get_best_setup, SetupSignal
from config import settings, get_active_watchlist
from core.resilience import broker_circuit_breaker

try:
    from core.alerts import AlertManager, AlertConfig
    _ALERTS_AVAILABLE = True
except ImportError:
    _ALERTS_AVAILABLE = False

try:
    from ai.openai_analyzer import OpenAIAnalyzer
    _AI_AVAILABLE = bool(settings.openai_api_key)
except ImportError:
    _AI_AVAILABLE = False

try:
    from core.scalping_engine import ScalpingAnalyzer, ScalpingData
    _SCALPING_AVAILABLE = True
except ImportError:
    _SCALPING_AVAILABLE = False

try:
    from core.screenshot_generator import TradeScreenshotGenerator
    _SCREENSHOTS_AVAILABLE = True
except ImportError:
    _SCREENSHOTS_AVAILABLE = False

try:
    from core.monthly_review import MonthlyReviewGenerator
    _MONTHLY_REVIEW_AVAILABLE = True
except ImportError:
    _MONTHLY_REVIEW_AVAILABLE = False


# ── Trading Mode ──────────────────────────────────────────────────

class TradingMode(Enum):
    """Trading execution mode."""
    AUTO = "AUTO"       # Executes trades automatically
    MANUAL = "MANUAL"   # Detects setups but queues them for user approval


@dataclass
class PendingSetup:
    """A detected setup waiting for user approval in MANUAL mode."""
    id: str
    timestamp: str
    instrument: str
    strategy: str
    direction: str  # "BUY" or "SELL"
    entry_price: float
    stop_loss: float
    take_profit: float
    units: float  # float for crypto fractional lots (e.g. 0.001 BTC)
    confidence: float
    risk_reward_ratio: float
    reasoning: str  # Spanish explanation
    take_profit_max: Optional[float] = None  # Extended TP for HTF "run" context
    trailing_tp_only: bool = False  # True for crypto GREEN: use EMA 50 trailing, not hard TP1
    strategy_variant: Optional[str] = None  # e.g. "GREEN", "BLUE_A", "RED"
    status: str = "pending"  # "pending", "approved", "rejected", "expired"
    expires_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _create_broker():
    """Create the active broker based on config."""
    if settings.active_broker == "ibkr":
        from broker.ibkr_client import IBKRClient
        return IBKRClient(
            consumer_key=settings.ibkr_consumer_key,
            access_token=settings.ibkr_access_token,
            access_token_secret=settings.ibkr_access_token_secret,
            keys_dir=settings.ibkr_keys_dir,
            environment=settings.ibkr_environment,
        )
    elif settings.active_broker == "capital":
        from broker.capital_client import CapitalClient
        return CapitalClient(
            api_key=settings.capital_api_key,
            password=settings.capital_password,
            identifier=settings.capital_identifier,
            environment=settings.capital_environment,
            account_id=settings.capital_account_id or None,
        )
    else:
        raise ValueError(f"Unsupported broker: {settings.active_broker}. Supported: 'capital', 'ibkr'")


class TradingEngine:
    """Main trading engine - the brain of Atlas."""

    def __init__(self):
        self.broker = _create_broker()
        self.risk_manager = RiskManager(self.broker)
        self.position_manager = PositionManager(
            self.broker,
            risk_manager=self.risk_manager,
            management_style=settings.position_management_style,
            trading_style=settings.trading_style,
            allow_partial_profits=settings.allow_partial_profits,
        )

        # OpenAI analyzer for AI-enhanced trade validation
        if _AI_AVAILABLE:
            self.ai_analyzer = OpenAIAnalyzer()
            logger.info("OpenAI analyzer initialized (AI-enhanced trading active)")
        else:
            self.ai_analyzer = None
            logger.warning("OpenAI analyzer not available — trading without AI validation")
        self.market_analyzer = MarketAnalyzer(self.broker)
        self.explanation_engine = ExplanationEngine()
        # R30 fix: scan lock prevents overlapping scan cycles (duplicate trades)
        self._scan_lock = asyncio.Lock()
        from core.news_filter import TradingStyle as NFTradingStyle
        news_style = NFTradingStyle.SCALPING if settings.scalping_enabled else NFTradingStyle.DAY_TRADING
        self.news_filter = NewsFilter(
            trading_style=news_style,
            finnhub_key=getattr(settings, 'finnhub_api_key', ''),
            newsapi_key=getattr(settings, 'newsapi_key', ''),
        )

        # Alert manager (Telegram, Discord, Email, Gmail OAuth2)
        if _ALERTS_AVAILABLE:
            # Auto-enable each channel if credentials are configured
            tg_token = getattr(settings, 'telegram_bot_token', '')
            tg_chat = getattr(settings, 'telegram_chat_id', '')
            discord_url = getattr(settings, 'discord_webhook_url', '')
            email_user = getattr(settings, 'alert_email_username', '')
            email_pass = getattr(settings, 'alert_email_password', '')
            email_recip = getattr(settings, 'alert_email_recipient', '')
            gmail_refresh = getattr(settings, 'gmail_refresh_token', '')
            gmail_cid = getattr(settings, 'gmail_client_id', '')
            gmail_secret = getattr(settings, 'gmail_client_secret', '')
            gmail_sender = getattr(settings, 'gmail_sender', '')
            gmail_recipient = getattr(settings, 'gmail_recipient', '') or gmail_sender

            alert_cfg = AlertConfig(
                telegram_enabled=bool(tg_token and tg_chat),
                telegram_bot_token=tg_token,
                telegram_chat_id=tg_chat,
                discord_enabled=bool(discord_url),
                discord_webhook_url=discord_url,
                email_enabled=bool(email_user and email_pass and email_recip),
                email_smtp_server=getattr(settings, 'alert_email_smtp_server', 'smtp.gmail.com'),
                email_smtp_port=getattr(settings, 'alert_email_smtp_port', 587),
                email_username=email_user,
                email_password=email_pass,
                email_recipient=email_recip,
                # Require ALL 5 OAuth fields so _send_gmail() never reaches the "skipped"
                # warning at runtime for a partially-configured channel.
                gmail_enabled=bool(gmail_refresh and gmail_cid and gmail_secret and gmail_sender and gmail_recipient),
                gmail_sender=gmail_sender,
                gmail_recipient=gmail_recipient,
                gmail_client_id=gmail_cid,
                gmail_client_secret=gmail_secret,
                gmail_refresh_token=gmail_refresh,
            )
            self.alert_manager = AlertManager(alert_cfg)
            channels = []
            if alert_cfg.gmail_enabled:
                channels.append("Gmail")
            if alert_cfg.telegram_enabled:
                channels.append("Telegram")
            if alert_cfg.discord_enabled:
                channels.append("Discord")
            if alert_cfg.email_enabled:
                channels.append("Email/SMTP")
            if channels:
                logger.info("Alert channels enabled: {}", ", ".join(channels))
            else:
                logger.warning("No alert channels configured — notifications disabled")
        else:
            self.alert_manager = None

        # Trading mode — Sergio's preference is AUTO (changed default 2026-04-22).
        # Engine init reads settings.engine_mode (loaded from data/risk_config.json)
        # so persisted overrides win; falls back to AUTO if absent or invalid.
        _persisted_mode = (getattr(settings, "engine_mode", "AUTO") or "AUTO").upper()
        try:
            self.mode: TradingMode = TradingMode(_persisted_mode)
        except ValueError:
            self.mode = TradingMode.AUTO
            logger.warning(f"Invalid persisted engine_mode={_persisted_mode!r}; falling back to AUTO")
        self.pending_setups: List[PendingSetup] = []
        self._setup_expiry_minutes: int = 30  # Configurable expiry

        # Strategy selection (persisted in data/strategy_config.json)
        self._strategy_config_path = os.path.join("data", "strategy_config.json")
        self._enabled_strategies: Dict[str, bool] = self._load_strategy_config()

        # Internal state
        self._running = False
        # Background-task registry: strong refs to fire-and-forget tasks so the
        # event loop's weak references don't let them GC mid-run.
        # Tasks auto-remove via add_done_callback.
        self._background_tasks: set = set()
        self._scan_interval = 120  # seconds (2 minutes)
        self._pre_scalping_interval: int = self._scan_interval  # saved before scalping
        self._last_scan_results: Dict[str, AnalysisResult] = {}
        self._latest_explanations: Dict[str, StrategyExplanation] = {}
        self._startup_error: str = ""  # Last broker connection error (for diagnostics)

        # WebSocket broadcast callback (set externally when WS is connected)
        self._ws_broadcast: Optional[Callable] = None

        # Database reference (injected by main.py after DB init)
        self._db = None

        # Trade journal (initialized with actual balance in start())
        self.trade_journal: Optional[TradeJournal] = None

        # Screenshot generator (Trading Plan: "Take screenshots of every executed trade")
        self.screenshot_generator = TradeScreenshotGenerator() if _SCREENSHOTS_AVAILABLE else None

        # Monthly review generator
        self.monthly_review = MonthlyReviewGenerator() if _MONTHLY_REVIEW_AVAILABLE else None

        # Notification queue for Electron native notifications
        self._notifications: List[Dict] = []
        self._max_notifications = 100

        # Equity snapshot tracking (record every 10 minutes)
        self._last_equity_snapshot: datetime = datetime.min.replace(tzinfo=timezone.utc)

        # Reentry tracking: instrument -> {"tp1_time": datetime, "direction": str, "count": int}
        # TradingLab (Esp. Criptomonedas Section 9 + Avanzado position management):
        # Reentries allowed up to 3 times with PROGRESSIVE risk reduction:
        #   Reentry 1: 50% of normal risk (1% -> 0.5%)
        #   Reentry 2: 25% of normal risk (1% -> 0.25%)
        #   Reentry 3: 25% of normal risk (minimum floor)
        # Alex: "necesitas 6 meses de experiencia antes de reentrar"
        self._reentry_candidates: Dict[str, Dict] = {}
        self._max_reentries_per_setup: int = settings.max_reentries_per_setup

        # Daily activity counters (reset each day) — proves the app was alive
        self._daily_scan_count: int = 0
        self._daily_setups_found: int = 0
        self._daily_setups_executed: int = 0
        self._daily_setups_filtered: int = 0
        self._daily_errors: int = 0
        self._daily_counter_date: str = ""  # YYYY-MM-DD of current counters

        # Overtrading / revenge trading prevention (Psicología Avanzada)
        self._consecutive_losses_today: int = 0
        self._last_loss_time: Optional[datetime] = None

        # ── Scalping Module (Workshop de Scalping) ──
        self.scalping_analyzer: Optional['ScalpingAnalyzer'] = None
        if settings.scalping_enabled and _SCALPING_AVAILABLE:
            self.scalping_analyzer = ScalpingAnalyzer(self.broker)
            self._scan_interval = 30  # 30s for scalping (faster than 120s day trading)
            logger.info(f"Scalping module ENABLED — scan interval {self._scan_interval}s, compressed timeframes active")
        elif settings.scalping_enabled and not _SCALPING_AVAILABLE:
            logger.warning("Scalping enabled in config but module not available")

        # Scalping drawdown tracking
        self._scalping_daily_dd: float = 0.0  # Today's scalping P&L as fraction of balance
        self._scalping_dd_date: str = ""       # YYYY-MM-DD for daily DD reset
        self._scalping_total_dd: float = 0.0   # Total scalping drawdown from peak
        self._scalping_peak_balance: float = 0.0  # Peak balance for total DD calc
        # Scalping scan interval: 30 seconds (faster than normal 120s)
        self._scalping_scan_interval: int = 30

    # ── Public accessors for internal state ─────────────────────────

    @property
    def running(self) -> bool:
        return self._running

    @property
    def startup_error(self) -> str:
        return self._startup_error

    @startup_error.setter
    def startup_error(self, value: str):
        self._startup_error = value

    @property
    def last_scan_results(self) -> Dict[str, 'AnalysisResult']:
        return self._last_scan_results

    @property
    def latest_explanations(self) -> Dict[str, 'StrategyExplanation']:
        return self._latest_explanations

    @property
    def scan_interval(self) -> int:
        return self._scan_interval

    # ── Notifications ──────────────────────────────────────────────

    def _push_notification(self, notif_type: str, title: str, body: str, data: dict = None):
        """Add a notification to the queue for Electron to consume."""
        notif = {
            "id": str(uuid.uuid4()),
            "type": notif_type,
            "title": title,
            "body": body,
            "data": data or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "read": False,
        }
        self._notifications.append(notif)
        # Trim old notifications
        if len(self._notifications) > self._max_notifications:
            self._notifications = self._notifications[-self._max_notifications:]
        logger.warning(f"Notification: [{notif_type}] {title} — {body}")

    def get_unread_notifications(self) -> List[Dict]:
        """Get and mark as read all unread notifications."""
        unread = [n for n in self._notifications if not n["read"]]
        for n in unread:
            n["read"] = True
        return unread

    # ── Strategy Selection ────────────────────────────────────────

    # TradingLab: start with BLUE + RED only. "La BLUE es la más fácil de
    # ejecutar" and "La RED es la más fácil y sencilla de operar".
    # Enable PINK, WHITE, BLACK, GREEN only after mastering BLUE + RED.
    # BLUE_A is the most effective (highest win rate), BLUE_B most common.
    _DEFAULT_STRATEGY_CONFIG: Dict[str, bool] = {
        "BLUE": True, "BLUE_A": True, "BLUE_B": True, "BLUE_C": True,
        "RED": True,
        "PINK": False, "WHITE": False, "BLACK": False, "GREEN": False,
    }

    def _load_strategy_config(self) -> Dict[str, bool]:
        """Load strategy config from JSON file, or return defaults."""
        try:
            if os.path.exists(self._strategy_config_path):
                with open(self._strategy_config_path, "r") as f:
                    config = json.load(f)
                logger.info(f"Loaded strategy config: {config}")
                return config
        except Exception as e:
            logger.warning(f"Failed to load strategy config: {e}")
        return dict(self._DEFAULT_STRATEGY_CONFIG)

    def _save_strategy_config(self):
        """Persist strategy config to JSON file (atomic write)."""
        try:
            import tempfile
            dir_name = os.path.dirname(self._strategy_config_path)
            os.makedirs(dir_name, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(self._enabled_strategies, f, indent=2)
                os.replace(tmp_path, self._strategy_config_path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            logger.info(f"Strategy config saved: {self._enabled_strategies}")
        except Exception as e:
            logger.error(f"Failed to save strategy config: {e}")

    def get_enabled_strategies(self) -> Dict[str, bool]:
        """Get current strategy enablement map."""
        return dict(self._enabled_strategies)

    def set_enabled_strategies(self, config: Dict[str, bool]):
        """Update enabled strategies and persist."""
        # Merge with defaults so all keys are present
        merged = dict(self._DEFAULT_STRATEGY_CONFIG)
        for key, value in config.items():
            if key in merged:
                merged[key] = bool(value)
        self._enabled_strategies = merged
        self._save_strategy_config()

        enabled = [k for k, v in merged.items() if v]
        logger.info(f"Strategies updated. Enabled: {enabled}")

    # ── Mode Management ───────────────────────────────────────────

    def set_mode(self, mode):
        """Switch between AUTO and MANUAL trading modes."""
        old_mode = self.mode
        if isinstance(mode, str):
            mode = TradingMode(mode)
        self.mode = mode
        logger.info(f"Trading mode changed: {old_mode.value} -> {mode.value}")
        if mode == TradingMode.AUTO and old_mode == TradingMode.MANUAL:
            logger.info(
                f"{len(self.pending_setups)} pending setups remain from MANUAL mode"
            )

    def toggle_scalping(self, enabled: bool):
        """Enable or disable scalping mode at runtime."""
        was_enabled = self._scan_interval == self._scalping_scan_interval
        settings.scalping_enabled = enabled
        if enabled and _SCALPING_AVAILABLE:
            if self.scalping_analyzer is None:
                self.scalping_analyzer = ScalpingAnalyzer(self.broker)
            # Only save the pre-scalping interval on an actual off->on transition,
            # otherwise a no-op toggle-on would overwrite it with the scalping value.
            if not was_enabled:
                self._pre_scalping_interval = self._scan_interval
            self._scan_interval = self._scalping_scan_interval
            logger.info(
                f"Scalping ENABLED — scan interval set to {self._scalping_scan_interval}s"
            )
        else:
            # Restore the scan interval that was active before scalping was enabled
            self._scan_interval = self._pre_scalping_interval
            if not enabled:
                logger.info(f"Scalping DISABLED — scan interval restored to {self._pre_scalping_interval}s")

    def get_pending_setups(self) -> List[dict]:
        """Get all pending (non-expired) setups as dicts."""
        self._expire_old_setups()
        return [
            s.to_dict() for s in self.pending_setups
            if s.status == "pending"
        ]

    _approve_lock: asyncio.Lock = None  # Initialized lazily

    async def approve_setup(self, setup_id: str) -> bool:
        """Approve and execute a pending setup by ID. Thread-safe against double approval."""
        if self._approve_lock is None:
            self._approve_lock = asyncio.Lock()
        async with self._approve_lock:
            self._expire_old_setups()
            for setup in self.pending_setups:
                if setup.id == setup_id and setup.status == "pending":
                    # Check risk limits before approving — per-instrument style
                    # so equities can use SWING when swing_for_equities is on.
                    current_style = self._style_for_instrument(setup.instrument)
                    if not self.risk_manager.can_take_trade(current_style, setup.instrument):
                        logger.warning(f"Setup {setup_id} rejected: max risk limit or scale-in rule")
                        return False
                    try:
                        setup.status = "approved"
                        logger.info(f"Setup approved: {setup_id} | {setup.instrument} {setup.direction}")
                        await self._execute_approved_setup(setup)
                        return True
                    except Exception as e:
                        logger.error(f"Setup {setup_id} execution failed: {e}")
                        # Preserve terminal states (expired, rejected, error,
                        # executed). Only revert if _execute_approved_setup
                        # left the status at "approved" — i.e., broker call
                        # itself raised before the inner flow marked a
                        # concrete terminal state.
                        if setup.status == "approved":
                            setup.status = "pending"
                        return False
            logger.warning(f"Setup not found or not pending: {setup_id}")
            return False

    def reject_setup(self, setup_id: str) -> bool:
        """Reject and remove a pending setup by ID."""
        for setup in self.pending_setups:
            if setup.id == setup_id and setup.status == "pending":
                setup.status = "rejected"
                logger.info(f"Setup rejected: {setup_id} | {setup.instrument}")
                return True
        logger.warning(f"Setup not found or not pending: {setup_id}")
        return False

    async def approve_all_pending(self) -> int:
        """Approve and execute all pending setups. Returns count approved.
        Checks risk limits before each execution to avoid breaching max risk."""
        if self._approve_lock is None:
            self._approve_lock = asyncio.Lock()
        async with self._approve_lock:
            return await self._approve_all_pending_locked()

    async def _approve_all_pending_locked(self) -> int:
        """Inner implementation — must be called under _approve_lock."""
        self._expire_old_setups()
        pending = [s for s in self.pending_setups if s.status == "pending"]
        count = 0
        for setup in pending:
            # Per-instrument style so equity trades go through SWING when enabled.
            current_style = self._style_for_instrument(setup.instrument)
            if not self.risk_manager.can_take_trade(current_style, setup.instrument):
                logger.warning(f"Skipping setup {setup.id} ({setup.instrument}): max risk limit reached")
                continue
            setup.status = "approved"
            try:
                await self._execute_approved_setup(setup)
                count += 1
            except Exception as e:
                logger.error(f"Failed to execute approved setup {setup.id}: {e}")
                # Only revert if inner flow hadn't already set a terminal
                # state (expired/rejected/error/executed).
                if setup.status == "approved":
                    setup.status = "pending"
        logger.info(f"Approved and executed {count}/{len(pending)} pending setups")
        return count

    @staticmethod
    def _style_for_instrument(instrument: str) -> TradingStyle:
        """Resolve the trading style for ``instrument`` honoring per-asset-class
        overrides.

        Mentoría audit C1 (Watchlist para Acciones): Alex says he does SWING
        trading on US equities, not day trading. When ``swing_for_equities``
        is True and the instrument lives in the equities watchlist, force
        SWING regardless of the global ``trading_style``. Falls back to the
        configured global style for everything else.
        """
        style_map = {
            "day_trading": TradingStyle.DAY_TRADING,
            "swing": TradingStyle.SWING,
            "scalping": TradingStyle.SCALPING,
        }
        base = style_map.get(settings.trading_style, TradingStyle.DAY_TRADING)
        if getattr(settings, "swing_for_equities", False):
            try:
                if instrument in settings.equities_watchlist:
                    return TradingStyle.SWING
            except Exception:
                pass
        return base

    def _spawn_bg(self, coro, name: str = "") -> None:
        """Start a fire-and-forget coroutine with GC-safe strong reference.

        Python's event loop only holds weak refs to tasks, so naked
        asyncio.create_task(coro()) can be collected mid-run under memory
        pressure. We hold a strong ref in self._background_tasks until the
        task finishes, then remove it via done_callback.
        """
        try:
            task = asyncio.create_task(coro, name=name) if name else asyncio.create_task(coro)
        except RuntimeError:
            # No running loop (called from sync context) — drop silently.
            # The coroutine object won't be awaited; suppress the warning.
            try:
                coro.close()
            except Exception:
                pass
            return
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _expire_old_setups(self):
        """Mark setups past their expiry time as expired, and prune old non-pending setups."""
        now = datetime.now(timezone.utc)
        newly_expired = []
        for setup in self.pending_setups:
            if setup.status != "pending":
                continue
            if setup.expires_at:
                try:
                    expires = datetime.fromisoformat(setup.expires_at)
                    if expires.tzinfo is None:
                        expires = expires.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    expires = now  # Force expiry on unparseable dates
                if now >= expires:
                    setup.status = "expired"
                    newly_expired.append(setup)
                    logger.info(
                        f"Setup expired: {setup.id} | {setup.instrument} "
                        f"(after {self._setup_expiry_minutes} min)"
                    )
        # Prune: keep only pending setups + last 20 non-pending (prevent memory leak)
        pending = [s for s in self.pending_setups if s.status == "pending"]
        finished = [s for s in self.pending_setups if s.status != "pending"]
        self.pending_setups = pending + finished[-20:]

        # Notify user about silently expired setups so MANUAL-mode users don't
        # miss the window without warning. Fire-and-forget so the sync loop
        # isn't blocked by gmail/WS latency.
        if newly_expired and (self.alert_manager or self._ws_broadcast):
            async def _notify_expired(items=newly_expired):
                for s in items:
                    if self.alert_manager:
                        try:
                            await self.alert_manager.send_setup_expired(
                                instrument=s.instrument,
                                direction=s.direction,
                                strategy=getattr(s, "_strategy_name", "") or "",
                                setup_id=s.id,
                                expiry_minutes=self._setup_expiry_minutes,
                            )
                        except Exception as ae:
                            logger.warning(f"Expired-setup alert failed for {s.id}: {ae}")
                    if self._ws_broadcast:
                        try:
                            await self._ws_broadcast("setup_expired", {
                                "setup_id": s.id,
                                "instrument": s.instrument,
                                "direction": s.direction,
                                "reason": "expiry_timeout",
                            })
                        except Exception as we:
                            logger.warning(f"WS broadcast setup_expired failed for {s.id}: {we}")
            self._spawn_bg(_notify_expired(), name="notify_expired_setups")

    # ── Main Loop ────────────────────────────────────────────────

    async def start(self):
        """Start the trading engine."""
        # Prevent parallel start() calls from creating duplicate broker
        # connections or contesting risk_manager initialization. The /engine
        # /start HTTP endpoint already guards via 'if not engine.running',
        # but start() can also be re-invoked from lifespan or tests.
        if self._running:
            logger.warning("Trading engine already running — start() call ignored")
            return

        logger.info("=" * 60)
        logger.info("  Atlas - Trading Engine Starting")
        logger.info(f"  Mode: {self.mode.value}")
        logger.info("=" * 60)

        # Validate connection (retry up to 5 times with exponential backoff)
        max_retries = 5
        retry_delay = 10
        connected = False
        for attempt in range(1, max_retries + 1):
            try:
                summary = await self.broker.get_account_summary()
                balance = summary.balance
                currency = summary.currency
                broker_name = self.broker.broker_type.value.upper()
                logger.info(f"Connected to {broker_name} | Balance: {balance} {currency}")
                logger.info(f"Broker: {broker_name} | Environment: {settings.active_broker}")
                # Initialize risk manager with actual balance (fixes drawdown tracking)
                self.risk_manager._current_balance = balance
                self.risk_manager._peak_balance = balance
                logger.info(f"Risk manager initialized: peak_balance={balance}")

                # Initialize trade journal with actual balance
                if self.trade_journal is None:
                    self.trade_journal = TradeJournal(initial_capital=balance)
                    logger.info(f"Trade journal initialized: initial_capital={balance}")
                self._startup_error = ""
                connected = True
                break
            except Exception as e:
                self._startup_error = str(e)
                logger.error(f"Broker connection failed (attempt {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    logger.info(f"Retrying in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 60)

        if not connected:
            logger.error("All broker connection attempts failed. Engine will NOT start.")
            logger.error(f"Last error: {self._startup_error}")
            return

        # Register PositionManager callback so its internal closes
        # (TP_max, emergency exit) also persist to DB + trade journal
        self.position_manager.set_on_trade_closed(self._on_position_closed)
        # Persist SL changes to the trades row (audit trail) — without this the
        # journal stop_loss column froze at the original SL even though the
        # position manager moved it intraday (root cause of JPM audit confusion).
        self.position_manager.set_on_sl_changed(self._on_sl_changed)

        self._running = True
        logger.info(f"Watching {len(get_active_watchlist())} pairs")
        logger.info(f"Scan interval: {self._scan_interval}s")

        # Send startup alert
        if self.alert_manager and hasattr(self.alert_manager, 'send_engine_status'):
            try:
                await self.alert_manager.send_engine_status(
                    "STARTED",
                    f"Atlas engine started. Mode: {self.mode.value}. "
                    f"Broker: {broker_name}. Balance: {balance} {currency}. "
                    f"Watching {len(get_active_watchlist())} pairs.",
                )
            except Exception as e:
                logger.warning(f"Startup alert failed: {e}")

        # Initial scan on startup — run regardless of market hours
        # so that analysis data is available immediately for the UI
        logger.info("Running initial scan (ignoring market hours)...")

        # Reset circuit breaker before scan so stale failures don't cascade
        broker_circuit_breaker.reset()

        # Pre-resolve all instrument epics (with throttling) to avoid
        # burst API calls during the scan
        if hasattr(self.broker, 'warm_epic_cache'):
            try:
                await self.broker.warm_epic_cache(get_active_watchlist())
            except Exception as e:
                logger.warning(f"Epic cache warmup failed (non-critical): {e}")

        try:
            await self._initial_scan()
        except Exception as e:
            logger.error(f"Initial scan failed (non-critical): {e}")

        # Main loop
        logger.info(f"Main loop starting — scan every {self._scan_interval}s")
        tick_count = 0
        while self._running:
            tick_count += 1
            try:
                await asyncio.wait_for(self._tick(), timeout=300)  # 5 min timeout per tick
            except asyncio.TimeoutError:
                logger.error(f"Tick #{tick_count} TIMED OUT after 300s — skipping to next cycle")
            except Exception as e:
                logger.error(f"Error in main loop tick #{tick_count}: {e}")
                if self._ws_broadcast:
                    try:
                        await self._ws_broadcast("engine_error", {"error": str(e)})
                    except Exception as ws_err:
                        logger.warning(f"WS broadcast of engine error also failed: {ws_err}")

            await asyncio.sleep(self._scan_interval)

    async def stop(self):
        """Stop the trading engine gracefully. Final sync before shutdown."""
        logger.info("Trading engine stopping...")
        self._running = False
        # Final position sync to record any trades closed since last tick
        try:
            await self._sync_positions_from_broker()
        except Exception as e:
            logger.warning(f"Final position sync on stop failed: {e}")
        # Close alert manager HTTP client to avoid connection leaks
        if hasattr(self, 'alert_manager') and self.alert_manager:
            await self.alert_manager.close()

    # ── Core Tick ────────────────────────────────────────────────

    async def _tick(self):
        """One iteration of the main trading loop."""
        now = datetime.now(timezone.utc)
        market_open = self._is_market_open(now)
        logger.info(f"Tick at {now.strftime('%H:%M:%S')} UTC | market_open={market_open} | weekday={now.weekday()} | hour={now.hour}")

        # Reset daily counters at midnight UTC
        self._reset_daily_counters()

        # Always expire old pending setups
        self._expire_old_setups()

        # Morning heartbeat email (proof of life)
        await self._maybe_send_morning_heartbeat(now)

        # Daily summary: send at end of trading day (21:00 UTC EDT = trading_end_hour) once
        offset = self._dst_offset(now)
        if now.hour == settings.trading_end_hour + offset and now.minute < 10:
            if not hasattr(self, '_daily_summary_sent_date') or self._daily_summary_sent_date != now.date():
                self._daily_summary_sent_date = now.date()
                self._spawn_bg(self._send_daily_summary(), name="send_daily_summary")

        # Monthly ASR (After Session Review) on the 1st at ~08:00 UTC
        await self._maybe_send_monthly_asr(now)

        # Weekly Self-Improvement review (Sun 08:00 UTC) — runs the
        # TuningEngine over last 7 days of trades and either emits proposals
        # for approval or auto-applies SAFE-tier ones, depending on
        # settings.self_improvement_tuning_mode.
        await self._maybe_run_weekly_review(now)

        if market_open:
            # Check Friday close rule
            if self._should_close_friday(now):
                await self._handle_friday_close()
                # Still manage open positions (trailing stop, BE) for any kept positions
                await self._manage_open_positions()
                return

            # Funded account: close all positions at trading_end_hour every day (DST-adjusted)
            if settings.funded_account_mode and settings.funded_no_overnight:
                offset = self._dst_offset(now)
                if now.hour >= settings.trading_end_hour + offset:
                    await self._sync_positions_from_broker()
                    await self._handle_funded_overnight_close()
                    return

            # Funded account: close positions before weekend (Friday close, DST-adjusted)
            if settings.funded_account_mode and settings.funded_no_weekend:
                offset = self._dst_offset(now)
                if now.weekday() == 4 and now.hour >= settings.close_before_friday_hour + offset:
                    logger.info("Funded mode: closing all positions before weekend")
                    await self._sync_positions_from_broker()
                    await self._handle_funded_overnight_close()
                    return

            # Check economic calendar for upcoming news
            logger.debug("Checking news filter...")
            has_news, news_desc = await self.news_filter.has_upcoming_news()
            logger.info(f"News check: has_news={has_news} desc={news_desc[:50] if news_desc else 'none'}")
            self._news_active = has_news  # Cache for CPA auto-trigger check
            if has_news:
                # Funded account: block ALL trades during news, not just execution
                if settings.funded_account_mode and settings.funded_no_news_trading:
                    logger.info(
                        f"Funded mode: news filter blocking ALL activity: {news_desc}"
                    )
                    await self._sync_positions_from_broker()
                    return
                # Swing trading: mentorship says "podemos llegar a ejecutar incluso"
                # Don't hard-block execution for swing — just warn and continue
                if settings.trading_style == "swing":
                    logger.warning(
                        f"News active during swing trading: {news_desc} — "
                        f"proceeding with caution (mentorship: swing can execute during news)"
                    )
                    # Continue to normal scan — swing is allowed during news
                else:
                    logger.info(f"News filter active: {news_desc} — skipping new trade execution")
                    # Scalping: close positions on instruments affected by this specific news
                    # Mentorship + should_close_for_news: "SCALPING: always close before news"
                    # (news spikes can gap through tight scalping SLs causing outsized losses)
                    if settings.trading_style == "scalping":
                        await self._sync_positions_from_broker()
                        await self._close_news_affected_positions()
                    # Still scan for analysis but don't execute new trades
                    await self._scan_analysis_only()
                    # Mentorship: day trading during news = "poner break evens y esperar"
                    # Continue managing open positions (set BE, trail SL) even when news blocks new trades
                    await self._manage_open_positions()
                    return

            # Step 0: Sync balance for drawdown tracking (risk manager)
            try:
                await self.risk_manager.update_balance_tracking()
            except Exception as e:
                logger.warning(f"Balance tracking update failed: {e}")

            # Step 0b: Sync positions from broker (detect external closes)
            await self._sync_positions_from_broker()

            # Step 0c: Close existing positions threatened by upcoming high-impact news
            # Trading Plan: 'Cerrar trades antes de noticias importantes'
            await self._close_news_affected_positions()

            # Step 1: Update position management for open trades
            await self._manage_open_positions()

            # Record equity snapshot every 10 minutes
            await self._maybe_record_equity_snapshot(now)

            # Trading Plan: No new trades after Friday 18:00 UTC
            if self._is_friday_no_new_trades(now):
                logger.info("Friday rule: no new trades after 18:00 UTC — only managing open positions")
            else:
                # Step 2: Scan for new opportunities (with trade execution)
                await self._scan_for_setups()
        else:
            # Market closed — still sync and manage open positions
            # (broker can close via SL/TP even when market is "closed" for us)
            await self._sync_positions_from_broker()
            if self.position_manager.positions:
                await self._manage_open_positions()

            # Scan for analysis data every 10 minutes so the UI has fresh data
            if not hasattr(self, '_last_offhours_scan'):
                self._last_offhours_scan = datetime.min.replace(tzinfo=timezone.utc)
            if (now - self._last_offhours_scan).total_seconds() >= 600:
                logger.debug("Off-hours analysis scan...")
                await self._scan_analysis_only()
                self._last_offhours_scan = now

        # Cleanup expired reentry candidates
        expired = [k for k, v in self._reentry_candidates.items()
                   if (datetime.now(timezone.utc) - v["tp1_time"]).total_seconds() > settings.reentry_window_seconds]
        for k in expired:
            self._reentry_candidates.pop(k, None)

    # ── Equity Snapshot ─────────────────────────────────────────

    async def _maybe_record_equity_snapshot(self, now: datetime):
        """Record an equity snapshot every 10 minutes if the DB is available."""
        elapsed = (now - self._last_equity_snapshot).total_seconds()
        if elapsed < 600:  # 10 minutes
            return

        if not self._db:
            return

        try:
            summary = await self.broker.get_account_summary()
            balance = summary.balance
            equity = summary.equity
            unrealized_pnl = summary.unrealized_pnl
            open_positions = len(self.position_manager.positions)
            total_risk = self.risk_manager.get_current_total_risk()

            await self._db.record_equity_snapshot(
                balance=balance,
                equity=equity,
                unrealized_pnl=unrealized_pnl,
                open_positions=open_positions,
                total_risk=total_risk,
            )
            self._last_equity_snapshot = now
        except Exception as e:
            logger.warning(f"Equity snapshot failed (non-critical): {e}")

    # ── Market Hours ─────────────────────────────────────────────

    @staticmethod
    def _dst_offset(now: datetime) -> int:
        """Return DST offset: 0 during EDT (summer), 1 during EST (winter).

        During EST (Nov-Mar), US markets open/close 1 hour later in UTC.
        Config hours are set for EDT (e.g. trading_end_hour=21 → 5PM EDT).
        Add this offset during EST so 21+1=22 UTC → 5PM EST.
        """
        try:
            from zoneinfo import ZoneInfo
            et = now.astimezone(ZoneInfo("America/New_York"))
            # EDT = UTC-4 (dst=1h), EST = UTC-5 (dst=0h)
            return 0 if et.dst() else 1
        except Exception:
            return 0  # Fallback: assume EDT (no offset)

    def _get_session_quality(self, now: datetime, instrument: str = "") -> tuple:
        """
        Return (session_name, quality_score) based on current UTC hour.

        TradingLab mentorship (all times originally in ET, converted to UTC):
        - SYDNEY (Australian): 5:00 PM - 2:00 AM ET → 21:00-06:00 UTC (EDT)
        - ASIAN (Tokyo):       7:00 PM - 4:00 AM ET → 23:00-08:00 UTC (EDT)
        - LONDON (European):   3:00 AM - 12:00 PM ET → 07:00-16:00 UTC (EDT)
        - NEW_YORK:            8:00 AM - 5:00 PM ET → 12:00-21:00 UTC (EDT)
        - OVERLAP (London+NY): 8:00 AM - 12:00 PM ET → 12:00-16:00 UTC (EDT)

        DST handling: base values are EDT (UTC-4). _dst_offset() returns 0
        for EDT, 1 for EST — shifting boundaries +1h in UTC during winter
        (e.g. London 07:00 EDT → 08:00 EST).

        Quality scores reflect TradingLab guidance: overlap is peak volatility,
        London is the most liquid session, NY carries major news impact.

        For crypto instruments, ASIAN session gets a higher score (0.7) because
        crypto markets are active during Asian hours (TradingLab Crypto Mastery).
        """
        # Check if instrument is crypto
        from strategies.base import _is_crypto_instrument
        is_crypto = bool(instrument) and _is_crypto_instrument(instrument)

        hour = now.hour
        # Apply DST offset: during EST (winter), sessions shift +1h in UTC
        offset = self._dst_offset(now)
        if 12 + offset <= hour < 16 + offset:
            return ("OVERLAP", 1.0)
        elif 7 + offset <= hour < 12 + offset:
            return ("LONDON", 0.9)
        elif 16 + offset <= hour < 21 + offset:
            return ("NEW_YORK", 0.8)
        elif hour < 7 + offset:
            # Crypto is active in Asian hours — higher quality score
            return ("ASIAN", 0.7 if is_crypto else 0.5)
        else:
            return ("SYDNEY", 0.4)

    def _is_market_open(self, now: datetime) -> bool:
        """Check if market is open. Forex: Mon-Fri during sessions. Crypto: 24/7.
        Adjusts for DST: EST (winter) shifts session hours +1h in UTC."""
        # If crypto is in the active watchlist, market is always open for crypto
        # (crypto markets trade 24/7 including weekends — mentorship: "abierto 24/7")
        has_crypto = "crypto" in settings.active_watchlist_categories

        # Forex is closed on weekends
        if now.weekday() >= 5:  # Saturday=5, Sunday=6
            return has_crypto  # Only open for crypto on weekends

        # Only trade during London + NY sessions (DST-adjusted)
        hour = now.hour
        offset = self._dst_offset(now)
        start = settings.trading_start_hour + offset
        end = settings.trading_end_hour + offset
        if start <= hour < end:
            return True
        # Outside forex hours but crypto is always open
        return has_crypto

    def _should_close_friday(self, now: datetime) -> bool:
        """Check if we should close all positions (Friday rule). DST-adjusted."""
        offset = self._dst_offset(now)
        return (now.weekday() == 4 and
                now.hour >= settings.close_before_friday_hour + offset)

    def _is_friday_no_new_trades(self, now: datetime) -> bool:
        """Trading Plan: No new trades after Friday 18:00 UTC. DST-adjusted."""
        offset = self._dst_offset(now)
        return (now.weekday() == 4 and
                now.hour >= settings.no_new_trades_friday_hour + offset)

    async def _handle_friday_close(self):
        """Close only positions near SL or TP before Friday market close (Trading Plan rule).
        'Cerrar trades que estén cerca de SL o TP antes del cierre del viernes'
        A position is 'near' when price is within 30% of the entry-SL or entry-TP distance."""
        open_trades = await self.broker.get_open_trades()
        if not open_trades:
            return

        closed = 0
        kept = 0
        from strategies.base import _is_crypto_instrument
        for trade in open_trades:
            should_close = False
            close_reason = ""

            instrument = getattr(trade, 'instrument', '?')

            # Crypto positions are exempt from Friday close (crypto trades 24/7)
            if _is_crypto_instrument(instrument):
                kept += 1
                logger.info(f"Friday: Keeping {instrument} (crypto — markets open 24/7)")
                continue

            entry = getattr(trade, 'entry_price', None)
            current = getattr(trade, 'current_price', None)
            sl = getattr(trade, 'stop_loss', None)
            tp = getattr(trade, 'take_profit', None)

            # If we lack price data, skip (don't close blindly)
            if entry is None or current is None:
                kept += 1
                logger.info(f"Friday: Keeping {instrument} (missing price data)")
                continue

            # Check if near SL
            if sl is not None and entry:
                sl_distance = abs(entry - sl)
                current_to_sl = abs(current - sl)
                if sl_distance > 0 and current_to_sl <= sl_distance * 0.30:
                    should_close = True
                    close_reason = "SL"

            # Check if near TP
            if tp is not None and entry:
                tp_distance = abs(tp - entry)
                current_to_tp = abs(current - tp)
                if tp_distance > 0 and current_to_tp <= tp_distance * 0.30:
                    should_close = True
                    close_reason = "TP" if not close_reason else "SL+TP"

            trade_id = getattr(trade, 'trade_id', None)

            if not trade_id:
                kept += 1
                continue

            if should_close:
                try:
                    ok = await self.broker.close_trade(trade_id)
                    if not ok:
                        logger.error(f"Friday close: broker.close_trade({trade_id}) returned False — skipping cleanup")
                        continue
                    # Record trade result BEFORE cleanup (delta/reentry tracking)
                    pos = self.position_manager.positions.get(trade_id)
                    if current and entry:
                        direction = getattr(trade, 'direction', 'BUY')
                        pnl_raw = (current - entry) if direction == "BUY" else (entry - current)
                        units = abs(getattr(trade, 'units', 0) or (getattr(pos, 'units', 0) if pos else 0))
                        pnl_dollars = pnl_raw * units if units else pnl_raw
                        balance = getattr(self.risk_manager, '_current_balance', 0.0) or 1.0
                        self.risk_manager.record_trade_result(
                            trade_id or "", instrument, pnl_dollars / balance if balance > 0 else 0.0
                        )
                    # Clean up internal tracking after recording
                    self.position_manager.positions.pop(trade_id, None)
                    if pos:
                        self.risk_manager.unregister_trade(trade_id, pos.instrument)
                    closed += 1
                    logger.info(f"Friday close: Closed {instrument} (near {close_reason})")
                    # Persist close to DB with PnL
                    if self._db and trade_id and current and entry:
                        try:
                            direction = getattr(trade, 'direction', 'BUY')
                            pnl_val = (current - entry) if direction == "BUY" else (entry - current)
                            units = abs(getattr(trade, 'units', 0) or (getattr(pos, 'units', 0) if pos else 0))
                            await self._db.update_trade(trade_id, {
                                "status": f"closed_friday_{close_reason.lower()}",
                                "closed_at": datetime.now(timezone.utc).isoformat(),
                                "exit_price": current,
                                "pnl": pnl_val * units if units else pnl_val,
                            })
                        except Exception as db_err:
                            logger.warning(f"DB update failed for Friday close {trade_id}: {db_err}")
                    # Record in trade journal
                    if self.trade_journal and trade_id and current and entry:
                        try:
                            direction = getattr(trade, 'direction', 'BUY')
                            pnl_val = (current - entry) if direction == "BUY" else (entry - current)
                            units = abs(getattr(trade, 'units', 0) or (getattr(pos, 'units', 0) if pos else 0))
                            self.trade_journal.record_trade(
                                trade_id=trade_id,
                                instrument=instrument,
                                pnl_dollars=pnl_val * units if units else pnl_val,
                                entry_price=entry,
                                exit_price=current,
                                strategy=getattr(pos, 'strategy_variant', 'UNKNOWN') if pos else 'UNKNOWN',
                                direction=direction,
                            )
                        except Exception as je:
                            logger.warning(f"Trade journal failed for Friday close {trade_id}: {je}")
                except Exception as e:
                    logger.error(f"Friday close failed for {trade_id}: {e}")
            else:
                kept += 1
                logger.info(f"Friday: Keeping {instrument} (not near SL/TP)")

        if closed > 0:
            logger.warning(f"FRIDAY CLOSE: Closed {closed} trades near SL/TP, kept {kept}")
            # Send alert about Friday closures
            if self.alert_manager:
                try:
                    await self.alert_manager.send_engine_status(
                        "FRIDAY_CLOSE",
                        f"Closed {closed} positions near SL/TP before weekend. Kept {kept} running.",
                    )
                except Exception as e:
                    logger.warning(f"Friday close alert failed: {e}")
        elif kept > 0:
            logger.info(f"Friday: All {kept} positions are mid-range — keeping through weekend")

    async def _handle_funded_overnight_close(self):
        """Close all positions at end of trading session (funded account rule)."""
        open_trades = await self.broker.get_open_trades()
        if open_trades:
            logger.warning(
                f"FUNDED OVERNIGHT CLOSE: Closing {len(open_trades)} open trades "
                f"(no overnight holding)"
            )
            # Record PnL and persist to DB in a single pass (avoid double API calls)
            now_iso = datetime.now(timezone.utc).isoformat()
            for tid, pos in list(self.position_manager.positions.items()):
                try:
                    price_data = await self.broker.get_current_price(pos.instrument)
                    current_price = (
                        price_data.bid if pos.direction == "BUY" else price_data.ask
                    )
                    price_diff = (current_price - pos.entry_price) if pos.direction == "BUY" else (pos.entry_price - current_price)
                    pnl = price_diff * abs(pos.units) if pos.units != 0 else price_diff

                    # Close via broker FIRST, then record PnL on success
                    try:
                        ok = await self.broker.close_trade(tid)
                        if not ok:
                            logger.error(f"Broker close_trade returned False for funded overnight {tid} — skipping DB update")
                            continue
                    except Exception as be:
                        logger.error(f"Broker close_trade failed for funded overnight {tid}: {be}")
                        continue

                    self.risk_manager.record_funded_pnl(pnl)
                    # Record trade result for delta/reentry tracking
                    balance = getattr(self.risk_manager, '_current_balance', 0.0) or 1.0
                    self.risk_manager.record_trade_result(tid, pos.instrument, pnl / balance if balance > 0 else 0.0)

                    if self._db:
                        await self._db.update_trade(tid, {
                            "status": "closed_funded_overnight",
                            "closed_at": now_iso,
                            "exit_price": current_price,
                            "pnl": pnl,
                        })
                    # Record in trade journal
                    if self.trade_journal:
                        try:
                            self.trade_journal.record_trade(
                                trade_id=tid,
                                instrument=pos.instrument,
                                pnl_dollars=pnl,
                                entry_price=pos.entry_price,
                                exit_price=current_price,
                                strategy=getattr(pos, 'strategy_variant', 'UNKNOWN'),
                                direction=pos.direction,
                            )
                        except Exception as je:
                            logger.warning(f"Trade journal failed for funded close {tid}: {je}")
                except Exception as e:
                    logger.warning(f"Failed to process funded close for {tid}: {e}")

            # Close any remaining trades not tracked in position_manager
            await self.broker.close_all_trades()
            self.risk_manager.unregister_all_trades()
            self.position_manager.positions.clear()

    # ── Position-Manager SL change callback ────────────────────

    async def _on_sl_changed(
        self,
        trade_id: str,
        instrument: str,
        direction: str,
        old_sl: float,
        new_sl: float,
        phase: str,
    ):
        """Persist SL moves to the trades row so the audit trail reflects
        every broker-confirmed stop adjustment. Without this the journal
        column stayed at the original SL forever, hiding tightening events."""
        if not self._db:
            return
        try:
            await self._db.update_trade(trade_id, {"stop_loss": new_sl})
            logger.info(
                f"{trade_id}: SL persisted {old_sl:.5f} -> {new_sl:.5f} "
                f"(phase={phase}, instrument={instrument}, direction={direction})"
            )
        except Exception as db_err:
            logger.warning(
                f"DB SL persist failed for {trade_id}: {db_err}"
            )

    # ── Position-Manager close callback ────────────────────────

    async def _on_position_closed(
        self,
        trade_id: str,
        instrument: str,
        direction: str,
        entry_price: float,
        exit_price: float,
        pnl_dollars: float,
        units: float,
        reason: str,
        strategy_variant: Optional[str] = None,
        style: Optional[str] = None,
    ):
        """Called by PositionManager when it closes a trade (TP_max / emergency exit).

        Mirrors the DB + journal + consecutive-loss logic already used in
        _sync_positions_from_broker for externally-closed positions.
        """
        # Scalping DD tracking — internal closes (TP_max / emergency exit /
        # trailing SL hit) previously did NOT increment _scalping_daily_dd.
        # Only the external-close path in _sync_positions_from_broker updated
        # it, which meant the daily/total-DD pause gate almost never fired
        # in normal flows. Increment here on losses; reset happens at SOD.
        if style == "scalping" and pnl_dollars < 0:
            balance = getattr(self.risk_manager, "_current_balance", 0.0) or 0.0
            if balance > 0:
                self._scalping_daily_dd += abs(pnl_dollars) / balance
        # 1. Persist to SQLite DB
        if self._db:
            try:
                await self._db.update_trade(trade_id, {
                    "status": f"closed_{reason}",
                    "closed_at": datetime.now(timezone.utc).isoformat(),
                    "exit_price": exit_price,
                    "pnl": pnl_dollars,
                })
            except Exception as db_err:
                logger.warning(f"DB update failed for {reason} close {trade_id}: {db_err}")

        # 2. Record in trade journal
        if self.trade_journal:
            try:
                self.trade_journal.record_trade(
                    trade_id=trade_id,
                    instrument=instrument,
                    pnl_dollars=pnl_dollars,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    strategy=strategy_variant or "UNKNOWN",
                    direction=direction,
                )
            except Exception as je:
                logger.warning(f"Trade journal record failed for {trade_id}: {je}")

        # 3. Track consecutive losses for cooldown (Psicologia Avanzada)
        if pnl_dollars < 0:
            self._consecutive_losses_today += 1
            self._last_loss_time = datetime.now(timezone.utc)
        else:
            self._consecutive_losses_today = 0

        # 4. Record trade result for delta/reentry tracking
        balance = getattr(self.risk_manager, '_current_balance', 1.0) or 1.0
        pnl_pct = pnl_dollars / balance if balance > 0 else 0.0
        self.risk_manager.record_trade_result(trade_id, instrument, pnl_pct)

        # 5. Funded account PnL tracking
        if settings.funded_account_mode:
            self.risk_manager.record_funded_pnl(pnl_dollars)

        # 6. WebSocket broadcast — fire-and-forget so slow WS client can't block alerts
        if self._ws_broadcast:
            async def _ws_close():
                try:
                    await self._ws_broadcast("trade_closed", {
                        "trade_id": trade_id,
                        "instrument": instrument,
                        "reason": reason,
                        "pnl": pnl_dollars,
                    })
                except Exception as e:
                    logger.warning(f"WS broadcast trade_closed failed: {e}")
            self._spawn_bg(_ws_close(), name="ws_trade_closed")

        # 7. Email notification on trade close (blocking — critical delivery path)
        if self.alert_manager:
            try:
                from core.backtester import _pips as _pip_distance
                price_diff = (exit_price - entry_price) if direction == "BUY" else (entry_price - exit_price)
                pips = round(_pip_distance(instrument, price_diff), 1)
                await self.alert_manager.send_trade_closed(
                    instrument=instrument,
                    pnl=pnl_dollars,
                    pips=pips,
                    reason=reason,
                    strategy=strategy_variant,
                )
            except Exception as e:
                logger.warning(f"Alert send_trade_closed failed for {trade_id}: {e}")

        # 8. Screenshot on trade close — fire-and-forget (non-critical)
        if self.screenshot_generator:
            _pnl_pct_close = round((exit_price - entry_price if direction == "BUY" else entry_price - exit_price) / entry_price * 100, 2) if entry_price else 0
            async def _capture_close():
                try:
                    await self.screenshot_generator.capture_trade_close(
                        trade_id=trade_id,
                        instrument=instrument,
                        direction=direction,
                        entry_price=entry_price,
                        close_price=exit_price,
                        pnl_pct=_pnl_pct_close,
                        result="TP" if pnl_dollars > 0 else ("SL" if pnl_dollars < 0 else "BE"),
                    )
                except Exception as e:
                    logger.warning(f"Screenshot capture failed for {trade_id}: {e}")
            self._spawn_bg(_capture_close(), name="capture_trade_close")

        # 9. Self-improvement: AutoASR (fire-and-forget, opt-in via flag).
        # Uses GPT-4o (vision) to grade execution against the trading plan and
        # write back to the journal's ASR fields. Safe: fully wrapped, never
        # blocks the close pipeline. See backend/core/self_improvement.py.
        if (
            getattr(settings, "auto_asr_enabled", False)
            and self.ai_analyzer is not None
            and self.trade_journal is not None
        ):
            async def _auto_asr():
                try:
                    from core.self_improvement import AutoASRGenerator, find_close_screenshot
                    # Wait briefly so the close screenshot file lands on disk
                    # before we try to attach it to the vision prompt.
                    await asyncio.sleep(3.0)
                    record = next(
                        (t for t in self.trade_journal.get_trades(50) if t.get("trade_id") == trade_id),
                        None,
                    )
                    if not record:
                        logger.debug(f"AutoASR skipped: trade {trade_id} not yet in journal")
                        return
                    journal_path = getattr(self.trade_journal, "_data_path", "data/trade_journal.json")
                    screenshots_dir = os.path.join(os.path.dirname(os.path.abspath(journal_path)), "screenshots")
                    shot = find_close_screenshot(screenshots_dir, trade_id)
                    gen = AutoASRGenerator(
                        openai_client=self.ai_analyzer.client,
                        trade_journal=self.trade_journal,
                        model=getattr(settings, "auto_asr_model", "gpt-4o"),
                    )
                    await gen.generate_asr(record, screenshot_path=shot)
                except Exception as e:
                    logger.warning(f"AutoASR background task failed for {trade_id}: {e}")
            self._spawn_bg(_auto_asr(), name="auto_asr")

    # ── Position Sync ────────────────────────────────────────────

    async def _sync_positions_from_broker(self):
        """Sync tracked positions with actual broker state.
        Detects positions closed externally (via broker UI or SL/TP hit)."""
        try:
            broker_trades = await self.broker.get_open_trades()
            broker_ids = {t.trade_id for t in broker_trades}
            tracked_ids = set(self.position_manager.positions.keys())

            # Adopt positions that exist at the broker but aren't tracked
            # (opened externally, or app restarted with open positions)
            new_ids = broker_ids - tracked_ids
            for trade in broker_trades:
                if trade.trade_id in new_ids:
                    # ManagedPosition + PositionPhase already imported at module level.
                    # Previous local import shadowed the module-level binding and left
                    # PositionPhase unbound when new_ids was empty but closed_ids was not.
                    # Skip adoption if missing critical fields
                    if not trade.stop_loss or not trade.entry_price:
                        logger.warning(
                            f"Skipping adoption of {trade.trade_id} ({trade.instrument}): "
                            f"missing SL or entry price"
                        )
                        continue
                    pos = ManagedPosition(
                        trade_id=trade.trade_id,
                        instrument=trade.instrument,
                        direction=trade.direction,
                        entry_price=trade.entry_price,
                        original_sl=trade.stop_loss,
                        current_sl=trade.stop_loss,
                        take_profit_1=trade.take_profit or trade.entry_price * (1.01 if trade.direction == "BUY" else 0.99),
                        units=trade.units or 0,
                        style=settings.trading_style,
                    )
                    # Infer correct phase from SL position relative to entry
                    if pos.direction == "BUY" and pos.current_sl >= pos.entry_price:
                        pos.phase = PositionPhase.BREAK_EVEN
                    elif pos.direction == "SELL" and pos.current_sl <= pos.entry_price:
                        pos.phase = PositionPhase.BREAK_EVEN
                    self.position_manager.positions[trade.trade_id] = pos
                    # Use correct risk for current trading style
                    style_risk_map = {
                        "day_trading": settings.risk_day_trading,
                        "swing": settings.risk_swing,
                        "scalping": settings.risk_scalping,
                    }
                    adopt_risk = style_risk_map.get(settings.trading_style, settings.risk_day_trading)
                    self.risk_manager.register_trade(
                        trade.trade_id, trade.instrument, adopt_risk
                    )
                    logger.info(
                        f"Adopted broker position: {trade.trade_id} | "
                        f"{trade.instrument} {trade.direction} | "
                        f"entry={trade.entry_price} units={trade.units}"
                    )

            # Remove positions that no longer exist at the broker
            closed_ids = tracked_ids - broker_ids
            for tid in closed_ids:
                pos = self.position_manager.positions.pop(tid, None)
                if pos:
                    self.risk_manager.unregister_trade(tid, pos.instrument)
                    logger.info(
                        f"Position {tid} ({pos.instrument}) closed externally — removed from tracking"
                    )

                    # Determine close price: use SL/TP as approximation since
                    # the broker already closed the position and current price may differ.
                    # If price moved past TP → likely TP hit. Past SL → likely SL hit.
                    close_price = pos.entry_price  # default
                    pnl_dollars = 0.0
                    try:
                        price_data = await self.broker.get_current_price(pos.instrument)
                        current = price_data.bid if pos.direction == "BUY" else price_data.ask

                        # Heuristic: if current price is beyond TP, assume TP was hit
                        # If current price is beyond SL, assume SL was hit
                        if pos.direction == "BUY":
                            if pos.take_profit_1 and current >= pos.take_profit_1:
                                close_price = pos.take_profit_1  # TP hit
                            elif current <= pos.current_sl:
                                close_price = pos.current_sl  # SL hit
                            else:
                                close_price = current  # Manual close or mid-range
                        else:  # SELL
                            if pos.take_profit_1 and current <= pos.take_profit_1:
                                close_price = pos.take_profit_1
                            elif current >= pos.current_sl:
                                close_price = pos.current_sl
                            else:
                                close_price = current

                        price_diff = (
                            (close_price - pos.entry_price)
                            if pos.direction == "BUY"
                            else (pos.entry_price - close_price)
                        )
                        pnl_dollars = price_diff * abs(pos.units) if pos.units != 0 else price_diff
                    except Exception as e:
                        # Fallback: use SL as worst-case close price
                        if pos.current_sl and pos.current_sl != pos.entry_price:
                            close_price = pos.current_sl
                            price_diff = (close_price - pos.entry_price) if pos.direction == "BUY" else (pos.entry_price - close_price)
                            pnl_dollars = price_diff * abs(pos.units) if pos.units != 0 else price_diff
                        logger.warning(f"Failed to get close price for {tid}, using SL estimate: {e}")

                    # Record trade result for delta algorithm, win rate, and reentry tracking
                    balance = getattr(self.risk_manager, '_current_balance', 0.0) or 1.0
                    pnl_pct = pnl_dollars / balance if balance > 0 else 0.0
                    self.risk_manager.record_trade_result(tid, pos.instrument, pnl_pct)

                    # Record funded PnL from externally closed position
                    if settings.funded_account_mode:
                        self.risk_manager.record_funded_pnl(pnl_dollars)

                    # Track scalping drawdown if this was a scalping trade
                    if getattr(pos, 'style', '') == 'scalping' and pnl_dollars < 0:
                        balance = getattr(self.risk_manager, '_current_balance', 0.0) or 0.0
                        if balance > 0:
                            self._scalping_daily_dd += abs(pnl_dollars) / balance

                    # TradingLab: Register reentry candidate if position was profitable
                    # (TP1 was likely hit if it was in BEYOND_TP1 phase or profitable)
                    if pos.phase in (PositionPhase.BEYOND_TP1, PositionPhase.TRAILING_TO_TP1):
                        self._reentry_candidates[pos.instrument] = {
                            "tp1_time": datetime.now(timezone.utc),
                            "direction": pos.direction,
                            "count": 0,
                            "entry_price": pos.entry_price,
                        }
                        logger.info(
                            f"Reentry candidate registered: {pos.instrument} {pos.direction} "
                            f"(TP1 reached, 30min window)"
                        )

                    if self._ws_broadcast:
                        # Fire-and-forget: slow WS client shouldn't block sync.
                        # Payload shape mirrors the internal close path so any
                        # consumer can read `pnl` unconditionally.
                        _ws_tid = tid
                        _ws_inst = pos.instrument
                        _ws_pnl = pnl_dollars
                        async def _ws_ext_close(__tid=_ws_tid, __inst=_ws_inst, __pnl=_ws_pnl):
                            try:
                                await self._ws_broadcast("trade_closed", {
                                    "trade_id": __tid,
                                    "instrument": __inst,
                                    "reason": "external",
                                    "pnl": __pnl,
                                })
                            except Exception as e:
                                logger.warning(f"WS broadcast trade_closed failed: {e}")
                        self._spawn_bg(_ws_ext_close(), name="ws_ext_close")

                    # Determine actual close reason from heuristic
                    if pos.direction == "BUY":
                        if pos.take_profit_1 and close_price >= pos.take_profit_1:
                            close_status = "closed_tp"
                        elif close_price <= pos.current_sl:
                            close_status = "closed_sl"
                        else:
                            close_status = "closed_external"
                    else:  # SELL
                        if pos.take_profit_1 and close_price <= pos.take_profit_1:
                            close_status = "closed_tp"
                        elif close_price >= pos.current_sl:
                            close_status = "closed_sl"
                        else:
                            close_status = "closed_external"

                    # Persist close to database with PnL data
                    if self._db:
                        try:
                            await self._db.update_trade(tid, {
                                "status": close_status,
                                "closed_at": datetime.now(timezone.utc).isoformat(),
                                "exit_price": close_price,
                                "pnl": pnl_dollars,
                            })
                        except Exception as db_err:
                            logger.warning(f"DB update failed for external close {tid}: {db_err}")

                    # Track consecutive losses for cooldown (Psicología Avanzada)
                    if pnl_dollars < 0:
                        self._consecutive_losses_today += 1
                        self._last_loss_time = datetime.now(timezone.utc)
                    else:
                        self._consecutive_losses_today = 0  # Reset on win/BE

                    # Record in trade journal
                    if self.trade_journal:
                        try:
                            self.trade_journal.record_trade(
                                trade_id=tid,
                                instrument=pos.instrument,
                                pnl_dollars=pnl_dollars,
                                entry_price=pos.entry_price,
                                exit_price=close_price,
                                strategy=getattr(pos, 'strategy_variant', 'UNKNOWN'),
                                direction=pos.direction,
                            )
                        except Exception as je:
                            logger.warning(f"Trade journal record failed for {tid}: {je}")

                    # Screenshot on trade close — fire-and-forget, don't block sync loop
                    if self.screenshot_generator:
                        _ss_pnl_pct = round(
                            (close_price - pos.entry_price if pos.direction == "BUY" else pos.entry_price - close_price)
                            / pos.entry_price * 100,
                            2,
                        ) if pos.entry_price else 0
                        _ss_result = "TP" if pnl_dollars > 0 else ("SL" if pnl_dollars < 0 else "BE")
                        _ss_tid = tid
                        _ss_inst = pos.instrument
                        _ss_dir = pos.direction
                        _ss_entry = pos.entry_price
                        _ss_close = close_price
                        async def _capture_ext_close(
                            __tid=_ss_tid, __inst=_ss_inst, __dir=_ss_dir,
                            __entry=_ss_entry, __close=_ss_close,
                            __pct=_ss_pnl_pct, __res=_ss_result,
                        ):
                            try:
                                await self.screenshot_generator.capture_trade_close(
                                    trade_id=__tid,
                                    instrument=__inst,
                                    direction=__dir,
                                    entry_price=__entry,
                                    close_price=__close,
                                    pnl_pct=__pct,
                                    result=__res,
                                )
                            except Exception as e:
                                logger.warning(f"Screenshot capture failed for {__tid}: {e}")
                        self._spawn_bg(_capture_ext_close(), name="capture_ext_close")

                    # Send close alert
                    if self.alert_manager:
                        try:
                            from core.backtester import _pips as _pip_distance
                            _close_diff = (close_price - pos.entry_price) if pos.direction == "BUY" else (pos.entry_price - close_price)
                            _close_pips = round(_pip_distance(pos.instrument, _close_diff), 1)
                            await self.alert_manager.send_trade_closed(
                                instrument=pos.instrument,
                                pnl=pnl_dollars,
                                pips=_close_pips,
                                reason="Position closed externally (broker/SL/TP)",
                                strategy=getattr(pos, 'strategy_variant', '') or '',
                            )
                            logger.info(f"Close alert sent for {pos.instrument}")
                        except Exception as ae:
                            logger.warning(f"Close alert failed for {pos.instrument}: {ae}")
        except Exception as e:
            logger.warning(f"Position sync failed: {e}")

    # ── Position Management ──────────────────────────────────────

    async def _manage_open_positions(self):
        """Update SL/TP management for all open positions."""
        if not self.position_manager.positions:
            return

        # Get current prices for all tracked instruments
        instruments = list(set(
            pos.instrument for pos in self.position_manager.positions.values()
        ))
        try:
            # Feed latest EMA values to position manager for trailing
            # Skip stale data (older than 3x scan interval) to avoid trailing on outdated EMAs
            now = datetime.now(timezone.utc)
            max_age_seconds = self._scan_interval * 3
            for inst in instruments:
                if inst in self._last_scan_results:
                    result = self._last_scan_results[inst]
                    scan_ts = getattr(result, '_scan_timestamp', None)
                    if scan_ts and (now - scan_ts).total_seconds() > max_age_seconds:
                        logger.warning(
                            f"Skipping stale EMA data for {inst}: "
                            f"last scan {(now - scan_ts).total_seconds():.0f}s ago"
                        )
                        continue
                    self.position_manager.set_ema_values(inst, result.ema_values)
                    # Feed swing data for Phase 1 structural SL movement
                    swing_highs = getattr(result, 'swing_highs', [])
                    swing_lows = getattr(result, 'swing_lows', [])
                    if swing_highs or swing_lows:
                        self.position_manager.set_swing_values(inst, swing_highs, swing_lows)

            # Capture phase state before update to detect transitions
            pre_phases = {
                tid: pos.phase.name for tid, pos in self.position_manager.positions.items()
            }
            pre_sls = {
                tid: pos.current_sl for tid, pos in self.position_manager.positions.items()
            }

            prices = await self.broker.get_prices_bulk(instruments)
            await self.position_manager.update_all_positions(prices)

            # Notify on phase transitions and SL moves. Iterate a snapshot so
            # concurrent close callbacks (which pop from self.positions) don't
            # mutate the dict mid-iteration across the inner awaits.
            if self.alert_manager:
                for tid, pos in list(self.position_manager.positions.items()):
                    old_phase = pre_phases.get(tid)
                    old_sl = pre_sls.get(tid)
                    if old_phase and pos.phase.name != old_phase:
                        try:
                            await self.alert_manager.send_position_update(
                                instrument=pos.instrument,
                                phase=pos.phase.name,
                                current_sl=pos.current_sl,
                                entry_price=pos.entry_price,
                            )
                        except Exception as e:
                            logger.warning(f"Position update alert failed: {e}")
                    elif old_sl and pos.current_sl != old_sl:
                        try:
                            await self.alert_manager.send_position_update(
                                instrument=pos.instrument,
                                phase=f"{pos.phase.name} (SL moved)",
                                current_sl=pos.current_sl,
                                entry_price=pos.entry_price,
                            )
                        except Exception as e:
                            logger.warning(f"SL move alert failed: {e}")

            # CPA auto-trigger checks (TradingLab: double pattern, news, Friday, indecision)
            self._check_cpa_auto_triggers(prices)
        except Exception as e:
            logger.error(f"Error managing positions: {e}")

    async def _close_news_affected_positions(self):
        """Close positions on instruments threatened by upcoming high-impact news.

        Trading Plan: 'Cerrar trades antes de noticias importantes'
        Called during news windows to protect against news-spike slippage.
        Scalping: always close.  Day trading: move to BE (handled by position manager).
        Swing: proceeds with caution (this method still closes if should_close_for_news triggers).
        """
        if not self.news_filter or not self.position_manager.positions:
            return
        for trade_id, pos in list(self.position_manager.positions.items()):
            # Idempotency: if another path (tick-driven close, broker-sync close,
            # emergency close) has already claimed this position, skip the news-
            # close flow to prevent double DB writes / double-credit on delta
            # algorithm / duplicate journal + email.
            if getattr(pos, "_closing", False):
                continue
            try:
                should_close, reason = await self.news_filter.should_close_for_news(pos.instrument)
                if should_close:
                    pos._closing = True
                    ok = await self.broker.close_trade(pos.trade_id)
                    if not ok:
                        # Release the claim so a future close path can retry.
                        pos._closing = False
                        logger.error(f"News close: broker.close_trade({pos.trade_id}) returned False — position remains tracked")
                        continue
                    # Record trade result before removing
                    pnl_val = 0.0
                    news_exit_price = pos.entry_price  # fallback
                    try:
                        price_data = await self.broker.get_current_price(pos.instrument)
                        news_exit_price = price_data.bid if pos.direction == "BUY" else price_data.ask
                        pnl_val = ((news_exit_price - pos.entry_price) if pos.direction == "BUY" else (pos.entry_price - news_exit_price)) * abs(pos.units)
                    except Exception as e:
                        logger.warning(f"News close: could not get price for PnL ({e}), recording as $0")
                    balance = getattr(self.risk_manager, '_current_balance', 1.0) or 1.0
                    self.risk_manager.record_trade_result(pos.trade_id, pos.instrument, pnl_val / balance)
                    self.position_manager.remove_position(pos.trade_id)
                    self.risk_manager.unregister_trade(pos.trade_id, pos.instrument)
                    logger.warning(f"News close: Closed {pos.instrument} — {reason}")
                    # Persist to DB
                    if self._db:
                        try:
                            await self._db.update_trade(pos.trade_id, {
                                "status": "closed_news",
                                "closed_at": datetime.now(timezone.utc).isoformat(),
                                "exit_price": news_exit_price,
                                "pnl": pnl_val,
                            })
                        except Exception as db_err:
                            logger.warning(f"DB update failed for news close {pos.trade_id}: {db_err}")
                    # Record in trade journal
                    if self.trade_journal:
                        try:
                            self.trade_journal.record_trade(
                                trade_id=pos.trade_id,
                                instrument=pos.instrument,
                                pnl_dollars=pnl_val,
                                entry_price=pos.entry_price,
                                exit_price=news_exit_price,
                                strategy=getattr(pos, 'strategy_variant', 'UNKNOWN'),
                                direction=pos.direction,
                            )
                        except Exception as je:
                            logger.warning(f"Trade journal failed for news close {pos.trade_id}: {je}")
                    # Send alert
                    if self.alert_manager:
                        try:
                            from core.backtester import _pips as _pip_distance
                            _news_diff = (news_exit_price - pos.entry_price) if pos.direction == "BUY" else (pos.entry_price - news_exit_price)
                            _news_pips = round(_pip_distance(pos.instrument, _news_diff), 1)
                            await self.alert_manager.send_trade_closed(
                                instrument=pos.instrument,
                                pnl=pnl_val,
                                pips=_news_pips,
                                reason=f"Closed before news: {reason}",
                                strategy=getattr(pos, 'strategy_variant', '') or '',
                            )
                        except Exception as ae:
                            logger.warning(f"Close alert failed for {trade_id}: {ae}")
            except Exception as e:
                logger.error(f"News close failed for {trade_id}: {e}")

    def _check_cpa_auto_triggers(self, prices: dict):
        """Check CPA auto-trigger conditions for open positions (TradingLab mentorship).

        Conditions: double pattern near TP, upcoming news, Friday close, indecision.
        """
        import datetime as _dt

        now = _dt.datetime.now(_dt.timezone.utc)
        is_friday = now.weekday() == 4
        offset = self._dst_offset(now)
        friday_close_soon = is_friday and now.hour >= settings.no_new_trades_friday_hour + offset

        # Check upcoming news — use cached value from last scan cycle
        # (the main scan loop already calls has_upcoming_news() asynchronously
        # and stores the result; we just read the cached state here)
        news_active = getattr(self, '_news_active', False)

        for pos in list(self.position_manager.positions.values()):
            # Only trigger CPA on positions past BE
            if pos.phase not in (PositionPhase.BREAK_EVEN, PositionPhase.TRAILING_TO_TP1):
                continue

            # Condition 1: Friday close approaching
            if friday_close_soon and settings.cpa_auto_on_friday_close:
                self.position_manager.set_cpa_trigger(pos.trade_id, "friday_close_approaching")
                continue

            # Condition 2: High-impact news approaching
            if news_active and settings.cpa_auto_on_news:
                self.position_manager.set_cpa_trigger(pos.trade_id, "high_impact_news")
                continue

            # Condition 3: Double pattern near TP (check chart patterns)
            if settings.cpa_auto_on_double_pattern:
                analysis = self._last_scan_results.get(pos.instrument)
                if analysis and analysis.chart_patterns:
                    for cp in analysis.chart_patterns:
                        cp_name = cp.get("pattern", "").lower() if isinstance(cp, dict) else str(cp).lower()
                        if "double" in cp_name:
                            self.position_manager.set_cpa_trigger(pos.trade_id, f"double_pattern:{cp_name}")
                            break

            # Condition 4: Indecision near TP (DOJI patterns)
            if settings.cpa_auto_on_indecision:
                analysis = self._last_scan_results.get(pos.instrument)
                if analysis and "DOJI" in analysis.candlestick_patterns:
                    raw_price = prices.get(pos.instrument)
                    # Extract numeric price from broker price object
                    if raw_price is not None and pos.take_profit_1:
                        price_val = raw_price.bid if hasattr(raw_price, 'bid') else float(raw_price)
                        tp_dist = abs(pos.take_profit_1 - price_val)
                        entry_dist = abs(pos.take_profit_1 - pos.entry_price)
                        if entry_dist > 0 and tp_dist / entry_dist < 0.3:
                            self.position_manager.set_cpa_trigger(pos.trade_id, "indecision_near_tp")

            # Condition 5: Price approaching key reference levels (previous highs/lows, Fib extensions)
            # TradingLab mentorship: "en momentos donde estemos llegando a puntos determinantes,
            # como soportes o resistencias" — CPA activates at key structural levels
            if getattr(settings, 'cpa_auto_on_key_levels', True):
                analysis = self._last_scan_results.get(pos.instrument)
                raw_price = prices.get(pos.instrument)
                if analysis and raw_price is not None:
                    current_price = raw_price.bid if hasattr(raw_price, 'bid') else float(raw_price)
                    key_levels = []
                    # Previous swing highs/lows from H1 structure detection
                    for sh in getattr(analysis, 'swing_highs', []):
                        key_levels.append(sh)
                    for sl_level in getattr(analysis, 'swing_lows', []):
                        key_levels.append(sl_level)
                    # Fibonacci extension levels (1.272, 1.618 — key profit-taking zones)
                    fib = getattr(analysis, 'fibonacci_levels', {}) or {}
                    for ext_key in ['ext_bull_1.272', 'ext_bull_1.618', 'ext_bear_1.272', 'ext_bear_1.618']:
                        if ext_key in fib:
                            key_levels.append(fib[ext_key])

                    for level in key_levels:
                        if level and current_price > 0 and abs(current_price - level) / current_price < 0.02:
                            self.position_manager.set_cpa_trigger(
                                pos.trade_id,
                                f"key_level_proximity:{level:.5f}",
                                temporary=True,
                                revert_level=level,
                            )
                            break

    # ── Analysis-Only Scan (off-hours / news active) ───────────

    async def _scan_analysis_only(self):
        """Scan all watchlist pairs for analysis only (no trade execution).
        Used during off-hours and news events to keep UI data fresh."""
        # Reset circuit breaker so a previous batch failure doesn't block this scan
        if broker_circuit_breaker.is_open:
            broker_circuit_breaker.reset()

        failed_count = 0
        total_count = 0
        for instrument in get_active_watchlist():
            total_count += 1
            try:
                analysis = await self.market_analyzer.full_analysis(instrument)
                self._last_scan_results[instrument] = analysis
                explanation = self.explanation_engine.generate_full_analysis(
                    instrument=instrument,
                    analysis_result=analysis,
                    setup_signal=None,
                )
                self._latest_explanations[instrument] = explanation
            except Exception as e:
                failed_count += 1
                logger.warning(f"Analysis-only scan failed for {instrument}: {e}")
            # Throttle between pairs to avoid 429 rate limits from broker API
            await asyncio.sleep(1.5)

        if failed_count > 0:
            logger.warning(f"Analysis-only scan: {failed_count}/{total_count} instruments failed")

    # ── Initial Scan (startup, ignores market hours) ────────────

    async def _initial_scan(self):
        """Run analysis on all watchlist pairs at startup.
        Populates _last_scan_results so the UI has data immediately.
        Also detects setups so the user sees results right away."""
        # Recover any open positions from broker (survives redeploys)
        try:
            await self._sync_positions_from_broker()
            if self.position_manager.positions:
                logger.info(f"Recovered {len(self.position_manager.positions)} open position(s) from broker")
        except Exception as e:
            logger.warning(f"Initial position sync failed: {e}")

        logger.info(f"Initial scan: analyzing {len(get_active_watchlist())} pairs...")
        setups_found = 0
        for instrument in get_active_watchlist():
            try:
                analysis = await self.market_analyzer.full_analysis(instrument)
                self._last_scan_results[instrument] = analysis

                explanation = self.explanation_engine.generate_full_analysis(
                    instrument=instrument,
                    analysis_result=analysis,
                    setup_signal=None,
                )
                self._latest_explanations[instrument] = explanation
                logger.debug(f"Initial scan: {instrument} score={analysis.score:.0f}")

                # Also detect setups during initial scan — but respect trading guards
                now = datetime.now(timezone.utc)
                market_open = self._is_market_open(now)
                friday_block = self._is_friday_no_new_trades(now)
                if market_open and not friday_block:
                    setup = await self._detect_setup(analysis)
                    if setup:
                        setups_found += 1
                        await self._handle_setup(setup, analysis, explanation)

            except Exception as e:
                logger.warning(f"Initial scan failed for {instrument}: {e}")
            # Throttle between pairs to avoid 429 rate limits from broker API
            await asyncio.sleep(2.0)

            # Broadcast progress via WebSocket so frontend knows scan is active
            if self._ws_broadcast:
                try:
                    await self._ws_broadcast("engine_status", self.get_status())
                except Exception as e:
                    logger.debug(f"WS progress broadcast failed: {e}")

        logger.info(
            f"Initial scan complete: {len(self._last_scan_results)}/{len(get_active_watchlist())} pairs analyzed, "
            f"{setups_found} setups detected"
        )

    # ── Scanning ─────────────────────────────────────────────────

    async def _scan_for_setups(self):
        """Scan all watchlist pairs for trading setups."""
        # R30 fix: prevent overlapping scan cycles that could cause duplicate trades
        if self._scan_lock.locked():
            logger.debug("Scan skipped — previous scan still running")
            return
        async with self._scan_lock:
            await self._scan_for_setups_impl()

    async def _scan_for_setups_impl(self):
        """Internal scan implementation (protected by _scan_lock)."""
        self._daily_scan_count += 1

        # ── Overtrading / Revenge Trading Prevention (Psicología Avanzada) ──
        # "sobreoperar después de una pérdida" — top-5 failure mode per mentorship
        if settings.max_trades_per_day > 0:
            today_trades = self._daily_setups_executed
            if today_trades >= settings.max_trades_per_day:
                logger.info(f"Max daily trades reached ({settings.max_trades_per_day}). Skipping scan.")
                return

        # Post-loss cooldown: if N consecutive losses today, wait before next trade
        consecutive_losses = getattr(self, '_consecutive_losses_today', 0)
        if consecutive_losses >= settings.cooldown_after_consecutive_losses:
            last_loss_time = getattr(self, '_last_loss_time', None)
            if last_loss_time:
                now_utc = datetime.now(timezone.utc)
                elapsed = (now_utc - last_loss_time).total_seconds() / 60
                if elapsed < settings.cooldown_minutes:
                    logger.info(
                        f"Cooldown active: {consecutive_losses} consecutive losses, "
                        f"waiting {settings.cooldown_minutes - elapsed:.0f}min more"
                    )
                    return

        # Round-robin scanning: if watchlist is large (>50), scan a batch per tick
        # to stay within scan interval. Each batch covers max 50 instruments.
        full_watchlist = get_active_watchlist()
        max_per_scan = 50
        if len(full_watchlist) > max_per_scan:
            batch_idx = getattr(self, '_scan_batch_idx', 0)
            # Clamp batch_idx if watchlist shrank since last scan
            if batch_idx >= len(full_watchlist):
                batch_idx = 0
            batch = full_watchlist[batch_idx:batch_idx + max_per_scan]
            self._scan_batch_idx = (batch_idx + max_per_scan) % len(full_watchlist)
            logger.info(
                f"Round-robin scan: batch {batch_idx // max_per_scan + 1} "
                f"({len(batch)}/{len(full_watchlist)} instruments)"
            )
        else:
            batch = full_watchlist

        for instrument in batch:
            try:
                # Skip instruments that the broker can't resolve (saves ~4 wasted
                # API calls per scan cycle on each broken epic — 10+ indices were
                # returning 404 every cycle before this guard).
                if hasattr(self.broker, "is_blocklisted") and self.broker.is_blocklisted(instrument):
                    continue

                # Check if we can take more risk (per-instrument style routing)
                current_style = self._style_for_instrument(instrument)
                if not self.risk_manager.can_take_trade(
                    current_style, instrument
                ):
                    continue

                # Skip if already in a trade on this instrument
                if any(
                    pos.instrument == instrument
                    for pos in self.position_manager.positions.values()
                ):
                    continue

                # TradingLab: Check reentry opportunity after TP1
                # Skip normal scan if we just handle reentry below
                reentry_info = self._reentry_candidates.get(instrument)
                if reentry_info and reentry_info.get("count", 0) < self._max_reentries_per_setup:
                    tp1_time = reentry_info.get("tp1_time")
                    now_utc = datetime.now(timezone.utc)
                    # Reentry window: 30 minutes after TP1
                    if tp1_time and (now_utc - tp1_time).total_seconds() < settings.reentry_window_seconds:
                        # Still in reentry window - normal scan will handle it
                        # The setup detection will find a new entry if conditions hold
                        pass
                    else:
                        # Reentry window expired, clear candidate
                        self._reentry_candidates.pop(instrument, None)

                # Run full analysis
                analysis = await self.market_analyzer.full_analysis(instrument)
                analysis._scan_timestamp = datetime.now(timezone.utc)  # Staleness tracking
                self._last_scan_results[instrument] = analysis

                # Generate explanation for this instrument
                explanation = self.explanation_engine.generate_full_analysis(
                    instrument=instrument,
                    analysis_result=analysis,
                    setup_signal=None,  # Will be updated if setup found
                )
                self._latest_explanations[instrument] = explanation

                # Check for strategy setups
                setup = await self._detect_setup(analysis)
                if setup:
                    # Check if this is a reentry opportunity
                    # TradingLab: re-entry risk is CONFIGURABLE per trader's plan.
                    # Defaults: Reentry 1=50%, Reentry 2=25%, Reentry 3+=25% of normal risk.
                    reentry = self._reentry_candidates.get(instrument)
                    if reentry and setup.direction == reentry.get("direction"):
                        # Validate setup "essence" is preserved (TradingLab: Reentradas Efectivas)
                        # A reentry is only valid if the original setup conditions still hold:
                        #   1. HTF trend must still be aligned with the reentry direction
                        #   2. No structural break (BOS/CHOCH) against the direction
                        #   3. Key support/resistance zones still intact
                        reentry_valid = True
                        if analysis:
                            # Check 1: HTF trend alignment
                            htf_trend = getattr(analysis, 'htf_trend', None)
                            if htf_trend is not None:
                                if setup.direction == "BUY" and htf_trend.value == "bearish":
                                    reentry_valid = False
                                    logger.info(
                                        f"[{instrument}] Reentry REJECTED — HTF trend bearish, "
                                        f"setup direction BUY. Essence not preserved."
                                    )
                                elif setup.direction == "SELL" and htf_trend.value == "bullish":
                                    reentry_valid = False
                                    logger.info(
                                        f"[{instrument}] Reentry REJECTED — HTF trend bullish, "
                                        f"setup direction SELL. Essence not preserved."
                                    )

                            # Check 2: No structural break against direction (BOS/CHOCH)
                            if reentry_valid:
                                structure_breaks = getattr(analysis, 'structure_breaks', [])
                                for sb in structure_breaks:
                                    sb_type = sb.get("type", "").lower() if isinstance(sb, dict) else ""
                                    sb_dir = sb.get("direction", "").lower() if isinstance(sb, dict) else ""
                                    if "choch" in sb_type:
                                        # CHOCH = Change of Character = structural trend reversal
                                        if (setup.direction == "BUY" and sb_dir == "bearish") or \
                                           (setup.direction == "SELL" and sb_dir == "bullish"):
                                            reentry_valid = False
                                            logger.info(
                                                f"[{instrument}] Reentry REJECTED — CHOCH detected "
                                                f"against {setup.direction}. Structural break invalidates reentry."
                                            )
                                            break

                        if not reentry_valid:
                            # Skip this reentry — essence is not preserved
                            logger.info(
                                f"[{instrument}] Reentry skipped — setup essence not preserved "
                                f"(mentorship: Reentradas Efectivas)"
                            )
                            continue

                        reentry_count = reentry.get("count", 0) + 1
                        if reentry_count == 1:
                            risk_multiplier = settings.reentry_risk_1
                        elif reentry_count == 2:
                            risk_multiplier = settings.reentry_risk_2
                        else:
                            risk_multiplier = settings.reentry_risk_3
                        setup.risk_percent *= risk_multiplier
                        raw = setup.units * risk_multiplier
                        setup.units = round(raw, 6) if abs(raw) < 100 else int(raw) or (1 if setup.units > 0 else -1)
                        logger.info(
                            f"[{instrument}] Reentry #{reentry_count} — "
                            f"risk reduced to {setup.risk_percent:.2%} ({risk_multiplier:.0%} of normal)"
                        )

                    self._daily_setups_found += 1

                    # Session quality filter: reduce confidence or skip during low-quality sessions
                    now_utc = datetime.now(timezone.utc)
                    session_name, session_quality = self._get_session_quality(now_utc, instrument)
                    logger.info(
                        f"Setup on {instrument} during {session_name} session "
                        f"(quality={session_quality:.1f})"
                    )

                    if session_quality < 0.3:
                        # OFF_HOURS: skip entirely for day trading and scalping (swing is ok)
                        if setup.style in (TradingStyle.DAY_TRADING, TradingStyle.SCALPING):
                            logger.info(
                                f"Skipping {instrument} setup: OFF_HOURS session "
                                f"(quality={session_quality:.1f}) — not suitable for {setup.style.value}"
                            )
                            setup = None
                    elif session_quality <= 0.5:
                        # SYDNEY/ASIAN sessions: reduce risk (proxy for confidence penalty of -15 pts)
                        original_risk = setup.risk_percent
                        setup.risk_percent *= 0.85
                        raw_units = setup.units * 0.85
                        setup.units = round(raw_units, 6) if abs(raw_units) < 100 else int(raw_units) or (1 if setup.units > 0 else -1)
                        setup.session_warning = (
                            f"Sesión {session_name} (calidad {session_quality:.0%}): "
                            f"riesgo reducido de {original_risk:.2%} a {setup.risk_percent:.2%}"
                        )
                        logger.warning(
                            f"Reduced risk for {instrument}: {session_name} session "
                            f"(quality={session_quality:.1f}) — risk adjusted to {setup.risk_percent:.2%}"
                        )

                    if setup is None:
                        continue

                    # Re-generate explanation with the SetupSignal context now
                    # that strategies have committed to a trade. Without this,
                    # the persisted trade reasoning ends with the
                    # "Buena estructura pero sin señal de entrada clara aún.
                    #  Monitorear." line from the analysis-phase explanation
                    # (signal=None branch in explanation_engine), which made the
                    # JPM audit trail look like the engine had ignored its own
                    # advice. _detect_setup stashes the raw SetupSignal on
                    # `trade_risk._signal`.
                    real_signal = getattr(setup, "_signal", None)
                    if real_signal is not None:
                        try:
                            explanation = self.explanation_engine.generate_full_analysis(
                                instrument=instrument,
                                analysis_result=analysis,
                                setup_signal=real_signal,
                            )
                            self._latest_explanations[instrument] = explanation
                        except Exception as e:
                            logger.debug(
                                f"Explanation regen for {instrument} failed (non-blocking): {e}"
                            )
                    await self._handle_setup(setup, analysis, explanation)

            except Exception as e:
                self._daily_errors += 1
                logger.error(f"Error scanning {instrument}: {e}")
            # Throttle between pairs to avoid 429 rate limits from broker API
            await asyncio.sleep(1.5)

        # ── Scalping scan (runs alongside normal scan if enabled) ──
        if self.scalping_analyzer and settings.scalping_enabled:
            await self._scan_scalping_setups()

    async def _scan_scalping_setups(self):
        """
        Run scalping analysis on all watchlist pairs.
        Uses compressed timeframes (H1/M15/M5/M1) and scalping risk rules.
        Note: In scalping mode, _scan_interval should be set to
        _scalping_scan_interval (30s) for faster reaction.
        """
        if not self._check_scalping_dd_limits():
            logger.warning("Scalping: DD limits reached — scalping paused")
            return

        for instrument in get_active_watchlist():
            try:
                # Skip if already in a trade on this instrument
                if any(
                    pos.instrument == instrument
                    for pos in self.position_manager.positions.values()
                ):
                    continue

                # Check if we can take more risk (scalping uses 0.5%)
                if not self.risk_manager.can_take_trade(
                    TradingStyle.SCALPING, instrument
                ):
                    continue

                # Run scalping analysis
                scalp_data = await self.scalping_analyzer.analyze_scalping(instrument)

                # Use the existing day-trading analysis if available
                base_analysis = self._last_scan_results.get(instrument)
                if base_analysis is None:
                    # Need at least a basic analysis for key levels / patterns
                    base_analysis = await self.market_analyzer.full_analysis(instrument)
                    self._last_scan_results[instrument] = base_analysis

                # Detect scalping setup
                signal = self.scalping_analyzer.detect_scalping_setup(
                    base_analysis, scalp_data, self._enabled_strategies
                )
                if signal:
                    self._daily_setups_found += 1

                    # Convert scalping SetupSignal → TradeRisk directly
                    # (skip _detect_setup which runs day-trading strategies)
                    style = TradingStyle.SCALPING
                    risk_percent = self.risk_manager.get_risk_for_style(style, signal.instrument)
                    risk_percent = self.risk_manager._adjust_for_correlation(signal.instrument, risk_percent)
                    units = await self.risk_manager.calculate_position_size(
                        signal.instrument, style, signal.entry_price, signal.stop_loss
                    )
                    if units == 0:
                        continue
                    if signal.direction == "SELL":
                        units = -abs(units)

                    sl_distance = abs(signal.entry_price - signal.stop_loss)
                    rr = abs(signal.take_profit_1 - signal.entry_price) / max(sl_distance, 0.00001)

                    setup = TradeRisk(
                        instrument=signal.instrument,
                        style=style,
                        risk_percent=risk_percent,
                        units=units,
                        stop_loss=signal.stop_loss,
                        take_profit_1=signal.take_profit_1,
                        take_profit_max=signal.take_profit_max,
                        reward_risk_ratio=rr,
                        entry_price=signal.entry_price,
                        direction=signal.direction,
                        entry_type=getattr(signal, 'entry_type', 'MARKET'),
                        limit_price=getattr(signal, 'limit_price', None),
                        trailing_tp_only=getattr(signal, 'trailing_tp_only', False),
                        strategy_variant=getattr(signal, 'strategy_variant', None),
                    )

                    explanation = self._latest_explanations.get(instrument)
                    if explanation is None:
                        explanation = self.explanation_engine.generate_full_analysis(
                            instrument=instrument,
                            analysis_result=base_analysis,
                            setup_signal=signal,
                        )
                    await self._handle_setup(setup, base_analysis, explanation)

            except Exception as e:
                self._daily_errors += 1
                logger.error(f"Scalping scan error for {instrument}: {e}")
            await asyncio.sleep(1.0)

    def _check_scalping_dd_limits(self) -> bool:
        """
        Check scalping drawdown limits.
        Returns False if daily DD > 5% or total DD > 10% (from config).
        Resets daily DD counter at midnight UTC.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Reset daily DD at midnight
        if self._scalping_dd_date != today:
            self._scalping_daily_dd = 0.0
            self._scalping_dd_date = today

        # Initialize peak balance if not set
        if self._scalping_peak_balance <= 0:
            self._scalping_peak_balance = getattr(
                self.risk_manager, '_current_balance', 0.0
            ) or 0.0

        # Update peak balance
        current_balance = getattr(
            self.risk_manager, '_current_balance', 0.0
        ) or 0.0
        if current_balance > self._scalping_peak_balance:
            self._scalping_peak_balance = current_balance

        # Calculate total DD from peak
        if self._scalping_peak_balance > 0:
            self._scalping_total_dd = (
                (self._scalping_peak_balance - current_balance) /
                self._scalping_peak_balance
            )

        # Check limits from config
        max_daily_dd = settings.scalping_max_daily_dd  # default 0.05 (5%)
        max_total_dd = settings.scalping_max_total_dd  # default 0.10 (10%)

        if self._scalping_daily_dd > max_daily_dd:
            logger.warning(
                f"Scalping PAUSED: daily DD {self._scalping_daily_dd:.2%} "
                f"> limit {max_daily_dd:.2%}"
            )
            return False

        if self._scalping_total_dd > max_total_dd:
            logger.warning(
                f"Scalping PAUSED: total DD {self._scalping_total_dd:.2%} "
                f"> limit {max_total_dd:.2%}"
            )
            return False

        return True

    async def _detect_setup(self, analysis: AnalysisResult) -> Optional[TradeRisk]:
        """
        Detect trading setups using all 6 color strategies from TradingLab.

        Strategy detection order:
        1. BLUE  - Trend change in 1H (3 variants A/B/C)
        2. RED   - Trend change in 4H
        3. PINK  - Corrective pattern continuation
        4. WHITE - Post-Pink continuation
        5. BLACK - Counter-trend anticipation (min 2:1 R:R)
        6. GREEN - Weekly + daily + 15M entry (most lucrative)

        The get_best_setup() function runs all 6 and returns the highest-confidence match.
        """
        # Run strategies filtered by user selection
        signal: Optional[SetupSignal] = get_best_setup(
            analysis, self._enabled_strategies
        )

        if signal is None:
            return None

        logger.info(
            f"Strategy {signal.strategy_variant} detected on {signal.instrument}: "
            f"{signal.direction} | Confidence: {signal.confidence:.0f}%"
        )

        # AI enrichment: generate explanation and opinion (INFORMATIONAL ONLY)
        # Per TradingLab mentorship: 0% discretion for beginners. Technical analysis
        # decides, AI does NOT block or modify trades. AI provides context for learning.
        if self.ai_analyzer:
            try:
                ai_result = await self.ai_analyzer.validate_setup_with_ai(signal, analysis)
                ai_score = ai_result.get("ai_score", 0)
                ai_rec = ai_result.get("ai_recommendation", "SKIP")
                ai_reason = ai_result.get("ai_reasoning", "")
                logger.info(
                    f"AI opinion for {signal.instrument}: "
                    f"Score={ai_score} Rec={ai_rec} — {ai_reason}"
                )
                # Store AI opinion for emails/UI (informational, not gating)
                signal._ai_score = ai_score
                signal._ai_recommendation = ai_rec
                signal._ai_reasoning = ai_reason
                # NOTE: AI does NOT block trades. Technical analysis is the sole decision maker.
                # AI does NOT modify SL/TP. Fibonacci and EMA rules from mentorship are final.
                if ai_rec != "TAKE":
                    logger.info(
                        f"AI says {ai_rec} for {signal.instrument} (score={ai_score}) "
                        f"— LOGGED ONLY, trade proceeds per mentorship 0% discretion rule"
                    )
            except Exception as e:
                logger.warning(f"AI enrichment failed (non-blocking): {e}")
                # AI failure does NOT block the trade

        # Validate risk management (strategy-specific R:R minimums)
        if not self.risk_manager.validate_reward_risk(
            signal.entry_price, signal.stop_loss, signal.take_profit_1,
            strategy=signal.strategy_variant,
        ):
            logger.info(f"R:R validation failed for {signal.instrument} ({signal.strategy_variant})")
            return None

        # TradingLab: Scale-in rule — no new trade unless BE on existing
        # "si tú no tienes como mínimo el breakeven puesto, tú no puedes reentrar"
        if not self.risk_manager.can_scale_in(signal.instrument):
            logger.info(
                f"Scale-in blocked for {signal.instrument}: "
                f"existing position has not reached BE"
            )
            return None

        # Per-instrument style routing — equities use SWING when enabled.
        style = self._style_for_instrument(signal.instrument)
        units = await self.risk_manager.calculate_position_size(
            signal.instrument, style, signal.entry_price, signal.stop_loss
        )
        if units == 0:
            logger.warning(
                f"Setup {signal.strategy_variant} on {signal.instrument} skipped: "
                f"position size too small for current balance "
                f"(entry={signal.entry_price:.5f}, sl={signal.stop_loss:.5f})"
            )
            return None

        # Adjust direction sign for units
        if signal.direction == "SELL":
            units = -abs(units)

        risk_percent = self.risk_manager.get_risk_for_style(style, signal.instrument)
        risk_percent = self.risk_manager._adjust_for_correlation(signal.instrument, risk_percent)
        sl_distance = abs(signal.entry_price - signal.stop_loss)
        rr = abs(signal.take_profit_1 - signal.entry_price) / max(sl_distance, 0.00001)

        trade_risk = TradeRisk(
            instrument=signal.instrument,
            style=style,
            risk_percent=risk_percent,
            units=units,
            stop_loss=signal.stop_loss,
            take_profit_1=signal.take_profit_1,
            take_profit_max=signal.take_profit_max,
            reward_risk_ratio=rr,
            entry_price=signal.entry_price,
            direction=signal.direction,
            entry_type=getattr(signal, 'entry_type', 'MARKET'),
            limit_price=getattr(signal, 'limit_price', None),
            trailing_tp_only=getattr(signal, 'trailing_tp_only', False),
            strategy_variant=getattr(signal, 'strategy_variant', None),
        )
        # Carry strategy confidence and AI opinion from signal to setup for email/UI
        trade_risk._strategy_confidence = getattr(signal, 'confidence', 0.0)
        trade_risk._ai_score = getattr(signal, '_ai_score', 0)
        trade_risk._ai_recommendation = getattr(signal, '_ai_recommendation', '')
        trade_risk._ai_reasoning = getattr(signal, '_ai_reasoning', '')
        # Carry the raw SetupSignal so the scan loop can re-generate the
        # explanation with signal context (otherwise the pre-setup "Monitorear"
        # recommendation leaks into the persisted trade reasoning — root cause
        # confirmed 2026-04-22 JPM forensic audit).
        trade_risk._signal = signal
        return trade_risk

    def _calculate_sl_tp(
        self,
        analysis: AnalysisResult,
        direction: str,
        entry_price: float,
    ) -> tuple:
        """Calculate Stop Loss and Take Profit from analysis levels."""
        supports = analysis.key_levels.get("supports", [])
        resistances = analysis.key_levels.get("resistances", [])

        if direction == "BUY":
            # SL below nearest support
            valid_supports = [s for s in supports if s < entry_price]
            if not valid_supports:
                return None, None
            sl = max(valid_supports)

            # TP1 = nearest resistance above (previous high)
            valid_resistances = [r for r in resistances if r > entry_price]
            if not valid_resistances:
                return None, None
            tp1 = min(valid_resistances)

        else:  # SELL
            # SL above nearest resistance
            valid_resistances = [r for r in resistances if r > entry_price]
            if not valid_resistances:
                return None, None
            sl = min(valid_resistances)

            # TP1 = nearest support below (previous low)
            valid_supports = [s for s in supports if s < entry_price]
            if not valid_supports:
                return None, None
            tp1 = max(valid_supports)

        return sl, tp1

    # ── Setup Handling (AUTO vs MANUAL) ───────────────────────────

    async def _handle_setup(
        self,
        setup: TradeRisk,
        analysis: AnalysisResult,
        explanation: StrategyExplanation,
    ):
        """Route a detected setup based on the current trading mode."""
        # Quality gate: only send operable setups to email/queue
        # Per mentorship: 0% discretion, but don't waste time on low-quality setups
        # that even the technical analysis says "no operar"
        min_score = 50  # Minimum analysis score to be considered operable
        if analysis.score < min_score:
            # Quality-gate filter fired (R:R, cooldown, news blackout, scale-in, etc.).
            # IA does NOT contribute to this counter — it only adds narrative analysis.
            self._daily_setups_filtered += 1
            logger.info(
                f"Setup {setup.instrument} {setup.direction} filtered: "
                f"score {analysis.score:.0f} < {min_score} minimum — not operable"
            )
            return

        reasoning = self._build_setup_reasoning(setup, analysis, explanation)

        # Attach strategy name from explanation to setup for later use
        setup._strategy_name = getattr(explanation, 'strategy_detected', None) or "DETECTED"

        # Attach reasoning to setup so it's available in _execute_setup for DB/alerts
        setup._reasoning = reasoning

        if self.mode == TradingMode.AUTO:
            # Execute immediately (original behavior)
            await self._execute_setup(setup)
        else:
            # MANUAL mode: queue for user approval
            await self._queue_setup(setup, reasoning)

    def _build_setup_reasoning(
        self,
        setup: TradeRisk,
        analysis: AnalysisResult,
        explanation: StrategyExplanation,
    ) -> str:
        """Build a Spanish reasoning string for the setup."""
        parts = []
        parts.append(f"Instrumento: {setup.instrument}")
        parts.append(f"Dirección: {'COMPRA' if setup.direction == 'BUY' else 'VENTA'}")
        parts.append(f"Score de análisis: {analysis.score:.0f}/100")
        parts.append(f"Sesgo general: {explanation.overall_bias}")
        parts.append(f"Confianza: {explanation.confidence_level}")

        if explanation.strategy_detected:
            name = self.explanation_engine.STRATEGY_NAMES.get(
                explanation.strategy_detected, explanation.strategy_detected
            )
            parts.append(f"Estrategia: {name}")

        if explanation.conditions_met:
            parts.append("Condiciones cumplidas:")
            for c in explanation.conditions_met:
                parts.append(f"  - {c}")

        if explanation.conditions_missing:
            parts.append("Condiciones faltantes:")
            for c in explanation.conditions_missing:
                parts.append(f"  - {c}")

        parts.append(f"R:R = 1:{setup.reward_risk_ratio:.2f}")
        parts.append(explanation.recommendation)

        # BLACK is contra-trend by design (Elliott Wave 1 anticipation): the
        # SELL/BUY direction can look opposite to the HTF bias to a casual
        # reader. Surface this so the audit trail does not look like the engine
        # contradicted itself (added 2026-04-22 after JPM forensic audit).
        if (setup.strategy_variant or "").upper() == "BLACK":
            parts.append(
                "Nota: BLACK es estrategia CONTRATENDENCIA (anticipacion Onda 1 "
                "Elliott). Cuando el sesgo HTF es ALCISTA, BLACK busca VENTA; "
                "cuando es BAJISTA, busca COMPRA. La aparente contradiccion "
                "direccion vs sesgo es esperada y correcta."
            )

        return "\n".join(parts)

    async def _queue_setup(self, setup: TradeRisk, reasoning: str):
        """Queue a setup for manual approval (MANUAL mode)."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=self._setup_expiry_minutes)

        pending = PendingSetup(
            id=str(uuid.uuid4()),
            timestamp=now.isoformat(),
            instrument=setup.instrument,
            strategy=getattr(setup, '_strategy_name', 'DETECTED'),
            direction=setup.direction,
            entry_price=setup.entry_price,
            stop_loss=setup.stop_loss,
            take_profit=setup.take_profit_1,
            units=setup.units,
            confidence=getattr(setup, '_strategy_confidence', 0.0) or min(setup.reward_risk_ratio * 33, 100.0),
            risk_reward_ratio=setup.reward_risk_ratio,
            reasoning=reasoning,
            take_profit_max=setup.take_profit_max,
            trailing_tp_only=setup.trailing_tp_only,
            strategy_variant=setup.strategy_variant,
            status="pending",
            expires_at=expires_at.isoformat(),
        )

        self.pending_setups.append(pending)

        logger.warning("=" * 50)
        logger.warning(f"SETUP QUEUED (MANUAL MODE): {setup.direction} {setup.instrument}")
        logger.warning(f"  Entry: {setup.entry_price:.5f}")
        logger.warning(f"  SL: {setup.stop_loss:.5f}")
        logger.warning(f"  TP: {setup.take_profit_1:.5f}")
        logger.warning(f"  R:R: {setup.reward_risk_ratio:.2f}")
        logger.warning(f"  Expires: {expires_at.isoformat()}")
        logger.warning(f"  ID: {pending.id}")
        logger.warning("=" * 50)

        # Push native notification
        dir_text = 'COMPRA' if setup.direction == 'BUY' else 'VENTA'
        inst_text = setup.instrument.replace('_', '/')
        self._push_notification(
            "setup_pending",
            f"Setup: {inst_text} {dir_text}",
            f"R:R {setup.reward_risk_ratio:.1f} | Entrada: {setup.entry_price:.5f} | Esperando aprobación",
            {"setup_id": pending.id, "instrument": setup.instrument},
        )

        # Send external alerts
        if self.alert_manager:
            try:
                await self.alert_manager.send_setup_pending(
                    instrument=setup.instrument,
                    direction=setup.direction,
                    entry=setup.entry_price,
                    rr=setup.reward_risk_ratio,
                    sl=setup.stop_loss,
                    tp=setup.take_profit_1,
                    strategy=setup.strategy_variant or getattr(setup, '_strategy_name', ''),
                    ai_score=getattr(setup, '_ai_score', 0),
                    ai_recommendation=getattr(setup, '_ai_recommendation', ''),
                    ai_reasoning=getattr(setup, '_ai_reasoning', ''),
                    reasoning=reasoning,
                )
            except Exception as ae:
                logger.warning(f"Alert send failed: {ae}")

        # Broadcast via WebSocket if callback is set
        if self._ws_broadcast:
            try:
                await self._ws_broadcast("new_setup", pending.to_dict())
            except Exception as e:
                logger.error(f"Failed to broadcast pending setup via WS: {e}")

    # ── Trade Execution ──────────────────────────────────────────

    @staticmethod
    def _is_equity_market_open(now: datetime) -> bool:
        """NYSE/NASDAQ regular session = Mon-Fri 13:30-20:00 UTC.
        Used to skip equity setups when the market is closed (broker would
        reject anyway with "Instrument is currently closed", but rejecting
        upstream avoids broker spam + a bad audit trail entry).
        """
        wd = now.weekday()  # 0=Mon..6=Sun
        if wd >= 5:
            return False
        h = now.hour
        m = now.minute
        # Open at 13:30 UTC, close at 20:00 UTC
        if h < 13 or (h == 13 and m < 30):
            return False
        if h >= 20:
            return False
        return True

    def _is_equity_instrument(self, instrument: str) -> bool:
        try:
            return instrument in settings.equities_watchlist
        except Exception:
            return False

    async def _execute_setup(self, setup: TradeRisk):
        """Execute a validated trading setup (AUTO mode).
        Supports MARKET and LIMIT entry types from TradingLab."""
        entry_type = getattr(setup, 'entry_type', 'MARKET')
        limit_price = getattr(setup, 'limit_price', None)

        # Equity market hours guard — broker rejects with "Instrument is
        # currently closed" anyway, but skipping upstream avoids the
        # rejected order in the audit log + the broker's circuit-breaker
        # noise (observed live: IBB BLACK setup at 03:39 UTC tried to fire
        # while NYSE was closed, broker rejected, log got polluted).
        if self._is_equity_instrument(setup.instrument):
            now_utc = datetime.now(timezone.utc)
            if not self._is_equity_market_open(now_utc):
                logger.info(
                    f"Skipping {setup.instrument} {setup.direction}: NYSE closed "
                    f"({now_utc.strftime('%H:%M UTC')}). Equity hours: Mon-Fri 13:30-20:00 UTC."
                )
                return None

        logger.info("=" * 50)
        logger.info(f"EXECUTING TRADE: {setup.direction} {setup.instrument}")
        logger.info(f"  Entry Type: {entry_type}")
        logger.info(f"  Entry: {setup.entry_price:.5f}" + (f" (Limit: {limit_price:.5f})" if limit_price else ""))
        logger.info(f"  SL: {setup.stop_loss:.5f}")
        logger.info(f"  TP1: {setup.take_profit_1:.5f}")
        logger.info(f"  Units: {setup.units}")
        logger.info(f"  R:R: {setup.reward_risk_ratio:.2f}")
        logger.info(f"  Risk: {setup.risk_percent:.2%}")
        logger.info(f"  Mode: {self.mode.value}")
        logger.info("=" * 50)

        # Safety net: reject if TP is on the wrong side of entry
        effective_entry = limit_price or setup.entry_price
        if setup.direction == "BUY" and setup.take_profit_1 <= effective_entry:
            logger.error(f"REJECTED {setup.instrument}: TP1 ({setup.take_profit_1:.5f}) <= entry ({effective_entry:.5f}) for BUY")
            return None
        if setup.direction == "SELL" and setup.take_profit_1 >= effective_entry:
            logger.error(f"REJECTED {setup.instrument}: TP1 ({setup.take_profit_1:.5f}) >= entry ({effective_entry:.5f}) for SELL")
            return None

        try:
            # TradingLab: Support limit entries for confluence zones
            if entry_type == "LIMIT" and limit_price and hasattr(self.broker, 'place_limit_order'):
                result = await self.broker.place_limit_order(
                    instrument=setup.instrument,
                    units=setup.units,
                    price=limit_price,
                    stop_loss=setup.stop_loss,
                    take_profit=setup.take_profit_1,
                )
                logger.info(f"Limit order placed at {limit_price:.5f} for {setup.instrument}")
            elif entry_type == "STOP" and limit_price and hasattr(self.broker, 'place_stop_order'):
                result = await self.broker.place_stop_order(
                    instrument=setup.instrument,
                    units=setup.units,
                    stop_price=limit_price,
                    stop_loss=setup.stop_loss,
                    take_profit=setup.take_profit_1,
                )
                logger.info(f"Stop order placed at {limit_price:.5f} for {setup.instrument}")
            else:
                # Default: market order
                # For trailing_tp_only (crypto GREEN): don't send hard TP to broker
                # The position manager will trail with EMA 50 instead of hard TP exit
                broker_tp = None if getattr(setup, 'trailing_tp_only', False) else setup.take_profit_1
                result = await self.broker.place_market_order(
                    instrument=setup.instrument,
                    units=setup.units,
                    stop_loss=setup.stop_loss,
                    take_profit=broker_tp,
                )

            # result is now an OrderResult dataclass
            if not result.success:
                logger.error(f"Order failed for {setup.instrument}: {result.error}")
                return

            trade_id = result.trade_id
            # Use actual fill price from broker if available (not scan-time price)
            fill_price = getattr(result, 'fill_price', None) or setup.entry_price
            if fill_price != setup.entry_price:
                logger.info(f"Fill price {fill_price:.5f} differs from scan price {setup.entry_price:.5f} (slippage)")

            if not trade_id:
                logger.critical(
                    f"ORPHANED TRADE: Order succeeded but no trade_id for {setup.instrument}. "
                    f"Trade is LIVE on broker but NOT tracked by risk/position manager. "
                    f"Manual intervention required!"
                )
                if self.alert_manager:
                    try:
                        await self.alert_manager.send_alert(
                            "engine_status",
                            f"⚠️ ORPHANED TRADE — {setup.instrument}",
                            f"Order succeeded but broker returned no trade_id.\n"
                            f"Direction: {setup.direction} | Units: {setup.units}\n"
                            f"Entry: {setup.entry_price:.5f} | SL: {setup.stop_loss:.5f}\n"
                            f"THIS TRADE IS LIVE BUT INVISIBLE TO THE SYSTEM.\n"
                            f"Check broker manually and close if needed.",
                            {"instrument": setup.instrument, "direction": setup.direction},
                        )
                    except Exception as ae:
                        logger.error(f"CRITICAL: Orphaned trade alert ALSO failed to send: {ae}")
                return

            if trade_id:
                # Register with risk manager
                self.risk_manager.register_trade(
                    trade_id, setup.instrument, setup.risk_percent
                )

                # Track with position manager
                self.position_manager.track_position(ManagedPosition(
                    trade_id=trade_id,
                    instrument=setup.instrument,
                    direction=setup.direction,
                    entry_price=fill_price,
                    original_sl=setup.stop_loss,
                    current_sl=setup.stop_loss,
                    take_profit_1=setup.take_profit_1,
                    take_profit_max=setup.take_profit_max,
                    units=setup.units,
                    style=setup.style.value if hasattr(setup.style, 'value') else str(setup.style),
                    highest_price=fill_price,
                    lowest_price=fill_price,
                    trailing_tp_only=getattr(setup, 'trailing_tp_only', False),
                    strategy_variant=getattr(setup, 'strategy_variant', None),
                ))

                # Persist trade to database
                if self._db:
                    try:
                        await self._db.record_trade({
                            "id": trade_id,
                            "instrument": setup.instrument,
                            "strategy": getattr(setup, '_strategy_name', 'DETECTED'),
                            "strategy_variant": setup.strategy_variant or getattr(setup, '_strategy_name', 'DETECTED'),
                            "direction": setup.direction,
                            "units": abs(setup.units),
                            "entry_price": fill_price,
                            "stop_loss": setup.stop_loss,
                            "take_profit": setup.take_profit_1,
                            "mode": self.mode.value,
                            "confidence": getattr(setup, '_strategy_confidence', 0.0) or min(setup.reward_risk_ratio * 33, 100.0),
                            "risk_reward_ratio": setup.reward_risk_ratio,
                            "reasoning": getattr(setup, '_reasoning', None) or f"R:R {setup.reward_risk_ratio:.2f} | Risk {setup.risk_percent:.2%}",
                        })
                    except Exception as db_err:
                        logger.warning(f"DB record_trade failed (non-critical): {db_err}")

                # Send native notification
                dir_text = 'COMPRA' if setup.direction == 'BUY' else 'VENTA'
                inst_text = setup.instrument.replace('_', '/')
                self._push_notification(
                    "trade_executed",
                    f"Trade Ejecutado: {inst_text}",
                    f"{dir_text} | Entry: {fill_price:.5f} | SL: {setup.stop_loss:.5f} | TP: {setup.take_profit_1:.5f} | R:R {setup.reward_risk_ratio:.1f}",
                    {"trade_id": trade_id, "instrument": setup.instrument},
                )
                self._daily_setups_executed += 1
                logger.info(f"Trade {trade_id} opened and tracked")

                # Broadcast trade_executed via WebSocket — fire-and-forget so
                # a slow WS client can't block screenshot/alert dispatch.
                if self._ws_broadcast:
                    async def _ws_send():
                        try:
                            await self._ws_broadcast("trade_executed", {
                                "trade_id": trade_id,
                                "instrument": setup.instrument,
                                "direction": setup.direction,
                                "entry_price": fill_price,
                                "stop_loss": setup.stop_loss,
                                "take_profit": setup.take_profit_1,
                                "units": setup.units,
                                "risk_reward_ratio": setup.reward_risk_ratio,
                                "risk_percent": setup.risk_percent,
                                "strategy": getattr(setup, '_strategy_name', 'DETECTED'),
                                "mode": self.mode.value,
                            })
                        except Exception as ws_err:
                            logger.warning(f"WS broadcast trade_executed failed: {ws_err}")
                    self._spawn_bg(_ws_send(), name="ws_trade_executed")

                # Screenshot on trade open (Trading Plan rule) — fire-and-forget.
                if self.screenshot_generator:
                    candles = None
                    ema_vals = None
                    if setup.instrument in self._last_scan_results:
                        analysis = self._last_scan_results[setup.instrument]
                        candles = getattr(analysis, 'candles_m5', None) or getattr(analysis, 'last_candles', {}).get('M5')
                        ema_vals = getattr(analysis, 'ema_values', None)

                    async def _capture():
                        try:
                            await self.screenshot_generator.capture_trade_open(
                                trade_id=trade_id,
                                instrument=setup.instrument,
                                direction=setup.direction,
                                entry_price=fill_price,
                                sl=setup.stop_loss,
                                tp1=setup.take_profit_1,
                                tp_max=setup.take_profit_max,
                                strategy=getattr(setup, '_strategy_name', 'DETECTED'),
                                confidence=(getattr(setup, '_strategy_confidence', 0.0) or min(setup.reward_risk_ratio * 33, 100.0)) / 100.0,
                                candles=candles,
                                ema_values=ema_vals,
                            )
                        except Exception as ss_err:
                            logger.warning(f"Screenshot capture failed (non-critical): {ss_err}")
                    self._spawn_bg(_capture(), name="capture_trade_open")

                # TradingLab: Track reentry count
                if setup.instrument in self._reentry_candidates:
                    self._reentry_candidates[setup.instrument]["count"] = (
                        self._reentry_candidates[setup.instrument].get("count", 0) + 1
                    )
                    logger.info(
                        f"Reentry #{self._reentry_candidates[setup.instrument]['count']} "
                        f"executed for {setup.instrument}"
                    )

                # Send external alerts
                if self.alert_manager:
                    try:
                        await self.alert_manager.send_trade_executed(
                            instrument=setup.instrument,
                            direction=setup.direction,
                            entry=fill_price,
                            sl=setup.stop_loss,
                            tp=setup.take_profit_1,
                            rr=setup.reward_risk_ratio,
                            strategy=getattr(setup, '_strategy_name', 'DETECTED'),
                        )
                    except Exception as ae:
                        logger.warning(f"Alert send failed (non-critical): {ae}")

                return True

        except Exception as e:
            logger.error(f"Failed to execute trade: {e}")

    async def _execute_approved_setup(self, setup: PendingSetup):
        """Execute a previously pending setup that has been approved."""
        logger.info(f"Executing approved setup: {setup.id} | {setup.instrument}")

        # Re-check current price - market may have moved
        try:
            price_data = await self.broker.get_current_price(setup.instrument)
        except Exception as e:
            logger.error(f"Cannot get price for approved setup: {e}")
            setup.status = "expired"
            return

        current_price = (
            price_data.ask if setup.direction == "BUY" else price_data.bid
        )

        # Check if entry is still reasonable (within 0.5% of original)
        if setup.entry_price <= 0:
            logger.error(f"Invalid entry price for setup {setup.id}")
            setup.status = "expired"
            return
        price_diff_pct = abs(current_price - setup.entry_price) / setup.entry_price
        if price_diff_pct > 0.005:
            logger.warning(
                f"Price moved too far from original entry "
                f"({setup.entry_price:.5f} -> {current_price:.5f}, "
                f"{price_diff_pct:.2%}). Skipping execution."
            )
            setup.status = "expired"
            # Notify user that their approved setup was not executed
            if self._ws_broadcast:
                try:
                    await self._ws_broadcast("setup_expired", {
                        "setup_id": setup.id,
                        "instrument": setup.instrument,
                        "reason": f"Price moved {price_diff_pct:.2%} from entry",
                    })
                except Exception:
                    pass
            if self.alert_manager:
                try:
                    await self.alert_manager.send_alert(
                        "setup_expired",
                        f"Setup Expired: {setup.instrument}",
                        f"Your approved setup was not executed because price moved "
                        f"{price_diff_pct:.2%} from the original entry "
                        f"({setup.entry_price:.5f} -> {current_price:.5f}).",
                        {"instrument": setup.instrument},
                    )
                except Exception:
                    pass
            return

        # Build a TradeRisk from the pending setup
        # R30 fix: per-instrument style (was hardcoded DAY_TRADING; now also
        # respects swing_for_equities for equity setups).
        _style = self._style_for_instrument(setup.instrument)
        _risk = self.risk_manager.get_risk_for_style(_style, setup.instrument)
        _risk = self.risk_manager._adjust_for_correlation(setup.instrument, _risk)

        # TE-02 fix: recalculate units at execution time since entry price shifted
        # units = risk_amount / sl_distance — SL distance changed with new entry
        units = await self.risk_manager.calculate_position_size(
            setup.instrument, _style, current_price, setup.stop_loss
        )
        # calculate_position_size returns 0 for "no trade" (e.g., insufficient margin)
        # and signed units otherwise (positive for BUY, negative for SELL). Check
        # magnitude, not sign — a negative value is a valid SELL, not an error.
        if units == 0:
            logger.warning(
                f"Approved setup {setup.id}: recalculated units=0 at "
                f"current price {current_price:.5f} — marking expired"
            )
            setup.status = "expired"
            return

        # Ensure sign matches direction (idempotent for correctly-signed values
        # from calculate_position_size; defensive if caller constructs manually).
        if setup.direction == "SELL":
            units = -abs(units)
        else:
            units = abs(units)

        trade_risk = TradeRisk(
            instrument=setup.instrument,
            style=_style,
            risk_percent=_risk,
            units=units,
            stop_loss=setup.stop_loss,
            take_profit_1=setup.take_profit,
            take_profit_max=setup.take_profit_max,
            reward_risk_ratio=setup.risk_reward_ratio,
            entry_price=current_price,
            direction=setup.direction,
            trailing_tp_only=setup.trailing_tp_only,
            strategy_variant=setup.strategy_variant,
        )
        # Preserve strategy name from PendingSetup so DB records the correct color
        trade_risk._strategy_name = setup.strategy

        result = await self._execute_setup(trade_risk)
        if not result:
            logger.warning(f"Approved setup {setup.id} execution failed — marking as expired")
            setup.status = "expired"

    # ── Daily Summary ────────────────────────────────────────────

    async def _send_daily_summary(self):
        """Send daily trading summary via alerts and optionally via AI-generated report."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        logger.info(f"Generating daily summary for {today}...")

        stats = {}
        if self._db:
            try:
                stats = await self._db.get_daily_stats(today)
            except Exception as e:
                logger.warning(f"Failed to get daily stats: {e}")

        # Send basic summary via alert channels (includes activity proof)
        if self.alert_manager:
            try:
                await self.alert_manager.send_daily_summary({
                    "total_pnl": stats.get("total_pnl", 0.0),
                    "trades_count": stats.get("total_trades", 0),
                    "wins": stats.get("winning_trades", 0),
                    "losses": stats.get("losing_trades", 0),
                    "best_trade": f"{stats.get('best_trade_pnl', 0):.2f}",
                    "worst_trade": f"{stats.get('worst_trade_pnl', 0):.2f}",
                    # Activity proof — proves the engine was alive all day
                    "scans_completed": self._daily_scan_count,
                    "setups_found": self._daily_setups_found,
                    "setups_executed": self._daily_setups_executed,
                    "setups_filtered": self._daily_setups_filtered,
                    "scan_errors": self._daily_errors,
                })
            except Exception as e:
                logger.warning(f"Failed to send daily summary alert: {e}")

        # Generate AI-powered daily report
        if self.ai_analyzer and self._db:
            try:
                trades = await self._db.get_trade_history(limit=50)
                today_trades = [t for t in trades if t.get("opened_at", "").startswith(today)]
                account = None
                try:
                    account = await self.broker.get_account_summary()
                except Exception:
                    pass
                # Snapshot scan results so a concurrent scan writing to
                # _last_scan_results can't raise "dict changed size during
                # iteration" while we build the dict-comp.
                _scan_snapshot = dict(self._last_scan_results)
                report = await self.ai_analyzer.generate_daily_report(
                    trades_today=today_trades,
                    account_summary={"balance": account.balance, "currency": account.currency} if account else {},
                    scan_results={
                        inst: {"score": r.score, "htf_trend": r.htf_trend.value if hasattr(r.htf_trend, 'value') else str(r.htf_trend)}
                        for inst, r in _scan_snapshot.items()
                    },
                    pending_setups=[],
                )
                # Send AI report via email
                if self.alert_manager:
                    await self.alert_manager.send_alert(
                        "ai_daily_report",
                        f"Atlas - Daily Report {today}",
                        report,
                    )
            except Exception as e:
                logger.warning(f"AI daily report failed: {e}")

    # ── Weekly Self-Improvement Review ────────────────────────

    async def _maybe_run_weekly_review(self, now: datetime):
        """Sunday 08:00 UTC — aggregate last 7 days, run TuningEngine, email or auto-apply.

        Mirror of `_maybe_send_monthly_asr`. Single-shot per (year, isoweek)
        via `self._weekly_review_done` flag.
        """
        if now.weekday() != 6 or now.hour != 8 or now.minute > 5:  # 6 = Sunday
            return
        if not self._db:
            return
        iso_year, iso_week, _ = now.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"
        if getattr(self, "_weekly_review_done", None) == week_key:
            return
        self._weekly_review_done = week_key

        # If self-improvement is fully off, nothing to do.
        mode = getattr(settings, "self_improvement_tuning_mode", "off")
        if mode == "off":
            logger.info(f"Weekly review {week_key}: tuning_mode=off, skipping")
            return

        try:
            from core.self_improvement import (
                TuningEngine, ProposalStore, apply_proposal,
            )
            store = ProposalStore()
            engine_t = TuningEngine(settings, store)

            # Aggregate last 7 days from trade journal
            week_start = (now - timedelta(days=7)).isoformat()
            trades = await self._db.get_trades_between(week_start, now.isoformat())
            if not trades:
                logger.info(f"Weekly review {week_key}: no trades in window, no proposals")
                return

            stats = self._build_tuning_stats(trades)
            proposals = engine_t.evaluate(stats)
            logger.info(f"Weekly review {week_key}: {len(proposals)} proposals emitted")

            for p in proposals:
                store.create(p)
                # Always email so Sergio can audit
                if self.alert_manager:
                    try:
                        await self.alert_manager.send_alert(
                            "tuning_proposal",
                            f"Atlas Tuning Proposal — {p.parameter_key}",
                            (
                                f"<b>Parámetro:</b> {p.parameter_key}\n"
                                f"<b>Actual:</b> {p.current_value}\n"
                                f"<b>Propuesto:</b> {p.proposed_value}\n"
                                f"<b>Tier:</b> {p.tier}\n\n"
                                f"<b>Razón:</b>\n{p.rationale}\n\n"
                                f"<b>Aprobar:</b> POST /api/v1/self-improvement/proposals/{p.id}/approve\n"
                                f"<b>Rechazar:</b> POST /api/v1/self-improvement/proposals/{p.id}/reject"
                            ),
                        )
                    except Exception as e:
                        logger.warning(f"Failed to email proposal {p.id}: {e}")

                # Auto-apply only SAFE-tier when mode == "auto"
                if mode == "auto" and p.tier == "safe":
                    persist = self._make_tuning_persist_fn()
                    if apply_proposal(settings, p, persist):
                        store._save()
                        logger.info(f"Auto-applied SAFE proposal {p.id}: {p.parameter_key}={p.proposed_value}")
        except Exception as e:
            logger.warning(f"Weekly review {week_key} failed: {e}")

    @staticmethod
    def _build_tuning_stats(trades: list) -> dict:
        """Reduce a list of closed trades to the small dict TuningEngine expects."""
        total = len(trades)
        wins = sum(1 for t in trades if (t.get("pnl", 0) or 0) > 0)
        losses = sum(1 for t in trades if (t.get("pnl", 0) or 0) < 0)
        win_rate = wins / total if total else 0.0
        gross_profit = sum((t.get("pnl", 0) or 0) for t in trades if (t.get("pnl", 0) or 0) > 0)
        gross_loss = abs(sum((t.get("pnl", 0) or 0) for t in trades if (t.get("pnl", 0) or 0) < 0))
        pf = (gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)

        # Per-style buckets (best-effort: trades dict may or may not have 'style' field)
        by_style: Dict[str, Dict[str, float]] = {}
        for s in ("day_trading", "swing", "scalping"):
            tr = [t for t in trades if t.get("style") == s or t.get("trading_style") == s]
            if not tr:
                continue
            wn = sum(1 for t in tr if (t.get("pnl", 0) or 0) > 0)
            gp = sum((t.get("pnl", 0) or 0) for t in tr if (t.get("pnl", 0) or 0) > 0)
            gl = abs(sum((t.get("pnl", 0) or 0) for t in tr if (t.get("pnl", 0) or 0) < 0))
            by_style[s] = {
                "trades": len(tr),
                "wins": wn,
                "win_rate": wn / len(tr),
                "profit_factor": (gp / gl) if gl > 0 else (float("inf") if gp > 0 else 0.0),
            }

        # Max DD as a percentage from the equity walk
        balances = []
        running = 0.0
        for t in sorted(trades, key=lambda x: x.get("opened_at") or x.get("date") or ""):
            running += t.get("pnl", 0) or 0
            balances.append(running)
        if balances:
            peak = balances[0]
            max_dd = 0.0
            for b in balances:
                if b > peak:
                    peak = b
                if peak > 0:
                    dd = (peak - b) / peak * 100
                    if dd > max_dd:
                        max_dd = dd
        else:
            max_dd = 0.0

        return {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "profit_factor": pf,
            "by_style": by_style,
            "max_dd_pct": max_dd,
        }

    def _make_tuning_persist_fn(self):
        """Build a closure that persists a single (key, value) override to
        data/risk_config.json using the same atomic write pattern as the
        runtime `PUT /risk-config` endpoint."""
        def _persist(key: str, value):
            import json as _json, os as _os, tempfile as _tf
            backend_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
            risk_path = _os.path.join(backend_dir, "data", "risk_config.json")
            overrides: dict = {}
            if _os.path.exists(risk_path):
                try:
                    with open(risk_path) as f:
                        overrides = _json.load(f)
                    if not isinstance(overrides, dict):
                        overrides = {}
                except Exception:
                    overrides = {}
            overrides[key] = value
            _os.makedirs(_os.path.dirname(risk_path), exist_ok=True)
            fd, tmp = _tf.mkstemp(dir=_os.path.dirname(risk_path), suffix=".tmp")
            try:
                with _os.fdopen(fd, "w") as f:
                    _json.dump(overrides, f, indent=2)
                _os.replace(tmp, risk_path)
            except Exception:
                try:
                    _os.unlink(tmp)
                except OSError:
                    pass
                raise
        return _persist

    # ── Monthly ASR ────────────────────────────────────────────

    async def _maybe_send_monthly_asr(self, now: datetime):
        """Send monthly ASR (After Session Review) on the 1st of each month."""
        if now.day != 1 or now.hour != 8 or now.minute > 2:
            return
        if not self._db or not self.alert_manager:
            return
        if hasattr(self, '_monthly_asr_sent') and self._monthly_asr_sent == now.strftime("%Y-%m"):
            return

        self._monthly_asr_sent = now.strftime("%Y-%m")

        try:
            # Get last month's trades from DB
            first_of_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            last_month_end = first_of_this - timedelta(seconds=1)
            last_month_start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            trades = await self._db.get_trades_between(
                last_month_start.isoformat(),
                last_month_end.isoformat(),
            )

            if not trades:
                logger.info("Monthly ASR: No trades last month")
                return

            # Calculate stats
            total = len(trades)
            wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
            losses = total - wins
            win_rate = (wins / total * 100) if total > 0 else 0
            total_pnl = sum(t.get("pnl", 0) for t in trades)
            avg_rr = sum(t.get("risk_reward_ratio", 0) for t in trades) / max(total, 1)

            # Best strategy
            strategy_counts = {}
            for t in trades:
                s = t.get("strategy", "UNKNOWN")
                if s not in strategy_counts:
                    strategy_counts[s] = {"count": 0, "pnl": 0}
                strategy_counts[s]["count"] += 1
                strategy_counts[s]["pnl"] += t.get("pnl", 0)

            best_strategy = max(strategy_counts.items(), key=lambda x: x[1]["pnl"])[0] if strategy_counts else "N/A"

            month_name = last_month_start.strftime("%B %Y")

            report = (
                f"REPORTE MENSUAL ASR -- {month_name}\n\n"
                f"Total trades: {total}\n"
                f"Ganados: {wins} | Perdidos: {losses}\n"
                f"Win Rate: {win_rate:.1f}%\n"
                f"PnL Total: ${total_pnl:.2f}\n"
                f"R:R Promedio: {avg_rr:.2f}\n"
                f"Mejor estrategia: {best_strategy}\n\n"
                f"Estrategias:\n"
            )
            for s, data in sorted(strategy_counts.items(), key=lambda x: -x[1]["pnl"]):
                report += f"  {s}: {data['count']} trades, PnL ${data['pnl']:.2f}\n"

            await self.alert_manager.send_engine_status("MONTHLY_ASR", report)
            logger.info(f"Monthly ASR sent for {month_name}")

        except Exception as e:
            logger.error(f"Monthly ASR failed: {e}")

    # ── Daily Heartbeat ─────────────────────────────────────────

    def _reset_daily_counters(self):
        """Reset daily activity counters for a new day."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._daily_counter_date != today:
            self._daily_scan_count = 0
            self._daily_setups_found = 0
            self._daily_setups_executed = 0
            self._daily_setups_filtered = 0
            self._daily_errors = 0
            self._consecutive_losses_today = 0
            self._last_loss_time = None
            self._daily_counter_date = today

    def _build_presession_checklist(self, session_label: str) -> str:
        """Build the pre-session checklist based on the Psychology Manual.
        Used for both morning and NY session notifications."""
        return (
            f"\n<b>--- Checklist Pre-Sesión ({session_label}) ---</b>\n"
            f"1. ¿Has meditado 10 minutos? (Ejercicio 2: Meditación)\n"
            f"2. ¿Estás en estado emocional estable? (No operes estresado)\n"
            f"3. ¿Has revisado el calendario económico? (Noticias de hoy)\n"
            f"4. ¿Has verificado las posiciones abiertas? (Revisar SL/TP)\n"
            f"5. Recuerda: 3-5 respiraciones profundas antes de cada trade (Ejercicio 3)\n"
        )

    async def _maybe_send_morning_heartbeat(self, now: datetime):
        """
        Send a 'proof of life' email at ~8:00 UTC (3am Colombia) every day,
        including the pre-session psychological checklist (Psychology Manual).
        Also sends a NY session checklist at ~13:00 UTC.
        """
        # ── Morning heartbeat at 08:00 UTC ──
        if now.hour == 8 and now.minute < 3:
            if not (hasattr(self, '_heartbeat_sent_date') and self._heartbeat_sent_date == now.date()):
                self._heartbeat_sent_date = now.date()
                await self._send_heartbeat_with_checklist(now, "Mañana / London Open")

        # ── NY session checklist at 13:00 UTC ──
        if now.hour == 13 and now.minute < 3:
            if not (hasattr(self, '_ny_checklist_sent_date') and self._ny_checklist_sent_date == now.date()):
                self._ny_checklist_sent_date = now.date()
                await self._send_presession_checklist_alert(now, "Sesión New York")

    async def _send_heartbeat_with_checklist(self, now: datetime, session_label: str):
        """Send the morning heartbeat email with pre-session checklist."""
        if not self.alert_manager:
            return

        try:
            # Gather status info
            account = None
            try:
                account = await self.broker.get_account_summary()
            except Exception:
                pass

            balance_str = f"{account.balance:.2f} {account.currency}" if account else "N/A"
            open_positions = len(self.position_manager.positions)
            pairs_analyzed = len(self._last_scan_results)
            mode = self.mode.value.upper()
            strategies_on = sum(1 for v in self._enabled_strategies.values() if v)

            checklist = self._build_presession_checklist(session_label)

            body = (
                f"<b>Atlas is ALIVE and running.</b>\n\n"
                f"<b>Balance:</b> {balance_str}\n"
                f"<b>Mode:</b> {mode}\n"
                f"<b>Open Positions:</b> {open_positions}\n"
                f"<b>Pairs Watched:</b> {len(get_active_watchlist())}\n"
                f"<b>Pairs Analyzed:</b> {pairs_analyzed}\n"
                f"<b>Strategies Active:</b> {strategies_on}/9\n"
                f"<b>Scan Interval:</b> {self._scan_interval}s\n\n"
                f"{checklist}\n"
                f"<i>Trading hours: 07:00-22:00 UTC. You'll get a summary at 22:00 UTC.</i>"
            )

            await self.alert_manager.send_alert(
                "engine_status",
                f"Atlas - Morning Heartbeat ({now.strftime('%Y-%m-%d')})",
                body,
            )
            logger.info("Morning heartbeat email sent (with pre-session checklist)")
        except Exception as e:
            logger.warning(f"Failed to send morning heartbeat: {e}")

    async def _send_presession_checklist_alert(self, now: datetime, session_label: str):
        """Send a pre-session checklist notification before NY session (13:00 UTC).
        Psychology Manual: checklist both in the morning AND before NY session."""
        if not self.alert_manager:
            return

        try:
            open_positions = len(self.position_manager.positions)
            checklist = self._build_presession_checklist(session_label)

            body = (
                f"<b>Pre-Session Checklist - {session_label}</b>\n\n"
                f"<b>Posiciones abiertas:</b> {open_positions}\n"
                f"{checklist}\n"
                f"<i>La sesión NY (13:00-22:00 UTC) es de alta volatilidad. Mantén disciplina.</i>"
            )

            await self.alert_manager.send_alert(
                "presession_checklist",
                f"Atlas - Checklist {session_label} ({now.strftime('%Y-%m-%d')})",
                body,
            )
            logger.info(f"Pre-session checklist sent for {session_label}")
        except Exception as e:
            logger.warning(f"Failed to send pre-session checklist: {e}")

    # ── Status ───────────────────────────────────────────────────

    def get_status(self) -> Dict:
        """Get current engine status for the API/frontend."""
        self._expire_old_setups()
        pending_count = sum(
            1 for s in self.pending_setups if s.status == "pending"
        )

        return {
            "running": self._running,
            "startup_error": self._startup_error,
            "scanned_instruments": len(self._last_scan_results),
            "mode": self.mode.value,
            "open_positions": len(self.position_manager.positions),
            "total_risk": self.risk_manager.get_current_total_risk(),
            "watchlist_count": len(get_active_watchlist()),
            "pending_setups": pending_count,
            "pending_setups_count": pending_count,  # Alias for backwards compat
            "enabled_strategies": self._enabled_strategies,
            "daily_activity": {
                "date": self._daily_counter_date,
                "scans_completed": self._daily_scan_count,
                "setups_found": self._daily_setups_found,
                "setups_executed": self._daily_setups_executed,
                "setups_filtered": self._daily_setups_filtered,
                "errors": self._daily_errors,
            },
            "last_scan": {
                inst: {
                    "score": result.score,
                    "htf_trend": result.htf_trend.value if hasattr(result.htf_trend, 'value') else str(result.htf_trend),
                    "ltf_trend": result.ltf_trend.value if hasattr(result.ltf_trend, 'value') else str(result.ltf_trend),
                    "convergence": result.htf_ltf_convergence,
                    "patterns": result.candlestick_patterns,
                }
                for inst, result in dict(self._last_scan_results).items()
            },
            "positions": [
                {
                    "trade_id": tid,
                    "instrument": pos.instrument,
                    "direction": pos.direction,
                    "entry": pos.entry_price,
                    "current_sl": pos.current_sl,
                    "tp1": pos.take_profit_1,
                    "tp_max": pos.take_profit_max,
                    "units": pos.units,
                    "phase": pos.phase.value,
                    "strategy_variant": pos.strategy_variant,
                }
                for tid, pos in self.position_manager.positions.items()
            ],
            "latest_explanations": {
                inst: {
                    "overall_bias": expl.overall_bias,
                    "score": expl.score,
                    "strategy_detected": expl.strategy_detected,
                    "confidence_level": expl.confidence_level,
                    "recommendation": expl.recommendation,
                }
                for inst, expl in self._latest_explanations.items()
            },
            "scalping": {
                "enabled": settings.scalping_enabled,
                "available": _SCALPING_AVAILABLE,
                "daily_dd": self._scalping_daily_dd,
                "total_dd": self._scalping_total_dd,
                "max_daily_dd": settings.scalping_max_daily_dd,
                "max_total_dd": settings.scalping_max_total_dd,
                "scan_interval": self._scalping_scan_interval,
                "status": (
                    self.scalping_analyzer.get_scalping_status()
                    if self.scalping_analyzer else {}
                ),
            },
            "journal": self.trade_journal.get_stats() if self.trade_journal else {},
        }

    # ──────────────────────────────────────────────────────────────────
    # Visual dashboard helpers (for V1-V10 UI features)
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _current_session(now: datetime, offset: int) -> str:
        """Return trading session for the given UTC time.

        Sessions (approx UTC, DST-adjusted):
          london:             08:00-13:00
          london_ny_overlap:  13:00-17:00   (best liquidity)
          ny:                 17:00-22:00
          asia:               23:00-07:00
          quiet:              07:00-08:00 (pre-london, low volume)
        """
        h = now.hour
        lon_start = 8 + offset
        lon_end = 17 + offset
        ny_start = 13 + offset
        ny_end = 22 + offset
        if lon_start <= h < ny_start:
            return "london"
        if ny_start <= h < lon_end:
            return "london_ny_overlap"
        if lon_end <= h < ny_end:
            return "ny"
        if h >= 23 or h < 7 + offset:
            return "asia"
        return "quiet"

    def _next_trading_open_iso(self, now: datetime, offset: int) -> str:
        """Compute ISO datetime of the next trading window open."""
        next_open = now.replace(hour=settings.trading_start_hour + offset,
                                minute=0, second=0, microsecond=0)
        if next_open <= now:
            next_open += timedelta(days=1)
        # Skip weekend
        while next_open.weekday() >= 5:
            next_open += timedelta(days=1)
        return next_open.isoformat()

    def get_engine_state(self) -> Dict:
        """UI-friendly consolidated state: why the engine is/isn't taking trades.

        Used by /api/v1/engine-state to power V1 (news banner), V2 (engine dot),
        V3 (session timeline), V9 (next-news countdown).
        """
        now = datetime.now(timezone.utc)
        offset = self._dst_offset(now)
        hour = now.hour

        # News state (active + next) from filter cache
        try:
            news_state = self.news_filter.get_active_and_upcoming()
        except Exception:
            news_state = {"active": None, "next": None}

        session = self._current_session(now, offset)

        reason: Optional[str] = None
        text = "Activo — escaneando cada 120s"
        resumes_at: Optional[str] = None

        # Priority order: out-of-hours > funded weekend > friday cutoff >
        # news blackout > max trades reached > cooldown after losses
        if hour < settings.trading_start_hour + offset or hour >= settings.trading_end_hour + offset:
            reason = "out_of_hours"
            text = (
                f"Engine opera {settings.trading_start_hour:02d}:00–"
                f"{settings.trading_end_hour:02d}:00 UTC. "
                f"Ahora {hour:02d}:{now.minute:02d} UTC."
            )
            resumes_at = self._next_trading_open_iso(now, offset)
        elif now.weekday() == 4 and hour >= settings.close_before_friday_hour + offset:
            reason = "friday_close"
            text = (
                f"Viernes post-{settings.close_before_friday_hour:02d}:00 UTC — "
                f"cerrando la semana. Reanuda el lunes."
            )
            resumes_at = self._next_trading_open_iso(now, offset)
        elif now.weekday() == 4 and hour >= settings.no_new_trades_friday_hour + offset:
            reason = "friday_no_new_trades"
            text = (
                f"Viernes post-{settings.no_new_trades_friday_hour:02d}:00 UTC — "
                f"sin nuevos trades. Posiciones abiertas siguen gestionadas."
            )
            resumes_at = self._next_trading_open_iso(now, offset)
        elif news_state.get("active"):
            e = news_state["active"]
            reason = "news_blackout"
            hhmm = e["ends_at_utc"][11:16]
            text = (
                f"News: {e['currency']} {e['title']} — "
                f"sin nuevos trades hasta {hhmm} UTC."
            )
            resumes_at = e["ends_at_utc"]
        elif self._daily_setups_executed >= settings.max_trades_per_day:
            reason = "max_trades_reached"
            text = (
                f"Límite de {settings.max_trades_per_day} trades/día alcanzado. "
                f"Reanuda mañana."
            )
            resumes_at = self._next_trading_open_iso(now, offset)
        elif (self._consecutive_losses_today >= settings.cooldown_after_consecutive_losses
              and self._last_loss_time is not None):
            cooldown_end = self._last_loss_time + timedelta(minutes=settings.cooldown_minutes)
            if now < cooldown_end:
                reason = "cooldown_after_losses"
                text = (
                    f"Cooldown post {self._consecutive_losses_today} pérdidas — "
                    f"reanuda {cooldown_end.strftime('%H:%M')} UTC."
                )
                resumes_at = cooldown_end.isoformat()

        return {
            "running": self._running,
            "paused_reason": reason,
            "paused_reason_text": text,
            "resumes_at_utc": resumes_at,
            "session": session,
            "news": news_state,
            "consecutive_losses_today": self._consecutive_losses_today,
            "setups_executed_today": self._daily_setups_executed,
            "max_trades_per_day": settings.max_trades_per_day,
            "now_utc": now.isoformat(),
            "trading_hours_utc": f"{settings.trading_start_hour:02d}:00-{settings.trading_end_hour:02d}:00",
        }

    def get_watchlist_status(self) -> List[Dict]:
        """Per-instrument visual status for V4 (status chips in Market tab).

        Derives status from last scan + pending setups queue.
        """
        pending_instruments = {s.instrument for s in self.pending_setups if s.status == "pending"}
        out: List[Dict] = []
        for inst, result in dict(self._last_scan_results).items():
            score = float(getattr(result, "score", 0) or 0)
            convergence = bool(getattr(result, "htf_ltf_convergence", False))
            htf = getattr(result, "htf_trend", "")
            ltf = getattr(result, "ltf_trend", "")
            htf_str = htf.value if hasattr(htf, "value") else str(htf)
            ltf_str = ltf.value if hasattr(ltf, "value") else str(ltf)

            if inst in pending_instruments:
                status = "setup_queued"
                status_text = "Setup en cola — pendiente de aprobación"
            elif score >= 75 and convergence:
                status = "ready_waiting"
                status_text = "HTF alineado, score alto — esperando patrón de entrada"
            elif score >= 55:
                status = "forming"
                status_text = "Condiciones formándose — aún sin patrón claro"
            elif score >= 30:
                status = "weak"
                status_text = "Condiciones débiles — baja probabilidad"
            else:
                status = "no_pattern"
                status_text = "Sin alineación HTF/LTF ni confluencia"

            out.append({
                "instrument": inst,
                "score": round(score, 1),
                "htf_trend": htf_str,
                "ltf_trend": ltf_str,
                "convergence": convergence,
                "status": status,
                "status_text": status_text,
            })
        # Sort by score descending so the best candidates show first
        out.sort(key=lambda d: d["score"], reverse=True)
        return out

