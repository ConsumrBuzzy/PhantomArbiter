"""
DNEM Type Definitions
=====================
PEP 484 compliant dataclasses for the Delta Neutral Execution Module.

These types form the "language" the engine speaks:
- MarketState: Current market snapshot
- DeltaPosition: The Position Matrix (Spot + Perp unified view)
- SyncTradeBundle: Atomic execution payload
- RebalanceSignal: Output of the NeutralityMonitor
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional
from enum import Enum


class RebalanceDirection(Enum):
    """Direction of rebalance action required."""
    
    ADD_SPOT = "ADD_SPOT"          # Perp heavy → buy more spot
    ADD_SHORT = "ADD_SHORT"        # Spot heavy → increase short
    REDUCE_SPOT = "REDUCE_SPOT"    # Reduce spot exposure
    REDUCE_SHORT = "REDUCE_SHORT"  # Reduce perp exposure
    NONE = "NONE"                  # Delta within threshold


@dataclass(frozen=True, slots=True)
class MarketState:
    """
    Current market snapshot for delta neutral calculations.
    
    Attributes:
        sol_price: Current SOL/USD price from Jupiter/Pyth
        funding_rate_hourly: Hourly funding rate (positive = longs pay shorts)
        equity_usd: Total account equity in USD
        delta: Net directional exposure (Goal: 0.0)
    """
    
    sol_price: float
    funding_rate_hourly: float
    equity_usd: float
    delta: float = 0.0  # Goal: 0.0


@dataclass(slots=True)
class DeltaPosition:
    """
    The Position Matrix: Unified view of Spot and Perp legs.
    
    This is the core state object that NeutralityMonitor operates on.
    
    Attributes:
        spot_qty: Quantity of SOL held in spot wallet
        perp_qty: Size of perpetual position (negative = short)
        spot_value_usd: USD value of spot holdings
        perp_value_usd: USD notional of perp position (absolute value)
        entry_price_spot: Average entry price for spot leg
        entry_price_perp: Average entry price for perp leg
        delta_drift_pct: Current drift from neutrality as percentage
        timestamp_ms: Last update time in milliseconds
    """
    
    spot_qty: float
    perp_qty: float  # Negative = short
    spot_value_usd: float
    perp_value_usd: float  # Absolute notional value
    entry_price_spot: float = 0.0
    entry_price_perp: float = 0.0
    delta_drift_pct: float = 0.0
    timestamp_ms: int = 0
    
    @property
    def is_neutral(self) -> bool:
        """Check if position is within acceptable drift threshold (0.5%)."""
        return abs(self.delta_drift_pct) <= 0.5
    
    @property
    def net_delta_usd(self) -> float:
        """Net USD exposure. Positive = long bias, Negative = short bias."""
        return self.spot_value_usd - abs(self.perp_value_usd)
    
    def __repr__(self) -> str:
        direction = "NEUTRAL" if self.is_neutral else (
            "LONG BIAS" if self.net_delta_usd > 0 else "SHORT BIAS"
        )
        return (
            f"DeltaPosition({direction}: "
            f"Spot={self.spot_qty:.4f} SOL (${self.spot_value_usd:.2f}), "
            f"Perp={self.perp_qty:.4f} (${self.perp_value_usd:.2f}), "
            f"Drift={self.delta_drift_pct:.2f}%)"
        )


@dataclass(frozen=True, slots=True)
class RebalanceSignal:
    """
    Output of the NeutralityMonitor.
    
    Generated when delta drift exceeds threshold (0.5%).
    Consumed by SyncExecution to restore neutrality.
    
    Attributes:
        direction: Which leg to adjust
        qty: Quantity of SOL to trade
        qty_usd: USD value of trade
        current_drift_pct: Drift at time of signal
        reason: Human-readable explanation
        urgency: Priority level (1-3, 3 = immediate)
    """
    
    direction: RebalanceDirection
    qty: float
    qty_usd: float
    current_drift_pct: float
    reason: str
    urgency: int = 1  # 1=normal, 2=elevated, 3=critical
    
    def __repr__(self) -> str:
        return (
            f"RebalanceSignal({self.direction.value}: "
            f"{self.qty:.4f} SOL (${self.qty_usd:.2f}), "
            f"Drift={self.current_drift_pct:.2f}%, "
            f"Urgency={self.urgency})"
        )


@dataclass(slots=True)
class SyncTradeBundle:
    """
    Atomic execution payload for Jito BlockEngine.
    
    Contains both legs (Spot + Perp) bundled with tip for atomic settlement.
    
    ⚠️ CRITICAL: If bundle fails partially, RiskManager must trigger
    emergency rollback within 3 blocks.
    
    Attributes:
        spot_instruction: Serialized Jupiter swap transaction
        perp_instruction: Serialized Drift order transaction
        jito_tip_lamports: Validator tip for bundle priority
        bundle_id: Returned by Jito after submission
        status: Current bundle status
        submitted_slot: Slot number when submitted
        confirmed_slot: Slot number when confirmed (if successful)
    """
    
    spot_instruction: bytes
    perp_instruction: bytes
    jito_tip_lamports: int = 10_000  # ~0.00001 SOL
    bundle_id: Optional[str] = None
    status: Literal["PENDING", "SUBMITTED", "CONFIRMED", "FAILED", "PARTIAL"] = "PENDING"
    submitted_slot: int = 0
    confirmed_slot: int = 0
    
    @property
    def is_atomic(self) -> bool:
        """True if both legs confirmed in same block."""
        if self.status != "CONFIRMED":
            return False
        return self.confirmed_slot > 0
    
    @property
    def needs_rollback(self) -> bool:
        """True if partial fill detected - EMERGENCY."""
        return self.status == "PARTIAL"


@dataclass(frozen=True, slots=True)
class LatencyKillSwitchError(Exception):
    """
    Raised when RPC latency exceeds safe threshold.
    
    At >500ms latency, the risk of "legging out" (partial execution)
    is too high. All execution must halt until latency recovers.
    """
    
    latency_ms: float
    threshold_ms: float = 500.0
    
    def __str__(self) -> str:
        return (
            f"KILL SWITCH ACTIVATED: Latency {self.latency_ms:.0f}ms "
            f"exceeds threshold {self.threshold_ms:.0f}ms"
        )


@dataclass(frozen=True, slots=True)
class LegFailureError(Exception):
    """
    Raised when one leg of a sync trade fails while the other succeeds.
    
    This is the most dangerous failure mode in delta neutral trading.
    Immediate rollback required.
    """
    
    failed_leg: Literal["SPOT", "PERP"]
    successful_leg: Literal["SPOT", "PERP"]
    bundle_id: str
    slot: int
    
    def __str__(self) -> str:
        return (
            f"LEG FAILURE: {self.failed_leg} failed, {self.successful_leg} succeeded! "
            f"Bundle={self.bundle_id}, Slot={self.slot}. IMMEDIATE ROLLBACK REQUIRED."
        )
