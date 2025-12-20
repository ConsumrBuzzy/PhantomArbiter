"""
Meteora DLMM Pool Fetcher
==========================
Fetches and caches valid DLMM pool addresses from Meteora's public API.

This ensures we always have valid, high-liquidity pool IDs and avoids
"Invalid Account Discriminator" errors from stale/incorrect addresses.

Usage:
    fetcher = MeteoraPoolFetcher()
    pools = fetcher.get_pools_for_token("SOL", min_liquidity=50000)
    sol_usdc = fetcher.get_best_pool("SOL", "USDC")
"""

import requests
import time
from typing import Dict, List, Optional
from dataclasses import dataclass

try:
    from src.shared.system.logging import Logger
except ImportError:
    # Standalone execution
    class Logger:
        @staticmethod
        def info(msg): print(f"[INFO] {msg}")
        @staticmethod
        def warning(msg): print(f"[WARN] {msg}")
        @staticmethod
        def error(msg): print(f"[ERROR] {msg}")
        @staticmethod
        def debug(msg): pass


@dataclass
class MeteoraPool:
    """Represents a Meteora DLMM pool."""
    name: str
    address: str
    token_x_symbol: str
    token_y_symbol: str
    token_x_mint: str
    token_y_mint: str
    liquidity: float
    bin_step: int
    base_fee_bps: float
    
    def __repr__(self):
        return f"<MeteoraPool {self.name} TVL=${self.liquidity:,.0f} addr={self.address[:8]}...>"


class MeteoraPoolFetcher:
    """
    Fetches and caches Meteora DLMM pool information.
    
    Dynamically retrieves valid pool addresses from Meteora's API,
    ensuring we don't use stale or incorrect addresses.
    """
    
    API_URL = "https://dlmm-api.meteora.ag/pair/all"
    CACHE_TTL_SECONDS = 300  # 5 minutes
    
    def __init__(self):
        self._cache: List[MeteoraPool] = []
        self._cache_time: float = 0
    
    def _refresh_cache(self, force: bool = False) -> bool:
        """Refresh pool cache from Meteora API."""
        now = time.time()
        
        if not force and self._cache and (now - self._cache_time) < self.CACHE_TTL_SECONDS:
            return True  # Cache still valid
        
        try:
            Logger.debug("[METEORA] Fetching pools from API...")
            response = requests.get(self.API_URL, timeout=15)
            response.raise_for_status()
            pools_data = response.json()
            
            self._cache = []
            for pool in pools_data:
                try:
                    self._cache.append(MeteoraPool(
                        name=pool.get('name', ''),
                        address=pool.get('address', ''),
                        token_x_symbol=pool.get('mint_x_symbol', ''),
                        token_y_symbol=pool.get('mint_y_symbol', ''),
                        token_x_mint=pool.get('mint_x', ''),
                        token_y_mint=pool.get('mint_y', ''),
                        liquidity=float(pool.get('liquidity', 0)),
                        bin_step=int(pool.get('bin_step', 0)),
                        base_fee_bps=float(pool.get('base_fee_percentage', 0)) * 100,
                    ))
                except (KeyError, ValueError, TypeError):
                    continue
            
            self._cache_time = now
            Logger.info(f"[METEORA] Cached {len(self._cache)} pools")
            return True
            
        except requests.exceptions.RequestException as e:
            Logger.error(f"[METEORA] Failed to fetch pools: {e}")
            return False
        except Exception as e:
            Logger.error(f"[METEORA] Pool fetch error: {e}")
            return False
    
    def get_all_pools(self, min_liquidity: float = 0, force_refresh: bool = False) -> List[MeteoraPool]:
        """
        Get all pools with optional liquidity filter.
        
        Args:
            min_liquidity: Minimum TVL in USD
            force_refresh: Force refresh from API
            
        Returns:
            List of MeteoraPool objects sorted by liquidity
        """
        self._refresh_cache(force=force_refresh)
        
        pools = [p for p in self._cache if p.liquidity >= min_liquidity]
        pools.sort(key=lambda x: x.liquidity, reverse=True)
        return pools
    
    def get_pools_for_token(
        self, 
        token_symbol: str, 
        min_liquidity: float = 10000
    ) -> List[MeteoraPool]:
        """
        Get pools containing a specific token.
        
        Args:
            token_symbol: Token symbol to search for (e.g., "SOL", "USDC")
            min_liquidity: Minimum TVL in USD
            
        Returns:
            List of matching pools sorted by liquidity
        """
        self._refresh_cache()
        
        token_upper = token_symbol.upper()
        pools = [
            p for p in self._cache 
            if (token_upper in p.token_x_symbol.upper() or 
                token_upper in p.token_y_symbol.upper())
            and p.liquidity >= min_liquidity
        ]
        pools.sort(key=lambda x: x.liquidity, reverse=True)
        return pools
    
    def get_best_pool(
        self, 
        token_a: str, 
        token_b: str, 
        min_liquidity: float = 5000
    ) -> Optional[MeteoraPool]:
        """
        Get the highest liquidity pool for a token pair.
        
        Args:
            token_a: First token symbol
            token_b: Second token symbol
            min_liquidity: Minimum TVL
            
        Returns:
            Best matching pool or None
        """
        self._refresh_cache()
        
        a_upper = token_a.upper()
        b_upper = token_b.upper()
        
        candidates = []
        for pool in self._cache:
            x_sym = pool.token_x_symbol.upper()
            y_sym = pool.token_y_symbol.upper()
            
            if ((a_upper in x_sym and b_upper in y_sym) or
                (b_upper in x_sym and a_upper in y_sym)):
                if pool.liquidity >= min_liquidity:
                    candidates.append(pool)
        
        if not candidates:
            return None
        
        # Return highest liquidity
        return max(candidates, key=lambda x: x.liquidity)
    
    def get_pool_by_address(self, address: str) -> Optional[MeteoraPool]:
        """Get pool info by address."""
        self._refresh_cache()
        
        for pool in self._cache:
            if pool.address == address:
                return pool
        return None


# ═══════════════════════════════════════════════════════════════════
# STANDALONE EXECUTION
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("Meteora DLMM Pool Fetcher")
    print("=" * 70)
    
    fetcher = MeteoraPoolFetcher()
    
    # Fetch top SOL pools
    print("\n📊 Top SOL/USDC Pools by Liquidity:")
    print("-" * 70)
    
    sol_pools = fetcher.get_pools_for_token("SOL", min_liquidity=50000)
    for i, pool in enumerate(sol_pools[:10], 1):
        print(f"  {i}. {pool.name:<20} | TVL: ${pool.liquidity:>12,.0f} | Bin: {pool.bin_step:>3}")
        print(f"     Address: {pool.address}")
    
    # Get best SOL/USDC pool
    print("\n🎯 Best Pool for SOL/USDC:")
    best = fetcher.get_best_pool("SOL", "USDC")
    if best:
        print(f"   {best.name}")
        print(f"   Address: {best.address}")
        print(f"   Liquidity: ${best.liquidity:,.0f}")
        print(f"   Bin Step: {best.bin_step}")
    else:
        print("   ❌ No pool found")
    
    print("\n" + "=" * 70)
