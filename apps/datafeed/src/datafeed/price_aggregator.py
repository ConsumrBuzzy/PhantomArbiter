"""
Price Aggregator - Multi-source price aggregation.

Collects prices from multiple sources and maintains current state.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from enum import Enum


class PriceSource(str, Enum):
    """Price data sources."""
    WSS = "WSS"
    JUPITER = "JUPITER"
    DEXSCREENER = "DEXSCREENER"
    BIRDEYE = "BIRDEYE"
    PYTH = "PYTH"


@dataclass
class PricePoint:
    """A single price observation."""
    symbol: str
    mint: str
    price: float
    volume_24h: float = 0.0
    liquidity: float = 0.0
    price_change_1h: float = 0.0
    price_change_24h: float = 0.0
    timestamp_ms: int = 0
    source: PriceSource = PriceSource.WSS
    slot: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "mint": self.mint,
            "price": self.price,
            "volume_24h": self.volume_24h,
            "liquidity": self.liquidity,
            "price_change_1h": self.price_change_1h,
            "price_change_24h": self.price_change_24h,
            "timestamp_ms": self.timestamp_ms,
            "source": self.source.value,
            "slot": self.slot,
        }


@dataclass
class AggregatorStats:
    """Aggregator statistics."""
    symbols_tracked: int = 0
    updates_per_second: float = 0.0
    avg_latency_ms: float = 0.0
    source_counts: Dict[str, int] = field(default_factory=dict)


class PriceAggregator:
    """
    Aggregates prices from multiple sources.
    
    Maintains current state and notifies subscribers of updates.
    """
    
    def __init__(self, max_age_seconds: float = 30.0) -> None:
        self._prices: Dict[str, PricePoint] = {}  # mint -> PricePoint
        self._symbol_to_mint: Dict[str, str] = {}  # symbol -> mint
        self._subscribers: List[Callable[[PricePoint], None]] = []
        self._async_subscribers: List[Callable[[PricePoint], Any]] = []
        self._max_age = max_age_seconds
        self._lock = asyncio.Lock()
        
        # Stats tracking
        self._update_count = 0
        self._update_times: List[float] = []
        self._latencies: List[float] = []
        self._start_time = time.time()
    
    async def update_price(self, point: PricePoint) -> None:
        """
        Update price for a symbol.
        
        Notifies all subscribers of the update.
        """
        async with self._lock:
            self._prices[point.mint] = point
            self._symbol_to_mint[point.symbol] = point.mint
            
            # Track stats
            self._update_count += 1
            self._update_times.append(time.time())
            
            # Track latency if we have receive time
            if point.timestamp_ms > 0:
                latency = (time.time() * 1000) - point.timestamp_ms
                if 0 < latency < 10000:  # Sanity check
                    self._latencies.append(latency)
                    if len(self._latencies) > 1000:
                        self._latencies = self._latencies[-500:]
        
        # Notify subscribers (outside lock)
        for callback in self._subscribers:
            try:
                callback(point)
            except Exception:
                pass
        
        for async_callback in self._async_subscribers:
            try:
                await async_callback(point)
            except Exception:
                pass
    
    async def update_batch(self, points: List[PricePoint]) -> int:
        """Update multiple prices at once."""
        for point in points:
            await self.update_price(point)
        return len(points)
    
    async def get_price(self, mint: str) -> Optional[PricePoint]:
        """Get price for a mint address."""
        async with self._lock:
            point = self._prices.get(mint)
            if point and self._is_fresh(point):
                return point
            return None
    
    async def get_price_by_symbol(self, symbol: str) -> Optional[PricePoint]:
        """Get price by symbol."""
        async with self._lock:
            mint = self._symbol_to_mint.get(symbol)
            if mint:
                point = self._prices.get(mint)
                if point and self._is_fresh(point):
                    return point
            return None
    
    async def get_snapshot(self, max_age: Optional[float] = None) -> List[PricePoint]:
        """Get all current prices."""
        max_age = max_age or self._max_age
        async with self._lock:
            now_ms = int(time.time() * 1000)
            cutoff = now_ms - int(max_age * 1000)
            
            return [
                p for p in self._prices.values()
                if p.timestamp_ms >= cutoff
            ]
    
    def subscribe(self, callback: Callable[[PricePoint], None]) -> None:
        """Subscribe to price updates (sync callback)."""
        self._subscribers.append(callback)
    
    def subscribe_async(self, callback: Callable[[PricePoint], Any]) -> None:
        """Subscribe to price updates (async callback)."""
        self._async_subscribers.append(callback)
    
    def unsubscribe(self, callback: Callable) -> None:
        """Unsubscribe from updates."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)
        if callback in self._async_subscribers:
            self._async_subscribers.remove(callback)
    
    def get_stats(self) -> AggregatorStats:
        """Get current aggregator statistics."""
        # Calculate updates per second (last 60s)
        now = time.time()
        recent_updates = [t for t in self._update_times if now - t < 60]
        ups = len(recent_updates) / 60 if recent_updates else 0
        
        # Average latency
        avg_latency = sum(self._latencies) / len(self._latencies) if self._latencies else 0
        
        # Source distribution
        source_counts: Dict[str, int] = {}
        for p in self._prices.values():
            source = p.source.value
            source_counts[source] = source_counts.get(source, 0) + 1
        
        return AggregatorStats(
            symbols_tracked=len(self._prices),
            updates_per_second=round(ups, 2),
            avg_latency_ms=round(avg_latency, 2),
            source_counts=source_counts,
        )
    
    def _is_fresh(self, point: PricePoint) -> bool:
        """Check if price is still fresh."""
        now_ms = int(time.time() * 1000)
        age_ms = now_ms - point.timestamp_ms
        return age_ms < (self._max_age * 1000)
    
    async def prune_stale(self) -> int:
        """Remove stale prices. Returns count removed."""
        async with self._lock:
            stale_mints = [
                mint for mint, point in self._prices.items()
                if not self._is_fresh(point)
            ]
            for mint in stale_mints:
                del self._prices[mint]
            return len(stale_mints)


# Global instance
_aggregator: Optional[PriceAggregator] = None


def get_aggregator() -> PriceAggregator:
    """Get or create the global PriceAggregator instance."""
    global _aggregator
    if _aggregator is None:
        _aggregator = PriceAggregator()
    return _aggregator
