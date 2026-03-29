"""
NeonTrade AI - Database Models
SQLite models using aiosqlite for async trade history,
analysis logs, pending approvals, and daily stats.
"""

import json
import uuid
import aiosqlite
from datetime import datetime, timezone
from typing import Dict, List, Optional
from loguru import logger


class TradeDatabase:
    """Async SQLite database for NeonTrade AI trade tracking."""

    def __init__(self, db_path: str = "data/neontrade.db"):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    # ── Connection Management ─────────────────────────────────────

    async def initialize(self):
        """Create tables if they don't exist and open connection."""
        import os
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)

        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")

        await self._create_tables()
        logger.info(f"Database initialized: {self.db_path}")

    async def _create_tables(self):
        """Create all required tables."""
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                id TEXT PRIMARY KEY,
                instrument TEXT NOT NULL,
                strategy TEXT,
                strategy_variant TEXT,
                direction TEXT NOT NULL CHECK(direction IN ('BUY', 'SELL')),
                units INTEGER NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL,
                stop_loss REAL NOT NULL,
                take_profit REAL NOT NULL,
                pnl REAL,
                pnl_pips REAL,
                status TEXT NOT NULL DEFAULT 'open'
                    CHECK(status IN ('open', 'closed_tp', 'closed_sl', 'closed_manual', 'closed_be')),
                mode TEXT NOT NULL DEFAULT 'AUTO' CHECK(mode IN ('AUTO', 'MANUAL')),
                confidence REAL,
                risk_reward_ratio REAL,
                reasoning TEXT,
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                notes TEXT,
                ai_analysis TEXT
            );

            CREATE TABLE IF NOT EXISTS analysis_log (
                id TEXT PRIMARY KEY,
                instrument TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                htf_trend TEXT,
                ltf_trend TEXT,
                convergence INTEGER DEFAULT 0,
                score REAL,
                strategy_detected TEXT,
                explanation_json TEXT
            );

            CREATE TABLE IF NOT EXISTS pending_approvals (
                id TEXT PRIMARY KEY,
                instrument TEXT NOT NULL,
                strategy TEXT,
                direction TEXT NOT NULL CHECK(direction IN ('BUY', 'SELL')),
                entry_price REAL NOT NULL,
                stop_loss REAL NOT NULL,
                take_profit REAL NOT NULL,
                confidence REAL,
                reasoning TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending', 'approved', 'rejected', 'expired')),
                created_at TEXT NOT NULL,
                resolved_at TEXT
            );

            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                total_trades INTEGER DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,
                losing_trades INTEGER DEFAULT 0,
                total_pnl REAL DEFAULT 0.0,
                total_pips REAL DEFAULT 0.0,
                max_drawdown REAL DEFAULT 0.0,
                best_trade_pnl REAL DEFAULT 0.0,
                worst_trade_pnl REAL DEFAULT 0.0
            );

            CREATE TABLE IF NOT EXISTS equity_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                balance REAL NOT NULL,
                equity REAL NOT NULL,
                unrealized_pnl REAL DEFAULT 0.0,
                open_positions INTEGER DEFAULT 0,
                total_risk REAL DEFAULT 0.0
            );

            CREATE INDEX IF NOT EXISTS idx_equity_snapshots_timestamp ON equity_snapshots(timestamp);

            CREATE INDEX IF NOT EXISTS idx_trades_instrument ON trades(instrument);
            CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
            CREATE INDEX IF NOT EXISTS idx_trades_opened_at ON trades(opened_at);
            CREATE INDEX IF NOT EXISTS idx_analysis_instrument ON analysis_log(instrument);
            CREATE INDEX IF NOT EXISTS idx_analysis_timestamp ON analysis_log(timestamp);
            CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_approvals(status);
        """)
        await self._db.commit()

    async def close(self):
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("Database connection closed")

    # ── Trade Operations ──────────────────────────────────────────

    async def record_trade(self, trade_data: dict) -> str:
        """
        Insert a new trade record.

        trade_data should contain: instrument, strategy, strategy_variant,
        direction, units, entry_price, stop_loss, take_profit, mode,
        confidence, risk_reward_ratio, reasoning.
        Returns the trade ID.
        """
        trade_id = trade_data.get("id", str(uuid.uuid4()))
        now = datetime.now(timezone.utc).isoformat()

        await self._db.execute(
            """
            INSERT INTO trades (
                id, instrument, strategy, strategy_variant, direction,
                units, entry_price, stop_loss, take_profit,
                status, mode, confidence, risk_reward_ratio, reasoning,
                opened_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade_id,
                trade_data["instrument"],
                trade_data.get("strategy"),
                trade_data.get("strategy_variant"),
                trade_data["direction"],
                trade_data["units"],
                trade_data["entry_price"],
                trade_data["stop_loss"],
                trade_data["take_profit"],
                trade_data.get("status", "open"),
                trade_data.get("mode", "AUTO"),
                trade_data.get("confidence"),
                trade_data.get("risk_reward_ratio"),
                trade_data.get("reasoning"),
                trade_data.get("opened_at", now),
            ),
        )
        await self._db.commit()
        logger.info(f"Trade recorded: {trade_id} | {trade_data['instrument']} {trade_data['direction']}")
        return trade_id

    async def update_trade(self, trade_id: str, updates: dict) -> bool:
        """
        Update an existing trade (e.g., close it, set exit_price, pnl).

        updates can contain any column name as key.
        Returns True if a row was updated.
        """
        if not updates:
            return False

        allowed_columns = {
            "exit_price", "pnl", "pnl_pips", "status", "closed_at",
            "stop_loss", "take_profit", "notes", "ai_analysis",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed_columns}
        if not filtered:
            return False

        set_clause = ", ".join(f"{col} = ?" for col in filtered)
        values = list(filtered.values()) + [trade_id]

        cursor = await self._db.execute(
            f"UPDATE trades SET {set_clause} WHERE id = ?",
            values,
        )
        await self._db.commit()
        updated = cursor.rowcount > 0
        if updated:
            logger.info(f"Trade updated: {trade_id} | {filtered}")
        return updated

    async def get_trade_history(
        self,
        limit: int = 50,
        offset: int = 0,
        instrument: Optional[str] = None,
        strategy: Optional[str] = None,
    ) -> List[dict]:
        """Query trade history with optional filters."""
        query = "SELECT * FROM trades WHERE 1=1"
        params = []

        if instrument:
            query += " AND instrument = ?"
            params.append(instrument)
        if strategy:
            query += " AND strategy = ?"
            params.append(strategy)

        query += " ORDER BY opened_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_trades_between(self, start_iso: str, end_iso: str) -> list:
        """Get trades between two ISO datetime strings."""
        # Bug fix R27: use self._db instead of opening separate connection
        # (avoids WAL bypass and potential locking issues)
        cursor = await self._db.execute(
            "SELECT * FROM trades WHERE opened_at >= ? AND opened_at <= ? ORDER BY opened_at",
            (start_iso, end_iso),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # ── Daily Stats ───────────────────────────────────────────────

    async def get_daily_stats(self, date: str) -> dict:
        """
        Get or calculate daily stats for a given date (YYYY-MM-DD).
        If stats don't exist yet, calculate from trades.
        """
        # Check if stats already exist
        cursor = await self._db.execute(
            "SELECT * FROM daily_stats WHERE date = ?", (date,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)

        # Calculate from trades closed on that date
        cursor = await self._db.execute(
            """
            SELECT
                COUNT(*) as total_trades,
                COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0) as winning_trades,
                COALESCE(SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END), 0) as losing_trades,
                COALESCE(SUM(pnl), 0.0) as total_pnl,
                COALESCE(SUM(pnl_pips), 0.0) as total_pips,
                COALESCE(MAX(pnl), 0.0) as best_trade_pnl,
                COALESCE(MIN(pnl), 0.0) as worst_trade_pnl
            FROM trades
            WHERE closed_at LIKE ? AND status != 'open'
            """,
            (f"{date}%",),
        )
        row = await cursor.fetchone()
        stats = dict(row) if row else {}

        # Calculate max drawdown (running sum of pnl, find largest drop)
        cursor = await self._db.execute(
            """
            SELECT pnl FROM trades
            WHERE closed_at LIKE ? AND status != 'open'
            ORDER BY closed_at ASC
            """,
            (f"{date}%",),
        )
        pnl_rows = await cursor.fetchall()
        max_drawdown = 0.0
        running_sum = 0.0
        peak = 0.0
        for r in pnl_rows:
            pnl_val = r["pnl"] or 0.0
            running_sum += pnl_val
            if running_sum > peak:
                peak = running_sum
            drawdown = peak - running_sum
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        result = {
            "date": date,
            "total_trades": stats.get("total_trades", 0),
            "winning_trades": stats.get("winning_trades", 0),
            "losing_trades": stats.get("losing_trades", 0),
            "total_pnl": stats.get("total_pnl", 0.0),
            "total_pips": stats.get("total_pips", 0.0),
            "max_drawdown": max_drawdown,
            "best_trade_pnl": stats.get("best_trade_pnl", 0.0),
            "worst_trade_pnl": stats.get("worst_trade_pnl", 0.0),
        }

        # Persist calculated stats
        if result["total_trades"] > 0:
            await self._db.execute(
                """
                INSERT OR REPLACE INTO daily_stats
                    (date, total_trades, winning_trades, losing_trades,
                     total_pnl, total_pips, max_drawdown, best_trade_pnl, worst_trade_pnl)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    date,
                    result["total_trades"],
                    result["winning_trades"],
                    result["losing_trades"],
                    result["total_pnl"],
                    result["total_pips"],
                    result["max_drawdown"],
                    result["best_trade_pnl"],
                    result["worst_trade_pnl"],
                ),
            )
            await self._db.commit()

        return result

    async def get_performance_summary(self, days: int = 30) -> dict:
        """Get overall performance summary for the last N days."""
        from datetime import timedelta

        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        cursor = await self._db.execute(
            """
            SELECT
                COUNT(*) as total_trades,
                COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0) as winning_trades,
                COALESCE(SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END), 0) as losing_trades,
                COALESCE(SUM(CASE WHEN pnl = 0 THEN 1 ELSE 0 END), 0) as breakeven_trades,
                COALESCE(SUM(pnl), 0.0) as total_pnl,
                COALESCE(SUM(pnl_pips), 0.0) as total_pips,
                COALESCE(AVG(pnl), 0.0) as avg_pnl,
                COALESCE(AVG(CASE WHEN pnl > 0 THEN pnl END), 0.0) as avg_win,
                COALESCE(AVG(CASE WHEN pnl < 0 THEN pnl END), 0.0) as avg_loss,
                COALESCE(MAX(pnl), 0.0) as best_trade,
                COALESCE(MIN(pnl), 0.0) as worst_trade,
                COALESCE(AVG(risk_reward_ratio), 0.0) as avg_rr
            FROM trades
            WHERE opened_at >= ? AND status != 'open'
            """,
            (start_date.isoformat(),),
        )
        row = await cursor.fetchone()
        data = dict(row) if row else {}

        total = data.get("total_trades", 0)
        wins = data.get("winning_trades", 0)
        win_rate = (wins / total * 100) if total > 0 else 0.0

        # Strategy breakdown
        cursor = await self._db.execute(
            """
            SELECT strategy,
                   COUNT(*) as count,
                   SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                   COALESCE(SUM(pnl), 0) as pnl
            FROM trades
            WHERE opened_at >= ? AND status != 'open'
            GROUP BY strategy
            """,
            (start_date.isoformat(),),
        )
        strategy_rows = await cursor.fetchall()
        by_strategy = {
            row["strategy"]: {
                "count": row["count"],
                "wins": row["wins"],
                "pnl": row["pnl"],
                "win_rate": (row["wins"] / row["count"] * 100) if row["count"] > 0 else 0,
            }
            for row in strategy_rows
        }

        # Instrument breakdown
        cursor = await self._db.execute(
            """
            SELECT instrument,
                   COUNT(*) as count,
                   SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                   COALESCE(SUM(pnl), 0) as pnl
            FROM trades
            WHERE opened_at >= ? AND status != 'open'
            GROUP BY instrument
            ORDER BY pnl DESC
            LIMIT 10
            """,
            (start_date.isoformat(),),
        )
        instrument_rows = await cursor.fetchall()
        by_instrument = {
            row["instrument"]: {
                "count": row["count"],
                "wins": row["wins"],
                "pnl": row["pnl"],
            }
            for row in instrument_rows
        }

        return {
            "period_days": days,
            "total_trades": total,
            "winning_trades": wins,
            "losing_trades": data.get("losing_trades", 0),
            "breakeven_trades": data.get("breakeven_trades", 0),
            "win_rate": round(win_rate, 2),
            "total_pnl": data.get("total_pnl", 0.0),
            "total_pips": data.get("total_pips", 0.0),
            "avg_pnl_per_trade": data.get("avg_pnl", 0.0),
            "avg_win": data.get("avg_win", 0.0),
            "avg_loss": data.get("avg_loss", 0.0),
            "best_trade": data.get("best_trade", 0.0),
            "worst_trade": data.get("worst_trade", 0.0),
            "avg_risk_reward": data.get("avg_rr", 0.0),
            "by_strategy": by_strategy,
            "by_instrument": by_instrument,
        }

    # ── Analysis Log ──────────────────────────────────────────────

    async def record_analysis(self, analysis_data: dict) -> str:
        """Log a market analysis."""
        analysis_id = analysis_data.get("id", str(uuid.uuid4()))

        explanation_json = analysis_data.get("explanation_json")
        if isinstance(explanation_json, dict):
            explanation_json = json.dumps(explanation_json, ensure_ascii=False)

        await self._db.execute(
            """
            INSERT INTO analysis_log (
                id, instrument, timestamp, htf_trend, ltf_trend,
                convergence, score, strategy_detected, explanation_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis_id,
                analysis_data["instrument"],
                analysis_data.get("timestamp", datetime.now(timezone.utc).isoformat()),
                analysis_data.get("htf_trend"),
                analysis_data.get("ltf_trend"),
                1 if analysis_data.get("convergence") else 0,
                analysis_data.get("score"),
                analysis_data.get("strategy_detected"),
                explanation_json,
            ),
        )
        await self._db.commit()
        return analysis_id

    # ── Pending Approvals ─────────────────────────────────────────

    async def add_pending_approval(self, setup: dict) -> str:
        """Add a pending setup for manual approval."""
        setup_id = setup.get("id", str(uuid.uuid4()))
        now = datetime.now(timezone.utc).isoformat()

        await self._db.execute(
            """
            INSERT INTO pending_approvals (
                id, instrument, strategy, direction, entry_price,
                stop_loss, take_profit, confidence, reasoning,
                status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                setup_id,
                setup["instrument"],
                setup.get("strategy"),
                setup["direction"],
                setup["entry_price"],
                setup["stop_loss"],
                setup["take_profit"],
                setup.get("confidence"),
                setup.get("reasoning"),
                "pending",
                setup.get("created_at", now),
            ),
        )
        await self._db.commit()
        logger.info(f"Pending approval added: {setup_id} | {setup['instrument']} {setup['direction']}")
        return setup_id

    async def resolve_pending(self, setup_id: str, status: str) -> bool:
        """Approve or reject a pending setup."""
        if status not in ("approved", "rejected", "expired"):
            logger.warning(f"Invalid resolve status: {status}")
            return False

        now = datetime.now(timezone.utc).isoformat()
        cursor = await self._db.execute(
            """
            UPDATE pending_approvals
            SET status = ?, resolved_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (status, now, setup_id),
        )
        await self._db.commit()
        resolved = cursor.rowcount > 0
        if resolved:
            logger.info(f"Pending setup {setup_id} -> {status}")
        return resolved

    async def get_pending_approvals(self) -> List[dict]:
        """Get all pending (unresolved) approval setups."""
        cursor = await self._db.execute(
            """
            SELECT * FROM pending_approvals
            WHERE status = 'pending'
            ORDER BY created_at DESC
            """
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # ── Equity Snapshots ─────────────────────────────────────────

    async def record_equity_snapshot(
        self,
        balance: float,
        equity: float,
        unrealized_pnl: float = 0.0,
        open_positions: int = 0,
        total_risk: float = 0.0,
    ) -> None:
        """Insert an equity snapshot for tracking the equity curve."""
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            """
            INSERT INTO equity_snapshots
                (timestamp, balance, equity, unrealized_pnl, open_positions, total_risk)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (now, balance, equity, unrealized_pnl, open_positions, total_risk),
        )
        await self._db.commit()
        logger.debug(f"Equity snapshot recorded: balance={balance}, equity={equity}")

    async def get_equity_curve(self, days: int = 30) -> List[dict]:
        """Return equity snapshots for the last N days."""
        from datetime import timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cursor = await self._db.execute(
            """
            SELECT * FROM equity_snapshots
            WHERE timestamp >= ?
            ORDER BY timestamp ASC
            """,
            (cutoff,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # ── Data Retention ───────────────────────────────────────────

    async def cleanup_old_data(self, days: int = 90):
        """Delete analysis_log and equity_snapshots older than N days."""
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        await self._db.execute(
            "DELETE FROM analysis_log WHERE timestamp < ?", (cutoff,)
        )
        await self._db.execute(
            "DELETE FROM equity_snapshots WHERE timestamp < ?", (cutoff,)
        )
        await self._db.commit()
        logger.info(f"Cleaned up analysis_log and equity_snapshots older than {days} days")

    # ── Trade Notes ──────────────────────────────────────────────

    async def update_trade_notes(self, trade_id: str, notes: str) -> bool:
        """Update the notes field for a specific trade."""
        cursor = await self._db.execute(
            "UPDATE trades SET notes = ? WHERE id = ?",
            (notes, trade_id),
        )
        await self._db.commit()
        updated = cursor.rowcount > 0
        if updated:
            logger.info(f"Trade notes updated: {trade_id}")
        return updated
