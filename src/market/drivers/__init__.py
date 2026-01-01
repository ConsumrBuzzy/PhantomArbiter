"""
Market Drivers - The "How" Layer
=================================
Specific DEX/API implementations for price and data ingestion.

Each driver handles the dirty work of parsing responses from a specific
source. The Services layer (price_feed_service.py) aggregates these
into a unified interface.

Drivers:
- JupiterFeed: Jupiter V6 API
- RaydiumFeed: Raydium AMM/CLMM
- OrcaFeed: Orca Whirlpools
- MeteoraFeed: Meteora DLMM
- DriftFeed: Drift funding rates
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.market.drivers.jupiter_feed import JupiterFeed
    from src.market.drivers.raydium_feed import RaydiumFeed
    from src.market.drivers.orca_feed import OrcaFeed
    from src.market.drivers.meteora_feed import MeteoraFeed
    from src.market.drivers.drift_funding import DriftFundingFeed


def get_jupiter_driver() -> "JupiterFeed":
    """Get Jupiter feed driver."""
    from src.market.drivers.jupiter_feed import JupiterFeed
    return JupiterFeed()


from functools import lru_cache

@lru_cache(maxsize=1)
def get_raydium_driver() -> "RaydiumFeed":
    """Get Raydium feed driver (Singleton)."""
    from src.market.drivers.raydium_feed import RaydiumFeed
    return RaydiumFeed()


def get_orca_driver() -> "OrcaFeed":
    """Get Orca feed driver."""
    from src.market.drivers.orca_feed import OrcaFeed
    return OrcaFeed()


def get_meteora_driver() -> "MeteoraFeed":
    """Get Meteora feed driver."""
    from src.market.drivers.meteora_feed import MeteoraFeed
    return MeteoraFeed()


__all__ = [
    "get_jupiter_driver",
    "get_raydium_driver", 
    "get_orca_driver",
    "get_meteora_driver",
]
