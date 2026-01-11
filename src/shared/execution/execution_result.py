"""
Unified Execution Result
========================
Standardized return type for all execution paths.

Every "Hand" (JupiterSwapper, DriftAdapter, SyncExecution) returns
this unified result type for consistent error handling and logging.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum
import time


class ExecutionStatus(Enum):
    """Status codes for execution results."""
    
    SUCCESS = "SUCCESS"
    PARTIAL_FILL = "PARTIAL_FILL"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    SIMULATED = "SIMULATED"  # Paper trade


class ErrorCode(Enum):
    """Standardized error codes for execution failures."""
    
    # Slippage errors
    SLIPPAGE_EXCEEDED = "SLIPPAGE_EXCEEDED"
    PRICE_MOVED = "PRICE_MOVED"
    
    # Liquidity errors
    INSUFFICIENT_LIQUIDITY = "INSUFFICIENT_LIQUIDITY"
    POOL_DEPLETED = "POOL_DEPLETED"
    
    # Balance errors
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    INSUFFICIENT_SOL = "INSUFFICIENT_SOL"
    
    # Network errors
    RPC_ERROR = "RPC_ERROR"
    TIMEOUT = "TIMEOUT"
    BLOCKHASH_EXPIRED = "BLOCKHASH_EXPIRED"
    
    # Jito bundle errors
    BUNDLE_REJECTED = "BUNDLE_REJECTED"
    BUNDLE_DROPPED = "BUNDLE_DROPPED"
    PARTIAL_BUNDLE = "PARTIAL_BUNDLE"
    
    # Safety errors
    KILL_SWITCH_TRIGGERED = "KILL_SWITCH_TRIGGERED"
    SAFETY_GATE_BLOCKED = "SAFETY_GATE_BLOCKED"
    
    # General
    UNKNOWN = "UNKNOWN"


@dataclass
class ExecutionResult:
    """
    Unified result for all trade execution paths.
    
    This is the standard return type for:
    - JupiterSwapper.execute_swap()
    - DriftAdapter.place_order()
    - SyncExecution.execute_sync_trade()
    - BaseEngine.execute_swap()
    
    Usage:
        result = await swapper.execute_swap(...)
        if result.success:
            log(f"Filled at {result.fill_price}")
        else:
            handle_error(result.error_code)
    """
    
    # Core status
    success: bool
    status: ExecutionStatus = ExecutionStatus.FAILED
    
    # Transaction details
    tx_signature: Optional[str] = None
    bundle_id: Optional[str] = None  # For Jito bundles
    
    # Fill information
    fill_price: float = 0.0
    requested_amount: float = 0.0
    filled_amount: float = 0.0
    
    # Cost breakdown
    fees_paid: float = 0.0
    gas_cost_usd: float = 0.0
    jito_tip_usd: float = 0.0
    slippage_pct: float = 0.0
    
    # Error handling
    error_code: Optional[ErrorCode] = None
    error_message: Optional[str] = None
    
    # Context
    engine: Optional[str] = None
    venue: Optional[str] = None  # "JUPITER", "DRIFT", "RAYDIUM"
    timestamp: float = field(default_factory=time.time)
    latency_ms: float = 0.0
    
    # Raw data for debugging
    raw_response: Optional[Dict[str, Any]] = None
    
    @property
    def net_cost_usd(self) -> float:
        """Total cost in USD (fees + gas + tip)."""
        return self.fees_paid + self.gas_cost_usd + self.jito_tip_usd
    
    @property
    def fill_ratio(self) -> float:
        """Ratio of filled amount to requested amount."""
        if self.requested_amount == 0:
            return 0.0
        return self.filled_amount / self.requested_amount
    
    @property
    def is_partial(self) -> bool:
        """Check if this was a partial fill."""
        return self.status == ExecutionStatus.PARTIAL_FILL
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/storage."""
        return {
            "success": self.success,
            "status": self.status.value,
            "tx_signature": self.tx_signature,
            "fill_price": self.fill_price,
            "filled_amount": self.filled_amount,
            "fees_paid": self.fees_paid,
            "slippage_pct": self.slippage_pct,
            "error_code": self.error_code.value if self.error_code else None,
            "error_message": self.error_message,
            "venue": self.venue,
            "latency_ms": self.latency_ms,
        }
    
    def __repr__(self) -> str:
        if self.success:
            return (
                f"ExecutionResult(SUCCESS: {self.filled_amount:.4f} @ {self.fill_price:.4f}, "
                f"fees=${self.net_cost_usd:.4f}, tx={self.tx_signature[:12] if self.tx_signature else 'N/A'}...)"
            )
        else:
            return f"ExecutionResult(FAILED: {self.error_code}, {self.error_message})"


# ═══════════════════════════════════════════════════════════════════════════════
# FACTORY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def success_result(
    tx_signature: str,
    fill_price: float,
    filled_amount: float,
    venue: str,
    **kwargs
) -> ExecutionResult:
    """Create a successful execution result."""
    return ExecutionResult(
        success=True,
        status=ExecutionStatus.SUCCESS,
        tx_signature=tx_signature,
        fill_price=fill_price,
        filled_amount=filled_amount,
        requested_amount=kwargs.get("requested_amount", filled_amount),
        venue=venue,
        fees_paid=kwargs.get("fees_paid", 0.0),
        gas_cost_usd=kwargs.get("gas_cost_usd", 0.0),
        slippage_pct=kwargs.get("slippage_pct", 0.0),
        latency_ms=kwargs.get("latency_ms", 0.0),
        raw_response=kwargs.get("raw_response"),
    )


def failure_result(
    error_code: ErrorCode,
    error_message: str,
    venue: str = None,
    **kwargs
) -> ExecutionResult:
    """Create a failed execution result."""
    return ExecutionResult(
        success=False,
        status=ExecutionStatus.FAILED,
        error_code=error_code,
        error_message=error_message,
        venue=venue,
        latency_ms=kwargs.get("latency_ms", 0.0),
        raw_response=kwargs.get("raw_response"),
    )


def simulated_result(
    fill_price: float,
    filled_amount: float,
    venue: str = "PAPER",
    **kwargs
) -> ExecutionResult:
    """Create a simulated (paper) execution result."""
    return ExecutionResult(
        success=True,
        status=ExecutionStatus.SIMULATED,
        tx_signature="PAPER_" + str(int(time.time() * 1000)),
        fill_price=fill_price,
        filled_amount=filled_amount,
        requested_amount=kwargs.get("requested_amount", filled_amount),
        venue=venue,
        fees_paid=kwargs.get("fees_paid", 0.0),
    )
