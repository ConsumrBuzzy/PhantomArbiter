"""
Mock Signal Bus
===============
Captures emitted signals for test assertions.
"""

from typing import List, Dict, Any, Callable, Optional
from dataclasses import dataclass, field
from enum import Enum
import time


@dataclass
class CapturedSignal:
    """A signal captured during testing."""
    signal_type: Any
    data: Any
    timestamp: float = field(default_factory=time.time)


class MockSignalBus:
    """
    Test double for SignalBus that captures all emissions.
    
    Usage:
        bus = MockSignalBus()
        bus.emit(SignalType.ARB_OPP, {"spread": 1.5})
        
        assert len(bus.captured) == 1
        assert bus.captured[0].data["spread"] == 1.5
    """
    
    def __init__(self):
        self.captured: List[CapturedSignal] = []
        self._subscribers: Dict[Any, List[Callable]] = {}
        
    def emit(self, signal_type: Any, data: Any = None):
        """Emit a signal, capturing it for assertions."""
        self.captured.append(CapturedSignal(
            signal_type=signal_type,
            data=data
        ))
        
        # Also call subscribers (for integration tests)
        if signal_type in self._subscribers:
            for callback in self._subscribers[signal_type]:
                try:
                    callback(data)
                except Exception:
                    pass
                    
    def subscribe(self, signal_type: Any, callback: Callable):
        """Subscribe to a signal type."""
        if signal_type not in self._subscribers:
            self._subscribers[signal_type] = []
        self._subscribers[signal_type].append(callback)
        
    def unsubscribe(self, signal_type: Any, callback: Callable):
        """Unsubscribe from a signal type."""
        if signal_type in self._subscribers:
            self._subscribers[signal_type] = [
                cb for cb in self._subscribers[signal_type] 
                if cb != callback
            ]
            
    def clear(self):
        """Clear all captured signals."""
        self.captured.clear()
        
    def get_by_type(self, signal_type: Any) -> List[CapturedSignal]:
        """Get all captured signals of a specific type."""
        return [s for s in self.captured if s.signal_type == signal_type]
        
    def assert_emitted(self, signal_type: Any, count: int = None, data_contains: Dict[str, Any] = None):
        """
        Assert that a signal was emitted.
        
        Args:
            signal_type: Expected signal type
            count: Optional expected count
            data_contains: Optional dict of expected data fields
            
        Raises:
            AssertionError if conditions not met
        """
        matching = self.get_by_type(signal_type)
        
        if count is not None:
            assert len(matching) == count, (
                f"Expected {count} {signal_type} signals, got {len(matching)}"
            )
        else:
            assert len(matching) > 0, f"No {signal_type} signals emitted"
            
        if data_contains:
            for signal in matching:
                if isinstance(signal.data, dict):
                    for key, value in data_contains.items():
                        assert key in signal.data, f"Key '{key}' not in signal data"
                        assert signal.data[key] == value, (
                            f"Expected {key}={value}, got {signal.data[key]}"
                        )
                        
    def assert_not_emitted(self, signal_type: Any):
        """Assert that a signal type was NOT emitted."""
        matching = self.get_by_type(signal_type)
        assert len(matching) == 0, (
            f"Expected no {signal_type} signals, but got {len(matching)}"
        )
