"""
Portfolio Data Models
====================

Shared portfolio state and position models for all trading engines.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime
from decimal import Decimal


@dataclass
class Position:
    """Individual position in a market."""
    market: str
    side: str  # "long" or "short"
    size: float  # Base asset amount
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    realized_pnl: float
    margin_requirement: float
    last_updated: datetime
    
    # Additional position metadata
    position_id: Optional[str] = None
    open_orders: Optional[List[str]] = None
    funding_payments: float = 0.0
    
    @property
    def notional_value(self) -> float:
        """Calculate notional value of position."""
        return abs(self.size) * self.mark_price
    
    @property
    def is_long(self) -> bool:
        """Check if position is long."""
        return self.size > 0
    
    @property
    def is_short(self) -> bool:
        """Check if position is short."""
        return self.size < 0
    
    @property
    def pnl_percentage(self) -> float:
        """Calculate PnL as percentage of entry value."""
        entry_value = abs(self.size) * self.entry_price
        if entry_value == 0:
            return 0.0
        return (self.unrealized_pnl / entry_value) * 100


@dataclass
class PositionSummary:
    """Summary of positions by market or category."""
    category: str  # "market", "asset_class", "strategy", etc.
    total_positions: int
    long_positions: int
    short_positions: int
    total_notional: float
    long_notional: float
    short_notional: float
    net_notional: float
    total_unrealized_pnl: float
    total_realized_pnl: float
    margin_used: float
    
    @property
    def net_exposure(self) -> float:
        """Calculate net exposure (long - short)."""
        return self.long_notional - self.short_notional
    
    @property
    def gross_exposure(self) -> float:
        """Calculate gross exposure (long + short)."""
        return self.long_notional + self.short_notional
    
    @property
    def leverage_ratio(self) -> float:
        """Calculate leverage ratio."""
        if self.margin_used == 0:
            return 0.0
        return self.gross_exposure / self.margin_used


@dataclass
class PortfolioState:
    """Complete portfolio state across all engines."""
    
    # Core portfolio metrics
    total_value: float  # Total portfolio value (collateral + unrealized PnL)
    total_collateral: float  # Total collateral deposited
    unrealized_pnl: float  # Total unrealized PnL across all positions
    realized_pnl: float  # Total realized PnL
    margin_used: float  # Total margin currently used
    margin_available: float  # Available margin for new positions
    
    # Health and risk metrics
    health_ratio: float  # Portfolio health ratio (1.0 = healthy, <0.1 = liquidation risk)
    leverage: float  # Overall portfolio leverage
    buying_power: float  # Available buying power
    
    # Position data
    positions: List[Position]  # All current positions
    position_count: int  # Total number of positions
    
    # Timestamps and metadata
    last_updated: datetime
    account_id: Optional[str] = None
    subaccount_id: Optional[str] = None
    
    # Additional portfolio metrics
    daily_pnl: float = 0.0  # PnL for current day
    funding_payments: float = 0.0  # Total funding payments
    fees_paid: float = 0.0  # Total fees paid
    
    def get_positions_by_market(self) -> Dict[str, Position]:
        """Get positions indexed by market."""
        return {pos.market: pos for pos in self.positions}
    
    def get_position_summary_by_asset(self) -> Dict[str, PositionSummary]:
        """Get position summary grouped by underlying asset."""
        asset_positions = {}
        
        for position in self.positions:
            # Extract asset from market (e.g., "SOL-PERP" -> "SOL")
            asset = position.market.split('-')[0] if '-' in position.market else position.market
            
            if asset not in asset_positions:
                asset_positions[asset] = []
            asset_positions[asset].append(position)
        
        # Create summaries
        summaries = {}
        for asset, positions in asset_positions.items():
            long_positions = [p for p in positions if p.is_long]
            short_positions = [p for p in positions if p.is_short]
            
            summaries[asset] = PositionSummary(
                category=asset,
                total_positions=len(positions),
                long_positions=len(long_positions),
                short_positions=len(short_positions),
                total_notional=sum(p.notional_value for p in positions),
                long_notional=sum(p.notional_value for p in long_positions),
                short_notional=sum(p.notional_value for p in short_positions),
                net_notional=sum(p.size * p.mark_price for p in positions),
                total_unrealized_pnl=sum(p.unrealized_pnl for p in positions),
                total_realized_pnl=sum(p.realized_pnl for p in positions),
                margin_used=sum(p.margin_requirement for p in positions)
            )
        
        return summaries
    
    def get_largest_positions(self, limit: int = 5) -> List[Position]:
        """Get largest positions by notional value."""
        return sorted(self.positions, key=lambda p: p.notional_value, reverse=True)[:limit]
    
    def get_most_profitable_positions(self, limit: int = 5) -> List[Position]:
        """Get most profitable positions by unrealized PnL."""
        return sorted(self.positions, key=lambda p: p.unrealized_pnl, reverse=True)[:limit]
    
    def get_portfolio_delta(self) -> float:
        """Calculate approximate portfolio delta (simplified)."""
        # Simplified delta calculation - in practice would be more sophisticated
        return sum(pos.size * pos.mark_price for pos in self.positions)
    
    @property
    def is_healthy(self) -> bool:
        """Check if portfolio is in healthy state."""
        return self.health_ratio > 0.2  # 20% threshold
    
    @property
    def is_at_risk(self) -> bool:
        """Check if portfolio is at liquidation risk."""
        return self.health_ratio < 0.1  # 10% threshold
    
    @property
    def utilization_ratio(self) -> float:
        """Calculate margin utilization ratio."""
        total_margin = self.margin_used + self.margin_available
        if total_margin == 0:
            return 0.0
        return self.margin_used / total_margin
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'total_value': self.total_value,
            'total_collateral': self.total_collateral,
            'unrealized_pnl': self.unrealized_pnl,
            'realized_pnl': self.realized_pnl,
            'margin_used': self.margin_used,
            'margin_available': self.margin_available,
            'health_ratio': self.health_ratio,
            'leverage': self.leverage,
            'buying_power': self.buying_power,
            'position_count': self.position_count,
            'daily_pnl': self.daily_pnl,
            'funding_payments': self.funding_payments,
            'fees_paid': self.fees_paid,
            'last_updated': self.last_updated.isoformat(),
            'account_id': self.account_id,
            'subaccount_id': self.subaccount_id,
            'positions': [
                {
                    'market': pos.market,
                    'side': pos.side,
                    'size': pos.size,
                    'entry_price': pos.entry_price,
                    'mark_price': pos.mark_price,
                    'unrealized_pnl': pos.unrealized_pnl,
                    'realized_pnl': pos.realized_pnl,
                    'margin_requirement': pos.margin_requirement,
                    'notional_value': pos.notional_value,
                    'last_updated': pos.last_updated.isoformat()
                }
                for pos in self.positions
            ]
        }