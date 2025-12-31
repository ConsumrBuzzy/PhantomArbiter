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
                seq = data.get("sequence", 0)
                nodes = len(data.get("nodes", []))
                links = len(data.get("links", []))
                
                # For Diffs, show counts. For Snapshots, show totals.
                if msg_type == "diff":
                    rem_nodes = len(data.get("removed_node_ids", []))
                    print(f"📉 [#{seq}] Received DIFF: {nodes} upserted, {links} updated links, {rem_nodes} removed")
                else:
                    print(f"📸 [#{seq}] Received SNAPSHOT: {nodes} nodes, {links} links")

    except Exception as e:
        print(f"❌ Connection Error: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(listen())
    except KeyboardInterrupt:
        pass
