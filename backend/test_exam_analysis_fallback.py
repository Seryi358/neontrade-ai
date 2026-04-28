from api.routes import _infer_exam_analysis_from_text


def test_infer_exam_analysis_from_reasoning_text():
    trade = {
        "reasoning": (
            "Instrumento: UK100_GBP\n"
            "Dirección: COMPRA\n"
            "Score de análisis: 75/100\n"
            "Sesgo general: BAJISTA\n"
            "Confianza: MEDIA\n"
            "Condiciones cumplidas:\n"
            "  - Convergencia HTF/LTF confirmada (ambas temporalidades apuntan en la misma dirección)\n"
        )
    }

    inferred = _infer_exam_analysis_from_text(trade)

    assert inferred is not None
    assert inferred["htf_analysis"]["trend"] == "bearish"
    assert inferred["htf_analysis"]["score"] == 75
    assert inferred["ltf_analysis"]["trend"] == "bearish"
    assert inferred["ltf_analysis"]["convergence"] is True


def test_infer_exam_analysis_returns_none_without_text():
    assert _infer_exam_analysis_from_text({}) is None
