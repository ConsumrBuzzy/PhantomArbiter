"""
WalletSyncService - The Accountant
==================================
Layer A: Market Monitor - Wallet balance synchronization.

Responsibilities:
- Wallet balance scanning (SOL, USDC, token accounts)
- Balance caching in SharedPriceCache
- Balance invalidation on trades

NOTE: This is the ONLY service that touches wallet keys.
"""

import time
from typing import Dict, Optional
from dataclasses import dataclass

from src.shared.system.logging import Logger


@dataclass
class WalletState:
    """Current wallet state snapshot."""
    sol_balance: float
    usdc_balance: float
    held_assets: Dict[str, float]  # mint -> balance
    timestamp: float
    
    @property
    def total_equity_usd(self) -> float:
        """Calculate total equity (requires price feed)."""
        # TODO: integrate with PriceFeedService for valuation
        return self.usdc_balance


class WalletSyncService:
    """
    The Accountant - Wallet balance synchronization.
    
    Isolated from price feeds for security. Only service
    that interacts with wallet private keys.
    """
    
    def __init__(self):
        self._last_state: Optional[WalletState] = None
        self._last_sync: float = 0.0
        self._sync_interval: float = 10.0  # seconds
        self._invalidated: bool = True
        
        Logger.info("💰 WalletSyncService initialized")
    
    def sync(self, force: bool = False) -> Optional[WalletState]:
        """
        Synchronize wallet state from chain.
        
        Args:
            force: Force sync even if recently synced
        
        Returns:
            Current wallet state or None on failure
        """
        now = time.time()
        
        # Skip if recently synced and not invalidated
        if not force and not self._invalidated:
            if (now - self._last_sync) < self._sync_interval:
                return self._last_state
        
        try:
            state = self._fetch_wallet_state()
            self._last_state = state
            self._last_sync = now
            self._invalidated = False
            
            # Write to cache for cross-process sharing
            self._write_to_cache(state)
            
            return state
        except Exception as e:
            Logger.error(f"Wallet sync failed: {e}")
            return self._last_state
    
    def get_balance(self, mint: str) -> float:
        """Get token balance by mint."""
        if not self._last_state:
            self.sync()
        
        if not self._last_state:
            return 0.0
        
        if mint == "So11111111111111111111111111111111111111112":
            return self._last_state.sol_balance
        
        return self._last_state.held_assets.get(mint, 0.0)
    
    def invalidate(self) -> None:
        """Invalidate cached state (call after trades)."""
        self._invalidated = True
        Logger.debug("♻️ Wallet state invalidated")
    
    def _fetch_wallet_state(self) -> WalletState:
        """Fetch wallet state from chain."""
        # TODO: Extract logic from DataBroker._scan_and_cache_wallet
        # For now, return placeholder
        return WalletState(
            sol_balance=0.0,
            usdc_balance=0.0,
            held_assets={},
            timestamp=time.time(),
        )
    
    def _write_to_cache(self, state: WalletState) -> None:
        """Write wallet state to SharedPriceCache."""
        try:
            from src.core.shared_cache import SharedPriceCache
            SharedPriceCache.write_wallet_state(
                usdc_balance=state.usdc_balance,
                held_assets=state.held_assets,
                sol_balance=state.sol_balance,
            )
        except Exception as e:
            Logger.error(f"Wallet cache write failed: {e}")
