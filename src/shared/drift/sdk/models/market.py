"""
Market Data Models
=================

Shared market data models for all trading engines.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum


class MarketStatus(Enum):
    """Market status enumeration."""
    ACTIVE = "active"
    PAUSED = "paused"
    DELISTED = "delisted"
    SETTLEMENT = "settlement"


class OrderbookSide(Enum):
    """Orderbook side enumeration."""
    BID = "bid"
    ASK = "ask"


@dataclass
class OrderbookLevel:
    """Single level in the orderbook."""
    price: float
    size: float
    orders: int = 1  # Number of orders at this level
    
    @property
    def notional(self) -> float:
        """Calculate notional value at this level."""
        return self.price * self.size


@dataclass
class OrderbookSnapshot:
    """Complete orderbook snapshot."""
    
    # Market identification
    market: str
    timestamp: datetime
    
    # Orderbook data
    bids: List[OrderbookLevel]  # Sorted by price descending
    asks: List[OrderbookLevel]  # Sorted by price ascending
    
    # Sequence and versioning
    sequence_number: Optional[int] = None
    
    @property
    def best_bid(self) -> Optional[OrderbookLevel]:
        """Get best bid (highest price)."""
        return self.bids[0] if self.bids else None
    
    @property
    def best_ask(self) -> Optional[OrderbookLevel]:
        """Get best ask (lowest price)."""
        return self.asks[0] if self.asks else None
    
    @property
    def spread(self) -> float:
        """Calculate bid-ask spread."""
        if not self.best_bid or not self.best_ask:
            return 0.0
        return self.best_ask.price - self.best_bid.price
    
    @property
    def spread_bps(self) -> float:
        """Calculate spread in basis points."""
        if not self.best_bid or not self.best_ask:
            return 0.0
        mid_price = (self.best_bid.price + self.best_ask.price) / 2
        if mid_price == 0:
            return 0.0
        return (self.spread / mid_price) * 10000
    
    @property
    def mid_price(self) -> float:
        """Calculate mid price."""
        if not self.best_bid or not self.best_ask:
            return 0.0
        return (self.best_bid.price + self.best_ask.price) / 2
    
    def get_depth(self, side: OrderbookSide, depth_levels: int = 5) -> List[OrderbookLevel]:
        """Get orderbook depth for specified side."""
        if side == OrderbookSide.BID:
            return self.bids[:depth_levels]
        else:
            return self.asks[:depth_levels]
    
    def calculate_liquidity(self, side: OrderbookSide, max_levels: int = 10) -> float:
        """Calculate available liquidity on one side."""
        levels = self.get_depth(side, max_levels)
        return sum(level.size for level in levels)
    
    def estimate_market_impact(self, side: OrderbookSide, size: float) -> Dict[str, float]:
        """Estimate market impact for a given trade size."""
        levels = self.bids if side == OrderbookSide.ASK else self.asks  # Opposite side for impact
        
        if not levels:
            return {'average_price': 0.0, 'slippage': 0.0, 'impact_bps': 0.0}
        
        remaining_size = size
        total_cost = 0.0
        levels_consumed = 0
        
        for level in levels:
            if remaining_size <= 0:
                break
            
            consumed_size = min(remaining_size, level.size)
            total_cost += consumed_size * level.price
            remaining_size -= consumed_size
            levels_consumed += 1
        
        if size == 0 or total_cost == 0:
            return {'average_price': 0.0, 'slippage': 0.0, 'impact_bps': 0.0}
        
        average_price = total_cost / (size - remaining_size)
        reference_price = levels[0].price
        slippage = (average_price - reference_price) / reference_price if reference_price != 0 else 0.0
        impact_bps = abs(slippage) * 10000
        
        return {
            'average_price': average_price,
            'slippage': slippage,
            'impact_bps': impact_bps,
            'levels_consumed': levels_consumed,
            'unfilled_size': remaining_size
        }


@dataclass
class MarketSummary:
    """Market summary statistics."""
    
    # Market identification
    market: str
    base_asset: str
    quote_asset: str
    
    # Current prices
    mark_price: float  # Current mark price
    index_price: Optional[float] = None  # Underlying index price
    last_price: Optional[float] = None  # Last trade price
    
    # 24h statistics
    price_24h_change: float = 0.0  # 24h price change
    price_24h_change_pct: float = 0.0  # 24h price change percentage
    volume_24h: float = 0.0  # 24h volume
    high_24h: Optional[float] = None  # 24h high
    low_24h: Optional[float] = None  # 24h low
    
    # Funding and interest (for perpetuals)
    funding_rate: Optional[float] = None  # Current funding rate
    predicted_funding_rate: Optional[float] = None  # Next funding rate
    funding_rate_timestamp: Optional[datetime] = None
    
    # Open interest and positions
    open_interest: Optional[float] = None  # Total open interest
    open_interest_change_24h: Optional[float] = None
    
    # Market status and metadata
    status: MarketStatus = MarketStatus.ACTIVE
    min_order_size: float = 0.0
    tick_size: float = 0.0
    step_size: float = 0.0
    
    # Timestamps
    timestamp: datetime
    
    @property
    def is_active(self) -> bool:
        """Check if market is active for trading."""
        return self.status == MarketStatus.ACTIVE
    
    @property
    def funding_rate_annualized(self) -> Optional[float]:
        """Calculate annualized funding rate."""
        if self.funding_rate is None:
            return None
        # Assuming 8-hour funding periods (3 per day)
        return self.funding_rate * 365 * 3
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'market': self.market,
            'base_asset': self.base_asset,
            'quote_asset': self.quote_asset,
            'mark_price': self.mark_price,
            'index_price': self.index_price,
            'last_price': self.last_price,
            'price_24h_change': self.price_24h_change,
            'price_24h_change_pct': self.price_24h_change_pct,
            'volume_24h': self.volume_24h,
            'high_24h': self.high_24h,
            'low_24h': self.low_24h,
            'funding_rate': self.funding_rate,
            'predicted_funding_rate': self.predicted_funding_rate,
            'funding_rate_timestamp': self.funding_rate_timestamp.isoformat() if self.funding_rate_timestamp else None,
            'funding_rate_annualized': self.funding_rate_annualized,
            'open_interest': self.open_interest,
            'open_interest_change_24h': self.open_interest_change_24h,
            'status': self.status.value,
            'min_order_size': self.min_order_size,
            'tick_size': self.tick_size,
            'step_size': self.step_size,
            'timestamp': self.timestamp.isoformat(),
            'is_active': self.is_active
        }


@dataclass
class MarketData:
    """Comprehensive market data container."""
    
    # Market summary
    summary: MarketSummary
    
    # Orderbook data
    orderbook: Optional[OrderbookSnapshot] = None
    
    # Recent trades
    recent_trades: List[Dict[str, Any]] = None
    
    # Technical indicators (optional)
    indicators: Dict[str, float] = None
    
    # Volatility metrics
    volatility_1h: Optional[float] = None
    volatility_24h: Optional[float] = None
    volatility_7d: Optional[float] = None
    
    # Liquidity metrics
    liquidity_score: Optional[float] = None  # 0-1 score
    average_spread_bps: Optional[float] = None
    
    # Market microstructure
    trade_frequency: Optional[float] = None  # Trades per minute
    average_trade_size: Optional[float] = None
    
    # Data quality
    data_age_ms: float = 0.0  # Age of data in milliseconds
    data_quality_score: float = 1.0  # 0-1 quality score
    
    def __post_init__(self):
        """Initialize default values."""
        if self.recent_trades is None:
            self.recent_trades = []
        if self.indicators is None:
            self.indicators = {}
    
    @property
    def is_stale(self, max_age_ms: float = 5000) -> bool:
        """Check if market data is stale."""
        return self.data_age_ms > max_age_ms
    
    @property
    def effective_spread(self) -> Optional[float]:
        """Get effective spread from orderbook or summary."""
        if self.orderbook:
            return self.orderbook.spread_bps
        return self.average_spread_bps
    
    def get_liquidity_assessment(self) -> Dict[str, Any]:
        """Get comprehensive liquidity assessment."""
        assessment = {
            'liquidity_score': self.liquidity_score or 0.0,
            'spread_bps': self.effective_spread or 0.0,
            'trade_frequency': self.trade_frequency or 0.0,
            'volume_24h': self.summary.volume_24h
        }
        
        # Calculate overall liquidity grade
        score = assessment['liquidity_score']
        if score > 0.8:
            grade = 'A'
        elif score > 0.6:
            grade = 'B'
        elif score > 0.4:
            grade = 'C'
        elif score > 0.2:
            grade = 'D'
        else:
            grade = 'F'
        
        assessment['liquidity_grade'] = grade
        return assessment
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'summary': self.summary.to_dict(),
            'orderbook': {
                'market': self.orderbook.market,
                'timestamp': self.orderbook.timestamp.isoformat(),
                'best_bid': self.orderbook.best_bid.price if self.orderbook.best_bid else None,
                'best_ask': self.orderbook.best_ask.price if self.orderbook.best_ask else None,
                'spread_bps': self.orderbook.spread_bps,
                'mid_price': self.orderbook.mid_price
            } if self.orderbook else None,
            'recent_trades_count': len(self.recent_trades),
            'indicators': self.indicators,
            'volatility_1h': self.volatility_1h,
            'volatility_24h': self.volatility_24h,
            'volatility_7d': self.volatility_7d,
            'liquidity_assessment': self.get_liquidity_assessment(),
            'trade_frequency': self.trade_frequency,
            'average_trade_size': self.average_trade_size,
            'data_age_ms': self.data_age_ms,
            'data_quality_score': self.data_quality_score,
            'is_stale': self.is_stale()
        }