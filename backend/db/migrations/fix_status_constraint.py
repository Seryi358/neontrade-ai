"""
Migration: Expand trades.status CHECK constraint to include missing statuses.

Adds: closed_news, closed_tp_max, closed_emergency_exit

SQLite does not support ALTER TABLE to modify CHECK constraints, so this
migration recreates the table with the updated constraint and copies data.

Also fixes any trades stuck as 'open' that have exit_price set (should be closed).

Usage:
    python -m db.migrations.fix_status_constraint
    # or
    python backend/db/migrations/fix_status_constraint.py
"""
import asyncio
import sys
import os

# Allow running from repo root or backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import aiosqlite
from loguru import logger

# Default path matches the app's data directory
DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "atlas.db"
)

VALID_STATUSES = (
    "'open', 'closed_tp', 'closed_sl', 'closed_manual', 'closed_be', "
    "'closed_friday_sl', 'closed_friday_tp', 'closed_friday_sl+tp', "
    "'closed_funded_overnight', 'closed_news', 'closed_tp_max', 'closed_emergency_exit'"
)

CREATE_NEW_TABLE = f"""
CREATE TABLE trades_new (
    id TEXT PRIMARY KEY,
    instrument TEXT NOT NULL,
    strategy TEXT,
    strategy_variant TEXT,
    direction TEXT NOT NULL CHECK(direction IN ('BUY', 'SELL')),
    units REAL NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL,
    stop_loss REAL NOT NULL,
    take_profit REAL NOT NULL,
    pnl REAL,
    pnl_pips REAL,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK(status IN ({VALID_STATUSES})),
    mode TEXT NOT NULL DEFAULT 'AUTO' CHECK(mode IN ('AUTO', 'MANUAL')),
    confidence REAL,
    risk_reward_ratio REAL,
    reasoning TEXT,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    notes TEXT,
    ai_analysis TEXT
);
"""


async def run_migration(db_path: str = DEFAULT_DB_PATH):
    """Run the status constraint migration."""
    if not os.path.exists(db_path):
        logger.warning(f"Database not found at {db_path} -- nothing to migrate")
        return

    logger.info(f"Running status constraint migration on {db_path}")

    async with aiosqlite.connect(db_path) as db:
        # Step 0: Fix stuck trades (have exit_price but status is still 'open')
        cursor = await db.execute(
            "SELECT id, exit_price, pnl FROM trades WHERE status = 'open' AND exit_price IS NOT NULL AND exit_price > 0"
        )
        stuck_trades = await cursor.fetchall()
        if stuck_trades:
            logger.warning(f"Found {len(stuck_trades)} trades stuck as 'open' with exit_price set")
            for trade_id, exit_price, pnl in stuck_trades:
                # Determine close reason from PnL
                if pnl is not None and pnl > 0:
                    new_status = "closed_tp"
                elif pnl is not None and pnl < 0:
                    new_status = "closed_sl"
                elif pnl is not None and pnl == 0:
                    new_status = "closed_be"
                else:
                    new_status = "closed_manual"
                await db.execute(
                    "UPDATE trades SET status = ? WHERE id = ?",
                    (new_status, trade_id),
                )
                logger.info(f"  Fixed trade {trade_id}: open -> {new_status} (exit_price={exit_price}, pnl={pnl})")

        # Step 1: Create new table with expanded CHECK constraint
        await db.execute(CREATE_NEW_TABLE)

        # Step 2: Copy all data from old table to new
        await db.execute("""
            INSERT INTO trades_new
            SELECT id, instrument, strategy, strategy_variant, direction, units,
                   entry_price, exit_price, stop_loss, take_profit, pnl, pnl_pips,
                   status, mode, confidence, risk_reward_ratio, reasoning,
                   opened_at, closed_at, notes, ai_analysis
            FROM trades
        """)

        # Step 3: Drop old table
        await db.execute("DROP TABLE trades")

        # Step 4: Rename new table
        await db.execute("ALTER TABLE trades_new RENAME TO trades")

        await db.commit()

        # Verify
        cursor = await db.execute("SELECT COUNT(*) FROM trades")
        count = (await cursor.fetchone())[0]
        logger.info(f"Migration complete. {count} trades in updated table.")


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB_PATH
    asyncio.run(run_migration(db_path))
