import asyncio
import time
from typing import Optional
from src.shared.state.app_state import state
from src.shared.infrastructure.websocket_listener import WebSocketListener
from src.arbiter.arbiter import PhantomArbiter, ArbiterConfig

# Import Slow Components (mock/real)
# from src.scraper.agents.scout_agent import ScoutAgent 

class Director:
    """
    The Orchestrator.
    Manages the lifecycle of Fast Lane (Arb) and Slow Lane (Scout/Whale) tasks.
    """
    def __init__(self):
        self.is_running = False
        self.fast_tasks = []
        self.slow_tasks = []
        
        # Components
        self.listener = WebSocketListener()
        
        # Configure Arbiter
        # (In prod, load from config/settings/args)
        config = ArbiterConfig(live_mode=False) 
        self.arbiter = PhantomArbiter(config)
        
        # Mocking Scout for now to show structure
        self.scout_active = True

    async def start(self):
        """Ignition."""
        self.is_running = True
        state.status = "STARTING_ENGINES"
        state.log("[Director] Igniting Systems...")
        
        # 1. THE WIRE (Fast Lane)
        # Allows Rust to see logs
        self.fast_tasks.append(asyncio.create_task(self._run_wss()))
        
        # 2. THE ARBITER (Hot Path)
        # Not strictly a loop if event-driven, but we might have a heartbeat
        # For now, Arbiter is reactive to Graph updates pushed by Listener->Rust.
        # But we might want a 'cleanup' loop or 'health check' loop.
        state.update_stat("rust_core_active", True) # Assuming successful init
        
        # 3. THE SCOUT (Slow Lane)
        self.slow_tasks.append(asyncio.create_task(self._run_scout_loop()))
        
        # 4. THE WHALE WATCHER (Slow Lane)
        self.slow_tasks.append(asyncio.create_task(self._run_whale_loop()))
        
        state.status = "OPERATIONAL"
        state.log("[Director] All Systems Nominal.")

    async def stop(self):
        """Shutdown."""
        self.is_running = False
        state.log("[Director] Shutting down...")
        self.listener.stop()
        
        for task in self.fast_tasks + self.slow_tasks:
            task.cancel()
        
        state.status = "OFFLINE"

    async def _run_wss(self):
        """Fast Lane: WebSocket Listener."""
        try:
            await self.listener.start()
        except Exception as e:
            state.log(f"[Director] ❌ WSS Crash: {e}")

    async def _run_scout_loop(self):
        """Slow Lane: Token Discovery."""
        state.log("[Director] Scout Agent: Active (Interval: 60s)")
        while self.is_running:
            try:
                # 1. Sleep first to let system settle
                await asyncio.sleep(60) 
                
                # 2. Perform Scan (Mock for now)
                # candidates = await self.scout.scan()
                # state.log(f"[Scout] Found {len(candidates)} new tokens.")
                pass 
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                state.log(f"[Scout] Error: {e}")
                await asyncio.sleep(60) # Backoff

    async def _run_whale_loop(self):
        """Slow Lane: Smart Money Tracker."""
        state.log("[Director] Whale Watcher: Active (Interval: 300s)")
        while self.is_running:
            try:
                await asyncio.sleep(300)
                # await self.whale.track()
                pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                state.log(f"[Whale] Error: {e}")
