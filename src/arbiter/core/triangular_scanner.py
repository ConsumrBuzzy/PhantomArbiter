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
        self.GAS_COST_PER_LEG_USD = 0.0005 * 180 
        
        # Bridge assets to simplify the graph
        self.ANCHORS = ["EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", # USDC
                        "So11111111111111111111111111111111111111112"] # SOL
        self.adj = {} # Graph: token_a -> {token_b: price}
        
    def update_graph(self, spread_detector) -> None:
        """
        Build adjacency matrix from spread detector's price cache.
        """
        # Clear graph
        self.adj = {}
        
        # We need a way to get all known prices. 
        # Currently SpreadDetector caches by Pair (e.g. "SOL/USDC").
        # We need to invert this to Token -> Token prices.
        
        # For V1, we will iterate known markets in the spread detector
        # This part requires SpreadDetector to expose its market list
        pass
        
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
                            
                            # Check basic profitability (> 1.0 + fees)
                            # 3 swaps = ~0.9% fees (conservative)
                            if gross_rate > 1.015:
                                # Detailed calculation
                                opp = self._build_opportunity(start_node, mid_node, end_node, price1, price2, price3, amount_in)
                                if opp and opp.net_profit_usd > 0.50: # Min 50c for complex arb
                                    opportunities.append(opp)
                                    
        return opportunities

    def _build_opportunity(self, t1, t2, t3, p1, p2, p3, amount_in) -> TriangularOpportunity:
        """Construct opportunity object with full fee calculation."""
        # Gross
        end_amount = amount_in * p1 * p2 * p3
        gross_profit = end_amount - amount_in
        
        # Fees (approx)
        total_fees = (amount_in * 3 * self.ASSUMED_LEG_FEE_PCT) + (3 * self.GAS_COST_PER_LEG_USD)
        net_profit = gross_profit - total_fees
        
        return TriangularOpportunity(
            route_tokens=[t1, t2, t3],
            route_pairs=[f"Pair1", f"Pair2", f"Pair3"], # Placeholder
            directions=["BUY", "BUY", "BUY"], # Placeholder
            start_amount=amount_in,
            expected_end_amount=end_amount,
            gross_profit_usd=gross_profit,
            net_profit_usd=net_profit,
            roi_pct=(net_profit / amount_in) * 100
        )

