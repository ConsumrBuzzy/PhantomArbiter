"""
Phantom Arbiter - End-to-End Paper Trade Test
==============================================
Tests the complete funding rate arbitrage flow:

1. Check sentiment (Fear & Greed + LunarCrush)
2. Check funding rates (Drift)
3. Validate entry conditions
4. Execute atomic position (spot + perp)
5. Monitor for exit conditions
6. Simulate funding collection
7. Exit position and calculate P&L

Usage:
    python run_paper_trade_test.py
    python run_paper_trade_test.py --coin SOL --budget 50
"""

import asyncio
import time
import argparse
from datetime import datetime

from config.settings import Settings


async def run_paper_trade(coin: str = "SOL", budget: float = 50.0):
    """Run a complete paper trade simulation."""
    
    print("\n" + "="*70)
    print("   PHANTOM ARBITER - END-TO-END PAPER TRADE TEST")
    print("="*70)
    print(f"   Coin: {coin}")
    print(f"   Budget: ${budget:.2f}")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # ═══════════════════════════════════════════════════════════════════
    # STEP 1: Check Sentiment
    # ═══════════════════════════════════════════════════════════════════
    print("\n📊 STEP 1: Checking Sentiment...")
    print("-"*50)
    
    from src.arbitrage.core.sentiment_engine import SentimentEngine
    
    sentiment_engine = SentimentEngine()
    sentiment = await sentiment_engine.get_sentiment_score(coin)
    
    print(sentiment)
    
    # ═══════════════════════════════════════════════════════════════════
    # STEP 2: Check Funding Rates
    # ═══════════════════════════════════════════════════════════════════
    print("\n💰 STEP 2: Checking Funding Rates...")
    print("-"*50)
    
    from src.arbitrage.feeds.drift_funding import MockDriftFundingFeed
    
    funding_feed = MockDriftFundingFeed()
    funding_info = await funding_feed.get_funding_rate(f"{coin}-PERP")
    
    if funding_info:
        print(f"   Market:     {funding_info.market}")
        print(f"   Rate (8h):  +{funding_info.rate_8h:.4f}%")
        print(f"   APY:        +{funding_info.rate_annual:.1f}%")
        print(f"   Next Fund:  {funding_info.time_to_next_funding // 60} min")
        funding_apr = funding_info.rate_annual
    else:
        print("   ❌ Could not fetch funding rate")
        return
    
    # ═══════════════════════════════════════════════════════════════════
    # STEP 3: Entry Filter Decision
    # ═══════════════════════════════════════════════════════════════════
    print("\n🎯 STEP 3: Entry Filter Decision...")
    print("-"*50)
    
    entry_decision = sentiment_engine.get_entry_filter(sentiment, funding_apr)
    
    print(f"   Action:  {entry_decision['action']}")
    print(f"   Reason:  {entry_decision['reason']}")
    print(f"   Enter:   {'✅ YES' if entry_decision['should_enter'] else '❌ NO'}")
    
    # For testing, we'll proceed even if sentiment says wait
    proceed = True
    if not entry_decision['should_enter']:
        print("\n   ⚠️ Sentiment says WAIT, but proceeding for demo...")
        proceed = True
    
    if not proceed:
        print("\n   🛑 Stopping - entry conditions not met")
        return
    
    # ═══════════════════════════════════════════════════════════════════
    # STEP 4: Execute Atomic Entry
    # ═══════════════════════════════════════════════════════════════════
    print("\n⚡ STEP 4: Executing Atomic Entry (Paper Mode)...")
    print("-"*50)
    
    from src.arbitrage.core.atomic_executor import AtomicExecutor
    
    executor = AtomicExecutor(paper_mode=True)
    entry_result = await executor.execute_funding_arb(coin, budget)
    
    if not entry_result['success']:
        print(f"   ❌ Entry failed: {entry_result.get('error')}")
        return
    
    position = entry_result['position']
    print(f"   ✅ Position Opened!")
    print(f"   Spot:    {position.spot_amount:.6f} {coin} @ ${position.entry_spot_price:.2f}")
    print(f"   Perp:    {position.perp_amount:.6f} {coin}-PERP @ ${position.entry_perp_price:.2f}")
    print(f"   Total:   ${position.total_usd:.2f}")
    print(f"   Fees:    ${entry_result['fees_paid']:.4f}")
    
    # ═══════════════════════════════════════════════════════════════════
    # STEP 5: Simulate Funding Collection (8 hours of payments)
    # ═══════════════════════════════════════════════════════════════════
    print("\n⏰ STEP 5: Simulating Funding Collection...")
    print("-"*50)
    
    # Calculate funding per 8h period
    funding_per_period = position.total_usd * (funding_info.rate_8h / 100)
    print(f"   Funding Rate:   +{funding_info.rate_8h:.4f}%/8h")
    print(f"   Position Size:  ${position.total_usd:.2f}")
    print(f"   Funding/Period: ${funding_per_period:.4f}")
    
    # Simulate 3 funding periods (24 hours)
    print("\n   Simulating 24 hours (3 funding periods):")
    total_funding = 0.0
    for i in range(3):
        total_funding += funding_per_period
        position.funding_collected = total_funding
        print(f"      Period {i+1}: +${funding_per_period:.4f} → Total: ${total_funding:.4f}")
    
    print(f"\n   Total Collected: ${total_funding:.4f} (24h)")
    
    # ═══════════════════════════════════════════════════════════════════
    # STEP 6: Check Exit Conditions
    # ═══════════════════════════════════════════════════════════════════
    print("\n🚨 STEP 6: Checking Exit Conditions...")
    print("-"*50)
    
    from src.arbitrage.core.exit_conditions import ExitConditionMonitor
    
    exit_monitor = ExitConditionMonitor(executor=executor)
    exit_signals = await exit_monitor.check_all_positions()
    
    print(exit_monitor.get_exit_recommendation(exit_signals))
    
    # ═══════════════════════════════════════════════════════════════════
    # STEP 7: Exit Position
    # ═══════════════════════════════════════════════════════════════════
    print("\n📤 STEP 7: Exiting Position...")
    print("-"*50)
    
    exit_result = await executor.close_position(coin)
    
    if exit_result['success']:
        print(f"   ✅ Position Closed!")
        print(f"   Net P&L:  ${exit_result['net_pnl']:+.4f}")
        print(f"   Fees:     ${exit_result['fees_paid']:.4f}")
    else:
        print(f"   ❌ Exit failed: {exit_result.get('error')}")
        return
    
    # ═══════════════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "="*70)
    print("   PAPER TRADE SUMMARY")
    print("="*70)
    
    entry_fees = entry_result['fees_paid']
    exit_fees = exit_result['fees_paid']
    total_fees = entry_fees + exit_fees
    gross_profit = total_funding
    net_profit = gross_profit - total_fees
    
    print(f"   Budget:         ${budget:.2f}")
    print(f"   Funding (24h):  ${gross_profit:.4f}")
    print(f"   Entry Fees:     -${entry_fees:.4f}")
    print(f"   Exit Fees:      -${exit_fees:.4f}")
    print(f"   ────────────────────────────")
    print(f"   Net Profit:     ${net_profit:+.4f}")
    
    if net_profit > 0:
        roi = (net_profit / budget) * 100
        daily_roi = roi
        monthly_roi = daily_roi * 30
        print(f"\n   ✅ PROFITABLE TRADE!")
        print(f"   ROI (24h):      {daily_roi:+.4f}%")
        print(f"   Projected (30d): {monthly_roi:+.2f}%")
    else:
        print(f"\n   ❌ UNPROFITABLE (need more holding time)")
        # Calculate breakeven
        if funding_per_period > 0:
            periods_to_breakeven = total_fees / funding_per_period
            hours_to_breakeven = periods_to_breakeven * 8
            print(f"   Breakeven:      {hours_to_breakeven:.0f} hours ({hours_to_breakeven/24:.1f} days)")
    
    print("\n" + "="*70)
    print("   END OF PAPER TRADE TEST")
    print("="*70 + "\n")
    
    return {
        "coin": coin,
        "budget": budget,
        "gross_profit": gross_profit,
        "total_fees": total_fees,
        "net_profit": net_profit,
        "sentiment_score": sentiment.score,
        "funding_apr": funding_apr
    }


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phantom Arbiter Paper Trade Test")
    parser.add_argument("--coin", type=str, default="SOL", help="Coin to trade (default: SOL)")
    parser.add_argument("--budget", type=float, default=50.0, help="Budget in USD (default: 50)")
    
    args = parser.parse_args()
    
    result = asyncio.run(run_paper_trade(args.coin, args.budget))
    
    if result:
        print(f"Test completed. Net P&L: ${result['net_profit']:+.4f}")
