"""
DNEM Position Snapshot
======================
Pre-trade position caching for partial fill detection.

The Problem:
- Jito bundles are atomic, but "PARTIAL" status can occur
- If bundle timeout/fails, we can't immediately tell what executed
- RPC latency means wallet/position queries may be stale

The Solution:
- Snapshot wallet + perp state BEFORE firing bundle
- If post-trade delta > threshold, compare to snapshot
- Calculate exactly what leg succeeded and rollback

Storage Options:
- Redis (production): Fast, shared across instances
- Local cache (dev): In-memory dict for testing
"""

from __future__ import annotations

import time
import json
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from abc import ABC, abstractmethod

from src.shared.system.logging import Logger


# =============================================================================
# SNAPSHOT DATA
# =============================================================================


@dataclass
class PositionSnapshot:
    """
    Pre-trade position state for rollback calculation.
    
    Captured immediately before SyncExecution fires bundle.
    """
    
    # Wallet state
    sol_balance: float
    usdc_balance: float
    
    # Perp state
    perp_size: float  # Negative = short
    perp_entry_price: float
    
    # Trade metadata
    intended_spot_qty: float
    intended_perp_qty: float
    intended_direction: str  # "ADD_SPOT" | "ADD_SHORT"
    
    # Timing
    timestamp_ms: int
    block_height: int
    bundle_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PositionSnapshot":
        return cls(**data)
    
    def expected_post_trade_sol(self) -> float:
        """Calculate expected SOL balance after trade."""
        if self.intended_direction == "ADD_SPOT":
            return self.sol_balance + self.intended_spot_qty
        else:
            return self.sol_balance - abs(self.intended_spot_qty)
    
    def expected_post_trade_perp(self) -> float:
        """Calculate expected perp size after trade."""
        if self.intended_direction == "ADD_SHORT":
            return self.perp_size - abs(self.intended_perp_qty)  # More negative
        else:
            return self.perp_size + self.intended_perp_qty  # Less negative


@dataclass
class RollbackAnalysis:
    """Result of comparing snapshot to current state."""
    
    spot_executed: bool
    perp_executed: bool
    spot_delta: float  # Actual - Expected
    perp_delta: float  # Actual - Expected
    needs_rollback: bool
    rollback_action: Optional[str]  # "CLOSE_SPOT" | "CLOSE_PERP" | None
    rollback_qty: float
    
    @property
    def is_partial_fill(self) -> bool:
        return self.spot_executed != self.perp_executed


# =============================================================================
# SNAPSHOT STORE (Abstract)
# =============================================================================


class SnapshotStore(ABC):
    """Abstract interface for snapshot storage."""
    
    @abstractmethod
    async def save_snapshot(self, key: str, snapshot: PositionSnapshot) -> bool:
        """Save a snapshot. Returns True on success."""
        pass
    
    @abstractmethod
    async def get_snapshot(self, key: str) -> Optional[PositionSnapshot]:
        """Retrieve a snapshot by key."""
        pass
    
    @abstractmethod
    async def delete_snapshot(self, key: str) -> bool:
        """Delete a snapshot after successful trade."""
        pass


# =============================================================================
# LOCAL CACHE (Development)
# =============================================================================


class LocalSnapshotStore(SnapshotStore):
    """In-memory snapshot store for development/testing."""
    
    def __init__(self):
        self._cache: Dict[str, PositionSnapshot] = {}
        self._ttl_seconds = 300  # 5 minute expiry
    
    async def save_snapshot(self, key: str, snapshot: PositionSnapshot) -> bool:
        self._cache[key] = snapshot
        Logger.debug(f"[SNAPSHOT] Saved: {key}")
        return True
    
    async def get_snapshot(self, key: str) -> Optional[PositionSnapshot]:
        snapshot = self._cache.get(key)
        if snapshot:
            age_ms = int(time.time() * 1000) - snapshot.timestamp_ms
            if age_ms > self._ttl_seconds * 1000:
                Logger.debug(f"[SNAPSHOT] Expired: {key}")
                del self._cache[key]
                return None
        return snapshot
    
    async def delete_snapshot(self, key: str) -> bool:
        if key in self._cache:
            del self._cache[key]
            Logger.debug(f"[SNAPSHOT] Deleted: {key}")
            return True
        return False


# =============================================================================
# REDIS STORE (Production)
# =============================================================================


class RedisSnapshotStore(SnapshotStore):
    """
    Redis-backed snapshot store for production.
    
    Provides:
    - Cross-instance visibility (multi-process safety)
    - Automatic TTL expiry
    - Fast K/V operations
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self._client = None
        self._ttl_seconds = 300  # 5 minute expiry
    
    async def _get_client(self):
        """Lazy-load Redis client."""
        if self._client is None:
            try:
                import redis.asyncio as redis
                self._client = redis.from_url(self.redis_url)
            except ImportError:
                Logger.warning("[SNAPSHOT] redis package not installed, using local cache")
                return None
        return self._client
    
    async def save_snapshot(self, key: str, snapshot: PositionSnapshot) -> bool:
        client = await self._get_client()
        if client is None:
            return False
        
        try:
            data = json.dumps(snapshot.to_dict())
            await client.setex(
                f"dnem:snapshot:{key}",
                self._ttl_seconds,
                data,
            )
            Logger.debug(f"[SNAPSHOT] Saved to Redis: {key}")
            return True
        except Exception as e:
            Logger.error(f"[SNAPSHOT] Redis save failed: {e}")
            return False
    
    async def get_snapshot(self, key: str) -> Optional[PositionSnapshot]:
        client = await self._get_client()
        if client is None:
            return None
        
        try:
            data = await client.get(f"dnem:snapshot:{key}")
            if data:
                return PositionSnapshot.from_dict(json.loads(data))
            return None
        except Exception as e:
            Logger.error(f"[SNAPSHOT] Redis get failed: {e}")
            return None
    
    async def delete_snapshot(self, key: str) -> bool:
        client = await self._get_client()
        if client is None:
            return False
        
        try:
            await client.delete(f"dnem:snapshot:{key}")
            return True
        except Exception:
            return False


# =============================================================================
# SNAPSHOT MANAGER
# =============================================================================


class SnapshotManager:
    """
    High-level interface for position snapshotting.
    
    Used by SyncExecution for partial fill protection.
    
    Example:
        >>> manager = SnapshotManager()
        >>> await manager.capture_pre_trade(wallet, drift, signal)
        >>> # ... execute bundle ...
        >>> analysis = await manager.analyze_post_trade(wallet, drift)
        >>> if analysis.needs_rollback:
        ...     # trigger emergency rollback
    """
    
    def __init__(self, use_redis: bool = False, redis_url: str = None):
        if use_redis and redis_url:
            self.store = RedisSnapshotStore(redis_url)
        else:
            self.store = LocalSnapshotStore()
        
        self._current_key: Optional[str] = None
    
    async def capture_pre_trade(
        self,
        wallet: Any,
        drift: Any,
        signal: Any,
        block_height: int = 0,
    ) -> str:
        """
        Capture position state before trade execution.
        
        Returns:
            Snapshot key for later retrieval
        """
        timestamp = int(time.time() * 1000)
        key = f"trade_{timestamp}"
        
        # Get current balances
        sol_balance = wallet.get_sol_balance() if hasattr(wallet, 'get_sol_balance') else 0
        usdc_balance = 0  # TODO: Get from wallet
        
        # Get current perp position
        perp_size = 0.0
        perp_entry = 0.0
        if drift and hasattr(drift, 'get_position'):
            pos = await drift.get_position("SOL-PERP")
            if pos:
                perp_size = pos.size
                perp_entry = pos.entry_price
        
        snapshot = PositionSnapshot(
            sol_balance=sol_balance,
            usdc_balance=usdc_balance,
            perp_size=perp_size,
            perp_entry_price=perp_entry,
            intended_spot_qty=signal.qty,
            intended_perp_qty=signal.qty,
            intended_direction=signal.direction.value if hasattr(signal.direction, 'value') else str(signal.direction),
            timestamp_ms=timestamp,
            block_height=block_height,
        )
        
        await self.store.save_snapshot(key, snapshot)
        self._current_key = key
        
        Logger.info(f"[SNAPSHOT] Pre-trade captured: SOL={sol_balance:.4f}, Perp={perp_size:.4f}")
        
        return key
    
    async def analyze_post_trade(
        self,
        wallet: Any,
        drift: Any,
        key: Optional[str] = None,
    ) -> Optional[RollbackAnalysis]:
        """
        Compare current state to pre-trade snapshot.
        
        Returns:
            RollbackAnalysis if snapshot found, None otherwise
        """
        key = key or self._current_key
        if not key:
            Logger.warning("[SNAPSHOT] No snapshot key for analysis")
            return None
        
        snapshot = await self.store.get_snapshot(key)
        if not snapshot:
            Logger.warning(f"[SNAPSHOT] Snapshot not found: {key}")
            return None
        
        # Get current state
        current_sol = wallet.get_sol_balance() if hasattr(wallet, 'get_sol_balance') else 0
        current_perp = 0.0
        if drift and hasattr(drift, 'get_position'):
            pos = await drift.get_position("SOL-PERP")
            if pos:
                current_perp = pos.size
        
        # Calculate deltas
        expected_sol = snapshot.expected_post_trade_sol()
        expected_perp = snapshot.expected_post_trade_perp()
        
        sol_delta = current_sol - expected_sol
        perp_delta = current_perp - expected_perp
        
        # Determine what executed
        tolerance = 0.001  # 0.001 SOL tolerance for dust
        spot_executed = abs(current_sol - snapshot.sol_balance) > tolerance
        perp_executed = abs(current_perp - snapshot.perp_size) > tolerance
        
        # Determine rollback action
        needs_rollback = spot_executed != perp_executed
        rollback_action = None
        rollback_qty = 0.0
        
        if needs_rollback:
            if spot_executed and not perp_executed:
                rollback_action = "CLOSE_SPOT"
                rollback_qty = abs(current_sol - snapshot.sol_balance)
                Logger.warning(f"[SNAPSHOT] PARTIAL: Spot executed, perp failed")
            elif perp_executed and not spot_executed:
                rollback_action = "CLOSE_PERP"
                rollback_qty = abs(current_perp - snapshot.perp_size)
                Logger.warning(f"[SNAPSHOT] PARTIAL: Perp executed, spot failed")
        
        analysis = RollbackAnalysis(
            spot_executed=spot_executed,
            perp_executed=perp_executed,
            spot_delta=sol_delta,
            perp_delta=perp_delta,
            needs_rollback=needs_rollback,
            rollback_action=rollback_action,
            rollback_qty=rollback_qty,
        )
        
        # Clean up snapshot after analysis
        await self.store.delete_snapshot(key)
        self._current_key = None
        
        return analysis
    
    async def mark_bundle_id(self, key: str, bundle_id: str) -> bool:
        """Update snapshot with bundle ID after submission."""
        snapshot = await self.store.get_snapshot(key)
        if snapshot:
            snapshot.bundle_id = bundle_id
            return await self.store.save_snapshot(key, snapshot)
        return False


# =============================================================================
# FACTORY
# =============================================================================


def create_snapshot_manager(use_redis: bool = False) -> SnapshotManager:
    """Factory for creating appropriate snapshot manager."""
    redis_url = None
    if use_redis:
        from config.settings import Settings
        redis_url = getattr(Settings, 'REDIS_URL', 'redis://localhost:6379')
    
    return SnapshotManager(use_redis=use_redis, redis_url=redis_url)
