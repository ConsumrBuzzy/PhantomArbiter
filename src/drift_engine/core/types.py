from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional

class OracleSource(Enum):
    """Drift OracleSource Enum."""
    PYTH = 0
    SWITCHBOARD = 1
    QUOTE_ASSET = 2
    PYTH_1K = 3
    PYTH_1M = 4
    PYTH_STABLE_COIN = 5
    PRELAUNCH = 6
    PYTH_PULL = 7
    PYTH_1K_PULL = 8
    PYTH_1M_PULL = 9
    PYTH_STABLE_COIN_PULL = 10
    SWITCHBOARD_ON_DEMAND = 11
    PYTH_LAZER = 12
    PYTH_LAZER_1K = 13
    PYTH_LAZER_1M = 14
    PYTH_LAZER_STABLE_COIN = 15

class PositionDirection(Enum):
    """Direction of perp position."""
    LONG = 0
    SHORT = 1

class OrderType(Enum):
    """Drift order types."""
    MARKET = 0
    LIMIT = 1
    TRIGGER_MARKET = 2
    TRIGGER_LIMIT = 3
    ORACLE = 4

class MarketType(Enum):
    """Drift market types."""
    SPOT = 0
    PERP = 1

@dataclass
class DriftPosition:
    """Current position info from Drift."""
    market: str
    size: float  # Positive = long, Negative = short
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    leverage: float = 1.0
    
    @property
    def is_short(self) -> bool:
        return self.size < 0
    
    @property
    def is_long(self) -> bool:
        return self.size > 0
    
    @property
    def notional_usd(self) -> float:
        return abs(self.size * self.mark_price)

@dataclass
class DriftMarginMetrics:
    """Drift Protocol margin and health metrics."""
    # Core Margin Values
    total_collateral: float = 0.0
    free_collateral: float = 0.0
    maintenance_margin: float = 0.0
    initial_margin: float = 0.0
    
    # Health Score
    health_score: float = 1.0
    leverage: float = 0.0
    max_leverage: float = 20.0
    
    # Derived Flags
    is_healthy: bool = True
    liquidation_risk: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_collateral": self.total_collateral,
            "free_collateral": self.free_collateral,
            "maintenance_margin": self.maintenance_margin,
            "initial_margin": self.initial_margin,
            "health_score": self.health_score,
            "leverage": self.leverage,
            "max_leverage": self.max_leverage,
            "is_healthy": self.is_healthy,
            "liquidation_risk": self.liquidation_risk,
        }
