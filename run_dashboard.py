"""
Dashboard Launcher (Minimal)
============================
Launches just the Command Center UI without legacy engine dependencies.
Includes live market data feed (SOL price from Pyth) and token watchlist.

Usage:
    python run_dashboard.py
"""

import asyncio
import sys
import os
import http.server
import socketserver
import threading
import json
from dataclasses import asdict

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()


async def main():
    """Launch the Command Center dashboard with live market data."""
    from src.shared.system.logging import Logger
    from src.shared.feeds.simple_price_feed import SimplePriceFeed, PriceData
    from src.shared.feeds.token_watchlist import TokenWatchlistFeed, TokenPrice
    
    Logger.info("🚀 Starting Phantom Arbiter Command Center...")
    
    # 1. Static Web Server (Frontend)
    def run_http():
        os.chdir("frontend")
        handler = http.server.SimpleHTTPRequestHandler
        with socketserver.TCPServer(("", 8000), handler) as httpd:
            Logger.info("📊 Frontend available at http://localhost:8000")
            httpd.serve_forever()
    
    frontend_thread = threading.Thread(target=run_http, daemon=True)
    frontend_thread.start()
    
    # 6. Local Dashboard Controller
    # -----------------------------
    # Intercepts START/STOP commands to control in-process engines
    # instead of spawning new subprocesses (since we want to keep the callbacks).
    
    from src.interface.dashboard_server import DashboardServer
    from src.interface.engine_registry import engine_registry, EngineStatus
    
    class LocalDashboardServer(DashboardServer):
        def __init__(self, engines_map: dict):
            super().__init__()
            self.local_engines = engines_map
            
        async def _handle_command(self, websocket, data):
            action = data.get("action", "").upper()
            
            if action == "START_ENGINE":
                name = data.get("engine")
                mode = data.get("mode", "paper").lower() # 'paper' or 'live'
                
                if name in self.local_engines:
                    eng = self.local_engines[name]
                    
                    # SINGLE ENGINE PER MODE CHECK
                    is_live_req = (mode == "live")
                    
                    for other_name, other_eng in self.local_engines.items():
                        if other_name != name and other_eng.running:
                            other_is_live = getattr(other_eng, 'live_mode', False)
                            
                            if is_live_req and other_is_live:
                                await self._send_engine_response(websocket, "START", name, False, 
                                    f"Start Failed: '{other_name}' is already LIVE. Only one live engine allowed.")
                                return
                            
                            if not is_live_req and not other_is_live:
                                await self._send_engine_response(websocket, "START", name, False, 
                                    f"Start Failed: '{other_name}' is running in PAPER mode. Only one paper engine allowed.")
                                return

                    if not eng.running:
                        # Set mode
                        eng.live_mode = (mode == "live")
                        await eng.start()
                        
                        # Update registry status manually since we aren't using EngineManager subproc
                        await engine_registry.update_status(
                            name, 
                            EngineStatus.RUNNING, 
                            pid=os.getpid()
                        )
                        Logger.info(f"🟢 [LOCAL] Started {name} engine ({mode})")
                        
                    await self._send_engine_response(websocket, "START", name, True, "Started locally")
                    await self._broadcast_engine_status()
                    return

            elif action == "STOP_ENGINE":
                name = data.get("engine")
                if name in self.local_engines:
                    eng = self.local_engines[name]
                    if eng.running:
                        await eng.stop()
                        
                        await engine_registry.update_status(
                            name, 
                            EngineStatus.STOPPED
                        )
                        Logger.info(f"🔴 [LOCAL] Stopped {name} engine")
                        
                    await self._send_engine_response(websocket, "STOP", name, True, "Stopped locally")
                    await self._broadcast_engine_status()
                    return

            # Fallback to default handler
            await super()._handle_command(websocket, data)

        async def _send_engine_response(self, websocket, action, engine, success, msg):
             await websocket.send(json.dumps({
                "type": "ENGINE_RESPONSE",
                "action": action,
                "engine": engine,
                "result": {"success": success, "message": msg}
            }))

    # Instantiate custom dashboard with empty map (populated later)
    dashboard = LocalDashboardServer({})
    
    # 3. Price Feed - Streams live SOL price (Pyth WebSocket)
    price_feed = SimplePriceFeed()
    
    async def on_price_update(price: PriceData):
        """Broadcast SOL price updates to all connected clients."""
        await dashboard.broadcast({
            "type": "MARKET_DATA",
            "data": {
                "sol_price": price.price,
                "change_24h": price.change_24h,
                "volume_24h": price.volume_24h,
                "timestamp": price.timestamp
            }
        })
    
    price_feed.set_callback(on_price_update)
    price_feed.start()
    
    # 4. Token Watchlist - Multi-token price tracking
    watchlist_feed = TokenWatchlistFeed(interval=5.0)
    
    async def on_watchlist_update(prices: dict):
        """Broadcast token watchlist updates to all connected clients."""
        # Convert TokenPrice objects to dicts for JSON serialization
        tokens_data = []
        for symbol, tp in prices.items():
            tokens_data.append({
                "symbol": tp.symbol,
                "mint": tp.mint,
                "category": tp.category,
                "prices": tp.prices,
                "best_bid": tp.best_bid,
                "best_ask": tp.best_ask,
                "spread_pct": tp.spread_pct,
                "volume_24h": tp.volume_24h,
                "change_24h": tp.change_24h,
                "last_update": tp.last_update
            })
        
        await dashboard.broadcast({
            "type": "TOKEN_WATCHLIST",
            "data": {
                "tokens": tokens_data,
                "timestamp": asyncio.get_event_loop().time()
            }
        })
    
    watchlist_feed.set_callback(on_watchlist_update)
    watchlist_feed.start()

    # 5. Market Context - Environment Data
    from src.drivers.context_driver import ContextDriver, MarketContext
    context_driver = ContextDriver(interval=15.0)

    async def on_context_update(ctx: MarketContext):
        """Broadcast context updates."""
        await dashboard.broadcast({
            "type": "CONTEXT_UPDATE",
            "data": {
                "sol_btc_strength": ctx.sol_btc_strength,
                "jito_tip": ctx.jito_tip_floor,
                "rpc_latencies": ctx.rpc_latencies
            }
        })
    
    context_driver.set_callback(on_context_update)
    context_driver.start()

    # 6. LST De-Pegger Engine (Paper Mode)
    from src.engines.lst_depeg.logic import LSTEngine
    lst_engine = LSTEngine(mode="paper")
    dashboard.local_engines["lst"] = lst_engine
    await engine_registry.update_status("lst", EngineStatus.STOPPED)
    
    async def on_lst_update(data):
        payload = {
            "type": "LST_UPDATE",
            "data": data,
            "timestamp": asyncio.get_event_loop().time()
        }
        await dashboard.broadcast(json.dumps(payload))
        
    lst_engine.set_callback(on_lst_update)
    # await lst_engine.start() # Default OFF
    
    # 7. Scalp Engine (Meme/Token Scalper) - Paper Mode
    from src.engines.scalp.logic import ScalpEngine
    scalp_engine = ScalpEngine(live_mode=False)
    dashboard.local_engines["scalp"] = scalp_engine
    await engine_registry.update_status("scalp", EngineStatus.STOPPED)
    
    async def on_scalp_update(data):
        # data is {"type": "SIGNAL", "data": ...}
        # If it's a signal, we want to broadcast SCALP_SIGNAL for the intel table
        # AND SCALP_UPDATE for the component view.
        
        if data.get("type") == "SIGNAL":
             # 1. Update Intel Table
             await dashboard.broadcast({
                 "type": "SCALP_SIGNAL",
                 "data": data.get("data"),
                 "timestamp": asyncio.get_event_loop().time()
             })
        
        # 2. Update Component View
        payload = {
            "type": "SCALP_UPDATE",
            "payload": data, # Nested
            "timestamp": asyncio.get_event_loop().time()
        }
        await dashboard.broadcast(json.dumps(payload))
        
    scalp_engine.set_callback(on_scalp_update)
    # await scalp_engine.start() # Default OFF

    # 8. Arb Engine (Trip Hopper) - Paper Mode
    from src.engines.arb.logic import ArbEngine
    arb_engine = ArbEngine(live_mode=False)
    dashboard.local_engines["arb"] = arb_engine
    await engine_registry.update_status("arb", EngineStatus.STOPPED)

    async def on_arb_update(data):
        # Broadcast as ARB_OPP for the intel table
        if "est_profit" in data:
             await dashboard.broadcast({
                 "type": "ARB_OPP",
                 "data": data,
                 "timestamp": asyncio.get_event_loop().time()
             })

        # Also broadcast ARB_UPDATE for component if needed (though ArbScanner listens to ARB_OPP mostly)
        payload = {
            "type": "ARB_UPDATE",
            "payload": data,
            "timestamp": asyncio.get_event_loop().time()
        }
        await dashboard.broadcast(json.dumps(payload))
    
    arb_engine.set_callback(on_arb_update)
    # await arb_engine.start() # Default OFF

    # 9. Funding Engine (Delta Neutral) - Paper Mode
    from src.engines.funding.logic import FundingEngine
    funding_engine = FundingEngine(live_mode=False)
    dashboard.local_engines["funding"] = funding_engine
    await engine_registry.update_status("funding", EngineStatus.STOPPED)

    async def on_funding_update(data):
        payload = {
            "type": "FUNDING_UPDATE",
            "payload": data,
            "timestamp": asyncio.get_event_loop().time()
        }
        # Funding engine sends status every minute
        await dashboard.broadcast(json.dumps(payload))

    funding_engine.set_callback(on_funding_update)
    # await funding_engine.start() # Default OFF
    
    # Add to engine manager (mock registration for now, ideally EngineManager handles this)
    # Since EngineManager is a subprocess manager, and we are running LST in-process for this MVP:
    # We might need to manually inject status into the stats broadcast or register it properly.
    # For MVP, we'll let it run and log to console, and maybe add a UI card later.

    Logger.info("📈 Live price feed connected (Pyth WebSocket)")
    Logger.info("🎯 Token watchlist tracking 10 meme/AI tokens")
    Logger.info("🌍 Market Context Driver active (SOL/BTC, Jito)")
    Logger.info("💧 LST De-Pegger Engine active (Paper Mode)")
    Logger.info("🔌 WebSocket server starting on ws://localhost:8765")
    Logger.info("")
    Logger.info("="*50)
    Logger.info("🎛️  COMMAND CENTER ONLINE")
    Logger.info("   Open http://localhost:8000 in your browser")
    Logger.info("="*50)
    
    try:
        await dashboard.start()
    except KeyboardInterrupt:
        Logger.info("👋 Shutting down...")
    finally:
        price_feed.stop()
        watchlist_feed.stop()
        context_driver.stop()
        await lst_engine.stop()
        await scalp_engine.stop()
        await arb_engine.stop()
        await funding_engine.stop()


if __name__ == "__main__":
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
