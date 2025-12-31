"""
Visual Bridge
=============
Phase 25: Real-Time Visualization

A WebSocket server that acts as the "Heartbeat" of the visual layer.
It streams the current state of the Market Graph (Nodes/Links) to any
connected frontend (local browser, desktop app, etc.).
"""

import asyncio
import json
import websockets
from websockets.server import serve
import logging

from src.shared.persistence.market_manager import MarketManager
from src.shared.schemas.graph_protocol import GraphPayload

# Configure Logging
logger = logging.getLogger("VisualBridge")


class VisualBridge:
    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port
        self.server = None
        self.connected_clients = set()
        self.market_manager = MarketManager()
        self.is_running = False

    async def register(self, websocket):
        """Register a new client connection."""
        self.connected_clients.add(websocket)
        logger.info(f"➕ Client Connected. Total: {len(self.connected_clients)}")
        
        # Send immediate snapshot on connect
        await self.send_snapshot(websocket)

    async def unregister(self, websocket):
        """Unregister a client connection."""
        self.connected_clients.remove(websocket)
        logger.info(f"➖ Client Disconnected. Total: {len(self.connected_clients)}")

    async def handler(self, websocket):
        """Main WebSocket handler."""
        await self.register(websocket)
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    if data.get("action") == "REQUEST_SYNC":
                        logger.info(f"🔄 Client requested SYNC. Resetting Snapshot.")
                        await self.send_snapshot(websocket)
                    elif data.get("action") == "PONG":
                        # Keep-alive received, could update timestamp here
                        pass
                except json.JSONDecodeError:
                    pass
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self.unregister(websocket)

    async def send_snapshot(self, websocket):
        """Sends a full snapshot to reset the client state."""
        try:
            snapshot = self.market_manager.get_graph_data()
            # Reset/Set sequence ID for this snapshot
            snapshot['seq_id'] = self.current_seq_id
            snapshot['type'] = 'snapshot'
            await websocket.send(json.dumps(snapshot))
        except Exception as e:
            logger.error(f"❌ Failed to send snapshot: {e}")

    async def send_update(self, websocket, message: str):
        """Send a message to a specific client."""
        try:
            await websocket.send(message)
        except websockets.exceptions.ConnectionClosed:
            logger.warning("⚠️ Connection closed during send.")
        except Exception as e:
            logger.error(f"❌ Send Error: {e}")

    async def broadcast_loop(self):
        """Periodically fetch graph data and broadcast to all clients."""
        logger.info("📡 Broadcast Loop Started.")
        while self.is_running:
            try:
                # 1. Get Fresh Data (Differential)
                payload_data: GraphPayload = self.market_manager.get_graph_diff()
                
                # Assign Global Sequence ID
                self.current_seq_id += 1
                payload_data['seq_id'] = self.current_seq_id
                payload_data['type'] = 'diff'
                
                # 2. Serialize to JSON
                payload = json.dumps(payload_data)
                
                # 3. Broadcast
                if self.connected_clients:
                    tasks = [self.send_update(client, payload) for client in self.connected_clients]
                    if tasks:
                        await asyncio.gather(*tasks)
                        # logger.debug(f"📤 Broadcast SEQ:{self.current_seq_id}") 
                        
            except Exception as e:
                logger.error(f"❌ Broadcast Error: {e}")
                
            # Rate Limit (e.g., 2 FPS for stability)
            await asyncio.sleep(0.5)

    async def heartbeat_loop(self):
        """Sends PING every 5s to keep connections alive."""
        while self.is_running:
            if self.connected_clients:
                ping_payload = json.dumps({"type": "PING"})
                tasks = [self.send_update(client, ping_payload) for client in self.connected_clients]
                await asyncio.gather(*tasks)
            await asyncio.sleep(5)

    async def start(self):
        """Starts the WebSocket server and background loops."""
        self.is_running = True
        self.current_seq_id = 0

        async with serve(self.handler, self.host, self.port):
            logger.info(f"🌉 Visual Bridge Running on ws://{self.host}:{self.port}")
            
            # Run loops concurrently
            await asyncio.gather(
                self.broadcast_loop(),
                self.heartbeat_loop()
            )

