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

@dataclass
class WalletData:
    """Snapshot of a wallet's state."""
    balance_sol: float = 0.0
    balance_usdc: float = 0.0
    gas_sol: float = 0.0
    inventory: Dict[str, float] = field(default_factory=dict) # {symbol: amount}
    total_value_usd: float = 0.0

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
        
        # V12.1: Wallet State (Dashboard 2.0)
        self.wallet_live = WalletData()
        self.wallet_paper = WalletData()
        self.mode = "PAPER" # Default
        
        self._initialized = True

    def log(self, message: str):
        """Add a log message."""
        self.logs.append(message)

    def add_opportunity(self, opp: ArbOpportunity):
        """Register a new arbitrage opportunity."""
        self.opportunities.insert(0, opp)
        if len(self.opportunities) > 50:
            self.opportunities.pop()

    def update_stat(self, key: str, value: Any):
        """Update a specific stat."""
        self.stats[key] = value

    def update_wallet(self, is_live: bool, data: WalletData):
        """Update wallet snapshot."""
        if is_live:
            self.wallet_live = data
        else:
            self.wallet_paper = data

    def get_logs(self) -> List[str]:
        return list(self.logs)

# Global Accessor
state = AppState()
