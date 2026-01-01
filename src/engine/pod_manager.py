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
- P0 (Doer): TacticalStrategy only receives verified signals
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

    HOP = "hop"  # Multi-hop arbitrage
    CYCLE = "cycle"  # Market cycle detection
    PERFORMER = "performer"  # Individual token tracking
    SCOUT = "scout"  # Discovery and recon
    WHALE = "whale"  # V140: Bridge inflow sniffer
    EXECUTION = "execution"  # V140: The Striker (Bundle executor)


@dataclass
class PodSignal:
    """A signal emitted by a Pod."""

    pod_id: str
    pod_type: PodType
    signal_type: str  # "OPPORTUNITY", "WARNING", "INFO"
    priority: int  # 1-10, higher = more urgent
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
    priority_boost: int = 0  # Boost to signal priority
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

    def emit_signal(self, signal: PodSignal) -> None:
        """Emit a signal via the callback."""
        self.total_signals += 1
        self.signals_this_minute += 1
        if self.signal_callback:
            self.signal_callback(signal)
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
        start_token: str = None,
    ):
        super().__init__(config, signal_callback)

        from config.settings import Settings

        self.start_token = start_token or getattr(
            Settings, "SOL_MINT", "So11111111111111111111111111111111111111112"
        )

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

            min_hops = self.config.params.get("min_hops", 2)
            max_hops = self.config.params.get("max_hops", 5)
            min_liquidity = self.config.params.get("min_liquidity_usd", 5000)

            self._scanner = MultiverseScanner(
                min_hops=min_hops, max_hops=max_hops, min_liquidity_usd=min_liquidity
            )
            self._graph = HopGraph()

            Logger.info(
                f"[HopPod] Rust engine initialized ({min_hops}-{max_hops} hops)"
            )
        except ImportError:
            Logger.warning("[HopPod] Rust engine not available - using fallback mode")

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
                    dex=pool.get("dex", "UNKNOWN"),
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

                signals.append(
                    PodSignal(
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
                            "cycles_by_hops": {
                                k: len(v) for k, v in result.cycles_by_hops.items()
                            },
                        },
                    )
                )

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


class CyclePod(BasePod):
    """
    The "Governor of Wisdom" - monitors global market conditions.

    CyclePod doesn't find trades; it finds Market Context. It provides
    intelligence to all other pods about when conditions favor trading
    and when they don't.

    Responsibilities:
    1. Jito Pulse: Monitor tip prices for congestion detection
    2. Sector Rotation: Track volume flow between asset classes
    3. Volatility Index: Calculate a "Solana VIX" equivalent
    4. Global Bias: Adjust profit thresholds across all pods
    """

    def __init__(self, config: PodConfig, signal_callback: Callable[[PodSignal], None]):
        super().__init__(config, signal_callback)

        # Market context singleton
        from src.shared.models.context import get_market_context

        self._context = get_market_context()

        # Historical tracking for trend detection
        self._tip_history: List[int] = []
        self._volume_history: List[float] = []
        self._max_history = 60  # 1 minute at 1Hz

        # Alert state (to avoid spamming)
        self._last_congestion_alert: float = 0
        self._alert_cooldown = 30.0  # seconds

        # Stats
        self.alerts_sent: int = 0
        self.congestion_events: int = 0
        self.sector_changes: int = 0

        Logger.info("[CyclePod] Initialized - Governor of Wisdom active")

    async def _scan(self) -> List[PodSignal]:
        """
        Update market context and emit alerts if conditions change significantly.
        """
        signals = []

        try:
            # 1. Update Jito metrics
            await self._update_jito_metrics()

            # 2. Update volume/sector metrics
            await self._update_volume_metrics()

            # 3. Update volatility index
            await self._update_volatility_metrics()

            # 4. Derive global state
            self._update_global_state()

            # 5. Check for alert conditions
            alert_signals = self._check_alert_conditions()
            signals.extend(alert_signals)

            # 6. Always emit context update for other systems
            signals.append(
                PodSignal(
                    pod_id=self.id,
                    pod_type=PodType.CYCLE,
                    signal_type="CONTEXT_UPDATE",
                    priority=3,  # Low priority, just informational
                    data=self._context.get_dashboard_summary(),
                )
            )

        except Exception as e:
            Logger.debug(f"[CyclePod] Scan error: {e}")

        return signals

    async def _update_jito_metrics(self) -> None:
        """Update Jito tip tracking from congestion monitor."""
        try:
            from src.strategies.components.congestion_monitor import get_congestion_monitor

            monitor = get_congestion_monitor()

            if monitor:
                status = monitor.get_status()
                current_tip = status.get("tip_lamports", 10_000)

                # Track history
                self._tip_history.append(current_tip)
                if len(self._tip_history) > self._max_history:
                    self._tip_history = self._tip_history[-self._max_history :]

                # Calculate percentiles from history
                if len(self._tip_history) >= 10:
                    sorted_tips = sorted(self._tip_history)
                    self._context.jito.p5_tip_lamports = sorted_tips[
                        len(sorted_tips) // 20
                    ]
                    self._context.jito.p50_tip_lamports = sorted_tips[
                        len(sorted_tips) // 2
                    ]
                    self._context.jito.p95_tip_lamports = sorted_tips[
                        int(len(sorted_tips) * 0.95)
                    ]

                # Calculate velocity (rate of change)
                if len(self._tip_history) >= 5:
                    recent = self._tip_history[-5:]
                    velocity = (recent[-1] - recent[0]) / 5
                    self._context.jito.tip_velocity = velocity

                self._context.jito.current_tip_lamports = current_tip
                self._context.jito.sample_count = len(self._tip_history)
                self._context.jito.last_update = time.time()

        except Exception as e:
            Logger.debug(f"[CyclePod] Jito update error: {e}")

    async def _update_volume_metrics(self) -> None:
        """Update DEX volume and sector flow tracking."""
        # TODO: Integrate with real volume data from RPC/WSS
        # For now, use placeholder logic based on price cache activity
        try:
            from src.core.shared_cache import SharedPriceCache

            # Count recent price updates as a proxy for volume activity
            updates = getattr(SharedPriceCache, "_update_count", 0)
            self._volume_history.append(float(updates))
            if len(self._volume_history) > self._max_history:
                self._volume_history = self._volume_history[-self._max_history :]

            # Estimate total volume from update frequency
            if len(self._volume_history) >= 2:
                delta = self._volume_history[-1] - self._volume_history[-2]
                self._context.volume.total_volume_1h = delta * 1000  # Rough estimate

            self._context.volume.last_update = time.time()

        except Exception as e:
            Logger.debug(f"[CyclePod] Volume update error: {e}")

    async def _update_volatility_metrics(self) -> None:
        """Calculate volatility index (Solana VIX equivalent)."""
        try:
            # Use tip velocity + update frequency as volatility proxy
            tip_velocity = abs(self._context.jito.tip_velocity)
            tip_factor = min(tip_velocity / 1000, 50)  # Cap at 50 points

            # Update frequency contribution
            if len(self._volume_history) >= 2:
                update_rate = (
                    self._volume_history[-1]
                    - self._volume_history[max(0, len(self._volume_history) - 10)]
                )
                freq_factor = min(update_rate / 10, 30)  # Cap at 30 points
            else:
                freq_factor = 10

            # Base + factors = VIX
            base_vix = 20
            self._context.volatility.volatility_index = min(
                base_vix + tip_factor + freq_factor, 100
            )

            # Update frequency tracking
            self._context.volatility.update_frequency_hz = len(
                self._volume_history
            ) / max(1, self._max_history)

        except Exception as e:
            Logger.debug(f"[CyclePod] Volatility update error: {e}")

    def _update_global_state(self) -> None:
        """Derive global trading state from metrics."""
        from src.shared.models.context import CongestionLevel

        jito = self._context.jito

        # Determine congestion level
        old_level = self._context.congestion_level
        if jito.current_tip_lamports > jito.p95_tip_lamports * 2:
            self._context.congestion_level = CongestionLevel.EXTREME
        elif jito.current_tip_lamports > jito.p95_tip_lamports:
            self._context.congestion_level = CongestionLevel.HIGH
        elif jito.current_tip_lamports > jito.p50_tip_lamports * 1.5:
            self._context.congestion_level = CongestionLevel.MODERATE
        else:
            self._context.congestion_level = CongestionLevel.LOW

        # Track congestion events
        if old_level != self._context.congestion_level:
            if self._context.congestion_level in [
                CongestionLevel.HIGH,
                CongestionLevel.EXTREME,
            ]:
                self.congestion_events += 1

        # Calculate global profit adjustment based on congestion
        adj_map = {
            CongestionLevel.LOW: 0.0,
            CongestionLevel.MODERATE: 0.05,
            CongestionLevel.HIGH: 0.15,
            CongestionLevel.EXTREME: 0.30,
        }
        self._context.global_min_profit_adj = adj_map.get(
            self._context.congestion_level, 0.0
        )

        # Adjust scan cooldown for high congestion
        if self._context.congestion_level == CongestionLevel.EXTREME:
            self._context.hop_cooldown_multiplier = 3.0
            self._context.trading_enabled = False
            self._context.reason = "Extreme network congestion"
        elif self._context.congestion_level == CongestionLevel.HIGH:
            self._context.hop_cooldown_multiplier = 2.0
            self._context.trading_enabled = True
        else:
            self._context.hop_cooldown_multiplier = 1.0
            self._context.trading_enabled = True
            self._context.reason = ""

        # Update timestamp
        self._context.last_update = time.time()
        self._context.update_count += 1

    def _check_alert_conditions(self) -> List[PodSignal]:
        """Check for conditions that warrant alerts."""
        signals = []
        now = time.time()

        from src.shared.models.context import CongestionLevel

        # Congestion alert (rate limited)
        if self._context.congestion_level in [
            CongestionLevel.HIGH,
            CongestionLevel.EXTREME,
        ]:
            if now - self._last_congestion_alert > self._alert_cooldown:
                self._last_congestion_alert = now
                self.alerts_sent += 1

                signals.append(
                    PodSignal(
                        pod_id=self.id,
                        pod_type=PodType.CYCLE,
                        signal_type="CONGESTION_ALERT",
                        priority=8,
                        data={
                            "level": self._context.congestion_level.value,
                            "jito_tip": self._context.jito.current_tip_lamports,
                            "p50_tip": self._context.jito.p50_tip_lamports,
                            "p95_tip": self._context.jito.p95_tip_lamports,
                            "profit_adj": self._context.global_min_profit_adj,
                            "trading_enabled": self._context.trading_enabled,
                            "message": f"Network congestion {self._context.congestion_level.value.upper()}: "
                            f"Raising profit thresholds by {self._context.global_min_profit_adj:.2f}%",
                        },
                    )
                )

        # VIX spike alert
        if self._context.volatility.volatility_index > 75:
            signals.append(
                PodSignal(
                    pod_id=self.id,
                    pod_type=PodType.CYCLE,
                    signal_type="VOLATILITY_ALERT",
                    priority=6,
                    data={
                        "vix": self._context.volatility.volatility_index,
                        "label": self._context.volatility.get_vix_label(),
                        "message": f"High volatility detected: VIX {self._context.volatility.volatility_index:.0f}",
                    },
                )
            )

        return signals

    def get_stats(self) -> Dict[str, Any]:
        """Get CyclePod statistics."""
        return {
            "pod_id": self.id,
            "pod_type": "cycle",
            "status": self.status.value,
            "total_scans": self.total_scans,
            "total_signals": self.total_signals,
            "alerts_sent": self.alerts_sent,
            "congestion_events": self.congestion_events,
            "sector_changes": self.sector_changes,
            "uptime_seconds": time.time() - self.created_at,
            "context": self._context.get_dashboard_summary(),
        }

    def get_context(self):
        """Get the current market context."""
        return self._context


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
        cooldown: float = 2.0,
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
            cooldown_seconds=cooldown,
        )

        pod = HopPod(config, self.signal_callback, start_token)
        self.pods[pod.id] = pod

        Logger.info(f"[PodManager] Spawned HopPod: {pod.id} ({name})")
        return pod

    def spawn_cycle_pod(
        self, name: str = "market_governor", cooldown: float = 1.0
    ) -> Optional[CyclePod]:
        """
        Spawn the CyclePod (Governor of Wisdom).

        Only one CyclePod should exist - it's a singleton that provides
        global market context to all other pods.

        Args:
            name: Human-readable name for the pod
            cooldown: Seconds between context updates

        Returns:
            The created CyclePod, or existing one if already spawned
        """
        # Check if we already have a CyclePod
        for pod in self.pods.values():
            if isinstance(pod, CyclePod):
                Logger.debug(f"[PodManager] CyclePod already exists: {pod.id}")
                return pod

        config = PodConfig(
            pod_type=PodType.CYCLE,
            name=name,
            params={},
            cooldown_seconds=cooldown,
            max_signals_per_minute=30,  # Higher limit for context updates
        )

        pod = CyclePod(config, self.signal_callback)
        self.pods[pod.id] = pod

        Logger.info(f"[PodManager] Spawned CyclePod: {pod.id} (Governor of Wisdom)")
        return pod

    def get_cycle_pod(self) -> Optional[CyclePod]:
        """Get the singleton CyclePod if it exists."""
        for pod in self.pods.values():
            if isinstance(pod, CyclePod):
                return pod
        return None

    def spawn_execution_pod(
        self,
        name: str = "striker",
        mode: str = "paper",
        min_profit_pct: float = 0.15,
        cooldown: float = 0.5,
    ):
        """
        Spawn the ExecutionPod (The Striker).

        Only one ExecutionPod should exist - it processes all
        HOP_OPPORTUNITY signals from the queue.

        Args:
            name: Human-readable name for the pod
            mode: "paper", "live", or "disabled"
            min_profit_pct: Minimum profit % to execute
            cooldown: Seconds between execution checks

        Returns:
            The created ExecutionPod, or existing one if already spawned
        """
        from src.engine.execution_pod import ExecutionPod, ExecutionMode

        # Check if we already have an ExecutionPod
        for pod in self.pods.values():
            if isinstance(pod, ExecutionPod):
                Logger.debug(f"[PodManager] ExecutionPod already exists: {pod.id}")
                return pod

        # Map string mode to enum
        mode_map = {
            "paper": ExecutionMode.PAPER,
            "ghost": ExecutionMode.GHOST,  # V140: Added Ghost Mode
            "live": ExecutionMode.LIVE,
            "disabled": ExecutionMode.DISABLED,
        }
        exec_mode = mode_map.get(mode.lower(), ExecutionMode.PAPER)

        config = PodConfig(
            pod_type=PodType.EXECUTION,  # V140: Correct type for Execution
            name=name,
            params={
                "min_profit_pct": min_profit_pct,
            },
            cooldown_seconds=cooldown,
            max_signals_per_minute=60,  # Higher limit for execution results
        )

        pod = ExecutionPod(
            config=config,
            signal_callback=self.signal_callback,
            mode=exec_mode,
            min_profit_pct=min_profit_pct,
        )
        self.pods[pod.id] = pod

        Logger.info(f"[PodManager] Spawned ExecutionPod: {pod.id} (mode={mode})")
        return pod

    def get_execution_pod(self):
        """Get the singleton ExecutionPod if it exists."""
        from src.engine.execution_pod import ExecutionPod

        for pod in self.pods.values():
            if isinstance(pod, ExecutionPod):
                return pod
        return None

    def spawn_bridge_pod(
        self,
        name: str = "sniffer",
        whale_threshold: float = 250_000.0,
        cooldown: float = 10.0,
    ):
        """
        Spawn the BridgePod (The Sniffer).

        Args:
            name: Human-readable name
            whale_threshold: USD inflow to trigger whale signals
            cooldown: Seconds between aggregation cycles
        """
        from src.engine.bridge_pod import BridgePod

        # Singleton check
        pod = self.get_bridge_pod()
        if pod:
            return pod

        config = PodConfig(
            pod_type=PodType.WHALE,
            name=name,
            params={"whale_threshold": whale_threshold},
            cooldown_seconds=cooldown,
        )

        pod = BridgePod(
            config=config,
            signal_callback=self.signal_callback,
            whale_threshold_usd=whale_threshold,
        )
        self.pods[pod.id] = pod

        Logger.info(f"[PodManager] Spawned BridgePod: {pod.id}")
        return pod

    def get_bridge_pod(self) -> Optional[BridgePod]:
        """Get the singleton BridgePod if it exists."""
        from src.engine.bridge_pod import BridgePod

        for pod in self.pods.values():
            if isinstance(pod, BridgePod):
                return pod
        return None

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
