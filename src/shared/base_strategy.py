"""
Base Strategy - Cartridge Interface
====================================
Abstract base class that all trading engine "cartridges" must implement.

This provides a standardized contract for the Command Center to interact
with any engine without knowing its internal logic.

Lifecycle:
    1. initialize() - Setup data feeds, recover state from DB
    2. get_decision() - Core logic loop (market data → signal)
    3. on_order_update() - React to fills/rejects
    4. shutdown() - Graceful cleanup
"""

from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
import time


class TradingSignal(Enum):
    """Trading decision output from get_decision()."""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    CLOSE = "close"  # Close existing position
    REBALANCE = "rebalance"  # Adjust existing position


class OrderStatus(Enum):
    """Order lifecycle states."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class Decision:
    """
    Structured output from get_decision().
    Contains the signal plus context for execution.
    """
    signal: TradingSignal
    symbol: str = ""
    size: float = 0.0
    price: Optional[float] = None  # None = market order
    confidence: float = 0.0  # 0.0 - 1.0
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    
    @property
    def is_actionable(self) -> bool:
        """Check if this decision requires execution."""
        return self.signal in [TradingSignal.BUY, TradingSignal.SELL, 
                               TradingSignal.CLOSE, TradingSignal.REBALANCE]


@dataclass
class OrderUpdate:
    """
    Inbound notification about an order's state change.
    """
    order_id: str
    status: OrderStatus
    symbol: str
    side: str  # "buy" or "sell"
    filled_size: float = 0.0
    filled_price: float = 0.0
    remaining_size: float = 0.0
    fee: float = 0.0
    tx_signature: str = ""
    error_msg: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategy cartridges.
    
    Implementations must define:
        - initialize(): Prepare for trading session
        - get_decision(): Analyze data and produce signals
        - on_order_update(): Handle execution feedback
    
    Optional overrides:
        - on_tick(): High-frequency data handler
        - on_heartbeat(): Periodic health check
        - shutdown(): Cleanup logic
    """
    
    def __init__(self, engine_name: str, config: Dict[str, Any] = None):
        """
        Initialize the strategy base.
        
        Args:
            engine_name: Unique identifier for this engine (e.g., "funding")
            config: Engine-specific configuration parameters
        """
        self.engine_name = engine_name
        self.config = config or {}
        self.is_initialized = False
        self.is_running = False
        self._start_time: Optional[float] = None
        
        # State that subclasses can use
        self.positions: Dict[str, Any] = {}
        self.pending_orders: Dict[str, Any] = {}
        self.last_decision: Optional[Decision] = None
    
    @property
    def uptime(self) -> float:
        """Get engine uptime in seconds."""
        if self._start_time:
            return time.time() - self._start_time
        return 0.0
    
    # ═══════════════════════════════════════════════════════════════
    # REQUIRED METHODS (Must be implemented by subclasses)
    # ═══════════════════════════════════════════════════════════════
    
    @abstractmethod
    async def initialize(self) -> bool:
        """
        Prepare the strategy for trading.
        
        Responsibilities:
            - Connect to data feeds
            - Load state from persistence layer
            - Validate configuration
            - Recover open positions from DB
        
        Returns:
            True if initialization successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def get_decision(self, market_data: Dict[str, Any]) -> Decision:
        """
        Core logic: Analyze market data and produce a trading decision.
        
        This is the "brain" of the strategy. It receives market data
        and returns a Decision object indicating what action to take.
        
        Args:
            market_data: Dict containing prices, orderbook, indicators, etc.
        
        Returns:
            Decision object with signal, size, confidence, reason
        """
        pass
    
    @abstractmethod
    async def on_order_update(self, update: OrderUpdate) -> None:
        """
        Handle feedback from order execution.
        
        Called when an order transitions states (filled, rejected, etc.)
        
        Responsibilities:
            - Update internal position tracking
            - Log trade to persistence layer
            - Adjust strategy state based on outcome
        
        Args:
            update: OrderUpdate with fill/reject details
        """
        pass
    
    # ═══════════════════════════════════════════════════════════════
    # OPTIONAL HOOKS (Can be overridden by subclasses)
    # ═══════════════════════════════════════════════════════════════
    
    async def on_tick(self, tick_data: Dict[str, Any]) -> None:
        """
        Handle high-frequency tick data (optional).
        
        For strategies that need sub-second data processing.
        Default implementation does nothing.
        """
        pass
    
    async def on_heartbeat(self) -> Dict[str, Any]:
        """
        Periodic health check (optional).
        
        Called by the orchestrator at regular intervals.
        Should return status info for monitoring.
        
        Returns:
            Dict with health metrics (positions, pnl, errors, etc.)
        """
        return {
            "engine": self.engine_name,
            "is_running": self.is_running,
            "uptime": self.uptime,
            "positions": len(self.positions),
            "pending_orders": len(self.pending_orders)
        }
    
    async def shutdown(self) -> None:
        """
        Graceful shutdown (optional).
        
        Called when the engine is stopped. Should:
            - Close connections
            - Save final state to persistence
            - Cancel pending orders (if configured)
        """
        self.is_running = False
    
    # ═══════════════════════════════════════════════════════════════
    # LIFECYCLE MANAGEMENT (Called by orchestrator)
    # ═══════════════════════════════════════════════════════════════
    
    async def start(self) -> bool:
        """
        Start the strategy engine.
        
        Called by the orchestrator to begin trading.
        """
        if self.is_running:
            return True
        
        # Initialize if not already done
        if not self.is_initialized:
            success = await self.initialize()
            if not success:
                return False
            self.is_initialized = True
        
        self._start_time = time.time()
        self.is_running = True
        return True
    
    async def stop(self) -> None:
        """
        Stop the strategy engine.
        
        Called by the orchestrator to halt trading.
        """
        await self.shutdown()
        self.is_running = False
    
    # ═══════════════════════════════════════════════════════════════
    # UTILITY METHODS (Available to subclasses)
    # ═══════════════════════════════════════════════════════════════
    
    def log(self, level: str, message: str) -> None:
        """Log a message through the shared logging system."""
        from src.shared.system.logging import Logger
        
        prefix = f"[{self.engine_name.upper()}]"
        if level == "INFO":
            Logger.info(f"{prefix} {message}")
        elif level == "WARNING":
            Logger.warning(f"{prefix} {message}")
        elif level == "ERROR":
            Logger.error(f"{prefix} {message}")
        else:
            Logger.debug(f"{prefix} {message}")
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """Get a configuration value with optional default."""
        return self.config.get(key, default)
    
    def update_config(self, updates: Dict[str, Any]) -> None:
        """Hot-update configuration values."""
        self.config.update(updates)
    
    async def save_state(self) -> None:
        """Persist current state to database."""
        from src.shared.system.persistence import get_db
        
        db = get_db()
        db.save_engine_snapshot(
            engine=self.engine_name,
            status="running" if self.is_running else "stopped",
            config=self.config,
            state={
                "positions": list(self.positions.keys()),
                "pending_orders": list(self.pending_orders.keys()),
                "last_decision": self.last_decision.signal.value if self.last_decision else None
            }
        )
    
    async def load_state(self) -> bool:
        """Load state from database for recovery."""
        from src.shared.system.persistence import get_db
        
        db = get_db()
        snapshot = db.get_engine_snapshot(self.engine_name)
        
        if snapshot:
            import json
            try:
                saved_config = json.loads(snapshot.config)
                saved_state = json.loads(snapshot.state)
                
                # Merge saved config with current
                for key, value in saved_config.items():
                    if key not in self.config:
                        self.config[key] = value
                
                self.log("INFO", f"Recovered state from snapshot (created: {snapshot.created_at})")
                return True
            except json.JSONDecodeError:
                self.log("WARNING", "Failed to parse saved state")
        
        return False
