"""
V37.0: Base Strategy Class
==========================
Abstract base class providing shared trading logic for all strategies.
Child classes implement only their unique signal generation logic.
"""

from abc import ABC, abstractmethod
import time
from config.settings import Settings
from src.strategy.watcher import Watcher
from src.strategy.risk import PositionSizer, TrailingStopManager
from src.strategy.metrics import Metrics
from src.shared.system.priority_queue import priority_queue
from src.shared.system.logging import Logger


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    
    Provides shared functionality:
    - Signal cooldown management
    - Position sizing (V27.0 Risk %)
    - Trailing Stop Loss updates
    - Hard Stop Loss checks
    - Portfolio integration
    
    Child classes MUST implement:
    - analyze_tick(watcher, price) -> (action, reason, size)
    """
    
    # Shared Constants
    SIGNAL_COOLDOWN_SECONDS = 30
    
    def __init__(self, portfolio):
        """Initialize with portfolio reference for risk checks."""
        self.portfolio = portfolio
        self.market_mode = "NORMAL"
        self.win_rate = 0.5
        self.last_mode_update = 0
        
    # ═══════════════════════════════════════════════════════════════════
    # ABSTRACT METHOD (Child Must Implement)
    # ═══════════════════════════════════════════════════════════════════
    
    @abstractmethod
    def analyze_tick(self, watcher: Watcher, price: float) -> tuple:
        """
        Analyze current market state and return trading decision.
        
        Args:
            watcher: Asset state container with price/indicator data.
            price: Current market price.
            
        Returns:
            tuple: (action, reason, size_usd)
                action: 'BUY', 'SELL', or 'HOLD'
                reason: Human-readable explanation
                size_usd: Position size for BUY orders
        """
        pass
    
    # ═══════════════════════════════════════════════════════════════════
    # SHARED METHODS (Inherited by All Strategies)
    # ═══════════════════════════════════════════════════════════════════
    
    def check_cooldown(self, watcher: Watcher) -> bool:
        """
        Check if signal cooldown period has passed.
        
        Returns:
            True if cooldown is active (should skip signal generation).
            False if cooldown has expired (can generate new signal).
        """
        if hasattr(watcher, 'last_signal_time'):
            cooldown = getattr(watcher, 'SIGNAL_COOLDOWN', self.SIGNAL_COOLDOWN_SECONDS)
            if time.time() - watcher.last_signal_time < cooldown:
                return True
        return False
    
    def set_signal_cooldown(self, watcher: Watcher):
        """Mark signal emission time for cooldown tracking."""
        watcher.last_signal_time = time.time()
    
    def calculate_position_size(self, atr: float = 0.0) -> float:
        """
        Calculate position size based on V27.0 Fixed Risk % logic.
        
        Args:
            atr: Average True Range for volatility-adjusted sizing.
            
        Returns:
            Position size in USD, respecting portfolio limits.
        """
        # Base size from settings
        base_size = Settings.POSITION_SIZE_USD
        
        # Cap at available cash
        available = self.portfolio.cash_available if hasattr(self.portfolio, 'cash_available') else base_size
        size = min(base_size, available)
        
        # Minimum viable trade
        if size < 5.0:
            return 0.0
            
        return size
    
    def update_trailing_stop(self, watcher: Watcher, price: float) -> tuple:
        """
        Update Trailing Stop Loss state.
        
        Returns:
            tuple: (triggered, reason)
                triggered: True if TSL was hit.
                reason: Exit reason string.
        """
        state = {
            'in_position': watcher.in_position,
            'entry_price': watcher.entry_price,
            'max_price_achieved': watcher.max_price_achieved,
            'trailing_stop_price': watcher.trailing_stop_price
        }
        
        new_state, triggered, reason = TrailingStopManager.update_tsl(price, state)
        
        # Update watcher state
        if new_state['max_price_achieved'] > watcher.max_price_achieved:
            watcher.max_price_achieved = new_state['max_price_achieved']
        if new_state['trailing_stop_price'] > watcher.trailing_stop_price:
            watcher.trailing_stop_price = new_state['trailing_stop_price']
            
        return triggered, reason
    
    def check_hard_stop_loss(self, watcher: Watcher, price: float) -> tuple:
        """
        Check if hard stop loss has been hit.
        
        Returns:
            tuple: (triggered, reason)
                triggered: True if SL was hit.
                reason: Exit reason string.
        """
        pnl_pct = Metrics.calculate_pnl_pct(watcher.entry_price, price)
        
        if pnl_pct <= Settings.STOP_LOSS_PCT:
            return True, f"🛑 STOP-LOSS ({pnl_pct*100:.2f}%)"
            
        return False, ""
    
    def get_net_pnl_reason(self, watcher: Watcher, price: float, base_reason: str) -> str:
        """Calculate net PnL and append to reason string."""
        net_pnl = Metrics.calculate_net_pnl_pct(watcher.entry_price, price, watcher.cost_basis) * 100
        return f"{base_reason} (Net: {net_pnl:.1f}%)"
    
    def log_signal(self, symbol: str, signal_type: str, reason: str = ""):
        """Log a signal for debugging/monitoring."""
        emoji = "📈" if signal_type == "BUY" else "📉" if signal_type == "SELL" else "⏸️"
        msg = f"[{self.__class__.__name__}] {emoji} {signal_type} Signal: {symbol}"
        if reason:
            msg += f" | {reason}"
        priority_queue.add(3, 'LOG', {'level': 'INFO', 'message': msg})
    
    def update_market_mode(self):
        """
        Update strategy mode based on win rate (V11.0 DSA).
        Override in child class for custom logic.
        """
        if time.time() - self.last_mode_update < 300:
            return
            
        from src.shared.system.db_manager import db_manager
        self.win_rate = db_manager.get_win_rate(limit=20)
        self.last_mode_update = time.time()
    
    # ═══════════════════════════════════════════════════════════════════
    # SHARED EXIT LOGIC (V37.0 Step 2)
    # ═══════════════════════════════════════════════════════════════════
    
    def check_take_profit(self, watcher: Watcher, price: float) -> tuple:
        """
        Check if take profit has been hit (Static TP, only if TSL disabled).
        
        Returns:
            tuple: (triggered, reason)
        """
        pnl_pct = Metrics.calculate_pnl_pct(watcher.entry_price, price)
        
        # Only apply static TP if TSL is disabled
        if not Settings.TSL_ENABLED and pnl_pct >= Settings.TAKE_PROFIT_PCT:
            return True, f"💰 TAKE PROFIT (+{pnl_pct*100:.2f}%)"
            
        return False, ""
    
    def _evaluate_exit_common(self, watcher: Watcher, price: float) -> tuple:
        """
        Common exit evaluation logic (TSL, SL, TP).
        
        This method performs risk-based exits that are universal across strategies.
        Strategy-specific exits (e.g., RSI-based) should be handled by child classes.
        
        Returns:
            tuple: (action, reason, size)
                action: 'SELL' if exit triggered, 'HOLD' otherwise
                reason: Exit reason if triggered
                size: Always 0.0 for sells
        """
        # A. Trailing Stop Loss
        tsl_triggered, tsl_reason = self.update_trailing_stop(watcher, price)
        if tsl_triggered:
            return 'SELL', self.get_net_pnl_reason(watcher, price, tsl_reason), 0.0
        
        # B. Hard Stop Loss
        sl_triggered, sl_reason = self.check_hard_stop_loss(watcher, price)
        if sl_triggered:
            return 'SELL', sl_reason, 0.0
        
        # C. Static Take Profit (if TSL disabled)
        tp_triggered, tp_reason = self.check_take_profit(watcher, price)
        if tp_triggered:
            return 'SELL', tp_reason, 0.0
        
        # No common exit triggered
        return 'HOLD', '', 0.0
    
    def validate_entry_common(self, watcher: Watcher, price: float) -> tuple:
        """
        Common entry validation checks.
        
        Returns:
            tuple: (is_valid, rejection_reason)
        """
        # Price threshold
        if price < Settings.MIN_PRICE_THRESHOLD:
            return False, "Price below threshold"
        
        # Warmup check
        if watcher.get_price_count() < 30:
            return False, "Insufficient price data"
        
        return True, ""
