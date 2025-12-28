import asyncio
import time
from typing import Optional
from src.shared.state.app_state import state
from src.shared.infrastructure.websocket_listener import WebSocketListener
from src.arbiter.arbiter import PhantomArbiter, ArbiterConfig
from src.scalper.engine import ScalperConfig

class PhantomScalperEngine:
    def __init__(self, config):
        self.config = config
        self.watchlist = []
    
    async def run_cycle(self):
        # Logic: Check watchlist -> Execute Strategy
        pass

class Director:
    """
    The Orchestrator.
    Manages the lifecycle of Fast Lane (Arb) and Slow Lane (Scout/Whale) tasks.
    And now: Mid Lane (Scalper).
    """
    def __init__(self, live_mode: bool = False):
        self.is_running = False
        self.fast_tasks = []
        self.mid_tasks = []
        self.slow_tasks = []
        
        # Components
        # V3.1: Inject dependencies for WebSocketListener
        class MockPriceCache:
            def update_price(self, mint, price): pass
        
        self.price_cache = MockPriceCache()
        self.watched_mints = {"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC"}
        
        self.listener = WebSocketListener(self.price_cache, self.watched_mints)
        
        # 1. ARBITER (Atomic)
        arb_config = ArbiterConfig(live_mode=live_mode) 
        self.arbiter = PhantomArbiter(arb_config)
        
        # 2. SCALPER (Inventory)
        scalp_config = ScalperConfig(live_mode=live_mode)
        self.scalper = PhantomScalperEngine(scalp_config)
        
        # 3. SCOUT (Discovery)
        self.scout_active = True

    async def start(self):
        """Ignition."""
        self.is_running = True
        state.status = "STARTING_ENGINES"
        state.log("[Director] Igniting Systems...")
        
        # 1. THE WIRE (Fast Lane)
        self.fast_tasks.append(asyncio.create_task(self._run_wss()))
        state.update_stat("rust_core_active", True)
        
        # 2. THE SCALPER (Mid Lane)
        self.mid_tasks.append(asyncio.create_task(self._run_scalper_loop()))
        
        # 3. THE SCOUT (Slow Lane)
        self.slow_tasks.append(asyncio.create_task(self._run_scout_loop()))
        
        # 4. THE WHALE (Slow Lane)
        self.slow_tasks.append(asyncio.create_task(self._run_whale_loop()))
        
        state.status = "OPERATIONAL"
        state.log("[Director] All Systems Nominal.")

    async def stop(self):
        """Shutdown."""
        self.is_running = False
        state.log("[Director] Shutting down...")
        self.listener.stop()
        
        for task in self.fast_tasks + self.mid_tasks + self.slow_tasks:
            task.cancel()
        
        state.status = "OFFLINE"

    async def _run_wss(self):
        """Fast Lane: WebSocket Listener."""
        try:
            await self.listener.start()
        except Exception as e:
            state.log(f"[Director] ❌ WSS Crash: {e}")

    async def _run_scalper_loop(self):
        """Mid Lane: Scalping Strategy."""
        state.log("[Director] Scalper: Active (Interval: 2s)")
        while self.is_running:
            try:
                await asyncio.sleep(2)
                # await self.scalper.run_cycle()
                # Mock activity for TUI
                if len(self.scalper.watchlist) > 0:
                     # state.log(f"[Scalper] Analyzing {len(self.scalper.watchlist)} tokens...")
                     pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                state.log(f"[Scalper] Error: {e}")

    async def _run_scout_loop(self):
        """Slow Lane: Token Discovery."""
        state.log("[Director] Scout Agent: Active (Interval: 60s)")
        while self.is_running:
            try:
                # 1. Sleep first
                await asyncio.sleep(60)
                
                # 2. Perform Scan (Mock)
                # new_tokens = await self.scout.scan()
                new_tokens = ["MOCK_TOKEN"] # Mock
                
                # 3. Feed Scalper
                if new_tokens:
                    self.scalper.watchlist.extend(new_tokens)
                    state.log(f"[Scout] Found {len(new_tokens)} targets -> Passed to Scalper")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                state.log(f"[Scout] Error: {e}")

    async def _run_whale_loop(self):
        """Slow Lane: Smart Money Tracker."""
        state.log("[Director] Whale Watcher: Active (Interval: 300s)")
        while self.is_running:
            try:
                await asyncio.sleep(300)
                # await self.whale.track()
            except asyncio.CancelledError:
                break
            except Exception as e:
                state.log(f"[Whale] Error: {e}")
