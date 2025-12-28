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

@dataclass
class ScalpSignal:
    token: str
    signal_type: str # "RSI Oversold", "Breakout"
    confidence: str # "High", "Med"
    action: str # "BUY", "SELL"
    timestamp: float = field(default_factory=time.time)

class AppState:
    """
    Thread-safe Singleton for UI/Worker communication.
    The 'Bridge' between Headless Logic and Textual UI.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(AppState, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized: return
        
        self.status = "INITIALIZING"
        self.logs = deque(maxlen=200)
        self.opportunities: List[ArbOpportunity] = []
        
        # Real-time Stats
        self.stats = {
            "cycles_per_sec": 0,
            "wss_latency_ms": 0,
            "loop_lag_ms": 0.0, # V23 Supervisor Metric
            "total_pnl_sol": 0.0,
            "rust_core_active": False,
            "start_time": time.time(),
            "pod_status": "Starting..." # V27: Pod Rotation Status
        }
        
        # V12.1: Wallet State (Dashboard 2.0)
        self.wallet_live = WalletData()
        self.wallet_paper = WalletData()
        self.mode = "PAPER"
        
        # V12.2: High-Fidelity Data (Market Pulse)
        self.market_pulse: Dict[str, float] = {} # {Symbol: Price}
        self.scalp_signals: List[ScalpSignal] = []
        
        self._initialized = True

    # ... (methods) ...
    
    def update_pulse(self, symbol: str, price: float):
        """Update live price for ticker."""
        self.market_pulse[symbol] = price
        
    def add_signal(self, signal: ScalpSignal):
        """Add new scalp signal."""
        self.scalp_signals.insert(0, signal)
        if len(self.scalp_signals) > 50:
            self.scalp_signals.pop()

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

    @property
    def inventory(self) -> List[Any]:
        """Get inventory list for current mode (Compatible with Dashboard)."""
        # Convert dict {symbol: amount} to list of objects or dicts for UI
        # We need objects with .symbol, .value_usd, .pnl for the UI
        wallet = self.wallet_live if self.mode == "LIVE" else self.wallet_paper
        items = []
        for symbol, amount in wallet.inventory.items():
            # Mock objects or simple dict access? 
            # PulsedDashboard expects .symbol, .value_usd, .pnl
            # We'll return a simple ad-hoc object
            @dataclass
            class InventoryItem:
                symbol: str
                amount: float
                value_usd: float = 0.0
                pnl: float = 0.0
            
            # TODO: Enrich with real price/pnl
            items.append(InventoryItem(symbol, amount, 0.0, 0.0))
        return items

# Global Accessor
state = AppState()
