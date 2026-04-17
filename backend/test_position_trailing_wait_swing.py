"""
Iter-29 / Audit A4 — Trailing espera ruptura del máximo/mínimo anterior.

Trading Mastery Short Term (mentoría):
  "ahí tenemos ya el 1%, break-even... a partir de aquí vamos a esperar
   y empezaremos a gestionar con la media móvil de 50, de cinco minutos.
   Hasta que no se rompa, evidentemente, este máximo anterior, no vamos
   a utilizarla"

Regla: después de BE, el trailing NO activa hasta que el precio rompe
el swing high previo (BUY) o swing low previo (SELL).
"""

import sys
import asyncio
from unittest.mock import patch

sys.path.insert(0, ".")

from core.position_manager import (
    PositionManager,
    ManagedPosition,
    PositionPhase,
)


class _MockBroker:
    def __init__(self):
        self.sl_updates = []
        self.closed = []

    async def modify_trade_sl(self, trade_id, new_sl):
        self.sl_updates.append((trade_id, new_sl))
        return True

    async def close_trade(self, trade_id, units=None):
        self.closed.append((trade_id, units))
        return True

    async def close_trade_partial(self, trade_id, percent=50):
        return True


def _run(coro):
    return asyncio.run(coro)


def _make_pos(direction="BUY", entry=1.1000, sl=1.0950,
              tp1=1.1100, tp_max=1.1200,
              phase=PositionPhase.SL_MOVED,
              trade_id="t-a4"):
    return ManagedPosition(
        trade_id=trade_id,
        instrument="EUR_USD",
        direction=direction,
        entry_price=entry,
        original_sl=sl,
        current_sl=sl,
        take_profit_1=tp1,
        take_profit_max=tp_max,
        units=20000,
        style="day_trading",
        phase=phase,
        highest_price=entry,
        lowest_price=entry,
    )


def _make_pm():
    return PositionManager(
        _MockBroker(),
        management_style="lp",
        trading_style="day_trading",
    )


# ─────────────────────────────────────────────────────────────────────
# Dataclass / helpers
# ─────────────────────────────────────────────────────────────────────

def test_managed_position_has_swing_to_break_field():
    """La posición debe exponer swing_to_break y swing_broken."""
    pos = _make_pos()
    assert hasattr(pos, "swing_to_break")
    assert hasattr(pos, "swing_broken")
    assert pos.swing_to_break is None
    assert pos.swing_broken is False


# ─────────────────────────────────────────────────────────────────────
# Swing capture at BE transition
# ─────────────────────────────────────────────────────────────────────

@patch("config.settings")
def test_swing_captured_when_be_fires_buy(mock_settings):
    """BUY: al disparar BE, se captura el swing high superior más cercano."""
    mock_settings.be_trigger_method = "risk_distance"
    pm = _make_pm()
    pos = _make_pos(direction="BUY", entry=1.1000, sl=1.0950,
                    tp1=1.1100, phase=PositionPhase.SL_MOVED)
    pos.current_sl = 1.0975
    pm.track_position(pos)

    # Swing highs dispobibles ENCIMA del precio actual
    pm.set_swing_values("EUR_USD",
                        swing_highs=[1.1080, 1.1150, 1.1200],
                        swing_lows=[1.0900, 1.0850])

    # price 1.1055 → profit 0.0055 >= risk_distance 0.005 → BE disparará
    _run(pm._handle_sl_moved_phase(pos, 1.1055))

    assert pos.phase == PositionPhase.BREAK_EVEN
    # El swing_to_break debe ser el más cercano por encima del current_price 1.1055
    # => 1.1080 (el menor de los highs > 1.1055)
    assert pos.swing_to_break == 1.1080, (
        f"BUY: swing_to_break debería ser 1.1080, fue {pos.swing_to_break}"
    )


@patch("config.settings")
def test_swing_captured_when_be_fires_sell(mock_settings):
    """SELL: al disparar BE, se captura el swing low inferior más cercano."""
    mock_settings.be_trigger_method = "risk_distance"
    pm = _make_pm()
    pos = _make_pos(direction="SELL", entry=1.1000, sl=1.1050,
                    tp1=1.0900, phase=PositionPhase.SL_MOVED)
    pos.current_sl = 1.1025
    pm.track_position(pos)

    # Swing lows disponibles DEBAJO del precio actual
    pm.set_swing_values("EUR_USD",
                        swing_highs=[1.1150, 1.1200],
                        swing_lows=[1.0920, 1.0850, 1.0800])

    # price 1.0945 → profit 0.0055 >= 0.005 → BE disparará
    _run(pm._handle_sl_moved_phase(pos, 1.0945))

    assert pos.phase == PositionPhase.BREAK_EVEN
    # Más cercano por debajo de 1.0945 = 1.0920 (el mayor de los lows < 1.0945)
    assert pos.swing_to_break == 1.0920, (
        f"SELL: swing_to_break debería ser 1.0920, fue {pos.swing_to_break}"
    )


@patch("config.settings")
def test_swing_capture_none_when_no_swing_data(mock_settings):
    """Sin swing data al momento de BE, swing_to_break queda None (legacy fallback)."""
    mock_settings.be_trigger_method = "risk_distance"
    pm = _make_pm()
    pos = _make_pos(direction="BUY", entry=1.1000, sl=1.0950,
                    tp1=1.1100, phase=PositionPhase.SL_MOVED)
    pos.current_sl = 1.0975
    pm.track_position(pos)

    _run(pm._handle_sl_moved_phase(pos, 1.1055))

    assert pos.phase == PositionPhase.BREAK_EVEN
    assert pos.swing_to_break is None


# ─────────────────────────────────────────────────────────────────────
# Gate: trailing NO activa hasta que se rompa el swing
# ─────────────────────────────────────────────────────────────────────

@patch("config.settings")
def test_trailing_not_activated_until_swing_break_buy(mock_settings):
    """BUY: tras BE, trailing NO activa hasta que precio supere swing high previo."""
    mock_settings.be_trigger_method = "risk_distance"
    pm = _make_pm()
    pos = _make_pos(direction="BUY", entry=1.1000, sl=1.0950,
                    tp1=1.1100, phase=PositionPhase.BREAK_EVEN)
    pos.current_sl = 1.1001
    pos.swing_to_break = 1.1080  # manualmente seteado
    pm.track_position(pos)

    # EMA_H1_50 FAVORABLE (below price) — bajo semántica vieja, esto activaría trailing
    pm.set_ema_values("EUR_USD", {"EMA_H1_50": 1.1030})

    # Precio 1.1070: por encima de BE, por encima de EMA, PERO aún debajo del swing 1.1080
    _run(pm._handle_be_phase(pos, 1.1070))
    assert pos.phase == PositionPhase.BREAK_EVEN, (
        "trailing NO debe activar antes de la ruptura del swing"
    )
    assert pos.swing_broken is False

    # Precio cruza el swing 1.1080 → trailing ahora sí activa
    _run(pm._handle_be_phase(pos, 1.1085))
    assert pos.phase == PositionPhase.TRAILING_TO_TP1, (
        "trailing debe activar tras ruptura del swing"
    )
    assert pos.swing_broken is True


@patch("config.settings")
def test_trailing_not_activated_until_swing_break_sell(mock_settings):
    """SELL: tras BE, trailing NO activa hasta que precio pierda el swing low previo."""
    mock_settings.be_trigger_method = "risk_distance"
    pm = _make_pm()
    pos = _make_pos(direction="SELL", entry=1.1000, sl=1.1050,
                    tp1=1.0900, phase=PositionPhase.BREAK_EVEN)
    pos.current_sl = 1.0999
    pos.swing_to_break = 1.0920  # manualmente seteado
    pm.track_position(pos)

    # EMA favorable (above price)
    pm.set_ema_values("EUR_USD", {"EMA_H1_50": 1.0970})

    # Precio 1.0930: mejor que BE, pero aún ENCIMA del swing 1.0920 → no ruptura
    _run(pm._handle_be_phase(pos, 1.0930))
    assert pos.phase == PositionPhase.BREAK_EVEN
    assert pos.swing_broken is False

    # Precio rompe DEBAJO del swing 1.0920 → trailing activa
    _run(pm._handle_be_phase(pos, 1.0915))
    assert pos.phase == PositionPhase.TRAILING_TO_TP1
    assert pos.swing_broken is True


@patch("config.settings")
def test_swing_break_latches(mock_settings):
    """Una vez rota, la ruptura queda latcheada (no se pierde si precio vuelve)."""
    mock_settings.be_trigger_method = "risk_distance"
    pm = _make_pm()
    pos = _make_pos(direction="BUY", entry=1.1000, sl=1.0950,
                    tp1=1.1100, phase=PositionPhase.BREAK_EVEN)
    pos.current_sl = 1.1001
    pos.swing_to_break = 1.1080
    pm.track_position(pos)

    pm.set_ema_values("EUR_USD", {"EMA_H1_50": 1.1030})

    # Rompe
    _run(pm._handle_be_phase(pos, 1.1085))
    assert pos.phase == PositionPhase.TRAILING_TO_TP1
    assert pos.swing_broken is True


# ─────────────────────────────────────────────────────────────────────
# Back-compat: sin swing_to_break, legacy EMA-favorable gate
# ─────────────────────────────────────────────────────────────────────

@patch("config.settings")
def test_no_swing_data_uses_legacy_ema_gate(mock_settings):
    """Sin swing_to_break capturado (None), activa trailing con EMA favorable."""
    mock_settings.be_trigger_method = "risk_distance"
    pm = _make_pm()
    pos = _make_pos(direction="BUY", entry=1.1000, sl=1.0950,
                    tp1=1.1100, phase=PositionPhase.BREAK_EVEN)
    pos.current_sl = 1.1001
    # swing_to_break = None (default)
    pm.track_position(pos)

    pm.set_ema_values("EUR_USD", {"EMA_H1_50": 1.1030})

    # Solo EMA favorable + precio por encima → activa trailing
    _run(pm._handle_be_phase(pos, 1.1060))
    assert pos.phase == PositionPhase.TRAILING_TO_TP1


# ─────────────────────────────────────────────────────────────────────
# End-to-end: full flow SL_MOVED → BE → wait → TRAILING
# ─────────────────────────────────────────────────────────────────────

@patch("config.settings")
def test_full_flow_captures_and_waits_for_swing(mock_settings):
    """E2E: SL_MOVED → BE (captura swing) → wait → swing break → TRAILING."""
    mock_settings.be_trigger_method = "risk_distance"
    pm = _make_pm()
    pos = _make_pos(direction="BUY", entry=1.1000, sl=1.0950,
                    tp1=1.1100, phase=PositionPhase.SL_MOVED)
    pos.current_sl = 1.0975
    pm.track_position(pos)
    pm.set_swing_values("EUR_USD", [1.1080, 1.1200], [1.0900])
    pm.set_ema_values("EUR_USD", {"EMA_H1_50": 1.1030})

    # 1) trigger BE
    _run(pm._handle_sl_moved_phase(pos, 1.1055))
    assert pos.phase == PositionPhase.BREAK_EVEN
    assert pos.swing_to_break == 1.1080

    # 2) precio sube pero NO rompe el swing → se mantiene en BE
    _run(pm._handle_be_phase(pos, 1.1070))
    assert pos.phase == PositionPhase.BREAK_EVEN

    # 3) precio rompe el swing → TRAILING activa
    _run(pm._handle_be_phase(pos, 1.1090))
    assert pos.phase == PositionPhase.TRAILING_TO_TP1
