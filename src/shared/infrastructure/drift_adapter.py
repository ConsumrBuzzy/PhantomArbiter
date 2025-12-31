"""
V49.0: Drift Protocol Adapter (Unified)
========================================
Unified adapter for Drift perpetual futures protocol.

This module re-exports the full DriftAdapter from infrastructure
for backwards compatibility with existing code that imports from here.

The real implementation is in src/infrastructure/drift_adapter.py
"""

# Re-export from the full implementation
from src.infrastructure.drift_adapter import DriftAdapter, DriftPosition

# Data classes for compatibility
from dataclasses import dataclass
from typing import Optional


@dataclass
class FundingRate:
    """Funding rate data from Drift (for backwards compatibility)."""

    market: str
    rate: float  # Annualized rate
    rate_hourly: float  # Hourly rate
    next_payment: int  # Unix timestamp
    is_positive: bool  # True = longs pay shorts


@dataclass
class Position:
    """Open position on Drift (alias for DriftPosition)."""

    market: str
    size: float  # Negative = short
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    collateral: float


# Singleton
_adapter: Optional[DriftAdapter] = None


def get_drift_adapter() -> DriftAdapter:
    """Get or create DriftAdapter singleton."""
    global _adapter
    if _adapter is None:
        _adapter = DriftAdapter("mainnet")
    return _adapter


# For imports that use old class name
__all__ = [
    "DriftAdapter",
    "DriftPosition",
    "FundingRate",
    "Position",
    "get_drift_adapter",
]
