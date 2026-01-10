import pandas as pd
import numpy as np


class VwapLogic:
    """
    V33.4: Live VWAP Banding Strategy.
    V38.3: Fixed to accept portfolio like other strategies.
    """

    def __init__(self, portfolio, vwap_period=20, std_dev=2.0):
        self.portfolio = portfolio  # V38.3: Match other strategies
        self.vwap_period = vwap_period
        self.std_dev = std_dev

        # Win Rate Tracking
        self.wins = 0
        self.losses = 0

    def title(self):
        return "VWAP"

    def get_market_mode(self):
        """Return formatted stats for UI."""
        total = self.wins + self.losses
        wr = (self.wins / total * 100) if total > 0 else 0
        return f"VWAP (W:{self.wins}|L:{self.losses} {wr:.0f}%)"

    def update_market_mode(self, result):
        """Update Win Rate based on Paper/Live trade result."""
        if result == "WIN":
            self.wins += 1
        elif result == "LOSS":
            self.losses += 1

    def analyze_tick(self, watcher, price: float = None):
        """
        Analyze current tick data for VWAP Setup.
        V38.1: Added price parameter for interface compatibility.
        Returns:
            tuple: (action, reason, size) matching BaseStrategy interface
        """
        # Use provided price or get from watcher
        if price is None:
            price = watcher.get_price()
        if price <= 0:
            return "HOLD", "", 0.0

        # access underlying deques
        feed = watcher.data_feed
        if len(feed.raw_prices) < self.vwap_period:
            return "HOLD", "", 0.0

        # Convert to Series for Vectorized Calc
        closes = pd.Series(list(feed.raw_prices))
        volumes = pd.Series(list(feed.raw_volumes))

        # Synthesize High/Low/Close from raw ticks?
        # For simplicity in Live Tick logic, we assume TP (Typical Price) ~= Close or we use Close.
        # TA Lib expects High, Low, Close. We can pass Close for all if using tick stream.
        # Or better, use DataFeed.candles?
        # Using Ticks gives faster response.

        tp = closes  # Use Close as TP proxy for tick stream

        # Calculate Rolling VWAP
        # VWAP = Sum(TP * Vol) / Sum(Vol)
        pv = tp * volumes
        cum_pv = pv.rolling(window=self.vwap_period).sum()
        cum_vol = volumes.rolling(window=self.vwap_period).sum()

        # Handle DivZero (if all volumes are 0 e.g. purely live run without history)
        # Fallback to EMA if Volume is missing
        current_vwap = 0.0
        try:
            vwap_series = cum_pv / cum_vol
            current_vwap = vwap_series.iloc[-1]
            if pd.isna(current_vwap) or np.isinf(current_vwap):
                current_vwap = (
                    closes.ewm(span=self.vwap_period).mean().iloc[-1]
                )  # Fallback
        except:
            current_vwap = closes.ewm(span=self.vwap_period).mean().iloc[-1]

        # Calculate Bands (StdDev of Close)
        std = closes.rolling(window=self.vwap_period).std().iloc[-1]
        if pd.isna(std):
            std = 0.0

        lower_band = current_vwap - (std * self.std_dev)
        upper_band = current_vwap + (std * self.std_dev)

        # Volatility Metric for Logging
        volatility = (std / price) * 100

        watcher.trailing_stop_price = lower_band

        # SIGNAL GENERATION

        # BUY: Price < Lower Band (Oversold)
        if price < lower_band:
            # Check for cooldown
            if watcher.in_position:
                return "HOLD", "", 0.0

            # BUY signal
            size_usd = 50.0  # TODO: Use proper sizing
            return "BUY", f"🌊 VWAP ENTRY (Price < Band {lower_band:.5f})", size_usd

        # SELL: Price > VWAP (Mean Reversion)
        elif price > current_vwap:
            if not watcher.in_position:
                return "HOLD", "", 0.0
            return "SELL", f"🌊 VWAP EXIT (Price > Mean {current_vwap:.5f})", 0.0

        return "HOLD", "", 0.0
