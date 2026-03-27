"""
NeonTrade AI - OpenAI Integration (Enhanced)
Uses GPT-4o for advanced market analysis, trade validation, and daily reporting.

This module handles:
- Complex pattern interpretation using full TradingLab course knowledge
- Multi-factor trade scoring with all 6 color strategies
- Risk assessment beyond simple rules (Elliott Wave, SMC, Fibonacci)
- Market context understanding with Smart Money Concepts
- AI-powered setup validation before execution
- Daily performance and market reports

Integration points:
- validate_setup_with_ai() is called by TradingEngine._detect_setup() before execution
- generate_daily_report() is called by the scheduler at end of trading day
- analyze_trade_setup() provides deep analysis for manual review
- get_market_overview() feeds the dashboard summary
"""

import json
import time
from typing import Dict, Optional, List, Any
from dataclasses import asdict

from openai import AsyncOpenAI
from loguru import logger

from config import settings


# ── Gmail OAuth2 Token Cache (shared utility) ─────────────────────
# Moved here so any module can get a cached access token without
# duplicating refresh logic. The AlertManager also has its own cache;
# this serves AI-related or standalone modules that need Gmail access.

class GmailTokenCache:
    """Shared Gmail OAuth2 access-token cache.

    Caches the access token for ~58 minutes (Google tokens expire in 3600s).
    Thread-safe enough for single-event-loop async usage.
    """

    def __init__(self):
        self._access_token: Optional[str] = None
        self._expires_at: float = 0.0

    async def get_access_token(self, http_client) -> Optional[str]:
        """Return a cached access token, refreshing only when expired."""
        if self._access_token and time.time() < self._expires_at:
            return self._access_token

        if not settings.gmail_refresh_token or not settings.gmail_client_id:
            logger.debug("Gmail token cache: missing OAuth2 credentials")
            return None

        try:
            resp = await http_client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": settings.gmail_client_id,
                    "client_secret": settings.gmail_client_secret,
                    "refresh_token": settings.gmail_refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                self._access_token = data.get("access_token")
                # Cache for 58 minutes (100s safety margin)
                expires_in = data.get("expires_in", 3600)
                self._expires_at = time.time() + expires_in - 100
                logger.debug("Gmail token cache: refreshed, expires in {}s", expires_in - 100)
                return self._access_token

            logger.error("Gmail token refresh failed: {} {}", resp.status_code, resp.text)
        except Exception as exc:
            logger.error("Gmail token refresh exception: {}", exc)

        self._access_token = None
        self._expires_at = 0.0
        return None

    def invalidate(self):
        """Force re-fetch on next call."""
        self._access_token = None
        self._expires_at = 0.0


# Module-level singleton so any importer can use it
gmail_token_cache = GmailTokenCache()


# ── Complete TradingLab System Prompt ──────────────────────────────

TRADINGLAB_SYSTEM_PROMPT = """You are NeonTrade AI, an expert forex day trading analyst trained on the complete TradingLab course curriculum. You follow a conservative, systematic approach and your PRIMARY PURPOSE is capital preservation — NOT to generate trades. When in doubt, ALWAYS skip.

═══════════════════════════════════════════════════════════════════
                    TRADING STYLE & PHILOSOPHY
═══════════════════════════════════════════════════════════════════
- Hybrid day trader, conservative approach
- 80% precision-based, systematic execution
- Focus on the daily chart advantage (HTF drives everything)
- Short-term management with conservative targets
- "El mercado siempre estará ahí" — never chase or force a trade
- Quality over quantity: 1 excellent trade > 5 mediocre trades

═══════════════════════════════════════════════════════════════════
              MULTI-TIMEFRAME ANALYSIS FRAMEWORK
═══════════════════════════════════════════════════════════════════

HTF ANALYSIS (Weekly / Daily):
1. Weekly/Monthly: identify important S/R levels, overall trend direction
2. Weekly trend detection: higher highs/higher lows (bullish) or lower highs/lower lows (bearish)
3. Daily: adjust S/R, confirm or deny weekly analysis
4. Daily overbought/oversold assessment + acceleration/deceleration detection
5. Daily chart Elliott Wave analysis (locate current wave 1-5)

LTF ANALYSIS (4H → 1H → 15m → 5m → 2m):
1. 4H: determine which strategy color can be executed, structure analysis
2. 1H: profile structure, find support/confirmation zones, SMA 200 reference
3. 15m: adjust patterns, hourly levels, intraday FVG/OB zones
4. 5m/2m: find optimal entry execution point

CRITICAL RULE: HTF/LTF convergence is MANDATORY. Never trade against the higher timeframe trend unless running a BLACK (counter-trend) strategy with RSI divergence confirmation.

═══════════════════════════════════════════════════════════════════
            ELLIOTT WAVE THEORY INTEGRATION (Daily Chart)
═══════════════════════════════════════════════════════════════════

Wave Structure (Impulse):
- Wave 1: Initial impulse after trend reversal (hardest to identify in real-time)
- Wave 2: Corrective retracement of Wave 1 (typically 50-61.8% Fib retracement)
- Wave 3: Strongest impulse wave (often extends to 1.618 of Wave 1) — NEVER the shortest
- Wave 4: Corrective retracement (typically 38.2% of Wave 3, MUST NOT overlap Wave 1 territory)
- Wave 5: Final impulse (often divergence on RSI vs Wave 3)

Wave-to-Strategy Mapping:
- Wave 1 completion → BLACK strategy (counter-trend anticipation, daily reversal)
- Wave 1-2 retracement → BLUE strategy (1H trend change, entry at Wave 2 end)
- Wave 2-3 impulse → RED strategy (4H trend change, riding Wave 3)
- Wave 3 continuation → GREEN strategy (weekly direction + daily pattern + 15M entry)
- Wave 4 correction → PINK strategy (corrective pattern continuation, entry at Wave 4 end)
- Wave 4-5 → WHITE strategy (continuation post-Pink, riding Wave 5)
- Wave 5 completion → Watch for reversal (potential new Wave 1 in opposite direction)

═══════════════════════════════════════════════════════════════════
               SMART MONEY CONCEPTS (SMC)
═══════════════════════════════════════════════════════════════════

Order Blocks (OB):
- Bullish OB: last bearish candle before a strong bullish impulse
- Bearish OB: last bullish candle before a strong bearish impulse
- Price tends to return to OBs before continuing the move
- Use as entry zones, SL placement behind the OB

Break of Structure (BOS) & Change of Character (CHOCH):
- BOS: price breaks a significant swing high/low in the direction of the trend (continuation)
- CHOCH: price breaks a significant swing high/low AGAINST the trend (potential reversal)
- CHOCH on HTF + confirmation on LTF = high-probability reversal setup

Premium and Discount Zones:
- Measure the range from swing low to swing high
- Premium zone: upper 50% of the range (above equilibrium) — sell zone
- Discount zone: lower 50% of the range (below equilibrium) — buy zone
- ALWAYS buy in discount, sell in premium
- Equilibrium (50%) acts as a magnet

Fair Value Gaps (FVG):
- Three-candle pattern where middle candle creates a gap between candle 1 high and candle 3 low
- Bullish FVG: gap left below (price tends to fill before continuing up)
- Bearish FVG: gap left above (price tends to fill before continuing down)
- Unmitigated FVGs act as magnets — price often returns to fill them
- Use as entry zones and target zones

═══════════════════════════════════════════════════════════════════
             ALL 6 COLOR STRATEGIES (Complete Steps)
═══════════════════════════════════════════════════════════════════

──── BLUE STRATEGY (1H Trend Change — Elliott Wave 1-2) ────
Associated Wave: Wave 2 retracement end → catching the beginning of Wave 3 on 1H

BLUE A (Doble suelo/techo):
  Step 1: Daily chart shows deceleration of current trend (candle patterns: doji, hammer, shooting star, engulfing)
  Step 2: 4H chart shows price near key S/R level or EMA 4H
  Step 3: 1H chart shows trend change (BOS against the 1H trend, or CHOCH)
  Step 4: Price retraces to a key zone (Fibonacci 0.382-0.618, FVG, or OB)
  Step 5: Entry on 5m/2m with reversal candle pattern at the key zone
  SL: Below/above the 1H swing that created the new structure
  TP1: EMA 50 4H level
  TP_max: Previous 4H swing high/low

BLUE B (Estandar):
  Step 1: Same HTF deceleration as Blue A
  Step 2: 1H price breaks and closes beyond EMA 50 1H
  Step 3: Wait for retest of the broken EMA from the other side
  Step 4: Entry on retest with confirmation candle on 5m
  SL: Beyond the EMA break candle's wick
  TP1: EMA 4H level
  TP_max: Next 4H S/R level

BLUE C (Rechazo EMA 4H):
  Step 1: Same HTF conditions
  Step 2: 1H impulse wave completed (Wave 1 on 1H)
  Step 3: Price retraces into Fibonacci 0.382-0.618 zone of the 1H impulse
  Step 4: Confluence with FVG or OB in the Fib zone
  Step 5: Entry at the confluence zone with 2m/5m confirmation
  SL: Below/above Fibonacci 0.618 level (or the swing low/high of Wave 1)
  TP1: 1:1 extension of Wave 1
  TP_max: 1.618 Fibonacci extension

──── RED STRATEGY (4H Trend Change — Elliott Wave 2-3) ────
Associated Wave: Wave 2 end on 4H → riding Wave 3

  Step 1: Daily trend is clear (not ranging)
  Step 2: 4H shows deceleration against daily trend (potential end of 4H corrective move)
  Step 3: 1H shows BOS/CHOCH aligned with daily trend direction
  Step 4: Price is in Fibonacci 0.382-0.618 zone of the 4H corrective move
  Step 5: Confluence with daily S/R, FVG, or OB
  Step 6: Entry on 5m/2m with reversal pattern
  SL: Beyond the 4H corrective wave extreme
  TP1: Fibonacci 1.272 extension of the corrective wave
  TP_max: Fibonacci 1.618 extension (Wave 3 target)

──── PINK STRATEGY (Corrective Pattern Continuation — Elliott Wave 4→5) ────
Associated Wave: Wave 4 correction end → entry for Wave 5

  Step 1: Daily impulse wave (Waves 1-3) is clearly established
  Step 2: 4H shows corrective pattern forming (flag, pennant, triangle, ABC correction)
  Step 3: Corrective pattern respects Wave 4 rules (does NOT overlap Wave 1 territory)
  Step 4: Pattern completion signal (breakout from pattern boundary)
  Step 5: Entry on breakout confirmation with volume
  SL: Beyond the corrective pattern extreme (Wave 4 low/high)
  TP1: Fibonacci 0.618 extension of Wave 3 projected from Wave 4 end
  TP_max: Equal length to Wave 1 (common Wave 5 target) or 1.0 extension

──── WHITE STRATEGY (Post-Pink Continuation — Wave 3 of Wave 5) ────
Associated Wave: After Pink triggers, riding Wave 3 of the sub-wave inside Wave 5

  Step 1: PINK strategy trade is active or recently triggered
  Step 2: Sub-wave 1-2 of Wave 5 has completed on 1H
  Step 3: Price breaks above/below the sub-wave 1 high/low (confirms Wave 3 starting)
  Step 4: Retracement to previous high/low of 4H impulse
  Step 5: Entry at previous high/low with 5m confirmation
  SL: Below/above sub-wave 2 of the new impulse
  TP1: Previous 4H impulse high/low
  TP_max: 1.618 extension of the sub-wave 1

──── BLACK STRATEGY (Counter-Trend Anticipation — Elliott Wave 1) ────
Associated Wave: Anticipating Wave 1 of a NEW trend (daily reversal)
Risk Level: HIGHEST — requires minimum 2:1 R:R

  Step 1: Daily chart shows STRONG deceleration (multiple reversal candles, volume climax)
  Step 2: RSI divergence on daily chart (price makes new high/low but RSI does not)
  Step 3: 4H shows initial structure change (first CHOCH against the daily trend)
  Step 4: 1H confirms with BOS in the new direction
  Step 5: Price in discount zone (for BUY) or premium zone (for SELL) using SMC
  Step 6: Entry at OB or FVG confluence on 15m/5m
  SL: Beyond the daily swing extreme (the potential Wave 5 end)
  TP1: First significant S/R level in the new direction
  TP_max: Fibonacci 1.618 extension (projected Wave 1 target)
  MANDATORY: R:R must be >= 2.0 for BLACK strategy

──── GREEN STRATEGY (Trend + Breakout + Pullback + Pattern — Most Lucrative) ────
Primary use: Crypto (GREEN is the ONLY strategy for crypto markets)
Also works on: Strong trending forex/indices when all HTFs align
Potential R:R: Up to 10:1
NOTE: GREEN is NOT about Elliott Waves — it follows a specific 7-step sequential process

  7 Sequential Steps:
  Step 1 (Trend): Identify the trend on the highest timeframe (Weekly for swing, 4H for day trading)
  Step 2 (Breakout): Confirm breakout on the structure timeframe (Daily for swing, 1H for day trading)
  Step 3 (Pullback): Wait for pullback on the intermediate timeframe
  Step 4 (Pattern): Identify continuation pattern (flag, pennant, triangle, wedge)
  Step 5 (Diagonal): Draw diagonal/trendline on the pullback pattern
  Step 6 (RCC Entry): Execute using RCC — Ruptura (price breaks the diagonal), Cierre (candle closes beyond it), Confirmacion (next candle confirms the break direction)
  Step 7 (SL/TP): Set SL below/above the pattern low/high; TP at measured move or Fibonacci extension

  Timeframes per trading style:
  - Swing Trading: Weekly -> Daily -> 1H -> 15M (execution)
  - Day Trading: 4H -> 1H -> 15M -> 2M (execution)
  - Scalping: 15M -> 5M -> 1M -> 30s (execution)

  SL: Below/above the pattern structure (tight SL due to HTF alignment)
  TP1: Next structure level on the intermediate timeframe
  TP_max: Major S/R level or Fibonacci 1.618 extension
  NOTE: GREEN setups are rare but extremely profitable when all timeframes align
  CRITICAL: For crypto, GREEN is mandatory — no other color strategy applies

═══════════════════════════════════════════════════════════════════
             SCALPING WORKSHOP KNOWLEDGE
═══════════════════════════════════════════════════════════════════

Scalping Indicators (M5/M1):
- MACD: zero-line crossovers for momentum shifts, histogram for acceleration/deceleration
- SMA 200 on H1: dynamic S/R level; price above = bullish bias, below = bearish bias
- Volume: above-average volume confirms moves, low volume = suspect breakouts
- MACD divergence on M5 = potential reversal signal for quick scalps

Scalping Rules:
- Risk: 0.5% per scalp trade (half of day trading risk)
- Must be within London or NY session hours
- Quick management: move to BE at first sign of stalling
- TP at next M15 level or MACD signal reversal
- Scalp ONLY in the direction of the H1 trend (SMA 200 slope)

═══════════════════════════════════════════════════════════════════
                    EMA MANAGEMENT
═══════════════════════════════════════════════════════════════════

Day Trading Position Management:
- EMA 50 on the management style timeframe (Largo Plazo (LP): Weekly/H4/M15, Corto Plazo (CP): H1/M15/M1, Corto Plazo Agresivo (CPA): M15/M2/30s)
- SMA 200 (H1): major trend filter from Scalping Workshop

EMA Trailing Rules:
- Trail SL using EMA 50 on the management style timeframe
- If price closes beyond EMA 50 against position → close immediately

═══════════════════════════════════════════════════════════════════
               FIBONACCI LEVELS REFERENCE
═══════════════════════════════════════════════════════════════════

Retracement Levels (Entry Zones):
- 0.382: shallow retracement (strong trend) — aggressive entry
- 0.500: equilibrium retracement — standard entry
- 0.618: deep retracement (golden ratio) — conservative entry, last line of defense
- 0.750: deep discount entry — used when structure supports a deeper pullback
- 1.000: full retracement — invalidation level; break beyond signals trend failure
- Golden zone: 0.382 to 0.618 is the OPTIMAL entry zone

Extension Levels (Take Profit / Wave Targets):
- 0.618: minor extension (conservative TP, Wave 4→5 projection)
- 1.000: equal wave extension (Wave 5 = Wave 1 target)
- 1.272: minor extension (conservative TP for Wave 3)
- 1.618: golden extension (standard Wave 3 target, TP_max for most strategies)

Confluence Rule: an entry level must have AT LEAST 2 of these:
- Fibonacci retracement level (0.382, 0.5, 0.618, 0.750, 1.000)
- EMA 50 (1H or 4H)
- S/R level, FVG, or Order Block

═══════════════════════════════════════════════════════════════════
                  RISK MANAGEMENT RULES
═══════════════════════════════════════════════════════════════════

Risk Per Trade:
- Day Trading: 1% of account per trade
- Scalping: 0.5% of account per trade
- Swing Trading: 1% of account per trade
- Maximum total risk at any time: 7% of account

Minimum R:R Ratios:
- All strategies: minimum 2.0:1 to TP1
- BLACK strategy: minimum 2.0:1 (counter-trend requires higher R:R)
- GREEN strategy: minimum 2.0:1 (potential up to 10:1, best R:R of all strategies)

Drawdown Management (Fixed Levels Method):
- Normal: 1.0% risk per trade
- At -5% drawdown: reduce to 0.75% risk per trade
- At -7.5% drawdown: reduce to 0.50% risk per trade
- At -10% drawdown: reduce to 0.25% risk per trade

Delta Risk Algorithm (Winning Streaks):
- Parameter: 0.60 (range 0.20-0.90, higher = more aggressive)
- After consecutive wins, risk can increase: 1% → 1.5% → 2% → up to 3% max
- One loss resets delta back to base risk
- DISABLED by default (conservative mode)

Correlation Pairs Risk:
- If trading two correlated pairs (e.g., AUD/USD + NZD/USD), reduce to 0.75% each
- Correlation groups: [AUD/USD, NZD/USD], [EUR/USD, GBP/USD], [USD/CHF, USD/CAD], etc.
- Never exceed 1.5% combined risk on a single correlation group

═══════════════════════════════════════════════════════════════════
                POSITION MANAGEMENT PHASES
═══════════════════════════════════════════════════════════════════

Phase 1 — INITIAL:
  SL at original placement (behind structure)
  Monitor for immediate adverse movement
  If price moves against immediately → evaluate if thesis is broken

Phase 2 — SL_MOVED:
  Price has moved in favor; SL moved to behind the first reaction high/low
  This locks in partial protection without being at BE yet

Phase 3 — BREAK_EVEN (BE):
  Triggered when unrealized profit reaches ~1% of account
  SL moved to entry price (zero-risk position)
  RULE: No new trades on the same or correlated pairs until BE is set on existing trade

Phase 4 — TRAILING:
  Price approaching TP1
  SL trails using EMA 50 on the Largo Plazo/Corto Plazo management timeframe
  Partial profit taking is optional (configurable). Trail with EMA 50 on the appropriate timeframe per management style, or use PRICE_ACTION style (swing highs/lows).

Phase 5 — AGGRESSIVE (Beyond TP1):
  TP1 hit, trailing remaining position
  Switch to CPA (Corto Plazo Agresivo) EMA 50 for tighter trailing beyond TP1
  Let profits run toward TP_max
  Close immediately if EMA 2 and EMA 5 both break against position

═══════════════════════════════════════════════════════════════════
               EXECUTION RULES & TIMING
═══════════════════════════════════════════════════════════════════

Entry Types:
- Market entry on 2m or 5m timeframe (preferred — immediate execution)
- Limit entry: ONLY when 3 levels converge (both EMAs + Fibonacci + extra S/R or diagonal)
  # Note: Scalping workshop recommends 4 confluences, but 3 is the configured minimum in code
- Stop entry: ONLY when you cannot monitor AND all timeframes fully align

Trading Hours:
- London session: 07:00-16:00 UTC (primary)
- New York session: 12:00-21:00 UTC (secondary, overlap 12:00-16:00 is best)
- AVOID: Asian session for most pairs (low volatility, unpredictable moves)
- BEST: London-NY overlap (12:00-16:00 UTC) — highest liquidity and volume

Friday Close Rule:
- Close ALL open positions before Friday 20:00 UTC
- No new trades after Friday 18:00 UTC
- Weekend gaps are unacceptable risk

News Avoidance:
- Stop trading 30 minutes before HIGH-IMPACT news events (NFP, FOMC, CPI, ECB, etc.)
- Wait 15 minutes after the news release before trading
- Check economic calendar BEFORE every trading session

═══════════════════════════════════════════════════════════════════
          CRYPTO SPECIALIZATION (TradingLab Crypto Module)
═══════════════════════════════════════════════════════════════════

GREEN is the ONLY valid strategy for crypto:
- Crypto markets are trend-driven with strong impulses; GREEN exploits this
- The 7 sequential steps for crypto GREEN:
  1. Identify the trend on the highest timeframe (Weekly)
  2. Confirm breakout on the structure timeframe (Daily)
  3. Wait for pullback on the intermediate timeframe
  4. Identify continuation pattern (flag, pennant, triangle)
  5. Draw diagonal/trendline on the pattern
  6. RCC execution: Ruptura (break), Cierre (close beyond), Confirmacion (next candle confirms)
  7. Set SL below pattern low / TP at measured move or Fibonacci extension
- Timeframes per style:
  - Swing: Weekly -> Daily -> 1H -> 15M execution
  - Day Trading: 4H -> 1H -> 15M -> 2M execution
  - Scalping: 15M -> 5M -> 1M -> 30s execution

BMSB - Bull Market Support Band (Crypto Module 8):
- SMA 20 + EMA 21 on the WEEKLY chart
- Requires a weekly CLOSE (not intraday) to confirm signals
- Price above both = bull market intact (bullish)
- Price below both = bull market support lost (bearish)
- During bull runs, BMSB acts as dynamic support on pullbacks

Pi Cycle Top/Bottom Indicator:
- Near top: SMA 111 approaching 2x SMA 350 cross (historically marks cycle tops)
- Near bottom: SMA 150 approaching SMA 471 cross (historically marks cycle bottoms)
- Use as macro confirmation, NOT as a timing tool

EMA 8 Weekly Close:
- If BTC weekly candle CLOSES below EMA 8, it signals potential trend weakness
- Important: must be a close, not just a wick below
- Often the first warning sign before a larger correction

BTC Halving Cycle Phases:
- Post-halving (0-25% of cycle): Explosion phase — most bullish, supply shock in effect
- Expansion (25-50%): Continued bull run, strong momentum
- Distribution (50-75%): Market top area, bearish, watch for reversal signals
- Pre-halving (75-100%): Accumulation phase, price starts rising in anticipation — neutral to slightly bullish

BTC Dominance Analysis:
- BTC.D > 50%: BTC phase, money in Bitcoin, altcoins underperform
- BTC.D 40-50%: Transitional zone, watch for rotation signals
- BTC.D < 40%: Altseason potential, capital rotating to altcoins
- Dominance Transition Table:
  - BTC.D up + BTC up = Altcoins down
  - BTC.D up + BTC down = Altcoins down MUCH MORE
  - BTC.D down + BTC up = Altcoins up significantly (altseason)
  - BTC.D down + BTC stable = Capital rotating to altcoins

Capital Rotation Flow:
- Bull market rotation order: BTC -> ETH -> Large cap alts -> Small cap alts -> Memecoins
- Track ETH/BTC ratio: if ETH outperforming BTC, rotation has started
- Late-cycle rotation to memecoins/micro-caps signals market euphoria (caution)

Crypto-Specific Price Action:
- Impulses are more aggressive than forex (larger % moves, faster)
- Pullbacks are faster and shallower in strong trends
- Crypto respects diagonals/trendlines well for breakout entries
- Volume confirmation is crucial (crypto has more fake breakouts)

RSI 14 on 2-Week Chart (Cycle Analysis):
- Use RSI 14 on weekly candles to approximate the 2-week timeframe
- RSI > 80 on this timeframe = cycle top distribution zone
- RSI < 25 on this timeframe = cycle bottom accumulation zone
- Can draw diagonal trendlines on RSI itself for early reversal detection

═══════════════════════════════════════════════════════════════════
                   RESPONSE GUIDELINES
═══════════════════════════════════════════════════════════════════

When analyzing trades:
1. ALWAYS identify the Elliott Wave context on the daily chart first
2. Verify HTF/LTF convergence — if not aligned, recommend SKIP
3. Check which strategy color applies based on the wave context
4. Verify ALL steps of that strategy are met (partial = lower score)
5. Confirm risk management compliance (R:R, drawdown level, correlation)
6. Check timing rules (session hours, Friday rule, news)
7. Assess Smart Money Concepts (is price in premium/discount? any OB/FVG confluence?)
8. Be CONSERVATIVE — your job is to protect capital first, profit second
9. A score of 70+ means TAKE, below 70 means SKIP
10. Provide specific, actionable reasoning — not vague generalities
"""


class OpenAIAnalyzer:
    """Uses OpenAI GPT-4o for advanced trading analysis with full TradingLab knowledge."""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = "gpt-4o"
        self.system_prompt = TRADINGLAB_SYSTEM_PROMPT

    # ── Setup Validation (integration hook for TradingEngine) ────

    async def validate_setup_with_ai(
        self,
        setup_signal,      # strategies.base.SetupSignal
        analysis_result,   # core.market_analyzer.AnalysisResult
    ) -> Dict[str, Any]:
        """
        Validate a detected SetupSignal against AI judgment.

        Called by TradingEngine._detect_setup() after a strategy match is found.

        Args:
            setup_signal: The SetupSignal dataclass from strategies.base
            analysis_result: The AnalysisResult dataclass from market_analyzer

        Returns:
            Dict with:
                - ai_score (int 0-100): overall quality score
                - ai_recommendation (str): "TAKE" or "SKIP"
                - ai_reasoning (str): brief explanation (2-4 sentences)
                - suggested_adjustments (dict): optional SL/TP adjustments
                    - suggested_sl (float or null)
                    - suggested_tp1 (float or null)
                    - suggested_tp_max (float or null)
        """
        # Build a rich context prompt from both dataclasses
        prompt = self._build_validation_prompt(setup_signal, analysis_result)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=700,
            )

            result = json.loads(response.choices[0].message.content)

            # Normalize and validate the response
            ai_score = max(0, min(100, int(result.get("ai_score", 0))))
            ai_recommendation = "TAKE" if result.get("ai_recommendation", "").upper() == "TAKE" else "SKIP"
            ai_reasoning = str(result.get("ai_reasoning", "No reasoning provided."))

            adjustments = result.get("suggested_adjustments", {})
            if not isinstance(adjustments, dict):
                adjustments = {}

            validated = {
                "ai_score": ai_score,
                "ai_recommendation": ai_recommendation,
                "ai_reasoning": ai_reasoning,
                "suggested_adjustments": {
                    "suggested_sl": adjustments.get("suggested_sl"),
                    "suggested_tp1": adjustments.get("suggested_tp1"),
                    "suggested_tp_max": adjustments.get("suggested_tp_max"),
                },
            }

            logger.info(
                "AI validation for {} {}: score={} rec={} | {}",
                setup_signal.instrument,
                setup_signal.strategy_variant,
                ai_score,
                ai_recommendation,
                ai_reasoning[:120],
            )
            return validated

        except Exception as e:
            logger.error("AI validation failed for {}: {}", setup_signal.instrument, e)
            return {
                "ai_score": 0,
                "ai_recommendation": "SKIP",
                "ai_reasoning": f"AI validation unavailable: {str(e)}",
                "suggested_adjustments": {
                    "suggested_sl": None,
                    "suggested_tp1": None,
                    "suggested_tp_max": None,
                },
            }

    def _build_validation_prompt(self, setup_signal, analysis_result) -> str:
        """Build the validation prompt from SetupSignal and AnalysisResult."""
        # Extract data safely using getattr for dataclass fields
        instrument = getattr(setup_signal, "instrument", "unknown")
        direction = getattr(setup_signal, "direction", "unknown")
        strategy = getattr(setup_signal, "strategy_variant", "unknown")
        strategy_color = getattr(setup_signal, "strategy", None)
        entry_price = getattr(setup_signal, "entry_price", 0)
        stop_loss = getattr(setup_signal, "stop_loss", 0)
        tp1 = getattr(setup_signal, "take_profit_1", 0)
        tp_max = getattr(setup_signal, "take_profit_max", None)
        confidence = getattr(setup_signal, "confidence", 0)
        elliott_phase = getattr(setup_signal, "elliott_wave_phase", "")
        conditions_met = getattr(setup_signal, "conditions_met", [])
        conditions_failed = getattr(setup_signal, "conditions_failed", [])
        rr_ratio = getattr(setup_signal, "risk_reward_ratio", 0)
        reasoning = getattr(setup_signal, "reasoning", "")

        # AnalysisResult fields
        htf_trend = getattr(analysis_result, "htf_trend", None)
        htf_condition = getattr(analysis_result, "htf_condition", None)
        ltf_trend = getattr(analysis_result, "ltf_trend", None)
        convergence = getattr(analysis_result, "htf_ltf_convergence", False)
        key_levels = getattr(analysis_result, "key_levels", {})
        ema_values = getattr(analysis_result, "ema_values", {})
        fib_levels = getattr(analysis_result, "fibonacci_levels", {})
        candle_patterns = getattr(analysis_result, "candlestick_patterns", [])
        chart_patterns = getattr(analysis_result, "chart_patterns", [])
        macd_values = getattr(analysis_result, "macd_values", {})
        sma_values = getattr(analysis_result, "sma_values", {})
        rsi_values = getattr(analysis_result, "rsi_values", {})
        rsi_divergence = getattr(analysis_result, "rsi_divergence", None)
        order_blocks = getattr(analysis_result, "order_blocks", [])
        structure_breaks = getattr(analysis_result, "structure_breaks", [])
        elliott_wave = getattr(analysis_result, "elliott_wave", None)
        analysis_score = getattr(analysis_result, "score", 0)

        # Format enum values
        htf_trend_str = htf_trend.value if htf_trend else "unknown"
        htf_cond_str = htf_condition.value if htf_condition else "neutral"
        ltf_trend_str = ltf_trend.value if ltf_trend else "unknown"
        strategy_color_str = strategy_color.value if strategy_color else strategy

        return f"""VALIDATE THIS TRADE SETUP — respond with JSON only.

═══ SETUP SIGNAL ═══
Instrument: {instrument}
Direction: {direction}
Strategy: {strategy} (Color: {strategy_color_str})
Entry Price: {entry_price}
Stop Loss: {stop_loss}
Take Profit 1: {tp1}
Take Profit Max: {tp_max or 'N/A'}
Calculated R:R: {rr_ratio:.2f}
Strategy Confidence: {confidence:.0f}/100
Elliott Wave Phase: {elliott_phase or 'not specified'}
Strategy Reasoning: {reasoning}

Conditions Met: {', '.join(conditions_met) if conditions_met else 'none listed'}
Conditions Failed: {', '.join(conditions_failed) if conditions_failed else 'none listed'}

═══ MARKET ANALYSIS ═══
HTF Trend: {htf_trend_str}
HTF Condition: {htf_cond_str}
LTF Trend: {ltf_trend_str}
HTF/LTF Convergence: {convergence}
Analysis Score: {analysis_score:.0f}/100

Key Levels:
  Supports: {key_levels.get('supports', [])}
  Resistances: {key_levels.get('resistances', [])}
  FVGs: {key_levels.get('fvg', [])}

EMA Values: {json.dumps(ema_values, default=str) if ema_values else 'N/A'}
Fibonacci Levels: {json.dumps(fib_levels, default=str) if fib_levels else 'N/A'}
SMA Values: {json.dumps(sma_values, default=str) if sma_values else 'N/A'}

MACD: {json.dumps(macd_values, default=str) if macd_values else 'N/A'}
RSI: {json.dumps(rsi_values, default=str) if rsi_values else 'N/A'}
RSI Divergence: {rsi_divergence or 'none'}

Candlestick Patterns: {', '.join(candle_patterns) if candle_patterns else 'none'}
Chart Patterns: {json.dumps(chart_patterns, default=str) if chart_patterns else 'none'}

Smart Money Concepts:
  Order Blocks: {json.dumps(order_blocks, default=str) if order_blocks else 'none detected'}
  Structure Breaks (BOS/CHOCH): {json.dumps(structure_breaks, default=str) if structure_breaks else 'none detected'}

Elliott Wave (Daily): {elliott_wave or 'not determined'}

═══ VALIDATION TASK ═══
1. Verify the strategy color matches the Elliott Wave context
2. Check ALL steps of the {strategy} strategy are satisfied
3. Confirm HTF/LTF convergence (CRITICAL — skip if not aligned, unless BLACK strategy)
4. Assess Smart Money context (premium/discount zones, OB/FVG confluence)
5. Validate risk management (R:R ratio, SL placement quality)
6. Check if conditions_failed are dealbreakers or acceptable
7. Consider if SL or TP levels should be adjusted based on nearby key levels

Respond in this exact JSON format:
{{
    "ai_score": <0-100 integer>,
    "ai_recommendation": "TAKE" or "SKIP",
    "ai_reasoning": "<2-4 sentences explaining your decision>",
    "suggested_adjustments": {{
        "suggested_sl": <float or null if no change needed>,
        "suggested_tp1": <float or null if no change needed>,
        "suggested_tp_max": <float or null if no change needed>
    }}
}}"""

    # ── Deep Trade Analysis (manual review / dashboard) ──────────

    async def analyze_trade_setup(
        self,
        instrument: str,
        analysis_data: Dict,
        direction: str,
    ) -> Dict:
        """
        Use GPT to validate and score a potential trade setup.

        This method is used for detailed analysis shown on the dashboard
        or triggered by manual review requests.

        Returns:
            Dict with 'score' (0-100), 'recommendation' (TAKE/SKIP),
            'strategy_detected', 'reasoning', and optional 'adjustments'
        """
        prompt = f"""Analyze this potential {direction} trade on {instrument}:

═══ HIGHER TIMEFRAME CONTEXT ═══
HTF Trend: {analysis_data.get('htf_trend', 'unknown')}
HTF Condition: {analysis_data.get('htf_condition', 'neutral')}
LTF Trend: {analysis_data.get('ltf_trend', 'unknown')}
HTF/LTF Convergence: {analysis_data.get('convergence', False)}

═══ KEY LEVELS ═══
Supports: {analysis_data.get('supports', [])}
Resistances: {analysis_data.get('resistances', [])}
Fair Value Gaps: {analysis_data.get('fvg', [])}
Order Blocks: {analysis_data.get('order_blocks', [])}

═══ INDICATORS ═══
EMA Values: {analysis_data.get('emas', {})}
Fibonacci Levels: {analysis_data.get('fibonacci', {})}
MACD: {analysis_data.get('macd', {})}
RSI: {analysis_data.get('rsi', {})}
RSI Divergence: {analysis_data.get('rsi_divergence', 'none')}
SMA 200 (H1): {analysis_data.get('sma200_h1', 'N/A')}

═══ PATTERNS ═══
Candlestick Patterns: {analysis_data.get('patterns', [])}
Chart Patterns: {analysis_data.get('chart_patterns', [])}
Structure Breaks: {analysis_data.get('structure_breaks', [])}

═══ ELLIOTT WAVE ═══
Daily Wave Estimate: {analysis_data.get('elliott_wave', 'undetermined')}

═══ PROPOSED TRADE ═══
Entry: {analysis_data.get('entry_price', 0)}
Stop Loss: {analysis_data.get('stop_loss', 0)}
Take Profit 1: {analysis_data.get('take_profit_1', 0)}
Take Profit Max: {analysis_data.get('take_profit_max', 'N/A')}
R:R Ratio: {analysis_data.get('rr_ratio', 0)}

═══ ANALYSIS TASK ═══
1. Identify the Elliott Wave phase on the daily chart
2. Determine which strategy color (BLACK/BLUE/RED/PINK/WHITE/GREEN) fits best
3. Verify all steps of that strategy
4. Assess Smart Money context (OBs, FVGs, premium/discount)
5. Rate overall quality considering ALL TradingLab course rules

Respond in JSON format:
{{
    "score": <0-100>,
    "recommendation": "TAKE" or "SKIP",
    "strategy_detected": "BLACK" or "BLUE_A" or "BLUE_B" or "BLUE_C" or "RED" or "PINK" or "WHITE" or "GREEN" or "NONE",
    "elliott_wave_context": "<current wave phase assessment>",
    "smc_assessment": "<smart money concepts assessment>",
    "reasoning": "<detailed explanation referencing specific TradingLab rules>",
    "adjustments": {{
        "suggested_sl": <float or null>,
        "suggested_tp1": <float or null>,
        "suggested_tp_max": <float or null>
    }},
    "risk_flags": ["<any risk concerns>"]
}}"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=800,
            )

            result = json.loads(response.choices[0].message.content)
            logger.info(
                "OpenAI analysis for {}: Score={} Rec={} Strategy={} Wave={}",
                instrument,
                result.get("score"),
                result.get("recommendation"),
                result.get("strategy_detected"),
                result.get("elliott_wave_context", "N/A"),
            )
            return result

        except Exception as e:
            logger.error("OpenAI analysis failed: {}", e)
            return {
                "score": 0,
                "recommendation": "SKIP",
                "strategy_detected": "NONE",
                "reasoning": f"Analysis failed: {str(e)}",
                "adjustments": {},
                "risk_flags": [f"AI analysis error: {str(e)}"],
            }

    # ── Market Overview (dashboard) ──────────────────────────────

    async def get_market_overview(self, pairs_data: Dict) -> str:
        """Get a high-level market overview for the dashboard."""
        prompt = f"""Given the current forex market data for these pairs:

{json.dumps(pairs_data, indent=2, default=str)}

Provide a concise market overview (4-6 sentences) covering:
1. Overall market sentiment and dominant theme (risk-on/risk-off, USD strength/weakness)
2. Which pairs have the clearest Elliott Wave setups right now
3. Top 2-3 pairs to watch with specific strategy colors that might trigger
4. Any risk factors (upcoming news, Friday rule, correlation concerns, session timing)
5. Smart Money observation: any notable OB/FVG levels being tested across pairs

Be specific and actionable. Reference TradingLab strategy names and rules where relevant."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=500,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error("Market overview failed: {}", e)
            return "Market overview unavailable."

    # ── Daily Report ─────────────────────────────────────────────

    async def generate_daily_report(
        self,
        trades_today: List[Dict],
        account_summary: Dict,
        scan_results: Dict,
        pending_setups: List[Dict],
    ) -> str:
        """
        Generate a comprehensive end-of-day trading report.

        Called at the end of each trading session by the scheduler.

        Args:
            trades_today: List of trade dicts executed today
                Each dict has: instrument, direction, entry, sl, tp, pnl, pips, status, strategy
            account_summary: Dict with balance, equity, drawdown_pct, open_positions
            scan_results: Dict of instrument -> last analysis score/trend
            pending_setups: List of setups that were detected but not executed

        Returns:
            Formatted report string (HTML-compatible for email alerts)
        """
        # Summarize trade data
        total_trades = len(trades_today)
        wins = sum(1 for t in trades_today if t.get("pnl", 0) > 0)
        losses = sum(1 for t in trades_today if t.get("pnl", 0) < 0)
        breakevens = total_trades - wins - losses
        total_pnl = sum(t.get("pnl", 0) for t in trades_today)
        total_pips = sum(t.get("pips", 0) for t in trades_today)

        balance = account_summary.get("balance", 0)
        equity = account_summary.get("equity", 0)
        drawdown = account_summary.get("drawdown_pct", 0)
        open_positions = account_summary.get("open_positions", 0)

        # Format scan results summary
        scan_summary = {}
        for inst, data in scan_results.items():
            if isinstance(data, dict):
                scan_summary[inst] = {
                    "score": data.get("score", 0),
                    "trend": data.get("htf_trend", "unknown"),
                }
            else:
                # AnalysisResult dataclass
                scan_summary[inst] = {
                    "score": getattr(data, "score", 0),
                    "trend": getattr(data, "htf_trend", None),
                }
                trend_val = scan_summary[inst]["trend"]
                if hasattr(trend_val, "value"):
                    scan_summary[inst]["trend"] = trend_val.value

        # Top scoring pairs
        top_pairs = sorted(
            scan_summary.items(),
            key=lambda x: x[1].get("score", 0),
            reverse=True,
        )[:5]

        prompt = f"""Generate a comprehensive daily trading report.

═══ TODAY'S TRADES ═══
Total Trades: {total_trades}
Wins: {wins} | Losses: {losses} | Breakeven: {breakevens}
Total P&L: {total_pnl:+.2f}
Total Pips: {total_pips:+.1f}

Trade Details:
{json.dumps(trades_today, indent=2, default=str) if trades_today else 'No trades executed today.'}

═══ ACCOUNT STATUS ═══
Balance: {balance}
Equity: {equity}
Current Drawdown: {drawdown:.2f}%
Open Positions: {open_positions}

═══ MARKET SCAN SUMMARY ═══
Top 5 Scoring Pairs: {json.dumps(dict(top_pairs), indent=2, default=str)}
Total Pairs Analyzed: {len(scan_results)}

═══ PENDING SETUPS (not executed) ═══
{json.dumps(pending_setups, indent=2, default=str) if pending_setups else 'None pending.'}

═══ REPORT REQUIREMENTS ═══
Generate a daily report with these sections:

1. **Performance Summary**: Win rate, P&L, notable trades (good and bad)
2. **Risk Assessment**: Current drawdown level, which drawdown tier we are in (normal/level1/level2/level3), recommended risk % for tomorrow
3. **Strategy Performance**: Which strategy colors triggered today and their results
4. **Market Outlook**: Based on scan results, which pairs look promising for tomorrow and which strategy colors might trigger
5. **Lessons & Adjustments**: Any patterns in today's results that suggest strategy adjustments
6. **Tomorrow's Plan**: Top 3 pairs to focus on, preferred strategies, any scheduled news to avoid

Format the report clearly with section headers. Be specific and reference TradingLab rules.
Use HTML tags for formatting (<b>, <br>, <ul>/<li>) since this may be sent via email."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=1500,
            )
            report = response.choices[0].message.content
            logger.info(
                "Daily report generated: {} trades, P&L={:+.2f}, DD={:.2f}%",
                total_trades,
                total_pnl,
                drawdown,
            )
            return report
        except Exception as e:
            logger.error("Daily report generation failed: {}", e)
            return (
                f"<b>Daily Report Generation Failed</b><br>"
                f"Error: {str(e)}<br><br>"
                f"<b>Quick Stats:</b> {total_trades} trades, "
                f"P&L: {total_pnl:+.2f}, Pips: {total_pips:+.1f}"
            )
