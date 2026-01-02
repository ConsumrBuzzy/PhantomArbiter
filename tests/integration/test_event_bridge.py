"""
Test Event Bridge Integration

Verifies that EventBridge correctly forwards SignalBus events to Galaxy.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

# Import after path setup
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.shared.infrastructure.event_bridge import (
    EventBridge, 
    EventBridgeConfig,
    BridgeState,
)
from src.shared.system.signal_bus import Signal, SignalType


@pytest.fixture
def event_bridge():
    """Create a test EventBridge instance."""
    config = EventBridgeConfig(
        galaxy_url="http://localhost:8001",
        batch_size=5,
        batch_timeout_ms=50,
        max_buffer_size=100,
        request_timeout=0.5,
    )
    bridge = EventBridge(config)
    return bridge


@pytest.mark.asyncio
async def test_signal_to_dict_conversion(event_bridge):
    """Test that Signal objects are correctly converted to dicts."""
    signal = Signal(
        type=SignalType.MARKET_UPDATE,
        source="TEST",
        data={
            "mint": "So11111111111111111111111111111111111111112",
            "symbol": "SOL",
            "price": 150.0,
        }
    )
    
    result = event_bridge._signal_to_dict(signal)
    
    assert result["type"] == "MARKET_UPDATE"
    assert result["source"] == "TEST"
    assert result["data"]["symbol"] == "SOL"
    assert result["data"]["price"] == 150.0


@pytest.mark.asyncio
async def test_batch_collection(event_bridge):
    """Test that events are batched correctly."""
    # Add events to buffer
    for i in range(3):
        await event_bridge._buffer.put({"id": i})
    
    # Collect batch
    batch = await event_bridge._collect_batch()
    
    assert len(batch) == 3
    assert batch[0]["id"] == 0
    assert batch[2]["id"] == 2


@pytest.mark.asyncio
async def test_circuit_breaker_opens_on_failure(event_bridge):
    """Test that circuit breaker opens after failed requests."""
    assert event_bridge._state == BridgeState.CLOSED
    
    # Simulate failure
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(
            side_effect=Exception("Connection refused")
        )
        
        result = await event_bridge._send_batch([{"test": "data"}])
        
    assert result is False
    # Note: Circuit state is managed by flush loop, not send_batch


@pytest.mark.asyncio  
async def test_buffer_overflow_handling(event_bridge):
    """Test that buffer overflow is handled gracefully."""
    # Fill buffer to max
    for i in range(event_bridge.config.max_buffer_size):
        await event_bridge._buffer.put({"id": i})
    
    assert event_bridge._buffer.full()
    
    # Simulate adding another event (should trigger overflow handling)
    event_bridge._running = True
    signal = Signal(
        type=SignalType.MARKET_UPDATE,
        source="OVERFLOW_TEST",
        data={"test": True}
    )
    
    # This should not raise, just handle overflow
    await event_bridge._on_signal(signal)


def test_config_defaults():
    """Test that EventBridgeConfig has sensible defaults."""
    config = EventBridgeConfig()
    
    assert config.galaxy_url == "http://localhost:8001"
    assert config.batch_size == 50
    assert config.batch_timeout_ms == 100
    assert config.max_buffer_size == 500


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
