
import sys
import os
import asyncio
import json
from unittest.mock import MagicMock, AsyncMock

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.shared.infrastructure.log_harvester import LogHarvester
from src.shared.system.signal_bus import signal_bus, SignalType
from src.shared.system.logging import Logger

async def mock_listen(harvester):
    # Simulate receiving a message
    fake_log = {
        "method": "logsNotification",
        "params": {
            "result": {
                "value": {
                    "signature": "TX_SIG_123_TEST",
                    "logs": [
                        "Program 675kPX9MCyJsD5ippTu671dKKkCtSE5v4RBmZJtHNv9v invoke [1]",
                        "log: initialize2: ...",
                        "Program 675kPX9MCyJsD5ippTu671dKKkCtSE5v4RBmZJtHNv9v success"
                    ]
                }
            }
        }
    }
    
    await harvester._process_message(fake_log)

def verify_harvester():
    print("🧪 Testing Log Harvester...")
    
    harvester = LogHarvester()
    
    # Capture Signals
    signals_received = []
    def on_signal(sig):
        if sig.type == SignalType.NEW_TOKEN:
            signals_received.append(sig)
            
    signal_bus.subscribe(SignalType.NEW_TOKEN, on_signal)
    
    # Run Mock
    print("   👉 Injecting Fake 'initialize2' Log...")
    asyncio.run(mock_listen(harvester))
    
    # Assert
    if len(signals_received) > 0:
        sig = signals_received[0]
        print(f"   ✅ Graduation Signal Detected: {sig.data['signature']}")
        if sig.data['program'] == "RAYDIUM":
            print("   ✅ Program Identified: RAYDIUM")
        else:
            print(f"   ❌ Wrong Program: {sig.data['program']}")
    else:
        print("   ❌ No Signal Emitted")

    # Stats Check
    if harvester.stats["graduations"] == 1:
        print("   ✅ Stats Updated Correctly")
    else:
        print(f"   ❌ Stats Count Wrong: {harvester.stats}")

if __name__ == "__main__":
    verify_harvester()
