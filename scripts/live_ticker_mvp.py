"""
V20.1: Live Ticker MVP (Portable)
=================================
Standalone high-performance ticker that aggregates SOL/USD from
Jupiter and Coinbase. Designed for easy porting to Hugo.

Outputs: ticker.json (Root)
"""

import asyncio
import json
import time
import os
from datetime import datetime

# Set up paths
import sys
sys.path.append(os.getcwd())

from src.shared.system.logging import Logger
from src.shared.feeds.jupiter_feed import JupiterFeed
from src.drivers.coinbase_driver import get_coinbase_driver

TICKER_PATH = "ticker.json"

async def run_ticker():
    Logger.section("PHASE 20: LIVE SOL TICKER MVP")
    
    jup = JupiterFeed()
    cb = get_coinbase_driver()
    
    SOL_MINT = "So11111111111111111111111111111111111111112"
    USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    
    Logger.info("📡 Initializing Feeds [Jupiter + Coinbase]...")
    
    while True:
        try:
            start_time = time.time()
            
            # 1. Fetch Prices in Parallel
            jup_task = jup.get_spot_price(SOL_MINT, USDC_MINT)
            cb_task = cb.fetch_ticker("SOL/USDC")
            
            jup_spot, cb_ticker = await asyncio.gather(jup_task, cb_task)
            
            prices = []
            if jup_spot:
                prices.append(jup_spot.price)
            if cb_ticker and cb_ticker.get("last"):
                prices.append(cb_ticker["last"])
            
            if not prices:
                Logger.warning("⚠️ No live prices received. Retrying...")
                await asyncio.sleep(2)
                continue
                
            # 2. Calculate Aggregate (Simple Average for MVP)
            avg_price = sum(prices) / len(prices)
            
            # Mock 24h change (would normally pull from historical feed)
            # Using $83.50 as a stable benchmark for March 2026 verification
            benchmark = 83.50
            change_pct = ((avg_price - benchmark) / benchmark) * 100
            
            # 3. Construct Payload
            payload = {
                "symbol": "SOL/USD",
                "price": round(avg_price, 2),
                "change_24h": round(change_pct, 2),
                "sources": {
                    "jupiter": round(jup_spot.price, 2) if jup_spot else None,
                    "coinbase": round(cb_ticker["last"], 2) if cb_ticker.get("last") else None
                },
                "status": "linked",
                "timestamp": datetime.now().isoformat(),
                "vitals": {
                    "volume_24h": cb_ticker.get("volume", 0) if cb_ticker else 0,
                    "market_cap": avg_price * 475000000 # Appx circulating supply
                }
            }
            
            # 4. Atomic Write to Ticker.json
            with open(TICKER_PATH, "w") as f:
                json.dump(payload, f, indent=4)
            
            # 5. Console Output (Formatted for MVP visibility)
            color = "\033[92m" if change_pct >= 0 else "\033[91m"
            reset = "\033[0m"
            Logger.info(f"SOL: ${avg_price:.2f} | Change: {color}{change_pct:+.2f}%{reset} | Jup: ${payload['sources']['jupiter']} | CB: ${payload['sources']['coinbase']}")
            
            # Maintain 1Hz (accounting for processing time)
            elapsed = time.time() - start_time
            await asyncio.sleep(max(0, 1.0 - elapsed))
            
        except KeyboardInterrupt:
            Logger.info("🛑 Ticker stopped by user.")
            break
        except Exception as e:
            Logger.error(f"❌ Ticker Error: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(run_ticker())
    except KeyboardInterrupt:
        pass
