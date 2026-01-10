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
- NeutralityMonitor: Delta drift detection
- SyncExecution: Atomic Spot+Perp bundling
- RiskManager: Kill-switch and leg failure protection
"""

from src.delta_neutral.types import (
    DeltaPosition,
    MarketState,
    SyncTradeBundle,
    RebalanceSignal,
)
from src.delta_neutral.position_calculator import (
    calculate_position_size,
    get_rebalance_qty,
    calculate_delta_drift,
)

__all__ = [
    # Types
    "DeltaPosition",
    "MarketState", 
    "SyncTradeBundle",
    "RebalanceSignal",
    # Calculator functions
    "calculate_position_size",
    "get_rebalance_qty",
    "calculate_delta_drift",
]
