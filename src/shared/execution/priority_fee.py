"""
Priority Fee Client
====================
V83.0: Dynamic fee optimization using Raydium V3 API.

Fetches statistical priority fee recommendations to ensure
transactions land during congested blocks.

Usage:
    from src.shared.execution.priority_fee import PriorityFeeClient
    
    fee = await PriorityFeeClient.get_fee_estimate(tier="h")
    # Returns: 5000 (microLamports)
"""

import time
import asyncio
from typing import Dict, Optional

try:
    import httpx
except ImportError:
    httpx = None

try:
    from src.shared.system.logging import Logger
except ImportError:
    class Logger:
        @staticmethod
        def info(msg): print(f"[INFO] {msg}")
        @staticmethod
        def warning(msg): print(f"[WARN] {msg}")
        @staticmethod
        def debug(msg): pass
        @staticmethod
        def error(msg): print(f"[ERROR] {msg}")


class PriorityFeeClient:
    """
    V83.0: Dynamic Fee Optimizer using Raydium V3 API.
    
    Raydium provides statistical priority fee estimates based on
    recent network activity. This helps transactions land faster
    during congested periods.
    """
    
    # Raydium V3 auto-fee endpoint
    BASE_URL = "https://api-v3.raydium.io/main/auto-fee"
    
    # Cache to avoid excessive API calls
    _cache: Dict[str, int] = {}
    _cache_time: float = 0
    CACHE_TTL = 10  # 10 seconds
    
    # Fallback values (in microLamports)
    FALLBACK_FEES = {
        "m": 1000,     # Medium
        "h": 5000,     # High
        "vh": 25000,   # Very High
    }
    
    @classmethod
    async def get_fee_estimate(cls, tier: str = "h") -> int:
        """
        Get priority fee estimate from Raydium.
        
        Args:
            tier: Fee tier - "m" (Medium), "h" (High), "vh" (Very High)
            
        Returns:
            Priority fee in microLamports
        """
        # Check cache
        if time.time() - cls._cache_time < cls.CACHE_TTL and tier in cls._cache:
            return cls._cache[tier]
        
        try:
            if httpx is None:
                Logger.warning("[FEE] httpx not installed, using fallback")
                return cls.FALLBACK_FEES.get(tier, 5000)
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(cls.BASE_URL)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get('success'):
                        # Raydium returns tiers in data['data']['default']
                        fees = data.get('data', {}).get('default', {})
                        
                        # Cache all tiers
                        cls._cache = {
                            "m": fees.get("m", cls.FALLBACK_FEES["m"]),
                            "h": fees.get("h", cls.FALLBACK_FEES["h"]),
                            "vh": fees.get("vh", cls.FALLBACK_FEES["vh"]),
                        }
                        cls._cache_time = time.time()
                        
                        Logger.debug(f"[FEE] Fetched: {cls._cache}")
                        return cls._cache.get(tier, cls.FALLBACK_FEES.get(tier, 5000))
                
                Logger.warning(f"[FEE] API returned {response.status_code}")
                
        except Exception as e:
            Logger.error(f"[FEE] Priority fee fetch failed: {e}")
        
        return cls.FALLBACK_FEES.get(tier, 5000)
    
    @classmethod
    def get_fee_sync(cls, tier: str = "h") -> int:
        """
        Synchronous wrapper for get_fee_estimate.
        Uses cached value if available, otherwise fetches fresh.
        """
        # Return cached if fresh
        if time.time() - cls._cache_time < cls.CACHE_TTL and tier in cls._cache:
            return cls._cache[tier]
        
        # Try to fetch synchronously
        try:
            import requests
            response = requests.get(cls.BASE_URL, timeout=5.0)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    fees = data.get('data', {}).get('default', {})
                    cls._cache = {
                        "m": fees.get("m", cls.FALLBACK_FEES["m"]),
                        "h": fees.get("h", cls.FALLBACK_FEES["h"]),
                        "vh": fees.get("vh", cls.FALLBACK_FEES["vh"]),
                    }
                    cls._cache_time = time.time()
                    return cls._cache.get(tier, cls.FALLBACK_FEES.get(tier, 5000))
        except:
            pass
        
        return cls.FALLBACK_FEES.get(tier, 5000)
    
    @classmethod
    def get_all_tiers(cls) -> Dict[str, int]:
        """Get all fee tiers (may use cached values)."""
        return {
            "m": cls.get_fee_sync("m"),
            "h": cls.get_fee_sync("h"),
            "vh": cls.get_fee_sync("vh"),
        }


# ═══════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    async def test():
        print("=" * 60)
        print("Priority Fee Client Test")
        print("=" * 60)
        
        # Test async
        fee_h = await PriorityFeeClient.get_fee_estimate("h")
        print(f"\n✅ High priority fee: {fee_h} microLamports")
        
        fee_m = await PriorityFeeClient.get_fee_estimate("m")
        print(f"✅ Medium priority fee: {fee_m} microLamports")
        
        fee_vh = await PriorityFeeClient.get_fee_estimate("vh")
        print(f"✅ Very High priority fee: {fee_vh} microLamports")
        
        # Test sync
        print(f"\n📊 All tiers (sync): {PriorityFeeClient.get_all_tiers()}")
        
        print("\n" + "=" * 60)
    
    asyncio.run(test())
