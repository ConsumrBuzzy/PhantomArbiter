
import asyncio
import time
from src.shared.system.logging import Logger
from src.shared.state.app_state import state

class LagMonitor:
    """
    V23: Event Loop Starvation Guard.
    
    Monitors the 'lag' of the asyncio event loop by scheduling a sleep(0.01)
    and measuring how long it actually takes to return.
    
    Metrics:
    - Target sleep: 10ms (0.01s)
    - Lag = Actual Duration - Target Sleep
    
    Thresholds:
    - < 2ms: Green (Healthy)
    - > 10ms: Orange (Congested)
    - > 50ms: Red (Starvation - 'Slow Tier' leaking)
    """
    def __init__(self):
        self.running = False
        self.interval = 0.5 # Check every 500ms
        self.check_duration = 0.01 # 10ms sleep target
        
    async def start(self):
        self.running = True
        Logger.info("[LAG_MONITOR] 🛡️ Event Loop Guard Active")
        
        while self.running:
            try:
                start_time = time.perf_counter()
                await asyncio.sleep(self.check_duration)
                end_time = time.perf_counter()
                
                # Calculate Lag
                actual_duration = end_time - start_time
                lag = actual_duration - self.check_duration
                lag_ms = lag * 1000.0
                
                # Update AppState (Smooth it out slightly?)
                # For high-freq updates, we just write latest
                state.update_stat("loop_lag_ms", round(lag_ms, 2))
                
                # Warn if heavy starvation
                if lag_ms > 50.0:
                    Logger.warning(f"[LAG_MONITOR] ⚠️ STARVATION DETECTED: {lag_ms:.1f}ms lag!")
                
                await asyncio.sleep(self.interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                Logger.error(f"[LAG_MONITOR] Error: {e}")
                await asyncio.sleep(5)

    def stop(self):
        self.running = False
