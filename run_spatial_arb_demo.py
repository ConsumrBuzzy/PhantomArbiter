"""
Phantom Arbiter - Spatial Arbitrage (Quick Flip) Demo
======================================================
Buy low on DEX A, sell high on DEX B.

This is the FAST arbitrage - quick flips, not holding.

Cycle Time: Seconds to minutes (same chain)
Turnover:   10-20x per day if opportunities exist
Target:     0.3% - 2% per flip (after fees)

Usage:
    python run_spatial_arb_demo.py
    python run_spatial_arb_demo.py --budget 100 --min-spread 0.3
"""

import asyncio
import time
import argparse
from datetime import datetime
from typing import List

from config.settings import Settings


async def find_spatial_opportunities(min_spread: float = 0.3) -> List[dict]:
    """
    Scan for spatial arbitrage opportunities across DEXs.
    
    Returns list of opportunities with price differences.
    """
    from src.arbitrage.core.spread_detector import SpreadDetector
    from src.arbitrage.feeds.jupiter_feed import JupiterFeed
    from src.arbitrage.feeds.raydium_feed import RaydiumFeed
    from src.arbitrage.feeds.orca_feed import OrcaFeed
    
    # Initialize feeds
    feeds = [
        JupiterFeed(),
        RaydiumFeed(),
        OrcaFeed(use_on_chain=False),
    ]
    
    # Initialize spread detector
    detector = SpreadDetector(feeds=feeds)
    
    # Define pairs to scan
    USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    SOL = "So11111111111111111111111111111111111111112"
    WIF = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
    JUP = "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"
    BONK = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
    
    pairs = [
        ("SOL/USDC", SOL, USDC),
        ("WIF/USDC", WIF, USDC),
        ("JUP/USDC", JUP, USDC),
        ("BONK/USDC", BONK, USDC),
    ]
    
    print(f"\n🔍 Scanning {len(pairs)} pairs across 3 DEXs...")
    print("-" * 70)
    
    # Scan for opportunities
    opportunities = detector.scan_all_pairs(pairs)
    
    # Filter by minimum spread
    filtered = [opp for opp in opportunities if opp.spread_pct >= min_spread]
    
    return filtered, opportunities


async def execute_spatial_flip(opportunity, budget: float = 100.0):
    """
    Execute a spatial arbitrage flip (paper mode).
    
    Buy on low-price DEX, sell on high-price DEX.
    """
    from src.arbitrage.core.executor import ArbitrageExecutor, ExecutionMode
    
    executor = ArbitrageExecutor(mode=ExecutionMode.PAPER)
    
    print(f"\n⚡ EXECUTING SPATIAL FLIP")
    print("-" * 50)
    print(f"   Pair:     {opportunity.pair}")
    print(f"   Buy on:   {opportunity.buy_dex} @ ${opportunity.buy_price:.6f}")
    print(f"   Sell on:  {opportunity.sell_dex} @ ${opportunity.sell_price:.6f}")
    print(f"   Spread:   +{opportunity.spread_pct:.2f}%")
    print(f"   Budget:   ${budget:.2f}")
    
    # Execute
    result = await executor.execute_spatial_arb(opportunity, trade_size=budget)
    
    if result.success:
        print(f"\n   ✅ FLIP COMPLETE!")
        print(f"   Input:     ${result.total_input:.2f}")
        print(f"   Output:    ${result.total_output:.2f}")
        print(f"   Fees:      ${result.total_fees:.4f}")
        print(f"   Net P&L:   ${result.net_profit:+.4f}")
        print(f"   ROI:       {(result.net_profit/budget)*100:+.3f}%")
        print(f"   Time:      {result.execution_time_ms}ms")
        return result
    else:
        print(f"   ❌ Failed: {result.error}")
        return None


async def run_spatial_demo(budget: float = 100.0, min_spread: float = 0.2):
    """Run the spatial arbitrage demo."""
    
    print("\n" + "="*70)
    print("   PHANTOM ARBITER - SPATIAL ARBITRAGE (QUICK FLIP) DEMO")
    print("="*70)
    print(f"   Budget: ${budget:.2f}")
    print(f"   Min Spread: {min_spread}%")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # ═══════════════════════════════════════════════════════════════════
    # STEP 1: Scan for Opportunities
    # ═══════════════════════════════════════════════════════════════════
    profitable_opps, all_opps = await find_spatial_opportunities(min_spread)
    
    # Show ALL spreads (even small ones)
    print(f"\n📊 CURRENT CROSS-DEX SPREADS:")
    print("-" * 70)
    print(f"   {'Pair':<12} {'Best Buy':<10} {'Price':<12} {'Best Sell':<10} {'Price':<12} {'Spread':<8}")
    print("-" * 70)
    
    for opp in all_opps:
        spread_color = "🟢" if opp.spread_pct >= 0.5 else "🟡" if opp.spread_pct >= 0.2 else "⚪"
        print(f"   {spread_color} {opp.pair:<10} {opp.buy_dex:<10} ${opp.buy_price:<10.6f} {opp.sell_dex:<10} ${opp.sell_price:<10.6f} +{opp.spread_pct:.2f}%")
    
    # ═══════════════════════════════════════════════════════════════════
    # STEP 2: Analyze Profitability
    # ═══════════════════════════════════════════════════════════════════
    print(f"\n💰 PROFITABILITY ANALYSIS:")
    print("-" * 70)
    
    FEE_PER_SWAP = 0.001  # 0.1% per swap
    TOTAL_FEES = FEE_PER_SWAP * 2  # Buy + Sell
    
    print(f"   Fee per swap: {FEE_PER_SWAP*100:.1f}%")
    print(f"   Total fees (buy+sell): {TOTAL_FEES*100:.2f}%")
    print(f"   Breakeven spread: >{TOTAL_FEES*100:.2f}%")
    print()
    
    for opp in all_opps:
        gross_profit = budget * (opp.spread_pct / 100)
        fees = budget * TOTAL_FEES
        net_profit = gross_profit - fees
        
        status = "✅ PROFITABLE" if net_profit > 0 else "❌ Fees > Spread"
        print(f"   {opp.pair:<12} Gross: ${gross_profit:+.4f} - Fees: ${fees:.4f} = Net: ${net_profit:+.4f}  {status}")
    
    # ═══════════════════════════════════════════════════════════════════
    # STEP 3: Execute Best Opportunity (if any)
    # ═══════════════════════════════════════════════════════════════════
    if profitable_opps:
        print(f"\n🎯 FOUND {len(profitable_opps)} PROFITABLE OPPORTUNITIES!")
        
        # Sort by spread (best first)
        profitable_opps.sort(key=lambda x: x.spread_pct, reverse=True)
        best = profitable_opps[0]
        
        print(f"\n   Best opportunity: {best.pair}")
        print(f"   Spread: +{best.spread_pct:.2f}%")
        print(f"   Expected net: ${budget * (best.spread_pct/100 - TOTAL_FEES):+.4f}")
        
        # Execute paper trade
        result = await execute_spatial_flip(best, budget)
        
    else:
        print(f"\n⚠️ NO PROFITABLE OPPORTUNITIES RIGHT NOW")
        print(f"   All spreads below {min_spread}% threshold")
        print(f"   Largest spread: +{all_opps[0].spread_pct:.2f}% on {all_opps[0].pair}" if all_opps else "   No data")
        print(f"\n   💡 TIP: Spatial arb opportunities are rare and fleeting.")
        print(f"   💡 MEV bots typically capture these in milliseconds.")
        print(f"   💡 For retail traders, funding rate arb is more consistent.")
    
    # ═══════════════════════════════════════════════════════════════════
    # COMPARISON: Spatial vs Funding
    # ═══════════════════════════════════════════════════════════════════
    print(f"\n" + "="*70)
    print(f"   STRATEGY COMPARISON (${budget} budget)")
    print("="*70)
    
    # Best spatial opportunity (if any)
    if all_opps:
        best_spatial = all_opps[0]
        spatial_gross = budget * (best_spatial.spread_pct / 100)
        spatial_fees = budget * 0.002
        spatial_net = spatial_gross - spatial_fees
        spatial_time = "~10 seconds"
    else:
        spatial_net = 0
        spatial_time = "N/A"
    
    # Funding rate (from earlier)
    funding_apr = 15.0  # ~15% APY typical
    funding_8h = budget * (funding_apr / 100 / 365) * (8/24)  # 8h of annual rate
    funding_fees = budget * 0.004  # Entry + Exit
    funding_net_24h = (funding_8h * 3) - funding_fees
    funding_time = "24+ hours"
    
    print(f"\n   {'Strategy':<20} {'Net P&L':<15} {'Time Required':<15} {'Risk':<15}")
    print("-" * 70)
    print(f"   {'SPATIAL (Quick Flip)':<20} ${spatial_net:+.4f}        {spatial_time:<15} {'MEV Competition':<15}")
    print(f"   {'FUNDING (Hold)':<20} ${funding_net_24h:+.4f}        {funding_time:<15} {'Funding Flip':<15}")
    
    print(f"\n   💡 INSIGHT: Spatial arb looks good on paper but:")
    print(f"      - Opportunities disappear in milliseconds (MEV bots)")
    print(f"      - Current spreads are typically <0.3%")
    print(f"      - Funding rate arb is more reliable for small budgets")
    
    print("\n" + "="*70)
    print("   END OF SPATIAL ARBITRAGE DEMO")
    print("="*70 + "\n")


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Spatial Arbitrage Demo")
    parser.add_argument("--budget", type=float, default=100.0, help="Budget in USD (default: 100)")
    parser.add_argument("--min-spread", type=float, default=0.2, help="Minimum spread % (default: 0.2)")
    
    args = parser.parse_args()
    
    asyncio.run(run_spatial_demo(args.budget, args.min_spread))
