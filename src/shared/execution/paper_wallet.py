"""
V16.0: Paper Wallet Simulation (Adapter)
========================================
V45.0: Now acts as an ADAPTER for the centralized CapitalManager.
This ensures TradingCore can access engine-specific state without refactoring 
internal logic, while CapitalManager maintains the single source of truth.
"""

from dataclasses import dataclass
from typing import Dict, Any
from src.shared.system.logging import Logger
from src.shared.system.capital_manager import get_capital_manager

@dataclass
class PaperAsset:
    symbol: str
    mint: str
    balance: float
    avg_price: float = 0.0

class PaperWallet:
    """V45.0: Adapter Class linking TradingCore to CapitalManager."""
    
    def __init__(self, engine_name: str = "PRIMARY"):
        self.engine_name = engine_name
        self.cm = get_capital_manager()
        self.initialized = True
        
        # V45.5: Auto-register engine if missing (Dynamic Engines support)
        # V45.5: Auto-register engine if missing (Dynamic Engines support)
        if hasattr(self.cm, 'state') and engine_name not in self.cm.state.get("engines", {}):
            # Use private method or recreate logic since _add_engine might be private/internal
            # But python allows access.
            self.cm._add_engine(engine_name)
        
    @property
    def initial_capital(self) -> float:
        """Delegate to CapitalManager allocated_capital."""
        if engine := self.cm.state.get("engines", {}).get(self.engine_name):
            return engine.get("allocated_capital", 0.0)
        return 0.0
        
    @property
    def cash_balance(self) -> float:
        """Delegate to CapitalManager."""
        return self.cm.get_available_cash(self.engine_name)

    @cash_balance.setter
    def cash_balance(self, value):
        """ReadOnly mostly, but allow simple sets if legacy logic requires."""
        # Directly overriding CapitalManager state is risky, but we'll try to find keys
        if engine := self.cm.state.get("engines", {}).get(self.engine_name):
            engine["cash_balance"] = value

    @property
    def sol_balance(self) -> float:
        return self.cm.get_sol_balance(self.engine_name)
        
    @sol_balance.setter
    def sol_balance(self, value):
        if engine := self.cm.state.get("engines", {}).get(self.engine_name):
            engine["sol_balance"] = value

    @property
    def assets(self) -> Dict[str, PaperAsset]:
        """Construct PaperAssets from CapitalManager state on-the-fly."""
        raw_positions = self.cm.get_all_positions(self.engine_name)
        assets = {}
        for s, data in raw_positions.items():
            if data['balance'] > 0:
                assets[s] = PaperAsset(
                    symbol=s,
                    mint=data.get('mint', ''),
                    balance=data['balance'],
                    avg_price=data.get('avg_price', 0.0)
                )
        return assets
        
    @property
    def stats(self) -> Dict[str, Any]:
        return self.cm.get_stats(self.engine_name)

    def init_from_real(self, real_usdc: float, real_sol: float):
        """Update CapitalManager state with initial funds."""
        # V45.6: Always reset state on init for Paper Trading (simulating fresh run)
        if engine := self.cm.state.get("engines", {}).get(self.engine_name):
            # Update Cash
            engine["cash_balance"] = real_usdc
            engine["allocated_capital"] = real_usdc # Reset allocation
            
            # Update SOL for Gas
            engine["sol_balance"] = real_sol
            
            # Reset Stats
            engine["daily_start_equity"] = real_usdc
            engine["peak_equity"] = real_usdc
            engine["stats"] = {
                "fees_paid_usd": 0.0,
                "slippage_usd": 0.0,
                "total_pnl_usd": 0.0,
                "wins": 0,
                "losses": 0
            }
            
            # V45.6: Clear positions to avoid "holding bags" from previous runs
            engine["positions"] = {}
            
            self.cm._save_state()
            Logger.info(f"💼 [PAPER:{self.engine_name}] State Reset: ${real_usdc:.2f} USDC | {real_sol:.3f} SOL | Positions Cleared")
    
    def ensure_gas(self, min_sol: float = 0.02):
        """Delegate to CapitalManager internal helper."""
        # Using private method access for adapter pattern efficiency
        return self.cm._ensure_gas(self.engine_name, min_sol)

    def get_total_value(self, price_map: Dict[str, float]) -> float:
        return self.cm.get_total_value(self.engine_name, price_map)

    def get_detailed_balance(self, price_map: Dict[str, float]) -> dict:
        """Match legacy API return format."""
        
        cash = self.cash_balance
        sol_price = price_map.get('SOL', price_map.get('SOL-USD', 150.0))
        gas_val = self.sol_balance * sol_price
        
        # Calculate assets value
        asset_val = 0.0
        current_assets = self.assets # Get adapter objects
        for s, a in current_assets.items():
            price = price_map.get(s, 0.0)
            if price > 0:
                asset_val += a.balance * price
                
        return {
            'cash': cash,
            'gas_usd': gas_val,
            'assets_usd': asset_val,
            'total_equity': cash + asset_val + gas_val,
            'asset_count': len(current_assets)
        }

    def check_drawdown_status(self, current_equity: float) -> tuple:
        return self.cm.check_drawdown(self.engine_name, current_equity)

    def simulate_buy(
        self, 
        symbol: str, 
        mint: str, 
        price: float, 
        size_usd: float, 
        liquidity_usd: float = 100000.0,
        is_volatile: bool = False
    ) -> bool:
        """Delegate execution to CapitalManager."""
        success, msg = self.cm.execute_buy(
            self.engine_name, 
            symbol, 
            mint, 
            price, 
            size_usd,
            liquidity_usd=liquidity_usd,
            is_volatile=is_volatile
        )
        if not success:
            Logger.warning(f"⚠️ [PAPER] Buy Failed: {msg}")
        return success

    def simulate_sell(
        self, 
        symbol: str, 
        price: float, 
        reason: str, 
        liquidity_usd: float = 100000.0, 
        is_volatile: bool = False
    ):
        """Delegate execution to CapitalManager."""
        success, msg, pnl = self.cm.execute_sell(
            self.engine_name, 
            symbol, 
            price, 
            reason,
            liquidity_usd=liquidity_usd,
            is_volatile=is_volatile
        )
        return pnl # Legacy expects PnL return
