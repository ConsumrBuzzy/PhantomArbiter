"""
Virtual Wallet Provider - Multi-Tenant Simulation Layer.

Wraps CapitalManager with escrow locking and fake signature generation.
Each engine gets its own isolated sandbox.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Any
from enum import Enum

from .friction_calculator import FrictionCalculator, get_friction_calculator
from .order_bus import TradeSignal, ExecutionResult, SignalStatus, SignalAction


class LockStatus(str, Enum):
    """Fund lock status."""
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"


@dataclass
class FundLock:
    """A locked fund entry for pending trades."""
    lock_id: str
    engine_id: str
    amount_usd: float
    mint: str
    created_at: float
    status: LockStatus = LockStatus.PENDING
    expires_at: float = 0.0  # 0 = no expiry
    
    def is_expired(self) -> bool:
        if self.expires_at <= 0:
            return False
        return time.time() > self.expires_at


@dataclass
class Position:
    """A virtual trading position."""
    symbol: str
    mint: str
    balance: float
    avg_price: float
    entry_time: float = field(default_factory=time.time)
    engine_id: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "mint": self.mint,
            "balance": round(self.balance, 8),
            "avg_price": round(self.avg_price, 8),
            "entry_time": self.entry_time,
            "engine_id": self.engine_id,
        }


@dataclass
class EngineWallet:
    """Virtual wallet state for a single engine."""
    engine_id: str
    cash_usd: float = 1000.0
    sol_balance: float = 0.1
    positions: Dict[str, Position] = field(default_factory=dict)
    locked_usd: float = 0.0
    total_pnl: float = 0.0
    trades_count: int = 0
    wins: int = 0
    
    def available_cash(self) -> float:
        """Cash minus locked funds."""
        return max(0, self.cash_usd - self.locked_usd)
    
    def to_dict(self) -> Dict:
        return {
            "engine_id": self.engine_id,
            "cash_usd": round(self.cash_usd, 2),
            "sol_balance": round(self.sol_balance, 6),
            "locked_usd": round(self.locked_usd, 2),
            "available_cash": round(self.available_cash(), 2),
            "positions_count": len(self.positions),
            "total_pnl": round(self.total_pnl, 2),
            "trades_count": self.trades_count,
            "win_rate": self.wins / max(self.trades_count, 1),
        }


class VirtualWalletProvider:
    """
    Multi-tenant virtual wallet with escrow locking.
    
    Features:
    - Engine-isolated virtual balances
    - Fund locking for pending trades (prevents double-spend)
    - Fake transaction signature generation
    - Integration with FrictionCalculator
    """
    
    def __init__(
        self,
        default_cash: float = 1000.0,
        default_sol: float = 0.1,
    ) -> None:
        self._wallets: Dict[str, EngineWallet] = {}
        self._locks: Dict[str, FundLock] = {}
        self._default_cash = default_cash
        self._default_sol = default_sol
        self._friction = get_friction_calculator()
    
    def get_or_create_wallet(self, engine_id: str) -> EngineWallet:
        """Get or create wallet for an engine."""
        if engine_id not in self._wallets:
            self._wallets[engine_id] = EngineWallet(
                engine_id=engine_id,
                cash_usd=self._default_cash,
                sol_balance=self._default_sol,
            )
        return self._wallets[engine_id]
    
    def get_balance(self, engine_id: str, mint: str = "USDC") -> float:
        """Get balance for an engine (USDC = cash, SOL = gas)."""
        wallet = self.get_or_create_wallet(engine_id)
        
        if mint == "USDC" or mint == "cash":
            return wallet.available_cash()
        elif mint == "SOL" or mint == "So11111111111111111111111111111111111111112":
            return wallet.sol_balance
        else:
            # Check positions
            pos = wallet.positions.get(mint)
            return pos.balance if pos else 0.0
    
    def lock_funds(
        self,
        engine_id: str,
        amount_usd: float,
        mint: str = "USDC",
        timeout_seconds: float = 60.0,
    ) -> Optional[str]:
        """
        Lock funds for a pending trade.
        
        Returns lock_id if successful, None if insufficient funds.
        """
        wallet = self.get_or_create_wallet(engine_id)
        
        if wallet.available_cash() < amount_usd:
            return None
        
        lock_id = f"lock_{engine_id[:8]}_{uuid.uuid4().hex[:8]}"
        
        lock = FundLock(
            lock_id=lock_id,
            engine_id=engine_id,
            amount_usd=amount_usd,
            mint=mint,
            created_at=time.time(),
            expires_at=time.time() + timeout_seconds if timeout_seconds > 0 else 0,
        )
        
        wallet.locked_usd += amount_usd
        self._locks[lock_id] = lock
        
        return lock_id
    
    def unlock_funds(self, lock_id: str) -> bool:
        """Release a fund lock (trade cancelled/failed)."""
        lock = self._locks.get(lock_id)
        if not lock or lock.status != LockStatus.PENDING:
            return False
        
        wallet = self._wallets.get(lock.engine_id)
        if wallet:
            wallet.locked_usd = max(0, wallet.locked_usd - lock.amount_usd)
        
        lock.status = LockStatus.RELEASED
        return True
    
    def execute_paper_trade(
        self,
        engine_id: str,
        signal: TradeSignal,
        lock_id: Optional[str] = None,
        current_price: Optional[float] = None,
        liquidity_usd: float = 100000.0,
    ) -> ExecutionResult:
        """
        Execute a paper trade with friction.
        
        Args:
            engine_id: Engine identifier
            signal: Trade signal to execute
            lock_id: Optional lock to consume (if pre-locked)
            current_price: Current market price (if not in signal)
            liquidity_usd: Pool liquidity for slippage calculation
        """
        wallet = self.get_or_create_wallet(engine_id)
        
        # Get price
        price = current_price or signal.target_price
        if price <= 0:
            # Try position price for sells
            pos = wallet.positions.get(signal.mint)
            price = pos.avg_price if pos else 1.0
        
        if signal.action == SignalAction.BUY:
            return self._execute_buy(wallet, signal, price, liquidity_usd, lock_id)
        elif signal.action == SignalAction.SELL:
            return self._execute_sell(wallet, signal, price, liquidity_usd)
        else:
            return ExecutionResult(
                signal_id=signal.id,
                status=SignalStatus.REJECTED,
                error=f"Invalid action: {signal.action}",
            )
    
    def _execute_buy(
        self,
        wallet: EngineWallet,
        signal: TradeSignal,
        price: float,
        liquidity_usd: float,
        lock_id: Optional[str],
    ) -> ExecutionResult:
        """Execute a buy order."""
        size_usd = signal.size_usd
        
        # Check funds (either locked or available)
        if lock_id:
            lock = self._locks.get(lock_id)
            if not lock or lock.status != LockStatus.PENDING:
                return ExecutionResult(
                    signal_id=signal.id,
                    status=SignalStatus.FAILED,
                    error="Invalid or expired lock",
                )
            # Use locked amount
            wallet.locked_usd = max(0, wallet.locked_usd - lock.amount_usd)
            lock.status = LockStatus.EXECUTED
        else:
            if wallet.available_cash() < size_usd:
                return ExecutionResult(
                    signal_id=signal.id,
                    status=SignalStatus.FAILED,
                    error=f"Insufficient funds: {wallet.available_cash():.2f} < {size_usd:.2f}",
                )
        
        # Calculate friction
        friction = self._friction.calculate(
            size_usd=size_usd,
            price=price,
            liquidity_usd=liquidity_usd,
            is_buy=True,
        )
        
        effective_price = friction.effective_price
        tokens = size_usd / effective_price
        
        # Deduct cash and gas
        wallet.cash_usd -= size_usd
        wallet.sol_balance -= friction.gas_fee_sol
        
        # Update or create position
        if signal.mint in wallet.positions:
            pos = wallet.positions[signal.mint]
            total_value = (pos.balance * pos.avg_price) + (tokens * effective_price)
            pos.balance += tokens
            pos.avg_price = total_value / pos.balance
        else:
            wallet.positions[signal.mint] = Position(
                symbol=signal.symbol,
                mint=signal.mint,
                balance=tokens,
                avg_price=effective_price,
                engine_id=wallet.engine_id,
            )
        
        wallet.trades_count += 1
        
        return ExecutionResult(
            signal_id=signal.id,
            status=SignalStatus.FILLED,
            filled_amount=tokens,
            filled_price=effective_price,
            slippage_pct=friction.slippage_pct,
            fees_usd=friction.gas_fee_usd,
            tx_signature=self._generate_fake_sig(wallet.engine_id, signal.id),
        )
    
    def _execute_sell(
        self,
        wallet: EngineWallet,
        signal: TradeSignal,
        price: float,
        liquidity_usd: float,
    ) -> ExecutionResult:
        """Execute a sell order."""
        pos = wallet.positions.get(signal.mint)
        
        if not pos or pos.balance <= 0:
            return ExecutionResult(
                signal_id=signal.id,
                status=SignalStatus.FAILED,
                error="No position to sell",
            )
        
        # Calculate tokens to sell
        sell_value = min(signal.size_usd, pos.balance * price)
        tokens_to_sell = sell_value / price
        
        if tokens_to_sell > pos.balance:
            tokens_to_sell = pos.balance
        
        # Calculate friction
        friction = self._friction.calculate(
            size_usd=sell_value,
            price=price,
            liquidity_usd=liquidity_usd,
            is_buy=False,
        )
        
        effective_price = friction.effective_price
        proceeds = tokens_to_sell * effective_price
        
        # Calculate PnL
        cost_basis = tokens_to_sell * pos.avg_price
        pnl = proceeds - cost_basis
        wallet.total_pnl += pnl
        if pnl > 0:
            wallet.wins += 1
        
        # Update position
        pos.balance -= tokens_to_sell
        if pos.balance <= 0.0001:
            pos.balance = 0
        
        # Add proceeds and deduct gas
        wallet.cash_usd += proceeds
        wallet.sol_balance -= friction.gas_fee_sol
        
        wallet.trades_count += 1
        
        return ExecutionResult(
            signal_id=signal.id,
            status=SignalStatus.FILLED,
            filled_amount=tokens_to_sell,
            filled_price=effective_price,
            slippage_pct=friction.slippage_pct,
            fees_usd=friction.gas_fee_usd,
            tx_signature=self._generate_fake_sig(wallet.engine_id, signal.id),
        )
    
    def _generate_fake_sig(self, engine_id: str, signal_id: str) -> str:
        """Generate a deterministic fake transaction signature."""
        data = f"{engine_id}:{signal_id}:{time.time()}:{uuid.uuid4()}"
        hash_bytes = hashlib.sha256(data.encode()).hexdigest()
        return f"sim_{hash_bytes[:58]}"  # Solana sigs are ~88 chars
    
    def get_positions(self, engine_id: str) -> List[Position]:
        """Get all positions for an engine."""
        wallet = self.get_or_create_wallet(engine_id)
        return list(wallet.positions.values())
    
    def get_stats(self, engine_id: str) -> Dict:
        """Get wallet stats for an engine."""
        wallet = self.get_or_create_wallet(engine_id)
        return wallet.to_dict()
    
    def get_all_stats(self) -> Dict[str, Dict]:
        """Get stats for all engines."""
        return {eid: w.to_dict() for eid, w in self._wallets.items()}
    
    def cleanup_expired_locks(self) -> int:
        """Release expired locks. Returns count released."""
        released = 0
        for lock_id, lock in list(self._locks.items()):
            if lock.status == LockStatus.PENDING and lock.is_expired():
                self.unlock_funds(lock_id)
                lock.status = LockStatus.EXPIRED
                released += 1
        return released


# Global instance
_provider: Optional[VirtualWalletProvider] = None


def get_virtual_wallet() -> VirtualWalletProvider:
    """Get or create the global VirtualWalletProvider instance."""
    global _provider
    if _provider is None:
        _provider = VirtualWalletProvider()
    return _provider
