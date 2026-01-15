"""
Vault Manager
=============
Per-engine virtual capital management for the Multi-Vault Architecture.

Each trading engine maintains isolated paper balances, preventing "noisy neighbor"
cross-contamination during simulations.

Features:
- Composite (engine, asset) primary key for isolation
- Lazy vault instantiation on first access
- Thread-safe operations via PersistenceDB transactions
- Global aggregation for portfolio reporting
"""

import logging
import time
from typing import Dict, Any, Optional
from enum import Enum
from dataclasses import dataclass, field

logger = logging.getLogger("phantom.vault_manager")

class VaultType(Enum):
    VIRTUAL = "VIRTUAL"      # Paper / Simulation
    ON_CHAIN = "ON_CHAIN"    # Real Wallet / Sub-Account


@dataclass
class EngineVault:
    """
    Isolated paper wallet for a single engine.
    
    Provides the same interface as the legacy PaperWallet but scoped
    to a specific engine's simulation context.
    """
    engine_name: str
    balances: Dict[str, float] = field(default_factory=dict)
    initial_equity: float = 50.0
    initial_sol: float = 0.25
    
    # Hybrid Vault Config
    vault_type: VaultType = VaultType.VIRTUAL
    sub_account_id: int = 0
    
    _db: Any = field(default=None, repr=False)
    
    def __post_init__(self):
        from src.shared.system.persistence import get_db
        self._db = get_db()
        self._load_state()
    
    @property
    def sol_balance(self) -> float:
        return self.balances.get('SOL', 0.0)
    
    @property
    def usdc_balance(self) -> float:
        return self.balances.get('USDC', 0.0)
    
    def _load_state(self):
        """Load balances from DB or initialize defaults."""
        try:
            conn = self._db._get_connection()
            rows = conn.execute(
                "SELECT asset, balance FROM engine_vaults WHERE engine = ?",
                (self.engine_name,)
            ).fetchall()
            
            self.balances = {}
            if rows:
                for row in rows:
                    self.balances[row['asset']] = row['balance']
                logger.debug(
                    f"Loaded vault [{self.engine_name}]: {len(self.balances)} assets "
                    f"(USDC: {self.usdc_balance:.2f}, SOL: {self.sol_balance:.4f})"
                )
            else:
                self._initialize_defaults()
                
        except Exception as e:
            logger.error(f"Failed to load vault [{self.engine_name}]: {e}")
    
    def _initialize_defaults(self):
        """Set default balances for new vault."""
        self.balances = {
            'SOL': self.initial_sol,
            'USDC': self.initial_equity - (self.initial_sol * 150.0)  # Approx SOL value
        }
        self._save_state()
        logger.info(f"Initialized vault [{self.engine_name}] with defaults")
    
    def _save_state(self):
        """Persist current balances to DB."""
        try:
            with self._db._transaction() as conn:
                timestamp = time.time()
                for asset, balance in self.balances.items():
                    conn.execute("""
                        INSERT INTO engine_vaults (engine, asset, balance, initial_balance, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(engine, asset) DO UPDATE SET
                            balance = excluded.balance,
                            updated_at = excluded.updated_at
                    """, (self.engine_name, asset, balance, 0.0, timestamp))
        except Exception as e:
            logger.error(f"Failed to save vault [{self.engine_name}]: {e}")
    
    def get_balances(self, sol_price: float = 0.0) -> Dict[str, Any]:
        """Get current virtual balances with equity calculation."""
        equity = self.balances.get('USDC', 0.0)
        
        # Add Drift Position Value (already in USD)
        equity += self.balances.get('DRIFT_POS', 0.0)
        
        total_sol_val = 0.0
        for asset, bal in self.balances.items():
            if asset in ['USDC', 'DRIFT_POS']:
                continue
                
            if asset == 'SOL':
                total_sol_val += bal
            else:
                # Assume parity with SOL for LST/staked assets (e.g. mSOL, jitoSOL)
                total_sol_val += bal
        
        equity += total_sol_val * sol_price
        
        return {
            'engine': self.engine_name,
            'type': self.vault_type.value,
            'sub_account': self.sub_account_id,
            'equity': equity,
            'sol_balance': self.sol_balance,
            'usdc_balance': self.usdc_balance,
            'assets': self.balances
        }
    
    def credit(self, asset: str, amount: float):
        """Add funds (e.g., trade profit)."""
        self.balances[asset] = self.balances.get(asset, 0.0) + amount
        self._save_state()
        logger.debug(f"[{self.engine_name}] Credit {amount:.4f} {asset}")
    
    def debit(self, asset: str, amount: float) -> bool:
        """Remove funds (e.g., trade entry). Returns False if insufficient."""
        current = self.balances.get(asset, 0.0)
        if current >= amount:
            self.balances[asset] = current - amount
            self._save_state()
            logger.debug(f"[{self.engine_name}] Debit {amount:.4f} {asset}")
            return True
        logger.warning(f"[{self.engine_name}] Insufficient {asset}: {current:.4f} < {amount:.4f}")
        return False
    
    def reset(self):
        """Reset to initial state."""
        self._clear_vault()
        self._initialize_defaults()
        logger.info(f"[{self.engine_name}] Vault reset to initial state")
    
    def _clear_vault(self):
        """Remove all vault entries for this engine."""
        try:
            with self._db._transaction() as conn:
                conn.execute(
                    "DELETE FROM engine_vaults WHERE engine = ?",
                    (self.engine_name,)
                )
        except Exception as e:
            logger.error(f"Failed to clear vault [{self.engine_name}]: {e}")
    
    def sync_from_live(self, live_balances: Dict[str, float]):
        """Mirror live wallet balances into paper vault for realistic testing."""
        self._clear_vault()
        self.balances = dict(live_balances)
        self._save_state()
        logger.info(f"[{self.engine_name}] Synced from live wallet: {len(live_balances)} assets")
    
    async def sync_from_drift(self, drift_adapter):
        """
        Sync balances from Drift Protocol Sub-Account.
        
        Args:
           drift_adapter: Instance of DriftAdapter connected to the user.
        """
        if self.vault_type != VaultType.ON_CHAIN:
            return

        try:
            # Check if adapter has builder (access to account)
            if not drift_adapter or not drift_adapter._builder:
                return
                
            # For now, we assume sub-account 0 (Main) until we add sub-account switching
            # The drift_adapter uses the wallet's configured sub-account
            
            # Fetch user account data (collateral)
            # The adapter should have a method for this, or we construct the URL
            wallet = str(drift_adapter._builder.wallet)
            
            # We can reuse the logic from HeartbeatCollector for now, 
            # or better: rely on the adapter to provide 'get_user_account()'
            
            # Temporary: direct fetch to avoid circular deps or complex adapter changes right now
            import requests
            url = f"https://drift-gateway-api.mainnet.drift.trade/v1/user/{wallet}"
            resp = requests.get(url, timeout=2.0)
            
            if resp.status_code == 200:
                data = resp.json()
                
                # Parse Collateral
                # Drift "Total Collateral" is essentially the equity we care about
                total_collateral = float(data.get("totalCollateralValue", 0)) / 1e6
                free_collateral = float(data.get("freeCollateral", 0)) / 1e6
                
                # Update Vault State
                # We map 'USDC' to Free Collateral (Tradeable)
                # We add 'DRIFT_POS' (synthetic) to represent active positions so Equity is correct
                # Equity = Free + Deployed
                deployed = max(0, total_collateral - free_collateral)
                
                self.balances['USDC'] = free_collateral
                self.balances['DRIFT_POS'] = deployed
                self.balances['SOL'] = 0.0 
                
                self._save_state()
                # logger.debug(f"[{self.engine_name}] Synced from Drift: ${total_collateral:.2f}")

        except Exception as e:
            logger.error(f"Failed to sync Drift vault [{self.engine_name}]: {e}")

    def reload(self):
        """Reload balances from DB."""
        self._load_state()


class VaultRegistry:
    """
    Singleton registry managing per-engine paper vaults.
    
    Provides lazy instantiation and global aggregation capabilities.
    """
    _instance: Optional["VaultRegistry"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._vaults: Dict[str, EngineVault] = {}
        self._ensure_schema()
        self._initialized = True
    
    def _ensure_schema(self):
        """Ensure engine_vaults table exists."""
        from src.shared.system.persistence import get_db
        db = get_db()
        conn = db._get_connection()
        
        conn.executescript("""
            -- Engine Vaults: Per-engine virtual balance tracking
            CREATE TABLE IF NOT EXISTS engine_vaults (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                engine TEXT NOT NULL,
                asset TEXT NOT NULL,
                balance REAL NOT NULL DEFAULT 0,
                initial_balance REAL NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL,
                UNIQUE(engine, asset)
            );
            CREATE INDEX IF NOT EXISTS idx_engine_vaults_engine ON engine_vaults(engine);
        """)
        conn.commit()
        logger.debug("Engine vaults schema verified")
    
    def get_vault(self, engine_name: str) -> EngineVault:
        """
        Get or create an isolated vault for the specified engine.
        
        Lazy instantiation ensures no database bloat for unused engines.
        """
        if engine_name not in self._vaults:
            # Factory Logic (ADR-0008)
            vault_type = VaultType.VIRTUAL
            sub_id = 0
            
            if engine_name == 'drift':
                vault_type = VaultType.VIRTUAL # Default to Paper for safety
                sub_id = 0 # Main Sub-Account
                
            self._vaults[engine_name] = EngineVault(
                engine_name=engine_name,
                vault_type=vault_type,
                sub_account_id=sub_id
            )
            logger.info(f"Created vault for engine: {engine_name} ({vault_type.name})")
        return self._vaults[engine_name]
    
    def reset_vault(self, engine_name: str):
        """Reset a specific engine's vault to initial state."""
        vault = self.get_vault(engine_name)
        vault.reset()
    
    def sync_from_live(self, engine_name: str, live_balances: Dict[str, float]):
        """Mirror live wallet into specific engine's paper vault."""
        vault = self.get_vault(engine_name)
        vault.sync_from_live(live_balances)
    
    def get_global_snapshot(self, sol_price: float = 0.0) -> Dict[str, Any]:
        """
        Aggregate all vaults for global portfolio reporting.
        
        Returns:
            {
                'total_equity': float,
                'assets': {asset: total_balance},
                'vaults': {engine_name: vault_summary}
            }
        """
        from src.shared.system.persistence import get_db
        db = get_db()
        conn = db._get_connection()
        
        # Efficient single-query aggregation
        rows = conn.execute("""
            SELECT asset, SUM(balance) as total
            FROM engine_vaults
            GROUP BY asset
        """).fetchall()
        
        aggregated = {row['asset']: row['total'] for row in rows}
        
        # Calculate total equity
        usdc = aggregated.get('USDC', 0.0)
        sol_assets = sum(v for k, v in aggregated.items() if k != 'USDC')
        total_equity = usdc + (sol_assets * sol_price)
        
        # Per-vault breakdown
        vault_summaries = {}
        for engine, vault in self._vaults.items():
            vault_summaries[engine] = vault.get_balances(sol_price)
        
        return {
            'total_equity': total_equity,
            'assets': aggregated,
            'vaults': vault_summaries
        }
    
    def get_all_vault_names(self) -> list:
        """Get list of all engines with active vaults."""
        from src.shared.system.persistence import get_db
        db = get_db()
        conn = db._get_connection()
        
        rows = conn.execute(
            "SELECT DISTINCT engine FROM engine_vaults"
        ).fetchall()
        
        return [row['engine'] for row in rows]


# Global singleton accessor
_vault_registry: Optional[VaultRegistry] = None

def get_vault_registry() -> VaultRegistry:
    """Get the global vault registry instance."""
    global _vault_registry
    if _vault_registry is None:
        _vault_registry = VaultRegistry()
    return _vault_registry


# Convenience function for engine-scoped access
def get_engine_vault(engine_name: str) -> EngineVault:
    """Shorthand for getting a specific engine's vault."""
    return get_vault_registry().get_vault(engine_name)
