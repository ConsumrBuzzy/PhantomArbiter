"""
HopGraphEngine - Python Wrapper for Rust Multi-Hop Arbitrage
=============================================================
V140: Narrow Path Infrastructure

This module provides the Python interface to the Rust-powered graph
pathfinding engine for multi-hop token arbitrage.

Key Features:
- O(1) pool edge updates via Rust HashMap
- Bounded DFS cycle detection (3-5 hops)
- Negative cycle detection via -ln(rate) edge weights
- Liquidity-aware filtering
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from config.settings import Settings
from src.shared.system.logging import Logger

# Try to import Rust extension
try:
    from phantom_core import HopGraph, CycleFinder, HopCycle, PoolEdge

    RUST_AVAILABLE = True
except ImportError:
    HopGraph = None
    CycleFinder = None
    HopCycle = None
    PoolEdge = None
    RUST_AVAILABLE = False
    Logger.warning(
        "⚠️ phantom_core not available - HopGraphEngine will use fallback mode"
    )


@dataclass
class HopOpportunity:
    """Python representation of a detected arbitrage cycle."""

    path: List[str]  # Token mints in order [SOL, A, B, SOL]
    pools: List[str]  # Pool addresses to traverse
    profit_pct: float  # Theoretical profit percentage
    min_liquidity_usd: float  # Bottleneck liquidity
    hop_count: int  # Number of legs
    total_fee_bps: int = 0  # Cumulative fees in basis points

    def __repr__(self) -> str:
        path_short = [p[:8] for p in self.path]
        return f"HopOpp({' → '.join(path_short)} | +{self.profit_pct:.3f}% | liq=${self.min_liquidity_usd:,.0f})"

    def is_executable(
        self, min_liquidity: float = 5000.0, max_fee_bps: int = 300
    ) -> bool:
        """Check if this opportunity is worth executing."""
        return (
            self.min_liquidity_usd >= min_liquidity
            and self.total_fee_bps <= max_fee_bps
        )


@dataclass
class HopEngineStats:
    """Statistics for monitoring engine health."""

    node_count: int = 0
    edge_count: int = 0
    cycles_found: int = 0
    last_scan_ms: float = 0.0
    total_scans: int = 0
    stale_edges_pruned: int = 0


class HopGraphEngine:
    """
    Deterministic Multi-Hop Arbitrage Engine.

    Replaces probabilistic DecisionEngine for Narrow Path strategy.
    Leverages Rust core for O(100μs) graph scans across 5000+ pools.
    """

    # Standard SOL mint address
    SOL_MINT = "So11111111111111111111111111111111111111112"

    def __init__(
        self,
        max_hops: int = None,
        min_profit_pct: float = None,
        min_liquidity_usd: int = None,
    ):
        """
        Initialize the HopGraphEngine.

        Args:
            max_hops: Maximum cycle length (3-5). Defaults to Settings.HOP_MAX_LEGS
            min_profit_pct: Minimum profit threshold. Defaults to Settings.HOP_MIN_PROFIT_PCT
            min_liquidity_usd: Minimum pool liquidity. Defaults to Settings.HOP_MIN_LIQUIDITY_USD
        """
        if not RUST_AVAILABLE:
            raise ImportError(
                "phantom_core Rust extension not available. "
                "Build with: cd src_rust && maturin develop --release"
            )

        # Load from settings with fallbacks
        self.max_hops = max_hops or getattr(Settings, "HOP_MAX_LEGS", 4)
        self.min_profit_pct = min_profit_pct or getattr(
            Settings, "HOP_MIN_PROFIT_PCT", 0.20
        )
        self.min_liquidity_usd = min_liquidity_usd or getattr(
            Settings, "HOP_MIN_LIQUIDITY_USD", 5000
        )

        # Initialize Rust components
        self.graph = HopGraph()
        self.finder = CycleFinder(
            self.max_hops,
            self.min_profit_pct / 100.0,  # Convert % to decimal
            self.min_liquidity_usd,
        )

        # Statistics
        self.stats = HopEngineStats()

        Logger.info(
            f"[HopEngine] Initialized "
            f"(max_hops={self.max_hops}, min_profit={self.min_profit_pct}%, min_liq=${self.min_liquidity_usd})"
        )

    def update_pool(self, pool_data: Dict[str, Any]) -> None:
        """
        Ingest a real-time pool update from WSS or RPC.

        Expected pool_data format:
        {
            "base_mint": str,        # Source token mint
            "quote_mint": str,       # Target token mint
            "pool_address": str,     # AMM pool address
            "price": float,          # Exchange rate (base -> quote)
            "fee_bps": int,          # Trading fee in basis points
            "liquidity_usd": int,    # Pool TVL in USD
            "slot": int,             # Solana slot when data was fetched
            "dex": str               # DEX identifier (RAYDIUM, ORCA, etc.)
        }
        """
        try:
            base = pool_data.get("base_mint", "")
            quote = pool_data.get("quote_mint", "")
            pool = pool_data.get("pool_address", "")
            price = pool_data.get("price", 0.0)

            if not all([base, quote, pool]) or price <= 0:
                return

            # Create edge and update graph
            edge = PoolEdge(
                source_mint=base,
                target_mint=quote,
                pool_address=pool,
                exchange_rate=price,
                fee_bps=pool_data.get("fee_bps", 25),
                liquidity_usd=int(pool_data.get("liquidity_usd", 0)),
                last_update_slot=pool_data.get("slot", 0),
                dex=pool_data.get("dex", "UNKNOWN"),
            )

            self.graph.update_edge(edge)

        except Exception as e:
            Logger.debug(f"[HopEngine] Update error: {e}")

    def update_pools_batch(self, pool_updates: List[Dict[str, Any]]) -> int:
        """
        Batch update multiple pools.

        Returns:
            Number of successful updates
        """
        updated = 0
        for pool_data in pool_updates:
            try:
                self.update_pool(pool_data)
                updated += 1
            except Exception:
                pass
        return updated

    def scan(self, start_mint: str = None) -> List[HopOpportunity]:
        """
        Scan for profitable arbitrage cycles.

        Args:
            start_mint: Token to start/end cycles at. Defaults to SOL.

        Returns:
            List of HopOpportunity sorted by profit (descending)
        """
        import time

        start_time = time.perf_counter()

        start = start_mint or self.SOL_MINT

        try:
            # Call Rust cycle finder
            cycles: List[HopCycle] = self.finder.find_cycles(self.graph, start)

            # Convert to Python dataclass
            opportunities = [
                HopOpportunity(
                    path=c.path,
                    pools=c.pool_addresses,
                    profit_pct=c.theoretical_profit_pct,
                    min_liquidity_usd=c.min_liquidity_usd,
                    hop_count=c.hop_count,
                    total_fee_bps=c.total_fee_bps,
                )
                for c in cycles
            ]

            # Update stats
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self.stats.cycles_found = len(opportunities)
            self.stats.last_scan_ms = elapsed_ms
            self.stats.total_scans += 1
            self.stats.node_count = self.graph.node_count()
            self.stats.edge_count = self.graph.edge_count()

            if opportunities:
                best = opportunities[0]
                Logger.info(
                    f"[HopEngine] Found {len(opportunities)} cycles "
                    f"(best: +{best.profit_pct:.3f}%) in {elapsed_ms:.2f}ms"
                )

            return opportunities

        except Exception as e:
            Logger.error(f"[HopEngine] Scan error: {e}")
            return []

    def validate_opportunity(self, opp: HopOpportunity) -> Optional[HopOpportunity]:
        """
        Re-validate an opportunity against current graph state.

        Returns:
            Updated HopOpportunity if still profitable, None otherwise
        """
        try:
            validated = self.finder.validate_path(self.graph, opp.path)
            if validated is None:
                return None

            return HopOpportunity(
                path=validated.path,
                pools=validated.pool_addresses,
                profit_pct=validated.theoretical_profit_pct,
                min_liquidity_usd=validated.min_liquidity_usd,
                hop_count=validated.hop_count,
                total_fee_bps=validated.total_fee_bps,
            )
        except Exception:
            return None

    def prune_stale(self, max_age_slots: int = None) -> int:
        """
        Remove stale edges from the graph.

        Args:
            max_age_slots: Maximum edge age in slots. Defaults to Settings.HOP_STALE_SLOT_THRESHOLD

        Returns:
            Number of edges pruned
        """
        threshold = max_age_slots or getattr(Settings, "HOP_STALE_SLOT_THRESHOLD", 150)

        # Calculate minimum valid slot (current - threshold)
        # We'd need current slot here, but for now just use the threshold directly
        # In practice, the caller should provide the current slot
        pruned = self.graph.prune_stale(threshold)
        self.stats.stale_edges_pruned += pruned

        if pruned > 0:
            Logger.debug(f"[HopEngine] Pruned {pruned} stale edges")

        return pruned

    def get_stats(self) -> Dict[str, Any]:
        """Return engine statistics for dashboard display."""
        return {
            "node_count": self.stats.node_count,
            "edge_count": self.stats.edge_count,
            "cycles_found": self.stats.cycles_found,
            "last_scan_ms": round(self.stats.last_scan_ms, 2),
            "total_scans": self.stats.total_scans,
            "stale_pruned": self.stats.stale_edges_pruned,
            "config": {
                "max_hops": self.max_hops,
                "min_profit_pct": self.min_profit_pct,
                "min_liquidity_usd": self.min_liquidity_usd,
            },
        }

    def get_neighbors(self, mint: str) -> List[str]:
        """Get all tokens reachable in one hop from the given token."""
        return self.graph.get_neighbors(mint)

    def clear(self) -> None:
        """Clear all edges and reset the graph."""
        self.graph.clear()
        self.stats = HopEngineStats()
        Logger.info("[HopEngine] Graph cleared")


# ═══════════════════════════════════════════════════════════════════════════
# FACTORY FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

_engine_instance: Optional[HopGraphEngine] = None


def get_hop_engine() -> HopGraphEngine:
    """
    Get or create the singleton HopGraphEngine instance.

    Returns:
        HopGraphEngine instance
    """
    global _engine_instance

    if _engine_instance is None:
        _engine_instance = HopGraphEngine()

    return _engine_instance


def reset_hop_engine() -> None:
    """Reset the singleton instance (for testing)."""
    global _engine_instance
    if _engine_instance:
        _engine_instance.clear()
    _engine_instance = None
