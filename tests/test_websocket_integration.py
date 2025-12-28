"""
Test Suite: WebSocket Integration (Phase 20.1)
==============================================
Verifies that WebSocketListener correctly integrates with:
1. Rust WssAggregator
2. ProviderPool
"""

import pytest
import threading
import time
from unittest.mock import MagicMock, patch

# Mock modules before importing listener
import sys
sys.modules['src.core.provider_pool'] = MagicMock()

from src.core.websocket_listener import WebSocketListener, create_websocket_listener
import phantom_core

class MockProviderPool:
    def get_wss_endpoints(self):
        return ["wss://mock-provider-1.com", "wss://mock-provider-2.com"]

@pytest.fixture
def mock_deps():
    price_cache = MagicMock()
    watched_mints = {"MINT1": "SYM1", "MINT2": "SYM2"}
    return price_cache, watched_mints

def test_listener_init(mock_deps):
    """Test initialization of Rust components."""
    price_cache, watched_mints = mock_deps
    
    with patch('src.core.websocket_listener.ProviderPool', return_value=MockProviderPool()):
        listener = WebSocketListener(price_cache, watched_mints)
        
        # Verify Rust aggregator creation
        assert isinstance(listener.aggregator, phantom_core.WssAggregator)
        assert hasattr(listener, 'provider_pool')
        assert listener.running == False

def test_listener_start_stop(mock_deps):
    """Test start lifecycle calls Rust start."""
    price_cache, watched_mints = mock_deps
    
    with patch('src.core.websocket_listener.ProviderPool', return_value=MockProviderPool()):
        listener = WebSocketListener(price_cache, watched_mints)
        
        # Mock the aggregator instance methods
        listener.aggregator.start = MagicMock()
        listener.aggregator.stop = MagicMock()
        listener.aggregator.is_running = MagicMock(return_value=False)
        
        # Start
        listener.start()
        
        assert listener.running == True
        listener.aggregator.start.assert_called_once()
        
        # Verify args passed to Rust
        call_args = listener.aggregator.start.call_args
        assert "wss://mock-provider-1.com" in call_args[1]['endpoints']
        assert len(call_args[1]['program_ids']) == 3  # Raydium V4, CLMM, Orca
        
        # Stop
        listener.stop()
        assert listener.running == False
        listener.aggregator.stop.assert_called_once()

def test_process_event_logic(mock_deps):
    """Test event filtering logic in _process_event."""
    price_cache, watched_mints = mock_deps
    
    with patch('src.core.websocket_listener.ProviderPool', return_value=MockProviderPool()):
        listener = WebSocketListener(price_cache, watched_mints)
        
        # Hack internal stats for testing
        listener.stats["swaps_detected"] = 0
        listener.stats["raydium_swaps"] = 0
        
        # 1. Test Swap Event
        # Create a real WssEvent (Rust object) if possible, or mock object if Python can't alloc
        # Since WssEvent is Rust-defined, we might need a helper or just mock attribute access
        
        # Try to instantiate via phantom_core? Not exposed as constructor usually
        # We'll mock the object structure
        class MockEvent:
            provider = "test_provider"
            slot = 12345
            signature = "sig123"
            logs = [
                "Program log: Instruction: Swap",
                "Program ray_log: ...", 
                "Program 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8 success"
            ]
            latency_ms = 10.5
            
        event = MockEvent()
        listener._process_event(event)
        
        assert listener.stats["swaps_detected"] == 1
        assert listener.stats["raydium_swaps"] == 1
        assert listener.stats["latency_stats"]["test_provider"] == 10.5
        
        # 2. Test Non-Swap Event
        event_noise = MockEvent()
        event_noise.logs = ["Program log: Instruction: InitializeAccount", "Program Tokenkeg..."]
        
        listener._process_event(event_noise)
        assert listener.stats["swaps_detected"] == 1  # Unchanged

if __name__ == "__main__":
    try:
        pytest.main([__file__, "-v"])
    except Exception as e:
        with open("error_log.txt", "w") as f:
            f.write(str(e))

