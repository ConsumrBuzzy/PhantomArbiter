"""
Friction Calculator - Unified Slippage and Fee Model.

Calculates realistic execution friction based on pool depth and volatility.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional


@dataclass
class FrictionConfig:
    """Friction calculation configuration."""
    base_spread_pct: float = 0.003  # 0.3% base spread
    size_impact_mult: float = 0.05  # Size impact multiplier
    volatility_mult: float = 3.0    # Choppy market multiplier
    mev_risk_rate: float = 0.05     # 5% chance of MEV attack
    mev_penalty_max: float = 0.02   # 2% max MEV penalty
    gas_fee_sol: float = 0.000005   # Base Solana gas
    priority_fee_sol: float = 0.0001  # Priority fee
    jito_tip_sol: float = 0.0001    # JITO tip


@dataclass
class FrictionResult:
    """Result of friction calculation."""
    slippage_pct: float
    slippage_usd: float
    gas_fee_sol: float
    gas_fee_usd: float
    total_friction_usd: float
    mev_applied: bool = False
    effective_price: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "slippage_pct": round(self.slippage_pct * 100, 4),
            "slippage_usd": round(self.slippage_usd, 4),
            "gas_fee_sol": self.gas_fee_sol,
            "gas_fee_usd": round(self.gas_fee_usd, 4),
            "total_friction_usd": round(self.total_friction_usd, 4),
            "mev_applied": self.mev_applied,
        }


class FrictionCalculator:
    """
    Calculates execution friction (slippage + fees).
    
    Factors:
    - Base spread (bid/ask)
    - Size impact (larger trades = more slippage)
    - Volatility multiplier
    - MEV/sandwich risk
    - Gas and priority fees
    """
    
    def __init__(self, config: Optional[FrictionConfig] = None) -> None:
        self.config = config or FrictionConfig()
        self._sol_price = 150.0  # Approximate for USD conversion
    
    def set_sol_price(self, price: float) -> None:
        """Update SOL price for fee calculations."""
        if price > 0:
            self._sol_price = price
    
    def calculate(
        self,
        size_usd: float,
        price: float,
        liquidity_usd: float = 100000.0,
        is_volatile: bool = False,
        is_buy: bool = True,
    ) -> FrictionResult:
        """
        Calculate total execution friction.
        
        Args:
            size_usd: Trade size in USD
            price: Current price of asset
            liquidity_usd: Pool liquidity (affects size impact)
            is_volatile: Whether market is choppy
            is_buy: Buy (slippage adds) or Sell (slippage subtracts)
            
        Returns:
            FrictionResult with all friction components
        """
        # Base slippage
        slippage = self.config.base_spread_pct
        
        # Size impact: larger trades relative to pool = more slippage
        if liquidity_usd > 0:
            size_ratio = size_usd / liquidity_usd
            size_impact = self.config.size_impact_mult * size_ratio
            slippage += size_impact
        
        # Volatility multiplier
        if is_volatile:
            slippage *= self.config.volatility_mult
        
        # MEV risk
        mev_applied = False
        if random.random() < self.config.mev_risk_rate:
            mev_penalty = random.uniform(0, self.config.mev_penalty_max)
            slippage += mev_penalty
            mev_applied = True
        
        # Cap slippage at 10%
        slippage = min(slippage, 0.10)
        
        # Calculate slippage cost
        slippage_usd = size_usd * slippage
        
        # Gas fees
        total_gas_sol = (
            self.config.gas_fee_sol +
            self.config.priority_fee_sol +
            self.config.jito_tip_sol
        )
        gas_fee_usd = total_gas_sol * self._sol_price
        
        # Total friction
        total_friction = slippage_usd + gas_fee_usd
        
        # Effective price (after slippage)
        if is_buy:
            effective_price = price * (1 + slippage)
        else:
            effective_price = price * (1 - slippage)
        
        return FrictionResult(
            slippage_pct=slippage,
            slippage_usd=slippage_usd,
            gas_fee_sol=total_gas_sol,
            gas_fee_usd=gas_fee_usd,
            total_friction_usd=total_friction,
            mev_applied=mev_applied,
            effective_price=effective_price,
        )
    
    def estimate_gas_only(self) -> float:
        """Estimate gas fee in USD (no slippage)."""
        total_gas_sol = (
            self.config.gas_fee_sol +
            self.config.priority_fee_sol
        )
        return total_gas_sol * self._sol_price


# Global instance
_calculator: Optional[FrictionCalculator] = None


def get_friction_calculator() -> FrictionCalculator:
    """Get or create the global FrictionCalculator instance."""
    global _calculator
    if _calculator is None:
        _calculator = FrictionCalculator()
    return _calculator
