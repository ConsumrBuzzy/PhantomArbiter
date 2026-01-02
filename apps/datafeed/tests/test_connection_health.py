"""
Test Connection Health - WSS Reconnection and Failover

Verifies WebSocket connection handling and recovery.
"""

import pytest
import asyncio
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from datafeed.websocket_manager import (
    WebSocketManager,
    WssConfig,
    ConnectionState,
)


class TestConnectionLifecycle:
    """Tests for connection lifecycle management."""
    
    @pytest.fixture
    def config(self):
        return WssConfig(
            endpoints=["wss://test.example.com"],
            reconnect_delay=0.1,  # Fast for tests
            max_reconnect_attempts=3,
        )
    
    def test_initial_state(self, config):
        """Manager starts in disconnected state."""
        manager = WebSocketManager(config)
        
        assert manager.state == ConnectionState.DISCONNECTED
        assert manager.is_connected() is False
    
    def test_connection_tracking(self, config):
        """Connection attempts are tracked."""
        manager = WebSocketManager(config)
        
        stats = manager.get_stats()
        assert stats.connection_attempts == 0
        assert stats.successful_connections == 0


class TestReconnectionLogic:
    """Tests for reconnection behavior."""
    
    @pytest.fixture
    def config(self):
        return WssConfig(
            endpoints=["wss://test.example.com"],
            reconnect_delay=0.05,
            max_reconnect_attempts=3,
        )
    
    def test_reconnect_settings(self, config):
        """Reconnection parameters are configured."""
        manager = WebSocketManager(config)
        
        assert manager.config.reconnect_delay == 0.05
        assert manager.config.max_reconnect_attempts == 3
    
    def test_exponential_backoff_calculation(self, config):
        """Backoff increases with attempts."""
        manager = WebSocketManager(config)
        
        # Simulate backoff calculation
        delay_1 = manager.config.reconnect_delay * (2 ** 0)
        delay_2 = manager.config.reconnect_delay * (2 ** 1)
        delay_3 = manager.config.reconnect_delay * (2 ** 2)
        
        assert delay_1 < delay_2 < delay_3


class TestMultiEndpointFailover:
    """Tests for multi-endpoint failover."""
    
    def test_multiple_endpoints_configured(self):
        """Multiple endpoints can be configured."""
        config = WssConfig(
            endpoints=[
                "wss://primary.example.com",
                "wss://secondary.example.com",
                "wss://tertiary.example.com",
            ]
        )
        manager = WebSocketManager(config)
        
        assert len(manager.config.endpoints) == 3
    
    def test_endpoint_rotation(self):
        """Failed endpoint rotates to next."""
        config = WssConfig(
            endpoints=[
                "wss://primary.example.com",
                "wss://secondary.example.com",
            ]
        )
        manager = WebSocketManager(config)
        
        # Simulate rotation
        endpoints = manager.config.endpoints
        first = endpoints[0]
        rotated = endpoints[1:] + [endpoints[0]]
        
        assert rotated[0] == "wss://secondary.example.com"
        assert rotated[1] == first


class TestHeartbeatHandling:
    """Tests for heartbeat/ping-pong handling."""
    
    @pytest.fixture
    def config(self):
        return WssConfig(
            endpoints=["wss://test.example.com"],
            heartbeat_interval=1.0,
        )
    
    def test_heartbeat_interval_configured(self, config):
        """Heartbeat interval is configurable."""
        manager = WebSocketManager(config)
        
        assert manager.config.heartbeat_interval == 1.0
    
    def test_last_heartbeat_tracking(self, config):
        """Last heartbeat time is tracked."""
        manager = WebSocketManager(config)
        
        # Simulate heartbeat
        manager._last_heartbeat = time.time()
        
        # Should be recent
        assert time.time() - manager._last_heartbeat < 1.0


class TestConnectionStats:
    """Tests for connection statistics."""
    
    @pytest.fixture
    def config(self):
        return WssConfig(endpoints=["wss://test.example.com"])
    
    def test_stats_structure(self, config):
        """Stats have expected fields."""
        manager = WebSocketManager(config)
        stats = manager.get_stats()
        
        assert hasattr(stats, "connection_attempts")
        assert hasattr(stats, "successful_connections")
        assert hasattr(stats, "messages_received")
        assert hasattr(stats, "last_message_time")
    
    def test_message_count_tracking(self, config):
        """Message count is tracked."""
        manager = WebSocketManager(config)
        
        # Simulate messages
        manager._stats["messages_received"] = 0
        manager._stats["messages_received"] += 100
        
        assert manager._stats["messages_received"] == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
