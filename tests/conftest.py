"""
PhantomArbiter Test Configuration
=================================
Root conftest.py - Shared fixtures, markers, and settings for the test suite.

Architecture:
    tests/
    ├── conftest.py          ← THIS FILE (global fixtures)
    ├── unit/conftest.py     ← Unit-layer fixtures (I/O isolation)
    ├── integration/conftest.py ← Integration fixtures (mock services)
    └── e2e/conftest.py      ← E2E fixtures (test wallet, chaos params)
"""

import pytest
import os
import sys
from unittest.mock import MagicMock, AsyncMock
from typing import Dict, Any

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


# ============================================================================
# PYTEST MARKERS
# ============================================================================


def pytest_configure(config):
    """Register custom markers for test categorization."""
    # Layer markers
    config.addinivalue_line("markers", "unit: Pure logic tests (no I/O)")
    config.addinivalue_line("markers", "integration: Component wiring tests")
    config.addinivalue_line("markers", "e2e: End-to-end mission tests")
    
    # Component markers
    config.addinivalue_line("markers", "rust: Tests requiring phantom_core Rust extension")
    config.addinivalue_line("markers", "layer_a: Market Monitor layer tests")
    config.addinivalue_line("markers", "layer_b: Execution layer tests")
    config.addinivalue_line("markers", "layer_c: Visualization layer tests")
    
    # Behavior markers
    config.addinivalue_line("markers", "slow: Long-running tests (deselect with '-m \"not slow\"')")
    config.addinivalue_line("markers", "network: Tests requiring network access")
    config.addinivalue_line("markers", "flaky: Tests that may fail intermittently")


# ============================================================================
# SESSION-SCOPED FIXTURES (Shared across all tests)
# ============================================================================


@pytest.fixture(scope="session")
def project_root() -> str:
    """Return the project root directory."""
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def settings_paper_mode(session_mocker):
    """Force paper mode for all tests in the session."""
    session_mocker.patch("config.settings.Settings.ENABLE_TRADING", False)
    session_mocker.patch("config.settings.Settings.PAPER_TRADING", True)
    yield


# ============================================================================
# FUNCTION-SCOPED FIXTURES (Fresh per test)
# ============================================================================


@pytest.fixture
def mock_settings(monkeypatch):
    """Provide mock settings for isolated tests."""
    monkeypatch.setattr("config.settings.Settings.PAPER_TRADING", True)
    monkeypatch.setattr("config.settings.Settings.ENABLE_TRADING", False)
    monkeypatch.setattr("config.settings.Settings.POSITION_SIZE_USD", 10.0)
    monkeypatch.setattr("config.settings.Settings.MAX_POSITION_SIZE_USD", 50.0)
    monkeypatch.setattr("config.settings.Settings.SLIPPAGE_TOLERANCE", 0.02)
    yield


@pytest.fixture
def mock_rpc_client():
    """
    Mock Solana RPC client that returns canned responses.
    Use this for tests that shouldn't hit the network.
    """
    client = MagicMock()
    client.get_account_info = AsyncMock(return_value={"value": None})
    client.get_balance = AsyncMock(return_value={"value": 1_000_000_000})  # 1 SOL
    client.get_token_accounts_by_owner = AsyncMock(return_value={"value": []})
    client.send_transaction = AsyncMock(return_value={"result": "fake_tx_signature"})
    return client


@pytest.fixture
def mock_datafeed():
    """
    Create a mock DataFeed with realistic synthetic test data.
    Simulates a token with rising prices and neutral RSI.
    """
    from src.core.data import DataFeed

    feed = object.__new__(DataFeed)
    feed.raw_prices = [1.0 + i * 0.01 for i in range(50)]  # Rising prices
    feed.raw_volumes = [1000.0] * 50
    feed.candles = []
    feed.current_candle = {"open": 1.0, "high": 1.5, "low": 0.95, "close": 1.45, "ticks": 50}
    feed.current_rsi = 50.0
    feed.last_source = "MOCK"
    feed.mint = "MockMint123456789abcdefghijklmnopqrstuvwx"
    feed.symbol = "MOCK"
    feed.is_critical = False
    feed.liquidity_usd = 100000.0
    feed.volume_h1 = 50000.0
    feed.last_metadata_update = 0
    return feed


@pytest.fixture
def mock_watcher(mock_datafeed):
    """
    Create a mock Watcher in a neutral state (not in position).
    """
    watcher = MagicMock()
    watcher.symbol = "MOCK"
    watcher.mint = "MockMint123456789abcdefghijklmnopqrstuvwx"
    watcher.data_feed = mock_datafeed
    watcher.in_position = False
    watcher.entry_price = 0.0
    watcher.position_size = 0.0
    watcher.get_price = MagicMock(return_value=1.45)
    watcher.get_rsi = MagicMock(return_value=50.0)
    watcher.get_detailed_status = MagicMock(return_value={"status": "WATCHING"})
    return watcher


@pytest.fixture
def mock_watcher_in_position(mock_datafeed):
    """
    Create a mock Watcher that is currently in a position.
    Entry at $1.00, current price $1.45 (45% profit).
    """
    watcher = MagicMock()
    watcher.symbol = "MOCK"
    watcher.mint = "MockMint123456789abcdefghijklmnopqrstuvwx"
    watcher.data_feed = mock_datafeed
    watcher.in_position = True
    watcher.entry_price = 1.0
    watcher.position_size = 100.0  # 100 tokens
    watcher.get_price = MagicMock(return_value=1.45)
    watcher.get_rsi = MagicMock(return_value=72.0)  # Overbought
    watcher.get_detailed_status = MagicMock(return_value={"status": "IN_POSITION", "pnl_pct": 45.0})
    return watcher


@pytest.fixture
def sample_watchlist() -> Dict[str, Dict[str, Any]]:
    """Sample watchlist with SOL and BONK for testing."""
    return {
        "SOL": {
            "mint": "So11111111111111111111111111111111111111112",
            "symbol": "SOL",
            "decimals": 9,
        },
        "BONK": {
            "mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
            "symbol": "BONK",
            "decimals": 5,
        },
        "WIF": {
            "mint": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
            "symbol": "WIF",
            "decimals": 6,
        },
    }


@pytest.fixture
def sample_token_metadata() -> Dict[str, Any]:
    """Standard token metadata for testing."""
    return {
        "mint": "MockMint123456789abcdefghijklmnopqrstuvwx",
        "symbol": "MOCK",
        "name": "Mock Token",
        "decimals": 9,
        "liquidity_usd": 100000.0,
        "volume_24h": 50000.0,
        "price_usd": 1.45,
        "is_verified": True,
        "is_frozen": False,
    }


@pytest.fixture
def mock_capital_manager():
    """
    Mock CapitalManager with pre-seeded balances.
    Cash: $10,000, SOL: 5.0
    """
    cm = MagicMock()
    cm.get_cash_balance = MagicMock(return_value=10000.0)
    cm.get_sol_balance = MagicMock(return_value=5.0)
    cm.get_total_equity = MagicMock(return_value=10500.0)
    cm.get_positions = MagicMock(return_value={})
    cm.record_trade = MagicMock(return_value=True)
    cm.can_afford = MagicMock(return_value=True)
    return cm


@pytest.fixture
def paper_wallet_state() -> Dict[str, Any]:
    """Sample paper wallet state for testing."""
    return {
        "cash_balance": 10000.0,
        "sol_balance": 0.5,
        "positions": {},
        "trade_history": [],
        "stats": {"wins": 0, "losses": 0, "fees_paid_usd": 0.0},
    }


# ============================================================================
# CHAOS PARAMETERS (For E2E Mocked Testing)
# ============================================================================


@pytest.fixture
def chaos_params() -> Dict[str, Any]:
    """
    Chaos parameters for E2E testing.
    These simulate real-world conditions without hitting devnet.
    """
    return {
        "bundle_inclusion_probability": 0.85,  # 85% Jito success
        "rpc_latency_ms": 50,                  # Simulated RPC delay
        "slippage_variance": 0.02,             # ±2% slippage noise
        "price_drift_per_tick": 0.001,         # 0.1% per tick
        "network_congestion_level": 0.3,       # 30% congestion
    }


# ============================================================================
# UTILITY FIXTURES
# ============================================================================


@pytest.fixture
def temp_db(tmp_path):
    """
    Create an ephemeral SQLite database for testing.
    Automatically cleaned up after test.
    """
    db_path = tmp_path / "test_phantom.db"
    return str(db_path)


@pytest.fixture
def mock_jupiter_quote():
    """Mock Jupiter quote response."""
    return {
        "inputMint": "So11111111111111111111111111111111111111112",
        "outputMint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
        "inAmount": "1000000000",
        "outAmount": "50000000000000",
        "priceImpactPct": "0.05",
        "routePlan": [{"swapInfo": {"ammKey": "test_pool"}}],
    }
