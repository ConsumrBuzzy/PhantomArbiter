import psutil
import os
import time
from src.system.logging import Logger
from src.core.global_state import GlobalState

class SystemMonitor:
    """
    V30.1: System Health Monitoring.
    Tracks CPU, Memory usage and triggers warnings/shutdowns.
    """
    
    # Thresholds
    MAX_CPU_PERCENT = 90.0
    MAX_MEM_PERCENT = 90.0
    CHECK_INTERVAL = 60 # seconds
    
    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.last_check = 0
        
    def check_health(self):
        """Run health check. Should be called periodically."""
        now = time.time()
        if now - self.last_check < self.CHECK_INTERVAL:
            return
            
        self.last_check = now
        
        # 1. CPU
        cpu = self.process.cpu_percent()
        if cpu > self.MAX_CPU_PERCENT:
             Logger.warning(f"🔥 [SYSTEM] High CPU Usage: {cpu}%")
             
        # 2. Memory
        mem = self.process.memory_info().rss / (1024 * 1024) # MB
        mem_pct = psutil.virtual_memory().percent
        
        if mem_pct > self.MAX_MEM_PERCENT:
            Logger.critical(f"🛑 [SYSTEM] CRITICAL MEMORY USAGE: {mem_pct}% ({mem:.1f} MB). Triggering Graceful Restart.")
            # Trigger Restart Logic
            self._trigger_restart()
            
        # Log Stats occasionally (DEBUG)
        # Logger.debug(f"🖥️ [SYSTEM] CPU: {cpu}% | MEM: {mem:.1f}MB ({mem_pct}%)")

    def _trigger_restart(self):
        """
        Set Global State to requested restart.
        The main loop should handle this.
        """
        GlobalState.update_state({'RESTART_REQUESTED': True})
        from src.system.comms_daemon import send_telegram
        send_telegram("🔄 System Restart Requested (Memory/CPU Limit)", source="SYSTEM", priority="HIGH")
