
import numpy as np
from typing import List, Dict, Tuple

class MicrostructureFeatures:
    """
    V62.0: Advanced Alpha Factors for HFT.
    Focuses on Order Flow, Liquidity, and Momentum Acceleration.
    """
    
    @staticmethod
    def calculate_obi(bids_vol: float, asks_vol: float) -> float:
        """
        Calculate Order Imbalance (OBI).
        Range: -1.0 (Selling Pressure) to +1.0 (Buying Pressure)
        Formula: (BidVol - AskVol) / (BidVol + AskVol)
        """
        total = bids_vol + asks_vol
        if total == 0: return 0.0
        return (bids_vol - asks_vol) / total
        
    @staticmethod
    def calculate_rsi_delta(current_rsi: float, past_rsi: float) -> float:
        """
        Calculate RSI Acceleration.
        > 0: Momentum increasing
        < 0: Momentum decreasing
        """
        return current_rsi - past_rsi
        
    @staticmethod
    def calculate_spread_variance(prices: List[float]) -> float:
        """
        Calculate realized volatility (Proxy for Spread Variance).
        Higher variance often precedes liquidity gaps.
        """
        if len(prices) < 2: return 0.0
        return float(np.std(prices))

    @staticmethod
    def calculate_effective_spread(trade_price: float, bid: float, ask: float) -> float:
        """
        Estimate effective spread from trade execution relative to quote.
        Feature for: Liquidity Cost Analysis.
        """
        mid = (bid + ask) / 2
        if mid == 0: return 0.0
        return 2 * abs(trade_price - mid) / mid
