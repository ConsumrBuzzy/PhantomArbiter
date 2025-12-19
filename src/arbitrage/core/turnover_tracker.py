"""
V1.0: Turnover Tracker
======================
Tracks how many times the budget has cycled through trades.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import List
import time


@dataclass
class TradeRecord:
    """Single trade record."""
    timestamp: float
    volume_usd: float
    profit_usd: float
    strategy: str
    pair: str


class TurnoverTracker:
    """
    Tracks budget turnover and daily performance.
    
    Turnover = total_volume / budget
    
    Example:
        $500 budget, trade $100 five times = 1x turnover
        $500 budget, trade $500 ten times = 10x turnover
    """
    
    def __init__(self, budget: float = 500.0):
        self.budget = budget
        self.trades: List[TradeRecord] = []
        self._day_start = date.today()
        
    def _check_day_rollover(self):
        """Reset daily stats at midnight."""
        if date.today() != self._day_start:
            self.trades = []
            self._day_start = date.today()
    
    def record_trade(
        self, 
        volume_usd: float, 
        profit_usd: float,
        strategy: str = "SPATIAL",
        pair: str = "UNKNOWN"
    ):
        """Record a completed trade."""
        self._check_day_rollover()
        
        self.trades.append(TradeRecord(
            timestamp=time.time(),
            volume_usd=volume_usd,
            profit_usd=profit_usd,
            strategy=strategy,
            pair=pair
        ))
    
    @property
    def daily_volume(self) -> float:
        """Total volume traded today."""
        self._check_day_rollover()
        return sum(t.volume_usd for t in self.trades)
    
    @property
    def daily_profit(self) -> float:
        """Total profit today."""
        self._check_day_rollover()
        return sum(t.profit_usd for t in self.trades)
    
    @property
    def trade_count(self) -> int:
        """Number of trades today."""
        self._check_day_rollover()
        return len(self.trades)
    
    @property
    def turnover_ratio(self) -> float:
        """How many times budget has turned over today."""
        return self.daily_volume / self.budget if self.budget > 0 else 0
    
    @property
    def daily_return_pct(self) -> float:
        """Daily return as percentage of budget."""
        return (self.daily_profit / self.budget) * 100 if self.budget > 0 else 0
    
    @property
    def effective_apy(self) -> float:
        """Annualized return based on today's performance."""
        return self.daily_return_pct * 365
    
    def get_strategy_breakdown(self) -> dict:
        """Get profit breakdown by strategy."""
        breakdown = {}
        for trade in self.trades:
            if trade.strategy not in breakdown:
                breakdown[trade.strategy] = {'volume': 0, 'profit': 0, 'trades': 0}
            breakdown[trade.strategy]['volume'] += trade.volume_usd
            breakdown[trade.strategy]['profit'] += trade.profit_usd
            breakdown[trade.strategy]['trades'] += 1
        return breakdown
    
    def get_summary(self) -> str:
        """Get a text summary of today's performance."""
        return (
            f"📊 Daily Summary\n"
            f"├─ Turnover: {self.turnover_ratio:.1f}x\n"
            f"├─ Trades: {self.trade_count}\n"
            f"├─ Volume: ${self.daily_volume:,.2f}\n"
            f"├─ Profit: ${self.daily_profit:+,.2f} ({self.daily_return_pct:+.2f}%)\n"
            f"└─ APY (if consistent): {self.effective_apy:+,.0f}%"
        )
