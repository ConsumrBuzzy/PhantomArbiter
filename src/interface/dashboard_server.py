
import asyncio
import json
import websockets
from typing import Dict, Any, Set
from src.shared.system.signal_bus import signal_bus, SignalType, Signal
from src.interface.dashboard_transformer import DashboardTransformer
from src.shared.system.logging import Logger

class DashboardServer:
    """
    "The Voice" - WebSocket Server Bridge
    Bridges internal SignalBus events to external WebSocket clients.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self.running = False
        self._server = None

    async def start(self):
        """Ignite the WebSocket Server."""
        self.running = True
        
        # 1. Subscribe to SignalBus
        relevant_signals = [
            SignalType.ARB_OPP,
            SignalType.SCALP_SIGNAL,
            SignalType.LOG_UPDATE,
            SignalType.SYSTEM_STATS,
            SignalType.MARKET_INTEL,
            SignalType.WHALE_ACTIVITY
        ]
        
        for sig in relevant_signals:
            signal_bus.subscribe(sig, self._handle_signal)
        
        Logger.info(f"   Dashboard Voice active on ws://{self.host}:{self.port}")

        # 2. Start Heartbeat
        asyncio.create_task(self._heartbeat_loop())

        # 3. Start Server
        try:
            self._server = await websockets.serve(self._handler, self.host, self.port)
            await asyncio.Future()  # Run forever
        except asyncio.CancelledError:
            Logger.info("   Voice fading out...")
            if self.clients:
                await asyncio.gather(
                    *[client.close() for client in self.clients],
                    return_exceptions=True
                )
        except Exception as e:
            Logger.error(f"   Dashboard Server Error: {e}")

    async def _heartbeat_loop(self):
        """1Hz System Pulse."""
        while self.running:
            try:
                if self.clients:
                    # Fetch stats from AppState or shared metrics
                    from src.shared.state.app_state import state
                    stats_payload = {
                        "type": "SYSTEM_STATS",
                        "data": state.stats or {},
                        "timestamp": asyncio.get_event_loop().time()
                    }
                    message = json.dumps(stats_payload)
                    await self._broadcast(message)
            except Exception:
                pass
            await asyncio.sleep(1.0)

    async def _handler(self, websocket):
        """Handle new client connections."""
        self.clients.add(websocket)
        Logger.info(f"   [DASH] Client Linked. Active Clients: {len(self.clients)}")
        try:
            async for message in websocket:
                data = json.loads(message)
                if data.get("action") == "REQUEST_SYNC":
                    await websocket.send(json.dumps({"type": "PING", "msg": "PONG"}))
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.clients.remove(websocket)

    async def _handle_signal(self, signal: Signal):
        """Transform and broadcast signals."""
        if not self.clients:
            return

        payload = DashboardTransformer.transform(signal)
        if payload:
            message = json.dumps(payload)
            await self._broadcast(message)

    async def _broadcast(self, message: str):
        """Safe broadcast to all clients."""
        if not self.clients:
            return
        
        # Snapshot clients to avoid 'Set changed size during iteration'
        target_clients = list(self.clients)
        await asyncio.gather(
            *[client.send(message) for client in target_clients],
            return_exceptions=True
        )

if __name__ == "__main__":
    server = DashboardServer()
    asyncio.run(server.start())
