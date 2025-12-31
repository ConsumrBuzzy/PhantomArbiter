import time
from src.shared.system.database.repositories.base import BaseRepository
from src.shared.system.logging import Logger


class TradeRepository(BaseRepository):
    """
    Handles Trade Logging, Win Rate calculation, and warm-up checks.
    """

    def init_table(self):
        """Create trades table if not exists."""
        with self.db.cursor(commit=True) as c:
            c.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                entry_price REAL,
                exit_price REAL,
                size_usd REAL,
                pnl_usd REAL,
                net_pnl_pct REAL,
                exit_reason TEXT,
                timestamp REAL,
                is_win BOOLEAN,
                engine_name TEXT DEFAULT 'UNKNOWN',
                slippage_pct REAL DEFAULT 0,
                slippage_usd REAL DEFAULT 0,
                fees_usd REAL DEFAULT 0,
                liquidity_usd REAL DEFAULT 0,
                is_volatile BOOLEAN DEFAULT 0,
                trigger_wallet TEXT
            )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)")
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp)"
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_trades_engine ON trades(engine_name)"
            )

            # V134: Migration - add trigger_wallet if missing (for existing DBs)
            try:
                c.execute("SELECT trigger_wallet FROM trades LIMIT 1")
            except Exception:
                try:
                    c.execute("ALTER TABLE trades ADD COLUMN trigger_wallet TEXT")
                    Logger.info(
                        "[DB] Migrated trades table: added trigger_wallet column"
                    )
                except Exception as e:
                    Logger.debug(f"[DB] Migration skipped: {e}")

    def log_trade(self, trade_data: dict):
        """Insert a completed trade record."""
        with self.db.cursor(commit=True) as c:
            c.execute(
                """
            INSERT INTO trades (
                symbol, entry_price, exit_price, size_usd,
                pnl_usd, net_pnl_pct, exit_reason, timestamp, is_win, engine_name,
                slippage_pct, slippage_usd, fees_usd, liquidity_usd, is_volatile, trigger_wallet
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    trade_data.get("symbol"),
                    trade_data.get("entry_price"),
                    trade_data.get("exit_price"),
                    trade_data.get("size_usd"),
                    trade_data.get("pnl_usd"),
                    trade_data.get("net_pnl_pct"),
                    trade_data.get("exit_reason"),
                    trade_data.get("timestamp", time.time()),
                    trade_data.get("is_win", False),
                    trade_data.get("engine_name", "UNKNOWN"),
                    trade_data.get("slippage_pct", 0),
                    trade_data.get("slippage_usd", 0),
                    trade_data.get("fees_usd", 0),
                    trade_data.get("liquidity_usd", 0),
                    trade_data.get("is_volatile", False),
                    trade_data.get("trigger_wallet"),
                ),
            )

    def get_win_rate(self, limit: int = 20) -> float:
        """Calculate recent win rate."""
        with self.db.cursor() as c:
            c.execute(
                """
            SELECT 
                CAST(SUM(CASE WHEN is_win THEN 1 ELSE 0 END) AS REAL) / COUNT(*)
            FROM (
                SELECT is_win FROM trades 
                ORDER BY timestamp DESC 
                LIMIT ?
            )
            """,
                (limit,),
            )
            result = c.fetchone()[0]
            return float(result) if result is not None else 0.5

    def get_total_trades(self) -> int:
        """Get total number of trades."""
        result = self._fetchone("SELECT COUNT(*) as count FROM trades")
        return result["count"] if result else 0
