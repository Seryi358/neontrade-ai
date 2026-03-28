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

    # Trading style: "day_trading" (default, Alex's preference), "scalping", "swing"
    # "me he dado cuenta que lo que más me gusta es el day trading [...] es el
    #  estilo que se adapta más a mí" — Alex (Estilos de trading)
    # User can change this; all strategies adapt to the selected style.
    trading_style: str = "day_trading"

    # Risk per trade by style (ch18.3 Regla del 1%)
    risk_day_trading: float = 0.01        # 1% — the foundational rule
    risk_scalping: float = 0.005          # 0.5% (NeonTrade AI default; workshop defers exact %)
    risk_swing: float = 0.03             # Trading Plan PDF: 3% en Swing trading
    max_total_risk: float = 0.07          # 7% max simultaneous open risk

    # Correlated pairs risk reduction (ch18.3)
    # Mentorship: "entrar con el 0,75% de riesgo en cada uno"
    # This is a FIXED absolute value: 0.75% per correlated trade
    correlated_risk_pct: float = 0.0075  # Fixed 0.75% risk per correlated trade

    # Minimum reward:risk ratio to TP1 (ch22.1 Trading Plan)
    # Trading Plan PDF: R:R mínimo 0.80:1 con 61% win rate (Alex experimentado)
    # Mentoría ch18.3: R:R referencia ~2.5:1 con 30% win rate → breakeven con 1% riesgo
    # Rango target: 1.5:1 a 2.5:1 (Alex: "Perfectamente puede ser un 2. Dos y medio, tres")
    # Default 1.5:1 as balanced starting point; adjust based on win rate
    min_rr_ratio: float = 1.5
    min_rr_black: float = 2.0   # BLACK is counter-trend, needs higher R:R (mentoría explícita)
    min_rr_green: float = 2.0   # GREEN has potential up to 10:1 R:R (mentoría explícita)
    min_confluence_points: int = 2  # Minimum positive confluence points required (mentorship doesn't specify 3)

    # Reference benchmarks from ch18.3 Regla del 1%:
    # - Win rate target de referencia: 30% (con R:R 2.5:1 y 1% riesgo = ~breakeven)
    #   Alex: "puedes ganar sin problema el 30% de los trades que ejecutas"
    # - Mínimo 100 trades antes de juzgar el sistema (100 oportunidades al 1%)
    #   Alex: "tienes 100 trades como mínimo para poder practicar, progresar, mejorar"
    reference_win_rate: float = 0.30   # 30% — informational, not a gate
    reference_min_trades: int = 100    # Minimum trades before evaluating system

    # Position management (ch21 Avanzado)
    # Default management style: "cp" (short-term, Alex's preference), "lp" (long-term), "cpa" (aggressive)
    # Alex: "personas como yo, que lo que buscamos es salir cuanto antes" → CP
    # LP gives trades more room (wider EMA), CP locks profit sooner (tighter EMA)
    # CPA is NOT standalone — only used combined with LP/CP at key levels
    position_management_style: str = "cp"

    # Break Even trigger method:
    #   "risk_distance" (Alex's preference): BE when profit >= 1x risk distance
    #     Alex: "cuando ya tengo un 1% de ganancia, pongo el break-even"
    #     For 1% risk, this means BE at 1% profit (R:R 1:1 point)
    #   "pct_to_tp1": BE at a percentage of distance to TP1
    #     Trading Plan PDF: "Cuando estemos por la mitad del beneficio hasta el TP1, pondré el BE"
    # For a 2:1 R:R trade at 1% risk, both methods coincide (1% profit = 50% to TP1).
    # For other R:R ratios, "risk_distance" is simpler and matches Alex's oral instruction.
    be_trigger_method: str = "risk_distance"
    move_sl_to_be_pct_to_tp1: float = 0.50  # Only used when be_trigger_method="pct_to_tp1"

    scale_in_require_be: bool = True  # No new trade unless BE on existing (non-negotiable)
    partial_taking: bool = False      # Alex does NOT take partials — prefers quick exit at TP1
    # Partial profit taking: Alex personally doesn't use it, but the mentorship
    # teaches it as optional and the CPA section recommends partial closes at
    # key levels. Enable to allow partial position closes at TP levels.
    allow_partial_profits: bool = False
    # SL management style: "ema" (recommended), "price_action" (swing highs/lows alternative)
    sl_management_style: str = "ema"

    # CPA auto-trigger conditions (Short-term Aggressive)
    # Alex: CPA is used in specific situations, not from the start of a trade.
    # When enabled, the position manager will automatically switch to CPA trailing
    # when any of these conditions are detected at an advanced phase of the trade.
    # Alex: "doble techo, noticias, fin de semana, indecisión cerca del TP"
    cpa_auto_on_double_pattern: bool = True    # Switch to CPA near double top/bottom
    cpa_auto_on_news: bool = True              # Switch to CPA before high-impact news
    cpa_auto_on_friday_close: bool = True      # Switch to CPA approaching Friday close
    cpa_auto_on_indecision: bool = True        # Switch to CPA on indecision near TP/key levels

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
    # TradingLab: London 08:00-17:00 UTC, NY 13:00-22:00 UTC (approx, shifts with DST)
    # We start at 07:00 to catch London pre-market and end at 22:00 for full NY session
    trading_start_hour: int = 7    # 07:00 UTC (London pre-open)
    trading_end_hour: int = 22     # 22:00 UTC (NY close, 5PM ET in EST)

    # Days to avoid
    close_before_friday_hour: int = 20  # Close positions before Friday 20:00 UTC
    no_new_trades_friday_hour: int = 18  # No NEW trades after Friday 18:00 UTC (Trading Plan)
    avoid_news_minutes_before: int = 30  # Don't trade 30 min before major news
    avoid_news_minutes_after: int = 15   # Don't trade 15 min after major news

    # Timeframes — Day Trading layout (Alex's preferred style)
    # Roles: Directional=D (1D), Analysis=H4, Entry/Management=H1, Execution=M5
    # W is included for context (Elliott waves, macro structure)
    # "me levanto por la mañana, hago mi lista de seguimiento, me pongo mis
    #  alertas [...] en el momento en que me saltan las alertas estoy pendiente
    #  de si tengo que ejecutar alguna posición o no" — Alex (Estilos de trading)
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
    # NeonTrade AI defaults (NOT from workshop — workshop defers DD limits)
    scalping_max_daily_dd: float = 0.05  # 5% max daily drawdown (app-added safety)
    scalping_max_total_dd: float = 0.10  # 10% max total drawdown (app-added safety)
    # BLUE strategy handling in scalping (Workshop Section 10):
    # "aggressive" = trade all BLUEs, "skip_all" = skip all, "clean_only" = 80%+ confidence only
    scalping_blue_mode: str = "clean_only"
    # Exit method (Workshop Section 7):
    # "fixed_tp" = Method 1 (hold until TP, safest, instructor default)
    # "fast" = Method 2 (M1 EMA 50 trailing)
    # "slow" = Method 3 (M5 EMA 50 trailing)
    scalping_exit_method: str = "fixed_tp"

    # Funded account mode (Workshop de Cuentas Fondeadas)
    # Only enable after 3 consecutive months of profitability
    funded_account_mode: bool = False
    # Account type: "normal" (FTMO restricted) or "swing" (FTMO no restrictions)
    # Workshop: Kevin recommends "swing" for TradingLab day trading + swing strategies
    funded_account_type: str = "swing"
    # Evaluation type: "2phase" (standard), "1phase" (sprint, tighter DD), "instant", "real" (passed)
    funded_evaluation_type: str = "2phase"
    # DD limits - standard 2-phase (5%/10%). Sprint/1-phase: 4%/6% (set manually)
    funded_max_daily_dd: float = 0.05  # 5% max daily drawdown (2-phase); 4% for 1-phase
    funded_max_total_dd: float = 0.10  # 10% max total drawdown (2-phase); 6% for 1-phase
    # Profit targets for evaluation phases
    funded_profit_target_phase1: float = 0.10  # 10% for Phase 1 (FTMO), 8% (5RF)
    funded_profit_target_phase2: float = 0.05  # 5% for Phase 2
    funded_current_phase: int = 1  # 1 or 2 (for 2-phase evaluations)
    # Restrictions — depends on account type:
    # "normal" (FTMO): no overnight, no weekend, no news. "swing": no restrictions.
    # Default False because workshop recommends swing accounts for TradingLab strategies.
    funded_no_overnight: bool = False   # True only for FTMO "normal" accounts
    funded_no_news_trading: bool = False  # True only for FTMO "normal" accounts
    funded_no_weekend: bool = False  # True only for FTMO "normal" accounts

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
        # Exotic EUR (reduced — worse than USD exotics per Alex, but kept per FOREX.txt)
        "EUR_CNH", "EUR_MXN", "EUR_NOK", "EUR_SGD", "EUR_ZAR",
        # Precious metals (beyond Gold/Silver)
        "XPD_USD", "XPT_USD",
    ]

    # Commodities — NOT recommended by TradingLab for primary trading.
    # Available only for backtesting/analysis.
    commodities_watchlist: List[str] = [
        # Energy (COMMODITIES.txt: CL, QM, HO, NG, QG, EH, RB)
        "BCO_USD", "WTICO_USD", "NATGAS_USD",
        # Agricultural (COMMODITIES.txt: ZW, KE, ZC, ZO, ZS, ZL, ZM, ZR, SB, KC, CC, LBS + livestock)
        # Oanda CFDs available:
        "WHEAT_USD", "CORN_USD", "SOYBN_USD", "SUGAR_USD",
        # Not available as Oanda CFDs: oats (ZO), soybean oil (ZL), soybean meal (ZM),
        # rough rice (ZR), KC wheat (KE), cocoa (CC), coffee (KC), lumber (LBS),
        # lean hogs (HE), live cattle (LE), feeder cattle (GF), milk (DC)
        # Metals (COMMODITIES.txt: PL, PA, SI, GC, HG)
        "XAU_USD", "XAG_USD", "XPT_USD", "XPD_USD", "XCU_USD",
    ]

    # Indices — from FOREX.txt (US500, SX5E, US2000)
    indices_watchlist: List[str] = [
        "US30_USD", "US2000_USD", "NAS100_USD", "SPX500_USD",
        "DE30_EUR", "FR40_EUR", "UK100_GBP",
        "JP225_USD", "AU200_AUD", "HK33_HKD", "CN50_USD",
    ]

    # Equities — US sector ETFs for swing trading (from EQUITIES_IND.txt)
    # TradingLab: use sector ETFs to detect opportunities, then drill into holdings.
    # Alex: "yo enfoco el trading en acciones como swing trading en acciones de EEUU"
    # Available only via IBKR (not Oanda/Capital.com).
    equities_watchlist: List[str] = [
        # Innovation (ARK) — EQUITIES_IND.txt
        "ARKK", "ARKW", "ARKF", "ARKG", "ARKQ", "ARKX", "PRNT", "IZRL",
        # Airlines
        "JETS", "AAL", "DAL", "UAL",
        # Banking
        "KBE", "JPM", "BAC", "GS", "MS", "WFC",
        # Software / Cybersecurity
        "HACK", "IGV", "PSJ",
        # Semiconductors
        "SOXX", "PSI", "XSD",
        # Networking
        "PXQ",
        # Internet / Cloud
        "FDN", "CLOU", "SKYY", "CIBR", "EMQQ", "IHAK", "PNQI",
        # Clean Energy
        "ICLN", "TAN", "FAN", "KRBN",
        # Aerospace / Defense
        "XAR", "ITA", "PPA", "BA", "LMT", "RTX", "NOC", "GD", "TDG",
        "AVAV", "IRDM", "SPCE",
        # Biotechnology
        "XBI", "IBB", "FBT",
        # Gaming
        "ESPO", "HERO", "GAMR", "NERD", "EA",
        # Uranium
        "URA", "CCJ", "NXE", "DNN", "UUUU",
        # Agriculture
        "COW", "MOO",
        # Electric Car
        "NIO", "FCEL", "PLUG",
        # AI
        "NVDA", "IBM", "BIDU",
        # Cannabis
        "MJ", "MSOS", "TLRY", "CGC", "ACB",
        # VR
        "VUZI",
        # Crypto-related equities
        "COIN", "MSTR", "MARA", "RIOT", "HUT", "BLOK", "BITO",
        # Basic Materials
        "GDX", "GLD", "SLV", "XME", "PALL", "PPLT",
    ]

    # Crypto — separate allocation per Trading Plan (10% of trading capital)
    # Mentoría: GREEN es la ÚNICA estrategia para crypto
    crypto_default_strategy: str = "GREEN"
    # Mentorship: "Memecoins to be AVOIDED for strategy trading (too manipulated, no patterns)"
    # These are included in watchlist for capital rotation monitoring only.
    memecoins_monitor_only: bool = True
    memecoin_symbols: List[str] = ["DOGE_USD", "SHIB_USD", "PEPE_USD", "WIF_USD", "BONK_USD"]
    # Mentoría: up to ~150 cryptos. Organized by capitalization tiers.
    # Below ~1B market cap = extreme volatility, manipulation, less pattern reliability.
    crypto_watchlist: List[str] = [
        # === Top 10 (most stable, core positions) ===
        "BTC_USD", "ETH_USD", "BNB_USD", "SOL_USD", "XRP_USD",
        "ADA_USD", "AVAX_USD", "DOT_USD", "TRX_USD", "LINK_USD",
        # === Top 10-50 (growth potential + risk) ===
        "MATIC_USD", "UNI_USD", "ATOM_USD", "LTC_USD", "NEAR_USD",
        "APT_USD", "FIL_USD", "ARB_USD", "OP_USD", "INJ_USD",
        "RENDER_USD", "FET_USD", "GRT_USD", "STX_USD", "IMX_USD",
        "SEI_USD", "SUI_USD", "AAVE_USD", "MKR_USD", "RUNE_USD",
        "DOGE_USD", "SHIB_USD", "PEPE_USD", "WIF_USD", "BONK_USD",
        "FTM_USD", "ALGO_USD", "XLM_USD", "HBAR_USD", "VET_USD",
        "ICP_USD", "EOS_USD", "THETA_USD", "XTZ_USD", "EGLD_USD",
        "MANA_USD", "SAND_USD", "GALA_USD", "AXS_USD", "CHZ_USD",
        "CAKE_USD", "IOTA_USD",
        # === Top 50-150 (high volatility, smaller allocations) ===
        "CRV_USD", "SNX_USD", "COMP_USD", "LDO_USD", "RPL_USD",
        "ENS_USD", "PENDLE_USD", "GMX_USD", "DYDX_USD", "JUP_USD",
        "TIA_USD", "PYTH_USD", "WLD_USD", "ONDO_USD", "JTO_USD",
    ]

    # Market View — macro dashboard symbols (from MARKET_VIEW.txt)
    # NOT for trading — for context analysis (inflation, interest rates, global indices)
    market_view_symbols: List[str] = [
        # Europe indices (MARKET_VIEW.txt: DE30, SX5E, FR40, ESP35, ITA40, UK100)
        "DE30_EUR", "EU50_EUR", "FR40_EUR", "ESP35_EUR", "UK100_GBP",
        # US indices (MARKET_VIEW.txt: US30, US2000, NAS100, US500, NDQ, SPX, DJI, RTY)
        "US30_USD", "US2000_USD", "NAS100_USD", "SPX500_USD",
        # World indices (MARKET_VIEW.txt: CN50, HK33, IX0118, JP225, AU200, NZ50G)
        "CN50_USD", "HK33_HKD", "JP225_USD", "AU200_AUD",
        # Metals (MARKET_VIEW.txt: XAUXAG ratio, XAUUSD, XAGUSD, XPDUSD, XPTUSD, XCUUSD)
        "XAU_USD", "XAG_USD", "XPD_USD", "XPT_USD", "XCU_USD",
        # Energy / Commodities (MARKET_VIEW.txt: NATGAS, NG, SOYBN, WHEAT, KC, UKOIL, WTICO)
        "NATGAS_USD", "BCO_USD", "WTICO_USD", "SOYBN_USD", "WHEAT_USD",
        # Crypto (macro view — BTC + ETH only, per MARKET_VIEW.txt)
        "BTC_USD", "ETH_USD",
    ]

    # Active categories — only forex by default (TradingLab: focus on divisas)
    # Options: forex, forex_exotic, commodities, indices, equities, crypto
    active_watchlist_categories: List[str] = ["forex"]

    # ── Capital Allocation (ch18.5 + Trading Plan PDF) ──────────────
    # Trading Plan PDF: 80% trading (90% forex, 10% crypto), 20% investment
    # Mentoría clase: 70% trading, 20% inversión, 10% cripto
    # Using Trading Plan PDF values as authoritative
    allocation_trading_pct: float = 0.80     # 80% in trading accounts (Trading Plan PDF)
    allocation_forex_pct: float = 0.90       # 90% forex/indices/metals (within trading)
    allocation_crypto_pct: float = 0.10      # 10% crypto (within trading)
    allocation_investment_pct: float = 0.20  # 20% long-term (stocks/ETFs)
    allocation_investment_stocks: float = 0.80  # 80% stocks/ETFs (70% VT/S&P500, 30% sectors)
    allocation_investment_crypto: float = 0.20  # 20% crypto (70% BTC, 20% ETH, 10% alts)

    # Extended crypto correlation groups (mentoría: most cryptos move together)
    crypto_correlation_groups: List[List[str]] = [
        ["BTC_USD", "ETH_USD"],
        ["SOL_USD", "AVAX_USD", "FTM_USD", "NEAR_USD", "SUI_USD", "SEI_USD"],
        ["ADA_USD", "DOT_USD", "ATOM_USD", "LINK_USD"],
        ["ARB_USD", "OP_USD", "MATIC_USD", "IMX_USD"],
        ["UNI_USD", "AAVE_USD", "CRV_USD", "SNX_USD", "COMP_USD"],
        ["DOGE_USD", "SHIB_USD", "PEPE_USD", "WIF_USD", "BONK_USD"],
        ["FET_USD", "RENDER_USD", "WLD_USD"],
    ]

    # Extended index correlation groups
    indices_correlation_groups: List[List[str]] = [
        ["US30_USD", "SPX500_USD", "NAS100_USD"],
        ["DE30_EUR", "FR40_EUR"],
        ["JP225_USD", "AU200_AUD"],
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
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to load risk overrides from data/risk_config.json: {e}")

_load_risk_overrides()


# ── Trading Profile Presets ──────��─────────────────────────────
# Pre-configured profiles that apply a batch of settings at once.
# "tradinglab_recommended" = Alex Ruiz's exact preferences (Day Trading)
# "conservative" = Safer settings for beginners (Swing, lower risk)
TRADING_PROFILES = {
    "tradinglab_recommended": {
        "name": "TradingLab Recommended",
        "description": "Configuración exacta de Alex Ruiz: Day Trading, 1% riesgo, salida rápida, sin parciales, BE al 1%",
        "settings": {
            "trading_style": "day_trading",
            # Risk management — Alex's exact values
            "risk_day_trading": 0.01,       # 1% per trade
            "risk_scalping": 0.005,         # 0.5%
            "risk_swing": 0.03,             # 3%
            "max_total_risk": 0.07,         # 7% max simultaneous
            "correlated_risk_pct": 0.0075,  # 0.75% per correlated pair
            "min_rr_ratio": 1.5,            # 1.5:1 minimum R:R
            "min_rr_black": 2.0,            # BLACK counter-trend
            "min_rr_green": 2.0,            # GREEN crypto
            # Position management — Alex prefers quick exits
            "position_management_style": "cp",  # Short-term (Alex: "salir cuanto antes")
            "be_trigger_method": "risk_distance",  # BE at 1% profit
            "partial_taking": False,         # Alex does NOT take partials
            "allow_partial_profits": False,
            "sl_management_style": "ema",
            # CPA auto-triggers
            "cpa_auto_on_double_pattern": True,
            "cpa_auto_on_news": True,
            "cpa_auto_on_friday_close": True,
            "cpa_auto_on_indecision": True,
            # Drawdown — fixed 1% for safety
            "drawdown_method": "fixed_1pct",
            "delta_enabled": False,
            # Session hours — London + NY
            "trading_start_hour": 7,
            "trading_end_hour": 22,
            "close_before_friday_hour": 20,
            "no_new_trades_friday_hour": 18,
            "avoid_news_minutes_before": 30,
            "avoid_news_minutes_after": 15,
            # Watchlists — Alex's full set
            "active_watchlist_categories": ["forex", "forex_exotic", "commodities", "indices", "crypto"],
            # Discretion — Alex uses 20% but default for users is 0%
            "discretion_pct": 0.0,
            # Scalping/Funded off by default
            "scalping_enabled": False,
            "funded_account_mode": False,
        },
    },
    "conservative": {
        "name": "Conservative",
        "description": "Perfil conservador para principiantes: Swing Trading, menor riesgo, solo forex principales",
        "settings": {
            "trading_style": "swing",
            # Risk management — lower risk for beginners
            "risk_day_trading": 0.01,
            "risk_scalping": 0.005,
            "risk_swing": 0.01,             # 1% instead of 3% for safety
            "max_total_risk": 0.05,          # 5% max (stricter)
            "correlated_risk_pct": 0.005,    # 0.5% per correlated pair
            "min_rr_ratio": 2.0,             # Higher minimum R:R for beginners
            "min_rr_black": 2.5,
            "min_rr_green": 2.5,
            # Position management — long-term (more room)
            "position_management_style": "lp",  # Long-term: wider trailing
            "be_trigger_method": "risk_distance",
            "partial_taking": False,
            "allow_partial_profits": False,
            "sl_management_style": "ema",
            # CPA auto-triggers
            "cpa_auto_on_double_pattern": True,
            "cpa_auto_on_news": True,
            "cpa_auto_on_friday_close": True,
            "cpa_auto_on_indecision": True,
            # Drawdown — fixed 1% (safest for beginners)
            "drawdown_method": "fixed_1pct",
            "delta_enabled": False,
            # Session hours — same London + NY
            "trading_start_hour": 7,
            "trading_end_hour": 22,
            "close_before_friday_hour": 20,
            "no_new_trades_friday_hour": 18,
            "avoid_news_minutes_before": 30,
            "avoid_news_minutes_after": 15,
            # Watchlists — only forex principals for beginners
            "active_watchlist_categories": ["forex"],
            # No discretion for beginners
            "discretion_pct": 0.0,
            # Scalping/Funded off
            "scalping_enabled": False,
            "funded_account_mode": False,
        },
    },
}


def apply_trading_profile(profile_id: str) -> dict:
    """Apply a trading profile preset to the current settings.
    Returns the dict of settings that were applied."""
    import json
    if profile_id not in TRADING_PROFILES:
        raise ValueError(f"Perfil '{profile_id}' no existe. Disponibles: {list(TRADING_PROFILES.keys())}")

    profile = TRADING_PROFILES[profile_id]
    applied = {}
    for key, value in profile["settings"].items():
        if hasattr(settings, key):
            setattr(settings, key, value)
            applied[key] = value

    # Persist risk-related settings to data/risk_config.json
    risk_keys = {
        "risk_day_trading", "risk_scalping", "risk_swing", "max_total_risk",
        "correlated_risk_pct", "min_rr_ratio", "move_sl_to_be_pct_to_tp1",
        "drawdown_method", "delta_enabled", "delta_parameter", "delta_max_risk",
        "scale_in_require_be", "min_rr_black", "min_rr_green",
    }
    risk_updates = {k: v for k, v in applied.items() if k in risk_keys}
    if risk_updates:
        config_path = os.path.join("data", "risk_config.json")
        existing = {}
        if os.path.exists(config_path):
            try:
                with open(config_path) as f:
                    existing = json.load(f)
            except Exception:
                pass
        existing.update(risk_updates)
        os.makedirs("data", exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(existing, f, indent=2)

    return applied


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
    return OANDA_API_URL.get(settings.oanda_environment, OANDA_API_URL["practice"])


def get_oanda_stream_url() -> str:
    return OANDA_STREAM_URL.get(settings.oanda_environment, OANDA_STREAM_URL["practice"])
