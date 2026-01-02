"""
Hydration Manager - State Reconstruction.

Rebuilds SQLite from checkpoints and deltas on startup.
Implements the "Rehydration" phase of the Bellows architecture.
"""

from __future__ import annotations

import os
import time
from typing import Optional, Dict, List, Any

from src.shared.system.logging import Logger
from src.data_storage.snapshot_service import (
    SnapshotService,
    MarketSnapshot,
    get_snapshot_service,
)
from src.data_storage.archive_engine import ArchiveEngine, get_archive_engine
from src.data_storage.trend_engine import DeltaBlock


class HydrationManager:
    """
    Manages state rehydration from archives.
    
    Boot sequence:
    1. Find latest checkpoint
    2. Load checkpoint into SQLite
    3. Replay deltas since checkpoint
    4. System is now "warm" with historical data
    """
    
    def __init__(
        self,
        snapshot_service: Optional[SnapshotService] = None,
        archive_engine: Optional[ArchiveEngine] = None,
    ) -> None:
        self.snapshot_service = snapshot_service or get_snapshot_service()
        self.archive_engine = archive_engine or get_archive_engine()
        
        self._checkpoint_loaded: Optional[MarketSnapshot] = None
        self._deltas_replayed = 0
        self._last_hydration_time = 0.0
    
    def boot_sync(self, db_manager=None) -> Dict[str, Any]:
        """
        Full rehydration sequence.
        
        Args:
            db_manager: Optional database manager. If None, imports default.
            
        Returns:
            Dict with hydration results.
        """
        start_time = time.time()
        Logger.info("🌊 [Hydration] Starting boot-sync...")
        
        results = {
            "checkpoint_loaded": False,
            "checkpoint_timestamp": 0,
            "checkpoint_tokens": 0,
            "deltas_replayed": 0,
            "duration_seconds": 0,
            "errors": [],
        }
        
        # Get database manager
        if db_manager is None:
            try:
                from src.data_storage.db_manager import db_manager as default_db
                db_manager = default_db
            except ImportError as e:
                results["errors"].append(f"DB import failed: {e}")
                return results
        
        # Step 1: Load checkpoint
        checkpoint = self.load_latest_checkpoint()
        
        if checkpoint:
            results["checkpoint_loaded"] = True
            results["checkpoint_timestamp"] = checkpoint.timestamp
            results["checkpoint_tokens"] = len(checkpoint.tokens)
            
            # Inject into database
            injected = self._inject_checkpoint(checkpoint, db_manager)
            Logger.info(f"🌊 [Hydration] Loaded checkpoint: {injected} tokens")
        else:
            Logger.info("🌊 [Hydration] No checkpoint found, starting fresh")
        
        # Step 2: Replay deltas
        since_ts = checkpoint.timestamp if checkpoint else 0
        since_seq = checkpoint.sequence if checkpoint else 0
        
        replayed = self.replay_deltas(db_manager, since_ts, since_seq)
        results["deltas_replayed"] = replayed
        
        # Done
        duration = time.time() - start_time
        results["duration_seconds"] = round(duration, 2)
        self._last_hydration_time = time.time()
        
        Logger.success(
            f"🌊 [Hydration] Complete: {results['checkpoint_tokens']} tokens, "
            f"{results['deltas_replayed']} deltas, {results['duration_seconds']}s"
        )
        
        return results
    
    def load_latest_checkpoint(self) -> Optional[MarketSnapshot]:
        """Load the most recent checkpoint."""
        checkpoint = self.snapshot_service.get_latest_checkpoint()
        self._checkpoint_loaded = checkpoint
        return checkpoint
    
    def _inject_checkpoint(self, checkpoint: MarketSnapshot, db_manager) -> int:
        """
        Inject checkpoint prices into database.
        
        Returns count of tokens injected.
        """
        count = 0
        
        for mint, token in checkpoint.tokens.items():
            try:
                db_manager.insert_tick(
                    mint=mint,
                    price=token.price,
                    volume=token.volume_24h,
                    liq=token.liquidity,
                    latency=0,
                )
                count += 1
            except Exception:
                continue
        
        return count
    
    def replay_deltas(
        self,
        db_manager,
        since_timestamp: float = 0,
        since_sequence: int = 0,
    ) -> int:
        """
        Replay delta blocks since a checkpoint.
        
        Returns count of deltas replayed.
        """
        count = 0
        last_seq = since_sequence
        
        for delta in self.archive_engine.read_deltas_since(since_timestamp, since_sequence):
            try:
                # Check for gaps
                if delta.sequence > last_seq + 1:
                    Logger.warning(
                        f"🌊 [Hydration] Gap detected: seq {last_seq} -> {delta.sequence}"
                    )
                
                # Insert into database
                db_manager.insert_tick(
                    mint=delta.mint,
                    price=delta.close,  # Use close price
                    volume=delta.volume,
                    liq=delta.liquidity,
                    latency=0,
                )
                
                count += 1
                last_seq = delta.sequence
                
            except Exception:
                continue
        
        self._deltas_replayed = count
        return count
    
    def dehydrate(self, trend_engine=None, shared_cache=None) -> Dict[str, Any]:
        """
        Dehydration sequence (shutdown).
        
        Captures final checkpoint and flushes pending deltas.
        """
        results = {
            "checkpoint_saved": False,
            "checkpoint_path": "",
            "deltas_flushed": 0,
        }
        
        # Get TrendEngine
        if trend_engine is None:
            try:
                from src.data_storage.trend_engine import get_trend_engine
                trend_engine = get_trend_engine()
            except ImportError:
                return results
        
        # Flush pending deltas
        deltas = trend_engine.flush_all()
        if deltas:
            count = self.archive_engine.append_deltas(deltas)
            results["deltas_flushed"] = count
        
        # Set price source if provided
        if shared_cache:
            self.snapshot_service.set_price_source(shared_cache)
        
        # Capture checkpoint
        sequence = trend_engine.get_sequence()
        snapshot = self.snapshot_service.capture(sequence)
        
        if snapshot.tokens:
            path = self.snapshot_service.save_checkpoint(snapshot)
            results["checkpoint_saved"] = True
            results["checkpoint_path"] = path
        
        Logger.info(
            f"💧 [Dehydration] Saved: {results['deltas_flushed']} deltas, "
            f"checkpoint={results['checkpoint_saved']}"
        )
        
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """Get hydration statistics."""
        return {
            "checkpoint_loaded": self._checkpoint_loaded is not None,
            "checkpoint_tokens": len(self._checkpoint_loaded.tokens) if self._checkpoint_loaded else 0,
            "deltas_replayed": self._deltas_replayed,
            "last_hydration_time": self._last_hydration_time,
        }


# Global instance
_manager: Optional[HydrationManager] = None


def get_hydration_manager() -> HydrationManager:
    """Get or create the global HydrationManager instance."""
    global _manager
    if _manager is None:
        _manager = HydrationManager()
    return _manager


def boot_sync() -> Dict[str, Any]:
    """Convenience function for boot-sync."""
    return get_hydration_manager().boot_sync()


def dehydrate() -> Dict[str, Any]:
    """Convenience function for dehydration."""
    return get_hydration_manager().dehydrate()
