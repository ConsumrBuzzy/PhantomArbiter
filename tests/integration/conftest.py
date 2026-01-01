"""
Integration Test Configuration
==============================
Fixtures for component wiring tests with mocked external services.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import json
import os


# ============================================================================
# MOCKED EXTERNAL SERVICES
# ============================================================================


@pytest.fixture
def mock_jupiter_api():
    """
    Mock Jupiter API that returns canned quote responses.
    Use for testing swap routing without network calls.
    """
    async def mock_get_quote(input_mint, output_mint, amount, slippage_bps=50):
        return {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "inAmount": str(amount),
            "outAmount": str(int(amount * 1.5)),  # 1.5x output
            "priceImpactPct": "0.05",
            "routePlan": [
                {"swapInfo": {"ammKey": "raydium_pool_1", "label": "Raydium"}},
            ],
        }
    
    mock = MagicMock()
    mock.get_quote = AsyncMock(side_effect=mock_get_quote)
    mock.execute_swap = AsyncMock(return_value={"txid": "fake_tx_123"})
    return mock


@pytest.fixture
def mock_raydium_pool():
    """Mock Raydium pool state for integration testing."""
    return {
        "pool_id": "IntegrationTestPool",
        "base_mint": "So11111111111111111111111111111111111111112",
        "quote_mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "base_reserve": 50000.0,
        "quote_reserve": 2500000.0,
        "lp_supply": 100000.0,
        "open_orders": "OrdersAccount123",
        "amm_id": "AmmAccount456",
    }


@pytest.fixture
def test_db(tmp_path):
    """
    Create an ephemeral SQLite database for integration tests.
    Pre-initialized with schema.
    """
    from src.shared.system.db_manager import DBManager
    
    db_path = tmp_path / "test_phantom.db"
    db = DBManager(str(db_path))
    db._init_tables()
    yield db
    # Cleanup handled by tmp_path


@pytest.fixture
def mock_websocket_feed():
    """Mock WebSocket feed with synthetic market events."""
    events = [
        {"type": "PRICE_UPDATE", "mint": "SOL", "price": 100.50},
        {"type": "PRICE_UPDATE", "mint": "BONK", "price": 0.00001234},
        {"type": "POOL_UPDATE", "pool_id": "TestPool", "reserve_change": 5.2},
    ]
    
    async def mock_receive():
        for event in events:
            yield json.dumps(event)
    
    mock = MagicMock()
    mock.receive = mock_receive
    mock.connected = True
    return mock


# ============================================================================
# LAYER B: EXECUTION INTEGRATION FIXTURES
# ============================================================================


@pytest.fixture
def mock_execution_backend():
    """
    Mock ExecutionBackend for testing TacticalStrategy wiring.
    Tracks all calls for assertion.
    """
    backend = MagicMock()
    backend.execute_buy = AsyncMock(return_value={
        "success": True,
        "tx_id": "paper_buy_123",
        "filled_price": 1.45,
        "filled_amount": 100.0,
        "slippage_pct": 0.5,
        "fee_usd": 0.02,
    })
    backend.execute_sell = AsyncMock(return_value={
        "success": True,
        "tx_id": "paper_sell_456",
        "filled_price": 1.50,
        "filled_amount": 100.0,
        "slippage_pct": 0.3,
        "fee_usd": 0.02,
    })
    backend.calculate_slippage = MagicMock(return_value=0.5)
    backend.calls = []  # Track calls for assertion
    return backend


@pytest.fixture
def mock_signal_bus():
    """Mock SignalBus for testing event propagation."""
    from collections import defaultdict
    
    bus = MagicMock()
    bus.subscribers = defaultdict(list)
    bus.published = []
    
    def subscribe(signal_type, callback):
        bus.subscribers[signal_type].append(callback)
    
    def publish(signal_type, data):
        bus.published.append((signal_type, data))
        for callback in bus.subscribers[signal_type]:
            callback(data)
    
    bus.subscribe = subscribe
    bus.publish = publish
    return bus


# ============================================================================
# NOMAD/HYDRATION FIXTURES
# ============================================================================


@pytest.fixture
def sample_archive_state(tmp_path):
    """
    Create a sample JSON archive for hydration testing.
    Simulates saved Nomad state.
    """
    archive = {
        "version": "1.0",
        "timestamp": 1704100000,
        "positions": {
            "BONK": {
                "mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
                "entry_price": 0.00001200,
                "amount": 1000000,
                "timestamp": 1704099000,
            }
        },
        "hop_graph": {
            "nodes": ["SOL", "USDC", "BONK"],
            "edges": [
                {"from": "SOL", "to": "USDC", "weight": 0.02},
                {"from": "USDC", "to": "BONK", "weight": 0.015},
            ],
        },
    }
    
    archive_path = tmp_path / "nomad_archive.json"
    with open(archive_path, "w") as f:
        json.dump(archive, f)
    
    return str(archive_path)
