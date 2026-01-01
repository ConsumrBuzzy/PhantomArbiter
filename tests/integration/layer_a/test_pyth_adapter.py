"""
V48.0: Unit Tests for Pyth Network Adapter
============================================
Tests for the Pyth Network low-latency price oracle.

Run: pytest tests/test_pyth_adapter.py -v
"""

import pytest
import sys
import os
from unittest.mock import MagicMock

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPythAdapterImport:
    """Test that PythAdapter can be imported."""

    def test_import_pyth_adapter(self):
        """Verify PythAdapter imports successfully."""
        from src.core.prices.pyth_adapter import PythAdapter, PythPrice

        assert PythAdapter is not None
        assert PythPrice is not None

    def test_feed_ids_defined(self):
        """Verify key feed IDs are defined."""
        from src.core.prices.pyth_adapter import PythAdapter

        adapter = PythAdapter()
        assert "SOL" in adapter.FEED_IDS
        assert "ETH" in adapter.FEED_IDS
        assert "BTC" in adapter.FEED_IDS
        assert "USDC" in adapter.FEED_IDS
        assert "JITOSOL" in adapter.FEED_IDS


class TestPythPrice:
    """Test PythPrice dataclass."""

    def test_pyth_price_creation(self):
        """Test PythPrice can be created."""
        from src.core.prices.pyth_adapter import PythPrice
        import time

        price = PythPrice(
            price=228.50,
            confidence=0.05,
            expo=-8,
            publish_time=int(time.time()),
            confidence_pct=0.022,
        )

        assert price.price == 228.50
        assert price.confidence_pct == 0.022
        assert price.is_stale is False

    def test_stale_detection(self):
        """Test stale price detection."""
        from src.core.prices.pyth_adapter import PythPrice
        import time

        # Create price from 10 seconds ago
        old_price = PythPrice(
            price=228.50,
            confidence=0.05,
            expo=-8,
            publish_time=int(time.time()) - 10,
            confidence_pct=0.022,
        )

        assert old_price.is_stale is True


class TestPythFetch:
    """Test Pyth API fetching (requires network)."""

    @pytest.fixture
    def adapter(self):
        """Create PythAdapter instance."""
        from src.core.prices.pyth_adapter import PythAdapter

        return PythAdapter()

    def test_has_feed_check(self, adapter):
        """Test has_feed returns correct values."""
        assert adapter.has_feed("SOL") is True
        assert adapter.has_feed("ETH") is True
        assert adapter.has_feed("BONK") is False  # Meme token - no Pyth feed
        assert adapter.has_feed("WIF") is False

    def test_get_supported_symbols(self, adapter):
        """Test supported symbols list."""
        symbols = adapter.get_supported_symbols()

        assert "SOL" in symbols
        assert "ETH" in symbols
        assert len(symbols) >= 5


class TestPriceDivergence:
    """Test price divergence guardrail."""

    def test_divergence_blocks_when_exceeded(self):
        """Test that large divergence blocks trades."""
        from src.engine.trade_executor import TradeExecutor
        from src.core.prices.pyth_adapter import PythAdapter, PythPrice

        # Create mock Pyth adapter
        mock_adapter = MagicMock(spec=PythAdapter)
        mock_adapter.has_feed = MagicMock(return_value=True)

        # Mock Pyth price significantly different from signal
        mock_pyth_price = PythPrice(
            price=230.0,  # Pyth says $230
            confidence=0.05,
            expo=-8,
            publish_time=9999999999,
            confidence_pct=0.02,
        )
        mock_adapter.fetch_single = MagicMock(return_value=mock_pyth_price)

        # Create executor with mock adapter
        executor = TradeExecutor(
            engine_name="TEST",
            capital_mgr=MagicMock(),
            paper_wallet=MagicMock(),
            swapper=MagicMock(),
            portfolio=MagicMock(),
            pyth_adapter=mock_adapter,
        )

        # Mock watcher
        mock_watcher = MagicMock()
        mock_watcher.symbol = "SOL"

        # Signal price is $225 (2.2% different from Pyth's $230)
        is_valid, reason, pyth_price = executor._check_price_divergence(
            mock_watcher, 225.0
        )

        assert is_valid is False
        assert "divergence" in reason.lower()

    def test_divergence_passes_when_small(self):
        """Test that small divergence allows trades."""
        from src.engine.trade_executor import TradeExecutor
        from src.core.prices.pyth_adapter import PythAdapter, PythPrice

        mock_adapter = MagicMock(spec=PythAdapter)
        mock_adapter.has_feed = MagicMock(return_value=True)

        # Mock Pyth price very close to signal
        mock_pyth_price = PythPrice(
            price=228.50,  # Pyth says $228.50
            confidence=0.05,
            expo=-8,
            publish_time=9999999999,
            confidence_pct=0.02,
        )
        mock_adapter.fetch_single = MagicMock(return_value=mock_pyth_price)

        executor = TradeExecutor(
            engine_name="TEST",
            capital_mgr=MagicMock(),
            paper_wallet=MagicMock(),
            swapper=MagicMock(),
            portfolio=MagicMock(),
            pyth_adapter=mock_adapter,
        )

        mock_watcher = MagicMock()
        mock_watcher.symbol = "SOL"

        # Signal price is $228.60 (0.04% different - well within tolerance)
        is_valid, reason, pyth_price = executor._check_price_divergence(
            mock_watcher, 228.60
        )

        assert is_valid is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
