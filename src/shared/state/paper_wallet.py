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
from typing import Dict, Optional
from src.shared.system.persistence import get_db

logger = logging.getLogger("phantom.paper_wallet")

class PaperWallet:
    def __init__(self, initial_equity: float = 10000.0, initial_sol: float = 50.0):
        self.db = get_db()
        self.equity = initial_equity
        self.sol_balance = initial_sol
        self.usdc_balance = initial_equity - (initial_sol * 150.0) # Approx
        
        # Load from DB or initialize
        self._load_state()
        
    def _load_state(self):
        """Load balances from DB or create simulated initial state."""
        try:
            conn = self.db._get_connection()
            rows = conn.execute("SELECT asset, balance FROM paper_wallet").fetchall()
            
            loaded = False
            for row in rows:
                if row['asset'] == 'SOL':
                    self.sol_balance = row['balance']
                elif row['asset'] == 'USDC':
                    self.usdc_balance = row['balance']
                loaded = True
                
            if not loaded:
                self._save_state()
                logger.info(f"Initialized Paper Wallet with ${self.usdc_balance} USDC / {self.sol_balance} SOL")
            else:
                current_value = self.usdc_balance + (self.sol_balance * 150.0) # Todo: fetch real price
                logger.info(f"Loaded Paper Wallet: ${current_value:.2f} Equity")
                
        except Exception as e:
            logger.error(f"Failed to load paper wallet: {e}")

    def _save_state(self):
        """Persist current balances to DB."""
        try:
            with self.db._transaction() as conn:
                timestamp = time.time()
                conn.execute("""
                    INSERT INTO paper_wallet (asset, balance, initial_balance, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(asset) DO UPDATE SET
                        balance = excluded.balance,
                        updated_at = excluded.updated_at
                """, ('SOL', self.sol_balance, 50.0, timestamp))
                
                conn.execute("""
                    INSERT INTO paper_wallet (asset, balance, initial_balance, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(asset) DO UPDATE SET
                        balance = excluded.balance,
                        updated_at = excluded.updated_at
                """, ('USDC', self.usdc_balance, 5000.0, timestamp))
        except Exception as e:
            logger.error(f"Failed to save paper wallet: {e}")

    def get_balances(self, sol_price: float = 0.0) -> Dict[str, float]:
        """Get current virtual balances."""
        equity = self.usdc_balance + (self.sol_balance * (sol_price or 0)) 
        return {
            'equity': equity,
            'sol_balance': self.sol_balance,
            'usdc_balance': self.usdc_balance
        }

    def credit(self, asset: str, amount: float):
        """Add funds (e.g. trade profit)."""
        if asset == 'SOL':
            self.sol_balance += amount
        elif asset == 'USDC':
            self.usdc_balance += amount
        self._save_state()

    def debit(self, asset: str, amount: float) -> bool:
        """Remove funds (e.g. trade entry). Returns False if insufficient."""
        if asset == 'SOL':
            if self.sol_balance >= amount:
                self.sol_balance -= amount
                self._save_state()
                return True
        elif asset == 'USDC':
            if self.usdc_balance >= amount:
                self.usdc_balance -= amount
                self._save_state()
                return True
        return False
        
    def reset(self):
        """Reset to initial state."""
        self.sol_balance = 50.0
        self.usdc_balance = 5000.0
        self._save_state()

# Singleton
_paper_wallet = None

def get_paper_wallet() -> PaperWallet:
    global _paper_wallet
    if _paper_wallet is None:
        _paper_wallet = PaperWallet()
    return _paper_wallet
