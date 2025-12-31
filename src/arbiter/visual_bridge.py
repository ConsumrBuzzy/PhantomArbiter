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
import logging
import websockets
from websockets.server import serve

from src.shared.persistence.market_manager import MarketManager
from src.shared.system.logging import Logger

class VisualBridge:
    def __init__(self, host="localhost", port=8765, update_interval=2.0):
        self.host = host
        self.port = port
        self.update_interval = update_interval
        self.market_manager = MarketManager()
        self.connected_clients = set()
        self.running = False

    async def register(self, websocket):
        self.connected_clients.add(websocket)
        Logger.info(f"   🔌 Client Connected. Total: {len(self.connected_clients)}")
        # Send immediate update on connect
        await self.send_update(websocket)

    async def unregister(self, websocket):
        self.connected_clients.remove(websocket)
        Logger.info(f"   🔌 Client Disconnected. Total: {len(self.connected_clients)}")

    async def handler(self, websocket):
        await self.register(websocket)
        try:
            async for message in websocket:
                # Handle any incoming control messages here (e.g. "filter:min_liq=X")
                # For now, we just ignore inputs or log them
                pass
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self.unregister(websocket)

    async def send_update(self, websocket):
        """Sends current graph snapshot to a specific client."""
        try:
            data = self.market_manager.get_graph_data()
            message = json.dumps({
                "type": "graph_snapshot",
                "data": data
            })
            await websocket.send(message)
        except Exception as e:
            Logger.error(f"❌ Bridge Send Error: {e}")

    async def broadcast_loop(self):
        """Periodically broadcasts updates to all clients."""
        Logger.info(f"   📡 Broadcast Loop Started (Interval: {self.update_interval}s)")
        while self.running:
            try:
                if self.connected_clients:
                    # Fetch fresh data
                    # Note: In a real high-freq scenario, we might want to check if data CHANGED
                    # before sending. For now, we send snapshots.
                    data = self.market_manager.get_graph_data()
                    message = json.dumps({
                        "type": "graph_update",
                        "data": data,
                        "meta": {"clients": len(self.connected_clients)}
                    })
                    
                    # Broadcast
                    websockets.broadcast(self.connected_clients, message)
                    
                await asyncio.sleep(self.update_interval)
            except Exception as e:
                Logger.error(f"❌ Broadcast Error: {e}")
                await asyncio.sleep(1) # Backoff on error

    async def start(self):
        """Starts the WebSocket server and the broadcast loop."""
        self.running = True
        
        server = await serve(self.handler, self.host, self.port)
        Logger.info(f"🌉 Visual Bridge Running on ws://{self.host}:{self.port}")
        
        # Run broadcast loop alongside server
        await self.broadcast_loop()
