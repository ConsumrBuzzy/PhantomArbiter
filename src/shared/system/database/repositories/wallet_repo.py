import time
from typing import List
from src.shared.system.database.repositories.base import BaseRepository


class WalletRepository(BaseRepository):
    """
    Handles Alpha Wallet tracking and 'Target' status.
    """

    def init_table(self):
        with self.db.cursor(commit=True) as c:
            # V116-117 Schema
            c.execute("""
            CREATE TABLE IF NOT EXISTS target_wallets (
                address TEXT PRIMARY KEY,
                tags TEXT,
                last_seen REAL,
                success_count INTEGER DEFAULT 0,
                total_trades INTEGER DEFAULT 0,
                total_pnl_usd REAL DEFAULT 0,
                updated_at REAL
            )
            """)

    def add_target_wallet(self, address: str, tags: str = "ALFA"):
        """Add wallet to watchlist."""
        with self.db.cursor(commit=True) as c:
            c.execute(
                """
            INSERT OR REPLACE INTO target_wallets (address, tags, last_seen)
            VALUES (?, ?, ?)
            """,
                (address, tags, time.time()),
            )

    def update_performance(self, address: str, is_win: bool, pnl_usd: float):
        """Record success/failure for an alpha wallet."""
        with self.db.cursor(commit=True) as c:
            c.execute(
                """
            UPDATE target_wallets SET 
                success_count = success_count + ?,
                total_trades = total_trades + 1,
                total_pnl_usd = total_pnl_usd + ?,
                updated_at = ?
            WHERE address = ?
            """,
                (1 if is_win else 0, pnl_usd, time.time(), address),
            )

    def get_target_wallets(self) -> List[str]:
        """Get all watchlisted wallets."""
        result = self._fetchall("SELECT address FROM target_wallets")
        return [row["address"] for row in result]
