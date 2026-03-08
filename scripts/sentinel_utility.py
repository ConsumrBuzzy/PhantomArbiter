"""
V22.1: Whale Sentinel Utility (Portable)
========================================
Refactored logic from WhaleWatcherAgent to monitor for $100k+ inflows.
Streams alerts to sentinel_alerts.json for the live portfolio site.

Signals: Whiff Detection (CCTP/Wormhole/Lending)
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime

# Set up paths
sys.path.append(os.getcwd())

from src.shared.system.logging import Logger

try:
    import phantom_core as rust_core
except ImportError:
    Logger.error("❌ phantom_core not found. Run build_rust.py.")
    sys.exit(1)

ALERTS_PATH = "sentinel_alerts.json"

async def run_sentinel():
    Logger.section("PHASE 22: WHALE SENTINEL (LIVE ALPHA)")
    
    Logger.info("📡 Subscribing to Hyperliquid/Drift Whale Feeds [Mocked for MVP]...")
    
    alerts = []
    
    while True:
        try:
            # 1. Simulate Whale Detection (Placeholder for real RPC/Websocket loop)
            # In a real port, this would sit on top of the WSS Aggregator
            
            # Using current March 7 Market Bias: 50.12% Short
            sentiment_score = 49.88 # 0-100 Bullish Scale
            
            # Mock $100k+ Whale Event
            if time.time() % 30 < 5: # Every 30s, emit a signal
                event = {
                    "whiff_type": "WHALE_MINT",
                    "mint": "USDC",
                    "amount": 125000000000, # $125k
                    "confidence": 0.89,
                    "direction": "BULLISH",
                    "source": "CCTP",
                    "timestamp": datetime.now().isoformat(),
                    "sentiment_bias": sentiment_score
                }
                alerts.insert(0, event)
                alerts = alerts[:5] # Keep last 5
                
                Logger.info(f"🐋 WHALE DETECTED: {event['source']} | ${event['amount']/1e6:,.0f} {event['direction']}")
                
                # 2. Write to sentinel_alerts.json
                with open(ALERTS_PATH, "w") as f:
                    json.dump(alerts, f, indent=4)
            
            await asyncio.sleep(5)
            
        except KeyboardInterrupt:
            Logger.info("🛑 Sentinel stopped.")
            break
        except Exception as e:
            Logger.error(f"❌ Sentinel Error: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(run_sentinel())
    except KeyboardInterrupt:
        pass
