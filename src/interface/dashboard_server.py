"""
Dashboard Server - Bidirectional Command Center
================================================
v2.0: Upgraded from one-way broadcast to full Trading OS Kernel.

Features:
- Inbound WebSocket commands for engine lifecycle control
- Engine status broadcasting at 1Hz
- SOS emergency stop handling
- Dynamic configuration updates
"""

import asyncio
import json
import websockets
from typing import Dict, Any, Set
from src.shared.system.signal_bus import signal_bus, SignalType, Signal
from src.interface.dashboard_transformer import DashboardTransformer
from src.interface.engine_registry import engine_registry
from src.interface.engine_manager import engine_manager
from src.shared.system.logging import Logger


class DashboardServer:
    """
    The Kernel - Bidirectional WebSocket Command Center.
    
    Inbound Commands:
        - REQUEST_SYNC: Handshake/ping
        - START_ENGINE: Launch engine subprocess
        - STOP_ENGINE: Graceful engine shutdown
        - RESTART_ENGINE: Stop + Start
        - UPDATE_CONFIG: Hot-swap engine parameters
        - GET_STATUS: Request current engine states
        - SOS: Emergency stop all engines + close positions
    
    Outbound Broadcasts:
        - SYSTEM_STATS: 1Hz heartbeat with metrics
        - ENGINE_STATUS: Engine state changes
        - LOG_ENTRY: Real-time log streaming
        - Signal passthrough (ARB_OPP, SCALP_SIGNAL, etc.)
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self.running = False
        self._server = None
        
        # Register for engine log streaming
        engine_manager.on_log(self._handle_engine_log)

    async def start(self):
        """Ignite the WebSocket Command Center."""
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
        
        Logger.info(f"   🎮 Command Center active on ws://{self.host}:{self.port}")

        # 2. Start Heartbeat (includes engine status)
        asyncio.create_task(self._heartbeat_loop())

        # 3. Start Server
        try:
            self._server = await websockets.serve(self._handler, self.host, self.port)
            await asyncio.Future()  # Run forever
        except asyncio.CancelledError:
            Logger.info("   Command Center shutting down...")
            # Stop all engines on shutdown
            await engine_manager.emergency_stop_all()
            if self.clients:
                await asyncio.gather(
                    *[client.close() for client in self.clients],
                    return_exceptions=True
                )
        except Exception as e:
            Logger.error(f"   Command Center Error: {e}")

    async def _heartbeat_loop(self):
        """1Hz System Pulse with engine status."""
        while self.running:
            try:
                if self.clients:
                    from src.shared.state.app_state import state
                    
                    # Get engine statuses
                    engine_status = await engine_manager.get_status()
                    
                    stats_payload = {
                        "type": "SYSTEM_STATS",
                        "data": {
                            **(state.stats or {}),
                            "engines": engine_status
                        },
                        "timestamp": asyncio.get_event_loop().time()
                    }
                    message = json.dumps(stats_payload)
                    await self._broadcast(message)
            except Exception as e:
                Logger.debug(f"Heartbeat error: {e}")
            await asyncio.sleep(1.0)

    async def _handler(self, websocket):
        """Handle client connections and inbound commands."""
        self.clients.add(websocket)
        client_count = len(self.clients)
        Logger.info(f"   [KERNEL] Client Linked. Active: {client_count}")
        
        # Send initial state on connect
        await self._send_initial_state(websocket)
        
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self._handle_command(websocket, data)
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({
                        "type": "ERROR",
                        "message": "Invalid JSON"
                    }))
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.clients.discard(websocket)
            Logger.info(f"   [KERNEL] Client Disconnected. Active: {len(self.clients)}")

    async def _send_initial_state(self, websocket):
        """Send current engine states on client connect."""
        try:
            engine_status = await engine_manager.get_status()
            await websocket.send(json.dumps({
                "type": "ENGINE_STATUS",
                "data": engine_status
            }))
        except Exception:
            pass

    async def _handle_command(self, websocket, data: Dict[str, Any]):
        """
        Process inbound commands from the UI.
        """
        action = data.get("action", "").upper()
        
        if action == "REQUEST_SYNC":
            await websocket.send(json.dumps({"type": "PING", "msg": "PONG"}))
        
        elif action == "START_ENGINE":
            engine_name = data.get("engine")
            config = data.get("config", {})
            result = await engine_manager.start_engine(engine_name, config)
            await websocket.send(json.dumps({
                "type": "ENGINE_RESPONSE",
                "action": "START",
                "engine": engine_name,
                "result": result
            }))
            # Broadcast status update to all clients
            await self._broadcast_engine_status()
        
        elif action == "STOP_ENGINE":
            engine_name = data.get("engine")
            result = await engine_manager.stop_engine(engine_name)
            await websocket.send(json.dumps({
                "type": "ENGINE_RESPONSE",
                "action": "STOP",
                "engine": engine_name,
                "result": result
            }))
            await self._broadcast_engine_status()
        
        elif action == "RESTART_ENGINE":
            engine_name = data.get("engine")
            config = data.get("config", {})
            result = await engine_manager.restart_engine(engine_name, config)
            await websocket.send(json.dumps({
                "type": "ENGINE_RESPONSE",
                "action": "RESTART",
                "engine": engine_name,
                "result": result
            }))
            await self._broadcast_engine_status()
        
        elif action == "UPDATE_CONFIG":
            engine_name = data.get("engine")
            config = data.get("config", {})
            success = await engine_registry.update_config(engine_name, config)
            await websocket.send(json.dumps({
                "type": "CONFIG_RESPONSE",
                "engine": engine_name,
                "success": success
            }))
        
        elif action == "GET_STATUS":
            engine_status = await engine_manager.get_status()
            await websocket.send(json.dumps({
                "type": "ENGINE_STATUS",
                "data": engine_status
            }))
        
        elif action == "SOS":
            Logger.warning("   🆘 SOS COMMAND RECEIVED!")
            result = await engine_manager.emergency_stop_all()
            await self._broadcast(json.dumps({
                "type": "SOS_RESPONSE",
                "result": result
            }))
            await self._broadcast_engine_status()
        
        else:
            await websocket.send(json.dumps({
                "type": "ERROR",
                "message": f"Unknown action: {action}"
            }))

    async def _broadcast_engine_status(self):
        """Broadcast current engine states to all clients."""
        try:
            engine_status = await engine_manager.get_status()
            await self._broadcast(json.dumps({
                "type": "ENGINE_STATUS",
                "data": engine_status
            }))
        except Exception:
            pass

    def _handle_engine_log(self, engine: str, level: str, message: str):
        """Callback for engine log streaming."""
        if self.clients:
            payload = json.dumps({
                "type": "LOG_ENTRY",
                "data": {
                    "source": f"ENGINE:{engine.upper()}",
                    "level": level,
                    "message": message
                }
            })
            # Schedule broadcast (we're in sync context)
            asyncio.create_task(self._broadcast(payload))

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
        
        target_clients = list(self.clients)
        await asyncio.gather(
            *[client.send(message) for client in target_clients],
            return_exceptions=True
        )


if __name__ == "__main__":
    server = DashboardServer()
    asyncio.run(server.start())
