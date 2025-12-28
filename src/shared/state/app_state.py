from collections import deque
from typing import List, Dict, Any
from dataclasses import dataclass, field
import threading
import time

@dataclass
class ArbOpportunity:
    token: str
    route: str
    profit_pct: float
    est_profit_sol: float
    timestamp: float = field(default_factory=time.time)

class AppState:
    """
    Thread-safe Singleton for UI/Worker communication.
    The 'Bridge' between Headless Logic and Textual UI.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(AppState, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized: return
        
        self.status = "INITIALIZING"
        self.logs = deque(maxlen=200) # Keep last 200 logs
        self.opportunities: List[ArbOpportunity] = []
        
        # Real-time Stats
        self.stats = {
            "cycles_per_sec": 0,
            "wss_latency_ms": 0,
            "total_pnl_sol": 0.0,
            "rust_core_active": False,
            "start_time": time.time()
        }
        
        self._initialized = True

    def log(self, message: str):
        """Add a log message."""
        # Simple timestamp prefix? Textual Log handles it? 
        # Let's just store the raw string, the UI can format.
        self.logs.append(message)

    def add_opportunity(self, opp: ArbOpportunity):
        """Register a new arbitrage opportunity."""
        self.opportunities.insert(0, opp)
        # Keep list trim
        if len(self.opportunities) > 50:
            self.opportunities.pop()

    def update_stat(self, key: str, value: Any):
        """Update a specific stat."""
        self.stats[key] = value

    def get_logs(self) -> List[str]:
        return list(self.logs)

# Global Accessor
state = AppState()
