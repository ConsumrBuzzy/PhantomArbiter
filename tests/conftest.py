"""
Phantom Arbiter Test Fixtures
=============================
Shared pytest fixtures for deterministic, isolated testing.

This module provides the foundation for testing the trading system
with clean state isolation and mocked external dependencies.
"""

import pytest
import asyncio
import os
from pathlib import Path
from typing import Dict, Any, Optional
from unittest.mock import MagicMock, AsyncMock


# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """
    Isolated SQLite database for each test.
    
    Patches PersistenceDB singleton to use a fresh temp database,
    ensuring complete isolation between tests.
    """
    test_db = tmp_path / "test_arbiter.db"
    
    # Create a single instance for this test
    _db_instance = None
    
    def mock_get_db():
        nonlocal _db_instance
        from src.shared.system.persistence import PersistenceDB
        
        if _db_instance is None:
            # Create fresh instance on first call
            PersistenceDB._instance = None
            _db_instance = PersistenceDB(str(test_db))
            
            # Initialize schema immediately
            with _db_instance._get_connection() as conn:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS engine_vaults (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        engine TEXT NOT NULL,
                        asset TEXT NOT NULL,
                        balance REAL NOT NULL DEFAULT 0,
                        initial_balance REAL NOT NULL DEFAULT 0,
                        updated_at REAL NOT NULL,
                        UNIQUE(engine, asset)
                    );
                    CREATE INDEX IF NOT EXISTS idx_engine_vaults_engine ON engine_vaults(engine);
                """)
                conn.commit()
        
        return _db_instance
    
    monkeypatch.setattr("src.shared.system.persistence.get_db", mock_get_db)
    
    # Also reset VaultRegistry singleton
    try:
        from src.shared.state.vault_manager import VaultRegistry
        import src.shared.state.vault_manager as vm
        VaultRegistry._instance = None
        vm._vault_registry = None
    except ImportError:
        pass
    
    yield test_db
    
    # Cleanup singletons
    _db_instance = None
    try:
        from src.shared.system.persistence import PersistenceDB
        from src.shared.state.vault_manager import VaultRegistry
        import src.shared.state.vault_manager as vm
        PersistenceDB._instance = None
        VaultRegistry._instance = None
        vm._vault_registry = None
    except ImportError:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# MOCK FEED FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_jupiter_feed(monkeypatch):
    """
    JupiterFeed returning deterministic prices.
    
    Prevents HTTP calls during tests while providing
    controllable price data for strategy testing.
    """
    from tests.mocks.mock_feeds import MockJupiterFeed
    
    mock_feed = MockJupiterFeed()
    
    # Patch the feed import in engines
    monkeypatch.setattr(
        "src.shared.feeds.jupiter_feed.JupiterFeed",
        lambda: mock_feed
    )
    
    return mock_feed


# Force load pytest-asyncio if auto-discovery fails
pytest_plugins = ["pytest_asyncio"]

@pytest.fixture
def mock_settings():
    """
    Default price dictionary for testing.
    
    Provides a consistent market state for deterministic tests.
    """
    return {
        "SOL": 150.0,
        "USDC": 1.0,
        "JUP": 0.85,
        "JTO": 2.50,
        "BONK": 0.00001,
        "WIF": 1.20,
    }


@pytest.fixture
def mock_prices():
    """
    Default price dictionary for testing.
    
    Provides a consistent market state for deterministic tests.
    """
    return {
        "SOL": 150.0,
        "USDC": 1.0,
        "JUP": 0.85,
        "JTO": 2.50,
        "BONK": 0.00001,
        "WIF": 1.20,
    }


@pytest.fixture
def arb_triangle_prices():
    """
    Price configuration creating a profitable arbitrage triangle.
    
    SOL -> JUP -> USDC -> SOL with ~1% profit opportunity.
    Used to verify ArbScanner detection logic.
    """
    return {
        "venues": {
            "raydium": {
                "SOL/USDC": 150.0,
                "JUP/USDC": 0.85,
                "SOL/JUP": 175.0,  # Mispriced - creates arb
            },
            "orca": {
                "SOL/USDC": 150.5,
                "JUP/USDC": 0.86,
                "SOL/JUP": 176.5,
            },
        },
        "spread_pct": 1.2,  # Expected spread
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ENGINE FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_engine_config():
    """Default configuration for test engines."""
    return {
        "arb": {
            "min_spread": 0.5,
            "max_trade_usd": 100,
            "scan_interval": 1,
            "risk_tier": "low",
        },
        "funding": {
            "leverage": 2.0,
            "watchdog_threshold": -0.0005,
            "rebalance_enabled": True,
            "max_position_usd": 500,
        },
        "scalp": {
            "take_profit_pct": 10.0,
            "stop_loss_pct": 5.0,
            "max_pods": 3,
            "sentiment_threshold": 0.7,
        },
    }


@pytest.fixture
def paper_engine(temp_db, mock_jupiter_feed):
    """
    BaseEngine subclass in paper mode with mock feed.
    
    Provides a fully isolated engine instance for lifecycle testing.
    """
    from tests.mocks.mock_engine import MockTradingEngine
    
    engine = MockTradingEngine(name="test_engine", live_mode=False)
    yield engine
    
    # Cleanup
    if engine.running:
        import asyncio
        try:
            asyncio.get_event_loop().run_until_complete(engine.stop())
        except RuntimeError:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# WALLET FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_wallet_balances():
    """Fake live wallet balances for testing."""
    return {
        "SOL": 5.0,
        "USDC": 500.0,
        "JUP": 100.0,
    }


@pytest.fixture
def mock_wallet_manager(mock_wallet_balances, monkeypatch):
    """
    Mocked WalletManager returning preset balances.
    
    Prevents any real Solana RPC calls during tests.
    """
    from tests.mocks.mock_wallet import MockWalletManager
    
    mock_wallet = MockWalletManager(balances=mock_wallet_balances)
    
    monkeypatch.setattr(
        "src.drivers.wallet_manager.WalletManager",
        lambda: mock_wallet
    )
    
    return mock_wallet


# ═══════════════════════════════════════════════════════════════════════════════
# SIGNAL BUS FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_signal_bus(monkeypatch):
    """
    Captures all emitted signals for assertion.
    
    Allows tests to verify that engines emit correct signals
    without side effects.
    """
    from tests.mocks.mock_signal_bus import MockSignalBus
    
    mock_bus = MockSignalBus()
    
    monkeypatch.setattr(
        "src.shared.system.signal_bus.signal_bus",
        mock_bus
    )
    
    return mock_bus


# ═══════════════════════════════════════════════════════════════════════════════
# ASYNC FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_rpc_client():
    """
    Mocked Solana RPC client.
    
    Returns preset responses for common RPC calls
    without network access.
    """
    from tests.mocks.mock_rpc import MockRpcClient
    return MockRpcClient()


# ═══════════════════════════════════════════════════════════════════════════════
# GRAPH FIXTURES (for Arb Engine)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def seeded_hop_graph():
    """
    HopGraphEngine pre-seeded with test pools.
    
    Contains a known profitable cycle for detection testing.
    """
    from src.engines.arb.graph import HopGraphEngine
    
    engine = HopGraphEngine(max_hops=4, min_profit_pct=0.1)
    
    # Seed with test pools
    test_pools = [
        {
            "base_mint": "So11111111111111111111111111111111111111112",  # SOL
            "quote_mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
            "price": 150.0,
            "liquidity_usd": 10000000,
            "slot": 100000,
            "dex": "RAYDIUM",
            "pool_address": "pool1",
            "fee_bps": 25,
        },
        {
            "base_mint": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",  # JUP
            "quote_mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
            "price": 0.85,
            "liquidity_usd": 5000000,
            "slot": 100000,
            "dex": "ORCA",
            "pool_address": "pool2",
            "fee_bps": 30,
        },
        {
            "base_mint": "So11111111111111111111111111111111111111112",  # SOL
            "quote_mint": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",  # JUP
            "price": 180.0,  # Mispriced for arb
            "liquidity_usd": 2000000,
            "slot": 100000,
            "dex": "METEORA",
            "pool_address": "pool3",
            "fee_bps": 20,
        },
    ]
    
    for pool in test_pools:
        engine.update_pool(pool)
    
    return engine


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITY FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def capture_logs(caplog):
    """Capture logs for assertion."""
    import logging
    caplog.set_level(logging.DEBUG)
    return caplog


@pytest.fixture
def freeze_time(monkeypatch):
    """
    Freeze time.time() for deterministic timestamp testing.
    """
    import time
    frozen_time = 1700000000.0  # Fixed timestamp
    
    monkeypatch.setattr(time, "time", lambda: frozen_time)
    
    return frozen_time
