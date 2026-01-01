"""
Test Suite: WSS Aggregator (Phase 17.5)
=======================================
Verifies Rust WebSocket aggregation for parallel RPC racing.

Run: pytest tests/test_wss_aggregator.py -v
"""

import pytest


def test_wss_aggregator_imports():
    """Verify WSS Aggregator classes are available."""
    import phantom_core

    assert hasattr(phantom_core, "WssAggregator")
    assert hasattr(phantom_core, "WssEvent")
    assert hasattr(phantom_core, "WssStats")


def test_wss_aggregator_creation():
    """Test WssAggregator instantiation."""
    import phantom_core

    aggregator = phantom_core.WssAggregator(channel_size=100)

    assert aggregator is not None
    assert aggregator.is_running() == False
    assert aggregator.pending_count() == 0


def test_wss_aggregator_stats():
    """Test WssAggregator stats."""
    import phantom_core

    aggregator = phantom_core.WssAggregator()
    stats = aggregator.get_stats()

    assert stats.active_connections == 0
    assert stats.messages_received == 0
    assert stats.messages_accepted == 0
    assert stats.messages_dropped == 0


def test_wss_aggregator_poll_empty():
    """Polling an idle aggregator returns None."""
    import phantom_core

    aggregator = phantom_core.WssAggregator()

    event = aggregator.poll_event()
    assert event is None

    events = aggregator.poll_events(10)
    assert len(events) == 0


def test_wss_aggregator_start_stop():
    """Test start/stop without real endpoints (dry run)."""
    import phantom_core
    import time

    aggregator = phantom_core.WssAggregator()

    # Start with empty endpoints (should work, just no connections)
    aggregator.start(
        endpoints=[],
        program_ids=["675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"],
        commitment="processed",
    )

    assert aggregator.is_running() == True

    # Give it a moment
    time.sleep(0.1)

    aggregator.stop()
    assert aggregator.is_running() == False


def test_wss_aggregator_double_start():
    """Starting twice should raise error."""
    import phantom_core

    aggregator = phantom_core.WssAggregator()

    aggregator.start([], [], "processed")

    with pytest.raises(RuntimeError):
        aggregator.start([], [], "processed")

    aggregator.stop()


def test_wss_event_repr():
    """Test WssEvent representation (if we could create one)."""
    import phantom_core

    # WssEvent is created by Rust, we can only test the class exists
    assert phantom_core.WssEvent is not None


def test_wss_stats_fields():
    """Verify WssStats has all expected fields."""
    import phantom_core

    aggregator = phantom_core.WssAggregator()
    stats = aggregator.get_stats()

    # Check all fields exist
    assert hasattr(stats, "active_connections")
    assert hasattr(stats, "messages_received")
    assert hasattr(stats, "messages_accepted")
    assert hasattr(stats, "messages_dropped")
    assert hasattr(stats, "avg_latency_ms")

    print(
        f"\nWssStats: connections={stats.active_connections}, "
        f"received={stats.messages_received}"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
