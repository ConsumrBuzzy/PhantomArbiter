"""
MarketDataService - The Strategist
===================================
Layer A: Market Monitor - Market context and regime detection.

Responsibilities:
- Market regime detection (BULL, BEAR, CHOP)
- Order Flow Imbalance (OFI) calculation
- Price momentum tracking
- Aggregate market reporting

Does NOT handle individual trades - provides context for strategy.
"""

import time
from typing import Dict, Optional
from dataclasses import dataclass
from enum import Enum
from collections import defaultdict

from src.shared.system.logging import Logger


class MarketRegime(Enum):
    """Market regime classification."""
    BULL = "BULL"       # Strong uptrend
    BEAR = "BEAR"       # Strong downtrend
    CHOP = "CHOP"       # Sideways/volatile
    UNKNOWN = "UNKNOWN"


@dataclass
class MarketContext:
    """Current market context snapshot."""
    regime: MarketRegime
    regime_confidence: float  # 0.0 - 1.0
    sol_price: float
    btc_correlation: float
    volatility_index: float
    timestamp: float


class MarketDataService:
    """
    The Strategist - Market context and regime detection.
    
    Provides aggregate market intelligence for strategy adjustment.
    Works with DecisionEngine's DSA (Dynamic Strategy Adjustment).
    """
    
    def __init__(self):
        self._current_regime: MarketRegime = MarketRegime.UNKNOWN
        self._regime_history: list = []
        self._ofi_cache: Dict[str, float] = {}
        self._momentum_cache: Dict[str, float] = {}
        self._price_history: Dict[str, list] = defaultdict(list)
        
        # Configuration
        self._regime_update_interval = 300.0  # 5 minutes
        self._last_regime_update = 0.0
        self._momentum_window = 20  # ticks
        
        Logger.info("📊 MarketDataService initialized")
    
    def get_regime(self) -> MarketRegime:
        """
        Get current market regime.
        
        Returns:
            Current regime classification
        """
        now = time.time()
        if (now - self._last_regime_update) > self._regime_update_interval:
            self._update_regime()
        
        return self._current_regime
    
    def get_context(self) -> MarketContext:
        """Get full market context snapshot."""
        return MarketContext(
            regime=self.get_regime(),
            regime_confidence=self._calculate_regime_confidence(),
            sol_price=self._get_sol_price(),
            btc_correlation=self._calculate_btc_correlation(),
            volatility_index=self._calculate_volatility_index(),
            timestamp=time.time(),
        )
    
    def get_ofi(self, mint: str) -> float:
        """
        Get Order Flow Imbalance for a token.
        
        Args:
            mint: Token mint address
        
        Returns:
            OFI value (-1.0 to 1.0, positive = buying pressure)
        """
        return self._ofi_cache.get(mint, 0.0)
    
    def get_momentum(self, mint: str) -> float:
        """
        Get price momentum for a token.
        
        Args:
            mint: Token mint address
        
        Returns:
            Momentum as percentage change
        """
        return self._momentum_cache.get(mint, 0.0)
    
    def update_ofi(self, mint: str, bid_delta: float, ask_delta: float) -> None:
        """Update OFI from order book changes."""
        ofi = bid_delta - ask_delta
        # Normalize to -1.0 to 1.0
        self._ofi_cache[mint] = max(-1.0, min(1.0, ofi / 1000.0))
    
    def track_price(self, mint: str, price: float) -> None:
        """Track price for momentum calculation."""
        history = self._price_history[mint]
        history.append(price)
        
        # Keep limited history
        if len(history) > self._momentum_window:
            history.pop(0)
        
        # Calculate momentum
        if len(history) >= 2:
            old_price = history[0]
            if old_price > 0:
                self._momentum_cache[mint] = (price - old_price) / old_price
    
    def _update_regime(self) -> None:
        """Update market regime classification."""
        try:
            from src.core.shared_cache import SharedPriceCache
            cached = SharedPriceCache.get_market_regime()
            
            if cached:
                regime_str = cached.get("regime", "UNKNOWN")
                self._current_regime = MarketRegime(regime_str)
            else:
                self._current_regime = MarketRegime.UNKNOWN
            
            self._last_regime_update = time.time()
        except Exception as e:
            Logger.error(f"Regime update failed: {e}")
    
    def _calculate_regime_confidence(self) -> float:
        """Calculate confidence in current regime classification."""
        # TODO: implement based on indicator alignment
        return 0.6
    
    def _get_sol_price(self) -> float:
        """Get current SOL price."""
        try:
            from src.market import get_price_feed
            return get_price_feed().get_price("So11111111111111111111111111111111111111112") or 0.0
        except:
            return 0.0
    
    def _calculate_btc_correlation(self) -> float:
        """Calculate SOL/BTC correlation."""
        # TODO: implement correlation calculation
        return 0.7
    
    def _calculate_volatility_index(self) -> float:
        """Calculate market volatility index."""
        # TODO: implement volatility calculation
        return 0.5
    
    # =========================================================================
    # PRESSURE METRICS (Integration with SignalScoutService)
    # =========================================================================
    
    def get_pressure(self, mint: str) -> dict:
        """
        Get directional pressure from asymmetric intelligence.
        
        Integrates with SignalScoutService for "whiff" based pressure.
        
        Returns:
            {"bullish": 0.0-1.0, "bearish": 0.0-1.0, "volatile": 0.0-1.0}
        """
        try:
            from src.market import get_signal_scout
            scout = get_signal_scout()
            return scout.get_pressure(mint)
        except Exception as e:
            Logger.debug(f"Pressure fetch failed: {e}")
            return {"bullish": 0.0, "bearish": 0.0, "volatile": 0.0}
    
    def get_market_heat(self, mint: str) -> float:
        """
        Get aggregated "market heat" from whiff signals.
        
        Returns 0.0 (cold) to 1.0 (on fire).
        """
        try:
            from src.market import get_signal_scout
            scout = get_signal_scout()
            return scout.get_market_heat(mint)
        except Exception:
            return 0.0
