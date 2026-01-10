"""
Dashboard Launcher (Minimal)
============================
Launches just the Command Center UI without legacy engine dependencies.
Includes live market data feed (SOL price from Pyth).

Usage:
    python run_dashboard.py
"""

import asyncio
import sys
import os
import http.server
import socketserver
import threading

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()


async def main():
    """Launch the Command Center dashboard with live market data."""
    from src.shared.system.logging import Logger
    from src.shared.feeds.simple_price_feed import SimplePriceFeed, PriceData
    
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
    
    # 3. Price Feed - Streams live SOL price
    price_feed = SimplePriceFeed()
    
    async def on_price_update(price: PriceData):
        """Broadcast price updates to all connected clients."""
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
    
    Logger.info("📈 Live price feed connected (Pyth WebSocket)")
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


if __name__ == "__main__":
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
