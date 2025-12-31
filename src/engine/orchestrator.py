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

    async def ignite_system(self):
        """Ignites the Director and Visual Bridge."""
        self.is_running = True
        
        # 1. Visual Bridge (The Eyes)
        self.visual_bridge = VisualBridge()
        bridge_task = asyncio.create_task(self.visual_bridge.start())
        
        # 2. Director (The Brain)
        self.director = Director()
        engine_task = asyncio.create_task(self.director.start())
        
        return bridge_task, engine_task

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
