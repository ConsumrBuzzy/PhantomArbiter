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
        """1Hz System Pulse with engine status."""
        # Logger.info("[HEARTBEAT] Loop starting...")
        while self.running:
            try:
                # Logger.info("[HEARTBEAT] Pulse...") 
                if self.clients:
                    # Logger.info(f"[HEARTBEAT] Broadcasting to {len(self.clients)} clients")
                    from src.shared.state.app_state import state
                    
                    # Get engine statuses
                    engine_status = await engine_manager.get_status()
                    
                    # V23.1: Always fetch BOTH wallets
                    # LIVE = Real Solana on-chain balance
                    # PAPER = Simulation wallet for paper trading
                    
                    paper_wallet_data = {}
                    live_wallet_data = {}
                    
                    # 1. PAPER WALLET (Simulation)
                    try:
                        pw.reload()
                    except Exception:
                        pass
                    
                    enriched_paper = {}
                    paper_equity = 0.0
                    FALLBACK_PRICES = {"SOL": 150.0, "USDC": 1.0, "JTO": 2.5, "JUP": 0.8}
                    
                    for asset, balance in pw.balances.items():
                        price = FALLBACK_PRICES.get(asset, 0.0)
                        try:
                            if not hasattr(self, '_val_feed'):
                                from src.shared.feeds.jupiter_feed import JupiterFeed
                                self._val_feed = JupiterFeed()
                            if hasattr(self, '_val_feed') and asset != "USDC":
                                quote = self._val_feed.get_spot_price(asset, "USDC")
                                if quote and quote.price > 0:
                                    price = quote.price
                        except Exception:
                            pass
                        
                        value = balance * price
                        paper_equity += value
                        enriched_paper[asset] = {"amount": balance, "value_usd": value, "price": price}
                    
                    paper_wallet_data = {
                        "assets": enriched_paper,
                        "equity": paper_equity,
                        "sol_balance": pw.balances.get("SOL", 0.0),
                        "type": "PAPER"
                    }
                    
                    # 2. LIVE WALLET (Real Solana On-Chain)
                    enriched_live = {}  # Initialize before try
                    drift_equity = 0.0  # Drift account balance
                    try:
                        from src.drivers.wallet_manager import WalletManager
                        if not hasattr(self, '_wallet_mgr'):
                            self._wallet_mgr = WalletManager()
                        
                        live_data = self._wallet_mgr.get_current_live_usd_balance()
                        
                        for asset_info in live_data.get("assets", []):
                            sym = asset_info.get("symbol", "UNKNOWN")
                            amt = asset_info.get("amount", 0)
                            val = asset_info.get("usd_value", 0)
                            enriched_live[sym] = {
                                "amount": amt,
                                "value_usd": val,
                                "price": val / max(amt, 0.0001) if amt else 0
                            }
                        
                        breakdown = live_data.get("breakdown", {})
                        if "SOL" in breakdown:
                            sol_bal = breakdown["SOL"]
                            sol_price = enriched_live.get("SOL", {}).get("price", 150.0)
                            enriched_live["SOL"] = {"amount": sol_bal, "value_usd": sol_bal * sol_price, "price": sol_price}
                        if "USDC" in breakdown:
                            enriched_live["USDC"] = {"amount": breakdown["USDC"], "value_usd": breakdown["USDC"], "price": 1.0}
                        
                        # 3. DRIFT BALANCE (Perp Account Equity)
                        try:
                            from src.delta_neutral.drift_order_builder import DriftAdapter
                            if not hasattr(self, '_drift'):
                                self._drift = DriftAdapter("mainnet")
                                self._drift.set_wallet(self._wallet_mgr)
                            
                            # Try to get Drift account equity (USDC collateral + unrealized PnL)
                            # Using DriftAdapter's integrated balance fetch
                            drift_equity = self._drift.get_user_equity()
                            
                            # Add to payload for dedicated UI
                            live_data['drift_equity'] = drift_equity
                            
                            if drift_equity > 0:
                                enriched_live["DRIFT"] = {
                                    "amount": drift_equity,  # Show as equity amount
                                    "value_usd": drift_equity,
                                    "price": 1.0  # USDC-denominated
                                }
                        except Exception as drift_err:
                            Logger.debug(f"Drift balance fetch: {drift_err}")
                            Logger.debug(f"Drift balance fetch: {drift_err}")
                        
                        total_live_equity = live_data.get("total_usd", 0.0) + drift_equity
                        
                        live_wallet_data = {
                            "assets": enriched_live,
                            "equity": total_live_equity,
                            "sol_balance": breakdown.get("SOL", 0.0),
                            "drift_equity": drift_equity,
                            "type": "LIVE"
                        }
                    except Exception as live_err:
                        Logger.debug(f"Live wallet fetch: {live_err}")
                        live_wallet_data = {"assets": {}, "equity": 0.0, "sol_balance": 0.0, "type": "LIVE (error)"}
                    
                    # Broadcast SOL price for SolTape
                    sol_price = enriched_paper.get("SOL", {}).get("price", 0) or enriched_live.get("SOL", {}).get("price", 0) or 150.0
                    if sol_price > 0:
                        await self._broadcast(json.dumps({
                            "type": "MARKET_DATA",
                            "data": {"sol_price": sol_price, "source": "JUPITER"}
                        }))

                    # Gather System Metrics
                    import psutil
                    try:
                        disk_pct = psutil.disk_usage('C:').percent
                    except Exception:
                        disk_pct = 0.0
                    metrics = {
                        "cpu_percent": psutil.cpu_percent(interval=None),
                        "memory_percent": psutil.virtual_memory().percent,
                        "disk_percent": disk_pct
                    }

                    # Send BOTH wallets in payload
                    stats_payload = {
                        "type": "SYSTEM_STATS",
                        "data": {
                            **(state.stats or {}),
                            "engines": engine_status,
                            "mode": self.global_mode,
                            "wallet": paper_wallet_data,  # For Inventory (based on mode)
                            "paper_wallet": paper_wallet_data,
                            "live_wallet": live_wallet_data,
                            "metrics": metrics
                        },
                        "timestamp": asyncio.get_event_loop().time()
                    }
                    message = json.dumps(stats_payload)
                    await self._broadcast(message)
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
    
    async def broadcast(self, data: Dict[str, Any]):
        """Public broadcast method - accepts a dict, serializes to JSON."""
        message = json.dumps(data)
        await self._broadcast(message)


if __name__ == "__main__":
    server = DashboardServer()
    asyncio.run(server.start())
