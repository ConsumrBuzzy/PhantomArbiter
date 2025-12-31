"""
V49.0: Orca Pool Discovery
===========================
Discovers and ranks Whirlpools by volume, TVL, and fee APR.

Methods:
1. API-based: Uses Orca's public pools API (preferred)
2. RPC-based: Scans known pools via Solana RPC
3. Browser-based: Fallback scraping from Orca website

Usage:
    scraper = OrcaPoolScraper()
    pools = scraper.discover_top_pools(limit=10)
"""

import time
import requests
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor

from src.shared.system.logging import Logger
from src.liquidity.orca_adapter import get_orca_adapter


@dataclass
class PoolInfo:
    """Summarized pool information for ranking."""

    address: str
    token_a_symbol: str
    token_b_symbol: str
    token_a_mint: str
    token_b_mint: str
    fee_rate_pct: float
    tick_spacing: int
    tvl_usd: float = 0.0
    volume_24h_usd: float = 0.0
    fee_apr_pct: float = 0.0
    price: float = 0.0
    liquidity: int = 0
    last_updated: float = field(default_factory=time.time)

    @property
    def pair_name(self) -> str:
        return f"{self.token_a_symbol}/{self.token_b_symbol}"

    def __repr__(self):
        return f"<Pool {self.pair_name} TVL=${self.tvl_usd / 1e6:.2f}M APR={self.fee_apr_pct:.1f}%>"


class OrcaPoolScraper:
    """
    V49.0: Discovers and ranks Orca Whirlpools.

    Periodically scans for the best pools to provide liquidity.
    """

    # Orca API endpoints
    ORCA_API_BASE = "https://api.orca.so"
    ORCA_POOLS_ENDPOINT = "/allPools"  # May require different endpoint

    # Well-known high-volume pools (fallback)
    SEED_POOLS = [
        "Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE",  # Active pool from Orca
    ]

    # Token symbol mapping (mint -> symbol)
    TOKEN_SYMBOLS = {
        "So11111111111111111111111111111111111111112": "SOL",
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
        "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT",
        "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So": "mSOL",
        "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj": "stSOL",
        "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263": "BONK",
        "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": "JUP",
    }

    def __init__(self):
        """Initialize pool scraper."""
        self.adapter = get_orca_adapter()
        self._pool_cache: Dict[str, PoolInfo] = {}
        self._last_scan_time = 0
        self._scan_interval = 300  # 5 minutes
        Logger.info("   🔍 [ORCA] Pool Scraper Initialized")

    def discover_top_pools(
        self, limit: int = 10, min_tvl_usd: float = 100_000, force_refresh: bool = False
    ) -> List[PoolInfo]:
        """
        Discover and rank top pools by TVL and volume.

        Args:
            limit: Maximum number of pools to return
            min_tvl_usd: Minimum TVL filter
            force_refresh: Force re-scan even if cache is fresh

        Returns:
            List of PoolInfo sorted by TVL (descending)
        """
        # Check cache freshness
        now = time.time()
        if not force_refresh and (now - self._last_scan_time) < self._scan_interval:
            cached = list(self._pool_cache.values())
            return sorted(cached, key=lambda p: p.tvl_usd, reverse=True)[:limit]

        Logger.info("   🔍 [ORCA] Scanning for pools...")

        # Try API first, fall back to RPC scanning
        pools = self._fetch_via_api()

        if not pools:
            Logger.info("   🔍 [ORCA] API unavailable, using RPC scan...")
            pools = self._scan_via_rpc()

        # Filter and rank
        filtered = [p for p in pools if p.tvl_usd >= min_tvl_usd]
        ranked = sorted(filtered, key=lambda p: p.tvl_usd, reverse=True)

        # Update cache
        self._pool_cache = {p.address: p for p in ranked}
        self._last_scan_time = now

        Logger.info(
            f"   🔍 [ORCA] Found {len(ranked)} pools (TVL > ${min_tvl_usd / 1000:.0f}K)"
        )

        return ranked[:limit]

    def _fetch_via_api(self) -> List[PoolInfo]:
        """
        Fetch pool data from Orca's public API.

        Returns empty list if API is unavailable.
        """
        try:
            # Try different API endpoints
            endpoints = [
                "https://api.mainnet.orca.so/v1/whirlpool/list",
                "https://api.orca.so/v1/pools",
            ]

            for endpoint in endpoints:
                try:
                    response = requests.get(endpoint, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        return self._parse_api_response(data)
                except Exception:
                    continue

            return []

        except Exception as e:
            Logger.debug(f"   🔍 [ORCA] API fetch failed: {e}")
            return []

    def _parse_api_response(self, data: Any) -> List[PoolInfo]:
        """Parse Orca API response into PoolInfo objects."""
        pools = []

        # Handle different response formats
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict) and "whirlpools" in data:
            items = data["whirlpools"]
        elif isinstance(data, dict) and "pools" in data:
            items = data["pools"]
        else:
            return []

        for item in items:
            try:
                pool = PoolInfo(
                    address=item.get("address", ""),
                    token_a_symbol=item.get("tokenA", {}).get("symbol", "?"),
                    token_b_symbol=item.get("tokenB", {}).get("symbol", "?"),
                    token_a_mint=item.get("tokenA", {}).get("mint", ""),
                    token_b_mint=item.get("tokenB", {}).get("mint", ""),
                    fee_rate_pct=item.get("feeRate", 0) / 10000,
                    tick_spacing=item.get("tickSpacing", 0),
                    tvl_usd=item.get("tvl", 0),
                    volume_24h_usd=item.get("volume", {}).get("day", 0),
                    fee_apr_pct=item.get("feeApr", 0) * 100,
                    price=item.get("price", 0),
                    liquidity=item.get("liquidity", 0),
                )
                pools.append(pool)
            except Exception:
                continue

        return pools

    def _scan_via_rpc(self) -> List[PoolInfo]:
        """
        Scan known pools via RPC (fallback method).

        Uses seed pools and expands discovery from there.
        """
        pools = []

        # Scan seed pools in parallel
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(self._fetch_pool_info, addr): addr
                for addr in self.SEED_POOLS
            }

            for future in futures:
                try:
                    pool_info = future.result(timeout=10)
                    if pool_info:
                        pools.append(pool_info)
                except Exception:
                    continue

        return pools

    def _fetch_pool_info(self, address: str) -> Optional[PoolInfo]:
        """Fetch pool info from RPC and convert to PoolInfo."""
        state = self.adapter.get_whirlpool_state(address)

        if not state:
            return None

        # Look up token symbols
        symbol_a = self.TOKEN_SYMBOLS.get(state.token_mint_a, state.token_mint_a[:8])
        symbol_b = self.TOKEN_SYMBOLS.get(state.token_mint_b, state.token_mint_b[:8])

        return PoolInfo(
            address=address,
            token_a_symbol=symbol_a,
            token_b_symbol=symbol_b,
            token_a_mint=state.token_mint_a,
            token_b_mint=state.token_mint_b,
            fee_rate_pct=state.fee_rate / 10000,
            tick_spacing=state.tick_spacing,
            tvl_usd=state.tvl_usd,
            volume_24h_usd=state.volume_24h,
            fee_apr_pct=state.fee_apr,
            price=state.price,
            liquidity=state.liquidity,
        )

    def get_pool_by_pair(self, symbol_a: str, symbol_b: str) -> Optional[PoolInfo]:
        """
        Find a pool by token pair symbols.

        Args:
            symbol_a: First token symbol (e.g., "SOL")
            symbol_b: Second token symbol (e.g., "USDC")

        Returns:
            PoolInfo or None
        """
        # Ensure cache is fresh
        self.discover_top_pools(force_refresh=False)

        pair_names = [
            f"{symbol_a}/{symbol_b}",
            f"{symbol_b}/{symbol_a}",
        ]

        for pool in self._pool_cache.values():
            if pool.pair_name in pair_names:
                return pool

        return None

    def display_top_pools(self, limit: int = 5) -> None:
        """Print formatted table of top pools."""
        pools = self.discover_top_pools(limit=limit, min_tvl_usd=0)

        if not pools:
            print("❌ No pools found")
            return

        print("\n" + "=" * 70)
        print("🐋 TOP ORCA WHIRLPOOLS")
        print("=" * 70)
        print(f"{'Pair':<15} {'TVL':>12} {'Volume 24h':>12} {'Fee':>8} {'APR':>8}")
        print("-" * 70)

        for pool in pools:
            tvl = (
                f"${pool.tvl_usd / 1e6:.2f}M"
                if pool.tvl_usd >= 1e6
                else f"${pool.tvl_usd / 1e3:.0f}K"
            )
            vol = (
                f"${pool.volume_24h_usd / 1e6:.2f}M"
                if pool.volume_24h_usd >= 1e6
                else f"${pool.volume_24h_usd / 1e3:.0f}K"
            )

            print(
                f"{pool.pair_name:<15} {tvl:>12} {vol:>12} {pool.fee_rate_pct:>7.2f}% {pool.fee_apr_pct:>7.1f}%"
            )

        print("=" * 70 + "\n")


# =============================================================================
# SINGLETON
# =============================================================================

_scraper_instance: Optional[OrcaPoolScraper] = None


def get_pool_scraper() -> OrcaPoolScraper:
    """Get or create the singleton pool scraper."""
    global _scraper_instance
    if _scraper_instance is None:
        _scraper_instance = OrcaPoolScraper()
    return _scraper_instance


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    import sys

    sys.path.insert(0, ".")

    print("\n🔍 Orca Pool Discovery Test")
    print("=" * 50)

    scraper = get_pool_scraper()
    scraper.display_top_pools(limit=5)
