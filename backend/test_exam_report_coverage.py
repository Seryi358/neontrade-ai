from api.routes import (
    _aggregate_monthly_candles,
    _build_exam_html,
    _infer_exam_operativa,
    _normalize_exam_direction,
    _normalize_exam_timeframes,
)


def test_infer_exam_operativa_from_timeframes():
    trade = {
        "instrument": "EUR_USD",
        "timeframes_used": ["H1", "M15", "M5", "M1"],
        "trading_style": "",
    }
    style_key, label = _infer_exam_operativa(trade)
    assert style_key == "scalping"
    assert label == "Scalping"


def test_normalize_exam_timeframes_falls_back_to_mentoria_plan():
    normalized = _normalize_exam_timeframes([], "swing")
    assert normalized == ["M", "W", "D", "H1"]


def test_aggregate_monthly_candles_from_weekly_series():
    weekly = [
        {"time": "2026-01-03T00:00:00Z", "open": 10, "high": 12, "low": 9, "close": 11, "volume": 10},
        {"time": "2026-01-10T00:00:00Z", "open": 11, "high": 13, "low": 10, "close": 12, "volume": 20},
        {"time": "2026-02-07T00:00:00Z", "open": 12, "high": 14, "low": 11, "close": 13, "volume": 30},
    ]

    monthly = _aggregate_monthly_candles(weekly)

    assert len(monthly) == 2
    assert monthly[0]["open"] == 10
    assert monthly[0]["high"] == 13
    assert monthly[0]["low"] == 9
    assert monthly[0]["close"] == 12
    assert monthly[0]["volume"] == 30
    assert monthly[1]["close"] == 13


def test_build_exam_html_renders_required_exam_fields():
    html = _build_exam_html(
        [
            {
                "instrument": "UK100_GBP",
                "activo": "UK100_GBP",
                "operativa": "Day Trading",
                "direction": "BUY",
                "direction_label": _normalize_exam_direction("BUY"),
                "strategy": "BLACK",
                "strategy_variant": "",
                "entry_price": 100.0,
                "exit_price": 101.0,
                "stop_loss": 99.0,
                "take_profit": 104.0,
                "pnl": 12.34,
                "status": "closed_tp1",
                "opened_at": "2026-04-29T12:00:00Z",
                "closed_at": "2026-04-29T13:00:00Z",
                "units": 1,
                "risk_reward_ratio": 4.0,
                "rr_achieved": 1.0,
                "risk_dollars": 1.0,
                "confidence": 75,
                "reasoning": "Entrada valida por contexto de giro.",
                "trade_summary": "Resumen del trade.",
                "management_notes": "Gestion correcta.",
                "screenshots_b64": [{"label": "Open", "b64": "ZmFrZQ=="}],
                "context_charts_b64": [
                    {"label": "Gráfico Mensual", "b64": "ZmFrZQ=="},
                    {"label": "Gráfico Semanal", "b64": "ZmFrZQ=="},
                ],
                "timeframes_used": ["M", "W", "D", "H4", "H1", "M5"],
                "mentoria_timeframe_plan": {
                    "monthly": "M",
                    "weekly": "W",
                    "directional": "D",
                    "confirmation": "H4",
                    "setup": "H1",
                    "execution": "M5",
                },
                "htf_analysis": {"trend": "bearish", "condition": "overbought", "score": 75},
                "ltf_analysis": {"trend": "bullish", "convergence": True},
                "ai_analysis": "",
                "asr_completed": False,
                "asr_lessons": "",
                "asr_would_enter_again": None,
            }
        ]
    )

    assert "OPERATIVA" in html
    assert "ESTRATEGIA" in html
    assert "DIRECCIÓN" in html
    assert "ACTIVO" in html
    assert "Day Trading" in html
    assert "Long" in html
    assert "Gráfico Mensual" in html
    assert "Gráfico Semanal" in html
    assert "TEMPORALIDADES" in html
