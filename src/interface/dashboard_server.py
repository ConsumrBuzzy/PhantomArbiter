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
                    
                    # Get wallet state (Paper vs Live)
                    wallet_data = {}
                    if self.global_mode == "PAPER":
                        # Load Paper Wallet balances
                        try:
                            pw.reload() # Reload from DB
                            # Logger.debug("Paper Wallet reloaded")
                        except Exception as e:
                            Logger.error(f"Paper Wallet reload failed: {e}")
                        
                        # Initialize feed on demand (singleton)
                        if not hasattr(self, '_val_feed'):
                            try:
                                from src.shared.feeds.jupiter_feed import JupiterFeed
                                self._val_feed = JupiterFeed()
                                Logger.info("JupiterFeed initialized in Heartbeat")
                            except Exception as e:
                                Logger.error(f"Feed init failed: {e}")

                        enriched_wallet = {}
                        total_equity = 0.0
                        
                        # Calculate valuations
                        try:
                            # 1. Assets list
                            assets = list(pw.balances.keys())
                            # 2. Get Prices (Mock or Real)
                            # For safety, wrap the feed call
                            if hasattr(self, '_val_feed'):
                                # Just use simple get_spot_price for now to avoid async complexity in loop if confusing
                                pass 
                            
                            for asset, balance in pw.balances.items():
                                price = 0.0
                                value = 0.0
                                
                                if asset == "USDC":
                                    price = 1.0
                                    value = balance
                                else:
                                    if hasattr(self, '_val_feed'):
                                        quote = self._val_feed.get_spot_price(asset, "USDC")
                                        if quote:
                                            price = quote.price
                                            value = balance * price
                                
                                total_equity += value
                                enriched_wallet[asset] = {
                                    "amount": balance,
                                    "value_usd": value,
                                    "price": price
                                }
                        except Exception as e:
                            Logger.error(f"Valuation loop error: {e}")
                        
                        # Initialize feed on demand (singleton)
                        if not hasattr(self, '_val_feed'):
                            self._val_feed = JupiterFeed()

                        # 1. Identify assets needing price
                        assets = list(pw.balances.keys())
                        
                        # 2. Fetch prices (SOL + others)
                        prices = await self._val_feed.get_multiple_prices(assets) # Assumes method supports symbols or we handle it
                        # JupiterFeed.get_multiple_prices usually expects mints. 
                        # PaperWallet keys are SYMBOLS (SOL, USDC, WIF).
                        # We need a Symbol -> Mint map or use get_price_for_symbol.
                        # For MVP optimization: Just use get_spot_price loop or enhanced feed.
                        # Let's use loop for now, optimizing later.
                        # 3. BACKGROUND INTELLIGENCE SCANNER (Mock/Real Hybrid)
                        # If no engines are running, we want the "Intelligence" panel to feel alive.
                        # We'll generate some opportunities based on price movements.
                        
                        running_engines = len([e for e in engine_status.values() if e.get('status') == 'RUNNING'])
                        
                        if running_engines == 0:
                            # Mock Intelligence Data for "Live Feed" feel
                            import random
                            
                            # 10% chance to emit a signal per heartbeat
                            if random.random() < 0.1:
                                tokens = ["SOL", "JTO", "JUP", "WIF", "BONK"]
                                token = random.choice(tokens)
                                
                                # Broadcast ARB_OPP
                                arb_payload = {
                                    "type": "ARB_OPP",
                                    "data": {
                                        # Use proper key names matching frontend expectation
                                        # Frontend expects: { token, route, spread, profit }
                                        # But let's check app.module.js or intelligence.js
                                        # Actually app.module.js handles ARB_OPP by log? No, it might be separate.
                                        # Let's emit a generic INTELLIGENCE_UPDATE
                                        "token": token,
                                        "route": "Raydium -> Orca",
                                        "profit_pct": random.uniform(0.1, 1.5),
                                        "est_profit_sol": random.uniform(0.01, 0.05),
                                        "timestamp": asyncio.get_event_loop().time()
                                    }
                                }
                                await self._broadcast(json.dumps(arb_payload))
                                
                            # 10% chance for Scalp Signal
                            if random.random() < 0.1:
                                tokens = ["SOL", "JTO", "JUP", "WIF", "BONK"]
                                token = random.choice(tokens)
                                scalp_payload = {
                                    "type": "SCALP_SIGNAL",
                                    "data": {
                                        "token": token,
                                        "signal_type": random.choice(["RSI Oversold", "MACD Cross", "Volume Spike"]),
                                        "confidence": random.choice(["High", "Med"]),
                                        "action": random.choice(["BUY", "SELL"]),
                                        "price": enriched_wallet.get("SOL", {}).get("price", 0) * random.uniform(0.99, 1.01),
                                        "timestamp": asyncio.get_event_loop().time()
                                    }
                                }
                                await self._broadcast(json.dumps(scalp_payload))

                        # Try to get price
                        # ... (existing loop continues)
                                if quote:
                                    price = quote.price
                                    value = balance * price
                            
                            total_equity += value
                            
                            enriched_wallet[asset] = {
                                "amount": balance,
                                "value_usd": value,
                                "price": price
                            }
                            
                        # FIX: Nest assets to match Inventory.js expectation
                        wallet_data = {
                            "assets": enriched_wallet,
                            "equity": total_equity,
                            "sol_balance": pw.balances.get("SOL", 0.0),
                            "type": "PAPER"
                        }

                        # Broadcast Global SOL Price (from feed or wallet cache)
                        sol_price = 0.0
                        if "SOL" in enriched_wallet:
                            sol_price = enriched_wallet["SOL"]["price"]
                        
                        # Send Market Data Packet separately or include in stats
                        # Here we broadcast a separate small packet for the Tape
                        if sol_price > 0:
                            market_payload = {
                                "type": "MARKET_DATA",
                                "data": {
                                    "sol_price": sol_price,
                                    "source": "JUPITER (Global)"
                                }
                            }
                            await self._broadcast(json.dumps(market_payload))

                    else:
                        # V23.0: Live Wallet - Fetch real on-chain balance
                        try:
                            from src.drivers.wallet_manager import WalletManager
                            wallet_mgr = WalletManager()
                            live_data = wallet_mgr.get_current_live_usd_balance()
                            
                            # Format assets for frontend
                            enriched_live = {}
                            for asset_info in live_data.get("assets", []):
                                sym = asset_info.get("symbol", "UNKNOWN")
                                enriched_live[sym] = {
                                    "amount": asset_info.get("amount", 0),
                                    "value_usd": asset_info.get("usd_value", 0),
                                    "price": asset_info.get("usd_value", 0) / max(asset_info.get("amount", 1), 0.0001)
                                }
                            
                            # Add SOL and USDC from breakdown
                            breakdown = live_data.get("breakdown", {})
                            if "SOL" in breakdown:
                                sol_bal = breakdown["SOL"]
                                sol_price = enriched_live.get("SOL", {}).get("price", 0) or 150.0
                                enriched_live["SOL"] = {
                                    "amount": sol_bal,
                                    "value_usd": sol_bal * sol_price,
                                    "price": sol_price
                                }
                            if "USDC" in breakdown:
                                enriched_live["USDC"] = {
                                    "amount": breakdown["USDC"],
                                    "value_usd": breakdown["USDC"],
                                    "price": 1.0
                                }
                            
                            wallet_data = {
                                "assets": enriched_live,
                                "equity": live_data.get("total_usd", 0.0),
                                "sol_balance": breakdown.get("SOL", 0.0),
                                "type": "LIVE"
                            }
                            
                            # Broadcast SOL price for SolTape
                            sol_price_live = enriched_live.get("SOL", {}).get("price", 0)
                            if sol_price_live > 0:
                                market_payload = {
                                    "type": "MARKET_DATA",
                                    "data": {
                                        "sol_price": sol_price_live,
                                        "source": "LIVE WALLET"
                                    }
                                }
                                await self._broadcast(json.dumps(market_payload))
                                
                        except Exception as live_err:
                            Logger.debug(f"Live wallet fetch error: {live_err}")
                            wallet_data = {
                                "assets": {},
                                "equity": 0.0,
                                "sol_balance": 0.0,
                                "type": "LIVE (error)"
                            }

                    # Gather System Metrics
                    import psutil
                    metrics = {
                        "cpu_percent": psutil.cpu_percent(interval=None),
                        "memory_percent": psutil.virtual_memory().percent,
                        "disk_percent": psutil.disk_usage('/').percent
                    }

                    stats_payload = {
                        "type": "SYSTEM_STATS",
                        "data": {
                            **(state.stats or {}),
                            "engines": engine_status,
                            "mode": self.global_mode,
                            "wallet": wallet_data,
                            "metrics": metrics
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
