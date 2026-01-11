"""
Feed Aggregator
===============
Intelligent price feed routing with automatic fallback.

The "Eyes" of the Phantom Arbiter - consolidates multiple DEX feeds
into a single reliable price source.

Features:
- Priority-based feed selection
- Automatic latency-based fallback
- Result caching with TTL
- Unified error handling
"""

import asyncio
import time
from typing import List, Dict, Optional, Protocol, runtime_checkable
from dataclasses import dataclass, field
from collections import defaultdict

from src.shared.system.logging import Logger
from src.shared.feeds.price_source import PriceSource, Quote, SpotPrice


# ═══════════════════════════════════════════════════════════════════════════════
# PROTOCOL DEFINITION (Structural Typing)
# ═══════════════════════════════════════════════════════════════════════════════

@runtime_checkable
class PriceFeedProtocol(Protocol):
    """
    Protocol for price feed implementations.
    
    Any class implementing these methods is a valid PriceFeed.
    This enables duck-typing while maintaining type safety.
    """
    
    def get_name(self) -> str:
        """Return feed identifier (e.g., 'JUPITER', 'RAYDIUM')."""
        ...
        
    async def get_spot_price(self, base_mint: str, quote_mint: str) -> Optional[SpotPrice]:
        """Get current spot price for a pair."""
        ...
        
    async def get_quote(self, input_mint: str, output_mint: str, amount: float) -> Optional[Quote]:
        """Get executable quote for a trade."""
        ...
        
    def get_fee_pct(self) -> float:
        """Return default trading fee percentage."""
        ...


# ═══════════════════════════════════════════════════════════════════════════════
# FEED HEALTH TRACKING
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class FeedHealth:
    """Health metrics for a single feed."""
    
    feed_name: str
    success_count: int = 0
    failure_count: int = 0
    total_latency_ms: float = 0.0
    last_success: float = 0.0
    last_failure: float = 0.0
    consecutive_failures: int = 0
    
    @property
    def avg_latency_ms(self) -> float:
        """Average latency in milliseconds."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.total_latency_ms / total
    
    @property
    def success_rate(self) -> float:
        """Success rate as percentage."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 100.0
        return (self.success_count / total) * 100
    
    @property
    def is_healthy(self) -> bool:
        """Feed is healthy if <5 consecutive failures and latency <1000ms."""
        return self.consecutive_failures < 5 and self.avg_latency_ms < 1000
    
    def record_success(self, latency_ms: float):
        """Record successful request."""
        self.success_count += 1
        self.total_latency_ms += latency_ms
        self.last_success = time.time()
        self.consecutive_failures = 0
        
    def record_failure(self, latency_ms: float):
        """Record failed request."""
        self.failure_count += 1
        self.total_latency_ms += latency_ms
        self.last_failure = time.time()
        self.consecutive_failures += 1


# ═══════════════════════════════════════════════════════════════════════════════
# PRICE CACHE
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CachedPrice:
    """Cached price with TTL."""
    
    price: SpotPrice
    cached_at: float = field(default_factory=time.time)
    ttl_seconds: float = 5.0  # 5 second default TTL
    
    @property
    def is_fresh(self) -> bool:
        """Check if cache entry is still valid."""
        return (time.time() - self.cached_at) < self.ttl_seconds


# ═══════════════════════════════════════════════════════════════════════════════
# FEED AGGREGATOR
# ═══════════════════════════════════════════════════════════════════════════════

class FeedAggregator:
    """
    Intelligent price feed aggregator with fallback routing.
    
    Engines request prices from this aggregator instead of individual feeds.
    The aggregator handles:
    - Priority-based feed selection
    - Automatic failover when feeds are slow/down
    - Result caching to reduce API calls
    - Health tracking for observability
    
    Usage:
        aggregator = FeedAggregator([jupiter_feed, raydium_feed, orca_feed])
        price = await aggregator.get_best_price("SOL", "USDC")
    """
    
    # Maximum latency before triggering fallback
    MAX_LATENCY_MS = 500.0
    
    # Default cache TTL
    CACHE_TTL_SECONDS = 5.0
    
    def __init__(self, feeds: List[PriceSource], cache_ttl: float = None):
        """
        Initialize aggregator with ordered list of feeds.
        
        Args:
            feeds: List of PriceSource implementations, ordered by priority
            cache_ttl: Cache time-to-live in seconds (default: 5.0)
        """
        self.feeds = feeds
        self.cache_ttl = cache_ttl or self.CACHE_TTL_SECONDS
        
        # Health tracking per feed
        self._health: Dict[str, FeedHealth] = {
            feed.get_name(): FeedHealth(feed.get_name())
            for feed in feeds
        }
        
        # Price cache: (base, quote) -> CachedPrice
        self._cache: Dict[tuple, CachedPrice] = {}
        
        Logger.info(f"FeedAggregator initialized with {len(feeds)} feeds: {[f.get_name() for f in feeds]}")
    
    def add_feed(self, feed: PriceSource, priority: int = None):
        """Add a feed at specified priority (0 = highest)."""
        if priority is not None and 0 <= priority <= len(self.feeds):
            self.feeds.insert(priority, feed)
        else:
            self.feeds.append(feed)
        
        self._health[feed.get_name()] = FeedHealth(feed.get_name())
    
    def remove_feed(self, feed_name: str):
        """Remove a feed by name."""
        self.feeds = [f for f in self.feeds if f.get_name() != feed_name]
        self._health.pop(feed_name, None)
    
    async def get_best_price(
        self, 
        base_mint: str, 
        quote_mint: str,
        use_cache: bool = True
    ) -> Optional[SpotPrice]:
        """
        Get best available price from healthy feeds.
        
        Tries feeds in priority order, falling back on slow/failed feeds.
        
        Args:
            base_mint: Token to price
            quote_mint: Quote token (usually USDC)
            use_cache: Whether to use cached prices
            
        Returns:
            Best available SpotPrice or None if all feeds fail
        """
        cache_key = (base_mint, quote_mint)
        
        # Check cache first
        if use_cache and cache_key in self._cache:
            cached = self._cache[cache_key]
            if cached.is_fresh:
                return cached.price
        
        # Try feeds in priority order (healthy feeds first)
        sorted_feeds = self._sort_feeds_by_health()
        
        for feed in sorted_feeds:
            feed_name = feed.get_name()
            health = self._health[feed_name]
            
            # Skip feeds with too many consecutive failures
            if health.consecutive_failures >= 5:
                continue
            
            start_time = time.time()
            try:
                # Use asyncio.wait_for to enforce timeout
                price = await asyncio.wait_for(
                    feed.get_spot_price(base_mint, quote_mint),
                    timeout=self.MAX_LATENCY_MS / 1000
                )
                
                latency_ms = (time.time() - start_time) * 1000
                
                if price:
                    health.record_success(latency_ms)
                    
                    # Cache the result
                    self._cache[cache_key] = CachedPrice(
                        price=price,
                        ttl_seconds=self.cache_ttl
                    )
                    
                    return price
                else:
                    health.record_failure(latency_ms)
                    
            except asyncio.TimeoutError:
                latency_ms = (time.time() - start_time) * 1000
                health.record_failure(latency_ms)
                Logger.debug(f"Feed {feed_name} timed out after {latency_ms:.0f}ms")
                
            except Exception as e:
                latency_ms = (time.time() - start_time) * 1000
                health.record_failure(latency_ms)
                Logger.debug(f"Feed {feed_name} error: {e}")
        
        # All feeds failed
        Logger.warning(f"All feeds failed for {base_mint}/{quote_mint}")
        return None
    
    async def get_best_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: float
    ) -> Optional[Quote]:
        """
        Get best executable quote from healthy feeds.
        
        Similar to get_best_price but includes trade size consideration.
        """
        sorted_feeds = self._sort_feeds_by_health()
        
        for feed in sorted_feeds:
            feed_name = feed.get_name()
            health = self._health[feed_name]
            
            if health.consecutive_failures >= 5:
                continue
            
            start_time = time.time()
            try:
                quote = await asyncio.wait_for(
                    feed.get_quote(input_mint, output_mint, amount),
                    timeout=self.MAX_LATENCY_MS / 1000
                )
                
                latency_ms = (time.time() - start_time) * 1000
                
                if quote:
                    health.record_success(latency_ms)
                    return quote
                else:
                    health.record_failure(latency_ms)
                    
            except asyncio.TimeoutError:
                latency_ms = (time.time() - start_time) * 1000
                health.record_failure(latency_ms)
                
            except Exception as e:
                latency_ms = (time.time() - start_time) * 1000
                health.record_failure(latency_ms)
                Logger.debug(f"Feed {feed_name} quote error: {e}")
        
        return None
    
    async def get_all_prices(
        self,
        base_mint: str,
        quote_mint: str
    ) -> Dict[str, SpotPrice]:
        """
        Get prices from ALL healthy feeds (for spread detection).
        
        Returns dict of {feed_name: SpotPrice}
        """
        results = {}
        
        async def fetch_from_feed(feed: PriceSource):
            try:
                price = await asyncio.wait_for(
                    feed.get_spot_price(base_mint, quote_mint),
                    timeout=self.MAX_LATENCY_MS / 1000
                )
                if price:
                    return (feed.get_name(), price)
            except Exception:
                pass
            return None
        
        # Fetch from all feeds concurrently
        tasks = [fetch_from_feed(f) for f in self.feeds]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        for response in responses:
            if response and not isinstance(response, Exception):
                name, price = response
                results[name] = price
        
        return results
    
    def _sort_feeds_by_health(self) -> List[PriceSource]:
        """Sort feeds by health score (healthy + fast first)."""
        def health_score(feed: PriceSource) -> tuple:
            health = self._health[feed.get_name()]
            # Tuple: (is_healthy, -consecutive_failures, -avg_latency)
            # Higher = better, so we negate for descending sort
            return (
                health.is_healthy,
                -health.consecutive_failures,
                -health.avg_latency_ms
            )
        
        return sorted(self.feeds, key=health_score, reverse=True)
    
    def get_health_report(self) -> Dict[str, Dict]:
        """Get health metrics for all feeds."""
        return {
            name: {
                "avg_latency_ms": health.avg_latency_ms,
                "success_rate": health.success_rate,
                "consecutive_failures": health.consecutive_failures,
                "is_healthy": health.is_healthy,
            }
            for name, health in self._health.items()
        }
    
    def clear_cache(self):
        """Clear the price cache."""
        self._cache.clear()
    
    async def close(self):
        """Cleanup all feed resources."""
        for feed in self.feeds:
            if hasattr(feed, 'close'):
                await feed.close()


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON ACCESS
# ═══════════════════════════════════════════════════════════════════════════════

_aggregator_instance: Optional[FeedAggregator] = None


def get_feed_aggregator() -> FeedAggregator:
    """Get or create the global FeedAggregator instance."""
    global _aggregator_instance
    
    if _aggregator_instance is None:
        # Import feeds lazily to avoid circular imports
        from src.shared.feeds.jupiter_feed import JupiterFeed
        from src.shared.feeds.raydium_feed import RaydiumFeed
        from src.shared.feeds.orca_feed import OrcaFeed
        
        # Priority order: Jupiter (aggregator) > Raydium > Orca
        feeds = [
            JupiterFeed(),
            RaydiumFeed(),
            OrcaFeed(),
        ]
        
        _aggregator_instance = FeedAggregator(feeds)
    
    return _aggregator_instance


def reset_feed_aggregator():
    """Reset the global aggregator (for testing)."""
    global _aggregator_instance
    _aggregator_instance = None
