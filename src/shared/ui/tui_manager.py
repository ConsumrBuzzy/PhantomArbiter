"""
TUI Manager
===========
Shared orchestrator for running trading engines with a Rich TUI.
"""

import asyncio
import sys
import time
from datetime import datetime
from rich.live import Live
from loguru import logger
from src.shared.system.logging import Logger, ENGINE_LOG_PATH
from src.shared.ui.rich_panel import DNEMDashboard

class TUIRunner:
    """
    Wraps an engine and runs its cycle within a Rich Live TUI.
    """
    def __init__(self, engine, mode_name: str, tick_interval: float = 1.0):
        self.engine = engine
        self.mode_name = mode_name
        self.tick_interval = tick_interval
        self.dashboard = DNEMDashboard()
        self.log_buffer = None

    async def run(self):
        # 1. Reconfigure Logging for TUI
        logger.remove()
        Logger.add_file_sink(ENGINE_LOG_PATH)
        self.log_buffer = Logger.add_memory_sink(maxlen=10)
        
        # 2. Prepare Data Object
        # Note: Engines will ALSO update AppState directly
        engine_data = {
            "mode": self.mode_name,
            "state": "ACTIVE",
            "recent_logs": []
        }
        
        # 3. Enter TUI Loop
        last_tick = 0
        with Live(self.dashboard.layout, refresh_per_second=4, screen=True):
            while True:
                try:
                    now = time.time()
                    
                    # Execute engine cycle if interval passed
                    if now - last_tick >= self.tick_interval:
                        if hasattr(self.engine, "tick"):
                            result = await self.engine.tick()
                            if result: engine_data.update(result)
                        last_tick = now
                    
                    # Update UI
                    engine_data["recent_logs"] = list(self.log_buffer)
                    self.dashboard.update(engine_data)
                    
                    await asyncio.sleep(0.1) 

                except KeyboardInterrupt:
                    break
                except Exception as e:
                    Logger.error(f"TUI Runner Error: {e}")
                    await asyncio.sleep(1)

        Logger.section(f"👋 Shutdown: {self.mode_name}")
