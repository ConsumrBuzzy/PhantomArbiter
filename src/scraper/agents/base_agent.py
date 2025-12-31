from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional
import time


@dataclass
class AgentSignal:
    """
    Standardized output from any agent.
    """

    source: str  # Agent Name (e.g., "SCOUT_V1")
    symbol: str  # Target Asset
    action: str  # BUY, SELL, HOLD, ALERT
    confidence: float  # 0.0 to 1.0
    reason: str  # Human-readable explanation
    timestamp: float = 0.0
    metadata: Dict = None  # Extra data (e.g., "whale_wallet": "...")

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class BaseAgent(ABC):
    """
    Abstract Base Class for all specialized agents in the Hybrid Architecture.

    Lifecycle:
    1. __init__(config)
    2. start() -> Launches background tasks
    3. on_tick(market_data) -> Called by Orchestrator
    4. stop() -> Cleanup
    """

    def __init__(self, name: str, config: Dict[str, Any] = None):
        self.name = name
        self.config = config or {}
        self.running = False
        self.last_signal = None

    @abstractmethod
    def start(self):
        """Start agent lifecycle (threads, listeners)."""
        pass

    @abstractmethod
    def stop(self):
        """Stop agent lifecycle."""
        pass

    @abstractmethod
    def on_tick(self, market_data: Any) -> Optional[AgentSignal]:
        """
        Process a market tick and potentially emit a signal.
        market_data type is generic (dict or object) depending on system.
        """
        pass

    def _create_signal(
        self,
        symbol: str,
        action: str,
        confidence: float,
        reason: str,
        metadata: Dict = None,
    ) -> AgentSignal:
        """Helper to create a standardized signal."""
        signal = AgentSignal(
            source=self.name,
            symbol=symbol,
            action=action,
            confidence=confidence,
            reason=reason,
            metadata=metadata,
        )
        self.last_signal = signal
        return signal
