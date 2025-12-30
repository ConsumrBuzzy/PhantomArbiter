import sys
import os
import asyncio
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from src.shared.system.signal_bus import signal_bus, Signal, SignalType
from src.engine.director import Director
from src.shared.system.logging import Logger
from config.settings import Settings

async def verify_bus():
    print("🚌 Verifying Cross-Strategy Signal Bus (V41.0)...")
    
    # 1. Setup Director (Mock agents)
    director = Director(lite_mode=True)
    
    # Mock Arbiter and its engine
    class MockEngine:
        def inject_priority_token(self, token):
            print(f"   ✅ [Engine] Priority Injection Triggered for {token}!")

    class MockArbiter:
        def __init__(self):
            self._engine = MockEngine()
            self.config = type('Config', (), {'pairs': []})()
            
        def handle_strategy_tip(self, token: str):
            print(f"   ✅ [Arbiter] Received Tip: {token}")
            self._engine.inject_priority_token(token)

    director.agents["arbiter"] = MockArbiter()
    
    # 2. Emit Scalp Signal (High Confidence)
    print("📢 Emitting High Confidence SCALP_SIGNAL...")
    signal = Signal(
        type=SignalType.SCALP_SIGNAL,
        source="Scalper",
        data={
            "symbol": "PUMP_TOKEN", 
            "confidence": 0.95, 
            "action": "BUY"
        }
    )
    
    # Manually trigger routing (since Director loop isn't running full async)
    # We can access the callback directly or just emit and wait a bit
    signal_bus.emit(signal)
    
    # Give asyncio a moment to process the callback
    await asyncio.sleep(0.5)
    
    # 3. Emit Low Confidence (Should NOT trigger)
    print("📢 Emitting Low Confidence Signal (Should be ignored)...")
    signal_low = Signal(
        type=SignalType.SCALP_SIGNAL,
        source="Scalper",
        data={
            "symbol": "DUMP_TOKEN", 
            "confidence": 0.4, 
            "action": "BUY"
        }
    )
    signal_bus.emit(signal_low)
    await asyncio.sleep(0.5)
    
    print("🎉 Bus Verification Complete.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(verify_bus())
