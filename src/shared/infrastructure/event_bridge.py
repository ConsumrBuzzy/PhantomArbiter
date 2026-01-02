"""
Event Bridge - Core to Galaxy telemetry.

Non-blocking transmitter that buffers events and flushes to Galaxy.
Implements batching and circuit breaker for resilience.
"""

from __future__ import annotations

import asyncio
import time
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

from src.shared.system.logging import Logger
from src.shared.system.signal_bus import signal_bus, Signal, SignalType


class BridgeState(Enum):
    """Circuit breaker states."""
    CLOSED = "CLOSED"      # Normal operation
    OPEN = "OPEN"          # Galaxy is down, drop events
    HALF_OPEN = "HALF_OPEN"  # Testing if Galaxy is back


@dataclass
class EventBridgeConfig:
    """Configuration for EventBridge."""
    galaxy_url: str = "http://localhost:8001"
    batch_size: int = 50
    batch_timeout_ms: int = 100
    max_buffer_size: int = 500
    circuit_open_timeout: float = 30.0
    request_timeout: float = 0.5


class EventBridge:
    """
    Non-blocking event transmitter from Core to Galaxy.
    
    Features:
    - Batching: Collects events for batch_timeout_ms or until batch_size
    - Circuit Breaker: Drops events if Galaxy is unreachable
    - Async: Never blocks the trading hot-path
    """
    
    # Signal types to forward to Galaxy
    SUBSCRIBED_SIGNALS = [
        SignalType.MARKET_UPDATE,
        SignalType.NEW_TOKEN,
        SignalType.WHALE_ACTIVITY,
        SignalType.ARB_OPP,
        SignalType.MARKET_INTEL,
        SignalType.WHIFF_DETECTED,
        SignalType.SYSTEM_STATS,
        SignalType.LOG_UPDATE,
        SignalType.SCAN_UPDATE,
    ]
    
    def __init__(self, config: Optional[EventBridgeConfig] = None) -> None:
        self.config = config or EventBridgeConfig()
        self._buffer: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(
            maxsize=self.config.max_buffer_size
        )
        self._state = BridgeState.CLOSED
        self._last_failure: float = 0.0
        self._running = False
        self._flush_task: Optional[asyncio.Task] = None
        self._subscribed = False
        
        if httpx is None:
            Logger.warning("[EventBridge] httpx not installed - bridge disabled")
    
    def start(self) -> None:
        """Start the event bridge."""
        if self._running or httpx is None:
            return
        
        self._running = True
        self._subscribe_to_signals()
        self._flush_task = asyncio.create_task(self._flush_loop())
        Logger.info(f"[EventBridge] Started → {self.config.galaxy_url}")
    
    def stop(self) -> None:
        """Stop the event bridge."""
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
        Logger.info("[EventBridge] Stopped")
    
    def _subscribe_to_signals(self) -> None:
        """Subscribe to relevant SignalBus events."""
        if self._subscribed:
            return
        
        for signal_type in self.SUBSCRIBED_SIGNALS:
            signal_bus.subscribe(signal_type, self._on_signal)
        
        self._subscribed = True
        Logger.debug(f"[EventBridge] Subscribed to {len(self.SUBSCRIBED_SIGNALS)} signal types")
    
    async def _on_signal(self, signal: Signal) -> None:
        """Handle incoming signal - add to buffer."""
        if not self._running:
            return
        
        # Convert Signal to dict for transmission
        payload = self._signal_to_dict(signal)
        
        # Non-blocking put with overflow handling
        try:
            self._buffer.put_nowait(payload)
        except asyncio.QueueFull:
            # Buffer overflow - drop oldest events
            if self._state == BridgeState.OPEN:
                return  # Already dropping
            
            # Try to make room
            try:
                self._buffer.get_nowait()
                self._buffer.put_nowait(payload)
            except asyncio.QueueEmpty:
                pass
    
    async def _flush_loop(self) -> None:
        """Main loop - collect and flush batches."""
        Logger.debug("[EventBridge] Flush loop started")
        
        while self._running:
            try:
                # Check circuit breaker
                if self._state == BridgeState.OPEN:
                    elapsed = time.time() - self._last_failure
                    if elapsed >= self.config.circuit_open_timeout:
                        self._state = BridgeState.HALF_OPEN
                        Logger.info("[EventBridge] Circuit half-open, testing Galaxy...")
                    else:
                        # Drain buffer while circuit is open
                        await self._drain_buffer()
                        await asyncio.sleep(1.0)
                        continue
                
                # Collect batch
                batch = await self._collect_batch()
                
                if batch:
                    success = await self._send_batch(batch)
                    
                    if success:
                        if self._state == BridgeState.HALF_OPEN:
                            self._state = BridgeState.CLOSED
                            Logger.info("[EventBridge] Circuit closed, Galaxy is back")
                    else:
                        self._state = BridgeState.OPEN
                        self._last_failure = time.time()
                        Logger.warning("[EventBridge] Circuit opened, Galaxy unreachable")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                Logger.error(f"[EventBridge] Flush loop error: {e}")
                await asyncio.sleep(1.0)
        
        Logger.debug("[EventBridge] Flush loop stopped")
    
    async def _collect_batch(self) -> List[Dict[str, Any]]:
        """Collect events until batch_size or timeout."""
        batch: List[Dict[str, Any]] = []
        deadline = time.time() + (self.config.batch_timeout_ms / 1000)
        
        while len(batch) < self.config.batch_size:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            
            try:
                item = await asyncio.wait_for(
                    self._buffer.get(),
                    timeout=remaining
                )
                batch.append(item)
            except asyncio.TimeoutError:
                break
        
        return batch
    
    async def _send_batch(self, batch: List[Dict[str, Any]]) -> bool:
        """Send batch to Galaxy. Returns True on success."""
        if httpx is None:
            return False
        
        url = f"{self.config.galaxy_url}/api/v1/events"
        payload = {"events": batch}
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=payload,
                    timeout=self.config.request_timeout,
                )
                return response.status_code == 200
        except Exception:
            return False
    
    async def _drain_buffer(self) -> None:
        """Drain buffer when circuit is open."""
        drained = 0
        while not self._buffer.empty():
            try:
                self._buffer.get_nowait()
                drained += 1
            except asyncio.QueueEmpty:
                break
        
        if drained > 0:
            Logger.debug(f"[EventBridge] Drained {drained} events (circuit open)")
    
    @staticmethod
    def _signal_to_dict(signal: Signal) -> Dict[str, Any]:
        """Convert Signal to transmissible dict."""
        return {
            "type": signal.type.value if hasattr(signal.type, "value") else str(signal.type),
            "source": signal.source or "CORE",
            "timestamp": signal.timestamp,
            "data": signal.data,
        }


# Module-level convenience functions
_bridge: Optional[EventBridge] = None


def get_event_bridge(config: Optional[EventBridgeConfig] = None) -> EventBridge:
    """Get or create the global EventBridge instance."""
    global _bridge
    if _bridge is None:
        _bridge = EventBridge(config)
    return _bridge


def start_event_bridge(galaxy_url: str = "http://localhost:8001") -> EventBridge:
    """Start the event bridge with the given Galaxy URL."""
    config = EventBridgeConfig(galaxy_url=galaxy_url)
    bridge = get_event_bridge(config)
    bridge.start()
    return bridge


def stop_event_bridge() -> None:
    """Stop the global event bridge."""
    global _bridge
    if _bridge:
        _bridge.stop()
        _bridge = None
