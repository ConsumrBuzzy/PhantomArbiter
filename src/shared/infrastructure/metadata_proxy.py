"""
V134: Metadata Proxy Service
===========================
Unified access point for 3-tier token metadata:
1. Static Identity (Mint, Symbol, Decimals)
2. Risk/Security (Authorities, Mutability)
3. Market/Liquidity (Price, Volume, Pools)

Usage:
    proxy = get_metadata_proxy()
    meta = proxy.get_metadata("So111...")
    print(meta['risk'].safety_score)
"""

import time
import threading
from typing import Dict, Optional, Any
from src.shared.system.logging import Logger
from src.shared.infrastructure.token_registry import get_registry

class MetadataProxy:
    """
    Central service for fetching and caching token metadata.
    Delegates to TokenRegistry for underlying storage/fetching.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.registry = get_registry()
        Logger.info("📚 [PROXY] Metadata Proxy Service initialized")
        
    def get_metadata(self, mint: str) -> Dict[str, Any]:
        """
        Get full metadata for a token.
        Returns dict with 'identity', 'risk', 'market' keys.
        """
        return self.registry.get_full_metadata(mint)
        
    def refresh_risk_data(self, mint: str):
        """Trigger background refresh of risk data."""
        # TODO: Integrate with Helius/Solscan scraper
        pass
        
    def refresh_market_data(self, mint: str):
        """Trigger background refresh of market data."""
        # TODO: Integrate with DexScreener batch fetch
        pass

# Singleton accessor
_proxy: Optional[MetadataProxy] = None

def get_metadata_proxy() -> MetadataProxy:
    global _proxy
    if _proxy is None:
        _proxy = MetadataProxy()
    return _proxy
