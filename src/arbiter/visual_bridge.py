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
from src.shared.system.signal_bus import signal_bus, SignalType, Signal

# Configure Logging
logger = logging.getLogger("VisualBridge")


class VisualBridge:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self.server = None
        self.connected_clients = set()
        self.market_manager = MarketManager()
        self.is_running = False
        self._setup_signal_listener()

    def _setup_signal_listener(self):
        """Subscribe to SignalBus for real-time events."""
        
        # V33: Import Transformer
        from src.arbiter.visual_transformer import VisualTransformer

        async def handle_market_update(sig: Signal):
            # Transform Raw Signal -> Visual Globe
            payload = VisualTransformer.transform(sig)
            
            if payload:
                # Serialize and Broadcast
                # We use fire-and-forget to avoid blocking the bus
                packet = json.dumps(payload)
                asyncio.create_task(self._broadcast_flash(packet))

        signal_bus.subscribe(SignalType.MARKET_UPDATE, handle_market_update)
        signal_bus.subscribe(SignalType.SCALP_SIGNAL, handle_market_update)

    async def _broadcast_flash(self, payload: str):
        """High-speed broadcast for flash events."""
        if self.connected_clients:
            tasks = [self.send_update(client, payload) for client in self.connected_clients]
            await asyncio.gather(*tasks)

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
            # logger.warning("⚠️ Connection closed during send.")
            pass # Suppress warning for high-freq flashes
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
        """Sends PING every 5s and Test Archetypes if idle."""
        import random
        from src.arbiter.visual_transformer import VisualTransformer
        
        while self.is_running:
            if self.connected_clients:
                # 1. Ping
                ping_payload = json.dumps({"type": "PING"})
                tasks = [self.send_update(client, ping_payload) for client in self.connected_clients]
                await asyncio.gather(*tasks)
                
                # 2. V33: TEST ARCHEOTYPE
                # Randomly pick a source to trigger various archetypes
                sources = ["WSS_Listener", "PYTH", "PUMP_GRAD", "DISCOVERY"]
                mock_sig = Signal(
                    type=SignalType.MARKET_UPDATE,
                    source=random.choice(sources),
                    data={
                        "mint": f"TEST_{random.randint(1000,9999)}",
                        "symbol": "MOCK_TK",
                        "price": 1.23,
                        "timestamp": 0
                    }
                )
                
                payload = VisualTransformer.transform(mock_sig)
                if payload:
                    packet = json.dumps(payload)
                    tasks = [self.send_update(client, packet) for client in self.connected_clients]
                    await asyncio.gather(*tasks)

            await asyncio.sleep(2.0) # 2s heartbeat

    async def start(self):
        """Starts the WebSocket server and background loops."""
        self.is_running = True
        self.current_seq_id = 0

        try:
            async with serve(self.handler, self.host, self.port):
                logger.info(f"🌉 Visual Bridge Running on ws://{self.host}:{self.port}")
                print(f"🌉 Visual Bridge Online: ws://{self.host}:{self.port}")
                
                # Run loops concurrently
                await asyncio.gather(
                    self.broadcast_loop(),
                    self.heartbeat_loop()
                )
        except Exception as e:
            logger.error(f"❌ Visual Bridge Server Error: {e}")
            print(f"❌ Visual Bridge Failed to Start: {e}")
            self.is_running = False

