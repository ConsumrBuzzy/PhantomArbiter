"""
Adaptive Scanner
================
Dynamically adjusts scan rate based on market conditions while respecting RPS limits.

- Base interval: 3 seconds (slow, saves RPS)
- Fast interval: 0.5 seconds (when spreads > threshold)
- Cooldown: Returns to slow after 30s of no activity
"""

import time
from typing import Dict, List

from src.arbiter.core.spread_detector import SpreadOpportunity


class AdaptiveScanner:
    """
    Adapts scan rate based on market conditions while respecting RPS limits.
    
    Usage:
        scanner = AdaptiveScanner()
        
        # In main loop:
        interval = scanner.update(spreads)
        priority_pairs = scanner.get_priority_pairs(all_pairs)
        await asyncio.sleep(interval)
    """
    
    SPREAD_THRESHOLD = 0.5  # % spread that triggers fast mode
    COOLDOWN_SECONDS = 30   # Return to slow after this
    
    def __init__(self, base_interval=5.0, fast_interval=0.5, rps_limit=8):
        self.base_interval = base_interval
        self.fast_interval = fast_interval
        self.rps_limit = rps_limit
        
        # State tracking
        self.last_spread_spike = 0.0
        self.pair_heat: Dict[str, float] = {}  # {pair: last_activity_time}
        self.current_interval = base_interval

    def trigger_activity(self, pair: str):
        """External trigger (e.g. WSS) to indicate activity on a pair."""
        now = time.time()
        self.last_spread_spike = now
        self.pair_heat[pair] = now
        self.current_interval = self.fast_interval
        
    def update(self, spreads: List[SpreadOpportunity]) -> float:
        """Update based on scan results, return next interval."""
        now = time.time()
        
        # Check for promising spreads (> threshold)
        hot_pairs = [s for s in spreads if s.spread_pct > self.SPREAD_THRESHOLD]
        
        if hot_pairs:
            self.last_spread_spike = now
            for s in hot_pairs:
                self.pair_heat[s.pair] = now
            self.current_interval = self.fast_interval
            return self.fast_interval
        
        # Cooldown: 30s since last spike → slow down
        time_since_spike = now - self.last_spread_spike
        if time_since_spike > self.COOLDOWN_SECONDS:
            self.current_interval = self.base_interval
            return self.base_interval
        
        # Gradual slowdown: 1s during cooldown
        self.current_interval = 1.0
        return 1.0
    
    def get_priority_pairs(self, all_pairs: List) -> List:
        """Return pairs sorted by recent activity (hot pairs first)."""
        return sorted(
            all_pairs, 
            key=lambda p: self.pair_heat.get(p[0], 0), 
            reverse=True
        )
    
    @property
    def mode_emoji(self) -> str:
        """Return emoji indicating current mode."""
        if self.current_interval <= 0.5:
            return "🔥"  # Fast
        elif self.current_interval <= 1.5:
            return "⚡"  # Medium
        return "💤"  # Slow
    
    @property
    def mode_name(self) -> str:
        """Return current mode name."""
        if self.current_interval <= 0.5:
            return "FAST"
        elif self.current_interval <= 1.5:
            return "MEDIUM"
        return "SLOW"
