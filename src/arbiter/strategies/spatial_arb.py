"""
V1.1: Spatial Arbitrage Strategy
================================
Cross-DEX arbitrage: Buy on one DEX, sell on another.

Cycle Time: Near-instant (same chain, atomic possible)
Turnover: 10-20x/day (limited by opportunity frequency)
Target Profit: 0.5-2% per cycle

This strategy uses:
- SpreadDetector to find cross-DEX price differences
- ArbitrageExecutor to execute trades (paper or live mode)
"""

from typing import List

from config.settings import Settings
from src.shared.system.logging import Logger
from src.legacy.arbiter.core.spread_detector import SpreadOpportunity


class SpatialArbitrage:
    """
    Spatial Arbitrage: Buy low on DEX A, sell high on DEX B.

    On Solana, this can be atomic using:
    - Jupiter's aggregation (handles multi-DEX routing)
    - Custom instruction bundling
    - Jito bundles for MEV protection

    The SpreadDetector identifies opportunities by comparing
    prices across Jupiter, Raydium, and Orca.
    """

    def __init__(self, spread_detector=None, executor=None):
        self.spread_detector = spread_detector
        self.executor = executor
        self.min_spread = getattr(Settings, "SPATIAL_MIN_SPREAD_PCT", 0.3)
        self.trade_size = getattr(Settings, "SPATIAL_TRADE_SIZE_USD", 50.0)

        # Strategy stats
        self.opportunities_found = 0
        self.trades_executed = 0
        self.total_profit = 0.0

    def scan_and_execute(
        self, pairs: List[tuple], auto_execute: bool = False
    ) -> List[SpreadOpportunity]:
        """
        Scan for opportunities and optionally execute.

        Args:
            pairs: List of (name, base_mint, quote_mint) tuples
            auto_execute: If True, execute profitable opportunities

        Returns:
            List of detected opportunities
        """
        if not self.spread_detector:
            Logger.warning("[SPATIAL] No spread detector configured")
            return []

        # Scan for opportunities
        opportunities = self.spread_detector.scan_all_pairs(pairs)

        # Filter by minimum spread
        profitable = [
            opp
            for opp in opportunities
            if opp.spread_pct >= self.min_spread and opp.status in ["READY", "MONITOR"]
        ]

        self.opportunities_found += len(profitable)

        if profitable:
            Logger.info(
                f"[SPATIAL] Found {len(profitable)} opportunities above {self.min_spread}%"
            )

        # Auto-execute if enabled
        if auto_execute and self.executor and profitable:
            for opp in profitable:
                if opp.status == "READY":
                    self._execute_opportunity(opp)

        return profitable

    async def execute(self, opportunity: SpreadOpportunity) -> dict:
        """
        Execute spatial arbitrage on an opportunity.

        Returns:
            Dict with success, profit, error, etc.
        """
        if not self.executor:
            return {"success": False, "error": "No executor configured"}

        try:
            Logger.info(
                f"[SPATIAL] Executing: {opportunity.pair} | Spread: +{opportunity.spread_pct:.2f}%"
            )

            result = await self.executor.execute_spatial_arb(
                opportunity, trade_size=self.trade_size
            )

            if result.success:
                self.trades_executed += 1
                self.total_profit += result.net_profit

                Logger.info(
                    f"[SPATIAL] ✅ Trade complete: "
                    f"${result.total_input:.2f} → ${result.total_output:.2f} "
                    f"(Net: ${result.net_profit:+.2f})"
                )
            else:
                Logger.warning(f"[SPATIAL] Trade failed: {result.error}")

            return {
                "success": result.success,
                "profit": result.net_profit if result.success else 0,
                "error": result.error,
                "execution_time_ms": result.execution_time_ms,
            }

        except Exception as e:
            Logger.error(f"[SPATIAL] Execution error: {e}")
            return {"success": False, "error": str(e)}

    def _execute_opportunity(self, opportunity: SpreadOpportunity):
        """Wrapper to execute asynchronously."""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.execute(opportunity))
            else:
                asyncio.run(self.execute(opportunity))
        except Exception as e:
            Logger.error(f"[SPATIAL] Async execution error: {e}")

    def get_stats(self) -> dict:
        """Get strategy statistics."""
        return {
            "strategy": "SPATIAL",
            "opportunities_found": self.opportunities_found,
            "trades_executed": self.trades_executed,
            "total_profit": self.total_profit,
            "min_spread_pct": self.min_spread,
            "trade_size_usd": self.trade_size,
        }

    def __repr__(self) -> str:
        return f"<SpatialArbitrage trades={self.trades_executed} profit=${self.total_profit:+.2f}>"
