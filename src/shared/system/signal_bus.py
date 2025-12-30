import asyncio
from typing import Dict, List, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
import time

class SignalType(Enum):
    WHALE = "WHALE"
    SCOUT = "SCOUT"
    ARB_OPP = "ARB_OPP"
    SCALP_SIGNAL = "SCALP_SIGNAL"
    SYSTEM_ALERT = "SYSTEM_ALERT"
    CONFIG_CHANGE = "CONFIG_CHANGE"
    MARKET_UPDATE = "MARKET_UPDATE"  # V134: Price changes for Global Feed
    METADATA = "METADATA"         # V40.0: Shared Token Metadata Updates
    STRATEGY_TIP = "STRATEGY_TIP" # V41.0: Cross-Strategy Hints (e.g. Scalper -> Arbiter)
    NEW_TOKEN = "NEW_TOKEN"       # V140: Sauron Discovery -> Scout Metadata Scan

@dataclass
class Signal:
    type: SignalType
    source: str
    data: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)

class SignalBus:
    """
    Reactive Signal Bus for the Unified HFT OS.
    Allows agents to emit and subscribe to signals without direct coupling.
    """
    def __init__(self):
        self._subscribers: Dict[SignalType, List[Callable]] = {t: [] for t in SignalType}
        self._history: List[Signal] = []
        self._max_history = 100

    def subscribe(self, signal_type: SignalType, callback: Callable[[Signal], None]):
        """Register a callback for a specific signal type."""
        if callback not in self._subscribers[signal_type]:
            self._subscribers[signal_type].append(callback)

    def emit(self, signal: Signal):
        """Emit a signal to all subscribers."""
        self._history.append(signal)
        if len(self._history) > self._max_history:
            self._history.pop(0)
            
        for callback in self._subscribers.get(signal.type, []):
            if asyncio.iscoroutinefunction(callback):
                asyncio.create_task(callback(signal))
            else:
                callback(signal)

# Global Hub Accessor
signal_bus = SignalBus()
