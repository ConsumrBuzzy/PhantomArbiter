"""
V1.0: Triangular Arbitrage Scanner
==================================
Detects 3-leg arbitrage loops (e.g., USDC -> SOL -> JUP -> USDC).
This framework enables "Triple Hopping" to capture inefficiencies across multiple pairs.
"""

from dataclasses import dataclass, field
from typing import List, Tuple
import time


@dataclass
class TriangularOpportunity:
    """
    Represents a 3-leg arbitrage loop.
    Path: Token A -> Token B -> Token C -> Token A
    """

    route_tokens: List[str]  # [USDC, SOL, JUP] (implied return to USDC)
    route_pairs: List[str]  # ["SOL/USDC", "JUP/SOL", "JUP/USDC"]
    directions: List[str]  # ["BUY", "BUY", "SELL"]

    start_amount: float  # Input amount (e.g., $100 USDC)
    expected_end_amount: float  # Output amount (e.g., $101 USDC)
    gross_profit_usd: float
    net_profit_usd: float  # After 3x fees
    roi_pct: float

    timestamp: float = field(default_factory=time.time)


class TriangularScanner:
    """
    Scans for triangular arbitrage loops using existing price feeds.
    Uses a graph-based approach to find negative log-price cycles.
    """

    def __init__(self, feeds: List = None):
        self.feeds = feeds or []
        # Standard fee estimation per leg (0.3% taker + network fee)
        self.ASSUMED_LEG_FEE_PCT = 0.003
        self.ASSUMED_SLIPPAGE_PCT = (
            0.001  # 0.1% impact per leg (conservative spot estimate)
        )
        self.GAS_COST_PER_LEG_USD = 0.0005 * 180
        self.JITO_TIP_USD = 0.01  # Fixed "bribe" estimate

        # Bridge assets to simplify the graph
        self.USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        self.SOL_MINT = "So11111111111111111111111111111111111111112"
        self.ANCHORS = [self.USDC_MINT, self.SOL_MINT]

        self.adj = {}  # Graph: mint_a -> {mint_b: price}
        self.mint_to_symbol = {self.USDC_MINT: "USDC", self.SOL_MINT: "SOL"}

    def update_graph(
        self, spread_detector, pairs_config: List[Tuple[str, str, str]]
    ) -> None:
        """
        Build adjacency matrix using Mint addresses for nodes.
        pairs_config: [(symbol_pair, base_mint, quote_mint), ...]
        """
        self.adj = {}

        # Build symbol -> mint map for scanner and reverse for logging
        for pair_name, base, quote in pairs_config:
            symbols = pair_name.split("/")
            self.mint_to_symbol[base] = symbols[0]
            self.mint_to_symbol[quote] = symbols[1]

        if not hasattr(spread_detector, "_price_cache"):
            return

        cache = spread_detector._price_cache

        for pair_name, base_mint, quote_mint in pairs_config:
            # Look up prices in detector's cache by the symbol pair name
            prices = cache.get(pair_name)
            if not prices:
                continue

            best_bid = max(prices.values())  # Sell Base -> Quote (Rate = Price)
            best_ask = min(prices.values())  # Buy Base <- Quote (Rate = 1/Price)

            if best_bid <= 0 or best_ask <= 0:
                continue

            # 1. Edge BASE -> QUOTE (Selling Base)
            if base_mint not in self.adj:
                self.adj[base_mint] = {}
            self.adj[base_mint][quote_mint] = best_bid

            # 2. Edge QUOTE -> BASE (Buying Base)
            if quote_mint not in self.adj:
                self.adj[quote_mint] = {}
            self.adj[quote_mint][base_mint] = 1.0 / best_ask

            # Note: This graph mixes Symbols (SOL) and Mints (So111...) depending on what keys are used.
            # We need to ensure consistency. The spread_detector cache uses keys from 'pair_name' arg in scan_pair.
            # Usually strings like "SOL/USDC".

        # Ensure our Anchors are using the same naming convention
        # If cache uses "SOL", "USDC", then ANCHORS must match
        # Updating logic to detect aliases mapping if needed.
        # For now, we assume standard tickers.
        # Logger.debug(f"📐 Graph updated: {len(self.adj)} nodes") # Uncomment for verbose debugging

    def find_cycles(self, amount_in: float = 100.0) -> List[TriangularOpportunity]:
        """
        Find profitable cycles starting from anchors.
        """
        opportunities = []

        # Iterating anchors (USDC, SOL)
        for start_node in self.ANCHORS:
            if start_node not in self.adj:
                continue

            # Level 1: Neighbors of Start
            for mid_node, price1 in self.adj[start_node].items():
                if mid_node == start_node:
                    continue

                # Level 2: Neighbors of Mid
                if mid_node in self.adj:
                    for end_node, price2 in self.adj[mid_node].items():
                        if end_node == start_node or end_node == mid_node:
                            continue

                        # Level 3: Return to Start
                        if end_node in self.adj and start_node in self.adj[end_node]:
                            price3 = self.adj[end_node][start_node]

                            # Calculate Cycle Rate
                            gross_rate = price1 * price2 * price3

                            # Scan Thresholds:
                            # Gross > 1.005 (0.5%) to justify calculating fees
                            if gross_rate > 1.005:
                                opp = self._build_opportunity(
                                    start_node,
                                    mid_node,
                                    end_node,
                                    price1,
                                    price2,
                                    price3,
                                    amount_in,
                                )

                                # Use symbols for logging
                                s1 = self.mint_to_symbol.get(start_node, start_node[:4])
                                s2 = self.mint_to_symbol.get(mid_node, mid_node[:4])
                                s3 = self.mint_to_symbol.get(end_node, end_node[:4])

                                # Log if it meets the user's "observation threshold" of $0.05
                                if opp.net_profit_usd > 0.05:
                                    from src.shared.system.logging import Logger

                                    Logger.info(
                                        f"📐 [SCAN] Opportunity: {s1}->{s2}->{s3} | Gross: {gross_rate:.4f}x | Net: ${opp.net_profit_usd:.2f}"
                                    )
                                    opportunities.append(opp)

                                # Still log "near misses" / raw candidates if high gross but low net
                                elif gross_rate > 1.01:
                                    from src.shared.system.logging import Logger

                                    Logger.info(
                                        f"📐 [SCAN] Candidate: {s1}->{s2}->{s3} | Gross: {gross_rate:.4f}x (Net ${opp.net_profit_usd:.2f})"
                                    )

        return opportunities

    def _build_opportunity(
        self, t1, t2, t3, p1, p2, p3, amount_in
    ) -> TriangularOpportunity:
        """Construct opportunity object with full fee calculation."""
        # Theoretical Gross (Spot Price)
        theoretical_end_amount = amount_in * p1 * p2 * p3
        gross_profit = theoretical_end_amount - amount_in

        # 1. Apply Compound Slippage
        # (1 - s)^3 ~ 1 - 3s for small s
        slippage_factor = (1 - self.ASSUMED_SLIPPAGE_PCT) ** 3
        realized_end_amount = theoretical_end_amount * slippage_factor

        # 2. Subtract Fees (Exchange + Gas + Jito Tip)
        # Exchange fees are taken from input/output usually, simplified here as USD deduction
        exchange_fees = amount_in * 3 * self.ASSUMED_LEG_FEE_PCT
        gas_fees = 3 * self.GAS_COST_PER_LEG_USD

        total_costs = exchange_fees + gas_fees + self.JITO_TIP_USD

        net_profit = realized_end_amount - amount_in - total_costs

        return TriangularOpportunity(
            route_tokens=[t1, t2, t3],
            route_pairs=["Pair1", "Pair2", "Pair3"],  # Placeholder
            directions=["BUY", "BUY", "BUY"],  # Placeholder
            start_amount=amount_in,
            expected_end_amount=realized_end_amount,
            gross_profit_usd=gross_profit,
            net_profit_usd=net_profit,
            roi_pct=(net_profit / amount_in) * 100,
        )
