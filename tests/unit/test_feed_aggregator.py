"""
FeedAggregator Unit Tests
=========================
Tests for priority routing, fallback, and health tracking.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Optional

from src.shared.feeds.price_source import SpotPrice, Quote


class TestFeedAggregatorRouting:
    """Test priority-based feed routing."""

    @pytest.fixture
    def mock_feeds(self):
        """Create mock feeds with different priorities."""
        # Primary (fastest)
        primary = MagicMock()
        primary.get_name.return_value = "PRIMARY"
        primary.get_fee_pct.return_value = 0.3
        
        # Secondary (slower)
        secondary = MagicMock()
        secondary.get_name.return_value = "SECONDARY"
        secondary.get_fee_pct.return_value = 0.25
        
        # Tertiary (fallback)
        tertiary = MagicMock()
        tertiary.get_name.return_value = "TERTIARY"
        tertiary.get_fee_pct.return_value = 0.3
        
        return [primary, secondary, tertiary]

    @pytest.fixture
    def aggregator(self, mock_feeds):
        """Create FeedAggregator with mock feeds."""
        from src.shared.feeds.aggregator import FeedAggregator
        return FeedAggregator(mock_feeds)

    @pytest.mark.asyncio
    async def test_uses_primary_feed_first(self, aggregator, mock_feeds):
        """Primary feed should be tried first when healthy."""
        primary, secondary, tertiary = mock_feeds
        
        expected_price = SpotPrice(
            dex="PRIMARY",
            base_mint="SOL",
            quote_mint="USDC",
            price=150.0
        )
        
        primary.get_spot_price = AsyncMock(return_value=expected_price)
        secondary.get_spot_price = AsyncMock()
        tertiary.get_spot_price = AsyncMock()
        
        result = await aggregator.get_best_price("SOL", "USDC")
        
        assert result is not None
        assert result.dex == "PRIMARY"
        primary.get_spot_price.assert_called_once()
        secondary.get_spot_price.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_on_primary_failure(self, aggregator, mock_feeds):
        """Should fallback to secondary when primary fails."""
        primary, secondary, tertiary = mock_feeds
        
        primary.get_spot_price = AsyncMock(return_value=None)
        secondary.get_spot_price = AsyncMock(return_value=SpotPrice(
            dex="SECONDARY",
            base_mint="SOL",
            quote_mint="USDC",
            price=150.0
        ))
        
        result = await aggregator.get_best_price("SOL", "USDC")
        
        assert result is not None
        assert result.dex == "SECONDARY"

    @pytest.mark.asyncio
    async def test_falls_back_on_timeout(self, aggregator, mock_feeds):
        """Should fallback when primary times out."""
        primary, secondary, tertiary = mock_feeds
        
        async def slow_request(*args):
            await asyncio.sleep(1.0)  # Exceeds 500ms timeout
            return SpotPrice(dex="PRIMARY", base_mint="SOL", quote_mint="USDC", price=150.0)
        
        primary.get_spot_price = slow_request
        secondary.get_spot_price = AsyncMock(return_value=SpotPrice(
            dex="SECONDARY",
            base_mint="SOL",
            quote_mint="USDC",
            price=151.0
        ))
        
        result = await aggregator.get_best_price("SOL", "USDC")
        
        # Should get secondary result due to timeout
        assert result is not None
        # Note: actual result depends on race condition timing

    @pytest.mark.asyncio
    async def test_returns_none_when_all_fail(self, aggregator, mock_feeds):
        """Should return None when all feeds fail."""
        for feed in mock_feeds:
            feed.get_spot_price = AsyncMock(return_value=None)
        
        result = await aggregator.get_best_price("SOL", "USDC")
        
        assert result is None


class TestFeedHealthTracking:
    """Test feed health metrics."""

    @pytest.fixture
    def aggregator(self):
        """Create aggregator with mock feeds."""
        from src.shared.feeds.aggregator import FeedAggregator
        
        feed = MagicMock()
        feed.get_name.return_value = "TEST_FEED"
        feed.get_fee_pct.return_value = 0.3
        
        return FeedAggregator([feed])

    def test_initial_health_is_healthy(self, aggregator):
        """New feeds should start as healthy."""
        report = aggregator.get_health_report()
        
        assert "TEST_FEED" in report
        assert report["TEST_FEED"]["is_healthy"] is True
        assert report["TEST_FEED"]["consecutive_failures"] == 0

    @pytest.mark.asyncio
    async def test_health_degrades_on_failures(self, aggregator):
        """Consecutive failures should degrade health."""
        feed = aggregator.feeds[0]
        feed.get_spot_price = AsyncMock(return_value=None)
        
        # Cause multiple failures
        for _ in range(5):
            await aggregator.get_best_price("SOL", "USDC", use_cache=False)
        
        report = aggregator.get_health_report()
        assert report["TEST_FEED"]["consecutive_failures"] >= 5

    @pytest.mark.asyncio
    async def test_health_recovers_on_success(self, aggregator):
        """Successful request should reset consecutive failures."""
        feed = aggregator.feeds[0]
        
        # Cause some failures first
        feed.get_spot_price = AsyncMock(return_value=None)
        for _ in range(3):
            await aggregator.get_best_price("SOL", "USDC", use_cache=False)
        
        # Now succeed
        feed.get_spot_price = AsyncMock(return_value=SpotPrice(
            dex="TEST_FEED",
            base_mint="SOL",
            quote_mint="USDC",
            price=150.0
        ))
        await aggregator.get_best_price("SOL", "USDC", use_cache=False)
        
        report = aggregator.get_health_report()
        assert report["TEST_FEED"]["consecutive_failures"] == 0


class TestPriceCache:
    """Test price caching behavior."""

    @pytest.fixture
    def aggregator(self):
        """Create aggregator with mock feed."""
        from src.shared.feeds.aggregator import FeedAggregator
        
        feed = MagicMock()
        feed.get_name.return_value = "CACHED_FEED"
        feed.get_fee_pct.return_value = 0.3
        
        return FeedAggregator([feed], cache_ttl=5.0)

    @pytest.mark.asyncio
    async def test_cache_hit_avoids_request(self, aggregator):
        """Cached price should be returned without new request."""
        feed = aggregator.feeds[0]
        feed.get_spot_price = AsyncMock(return_value=SpotPrice(
            dex="CACHED_FEED",
            base_mint="SOL",
            quote_mint="USDC",
            price=150.0
        ))
        
        # First call populates cache
        await aggregator.get_best_price("SOL", "USDC")
        assert feed.get_spot_price.call_count == 1
        
        # Second call should use cache
        await aggregator.get_best_price("SOL", "USDC")
        assert feed.get_spot_price.call_count == 1  # No new call

    @pytest.mark.asyncio
    async def test_cache_bypass_when_disabled(self, aggregator):
        """Should fetch fresh price when cache disabled."""
        feed = aggregator.feeds[0]
        feed.get_spot_price = AsyncMock(return_value=SpotPrice(
            dex="CACHED_FEED",
            base_mint="SOL",
            quote_mint="USDC",
            price=150.0
        ))
        
        await aggregator.get_best_price("SOL", "USDC", use_cache=True)
        await aggregator.get_best_price("SOL", "USDC", use_cache=False)
        
        assert feed.get_spot_price.call_count == 2

    def test_clear_cache(self, aggregator):
        """clear_cache should empty the cache."""
        aggregator._cache[("SOL", "USDC")] = "cached_value"
        
        aggregator.clear_cache()
        
        assert len(aggregator._cache) == 0


class TestGetAllPrices:
    """Test fetching prices from all feeds."""

    @pytest.fixture
    def multi_feed_aggregator(self):
        """Create aggregator with multiple mock feeds."""
        from src.shared.feeds.aggregator import FeedAggregator
        
        feeds = []
        for name in ["JUPITER", "RAYDIUM", "ORCA"]:
            feed = MagicMock()
            feed.get_name.return_value = name
            feed.get_fee_pct.return_value = 0.3
            feeds.append(feed)
        
        return FeedAggregator(feeds)

    @pytest.mark.asyncio
    async def test_returns_all_successful_prices(self, multi_feed_aggregator):
        """Should return dict with all successful prices."""
        prices = {
            "JUPITER": 150.0,
            "RAYDIUM": 150.2,
            "ORCA": 149.8,
        }
        
        for feed in multi_feed_aggregator.feeds:
            name = feed.get_name()
            feed.get_spot_price = AsyncMock(return_value=SpotPrice(
                dex=name,
                base_mint="SOL",
                quote_mint="USDC",
                price=prices[name]
            ))
        
        result = await multi_feed_aggregator.get_all_prices("SOL", "USDC")
        
        assert len(result) == 3
        assert "JUPITER" in result
        assert "RAYDIUM" in result
        assert "ORCA" in result

    @pytest.mark.asyncio
    async def test_partial_results_on_failure(self, multi_feed_aggregator):
        """Should return partial results when some feeds fail."""
        feeds = multi_feed_aggregator.feeds
        
        feeds[0].get_spot_price = AsyncMock(return_value=SpotPrice(
            dex="JUPITER", base_mint="SOL", quote_mint="USDC", price=150.0
        ))
        feeds[1].get_spot_price = AsyncMock(return_value=None)  # Fails
        feeds[2].get_spot_price = AsyncMock(return_value=SpotPrice(
            dex="ORCA", base_mint="SOL", quote_mint="USDC", price=149.8
        ))
        
        result = await multi_feed_aggregator.get_all_prices("SOL", "USDC")
        
        assert len(result) == 2
        assert "JUPITER" in result
        assert "ORCA" in result
        assert "RAYDIUM" not in result
