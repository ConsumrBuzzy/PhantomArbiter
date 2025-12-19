
import sys
import os
import asyncio

# Add root project dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.discovery.sauron_discovery import SauronDiscovery

async def test_sauron_connection():
    sauron = SauronDiscovery()
    
    # We redefine start slightly to run for only 15 seconds then exit for test
    if not sauron.api_key:
        print("❌ test_sauron: No API Key")
        return

    print("🧪 Starting Sauron Test (10s duration)...")
    
    # Run in background task
    task = asyncio.create_task(sauron.start())
    
    await asyncio.sleep(10)
    print("⏳ Test duration ended. Stopping...")
    sauron.stop()
    
    # Wait a bit for closure
    await asyncio.sleep(2)
    task.cancel()
    print("✅ Test Complete")

if __name__ == "__main__":
    asyncio.run(test_sauron_connection())
