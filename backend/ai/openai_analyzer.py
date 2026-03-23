"""
NeonTrade AI - OpenAI Integration
Uses GPT-4 for advanced market analysis and trade validation.

This module handles:
- Complex pattern interpretation
- Multi-factor trade scoring
- Risk assessment beyond simple rules
- Market context understanding
"""

from typing import Dict, Optional, List
from openai import AsyncOpenAI
from loguru import logger
from config import settings


class OpenAIAnalyzer:
    """Uses OpenAI GPT for advanced trading analysis."""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = "gpt-4o"

        # System prompt based on the Trading Plan methodology
        self.system_prompt = """You are NeonTrade AI, an expert forex day trading analyst.
You follow a conservative day trading approach with these core principles:

TRADING STYLE:
- Hybrid day trader, conservative approach
- 80% precision-based, systematic execution
- Focus on the daily chart advantage
- Short-term management with conservative targets

RISK MANAGEMENT:
- 1% risk per day trade, 0.5% scalping, 3% swing
- Maximum 7% total risk at any time
- Minimum R:R ratio of 0.80 to TP1
- Never trade before major news events
- Close all positions before Friday market close

ANALYSIS METHOD:
- Multi-timeframe: Weekly/Daily (HTF) → 4H/1H/15m/5m/2m (LTF)
- HTF/LTF convergence is critical
- Elliott Wave integration on daily chart
- EMA 2 and EMA 5 for day trading management
- Fibonacci retracement and extension levels
- Support/Resistance and Fair Value Gaps (FVG)

STRATEGIES (by priority):
- BLACK: Elliott Wave aligned in HTF
- BLUE: EMA 4H based targets
- RED: HTF aligned + Fibonacci extension targets
- GREEN: Trend continuation (Wave 1 and 3 daily)
- WHITE: Previous high/low of 4H impulse

EXECUTION:
- Prefer market entry on 2m or 5m timeframe
- Limit entry: requires convergence of 3 levels (Fibonacci + EMA 1H/4H + S/R/FVG)
- Stop entry: only when can't monitor and all timeframes align

You must be CONSERVATIVE. When in doubt, skip the trade.
Your primary purpose is NOT to lose money.
Always remove risk as soon as possible and secure profits quickly."""

    async def analyze_trade_setup(
        self,
        instrument: str,
        analysis_data: Dict,
        direction: str,
    ) -> Dict:
        """
        Use GPT to validate and score a potential trade setup.

        Returns:
            Dict with 'score' (0-100), 'recommendation' (TAKE/SKIP),
            'reasoning', and optional 'adjustments'
        """
        prompt = f"""Analyze this potential {direction} trade on {instrument}:

HTF Trend: {analysis_data.get('htf_trend', 'unknown')}
LTF Trend: {analysis_data.get('ltf_trend', 'unknown')}
HTF/LTF Convergence: {analysis_data.get('convergence', False)}
Market Condition: {analysis_data.get('condition', 'neutral')}

Key Levels:
- Supports: {analysis_data.get('supports', [])}
- Resistances: {analysis_data.get('resistances', [])}
- FVGs: {analysis_data.get('fvg', [])}

EMA Values: {analysis_data.get('emas', {})}
Fibonacci Levels: {analysis_data.get('fibonacci', {})}
Candlestick Patterns: {analysis_data.get('patterns', [])}

Proposed Entry: {analysis_data.get('entry_price', 0)}
Proposed SL: {analysis_data.get('stop_loss', 0)}
Proposed TP1: {analysis_data.get('take_profit_1', 0)}
R:R Ratio: {analysis_data.get('rr_ratio', 0)}

Should we take this trade? Respond in JSON format:
{{
    "score": <0-100>,
    "recommendation": "TAKE" or "SKIP",
    "strategy_detected": "BLACK/BLUE/RED/GREEN/WHITE or NONE",
    "reasoning": "<brief explanation>",
    "adjustments": {{
        "suggested_sl": <float or null>,
        "suggested_tp1": <float or null>
    }}
}}"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,  # Low temperature for consistency
                max_tokens=500,
            )

            import json
            result = json.loads(response.choices[0].message.content)
            logger.info(
                f"OpenAI analysis for {instrument}: "
                f"Score={result.get('score')} "
                f"Rec={result.get('recommendation')} "
                f"Strategy={result.get('strategy_detected')}"
            )
            return result

        except Exception as e:
            logger.error(f"OpenAI analysis failed: {e}")
            return {
                "score": 0,
                "recommendation": "SKIP",
                "reasoning": f"Analysis failed: {str(e)}",
            }

    async def get_market_overview(self, pairs_data: Dict) -> str:
        """Get a high-level market overview for the dashboard."""
        prompt = f"""Given the current forex market data for these pairs:

{pairs_data}

Provide a brief market overview (3-5 sentences) covering:
1. Overall market sentiment
2. Key opportunities
3. Pairs to watch
4. Any risks or cautions

Be concise and actionable."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=300,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Market overview failed: {e}")
            return "Market overview unavailable."
