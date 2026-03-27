"""
NeonTrade AI - Explanation Engine
Generates detailed human-readable explanations in Spanish
for every trading decision the system makes.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum


@dataclass
class TimeframeExplanation:
    """Explanation for what the system sees on a specific timeframe."""
    timeframe: str
    trend: str
    key_observations: List[str]
    levels: List[str]
    patterns: List[str]
    conclusion: str


@dataclass
class StrategyExplanation:
    """Complete explanation of a strategy signal or analysis."""
    instrument: str
    timestamp: str
    overall_bias: str  # "ALCISTA", "BAJISTA", "NEUTRAL"
    score: float
    timeframe_analysis: List[TimeframeExplanation]
    strategy_detected: Optional[str]  # e.g., "BLUE_A", "RED", "GREEN"
    strategy_steps: List[str]  # Step-by-step in Spanish
    conditions_met: List[str]
    conditions_missing: List[str]
    entry_explanation: Optional[str]
    sl_explanation: Optional[str]
    tp_explanation: Optional[str]
    risk_assessment: str
    recommendation: str  # Final recommendation in Spanish
    confidence_level: str  # "ALTA", "MEDIA", "BAJA"


class ExplanationEngine:
    """Generates detailed explanations for the frontend."""

    # Include trend descriptions in Spanish
    TREND_DESC = {
        "bullish": "alcista",
        "bearish": "bajista",
        "ranging": "lateral/rango",
    }

    CONDITION_DESC = {
        "overbought": "sobrecomprado",
        "oversold": "sobrevendido",
        "neutral": "neutral",
        "accelerating": "acelerando",
        "decelerating": "desacelerando",
    }

    STRATEGY_NAMES = {
        "BLUE": "BLUE - Cambio de tendencia en 1H",
        "BLUE_A": "BLUE A - Cambio de tendencia con doble suelo",
        "BLUE_B": "BLUE B - Cambio de tendencia estándar",
        "BLUE_C": "BLUE C - Cambio con rechazo de EMA 4H",
        "RED": "RED - Cambio de tendencia en 4H",
        "PINK": "PINK - Patrón correctivo de continuación",
        "WHITE": "WHITE - Continuación post-Pink",
        "BLACK": "BLACK - Anticipación contratendencia",
        "GREEN": "GREEN - Dirección semanal + patrón diario",
    }

    def generate_full_analysis(
        self,
        instrument: str,
        analysis_result,  # AnalysisResult from market_analyzer
        setup_signal=None,  # SetupSignal if one was found
    ) -> StrategyExplanation:
        """Generate a complete explanation for an instrument analysis."""
        from datetime import datetime, timezone

        tf_explanations = []

        # Weekly/Daily analysis
        htf_trend_es = self.TREND_DESC.get(analysis_result.htf_trend.value, "desconocido")
        htf_cond_es = self.CONDITION_DESC.get(analysis_result.htf_condition.value, "neutral")

        tf_explanations.append(TimeframeExplanation(
            timeframe="Diario (D)",
            trend=f"Tendencia {htf_trend_es}",
            key_observations=self._build_htf_observations(analysis_result, htf_trend_es, htf_cond_es),
            levels=self._format_key_levels(analysis_result.key_levels, "D"),
            patterns=[],
            conclusion=f"El gráfico diario muestra una tendencia {htf_trend_es} con condición {htf_cond_es}.",
        ))

        # 4H analysis — Mentoría: solo EMA 50 en H4
        ema_4h_50 = analysis_result.ema_values.get("EMA_H4_50", None)
        h4_obs = []
        if ema_4h_50 and analysis_result.current_price:
            if analysis_result.current_price > ema_4h_50:
                h4_obs.append("Precio por encima de EMA 50 en 4H (estructura alcista)")
            else:
                h4_obs.append("Precio por debajo de EMA 50 en 4H (estructura bajista)")

        tf_explanations.append(TimeframeExplanation(
            timeframe="4 Horas (H4)",
            trend=f"EMA 50: {'alcista' if ema_4h_50 and analysis_result.current_price and analysis_result.current_price > ema_4h_50 else 'bajista'}",
            key_observations=h4_obs,
            levels=[f"EMA 50 4H: {ema_4h_50:.5f}" if ema_4h_50 else "EMA 50 4H: no disponible"],
            patterns=[],
            conclusion=self._build_4h_conclusion(analysis_result),
        ))

        # 1H analysis
        ltf_trend_es = self.TREND_DESC.get(analysis_result.ltf_trend.value, "desconocido")
        ema_h1_50 = analysis_result.ema_values.get("EMA_H1_50", None)

        tf_explanations.append(TimeframeExplanation(
            timeframe="1 Hora (H1)",
            trend=f"Tendencia {ltf_trend_es}",
            key_observations=self._build_ltf_observations(analysis_result, ltf_trend_es),
            levels=[
                f"EMA 50 1H: {ema_h1_50:.5f}" if ema_h1_50 else "EMA 50 1H: no disponible",
            ],
            patterns=analysis_result.candlestick_patterns,
            conclusion=f"El gráfico horario muestra tendencia {ltf_trend_es}.",
        ))

        # Convergence check
        convergence = analysis_result.htf_ltf_convergence
        overall_bias = "ALCISTA" if analysis_result.htf_trend.value == "bullish" else (
            "BAJISTA" if analysis_result.htf_trend.value == "bearish" else "NEUTRAL"
        )

        # Strategy detection explanation
        conditions_met = []
        conditions_missing = []

        if convergence:
            conditions_met.append("Convergencia HTF/LTF confirmada (ambas temporalidades apuntan en la misma dirección)")
        else:
            conditions_missing.append("No hay convergencia HTF/LTF (las temporalidades no están alineadas)")

        if analysis_result.score >= 65:
            conditions_met.append(f"Score de calidad: {analysis_result.score:.0f}/100 (por encima del umbral de 65)")
        else:
            conditions_missing.append(f"Score de calidad insuficiente: {analysis_result.score:.0f}/100 (necesita >= 65)")

        if analysis_result.key_levels.get("supports"):
            conditions_met.append(f"Niveles de soporte identificados: {len(analysis_result.key_levels['supports'])}")
        if analysis_result.key_levels.get("resistances"):
            conditions_met.append(f"Niveles de resistencia identificados: {len(analysis_result.key_levels['resistances'])}")

        if analysis_result.fibonacci_levels:
            conditions_met.append("Niveles de Fibonacci calculados")

        if analysis_result.candlestick_patterns:
            patterns_str = ", ".join(analysis_result.candlestick_patterns)
            conditions_met.append(f"Patrones de velas detectados: {patterns_str}")

        # Strategy-specific explanation
        strategy_detected = None
        strategy_steps = []
        entry_explanation = None
        sl_explanation = None
        tp_explanation = None

        if setup_signal:
            strategy_detected = setup_signal.strategy.value
            strategy_steps = self._build_strategy_steps(setup_signal)
            entry_explanation = self._build_entry_explanation(setup_signal)
            sl_explanation = self._build_sl_explanation(setup_signal)
            tp_explanation = self._build_tp_explanation(setup_signal)

        # Risk assessment
        risk_assessment = self._build_risk_assessment(analysis_result, setup_signal)

        # Recommendation
        recommendation = self._build_recommendation(
            analysis_result, setup_signal, convergence
        )

        # Confidence level
        if analysis_result.score >= 80 and convergence:
            confidence_level = "ALTA"
        elif analysis_result.score >= 65:
            confidence_level = "MEDIA"
        else:
            confidence_level = "BAJA"

        return StrategyExplanation(
            instrument=instrument,
            timestamp=datetime.now(timezone.utc).isoformat(),
            overall_bias=overall_bias,
            score=analysis_result.score,
            timeframe_analysis=tf_explanations,
            strategy_detected=strategy_detected,
            strategy_steps=strategy_steps,
            conditions_met=conditions_met,
            conditions_missing=conditions_missing,
            entry_explanation=entry_explanation,
            sl_explanation=sl_explanation,
            tp_explanation=tp_explanation,
            risk_assessment=risk_assessment,
            recommendation=recommendation,
            confidence_level=confidence_level,
        )

    def _build_htf_observations(self, analysis, trend_es, cond_es):
        obs = []
        obs.append(f"Tendencia principal: {trend_es}")
        obs.append(f"Condición del mercado: {cond_es}")

        supports = analysis.key_levels.get("supports", [])
        resistances = analysis.key_levels.get("resistances", [])
        if supports:
            obs.append(f"Soportes diarios clave: {', '.join(f'{s:.5f}' for s in supports[-3:])}")
        if resistances:
            obs.append(f"Resistencias diarias clave: {', '.join(f'{r:.5f}' for r in resistances[-3:])}")

        if analysis.fibonacci_levels:
            fib_382 = analysis.fibonacci_levels.get("0.382")
            fib_618 = analysis.fibonacci_levels.get("0.618")
            if fib_382 and fib_618:
                obs.append(f"Zona Fibonacci: 0.382={fib_382:.5f} | 0.618={fib_618:.5f}")

        return obs

    def _format_key_levels(self, key_levels, tf):
        levels = []
        for s in key_levels.get("supports", [])[-3:]:
            levels.append(f"Soporte {tf}: {s:.5f}")
        for r in key_levels.get("resistances", [])[-3:]:
            levels.append(f"Resistencia {tf}: {r:.5f}")
        return levels

    def _build_4h_conclusion(self, analysis):
        ema_4h_50 = analysis.ema_values.get("EMA_H4_50")
        if ema_4h_50:
            return f"EMA 50 de 4H en {ema_4h_50:.5f}. Este nivel es clave para estrategias RED y BLACK."
        return "Datos de 4H limitados."

    def _build_ltf_observations(self, analysis, trend_es):
        obs = [f"Tendencia LTF: {trend_es}"]
        if analysis.htf_ltf_convergence:
            obs.append("Las temporalidades superiores e inferiores convergen en la misma dirección")
        else:
            obs.append("Las temporalidades NO convergen - precaución necesaria")
        if analysis.candlestick_patterns:
            obs.append(f"Patrones de velas: {', '.join(analysis.candlestick_patterns)}")
        return obs

    def _build_strategy_steps(self, signal):
        color = signal.strategy.value
        steps = {
            "BLUE": [
                "1. Nivel de soporte/resistencia en gráfico diario identificado",
                "2. El precio atacó el nivel y desaceleró",
                "3. Cambio de tendencia confirmado en 1H (EMA 50 1H rota + máximos crecientes)",
                "4. Pullback hasta EMA 50 1H + niveles de Fibonacci",
                "5. Desaceleración y giro en 1H",
                "6. Ruptura + cierre + confirmación en 5M",
                "7. SL en Fibonacci 0.618 / mínimo anterior | TP en EMA 50 4H",
            ],
            "RED": [
                "1. Nivel de soporte/resistencia en gráfico diario identificado",
                "2. El precio atacó el nivel y desaceleró",
                "3. Cambio de tendencia confirmado en 4H (EMA 50 4H rota)",
                "4. Pullback en 1H hasta EMA 50 1H + EMA 50 4H + Fibonacci",
                "5. Desaceleración en 1H",
                "6. Ruptura + cierre + confirmación en 5M",
                "7. SL debajo de EMA 50 4H | TP en máximo/mínimo anterior o extensión Fibonacci",
            ],
            "PINK": [
                "1. Nivel de soporte/resistencia diario O tendencia desarrollada",
                "2. Tendencia alineada en todas las temporalidades",
                "3. Pullback hasta EMA 50 4H (la EMA 50 4H NO se rompe - si se rompiera seria RED, no PINK)",
                "4. En 1H: EMA 50 rota en forma de patrón correctivo (cuña/triángulo/canal)",
                "5. Ejecución al final del patrón cuando 5M rompe",
                "6. SL debajo del mínimo anterior | TP en máximo anterior",
            ],
            "WHITE": [
                "1. Venimos de una configuración PINK completada",
                "2. Impulso + pullback formado en 1H tras la Pink",
                "3. Pullback hasta EMA 50 1H + Fibonacci",
                "4. Desaceleración/giro (mismos criterios que Blue)",
                "5. Ruptura + cierre + confirmación en 5M",
                "6. SL encima del máximo anterior | TP en nivel de la Pink",
            ],
            "BLACK": [
                "1. Nivel de soporte/resistencia diario (OBLIGATORIO)",
                "2. Gráfico diario ataca el nivel con sobrecompra/sobreventa",
                "3. Desaceleración/giro en diario",
                "4. Verificar que EMA 50 1H NO actue como soporte/resistencia dinamica (si lo hace, no hay Black)",
                "5. Sobrecompra clara en 4H (precio lejos de EMA 50 4H) + consolidación",
                "6. Patrón de reversión en 1H (triángulo/cuña, NO canal). RSI divergencia",
                "7. Esperar patrón completo + candlestick de reversión + ruptura en 5M",
                "8. SL encima del máximo anterior | TP en EMA 50 4H | R:R mínimo 2:1",
            ],
            "GREEN": [
                "1. Dirección/tendencia semanal identificada",
                "2. Corrección semanal forma patrón en gráfico diario",
                "3. Niveles de soporte: Fibonacci + S/R + medias móviles",
                "4. Cambio de tendencia en 1H al final del patrón (diagonal/HCH)",
                "5. Copiar nivel de 1H a 15M y ejecutar en primera ruptura + confirmación",
                "6. SL debajo del mínimo de 1H (ajustado) | TP en máximo/mínimo diario anterior",
            ],
        }
        return steps.get(color, [f"Estrategia {color} detectada"])

    def _build_entry_explanation(self, signal):
        return (
            f"Entrada {signal.direction} en {signal.instrument} "
            f"a {signal.entry_price:.5f}. "
            f"Estrategia: {self.STRATEGY_NAMES.get(signal.strategy.value, signal.strategy.value)}. "
            f"Confianza: {signal.confidence:.0f}%."
        )

    def _build_sl_explanation(self, signal):
        distance = abs(signal.entry_price - signal.stop_loss)
        return (
            f"Stop Loss en {signal.stop_loss:.5f} "
            f"(distancia: {distance:.5f} desde entrada). "
            f"Protege el mínimo/máximo anterior según las reglas de la estrategia."
        )

    def _build_tp_explanation(self, signal):
        parts = [f"Take Profit 1 en {signal.take_profit_1:.5f}"]
        if signal.take_profit_max:
            parts.append(f"Take Profit máximo en {signal.take_profit_max:.5f}")
        rr = abs(signal.take_profit_1 - signal.entry_price) / max(
            abs(signal.entry_price - signal.stop_loss), 0.00001
        )
        parts.append(f"Ratio Riesgo:Beneficio = 1:{rr:.2f}")
        return ". ".join(parts) + "."

    def _build_risk_assessment(self, analysis, signal):
        if not signal:
            if analysis.score < 50:
                return "Riesgo ALTO: Score bajo, no se recomienda operar este par en este momento."
            if not analysis.htf_ltf_convergence:
                return "Riesgo MEDIO-ALTO: No hay convergencia entre temporalidades. Esperar mejor configuración."
            return "Riesgo MEDIO: Análisis en progreso, esperando señal de entrada."

        rr = abs(signal.take_profit_1 - signal.entry_price) / max(
            abs(signal.entry_price - signal.stop_loss), 0.00001
        )
        if rr >= 2.0 and signal.confidence >= 75:
            return f"Riesgo BAJO: R:R favorable ({rr:.1f}:1) con alta confianza ({signal.confidence:.0f}%)."
        if rr >= 1.0:
            return f"Riesgo MEDIO: R:R aceptable ({rr:.1f}:1) con confianza {signal.confidence:.0f}%."
        return f"Riesgo ALTO: R:R bajo ({rr:.1f}:1). Considerar no operar."

    def _build_recommendation(self, analysis, signal, convergence):
        if signal and signal.confidence >= 70 and convergence:
            return (
                f"RECOMENDACIÓN: Configuración {signal.strategy.value} detectada con buena confluencia. "
                f"Se recomienda ejecutar con gestión de riesgo apropiada."
            )
        if signal and signal.confidence >= 50:
            return (
                f"RECOMENDACIÓN: Configuración {signal.strategy.value} detectada pero con confluencia moderada. "
                f"Operar con precaución y tamaño de posición reducido."
            )
        if analysis.score >= 65 and convergence:
            return "RECOMENDACIÓN: Buena estructura pero sin señal de entrada clara aún. Monitorear."
        return "RECOMENDACIÓN: No se recomienda operar este par en este momento. Esperar mejor configuración."

    def format_for_notification(self, explanation: StrategyExplanation) -> str:
        """Format a short version for push notifications."""
        if explanation.strategy_detected:
            return (
                f"{'🟢' if explanation.overall_bias == 'ALCISTA' else '🔴'} "
                f"{explanation.instrument}: "
                f"Estrategia {explanation.strategy_detected} detectada | "
                f"Score: {explanation.score:.0f} | "
                f"Confianza: {explanation.confidence_level}"
            )
        return (
            f"📊 {explanation.instrument}: "
            f"Tendencia {explanation.overall_bias.lower()} | "
            f"Score: {explanation.score:.0f} | "
            f"Sin señal de entrada"
        )
