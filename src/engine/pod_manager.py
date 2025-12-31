"""
Smart Pod System - Autonomous Trading Units
============================================
V140: Narrow Path Infrastructure (Phase 3)

Pods are isolated, autonomous logic containers that specialize in specific
trading tasks. Instead of a monolithic scanner, each Pod handles its own
domain and broadcasts signals when opportunities arise.

Pod Types:
- HopPod: Multi-hop arbitrage pathfinding (SOL→A→B→SOL)
- CyclePod: Market cycle detection (congestion, volatility phases)
- PerformerPod: Individual token tracking with TSL logic

Architecture:
- P0 (Doer): TradingCore only receives verified signals
- P1 (Thinker): Pods live here, doing specialized analysis
- P2 (Helper): DiscoveryDaemon spawns new pods based on Scout input
"""

from __future__ import annotations

import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime

from src.shared.system.logging import Logger


class PodStatus(Enum):
    """Lifecycle status of a Pod."""
    INITIALIZING = "initializing"
    ACTIVE = "active"
    PAUSED = "paused"
    COOLDOWN = "cooldown"
    TERMINATED = "terminated"


class PodType(Enum):
    """Classification of Pod types."""
    HOP = "hop"           # Multi-hop arbitrage
    CYCLE = "cycle"       # Market cycle detection
    PERFORMER = "performer"  # Individual token tracking
    SCOUT = "scout"       # Discovery and recon


@dataclass
class PodSignal:
    """A signal emitted by a Pod."""
    pod_id: str
    pod_type: PodType
    signal_type: str          # "OPPORTUNITY", "WARNING", "INFO"
    priority: int             # 1-10, higher = more urgent
    data: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    
    def __repr__(self) -> str:
        return f"PodSignal({self.pod_type.value}:{self.signal_type} P{self.priority})"


@dataclass
class PodConfig:
    """Configuration for a Pod instance."""
    pod_type: PodType
    name: str
    params: Dict[str, Any] = field(default_factory=dict)
    priority_boost: int = 0    # Boost to signal priority
    max_signals_per_minute: int = 10
    cooldown_seconds: float = 5.0


class BasePod(ABC):
    """
    Abstract base class for all Pods.
    
    Pods are autonomous units that:
    1. Run their own analysis loop
    2. Emit signals when opportunities are found
    3. Can be paused/resumed/terminated by PodManager
    """
    
    def __init__(self, config: PodConfig, signal_callback: Callable[[PodSignal], None]):
        self.id = f"{config.pod_type.value}_{uuid.uuid4().hex[:8]}"
        self.config = config
        self.status = PodStatus.INITIALIZING
        self.signal_callback = signal_callback
        
        # Metrics
        self.created_at = time.time()
        self.last_scan_at: float = 0
        self.total_scans: int = 0
        self.total_signals: int = 0
        self.signals_this_minute: int = 0
        self._minute_start: float = time.time()
        
        # Control
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        
        Logger.debug(f"[Pod] Created {self.id} ({config.name})")
    
    @abstractmethod
    async def _scan(self) -> List[PodSignal]:
        """
        Perform one scan cycle. Override in subclasses.
        
        Returns:
            List of signals to emit (can be empty)
        """
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Get pod-specific statistics."""
        pass
    
    async def start(self) -> None:
        """Start the pod's scan loop."""
        self.status = PodStatus.ACTIVE
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop())
        Logger.info(f"[Pod] Started {self.id}")
    
    async def stop(self) -> None:
        """Stop the pod gracefully."""
        self._stop_event.set()
        self.status = PodStatus.TERMINATED
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        Logger.info(f"[Pod] Stopped {self.id}")
    
    def pause(self) -> None:
        """Pause the pod temporarily."""
        self.status = PodStatus.PAUSED
        Logger.debug(f"[Pod] Paused {self.id}")
    
    def resume(self) -> None:
        """Resume a paused pod."""
        if self.status == PodStatus.PAUSED:
            self.status = PodStatus.ACTIVE
            Logger.debug(f"[Pod] Resumed {self.id}")
    
    async def _run_loop(self) -> None:
        """Main pod loop."""
        while not self._stop_event.is_set():
            if self.status != PodStatus.ACTIVE:
                await asyncio.sleep(0.5)
                continue
            
            try:
                # Rate limiting check
                if not self._check_rate_limit():
                    await asyncio.sleep(1.0)
                    continue
                
                # Run scan
                signals = await self._scan()
                self.last_scan_at = time.time()
                self.total_scans += 1
                
                # Emit signals
                for signal in signals:
                    if self._check_rate_limit():
                        self._emit_signal(signal)
                
                # Cooldown
                await asyncio.sleep(self.config.cooldown_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                Logger.error(f"[Pod] {self.id} error: {e}")
                await asyncio.sleep(5.0)  # Back off on error
    
    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits."""
        now = time.time()
        if now - self._minute_start > 60:
            self._minute_start = now
            self.signals_this_minute = 0
        return self.signals_this_minute < self.config.max_signals_per_minute
    
    def _emit_signal(self, signal: PodSignal) -> None:
        """Emit a signal to the callback."""
        signal.priority += self.config.priority_boost
        self.signal_callback(signal)
        self.total_signals += 1
        self.signals_this_minute += 1


class HopPod(BasePod):
    """
    A Pod specialized in multi-hop arbitrage pathfinding.
    
    Each HopPod is dedicated to exploring paths starting from a specific
    token (usually SOL) and uses the Rust MultiverseScanner for efficient
    cycle detection across 2-5 hop ranges.
    """
    
    def __init__(
        self,
        config: PodConfig,
        signal_callback: Callable[[PodSignal], None],
        start_token: str = None
    ):
        super().__init__(config, signal_callback)
        
        from config.settings import Settings
        
        self.start_token = start_token or getattr(Settings, 'SOL_MINT', 
            "So11111111111111111111111111111111111111112")
        
        # Try to get Rust engine - graceful fallback if not available
        self._scanner = None
        self._graph = None
        self._init_rust_engine()
        
        # Stats
        self.cycles_found: int = 0
        self.best_profit_ever: float = 0.0
        self.last_best_cycle: Optional[Dict] = None
    
    def _init_rust_engine(self) -> None:
        """Initialize the Rust multiverse scanner."""
        try:
            from phantom_core import MultiverseScanner, HopGraph
            
            min_hops = self.config.params.get('min_hops', 2)
            max_hops = self.config.params.get('max_hops', 5)
            min_liquidity = self.config.params.get('min_liquidity_usd', 5000)
            
            self._scanner = MultiverseScanner(
                min_hops=min_hops,
                max_hops=max_hops,
                min_liquidity_usd=min_liquidity
            )
            self._graph = HopGraph()
            
            Logger.info(f"[HopPod] Rust engine initialized ({min_hops}-{max_hops} hops)")
        except ImportError:
            Logger.warning(f"[HopPod] Rust engine not available - using fallback mode")
    
    def update_graph(self, pool_updates: List[Dict[str, Any]]) -> int:
        """
        Update the graph with new pool data.
        
        Args:
            pool_updates: List of pool data dicts from WSS/RPC
            
        Returns:
            Number of successful updates
        """
        if not self._graph:
            return 0
        
        from phantom_core import PoolEdge
        
        updated = 0
        for pool in pool_updates:
            try:
                edge = PoolEdge(
                    source_mint=pool.get("base_mint", ""),
                    target_mint=pool.get("quote_mint", ""),
                    pool_address=pool.get("pool_address", ""),
                    exchange_rate=pool.get("price", 0.0),
                    fee_bps=pool.get("fee_bps", 25),
                    liquidity_usd=int(pool.get("liquidity_usd", 0)),
                    last_update_slot=pool.get("slot", 0),
                    dex=pool.get("dex", "UNKNOWN")
                )
                self._graph.update_edge(edge)
                updated += 1
            except Exception:
                pass
        
        return updated
    
    async def _scan(self) -> List[PodSignal]:
        """Scan for profitable multiverse cycles."""
        if not self._scanner or not self._graph:
            return []
        
        signals = []
        
        try:
            # Run multiverse scan
            result = self._scanner.scan_multiverse(self._graph, self.start_token)
            
            if result.best_cycle:
                best = result.best_cycle
                self.cycles_found += result.scan_stats.total_cycles_found
                
                # Track best ever
                if best.profit_pct > self.best_profit_ever:
                    self.best_profit_ever = best.profit_pct
                    self.last_best_cycle = {
                        "path": best.path,
                        "pools": best.pool_addresses,
                        "profit_pct": best.profit_pct,
                        "hop_count": best.hop_count,
                        "min_liquidity": best.min_liquidity_usd,
                        "dexes": best.dexes,
                    }
                
                # Emit signal for best cycle
                priority = self._calculate_priority(best)
                
                signals.append(PodSignal(
                    pod_id=self.id,
                    pod_type=PodType.HOP,
                    signal_type="OPPORTUNITY",
                    priority=priority,
                    data={
                        "path": best.path,
                        "pools": best.pool_addresses,
                        "profit_pct": best.profit_pct,
                        "hop_count": best.hop_count,
                        "min_liquidity_usd": best.min_liquidity_usd,
                        "total_fee_bps": best.total_fee_bps,
                        "dexes": best.dexes,
                        "estimated_gas": best.estimated_gas_lamports,
                        "scan_time_ms": result.scan_stats.scan_time_ms,
                        "cycles_by_hops": {k: len(v) for k, v in result.cycles_by_hops.items()},
                    }
                ))
                
        except Exception as e:
            Logger.debug(f"[HopPod] Scan error: {e}")
        
        return signals
    
    def _calculate_priority(self, cycle) -> int:
        """Calculate signal priority based on cycle quality."""
        priority = 5  # Base
        
        # Profit boost
        if cycle.profit_pct > 1.0:
            priority += 3
        elif cycle.profit_pct > 0.5:
            priority += 2
        elif cycle.profit_pct > 0.2:
            priority += 1
        
        # 4-hop alpha zone boost
        if cycle.hop_count == 4:
            priority += 1
        
        # High liquidity boost
        if cycle.min_liquidity_usd > 100_000:
            priority += 1
        
        return min(priority, 10)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get HopPod statistics."""
        graph_stats = {}
        if self._graph:
            graph_stats = {
                "node_count": self._graph.node_count(),
                "edge_count": self._graph.edge_count(),
            }
        
        return {
            "pod_id": self.id,
            "pod_type": "hop",
            "status": self.status.value,
            "start_token": self.start_token[:8] + "...",
            "total_scans": self.total_scans,
            "total_signals": self.total_signals,
            "cycles_found": self.cycles_found,
            "best_profit_ever": self.best_profit_ever,
            "last_best_cycle": self.last_best_cycle,
            "uptime_seconds": time.time() - self.created_at,
            **graph_stats,
        }


class PodManager:
    """
    Manages the lifecycle of all Pods in the system.
    
    Responsibilities:
    - Spawn pods based on configuration or Scout input
    - Terminate pods based on performance or resource constraints
    - Route pod signals to the SignalBus
    - Provide pod metrics for dashboard
    """
    
    def __init__(self, signal_callback: Callable[[PodSignal], None] = None):
        self.pods: Dict[str, BasePod] = {}
        self.signal_callback = signal_callback or self._default_signal_handler
        self._signal_queue: List[PodSignal] = []
        
        # Limits
        self.max_pods = 50
        self.max_hop_pods = 10
        self.max_performer_pods = 30
        
        Logger.info("[PodManager] Initialized")
    
    def _default_signal_handler(self, signal: PodSignal) -> None:
        """Default signal handler - queues signals."""
        self._signal_queue.append(signal)
        if len(self._signal_queue) > 1000:
            self._signal_queue = self._signal_queue[-500:]  # Trim
    
    def spawn_hop_pod(
        self,
        name: str = "default_hop",
        start_token: str = None,
        min_hops: int = 2,
        max_hops: int = 5,
        min_liquidity: int = 5000,
        cooldown: float = 2.0
    ) -> Optional[HopPod]:
        """
        Spawn a new HopPod for multi-hop arbitrage.
        
        Args:
            name: Human-readable name for the pod
            start_token: Token mint to start cycles from (default: SOL)
            min_hops: Minimum hop count (2-5)
            max_hops: Maximum hop count (2-5)
            min_liquidity: Minimum pool liquidity in USD
            cooldown: Seconds between scans
            
        Returns:
            The created HopPod, or None if limits exceeded
        """
        # Check limits
        hop_count = sum(1 for p in self.pods.values() if isinstance(p, HopPod))
        if hop_count >= self.max_hop_pods:
            Logger.warning(f"[PodManager] HopPod limit reached ({self.max_hop_pods})")
            return None
        
        if len(self.pods) >= self.max_pods:
            Logger.warning(f"[PodManager] Total pod limit reached ({self.max_pods})")
            return None
        
        config = PodConfig(
            pod_type=PodType.HOP,
            name=name,
            params={
                "min_hops": min_hops,
                "max_hops": max_hops,
                "min_liquidity_usd": min_liquidity,
            },
            cooldown_seconds=cooldown
        )
        
        pod = HopPod(config, self.signal_callback, start_token)
        self.pods[pod.id] = pod
        
        Logger.info(f"[PodManager] Spawned HopPod: {pod.id} ({name})")
        return pod
    
    async def start_all(self) -> None:
        """Start all pods."""
        for pod in self.pods.values():
            await pod.start()
    
    async def stop_all(self) -> None:
        """Stop all pods gracefully."""
        for pod in self.pods.values():
            await pod.stop()
        self.pods.clear()
        Logger.info("[PodManager] All pods stopped")
    
    async def terminate_pod(self, pod_id: str) -> bool:
        """Terminate a specific pod."""
        if pod_id not in self.pods:
            return False
        
        pod = self.pods[pod_id]
        await pod.stop()
        del self.pods[pod_id]
        Logger.info(f"[PodManager] Terminated {pod_id}")
        return True
    
    def get_pod(self, pod_id: str) -> Optional[BasePod]:
        """Get a pod by ID."""
        return self.pods.get(pod_id)
    
    def get_hop_pods(self) -> List[HopPod]:
        """Get all HopPods."""
        return [p for p in self.pods.values() if isinstance(p, HopPod)]
    
    def get_signals(self, clear: bool = True) -> List[PodSignal]:
        """
        Get queued signals.
        
        Args:
            clear: Whether to clear the queue after retrieval
            
        Returns:
            List of PodSignals sorted by priority (descending)
        """
        signals = sorted(self._signal_queue, key=lambda s: s.priority, reverse=True)
        if clear:
            self._signal_queue.clear()
        return signals
    
    def get_stats(self) -> Dict[str, Any]:
        """Get aggregate pod statistics."""
        hop_pods = self.get_hop_pods()
        
        return {
            "total_pods": len(self.pods),
            "hop_pods": len(hop_pods),
            "queued_signals": len(self._signal_queue),
            "total_scans": sum(p.total_scans for p in self.pods.values()),
            "total_signals": sum(p.total_signals for p in self.pods.values()),
            "pods": [p.get_stats() for p in self.pods.values()],
        }


# ═══════════════════════════════════════════════════════════════════════════
# SINGLETON FACTORY
# ═══════════════════════════════════════════════════════════════════════════

_pod_manager: Optional[PodManager] = None

def get_pod_manager() -> PodManager:
    """Get or create the singleton PodManager."""
    global _pod_manager
    if _pod_manager is None:
        _pod_manager = PodManager()
    return _pod_manager


def reset_pod_manager() -> None:
    """Reset the singleton (for testing)."""
    global _pod_manager
    if _pod_manager:
        asyncio.create_task(_pod_manager.stop_all())
    _pod_manager = None
