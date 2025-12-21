"""
V1.0: Triangular Arbitrage Scanner
==================================
Detects 3-leg arbitrage loops (e.g., USDC -> SOL -> JUP -> USDC).
This framework enables "Triple Hopping" to capture inefficiencies across multiple pairs.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import time

@dataclass
class TriangularOpportunity:
    """
    Represents a 3-leg arbitrage loop.
    Path: Token A -> Token B -> Token C -> Token A
    """
    route_tokens: List[str]     # [USDC, SOL, JUP] (implied return to USDC)
    route_pairs: List[str]      # ["SOL/USDC", "JUP/SOL", "JUP/USDC"]
    directions: List[str]       # ["BUY", "BUY", "SELL"]
    
    start_amount: float         # Input amount (e.g., $100 USDC)
    expected_end_amount: float  # Output amount (e.g., $101 USDC)
    gross_profit_usd: float
    net_profit_usd: float       # After 3x fees
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
        self.ASSUMED_SLIPPAGE_PCT = 0.001  # 0.1% impact per leg (conservative spot estimate)
        self.GAS_COST_PER_LEG_USD = 0.0005 * 180 
        self.JITO_TIP_USD = 0.01  # Fixed "bribe" estimate 
        
        # Bridge assets to simplify the graph
        # Using Symbols to match the keys from update_graph (which parses pair names like "SOL/USDC")
        self.ANCHORS = ["USDC", "SOL"] 
        self.adj = {} # Graph: token_a -> {token_b: price}
        
    def update_graph(self, spread_detector) -> None:
        """
        Build adjacency matrix from spread detector's price cache.
        Input: spread_detector._price_cache = {"SOL/USDC": {"Orca": 100.0, "Raydium": 101.0}}
        Output: self.adj["SOL"]["USDC"] = 101.0 (Best Sell Price for SOL? No, best rate)
        
        For Arbitrage A -> B:
        - If we trade A -> B, we are selling A and buying B.
        - Rate = Output Amount of B per 1 unit of A.
        
        If Pair is "A/B" (Price of A in terms of B):
        - A -> B (Sell A): Rate = Price (We want Highest Price to get most B)
        - B -> A (Buy A): Rate = 1/Price (We want Lowest Price to pay least B)
        """
        # Clear graph
        self.adj = {}
        
        if not hasattr(spread_detector, '_price_cache'):
            return

        cache = spread_detector._price_cache
        
        for pair_name, prices in cache.items():
            if "/" not in pair_name:
                continue
                
            base, quote = pair_name.split("/")
            # Use mints if available, but for now we rely on symbols as keys in this graph
            # In a real system, we'd map symbols to mints.
            
            # Find Best Bid (Highest Price) and Best Ask (Lowest Price) across DEXs
            if not prices:
                continue
                
            best_bid = max(prices.values()) # Sell A -> B (get most B)
            best_ask = min(prices.values()) # Buy A <- B (pay least B)
            
            if best_bid <= 0 or best_ask <= 0:
                continue
            
            # 1. Edge BASE -> QUOTE (Selling Base)
            # Rate = Price
            if base not in self.adj: self.adj[base] = {}
            # Allow overwriting if we find a better path? 
            # In this simple version, we process each pair once.
            self.adj[base][quote] = best_bid
            
            # 2. Edge QUOTE -> BASE (Buying Base)
            # Rate = 1 / Price
            if quote not in self.adj: self.adj[quote] = {}
            self.adj[quote][base] = 1.0 / best_ask
            
            # Note: This graph mixes Symbols (SOL) and Mints (So111...) depending on what keys are used.
            # We need to ensure consistency. The spread_detector cache uses keys from 'pair_name' arg in scan_pair.
            # Usually strings like "SOL/USDC".
            
        # Ensure our Anchors are using the same naming convention
        # If cache uses "SOL", "USDC", then ANCHORS must match
        # Updating logic to detect aliases mapping if needed.
        # For now, we assume standard tickers.
        from src.shared.system.logging import Logger
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
                if mid_node == start_node: continue
                
                # Level 2: Neighbors of Mid
                if mid_node in self.adj:
                    for end_node, price2 in self.adj[mid_node].items():
                        if end_node == start_node or end_node == mid_node: continue
                        
                        # Level 3: Return to Start
                        if end_node in self.adj and start_node in self.adj[end_node]:
                            price3 = self.adj[end_node][start_node]
                            
                            # Calculate Cycle Rate
                            gross_rate = price1 * price2 * price3
                            
                            # Log candidates to show activity (User Request)
                            # Log candidates to show activity (User Request)
                            # V129: Lower threshold to 0.1% to show activity
                            if gross_rate > 1.001:
                                from src.shared.system.logging import Logger
                                Logger.info(f"📐 [SCAN] Candidate: {start_node}->{mid_node}->{end_node} | Gross: {gross_rate:.4f}x")

                            # Check basic profitability (> 1.0 + fees)
                            # 3 swaps = ~0.9% fees (conservative)
                            if gross_rate > 1.015:
                                # Detailed calculation
                                opp = self._build_opportunity(start_node, mid_node, end_node, price1, price2, price3, amount_in)
                                if opp and opp.net_profit_usd > 0.05: # Min 5c (lowered for visibility)
                                    opportunities.append(opp)
                                    
        return opportunities

    def _build_opportunity(self, t1, t2, t3, p1, p2, p3, amount_in) -> TriangularOpportunity:
        """Construct opportunity object with full fee calculation."""
        # Theoretical Gross (Spot Price)
        theoretical_end_amount = amount_in * p1 * p2 * p3
        
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
            route_pairs=[f"Pair1", f"Pair2", f"Pair3"], # Placeholder
            directions=["BUY", "BUY", "BUY"], # Placeholder
            start_amount=amount_in,
            expected_end_amount=realized_end_amount,
            gross_profit_usd=gross_profit,
            net_profit_usd=net_profit,
            roi_pct=(net_profit / amount_in) * 100
        )

