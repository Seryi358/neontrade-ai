"""
Tests for screenshot_generator.py — THEME config, time label extraction,
capture_trade_open, capture_trade_close, get_screenshot_path, info card,
candlestick chart, and EMA overlays.
"""

import os
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from core.screenshot_generator import (
    THEME,
    TradeScreenshotGenerator,
    HAS_MATPLOTLIB,
)


@pytest.fixture
def gen(tmp_path):
    """Generator with a temp screenshots directory."""
    return TradeScreenshotGenerator(data_dir=str(tmp_path))


def _make_candles(n=30, base_price=1.1000):
    """Build a list of candle dicts."""
    candles = []
    for i in range(n):
        o = base_price + i * 0.001
        h = o + 0.002
        l = o - 0.001
        c = o + 0.0005
        candles.append({
            "time": f"2025-03-10T{10 + i % 12:02d}:00:00Z",
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": 100 + i,
        })
    return candles


# ──────────────────────────────────────────────────────────────────
# THEME constants
# ──────────────────────────────────────────────────────────────────

class TestTheme:
    def test_has_required_keys(self):
        required = [
            "bg", "bg_card", "bullish", "bearish", "text", "text_dim",
            "grid", "entry", "sl", "tp", "tp_max", "ema_fast", "ema_slow",
            "current_price", "info_box_bg", "info_box_border",
        ]
        for key in required:
            assert key in THEME, f"Missing THEME key: {key}"

    def test_colors_are_strings(self):
        for key, value in THEME.items():
            assert isinstance(value, str), f"THEME[{key}] should be string"


# ──────────────────────────────────────────────────────────────────
# __init__
# ──────────────────────────────────────────────────────────────────

class TestInit:
    def test_creates_directory(self, tmp_path):
        data_dir = str(tmp_path / "shots")
        gen = TradeScreenshotGenerator(data_dir=data_dir)
        assert os.path.isdir(data_dir)

    def test_existing_directory_ok(self, tmp_path):
        gen = TradeScreenshotGenerator(data_dir=str(tmp_path))
        assert gen._data_dir == str(tmp_path)


# ──────────────────────────────────────────────────────────────────
# _extract_time_labels
# ──────────────────────────────────────────────────────────────────

class TestExtractTimeLabels:
    def test_iso_strings(self, gen):
        candles = [
            {"time": "2025-03-10T10:00:00Z"},
            {"time": "2025-03-10T11:00:00Z"},
        ]
        labels = gen._extract_time_labels(candles)
        assert labels == ["10:00", "11:00"]

    def test_unix_timestamps(self, gen):
        ts1 = datetime(2025, 3, 10, 10, 0, tzinfo=timezone.utc).timestamp()
        ts2 = datetime(2025, 3, 10, 11, 0, tzinfo=timezone.utc).timestamp()
        candles = [{"time": ts1}, {"time": ts2}]
        labels = gen._extract_time_labels(candles)
        assert labels == ["10:00", "11:00"]

    def test_datetime_objects(self, gen):
        candles = [
            {"time": datetime(2025, 3, 10, 14, 30, tzinfo=timezone.utc)},
        ]
        labels = gen._extract_time_labels(candles)
        assert labels == ["14:30"]

    def test_no_time_key(self, gen):
        candles = [{"open": 1.1}]
        labels = gen._extract_time_labels(candles)
        assert labels == []

    def test_empty_candles(self, gen):
        assert gen._extract_time_labels([]) == []

    def test_timestamp_key_fallback(self, gen):
        candles = [{"timestamp": "2025-03-10T09:00:00Z"}]
        labels = gen._extract_time_labels(candles)
        assert labels == ["09:00"]

    def test_datetime_key_fallback(self, gen):
        candles = [{"datetime": "2025-03-10T09:00:00Z"}]
        labels = gen._extract_time_labels(candles)
        assert labels == ["09:00"]


# ──────────────────────────────────────────────────────────────────
# get_screenshot_path
# ──────────────────────────────────────────────────────────────────

class TestGetScreenshotPath:
    def test_finds_matching_files(self, gen, tmp_path):
        # Create dummy screenshot files
        for name in ["EUR_USD_abc123_open_20250310.png", "EUR_USD_abc123_close_20250310.png"]:
            (tmp_path / name).write_text("dummy")
        paths = gen.get_screenshot_path("abc123")
        assert len(paths) == 2

    def test_no_match(self, gen):
        paths = gen.get_screenshot_path("nonexistent")
        assert paths == []

    def test_ignores_non_png(self, gen, tmp_path):
        (tmp_path / "EUR_USD_abc123_open.txt").write_text("dummy")
        paths = gen.get_screenshot_path("abc123")
        assert paths == []

    def test_nonexistent_directory(self):
        gen = TradeScreenshotGenerator.__new__(TradeScreenshotGenerator)
        gen._data_dir = "/nonexistent/path"
        paths = gen.get_screenshot_path("abc")
        assert paths == []


# ──────────────────────────────────────────────────────────────────
# capture_trade_open
# ──────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not HAS_MATPLOTLIB, reason="matplotlib not installed")
class TestCaptureTradeOpen:
    @pytest.mark.asyncio
    async def test_with_candles(self, gen, tmp_path):
        candles = _make_candles(30)
        filepath = await gen.capture_trade_open(
            trade_id="t001",
            instrument="EUR_USD",
            direction="BUY",
            entry_price=1.1000,
            sl=1.0950,
            tp1=1.1100,
            tp_max=1.1200,
            strategy="BLUE_A",
            confidence=0.85,
            candles=candles,
        )
        assert filepath != ""
        assert os.path.exists(filepath)
        assert filepath.endswith(".png")
        assert "t001" in filepath
        assert "open" in filepath

    @pytest.mark.asyncio
    async def test_without_candles_fallback_info_card(self, gen):
        filepath = await gen.capture_trade_open(
            trade_id="t002",
            instrument="GBP_USD",
            direction="SELL",
            entry_price=1.2500,
            sl=1.2550,
            tp1=1.2400,
            tp_max=None,
            strategy="RED",
            confidence=0.70,
            candles=None,
        )
        assert filepath != ""
        assert os.path.exists(filepath)

    @pytest.mark.asyncio
    async def test_with_ema_values(self, gen):
        candles = _make_candles(20)
        ema_values = {
            "ema2": [c["close"] + 0.0005 for c in candles],
            "ema5": [c["close"] - 0.0005 for c in candles],
        }
        filepath = await gen.capture_trade_open(
            trade_id="t003",
            instrument="EUR_USD",
            direction="BUY",
            entry_price=1.1000,
            sl=1.0950,
            tp1=1.1100,
            tp_max=None,
            strategy="BLUE_A",
            confidence=0.80,
            candles=candles,
            ema_values=ema_values,
        )
        assert filepath != ""
        assert os.path.exists(filepath)

    @pytest.mark.asyncio
    async def test_zero_risk_rr_zero(self, gen):
        """When SL == entry, R:R should be 0 (no division error)."""
        candles = _make_candles(10)
        filepath = await gen.capture_trade_open(
            trade_id="t004",
            instrument="EUR_USD",
            direction="BUY",
            entry_price=1.1000,
            sl=1.1000,  # Same as entry
            tp1=1.1100,
            tp_max=None,
            strategy="BLUE_A",
            confidence=0.50,
            candles=candles,
        )
        assert filepath != ""


# ──────────────────────────────────────────────────────────────────
# capture_trade_close
# ──────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not HAS_MATPLOTLIB, reason="matplotlib not installed")
class TestCaptureTradeClose:
    @pytest.mark.asyncio
    async def test_with_candles_win(self, gen):
        candles = _make_candles(25)
        filepath = await gen.capture_trade_close(
            trade_id="t010",
            instrument="EUR_USD",
            direction="BUY",
            entry_price=1.1000,
            close_price=1.1100,
            pnl_pct=1.5,
            result="TP",
            candles=candles,
        )
        assert filepath != ""
        assert os.path.exists(filepath)
        assert "close" in filepath

    @pytest.mark.asyncio
    async def test_with_candles_loss(self, gen):
        filepath = await gen.capture_trade_close(
            trade_id="t011",
            instrument="EUR_USD",
            direction="BUY",
            entry_price=1.1000,
            close_price=1.0950,
            pnl_pct=-0.5,
            result="SL",
            candles=_make_candles(15),
        )
        assert filepath != ""

    @pytest.mark.asyncio
    async def test_without_candles(self, gen):
        filepath = await gen.capture_trade_close(
            trade_id="t012",
            instrument="GBP_USD",
            direction="SELL",
            entry_price=1.2500,
            close_price=1.2450,
            pnl_pct=0.4,
            result="TP",
            candles=None,
        )
        assert filepath != ""
        assert os.path.exists(filepath)

    @pytest.mark.asyncio
    async def test_break_even_result(self, gen):
        filepath = await gen.capture_trade_close(
            trade_id="t013",
            instrument="EUR_USD",
            direction="BUY",
            entry_price=1.1000,
            close_price=1.1000,
            pnl_pct=0.0,
            result="BE",
            candles=_make_candles(10),
        )
        assert filepath != ""


# ──────────────────────────────────────────────────────────────────
# matplotlib not installed fallback
# ──────────────────────────────────────────────────────────────────

class TestNoMatplotlib:
    @pytest.mark.asyncio
    async def test_capture_open_returns_empty(self, gen):
        with patch("core.screenshot_generator.HAS_MATPLOTLIB", False):
            filepath = await gen.capture_trade_open(
                trade_id="t020",
                instrument="EUR_USD",
                direction="BUY",
                entry_price=1.1,
                sl=1.09,
                tp1=1.12,
                tp_max=None,
                strategy="BLUE",
                confidence=0.5,
            )
            assert filepath == ""

    @pytest.mark.asyncio
    async def test_capture_close_returns_empty(self, gen):
        with patch("core.screenshot_generator.HAS_MATPLOTLIB", False):
            filepath = await gen.capture_trade_close(
                trade_id="t021",
                instrument="EUR_USD",
                direction="BUY",
                entry_price=1.1,
                close_price=1.11,
                pnl_pct=1.0,
                result="TP",
            )
            assert filepath == ""


# ──────────────────────────────────────────────────────────────────
# Internal chart methods (unit tests on matplotlib primitives)
# ──────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not HAS_MATPLOTLIB, reason="matplotlib not installed")
class TestInternalChartMethods:
    def test_draw_candlesticks(self, gen):
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        candles = _make_candles(10)
        gen._draw_candlesticks(ax, candles)
        # Should have patches (rectangles) and lines
        assert len(ax.patches) == 10  # One rectangle per candle
        plt.close(fig)

    def test_draw_ema_overlays(self, gen):
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        candles = _make_candles(10)
        ema_values = {
            "ema2": [c["close"] for c in candles],
            "ema5": [c["close"] for c in candles],
        }
        gen._draw_ema_overlays(ax, candles, ema_values)
        # Should have drawn 2 lines
        assert len(ax.lines) >= 2
        plt.close(fig)

    def test_draw_trade_levels(self, gen):
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        levels = {"entry": 1.1, "sl": 1.09, "tp1": 1.12, "tp_max": 1.13}
        gen._draw_trade_levels(ax, levels, 20)
        # Should have horizontal lines
        assert len(ax.lines) >= 4  # entry, sl, tp1, tp_max
        plt.close(fig)

    def test_draw_trade_levels_partial(self, gen):
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        levels = {"entry": 1.1, "sl": 1.09}  # No TP
        gen._draw_trade_levels(ax, levels, 20)
        assert len(ax.lines) >= 2
        plt.close(fig)

    def test_draw_trade_info_box_open(self, gen):
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        trade_info = {
            "event": "OPEN",
            "strategy": "BLUE_A",
            "direction": "BUY",
            "entry": 1.1,
            "sl": 1.09,
            "tp1": 1.12,
            "rr": 2.0,
            "confidence": 0.85,
        }
        gen._draw_trade_info_box(ax, trade_info, 20)
        # Should have text elements
        assert len(ax.texts) >= 1
        plt.close(fig)

    def test_draw_trade_info_box_close(self, gen):
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        trade_info = {
            "event": "CLOSE",
            "direction": "BUY",
            "entry": 1.1,
            "close_price": 1.12,
            "result": "TP",
            "pnl_display": "+2.00%",
        }
        gen._draw_trade_info_box(ax, trade_info, 20)
        assert len(ax.texts) >= 1
        plt.close(fig)

    def test_draw_trade_info_box_unknown_event(self, gen):
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        gen._draw_trade_info_box(ax, {"event": "UNKNOWN"}, 20)
        assert len(ax.texts) == 0  # No text added
        plt.close(fig)


# ──────────────────────────────────────────────────────────────────
# Edge cases
# ──────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not HAS_MATPLOTLIB, reason="matplotlib not installed")
class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_single_candle(self, gen):
        candles = _make_candles(1)
        filepath = await gen.capture_trade_open(
            trade_id="t030",
            instrument="EUR_USD",
            direction="BUY",
            entry_price=1.1,
            sl=1.09,
            tp1=1.12,
            tp_max=None,
            strategy="BLUE",
            confidence=0.5,
            candles=candles,
        )
        assert filepath != ""

    @pytest.mark.asyncio
    async def test_many_candles_trimmed_to_100(self, gen):
        candles = _make_candles(200)
        filepath = await gen.capture_trade_open(
            trade_id="t031",
            instrument="EUR_USD",
            direction="BUY",
            entry_price=1.1,
            sl=1.09,
            tp1=1.12,
            tp_max=None,
            strategy="BLUE",
            confidence=0.5,
            candles=candles,
        )
        assert filepath != ""

    @pytest.mark.asyncio
    async def test_empty_candles_list(self, gen):
        filepath = await gen.capture_trade_open(
            trade_id="t032",
            instrument="EUR_USD",
            direction="BUY",
            entry_price=1.1,
            sl=1.09,
            tp1=1.12,
            tp_max=None,
            strategy="BLUE",
            confidence=0.5,
            candles=[],
        )
        # Empty list treated as no candles → fallback to info card
        assert filepath != ""
