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
    # Risk per trade by style
    risk_day_trading: float = 0.01        # 1%
    risk_scalping: float = 0.005          # 0.5%
    risk_swing: float = 0.03             # 3%
    max_total_risk: float = 0.07          # 7% max simultaneous

    # Correlated pairs risk reduction
    correlated_risk_factor: float = 0.75  # 0.75% each instead of 1%

    # Minimum reward:risk ratio to TP1 (Trading Plan: 0.80 because win rate is 61%)
    # BLACK strategy enforces its own minimum of 2.0 separately
    min_rr_ratio: float = 0.80

    # Position management
    move_sl_to_be_at: float = 0.50  # Move SL to BE when price is 50% to TP1
    scale_in_require_be: bool = True  # No new trade unless BE set on existing (Trading Plan)

    # Drawdown-based risk adjustment (from TradingLab ch18.7)
    # Methods: "fixed_1pct" (always 1%), "variable" (win-rate based), "fixed_levels"
    drawdown_method: str = "fixed_levels"
    # Fixed levels: reduce risk at these drawdown thresholds
    drawdown_level_1: float = 0.0412  # -4.12% DD -> 0.75% risk
    drawdown_level_2: float = 0.0618  # -6.18% DD -> 0.50% risk
    drawdown_level_3: float = 0.0824  # -8.24% DD -> 0.25% risk
    drawdown_risk_1: float = 0.0075   # 0.75% at level 1
    drawdown_risk_2: float = 0.005    # 0.50% at level 2
    drawdown_risk_3: float = 0.0025   # 0.25% at level 3

    # Delta risk algorithm (from TradingLab ch18.8)
    # Increase risk during winning streaks
    delta_enabled: bool = False       # Disabled by default (conservative)
    delta_parameter: float = 0.60     # 0.20-0.90, 0.60 recommended
    delta_max_risk: float = 0.03      # Max risk increase cap (3%)

    # Trading hours (UTC) - London + New York sessions
    trading_start_hour: int = 7    # 07:00 UTC (London open)
    trading_end_hour: int = 21     # 21:00 UTC (NY close)

    # Days to avoid
    close_before_friday_hour: int = 20  # Close positions before Friday 20:00 UTC
    avoid_news_minutes_before: int = 30  # Don't trade 30 min before major news
    avoid_news_minutes_after: int = 15   # Don't trade 15 min after major news

    # Timeframes
    htf_timeframes: List[str] = ["W", "D"]         # Weekly, Daily
    ltf_timeframes: List[str] = ["H4", "H1", "M15", "M5", "M2"]

    # EMAs for Day Trading
    ema_fast: int = 2    # EMA 2 periods
    ema_slow: int = 5    # EMA 5 periods

    # Scalping module (Workshop de Scalping)
    scalping_enabled: bool = False  # Toggle scalping mode
    scalping_max_daily_dd: float = 0.05  # 5% max daily drawdown
    scalping_max_total_dd: float = 0.10  # 10% max total drawdown

    # Funded account mode (Workshop de Cuentas Fondeadas)
    funded_account_mode: bool = False  # Enable funded account constraints
    funded_max_daily_dd: float = 0.05  # 5% max daily drawdown
    funded_max_total_dd: float = 0.10  # 10% max total drawdown
    funded_no_overnight: bool = True   # Close all positions before session end
    funded_no_news_trading: bool = True  # No trading around news events

    # Forex pairs watchlist (from FOREX.txt)
    forex_watchlist: List[str] = [
        # Principales USD
        "AUD_USD", "EUR_USD", "GBP_USD", "NZD_USD",
        "USD_CAD", "USD_CHF", "USD_JPY",
        # Principales EUR
        "EUR_AUD", "EUR_CHF", "EUR_GBP", "EUR_JPY", "EUR_NZD",
        # Principales CAD
        "AUD_CAD", "CAD_CHF", "EUR_CAD", "GBP_CAD", "NZD_CAD",
        # Principales JPY
        "AUD_JPY", "CAD_JPY", "CHF_JPY", "GBP_JPY", "NZD_JPY",
        # Otros
        "AUD_CHF", "AUD_NZD", "GBP_AUD", "GBP_CHF", "GBP_NZD", "NZD_CHF",
        # Metales (from FOREX.txt)
        "XAU_USD", "XAG_USD",
    ]

    # Correlation pairs map (pairs that tend to move together)
    correlation_groups: List[List[str]] = [
        ["AUD_USD", "NZD_USD"],
        ["AUD_JPY", "AUD_CAD", "AUD_NZD", "AUD_CHF"],
        ["EUR_USD", "GBP_USD"],
        ["USD_CHF", "USD_CAD"],
        ["EUR_JPY", "GBP_JPY", "CAD_JPY"],
        ["XAU_USD", "XAG_USD"],
    ]

    # ── Extended Watchlists (from TradingLab course files) ──────────
    # These contain ALL instruments from the course. The active watchlist
    # is forex_watchlist by default; extended lists are available for
    # backtesting, analysis, and when using brokers that support them.

    # Additional forex pairs (exotics + metals/indices from FOREX.txt)
    forex_exotic_watchlist: List[str] = [
        # Exotic EUR
        "EUR_CNH", "EUR_MXN", "EUR_NOK", "EUR_SGD", "EUR_ZAR",
        # Exotic USD
        "USD_CNH", "USD_CZK", "USD_HUF", "USD_MXN", "USD_NOK",
        "USD_PLN", "USD_SEK", "USD_SGD", "USD_TRY", "USD_ZAR",
        # Metals & Indices (from FOREX.txt)
        "XPD_USD", "XPT_USD",
    ]

    commodities_watchlist: List[str] = [
        # Energy
        "BCO_USD", "WTICO_USD", "NATGAS_USD",
        # Agricultural
        "WHEAT_USD", "CORN_USD", "SOYBN_USD", "SUGAR_USD",
        # Metals (already in forex: XAU, XAG)
        "XPT_USD", "XPD_USD", "XCU_USD",
    ]

    indices_watchlist: List[str] = [
        # US
        "US30_USD", "US2000_USD", "NAS100_USD", "SPX500_USD",
        # Europe
        "DE30_EUR", "FR40_EUR", "UK100_GBP",
        # Asia/Pacific
        "JP225_USD", "AU200_AUD", "HK33_HKD", "CN50_USD",
    ]

    crypto_watchlist: List[str] = [
        # Top crypto pairs (from CRYPTO USDT.txt - most liquid only)
        "BTC_USD", "ETH_USD", "SOL_USD", "ADA_USD", "DOT_USD",
        "LINK_USD", "AVAX_USD", "MATIC_USD", "UNI_USD", "ATOM_USD",
        "XRP_USD", "DOGE_USD", "LTC_USD", "BNB_USD", "FTM_USD",
        "ALGO_USD", "XLM_USD", "EOS_USD", "XTZ_USD", "VET_USD",
    ]

    # Which watchlist categories are active (toggle in UI)
    active_watchlist_categories: List[str] = ["forex"]  # Options: forex, forex_exotic, commodities, indices, crypto

    # Capital allocation per Trading Plan
    allocation_trading_pct: float = 0.80     # 80% in trading accounts
    allocation_forex_pct: float = 0.90       # 90% forex/indices/metals
    allocation_crypto_pct: float = 0.10      # 10% crypto
    allocation_investment_pct: float = 0.20  # 20% long-term
    allocation_investment_stocks: float = 0.80  # 80% stocks
    allocation_investment_crypto: float = 0.20  # 20% crypto

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
