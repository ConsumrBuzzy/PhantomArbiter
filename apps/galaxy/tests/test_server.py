"""
Test Galaxy Server Standalone

Verifies that Galaxy server works independently of Core.
"""

import pytest
from fastapi.testclient import TestClient

# Galaxy imports
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from galaxy.server import app
from galaxy.models import EventPayload, EventType


@pytest.fixture
def client():
    """Create test client for Galaxy server."""
    return TestClient(app)


def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "ok"
    assert "clients" in data
    assert "objects" in data


def test_state_endpoint_empty(client):
    """Test state endpoint returns empty list initially."""
    response = client.get("/api/v1/state")
    assert response.status_code == 200
    assert response.json() == []


def test_receive_single_event(client):
    """Test receiving a single event."""
    event = {
        "type": "MARKET_UPDATE",
        "source": "TEST",
        "timestamp": 1234567890.0,
        "data": {
            "mint": "So11111111111111111111111111111111111111112",
            "symbol": "SOL",
            "price": 150.0,
            "volume_24h": 1000000,
            "liquidity": 50000,
        }
    }
    
    response = client.post("/api/v1/event", json=event)
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "processed"


def test_receive_batch_events(client):
    """Test receiving a batch of events."""
    batch = {
        "events": [
            {
                "type": "MARKET_UPDATE",
                "source": "TEST",
                "timestamp": 1234567890.0,
                "data": {
                    "mint": f"Token{i}",
                    "symbol": f"TKN{i}",
                    "price": 100.0 + i,
                }
            }
            for i in range(5)
        ]
    }
    
    response = client.post("/api/v1/events", json=batch)
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "processed"
    assert data["received"] == 5
    assert data["transformed"] == 5


def test_websocket_connection(client):
    """Test WebSocket connection and state snapshot."""
    with client.websocket_connect("/ws/v1/stream") as websocket:
        # Should receive state snapshot on connect
        data = websocket.receive_json()
        assert data["type"] == "STATE_SNAPSHOT"
        assert "data" in data


def test_visual_transformer_integration(client):
    """Test that events are transformed correctly."""
    # Send a whale event
    event = {
        "type": "WHALE_ACTIVITY",
        "source": "WHALE",
        "timestamp": 1234567890.0,
        "data": {
            "mint": "WhaleToken123",
            "symbol": "WHALE",
            "volume_24h": 100000,  # Above whale threshold
            "liquidity": 1000000,
        }
    }
    
    response = client.post("/api/v1/event", json=event)
    assert response.status_code == 200
    
    # Check state includes the whale
    response = client.get("/api/v1/state")
    state = response.json()
    
    assert len(state) >= 1
    whale_obj = next((o for o in state if o["id"] == "WhaleToken123"), None)
    assert whale_obj is not None
    assert whale_obj["archetype"] == "WHALE"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
