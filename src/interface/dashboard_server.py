
import asyncio
import json
import websockets
from typing import Dict, Any, Set
from src.shared.system.signal_bus import signal_bus, SignalType, Signal
from src.arbiter.visual_transformer import VisualTransformer
from src.shared.system.logging import Logger

class DashboardServer:
    """
    "The Voice" - WebSocket Server Bridge
    Bridges internal SignalBus events to external WebSocket clients (The Void).
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self.running = False

    async def start(self):
        """Ignite the WebSocket Server."""
        self.running = True
        
        # 1. Subscribe to SignalBus
        signal_bus.subscribe(SignalType.MARKET_UPDATE, self._handle_signal)
        signal_bus.subscribe(SignalType.NEW_TOKEN, self._handle_signal)
        signal_bus.subscribe(SignalType.WHALE_ACTIVITY, self._handle_signal)
        
        Logger.info(f"   🎙️  Dashboard Voice active on ws://{self.host}:{self.port}")

        # 2. Start Server
        async with websockets.serve(self._handler, self.host, self.port):
            await asyncio.Future()  # Run forever

    async def _handler(self, websocket):
        """Handle new client connections."""
        self.clients.add(websocket)
        try:
            async for message in websocket:
                data = json.loads(message)
                if data.get("action") == "REQUEST_SYNC":
                    # Send sync data if needed (e.g. current universe state)
                    await websocket.send(json.dumps({"type": "PING", "msg": "PONG"}))
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.clients.remove(websocket)

    async def _handle_signal(self, signal: Signal):
        """Transform and broadcast signals to the Void."""
        if not self.clients:
            return

        payload = VisualTransformer.transform(signal)
        if payload:
            message = json.dumps(payload)
            # Broadcast to all connected clients
            await asyncio.gather(
                *[client.send(message) for client in self.clients],
                return_exceptions=True
            )

if __name__ == "__main__":
    # Test Run
    server = DashboardServer()
    asyncio.run(server.start())
