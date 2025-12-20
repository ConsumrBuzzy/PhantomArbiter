"""
Decay Detector - Targeted spread decay monitoring.

Use cases:
1. When a promising spread appears, measure its decay rate quickly
2. On-demand monitoring for specific pairs
3. Decide if a pair is "safe" to execute (stable spread) or risky (fast decay)
"""

import time
import asyncio
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class DecayResult:
    """Result of decay monitoring."""
    pair: str
    initial_spread: float
    final_spread: float
    decay_pct: float          # Total decay in %
    duration_sec: float
    decay_per_sec: float      # Decay velocity
    is_stable: bool           # True if decay < 0.1%/sec
    samples: int


class DecayDetector:
    """
    Monitors spread decay for a specific pair.
    
    Usage:
        detector = DecayDetector(spread_detector)
        result = await detector.measure_decay("PIPPIN/USDC", samples=3, interval=2)
        if result.is_stable:
            # Safe to execute
    """
    
    def __init__(self, spread_detector):
        self.spread_detector = spread_detector
        self._cache = {}  # pair -> (decay_result, timestamp)
    
    async def measure_decay(
        self, 
        pair: str, 
        base_mint: str,
        quote_mint: str,
        samples: int = 3, 
        interval_sec: float = 2.0,
        trade_size: float = 50
    ) -> Optional[DecayResult]:
        """
        Take multiple spread measurements and calculate decay velocity.
        
        Args:
            pair: Pair name (e.g., "PIPPIN/USDC")
            base_mint: Base token mint
            quote_mint: Quote token mint
            samples: Number of price samples to take
            interval_sec: Seconds between samples
            trade_size: Trade size for spread calculation
            
        Returns:
            DecayResult with measured decay velocity
        """
        measurements = []
        
        for i in range(samples):
            opp = self.spread_detector.get_spread(
                base_mint, quote_mint, pair, trade_size
            )
            if opp:
                measurements.append((time.time(), opp.spread_pct))
            
            if i < samples - 1:  # Don't wait after last sample
                await asyncio.sleep(interval_sec)
        
        if len(measurements) < 2:
            return None
        
        # Calculate decay
        initial_time, initial_spread = measurements[0]
        final_time, final_spread = measurements[-1]
        
        duration = final_time - initial_time
        decay_pct = initial_spread - final_spread
        decay_per_sec = decay_pct / duration if duration > 0 else 0
        
        result = DecayResult(
            pair=pair,
            initial_spread=initial_spread,
            final_spread=final_spread,
            decay_pct=decay_pct,
            duration_sec=duration,
            decay_per_sec=decay_per_sec,
            is_stable=abs(decay_per_sec) < 0.1,  # < 0.1%/sec = stable
            samples=len(measurements)
        )
        
        # Cache result
        self._cache[pair] = (result, time.time())
        
        # Log to DB for learning
        try:
            from src.shared.system.db_manager import db_manager
            db_manager.log_spread_decay(pair, initial_spread, final_spread, duration)
        except:
            pass
        
        return result
    
    def get_cached(self, pair: str, max_age_sec: float = 60) -> Optional[DecayResult]:
        """Get cached decay result if fresh enough."""
        if pair in self._cache:
            result, ts = self._cache[pair]
            if time.time() - ts < max_age_sec:
                return result
        return None
    
    def get_status_icon(self, pair: str) -> str:
        """Get a status icon for display."""
        result = self.get_cached(pair)
        if not result:
            return ""
        
        if result.is_stable:
            return "🟢"  # Stable - safe to execute
        elif result.decay_per_sec > 0.2:
            return f"⚡{result.decay_per_sec:.1f}"  # Fast decay - risky
        else:
            return "📉"  # Some decay


# Factory function for easy use
_detector_instance = None

def get_decay_detector(spread_detector=None):
    """Get or create the decay detector singleton."""
    global _detector_instance
    if _detector_instance is None and spread_detector:
        _detector_instance = DecayDetector(spread_detector)
    return _detector_instance
