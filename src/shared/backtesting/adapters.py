from backtesting import Strategy
from backtesting.lib import crossover
import pandas as pd
from src.backtesting.ta_lib import TA as ta

class PhantomScalper(Strategy):
    """
    V29.0 Backtesting Adapter for Scalper Strategy.
    Mirrors 'DecisionEngine' logic: RSI < 30 (Buy), RSI > 70 (Sell).
    """
    
    # Parameters to optimize later
    rsi_period = 14
    rsi_buy = 30
    rsi_sell = 70
    
    def init(self):
        # Pre-calculate indicators using vectorized local TA lib
        self.rsi = self.I(ta.rsi, pd.Series(self.data.Close), length=self.rsi_period)
        
    def next(self):
        # V27.0 Logic: Risk Sizing handled by 'size' kwarg in Backtest.run or self.buy
        # Here we just generate signals
        
        # BUY Logic: RSI < 30 (Oversold)
        if self.rsi[-1] < self.rsi_buy:
             if not self.position:
                 self.buy()
                 
        # SELL Logic: RSI > 70 (Overbought)
        elif self.rsi[-1] > self.rsi_sell:
            if self.position:
                self.position.close()

class PhantomLongtail(Strategy):
    """
    V29.0 Backtesting Adapter for Longtail Strategy.
    Mirrors 'DecisionEngine' logic: MACD Crossover.
    """
    
    # MACD Defaults (12, 26, 9)
    fast = 12
    slow = 26
    signal = 9
    
    def init(self):
        # Calculate MACD. ta.macd returns DataFrame, we need specific columns
        # self.I requires a callable that returns a numpy array.
        # Wrapper to extract MACD line and Signal line
        def get_macd(close):
            df = ta.macd(pd.Series(close), fast=12, slow=26, signal=9)
            return df['MACD_12_26_9'].to_numpy()
            
        def get_signal(close):
            df = ta.macd(pd.Series(close), fast=12, slow=26, signal=9)
            return df['MACDs_12_26_9'].to_numpy()

        self.macd = self.I(get_macd, self.data.Close)
        self.signal_line = self.I(get_signal, self.data.Close)
        
    def next(self):
        # BUY: MACD crosses above Signal
        if crossover(self.macd, self.signal_line):
            if not self.position:
                self.buy()
        
        # SELL: Signal crosses above MACD (or specific exit logic)
        elif crossover(self.signal_line, self.macd):
            if self.position:
                self.position.close()

class PhantomKeltner(Strategy):
    """
    V31.1: Keltner Channel Reversion Strategy.
    Buy when price dips below Lower Band.
    Sell when price returns to EMA (Middle).
    """
    ema_period = 20
    atr_period = 10
    atr_mult = 2.0
    
    def init(self):
        # Middle
        self.ema = self.I(ta.ema, pd.Series(self.data.Close), length=self.ema_period)
        
        # ATR Bands
        def get_lower(high, low, close):
            atr = ta.atr(pd.Series(high), pd.Series(low), pd.Series(close), length=self.atr_period)
            ema = ta.ema(pd.Series(close), length=self.ema_period)
            return (ema - (atr * self.atr_mult)).to_numpy()
            
        def get_upper(high, low, close):
            atr = ta.atr(pd.Series(high), pd.Series(low), pd.Series(close), length=self.atr_period)
            ema = ta.ema(pd.Series(close), length=self.ema_period)
            return (ema + (atr * self.atr_mult)).to_numpy()
            
        self.lower = self.I(get_lower, self.data.High, self.data.Low, self.data.Close)
        self.upper = self.I(get_upper, self.data.High, self.data.Low, self.data.Close)
        
    def next(self):
        # BUY: Close < Lower Band (Oversold extension)
        if self.data.Close[-1] < self.lower[-1]:
            if not self.position:
                self.buy()
                
        # SELL: Close > EMA (Mean Reversion complete)
        # Note: Or use Upper band for greedy exit. Let's start with EMA for prob.
        elif self.data.Close[-1] > self.ema[-1]:
            if self.position:
                self.position.close()

class PhantomVWAP(Strategy):
    """
    V33.1: VWAP Banding Strategy.
    Volume-Weighted Mean Reversion.
    """
    vwap_period = 20
    std_dev = 2.0
    
    def init(self):
        # Rolling VWAP
        def get_vwap(high, low, close, volume):
            return ta.vwap_rolling(pd.Series(high), pd.Series(low), pd.Series(close), pd.Series(volume), length=self.vwap_period).to_numpy()
            
        self.vwap = self.I(get_vwap, self.data.High, self.data.Low, self.data.Close, self.data.Volume)
        
        # Bands: VWAP +/- StdDev * Mult
        # Note: Using StdDev of Close relative to VWAP? 
        # Or simple StdDev of Close. 
        # User spec: "below the 2nd Standard Deviation band". 
        # Usually implies Bollinger-like bands around VWAP.
        def get_std(close):
            return ta.std_rolling(pd.Series(close), length=self.vwap_period).to_numpy()
            
        self.std = self.I(get_std, self.data.Close)
        
        # We construct bands in init or calculate on fly? 
        # Backtesting.py handles indicator arrays best.
        self.lower = self.I(lambda v, s: v - (s * self.std_dev), self.vwap, self.std)
        self.upper = self.I(lambda v, s: v + (s * self.std_dev), self.vwap, self.std)
        
    def next(self):
         # BUY: Close < Lower Band (Oversold relative to Volume-Weighted Mean)
         if self.data.Close[-1] < self.lower[-1]:
             if not self.position:
                 self.buy()
                 
         # SELL: Close > VWAP (Mean Reversion)
         elif self.data.Close[-1] > self.vwap[-1]:
             if self.position:
                 self.position.close()
