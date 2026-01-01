import asyncio
import aiohttp
import sys

async def test_connectivity():
    print("🧪 Testing PhantomArbiter Connectivity...")
    
    # Test 1: HTTP API
    try:
        async with aiohttp.ClientSession() as session:
            print("   ⏳ Testing HTTP GET /api/v1/galaxy...")
            async with session.get('http://localhost:8000/api/v1/galaxy') as resp:
                print(f"      HTTP Status: {resp.status}")
                if resp.status == 200:
                    data = await resp.json()
                    print(f"      ✅ Galaxy Data: {len(data)} nodes returned")
                else:
                    print(f"      ❌ HTTP Failed: {await resp.text()}")
    except Exception as e:
        print(f"      ❌ HTTP Connection Error: {e}")

    # Test 2: WebSocket
    try:
        async with aiohttp.ClientSession() as session:
            print("   ⏳ Testing WebSocket /ws/v1/stream...")
            async with session.ws_connect('ws://localhost:8000/ws/v1/stream') as ws:
                print("      ✅ WebSocket Connected!")
                await ws.send_str("PING")
                print("      Sent PING")
                # Wait for potential messages
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=3.0)
                    print(f"      📩 Received: {msg.type} {msg.data[:50]}...")
                except asyncio.TimeoutError:
                    print("      ⚠️ No welcome message (this is okay if system is quiet)")
                
                await ws.close()
                print("      WebSocket Closed Properly")
    except Exception as e:
        print(f"      ❌ WebSocket Connection Error: {e}")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_connectivity())
