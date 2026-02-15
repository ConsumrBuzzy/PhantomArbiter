"""
NFT Janitor Configuration
==========================
Configuration dataclass with economic thresholds and safety parameters.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class JanitorConfig:
    """Configuration for NFT Janitor rent reclamation operations."""

    # Economic Thresholds
    RENT_VALUE_SOL: float = 0.0121  # Standard Legacy NFT rent deposit
    MAX_FLOOR_PRICE_SOL: float = 0.0095  # Max price to buy (must be profitable)
    MIN_PROFIT_SOL: float = 0.002  # Minimum profit after all fees
    MARKET_FEE_PERCENT: float = 0.02  # 2% Tensor/marketplace fee
    GAS_ESTIMATE_SOL: float = 0.0001  # Conservative gas estimate

    # Priority Fees (to compete with other janitor bots)
    PRIORITY_FEE_LAMPORTS: int = 10_000  # 10k micro-lamports
    COMPUTE_UNITS: int = 200_000  # Conservative compute budget

    # Rate Limiting
    SCAN_BATCH_SIZE: int = 100  # Max NFTs per scan
    RPC_DELAY_MS: int = 50  # Delay between RPC calls
    TENSOR_DELAY_MS: int = 50  # Delay between Tensor API calls
    MAX_PURCHASE_BATCH: int = 5  # Max NFTs to buy at once
    MAX_BURN_BATCH: int = 3  # Max NFTs to burn per transaction

    # Safety Guardrails
    DRY_RUN_DEFAULT: bool = True  # Always dry-run unless --live
    MAX_WALLET_EXPOSURE_SOL: float = 0.06  # Max SOL locked in NFTs
    PRIORITY_FEE_MULTIPLIER: float = 2.0  # Profit must be 2x priority fee
    MAX_RETRY_ATTEMPTS: int = 3  # Max retries for failed operations

    # Tensor API
    TENSOR_GRAPHQL_URL: str = "https://api.tensor.so/graphql"
    TENSOR_API_KEY: Optional[str] = None  # May be needed for rate limits

    # Metaplex Token Metadata Program
    METADATA_PROGRAM_ID: str = "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s"

    def calculate_profit(self, floor_price_sol: float, current_priority_fee_sol: float = 0.0) -> float:
        """
        Calculate expected profit for an NFT purchase.

        Args:
            floor_price_sol: Current floor price in SOL
            current_priority_fee_sol: Current network priority fee

        Returns:
            Expected profit in SOL (negative if unprofitable)
        """
        market_fee = floor_price_sol * self.MARKET_FEE_PERCENT
        total_cost = floor_price_sol + market_fee + self.GAS_ESTIMATE_SOL
        profit = self.RENT_VALUE_SOL - total_cost

        # Ensure profit exceeds minimum threshold and priority fee multiplier
        min_required_profit = max(
            self.MIN_PROFIT_SOL,
            current_priority_fee_sol * self.PRIORITY_FEE_MULTIPLIER
        )

        return profit if profit >= min_required_profit else 0.0

    def is_profitable(self, floor_price_sol: float, current_priority_fee_sol: float = 0.0) -> bool:
        """
        Check if an NFT purchase would be profitable.

        Args:
            floor_price_sol: Current floor price in SOL
            current_priority_fee_sol: Current network priority fee

        Returns:
            True if profitable after all fees and safety margins
        """
        return self.calculate_profit(floor_price_sol, current_priority_fee_sol) > 0.0
