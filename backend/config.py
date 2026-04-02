"""
NeonTrade AI - Configuration
Multi-broker Trading System powered by TradingLab Strategies
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import os


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    # Active broker: "ibkr" or "capital" (OANDA removed — out of scope per PROJECT.md)
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
    risk_swing: float = 0.01             # 1% default (Alex's Trading Plan uses 3% for swing; adjustable via API)
    max_total_risk: float = 0.07          # 7% max simultaneous open risk

    # Correlated pairs risk reduction (ch18.3)
    # Mentorship: "entrar con el 0,75% de riesgo en cada uno"
    # This is a FIXED absolute value: 0.75% per correlated trade
    correlated_risk_pct: float = 0.0075  # Fixed 0.75% risk per correlated trade

    # Minimum reward:risk ratio to TP1 (ch22.1 Trading Plan)
    # Trading Plan PDF: R:R mínimo 0.80:1 con 61% win rate (Alex experimentado)
    # Mentoría ch18.3: R:R referencia ~2.5:1 con 30% win rate → breakeven con 1% riesgo
    # Trading Plan PDF: Alex uses 0.80:1 minimum to TP1 (with 61% win rate)
    # Default 1.5:1 is more conservative for users with unknown win rate.
    # Adjust down to 0.80 once you achieve 60%+ win rate over 100+ trades.
    min_rr_ratio: float = 1.5
    min_rr_black: float = 2.0   # BLACK is counter-trend, needs higher R:R (mentoría explícita)
    min_rr_green: float = 2.0   # GREEN has potential up to 10:1 R:R (mentoría explícita)
    min_rr_blue_c: float = 2.0  # Blue C requires min 2:1 R:R (mentorship: "minimo 2 a 1, incluso 3 a 1")
    min_confluence_points: int = 2  # Market orders: 2 levels. Limit orders: Trading Plan PDF says 3 (Fib+EMA+S/R)
    min_confluence_limit_order: int = 3  # Limit order convergence: 3 levels required (Trading Plan PDF)

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

    # ── Overtrading / Revenge Trading Prevention (Psicología Avanzada) ──
    # Mentorship: "sobreoperar después de una pérdida" is a top-5 failure mode.
    # These limits protect against emotional trading during drawdowns.
    max_trades_per_day: int = 5           # Max trades per day (0 = unlimited). Alex: conservative 3-5/day
    cooldown_after_consecutive_losses: int = 2  # After N consecutive losses, enforce cooldown
    cooldown_minutes: int = 60            # Minutes to wait after consecutive loss threshold

    # Re-entry risk reduction (configurable per trader's plan)
    # Mentorship: "Cada uno pone sus normas" — these are DEFAULTS, not hard rules.
    # Alex uses 0.5% and 0.25% as examples but says the trader defines their own plan.
    max_reentries_per_setup: int = 3       # Max re-entries per setup (0 = disabled)
    reentry_window_seconds: int = 1800     # 30 minutes (configurable per trader's plan)
    reentry_risk_1: float = 0.50           # Reentry 1: 50% of normal risk (e.g., 1% -> 0.5%)
    reentry_risk_2: float = 0.25           # Reentry 2: 25% of normal risk (e.g., 1% -> 0.25%)
    reentry_risk_3: float = 0.25           # Reentry 3+: 25% of normal risk (floor)
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
    cpa_auto_on_key_levels: bool = True        # Switch to CPA near key reference levels (prev highs/lows, Fib extensions)

    # Drawdown-based risk adjustment (ch18.7)
    # Methods: "fixed_1pct" (always 1%, recommended for beginners),
    #          "variable" (win-rate based, most professional),
    #          "fixed_levels" (step-down at DD thresholds, most conservative)
    drawdown_method: str = "fixed_1pct"
    # Fixed levels: reduce risk at these drawdown thresholds
    # Values from TradingPlan_2024.pdf "Cálculo fijo" screenshot:
    # Level 1: -4.12% DD (4 trades * 1.03% avg loss)
    # Level 2: -6.18% DD (6 trades * 1.03% avg loss)
    # Level 3: -8.23% DD (8 trades * 1.03% avg loss)
    drawdown_level_1: float = 0.0412  # -4.12% DD -> 0.75% risk
    drawdown_level_2: float = 0.0618  # -6.18% DD -> 0.50% risk
    drawdown_level_3: float = 0.0823  # -8.23% DD -> 0.25% risk (funded account max)
    drawdown_risk_1: float = 0.0075   # 0.75% at level 1
    drawdown_risk_2: float = 0.005    # 0.50% at level 2
    drawdown_risk_3: float = 0.0025   # 0.25% at level 3
    # Minimum risk floor (never go below this regardless of drawdown)
    drawdown_min_risk: float = 0.0025  # 0.25% absolute floor

    # Delta risk algorithm (ch18.8) — increase risk during winning streaks
    # Disabled by default (beginners should use fixed 1% until profitable)
    delta_enabled: bool = False
    delta_parameter: float = 0.60     # 0.20-0.90, 0.60 recommended
    delta_max_risk: float = 0.02      # Max risk increase cap (2% per TradingLab)

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
    # Swing trading: Alex says "podemos llegar a ejecutar incluso" during news
    # Relaxed buffers for swing style (mentorship: swing is less affected by news)
    avoid_news_minutes_before_swing: int = 15  # Relaxed: 15 min before for swing (matches NewsFilter)
    avoid_news_minutes_after_swing: int = 5    # Relaxed: 5 min after for swing
    # News impact differentiation (mentorship: Interest Rates, Unemployment, CPI, GDP
    # are the key ones — "estas cuatro son las más importantes")
    # high = Interest Rates, NFP/Unemployment, CPI, GDP
    # medium = PMI, Retail Sales, Trade Balance, Consumer Confidence
    # low = everything else
    news_impact_filter: str = "high"  # "high" = only avoid high-impact, "all" = avoid all

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

    # ── Green Strategy SL Mode ──────────────────────────────────
    # "advanced" (default) = SL below last swing before diagonal (mentorship method)
    # "beginner" = SL below pattern minimum (simpler, wider SL)
    green_sl_mode: str = "advanced"

    # ── Discretion Level (ch22.1 Trading Plan) ──────────────────
    # Beginners: 100% precision, 0% discretion. Follow the plan exactly.
    # Alex (experienced): 80% precision, 20% discretion.
    discretion_pct: float = 0.0  # 0% discretion for beginners

    # ── Forex Watchlist (from mentorship course materials) ──────────────────────────
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
    # Expanded to cover all watchlist pairs sharing a common currency
    correlation_groups: List[List[str]] = [
        ["AUD_USD", "NZD_USD"],
        ["AUD_JPY", "AUD_CAD", "AUD_NZD", "AUD_CHF"],
        ["EUR_USD", "GBP_USD"],
        ["USD_CHF", "USD_CAD"],
        ["EUR_JPY", "GBP_JPY", "CAD_JPY", "CHF_JPY", "NZD_JPY"],
        ["GBP_AUD", "GBP_NZD", "GBP_CHF"],
        ["NZD_CHF", "NZD_CAD"],
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
        # Exotic EUR (reduced — worse than USD exotics per Alex, but kept per mentorship course materials)
        "EUR_CNH", "EUR_MXN", "EUR_NOK", "EUR_SGD", "EUR_ZAR",
        # Precious metals (beyond Gold/Silver)
        "XPD_USD", "XPT_USD",
    ]

    # Commodities — NOT recommended by TradingLab for primary trading.
    # Available only for backtesting/analysis.
    commodities_watchlist: List[str] = [
        # Energy (from mentorship course materials: CL, QM, HO, NG, QG, EH, RB)
        "BCO_USD", "WTICO_USD", "NATGAS_USD",
        # Agricultural (from mentorship course materials: ZW, KE, ZC, ZO, ZS, ZL, ZM, ZR, SB, KC, CC, LBS + livestock)
        # Oanda CFDs available:
        "WHEAT_USD", "CORN_USD", "SOYBN_USD", "SUGAR_USD",
        # Not available as Oanda CFDs: oats (ZO), soybean oil (ZL), soybean meal (ZM),
        # rough rice (ZR), KC wheat (KE), cocoa (CC), coffee (KC), lumber (LBS),
        # lean hogs (HE), live cattle (LE), feeder cattle (GF), milk (DC)
        # Metals (from mentorship course materials: PL, PA, SI, GC, HG)
        "XAU_USD", "XAG_USD", "XPT_USD", "XPD_USD", "XCU_USD",
    ]

    # Indices (from mentorship course materials: US500, SX5E, US2000)
    indices_watchlist: List[str] = [
        "US30_USD", "US2000_USD", "NAS100_USD", "SPX500_USD",
        "DE30_EUR", "FR40_EUR", "UK100_GBP",
        "JP225_USD", "AU200_AUD", "HK33_HKD", "CN50_USD",
    ]

    # Equities — US sector ETFs for swing trading (from mentorship course materials)
    # TradingLab: use sector ETFs to detect opportunities, then drill into holdings.
    # Alex: "yo enfoco el trading en acciones como swing trading en acciones de EEUU"
    # Available only via IBKR (not Oanda/Capital.com).
    equities_watchlist: List[str] = [
        # Innovation (ARK) — from mentorship course materials
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

    # Dominance & Market Cap tracking symbols (Esp. Criptomonedas Section 7)
    # Alex tracks these in his watchlist for macro cycle analysis:
    # "BTC.D, ETH.D, Others.D, USDT.D, TOTAL, TOTAL2, TOTAL3"
    # These are NOT for strategy trading — they feed crypto_cycle.py analysis
    crypto_dominance_symbols: List[str] = [
        "BTC.D",     # Bitcoin Dominance
        "ETH.D",     # Ethereum Dominance
        "OTHERS.D",  # Altcoin Dominance (excl. BTC+ETH)
        "USDT.D",    # Tether Dominance (risk-off indicator)
        "TOTAL",     # Total crypto market cap
        "TOTAL2",    # Total market cap excl. BTC
        "TOTAL3",    # Total market cap excl. BTC+ETH
    ]

    # Crypto vs BTC pairs (Esp. Criptomonedas Section 7)
    # Alex: "criptos contra bitcoin" — tracks relative performance
    # When ETH/BTC rises, capital is rotating from BTC to alts
    crypto_btc_pairs: List[str] = [
        "ETH_BTC", "SOL_BTC", "BNB_BTC", "XRP_BTC", "ADA_BTC",
        "AVAX_BTC", "DOT_BTC", "LINK_BTC", "NEAR_BTC", "UNI_BTC",
    ]

    # Crypto position management style (Esp. Criptomonedas position management)
    # Three modes taught in the specialization:
    #   "long_term" = weekly EMA 50 trailing (default, safest)
    #   "daily" = daily EMA 50 trailing (mentorship: dynamic support in bull, resistance in bear)
    #   "short_term" = H1 EMA 50 trailing (faster exits, ~7-10% moves)
    #   "aggressive" = M15 EMA 50 trailing / reference TP + M15 validation
    # Alex recommends beginners start with "long_term"
    crypto_position_mgmt_style: str = "long_term"

    # Mentoría: up to ~150 cryptos. Organized by capitalization tiers.
    # Below ~1B market cap = extreme volatility, manipulation, less pattern reliability.
    crypto_watchlist: List[str] = [
        # === Top 10 (most stable, core positions) ===
        "BTC_USD", "ETH_USD", "BNB_USD", "SOL_USD", "XRP_USD",
        "ADA_USD", "AVAX_USD", "DOT_USD", "TRX_USD", "LINK_USD",
        # === Top 10-50 (growth potential + risk) ===
        "BCH_USD", "ETC_USD", "XMR_USD",  # Added R4: top-50 coins missing from watchlist
        "MATIC_USD", "UNI_USD", "ATOM_USD", "LTC_USD", "NEAR_USD",
        "APT_USD", "FIL_USD", "ARB_USD", "OP_USD", "INJ_USD",
        "RENDER_USD", "FET_USD", "GRT_USD", "STX_USD", "IMX_USD",
        "SEI_USD", "SUI_USD", "AAVE_USD", "MKR_USD", "RUNE_USD",
        "DOGE_USD", "SHIB_USD", "PEPE_USD", "WIF_USD", "BONK_USD",
        "FTM_USD", "ALGO_USD", "XLM_USD", "HBAR_USD", "VET_USD",
        "ICP_USD", "EOS_USD", "THETA_USD", "XTZ_USD", "EGLD_USD",
        "MANA_USD", "SAND_USD", "GALA_USD", "AXS_USD", "CHZ_USD",
        "CAKE_USD", "IOTA_USD",
        # === Top 50-100 (high volatility, smaller allocations) ===
        "CRV_USD", "SNX_USD", "COMP_USD", "LDO_USD", "RPL_USD",
        "ENS_USD", "PENDLE_USD", "GMX_USD", "DYDX_USD", "JUP_USD",
        "TIA_USD", "PYTH_USD", "WLD_USD", "ONDO_USD", "JTO_USD",
        # === Top 100-150 (expanded per mentorship recommendation) ===
        "FLOW_USD", "KAVA_USD", "ZIL_USD", "ONE_USD", "CELO_USD",
        "ROSE_USD", "KDA_USD", "OCEAN_USD", "BAL_USD", "SUSHI_USD",
        "YFI_USD", "ZRX_USD", "ANKR_USD", "SKL_USD", "STORJ_USD",
        "ICX_USD", "ONT_USD", "ZEC_USD", "DASH_USD", "KSM_USD",
        "WAVES_USD", "1INCH_USD", "MASK_USD", "BAND_USD", "REN_USD",
        "AUDIO_USD", "CELR_USD", "MTL_USD", "CTSI_USD", "RAD_USD",
        "BAT_USD", "LOOM_USD", "NKN_USD", "OGN_USD", "PERP_USD",
        "QNT_USD", "RLC_USD", "SPELL_USD", "SSV_USD", "WAXP_USD",
        "API3_USD", "BAKE_USD", "BNT_USD", "COTI_USD", "HIFI_USD",
        "JASMY_USD", "LPT_USD", "OMG_USD", "POLS_USD", "REEF_USD",
        "SLP_USD", "SUPER_USD", "TOMO_USD", "TRB_USD", "UMA_USD",
    ]

    # Currency Strength Indices (from mentorship: Watchlist para Forex)
    # Alex: "Te recomiendo encarecidamente que tengas estos principales indices"
    # Used to understand what's driving each pair (e.g., AUDCHF: is AUD weak or CHF strong?)
    # NOT for trading — for analysis context (currency strength comparison)
    currency_strength_indices: List[str] = [
        "DXY",   # US Dollar Index
        "EXY",   # Euro Index
        "BXY",   # British Pound Index
        "JXY",   # Japanese Yen Index
        "AXY",   # Australian Dollar Index
        "SXY",   # Swiss Franc Index
        "CXY",   # Canadian Dollar Index
        "NXY",   # New Zealand Dollar Index
    ]

    # Market View — macro dashboard symbols (from mentorship course materials)
    # NOT for trading — for context analysis (inflation, interest rates, global indices)
    market_view_symbols: List[str] = [
        # Europe indices (from mentorship course materials: DE30, SX5E, FR40, ESP35, ITA40, UK100)
        "DE30_EUR", "EU50_EUR", "FR40_EUR", "ESP35_EUR", "UK100_GBP",
        # US indices (from mentorship course materials: US30, US2000, NAS100, US500, NDQ, SPX, DJI, RTY)
        "US30_USD", "US2000_USD", "NAS100_USD", "SPX500_USD",
        # World indices (from mentorship course materials: CN50, HK33, IX0118, JP225, AU200, NZ50G)
        "CN50_USD", "HK33_HKD", "JP225_USD", "AU200_AUD",
        # Metals (from mentorship course materials: XAUXAG ratio, XAUUSD, XAGUSD, XPDUSD, XPTUSD, XCUUSD)
        "XAU_USD", "XAG_USD", "XPD_USD", "XPT_USD", "XCU_USD",
        # Energy / Commodities (from mentorship course materials: NATGAS, NG, SOYBN, WHEAT, KC, UKOIL, WTICO)
        "NATGAS_USD", "BCO_USD", "WTICO_USD", "SOYBN_USD", "WHEAT_USD",
        # Crypto (macro view — BTC + ETH only, per mentorship course materials)
        "BTC_USD", "ETH_USD",
    ]

    # Active categories — only forex by default (TradingLab: focus on divisas)
    # Options: forex, forex_exotic, commodities, indices, equities, crypto
    active_watchlist_categories: List[str] = ["forex"]

    # ── Capital Allocation (ch18.5 Reparto del capital) ──────────────
    # Mentoría: 70% trading, 20% stocks/ETFs, 10% crypto largo plazo
    # Within trading: 70% forex, 20% other (indices/commodities/metals), 10% crypto
    allocation_trading_pct: float = 0.70     # 70% in trading accounts (mentorship class)
    allocation_forex_pct: float = 0.70       # 70% forex (within trading)
    allocation_other_pct: float = 0.20       # 20% other: indices, commodities, metals (within trading)
    allocation_crypto_pct: float = 0.10      # 10% crypto (within trading)
    allocation_investment_pct: float = 0.20  # 20% long-term stocks/ETFs (70% VT/S&P500, 30% sectors)
    allocation_crypto_longterm_pct: float = 0.10  # 10% crypto long-term (70% BTC, 20% ETH, 10% alts)

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

    # model_config defined at class level above (Pydantic v2 ConfigDict)


settings = Settings()

# ── Load persisted risk configuration overrides ──────────────────
def _load_risk_overrides():
    """Load any runtime risk config overrides from data/risk_config.json."""
    import json
    _config_dir = os.path.dirname(os.path.abspath(__file__))
    risk_path = os.path.join(_config_dir, "data", "risk_config.json")
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


def get_active_watchlist() -> list:
    """Build the combined watchlist from all active categories.

    Returns instruments from forex_watchlist, forex_exotic_watchlist,
    commodities_watchlist, indices_watchlist, equities_watchlist, and
    crypto_watchlist based on which categories are enabled in
    active_watchlist_categories.
    """
    category_map = {
        "forex": settings.forex_watchlist,
        "forex_exotic": settings.forex_exotic_watchlist,
        "commodities": settings.commodities_watchlist,
        "indices": settings.indices_watchlist,
        "equities": settings.equities_watchlist,
        "crypto": settings.crypto_watchlist,
    }
    combined = []
    for cat in settings.active_watchlist_categories:
        instruments = category_map.get(cat, [])
        combined.extend(instruments)
    # Deduplicate while preserving order
    seen = set()
    result = []
    for inst in combined:
        if inst not in seen:
            seen.add(inst)
            result.append(inst)
    return result


def _apply_funded_evaluation_defaults():
    """Auto-apply DD limits based on funded evaluation type.
    Workshop: Sprint/1-phase = 4% daily DD, 6% total DD (tighter than standard 5%/10%)."""
    if settings.funded_evaluation_type == "1phase":
        # Only override if user hasn't manually set different values
        if settings.funded_max_daily_dd == 0.05:  # still at default
            settings.funded_max_daily_dd = 0.04
        if settings.funded_max_total_dd == 0.10:  # still at default
            settings.funded_max_total_dd = 0.06
    elif settings.funded_evaluation_type == "instant":
        # Instant Funding: no daily DD limit, 10% total
        pass  # defaults are already correct

_apply_funded_evaluation_defaults()


# ── Trading Profile Presets ──────��─────────────────────────────
# Pre-configured profiles that apply a batch of settings at once.
# "tradinglab_recommended" = Alex Ruiz's exact preferences (Day Trading)
# "conservative" = Safer settings for beginners (Swing, lower risk)
TRADING_PROFILES = {
    "tradinglab_recommended": {
        "name": "TradingLab Recommended",
        "description": "Configuración exacta de Alex Ruiz: Day Trading, 1% riesgo en todos los estilos, salida rápida, sin parciales, BE al 1%",
        "settings": {
            "trading_style": "day_trading",
            # Risk management — Alex's exact values
            "risk_day_trading": 0.01,       # 1% per trade
            "risk_scalping": 0.005,         # 0.5%
            "risk_swing": 0.01,             # 1% — NON-NEGOTIABLE
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
            "cpa_auto_on_key_levels": True,
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
            # Green SL mode — advanced (below last swing before diagonal)
            "green_sl_mode": "advanced",
            # Scalping — Alex prefers quick exits with M1 EMA 50 trailing
            "scalping_enabled": False,
            "scalping_exit_method": "fast",
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
            "risk_swing": 0.01,             # 1% — NON-NEGOTIABLE per mentorship
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
            "cpa_auto_on_key_levels": True,
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

# ── Funded Account Presets (Workshop de Cuentas Fondeadas) ────────────
# Pre-configured settings for specific prop firm evaluation parameters.
FUNDED_ACCOUNT_PRESETS = {
    "ftmo_2phase": {
        "name": "FTMO 2-Phase",
        "description": "Standard FTMO evaluation: Phase 1=10%, Phase 2=5%, DD 5%/10%",
        "settings": {
            "funded_evaluation_type": "2phase",
            "funded_max_daily_dd": 0.05,
            "funded_max_total_dd": 0.10,
            "funded_profit_target_phase1": 0.10,
            "funded_profit_target_phase2": 0.05,
        },
    },
    "ftmo_sprint": {
        "name": "FTMO Sprint (1-Phase)",
        "description": "FTMO Sprint evaluation: tighter DD (4%/6%), single phase",
        "settings": {
            "funded_evaluation_type": "1phase",
            "funded_max_daily_dd": 0.04,
            "funded_max_total_dd": 0.06,
            "funded_profit_target_phase1": 0.10,
            "funded_profit_target_phase2": 0.05,
        },
    },
    "ftmo_instant": {
        "name": "FTMO Instant Funding",
        "description": "Instant funding: no daily DD limit, 10% total DD",
        "settings": {
            "funded_evaluation_type": "instant",
            "funded_max_daily_dd": 1.0,  # No daily DD limit for instant
            "funded_max_total_dd": 0.10,
            "funded_profit_target_phase1": 0.0,
            "funded_profit_target_phase2": 0.0,
        },
    },
    "bitfunded": {
        "name": "Bitfunded (Crypto)",
        "description": "Bitfunded crypto prop firm: Stage 1=8%, Stage 2=5%, DD 5%/10%, 80% profit share, max 5x leverage",
        "settings": {
            "funded_evaluation_type": "2phase",
            "funded_max_daily_dd": 0.05,
            "funded_max_total_dd": 0.10,
            "funded_profit_target_phase1": 0.08,  # 8% for Stage 1 (vs FTMO 10%)
            "funded_profit_target_phase2": 0.05,  # 5% for Stage 2
        },
    },
}


def apply_funded_preset(preset_id: str) -> dict:
    """Apply a funded account preset to the current settings.
    Returns the dict of settings that were applied."""
    if preset_id not in FUNDED_ACCOUNT_PRESETS:
        raise ValueError(f"Preset '{preset_id}' no existe. Disponibles: {list(FUNDED_ACCOUNT_PRESETS.keys())}")

    preset = FUNDED_ACCOUNT_PRESETS[preset_id]
    applied = {}
    for key, value in preset["settings"].items():
        if hasattr(settings, key):
            setattr(settings, key, value)
            applied[key] = value

    settings.funded_account_mode = True
    applied["funded_account_mode"] = True
    return applied


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
        _config_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(_config_dir, "data", "risk_config.json")
        existing = {}
        if os.path.exists(config_path):
            try:
                with open(config_path) as f:
                    existing = json.load(f)
            except Exception:
                pass
        existing.update(risk_updates)
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(existing, f, indent=2)

    return applied
