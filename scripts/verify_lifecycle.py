
import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.shared.system.signal_bus import signal_bus, Signal, SignalType
from src.scraper.agents.scout_agent import ScoutAgent
from src.shared.system.logging import Logger
from config.settings import Settings

async def verify_lifecycle():
    Logger.info("🧪 [VERIFY] Starting Lifecycle Discovery Verification")
    
    # 1. Initialize Scout
    scout = ScoutAgent()
    await scout.start()
    
    # Mints to test (Mocking)
    # 1. A known Pump.fun token (if available) - usually starts with 6EF8...
    # 2. A known Standard AMM token
    # 3. A known CLMM token
    
    # Test Mints (Placeholder/Known)
    # Using a known Pump.fun mint for testing if possible, else we'll see "UNKNOWN"
    test_mints = [
        "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P", # Pump.fun Program ID itself (for test)
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", # USDC (Probably CLMM/Standard)
        "So11111111111111111111111111111111111111112"  # SOL
    ]
    
    for mint in test_mints:
        Logger.info(f"\n🔍 Testing Mint: {mint}")
        
        # Emit NEW_TOKEN signal
        signal_bus.emit(Signal(
            type=SignalType.NEW_TOKEN,
            source="VERIFIER",
            data={"mint": mint, "platform": "MOCK"}
        ))
        
        # Wait for Scout to process
        await asyncio.sleep(5)
        
        # We can't easily check the internal token_registry of Director from here 
        # unless we access it. But we can check logs.
        
    scout.stop()
    Logger.info("\n✅ [VERIFY] Verification Finished. Check logs for stage detections.")

if __name__ == "__main__":
    asyncio.run(verify_lifecycle())
