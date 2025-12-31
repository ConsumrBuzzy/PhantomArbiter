import pandas as pd


class TA:
    """
    Lightweight Technical Analysis lib to replace pandas_ta.
    Provides RSI and MACD.
    """

    @staticmethod
    def rsi(close, length=14):
        """Exponential RSI"""
        delta = close.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.ewm(alpha=1 / length, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / length, adjust=False).mean()

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def macd(close, fast=12, slow=26, signal=9):
        """
        Returns DataFrame with keys: MACD, Signal, Hist
        """
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        sig = macd.ewm(span=signal, adjust=False).mean()
        hist = macd - sig

        return pd.DataFrame(
            {"MACD_12_26_9": macd, "MACDs_12_26_9": sig, "MACDh_12_26_9": hist}
        )

    @staticmethod
    def ema(close, length=20):
        """Exponential Moving Average"""
        return close.ewm(span=length, adjust=False).mean()

    @staticmethod
    def atr(high, low, close, length=14):
        """Average True Range"""
        # TR = max(high-low, abs(high-prev_close), abs(low-prev_close))
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.ewm(alpha=1 / length, adjust=False).mean()

    @staticmethod
    def vwap_rolling(high, low, close, volume, length=20):
        """
        Rolling Volume Weighted Average Price (anchored by rolling window).
        VWAP = Sum(Price * Vol) / Sum(Vol)
        """
        typical_price = (high + low + close) / 3
        pv = typical_price * volume

        # Calculate Rolling Sums
        cum_pv = pv.rolling(window=length).sum()
        cum_vol = volume.rolling(window=length).sum()

        return cum_pv / cum_vol

    @staticmethod
    def std_rolling(close, length=20):
        """Rolling Standard Deviation"""
        return close.rolling(window=length).std()
