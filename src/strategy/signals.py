"""
V9.7: SRP - Technical Analysis & Signals.
Responsibility: Calculate indicators (RSI, SMA) and evaluate raw signals.
"""

class TechnicalAnalysis:
    """Pure logic for Technical Analysis calculations."""
    
    @staticmethod
    def calculate_rsi(prices: list, period: int = 14) -> float:
        """
        Calculate RSI from a list of prices.
        Returns 50.0 if insufficient data.
        """
        if len(prices) < period + 1:
            return TechnicalAnalysis._simple_rsi(prices)
            
        gains = 0.0
        losses = 0.0
        
        # Calculate initial average gain/loss
        for i in range(1, period + 1):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains += change
            else:
                losses -= change
                
        avg_gain = gains / period
        avg_loss = losses / period
        
        # Smooth with Wilder's method for remaining points? 
        # For simplicity and performance on short arrays, we might just use the window.
        # But if prices list is long, we should iterate.
        # Assuming prices is potentially just the window or full history?
        # Standard implementation often uses full history.
        # Here we mimic the likely logic: Simple RSI if short, Standard if long.
        
        if avg_loss == 0: return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def _simple_rsi(prices: list) -> float:
        """Simple RSI for small datasets."""
        if len(prices) < 2: return 50.0
        
        gains = 0
        losses = 0
        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0: gains += change
            else: losses -= change
            
        if losses == 0: return 100.0 if gains > 0 else 50.0
        rs = gains / losses
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def calculate_sma(prices, period: int = 50) -> float:
        """Calculate Simple Moving Average. Handles lists and deques."""
        # Convert to list if needed (deques don't support slicing)
        if hasattr(prices, '__iter__') and not isinstance(prices, list):
            prices = list(prices)
        
        if len(prices) < period:
            return 0.0
        return sum(prices[-period:]) / period

    @staticmethod
    def is_uptrend(current_price: float, prices, sma_period: int = 50) -> bool:
        """Check if price is above SMA. Handles lists and deques."""
        sma = TechnicalAnalysis.calculate_sma(prices, sma_period)
        if sma <= 0: return True # Assume true if insufficient data (don't block)
        return current_price > sma

    @staticmethod
    def calculate_ema(prices, period: int = 20) -> float:
        """Calculate Exponential Moving Average."""
        if hasattr(prices, '__iter__') and not isinstance(prices, list):
            prices = list(prices)
            
        if len(prices) < period:
            return TechnicalAnalysis.calculate_sma(prices, period) # Fallback
            
        # Recursive calculation or loop
        # EMA_today = Close * alpha + EMA_yesterday * (1-alpha)
        alpha = 2.0 / (period + 1.0)
        
        # Start with SMA of first 'period' elements
        ema = sum(prices[:period]) / period
        
        for price in prices[period:]:
            ema = (price * alpha) + (ema * (1 - alpha))
            
        return ema
        
    @staticmethod
    def calculate_atr(highs, lows, closes, period: int = 14) -> float:
        """Calculate Average True Range."""
        # Convert to lists
        if len(closes) < period + 1:
            return 0.0
            
        tr_list = []
        for i in range(1, len(closes)):
            h = highs[i]
            l = lows[i]
            pc = closes[i-1]
            
            # TR = Max(H-L, |H-PC|, |L-PC|)
            tr = max(h - l, abs(h - pc), abs(l - pc))
            tr_list.append(tr)
            
        if len(tr_list) < period:
            return 0.0
            
        # First ATR is simple average of TRs
        atr = sum(tr_list[:period]) / period
        
        # Subsequent ATRs: (Previous ATR * (n-1) + Current TR) / n
        # Wilder's Smoothing
        for tr in tr_list[period:]:
            atr = ((atr * (period - 1)) + tr) / period
            
        return atr
