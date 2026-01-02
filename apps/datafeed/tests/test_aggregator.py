"""
Test Price Aggregator

Verifies price aggregation and subscriber notification.
"""

import pytest
import asyncio
import time

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from datafeed.price_aggregator import PriceAggregator, PricePoint, PriceSource


@pytest.fixture
def aggregator():
    """Create a fresh PriceAggregator instance."""
    return PriceAggregator(max_age_seconds=60)


@pytest.mark.asyncio
async def test_update_and_get_price(aggregator):
    """Test basic price update and retrieval."""
    point = PricePoint(
        symbol="SOL",
        mint="So11111111111111111111111111111111111111112",
        price=150.0,
        volume_24h=1000000,
        timestamp_ms=int(time.time() * 1000),
        source=PriceSource.WSS,
    )
    
    await aggregator.update_price(point)
    
    result = await aggregator.get_price(point.mint)
    assert result is not None
    assert result.price == 150.0
    assert result.symbol == "SOL"


@pytest.mark.asyncio
async def test_get_by_symbol(aggregator):
    """Test price retrieval by symbol."""
    point = PricePoint(
        symbol="BONK",
        mint="DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
        price=0.000025,
        timestamp_ms=int(time.time() * 1000),
        source=PriceSource.DEXSCREENER,
    )
    
    await aggregator.update_price(point)
    
    result = await aggregator.get_price_by_symbol("BONK")
    assert result is not None
    assert result.mint == point.mint


@pytest.mark.asyncio
async def test_subscriber_notification(aggregator):
    """Test that subscribers are notified of updates."""
    received = []
    
    async def callback(point: PricePoint):
        received.append(point)
    
    aggregator.subscribe_async(callback)
    
    point = PricePoint(
        symbol="JUP",
        mint="JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
        price=1.50,
        timestamp_ms=int(time.time() * 1000),
        source=PriceSource.JUPITER,
    )
    
    await aggregator.update_price(point)
    
    assert len(received) == 1
    assert received[0].symbol == "JUP"


@pytest.mark.asyncio
async def test_snapshot(aggregator):
    """Test getting market snapshot."""
    for i in range(5):
        point = PricePoint(
            symbol=f"TKN{i}",
            mint=f"Mint{i}",
            price=100.0 + i,
            timestamp_ms=int(time.time() * 1000),
            source=PriceSource.WSS,
        )
        await aggregator.update_price(point)
    
    snapshot = await aggregator.get_snapshot()
    assert len(snapshot) == 5


@pytest.mark.asyncio
async def test_stale_price_excluded(aggregator):
    """Test that stale prices are not returned."""
    # Create a stale price
    old_time_ms = int((time.time() - 120) * 1000)  # 2 minutes ago
    point = PricePoint(
        symbol="OLD",
        mint="OldMint",
        price=1.0,
        timestamp_ms=old_time_ms,
        source=PriceSource.WSS,
    )
    
    await aggregator.update_price(point)
    
    # Should not be returned (max age is 60s)
    result = await aggregator.get_price("OldMint")
    assert result is None


def test_stats(aggregator):
    """Test stats calculation."""
    stats = aggregator.get_stats()
    
    assert stats.symbols_tracked == 0
    assert stats.updates_per_second == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
