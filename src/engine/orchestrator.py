"""
Market Orchestrator (Mission Control)
=====================================
Phase 29b: The Orchestrator Pattern

Centralizes the lifecycle management of the entire Phantom Arbiter system:
1.  **System Hygiene**: Runs cleanup scripts.
2.  **Visual Bridge**: Starts the WebSocket visualization layer.
3.  **Frontend**: Optionally launches the Svelte HUD.
4.  **Director**: Initializes the brain (Director).
5.  **Shutdown**: Gracefully handles exit signals.
"""

import asyncio
import os
import subprocess
import sys
import time
import logging
from typing import Optional

# Import the clean_code logic (dynamically or via import if path is fixed)
# Since clean_code.py is in root, we might need sys.path hack or just execute it as subprocess.
# Subprocess is safer for script execution to avoid pollution.

from src.engine.director import Director
from src.arbiter.visual_bridge import VisualBridge
from config.settings import Settings

logger = logging.getLogger("Orchestrator")

class MarketOrchestrator:
    def __init__(self, headless_frontend: bool = False):
        self.headless_frontend = headless_frontend
        self.director: Optional[Director] = None
        self.visual_bridge: Optional[VisualBridge] = None
        self.frontend_process: Optional[subprocess.Popen] = None
        self.is_running = False
        
        # Paths
        self.root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self.hud_dir = os.path.join(self.root_dir, "prism_hud")
        self.clean_script = os.path.join(self.root_dir, "clean_code.py")

    def run_hygiene_check(self):
        """Runs the 'Janitor' phase to ensure clean state."""
        print("🧹 Running System Hygiene Check...")
        
        if os.path.exists(self.clean_script):
            try:
                # Run clean_code.py as a separate process to ensure isolation
                result = subprocess.run(
                    [sys.executable, self.clean_script], 
                    capture_output=True, 
                    text=True, 
                    timeout=10
                )
                if result.returncode == 0:
                    print("   ✅ Code Sanitized.")
                else:
                    print(f"   ⚠️ Cleanup Warning: {result.stderr[:100]}...")
            except Exception as e:
                print(f"   ⚠️ Hygiene Check Failed: {e}")
        else:
            print("   ⚠️ clean_code.py not found. Skipping hygiene.")

    def launch_frontend(self):
        """Launches the Svelte HUD background process."""
        if self.headless_frontend:
            print("   ℹ️ Headless Mode: Skipping Frontend Launch.")
            return

        if not os.path.exists(self.hud_dir):
            print(f"   ❌ HUD Directory not found at {self.hud_dir}")
            return

        print("   🚀 Launching Prism HUD...")
        try:
            # Use 'npm run dev'
            # On Windows, shell=True might be needed for npm, but explicit cmd is safer
            cmd = ["npm.cmd", "run", "dev"] if os.name == 'nt' else ["npm", "run", "dev"]
            
            self.frontend_process = subprocess.Popen(
                cmd,
                cwd=self.hud_dir,
                stdout=subprocess.DEVNULL, # Keep console clean
                stderr=subprocess.PIPE,    # Capture errors if needed
            )
            print("   ✅ HUD Process Started.")
        except Exception as e:
            print(f"   ❌ Failed to launch HUD: {e}")

    def ignite_http_server(self):
        """Starts a lightweight HTTP server for 'The Void' frontend."""
        import http.server
        import socketserver
        import threading
        
        PORT = 8000
        DIRECTORY = "frontend"
        
        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                # Serve from the root but default to dashboard.html
                # Or easier: Serve everything, user hits /frontend/dashboard.html
                # Let's serve from ROOT so /frontend/dashboard.html is accessible
                super().__init__(*args, directory=".", **kwargs)

        def run_server():
            try:
                # Allow address reuse
                socketserver.TCPServer.allow_reuse_address = True
                with socketserver.TCPServer(("", PORT), Handler) as httpd:
                    print(f"\n🔮 THE VOID IS OPEN: http://localhost:{PORT}/frontend/dashboard.html")
                    httpd.serve_forever()
            except OSError as e:
                print(f"⚠️ HTTP Server Error (Port {PORT} busy?): {e}")

        # Start in daemon thread
        threading.Thread(target=run_server, daemon=True).start()

    async def ignite_system(self):
        """
        Ignite the Phantom Engine and Visual Bridge.
        """
        self.is_running = True
        
        print("\n" + "═"*40)
        print(" 🔥 PHANTOM OS: IGNITING SYSTEM KERNEL")
        print("═"*40)

        # 1. Visual Bridge (The Voice) - START THIS FIRST
        # V33: Priority 1 - Get the UI pipe open
        self.visual_bridge = VisualBridge()
        bridge_task = asyncio.create_task(self.visual_bridge.start())
        # Give the bridge 100ms to bind before launching monitors
        await asyncio.sleep(0.1)

        print("   🚀 Launching The Void (WebGL)...")
        # V33: Launch HTTP Server (The Void)
        # DISABLE FOR API DECOUPLING (Main.py runs Uvicorn now)
        # self.ignite_http_server()
        
        # 2. Monitors (The Eyes)
        # V33: Ignite Pyth Polling for Full Spectrum
        from src.core.prices.pyth_adapter import PythAdapter
        self.pyth = PythAdapter()
        asyncio.create_task(self.pyth.start_polling(interval=2.0))

        # V33: Ignite Pump.fun Monitor (Orange Layer - Graduation)
        from src.engine.pump_monitor import PumpFunMonitor
        self.pump_monitor = PumpFunMonitor()
        asyncio.create_task(self.pump_monitor.start_monitoring(interval=0.2)) 
        
        # V33: Ignite Scraper (Purple Layer - Discovery)
        from src.scraper.scout.scraper import TokenScraper
        self.scraper = TokenScraper()
        asyncio.create_task(self.scraper.start_scanning(interval=30.0))
        
        # V33: Ignite Launchpad Monitor (Magenta Layer - Multi-Platform)
        from src.scraper.discovery.launchpad_monitor import get_launchpad_monitor
        self.launchpad = get_launchpad_monitor()
        asyncio.create_task(self.launchpad.start())
        
        # V33: Ignite Orca Adapter (Teal Layer - Liquidity)
        from src.liquidity.orca_adapter import OrcaAdapter
        self.orca = OrcaAdapter()
        asyncio.create_task(self.orca.start_polling(interval=5.0))
        
        # 3. Director (The Brain)
        self.director = Director()
        engine_task = asyncio.create_task(self.director.start())
        
        # 4. Terminal Pulse (User Feedback)
        asyncio.create_task(self._run_terminal_pulse())
        
        return bridge_task, engine_task

    async def _run_terminal_pulse(self):
        """Provides the scrolling feedback the user misses."""
        import time
        from src.shared.state.app_state import state
        while self.is_running:
            try:
                # Summary of recent activity
                swaps = len(state.signals) if hasattr(state, "signals") else 0
                print(f"⚡ [PULSE] System Active | Total Signals: {swaps} | Time: {time.strftime('%H:%M:%S')}", flush=True)
                await asyncio.sleep(5.0)
            except:
                await asyncio.sleep(5.0)

    async def shutdown(self):
        """Graceful Shutdown."""
        print("\n🛑 Initiating Graceful Shutdown...")
        self.is_running = False
        
        # 1. Visual Bridge
        if self.visual_bridge:
            # VisualBridge doesn't have an explicit stop method yet, it relies on task cancel
            # We can rely on task cancellation from main, but explicit is better if added
            pass 
            
        # 2. Director
        if self.director:
            await self.director.stop()
            
        # 3. Frontend
        if self.frontend_process:
            print("   Killing Frontend Process...")
            self.frontend_process.terminate()
            try:
                self.frontend_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.frontend_process.kill()
                
        print("✅ System Shutdown Complete.")

    async def keep_alive(self):
        """
        Keeps the main event loop running indefinitely.
        Used when running in Headless/Pure-Web mode (No TUI).
        """
        logger.info("[Orchestrator] Entering Keep-Alive Loop. Press Ctrl+C to exit.")
        try:
            while self.is_running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
