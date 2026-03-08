"""
V20.2: Market Feeds Standalone (Portable)
=========================================
Standalone utility to pull live snapshots from Raydium and Orca.
Designed to mirror the future "DEX Spreads" card layout.

Outputs: Live Console Logs (Formatted)
"""

import asyncio
import os
import sys
import time
from typing import Dict, Any

# Set up paths
sys.path.append(os.getcwd())

from src.shared.system.logging import Logger
from src.shared.feeds.raydium_feed import RaydiumFeed
from src.shared.feeds.orca_feed import OrcaFeed

async def fetch_dex_spreads():
    Logger.section("PHASE 20: DEX MARKET FEEDS (RAYDIUM/ORCA)")
    
    ray = RaydiumFeed()
    orca = OrcaFeed()
    
    SOL = "So11111111111111111111111111111111111111112"
    USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    
    Logger.info("🔍 Scanning DEX Pool Spreads [SOL-USDC]...")
    
    while True:
        try:
            # 1. Fetch Spot Prices
            ray_task = ray.get_spot_price(SOL, USDC)
            orca_task = orca.get_spot_price(SOL, USDC)
            
            ray_spot, orca_spot = await asyncio.gather(ray_task, orca_task)
            
            # 2. Extract Data
            ray_price = ray_spot.price if ray_spot else 0.0
            orca_price = orca_spot.price if orca_spot else 0.0
            
            # 3. Calculate Arbitrage Spread (Reference for Arb Angle)
            spread = 0.0
            if ray_price > 0 and orca_price > 0:
                spread = abs(ray_price - orca_price)
                spread_pct = (spread / min(ray_price, orca_price)) * 100
            else:
                spread_pct = 0.0
                
            # 4. Formatted Console Logs (Mirroring Future Web UI)
            # [DEX] [POOL] [PRICE] [LIQUIDITY/STATUS]
            Logger.info("--------------------------------------------------")
            Logger.info(f"📍 RAYDIUM | SOL-USDC | ${ray_price:,.4f} | Status: ONLINE")
            Logger.info(f"📍 ORCA    | SOL-USDC | ${orca_price:,.4f} | Status: ONLINE")
            
            if spread_pct > 0.05: # Highlighting profitable spreads (0.05%+)
                color = "\033[93m" # Gold for opportunity
                Logger.info(f"{color}✨ OPPORTUNITY: {spread_pct:.4f}% Cross-DEX Spread Detected{reset}")
            else:
                Logger.info(f"📊 Market Parity: {spread_pct:.4f}% Spread (Neutral)")
                
            Logger.info("--------------------------------------------------")
            
            # Maintain observation loop (5s for spreads to avoid rate limits)
            await asyncio.sleep(5)
            
        except KeyboardInterrupt:
            Logger.info("🛑 Feed scanner stopped.")
            await ray.close()
            await orca.close()
            break
        except Exception as e:
            Logger.error(f"❌ Feed Error: {e}")
            await asyncio.sleep(5)

# ANSI Reset helper (since Logger._parse might strip it)
reset = "\033[0m"

if __name__ == "__main__":
    try:
        asyncio.run(fetch_dex_spreads())
    except KeyboardInterrupt:
        pass
