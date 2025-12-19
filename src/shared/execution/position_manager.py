"""
Position Manager (DB)
=====================
Handles state persistence and lifecycle of positions using SQLite.
"""
from src.shared.system.db_manager import db_manager
from config.thresholds import DEFAULT_LEGACY_ENTRY_SIZE_USD

class PositionManager:
    """Manages persistence logic for a Watcher using DBManager."""
    
    def __init__(self, symbol: str):
        self.symbol = symbol

    def persist_state(self, state: dict):
        """Save state to DB."""
        # Clean state for DB if needed, or just pass dict
        # DBManager expects flat fields matching schema
        db_manager.save_position(self.symbol, state)

    def load_state(self) -> dict:
        """Load state from DB."""
        return db_manager.get_position(self.symbol) or {}
    
    def clear_state(self):
        """Delete persisted state from DB."""
        db_manager.delete_position(self.symbol)

    def recover_legacy_state(self, token_balance: float) -> dict:
        """Recover state from token balance if no DB record."""
        if token_balance > 0:
            estimated_entry = DEFAULT_LEGACY_ENTRY_SIZE_USD / token_balance
            return {
                "entry_price": estimated_entry,
                "cost_basis": DEFAULT_LEGACY_ENTRY_SIZE_USD,
                "in_position": True,
                "max_price_achieved": estimated_entry,
                "trailing_stop_price": 0.0,
                "token_balance": token_balance
            }
        return {}
