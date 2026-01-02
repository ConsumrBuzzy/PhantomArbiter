"""
Test Data Feed Pipeline - End-to-End Data Flow

Verifies data flows correctly from WSS → Aggregator → Client.
"""

import pytest
import asyncio
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from datafeed.price_aggregator import PriceAggregator, PricePoint, PriceSource


class TestPriceAggregatorFlow:
    """Tests for price aggregator data flow."""
    
    @pytest.fixture
    def aggregator(self):
        return PriceAggregator()
    
    def test_single_source_update(self, aggregator):
        """Single price update is stored correctly."""
        aggregator.update_price(
            mint="SOL123",
            symbol="SOL",
            price=150.0,
            source=PriceSource.HELIUS,
            volume=10000,
            liquidity=500000,
        )
        
        snapshot = aggregator.get_snapshot("SOL123")
        assert snapshot is not None
        assert snapshot.price == 150.0
        assert snapshot.source == PriceSource.HELIUS
    
    def test_multi_source_best_price(self, aggregator):
        """Multiple sources select best (most recent) price."""
        base_time = time.time()
        
        # Older price from source A
        aggregator.update_price(
            mint="TOKEN",
            symbol="TKN",
            price=100.0,
            source=PriceSource.HELIUS,
            timestamp=base_time - 10,
        )
        
        # Newer price from source B
        aggregator.update_price(
            mint="TOKEN",
            symbol="TKN",
            price=105.0,
            source=PriceSource.DEXSCREENER,
            timestamp=base_time,
        )
        
        snapshot = aggregator.get_snapshot("TOKEN")
        # Should use more recent price
        assert snapshot.price == 105.0
    
    def test_stale_price_detection(self, aggregator):
        """Old prices are marked as stale."""
        # Add an old price
        aggregator.update_price(
            mint="STALE",
            symbol="STL",
            price=50.0,
            source=PriceSource.HELIUS,
            timestamp=time.time() - 120,  # 2 minutes old
        )
        
        snapshot = aggregator.get_snapshot("STALE")
        # Price exists but is stale
        assert snapshot is not None
        assert snapshot.is_stale(max_age_seconds=60)
    
    def test_subscriber_notification(self, aggregator):
        """Subscribers receive price updates."""
        received = []
        
        def on_update(mint, point):
            received.append((mint, point.price))
        
        aggregator.subscribe(on_update)
        
        aggregator.update_price(
            mint="NOTIFY",
            symbol="NTF",
            price=25.0,
            source=PriceSource.HELIUS,
        )
        
        assert len(received) == 1
        assert received[0] == ("NOTIFY", 25.0)
    
    def test_bulk_snapshot(self, aggregator):
        """Get all prices at once."""
        aggregator.update_price("A", "A", 1.0, PriceSource.HELIUS)
        aggregator.update_price("B", "B", 2.0, PriceSource.HELIUS)
        aggregator.update_price("C", "C", 3.0, PriceSource.HELIUS)
        
        all_prices = aggregator.get_all_snapshots()
        
        assert len(all_prices) == 3
        assert "A" in all_prices
        assert "B" in all_prices
        assert "C" in all_prices


class TestPriceDataIntegrity:
    """Tests for data integrity in price updates."""
    
    @pytest.fixture
    def aggregator(self):
        return PriceAggregator()
    
    def test_zero_price_rejected(self, aggregator):
        """Zero or negative prices are rejected."""
        aggregator.update_price("BAD", "BAD", 0.0, PriceSource.HELIUS)
        aggregator.update_price("NEGATIVE", "NEG", -5.0, PriceSource.HELIUS)
        
        assert aggregator.get_snapshot("BAD") is None
        assert aggregator.get_snapshot("NEGATIVE") is None
    
    def test_volume_accumulated(self, aggregator):
        """Volume is tracked across updates."""
        aggregator.update_price("VOL", "VOL", 10.0, PriceSource.HELIUS, volume=100)
        aggregator.update_price("VOL", "VOL", 11.0, PriceSource.HELIUS, volume=200)
        
        snapshot = aggregator.get_snapshot("VOL")
        # Should have latest volume
        assert snapshot.volume == 200
    
    def test_liquidity_tracked(self, aggregator):
        """Liquidity USD is tracked."""
        aggregator.update_price(
            "LIQ", "LIQ", 5.0, PriceSource.HELIUS, liquidity=1000000
        )
        
        snapshot = aggregator.get_snapshot("LIQ")
        assert snapshot.liquidity == 1000000


class TestAggregatorStats:
    """Tests for aggregator statistics."""
    
    @pytest.fixture
    def aggregator(self):
        return PriceAggregator()
    
    def test_update_count_tracked(self, aggregator):
        """Update count is tracked."""
        for i in range(10):
            aggregator.update_price(f"T{i}", f"T{i}", float(i), PriceSource.HELIUS)
        
        stats = aggregator.get_stats()
        assert stats.total_updates == 10
        assert stats.tokens_tracked == 10
    
    def test_source_breakdown(self, aggregator):
        """Updates per source are tracked."""
        aggregator.update_price("A", "A", 1.0, PriceSource.HELIUS)
        aggregator.update_price("B", "B", 2.0, PriceSource.HELIUS)
        aggregator.update_price("C", "C", 3.0, PriceSource.DEXSCREENER)
        
        stats = aggregator.get_stats()
        assert stats.updates_by_source.get("HELIUS", 0) == 2
        assert stats.updates_by_source.get("DEXSCREENER", 0) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
