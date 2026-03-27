"""
NeonTrade AI - Configuration
Multi-broker Trading System powered by TradingLab Strategies
"""

from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    # Active broker: "ibkr", "capital", or "oanda"
    active_broker: str = "capital"

    # Interactive Brokers (IBKR) - Web API OAuth 1.0a
    ibkr_consumer_key: str = ""
    ibkr_access_token: str = ""
    ibkr_access_token_secret: str = ""
    ibkr_keys_dir: str = "keys"  # directory with PEM files
    ibkr_environment: str = "live"  # "live" or "paper"

    # Capital.com
    capital_api_key: str = ""
    capital_password: str = ""
    capital_identifier: str = ""  # email address
    capital_environment: str = "demo"  # "demo" or "live"
    capital_account_id: str = ""  # specific account ID (empty = auto-detect real account)

    # OANDA (alternative)
    oanda_api_key: str = ""
    oanda_account_id: str = ""
    oanda_environment: str = "practice"  # "practice" or "live"

    # OpenAI
    openai_api_key: str = ""

    # App
    app_secret_key: str = "change-me"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    # Firebase (push notifications)
    fcm_server_key: str = ""

    # News APIs
    finnhub_api_key: str = ""
    newsapi_key: str = ""

    # Alert channels
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    discord_webhook_url: str = ""
    alert_email_smtp_server: str = "smtp.gmail.com"
    alert_email_smtp_port: int = 587
    alert_email_username: str = ""
    alert_email_password: str = ""
    alert_email_recipient: str = ""

    # Gmail OAuth2 (preferred over SMTP for Gmail)
    gmail_sender: str = ""
    gmail_recipient: str = ""
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_refresh_token: str = ""

    # Security
    api_secret_key: str = ""  # Pre-shared API key (set in env to skip key generation)

    # Database
    database_url: str = "sqlite:///./data/trading.db"

    # ── Trading Plan Rules (from TradingLab Course) ──────────────
    # ── TradingLab recommends starting with BLUE + RED only.
    # ── All other strategies should be enabled only after mastering these two.
    # ── "Con que seáis bueno con una sola estrategia ya es suficiente para
    # ──  empezar a operar e incluso fondearos y vivir del trading" — Alex

    # Trading style: "day_trading" (default), "scalping", "swing"
    trading_style: str = "day_trading"

    # Risk per trade by style (ch18.3 Regla del 1%)
    risk_day_trading: float = 0.01        # 1% — the foundational rule
    risk_scalping: float = 0.005          # 0.5%
    risk_swing: float = 0.01             # Mentoría: 1% para todos los estilos
    max_total_risk: float = 0.07          # 7% max simultaneous open risk

    # Correlated pairs risk reduction (ch18.3)
    # e.g., AUD/JPY + AUD/CAD → 0.75% each instead of 1% + 1%
    correlated_risk_factor: float = 0.75

    # Minimum reward:risk ratio to TP1 (ch22.1 Trading Plan)
    # Mentoría: R:R mínimo ~2.5:1 para principiantes
    # BLACK and GREEN enforce their own minimum of 2.0 separately
    min_rr_ratio: float = 2.0
    min_rr_black: float = 2.0   # BLACK is counter-trend, needs higher R:R
    min_rr_green: float = 2.0   # GREEN has potential up to 10:1 R:R

    # Position management (ch21 Avanzado)
    move_sl_to_be_at: float = 0.01   # Move SL to BE at 1% unrealized profit (TradingLab: "al 1% pongo BE")
    scale_in_require_be: bool = True  # No new trade unless BE on existing (non-negotiable)
    partial_taking: bool = False      # Alex does NOT take partials — prefers quick exit at TP1
    # SL management style: "ema" (recommended), "price_action" (subjective, not recommended)
    sl_management_style: str = "ema"

    # Drawdown-based risk adjustment (ch18.7)
    # Methods: "fixed_1pct" (always 1%, recommended for beginners),
    #          "variable" (win-rate based, most professional),
    #          "fixed_levels" (step-down at DD thresholds, most conservative)
    drawdown_method: str = "fixed_1pct"
    # Fixed levels: reduce risk at these drawdown thresholds
    drawdown_level_1: float = 0.05    # -5% DD -> 0.75% risk
    drawdown_level_2: float = 0.075   # -7.5% DD -> 0.50% risk
    drawdown_level_3: float = 0.10    # -10% DD -> 0.25% risk (funded account max)
    drawdown_risk_1: float = 0.0075   # 0.75% at level 1
    drawdown_risk_2: float = 0.005    # 0.50% at level 2
    drawdown_risk_3: float = 0.0025   # 0.25% at level 3
    # Minimum risk floor (never go below this regardless of drawdown)
    drawdown_min_risk: float = 0.0025  # 0.25% absolute floor

    # Delta risk algorithm (ch18.8) — increase risk during winning streaks
    # Disabled by default (beginners should use fixed 1% until profitable)
    delta_enabled: bool = False
    delta_parameter: float = 0.60     # 0.20-0.90, 0.60 recommended
    delta_max_risk: float = 0.03      # Max risk increase cap (3%)

    # Trading hours (UTC) - London + New York sessions only
    trading_start_hour: int = 7    # 07:00 UTC (London open)
    trading_end_hour: int = 21     # 21:00 UTC (NY close)

    # Days to avoid
    close_before_friday_hour: int = 20  # Close positions before Friday 20:00 UTC
    avoid_news_minutes_before: int = 30  # Don't trade 30 min before major news
    avoid_news_minutes_after: int = 15   # Don't trade 15 min after major news

    # Timeframes — Day Trading (default)
    htf_timeframes: List[str] = ["W", "D"]
    ltf_timeframes: List[str] = ["H4", "H1", "M15", "M5", "M2"]

    # EMAs for Day Trading execution (ch21 Avanzado)
    ema_fast: int = 2    # EMA 2 periods (shortest, for aggressive trailing)
    ema_slow: int = 5    # EMA 5 periods (for short-term trailing)
    # Key structural EMAs (used by all strategies)
    ema_1h: int = 50     # EMA 50 on 1H — BLUE pullback zone
    ema_4h: int = 50     # EMA 50 on 4H — RED pullback zone, BLUE TP
    ema_daily: int = 20  # EMA 20 on Daily — trend filter
    sma_daily: int = 200 # SMA 200 on Daily — long-term trend filter

    # Scalping module (Workshop de Scalping)
    # TradingLab: scalping is the RISKIEST style — master day trading first.
    # RED is the recommended strategy for scalping. Avoid BLUE in scalping
    # (15M-to-5M ratio is 3x, making ruptures too similar between timeframes).
    scalping_enabled: bool = False
    scalping_max_daily_dd: float = 0.05  # 5% max daily drawdown
    scalping_max_total_dd: float = 0.10  # 10% max total drawdown

    # Funded account mode (Workshop de Cuentas Fondeadas)
    # Only enable after 3 consecutive months of profitability
    funded_account_mode: bool = False
    funded_max_daily_dd: float = 0.05  # 5% max daily drawdown
    funded_max_total_dd: float = 0.10  # 10% max total drawdown
    funded_no_overnight: bool = True   # Close all positions before session end
    funded_no_news_trading: bool = True  # No trading around news events

    # ── Discretion Level (ch22.1 Trading Plan) ──────────────────
    # Beginners: 100% precision, 0% discretion. Follow the plan exactly.
    # Alex (experienced): 80% precision, 20% discretion.
    discretion_pct: float = 0.0  # 0% discretion for beginners

    # ── Forex Watchlist (from FOREX.txt) ──────────────────────────
    # TradingLab focus: "mercado de Divisas (including indices and metals)"
    # Commodities are NOT the primary focus and should be avoided by beginners.
    # Exotics: USD exotics are better than EUR exotics (more volume, better
    # pattern respect). Alex pruned EUR exotics over time.
    forex_watchlist: List[str] = [
        # Principales USD (7 pairs — the core)
        "AUD_USD", "EUR_USD", "GBP_USD", "NZD_USD",
        "USD_CAD", "USD_CHF", "USD_JPY",
        # Principales EUR
        "EUR_AUD", "EUR_CHF", "EUR_GBP", "EUR_JPY", "EUR_NZD",
        # Principales CAD
        "AUD_CAD", "CAD_CHF", "EUR_CAD", "GBP_CAD", "NZD_CAD",
        # Principales JPY
        "AUD_JPY", "CAD_JPY", "CHF_JPY", "GBP_JPY", "NZD_JPY",
        # Otros cruces
        "AUD_CHF", "AUD_NZD", "GBP_AUD", "GBP_CHF", "GBP_NZD", "NZD_CHF",
        # Metales (included in forex per TradingLab — treated as currencies)
        "XAU_USD", "XAG_USD",
    ]

    # Correlation pairs map (TradingLab: enter with 0.75% each if correlated)
    correlation_groups: List[List[str]] = [
        ["AUD_USD", "NZD_USD"],
        ["AUD_JPY", "AUD_CAD", "AUD_NZD", "AUD_CHF"],
        ["EUR_USD", "GBP_USD"],
        ["USD_CHF", "USD_CAD"],
        ["EUR_JPY", "GBP_JPY", "CAD_JPY"],
        ["XAU_USD", "XAG_USD"],
    ]

    # ── Extended Watchlists ────────────────────────────────────────
    # Available for backtesting and when using brokers that support them.
    # NOT active by default per TradingLab recommendation to focus.

    # Exotic forex — USD exotics kept (better volume), EUR exotics pruned
    forex_exotic_watchlist: List[str] = [
        # Exotic USD (more volume = better pattern respect — Alex keeps these)
        "USD_CNH", "USD_CZK", "USD_HUF", "USD_MXN", "USD_NOK",
        "USD_PLN", "USD_SEK", "USD_SGD", "USD_TRY", "USD_ZAR",
        # Exotic EUR (reduced — worse than USD exotics per Alex)
        "EUR_MXN", "EUR_NOK", "EUR_ZAR",
        # Precious metals (beyond Gold/Silver)
        "XPD_USD", "XPT_USD",
    ]

    # Commodities — NOT recommended by TradingLab for primary trading.
    # Available only for backtesting/analysis.
    commodities_watchlist: List[str] = [
        "BCO_USD", "WTICO_USD", "NATGAS_USD",
        "WHEAT_USD", "CORN_USD", "SOYBN_USD", "SUGAR_USD",
        "XPT_USD", "XPD_USD", "XCU_USD",
    ]

    # Indices — from FOREX.txt (US500, SX5E, US2000)
    indices_watchlist: List[str] = [
        "US30_USD", "US2000_USD", "NAS100_USD", "SPX500_USD",
        "DE30_EUR", "FR40_EUR", "UK100_GBP",
        "JP225_USD", "AU200_AUD", "HK33_HKD", "CN50_USD",
    ]

    # Crypto — separate allocation per Trading Plan (10% of trading capital)
    # Mentoría: GREEN es la ÚNICA estrategia para crypto
    crypto_default_strategy: str = "GREEN"
    crypto_watchlist: List[str] = [
        # TradingLab allocation: 70% BTC, 20% ETH, 10% altcoins
        "BTC_USD", "ETH_USD", "SOL_USD", "ADA_USD", "DOT_USD",
        "LINK_USD", "AVAX_USD", "MATIC_USD", "UNI_USD", "ATOM_USD",
        "XRP_USD", "DOGE_USD", "LTC_USD", "BNB_USD", "FTM_USD",
        "ALGO_USD", "XLM_USD", "EOS_USD", "XTZ_USD", "VET_USD",
    ]

    # Active categories — only forex by default (TradingLab: focus on divisas)
    # Options: forex, forex_exotic, commodities, indices, crypto
    active_watchlist_categories: List[str] = ["forex"]

    # ── Capital Allocation (ch18.5 + Trading Plan) ────────────────
    # Mentoría: 70% trading, 20% inversión, 10% cripto
    allocation_trading_pct: float = 0.70     # 70% in trading accounts
    allocation_forex_pct: float = 0.70       # 70% forex/indices/metals (within trading)
    allocation_crypto_pct: float = 0.10      # 10% crypto (within trading)
    allocation_other_pct: float = 0.20       # Mentoría: 20% otros (índices, materias primas) dentro de trading
    allocation_investment_pct: float = 0.20  # 20% long-term (stocks/ETFs)
    allocation_investment_stocks: float = 0.80  # 80% stocks/ETFs (70% VT/S&P500, 30% sectors)
    allocation_investment_crypto: float = 0.20  # 20% crypto (70% BTC, 20% ETH, 10% alts)

    # Extended correlation groups
    indices_correlation_groups: List[List[str]] = [
        ["US30_USD", "SPX500_USD", "NAS100_USD"],
        ["DE30_EUR", "FR40_EUR"],
        ["JP225_USD", "AU200_AUD"],
    ]

    crypto_correlation_groups: List[List[str]] = [
        ["BTC_USD", "ETH_USD"],
        ["SOL_USD", "AVAX_USD", "FTM_USD"],
        ["ADA_USD", "DOT_USD", "ATOM_USD"],
    ]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# ── Load persisted risk configuration overrides ──────────────────
def _load_risk_overrides():
    """Load any runtime risk config overrides from data/risk_config.json."""
    import json
    risk_path = os.path.join("data", "risk_config.json")
    if os.path.exists(risk_path):
        try:
            with open(risk_path) as f:
                overrides = json.load(f)
            for key, value in overrides.items():
                if hasattr(settings, key):
                    setattr(settings, key, value)
        except Exception:
            pass

_load_risk_overrides()


# ── OANDA API URLs ───────────────────────────────────────────────
OANDA_API_URL = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}

OANDA_STREAM_URL = {
    "practice": "https://stream-fxpractice.oanda.com",
    "live": "https://stream-fxtrade.oanda.com",
}


def get_oanda_url() -> str:
    return OANDA_API_URL[settings.oanda_environment]


def get_oanda_stream_url() -> str:
    return OANDA_STREAM_URL[settings.oanda_environment]
