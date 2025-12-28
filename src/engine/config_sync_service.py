"""
V133: ConfigSyncService - Extracted from TradingCore (SRP Refactor)
===================================================================
Handles synchronization of global configuration state.

Responsibilities:
- Sync trading mode (LIVE vs MONITOR)
- Sync position size settings
- Sync budget/exposure limits
"""

from typing import Any, Optional
from config.settings import Settings
from src.shared.system.priority_queue import priority_queue
from src.core.global_state import GlobalState


class ConfigSyncService:
    """
    V133: Synchronizes global configuration state with local settings.
    
    This component was extracted from TradingCore to follow SRP.
    It reads from GlobalState and updates Settings accordingly.
    """
    
    def __init__(self, engine_name: str, portfolio: Any = None):
        """
        Initialize ConfigSyncService.
        
        Args:
            engine_name: Identifier for live engine targeting
            portfolio: PortfolioManager for budget updates (optional)
        """
        self.engine_name = engine_name
        self.portfolio = portfolio
    
    def sync(self) -> dict:
        """
        Sync all global state to local settings.
        
        Returns:
            Dict of what was synced and new values
        """
        state = GlobalState.read_state()
        synced = {}
        
        # 1. Sync Mode
        mode_changed = self._sync_mode(state)
        if mode_changed:
            synced['mode'] = Settings.ENABLE_TRADING
        
        # 2. Sync Position Size
        size_changed = self._sync_position_size(state)
        if size_changed:
            synced['position_size'] = Settings.POSITION_SIZE_USD
        
        # 3. Sync Budget
        budget_changed = self._sync_budget(state)
        if budget_changed:
            synced['max_exposure'] = getattr(Settings, 'MAX_TOTAL_EXPOSURE_USD', 0)
        
        return synced
    
    def _sync_mode(self, state: dict) -> bool:
        """
        V39.9: Sync trading mode with LIVE_ENGINE_TARGET check.
        
        Only enables live trading if this engine is the targeted engine.
        """
        global_mode = state.get("MODE", "MONITOR")
        live_target = state.get("LIVE_ENGINE_TARGET", None)
        
        # V39.9: Only enable live trading if I'm the targeted engine
        if global_mode == "LIVE" and live_target:
            should_be_live = (live_target == self.engine_name)
        else:
            should_be_live = False  # MONITOR mode or no target = paper trading
        
        if Settings.ENABLE_TRADING != should_be_live:
            Settings.ENABLE_TRADING = should_be_live
            if should_be_live:
                mode_str = f"🔴 LIVE (Target: {live_target})"
            else:
                mode_str = "🟢 MONITOR"
            priority_queue.add(3, 'LOG', {
                'level': 'WARNING', 
                'message': f"🔄 SYNC: {mode_str}"
            })
            return True
        
        return False
    
    def _sync_position_size(self, state: dict) -> bool:
        """Sync base position size from global state."""
        global_size = state.get("BASE_SIZE_USD", 50.0)
        
        if Settings.POSITION_SIZE_USD != global_size:
            Settings.POSITION_SIZE_USD = global_size
            priority_queue.add(4, 'LOG', {
                'level': 'INFO', 
                'message': f"🔄 SYNC: Size -> ${global_size}"
            })
            return True
        
        return False
    
    def _sync_budget(self, state: dict) -> bool:
        """Sync max exposure/budget from global state."""
        global_budget = state.get("MAX_EXPOSURE_USD", 1000.0)
        
        if getattr(Settings, 'MAX_TOTAL_EXPOSURE_USD', 0) != global_budget:
            Settings.MAX_TOTAL_EXPOSURE_USD = global_budget
            if self.portfolio:
                self.portfolio.set_max_exposure(global_budget)
            return True
        
        return False
