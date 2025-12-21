"""
V40.0: Centralized Capital Manager
==================================
Unified service for managing capital, positions, PnL, and simulation
for all trading engines in both LIVE and MONITOR modes.

Consolidates:
- PaperWallet (V16.0): Simulation, slippage, gas, drawdown
- PortfolioManager (V5.8): Cash tracking, global lock, exposure

Persistence: config/capital_state.json (atomic writes via os.replace)
"""

import json
import os
import time
import random
from typing import Dict, Any, Optional, Tuple, List, ClassVar
from dataclasses import dataclass, field, asdict
from src.shared.system.logging import Logger


# Type aliases for clarity
EngineState = Dict[str, Any]
PositionData = Dict[str, Any]
StatsData = Dict[str, Any]


@dataclass
class Position:
    """Represents a held token position with full type hints."""
    symbol: str
    mint: str
    balance: float
    avg_price: float
    entry_time: float = field(default=0.0)


class CapitalManager:
    """
    V40.0: Centralized capital management for all trading engines.
    
    Features:
    - Engine-isolated capital allocation (V19.0/V39.0 pattern)
    - Atomic JSON persistence (matches GlobalState pattern)
    - Realistic simulation (gas, slippage) for MONITOR mode
    - Unified API for both LIVE and MONITOR modes
    
    V48.0: Enhanced with comprehensive type hints.
    """
    
    # Class-level constants with type hints
    _CONFIG_DIR: ClassVar[str] = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../config"))
    STATE_FILE: ClassVar[str] = os.path.join(_CONFIG_DIR, "capital_state.json")
    
    # Engine configuration
    ENGINE_NAMES: ClassVar[List[str]] = ["MERCHANT"]
    
    # Simulation parameters (V16.2 pattern, now centralized)
    SLIPPAGE_MIN_PCT: ClassVar[float] = 0.005  # 0.5%
    SLIPPAGE_MAX_PCT: ClassVar[float] = 0.010  # 1.0%
    GAS_FEE_SOL: ClassVar[float] = 0.005       # SOL per transaction
    
    # Singleton instance
    _instance: ClassVar[Optional['CapitalManager']] = None
    
    # Instance attributes (declared for type hints)
    default_capital: float
    mode: str
    state: Dict[str, Any]
    _initialized: bool
    
    def __new__(cls, *args, **kwargs):
        """Singleton pattern - one CapitalManager per process."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, default_capital: float = 1000.0, mode: str = "MONITOR"):
        """
        Initialize CapitalManager.
        
        Args:
            default_capital: Initial capital if no state file exists
            mode: "LIVE" or "MONITOR" - affects execution behavior
        """
        if self._initialized:
            return
            
        self.default_capital = default_capital
        self.mode = mode
        self.state: Dict[str, Any] = {}
        
        # Load or initialize state
        self._load_state()
        self._initialize_defaults_if_missing()
        
        self._initialized = True
        Logger.info(f"💰 [CAPITAL] CapitalManager initialized ({mode} mode)")
    
    # ═══════════════════════════════════════════════════════════════════════
    # PERSISTENCE LAYER (Atomic JSON I/O)
    # ═══════════════════════════════════════════════════════════════════════
    
    def _load_state(self) -> None:
        """Load state from JSON file with error handling."""
        if not os.path.exists(self.STATE_FILE):
            self.state = {}
            return
            
        try:
            with open(self.STATE_FILE, 'r') as f:
                self.state = json.load(f)
            Logger.debug(f"[CAPITAL] Loaded state from {self.STATE_FILE}")
        except json.JSONDecodeError as e:
            Logger.error(f"[CAPITAL] Corrupted state file: {e}. Reinitializing.")
            self.state = {}
        except Exception as e:
            Logger.error(f"[CAPITAL] Failed to load state: {e}")
            self.state = {}
    
    def _save_state(self) -> bool:
        """
        Atomically write state to JSON file.
        Uses temp file + os.replace for safety (matches GlobalState pattern).
        """
        temp_file = self.STATE_FILE + ".tmp"
        
        # Update timestamp
        self.state["last_updated"] = time.time()
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Write to temp file
                with open(temp_file, 'w') as f:
                    json.dump(self.state, f, indent=2)
                
                # Atomic swap
                os.replace(temp_file, self.STATE_FILE)
                return True
                
            except PermissionError:
                if attempt < max_retries - 1:
                    time.sleep(0.05)
                else:
                    Logger.error("[CAPITAL] Failed to save state: Permission denied")
                    return False
            except Exception as e:
                Logger.error(f"[CAPITAL] Failed to save state: {e}")
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
                return False
        
        return False
    
    def _initialize_defaults_if_missing(self) -> None:
        """Initialize state structure and split capital if empty."""
        if self.state and "engines" in self.state:
            # State exists, ensure all engines are present
            for name in self.ENGINE_NAMES:
                if name not in self.state["engines"]:
                    self._add_engine(name)
            return
        
        # Fresh initialization
        split_capital = self.default_capital / len(self.ENGINE_NAMES)
        
        self.state = {
            "version": "40.0",
            "total_capital_usd": self.default_capital,
            "last_updated": time.time(),
            "engines": {}
        }
        
        for name in self.ENGINE_NAMES:
            self.state["engines"][name] = self._create_engine_state(name, split_capital)
        
        self._save_state()
        Logger.info(f"[CAPITAL] Initialized ${self.default_capital:.2f} split across {len(self.ENGINE_NAMES)} engines")
    
    def _create_engine_state(self, name: str, capital: float) -> Dict[str, Any]:
        """Create default state structure for an engine."""
        return {
            "allocated_capital": capital,
            "cash_balance": capital,
            "sol_balance": 0.02,  # Starting gas
            "positions": {},  # {symbol: {balance, avg_price, mint, entry_time}}
            "stats": {
                "wins": 0,
                "losses": 0,
                "total_pnl_usd": 0.0,
                "fees_paid_usd": 0.0,
                "slippage_usd": 0.0
            },
            "peak_equity": capital,
            "daily_start_equity": capital
        }
    
    def _add_engine(self, name: str) -> None:
        """Add a new engine with equal share of remaining capital."""
        if name not in self.ENGINE_NAMES:
            # Dynamic engine (e.g. MERCHANT) - Add safely
            if name not in self.ENGINE_NAMES:
                self.ENGINE_NAMES.append(name)
        
        existing_total = sum(
            e.get("allocated_capital", 0) 
            for e in self.state["engines"].values()
        )
        
        # Avoid division by zero if all hardcoded engines are already present
        active_count = len(self.state["engines"])
        total_slots = len(self.ENGINE_NAMES)
        
        # If we are adding a new engine, we effectively increase total slots if not present
        # But here we just want to execute the logic safely.
        
        remaining_slots = max(1, total_slots - active_count) # Prevent Div/0
        
        remaining_cap = max(0, self.state.get("total_capital_usd", 0) - existing_total)
        capital = remaining_cap / remaining_slots
        
        self.state["engines"][name] = self._create_engine_state(name, capital)
        self._save_state()
    
    # ═══════════════════════════════════════════════════════════════════════
    # PUBLIC API - Read Operations
    # ═══════════════════════════════════════════════════════════════════════
    
    def get_engine_state(self, engine_name: str) -> Dict[str, Any]:
        """Get full state dictionary for an engine."""
        return self.state.get("engines", {}).get(engine_name, {})
    
    def get_available_cash(self, engine_name: str) -> float:
        """Get current cash balance for an engine."""
        engine = self.get_engine_state(engine_name)
        return engine.get("cash_balance", 0.0)
    
    def get_sol_balance(self, engine_name: str) -> float:
        """Get SOL balance for gas simulation."""
        engine = self.get_engine_state(engine_name)
        return engine.get("sol_balance", 0.0)
    
    def has_position(self, engine_name: str, symbol: str) -> bool:
        """Check if engine holds a position in symbol."""
        engine = self.get_engine_state(engine_name)
        positions = engine.get("positions", {})
        return symbol in positions and positions[symbol].get("balance", 0) > 0
    
    def get_position(self, engine_name: str, symbol: str) -> Optional[Dict]:
        """Get position details for a symbol."""
        engine = self.get_engine_state(engine_name)
        return engine.get("positions", {}).get(symbol)
    
    def get_all_positions(self, engine_name: str) -> Dict[str, Dict]:
        """Get all positions for an engine."""
        engine = self.get_engine_state(engine_name)
        return engine.get("positions", {})
    
    def get_stats(self, engine_name: str) -> Dict[str, Any]:
        """Get trading stats for an engine."""
        engine = self.get_engine_state(engine_name)
        return engine.get("stats", {})
    
    def get_total_value(self, engine_name: str, price_map: Dict[str, float]) -> float:
        """
        Calculate total portfolio value (cash + positions).
        
        Args:
            engine_name: Engine identifier
            price_map: {symbol: current_price} for valuation
        """
        engine = self.get_engine_state(engine_name)
        total = engine.get("cash_balance", 0.0)
        
        for symbol, pos in engine.get("positions", {}).items():
            price = price_map.get(symbol, 0.0)
            if price > 0:
                total += pos.get("balance", 0) * price
        
        # Update peak equity
        if total > engine.get("peak_equity", 0):
            self.state["engines"][engine_name]["peak_equity"] = total
            # Don't save on every call - let trade execution handle persistence
        
        return total
    
    # ═══════════════════════════════════════════════════════════════════════
    # PUBLIC API - Trade Execution
    # ═══════════════════════════════════════════════════════════════════════
    
    # V46.0: Dynamic Slippage Calculation Helper
    def _calculate_slippage(self, trade_size_usd: float, liquidity_usd: float, is_volatile: bool = False) -> Tuple[float, float]:
        """
        Calculate realistic slippage based on trade size, liquidity, and volatility.
        Returns (slippage_pct, slippage_cost_usd)
        """
        from config.settings import Settings
        
        # Guard against zero liquidity (div by zero)
        safe_liquidity = max(liquidity_usd, 1000.0)
        
        # 1. Base Slippage (Spread + Latency)
        base = Settings.SLIPPAGE_BASE_PCT
        
        # 2. Impact Slippage (Price Impact)
        impact = Settings.SLIPPAGE_IMPACT_MULTIPLIER * (trade_size_usd / safe_liquidity)
        
        # 3. Volatility Multiplier
        vol_mult = Settings.SLIPPAGE_VOLATILITY_MULTIPLIER if is_volatile else 1.0
        
        # Total
        total_slippage_pct = (base + impact) * vol_mult
        
        # Cap at reasonable max (e.g. 50%) to prevent arithmetic explosions
        total_slippage_pct = min(total_slippage_pct, 0.50)
        
        slippage_cost = trade_size_usd * total_slippage_pct
        return total_slippage_pct, slippage_cost

    def execute_buy(
        self, 
        engine_name: str, 
        symbol: str, 
        mint: str, 
        price: float, 
        size_usd: float,
        liquidity_usd: float = 100000.0,
        is_volatile: bool = False,
        dex_id: str = "JUPITER"  # V50.2: Tag position source (e.g. PUMPFUN, RAYDIUM)
    ) -> Tuple[bool, str]:
        """
        Execute a buy order with V46.0 Dynamic Slippage and DEX Tagging.
        """
        engine = self.get_engine_state(engine_name)
        if not engine:
            return False, f"Unknown engine: {engine_name}"
        
        cash = engine.get("cash_balance", 0)
        if cash < size_usd:
            return False, f"Insufficient funds: ${cash:.2f} < ${size_usd:.2f}"
        
        # Simulate gas (deduct SOL)
        sol_balance = engine.get("sol_balance", 0)
        if sol_balance < self.GAS_FEE_SOL:
            # Auto-buy gas from USD
            if not self._ensure_gas(engine_name):
                return False, "Insufficient SOL for gas"
        
        # Deduct gas
        self.state["engines"][engine_name]["sol_balance"] -= self.GAS_FEE_SOL
        
        # V46.0: Dynamic Slippage
        # Buy = price goes UP due to slippage
        slippage_pct, slippage_usd = self._calculate_slippage(size_usd, liquidity_usd, is_volatile)
        slipped_price = price * (1 + slippage_pct)
        
        # Calculate tokens received (fewer due to slippage)
        tokens_received = size_usd / slipped_price
        
        # Deduct cash
        self.state["engines"][engine_name]["cash_balance"] -= size_usd
        
        # Update or create position
        positions = self.state["engines"][engine_name]["positions"]
        if symbol in positions:
            # Average in
            existing = positions[symbol]
            total_value = (existing["balance"] * existing["avg_price"]) + size_usd
            new_balance = existing["balance"] + tokens_received
            positions[symbol]["avg_price"] = total_value / new_balance if new_balance > 0 else 0
            positions[symbol]["balance"] = new_balance
            # Keep existing dex_id or overwrite? Let's keep original to track "bag origin"
            positions[symbol]["dex_id"] = positions[symbol].get("dex_id", dex_id)
        else:
            positions[symbol] = {
                "balance": tokens_received,
                "avg_price": slipped_price,
                "entry_price": slipped_price,      # Dashboard field
                "current_price": slipped_price,    # Dashboard field
                "size_usd": size_usd,              # Dashboard field
                "current_value": tokens_received * slipped_price,  # Dashboard field
                "mint": mint,
                "entry_time": time.time(),
                "dex_id": dex_id  # Store source DEX
            }
        
        # Update stats
        gas_usd = self.GAS_FEE_SOL * 150  # Approximate SOL price
        self.state["engines"][engine_name]["stats"]["fees_paid_usd"] += gas_usd
        self.state["engines"][engine_name]["stats"]["slippage_usd"] += slippage_usd
        
        # Persist
        self._save_state()
        
        msg = f"BUY {symbol} [{dex_id}] (Liq: ${liquidity_usd:,.0f}): {tokens_received:.4f} @ ${slipped_price:.6f} (Slip: {slippage_pct*100:.2f}% / ${slippage_usd:.2f})"
        Logger.info(f"💰 [{engine_name}] {msg}")
        return True, msg
    
    def execute_sell(
        self, 
        engine_name: str, 
        symbol: str, 
        price: float,
        reason: str = "",
        liquidity_usd: float = 100000.0,
        is_volatile: bool = False
    ) -> Tuple[bool, str, float]:
        """
        Execute a sell order with V46.0 Dynamic Slippage.
        """
        engine = self.get_engine_state(engine_name)
        if not engine:
            return False, f"Unknown engine: {engine_name}", 0.0
        
        position = engine.get("positions", {}).get(symbol)
        if not position or position.get("balance", 0) <= 0:
            return False, f"No position in {symbol}", 0.0
        
        # Simulate gas
        if engine.get("sol_balance", 0) < self.GAS_FEE_SOL:
            self._ensure_gas(engine_name)
        self.state["engines"][engine_name]["sol_balance"] -= self.GAS_FEE_SOL
        
        # Calculate Trade Value for impact
        balance = position["balance"]
        est_value = balance * price
        
        # V46.0: Dynamic Slippage (Sell = Price Lower)
        slippage_pct, slippage_usd = self._calculate_slippage(est_value, liquidity_usd, is_volatile)
        slipped_price = price * (1 - slippage_pct) # Sell low
        
        # Calculate proceeds
        avg_price = position["avg_price"]
        sale_value = balance * slipped_price
        cost_basis = balance * avg_price
        pnl = sale_value - cost_basis
        pnl_pct = (pnl / cost_basis * 100) if cost_basis > 0 else 0
        
        # Update cash
        self.state["engines"][engine_name]["cash_balance"] += sale_value
        
        # Update stats
        gas_usd = self.GAS_FEE_SOL * 150
        stats = self.state["engines"][engine_name]["stats"]
        stats["fees_paid_usd"] += gas_usd
        stats["slippage_usd"] += slippage_usd
        stats["total_pnl_usd"] += pnl
        if pnl > 0:
            stats["wins"] += 1
        else:
            stats["losses"] += 1
        
        # V46.1: Log trade with execution data for ML feedback loop
        from src.shared.system.db_manager import db_manager
        trade_record = {
            'symbol': symbol,
            'entry_price': avg_price,
            'exit_price': slipped_price,
            'size_usd': sale_value,
            'pnl_usd': pnl,
            'net_pnl_pct': pnl_pct / 100,  # Convert from % to decimal
            'exit_reason': reason,
            'timestamp': time.time(),
            'is_win': pnl > 0,
            'engine_name': engine_name,
            # V46.1: Execution data for ML
            'slippage_pct': slippage_pct,
            'slippage_usd': slippage_usd,
            'fees_usd': gas_usd,
            'liquidity_usd': liquidity_usd,
            'is_volatile': is_volatile
        }
        try:
            db_manager.log_trade(trade_record)
        except Exception as e:
            Logger.warning(f"[CAPITAL] Failed to log trade: {e}")
        
        # Remove position
        del self.state["engines"][engine_name]["positions"][symbol]
        
        # Persist
        self._save_state()
        
        emoji = "✅" if pnl > 0 else "❌"
        msg = f"SELL {symbol}: {emoji} ${pnl:.2f} ({pnl_pct:.2f}%) | Price: ${slipped_price:.6f} (Slip: {slippage_pct*100:.2f}%) | {reason}"
        Logger.info(f"💰 [{engine_name}] {msg}")
        
        return True, msg, pnl
    
    def _ensure_gas(self, engine_name: str, min_sol: float = 0.02) -> bool:
        """Auto-buy SOL from USD when gas is low."""
        engine = self.get_engine_state(engine_name)
        sol_balance = engine.get("sol_balance", 0)
        
        if sol_balance >= min_sol:
            return True
        
        # Buy $1 worth of SOL
        cost_usd = 1.0
        cash = engine.get("cash_balance", 0)
        
        if cash < cost_usd:
            return False
        
        sol_price = 150.0  # Could fetch from cache, using approximation
        sol_to_buy = cost_usd / sol_price
        
        self.state["engines"][engine_name]["cash_balance"] -= cost_usd
        self.state["engines"][engine_name]["sol_balance"] += sol_to_buy
        self.state["engines"][engine_name]["stats"]["fees_paid_usd"] += cost_usd * 0.01
        
        Logger.debug(f"[{engine_name}] ⛽ Gas refill: +{sol_to_buy:.4f} SOL")
        return True
    
    # ═══════════════════════════════════════════════════════════════════════
    # RISK MANAGEMENT (V28.0 Pattern)
    # ═══════════════════════════════════════════════════════════════════════
    
    def check_drawdown(self, engine_name: str, current_equity: float) -> Tuple[bool, str]:
        """
        Check if drawdown limits are breached.
        
        Args:
            engine_name: Engine to check
            current_equity: Current portfolio value
            
        Returns:
            (is_breached, reason) tuple
        """
        from config.settings import Settings
        
        engine = self.get_engine_state(engine_name)
        peak = engine.get("peak_equity", current_equity)
        daily_start = engine.get("daily_start_equity", current_equity)
        
        # Max drawdown check
        if peak > 0:
            dd_pct = (peak - current_equity) / peak
            max_dd = getattr(Settings, 'MAX_DRAWDOWN_PER_STRATEGY_PCT', 0.15)
            if dd_pct >= max_dd:
                return True, f"MAX DD: -{dd_pct*100:.2f}% (Limit: {max_dd*100:.1f}%)"
        
        # Daily drawdown check
        if daily_start > 0:
            daily_dd_pct = (daily_start - current_equity) / daily_start
            daily_limit = getattr(Settings, 'DAILY_DRAWDOWN_LIMIT_PCT', 0.05)
            if daily_dd_pct >= daily_limit:
                return True, f"DAILY DD: -{daily_dd_pct*100:.2f}% (Limit: {daily_limit*100:.1f}%)"
        
        return False, ""
    
    def reset_daily_equity(self) -> None:
        """Reset daily start equity for all engines (call at midnight)."""
        for engine_name in self.ENGINE_NAMES:
            if engine_name in self.state.get("engines", {}):
                cash = self.state["engines"][engine_name].get("cash_balance", 0)
                self.state["engines"][engine_name]["daily_start_equity"] = cash
        self._save_state()
    
    # ═══════════════════════════════════════════════════════════════════════
    # UTILITY
    # ═══════════════════════════════════════════════════════════════════════
    
    def __repr__(self) -> str:
        total = self.state.get("total_capital_usd", 0)
        engines = len(self.state.get("engines", {}))
        return f"<CapitalManager ${total:.2f} across {engines} engines ({self.mode})>"
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all engine states for reporting."""
        summary = {
            "total_capital": self.state.get("total_capital_usd", 0),
            "engines": {}
        }
        
        for name, engine in self.state.get("engines", {}).items():
            summary["engines"][name] = {
                "cash": engine.get("cash_balance", 0),
                "positions": len(engine.get("positions", {})),
                "pnl": engine.get("stats", {}).get("total_pnl_usd", 0),
                "wins": engine.get("stats", {}).get("wins", 0),
                "losses": engine.get("stats", {}).get("losses", 0)
            }
        
        return summary
    
    # ═══════════════════════════════════════════════════════════════════════
    # V48.1: REALISM INITIALIZATION
    # ═══════════════════════════════════════════════════════════════════════
    
    def seed_from_real_wallet(self, total_usdc: float, total_sol: float) -> None:
        """
        Overwrite initial state with Real Wallet balances (First Run Only).
        Called by DataBroker on startup if Settings.CLONE_WALLET_ON_FIRST_RUN is True.
        """
        # Scan engines to see if they look "default" (un-traded)
        # Or check explicit flag.
        if self.state.get("is_seeded", False):
            # Only log debug if needed, otherwise silent
            return 
            
        engines = self.state.get("engines", {})
        if not engines:
            return

        # Split capital across engines
        num_engines = len(engines)
        cash_per_engine = total_usdc / num_engines
        
        # Keep minimal SOL if real wallet is empty? No, clone exact.
        sol_per_engine = total_sol / num_engines
        
        for name in engines:
            self.state["engines"][name]["cash_balance"] = cash_per_engine
            self.state["engines"][name]["allocated_capital"] = cash_per_engine
            self.state["engines"][name]["sol_balance"] = sol_per_engine
            
            # Reset Stats to reflect clean slate
            self.state["engines"][name]["stats"] = {
                "wins": 0, "losses": 0, "total_pnl_usd": 0.0,
                "win_rate": 0.0, "profit_factor": 0.0, "total_volume_usd": 0.0
            }
            
            Logger.success(f"🌱 [{name}] CLONED REAL WALLET: ${cash_per_engine:.2f} | {sol_per_engine:.4f} SOL")

        self.state["is_seeded"] = True
        self._save_state()

    # ═══════════════════════════════════════════════════════════════════════
    # JLP STATE (V45.0 Lazy Landlord)
    # ═══════════════════════════════════════════════════════════════════════
    
    def get_jlp_state(self) -> Dict[str, Any]:
        """Get JLP investment state."""
        return self.state.get("jlp_state", {
            "entry_price": 0.0,
            "quantity": 0.0,
            "initial_value_usd": 0.0,
            "updated_at": None
        })
    
    def update_jlp_state(self, entry_price: float, quantity: float) -> Dict[str, Any]:
        """
        Update JLP investment state after user buys JLP.
        
        Args:
            entry_price: Price per JLP at time of purchase
            quantity: Number of JLP tokens purchased
            
        Returns:
            Updated JLP state dict
        """
        self.state["jlp_state"] = {
            "entry_price": entry_price,
            "quantity": quantity,
            "initial_value_usd": entry_price * quantity,
            "updated_at": time.time()
        }
        self._save_state()
        Logger.info(f"[CAPITAL] 🏠 JLP State Updated: {quantity:.4f} JLP @ ${entry_price:.4f}")
        return self.state["jlp_state"]
    
    def clear_jlp_state(self) -> None:
        """Clear JLP state (after selling)."""
        self.state["jlp_state"] = {
            "entry_price": 0.0,
            "quantity": 0.0,
            "initial_value_usd": 0.0,
            "updated_at": None
        }
        self._save_state()
        Logger.info("[CAPITAL] 🏠 JLP State Cleared")

    # ═══════════════════════════════════════════════════════════════════════
    # V47.3 & V47.5: RESILIENCE & MAINTENANCE (MICRO-ACCOUNT TUNED)
    # ═══════════════════════════════════════════════════════════════════════
    
    def perform_maintenance(self, engine_name: str) -> None:
        """
        Perform periodic maintenance checks (Bankruptcy, Gas Sweep, Zombie Bags).
        Call this periodically (e.g. hourly).
        """
        self._sweep_excess_gas(engine_name)  # Get cash first
        self._check_bankruptcy(engine_name)  # Then check solvency
        self._sweep_zombie_bags(engine_name)


    def _sweep_zombie_bags(self, engine_name: str) -> None:
        """
        V47.6: Force-sell positions held longer than MAX_HOLD_TIME_MINUTES.
        
        This is the runtime failsafe that catches any position that:
        - Lost watcher sync due to threading issues
        - Has a strategy bug preventing exit
        - Simply held too long (scalping mode)
        
        Returns list of symbols that were force-sold.
        """
        from config.settings import Settings
        
        engine = self.get_engine_state(engine_name)
        if not engine:
            return
        
        positions = engine.get("positions", {})
        if not positions:
            return
        
        max_hold_seconds = getattr(Settings, 'MAX_HOLD_TIME_MINUTES', 15) * 60
        current_time = time.time()
        zombies_found = []
        
        for symbol, pos_data in list(positions.items()):
            balance = pos_data.get('balance', 0)
            if balance <= 0:
                continue
                
            entry_time = pos_data.get('entry_time', 0)
            if entry_time == 0:
                # No entry time recorded - use a default (assume old position)
                entry_time = current_time - (max_hold_seconds + 60)  # Treat as expired
            
            hold_duration = current_time - entry_time
            
            if hold_duration > max_hold_seconds:
                zombies_found.append({
                    'symbol': symbol,
                    'balance': balance,
                    'entry_time': entry_time,
                    'hold_mins': hold_duration / 60
                })
        
        # Force-sell zombies
        for zombie in zombies_found:
            symbol = zombie['symbol']
            hold_mins = zombie['hold_mins']
            
            # Get approximate current price (we don't have live price here, use avg as estimate)
            pos = positions.get(symbol, {})
            avg_price = pos.get('avg_price', 0.0)
            
            if avg_price <= 0:
                Logger.warning(f"[V47.6] Cannot sell zombie {symbol}: No price data")
                continue
            
            # Execute force-sell at estimated price
            reason = f"ZOMBIE SWEEP: Max Hold Time Exceeded ({hold_mins:.0f}m > {max_hold_seconds/60:.0f}m)"
            
            success, msg, pnl = self.execute_sell(
                engine_name=engine_name,
                symbol=symbol,
                price=avg_price,  # Sell at entry price (worst case, breakeven minus fees)
                reason=reason,
                liquidity_usd=50000.0,  # Assume moderate liquidity
                is_volatile=True  # High slippage for zombie sells
            )
            
            if success:
                Logger.warning(f"[V47.6] [{engine_name}] ZOMBIE SOLD: {symbol} (Held {hold_mins:.0f}m) - PnL: ${pnl:.2f}")
            else:
                Logger.error(f"[V47.6] [{engine_name}] Zombie sell failed for {symbol}: {msg}")

    def _check_bankruptcy(self, engine_name: str) -> None:
        """
        Auto-reset checks for stuck/bankrupt engines.
        V47.5 Tuning: Aggressive reset for Micro-Accounts (<$25)
        """
        engine = self.get_engine_state(engine_name)
        if not engine:
            return

        cash = engine.get("cash_balance", 0.0)
        positions = engine.get("positions", {})
        
        # Calculate TRUE equity (Assets - Liabilities) instead of PnL history
        # PnL history ignores fees, which is the main killer in scalp strategies
        sol_value = engine.get("sol_balance", 0.0) * 150.0 # Approx val
        start_cap = engine.get("allocated_capital", self.default_capital)
        
        # Estimate position value (Optimistic: use entry price if live price unknown)
        # In CapitalManager we often lack live prices, so we assume held bags are worth cost execution
        # If they are down 90%, this is wrong, but typically we want to check CASH insolvency first.
        pos_value = 0.0
        for p in positions.values():
            pos_value += p.get("balance", 0.0) * p.get("avg_price", 0.0)
            
        current_equity_est = cash + sol_value + pos_value
        
        # V47.5 Rules (Micro-Account Fidelity):
        # 1. Insolvency: Cash < $5 AND Total Equity < $10 (Dead wallet)
        # 2. Capital Destruction: Equity < Threshold (Failed run) - Configurable (Default 50%, V48.0 Tuned to 75%)
        from config.settings import Settings
        max_dd_pct = getattr(Settings, 'MAX_CAPITAL_DRAWDOWN_PCT', 0.50)
        min_equity_threshold = start_cap * (1.0 - max_dd_pct)
        
        # Log status for debugging
        if cash < 10.0:
            Logger.info(f"🔍 [{engine_name}] Low Cash Check: Cash=${cash:.2f} Eq=${current_equity_est:.2f} Start=${start_cap:.0f} (Cutoff: ${min_equity_threshold:.2f})")
        
        # V48.2: Micro-Account Tuning
        # Lowered thresholds to prevent instant-death for split wallets (e.g. $19 / 4 = $4.83)
        is_insolvent = (cash < 1.0) and (current_equity_est < 2.0)
        is_destroyed = (current_equity_est < min_equity_threshold)
        
        if is_insolvent:
            Logger.warning(f"💀 [{engine_name}] BANKRUPTCY (Insolvent): Cash ${cash:.2f} / Eq ~${current_equity_est:.2f}. Resetting...")
            self._reset_engine(engine_name)
        elif is_destroyed:
             Logger.warning(f"📉 [{engine_name}] BANKRUPTCY (Destruction): Equity ~${current_equity_est:.2f} (< {100-max_dd_pct*100:.0f}% of ${start_cap}). Resetting...")
             self._reset_engine(engine_name)


    def _reset_engine(self, engine_name: str) -> None:
        """
        Reset an engine to initial state with VARIABLE CAPITAL.
        
        V47.4 Feature: "Training Scenarios"
        V47.5 Update: Added $25 "Micro-Account" Mode for realism.
        
        Scenarios:
        - $25:   Realism Mode (Exact user conditions) - High difficulty
        - $100:  Hard Mode (High Fee Impact) - Efficiency training
        - $1,000: Standard Mode - Baseline
        - $5,000: Whale Mode (Low Fee Impact) - Strategy training
        """
        # Define Scenarios
        SCENARIOS = [25.0,  100.0, 1000.0, 5000.0]
        weights   = [0.2,   0.2,   0.4,    0.2]   
        
        # Select Scenario
        start_cap = random.choices(SCENARIOS, weights=weights, k=1)[0]
        
        self.state["engines"][engine_name] = self._create_engine_state(engine_name, start_cap)
        self._save_state()
        
        # Log with appropriate emoji for difficulty
        if start_cap <= 25:
            difficulty = "REALISM (EXTREME)"
        elif start_cap <= 100:
            difficulty = "HARD"
        elif start_cap <= 1000:
            difficulty = "STANDARD"
        else:
            difficulty = "EASY"
            
        Logger.success(f"♻️ [{engine_name}] FACTORY RESET Complete.")
        Logger.info(f"   🎲 Scenario: ${start_cap:,.0f} ({difficulty} Mode) - Training for diverse conditions.")

    def _sweep_excess_gas(self, engine_name: str) -> None:
        """
        Swap excess SOL gas back to USDC if Cash is low.
        V47.5 Tuning: Aggressive Sweep for Micro-Accounts.
        
        Trigger: SOL > ~0.1 ($13)
        Target: Keep 0.015 SOL (~$2 for fees), sell the rest.
        """
        engine = self.get_engine_state(engine_name)
        sol = engine.get("sol_balance", 0.0)
        cash = engine.get("cash_balance", 0.0)
        
        # Thresholds (Tuned for $25 account)
        SOL_HIGH = 0.1        # ~ $15.00
        SOL_TARGET = 0.015    # ~ $2.25
        
        # V48.0: Emergency Liquidity Override
        # If Cash is critical (< $10), enable aggressive sweeping
        if cash < 10.0:
            SOL_HIGH = 0.03   # Trigger at ~$4.50
            if sol > SOL_HIGH:
                 Logger.info(f"🚨 [{engine_name}] EMERGENCY GAS SWEEP triggered (Cash ${cash:.2f} < $10.00)")
        
        if sol > SOL_HIGH:
            excess_sol = sol - SOL_TARGET
            
            # Simulate Swap
            sol_price_est = 150.0 # Approximation
            usdc_value = excess_sol * sol_price_est
            
            self.state["engines"][engine_name]["sol_balance"] -= excess_sol
            self.state["engines"][engine_name]["cash_balance"] += usdc_value
            
            self._save_state()
            Logger.info(f"🧹 [{engine_name}] GAS SWEEP: Converted {excess_sol:.4f} SOL -> ${usdc_value:.2f} USDC")


# Module-level instance getter
def get_capital_manager() -> CapitalManager:
    """Get or create the singleton CapitalManager instance."""
    return CapitalManager()

