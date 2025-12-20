"""
Adaptive Scanner
================
Dynamically adjusts scan rate based on market conditions while respecting RPS limits.

Features:
- Global adaptive interval (fast mode when spreads spike)
- Per-pair skip intervals based on spread variance AND absolute level
- Low-spread stable pairs get deprioritized to save API calls

Base interval: 3 seconds (slow, saves RPS)
Fast interval: 0.5 seconds (when spreads > threshold)
Cooldown: Returns to slow after 30s of no activity
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.arbiter.core.spread_detector import SpreadOpportunity


# ═══════════════════════════════════════════════════════════════════════════════
# PER-PAIR METRICS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class PairMetrics:
    """Tracks spread history for a single pair."""
    last_spread: float = 0.0
    spread_variance: float = 0.0  # EMA of spread deltas
    last_scan_time: float = 0.0
    skip_until: float = 0.0       # Unix timestamp - don't scan before this
    scan_count: int = 0           # Total scans for this pair


# ═══════════════════════════════════════════════════════════════════════════════
# ADAPTIVE SCANNER
# ═══════════════════════════════════════════════════════════════════════════════

class AdaptiveScanner:
    """
    Adapts scan rate based on market conditions while respecting RPS limits.
    
    Two-level adaptation:
    1. Global: Fast/slow cycle based on overall market activity
    2. Per-pair: Skip intervals based on spread variance AND absolute level
    
    Usage:
        scanner = AdaptiveScanner()
        
        # In main loop:
        interval = scanner.update(spreads)
        pairs_to_scan = scanner.filter_pairs(all_pairs)
        await asyncio.sleep(interval)
    """
    
    # Global thresholds
    SPREAD_THRESHOLD = 0.5  # % spread that triggers fast mode
    COOLDOWN_SECONDS = 30   # Return to slow after this
    
    # Per-pair thresholds
    HOT_SPREAD_PCT = 0.8      # Spreads >= this are always scanned
    WARM_SPREAD_PCT = 0.4     # Spreads >= this get medium priority
    VARIANCE_HOT = 0.20       # High variance = scan frequently
    VARIANCE_WARM = 0.10      # Medium variance
    VARIANCE_COLD = 0.05      # Low variance = skip often
    
    # Skip intervals (seconds)
    SKIP_HOT = 0.0            # Always scan
    SKIP_WARM = 3.0           # Skip 3 seconds
    SKIP_COOL = 8.0           # Skip 8 seconds
    SKIP_COLD = 15.0          # Skip 15 seconds
    SKIP_FROZEN = 20.0        # Very stale + low spread
    
    def __init__(self, base_interval: float = 5.0, fast_interval: float = 0.5, rps_limit: int = 8):
        self.base_interval = base_interval
        self.fast_interval = fast_interval
        self.rps_limit = rps_limit
        
        # Global state
        self.last_spread_spike = 0.0
        self.current_interval = base_interval
        
        # Per-pair state
        self.pair_metrics: Dict[str, PairMetrics] = {}
        self.pair_heat: Dict[str, float] = {}  # Legacy: {pair: last_activity_time}

    def trigger_activity(self, pair: str) -> None:
        """External trigger (e.g. WSS) to indicate activity on a pair."""
        now = time.time()
        self.last_spread_spike = now
        self.pair_heat[pair] = now
        self.current_interval = self.fast_interval
        
        # Reset skip for this pair
        if pair in self.pair_metrics:
            self.pair_metrics[pair].skip_until = 0.0
    
    def should_scan_pair(self, pair: str, now: float = None) -> bool:
        """
        Check if a pair should be scanned this cycle.
        
        Returns False if pair is in skip cooldown.
        """
        now = now or time.time()
        metrics = self.pair_metrics.get(pair)
        
        if not metrics:
            return True  # First scan - always go
        
        return now >= metrics.skip_until
    
    def filter_pairs(self, all_pairs: List[tuple], now: float = None) -> List[tuple]:
        """
        Filter pairs list to only those that should be scanned now.
        
        Args:
            all_pairs: List of (pair_name, base_mint, quote_mint) tuples
            
        Returns:
            Filtered list of pairs to scan this cycle
        """
        now = now or time.time()
        return [p for p in all_pairs if self.should_scan_pair(p[0], now)]
    
    def update_pair(self, opp: SpreadOpportunity) -> None:
        """
        Update pair metrics after scanning.
        
        Calculates skip interval based on:
        1. Absolute spread level (low spread = skip more)
        2. Spread variance (stable = skip more)
        """
        now = time.time()
        metrics = self.pair_metrics.setdefault(opp.pair, PairMetrics())
        
        # Calculate spread delta
        spread_delta = abs(opp.spread_pct - metrics.last_spread)
        metrics.last_spread = opp.spread_pct
        metrics.last_scan_time = now
        metrics.scan_count += 1
        
        # Update rolling variance (EMA, alpha=0.3)
        alpha = 0.3
        metrics.spread_variance = (
            alpha * spread_delta + 
            (1 - alpha) * metrics.spread_variance
        )
        
        # Determine skip interval based on BOTH spread level and variance
        skip_seconds = self._calculate_skip_interval(opp.spread_pct, metrics.spread_variance)
        metrics.skip_until = now + skip_seconds
    
    def _calculate_skip_interval(self, spread_pct: float, variance: float) -> float:
        """
        Calculate how long to skip before next scan.
        
        Matrix logic:
        - High spread (>= 0.8%) + any variance → ALWAYS SCAN (hot target)
        - Medium spread (0.4-0.8%) + high variance → short skip
        - Medium spread (0.4-0.8%) + low variance → medium skip
        - Low spread (< 0.4%) + any variance → long skip (not worth it for $30)
        """
        # High spread = always scan (potential profit)
        if spread_pct >= self.HOT_SPREAD_PCT:
            return self.SKIP_HOT
        
        # Medium spread - variance matters
        if spread_pct >= self.WARM_SPREAD_PCT:
            if variance >= self.VARIANCE_HOT:
                return self.SKIP_HOT       # Volatile, watch closely
            elif variance >= self.VARIANCE_WARM:
                return self.SKIP_WARM      # 3s skip
            else:
                return self.SKIP_COOL      # 8s skip
        
        # Low spread - deprioritize heavily
        # Not worth watching for $30 budget even if volatile
        if variance >= self.VARIANCE_HOT:
            return self.SKIP_COOL          # 8s - volatile but low spread
        elif variance >= self.VARIANCE_COLD:
            return self.SKIP_COLD          # 15s - stable and low
        else:
            return self.SKIP_FROZEN        # 20s - frozen target
    
    def update(self, spreads: List[SpreadOpportunity]) -> float:
        """
        Update global interval based on scan results.
        
        Also updates per-pair metrics for all scanned opportunities.
        
        Returns: Next global scan interval
        """
        now = time.time()
        
        # Update per-pair metrics
        for opp in spreads:
            self.update_pair(opp)
        
        # Check for promising spreads (> threshold) for global fast mode
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
    
    def get_stats(self) -> Dict[str, any]:
        """Get scanner statistics for debugging."""
        now = time.time()
        active = sum(1 for m in self.pair_metrics.values() if now >= m.skip_until)
        skipped = len(self.pair_metrics) - active
        
        return {
            "mode": self.mode_name,
            "interval": self.current_interval,
            "pairs_tracked": len(self.pair_metrics),
            "pairs_active": active,
            "pairs_skipped": skipped,
        }
    
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

