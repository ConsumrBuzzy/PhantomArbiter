"""
V39.9: Dynamic Live Strategy Selector
=====================================
Automatically selects the best-performing engine for live trading
based on historical performance from trading_journal.db.

Selection Criteria (Priority Order):
1. Minimum 10 trades
2. Total PnL > 0
3. Win Rate > 50%
4. Highest Total PnL wins
"""

import sqlite3
import os
from src.shared.system.logging import Logger

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
    "trading_journal.db",
)

MIN_TRADES = 10
MIN_WIN_RATE = 0.50
MIN_PNL = 0.0


def select_best_strategy() -> str | None:
    """
    Query trading_journal.db and select the best-performing engine.

    Returns:
        str: Engine name ('SCALPER', 'KELTNER', 'VWAP') or None if no eligible engines.
    """
    try:
        if not os.path.exists(DB_PATH):
            Logger.warning("[SELECTOR] Database not found - no trade history")
            return None

        conn = sqlite3.connect(DB_PATH, timeout=5.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Query performance stats per engine
        cursor.execute(
            """
            SELECT 
                engine_name,
                COUNT(*) as total_trades,
                SUM(CASE WHEN is_win THEN 1 ELSE 0 END) as wins,
                SUM(pnl_usd) as total_pnl,
                CAST(SUM(CASE WHEN is_win THEN 1 ELSE 0 END) AS REAL) / COUNT(*) as win_rate
            FROM trades
            WHERE engine_name IS NOT NULL AND engine_name != 'UNKNOWN'
            GROUP BY engine_name
            HAVING 
                COUNT(*) >= ? 
                AND SUM(pnl_usd) > ?
                AND CAST(SUM(CASE WHEN is_win THEN 1 ELSE 0 END) AS REAL) / COUNT(*) > ?
            ORDER BY SUM(pnl_usd) DESC
            LIMIT 1
        """,
            (MIN_TRADES, MIN_PNL, MIN_WIN_RATE),
        )

        result = cursor.fetchone()
        conn.close()

        if result:
            engine = result["engine_name"]
            trades = result["total_trades"]
            pnl = result["total_pnl"]
            wr = result["win_rate"] * 100

            Logger.info(
                f"🏆 [SELECTOR] Winner: {engine} ({trades} trades, ${pnl:.2f} PnL, {wr:.1f}% WR)"
            )
            return engine
        else:
            Logger.warning(
                "[SELECTOR] No eligible engines (need 10+ trades, PnL>0, WR>50%)"
            )
            return None

    except Exception as e:
        Logger.error(f"[SELECTOR] Error querying database: {e}")
        return None


def get_all_engine_stats() -> list:
    """
    Get performance stats for all engines (for status reports).

    Returns:
        List of dicts with engine stats.
    """
    try:
        if not os.path.exists(DB_PATH):
            return []

        conn = sqlite3.connect(DB_PATH, timeout=5.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 
                engine_name,
                COUNT(*) as total_trades,
                SUM(CASE WHEN is_win THEN 1 ELSE 0 END) as wins,
                SUM(pnl_usd) as total_pnl,
                CAST(SUM(CASE WHEN is_win THEN 1 ELSE 0 END) AS REAL) / COUNT(*) as win_rate
            FROM trades
            WHERE engine_name IS NOT NULL AND engine_name != 'UNKNOWN'
            GROUP BY engine_name
            ORDER BY SUM(pnl_usd) DESC
        """)

        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results

    except Exception as e:
        Logger.error(f"[SELECTOR] Error getting stats: {e}")
        return []
