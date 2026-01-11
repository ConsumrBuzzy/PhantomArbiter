"""
Paper Wallet Manager
====================
Manages virtual balances for simulation/paper trading mode.

Features:
- Tracks virtual Equity and SOL/USDC balances
- Persists to SQLite db via PersistenceDB
- Handles debit/credit operations for simulated trades
"""

import logging
import time
from typing import Dict, Optional, Any
from src.shared.system.persistence import get_db

logger = logging.getLogger("phantom.paper_wallet")

class PaperWallet:
    def __init__(self, initial_equity: float = 10000.0, initial_sol: float = 50.0):
        self.db = get_db()
        self.initial_equity = initial_equity
        self.initial_sol = initial_sol
        self.balances: Dict[str, float] = {}
        
        # Load from DB or initialize
        self.reload()
        
    @property
    def sol_balance(self):
        return self.balances.get('SOL', 0.0)
        
    @property
    def usdc_balance(self):
        return self.balances.get('USDC', 0.0)

    def reload(self):
        """Reload balances from DB."""
        self._load_state()

    def _load_state(self):
        """Load balances from DB or create simulated initial state."""
        try:
            conn = self.db._get_connection()
            rows = conn.execute("SELECT asset, balance FROM paper_wallet").fetchall()
            
            self.balances = {}
            if rows:
                for row in rows:
                    self.balances[row['asset']] = row['balance']
                
                # Log state
                usdc = self.balances.get('USDC', 0.0)
                sol = self.balances.get('SOL', 0.0)
                logger.debug(f"Loaded Paper Wallet: {len(self.balances)} assets (USDC: {usdc:.2f}, SOL: {sol:.4f})")
            else:
                self._initialize_defaults()
                
        except Exception as e:
            logger.error(f"Failed to load paper wallet: {e}")

    def _initialize_defaults(self):
        """Set default balances."""
        self.balances = {
            'SOL': self.initial_sol,
            'USDC': self.initial_equity - (self.initial_sol * 150.0)
        }
        self._save_state()
        logger.info(f"Initialized Paper Wallet with defaults")

    def _save_state(self):
        """Persist current balances to DB."""
        try:
            with self.db._transaction() as conn:
                timestamp = time.time()
                for asset, balance in self.balances.items():
                    conn.execute("""
                        INSERT INTO paper_wallet (asset, balance, initial_balance, updated_at)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(asset) DO UPDATE SET
                            balance = excluded.balance,
                            updated_at = excluded.updated_at
                    """, (asset, balance, 0.0, timestamp)) # Initial balance tracking separate if needed
        except Exception as e:
            logger.error(f"Failed to save paper wallet: {e}")

    def get_balances(self, sol_price: float = 0.0) -> Dict[str, Any]:
        """Get current virtual balances."""
        # Calculate Equity
        equity = self.balances.get('USDC', 0.0)
        
        # Add value of other assets (assuming they are priced in SOL, except USDC)
        # This is a simplification. Ideally we need prices for all assets.
        # For now, we only know SOL price.
        # If we have jitoSOL, we assume it's roughly 1.0 SOL * sol_price?
        # Or we return raw balances and let frontend calculate value?
        
        # Let's return raw balances map + total equity estimate
        
        total_sol_val = 0.0
        for asset, bal in self.balances.items():
            if asset == 'SOL':
                total_sol_val += bal
            elif asset != 'USDC':
                # Assume parity with SOL for now for simple estimation
                total_sol_val += bal
        
        equity += total_sol_val * sol_price
        
        return {
            'equity': equity,
            'sol_balance': self.sol_balance,
            'usdc_balance': self.usdc_balance,
            'assets': self.balances
        }

    def credit(self, asset: str, amount: float):
        """Add funds (e.g. trade profit)."""
        self.balances[asset] = self.balances.get(asset, 0.0) + amount
        self._save_state()

    def debit(self, asset: str, amount: float) -> bool:
        """Remove funds (e.g. trade entry). Returns False if insufficient."""
        current = self.balances.get(asset, 0.0)
        if current >= amount:
            self.balances[asset] = current - amount
            self._save_state()
            return True
        return False
        
    def reset(self):
        """Reset to initial state."""
        self._initialize_defaults()

# Singleton
_paper_wallet = None

def get_paper_wallet() -> PaperWallet:
    global _paper_wallet
    if _paper_wallet is None:
        _paper_wallet = PaperWallet()
    return _paper_wallet

# Export default singleton instance
pw = get_paper_wallet()
