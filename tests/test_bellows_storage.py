"""
Test Bellows Storage Components

Verifies TrendEngine aggregation and Hydration cycle.
"""

import pytest
import os
import time
import tempfile
import shutil

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.data_storage.trend_engine import TrendEngine, DeltaBlock
from src.data_storage.snapshot_service import SnapshotService, MarketSnapshot, TokenSnapshot
from src.data_storage.archive_engine import ArchiveEngine
from src.data_storage.hydration_manager import HydrationManager


class TestTrendEngine:
    """Tests for TrendEngine aggregation."""
    
    def test_single_tick(self):
        """Test adding a single tick."""
        engine = TrendEngine()
        delta = engine.add_tick(
            mint="SOL123",
            symbol="SOL",
            price=150.0,
            volume=1000,
            timestamp=time.time(),
        )
        
        # First tick opens window, doesn't close
        assert delta is None
        assert engine._ticks_received == 1
    
    def test_window_close(self):
        """Test that new window closes previous."""
        engine = TrendEngine()
        # Anchor to a known window boundary (multiple of 60)
        base_time = 1704214800  # 2024-01-02 15:00:00 UTC (exact minute)
        
        # Window 1
        engine.add_tick("SOL", "SOL", 100, timestamp=base_time)
        engine.add_tick("SOL", "SOL", 105, timestamp=base_time + 30)
        
        # Window 2 (60 seconds later)
        delta = engine.add_tick("SOL", "SOL", 110, timestamp=base_time + 65)
        
        # Previous window should close
        assert delta is not None
        assert delta.open == 100
        assert delta.high == 105
        assert delta.close == 105
    
    def test_ohlc_aggregation(self):
        """Test OHLC values are computed correctly."""
        engine = TrendEngine()
        base_time = time.time()
        
        engine.add_tick("XYZ", "XYZ", 100, timestamp=base_time)
        engine.add_tick("XYZ", "XYZ", 120, timestamp=base_time + 10)  # High
        engine.add_tick("XYZ", "XYZ", 90, timestamp=base_time + 20)   # Low
        engine.add_tick("XYZ", "XYZ", 110, timestamp=base_time + 30)  # Close
        
        # Force close
        deltas = engine.flush_all()
        
        assert len(deltas) == 1
        d = deltas[0]
        assert d.open == 100
        assert d.high == 120
        assert d.low == 90
        assert d.close == 110
        assert d.tick_count == 4
    
    def test_zero_delta_suppression(self):
        """Test that unchanged prices are suppressed."""
        engine = TrendEngine()
        base_time = time.time()
        
        # Window 1 - price 100
        engine.add_tick("STABLE", "STABLE", 100.0, timestamp=base_time)
        
        # Window 2 - same price (should suppress)
        delta = engine.add_tick("STABLE", "STABLE", 100.0, timestamp=base_time + 65)
        
        # Delta should be suppressed
        assert delta is None
        assert engine._deltas_suppressed == 1


class TestDeltaBlock:
    """Tests for DeltaBlock serialization."""
    
    def test_jsonl_roundtrip(self):
        """Test JSONL serialization/deserialization."""
        original = DeltaBlock(
            timestamp=1704214800,
            mint="SOL123456789",
            symbol="SOL",
            open=150.12345678,
            high=155.0,
            low=148.0,
            close=152.5,
            volume=10000.50,
            tick_count=45,
            sequence=123,
        )
        
        jsonl = original.to_jsonl()
        restored = DeltaBlock.from_jsonl(jsonl)
        
        assert restored.timestamp == 1704214800
        assert restored.open == 150.12345678
        assert restored.sequence == 123


class TestArchiveEngine:
    """Tests for ArchiveEngine JSONL storage."""
    
    def test_append_and_read(self):
        """Test appending and reading deltas."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = ArchiveEngine(archive_dir=tmpdir)
            
            delta = DeltaBlock(
                timestamp=time.time(),
                mint="TEST",
                symbol="TST",
                open=1.0,
                high=2.0,
                low=0.5,
                close=1.5,
                sequence=1,
            )
            
            engine.append_delta(delta)
            
            # Read back
            files = engine.list_delta_files()
            assert len(files) == 1
            
            path = os.path.join(tmpdir, files[0])
            deltas = list(engine.read_deltas(path))
            assert len(deltas) == 1
            assert deltas[0].close == 1.5


class TestSnapshotService:
    """Tests for SnapshotService checkpoints."""
    
    def test_save_and_load(self):
        """Test checkpoint save and load."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = SnapshotService(checkpoint_dir=tmpdir)
            
            snapshot = MarketSnapshot(
                timestamp=time.time(),
                sequence=100,
                tokens={
                    "MINT1": TokenSnapshot("MINT1", "TKN", 1.5, 1000, 50000),
                }
            )
            
            path = service.save_checkpoint(snapshot)
            assert os.path.exists(path)
            
            # Load back
            loaded = service.get_latest_checkpoint()
            assert loaded is not None
            assert loaded.sequence == 100
            assert "MINT1" in loaded.tokens


class TestHydrationManager:
    """Tests for HydrationManager rehydration."""
    
    def test_dehydrate_rehydrate_cycle(self):
        """Test full dehydration and rehydration cycle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cp_dir = os.path.join(tmpdir, "checkpoints")
            delta_dir = os.path.join(tmpdir, "deltas")
            os.makedirs(cp_dir)
            os.makedirs(delta_dir)
            
            # Create services
            snapshot_svc = SnapshotService(checkpoint_dir=cp_dir)
            archive_eng = ArchiveEngine(archive_dir=delta_dir)
            
            # Create and save a checkpoint
            snapshot = MarketSnapshot(
                timestamp=time.time(),
                sequence=50,
                tokens={
                    "TEST": TokenSnapshot("TEST", "TST", 10.0),
                }
            )
            snapshot_svc.save_checkpoint(snapshot)
            
            # Create some deltas
            delta = DeltaBlock(
                timestamp=time.time(),
                mint="TEST",
                symbol="TST",
                open=10, high=12, low=9, close=11,
                sequence=51,
            )
            archive_eng.append_delta(delta)
            
            # Create hydration manager
            hydrator = HydrationManager(snapshot_svc, archive_eng)
            
            # Verify checkpoint found
            cp = hydrator.load_latest_checkpoint()
            assert cp is not None
            assert cp.sequence == 50


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
