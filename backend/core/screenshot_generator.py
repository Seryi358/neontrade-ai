"""
Atlas - Trade Screenshot Generator
Generates chart screenshots for every executed trade.

From Trading Plan:
- "Take screenshots (always current) of every executed trade"
- Screenshots are captured at trade OPEN and trade CLOSE
- Charts include candlesticks, entry/SL/TP levels, EMAs, and trade info

Uses matplotlib with Agg backend (non-interactive, server-safe).
Falls back gracefully if matplotlib is not installed.
"""

import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from loguru import logger

try:
    import matplotlib
    matplotlib.use("Agg")  # Non-interactive backend, must be set before pyplot import
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.lines import Line2D
    from matplotlib.collections import PolyCollection
    import matplotlib.dates as mdates
    import matplotlib.ticker as mticker
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    logger.warning(
        "matplotlib not installed - trade screenshots will be disabled. "
        "Install with: pip install matplotlib"
    )

try:
    import mplfinance as mpf
    import pandas as pd
    HAS_MPLFINANCE = True
except ImportError:
    HAS_MPLFINANCE = False

# ── Atlas Chart Theme ────────────────────────────────────
THEME = {
    "bg": "#f2f2f7",            # Apple: systemGroupedBackground
    "bg_card": "#ffffff",        # Apple: white card
    "bullish": "#34C759",        # Apple: systemGreen
    "bearish": "#FF3B30",        # Apple: systemRed
    "text": "#1d1d1f",           # Apple: label
    "text_dim": "#86868b",       # Apple: secondaryLabel
    "grid": "#e5e5ea",           # Apple: systemGray5
    "entry": "#007AFF",          # Apple: systemBlue
    "sl": "#FF3B30",             # Apple: systemRed
    "tp": "#34C759",             # Apple: systemGreen
    "tp_max": "#FF9500",         # Apple: systemOrange
    "ema_fast": "#007AFF",       # Apple: systemBlue (EMA 2)
    "ema_slow": "#AF52DE",       # Apple: systemPurple (EMA 5)
    "current_price": "#1d1d1f",  # Dark text on light bg
    "info_box_bg": "#ffffffee",  # White semi-transparent
    "info_box_border": "#e5e5ea",
}


class TradeScreenshotGenerator:
    """
    Generates candlestick chart screenshots for trade documentation.
    Screenshots are saved at trade open and trade close, capturing the
    market context around each trade execution.
    """

    def __init__(self, data_dir: str = "data/screenshots"):
        self._data_dir = data_dir
        os.makedirs(self._data_dir, exist_ok=True)

    # ── Public API ────────────────────────────────────────────────

    async def capture_trade_open(
        self,
        trade_id: str,
        instrument: str,
        direction: str,
        entry_price: float,
        sl: float,
        tp1: float,
        tp_max: float | None,
        strategy: str,
        confidence: float,
        candles: list[dict] | None = None,
        ema_values: dict | None = None,
    ) -> str:
        """
        Generate screenshot when trade opens. Returns file path.

        Args:
            trade_id: Unique trade identifier.
            instrument: Trading instrument symbol (e.g. 'EURUSD').
            direction: 'BUY' or 'SELL'.
            entry_price: Trade entry price.
            sl: Stop loss price.
            tp1: Take profit 1 price.
            tp_max: Maximum take profit (optional).
            strategy: Strategy name that triggered the trade.
            confidence: Signal confidence score (0-1).
            candles: List of OHLC candle dicts with keys:
                     {time, open, high, low, close, volume?}.
            ema_values: Dict with optional keys 'ema2' and 'ema5',
                        each a list of float values aligned to candles.

        Returns:
            File path to the saved screenshot, or empty string on failure.
        """
        if not HAS_MATPLOTLIB:
            logger.warning("Cannot capture trade screenshot - matplotlib not installed")
            return ""

        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"{instrument}_{trade_id}_open_{timestamp}.png"
            filepath = os.path.join(self._data_dir, filename)

            # Calculate risk:reward ratio
            risk = abs(entry_price - sl)
            reward = abs(tp1 - entry_price)
            rr_ratio = round(reward / risk, 2) if risk > 0 else 0.0

            trade_info = {
                "instrument": instrument,
                "direction": direction,
                "strategy": strategy,
                "entry": entry_price,
                "sl": sl,
                "tp1": tp1,
                "tp_max": tp_max,
                "rr": rr_ratio,
                "confidence": confidence,
                "event": "OPEN",
                "timestamp": timestamp,
            }

            levels = {
                "entry": entry_price,
                "sl": sl,
                "tp1": tp1,
                "tp_max": tp_max,
                "current_price": entry_price,
            }

            if candles and len(candles) > 0:
                self._generate_candlestick_chart(
                    filepath, candles, levels, trade_info, ema_values
                )
            else:
                self._generate_info_card(filepath, trade_info)

            logger.info(
                f"Trade screenshot saved: {filepath} "
                f"({instrument} {direction} OPEN)"
            )
            return filepath

        except Exception as e:
            logger.error(f"Failed to generate trade open screenshot: {e}")
            return ""

    async def capture_trade_close(
        self,
        trade_id: str,
        instrument: str,
        direction: str,
        entry_price: float,
        close_price: float,
        pnl_pct: float,
        result: str,
        candles: list[dict] | None = None,
    ) -> str:
        """
        Generate screenshot when trade closes. Returns file path.

        Args:
            trade_id: Unique trade identifier.
            instrument: Trading instrument symbol.
            direction: 'BUY' or 'SELL'.
            entry_price: Original entry price.
            close_price: Price at which the trade was closed.
            pnl_pct: Profit/loss percentage.
            result: Trade result string (e.g. 'TP', 'SL', 'BE').
            candles: List of OHLC candle dicts.

        Returns:
            File path to the saved screenshot, or empty string on failure.
        """
        if not HAS_MATPLOTLIB:
            logger.warning("Cannot capture trade screenshot - matplotlib not installed")
            return ""

        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"{instrument}_{trade_id}_close_{timestamp}.png"
            filepath = os.path.join(self._data_dir, filename)

            # Determine result color for the header
            if pnl_pct > 0:
                result_color = THEME["bullish"]
            elif pnl_pct < 0:
                result_color = THEME["bearish"]
            else:
                result_color = THEME["text_dim"]

            pnl_sign = "+" if pnl_pct >= 0 else ""

            trade_info = {
                "instrument": instrument,
                "direction": direction,
                "strategy": "",
                "entry": entry_price,
                "close_price": close_price,
                "pnl_pct": pnl_pct,
                "pnl_display": f"{pnl_sign}{pnl_pct:.2f}%",
                "result": result,
                "result_color": result_color,
                "event": "CLOSE",
                "timestamp": timestamp,
            }

            levels = {
                "entry": entry_price,
                "current_price": close_price,
            }

            if candles and len(candles) > 0:
                self._generate_candlestick_chart(
                    filepath, candles, levels, trade_info, ema_values=None
                )
            else:
                self._generate_info_card(filepath, trade_info)

            logger.info(
                f"Trade screenshot saved: {filepath} "
                f"({instrument} {direction} CLOSE {result} {pnl_sign}{pnl_pct:.2f}%)"
            )
            return filepath

        except Exception as e:
            logger.error(f"Failed to generate trade close screenshot: {e}")
            return ""

    def get_screenshot_path(self, trade_id: str) -> list[str]:
        """
        Get all screenshot file paths for a given trade.

        Args:
            trade_id: The trade identifier to search for.

        Returns:
            List of absolute file paths matching the trade_id.
        """
        paths = []
        if not os.path.isdir(self._data_dir):
            return paths

        for filename in sorted(os.listdir(self._data_dir)):
            if trade_id in filename and filename.endswith(".png"):
                paths.append(os.path.join(self._data_dir, filename))

        return paths

    # ── Chart Generation (Candlestick) ────────────────────────────

    def _generate_candlestick_chart(
        self,
        filepath: str,
        candles: list[dict],
        levels: dict,
        trade_info: dict,
        ema_values: dict | None = None,
    ):
        """Render a full candlestick chart with trade levels and overlays."""
        # Limit to last 50-100 candles
        candles = candles[-100:]

        fig, ax = plt.subplots(1, 1, figsize=(14, 8), facecolor=THEME["bg"])
        try:
            self._render_candlestick_inner(fig, ax, filepath, candles, levels, trade_info, ema_values)
        finally:
            plt.close(fig)

    def _render_candlestick_inner(
        self,
        fig,
        ax,
        filepath: str,
        candles: list[dict],
        levels: dict,
        trade_info: dict,
        ema_values: dict | None = None,
    ):
        ax.set_facecolor(THEME["bg"])

        # Draw candlesticks
        self._draw_candlesticks(ax, candles)

        # Draw EMA overlays
        if ema_values:
            self._draw_ema_overlays(ax, candles, ema_values)

        # Draw horizontal trade levels
        self._draw_trade_levels(ax, levels, len(candles))

        # Draw current price marker
        current_price = levels.get("current_price")
        if current_price is not None:
            ax.axhline(
                y=current_price,
                color=THEME["current_price"],
                linewidth=1.0,
                linestyle=":",
                alpha=0.5,
            )
            ax.plot(
                len(candles) - 1,
                current_price,
                marker="D",
                color=THEME["current_price"],
                markersize=7,
                zorder=10,
            )

        # Trade info text box
        self._draw_trade_info_box(ax, trade_info, len(candles))

        # Chart title
        event = trade_info.get("event", "")
        instrument = trade_info.get("instrument", "")
        direction = trade_info.get("direction", "")

        if event == "CLOSE":
            result = trade_info.get("result", "")
            pnl_display = trade_info.get("pnl_display", "")
            result_color = trade_info.get("result_color", THEME["text"])
            title = f"{instrument}  {direction}  {event}"
            ax.set_title(title, color=THEME["text"], fontsize=16, fontweight="bold",
                         pad=15, loc="left")
            # Add result badge on the right side of the title
            ax.text(
                0.98, 1.02, f"  {result}  {pnl_display}  ",
                transform=ax.transAxes,
                fontsize=14, fontweight="bold",
                color=result_color,
                ha="right", va="bottom",
                bbox=dict(
                    boxstyle="round,pad=0.3",
                    facecolor=THEME["bg_card"],
                    edgecolor=result_color,
                    alpha=0.9,
                ),
            )
        else:
            title = f"{instrument}  {direction}  {event}"
            ax.set_title(title, color=THEME["text"], fontsize=16, fontweight="bold",
                         pad=15, loc="left")

        # Axis styling
        ax.tick_params(axis="both", colors=THEME["text_dim"], labelsize=9)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_color(THEME["grid"])
        ax.spines["left"].set_color(THEME["grid"])
        ax.grid(True, color=THEME["grid"], linewidth=0.5, alpha=0.6)

        # X-axis: show time labels if available
        time_labels = self._extract_time_labels(candles)
        if time_labels:
            step = max(1, len(time_labels) // 10)
            tick_positions = list(range(0, len(time_labels), step))
            ax.set_xticks(tick_positions)
            ax.set_xticklabels(
                [time_labels[i] for i in tick_positions],
                rotation=45, ha="right", fontsize=8,
            )
        else:
            ax.set_xlabel("Candles", color=THEME["text_dim"], fontsize=9)

        ax.set_ylabel("Price", color=THEME["text_dim"], fontsize=10)

        # Timestamp watermark
        ts = trade_info.get("timestamp", "")
        ax.text(
            0.99, 0.01, f"Atlas  |  {ts} UTC",
            transform=ax.transAxes, fontsize=7,
            color=THEME["text_dim"], alpha=0.5,
            ha="right", va="bottom",
        )

        plt.tight_layout()
        fig.savefig(filepath, dpi=150, facecolor=THEME["bg"], bbox_inches="tight")

    def _draw_candlesticks(self, ax, candles: list[dict]):
        """Draw OHLC candlesticks on the axes."""
        for i, c in enumerate(candles):
            o = c.get("open", 0)
            h = c.get("high", 0)
            l = c.get("low", 0)  # noqa: E741
            cl = c.get("close", 0)

            is_bullish = cl >= o
            color = THEME["bullish"] if is_bullish else THEME["bearish"]

            # Wick (high-low line)
            ax.plot(
                [i, i], [l, h],
                color=color, linewidth=0.8, zorder=3,
            )

            # Body (open-close rectangle)
            body_bottom = min(o, cl)
            body_height = abs(cl - o)
            if body_height < (h - l) * 0.005:
                # Doji or near-doji: draw a thin line
                body_height = (h - l) * 0.005 if (h - l) > 0 else 0.0001

            rect = plt.Rectangle(
                (i - 0.35, body_bottom),
                0.7,
                body_height,
                facecolor=color if is_bullish else THEME["bg"],
                edgecolor=color,
                linewidth=0.8,
                zorder=4,
            )
            ax.add_patch(rect)

    def _draw_ema_overlays(self, ax, candles: list[dict], ema_values: dict):
        """Draw EMA lines overlaying the candlestick chart."""
        n = len(candles)
        xs = list(range(n))

        ema2 = ema_values.get("ema2")
        ema5 = ema_values.get("ema5")

        if ema2 and len(ema2) > 0:
            # Align to candle count (take last n values)
            vals = ema2[-n:]
            x_offset = n - len(vals)
            ax.plot(
                [x_offset + j for j in range(len(vals))],
                vals,
                color=THEME["ema_fast"],
                linewidth=1.2,
                alpha=0.8,
                label="EMA 2",
                zorder=5,
            )

        if ema5 and len(ema5) > 0:
            vals = ema5[-n:]
            x_offset = n - len(vals)
            ax.plot(
                [x_offset + j for j in range(len(vals))],
                vals,
                color=THEME["ema_slow"],
                linewidth=1.2,
                alpha=0.8,
                label="EMA 5",
                zorder=5,
            )

        # Add legend for EMAs
        if (ema2 and len(ema2) > 0) or (ema5 and len(ema5) > 0):
            legend = ax.legend(
                loc="upper left",
                fontsize=8,
                framealpha=0.7,
                facecolor=THEME["bg_card"],
                edgecolor=THEME["grid"],
                labelcolor=THEME["text_dim"],
            )
            legend.get_frame().set_linewidth(0.5)

    def _draw_trade_levels(self, ax, levels: dict, num_candles: int):
        """Draw horizontal lines for entry, SL, TP1, TP max."""
        line_configs = [
            ("entry", THEME["entry"], "Entry", 1.5),
            ("sl", THEME["sl"], "SL", 1.3),
            ("tp1", THEME["tp"], "TP1", 1.3),
            ("tp_max", THEME["tp_max"], "TP Max", 1.0),
        ]

        for key, color, label, lw in line_configs:
            price = levels.get(key)
            if price is None:
                continue

            ax.axhline(
                y=price,
                color=color,
                linewidth=lw,
                linestyle="--",
                alpha=0.85,
                zorder=6,
            )

            # Price label on the right edge
            ax.text(
                num_candles + 0.5,
                price,
                f" {label}: {price:.5g}",
                color=color,
                fontsize=8,
                fontweight="bold",
                va="center",
                ha="left",
                zorder=7,
                bbox=dict(
                    boxstyle="round,pad=0.15",
                    facecolor=THEME["bg"],
                    edgecolor=color,
                    alpha=0.85,
                ),
            )

    def _draw_trade_info_box(self, ax, trade_info: dict, num_candles: int):
        """Draw a text box with trade information in the upper-right area."""
        event = trade_info.get("event", "")

        if event == "OPEN":
            lines = [
                f"Strategy: {trade_info.get('strategy', 'N/A')}",
                f"Direction: {trade_info.get('direction', 'N/A')}",
                f"Entry: {trade_info.get('entry', 0):.5g}",
                f"SL: {trade_info.get('sl', 0):.5g}",
                f"TP1: {trade_info.get('tp1', 0):.5g}",
            ]
            tp_max = trade_info.get("tp_max")
            if tp_max is not None:
                lines.append(f"TP Max: {tp_max:.5g}")
            lines.append(f"R:R  {trade_info.get('rr', 0):.2f}")
            lines.append(f"Confidence: {trade_info.get('confidence', 0):.0%}")
        elif event == "CLOSE":
            lines = [
                f"Direction: {trade_info.get('direction', 'N/A')}",
                f"Entry: {trade_info.get('entry', 0):.5g}",
                f"Close: {trade_info.get('close_price', 0):.5g}",
                f"Result: {trade_info.get('result', 'N/A')}",
                f"P&L: {trade_info.get('pnl_display', 'N/A')}",
            ]
        else:
            lines = []

        if not lines:
            return

        text = "\n".join(lines)

        ax.text(
            0.02, 0.97,
            text,
            transform=ax.transAxes,
            fontsize=9,
            fontfamily="monospace",
            color=THEME["text"],
            va="top",
            ha="left",
            zorder=10,
            bbox=dict(
                boxstyle="round,pad=0.6",
                facecolor=THEME["info_box_bg"],
                edgecolor=THEME["info_box_border"],
                linewidth=1.0,
            ),
        )

    def _extract_time_labels(self, candles: list[dict]) -> list[str]:
        """Extract formatted time labels from candle data."""
        labels = []
        for c in candles:
            t = c.get("time") or c.get("timestamp") or c.get("datetime")
            if t is None:
                return []  # No time data available

            if isinstance(t, (int, float)):
                # Unix timestamp
                try:
                    dt = datetime.fromtimestamp(t, tz=timezone.utc)
                    labels.append(dt.strftime("%H:%M"))
                except (ValueError, OSError):
                    return []
            elif isinstance(t, str):
                # Try to parse ISO format
                try:
                    dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
                    labels.append(dt.strftime("%H:%M"))
                except ValueError:
                    labels.append(t[-5:] if len(t) >= 5 else t)
            elif isinstance(t, datetime):
                labels.append(t.strftime("%H:%M"))
            else:
                return []

        return labels

    # ── Info Card (fallback when no candle data) ──────────────────

    def _generate_info_card(self, filepath: str, trade_info: dict):
        """Generate a simple info card when candle data is not available."""
        fig, ax = plt.subplots(1, 1, figsize=(10, 6), facecolor=THEME["bg"])
        try:
            self._render_info_card_inner(fig, ax, filepath, trade_info)
        finally:
            plt.close(fig)

    def _render_info_card_inner(self, fig, ax, filepath: str, trade_info: dict):
        ax.set_facecolor(THEME["bg"])
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 10)
        ax.axis("off")

        event = trade_info.get("event", "TRADE")
        instrument = trade_info.get("instrument", "N/A")
        direction = trade_info.get("direction", "N/A")

        # Header
        if event == "CLOSE":
            result = trade_info.get("result", "")
            pnl_display = trade_info.get("pnl_display", "")
            result_color = trade_info.get("result_color", THEME["text"])
            header = f"{instrument}  {direction}  {event}"
            ax.text(
                5, 9.0, header,
                fontsize=22, fontweight="bold",
                color=THEME["text"], ha="center", va="center",
            )
            ax.text(
                5, 8.0, f"{result}  {pnl_display}",
                fontsize=20, fontweight="bold",
                color=result_color, ha="center", va="center",
            )
        else:
            header = f"{instrument}  {direction}  {event}"
            ax.text(
                5, 9.0, header,
                fontsize=22, fontweight="bold",
                color=THEME["text"], ha="center", va="center",
            )

        # Build detail lines
        detail_lines = []
        if event == "OPEN":
            detail_lines = [
                f"Strategy:    {trade_info.get('strategy', 'N/A')}",
                f"Entry:       {trade_info.get('entry', 0):.5g}",
                f"Stop Loss:   {trade_info.get('sl', 0):.5g}",
                f"TP1:         {trade_info.get('tp1', 0):.5g}",
            ]
            tp_max = trade_info.get("tp_max")
            if tp_max is not None:
                detail_lines.append(f"TP Max:      {tp_max:.5g}")
            detail_lines.extend([
                f"R:R:         {trade_info.get('rr', 0):.2f}",
                f"Confidence:  {trade_info.get('confidence', 0):.0%}",
            ])
        elif event == "CLOSE":
            detail_lines = [
                f"Entry:       {trade_info.get('entry', 0):.5g}",
                f"Close:       {trade_info.get('close_price', 0):.5g}",
                f"Result:      {trade_info.get('result', 'N/A')}",
                f"P&L:         {trade_info.get('pnl_display', 'N/A')}",
            ]

        details = "\n".join(detail_lines)
        ax.text(
            5, 4.5, details,
            fontsize=14, fontfamily="monospace",
            color=THEME["text"], ha="center", va="center",
            bbox=dict(
                boxstyle="round,pad=1.0",
                facecolor=THEME["bg_card"],
                edgecolor=THEME["info_box_border"],
                linewidth=1.5,
            ),
        )

        # Decorative border
        border = plt.Rectangle(
            (0.3, 0.3), 9.4, 9.4,
            fill=False,
            edgecolor=THEME["entry"],
            linewidth=2.0,
            linestyle="--",
            alpha=0.3,
        )
        ax.add_patch(border)

        # Watermark
        ts = trade_info.get("timestamp", "")
        ax.text(
            5, 0.7, f"Atlas  |  {ts} UTC  |  No chart data available",
            fontsize=8, color=THEME["text_dim"], alpha=0.5,
            ha="center", va="center",
        )

        fig.savefig(filepath, dpi=150, facecolor=THEME["bg"], bbox_inches="tight")
