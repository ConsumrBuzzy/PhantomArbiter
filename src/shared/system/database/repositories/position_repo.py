import time
from typing import List, Optional, Dict
from src.shared.system.database.repositories.base import BaseRepository


class PositionRepository(BaseRepository):
    """
    Handles persistence of active positions.
    Replaces JSON file tracking.
    """

    def init_table(self):
        with self.db.cursor(commit=True) as c:
            c.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                symbol TEXT PRIMARY KEY,
                entry_price REAL,
                cost_basis REAL,
                entry_time REAL,
                max_price_achieved REAL,
                trailing_stop_price REAL,
                token_balance REAL,
                updated_at REAL
            )
            """)

    def save_position(self, symbol: str, data: Dict):
        """Upsert position state."""
        with self.db.cursor(commit=True) as c:
            c.execute(
                """
            INSERT INTO positions (
                symbol, entry_price, cost_basis, entry_time,
                max_price_achieved, trailing_stop_price, token_balance, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                entry_price=excluded.entry_price,
                cost_basis=excluded.cost_basis,
                entry_time=excluded.entry_time,
                max_price_achieved=excluded.max_price_achieved,
                trailing_stop_price=excluded.trailing_stop_price,
                token_balance=excluded.token_balance,
                updated_at=excluded.updated_at
            """,
                (
                    symbol,
                    data.get("entry_price", 0),
                    data.get("cost_basis", 0),
                    data.get("entry_time", 0) or time.time(),
                    data.get("max_price_achieved", 0),
                    data.get("trailing_stop_price", 0),
                    data.get("token_balance", 0),
                    time.time(),
                ),
            )

    def get_position(self, symbol: str) -> Optional[Dict]:
        """Retrieve position state."""
        return self._fetchone("SELECT * FROM positions WHERE symbol = ?", (symbol,))

    def delete_position(self, symbol: str):
        """Remove position state."""
        self._execute("DELETE FROM positions WHERE symbol = ?", (symbol,), commit=True)

    def get_all_positions(self) -> List[Dict]:
        """Get all active positions."""
        return self._fetchall("SELECT * FROM positions")
