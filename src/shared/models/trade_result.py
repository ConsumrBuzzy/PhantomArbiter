"""
V1.0: Trade Result Schema
==========================
Standardized result object for all execution paths (Paper & Live).
Used by ShadowManager for apples-to-apples comparison.
"""

from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class TradeResult:
    """
    Unified result from both Paper and Live execution paths.

    Enables Shadow Mode to compare fill prices and execution timing
    across different execution strategies.
    """

    # Required Fields
    success: bool
    action: str  # "BUY" | "SELL"
    token: str  # Symbol or mint address
    fill_price: float  # Actual fill price after slippage
    quantity: float  # Units acquired/sold
    slippage_pct: float  # Total slippage as percentage

    # Timing
    timestamp: float = field(default_factory=time.time)

    # Optional Fields
    tx_id: Optional[str] = None
    pnl_usd: Optional[float] = None
    reason: str = ""  # Trade reason/trigger

    # Execution Context
    source: str = "PAPER"  # "PAPER" | "LIVE" | "SHADOW"
    requested_price: float = 0.0  # Signal price before slippage
    latency_ms: float = 0.0  # Execution latency

    @property
    def price_delta_pct(self) -> float:
        """Calculate price deviation from requested."""
        if self.requested_price <= 0:
            return 0.0
        return ((self.fill_price - self.requested_price) / self.requested_price) * 100

    def to_dict(self) -> dict:
        """Convert to dictionary for logging/serialization."""
        return {
            "success": self.success,
            "action": self.action,
            "token": self.token,
            "fill_price": self.fill_price,
            "quantity": self.quantity,
            "slippage_pct": self.slippage_pct,
            "timestamp": self.timestamp,
            "tx_id": self.tx_id,
            "pnl_usd": self.pnl_usd,
            "reason": self.reason,
            "source": self.source,
            "requested_price": self.requested_price,
            "latency_ms": self.latency_ms,
        }

    @classmethod
    def from_paper_result(
        cls, result: dict, token: str, action: str, requested_price: float
    ) -> "TradeResult":
        """
        Factory method to convert PaperWallet result dict to TradeResult.

        Args:
            result: Dict from PaperWallet.simulate_buy/sell
            token: Token symbol
            action: "BUY" or "SELL"
            requested_price: Original signal price
        """
        if not result.get("success", False):
            return cls(
                success=False,
                action=action,
                token=token,
                fill_price=0.0,
                quantity=0.0,
                slippage_pct=0.0,
                source="PAPER",
                requested_price=requested_price,
                reason=result.get("reason", "Unknown error"),
            )

        return cls(
            success=True,
            action=action,
            token=token,
            fill_price=result.get("price", requested_price),
            quantity=result.get("quantity", 0.0),
            slippage_pct=result.get("slippage_pct", 0.0),
            source="PAPER",
            requested_price=requested_price,
            pnl_usd=result.get("pnl_usd"),
        )

    @classmethod
    def failed(
        cls, token: str, action: str, reason: str, source: str = "PAPER"
    ) -> "TradeResult":
        """Factory for failed trade result."""
        return cls(
            success=False,
            action=action,
            token=token,
            fill_price=0.0,
            quantity=0.0,
            slippage_pct=0.0,
            source=source,
            reason=reason,
        )
