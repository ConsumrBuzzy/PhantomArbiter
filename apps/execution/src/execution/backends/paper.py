"""
Paper Trading Backend - Simulated execution.

Provides realistic trade simulation with slippage and fees.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, List

from execution.order_bus import (
    TradeSignal,
    ExecutionResult,
    SignalStatus,
    SignalAction,
)


@dataclass
class Position:
    """A trading position."""
    symbol: str
    mint: str
    balance: float
    avg_price: float
    entry_time_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    status: str = "OPEN"
    
    def to_dict(self) -> Dict:
        return {
            "symbol": self.symbol,
            "mint": self.mint,
            "balance": self.balance,
            "avg_price": self.avg_price,
            "entry_time_ms": self.entry_time_ms,
            "status": self.status,
        }


@dataclass
class PaperConfig:
    """Paper trading configuration."""
    initial_cash: float = 1000.0
    initial_sol: float = 0.1
    base_slippage_pct: float = 0.003  # 0.3%
    slippage_impact_mult: float = 0.05
    volatility_mult: float = 3.0
    tx_fee_sol: float = 0.0001
    mev_risk_rate: float = 0.05  # 5% chance
    mev_penalty_max: float = 0.02  # 2% max extra slippage
    failure_rate: float = 0.02  # 2% chance


class PaperBackend:
    """
    Paper trading execution backend.
    
    Simulates trades with realistic:
    - Slippage based on size/liquidity
    - Transaction fees
    - MEV/sandwich risk
    - Partial fills and failures
    """
    
    def __init__(self, config: Optional[PaperConfig] = None) -> None:
        self.config = config or PaperConfig()
        self._cash = self.config.initial_cash
        self._sol = self.config.initial_sol
        self._positions: Dict[str, Position] = {}
        self._trades: List[Dict] = []
        self._start_time = time.time()
        
        # Stats
        self._total_pnl = 0.0
        self._trades_count = 0
        self._wins = 0
    
    def execute(self, signal: TradeSignal) -> ExecutionResult:
        """Execute a trade signal with paper simulation."""
        
        # Simulate network failures
        if random.random() < self.config.failure_rate:
            return ExecutionResult(
                signal_id=signal.id,
                status=SignalStatus.FAILED,
                error="Simulated network timeout",
            )
        
        # Get price (would come from market data in real impl)
        current_price = self._get_simulated_price(signal)
        if current_price <= 0:
            return ExecutionResult(
                signal_id=signal.id,
                status=SignalStatus.FAILED,
                error="No price available",
            )
        
        if signal.action == SignalAction.BUY:
            return self._execute_buy(signal, current_price)
        elif signal.action == SignalAction.SELL:
            return self._execute_sell(signal, current_price)
        else:
            return ExecutionResult(
                signal_id=signal.id,
                status=SignalStatus.REJECTED,
                error=f"Invalid action: {signal.action}",
            )
    
    def _execute_buy(
        self, signal: TradeSignal, price: float
    ) -> ExecutionResult:
        """Execute a buy order."""
        size_usd = signal.size_usd
        
        # Check cash
        if size_usd > self._cash:
            return ExecutionResult(
                signal_id=signal.id,
                status=SignalStatus.FAILED,
                error=f"Insufficient funds: {self._cash:.2f} < {size_usd:.2f}",
            )
        
        # Calculate slippage
        slippage = self._calculate_slippage(size_usd)
        
        # Apply MEV penalty
        if random.random() < self.config.mev_risk_rate:
            mev_penalty = random.uniform(0, self.config.mev_penalty_max)
            slippage += mev_penalty
        
        effective_price = price * (1 + slippage)
        tokens = size_usd / effective_price
        
        # Deduct cash and fees
        self._cash -= size_usd
        self._sol -= self.config.tx_fee_sol
        
        # Update or create position
        if signal.mint in self._positions:
            pos = self._positions[signal.mint]
            # Average price
            total_value = (pos.balance * pos.avg_price) + (tokens * effective_price)
            pos.balance += tokens
            pos.avg_price = total_value / pos.balance
        else:
            self._positions[signal.mint] = Position(
                symbol=signal.symbol,
                mint=signal.mint,
                balance=tokens,
                avg_price=effective_price,
            )
        
        self._trades_count += 1
        
        return ExecutionResult(
            signal_id=signal.id,
            status=SignalStatus.FILLED,
            filled_amount=tokens,
            filled_price=effective_price,
            slippage_pct=slippage,
            fees_usd=self.config.tx_fee_sol * 150,  # Approx SOL price
            tx_signature=f"paper_{signal.id}_{int(time.time())}",
        )
    
    def _execute_sell(
        self, signal: TradeSignal, price: float
    ) -> ExecutionResult:
        """Execute a sell order."""
        pos = self._positions.get(signal.mint)
        
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
        
        # Calculate slippage
        slippage = self._calculate_slippage(sell_value)
        effective_price = price * (1 - slippage)
        
        proceeds = tokens_to_sell * effective_price
        
        # Calculate PnL
        cost_basis = tokens_to_sell * pos.avg_price
        pnl = proceeds - cost_basis
        self._total_pnl += pnl
        if pnl > 0:
            self._wins += 1
        
        # Update position
        pos.balance -= tokens_to_sell
        if pos.balance <= 0.0001:
            pos.balance = 0
            pos.status = "CLOSED"
        
        # Add proceeds
        self._cash += proceeds
        self._sol -= self.config.tx_fee_sol
        
        self._trades_count += 1
        
        return ExecutionResult(
            signal_id=signal.id,
            status=SignalStatus.FILLED,
            filled_amount=tokens_to_sell,
            filled_price=effective_price,
            slippage_pct=slippage,
            fees_usd=self.config.tx_fee_sol * 150,
            tx_signature=f"paper_{signal.id}_{int(time.time())}",
        )
    
    def _calculate_slippage(self, size_usd: float) -> float:
        """Calculate realistic slippage."""
        # Base + size impact
        base = self.config.base_slippage_pct
        size_impact = self.config.slippage_impact_mult * (size_usd / 10000)
        
        return min(base + size_impact, 0.10)  # Cap at 10%
    
    def _get_simulated_price(self, signal: TradeSignal) -> float:
        """Get simulated price (would use aggregator in real impl)."""
        # Use target price if provided
        if signal.target_price > 0:
            return signal.target_price
        
        # Check existing position for reference
        pos = self._positions.get(signal.mint)
        if pos:
            return pos.avg_price * (1 + random.uniform(-0.05, 0.05))
        
        # Default dummy price for testing
        return 1.0
    
    def get_positions(self) -> List[Position]:
        """Get all positions."""
        return list(self._positions.values())
    
    def get_cash(self) -> float:
        """Get current cash balance."""
        return self._cash
    
    def get_pnl(self) -> Dict:
        """Get PnL summary."""
        return {
            "realized_pnl": self._total_pnl,
            "unrealized_pnl": 0,  # Would calculate from current prices
            "trades_count": self._trades_count,
            "win_rate": self._wins / max(self._trades_count, 1),
        }


# Global instance
_paper_backend: Optional[PaperBackend] = None


def get_paper_backend() -> PaperBackend:
    """Get or create the global PaperBackend instance."""
    global _paper_backend
    if _paper_backend is None:
        _paper_backend = PaperBackend()
    return _paper_backend
