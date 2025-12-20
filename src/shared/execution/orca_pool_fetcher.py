"""
Orca Pool Fetcher
==================
Fetches and caches Orca Whirlpool addresses from the Orca API.

Mirrors the interface of MeteoraPoolFetcher for consistency.

Usage:
    fetcher = OrcaPoolFetcher()
    pool = fetcher.get_best_pool("SOL", "USDC")
    print(pool.address)  # Whirlpool address
"""

import os
import time
import requests
from typing import Dict, List, Optional
from dataclasses import dataclass

try:
    from src.shared.system.logging import Logger
except ImportError:
    class Logger:
        @staticmethod
        def info(msg): print(f"[INFO] {msg}")
        @staticmethod
        def warning(msg): print(f"[WARN] {msg}")
        @staticmethod
        def error(msg): print(f"[ERROR] {msg}")
        @staticmethod
        def debug(msg): pass


# Well-known Orca Whirlpool addresses for major pairs
# These are the most liquid whirlpools on mainnet
KNOWN_WHIRLPOOLS = {
    "SOL/USDC": {
        "address": "HJPjoWUrhoZzkNfRpHuieeFk9WcZWjwy6PBjZ81ngndJ",
        "token_a": "So11111111111111111111111111111111111111112",
        "token_b": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "tick_spacing": 64,
    },
    "SOL/USDT": {
        "address": "4GpUivZ2jvZqQ3vJRsoq5PwnYv6gdV9fJ9BzHT2JcRr7",
        "token_a": "So11111111111111111111111111111111111111112",
        "token_b": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
        "tick_spacing": 64,
    },
    "USDC/USDT": {
        "address": "4fuUiYxTQ6QCrdSq9ouBYcTM7bqSwYTSyLueGZLTy4T4",
        "token_a": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "token_b": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
        "tick_spacing": 1,
    },
    "mSOL/SOL": {
        "address": "2AEWSvUds1wsufnsDPCXjFsJCMJH5SNNm7fSF4kxys9a",
        "token_a": "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",
        "token_b": "So11111111111111111111111111111111111111112",
        "tick_spacing": 1,
    },
    "JitoSOL/SOL": {
        "address": "2eicbpitfraZx4MELLxBEHQZT8EPo2j6jEBAz7jTKFPT",
        "token_a": "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn",
        "token_b": "So11111111111111111111111111111111111111112",
        "tick_spacing": 1,
    },
    "BONK/SOL": {
        "address": "5P6n5omLbLbP4kaPGL8etqQAHEx2UCkaUyvjLDnwV4EY",
        "token_a": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
        "token_b": "So11111111111111111111111111111111111111112",
        "tick_spacing": 64,
    },
    "WIF/SOL": {
        "address": "EP2ib6dYdEeqD8MfE2ezHCxX3kP3K2eLKkirfPm5eyMx",
        "token_a": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
        "token_b": "So11111111111111111111111111111111111111112",
        "tick_spacing": 64,
    },
}

# Token symbol to mint mapping
TOKEN_MINTS = {
    "SOL": "So11111111111111111111111111111111111111112",
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "MSOL": "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",
    "JITOSOL": "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn",
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "WIF": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
}


@dataclass
class OrcaPoolInfo:
    """Information about an Orca Whirlpool."""
    address: str
    name: str
    token_a_mint: str
    token_b_mint: str
    token_a_symbol: str
    token_b_symbol: str
    tick_spacing: int
    liquidity: float = 0.0


class OrcaPoolFetcher:
    """
    Fetches Orca Whirlpool pool information.
    
    Uses a combination of:
    1. Known high-liquidity pools (hardcoded for speed)
    2. Orca API for dynamic discovery
    """
    
    ORCA_API_URL = "https://api.mainnet.orca.so/v1/whirlpool/list"
    CACHE_TTL = 300  # 5 minutes
    
    def __init__(self):
        self._cache: Dict[str, OrcaPoolInfo] = {}
        self._all_pools: List[OrcaPoolInfo] = []
        self._cache_time = 0
        
        # Pre-populate with known pools
        self._load_known_pools()
    
    def _load_known_pools(self):
        """Load known high-liquidity pools."""
        for pair_name, pool_data in KNOWN_WHIRLPOOLS.items():
            tokens = pair_name.split("/")
            pool = OrcaPoolInfo(
                address=pool_data["address"],
                name=pair_name,
                token_a_mint=pool_data["token_a"],
                token_b_mint=pool_data["token_b"],
                token_a_symbol=tokens[0],
                token_b_symbol=tokens[1],
                tick_spacing=pool_data["tick_spacing"],
                liquidity=1_000_000,  # Assume high liquidity for known pools
            )
            self._cache[pool.address] = pool
            self._all_pools.append(pool)
        
        Logger.debug(f"[ORCA] Loaded {len(KNOWN_WHIRLPOOLS)} known pools")
    
    def _refresh_cache(self) -> bool:
        """Refresh pool cache from Orca API."""
        if time.time() - self._cache_time < self.CACHE_TTL:
            return True
        
        try:
            Logger.debug("[ORCA] Refreshing pool cache from API...")
            response = requests.get(self.ORCA_API_URL, timeout=10)
            
            if response.status_code != 200:
                Logger.warning(f"[ORCA] API returned {response.status_code}")
                return False
            
            data = response.json()
            whirlpools = data.get("whirlpools", [])
            
            for wp in whirlpools:
                address = wp.get("address", "")
                if address in self._cache:
                    continue  # Skip known pools
                
                pool = OrcaPoolInfo(
                    address=address,
                    name=f"{wp.get('tokenA', {}).get('symbol', '?')}/{wp.get('tokenB', {}).get('symbol', '?')}",
                    token_a_mint=wp.get("tokenA", {}).get("mint", ""),
                    token_b_mint=wp.get("tokenB", {}).get("mint", ""),
                    token_a_symbol=wp.get("tokenA", {}).get("symbol", ""),
                    token_b_symbol=wp.get("tokenB", {}).get("symbol", ""),
                    tick_spacing=wp.get("tickSpacing", 64),
                    liquidity=float(wp.get("tvl", 0)),
                )
                
                self._cache[address] = pool
                self._all_pools.append(pool)
            
            self._cache_time = time.time()
            Logger.debug(f"[ORCA] Cached {len(self._all_pools)} total pools")
            return True
            
        except Exception as e:
            Logger.warning(f"[ORCA] Cache refresh failed: {e}")
            return False
    
    def get_all_pools(self) -> List[OrcaPoolInfo]:
        """Get all known pools."""
        self._refresh_cache()
        return self._all_pools
    
    def get_pools_for_token(self, symbol: str) -> List[OrcaPoolInfo]:
        """Get all pools involving a specific token."""
        symbol_upper = symbol.upper()
        self._refresh_cache()
        
        return [
            p for p in self._all_pools
            if symbol_upper in p.name.upper()
        ]
    
    def get_best_pool(
        self,
        token_a: str,
        token_b: str,
        min_liquidity: float = 0
    ) -> Optional[OrcaPoolInfo]:
        """
        Get the best pool for a token pair.
        
        Args:
            token_a: First token symbol (e.g., "SOL")
            token_b: Second token symbol (e.g., "USDC")
            min_liquidity: Minimum TVL requirement
            
        Returns:
            OrcaPoolInfo or None
        """
        self._refresh_cache()
        
        a = token_a.upper()
        b = token_b.upper()
        
        # Check both orderings
        pair1 = f"{a}/{b}"
        pair2 = f"{b}/{a}"
        
        candidates = [
            p for p in self._all_pools
            if p.name.upper() in [pair1, pair2]
            and (min_liquidity == 0 or p.liquidity >= min_liquidity)
        ]
        
        if not candidates:
            Logger.warning(f"[ORCA] No pool found for {pair1}")
            return None
        
        # Sort by liquidity (highest first)
        candidates.sort(key=lambda x: x.liquidity, reverse=True)
        return candidates[0]
    
    def get_pool_by_address(self, address: str) -> Optional[OrcaPoolInfo]:
        """Get pool info by address."""
        return self._cache.get(address)


# ═══════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("Orca Pool Fetcher Test")
    print("=" * 60)
    
    fetcher = OrcaPoolFetcher()
    
    print(f"\n📊 Total pools: {len(fetcher.get_all_pools())}")
    
    # Test SOL/USDC
    pool = fetcher.get_best_pool("SOL", "USDC")
    if pool:
        print(f"\n✅ SOL/USDC Whirlpool:")
        print(f"   Address: {pool.address}")
        print(f"   Name: {pool.name}")
        print(f"   Tick Spacing: {pool.tick_spacing}")
    else:
        print("\n❌ No SOL/USDC pool found")
    
    # List all known pools
    print("\n📋 Known Whirlpools:")
    for p in fetcher.get_all_pools()[:5]:
        print(f"   {p.name}: {p.address[:16]}...")
    
    print("\n" + "=" * 60)
