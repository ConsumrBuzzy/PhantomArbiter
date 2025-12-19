"""
V1.0: Arbitrage Risk Manager
============================
Validates opportunities before execution.
"""

from dataclasses import dataclass
from typing import Tuple, Optional
from config.settings import Settings


class ArbitrageRiskManager:
    """
    Risk manager for arbitrage trades.
    
    Validates that an opportunity is truly profitable
    after accounting for all costs.
    """
    
    def __init__(self):
        self.min_profit_usd = getattr(Settings, 'MIN_PROFIT_AFTER_FEES', 0.10)
        self.max_slippage_pct = getattr(Settings, 'MAX_SLIPPAGE_PCT', 0.5)
        self.gas_buffer_sol = getattr(Settings, 'GAS_BUFFER_SOL', 0.05)
        
    def validate_opportunity(self, opportunity) -> Tuple[bool, str]:
        """
        Validate if an opportunity is safe to execute.
        
        Returns:
            (is_valid, reason)
        """
        # Check net profitability
        if opportunity.net_profit_usd < self.min_profit_usd:
            return False, f"Net profit ${opportunity.net_profit_usd:.2f} < min ${self.min_profit_usd:.2f}"
        
        # Check spread vs expected slippage
        if opportunity.spread_pct < self.max_slippage_pct:
            return False, f"Spread {opportunity.spread_pct:.2f}% may be eaten by slippage"
        
        # Check confidence
        if opportunity.confidence < 0.8:
            return False, f"Low confidence: {opportunity.confidence:.2f}"
        
        return True, f"Validated: Net profit ${opportunity.net_profit_usd:.2f}"
    
    def calculate_safe_size(
        self, 
        opportunity, 
        available_balance: float
    ) -> float:
        """
        Calculate safe position size for an opportunity.
        
        Args:
            opportunity: The arbitrage opportunity
            available_balance: Available USD balance
            
        Returns:
            Recommended trade size in USD
        """
        max_from_settings = getattr(Settings, 'MAX_TRADE_SIZE_USD', 100.0)
        max_from_liquidity = opportunity.max_size_usd
        max_from_balance = available_balance * 0.5  # Never use more than 50% in one trade
        
        return min(max_from_settings, max_from_liquidity, max_from_balance)
