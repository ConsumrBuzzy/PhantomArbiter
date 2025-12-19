"""
V49.0: Orca CLMM Types
======================
Data classes for Whirlpool and Position state.
"""

from dataclasses import dataclass, field
from typing import Optional, List
import time


@dataclass
class WhirlpoolState:
    """
    Represents the current state of an Orca Whirlpool.
    
    Fetched from on-chain account data.
    """
    address: str                    # Pool address (base58)
    token_mint_a: str               # Token A mint (e.g., SOL)
    token_mint_b: str               # Token B mint (e.g., USDC)
    tick_spacing: int               # Tick spacing (e.g., 64 for 1% pools)
    tick_current: int               # Current tick index
    sqrt_price: int                 # Current sqrt price (Q64.64)
    liquidity: int                  # Current liquidity
    fee_rate: int                   # Fee rate in hundredths of a bip (e.g., 10000 = 1%)
    protocol_fee_rate: int          # Protocol fee rate
    fee_growth_global_a: int        # Accumulated fees for token A
    fee_growth_global_b: int        # Accumulated fees for token B
    
    # Derived fields
    price: float = 0.0              # Human-readable price (B per A)
    tvl_usd: float = 0.0            # Total value locked in USD
    volume_24h: float = 0.0         # 24h volume in USD
    fee_apr: float = 0.0            # Estimated fee APR
    
    timestamp: float = field(default_factory=time.time)
    
    def __repr__(self):
        return f"<Whirlpool {self.address[:8]}... price=${self.price:.4f} TVL=${self.tvl_usd/1e6:.2f}M>"


@dataclass
class PositionState:
    """
    Represents a user's CLMM position in a Whirlpool.
    """
    address: str                    # Position NFT address
    whirlpool: str                  # Parent pool address
    owner: str                      # Owner wallet address
    
    # Range bounds
    tick_lower: int                 # Lower tick bound
    tick_upper: int                 # Upper tick bound
    price_lower: float = 0.0        # Lower price bound (human-readable)
    price_upper: float = 0.0        # Upper price bound (human-readable)
    
    # Liquidity
    liquidity: int = 0              # Liquidity amount
    
    # Token amounts
    amount_a: float = 0.0           # Token A amount in position
    amount_b: float = 0.0           # Token B amount in position
    value_usd: float = 0.0          # Total position value in USD
    
    # Uncollected fees
    fees_owed_a: float = 0.0        # Uncollected fees in token A
    fees_owed_b: float = 0.0        # Uncollected fees in token B
    fees_usd: float = 0.0           # Total uncollected fees in USD
    
    # Metadata
    entry_time: float = 0.0         # When position was opened
    entry_price: float = 0.0        # Price when position was opened
    
    timestamp: float = field(default_factory=time.time)
    
    @property
    def is_in_range(self) -> bool:
        """Check if current price is within position range."""
        # This requires current price - will be set by adapter
        return True  # Placeholder
    
    @property
    def age_hours(self) -> float:
        """Hours since position was opened."""
        if self.entry_time == 0:
            return 0.0
        return (time.time() - self.entry_time) / 3600
    
    def __repr__(self):
        return f"<Position {self.address[:8]}... range=[${self.price_lower:.4f}, ${self.price_upper:.4f}] value=${self.value_usd:.2f}>"


@dataclass
class LiquidityParams:
    """
    Parameters for opening a new liquidity position.
    """
    pool_address: str               # Target Whirlpool
    range_pct: float                # Range width as percentage (e.g., 1.0 = ±1%)
    amount_usd: float               # Total USD value to deploy
    
    # Computed fields (set by LiquidityManager)
    center_price: float = 0.0       # Current price at deployment
    tick_lower: int = 0             # Computed lower tick
    tick_upper: int = 0             # Computed upper tick
    amount_a: float = 0.0           # Token A amount
    amount_b: float = 0.0           # Token B amount
    
    def __repr__(self):
        return f"<LiquidityParams pool={self.pool_address[:8]}... range=±{self.range_pct}% amount=${self.amount_usd:.2f}>"


# Well-known Whirlpool addresses (Mainnet)
KNOWN_POOLS = {
    "SOL-USDC-1%": "HJPjoWUrhoZzkNfRpHuieeFk9WcZWjwy6PBjZ81ngndJ",
    "SOL-USDC-0.3%": "7qbRF6YsyGuLUVs6Y1q64bdVrfe4ZcUUz1JRdoVNUJnm",
    "SOL-USDC-0.01%": "Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crLCEgFbXe",
}

# Whirlpool Program ID
WHIRLPOOL_PROGRAM_ID = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
