import asyncio
import aiohttp
import sys

async def test_connectivity():
    print("🧪 Testing PhantomArbiter Connectivity (127.0.0.1:8001)...")
    
    # Updated to 8001
    timeout = aiohttp.ClientTimeout(total=5)

    # Test 1: HTTP API
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            print("   ⏳ Testing HTTP GET http://127.0.0.1:8001/api/v1/galaxy...")
            async with session.get('http://127.0.0.1:8001/api/v1/galaxy') as resp:
                print(f"      HTTP Status: {resp.status}")
                if resp.status == 200:
                    data = await resp.json()
                    print(f"      ✅ Galaxy Data: {len(data)} nodes returned")
                else:
                    print(f"      ❌ HTTP Failed: {await resp.text()}")
    except asyncio.TimeoutError:
         print("      ❌ HTTP Request Timed Out")
    except Exception as e:
        print(f"      ❌ HTTP Connection Error: {e}")

    # Test 2: WebSocket
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            print("   ⏳ Testing WebSocket ws://127.0.0.1:8001/ws/v1/stream...")
            async with session.ws_connect('ws://127.0.0.1:8001/ws/v1/stream') as ws:
                print("      ✅ WebSocket Connected!")
                await ws.send_str("PING")
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=3.0)
                    print(f"      📩 Received: {msg.type} {msg.data[:50]}...")
                except asyncio.TimeoutError:
                    print("      ⚠️ No welcome message")
                
                await ws.close()
    except asyncio.TimeoutError:
         print("      ❌ WebSocket Timed Out")
    except Exception as e:
        print(f"      ❌ WebSocket Connection Error: {e}")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_connectivity())
