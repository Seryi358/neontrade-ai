"""
NeonTrade AI - Trading Engine
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
from strategies.base import get_best_setup, SetupSignal
from config import settings

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
    units: int
    confidence: float
    risk_reward_ratio: float
    reasoning: str  # Spanish explanation
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
        )
    else:
        from broker.oanda_client import OandaClient
        return OandaClient()


class TradingEngine:
    """Main trading engine - the brain of NeonTrade AI."""

    def __init__(self):
        self.broker = _create_broker()
        self.risk_manager = RiskManager(self.broker)
        self.position_manager = PositionManager(self.broker)

        # OpenAI analyzer for AI-enhanced trade validation
        if _AI_AVAILABLE:
            self.ai_analyzer = OpenAIAnalyzer()
            logger.info("OpenAI analyzer initialized (AI-enhanced trading active)")
        else:
            self.ai_analyzer = None
            logger.warning("OpenAI analyzer not available — trading without AI validation")
        self.market_analyzer = MarketAnalyzer(self.broker)
        self.explanation_engine = ExplanationEngine()
        self.news_filter = NewsFilter(
            minutes_before=settings.avoid_news_minutes_before,
            minutes_after=settings.avoid_news_minutes_after,
            finnhub_key=getattr(settings, 'finnhub_api_key', ''),
            newsapi_key=getattr(settings, 'newsapi_key', ''),
        )

        # Alert manager (Telegram, Discord, Email, Gmail OAuth2)
        if _ALERTS_AVAILABLE:
            # Auto-enable Gmail if OAuth2 credentials are configured
            gmail_refresh = getattr(settings, 'gmail_refresh_token', '')
            gmail_enabled = bool(gmail_refresh and getattr(settings, 'gmail_client_id', ''))

            alert_cfg = AlertConfig(
                telegram_bot_token=getattr(settings, 'telegram_bot_token', ''),
                telegram_chat_id=getattr(settings, 'telegram_chat_id', ''),
                discord_webhook_url=getattr(settings, 'discord_webhook_url', ''),
                email_smtp_server=getattr(settings, 'alert_email_smtp_server', 'smtp.gmail.com'),
                email_smtp_port=getattr(settings, 'alert_email_smtp_port', 587),
                email_username=getattr(settings, 'alert_email_username', ''),
                email_password=getattr(settings, 'alert_email_password', ''),
                email_recipient=getattr(settings, 'alert_email_recipient', ''),
                gmail_enabled=gmail_enabled,
                gmail_sender=getattr(settings, 'gmail_sender', ''),
                gmail_recipient=getattr(settings, 'gmail_recipient', '') or getattr(settings, 'gmail_sender', ''),
                gmail_client_id=getattr(settings, 'gmail_client_id', ''),
                gmail_client_secret=getattr(settings, 'gmail_client_secret', ''),
                gmail_refresh_token=gmail_refresh,
            )
            self.alert_manager = AlertManager(alert_cfg)
            if gmail_enabled:
                logger.info("Gmail OAuth2 notifications enabled for {}", settings.gmail_sender)
        else:
            self.alert_manager = None

        # Trading mode — AUTO = proactive trading
        self.mode: TradingMode = TradingMode.AUTO
        self.pending_setups: List[PendingSetup] = []
        self._setup_expiry_minutes: int = 30  # Configurable expiry

        # Strategy selection (persisted in data/strategy_config.json)
        self._strategy_config_path = os.path.join("data", "strategy_config.json")
        self._enabled_strategies: Dict[str, bool] = self._load_strategy_config()

        # Internal state
        self._running = False
        self._scan_interval = 120  # seconds (2 minutes)
        self._last_scan_results: Dict[str, AnalysisResult] = {}
        self._latest_explanations: Dict[str, StrategyExplanation] = {}

        # WebSocket broadcast callback (set externally when WS is connected)
        self._ws_broadcast: Optional[Callable] = None

        # Database reference (injected by main.py after DB init)
        self._db = None

        # Notification queue for Electron native notifications
        self._notifications: List[Dict] = []
        self._max_notifications = 100

        # Equity snapshot tracking (record every 10 minutes)
        self._last_equity_snapshot: datetime = datetime.min.replace(tzinfo=timezone.utc)

        # Daily activity counters (reset each day) — proves the app was alive
        self._daily_scan_count: int = 0
        self._daily_setups_found: int = 0
        self._daily_setups_executed: int = 0
        self._daily_setups_skipped_ai: int = 0
        self._daily_errors: int = 0
        self._daily_counter_date: str = ""  # YYYY-MM-DD of current counters

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
        logger.info(f"Notification: [{notif_type}] {title} — {body}")

    def get_unread_notifications(self) -> List[Dict]:
        """Get and mark as read all unread notifications."""
        unread = [n for n in self._notifications if not n["read"]]
        for n in unread:
            n["read"] = True
        return unread

    # ── Strategy Selection ────────────────────────────────────────

    _DEFAULT_STRATEGY_CONFIG: Dict[str, bool] = {
        "BLUE": True, "BLUE_A": True, "BLUE_B": True, "BLUE_C": True,
        "RED": True, "PINK": True, "WHITE": True, "BLACK": True, "GREEN": True,
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
        """Persist strategy config to JSON file."""
        try:
            os.makedirs(os.path.dirname(self._strategy_config_path), exist_ok=True)
            with open(self._strategy_config_path, "w") as f:
                json.dump(self._enabled_strategies, f, indent=2)
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

    def get_pending_setups(self) -> List[dict]:
        """Get all pending (non-expired) setups as dicts."""
        self._expire_old_setups()
        return [
            s.to_dict() for s in self.pending_setups
            if s.status == "pending"
        ]

    async def approve_setup(self, setup_id: str) -> bool:
        """Approve and execute a pending setup by ID."""
        self._expire_old_setups()
        for setup in self.pending_setups:
            if setup.id == setup_id and setup.status == "pending":
                setup.status = "approved"
                logger.info(f"Setup approved: {setup_id} | {setup.instrument} {setup.direction}")
                # Execute the approved setup
                await self._execute_approved_setup(setup)
                return True
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
        """Approve and execute all pending setups. Returns count approved."""
        self._expire_old_setups()
        pending = [s for s in self.pending_setups if s.status == "pending"]
        count = 0
        for setup in pending:
            setup.status = "approved"
            try:
                await self._execute_approved_setup(setup)
                count += 1
            except Exception as e:
                logger.error(f"Failed to execute approved setup {setup.id}: {e}")
                setup.status = "pending"  # Revert on failure
        logger.info(f"Approved and executed {count}/{len(pending)} pending setups")
        return count

    def _expire_old_setups(self):
        """Mark setups past their expiry time as expired."""
        now = datetime.now(timezone.utc)
        for setup in self.pending_setups:
            if setup.status != "pending":
                continue
            if setup.expires_at:
                expires = datetime.fromisoformat(setup.expires_at)
                if now >= expires:
                    setup.status = "expired"
                    logger.info(
                        f"Setup expired: {setup.id} | {setup.instrument} "
                        f"(after {self._setup_expiry_minutes} min)"
                    )

    # ── Main Loop ────────────────────────────────────────────────

    async def start(self):
        """Start the trading engine."""
        logger.info("=" * 60)
        logger.info("  NeonTrade AI - Trading Engine Starting")
        logger.info(f"  Mode: {self.mode.value}")
        logger.info("=" * 60)

        # Validate connection
        try:
            summary = await self.broker.get_account_summary()
            balance = summary.balance
            currency = summary.currency
            broker_name = self.broker.broker_type.value.upper()
            logger.info(f"Connected to {broker_name} | Balance: {balance} {currency}")
            logger.info(f"Broker: {broker_name} | Environment: {settings.active_broker}")
        except Exception as e:
            logger.error(f"Failed to connect to broker: {e}")
            return

        self._running = True
        logger.info(f"Watching {len(settings.forex_watchlist)} pairs")
        logger.info(f"Scan interval: {self._scan_interval}s")

        # Send startup alert
        if self.alert_manager and hasattr(self.alert_manager, 'send_engine_status'):
            try:
                await self.alert_manager.send_engine_status(
                    "STARTED",
                    f"NeonTrade AI engine started. Mode: {self.mode.value}. "
                    f"Broker: {broker_name}. Balance: {balance} {currency}. "
                    f"Watching {len(settings.forex_watchlist)} pairs.",
                )
            except Exception:
                pass

        # Initial scan on startup — run regardless of market hours
        # so that analysis data is available immediately for the UI
        logger.info("Running initial scan (ignoring market hours)...")
        try:
            await self._initial_scan()
        except Exception as e:
            logger.error(f"Initial scan failed (non-critical): {e}")

        # Main loop
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.error(f"Error in main loop: {e}")

            await asyncio.sleep(self._scan_interval)

    async def stop(self):
        """Stop the trading engine gracefully."""
        logger.info("Trading engine stopping...")
        self._running = False

    # ── Core Tick ────────────────────────────────────────────────

    async def _tick(self):
        """One iteration of the main trading loop."""
        now = datetime.now(timezone.utc)
        market_open = self._is_market_open(now)

        # Reset daily counters at midnight UTC
        self._reset_daily_counters()

        # Always expire old pending setups
        self._expire_old_setups()

        # Morning heartbeat email (proof of life)
        await self._maybe_send_morning_heartbeat(now)

        # Daily summary: send at end of trading day (21:00 UTC) once
        if now.hour == settings.trading_end_hour and now.minute < 3:
            if not hasattr(self, '_daily_summary_sent_date') or self._daily_summary_sent_date != now.date():
                self._daily_summary_sent_date = now.date()
                asyncio.create_task(self._send_daily_summary())

        if market_open:
            # Check Friday close rule
            if self._should_close_friday(now):
                await self._handle_friday_close()
                return

            # Check economic calendar for upcoming news
            has_news, news_desc = await self.news_filter.has_upcoming_news()
            if has_news:
                logger.info(f"News filter active: {news_desc} — skipping trade execution")
                # Still scan for analysis but don't execute
                await self._scan_analysis_only()
                return

            # Step 0: Sync positions from broker (detect external closes)
            await self._sync_positions_from_broker()

            # Step 1: Update position management for open trades
            await self._manage_open_positions()

            # Record equity snapshot every 10 minutes
            await self._maybe_record_equity_snapshot(now)

            # Step 2: Scan for new opportunities (with trade execution)
            await self._scan_for_setups()
        else:
            # Market closed — still scan for analysis data every 10 minutes
            # so the UI always has fresh data
            if not hasattr(self, '_last_offhours_scan'):
                self._last_offhours_scan = datetime.min.replace(tzinfo=timezone.utc)
            if (now - self._last_offhours_scan).total_seconds() >= 600:
                logger.debug("Off-hours analysis scan...")
                await self._scan_analysis_only()
                self._last_offhours_scan = now

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
            logger.debug(f"Equity snapshot failed (non-critical): {e}")

    # ── Market Hours ─────────────────────────────────────────────

    def _is_market_open(self, now: datetime) -> bool:
        """Check if forex market is open (Mon-Fri, trading hours)."""
        # Forex is closed on weekends
        if now.weekday() >= 5:  # Saturday=5, Sunday=6
            return False

        # Only trade during London + NY sessions
        hour = now.hour
        return settings.trading_start_hour <= hour < settings.trading_end_hour

    def _should_close_friday(self, now: datetime) -> bool:
        """Check if we should close all positions (Friday rule)."""
        return (now.weekday() == 4 and
                now.hour >= settings.close_before_friday_hour)

    async def _handle_friday_close(self):
        """Close all positions before Friday market close."""
        open_trades = await self.broker.get_open_trades()
        if open_trades:
            logger.warning(
                f"FRIDAY CLOSE: Closing {len(open_trades)} open trades"
            )
            await self.broker.close_all_trades()
            self.position_manager.positions.clear()
            self.risk_manager._active_risks.clear()

    # ── Position Sync ────────────────────────────────────────────

    async def _sync_positions_from_broker(self):
        """Sync tracked positions with actual broker state.
        Detects positions closed externally (via broker UI or SL/TP hit)."""
        try:
            broker_trades = await self.broker.get_open_trades()
            broker_ids = {t.trade_id for t in broker_trades}
            tracked_ids = set(self.position_manager.positions.keys())

            # Remove positions that no longer exist at the broker
            closed_ids = tracked_ids - broker_ids
            for tid in closed_ids:
                pos = self.position_manager.positions.pop(tid, None)
                if pos:
                    self.risk_manager.unregister_trade(tid, pos.instrument)
                    logger.info(
                        f"Position {tid} ({pos.instrument}) closed externally — removed from tracking"
                    )
                    if self._ws_broadcast:
                        await self._ws_broadcast("trade_closed", {
                            "trade_id": tid,
                            "instrument": pos.instrument,
                            "reason": "external",
                        })

                    # Persist close to database
                    if self._db:
                        try:
                            await self._db.update_trade(tid, {
                                "status": "closed_manual",
                                "closed_at": datetime.now(timezone.utc).isoformat(),
                            })
                        except Exception:
                            pass

                    # Send close alert
                    if self.alert_manager:
                        try:
                            await self.alert_manager.send_trade_closed(
                                instrument=pos.instrument,
                                pnl=0.0,
                                pips=0.0,
                                reason="Position closed externally (broker/SL/TP)",
                            )
                        except Exception:
                            pass
        except Exception as e:
            logger.debug(f"Position sync failed (non-critical): {e}")

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
            for inst in instruments:
                if inst in self._last_scan_results:
                    emas = self._last_scan_results[inst].ema_values
                    self.position_manager.set_ema_values(inst, emas)

            prices = await self.broker.get_prices_bulk(instruments)
            await self.position_manager.update_all_positions(prices)
        except Exception as e:
            logger.error(f"Error managing positions: {e}")

    # ── Analysis-Only Scan (off-hours / news active) ───────────

    async def _scan_analysis_only(self):
        """Scan all watchlist pairs for analysis only (no trade execution).
        Used during off-hours and news events to keep UI data fresh."""
        for instrument in settings.forex_watchlist:
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
                logger.debug(f"Off-hours scan failed for {instrument}: {e}")
            # Throttle between pairs to avoid 429 rate limits from broker API
            await asyncio.sleep(1.5)

    # ── Initial Scan (startup, ignores market hours) ────────────

    async def _initial_scan(self):
        """Run analysis on all watchlist pairs at startup.
        Populates _last_scan_results so the UI has data immediately.
        Also detects setups so the user sees results right away."""
        logger.info(f"Initial scan: analyzing {len(settings.forex_watchlist)} pairs...")
        setups_found = 0
        for instrument in settings.forex_watchlist:
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

                # Also detect setups during initial scan
                setup = await self._detect_setup(analysis)
                if setup:
                    setups_found += 1
                    await self._handle_setup(setup, analysis, explanation)

            except Exception as e:
                logger.warning(f"Initial scan failed for {instrument}: {e}")
            # Throttle between pairs to avoid 429 rate limits from broker API
            await asyncio.sleep(1.5)

        logger.info(
            f"Initial scan complete: {len(self._last_scan_results)}/{len(settings.forex_watchlist)} pairs analyzed, "
            f"{setups_found} setups detected"
        )

    # ── Scanning ─────────────────────────────────────────────────

    async def _scan_for_setups(self):
        """Scan all watchlist pairs for trading setups."""
        self._daily_scan_count += 1
        for instrument in settings.forex_watchlist:
            try:
                # Check if we can take more risk
                if not self.risk_manager.can_take_trade(
                    TradingStyle.DAY_TRADING, instrument
                ):
                    continue

                # Skip if already in a trade on this instrument
                if any(
                    pos.instrument == instrument
                    for pos in self.position_manager.positions.values()
                ):
                    continue

                # Run full analysis
                analysis = await self.market_analyzer.full_analysis(instrument)
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
                    self._daily_setups_found += 1
                    # Re-generate explanation with the setup signal context
                    # (setup is TradeRisk, not SetupSignal, so we pass what we can)
                    await self._handle_setup(setup, analysis, explanation)

            except Exception as e:
                self._daily_errors += 1
                logger.error(f"Error scanning {instrument}: {e}")
            # Throttle between pairs to avoid 429 rate limits from broker API
            await asyncio.sleep(1.5)

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

        # AI validation: ask OpenAI to validate the setup before proceeding
        if self.ai_analyzer:
            try:
                ai_result = await self.ai_analyzer.validate_setup_with_ai(signal, analysis)
                ai_score = ai_result.get("ai_score", 0)
                ai_rec = ai_result.get("ai_recommendation", "SKIP")
                ai_reason = ai_result.get("ai_reasoning", "")
                logger.info(
                    f"AI validation for {signal.instrument}: "
                    f"Score={ai_score} Rec={ai_rec} — {ai_reason}"
                )
                if ai_rec == "SKIP" and ai_score < 40:
                    logger.info(f"AI rejected setup for {signal.instrument} (score={ai_score})")
                    self._daily_setups_skipped_ai += 1
                    return None
                # Apply AI-suggested SL/TP adjustments if provided
                adjustments = ai_result.get("suggested_adjustments", {})
                if adjustments:
                    new_sl = adjustments.get("suggested_sl")
                    new_tp = adjustments.get("suggested_tp1")
                    if new_sl and isinstance(new_sl, (int, float)) and new_sl > 0:
                        signal.stop_loss = float(new_sl)
                    if new_tp and isinstance(new_tp, (int, float)) and new_tp > 0:
                        signal.take_profit_1 = float(new_tp)
            except Exception as e:
                logger.warning(f"AI validation failed (proceeding without): {e}")

        # Validate risk management
        if not self.risk_manager.validate_reward_risk(
            signal.entry_price, signal.stop_loss, signal.take_profit_1
        ):
            logger.info(f"R:R validation failed for {signal.instrument}")
            return None

        # Calculate position size
        style = TradingStyle.DAY_TRADING
        units = await self.risk_manager.calculate_position_size(
            signal.instrument, style, signal.entry_price, signal.stop_loss
        )
        if units == 0:
            return None

        # Adjust direction sign for units
        if signal.direction == "SELL":
            units = -abs(units)

        risk_percent = self.risk_manager.get_risk_for_style(style)
        sl_distance = abs(signal.entry_price - signal.stop_loss)
        rr = abs(signal.take_profit_1 - signal.entry_price) / max(sl_distance, 0.00001)

        return TradeRisk(
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
        )

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
        reasoning = self._build_setup_reasoning(setup, analysis, explanation)

        # Attach strategy name from explanation to setup for later use
        setup._strategy_name = getattr(explanation, 'strategy_detected', None) or "DETECTED"

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
            confidence=setup.reward_risk_ratio * 33,  # Heuristic confidence
            risk_reward_ratio=setup.reward_risk_ratio,
            reasoning=reasoning,
            status="pending",
            expires_at=expires_at.isoformat(),
        )

        self.pending_setups.append(pending)

        logger.info("=" * 50)
        logger.info(f"SETUP QUEUED (MANUAL MODE): {setup.direction} {setup.instrument}")
        logger.info(f"  Entry: {setup.entry_price:.5f}")
        logger.info(f"  SL: {setup.stop_loss:.5f}")
        logger.info(f"  TP: {setup.take_profit_1:.5f}")
        logger.info(f"  R:R: {setup.reward_risk_ratio:.2f}")
        logger.info(f"  Expires: {expires_at.isoformat()}")
        logger.info(f"  ID: {pending.id}")
        logger.info("=" * 50)

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
                )
            except Exception as ae:
                logger.debug(f"Alert send failed (non-critical): {ae}")

        # Broadcast via WebSocket if callback is set
        if self._ws_broadcast:
            try:
                await self._ws_broadcast("new_setup", pending.to_dict())
            except Exception as e:
                logger.error(f"Failed to broadcast pending setup via WS: {e}")

    # ── Trade Execution ──────────────────────────────────────────

    async def _execute_setup(self, setup: TradeRisk):
        """Execute a validated trading setup (AUTO mode)."""
        logger.info("=" * 50)
        logger.info(f"EXECUTING TRADE: {setup.direction} {setup.instrument}")
        logger.info(f"  Entry: {setup.entry_price:.5f}")
        logger.info(f"  SL: {setup.stop_loss:.5f}")
        logger.info(f"  TP1: {setup.take_profit_1:.5f}")
        logger.info(f"  Units: {setup.units}")
        logger.info(f"  R:R: {setup.reward_risk_ratio:.2f}")
        logger.info(f"  Risk: {setup.risk_percent:.2%}")
        logger.info(f"  Mode: {self.mode.value}")
        logger.info("=" * 50)

        try:
            result = await self.broker.place_market_order(
                instrument=setup.instrument,
                units=setup.units,
                stop_loss=setup.stop_loss,
                take_profit=setup.take_profit_1,
            )

            # result is now an OrderResult dataclass
            if not result.success:
                logger.error(f"Order failed for {setup.instrument}: {result.error}")
                return

            trade_id = result.trade_id
            if not trade_id:
                logger.error(f"Order succeeded but no trade_id returned for {setup.instrument}")
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
                    entry_price=setup.entry_price,
                    original_sl=setup.stop_loss,
                    current_sl=setup.stop_loss,
                    take_profit_1=setup.take_profit_1,
                    take_profit_max=setup.take_profit_max,
                    highest_price=setup.entry_price,
                    lowest_price=setup.entry_price,
                ))

                # Persist trade to database
                if self._db:
                    try:
                        await self._db.record_trade({
                            "id": trade_id,
                            "instrument": setup.instrument,
                            "strategy": getattr(setup, '_strategy_name', 'DETECTED'),
                            "strategy_variant": getattr(setup, '_strategy_name', 'DETECTED'),
                            "direction": setup.direction,
                            "units": abs(setup.units),
                            "entry_price": setup.entry_price,
                            "stop_loss": setup.stop_loss,
                            "take_profit": setup.take_profit_1,
                            "mode": self.mode.value,
                            "confidence": setup.reward_risk_ratio * 33,
                            "risk_reward_ratio": setup.reward_risk_ratio,
                            "reasoning": f"R:R {setup.reward_risk_ratio:.2f} | Risk {setup.risk_percent:.2%}",
                        })
                    except Exception as db_err:
                        logger.warning(f"DB record_trade failed (non-critical): {db_err}")

                # Send native notification
                dir_text = 'COMPRA' if setup.direction == 'BUY' else 'VENTA'
                inst_text = setup.instrument.replace('_', '/')
                self._push_notification(
                    "trade_executed",
                    f"Trade Ejecutado: {inst_text}",
                    f"{dir_text} | Entry: {setup.entry_price:.5f} | SL: {setup.stop_loss:.5f} | TP: {setup.take_profit_1:.5f} | R:R {setup.reward_risk_ratio:.1f}",
                    {"trade_id": trade_id, "instrument": setup.instrument},
                )
                self._daily_setups_executed += 1
                logger.info(f"Trade {trade_id} opened and tracked")

                # Send external alerts
                if self.alert_manager:
                    try:
                        await self.alert_manager.send_trade_executed(
                            instrument=setup.instrument,
                            direction=setup.direction,
                            entry=setup.entry_price,
                            sl=setup.stop_loss,
                            tp=setup.take_profit_1,
                            rr=setup.reward_risk_ratio,
                        )
                    except Exception as ae:
                        logger.debug(f"Alert send failed (non-critical): {ae}")

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
            return

        # Build a TradeRisk from the pending setup
        trade_risk = TradeRisk(
            instrument=setup.instrument,
            style=TradingStyle.DAY_TRADING,
            risk_percent=settings.risk_day_trading,
            units=setup.units,
            stop_loss=setup.stop_loss,
            take_profit_1=setup.take_profit,
            take_profit_max=None,
            reward_risk_ratio=setup.risk_reward_ratio,
            entry_price=current_price,
            direction=setup.direction,
        )

        await self._execute_setup(trade_risk)

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
                    "setups_skipped_ai": self._daily_setups_skipped_ai,
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
                report = await self.ai_analyzer.generate_daily_report(
                    trades=today_trades,
                    account_summary={"balance": account.balance, "currency": account.currency} if account else {},
                    scan_results={
                        inst: {"score": r.score, "htf_trend": r.htf_trend.value}
                        for inst, r in self._last_scan_results.items()
                    },
                )
                # Send AI report via email
                if self.alert_manager:
                    await self.alert_manager.send_alert(
                        "ai_daily_report",
                        f"NeonTrade AI - Daily Report {today}",
                        report,
                    )
            except Exception as e:
                logger.warning(f"AI daily report failed: {e}")

    # ── Daily Heartbeat ─────────────────────────────────────────

    def _reset_daily_counters(self):
        """Reset daily activity counters for a new day."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._daily_counter_date != today:
            self._daily_scan_count = 0
            self._daily_setups_found = 0
            self._daily_setups_executed = 0
            self._daily_setups_skipped_ai = 0
            self._daily_errors = 0
            self._daily_counter_date = today

    async def _maybe_send_morning_heartbeat(self, now: datetime):
        """
        Send a 'proof of life' email at ~8:00 UTC (3am Colombia) every day.
        This way the user knows the app is alive even if 0 trades happen.
        """
        if now.hour != 8 or now.minute >= 3:
            return
        if hasattr(self, '_heartbeat_sent_date') and self._heartbeat_sent_date == now.date():
            return

        self._heartbeat_sent_date = now.date()

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

            body = (
                f"<b>NeonTrade AI is ALIVE and running.</b>\n\n"
                f"<b>Balance:</b> {balance_str}\n"
                f"<b>Mode:</b> {mode}\n"
                f"<b>Open Positions:</b> {open_positions}\n"
                f"<b>Pairs Watched:</b> {len(settings.forex_watchlist)}\n"
                f"<b>Pairs Analyzed:</b> {pairs_analyzed}\n"
                f"<b>Strategies Active:</b> {strategies_on}/9\n"
                f"<b>Scan Interval:</b> {self._scan_interval}s\n\n"
                f"<i>Trading hours: 07:00-21:00 UTC. You'll get a summary at 21:00 UTC.</i>"
            )

            await self.alert_manager.send_alert(
                "engine_status",
                f"NeonTrade AI - Morning Heartbeat ({now.strftime('%Y-%m-%d')})",
                body,
            )
            logger.info("Morning heartbeat email sent")
        except Exception as e:
            logger.warning(f"Failed to send morning heartbeat: {e}")

    # ── Status ───────────────────────────────────────────────────

    def get_status(self) -> Dict:
        """Get current engine status for the API/frontend."""
        self._expire_old_setups()
        pending_count = sum(
            1 for s in self.pending_setups if s.status == "pending"
        )

        return {
            "running": self._running,
            "mode": self.mode.value,
            "open_positions": len(self.position_manager.positions),
            "total_risk": self.risk_manager.get_current_total_risk(),
            "watchlist_count": len(settings.forex_watchlist),
            "pending_setups_count": pending_count,
            "enabled_strategies": self._enabled_strategies,
            "daily_activity": {
                "date": self._daily_counter_date,
                "scans_completed": self._daily_scan_count,
                "setups_found": self._daily_setups_found,
                "setups_executed": self._daily_setups_executed,
                "setups_skipped_ai": self._daily_setups_skipped_ai,
                "errors": self._daily_errors,
            },
            "last_scan": {
                inst: {
                    "score": result.score,
                    "htf_trend": result.htf_trend.value,
                    "ltf_trend": result.ltf_trend.value,
                    "convergence": result.htf_ltf_convergence,
                    "patterns": result.candlestick_patterns,
                }
                for inst, result in self._last_scan_results.items()
            },
            "positions": {
                tid: {
                    "instrument": pos.instrument,
                    "direction": pos.direction,
                    "entry": pos.entry_price,
                    "current_sl": pos.current_sl,
                    "tp1": pos.take_profit_1,
                    "phase": pos.phase.value,
                }
                for tid, pos in self.position_manager.positions.items()
            },
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
        }
