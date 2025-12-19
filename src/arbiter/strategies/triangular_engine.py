"""
Phantom Arbiter - Triangular Arbitrage Engine
==============================================
Intra-DEX cycles: A → B → C → A on the same exchange.

Example:
    Start: $100 USDC
    Step 1: USDC → SOL (buy SOL with USDC)
    Step 2: SOL → BONK (buy BONK with SOL)
    Step 3: BONK → USDC (sell BONK for USDC)
    End: $100.50 USDC (profit!)

Cycle Time: Milliseconds (single atomic transaction)
Turnover:   1000x+/day if opportunities exist
Target:     0.01% - 0.3% per cycle (tiny margins, high frequency)

WARNING: This strategy is HEAVILY competed by MEV bots.
They have faster infrastructure and will front-run you.

Usage:
    from src.arbiter.strategies.triangular_engine import TriangularEngine
    engine = TriangularEngine(dex="Jupiter")
    opportunities = await engine.find_opportunities()
"""

import asyncio
import time
import requests
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from itertools import permutations

from config.settings import Settings
from src.shared.system.logging import Logger


@dataclass
class TriangularOpportunity:
    """A triangular arbitrage opportunity."""
    cycle: List[str]              # ["USDC", "SOL", "BONK"] means USDC→SOL→BONK→USDC
    dex: str                      # Which DEX
    start_amount: float           # Starting amount in first token
    end_amount: float             # Ending amount in first token
    profit_amount: float          # end - start - fees
    profit_pct: float             # Percentage profit
    fees_total: float             # Total fees for 3 swaps
    prices: Dict[str, float]      # Prices used in calculation
    timestamp: float = field(default_factory=time.time)
    
    @property
    def is_profitable(self) -> bool:
        return self.profit_amount > 0
    
    def __str__(self) -> str:
        status = "✅ PROFITABLE" if self.is_profitable else "❌ NOT PROFITABLE"
        cycle_str = " → ".join(self.cycle + [self.cycle[0]])
        
        return (
            f"\n{'='*60}\n"
            f"  TRIANGULAR: {cycle_str}\n"
            f"  DEX: {self.dex}\n"
            f"{'='*60}\n"
            f"  Start:     {self.start_amount:.4f} {self.cycle[0]}\n"
            f"  End:       {self.end_amount:.4f} {self.cycle[0]}\n"
            f"  Fees:      {self.fees_total:.4f}\n"
            f"  Profit:    {self.profit_amount:+.4f} ({self.profit_pct:+.3f}%)\n"
            f"  Status:    {status}\n"
        )


class TriangularEngine:
    """
    Triangular Arbitrage Engine.
    
    Finds and executes A → B → C → A cycles within a single DEX.
    """
    
    # Fee per swap (0.1% typical for DEX)
    SWAP_FEE = 0.001
    TOTAL_FEES = SWAP_FEE * 3  # 3 swaps = 0.3%
    
    # Minimum profit threshold (must exceed fees)
    MIN_PROFIT_PCT = 0.05  # 0.05% after fees
    
    # Token mints
    TOKENS = {
        "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "SOL": "So11111111111111111111111111111111111111112",
        "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
        "WIF": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
        "JUP": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
        "RAY": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
    }
    
    # Predefined cycles to check
    DEFAULT_CYCLES = [
        ["USDC", "SOL", "BONK"],
        ["USDC", "SOL", "WIF"],
        ["USDC", "SOL", "JUP"],
        ["USDC", "SOL", "RAY"],
        ["SOL", "BONK", "WIF"],
        ["SOL", "JUP", "RAY"],
    ]
    
    def __init__(self, dex: str = "Jupiter"):
        self.dex = dex
        self._price_cache: Dict[str, float] = {}
        self._cache_time = 0
        self._cache_ttl = 5  # 5 second cache
        
    async def get_price(self, from_token: str, to_token: str) -> Optional[float]:
        """
        Get price for a token pair.
        
        Returns: Amount of to_token per 1 from_token
        """
        cache_key = f"{from_token}_{to_token}"
        
        # Check cache
        if cache_key in self._price_cache and time.time() - self._cache_time < self._cache_ttl:
            return self._price_cache[cache_key]
        
        try:
            from_mint = self.TOKENS.get(from_token)
            to_mint = self.TOKENS.get(to_token)
            
            if not from_mint or not to_mint:
                return None
            
            # Use DexScreener for fast prices
            url = f"https://api.dexscreener.com/latest/dex/tokens/{from_mint}"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                pairs = data.get("pairs", [])
                
                # Find the pair we need
                for pair in pairs:
                    base = pair.get("baseToken", {}).get("symbol", "")
                    quote = pair.get("quoteToken", {}).get("symbol", "")
                    
                    if base.upper() == from_token and quote.upper() == to_token:
                        price = float(pair.get("priceNative", 0))
                        self._price_cache[cache_key] = price
                        self._cache_time = time.time()
                        return price
                    elif quote.upper() == from_token and base.upper() == to_token:
                        price = 1 / float(pair.get("priceNative", 1))
                        self._price_cache[cache_key] = price
                        self._cache_time = time.time()
                        return price
                
                # Fallback: use USD prices
                from_usd = await self._get_usd_price(from_token)
                to_usd = await self._get_usd_price(to_token)
                
                if from_usd and to_usd and to_usd > 0:
                    price = from_usd / to_usd
                    self._price_cache[cache_key] = price
                    return price
                    
        except Exception as e:
            Logger.debug(f"Price fetch error {from_token}/{to_token}: {e}")
        
        return None
    
    async def _get_usd_price(self, token: str) -> Optional[float]:
        """Get USD price for a token."""
        try:
            from src.shared.feeds.jupiter_feed import JupiterFeed
            
            mint = self.TOKENS.get(token)
            if not mint:
                return None
            
            feed = JupiterFeed()
            USDC = self.TOKENS["USDC"]
            spot = feed.get_spot_price(mint, USDC)
            
            return spot.price if spot else None
            
        except Exception as e:
            Logger.debug(f"USD price error: {e}")
            return None
    
    async def calculate_cycle_profit(
        self,
        cycle: List[str],
        start_amount: float = 100.0
    ) -> Optional[TriangularOpportunity]:
        """
        Calculate profit for a triangular cycle.
        
        Args:
            cycle: ["USDC", "SOL", "BONK"] means USDC→SOL→BONK→USDC
            start_amount: Starting amount of first token
            
        Returns:
            TriangularOpportunity if calculable, else None
        """
        if len(cycle) < 3:
            return None
        
        prices = {}
        current_amount = start_amount
        
        # Execute each leg of the cycle
        for i in range(len(cycle)):
            from_token = cycle[i]
            to_token = cycle[(i + 1) % len(cycle)]
            
            price = await self.get_price(from_token, to_token)
            if price is None:
                Logger.debug(f"Could not get price for {from_token}/{to_token}")
                return None
            
            prices[f"{from_token}_{to_token}"] = price
            
            # Apply swap
            next_amount = current_amount * price
            
            # Apply fee
            next_amount *= (1 - self.SWAP_FEE)
            
            current_amount = next_amount
        
        # Calculate profit
        end_amount = current_amount
        fees_total = start_amount * self.TOTAL_FEES
        profit_amount = end_amount - start_amount
        profit_pct = (profit_amount / start_amount) * 100
        
        return TriangularOpportunity(
            cycle=cycle,
            dex=self.dex,
            start_amount=start_amount,
            end_amount=end_amount,
            profit_amount=profit_amount,
            profit_pct=profit_pct,
            fees_total=fees_total,
            prices=prices
        )
    
    async def find_opportunities(
        self,
        cycles: List[List[str]] = None,
        start_amount: float = 100.0
    ) -> List[TriangularOpportunity]:
        """
        Find all profitable triangular opportunities.
        
        Returns:
            List of opportunities sorted by profit (best first)
        """
        if cycles is None:
            cycles = self.DEFAULT_CYCLES
        
        opportunities = []
        
        for cycle in cycles:
            opp = await self.calculate_cycle_profit(cycle, start_amount)
            if opp and opp.profit_pct >= self.MIN_PROFIT_PCT:
                opportunities.append(opp)
        
        # Sort by profit (best first)
        opportunities.sort(key=lambda x: x.profit_pct, reverse=True)
        
        return opportunities
    
    async def scan_all_cycles(
        self,
        tokens: List[str] = None,
        start_amount: float = 100.0
    ) -> List[TriangularOpportunity]:
        """
        Scan ALL possible 3-token cycles.
        
        Warning: This is O(n^3) in number of tokens!
        """
        if tokens is None:
            tokens = list(self.TOKENS.keys())
        
        all_opportunities = []
        
        # Generate all 3-token permutations
        for perm in permutations(tokens, 3):
            cycle = list(perm)
            opp = await self.calculate_cycle_profit(cycle, start_amount)
            
            if opp:
                all_opportunities.append(opp)
        
        # Sort by profit
        all_opportunities.sort(key=lambda x: x.profit_pct, reverse=True)
        
        return all_opportunities
    
    async def execute_cycle(
        self,
        opportunity: TriangularOpportunity,
        paper_mode: bool = True
    ) -> Dict[str, Any]:
        """
        Execute a triangular arbitrage cycle.
        
        In paper mode: Simulates the trade
        In live mode: Would bundle 3 swaps into atomic TX
        """
        if paper_mode:
            Logger.info(f"[TRI] Paper trade: {' → '.join(opportunity.cycle)}")
            
            # Simulate execution
            await asyncio.sleep(0.1)  # Simulate network delay
            
            return {
                "success": True,
                "mode": "PAPER",
                "cycle": opportunity.cycle,
                "start": opportunity.start_amount,
                "end": opportunity.end_amount,
                "profit": opportunity.profit_amount,
                "execution_time_ms": 100,
                "signature": f"PAPER_TRI_{int(time.time())}"
            }
        else:
            # Live execution would:
            # 1. Get Jupiter swap instructions for each leg
            # 2. Bundle all 3 into one transaction
            # 3. Send with Jito for MEV protection
            return {"success": False, "error": "Live execution not implemented"}


# ═══════════════════════════════════════════════════════════════════
# DEMO SCRIPT
# ═══════════════════════════════════════════════════════════════════

async def run_triangular_demo(budget: float = 100.0):
    """Run the triangular arbitrage demo."""
    from datetime import datetime
    
    print("\n" + "="*70)
    print("   PHANTOM ARBITER - TRIANGULAR ARBITRAGE DEMO")
    print("="*70)
    print(f"   Budget: ${budget:.2f}")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Fee per swap: 0.1% × 3 = 0.3% total")
    print("="*70)
    
    engine = TriangularEngine(dex="Jupiter")
    
    # ═══════════════════════════════════════════════════════════════════
    # STEP 1: Scan predefined cycles
    # ═══════════════════════════════════════════════════════════════════
    print("\n🔍 SCANNING TRIANGULAR CYCLES...")
    print("-"*70)
    
    cycles = [
        ["USDC", "SOL", "BONK"],
        ["USDC", "SOL", "WIF"],
        ["USDC", "SOL", "JUP"],
        ["USDC", "BONK", "WIF"],
        ["SOL", "BONK", "WIF"],
    ]
    
    print(f"   Checking {len(cycles)} cycles...")
    
    all_results = []
    for cycle in cycles:
        opp = await engine.calculate_cycle_profit(cycle, budget)
        if opp:
            all_results.append(opp)
            cycle_str = " → ".join(cycle + [cycle[0]])
            status = "🟢" if opp.is_profitable else "🔴"
            print(f"   {status} {cycle_str}: {opp.profit_pct:+.4f}%")
        else:
            cycle_str = " → ".join(cycle + [cycle[0]])
            print(f"   ⚪ {cycle_str}: No data")
    
    # ═══════════════════════════════════════════════════════════════════
    # STEP 2: Show best opportunities
    # ═══════════════════════════════════════════════════════════════════
    print("\n💰 TOP OPPORTUNITIES:")
    print("-"*70)
    
    profitable = [o for o in all_results if o.is_profitable]
    
    if profitable:
        profitable.sort(key=lambda x: x.profit_pct, reverse=True)
        
        for opp in profitable[:3]:
            print(opp)
    else:
        print("   ❌ No profitable triangular cycles found")
        print(f"   All cycles have negative returns after 0.3% fees")
        
        # Show best (least negative)
        if all_results:
            best = max(all_results, key=lambda x: x.profit_pct)
            print(f"\n   Best cycle: {' → '.join(best.cycle)}")
            print(f"   Result: {best.profit_pct:+.4f}% (still negative)")
    
    # ═══════════════════════════════════════════════════════════════════
    # STEP 3: Execute best opportunity (if any)
    # ═══════════════════════════════════════════════════════════════════
    if profitable:
        best = profitable[0]
        
        print(f"\n⚡ EXECUTING BEST CYCLE (Paper Mode)...")
        print("-"*70)
        
        result = await engine.execute_cycle(best, paper_mode=True)
        
        if result['success']:
            print(f"   ✅ Cycle executed!")
            print(f"   Start:  ${result['start']:.4f}")
            print(f"   End:    ${result['end']:.4f}")
            print(f"   Profit: ${result['profit']:+.4f}")
            print(f"   Time:   {result['execution_time_ms']}ms")
    
    # ═══════════════════════════════════════════════════════════════════
    # STEP 4: Reality check
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "="*70)
    print("   TRIANGULAR ARBITRAGE REALITY CHECK")
    print("="*70)
    print("""
   ⚠️ IMPORTANT WARNINGS:

   1. MEV BOTS OWN THIS GAME
      - They execute in <100ms with dedicated hardware
      - They see your transaction in mempool and front-run
      - Retail traders rarely capture these opportunities

   2. FEES EAT PROFITS
      - 3 swaps × 0.1% = 0.3% minimum cost
      - Opportunities must exceed 0.3% to profit
      - These are extremely rare

   3. SLIPPAGE RISK
      - Price changes during execution
      - Large trades move the market
      - Your "profitable" cycle becomes a loss

   💡 RECOMMENDATION:
      For small budgets (<$1000), focus on:
      - Funding Rate Arbitrage (consistent, less competition)
      - Spatial Arbitrage (occasional, when spreads are large)
      
      Triangular arb is best for:
      - Bots with <10ms execution
      - Large capital ($100k+) that can absorb fees
      - Custom Solana programs that bypass Jupiter
""")
    
    print("="*70)
    print("   END OF TRIANGULAR ARBITRAGE DEMO")
    print("="*70 + "\n")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Triangular Arbitrage Demo")
    parser.add_argument("--budget", type=float, default=100.0, help="Budget in USD")
    
    args = parser.parse_args()
    
    asyncio.run(run_triangular_demo(args.budget))
