"""
Drift Market Data Manager
========================

Comprehensive market data access for Drift Protocol.
Provides real-time and historical market data with caching and subscriptions.

Features:
- Real-time orderbook data with L2 depth
- Trade history and analytics
- OHLCV candle data
- Market statistics and metrics
- Funding rate history
- Real-time data subscriptions
- Intelligent caching with TTL

Usage:
    market_data = DriftMarketDataManager(drift_adapter)
    
    # Get orderbook
    orderbook = await market_data.get_orderbook("SOL-PERP", depth=20)
    
    # Get recent trades
    trades = await market_data.get_recent_trades("SOL-PERP", limit=100)
    
    # Subscribe to real-time updates
    await market_data.subscribe_to_trades("SOL-PERP", trade_callback)
"""

import asyncio
import time
from typing import Optional, List, Dict, Any, Callable, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import defaultdict

from src.shared.system.logging import Logger
from src.shared.drift.cache_manager import CacheManager


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class OrderBook:
    """L2 orderbook data structure."""
    market: str
    bids: List[Tuple[float, float]]  # [(price, size), ...]
    asks: List[Tuple[float, float]]  # [(price, size), ...]
    timestamp: datetime
    sequence: int
    spread: float
    mid_price: float
    
    def __post_init__(self):
        """Calculate derived fields."""
        if self.bids and self.asks:
            self.spread = self.asks[0][0] - self.bids[0][0]
            self.mid_price = (self.asks[0][0] + self.bids[0][0]) / 2
        else:
            self.spread = 0.0
            self.mid_price = 0.0


@dataclass
class Trade:
    """Trade data structure."""
    market: str
    price: float
    size: float
    side: str  # "buy" or "sell"
    timestamp: datetime
    trade_id: str
    sequence: int


@dataclass
class Candle:
    """OHLCV candle data structure."""
    market: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    timestamp: datetime
    resolution: str  # "1m", "5m", "1h", "1d"
    trades_count: int
    vwap: float
    
    def __post_init__(self):
        """Calculate derived fields."""
        if self.volume > 0:
            # VWAP would be calculated from trade data in real implementation
            self.vwap = (self.high + self.low + self.close) / 3
        else:
            self.vwap = self.close


@dataclass
class MarketStats:
    """24-hour market statistics."""
    market: str
    last_price: float
    price_change_24h: float
    price_change_percent_24h: float
    high_24h: float
    low_24h: float
    volume_24h: float
    volume_quote_24h: float
    trades_count_24h: int
    funding_rate: float
    funding_rate_8h: float
    open_interest: float
    mark_price: float
    index_price: float
    timestamp: datetime


@dataclass
class FundingPayment:
    """Historical funding payment data."""
    market: str
    funding_rate: float
    funding_rate_8h: float
    payment_amount: float
    timestamp: datetime
    position_size: float


@dataclass
class Subscription:
    """Data subscription tracking."""
    id: str
    market: str
    data_type: str  # "trades", "orderbook", "candles"
    callback: Callable
    active: bool
    created_at: datetime


# =============================================================================
# DRIFT MARKET DATA MANAGER
# =============================================================================

class DriftMarketDataManager:
    """
    Comprehensive market data access for Drift Protocol.
    
    Provides real-time and historical market data with intelligent caching,
    subscriptions, and analytics built on the DriftAdapter singleton.
    """
    
    def __init__(self, drift_adapter):
        """
        Initialize market data manager.
        
        Args:
            drift_adapter: DriftAdapter instance (singleton-enabled)
        """
        self.drift_adapter = drift_adapter
        self._cache = CacheManager()
        self._subscriptions: Dict[str, Subscription] = {}
        self._next_subscription_id = 1
        
        # Cache TTL settings (seconds)
        self.CACHE_TTLS = {
            "orderbook": 1,        # 1 second
            "trades": 5,           # 5 seconds
            "candles": 300,        # 5 minutes
            "market_stats": 60,    # 1 minute
            "funding_history": 300, # 5 minutes
        }
        
        # Market data storage for subscriptions
        self._orderbooks: Dict[str, OrderBook] = {}
        self._recent_trades: Dict[str, List[Trade]] = defaultdict(list)
        
        # Subscription callbacks
        self._trade_callbacks: Dict[str, List[Callable]] = defaultdict(list)
        self._orderbook_callbacks: Dict[str, List[Callable]] = defaultdict(list)
    
    # =========================================================================
    # ORDERBOOK DATA
    # =========================================================================
    
    async def get_orderbook(
        self,
        market: str,
        depth: int = 20
    ) -> Optional[OrderBook]:
        """
        Get L2 orderbook with specified depth.
        
        Args:
            market: Market symbol (e.g., "SOL-PERP")
            depth: Number of price levels per side (default: 20)
        
        Returns:
            OrderBook object or None if unavailable
        """
        cache_key = f"orderbook:{market}:{depth}"
        
        # Check cache first
        cached = await self._cache.get(cache_key)
        if cached:
            return OrderBook(**cached)
        
        try:
            Logger.debug(f"[MarketData] Fetching orderbook: {market} (depth: {depth})")
            
            # TODO: Implement actual Drift SDK orderbook fetching
            # For now, simulate orderbook data
            orderbook = await self._fetch_orderbook_from_drift(market, depth)
            
            if orderbook:
                # Cache the result
                await self._cache.set(
                    cache_key,
                    asdict(orderbook),
                    ttl=self.CACHE_TTLS["orderbook"]
                )
                
                # Update subscription data
                self._orderbooks[market] = orderbook
                
                # Notify subscribers
                await self._notify_orderbook_subscribers(market, orderbook)
            
            return orderbook
            
        except Exception as e:
            Logger.error(f"[MarketData] Failed to fetch orderbook for {market}: {e}")
            return None
    
    async def _fetch_orderbook_from_drift(self, market: str, depth: int) -> Optional[OrderBook]:
        """Fetch orderbook from Drift Protocol."""
        try:
            # TODO: Implement actual Drift SDK orderbook API
            # This would use the DLOB (Decentralized Limit Order Book) API
            
            # For now, simulate realistic orderbook data
            base_price = 150.0  # SOL price simulation
            
            # Generate realistic bid/ask levels
            bids = []
            asks = []
            
            for i in range(depth):
                # Bids (decreasing prices)
                bid_price = base_price - (i * 0.01)
                bid_size = 1.0 + (i * 0.1)
                bids.append((bid_price, bid_size))
                
                # Asks (increasing prices)
                ask_price = base_price + 0.01 + (i * 0.01)
                ask_size = 1.0 + (i * 0.1)
                asks.append((ask_price, ask_size))
            
            return OrderBook(
                market=market,
                bids=bids,
                asks=asks,
                timestamp=datetime.now(),
                sequence=int(time.time() * 1000),
                spread=0.0,  # Will be calculated in __post_init__
                mid_price=0.0  # Will be calculated in __post_init__
            )
            
        except Exception as e:
            Logger.error(f"[MarketData] Drift orderbook fetch failed: {e}")
            return None
    
    # =========================================================================
    # TRADE DATA
    # =========================================================================
    
    async def get_recent_trades(
        self,
        market: str,
        limit: int = 100
    ) -> List[Trade]:
        """
        Get recent trade history.
        
        Args:
            market: Market symbol (e.g., "SOL-PERP")
            limit: Maximum number of trades to return
        
        Returns:
            List of Trade objects
        """
        cache_key = f"trades:{market}:{limit}"
        
        # Check cache first
        cached = await self._cache.get(cache_key)
        if cached:
            return [Trade(**trade) for trade in cached]
        
        try:
            Logger.debug(f"[MarketData] Fetching recent trades: {market} (limit: {limit})")
            
            # TODO: Implement actual Drift SDK trade history fetching
            trades = await self._fetch_trades_from_drift(market, limit)
            
            if trades:
                # Cache the result
                await self._cache.set(
                    cache_key,
                    [asdict(trade) for trade in trades],
                    ttl=self.CACHE_TTLS["trades"]
                )
                
                # Update subscription data
                self._recent_trades[market] = trades[-50:]  # Keep last 50 trades
                
                # Notify subscribers
                for trade in trades[-10:]:  # Notify for last 10 trades
                    await self._notify_trade_subscribers(market, trade)
            
            return trades or []
            
        except Exception as e:
            Logger.error(f"[MarketData] Failed to fetch trades for {market}: {e}")
            return []
    
    async def _fetch_trades_from_drift(self, market: str, limit: int) -> List[Trade]:
        """Fetch trade history from Drift Protocol."""
        try:
            # TODO: Implement actual Drift SDK trade history API
            
            # For now, simulate realistic trade data
            trades = []
            base_price = 150.0
            
            for i in range(limit):
                # Simulate price movement
                price_change = (i % 10 - 5) * 0.01
                price = base_price + price_change
                
                trade = Trade(
                    market=market,
                    price=price,
                    size=0.1 + (i % 5) * 0.1,
                    side="buy" if i % 2 == 0 else "sell",
                    timestamp=datetime.now() - timedelta(seconds=i * 10),
                    trade_id=f"trade_{market}_{int(time.time())}_{i}",
                    sequence=int(time.time() * 1000) - i
                )
                trades.append(trade)
            
            # Sort by timestamp (newest first)
            trades.sort(key=lambda x: x.timestamp, reverse=True)
            return trades
            
        except Exception as e:
            Logger.error(f"[MarketData] Drift trade fetch failed: {e}")
            return []
    
    # =========================================================================
    # CANDLE DATA
    # =========================================================================
    
    async def get_candles(
        self,
        market: str,
        resolution: str,
        from_time: datetime,
        to_time: datetime
    ) -> List[Candle]:
        """
        Get OHLCV candle data.
        
        Args:
            market: Market symbol (e.g., "SOL-PERP")
            resolution: Candle resolution ("1m", "5m", "1h", "1d")
            from_time: Start time
            to_time: End time
        
        Returns:
            List of Candle objects
        """
        cache_key = f"candles:{market}:{resolution}:{from_time.isoformat()}:{to_time.isoformat()}"
        
        # Check cache first
        cached = await self._cache.get(cache_key)
        if cached:
            return [Candle(**candle) for candle in cached]
        
        try:
            Logger.debug(f"[MarketData] Fetching candles: {market} {resolution} {from_time} to {to_time}")
            
            # TODO: Implement actual Drift SDK candle data fetching
            candles = await self._fetch_candles_from_drift(market, resolution, from_time, to_time)
            
            if candles:
                # Cache the result
                await self._cache.set(
                    cache_key,
                    [asdict(candle) for candle in candles],
                    ttl=self.CACHE_TTLS["candles"]
                )
            
            return candles or []
            
        except Exception as e:
            Logger.error(f"[MarketData] Failed to fetch candles for {market}: {e}")
            return []
    
    async def _fetch_candles_from_drift(
        self,
        market: str,
        resolution: str,
        from_time: datetime,
        to_time: datetime
    ) -> List[Candle]:
        """Fetch candle data from Drift Protocol."""
        try:
            # TODO: Implement actual Drift SDK candle API
            
            # For now, simulate realistic candle data
            candles = []
            
            # Calculate time intervals based on resolution
            resolution_minutes = {
                "1m": 1,
                "5m": 5,
                "15m": 15,
                "1h": 60,
                "4h": 240,
                "1d": 1440
            }.get(resolution, 60)
            
            current_time = from_time
            base_price = 150.0
            
            while current_time < to_time:
                # Simulate price movement
                price_change = (hash(str(current_time)) % 200 - 100) / 10000  # Small random changes
                
                open_price = base_price + price_change
                high_price = open_price + abs(price_change) * 2
                low_price = open_price - abs(price_change) * 2
                close_price = open_price + price_change * 0.5
                
                candle = Candle(
                    market=market,
                    open=open_price,
                    high=high_price,
                    low=low_price,
                    close=close_price,
                    volume=100.0 + (hash(str(current_time)) % 500),
                    timestamp=current_time,
                    resolution=resolution,
                    trades_count=10 + (hash(str(current_time)) % 50),
                    vwap=0.0  # Will be calculated in __post_init__
                )
                
                candles.append(candle)
                current_time += timedelta(minutes=resolution_minutes)
                base_price = close_price  # Use close as next open
            
            return candles
            
        except Exception as e:
            Logger.error(f"[MarketData] Drift candle fetch failed: {e}")
            return []
    
    # =========================================================================
    # MARKET STATISTICS
    # =========================================================================
    
    async def get_market_stats(self, market: str) -> Optional[MarketStats]:
        """
        Get 24-hour market statistics.
        
        Args:
            market: Market symbol (e.g., "SOL-PERP")
        
        Returns:
            MarketStats object or None if unavailable
        """
        cache_key = f"market_stats:{market}"
        
        # Check cache first
        cached = await self._cache.get(cache_key)
        if cached:
            return MarketStats(**cached)
        
        try:
            Logger.debug(f"[MarketData] Fetching market stats: {market}")
            
            # Get current funding rate from existing system
            funding_data = await self.drift_adapter.get_funding_rate(market)
            
            # TODO: Implement actual 24h statistics calculation
            # For now, simulate realistic market stats
            stats = MarketStats(
                market=market,
                last_price=150.0,
                price_change_24h=2.5,
                price_change_percent_24h=1.67,
                high_24h=155.0,
                low_24h=145.0,
                volume_24h=1250000.0,
                volume_quote_24h=187500000.0,
                trades_count_24h=15420,
                funding_rate=funding_data.get('rate_8h', 0.0) / 8 if funding_data else 0.0,
                funding_rate_8h=funding_data.get('rate_8h', 0.0) if funding_data else 0.0,
                open_interest=5000000.0,
                mark_price=funding_data.get('mark_price', 150.0) if funding_data else 150.0,
                index_price=150.1,
                timestamp=datetime.now()
            )
            
            # Cache the result
            await self._cache.set(
                cache_key,
                asdict(stats),
                ttl=self.CACHE_TTLS["market_stats"]
            )
            
            return stats
            
        except Exception as e:
            Logger.error(f"[MarketData] Failed to fetch market stats for {market}: {e}")
            return None
    
    # =========================================================================
    # FUNDING HISTORY
    # =========================================================================
    
    async def get_funding_history(
        self,
        market: str,
        limit: int = 100
    ) -> List[FundingPayment]:
        """
        Get historical funding payments.
        
        Args:
            market: Market symbol (e.g., "SOL-PERP")
            limit: Maximum number of payments to return
        
        Returns:
            List of FundingPayment objects
        """
        cache_key = f"funding_history:{market}:{limit}"
        
        # Check cache first
        cached = await self._cache.get(cache_key)
        if cached:
            return [FundingPayment(**payment) for payment in cached]
        
        try:
            Logger.debug(f"[MarketData] Fetching funding history: {market} (limit: {limit})")
            
            # TODO: Implement actual Drift SDK funding history API
            payments = await self._fetch_funding_history_from_drift(market, limit)
            
            if payments:
                # Cache the result
                await self._cache.set(
                    cache_key,
                    [asdict(payment) for payment in payments],
                    ttl=self.CACHE_TTLS["funding_history"]
                )
            
            return payments or []
            
        except Exception as e:
            Logger.error(f"[MarketData] Failed to fetch funding history for {market}: {e}")
            return []
    
    async def _fetch_funding_history_from_drift(self, market: str, limit: int) -> List[FundingPayment]:
        """Fetch funding payment history from Drift Protocol."""
        try:
            # TODO: Implement actual Drift SDK funding history API
            
            # For now, simulate realistic funding payment data
            payments = []
            
            for i in range(limit):
                # Simulate funding rate variations
                base_rate = 0.01  # 0.01% base rate
                rate_variation = (i % 20 - 10) * 0.001  # Small variations
                funding_rate_8h = base_rate + rate_variation
                
                payment = FundingPayment(
                    market=market,
                    funding_rate=funding_rate_8h / 8,  # Hourly rate
                    funding_rate_8h=funding_rate_8h,
                    payment_amount=funding_rate_8h * 1.0,  # Assume 1.0 position size
                    timestamp=datetime.now() - timedelta(hours=8 * i),
                    position_size=1.0
                )
                payments.append(payment)
            
            # Sort by timestamp (newest first)
            payments.sort(key=lambda x: x.timestamp, reverse=True)
            return payments
            
        except Exception as e:
            Logger.error(f"[MarketData] Drift funding history fetch failed: {e}")
            return []
    
    # =========================================================================
    # REAL-TIME SUBSCRIPTIONS
    # =========================================================================
    
    async def subscribe_to_trades(
        self,
        market: str,
        callback: Callable[[Trade], None]
    ) -> str:
        """
        Subscribe to real-time trade updates.
        
        Args:
            market: Market symbol (e.g., "SOL-PERP")
            callback: Function to call with new trades
        
        Returns:
            Subscription ID for unsubscribing
        """
        subscription_id = f"trades_{market}_{self._next_subscription_id}"
        self._next_subscription_id += 1
        
        subscription = Subscription(
            id=subscription_id,
            market=market,
            data_type="trades",
            callback=callback,
            active=True,
            created_at=datetime.now()
        )
        
        self._subscriptions[subscription_id] = subscription
        self._trade_callbacks[market].append(callback)
        
        Logger.info(f"[MarketData] ✅ Subscribed to trades: {market} ({subscription_id})")
        
        # TODO: Start real-time data feed if not already running
        asyncio.create_task(self._start_trade_feed(market))
        
        return subscription_id
    
    async def subscribe_to_orderbook(
        self,
        market: str,
        callback: Callable[[OrderBook], None]
    ) -> str:
        """
        Subscribe to real-time orderbook updates.
        
        Args:
            market: Market symbol (e.g., "SOL-PERP")
            callback: Function to call with orderbook updates
        
        Returns:
            Subscription ID for unsubscribing
        """
        subscription_id = f"orderbook_{market}_{self._next_subscription_id}"
        self._next_subscription_id += 1
        
        subscription = Subscription(
            id=subscription_id,
            market=market,
            data_type="orderbook",
            callback=callback,
            active=True,
            created_at=datetime.now()
        )
        
        self._subscriptions[subscription_id] = subscription
        self._orderbook_callbacks[market].append(callback)
        
        Logger.info(f"[MarketData] ✅ Subscribed to orderbook: {market} ({subscription_id})")
        
        # TODO: Start real-time data feed if not already running
        asyncio.create_task(self._start_orderbook_feed(market))
        
        return subscription_id
    
    async def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe from real-time updates.
        
        Args:
            subscription_id: Subscription ID to cancel
        
        Returns:
            True if unsubscribed successfully
        """
        if subscription_id not in self._subscriptions:
            Logger.warning(f"[MarketData] Subscription not found: {subscription_id}")
            return False
        
        subscription = self._subscriptions[subscription_id]
        subscription.active = False
        
        # Remove callback from appropriate list
        if subscription.data_type == "trades":
            if subscription.callback in self._trade_callbacks[subscription.market]:
                self._trade_callbacks[subscription.market].remove(subscription.callback)
        elif subscription.data_type == "orderbook":
            if subscription.callback in self._orderbook_callbacks[subscription.market]:
                self._orderbook_callbacks[subscription.market].remove(subscription.callback)
        
        del self._subscriptions[subscription_id]
        
        Logger.info(f"[MarketData] ✅ Unsubscribed: {subscription_id}")
        return True
    
    # =========================================================================
    # PRIVATE HELPER METHODS
    # =========================================================================
    
    async def _notify_trade_subscribers(self, market: str, trade: Trade):
        """Notify trade subscribers of new trade."""
        for callback in self._trade_callbacks[market]:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(trade)
                else:
                    callback(trade)
            except Exception as e:
                Logger.error(f"[MarketData] Trade callback error: {e}")
    
    async def _notify_orderbook_subscribers(self, market: str, orderbook: OrderBook):
        """Notify orderbook subscribers of update."""
        for callback in self._orderbook_callbacks[market]:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(orderbook)
                else:
                    callback(orderbook)
            except Exception as e:
                Logger.error(f"[MarketData] Orderbook callback error: {e}")
    
    async def _start_trade_feed(self, market: str):
        """Start real-time trade feed for market."""
        # TODO: Implement actual real-time trade feed
        # This would connect to Drift Protocol's WebSocket feeds
        pass
    
    async def _start_orderbook_feed(self, market: str):
        """Start real-time orderbook feed for market."""
        # TODO: Implement actual real-time orderbook feed
        # This would connect to Drift Protocol's WebSocket feeds
        pass