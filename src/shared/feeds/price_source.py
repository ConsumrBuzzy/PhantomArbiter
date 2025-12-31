"""
V1.0: Abstract Price Source Interface
=====================================
Defines the contract for all DEX price feed adapters.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import time


@dataclass
class Quote:
    """
    Represents a tradeable quote from a DEX.

    This is more than just a price - it includes enough info
    to actually execute the trade if desired.
    """

    dex: str  # "JUPITER", "RAYDIUM", "ORCA"
    input_mint: str  # Token being sold
    output_mint: str  # Token being bought
    input_amount: float  # Amount in (human readable)
    output_amount: float  # Amount out (human readable)
    price: float  # Effective price (output/input)
    slippage_estimate_pct: float  # Estimated slippage %
    fee_pct: float = 0.0  # Trading fee %
    route: Optional[Dict[str, Any]] = None  # DEX-specific routing info for execution
    timestamp: float = field(default_factory=time.time)

    @property
    def effective_price_after_fees(self) -> float:
        """Price after accounting for fees."""
        return self.price * (1 - self.fee_pct / 100)

    def __repr__(self) -> str:
        return f"Quote({self.dex}: {self.input_amount:.4f} → {self.output_amount:.4f} @ {self.price:.6f})"


@dataclass
class SpotPrice:
    """Simple spot price without execution context."""

    dex: str
    base_mint: str
    quote_mint: str
    price: float
    timestamp: float = field(default_factory=time.time)
    source: str = "UNKNOWN"
    liquidity_usd: float = 0.0

    @property
    def age_seconds(self) -> float:
        """How stale is this price?"""
        return time.time() - self.timestamp


class PriceSource(ABC):
    """
    Abstract interface for DEX price feeds.

    Implementations must provide:
    - get_name(): Unique identifier for this DEX
    - get_quote(): Executable quote for a specific trade size
    - get_spot_price(): Quick spot price (no size consideration)
    """

    @abstractmethod
    def get_name(self) -> str:
        """Return the DEX name (e.g., 'JUPITER', 'RAYDIUM')."""
        pass

    @abstractmethod
    async def get_quote(
        self, input_mint: str, output_mint: str, amount: float
    ) -> Optional[Quote]:
        """
        Get an executable quote for a trade.

        Args:
            input_mint: Token to sell (mint address)
            output_mint: Token to buy (mint address)
            amount: Amount of input token (human readable, not atomic)

        Returns:
            Quote object with execution details, or None if unavailable
        """
        pass

    @abstractmethod
    async def get_spot_price(
        self, base_mint: str, quote_mint: str
    ) -> Optional[SpotPrice]:
        """
        Get current spot price for a pair.

        This is a lightweight call for monitoring - not for execution.

        Args:
            base_mint: Base token (the one being priced)
            quote_mint: Quote token (usually USDC or SOL)

        Returns:
            SpotPrice object or None if unavailable
        """
        pass

    async def close(self):
        """Cleanup async resources (e.g. HTTP clients)."""
        pass

    def get_fee_pct(self) -> float:
        """Return the default trading fee percentage for this DEX."""
        return 0.3  # Default 0.3% fee
