"""
PhantomTrader Test Configuration
================================
Shared fixtures and pytest markers for the test suite.
"""

import pytest
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================================
# PYTEST MARKERS
# ============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "network: marks tests that require network access"
    )
    config.addinivalue_line(
        "markers", "integration: marks integration tests"
    )


# ============================================================================
# SHARED FIXTURES
# ============================================================================

@pytest.fixture
def mock_settings(monkeypatch):
    """Provide mock settings for isolated tests."""
    monkeypatch.setattr("config.settings.Settings.PAPER_TRADING", True)
    monkeypatch.setattr("config.settings.Settings.ENABLE_TRADING", False)
    yield


@pytest.fixture
def mock_datafeed():
    """Create a mock DataFeed with realistic test data."""
    from src.core.data import DataFeed
    
    # Create DataFeed without network calls
    feed = object.__new__(DataFeed)
    feed.raw_prices = [1.0 + i * 0.01 for i in range(50)]  # Rising prices
    feed.raw_volumes = [1000.0] * 50
    feed.candles = []
    feed.current_candle = {'open': 0, 'high': 0, 'low': 0, 'close': 0, 'ticks': 0}
    feed.current_rsi = 50.0
    feed.last_source = "MOCK"
    feed.mint = "MockMint123"
    feed.symbol = "MOCK"
    feed.is_critical = False
    feed.liquidity_usd = 100000.0
    feed.volume_h1 = 50000.0
    feed.last_metadata_update = 0
    
    return feed


@pytest.fixture
def sample_watchlist():
    """Sample watchlist for testing."""
    return {
        "SOL": {
            "mint": "So11111111111111111111111111111111111111112",
            "symbol": "SOL",
            "decimals": 9
        },
        "BONK": {
            "mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
            "symbol": "BONK",
            "decimals": 5
        }
    }


@pytest.fixture
def paper_wallet_state():
    """Sample paper wallet state for testing."""
    return {
        "cash_balance": 10000.0,
        "sol_balance": 0.5,
        "positions": {},
        "trade_history": []
    }
