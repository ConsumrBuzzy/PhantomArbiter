"""
Shared Wallet Protocol
======================
Unified wallet interface for Paper and Live trading modes.

Achieves "Systemic Parity" - the code path for a paper trade is
100% identical to a live trade, differing only in the backend driver.

Components:
- SharedWalletProtocol: Abstract interface for all wallet operations
- TransactionResult: Standardized result for debit/credit operations
- VirtualDriver: SQLite backend for paper trading
- SolanaDriver: RPC backend for live trading

The "Switch":
    Live Mode  → SolanaDriver (writes to blockchain)
    Paper Mode → VirtualDriver (writes to SQLite)
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Protocol, runtime_checkable
from dataclasses import dataclass, field
from enum import Enum
from decimal import Decimal

from src.shared.system.logging import Logger


# ═══════════════════════════════════════════════════════════════════════════════
# TRANSACTION RESULT
# ═══════════════════════════════════════════════════════════════════════════════

class TransactionStatus(Enum):
    """Status of a wallet transaction."""
    SUCCESS = "SUCCESS"
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    NETWORK_ERROR = "NETWORK_ERROR"
    TIMEOUT = "TIMEOUT"
    REJECTED = "REJECTED"


@dataclass
class TransactionResult:
    """Result of a wallet operation."""
    
    success: bool
    status: TransactionStatus
    
    # Amounts
    asset: str = ""
    amount: float = 0.0
    balance_before: float = 0.0
    balance_after: float = 0.0
    
    # Fees (for live transactions)
    fee_paid: float = 0.0
    fee_asset: str = "SOL"
    
    # Transaction details (for live)
    tx_signature: Optional[str] = None
    slot: Optional[int] = None
    
    # Error info
    error_message: Optional[str] = None
    
    # Timestamps
    timestamp: float = field(default_factory=time.time)
    
    @classmethod
    def success_debit(
        cls,
        asset: str,
        amount: float,
        before: float,
        after: float,
        fee: float = 0.0,
    ) -> "TransactionResult":
        return cls(
            success=True,
            status=TransactionStatus.SUCCESS,
            asset=asset,
            amount=amount,
            balance_before=before,
            balance_after=after,
            fee_paid=fee,
        )
    
    @classmethod
    def insufficient_balance(
        cls,
        asset: str,
        requested: float,
        available: float,
    ) -> "TransactionResult":
        return cls(
            success=False,
            status=TransactionStatus.INSUFFICIENT_BALANCE,
            asset=asset,
            amount=requested,
            balance_before=available,
            balance_after=available,
            error_message=f"Insufficient {asset}: requested {requested:.4f}, available {available:.4f}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# WALLET PROTOCOL
# ═══════════════════════════════════════════════════════════════════════════════

@runtime_checkable
class SharedWalletProtocol(Protocol):
    """
    Unified wallet interface for Paper and Live modes.
    
    All wallet operations go through this protocol, ensuring:
    - Same validation logic for paper and live
    - Same fee structures applied
    - Same slippage calculations
    - Same asset rounding rules
    
    Usage:
        wallet: SharedWalletProtocol = get_wallet(mode="paper")
        result = await wallet.debit("SOL", 1.5, reason="SWAP")
    """
    
    @property
    def mode(self) -> str:
        """Get wallet mode ('paper' or 'live')."""
        ...
    
    def get_balance(self, asset: str) -> float:
        """Get current balance for an asset."""
        ...
    
    def get_all_balances(self) -> Dict[str, float]:
        """Get all asset balances."""
        ...
    
    def get_equity_usd(self, prices: Dict[str, float]) -> float:
        """Calculate total equity in USD given asset prices."""
        ...
    
    async def debit(
        self,
        asset: str,
        amount: float,
        reason: str = "",
        validate: bool = True,
    ) -> TransactionResult:
        """
        Debit (subtract) an amount from an asset balance.
        
        Args:
            asset: Asset symbol (e.g., "SOL", "USDC")
            amount: Amount to debit (positive)
            reason: Reason for debit (for logging)
            validate: Whether to validate balance first
            
        Returns:
            TransactionResult with success/failure details
        """
        ...
    
    async def credit(
        self,
        asset: str,
        amount: float,
        reason: str = "",
    ) -> TransactionResult:
        """
        Credit (add) an amount to an asset balance.
        
        Args:
            asset: Asset symbol
            amount: Amount to credit (positive)
            reason: Reason for credit (for logging)
            
        Returns:
            TransactionResult with details
        """
        ...
    
    async def swap(
        self,
        from_asset: str,
        to_asset: str,
        from_amount: float,
        to_amount: float,
        fee_amount: float = 0.0,
        reason: str = "",
    ) -> TransactionResult:
        """
        Atomic swap between two assets.
        
        Args:
            from_asset: Asset to sell
            to_asset: Asset to receive
            from_amount: Amount to sell
            to_amount: Amount to receive
            fee_amount: Fee in from_asset
            reason: Reason for swap
            
        Returns:
            TransactionResult for the swap
        """
        ...
    
    def reset(self, initial_balances: Optional[Dict[str, float]] = None) -> None:
        """Reset wallet to initial state."""
        ...
    
    def get_transaction_history(self, limit: int = 100) -> List[TransactionResult]:
        """Get recent transaction history."""
        ...


# ═══════════════════════════════════════════════════════════════════════════════
# VIRTUAL DRIVER (Paper Trading)
# ═══════════════════════════════════════════════════════════════════════════════

class VirtualDriver:
    """
    SQLite-backed virtual wallet for paper trading.
    
    Implements SharedWalletProtocol with local persistence.
    """
    
    DEFAULT_BALANCES = {
        "SOL": 0.25,
        "USDC": 50.0,
    }
    
    def __init__(
        self,
        initial_balances: Optional[Dict[str, float]] = None,
        persistence_key: str = "default",
    ):
        self._mode = "paper"
        self._balances: Dict[str, float] = {}
        self._history: List[TransactionResult] = []
        self._persistence_key = persistence_key
        
        # Load from DB or initialize
        self._load_from_db()
        
        if not self._balances:
            self._balances = initial_balances or self.DEFAULT_BALANCES.copy()
            self._save_to_db()
    
    @property
    def mode(self) -> str:
        return self._mode
    
    def get_balance(self, asset: str) -> float:
        return self._balances.get(asset, 0.0)
    
    def get_all_balances(self) -> Dict[str, float]:
        return self._balances.copy()
    
    def get_equity_usd(self, prices: Dict[str, float]) -> float:
        equity = 0.0
        for asset, balance in self._balances.items():
            price = prices.get(asset, 1.0 if asset == "USDC" else 0.0)
            equity += balance * price
        return equity
    
    async def debit(
        self,
        asset: str,
        amount: float,
        reason: str = "",
        validate: bool = True,
    ) -> TransactionResult:
        """Debit from virtual balance."""
        current = self.get_balance(asset)
        
        if validate and current < amount:
            result = TransactionResult.insufficient_balance(asset, amount, current)
            self._history.append(result)
            return result
        
        new_balance = max(0, current - amount)
        self._balances[asset] = new_balance
        self._save_to_db()
        
        result = TransactionResult.success_debit(
            asset=asset,
            amount=amount,
            before=current,
            after=new_balance,
        )
        self._history.append(result)
        
        Logger.debug(f"[VirtualDriver] DEBIT {amount:.4f} {asset} ({reason}) → {new_balance:.4f}")
        
        return result
    
    async def credit(
        self,
        asset: str,
        amount: float,
        reason: str = "",
    ) -> TransactionResult:
        """Credit to virtual balance."""
        current = self.get_balance(asset)
        new_balance = current + amount
        
        self._balances[asset] = new_balance
        self._save_to_db()
        
        result = TransactionResult(
            success=True,
            status=TransactionStatus.SUCCESS,
            asset=asset,
            amount=amount,
            balance_before=current,
            balance_after=new_balance,
        )
        self._history.append(result)
        
        Logger.debug(f"[VirtualDriver] CREDIT {amount:.4f} {asset} ({reason}) → {new_balance:.4f}")
        
        return result
    
    async def swap(
        self,
        from_asset: str,
        to_asset: str,
        from_amount: float,
        to_amount: float,
        fee_amount: float = 0.0,
        reason: str = "",
    ) -> TransactionResult:
        """Atomic swap between two assets."""
        # Validate balance
        current = self.get_balance(from_asset)
        total_debit = from_amount + fee_amount
        
        if current < total_debit:
            return TransactionResult.insufficient_balance(from_asset, total_debit, current)
        
        # Execute swap atomically
        await self.debit(from_asset, from_amount + fee_amount, reason=f"SWAP_OUT: {reason}")
        await self.credit(to_asset, to_amount, reason=f"SWAP_IN: {reason}")
        
        Logger.info(
            f"[VirtualDriver] SWAP {from_amount:.4f} {from_asset} → "
            f"{to_amount:.4f} {to_asset} (fee: {fee_amount:.4f})"
        )
        
        return TransactionResult(
            success=True,
            status=TransactionStatus.SUCCESS,
            asset=from_asset,
            amount=from_amount,
            fee_paid=fee_amount,
        )
    
    def reset(self, initial_balances: Optional[Dict[str, float]] = None) -> None:
        """Reset to initial state."""
        self._balances = initial_balances or self.DEFAULT_BALANCES.copy()
        self._history.clear()
        self._save_to_db()
        Logger.info("[VirtualDriver] Wallet reset")
    
    def get_transaction_history(self, limit: int = 100) -> List[TransactionResult]:
        return self._history[-limit:]
    
    def _load_from_db(self) -> None:
        """Load balances from SQLite."""
        try:
            from src.shared.system.persistence import get_db
            db = get_db()
            conn = db._get_connection()
            rows = conn.execute("SELECT asset, balance FROM paper_wallet").fetchall()
            
            for row in rows:
                self._balances[row['asset']] = row['balance']
                
        except Exception as e:
            Logger.debug(f"[VirtualDriver] DB load failed: {e}")
    
    def _save_to_db(self) -> None:
        """Persist balances to SQLite."""
        try:
            from src.shared.system.persistence import get_db
            db = get_db()
            
            with db._transaction() as conn:
                timestamp = time.time()
                for asset, balance in self._balances.items():
                    conn.execute("""
                        INSERT INTO paper_wallet (asset, balance, initial_balance, updated_at)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(asset) DO UPDATE SET
                            balance = excluded.balance,
                            updated_at = excluded.updated_at
                    """, (asset, balance, 0.0, timestamp))
                    
        except Exception as e:
            Logger.debug(f"[VirtualDriver] DB save failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# SOLANA DRIVER (Live Trading)
# ═══════════════════════════════════════════════════════════════════════════════

class SolanaDriver:
    """
    Solana RPC-backed wallet for live trading.
    
    Implements SharedWalletProtocol with blockchain operations.
    Note: Actual transfers require the execution pipeline.
    """
    
    def __init__(self, wallet_manager: Any = None):
        self._mode = "live"
        self._wallet_manager = wallet_manager
        self._history: List[TransactionResult] = []
        self._cached_balances: Dict[str, float] = {}
        self._cache_time: float = 0.0
    
    @property
    def mode(self) -> str:
        return self._mode
    
    def get_balance(self, asset: str) -> float:
        """Get on-chain balance (cached)."""
        self._refresh_cache_if_needed()
        return self._cached_balances.get(asset, 0.0)
    
    def get_all_balances(self) -> Dict[str, float]:
        self._refresh_cache_if_needed()
        return self._cached_balances.copy()
    
    def get_equity_usd(self, prices: Dict[str, float]) -> float:
        balances = self.get_all_balances()
        equity = 0.0
        for asset, balance in balances.items():
            price = prices.get(asset, 1.0 if asset == "USDC" else 0.0)
            equity += balance * price
        return equity
    
    async def debit(
        self,
        asset: str,
        amount: float,
        reason: str = "",
        validate: bool = True,
    ) -> TransactionResult:
        """
        Record a debit (actual transfer happens via execution pipeline).
        
        This method is for tracking - the actual blockchain transfer
        is handled by JupiterSwapper or BundleSubmitter.
        """
        current = self.get_balance(asset)
        
        if validate and current < amount:
            return TransactionResult.insufficient_balance(asset, amount, current)
        
        # Update cache
        self._cached_balances[asset] = current - amount
        
        result = TransactionResult.success_debit(
            asset=asset,
            amount=amount,
            before=current,
            after=current - amount,
        )
        self._history.append(result)
        
        Logger.debug(f"[SolanaDriver] DEBIT (tracked) {amount:.4f} {asset} ({reason})")
        
        return result
    
    async def credit(
        self,
        asset: str,
        amount: float,
        reason: str = "",
    ) -> TransactionResult:
        """Record a credit (for tracking)."""
        current = self.get_balance(asset)
        
        # Update cache
        self._cached_balances[asset] = current + amount
        
        result = TransactionResult(
            success=True,
            status=TransactionStatus.SUCCESS,
            asset=asset,
            amount=amount,
            balance_before=current,
            balance_after=current + amount,
        )
        self._history.append(result)
        
        return result
    
    async def swap(
        self,
        from_asset: str,
        to_asset: str,
        from_amount: float,
        to_amount: float,
        fee_amount: float = 0.0,
        reason: str = "",
    ) -> TransactionResult:
        """Record a swap (actual execution via JupiterSwapper)."""
        await self.debit(from_asset, from_amount + fee_amount, reason=f"SWAP_OUT: {reason}")
        await self.credit(to_asset, to_amount, reason=f"SWAP_IN: {reason}")
        
        return TransactionResult(
            success=True,
            status=TransactionStatus.SUCCESS,
            asset=from_asset,
            amount=from_amount,
            fee_paid=fee_amount,
        )
    
    def reset(self, initial_balances: Optional[Dict[str, float]] = None) -> None:
        """Refresh cached balances from chain."""
        self._cached_balances.clear()
        self._cache_time = 0.0
        self._refresh_cache_if_needed()
    
    def get_transaction_history(self, limit: int = 100) -> List[TransactionResult]:
        return self._history[-limit:]
    
    def _refresh_cache_if_needed(self) -> None:
        """Refresh balance cache if stale (>5 seconds)."""
        if time.time() - self._cache_time < 5.0:
            return
        
        try:
            if self._wallet_manager:
                data = self._wallet_manager.get_current_live_usd_balance()
                breakdown = data.get("breakdown", {})
                
                for asset, balance in breakdown.items():
                    self._cached_balances[asset] = balance
                
                # Also include ATAs
                for asset_info in data.get("assets", []):
                    sym = asset_info.get("symbol")
                    amt = asset_info.get("amount", 0)
                    if sym:
                        self._cached_balances[sym] = amt
                
                self._cache_time = time.time()
                
        except Exception as e:
            Logger.debug(f"[SolanaDriver] Cache refresh failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# WALLET FACTORY
# ═══════════════════════════════════════════════════════════════════════════════

_virtual_driver: Optional[VirtualDriver] = None
_solana_driver: Optional[SolanaDriver] = None


def get_wallet(mode: str = "paper", wallet_manager: Any = None) -> SharedWalletProtocol:
    """
    Get wallet instance for specified mode.
    
    Args:
        mode: "paper" or "live"
        wallet_manager: WalletManager for live mode
        
    Returns:
        Wallet implementing SharedWalletProtocol
    """
    global _virtual_driver, _solana_driver
    
    if mode == "paper":
        if _virtual_driver is None:
            _virtual_driver = VirtualDriver()
        return _virtual_driver
    else:
        if _solana_driver is None:
            _solana_driver = SolanaDriver(wallet_manager)
        return _solana_driver


def reset_wallets():
    """Reset wallet singletons (for testing)."""
    global _virtual_driver, _solana_driver
    _virtual_driver = None
    _solana_driver = None
