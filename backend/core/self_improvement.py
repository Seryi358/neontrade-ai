"""Atlas — Self-Improvement Loop (MVP).

Closes the post-trade learning loop. Right now the only feature is
``AutoASRGenerator`` which uses GPT-4o (vision-capable) to fill in the
journal's ASR (Auto Self Review) fields after a trade closes. The fields
already exist in ``trade_journal.py`` but were always left blank because the
mentorship's ASR review is a human exercise. Auto-fill turns every closed
trade into structured feedback that the upcoming auto-tuning stage will
consume.

Design notes (full spec in ``/tmp/self_improvement_design.md``):

- This is a *thin orchestrator* — reuses ``OpenAIAnalyzer.client`` and the
  existing ``trade_journal.update_asr`` method. No new tables, no broker
  calls, no scheduling logic. Add those in later iterations.
- Fully opt-in via ``settings.auto_asr_enabled`` (default False) so this
  module never costs Sergio money or affects trading until he enables it.
- Fire-and-forget from ``trading_engine._on_position_closed``: an LLM
  failure must never propagate into the close pipeline.
- Vision is optional. When the close screenshot exists and is readable, it
  is attached as a base64 ``image_url`` part. Otherwise a text-only call.
- Output is a strict JSON object matching the ASR field set; coerced before
  hitting ``update_asr`` so the journal never receives malformed values.

Mentorship anchor (Alex Ruiz, ASR lesson):
    "correcto o incorrecto no viene relacionado con el resultado del trade,
     viene relacionado con vuestro plan de trading"

The post-mortem prompt enforces that bias: the model evaluates against the
TradingLab plan, not against PnL.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from loguru import logger


# Allowed values for asr_error_type per the ASR taxonomy in trade_journal.
_ALLOWED_ERROR_TYPES = {"PERCEPTION", "TECHNICAL", "ROUTINE", "EMOTIONAL", None}


ASR_POSTMORTEM_PROMPT = """Eres un analista experto del curso TradingLab evaluando un trade ya cerrado.
Tu tarea es completar el ASR (Auto Self Review) del trade, evaluando la EJECUCIÓN
contra el PLAN, NO contra el resultado.

Instrucciones (Alex Ruiz):
- "correcto o incorrecto no viene relacionado con el resultado del trade,
   viene relacionado con vuestro plan de trading"
- Un trade puede haber perdido dinero pero tener ejecución correcta (todo el plan
  cumplido, simplemente la probabilidad jugó en contra). De igual forma un trade
  ganador puede tener ejecución incorrecta (suerte, no plan).
- Si NO puedes evaluar un campo con la información disponible, devuelve null
  para ese campo (preferible a inventar).
- error_type: PERCEPTION (leí mal el gráfico), TECHNICAL (apliqué mal una regla),
  ROUTINE (no seguí mi rutina/checklist), EMOTIONAL (revenge/FOMO/miedo).

Devuelve EXACTAMENTE este JSON (sin markdown, sin texto extra):
{
  "asr_htf_correct": <bool|null>,
  "asr_ltf_correct": <bool|null>,
  "asr_strategy_correct": <bool|null>,
  "asr_sl_correct": <bool|null>,
  "asr_tp_correct": <bool|null>,
  "asr_management_correct": <bool|null>,
  "asr_would_enter_again": <bool|null>,
  "asr_lessons": "<string en español, 1-3 frases>",
  "asr_error_type": "<PERCEPTION|TECHNICAL|ROUTINE|EMOTIONAL|null>"
}

CONTEXTO DEL TRADE:
{trade_context}
"""


@dataclass
class AutoASRResult:
    trade_id: str
    success: bool
    fields_filled: int
    vision_used: bool
    raw_response: str
    error: Optional[str] = None


class AutoASRGenerator:
    """Vision-LLM-powered auto-fill of ASR fields after a trade closes."""

    # gpt-4o supports vision; tweak via settings.auto_asr_model if needed.
    DEFAULT_MODEL = "gpt-4o"

    def __init__(self, openai_client, trade_journal, model: Optional[str] = None):
        self.client = openai_client
        self.journal = trade_journal
        self.model = model or self.DEFAULT_MODEL

    async def generate_asr(
        self,
        trade_record: Dict[str, Any],
        screenshot_path: Optional[str] = None,
    ) -> AutoASRResult:
        """Generate ASR for a single trade. Best-effort; never raises."""
        trade_id = trade_record.get("trade_id", "unknown")
        try:
            user_text = ASR_POSTMORTEM_PROMPT.format(
                trade_context=self._format_trade_context(trade_record),
            )
            messages, vision_used = self._build_messages(user_text, screenshot_path)

            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=600,
            )
            raw = (resp.choices[0].message.content or "").strip()
            data = json.loads(raw)
            asr_fields = self._coerce_asr(data)

            applied = self.journal.update_asr(
                trade_id=trade_id,
                htf_correct=asr_fields.get("asr_htf_correct"),
                ltf_correct=asr_fields.get("asr_ltf_correct"),
                strategy_correct=asr_fields.get("asr_strategy_correct"),
                sl_correct=asr_fields.get("asr_sl_correct"),
                tp_correct=asr_fields.get("asr_tp_correct"),
                management_correct=asr_fields.get("asr_management_correct"),
                would_enter_again=asr_fields.get("asr_would_enter_again"),
                lessons=asr_fields.get("asr_lessons"),
                error_type=asr_fields.get("asr_error_type"),
            )
            filled = sum(1 for v in asr_fields.values() if v is not None)
            logger.info(
                f"AutoASR {trade_id}: applied={applied} filled={filled}/{len(asr_fields)} "
                f"vision={vision_used} model={self.model}"
            )
            return AutoASRResult(
                trade_id=trade_id,
                success=applied,
                fields_filled=filled,
                vision_used=vision_used,
                raw_response=raw,
            )
        except Exception as exc:
            logger.warning(f"AutoASR failed for {trade_id}: {exc}")
            return AutoASRResult(
                trade_id=trade_id,
                success=False,
                fields_filled=0,
                vision_used=False,
                raw_response="",
                error=str(exc),
            )

    def _build_messages(self, user_text: str, screenshot_path: Optional[str]):
        """Build the chat.completions message list, optionally attaching a
        screenshot via the vision API pattern."""
        if screenshot_path and os.path.isfile(screenshot_path):
            try:
                with open(screenshot_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
                data_url = f"data:image/png;base64,{b64}"
                return [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_text},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    },
                ], True
            except Exception as e:
                logger.debug(
                    f"AutoASR could not attach screenshot {screenshot_path}: {e}"
                )
        return [{"role": "user", "content": user_text}], False

    @staticmethod
    def _format_trade_context(t: Dict[str, Any]) -> str:
        """Compact human-readable summary the model uses to grade execution."""
        keys = [
            "instrument", "direction", "strategy", "entry_price", "exit_price",
            "sl", "tp", "rr_achieved", "pnl_dollars", "pnl_pct", "result",
            "balance_after", "drawdown_pct", "duration_minutes",
            "trading_style", "timeframes_used",
        ]
        lines = []
        for k in keys:
            if k in t and t[k] not in (None, "", []):
                lines.append(f"- {k}: {t[k]}")
        # Include any free-text fields the human filled
        for note_key in (
            "trade_summary", "management_notes",
            "emotional_notes_pre", "emotional_notes_during", "emotional_notes_post",
        ):
            v = t.get(note_key)
            if v:
                lines.append(f"- {note_key}: {v}")
        return "\n".join(lines) if lines else "(sin campos legibles)"

    @staticmethod
    def _coerce_asr(data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate the LLM JSON against expected types so we never feed
        garbage into ``update_asr``."""
        def _b(v):
            if v is None or isinstance(v, bool):
                return v
            if isinstance(v, (int, float)):
                return bool(v)
            if isinstance(v, str):
                low = v.strip().lower()
                if low in ("true", "yes", "si", "sí", "1"):
                    return True
                if low in ("false", "no", "0"):
                    return False
            return None

        def _s(v):
            if v is None:
                return None
            if isinstance(v, str):
                return v.strip() or None
            return str(v)

        def _err(v):
            if v is None:
                return None
            if isinstance(v, str):
                up = v.strip().upper()
                return up if up in _ALLOWED_ERROR_TYPES else None
            return None

        return {
            "asr_htf_correct": _b(data.get("asr_htf_correct")),
            "asr_ltf_correct": _b(data.get("asr_ltf_correct")),
            "asr_strategy_correct": _b(data.get("asr_strategy_correct")),
            "asr_sl_correct": _b(data.get("asr_sl_correct")),
            "asr_tp_correct": _b(data.get("asr_tp_correct")),
            "asr_management_correct": _b(data.get("asr_management_correct")),
            "asr_would_enter_again": _b(data.get("asr_would_enter_again")),
            "asr_lessons": _s(data.get("asr_lessons")),
            "asr_error_type": _err(data.get("asr_error_type")),
        }


def find_close_screenshot(screenshots_dir: str, trade_id: str) -> Optional[str]:
    """Locate the most recent close screenshot for a trade, if it exists."""
    if not os.path.isdir(screenshots_dir):
        return None
    try:
        candidates = [
            f for f in os.listdir(screenshots_dir)
            if trade_id in f and "_close_" in f and f.endswith(".png")
        ]
    except Exception:
        return None
    if not candidates:
        return None
    candidates.sort(reverse=True)  # filename ends with timestamp -> reverse sort = newest
    return os.path.join(screenshots_dir, candidates[0])
