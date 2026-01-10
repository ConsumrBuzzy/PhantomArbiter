"""
Delta Neutral Execution Module (DNEM)
=====================================
High-frequency, low-latency execution engine for delta neutral strategies.

Strategies supported:
- Funding Rate Arbitrage
- Basis Trading  
- Hedged LP

Reuses existing Hub infrastructure:
- Data Ingestion (WebSocket, RPC)
- Connectivity (Wallet, Signer, RPC Manager)
- Logging

Exports independent Spoke components:
- DeltaNeutralEngine: Main orchestrator
- NeutralityMonitor: Delta drift detection (the heartbeat)
- SyncExecution: Atomic Spot+Perp bundling via Jito
- RiskManager: Kill-switch and leg failure protection
"""

from src.delta_neutral.types import (
    DeltaPosition,
    MarketState,
    SyncTradeBundle,
    RebalanceSignal,
    RebalanceDirection,
    LatencyKillSwitchError,
    LegFailureError,
)
from src.delta_neutral.position_calculator import (
    calculate_position_size,
    get_rebalance_qty,
    calculate_delta_drift,
    calculate_rebalance_signal,
    build_delta_position,
    estimate_funding_yield,
    should_enter_funding_arb,
)

__all__ = [
    # Types
    "DeltaPosition",
    "MarketState", 
    "SyncTradeBundle",
    "RebalanceSignal",
    "RebalanceDirection",
    "LatencyKillSwitchError",
    "LegFailureError",
    # Calculator functions
    "calculate_position_size",
    "get_rebalance_qty",
    "calculate_delta_drift",
    "calculate_rebalance_signal",
    "build_delta_position",
    "estimate_funding_yield",
    "should_enter_funding_arb",
]

# Lazy imports for heavy modules (avoid circular imports)
def get_sync_execution():
    """Lazy import for SyncExecution."""
    from src.delta_neutral.sync_execution import SyncExecution
    return SyncExecution

def get_neutrality_monitor():
    """Lazy import for NeutralityMonitor."""
    from src.delta_neutral.neutrality_monitor import NeutralityMonitor
    return NeutralityMonitor

def get_engine():
    """Lazy import for DeltaNeutralEngine."""
    from src.delta_neutral.engine import DeltaNeutralEngine, DNEMConfig
    return DeltaNeutralEngine, DNEMConfig

