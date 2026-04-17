"""
Iter-28 / Audit C2 — Trailing post-BE usa EMAs ultra-cortas (EMA 2 + EMA 5 en M5)
no la EMA 50 en M5.

Trading Plan PDF pg.5 (autoritativo):
  "A partir de aquí usaré siempre las dos medias móviles más cortas en cada
   estilo de trading para gestionar mis posiciones (EMA2m y EMA5m para el
   Day trading)"

La implementación previa usaba `EMA_M5_50` como trail principal para
CP + DAY_TRADING. El fix:
  - Trail principal (CP, DAY_TRADING) -> "EMA_M5_5"
  - Aggressive exit signal -> "EMA_M5_2" (ruptura cierra emergencia)
"""

import sys
import asyncio
import pytest
from unittest.mock import patch

sys.path.insert(0, ".")

from core.position_manager import (
    PositionManager,
    ManagedPosition,
    ManagementStyle,
    TradingStyle,
    PositionPhase,
    _EMA_TIMEFRAME_GRID,
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


def _make_pos(direction="BUY", entry=1.1000, sl=1.0950, tp1=1.1100,
              tp_max=1.1200, phase=PositionPhase.BEYOND_TP1):
    return ManagedPosition(
        trade_id="t-c2",
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


# ─────────────────────────────────────────────────────────────────────
# Grid-level assertions
# ─────────────────────────────────────────────────────────────────────

def test_cp_day_trading_uses_ema_m5_5_as_trail():
    """PDF pg.5: EMA 5 en M5 es la trail principal para CP day trading."""
    assert _EMA_TIMEFRAME_GRID[
        (ManagementStyle.CP, TradingStyle.DAY_TRADING)
    ] == "EMA_M5_5", "CP/day_trading trail debe ser EMA_M5_5 (PDF pg.5)"


def test_cp_day_trading_not_ema_m5_50():
    """Regresión guard: CP/day_trading NO puede volver a ser EMA_M5_50."""
    assert _EMA_TIMEFRAME_GRID[
        (ManagementStyle.CP, TradingStyle.DAY_TRADING)
    ] != "EMA_M5_50"


def test_position_manager_cp_day_trading_base_ema_is_m5_5():
    """Un PositionManager configurado en CP + day trading debe exponer EMA_M5_5."""
    pm = PositionManager(_MockBroker(),
                         management_style="cp",
                         trading_style="day_trading")
    assert pm._base_ema_key == "EMA_M5_5"


# ─────────────────────────────────────────────────────────────────────
# Aggressive exit — EMA 2 en M5
# ─────────────────────────────────────────────────────────────────────

def test_aggressive_exit_ema_is_m5_2():
    """EMA 2 en M5 es la señal de emergency exit para day trading."""
    pm = PositionManager(_MockBroker(),
                         management_style="cp",
                         trading_style="day_trading")
    # Debe existir un accessor para aggressive-exit EMA
    assert hasattr(pm, "_get_aggressive_exit_ema_key"), \
        "PositionManager debe exponer _get_aggressive_exit_ema_key()"
    assert pm._get_aggressive_exit_ema_key("EUR_USD") == "EMA_M5_2"


@patch("config.settings")
def test_aggressive_phase_closes_on_ema_m5_2_break_buy(_mock_settings):
    """BUY en AGGRESSIVE phase: si precio rompe EMA_M5_2 debajo, cierre de emergencia."""
    broker = _MockBroker()
    pm = PositionManager(broker,
                         management_style="cp",
                         trading_style="day_trading")
    pos = _make_pos(direction="BUY", phase=PositionPhase.BEYOND_TP1)
    pm.track_position(pos)

    # Precio por encima de EMA_M5_5 pero por debajo de EMA_M5_2 → emergency exit
    # (fix C2: basta con romper la EMA más corta = EMA_M5_2)
    pm.set_ema_values("EUR_USD", {
        "EMA_M5_2": 1.1150,   # precio 1.1140 < 1.1150 → broken
        "EMA_M5_5": 1.1100,   # precio 1.1140 > 1.1100 → OK
        "EMA_M5_50": 1.1050,  # irrelevante para fix
    })

    _run(pm._handle_aggressive_phase(pos, 1.1140))

    # El emergency exit debe haber cerrado la posición al romper EMA 2
    assert len(broker.closed) == 1, (
        f"emergency exit debía cerrar por ruptura de EMA_M5_2; "
        f"closed={broker.closed}"
    )


@patch("config.settings")
def test_aggressive_phase_closes_on_ema_m5_2_break_sell(_mock_settings):
    """SELL en AGGRESSIVE phase: si precio rompe EMA_M5_2 arriba, cierre de emergencia."""
    broker = _MockBroker()
    pm = PositionManager(broker,
                         management_style="cp",
                         trading_style="day_trading")
    pos = _make_pos(direction="SELL", entry=1.1000, sl=1.1050,
                    tp1=1.0900, tp_max=1.0800,
                    phase=PositionPhase.BEYOND_TP1)
    pm.track_position(pos)

    pm.set_ema_values("EUR_USD", {
        "EMA_M5_2": 1.0860,   # precio 1.0870 > 1.0860 → broken
        "EMA_M5_5": 1.0900,   # precio 1.0870 < 1.0900 → OK
        "EMA_M5_50": 1.0950,
    })

    _run(pm._handle_aggressive_phase(pos, 1.0870))

    assert len(broker.closed) == 1, (
        f"SELL emergency exit debía disparar al romper EMA_M5_2 arriba; "
        f"closed={broker.closed}"
    )


@patch("config.settings")
def test_aggressive_phase_no_emergency_when_price_above_ema_m5_2_buy(_mock_settings):
    """BUY: si precio está por encima de ambas (EMA_M5_2, EMA_M5_5), NO emergency."""
    broker = _MockBroker()
    pm = PositionManager(broker,
                         management_style="cp",
                         trading_style="day_trading")
    pos = _make_pos(direction="BUY", phase=PositionPhase.BEYOND_TP1)
    pos.current_sl = 1.1050
    pm.track_position(pos)

    pm.set_ema_values("EUR_USD", {
        "EMA_M5_2": 1.1100,
        "EMA_M5_5": 1.1080,
        "EMA_M5_50": 1.1030,
    })

    # Precio por encima de ambas EMAs cortas → sin emergency
    _run(pm._handle_aggressive_phase(pos, 1.1150))

    assert len(broker.closed) == 0, "no emergency mientras precio > EMA_M5_2"
