"""
V1.0: Trade Tracker
===================
Handles all financial accounting and trade history for the Arbiter.
Extracted from arbiter.py for architectural cleanliness.
"""

import time
from typing import List, Dict, Optional, Any
from src.shared.system.logging import Logger
from src.arbiter.core.turnover_tracker import TurnoverTracker

class TradeTracker:
    """
    Manages balances, trade history, and PnL statistics.
    """
    
    def __init__(self, budget: float, gas_budget: float):
        self.starting_balance = budget
        self.current_balance = budget
        self.gas_balance = gas_budget # Gas in USD equivalent
        
        self.tracker = TurnoverTracker(budget=budget)
        self.total_trades = 0
        self.total_profit = 0.0
        self.total_gas_spent = 0.0
        self.trades: List[Dict] = []
        
    def record_trade(self, 
                     pair: str, 
                     net_profit: float, 
                     fees: float, 
                     mode: str, 
                     engine: str,
                     trade_size: float = 0.0):
        """Record a completed trade and update balances."""
        self.current_balance += net_profit
        self.total_profit += net_profit
        self.total_trades += 1
        
        # Record in TurnoverTracker (handles volume-based stats)
        self.tracker.record_trade(
            volume_usd=trade_size,
            profit_usd=net_profit,
            strategy="SPATIAL", # Default, can be refined
            pair=pair
        )
        
        # Log to internal history
        trade_record = {
            "pair": pair,
            "profit": net_profit,
            "fees": fees,
            "timestamp": time.time(),
            "mode": mode,
            "engine": engine
        }
        self.trades.append(trade_record)
        
        return trade_record

    def update_gas_spent(self, gas_usd: float):
        """Track gas costs."""
        self.total_gas_spent += gas_usd
        self.gas_balance -= gas_usd

    def get_stats(self) -> Dict[str, Any]:
        """Get summary of tracking state."""
        return {
            "starting_balance": self.starting_balance,
            "current_balance": self.current_balance,
            "total_profit": self.total_profit,
            "total_trades": self.total_trades,
            "roi_pct": (self.total_profit / self.starting_balance * 100) if self.starting_balance > 0 else 0,
            "gas_spent": self.total_gas_spent
        }
