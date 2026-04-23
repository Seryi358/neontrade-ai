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
Tu tarea es completar el ASR (Auto Self Review) evaluando la EJECUCIÓN contra
el PLAN, NO contra el resultado.

Instrucciones (Alex Ruiz):
- "correcto o incorrecto no viene relacionado con el resultado del trade,
   viene relacionado con vuestro plan de trading"
- Un trade puede haber perdido dinero pero tener ejecución correcta (todo el
  plan cumplido, simplemente la probabilidad jugó en contra). De igual forma
  un trade ganador puede tener ejecución incorrecta (suerte, no plan).
- **IMPORTANTE**: aunque el registro tenga campos vacíos o "no registrado",
  DEBES hacer tu mejor evaluación basada en: (1) los datos visibles (entry/SL/
  TP/strategy/result/screenshot), (2) las reglas conocidas de cada strategy
  (BLUE/RED/PINK/WHITE/BLACK/GREEN), (3) la imagen del gráfico si fue adjuntada.
  Sólo devuelve `null` cuando realmente no haya forma razonable de evaluar.
- Reglas por strategy (resumen TradingLab):
    * BLUE = Cambio de tendencia en 1H. SL debajo del 0.618 Fib / mínimo
      anterior. TP1 = swing anterior; TP_max = EMA 50 4H. R:R mínimo 1.5.
    * RED  = Cambio de tendencia en 4H. SL debajo EMA 50 4H. TP = máximo
      anterior o Fib 1.0. R:R ≥ 2.0.
    * PINK = Patrón correctivo de continuación. SL mínimo anterior. TP máximo
      anterior.
    * WHITE = Continuación post-Pink. SL extremo anterior. TP nivel de Pink.
    * BLACK = CONTRATENDENCIA. SL encima máximo anterior. TP = EMA 50 4H.
      R:R ≥ 2.0 OBLIGATORIO. SELL con HTF alcista (o BUY con HTF bajista)
      es la semántica ESPERADA, no una contradicción.
    * GREEN = Semanal + Diario + 15M. R:R hasta 10:1. Sólo cripto.
- error_type: PERCEPTION (leí mal el gráfico), TECHNICAL (apliqué mal una regla),
  ROUTINE (no seguí mi rutina/checklist), EMOTIONAL (revenge/FOMO/miedo).
  Escoge el MÁS relevante si el trade no fue perfecto; devuelve null sólo si
  la ejecución fue impecable según el plan.

Devuelve EXACTAMENTE este JSON (sin markdown, sin texto extra), con todas las
claves siguientes. Prefiere `true`/`false` razonado sobre `null`:
- asr_htf_correct (bool|null): ¿el análisis HTF estuvo alineado con la
  strategy? (p.ej. BLACK necesita HTF alcista para SELL)
- asr_ltf_correct (bool|null): ¿el timeframe de ejecución (M5 day / M1 scalp)
  mostró una señal válida?
- asr_strategy_correct (bool|null): ¿la strategy elegida era la adecuada para
  el contexto del mercado visible?
- asr_sl_correct (bool|null): ¿el SL estuvo en el lugar correcto según las
  reglas de la strategy?
- asr_tp_correct (bool|null): ¿el TP1 estuvo en el nivel correcto?
- asr_management_correct (bool|null): ¿la gestión post-entry fue correcta?
  (BE movido a tiempo, trailing activado tras swing, etc.)
- asr_would_enter_again (bool|null): con la info disponible, ¿volverías a
  tomar este trade?
- asr_lessons (string en español, 2-4 frases concretas sobre qué aprender
  de este trade específico)
- asr_error_type (string|null: PERCEPTION | TECHNICAL | ROUTINE | EMOTIONAL | null)

CONTEXTO DEL TRADE:
__TRADE_CONTEXT__
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
            user_text = ASR_POSTMORTEM_PROMPT.replace(
                "__TRADE_CONTEXT__",
                self._format_trade_context(trade_record),
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
            # Defensive: strip ```json fences if the model wraps the response.
            if raw.startswith("```"):
                lines = raw.splitlines()
                if lines and lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                raw = "\n".join(lines).strip()
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
        """Compact human-readable summary the model uses to grade execution.

        Always emit EVERY key the checklist cares about (even as "no
        registrado") so the model knows which dimensions exist and can
        still reason about them from the screenshot/strategy rules alone.
        Without this, sparse journal records caused the model to default to
        all-null ASR — observed live when JPM backfill filled only
        `asr_lessons`.
        """
        primary_keys = [
            "instrument", "direction", "strategy", "strategy_variant",
            "entry_price", "exit_price", "sl", "tp", "stop_loss", "take_profit",
            "rr_achieved", "risk_reward_ratio",
            "pnl_dollars", "pnl", "pnl_pct", "result", "status",
            "confidence",
            "balance_after", "drawdown_pct", "duration_minutes",
            "trading_style", "timeframes_used",
            "opened_at", "closed_at", "mode",
        ]
        lines = []
        for k in primary_keys:
            if k in t:
                val = t[k]
                if val in (None, "", []):
                    lines.append(f"- {k}: (no registrado)")
                else:
                    lines.append(f"- {k}: {val}")
        # Reasoning / explanation text from the strategy detection phase
        for long_key in ("reasoning", "ai_analysis", "ai_reasoning", "explanation_es"):
            v = t.get(long_key)
            if v and isinstance(v, str):
                # Truncate to keep prompt size bounded.
                snippet = v if len(v) <= 1500 else (v[:1500] + "...[truncated]")
                lines.append(f"\n=== {long_key} ===\n{snippet}")
        # Free-text fields (human-filled notes)
        for note_key in (
            "trade_summary", "management_notes", "notes",
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


# ── Phase 2: TuningEngine + ProposalStore (rule-based parameter tuning) ───────

import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Hard caps so a runaway rule can never tighten dangerously or loosen recklessly.
TUNING_SAFETY_GATES: Dict[str, Dict[str, float]] = {
    "max_total_risk":         {"floor": 0.01, "ceiling": 0.05},
    "risk_day_trading":       {"floor": 0.002, "ceiling": 0.02},
    "risk_scalping":          {"floor": 0.0,   "ceiling": 0.01},
    "risk_swing":             {"floor": 0.002, "ceiling": 0.02},
    "min_rr_ratio":           {"floor": 1.0,   "ceiling": 3.0},
    "move_sl_to_be_pct_to_tp1": {"floor": 0.30, "ceiling": 0.80},
}

TUNING_COOLDOWN_DAYS = {
    "default": 7,
    "max_total_risk": 14,
    "scalping_enabled": 30,
}


@dataclass
class TuningProposal:
    id: str
    created_at: str
    parameter_key: str
    current_value: object
    proposed_value: object
    tier: str                # "safe" | "moderate" | "drastic"
    rationale: str
    evidence: dict
    status: str = "pending"   # pending | applied | rejected | rolled_back | expired
    applied_at: Optional[str] = None
    rolled_back_at: Optional[str] = None
    parent_snapshot: Optional[dict] = None  # snapshot of changed key for rollback

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in (
            "id", "created_at", "parameter_key", "current_value",
            "proposed_value", "tier", "rationale", "evidence",
            "status", "applied_at", "rolled_back_at", "parent_snapshot",
        )}


class ProposalStore:
    """JSON-backed reversible change log. SQLite would be cleaner but the
    project already uses JSON for trade_journal/missed_trades/risk_config so
    a parallel file keeps ops simple. Atomic tempfile+replace writes."""

    def __init__(self, path: Optional[str] = None):
        if path is None:
            base = Path(__file__).resolve().parent.parent / "data" / "tuning_proposals.json"
            path = str(base)
        self.path = path
        self._proposals: List[TuningProposal] = self._load()

    def _load(self) -> List[TuningProposal]:
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path) as f:
                raw = json.load(f)
            return [TuningProposal(**p) for p in raw]
        except Exception as e:
            logger.warning(f"ProposalStore load failed ({e}); starting empty")
            return []

    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        import tempfile
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump([p.to_dict() for p in self._proposals], f, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def create(self, proposal: TuningProposal):
        self._proposals.append(proposal)
        self._save()

    def list_all(self, status: Optional[str] = None) -> List[TuningProposal]:
        if status is None:
            return list(self._proposals)
        return [p for p in self._proposals if p.status == status]

    def get(self, proposal_id: str) -> Optional[TuningProposal]:
        return next((p for p in self._proposals if p.id == proposal_id), None)

    def in_cooldown(self, parameter_key: str, days: int) -> bool:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        for p in self._proposals:
            if p.parameter_key == parameter_key and p.status == "applied" and p.applied_at:
                try:
                    when = datetime.fromisoformat(p.applied_at)
                    if when >= cutoff:
                        return True
                except Exception:
                    continue
        return False


class TuningEngine:
    """Rule-based parameter-change proposer.

    Reads aggregated stats + current settings, emits TuningProposal objects.
    Never mutates settings directly — that's the orchestrator's job after
    safety gating + (optional) approval.
    """

    MIN_TRADES_DEFAULT = 10

    def __init__(self, settings_obj, proposal_store: ProposalStore):
        self.settings = settings_obj
        self.store = proposal_store

    def evaluate(self, stats: dict) -> List[TuningProposal]:
        """Return new proposals based on `stats`.

        Expected stats shape (built by the orchestrator from MonthlyReport /
        weekly-review payload):
            {
              "total_trades": int,
              "win_rate": float (0..1),
              "by_style": {"day_trading": {trades, win_rate, profit_factor}, ...},
              "max_dd_pct": float (0..100),
            }
        """
        proposals: List[TuningProposal] = []
        min_trades = getattr(self.settings, "self_improvement_min_trades", self.MIN_TRADES_DEFAULT)
        if stats.get("total_trades", 0) < min_trades:
            return proposals

        # Rule 1 (SAFE): reduce day-trading risk by 50% if WR < 30% on >=10 trades.
        wr = stats.get("win_rate", 0.0)
        if wr < 0.30 and stats.get("total_trades", 0) >= min_trades:
            cur = float(getattr(self.settings, "risk_day_trading", 0.01))
            new_val = self._clamp("risk_day_trading", cur * 0.5)
            if new_val != cur and not self.store.in_cooldown("risk_day_trading", TUNING_COOLDOWN_DAYS["default"]):
                proposals.append(TuningProposal(
                    id=str(uuid.uuid4()),
                    created_at=datetime.now(timezone.utc).isoformat(),
                    parameter_key="risk_day_trading",
                    current_value=cur,
                    proposed_value=new_val,
                    tier="safe",
                    rationale=(
                        f"Win rate {wr*100:.1f}% sobre {stats.get('total_trades')} trades — "
                        f"reducir riesgo diario {cur*100:.2f}% -> {new_val*100:.2f}% para limitar "
                        f"el drawdown mientras se identifica la causa."
                    ),
                    evidence={"win_rate": wr, "trades": stats.get("total_trades"), "rule": "low_wr_reduce_risk"},
                ))

        # Rule 2 (SAFE): disable scalping if its profit factor < 0.7 and >=20 scalp trades
        # AND day trading is doing better.
        if getattr(self.settings, "scalping_enabled", False):
            scalp = stats.get("by_style", {}).get("scalping", {})
            day = stats.get("by_style", {}).get("day_trading", {})
            if (
                scalp.get("trades", 0) >= 20
                and scalp.get("profit_factor", 1.0) < 0.7
                and day.get("trades", 0) >= 10
                and day.get("win_rate", 0.0) > scalp.get("win_rate", 0.0) + 0.10
            ):
                if not self.store.in_cooldown("scalping_enabled", TUNING_COOLDOWN_DAYS["scalping_enabled"]):
                    proposals.append(TuningProposal(
                        id=str(uuid.uuid4()),
                        created_at=datetime.now(timezone.utc).isoformat(),
                        parameter_key="scalping_enabled",
                        current_value=True,
                        proposed_value=False,
                        tier="safe",
                        rationale=(
                            f"Scalping PF {scalp.get('profit_factor'):.2f} < 0.7 sobre {scalp.get('trades')} trades, "
                            f"y day trading WR {day.get('win_rate', 0)*100:.1f}% supera scalping WR {scalp.get('win_rate', 0)*100:.1f}% "
                            f"por más de 10 puntos. Sugerido: pausar scalping y enfocarse en day trading."
                        ),
                        evidence={
                            "scalping": scalp,
                            "day_trading": day,
                            "rule": "scalping_underperforms_day",
                        },
                    ))

        # Rule 3 (SAFE): tighten max_total_risk if observed max DD breached 8%.
        if stats.get("max_dd_pct", 0.0) >= 8.0:
            cur = float(getattr(self.settings, "max_total_risk", 0.05))
            new_val = self._clamp("max_total_risk", cur * 0.7)
            if new_val != cur and not self.store.in_cooldown("max_total_risk", TUNING_COOLDOWN_DAYS["max_total_risk"]):
                proposals.append(TuningProposal(
                    id=str(uuid.uuid4()),
                    created_at=datetime.now(timezone.utc).isoformat(),
                    parameter_key="max_total_risk",
                    current_value=cur,
                    proposed_value=new_val,
                    tier="safe",
                    rationale=(
                        f"Max drawdown {stats.get('max_dd_pct'):.2f}% supera el 8% objetivo. "
                        f"Reducir max_total_risk {cur*100:.1f}% -> {new_val*100:.1f}% mientras se recupera."
                    ),
                    evidence={"max_dd_pct": stats.get("max_dd_pct"), "rule": "dd_breach_tighten_risk"},
                ))

        return proposals

    @staticmethod
    def _clamp(key: str, value: float) -> float:
        gate = TUNING_SAFETY_GATES.get(key)
        if not gate:
            return value
        return max(gate["floor"], min(gate["ceiling"], value))


def apply_proposal(settings_obj, proposal: TuningProposal, persist_fn) -> bool:
    """Apply a proposal: mutate settings, snapshot prior value, persist via callback.

    `persist_fn(key, value)` is responsible for writing the override to disk
    (e.g. the same flow as PUT /risk-config so the change survives restarts).
    Returns True on success.
    """
    key = proposal.parameter_key
    if not hasattr(settings_obj, key):
        logger.warning(f"apply_proposal: settings has no attribute {key!r}; skipping")
        return False
    proposal.parent_snapshot = {key: getattr(settings_obj, key)}
    setattr(settings_obj, key, proposal.proposed_value)
    try:
        persist_fn(key, proposal.proposed_value)
    except Exception as e:
        # Roll back in-memory mutation if persistence fails — keeps disk and
        # memory consistent.
        setattr(settings_obj, key, proposal.parent_snapshot[key])
        logger.error(f"apply_proposal persist failed for {key}: {e}")
        return False
    proposal.status = "applied"
    proposal.applied_at = datetime.now(timezone.utc).isoformat()
    return True


def rollback_proposal(settings_obj, proposal: TuningProposal, persist_fn) -> bool:
    """Restore the snapshotted value and mark proposal rolled_back."""
    if proposal.status != "applied" or not proposal.parent_snapshot:
        return False
    key = proposal.parameter_key
    prior = proposal.parent_snapshot.get(key)
    setattr(settings_obj, key, prior)
    try:
        persist_fn(key, prior)
    except Exception as e:
        logger.error(f"rollback_proposal persist failed for {key}: {e}")
        return False
    proposal.status = "rolled_back"
    proposal.rolled_back_at = datetime.now(timezone.utc).isoformat()
    return True


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
