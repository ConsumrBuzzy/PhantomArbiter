"""
V17.0: Longtail Strategy Logic (MACD Crossover)
================================================
Trend-following strategy for longer-term trades.
Uses MACD (12/26/9) crossovers for entry signals.
"""

from config.settings import Settings
import time
from src.strategy.watcher import Watcher
from src.shared.system.priority_queue import priority_queue
from src.strategy.risk import PositionSizer, TrailingStopManager
from src.strategy.metrics import Metrics
from src.shared.system.logging import Logger


class LongtailLogic:
    """
    V17.0 Logic Engine for Longtail Trend Strategy.
    
    Uses MACD (Moving Average Convergence Divergence) crossovers
    to identify sustained trend shifts on slower timeframes.
    
    MACD Parameters: 12/26/9 (Standard)
    - Fast EMA: 12 periods
    - Slow EMA: 26 periods  
    - Signal Line: 9-period EMA of MACD
    """
    
    def __init__(self, portfolio):
        self.portfolio = portfolio
        self.market_mode = "LONGTAIL"
        self.win_rate = 0.5
        self.last_mode_update = 0
        
        # MACD State Cache (per symbol)
        self._macd_cache = {}
        
    def update_market_mode(self):
        """Longtail uses fixed mode - no dynamic adjustment."""
        import time
        if time.time() - self.last_mode_update < 300:
            return
            
        from src.shared.system.db_manager import db_manager
        self.win_rate = db_manager.get_win_rate(limit=20)
        self.last_mode_update = time.time()
        Logger.info(f"🔭 Longtail Mode: MACD 12/26/9 (Win Rate: {self.win_rate*100:.1f}%)")

    def _calculate_ema(self, prices: list, period: int) -> float:
        """Calculate Exponential Moving Average."""
        if len(prices) < period:
            return 0.0
            
        k = 2 / (period + 1)
        ema = prices[0]
        
        for price in prices[1:]:
            ema = (price * k) + (ema * (1 - k))
            
        return ema
    
    def _calculate_macd(self, prices: list) -> tuple:
        """
        Calculate MACD Line, Signal Line, and Histogram.
        
        Returns: (macd_line, signal_line, histogram, is_valid)
        """
        if len(prices) < 35:  # Need at least 26 + 9 for valid signal
            return 0.0, 0.0, 0.0, False
            
        # Calculate EMAs for MACD Line
        ema_12 = self._calculate_ema(prices[-26:], 12)  # Use recent slice
        ema_26 = self._calculate_ema(prices, 26)
        
        macd_line = ema_12 - ema_26
        
        # For Signal Line, we need historical MACD values
        # Simplified: Calculate MACD at multiple points and EMA those
        macd_history = []
        for i in range(9, len(prices)):
            slice_prices = prices[:i+1]
            if len(slice_prices) >= 26:
                e12 = self._calculate_ema(slice_prices[-26:], 12)
                e26 = self._calculate_ema(slice_prices, 26)
                macd_history.append(e12 - e26)
        
        if len(macd_history) < 9:
            return macd_line, 0.0, 0.0, False
            
        signal_line = self._calculate_ema(macd_history[-9:], 9)
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram, True

    def analyze_tick(self, watcher: Watcher, price: float) -> tuple:
        """
        Analyze a single watcher tick using MACD logic.
        Returns: (Action, Reason, Size)
        """
        self.update_market_mode()
        
        # Signal Cooldown (60s for Longtail - slower)
        if hasattr(watcher, 'last_signal_time') and (time.time() - watcher.last_signal_time < 60):
            return 'HOLD', '', 0.0

        # Get price history from watcher's data feed
        # V17.0 Fix: Convert to list (raw_prices may be deque)
        history = list(watcher.data_feed.raw_prices)
        if len(history) < 35:
            return 'HOLD', '', 0.0
            
        # Calculate MACD
        macd, signal, histogram, is_valid = self._calculate_macd(history)
        
        if not is_valid:
            return 'HOLD', '', 0.0
        
        # Cache previous state for crossover detection
        symbol = watcher.symbol
        prev_state = self._macd_cache.get(symbol, {'macd': 0, 'signal': 0, 'histogram': 0})
        
        # Update cache
        self._macd_cache[symbol] = {'macd': macd, 'signal': signal, 'histogram': histogram}
        
        # Check Exits First
        if watcher.in_position:
            return self._evaluate_exit(watcher, price, macd, signal, histogram, prev_state)
        
        # Check Entries
        return self._evaluate_entry(watcher, price, macd, signal, histogram, prev_state)
    
    def _evaluate_entry(self, watcher, price, macd, signal, histogram, prev_state) -> tuple:
        """MACD Crossover Entry Logic."""
        
        # A. Position Sizing (Capped to available cash)
        size_usd = min(Settings.POSITION_SIZE_USD, self.portfolio.cash_available)
        if size_usd < 5.0:  # Minimum viable trade
            return 'HOLD', '', 0.0
        atr = watcher.get_atr() if hasattr(watcher, 'get_atr') else 0.0
        
        # B. Basic Checks
        if price < Settings.MIN_PRICE_THRESHOLD: 
            return 'HOLD', '', 0.0
        # V19.1: Require 50+ ticks for proper MACD warmup (was 3    5)
        if watcher.get_price_count() < 50: 
            return 'HOLD', '', 0.0
        if watcher.hourly_trades >= Settings.MAX_TRADES_PER_HOUR: 
            return 'HOLD', '', 0.0
        
        # C. MACD Crossover Signal
        # BUY when MACD crosses ABOVE Signal (Bullish)
        prev_hist = prev_state.get('histogram', 0)
        prev_macd = prev_state.get('macd', 0)
        
        # V17.0 Fix: Require warmup - previous state must have been calculated
        # (not default zeros from first tick)
        if prev_macd == 0 and prev_hist == 0:
            return 'HOLD', '', 0.0  # Still warming up
        
        # Crossover: Previous histogram was negative/zero, current is positive
        if prev_hist <= 0 and histogram > 0:
            # Bullish Crossover!
            info = PositionSizer.get_size_info(atr, size_usd)
            reason = f"🔭 LONGTAIL MACD CROSS (MACD:{macd:.6f} > SIG:{signal:.6f}) [{info}]"
            priority_queue.add(3, 'LOG', {'level': 'INFO', 'message': f"[LONGTAIL] 📈 MACD Bullish Cross: {watcher.symbol}"})
            return 'BUY', reason, size_usd
        
        return 'HOLD', '', 0.0
    
    def _evaluate_exit(self, watcher, price, macd, signal, histogram, prev_state) -> tuple:
        """MACD Crossover Exit + TSL Logic."""
        
        # A. Update TSL State (Same as Scalper)
        state = {
            'in_position': watcher.in_position,
            'entry_price': watcher.entry_price,
            'max_price_achieved': watcher.max_price_achieved,
            'trailing_stop_price': watcher.trailing_stop_price
        }
        
        new_state, triggered, reason = TrailingStopManager.update_tsl(price, state)
        
        if new_state['max_price_achieved'] > watcher.max_price_achieved:
            watcher.max_price_achieved = new_state['max_price_achieved']
        if new_state['trailing_stop_price'] > watcher.trailing_stop_price:
            watcher.trailing_stop_price = new_state['trailing_stop_price']
        
        if triggered:
            net_pnl = Metrics.calculate_net_pnl_pct(watcher.entry_price, price, watcher.cost_basis) * 100
            return 'SELL', f"{reason} (Net: {net_pnl:.1f}%)", 0.0
        
        # B. Basic Stop Loss
        pnl_pct = Metrics.calculate_pnl_pct(watcher.entry_price, price)
        if pnl_pct <= Settings.STOP_LOSS_PCT:
            return 'SELL', f"🛑 STOP-LOSS ({pnl_pct*100:.2f}%)", 0.0
        
        # C. MACD Bearish Crossover Exit
        prev_hist = prev_state.get('histogram', 0)
        
        # Exit when histogram turns negative (MACD crosses BELOW Signal)
        if prev_hist >= 0 and histogram < 0:
            net_pnl = Metrics.calculate_net_pnl_pct(watcher.entry_price, price, watcher.cost_basis) * 100
            return 'SELL', f"🔭 LONGTAIL MACD CROSS EXIT (Net: {net_pnl:.1f}%)", 0.0
        
        return 'HOLD', '', 0.0
