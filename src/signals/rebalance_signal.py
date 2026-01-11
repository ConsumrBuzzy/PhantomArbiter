"""
Rebalance Signal Definitions
============================
Signal types for the Opportunity-Liquidity Matrix.

These dataclasses define the communication protocol between:
- FundingEngine (opportunity detection)
- RebalanceSensor (decision logic)
- BridgeManager (execution)
- Dashboard (visibility)

V200: Initial implementation
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum
import time


# ═══════════════════════════════════════════════════════════════════════════════
# DECISION TYPES
# ═══════════════════════════════════════════════════════════════════════════════

class RebalanceDecision(Enum):
    """Decision outcome from RebalanceSensor evaluation."""
    IDLE = "IDLE"           # No action needed
    BRIDGE = "BRIDGE"       # Trigger CEX→DEX transfer
    LOCK = "LOCK"           # Hold - volatile/uncertain conditions
    AWAIT = "AWAIT"         # Waiting for bridge confirmation
    COOLDOWN = "COOLDOWN"   # Recent bridge, waiting


# ═══════════════════════════════════════════════════════════════════════════════
# SIGNAL DATACLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class FundingOpportunitySignal:
    """
    Signal emitted when a high-yield funding opportunity is detected.
    
    This is the "trigger" that the RebalanceSensor evaluates against
    current DEX liquidity to decide if a bridge is needed.
    
    Emitted by: FundingWatchdog, FundingRateArbitrage
    Consumed by: RebalanceSensor
    """
    market: str                     # e.g., "SOL-PERP"
    funding_rate_8h: float          # Rate per 8h as percentage (e.g., 0.05 = 0.05%)
    expected_yield_usd: float       # Expected USD profit from this opportunity
    required_capital: float         # USD needed to capture the opportunity
    time_to_funding_sec: float      # Seconds until next funding payment
    direction: str                  # "SHORT_PERP" or "LONG_PERP"
    timestamp: float = field(default_factory=time.time)
    
    @property
    def annualized_apy(self) -> float:
        """
        Convert 8h rate to annualized APY.
        
        Formula: rate_8h × 3 (periods/day) × 365 (days)
        """
        return self.funding_rate_8h * 3 * 365
    
    @property
    def is_high_yield(self) -> bool:
        """Check if this qualifies as high yield (>15% APY)."""
        return self.annualized_apy >= 15.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "market": self.market,
            "funding_rate_8h": f"{self.funding_rate_8h:.4f}%",
            "expected_yield_usd": self.expected_yield_usd,
            "required_capital": self.required_capital,
            "annualized_apy": f"{self.annualized_apy:.1f}%",
            "time_to_funding_sec": self.time_to_funding_sec,
            "direction": self.direction,
            "is_high_yield": self.is_high_yield,
            "timestamp": self.timestamp,
        }


@dataclass
class BridgeTriggerSignal:
    """
    Signal emitted when a bridge is initiated.
    
    Used for dashboard visibility and coordination. The UI should
    show a "neon blue pulse" when this signal is active.
    
    Emitted by: RebalanceSensor
    Consumed by: Dashboard, BridgeManager
    """
    amount: float                   # USD amount being bridged
    reason: str                     # "funding_opportunity", "rebalance", "manual"
    opportunity: Optional[FundingOpportunitySignal] = None
    withdrawal_id: Optional[str] = None
    estimated_arrival_sec: float = 60.0  # Solana confirmation ~30-60s
    timestamp: float = field(default_factory=time.time)
    
    @property
    def is_pending(self) -> bool:
        """Check if bridge is still pending (< 2 min since trigger)."""
        return (time.time() - self.timestamp) < 120
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "amount": self.amount,
            "reason": self.reason,
            "withdrawal_id": self.withdrawal_id,
            "opportunity_market": self.opportunity.market if self.opportunity else None,
            "estimated_arrival_sec": self.estimated_arrival_sec,
            "is_pending": self.is_pending,
            "timestamp": self.timestamp,
        }


@dataclass
class BridgeCompleteSignal:
    """
    Signal emitted when a bridge transfer is confirmed on-chain.
    
    Emitted by: BridgeManager (after Solana confirmation)
    Consumed by: Dashboard, RebalanceSensor
    """
    amount: float
    withdrawal_id: str
    solana_signature: Optional[str] = None
    latency_sec: float = 0.0        # Time from initiation to confirmation
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "amount": self.amount,
            "withdrawal_id": self.withdrawal_id,
            "solana_signature": self.solana_signature,
            "latency_sec": self.latency_sec,
            "timestamp": self.timestamp,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# EVALUATION RESULT
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class RebalanceEvaluation:
    """
    Result of RebalanceSensor evaluation.
    
    Captures the full decision context for logging, debugging, and
    potential ML training on optimal bridge timing.
    """
    decision: RebalanceDecision
    reason: str
    
    # Liquidity state at evaluation time
    phantom_balance: float = 0.0    # Current DEX USDC
    cex_available: float = 0.0      # Current CEX USDC (withdrawable)
    required_capital: float = 0.0   # Capital needed for opportunity
    deficit: float = 0.0            # phantom_balance - required_capital
    
    # Opportunity context
    opportunity: Optional[FundingOpportunitySignal] = None
    yield_apy: float = 0.0          # Annualized yield
    
    # Action taken (if any)
    bridge_amount: float = 0.0
    bridge_triggered: bool = False
    
    # Metadata
    evaluation_id: str = ""
    timestamp: float = field(default_factory=time.time)
    
    def __post_init__(self):
        if not self.evaluation_id:
            self.evaluation_id = f"eval_{int(self.timestamp * 1000)}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "decision": self.decision.value,
            "reason": self.reason,
            "phantom_balance": self.phantom_balance,
            "cex_available": self.cex_available,
            "required_capital": self.required_capital,
            "deficit": self.deficit,
            "yield_apy": f"{self.yield_apy:.1f}%",
            "bridge_amount": self.bridge_amount,
            "bridge_triggered": self.bridge_triggered,
            "opportunity_market": self.opportunity.market if self.opportunity else None,
            "timestamp": self.timestamp,
        }
    
    def to_log_string(self) -> str:
        """Format for log output."""
        return (
            f"[{self.decision.value}] {self.reason} | "
            f"Phantom: ${self.phantom_balance:.2f} | "
            f"CEX: ${self.cex_available:.2f} | "
            f"Yield: {self.yield_apy:.1f}% APY"
        )
