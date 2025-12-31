"""
Test WebSocket Client
=====================
Phase 25 Verification

Connects to the Visual Bridge and prints received graph updates.
"""

import asyncio
import websockets
import json


async def listen():
    uri = "ws://localhost:8765"
    print(f"🔌 Connecting to {uri}...")

    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Connected!")

            while True:
                message = await websocket.recv()
                data = json.loads(message)

                msg_type = data.get("type", "unknown")
                graph_data = data.get("data", {})
                nodes = len(graph_data.get("nodes", []))
                links = len(graph_data.get("links", []))

                print(f"📩 Received {msg_type}: {nodes} nodes, {links} links")

    except Exception as e:
        print(f"❌ Connection Error: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(listen())
    except KeyboardInterrupt:
        pass
