"""
Pool Registry
=============
Smart tracking of DEX coverage for tokens.

Tracks which DEXs have liquidity for each token to:
1. Skip scanning dead DEXs (optimization)
2. Prioritize tokens with multi-DEX coverage (arb opportunities)
3. Auto-update during scans

Usage:
    registry = PoolRegistry()
    registry.update_token("BONK", mint, has_ray=True, has_orca=True)
    coverage = registry.get_coverage("BONK")
"""

import time
from typing import Dict, Optional, Any
from dataclasses import dataclass

try:
    from src.shared.system.logging import Logger
    from src.shared.system.db_manager import db_manager
except ImportError:
    class Logger:
        @staticmethod
        def info(msg): print(f"[INFO] {msg}")
        @staticmethod
        def debug(msg): pass
    db_manager = None


@dataclass
class TokenCoverage:
    """DEX coverage for a token."""
    mint: str
    symbol: str
    has_jupiter: bool = True  # Aggregator always covers if others do
    has_raydium: bool = False
    has_orca: bool = False
    has_meteora: bool = False
    last_checked: float = 0.0
    
    @property
    def dex_count(self) -> int:
        return sum([self.has_raydium, self.has_orca, self.has_meteora])


class PoolRegistry:
    """
    Registry for tracking DEX pool availability per token.
    Singleton pattern.
    """
    
    def __init__(self):
        self._cache: Dict[str, TokenCoverage] = {}
        self._load_from_db()
    
    def update_coverage(
        self,
        symbol: str,
        mint: str,
        has_raydium: bool = None,
        has_orca: bool = None,
        has_meteora: bool = None
    ):
        """
        Update DEX coverage for a token.
        Only updates provided fields (None = keep existing).
        """
        try:
            # Get existing or new
            coverage = self._cache.get(mint, TokenCoverage(mint=mint, symbol=symbol))
            
            # Update fields if provided
            if has_raydium is not None: coverage.has_raydium = has_raydium
            if has_orca is not None: coverage.has_orca = has_orca
            if has_meteora is not None: coverage.has_meteora = has_meteora
            
            coverage.last_checked = time.time()
            self._cache[mint] = coverage
            
            # Persist
            self._save_to_db(coverage)
            
        except Exception as e:
            Logger.debug(f"[REGISTRY] Update error: {e}")
    
    def get_coverage(self, mint: str) -> Optional[TokenCoverage]:
        """Get DEX coverage for a token mint."""
        return self._cache.get(mint)
    
    def get_arb_candidates(self, min_dexs: int = 2) -> list:
        """
        Get tokens suitable for arbitrage (present on multiple DEXs).
        Returns list of (symbol, mint) tuples.
        """
        candidates = []
        for cov in self._cache.values():
            if cov.dex_count >= min_dexs:
                candidates.append((cov.symbol, cov.mint))
        return candidates
    
    def _load_from_db(self):
        """Load registry from DB."""
        try:
            if db_manager:
                with db_manager.cursor() as c:
                    c.execute("SELECT * FROM pool_registry")
                    for row in c.fetchall():
                        self._cache[row['mint']] = TokenCoverage(
                            mint=row['mint'],
                            symbol=row['symbol'],
                            has_jupiter=bool(row['has_jupiter']),
                            has_raydium=bool(row['has_raydium']),
                            has_orca=bool(row['has_orca']),
                            has_meteora=bool(row['has_meteora']),
                            last_checked=row['last_checked']
                        )
        except Exception as e:
            Logger.debug(f"[REGISTRY] Load error: {e}")
    
    def _save_to_db(self, cov: TokenCoverage):
        """Save token coverage to DB."""
        try:
            if db_manager:
                with db_manager.cursor(commit=True) as c:
                    c.execute("""
                        INSERT INTO pool_registry 
                        (mint, symbol, has_jupiter, has_raydium, has_orca, has_meteora, last_checked)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(mint) DO UPDATE SET
                            has_jupiter=excluded.has_jupiter,
                            has_raydium=excluded.has_raydium,
                            has_orca=excluded.has_orca,
                            has_meteora=excluded.has_meteora,
                            last_checked=excluded.last_checked
                    """, (
                        cov.mint, cov.symbol,
                        cov.has_jupiter, cov.has_raydium, 
                        cov.has_orca, cov.has_meteora,
                        cov.last_checked
                    ))
        except Exception as e:
            Logger.debug(f"[REGISTRY] Save error: {e}")


# Global instance
_pool_registry: Optional[PoolRegistry] = None

def get_pool_registry() -> PoolRegistry:
    """Get or create singleton pool registry."""
    global _pool_registry
    if _pool_registry is None:
        _pool_registry = PoolRegistry()
    return _pool_registry
