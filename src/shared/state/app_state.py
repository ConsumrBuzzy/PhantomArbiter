from collections import deque
from typing import List, Dict, Any
from dataclasses import dataclass, field
import threading
import time
import os
from src.core.global_state import GlobalState
from src.shared.system.signal_bus import signal_bus, Signal, SignalType

@dataclass
class ArbOpportunity:
    token: str
    route: str
    profit_pct: float
    est_profit_sol: float
    timestamp: float = field(default_factory=time.time)

@dataclass
class InventoryItem:
    """Represents a held token with its value and pnl."""
    symbol: str
    amount: float
    value_usd: float = 0.0
    pnl: float = 0.0
    price_change_24h: float = 0.0

@dataclass
class WalletData:
    """Snapshot of a wallet's state."""
    balance_sol: float = 0.0
    balance_usdc: float = 0.0
    gas_sol: float = 0.0
    # V12.6: Support both Dict (legacy) and List (V100) of InventoryItems
    inventory: Any = field(default_factory=dict) 
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
        # Value is Dict: {'price': float, 'rsi': float, 'conf': float, 'action': str}
        self.market_pulse: Dict[str, Dict[str, Any]] = {} 
        self.scalp_signals: List[ScalpSignal] = []
        self.system_signals = deque(maxlen=50) # V35: Unified Signal Audit
        
        # V133: UI Footer Timestamp (seconds since last pulse update)
        self.last_pulse_time: float = 0.0
        
        # V133: Flash Error Bar (Real-time Red Alert display)
        self.flash_errors: deque = deque(maxlen=10)
        
        # V33: Persistent Registry Sync
        self._load_from_global_state()
        
        self._initialized = True

    def _load_from_global_state(self):
        """Initialize stats and mode from persistent GlobalState."""
        gs = GlobalState.read_state()
        self.mode = gs.get("MODE", "PAPER")
        self.stats["base_size_usd"] = gs.get("BASE_SIZE_USD", 50.0)
        self.stats["max_exposure_usd"] = gs.get("MAX_EXPOSURE_USD", 1000.0)
        self.stats["engines_halted"] = gs.get("ENGINES_HALTED", False)

    def update_persistent_setting(self, key: str, value: Any):
        """Update a setting and sync to disk."""
        if key == "MODE":
            self.mode = value
        elif key == "BASE_SIZE_USD":
            self.stats["base_size_usd"] = value
        
        # Sync to GlobalState (disk)
        GlobalState.update_state({key: value})
        self.log(f"[State] Persistent setting {key} -> {value}")
        
        # V35: Reactive Notify
        signal_bus.emit(Signal(
            type=SignalType.CONFIG_CHANGE,
            source="AppState",
            data={"key": key, "value": value}
        ))

    # ... (methods) ...
    
    def update_pulse(self, symbol: str, price: float):
        """Update live price for ticker (Legacy)."""
        self.market_pulse[symbol] = {'price': price}

    def update_pulse_batch(self, data: Dict[str, Dict[str, Any]]):
        """Update multiple tickers at once."""
        self.market_pulse.update(data)
        self.last_pulse_time = time.time()  # V133: Track for UI footer
        
    def add_signal(self, signal: ScalpSignal):
        """Add new scalp signal."""
        self.scalp_signals.insert(0, signal)
        if len(self.scalp_signals) > 50:
            self.scalp_signals.pop()

    def add_system_signal(self, sig: Any):
        """Add any signal to the audit log."""
        self.system_signals.appendleft(sig)

    def log(self, message: str):
        """Add a log message."""
        self.logs.append(message)
    
    def flash_error(self, message: str):
        """V133: Add a flash error for UI Red Alert bar."""
        self.flash_errors.appendleft({"msg": message, "ts": time.time()})

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
    def inventory(self) -> List[InventoryItem]:
        """Get inventory list for current mode (Compatible with Dashboard)."""
        wallet = self.wallet_live if self.mode == "LIVE" else self.wallet_paper
        
        # If inventory is already a list of InventoryItems (V100 path), return it
        if isinstance(wallet.inventory, list):
            return wallet.inventory
        
        # Legacy path: Convert dict {symbol: amount} to list of objects
        items = []
        if isinstance(wallet.inventory, dict):
            for symbol, amount in wallet.inventory.items():
                try:
                    from src.core.shared_cache import SharedPriceCache
                    price, _ = SharedPriceCache.get_price(symbol)
                    if price:
                        value_usd = price * amount
                        items.append(InventoryItem(symbol=symbol, amount=amount, value_usd=value_usd))
                    else:
                        items.append(InventoryItem(symbol=symbol, amount=amount))
                except:
                    items.append(InventoryItem(symbol=symbol, amount=amount))
        return items

# Global Accessor
state = AppState()
