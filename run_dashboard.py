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
    
    # 2. WebSocket Dashboard Server
    from src.interface.dashboard_server import DashboardServer
    dashboard = DashboardServer()
    
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
    
    Logger.info("📈 Live price feed connected (Pyth WebSocket)")
    Logger.info("🎯 Token watchlist tracking 10 meme/AI tokens")
    Logger.info("🌍 Market Context Driver active (SOL/BTC, Jito)")
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


if __name__ == "__main__":
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
