"""
Warm Trend Buffers - Rolling Technical Indicators.

Provides RSI, EMA, ATR for regime filtering.
The "telescope" for seeing market context.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Tuple
from enum import Enum


class MarketRegime(str, Enum):
    """Market regime classification."""
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    CHOPPY = "CHOPPY"
    UNKNOWN = "UNKNOWN"


@dataclass
class PricePoint:
    """A single price observation."""
    price: float
    timestamp: float
    volume: float = 0.0


@dataclass
class TrendIndicators:
    """Calculated indicators for a token."""
    rsi_14: float = 50.0
    ema_20: float = 0.0
    ema_50: float = 0.0
    atr_14: float = 0.0
    momentum: float = 0.0
    regime: MarketRegime = MarketRegime.UNKNOWN
    last_update: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            "rsi_14": round(self.rsi_14, 2),
            "ema_20": round(self.ema_20, 6),
            "ema_50": round(self.ema_50, 6),
            "atr_14": round(self.atr_14, 6),
            "momentum": round(self.momentum, 4),
            "regime": self.regime.value,
        }


class TokenBuffer:
    """Rolling price buffer for a single token."""
    
    MAX_HISTORY = 100  # Keep last 100 prices
    
    def __init__(self, mint: str, symbol: str) -> None:
        self.mint = mint
        self.symbol = symbol
        self.prices: deque[PricePoint] = deque(maxlen=self.MAX_HISTORY)
        self.gains: deque[float] = deque(maxlen=14)
        self.losses: deque[float] = deque(maxlen=14)
        self._ema_20: float = 0.0
        self._ema_50: float = 0.0
        self._last_price: float = 0.0
        self._atr_values: deque[float] = deque(maxlen=14)
    
    def add_price(self, price: float, timestamp: float, volume: float = 0.0) -> None:
        """Add a price observation."""
        point = PricePoint(price, timestamp, volume)
        
        # Calculate gain/loss for RSI
        if self._last_price > 0:
            change = price - self._last_price
            if change > 0:
                self.gains.append(change)
                self.losses.append(0)
            else:
                self.gains.append(0)
                self.losses.append(abs(change))
            
            # ATR: Use simplified true range
            tr = abs(price - self._last_price)
            self._atr_values.append(tr)
        
        self._last_price = price
        self.prices.append(point)
        
        # Update EMAs
        self._update_emas(price)
    
    def _update_emas(self, price: float) -> None:
        """Update exponential moving averages."""
        # EMA(20)
        if self._ema_20 == 0:
            self._ema_20 = price
        else:
            k20 = 2 / (20 + 1)
            self._ema_20 = price * k20 + self._ema_20 * (1 - k20)
        
        # EMA(50)
        if self._ema_50 == 0:
            self._ema_50 = price
        else:
            k50 = 2 / (50 + 1)
            self._ema_50 = price * k50 + self._ema_50 * (1 - k50)
    
    def get_rsi(self, period: int = 14) -> float:
        """Calculate RSI(period)."""
        if len(self.gains) < period:
            return 50.0  # Neutral if insufficient data
        
        avg_gain = sum(list(self.gains)[-period:]) / period
        avg_loss = sum(list(self.losses)[-period:]) / period
        
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def get_ema(self, period: int = 20) -> float:
        """Get EMA for specified period."""
        if period == 20:
            return self._ema_20
        elif period == 50:
            return self._ema_50
        else:
            # Calculate on-demand for other periods
            if len(self.prices) < period:
                return self._last_price
            
            prices = [p.price for p in list(self.prices)[-period:]]
            k = 2 / (period + 1)
            ema = prices[0]
            for p in prices[1:]:
                ema = p * k + ema * (1 - k)
            return ema
    
    def get_atr(self, period: int = 14) -> float:
        """Get Average True Range."""
        if len(self._atr_values) < period:
            return 0.0
        
        return sum(list(self._atr_values)[-period:]) / period
    
    def get_momentum(self, lookback: int = 10) -> float:
        """Get price momentum (% change over lookback)."""
        if len(self.prices) < lookback:
            return 0.0
        
        old_price = list(self.prices)[-lookback].price
        if old_price == 0:
            return 0.0
        
        return (self._last_price - old_price) / old_price
    
    def get_regime(self) -> MarketRegime:
        """Classify current market regime."""
        if len(self.prices) < 20:
            return MarketRegime.UNKNOWN
        
        rsi = self.get_rsi()
        momentum = self.get_momentum()
        ema_cross = self._ema_20 - self._ema_50
        
        # Trending up: RSI > 50, positive momentum, EMA20 > EMA50
        if rsi > 55 and momentum > 0.01 and ema_cross > 0:
            return MarketRegime.TRENDING_UP
        
        # Trending down: RSI < 45, negative momentum, EMA20 < EMA50
        if rsi < 45 and momentum < -0.01 and ema_cross < 0:
            return MarketRegime.TRENDING_DOWN
        
        # Choppy: RSI near 50, low momentum
        return MarketRegime.CHOPPY
    
    def get_indicators(self) -> TrendIndicators:
        """Get all calculated indicators."""
        return TrendIndicators(
            rsi_14=self.get_rsi(14),
            ema_20=self._ema_20,
            ema_50=self._ema_50,
            atr_14=self.get_atr(14),
            momentum=self.get_momentum(),
            regime=self.get_regime(),
            last_update=time.time(),
        )


class WarmTrendBuffer:
    """
    Multi-token warm trend buffer.
    
    Maintains rolling indicators for regime filtering.
    """
    
    def __init__(self) -> None:
        self._buffers: Dict[str, TokenBuffer] = {}
    
    def add_price(
        self,
        mint: str,
        price: float,
        timestamp: Optional[float] = None,
        symbol: str = "",
        volume: float = 0.0,
    ) -> None:
        """Add price observation for a token."""
        if price <= 0:
            return
        
        ts = timestamp or time.time()
        
        if mint not in self._buffers:
            self._buffers[mint] = TokenBuffer(mint, symbol or mint[:8])
        
        self._buffers[mint].add_price(price, ts, volume)
    
    def get_rsi(self, mint: str, period: int = 14) -> float:
        """Get RSI for a token."""
        if mint not in self._buffers:
            return 50.0
        return self._buffers[mint].get_rsi(period)
    
    def get_ema(self, mint: str, period: int = 20) -> float:
        """Get EMA for a token."""
        if mint not in self._buffers:
            return 0.0
        return self._buffers[mint].get_ema(period)
    
    def get_atr(self, mint: str, period: int = 14) -> float:
        """Get ATR for a token."""
        if mint not in self._buffers:
            return 0.0
        return self._buffers[mint].get_atr(period)
    
    def get_regime(self, mint: str) -> MarketRegime:
        """Get market regime for a token."""
        if mint not in self._buffers:
            return MarketRegime.UNKNOWN
        return self._buffers[mint].get_regime()
    
    def get_indicators(self, mint: str) -> TrendIndicators:
        """Get all indicators for a token."""
        if mint not in self._buffers:
            return TrendIndicators()
        return self._buffers[mint].get_indicators()
    
    def get_all_regimes(self) -> Dict[str, MarketRegime]:
        """Get regimes for all tracked tokens."""
        return {
            mint: buf.get_regime()
            for mint, buf in self._buffers.items()
        }
    
    def get_stats(self) -> Dict:
        """Get buffer statistics."""
        return {
            "tokens_tracked": len(self._buffers),
            "total_observations": sum(
                len(b.prices) for b in self._buffers.values()
            ),
        }


# Global instance
_buffer: Optional[WarmTrendBuffer] = None


def get_warm_buffer() -> WarmTrendBuffer:
    """Get or create the global WarmTrendBuffer instance."""
    global _buffer
    if _buffer is None:
        _buffer = WarmTrendBuffer()
    return _buffer
