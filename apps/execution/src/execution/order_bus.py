"""
Order Bus - Signal queue and execution routing.

Manages trade signals and routes to execution backends.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from enum import Enum


class SignalAction(str, Enum):
    """Trade signal actions."""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class SignalStatus(str, Enum):
    """Signal processing status."""
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    QUEUED = "QUEUED"
    EXECUTING = "EXECUTING"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class TradeSignal:
    """Trade signal from strategy."""
    symbol: str
    mint: str
    action: SignalAction
    size_usd: float
    reason: str = ""
    confidence: float = 0.5
    target_price: float = 0.0
    stop_loss: float = 0.0
    source: str = "UNKNOWN"
    
    # Generated fields
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    status: SignalStatus = SignalStatus.PENDING
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "symbol": self.symbol,
            "mint": self.mint,
            "action": self.action.value,
            "size_usd": self.size_usd,
            "reason": self.reason,
            "confidence": self.confidence,
            "target_price": self.target_price,
            "stop_loss": self.stop_loss,
            "source": self.source,
            "timestamp_ms": self.timestamp_ms,
            "status": self.status.value,
        }


@dataclass
class ExecutionResult:
    """Result of trade execution."""
    signal_id: str
    status: SignalStatus
    filled_amount: float = 0.0
    filled_price: float = 0.0
    slippage_pct: float = 0.0
    fees_usd: float = 0.0
    tx_signature: str = ""
    error: str = ""
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "signal_id": self.signal_id,
            "status": self.status.value,
            "filled_amount": self.filled_amount,
            "filled_price": self.filled_price,
            "slippage_pct": self.slippage_pct,
            "fees_usd": self.fees_usd,
            "tx_signature": self.tx_signature,
            "error": self.error,
            "timestamp_ms": self.timestamp_ms,
        }


class OrderBus:
    """
    Central order bus for signal processing.
    
    Queues signals, validates, and routes to execution backend.
    """
    
    def __init__(self, max_queue_size: int = 1000) -> None:
        self._queue: asyncio.Queue[TradeSignal] = asyncio.Queue(maxsize=max_queue_size)
        self._pending: Dict[str, TradeSignal] = {}
        self._history: List[TradeSignal] = []
        self._results: Dict[str, ExecutionResult] = {}
        self._result_callbacks: List[Callable[[ExecutionResult], Any]] = []
        self._lock = asyncio.Lock()
        self._running = False
        self._executor: Optional[Callable[[TradeSignal], ExecutionResult]] = None
        
        # Stats
        self._signals_received = 0
        self._signals_executed = 0
        self._signals_rejected = 0
    
    def set_executor(
        self, executor: Callable[[TradeSignal], ExecutionResult]
    ) -> None:
        """Set the execution backend."""
        self._executor = executor
    
    def subscribe_results(
        self, callback: Callable[[ExecutionResult], Any]
    ) -> None:
        """Subscribe to execution results."""
        self._result_callbacks.append(callback)
    
    async def submit(self, signal: TradeSignal) -> str:
        """
        Submit a trade signal.
        
        Returns signal ID or raises if rejected.
        """
        self._signals_received += 1
        
        # Validate signal
        if not self._validate(signal):
            signal.status = SignalStatus.REJECTED
            self._signals_rejected += 1
            raise ValueError(f"Invalid signal: {signal.symbol}")
        
        # Queue signal
        signal.status = SignalStatus.QUEUED
        await self._queue.put(signal)
        
        async with self._lock:
            self._pending[signal.id] = signal
        
        return signal.id
    
    async def get_result(self, signal_id: str) -> Optional[ExecutionResult]:
        """Get execution result for a signal."""
        return self._results.get(signal_id)
    
    async def start(self) -> None:
        """Start processing signals."""
        self._running = True
        asyncio.create_task(self._process_loop())
        print("📋 [OrderBus] Started signal processing")
    
    async def stop(self) -> None:
        """Stop processing signals."""
        self._running = False
        print("📋 [OrderBus] Stopped")
    
    async def _process_loop(self) -> None:
        """Main signal processing loop."""
        while self._running:
            try:
                signal = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=1.0
                )
                await self._execute(signal)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"⚠️ [OrderBus] Process error: {e}")
    
    async def _execute(self, signal: TradeSignal) -> None:
        """Execute a signal via the backend."""
        signal.status = SignalStatus.EXECUTING
        
        result: ExecutionResult
        
        if self._executor:
            try:
                result = await asyncio.to_thread(self._executor, signal)
            except Exception as e:
                result = ExecutionResult(
                    signal_id=signal.id,
                    status=SignalStatus.FAILED,
                    error=str(e),
                )
        else:
            # No executor - reject
            result = ExecutionResult(
                signal_id=signal.id,
                status=SignalStatus.FAILED,
                error="No execution backend configured",
            )
        
        # Update state
        signal.status = result.status
        self._signals_executed += 1
        
        async with self._lock:
            self._results[signal.id] = result
            if signal.id in self._pending:
                del self._pending[signal.id]
            self._history.append(signal)
            
            # Trim history
            if len(self._history) > 1000:
                self._history = self._history[-500:]
        
        # Notify subscribers
        for callback in self._result_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(result)
                else:
                    callback(result)
            except Exception:
                pass
    
    def _validate(self, signal: TradeSignal) -> bool:
        """Validate a signal before queueing."""
        if not signal.mint or len(signal.mint) < 10:
            return False
        if signal.size_usd <= 0:
            return False
        if signal.action == SignalAction.HOLD:
            return False
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Get order bus statistics."""
        return {
            "signals_received": self._signals_received,
            "signals_executed": self._signals_executed,
            "signals_rejected": self._signals_rejected,
            "queue_size": self._queue.qsize(),
            "pending_count": len(self._pending),
        }


# Global instance
_order_bus: Optional[OrderBus] = None


def get_order_bus() -> OrderBus:
    """Get or create the global OrderBus instance."""
    global _order_bus
    if _order_bus is None:
        _order_bus = OrderBus()
    return _order_bus
