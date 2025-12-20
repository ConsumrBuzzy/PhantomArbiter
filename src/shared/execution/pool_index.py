"""
Pool Index
===========
Unified pool index for Meteora + Orca pools with DB persistence.

Enables hybrid execution by mapping token pairs to available pools
and tracking pool performance for smart routing decisions.

Usage:
    index = PoolIndex()
    
    # Get pools for a pair
    pools = index.get_pools("SOL", "USDC")
    # Returns: {"meteora": "BGm1...", "orca": "HJPj..."}
    
    # Track execution performance
    index.record_execution("SOL/USDC", "meteora", success=True, latency_ms=450)
"""

import time
from typing import Dict, List, Optional, Any
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


@dataclass
class PoolEntry:
    """Entry for a pool in the index."""
    address: str
    dex: str  # "meteora" or "orca"
    token_a: str
    token_b: str
    token_a_symbol: str
    token_b_symbol: str
    liquidity: float = 0.0
    last_updated: float = 0.0
    success_count: int = 0
    fail_count: int = 0
    avg_latency_ms: float = 0.0


@dataclass
class PoolPair:
    """Available pools for a token pair."""
    pair: str  # e.g., "SOL/USDC"
    meteora_pool: Optional[str] = None
    orca_pool: Optional[str] = None
    preferred_dex: Optional[str] = None  # Based on performance
    meteora_success_rate: float = 0.0
    orca_success_rate: float = 0.0


class PoolIndex:
    """
    Unified pool index for cross-DEX execution.
    
    Features:
    - Automatic pool discovery for Meteora + Orca
    - Performance tracking per pool
    - Smart routing based on success rates
    - DB persistence for learned data
    """
    
    CACHE_TTL = 300  # 5 minutes
    
    def __init__(self):
        self._meteora_fetcher = MeteoraPoolFetcher()
        self._orca_fetcher = OrcaPoolFetcher()
        
        self._pool_cache: Dict[str, PoolPair] = {}
        self._cache_time = 0
        
        # Load persisted data
        self._load_from_db()
    
    def get_pools(self, token_a: str, token_b: str) -> Optional[PoolPair]:
        """
        Get available pools for a token pair.
        
        Args:
            token_a: First token symbol (e.g., "SOL")
            token_b: Second token symbol (e.g., "USDC")
            
        Returns:
            PoolPair with available pool addresses, or None
        """
        pair = f"{token_a.upper()}/{token_b.upper()}"
        reverse_pair = f"{token_b.upper()}/{token_a.upper()}"
        
        # Check cache
        if pair in self._pool_cache:
            return self._pool_cache[pair]
        if reverse_pair in self._pool_cache:
            return self._pool_cache[reverse_pair]
        
        # Fetch fresh
        return self._discover_pools(token_a, token_b)
    
    def get_pools_for_opportunity(self, opportunity) -> Optional[PoolPair]:
        """
        Get pools for a SpreadOpportunity.
        
        Args:
            opportunity: SpreadOpportunity with pair like "SOL/USDC"
            
        Returns:
            PoolPair if pools exist for both DEXs
        """
        tokens = opportunity.pair.split("/")
        if len(tokens) != 2:
            return None
        
        return self.get_pools(tokens[0], tokens[1])
    
    def _discover_pools(self, token_a: str, token_b: str) -> Optional[PoolPair]:
        """Discover pools from Meteora and Orca."""
        pair_name = f"{token_a.upper()}/{token_b.upper()}"
        
        meteora_pool = None
        orca_pool = None
        
        # Fetch Meteora pool
        try:
            mp = self._meteora_fetcher.get_best_pool(token_a, token_b)
            if mp:
                meteora_pool = mp.address
        except Exception as e:
            Logger.debug(f"Meteora lookup failed for {pair_name}: {e}")
        
        # Fetch Orca pool
        try:
            op = self._orca_fetcher.get_best_pool(token_a, token_b)
            if op:
                orca_pool = op.address
        except Exception as e:
            Logger.debug(f"Orca lookup failed for {pair_name}: {e}")
        
        if not meteora_pool and not orca_pool:
            return None
        
        pool_pair = PoolPair(
            pair=pair_name,
            meteora_pool=meteora_pool,
            orca_pool=orca_pool,
        )
        
        # Cache
        self._pool_cache[pair_name] = pool_pair
        
        # Persist to DB
        self._save_pool_to_db(pool_pair)
        
        Logger.debug(f"[POOL] Discovered {pair_name}: M={meteora_pool is not None}, O={orca_pool is not None}")
        return pool_pair
    
    def record_execution(
        self,
        pair: str,
        dex: str,
        success: bool,
        latency_ms: int = 0,
        error: Optional[str] = None
    ):
        """
        Record execution result for learning.
        
        Args:
            pair: Token pair (e.g., "SOL/USDC")
            dex: DEX used ("meteora" or "orca")
            success: Whether execution succeeded
            latency_ms: Execution latency
            error: Error message if failed
        """
        try:
            if db_manager:
                with db_manager.cursor(commit=True) as c:
                    c.execute("""
                        INSERT INTO pool_executions 
                        (pair, dex, success, latency_ms, error, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (pair, dex, success, latency_ms, error, time.time()))
            
            # Update cache
            if pair in self._pool_cache:
                pp = self._pool_cache[pair]
                if dex == "meteora":
                    if success:
                        pp.meteora_success_rate = self._calculate_success_rate(pair, "meteora")
                elif dex == "orca":
                    if success:
                        pp.orca_success_rate = self._calculate_success_rate(pair, "orca")
                
                # Update preferred DEX
                if pp.meteora_success_rate > pp.orca_success_rate:
                    pp.preferred_dex = "meteora"
                elif pp.orca_success_rate > pp.meteora_success_rate:
                    pp.preferred_dex = "orca"
                    
        except Exception as e:
            Logger.debug(f"Record execution error: {e}")
    
    def get_preferred_dex(self, pair: str) -> Optional[str]:
        """Get the preferred DEX for a pair based on historical performance."""
        pp = self._pool_cache.get(pair)
        if pp and pp.preferred_dex:
            return pp.preferred_dex
        
        # Check DB
        try:
            if db_manager:
                with db_manager.cursor() as c:
                    c.execute("""
                        SELECT dex, 
                               COUNT(*) as total,
                               SUM(CASE WHEN success THEN 1 ELSE 0 END) as successes
                        FROM pool_executions
                        WHERE pair = ? AND timestamp > ?
                        GROUP BY dex
                    """, (pair, time.time() - 86400))  # Last 24h
                    
                    rows = c.fetchall()
                    if rows:
                        best = max(rows, key=lambda r: r['successes'] / r['total'] if r['total'] > 0 else 0)
                        if best['total'] >= 3:  # Minimum samples
                            return best['dex']
        except:
            pass
        
        return None
    
    def _calculate_success_rate(self, pair: str, dex: str) -> float:
        """Calculate success rate for a DEX on a pair."""
        try:
            if db_manager:
                with db_manager.cursor() as c:
                    c.execute("""
                        SELECT COUNT(*) as total,
                               SUM(CASE WHEN success THEN 1 ELSE 0 END) as successes
                        FROM pool_executions
                        WHERE pair = ? AND dex = ? AND timestamp > ?
                    """, (pair, dex, time.time() - 86400))
                    
                    row = c.fetchone()
                    if row and row['total'] > 0:
                        return row['successes'] / row['total']
        except:
            pass
        return 0.0
    
    def _load_from_db(self):
        """Load persisted pool data from database."""
        try:
            if db_manager:
                with db_manager.cursor() as c:
                    c.execute("""
                        SELECT pair, meteora_pool, orca_pool, preferred_dex
                        FROM pool_index
                        WHERE updated_at > ?
                    """, (time.time() - 86400,))  # Last 24h
                    
                    for row in c.fetchall():
                        self._pool_cache[row['pair']] = PoolPair(
                            pair=row['pair'],
                            meteora_pool=row['meteora_pool'],
                            orca_pool=row['orca_pool'],
                            preferred_dex=row['preferred_dex'],
                        )
                    
                    Logger.debug(f"[POOL] Loaded {len(self._pool_cache)} pools from DB")
        except Exception as e:
            Logger.debug(f"Load from DB error: {e}")
    
    def _save_pool_to_db(self, pool_pair: PoolPair):
        """Persist pool to database."""
        try:
            if db_manager:
                with db_manager.cursor(commit=True) as c:
                    c.execute("""
                        INSERT OR REPLACE INTO pool_index 
                        (pair, meteora_pool, orca_pool, preferred_dex, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        pool_pair.pair,
                        pool_pair.meteora_pool,
                        pool_pair.orca_pool,
                        pool_pair.preferred_dex,
                        time.time()
                    ))
        except Exception as e:
            Logger.debug(f"Save pool error: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        meteora_count = sum(1 for p in self._pool_cache.values() if p.meteora_pool)
        orca_count = sum(1 for p in self._pool_cache.values() if p.orca_pool)
        both_count = sum(1 for p in self._pool_cache.values() if p.meteora_pool and p.orca_pool)
        
        return {
            "total_pairs": len(self._pool_cache),
            "meteora_pools": meteora_count,
            "orca_pools": orca_count,
            "both_dexs": both_count,
        }
    
    def can_use_unified_engine(self, opportunity) -> bool:
        """
        Check if an opportunity can be executed via unified engine.
        
        Requirements:
        - At least one pool exists (Meteora or Orca)
        - buy_dex or sell_dex matches available pools
        """
        pools = self.get_pools_for_opportunity(opportunity)
        if not pools:
            return False
        
        buy_dex = opportunity.buy_dex.lower() if opportunity.buy_dex else ""
        sell_dex = opportunity.sell_dex.lower() if opportunity.sell_dex else ""
        
        # Can use if we have pools for both sides
        buy_ok = (buy_dex == "meteora" and pools.meteora_pool) or (buy_dex == "orca" and pools.orca_pool)
        sell_ok = (sell_dex == "meteora" and pools.meteora_pool) or (sell_dex == "orca" and pools.orca_pool)
        
        return buy_ok or sell_ok


# Global instance
_pool_index: Optional[PoolIndex] = None

def get_pool_index() -> PoolIndex:
    """Get or create singleton pool index."""
    global _pool_index
    if _pool_index is None:
        _pool_index = PoolIndex()
    return _pool_index


# ═══════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("Pool Index Test")
    print("=" * 60)
    
    index = PoolIndex()
    
    # Test SOL/USDC
    pools = index.get_pools("SOL", "USDC")
    if pools:
        print(f"\n✅ SOL/USDC pools found:")
        print(f"   Meteora: {pools.meteora_pool}")
        print(f"   Orca: {pools.orca_pool}")
    else:
        print("\n❌ No pools found for SOL/USDC")
    
    # Stats
    print(f"\n📊 Stats: {index.get_stats()}")
    
    print("\n" + "=" * 60)
