
import time
from src.shared.system.logging import Logger

class BootTimer:
    _start = 0
    
    @classmethod
    def start(cls):
        cls._start = time.time()
        Logger.info(f"⏱️ [BOOT] Clock Started (T+0.00s)")
        
    @classmethod
    def mark(cls, step: str):
        if cls._start == 0: cls.start()
        elapsed = time.time() - cls._start
        Logger.info(f"⏱️ [BOOT] {step} (T+{elapsed:.2f}s)")
