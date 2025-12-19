"""
V49.0: Liquidity Package
========================
Orca Whirlpools CLMM integration for market making during sideways markets.

Components:
- orca_adapter.py: Low-level Whirlpool program interactions
- liquidity_manager.py: ML-driven position orchestration
- pool_scraper.py: Pool discovery and ranking
- types.py: Data classes for pool/position state
"""

from src.liquidity.types import WhirlpoolState, PositionState, LiquidityParams
from src.liquidity.orca_adapter import get_orca_adapter, SOL_MINT, USDC_MINT
from src.liquidity.liquidity_manager import get_liquidity_manager, MarketRegime
from src.liquidity.pool_scraper import get_pool_scraper

__all__ = [
    # Types
    "WhirlpoolState",
    "PositionState",
    "LiquidityParams",
    # Adapters
    "get_orca_adapter",
    "get_liquidity_manager",
    "get_pool_scraper",
    # Constants
    "SOL_MINT",
    "USDC_MINT",
    "MarketRegime",
]
