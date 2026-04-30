from api.routes import (
    _build_exam_chart_analysis,
    _aggregate_monthly_candles,
    _build_exam_html,
    _exam_required_context_timeframes,
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
    assert normalized == ["M", "W", "D", "H4"]


def test_exam_required_chart_timeframes_follow_operativa_sequence():
    assert _exam_required_context_timeframes("day_trading") == ["D", "H4", "H1", "M15"]
    assert _exam_required_context_timeframes("swing") == ["M", "W", "D", "H4"]
    assert _exam_required_context_timeframes("scalping") == ["H1", "M15", "M5", "M1"]


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


def test_build_exam_chart_analysis_describes_levels_and_diagonal():
    candles = []
    prices = [100, 99, 101, 100, 102, 101, 103, 102, 104, 103, 105, 104, 106, 105]
    for idx, close in enumerate(prices):
        candles.append(
            {
                "time": f"2026-04-01T{idx:02d}:00:00Z",
                "open": close - 0.4,
                "high": close + 0.8,
                "low": close - 0.8,
                "close": close,
                "volume": 100 + idx,
            }
        )

    analysis = _build_exam_chart_analysis(
        candles,
        instrument="UK100_GBP",
        timeframe_code="H1",
        role_label="Armado del setup",
        direction="BUY",
        entry_price=104.5,
        current_price=106.0,
    )

    assert analysis["candles"]
    assert analysis["annotations"]["overlay_levels"]
    assert analysis["annotations"]["ema_overlays"]
    assert "soporte" in analysis["explanation"].lower()
    assert "ejecución quedó anclada" in analysis["explanation"].lower()


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
                    {
                        "label": "Gráfico Diario",
                        "b64": "ZmFrZQ==",
                        "role": "Contexto direccional",
                        "explanation": "Acá se vio el sesgo principal del día y una zona de soporte que sostuvo la idea del trade.",
                    },
                    {
                        "label": "Gráfico 4 Horas",
                        "b64": "ZmFrZQ==",
                        "role": "Confirmación estructural",
                        "explanation": "Acá se vio la diagonal que contenía el precio y la resistencia desde donde se validó la presión vendedora previa.",
                    },
                    {
                        "label": "Gráfico 1 Hora",
                        "b64": "ZmFrZQ==",
                        "role": "Armado del setup",
                        "explanation": "Acá se vio el armado del setup con una diagonal de soporte y la ubicación precisa del pullback.",
                    },
                    {
                        "label": "Gráfico 15 Minutos",
                        "b64": "ZmFrZQ==",
                        "role": "Ejecución",
                        "explanation": "Acá se vio la ejecución exacta del trade, con soporte, resistencia y la zona donde entró la orden.",
                    },
                ],
                "timeframes_used": ["D", "H4", "H1", "M15"],
                "exam_chart_plan": [
                    {"code": "D", "role": "Contexto direccional"},
                    {"code": "H4", "role": "Confirmación estructural"},
                    {"code": "H1", "role": "Armado del setup"},
                    {"code": "M15", "role": "Ejecución"},
                ],
                "mentoria_timeframe_plan": {
                    "directional": "D",
                    "confirmation": "H4",
                    "setup": "H1",
                    "execution": "M15",
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
    assert "Gráfico Diario" in html
    assert "Gráfico 4 Horas" in html
    assert "Gráfico 1 Hora" in html
    assert "Gráfico 15 Minutos" in html
    assert "ANÁLISIS MULTI-TIMEFRAME" in html
    assert "Ejecución" in html
    assert "TEMPORALIDADES" in html
