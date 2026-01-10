"""
Unified Director - The Brain (Sprint 2)
=======================================
Single entry point for the PhantomArbiter system.
Eliminates the "Two Brains" fracture by centralizing:
1. Data Flow (DataBroker) - Sensors & Data Feeds
2. Execution (PhantomArbiter) - High-frequency Arbitrage
3. Execution (TacticalStrategy) - Scalping & Strategies

Usage:
    python src/director.py --live
"""

import asyncio
import signal
import sys
import os
from typing import Dict, Optional

# Core Infrastructure
from src.core.data_broker import DataBroker
from src.shared.state.app_state import state
# Use new global logger
try:
    from src.core.logger import setup_logging
    Logger = setup_logging("INFO")
except ImportError:
    from src.shared.system.logging import Logger

from src.shared.system.priority_queue import priority_queue # V140
from config.settings import Settings

# Engines
from src.legacy.arbiter.arbiter import PhantomArbiter, ArbiterConfig
from src.legacy.strategies.tactical import TacticalStrategy 

# Rust Acceleration
try:
    from phantom_core import PdaCache
except ImportError:
    PdaCache = None

# Galaxy Event Bridge
try:
    from src.shared.infrastructure.event_bridge import start_event_bridge, stop_event_bridge
    GALAXY_BRIDGE_AVAILABLE = True
except ImportError:
    GALAXY_BRIDGE_AVAILABLE = False
    start_event_bridge = None  # type: ignore
    stop_event_bridge = None  # type: ignore


class UnifiedDirector:
    """
    The Single Brain.
    Orchestrates the lifecycle of:
    - DataBroker (Senses: WSS, Scraper)
    - PhantomArbiter (Fast Lane: 1-cycle Arb)
    - TacticalStrategy (Mid Lane: Scalping)
    """

    def __init__(self, live_mode: bool = False, execution_enabled: bool = False):
        self.is_running = False
        self.live_mode = live_mode
        self.execution_enabled = execution_enabled
        self.tasks = {}

        Logger.info("="*40)
        Logger.info("UNIFIED DIRECTOR INITIATING")
        Logger.info("="*40)
        
        # V140: Start System Queue
        priority_queue.start()

        # 1. The Nervous System (DataBroker)
        # Initialize as SENSORS ONLY (enable_engines=False)
        # This prevents DataBroker from spawning its own TacticalStrategy/Arbiter
        Logger.info("[Brain] Initializing Nervous System (DataBroker)...")
        self.broker = DataBroker(enable_engines=False)
        
        # 2. Rust Optimizations
        if PdaCache:
            Logger.info("[Brain] Rust Acceleration Enabled (PdaCache)")
            self.pda_cache = PdaCache() 
        else:
            Logger.warning("[Brain] Rust Acceleration MISSING (phantom_core not found)")
            self.pda_cache = None
        
        # 3. Fast Lane (Arbiter)
        Logger.info(f"[Brain] Initializing Fast Lane (Arbiter) [Live={live_mode}]...")
        arb_config = ArbiterConfig(live_mode=live_mode)
        self.arbiter = PhantomArbiter(config=arb_config)
        
        # Wire HopEngine if available in Broker
        if hasattr(self.broker, 'hop_engine') and self.broker.hop_engine:
            # TODO: Expose method on PhantomArbiter to accept hop_engine if needed
            # currently PhantomArbiter manages its own scanners
            pass

        # 4. Mid Lane (Scalper)
        Logger.info("[Brain] Initializing Mid Lane (Scalper)...")
        self.scalper = TacticalStrategy(engine_name="SCALPER")
        if self.live_mode:
             # Configure scalper for live mode if needed (usually follows settings)
             pass
        
        # 5. Galaxy Event Bridge (Phase 24)
        self.event_bridge = None
        if GALAXY_BRIDGE_AVAILABLE:
            Logger.info("[Brain] Galaxy EventBridge available (starts with ignition)")
        else:
            Logger.info("[Brain] Galaxy EventBridge not available (httpx missing?)")

    async def start(self):
        """Ignition Sequence."""
        self.is_running = True
        state.status = "IGNITION"
        state.log("🧠 [Director] Unified Brain Ignition...")

        # Setup Signal Handlers for Graceful Shutdown
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
            except NotImplementedError:
                # Windows might not support add_signal_handler fully in some loops
                pass

        # A. Start Nervous System (DataBroker)
        # Run DataBroker in valid thread (it blocks)
        self.tasks['broker'] = asyncio.create_task(
            self._run_broker(), name="DataBroker"
        )
        Logger.info("[Brain] DataBroker task scheduled")

        # Wait for WSS Warmup (2s)
        await asyncio.sleep(2.0) 

        # B. Start Engines
        if self.execution_enabled:
            # 1. Arbiter (Fast Lane)
            # Arbiter.run() is an async loop
            Logger.info("[Brain] Igniting Arbiter Engine...")
            self.tasks['arbiter'] = asyncio.create_task(
                self.arbiter.run(duration_minutes=60*24, scan_interval=2),
                name="Arbiter"
            )
            
            # 2. Scalper (Mid Lane)
            # TacticalStrategy needs a loop wrapper
            Logger.info("[Brain] Igniting Scalper Engine...")
            self.tasks['scalper'] = asyncio.create_task(
                self._run_scalper_loop(), name="Scalper"
            )
        else:
            Logger.warning("⛔ Execution Systems (Arbiter/Scalper): STANDBY MODE")
        
        # 3. Galaxy Event Bridge (non-blocking telemetry to Galaxy)
        if GALAXY_BRIDGE_AVAILABLE:
            galaxy_url = os.getenv("GALAXY_URL", "http://localhost:8001")
            self.event_bridge = start_event_bridge(galaxy_url)
            Logger.info(f"[Brain] EventBridge → {galaxy_url}")
        
        state.status = "OPERATIONAL"
        state.log("🧠 [Director] System Operational.")
        
        # Monitor Loop (Keep Main Thread Alive)
        await self._monitor_loop()

    async def _run_broker(self):
        """Run DataBroker in non-blocking way."""
        try:
            # DataBroker.run() is blocking, so we offload to thread
            await asyncio.to_thread(self.broker.run)
        except Exception as e:
            import traceback
            Logger.error(f"[Brain] DataBroker Crashed: {e}")
            traceback.print_exc()

    async def _run_scalper_loop(self):
        """Scalper loop wrapper."""
        Logger.info("[Scalper] Loop Started")
        while self.is_running:
            try:
                # Scalper has its own interval logic usually?
                # TacticalStrategy.run_tick() style?
                # TacticalStrategy acts on signals.
                # But it also needs a heartbeat/tick?
                if hasattr(self.scalper, "on_tick"):
                    self.scalper.on_tick()
                elif hasattr(self.scalper, "run_tick"):
                    self.scalper.run_tick()
                
                # Sleep interval (1s)
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                Logger.error(f"[Scalper] Error: {e}")
                await asyncio.sleep(5) # Backoff

    async def _monitor_loop(self):
        """
        Simple monitor loop that keeps the main thread alive.
        No complex UI panels, just simple logging.
        """
        Logger.info("[DIRECTOR] 🟢 System Online - Monitoring Active")
        
        try:
            while self.is_running:
                # V89.5: Clean Keep-Alive (No TUI/Panels)
                # Check task health occasionally
                for name, task in self.tasks.items():
                    if task.done():
                        exc = task.exception()
                        if exc:
                            Logger.error(f"[Brain] Task '{name}' FAILED: {exc}")
                
                await asyncio.sleep(1.0)
                
        except asyncio.CancelledError:
            Logger.info("[DIRECTOR] Monitor loop cancelled")
        except Exception as e:
            Logger.error(f"[DIRECTOR] Monitor loop error: {e}")

    async def stop(self):
        """Shutdown."""
        if not self.is_running:
            return
            
        Logger.info("🛑 [Brain] Initiating Shutdown Sequence...")
        self.is_running = False
        state.status = "SHUTDOWN"
        
        # Stop broker (it has a stop flag)
        if hasattr(self.broker, 'stop'):
             self.broker.stop()
        
        # Stop Arbiter
        await self.arbiter.stop()
        
        # Stop Scalper (if needed)
        # self.scalper.stop() 
        
        # Stop EventBridge
        if GALAXY_BRIDGE_AVAILABLE and self.event_bridge:
            stop_event_bridge()
            Logger.info("[Brain] EventBridge stopped")

        # Cancel asyncio tasks
        for name, task in self.tasks.items():
            if not task.done():
                Logger.debug(f"[Brain] Cancelling {name}...")
                task.cancel()
        
        # Wait for cancellations
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        Logger.info("✅ [Brain] Shutdown Complete")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="PhantomArbiter Unified Director")
    parser.add_argument("--live", action="store_true", help="Enable LIVE trading mode")
    args = parser.parse_args()
    
    # Configure Logging
    Logger.setup(filename="director.log")
    
    director = UnifiedDirector(live_mode=args.live)
    
    try:
        if sys.platform == 'win32':
             # Windows Event Loop Policy fix
             asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(director.start())
    except KeyboardInterrupt:
        # Handled by signal handler, but just in case
        pass
