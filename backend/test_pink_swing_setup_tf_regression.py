import sys
from unittest.mock import patch

sys.path.insert(0, ".")

from strategies.base import PinkStrategy
from core.market_analyzer import AnalysisResult, Trend, MarketCondition


def test_pink_swing_uses_daily_history_for_setup_break():
    with patch("strategies.base.settings") as mock_s:
        from config import Settings

        real = Settings()
        for attr in dir(real):
            if attr.startswith("_"):
                continue
            try:
                setattr(mock_s, attr, getattr(real, attr))
            except Exception:
                pass
        mock_s.trading_style = "swing"

        analysis = AnalysisResult(
            instrument="EUR_USD",
            htf_trend=Trend.BULLISH,
            htf_condition=MarketCondition.NEUTRAL,
            ltf_trend=Trend.BULLISH,
            htf_ltf_convergence=True,
            key_levels={
                "supports": [1.0800, 1.0850, 1.0900],
                "resistances": [1.1100, 1.1200, 1.1300],
            },
            ema_values={
                "EMA_D_50": 1.1000,
                "EMA_W_50": 1.0900,
                "EMA_H1_50": 1.0950,
                "EMA_M5_50": 1.0980,
                "EMA_M5_20": 1.0985,
                "EMA_W_8": 1.0700,
            },
            fibonacci_levels={"0.382": 1.0960, "0.500": 1.0950, "0.618": 1.0940},
            candlestick_patterns=["DOJI", "HAMMER"],
            chart_patterns=[{"type": "triangle", "timeframe": "D", "completion_pct": 0.85}],
            current_price=1.1005,
            last_candles={
                "D": [
                    {"open": 1.1030, "high": 1.1040, "low": 1.1010, "close": 1.1020},
                    {"open": 1.1020, "high": 1.1030, "low": 1.0980, "close": 1.0990},
                    {"open": 1.0990, "high": 1.1000, "low": 1.0970, "close": 1.0985},
                    {"open": 1.0985, "high": 1.0995, "low": 1.0965, "close": 1.0975},
                    {"open": 1.0975, "high": 1.1015, "low": 1.0970, "close": 1.1005},
                ],
                "H1": [
                    {"open": 1.1000, "high": 1.1010, "low": 1.0995, "close": 1.1002},
                    {"open": 1.1002, "high": 1.1012, "low": 1.0998, "close": 1.1006},
                    {"open": 1.1006, "high": 1.1016, "low": 1.1000, "close": 1.1008},
                ],
            },
            swing_highs=[1.1080, 1.1120],
            swing_lows=[1.0920, 1.0940],
        )

        ok, _, _, failed = PinkStrategy().check_htf_conditions(analysis)
        assert ok, f"PINK swing should validate from daily history, failed: {failed}"
