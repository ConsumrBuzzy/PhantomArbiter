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
from src.shared.state.paper_wallet import pw
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

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self.running = False
        self._server = None
        self.global_mode = "PAPER"  # Default to Paper
        
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
        Logger.info("[DEBUG] Creating Heartbeat Task...")
        try:
            hb_task = asyncio.create_task(self._heartbeat_loop())
            
            def hb_done(f):
                try:
                    exc = f.exception()
                    if exc:
                        Logger.error(f"[HEARTBEAT] Task DIED with error: {exc}")
                    else:
                        Logger.info(f"[HEARTBEAT] Task finished cleanly")
                except Exception as e:
                    Logger.error(f"[HEARTBEAT] Callback error: {e}")

            hb_task.add_done_callback(hb_done)
            Logger.info("[DEBUG] Heartbeat Task Scheduled")
        except Exception as e:
            Logger.error(f"[DEBUG] Failed to create Heartbeat Task: {e}")

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
        """
        1Hz System Pulse with engine status.
        
        SRP Refactor: Data collection delegated to HeartbeatDataCollector.
        This method now only handles:
        1. Calling the collector
        2. Broadcasting the snapshot
        3. Error handling
        """
        from src.interface.heartbeat_collector import get_heartbeat_collector
        
        collector = get_heartbeat_collector()
        
        while self.running:
            try:
                if self.clients:
                    # Collect system snapshot (all data aggregation happens here)
                    snapshot = await collector.collect(global_mode=self.global_mode)
                    
                    # Broadcast SOL price for SolTape
                    if snapshot.sol_price > 0:
                        await self._broadcast(json.dumps({
                            "type": "MARKET_DATA",
                            "data": {"sol_price": snapshot.sol_price, "source": "JUPITER"}
                        }))
                    
                    # Broadcast main system stats packet
                    stats_payload = {
                        "type": "SYSTEM_STATS",
                        "data": snapshot.to_dict(),
                        "timestamp": asyncio.get_event_loop().time()
                    }
                    await self._broadcast(json.dumps(stats_payload))
                    
            except Exception as e:
                Logger.warning(f"Heartbeat error: {e}")
                import traceback
                traceback.print_exc()
                
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
        
        elif action == "SET_GLOBAL_MODE":
            mode = data.get("mode", "PAPER").upper()
            if mode in ["PAPER", "LIVE"]:
                self.global_mode = mode
                Logger.warning(f"   ⚠️  GLOBAL MODE SET TO: {mode}")
                
                # Broadcast immediate update
                await self._broadcast(json.dumps({
                    "type": "SYSTEM_STATS",
                    "data": {
                        "mode": self.global_mode,
                        # Include minimal update data
                    },
                    "timestamp": asyncio.get_event_loop().time()
                }))
        
        elif action == "GET_STATUS":
            engine_status = await engine_manager.get_status()
            await websocket.send(json.dumps({
                "type": "ENGINE_STATUS",
                "data": engine_status
            }))
        
        elif action == "GET_API_HEALTH":
            # V23.0: API Health Check
            try:
                from src.interface.api_health import get_api_health_checker
                checker = get_api_health_checker()
                results = await checker.check_all()
                await websocket.send(json.dumps({
                    "type": "API_HEALTH",
                    "data": results
                }))
            except Exception as e:
                Logger.error(f"API Health check failed: {e}")
                await websocket.send(json.dumps({
                    "type": "API_HEALTH",
                    "data": [{"name": "Error", "status": "error", "message": str(e)[:50]}]
                }))
        
        elif action == "SOS":
            Logger.warning("   🆘 SOS COMMAND RECEIVED!")
            result = await engine_manager.emergency_stop_all()
            await self._broadcast(json.dumps({
                "type": "SOS_RESPONSE",
                "result": result
            }))
            await self._broadcast_engine_status()
        
        # ═══════════════════════════════════════════════════════════════
        # MULTI-VAULT OPERATIONS
        # ═══════════════════════════════════════════════════════════════
        
        elif action == "GET_ENGINE_VAULT":
            # Fetch specific engine's paper vault for detail view
            engine_name = data.get("engine")
            try:
                from src.shared.state.vault_manager import get_engine_vault
                vault = get_engine_vault(engine_name)
                
                # Get current SOL price for equity calculation
                sol_price = 150.0  # Fallback
                try:
                    if hasattr(self, '_val_feed'):
                        quote = self._val_feed.get_spot_price("SOL", "USDC")
                        if quote and quote.price > 0:
                            sol_price = quote.price
                except Exception:
                    pass
                
                vault_data = vault.get_balances(sol_price)
                await websocket.send(json.dumps({
                    "type": "ENGINE_VAULT",
                    "engine": engine_name,
                    "data": vault_data
                }))
            except Exception as e:
                Logger.error(f"Vault fetch error [{engine_name}]: {e}")
                await websocket.send(json.dumps({
                    "type": "ENGINE_VAULT",
                    "engine": engine_name,
                    "data": {"error": str(e)}
                }))
        
        elif action == "VAULT_RESET":
            # Reset engine's paper vault to initial state
            engine_name = data.get("engine")
            try:
                from src.shared.state.vault_manager import get_vault_registry
                get_vault_registry().reset_vault(engine_name)
                Logger.info(f"   🔄 Vault Reset: {engine_name}")
                await websocket.send(json.dumps({
                    "type": "VAULT_RESPONSE",
                    "action": "RESET",
                    "engine": engine_name,
                    "success": True,
                    "message": f"Vault reset for {engine_name}"
                }))
            except Exception as e:
                Logger.error(f"Vault reset error [{engine_name}]: {e}")
                await websocket.send(json.dumps({
                    "type": "VAULT_RESPONSE",
                    "action": "RESET",
                    "engine": engine_name,
                    "success": False,
                    "message": str(e)
                }))
        
        elif action == "VAULT_SYNC":
            # Mirror live wallet into engine's paper vault
            engine_name = data.get("engine")
            try:
                from src.shared.state.vault_manager import get_vault_registry
                from src.drivers.wallet_manager import WalletManager
                
                if not hasattr(self, '_wallet_mgr'):
                    self._wallet_mgr = WalletManager()
                
                live_data = self._wallet_mgr.get_current_live_usd_balance()
                live_balances = {}
                
                # Extract raw balances from live wallet
                for asset_info in live_data.get("assets", []):
                    sym = asset_info.get("symbol", "UNKNOWN")
                    amt = asset_info.get("amount", 0)
                    if amt > 0:
                        live_balances[sym] = amt
                
                # Add breakdown assets
                breakdown = live_data.get("breakdown", {})
                for asset, amt in breakdown.items():
                    if amt > 0:
                        live_balances[asset] = amt
                
                get_vault_registry().sync_from_live(engine_name, live_balances)
                Logger.info(f"   🔗 Vault Sync: {engine_name} <- LIVE ({len(live_balances)} assets)")
                
                await websocket.send(json.dumps({
                    "type": "VAULT_RESPONSE",
                    "action": "SYNC",
                    "engine": engine_name,
                    "success": True,
                    "message": f"Synced {len(live_balances)} assets from live wallet"
                }))
            except Exception as e:
                Logger.error(f"Vault sync error [{engine_name}]: {e}")
                await websocket.send(json.dumps({
                    "type": "VAULT_RESPONSE",
                    "action": "SYNC",
                    "engine": engine_name,
                    "success": False,
                    "message": str(e)
                }))
        
        elif action == "GET_ALL_VAULTS":
            # Global vault snapshot for portfolio reporting
            try:
                from src.shared.state.vault_manager import get_vault_registry
                
                sol_price = 150.0
                try:
                    if hasattr(self, '_val_feed'):
                        quote = self._val_feed.get_spot_price("SOL", "USDC")
                        if quote and quote.price > 0:
                            sol_price = quote.price
                except Exception:
                    pass
                
                snapshot = get_vault_registry().get_global_snapshot(sol_price)
                await websocket.send(json.dumps({
                    "type": "VAULT_SNAPSHOT",
                    "data": snapshot
                }))
            except Exception as e:
                Logger.error(f"Vault snapshot error: {e}")
                await websocket.send(json.dumps({
                    "type": "VAULT_SNAPSHOT",
                    "data": {"error": str(e)}
                }))
        
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

    def _handle_signal(self, signal: Any):
        """Transform and broadcast signals."""
        try:
            # Handle both Signal object and dict
            payload = signal.to_dict() if hasattr(signal, 'to_dict') else signal
            
            self.broadcast({
                "type": "SIGNAL",
                "data": payload
            })
            Logger.info(f"📡 Signal Broadcast: {payload.get('type')} on {payload.get('symbol')}")
        except Exception as e:
            Logger.debug(f"Signal broadcast error: {e}")

    async def _broadcast(self, message: str):
        """Safe broadcast to all clients."""
        if not self.clients:
            return
        
        target_clients = list(self.clients)
        await asyncio.gather(
            *[client.send(message) for client in target_clients],
            return_exceptions=True
        )
    
    async def broadcast(self, data: Dict[str, Any]):
        """Public broadcast method - accepts a dict, serializes to JSON."""
        message = json.dumps(data)
        await self._broadcast(message)


if __name__ == "__main__":
    server = DashboardServer()
    asyncio.run(server.start())
