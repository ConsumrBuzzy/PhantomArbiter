"""
Pool Scanner
=============
Background pool discovery for Meteora and Orca.

Runs periodically to find new pools for existing tokens,
and suggests new pairs for pod expansion.

Usage:
    scanner = PoolScanner()
    await scanner.discover_all()
    new_pairs = scanner.get_suggested_pairs()
"""

import time
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

try:
    from src.shared.system.logging import Logger
    from src.shared.system.db_manager import db_manager
except ImportError:
    class Logger:
        @staticmethod
        def info(msg): print(f"[INFO] {msg}")
        @staticmethod
        def warning(msg): print(f"[WARN] {msg}")
        @staticmethod
        def debug(msg): pass
    db_manager = None

from src.shared.execution.pool_fetcher import MeteoraPoolFetcher
from src.shared.execution.orca_pool_fetcher import OrcaPoolFetcher


# Well-known token mints for discovery
KNOWN_TOKENS = {
    "SOL": "So11111111111111111111111111111111111111112",
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "WIF": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
    "JUP": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    "RAY": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
    "ORCA": "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE",
    "JITO": "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn",
    "PYTH": "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",
    "MSOL": "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",
    "JITOSOL": "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn",
    "PENGU": "2zMMhcVQEXDtdE6vsFS7S7D5oUodfJHE8vd1gnBouauv",
    "POPCAT": "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr",
    "GOAT": "CzLSujWBLFsSjncfkh59rUFqvafWcY5tzedWJSuypump",
    "FARTCOIN": "9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump",
}


@dataclass
class DiscoveredPool:
    """A discovered pool with metadata."""
    pair: str
    dex: str
    pool_address: str
    base_mint: str
    quote_mint: str
    liquidity: float = 0.0
    discovered_at: float = field(default_factory=time.time)


class PoolScanner:
    """
    Background pool scanner for Meteora and Orca.
    
    Features:
    - Discovers pools for known tokens
    - Suggests new pod pairs
    - Persists to database
    - Runs on configurable interval
    """
    
    def __init__(self):
        self._meteora = MeteoraPoolFetcher()
        self._orca = OrcaPoolFetcher()
        
        self._discovered: Dict[str, DiscoveredPool] = {}
        self._last_scan = 0
        
    async def discover_all(self) -> int:
        """
        Discover pools for all known tokens.
        
        Returns:
            Number of new pools discovered
        """
        new_count = 0
        quote_tokens = ["USDC", "SOL"]
        
        Logger.info("[SCANNER] 🔍 Starting pool discovery...")
        
        for symbol, mint in KNOWN_TOKENS.items():
            if symbol in quote_tokens:
                continue
                
            for quote in quote_tokens:
                quote_mint = KNOWN_TOKENS[quote]
                pair_name = f"{symbol}/{quote}"
                
                # Skip if already discovered recently
                if pair_name in self._discovered:
                    if time.time() - self._discovered[pair_name].discovered_at < 3600:
                        continue
                
                # Try Meteora
                try:
                    mp = self._meteora.get_best_pool(symbol, quote)
                    if mp:
                        pool = DiscoveredPool(
                            pair=pair_name,
                            dex="meteora",
                            pool_address=mp.address,
                            base_mint=mint,
                            quote_mint=quote_mint,
                            liquidity=mp.tvl_usd if hasattr(mp, 'tvl_usd') else 0,
                        )
                        self._discovered[f"{pair_name}_meteora"] = pool
                        new_count += 1
                        self._save_to_db(pool)
                except Exception as e:
                    Logger.debug(f"[SCANNER] Meteora {pair_name}: {e}")
                
                # Try Orca
                try:
                    op = self._orca.get_best_pool(symbol, quote)
                    if op:
                        pool = DiscoveredPool(
                            pair=pair_name,
                            dex="orca",
                            pool_address=op.address,
                            base_mint=mint,
                            quote_mint=quote_mint,
                            liquidity=op.liquidity,
                        )
                        self._discovered[f"{pair_name}_orca"] = pool
                        new_count += 1
                        self._save_to_db(pool)
                except Exception as e:
                    Logger.debug(f"[SCANNER] Orca {pair_name}: {e}")
                
                # Try Raydium (CLMM + Standard) (V98)
                try:
                    from src.shared.execution.raydium_bridge import RaydiumBridge
                    # Lazy init bridge if not exists?
                    bridge = RaydiumBridge()
                    res = bridge.discover_pool(mint, quote_mint)
                    
                    if res and res.get('success'):
                        pool_id = res.get('poolId')
                        pool_type = res.get('type')
                        
                        # We map it to "raydium_clmm" or "raydium_standard" dex
                        # DiscoveredPool only has 'dex' string. We can use that.
                        dex_name = "raydium_clmm" if pool_type == 'clmm' else "raydium_standard"
                        
                        pool = DiscoveredPool(
                            pair=pair_name,
                            dex=dex_name,
                            pool_address=pool_id,
                            base_mint=mint,
                            quote_mint=quote_mint,
                            liquidity=res.get('tvl', 0)
                        )
                        self._discovered[f"{pair_name}_{dex_name}"] = pool
                        new_count += 1
                        self._save_to_db(pool)
                except Exception as e:
                    Logger.debug(f"[SCANNER] Raydium {pair_name}: {e}")
        
        self._last_scan = time.time()
        Logger.info(f"[SCANNER] ✅ Discovered {new_count} pools")
        
        return new_count
    
    def get_discovered_pools(self) -> List[DiscoveredPool]:
        """Get all discovered pools."""
        return list(self._discovered.values())
    
    def get_suggested_pairs(self, min_liquidity: float = 10000) -> List[Tuple[str, str, str, str, str]]:
        """
        Get suggested pairs for pod expansion.
        
        Returns:
            List of (pair_name, base_mint, quote_mint, dex, pool_address)
        """
        suggestions = []
        
        for pool in self._discovered.values():
            if pool.liquidity >= min_liquidity:
                suggestions.append((
                    pool.pair,
                    pool.base_mint,
                    pool.quote_mint,
                    pool.dex,
                    pool.pool_address,
                ))
        
        # Sort by liquidity
        suggestions.sort(key=lambda x: self._discovered.get(f"{x[0]}_{x[3]}", DiscoveredPool("", "", "", "", "")).liquidity, reverse=True)
        
        return suggestions
    
    def _save_to_db(self, pool: DiscoveredPool):
        """Persist discovered pool to database."""
        try:
            if db_manager:
                with db_manager.cursor(commit=True) as c:
                    # V98: Safe UPSERT to avoid nuking other DEX columns
                    dex_col = None
                    if pool.dex == "meteora": dex_col = "meteora_pool"
                    elif pool.dex == "orca": dex_col = "orca_pool"
                    elif pool.dex == "raydium_clmm": dex_col = "raydium_clmm_pool"
                    elif pool.dex == "raydium_standard": dex_col = "raydium_standard_pool"
                    
                    if dex_col:
                        query = f"""
                            INSERT INTO pool_index (pair, {dex_col}, updated_at)
                            VALUES (?, ?, ?)
                            ON CONFLICT(pair) DO UPDATE SET
                                {dex_col}=excluded.{dex_col},
                                updated_at=excluded.updated_at
                        """
                        c.execute(query, (pool.pair, pool.pool_address, time.time()))
        except Exception as e:
            Logger.debug(f"[SCANNER] DB save error: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get scanner statistics."""
        meteora_count = sum(1 for p in self._discovered.values() if p.dex == "meteora")
        orca_count = sum(1 for p in self._discovered.values() if p.dex == "orca")
        
        return {
            "total_discovered": len(self._discovered),
            "meteora_pools": meteora_count,
            "orca_pools": orca_count,
            "last_scan": self._last_scan,
        }


# ═══════════════════════════════════════════════════════════════════
# DIRECT_POOLS POD DATA
# ═══════════════════════════════════════════════════════════════════

# Pre-verified high-liquidity pools for direct execution
DIRECT_POOLS_METEORA = [
    # ("PAIR", "BASE_MINT", "QUOTE_MINT", "POOL_ADDRESS")
    ("SOL/USDC", "So11111111111111111111111111111111111111112", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y"),
]

DIRECT_POOLS_ORCA = [
    ("SOL/USDC", "So11111111111111111111111111111111111111112", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "HJPjoWUrhoZzkNfRpHuieeFk9WcZWjwy6PBjZ81ngndJ"),
    ("BONK/SOL", "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", "So11111111111111111111111111111111111111112", "5P6n5omLbLbP4kaPGL8etqQAHEx2UCkaUyvjLDnwV4EY"),
    ("WIF/SOL", "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", "So11111111111111111111111111111111111111112", "EP2ib6dYdEeqD8MfE2ezHCxX3kP3K2eLKkirfPm5eyMx"),
    ("JitoSOL/SOL", "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn", "So11111111111111111111111111111111111111112", "2eicbpitfraZx4MELLxBEHQZT8EPo2j6jEBAz7jTKFPT"),
    ("mSOL/SOL", "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So", "So11111111111111111111111111111111111111112", "2AEWSvUds1wsufnsDPCXjFsJCMJH5SNNm7fSF4kxys9a"),
]


def build_direct_pools_pod() -> List[Tuple[str, str, str]]:
    """
    Build pairs list for DIRECT_POOLS pod.
    
    Returns:
        List of (pair_name, base_mint, quote_mint) tuples
        compatible with arbiter.py pair format
    """
    pairs = []
    seen = set()
    
    for pair_name, base_mint, quote_mint, _ in DIRECT_POOLS_METEORA:
        if pair_name not in seen:
            pairs.append((pair_name, base_mint, quote_mint))
            seen.add(pair_name)
    
    for pair_name, base_mint, quote_mint, _ in DIRECT_POOLS_ORCA:
        if pair_name not in seen:
            pairs.append((pair_name, base_mint, quote_mint))
            seen.add(pair_name)
    
    return pairs


# ═══════════════════════════════════════════════════════════════════
# AUTO-DISCOVERY ON STARTUP
# ═══════════════════════════════════════════════════════════════════

async def run_startup_discovery():
    """Run pool discovery on startup (non-blocking)."""
    scanner = PoolScanner()
    count = await scanner.discover_all()
    Logger.info(f"[STARTUP] Discovered {count} pools for existing tokens")
    return scanner


# ═══════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    async def test():
        print("=" * 60)
        print("Pool Scanner Test")
        print("=" * 60)
        
        scanner = PoolScanner()
        
        print("\n🔍 Running discovery...")
        count = await scanner.discover_all()
        
        print(f"\n✅ Discovered {count} pools")
        print(f"📊 Stats: {scanner.get_stats()}")
        
        print("\n📋 Suggested pairs:")
        for pair in scanner.get_suggested_pairs()[:10]:
            print(f"   {pair[0]} on {pair[3]}: {pair[4][:16]}...")
        
        print("\n📦 DIRECT_POOLS pod:")
        for pair in build_direct_pools_pod():
            print(f"   {pair}")
        
        print("\n" + "=" * 60)
    
    asyncio.run(test())
