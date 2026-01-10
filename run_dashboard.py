"""
Dashboard Launcher (Minimal)
============================
Launches just the Command Center UI without legacy engine dependencies.

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
    """Launch the Command Center dashboard."""
    from src.shared.system.logging import Logger
    
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
    
    Logger.info("🔌 WebSocket server starting on ws://localhost:8001")
    Logger.info("")
    Logger.info("="*50)
    Logger.info("🎛️  COMMAND CENTER ONLINE")
    Logger.info("   Open http://localhost:8000 in your browser")
    Logger.info("="*50)
    
    try:
        await dashboard.start()
    except KeyboardInterrupt:
        Logger.info("👋 Shutting down...")


if __name__ == "__main__":
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
