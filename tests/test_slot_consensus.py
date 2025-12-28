"""
Test Suite: Slot Consensus Engine (Phase 17)
=============================================
Verifies de-duplication and slot validation for parallel WSS streams.

Run: pytest tests/test_slot_consensus.py -v
"""

import pytest


def test_consensus_imports():
    """Verify Consensus classes are available."""
    import phantom_core
    
    assert hasattr(phantom_core, 'SignatureDedup')
    assert hasattr(phantom_core, 'SlotTracker')
    assert hasattr(phantom_core, 'ConsensusEngine')


def test_signature_dedup_basic():
    """Test basic de-duplication."""
    import phantom_core
    
    dedup = phantom_core.SignatureDedup(max_size=100)
    
    sig1 = "abc123"
    sig2 = "def456"
    
    # First time seeing sig1 -> True (new)
    assert dedup.is_new(sig1) == True
    
    # Second time seeing sig1 -> False (duplicate)
    assert dedup.is_new(sig1) == False
    
    # First time seeing sig2 -> True (new)
    assert dedup.is_new(sig2) == True
    
    # Size should be 2
    assert dedup.size() == 2


def test_signature_dedup_eviction():
    """Test eviction when capacity is reached."""
    import phantom_core
    
    dedup = phantom_core.SignatureDedup(max_size=10)
    
    # Fill it up
    for i in range(10):
        assert dedup.is_new(f"sig_{i}") == True
    
    assert dedup.size() == 10
    
    # Add one more - should trigger eviction
    assert dedup.is_new("sig_overflow") == True
    
    # Size should be reduced (eviction batch = 25% = 2 items removed, +1 added)
    assert dedup.size() < 10


def test_signature_dedup_clear():
    """Test clearing the dedup filter."""
    import phantom_core
    
    dedup = phantom_core.SignatureDedup()
    
    for i in range(100):
        dedup.is_new(f"sig_{i}")
    
    assert dedup.size() == 100
    
    dedup.clear()
    assert dedup.size() == 0


def test_slot_tracker_basic():
    """Test slot tracking and freshness."""
    import phantom_core
    
    tracker = phantom_core.SlotTracker(max_slot_lag=2)
    
    # First update
    status = tracker.update_slot("helius", 1000)
    assert status == 1  # Newer
    assert tracker.get_latest_slot() == 1000
    
    # Same slot from different provider
    status = tracker.update_slot("alchemy", 1000)
    assert status == 0  # Current
    
    # Newer slot
    status = tracker.update_slot("helius", 1005)
    assert status == 1  # Newer
    assert tracker.get_latest_slot() == 1005
    
    # Stale slot (more than 2 behind)
    status = tracker.update_slot("alchemy", 1000)
    assert status == -1  # Stale


def test_slot_tracker_acceptable():
    """Test is_acceptable method."""
    import phantom_core
    
    tracker = phantom_core.SlotTracker(max_slot_lag=2)
    tracker.update_slot("helius", 100)
    
    # Current slot is acceptable
    assert tracker.is_acceptable(100) == True
    
    # 1 slot behind is acceptable
    assert tracker.is_acceptable(99) == True
    
    # 2 slots behind is acceptable (within lag)
    assert tracker.is_acceptable(98) == True
    
    # 3 slots behind is NOT acceptable
    assert tracker.is_acceptable(97) == False


def test_consensus_engine_integration():
    """Test the full ConsensusEngine workflow."""
    import phantom_core
    
    engine = phantom_core.ConsensusEngine(max_signatures=1000, max_slot_lag=2)
    
    # First message from Helius - should be accepted
    assert engine.should_process("helius", "sig1", 100) == True
    
    # Same message from Alchemy (duplicate) - should be rejected
    assert engine.should_process("alchemy", "sig1", 100) == False
    
    # New message from Alchemy - should be accepted
    assert engine.should_process("alchemy", "sig2", 101) == True
    
    # Stale message - should be rejected
    assert engine.should_process("quicknode", "sig3", 50) == False
    
    # Check stats
    accepted, duplicates, stale, latest_slot = engine.get_stats()
    assert accepted == 2
    assert duplicates == 1
    assert stale == 1
    assert latest_slot == 101


def test_consensus_engine_slot_freshness():
    """Test quick slot freshness check."""
    import phantom_core
    
    engine = phantom_core.ConsensusEngine()
    engine.should_process("helius", "sig1", 1000)
    
    assert engine.is_slot_fresh(1000) == True
    assert engine.is_slot_fresh(999) == True
    assert engine.is_slot_fresh(998) == True
    assert engine.is_slot_fresh(990) == False


def test_consensus_engine_stats_reset():
    """Test stats reset functionality."""
    import phantom_core
    
    engine = phantom_core.ConsensusEngine()
    
    for i in range(100):
        engine.should_process("helius", f"sig_{i}", 1000 + i)
    
    accepted, _, _, _ = engine.get_stats()
    assert accepted == 100
    
    engine.reset_stats()
    accepted, duplicates, stale, _ = engine.get_stats()
    assert accepted == 0
    assert duplicates == 0
    assert stale == 0


def test_consensus_engine_high_throughput():
    """Benchmark high-throughput message processing."""
    import phantom_core
    import time
    
    engine = phantom_core.ConsensusEngine(max_signatures=50000)
    
    providers = ["helius", "alchemy", "quicknode", "chainstack"]
    
    start = time.perf_counter()
    
    # Simulate 10K messages with 25% duplicates
    for i in range(10000):
        provider = providers[i % len(providers)]
        sig = f"sig_{i % 7500}"  # 25% will be duplicates
        slot = 1000 + (i // 10)
        engine.should_process(provider, sig, slot)
    
    elapsed_ms = (time.perf_counter() - start) * 1000
    
    print(f"\n10K messages processed in {elapsed_ms:.2f}ms")
    print(f"Throughput: {10000 / (elapsed_ms / 1000):,.0f} msg/sec")
    
    accepted, duplicates, stale, _ = engine.get_stats()
    print(f"Accepted: {accepted}, Duplicates: {duplicates}, Stale: {stale}")
    
    # Should process at least 100K msg/sec
    assert elapsed_ms < 100, f"Too slow: {elapsed_ms}ms for 10K messages"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
