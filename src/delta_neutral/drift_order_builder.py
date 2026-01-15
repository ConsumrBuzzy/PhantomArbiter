"""
Legacy Drift Order Builder shim.
Re-exports components moved to src.drift_engine.
"""

from src.drift_engine.core.types import (
    DriftPosition, OrderType, MarketType, PositionDirection, OracleSource
)

from src.drift_engine.core.builder import (
    DriftOrderBuilder, 
    DriftOrderParams, 
    ORACLES, 
    MARKET_INDICES,
    create_drift_order_builder
)

from src.drift_engine.core.client import DriftAdapter
