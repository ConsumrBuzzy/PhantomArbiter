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

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

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
    last_status: str = "FAR"      # Last near-miss status for priority sorting


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
    
    # V102: Warming / Stickiness
    WARM_DURATION_SECONDS = 180  # Hold "Warming" status for 3 mins
    WARM_VOLATILITY_THRESHOLD = 0.15 # Volatility above this triggers warming

    
    # RPC rate limiting
    DEFAULT_MAX_CONCURRENT_RPC = 5  # Increased for 3 RPC providers
    
    def __init__(
        self, 
        base_interval: float = 5.0, 
        fast_interval: float = 0.5, 
        rps_limit: int = 8,
        max_concurrent_rpc: int = None
    ):
        self.base_interval = base_interval
        self.fast_interval = fast_interval
        self.rps_limit = rps_limit
        
        # RPC concurrency guard - prevents 429 errors during bulk scans
        max_rpc = max_concurrent_rpc or self.DEFAULT_MAX_CONCURRENT_RPC
        self._rpc_semaphore = asyncio.Semaphore(max_rpc)
        
        # Global state
        self.last_spread_spike = 0.0
        self.current_interval = base_interval
        
        # Per-pair state
        self.pair_metrics: Dict[str, PairMetrics] = {}
        self.warming_until: Dict[str, float] = {} # V102: pair -> unix timestamp

        
        # Learning-based promotion/demotion
        self.promoted_pairs: set = set()   # High-variance pairs → scan faster
        self.demoted_pairs: set = set()    # High LIQ failure → skip more
        self._last_db_sync = 0.0
    
    def sync_with_db(self) -> None:
        """
        Sync promotion/demotion lists from DB analytics.
        Called periodically (every 5 minutes) to update based on learned patterns.
        """
        now = time.time()
        if now - self._last_db_sync < 300:  # 5 minute cooldown
            return
        
        try:
            from src.shared.system.db_manager import db_manager
            
            # Promote high-variance pairs (scan them faster)
            self.promoted_pairs = set(db_manager.get_high_variance_pairs(hours=1, min_range=0.4))
            
            # Demote high-LIQ-failure pairs (skip them more)
            liq_rates = db_manager.get_liq_failure_rate(hours=2)
            self.demoted_pairs = {pair for pair, rate in liq_rates.items() if rate > 0.7}
            
            self._last_db_sync = now
            
        except Exception:
            pass  # Silent fail - don't break scanning

    def trigger_activity(self, pair: str) -> None:
        """External trigger (e.g. WSS) to indicate activity on a pair."""
        now = time.time()
        self.last_spread_spike = now
        self.warming_until[pair] = now + self.WARM_DURATION_SECONDS
        self.current_interval = self.fast_interval
        
        # Reset skip for this pair
        if pair in self.pair_metrics:
            self.pair_metrics[pair].skip_until = 0.0
    
    def should_scan_pair(self, pair: str, now: float = None) -> bool:
        """
        Check if a pair should be scanned this cycle.
        
        Returns False if pair is in skip cooldown.
        V102: Warming pairs ALWAYS bypass cooldown (Sticky Watchers).
        """
        now = now or time.time()
        
        # V102: Automated Warming logic
        if now < self.warming_until.get(pair, 0):
            return True
            
        from config.settings import Settings
        if pair in Settings.WATCHER_PAIRS:
            return True
            
        metrics = self.pair_metrics.get(pair)
        
        if not metrics:
            return True  # First scan - always go
        
        return now >= metrics.skip_until
    
    def filter_pairs(self, all_pairs: List[tuple], now: float = None) -> List[tuple]:
        """
        Filter pairs list to only those that should be scanned now.
        V106: Implements Fairness Reserve (Warming/Watcher cap) to ensure rotation.
        """
        now = now or time.time()
        
        # Filter to scannable pairs
        scannable = [p for p in all_pairs if self.should_scan_pair(p[0], now)]
        
        from config.settings import Settings
        
        def get_priority(pair_tuple: tuple) -> float:
            pair_name = pair_tuple[0]
            
            # V106: Continuous score to allow interleaving within tiers
            # Lowest score = highest priority
            
            # 1. Sticky Warming Pairs (-200 Base)
            if now < self.warming_until.get(pair_name, 0):
                # Subtract scan time to ensure warming pairs rotate among themselves
                last_scan = self.pair_metrics.get(pair_name).last_scan_time if pair_name in self.pair_metrics else 0
                return -200 + (last_scan % 100)
            
            # 2. Watcher Pairs (-100 Base)
            if pair_name in Settings.WATCHER_PAIRS:
                return -100
                
            metrics = self.pair_metrics.get(pair_name)
            
            # 3. Starvation Guard (Priority 0)
            if not metrics or (now - metrics.last_scan_time > 60):
                return 0
            
            # 4. Normal Pod Priority (1-10)
            base_symbol = pair_name.split('/')[0] if '/' in pair_name else pair_name
            meta = Settings.ASSET_METADATA.get(base_symbol, {})
            category = meta.get('category', 'WATCH')
            pod_priority = Settings.POD_PRIORITIES.get(category, 5)
            
            return float(pod_priority) + 1.0
            
        # Separate into Priority and Rotating groups
        sorted_scannable = sorted(scannable, key=get_priority)
        
        # V107: Diversity Guard - Only allow 1 variant of a token per batch 
        # unless it is high priority (Warming/Watcher < 0)
        seen_tokens = set()
        final_candidates = []
        
        for p in sorted_scannable:
            token = p[0].split('/')[0] if '/' in p[0] else p[0]
            pri = get_priority(p)
            
            # If not priority, and we've already seen this token in this batch, skip
            if pri >= 0 and token in seen_tokens:
                continue
            
            final_candidates.append(p)
            seen_tokens.add(token)
            
        # Separate into final groups
        prio_group = [p for p in final_candidates if get_priority(p) < 0]
        rotate_group = [p for p in final_candidates if get_priority(p) >= 0]
        
        # V106: Fairness Reserve (60/40 Split)
        # Assuming we handle up to 5-8 units for the RPC batch
        limit = 5 # Default RPC batch limit
        prio_limit = max(1, int(limit * 0.6)) if rotate_group else limit
        
        final = prio_group[:prio_limit]
        final.extend(rotate_group[:(limit - len(final))])
        
        return final
    
    def flash_warm(self, pair: str, duration: int = 30) -> None:
        """
        V109: Force a pair into high-priority scan mode instantly.
        Triggered by Whale Probes or external signals.
        """
        now = time.time()
        self.warming_until[pair] = now + duration
        # Also mark as active to wake up the main loop if needed
        self.activity_detected[pair] = now
        Logger.info(f"🔥 [SCAN] FLASH WARM: {pair} for {duration}s")
        
    def update_pair(self, opp: SpreadOpportunity) -> None:
        """
        Update pair metrics after scanning.
        
        Calculates skip interval based on:
        1. Absolute spread level (low spread = skip more)
        2. Spread variance (stable = skip more)
        
        Also tracks near-miss status for priority sorting.
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
        
        # Track near-miss status for priority sorting
        from src.arbiter.core.near_miss_analyzer import NearMissAnalyzer
        metrics.last_status = NearMissAnalyzer.classify_status(opp.net_profit_usd)
        
        # V106: Refined Warming Trigger
        # If status is Actionable (NEAR/READY) or high volatility spike
        # Avoid warming high-spread pairs that are structurally unprofitable (FAR)
        is_actionable = metrics.last_status in ("VIABLE", "NEAR_MISS")
        is_promising = metrics.last_status in ("VIABLE", "NEAR_MISS", "WARM")
        
        if (is_promising and opp.spread_pct >= self.SPREAD_THRESHOLD) or \
           (metrics.spread_variance >= self.WARM_VOLATILITY_THRESHOLD) or \
           (is_actionable):
             self.warming_until[opp.pair] = now + self.WARM_DURATION_SECONDS
        else:
             # Cool down if no longer promising
             self.warming_until[opp.pair] = 0

        
        # Determine skip interval based on spread, variance, AND learned data
        skip_seconds = self._calculate_skip_interval(opp.pair, opp.spread_pct, metrics.spread_variance)
        metrics.skip_until = now + skip_seconds
    
    def _calculate_skip_interval(self, pair: str, spread_pct: float, variance: float) -> float:
        """
        Calculate how long to skip before next scan.
        
        Matrix logic:
        - High spread (>= 0.8%) + any variance → ALWAYS SCAN (hot target)
        - Medium spread (0.4-0.8%) + high variance → short skip
        - Medium spread (0.4-0.8%) + low variance → medium skip
        - Low spread (< 0.4%) + any variance → long skip (not worth it for $30)
        
        Learning adjustments:
        - Promoted pairs (high variance history) → reduce skip by 50%
        - Demoted pairs (high LIQ failure) → increase skip by 2x
        """
        # Base calculation
        if spread_pct >= self.HOT_SPREAD_PCT:
            base_skip = self.SKIP_HOT
        elif spread_pct >= self.WARM_SPREAD_PCT:
            if variance >= self.VARIANCE_HOT:
                base_skip = self.SKIP_HOT
            elif variance >= self.VARIANCE_WARM:
                base_skip = self.SKIP_WARM
            else:
                base_skip = self.SKIP_COOL
        else:
            # Low spread - deprioritize heavily
            if variance >= self.VARIANCE_HOT:
                base_skip = self.SKIP_COOL
            elif variance >= self.VARIANCE_COLD:
                base_skip = self.SKIP_COLD
            else:
                base_skip = self.SKIP_FROZEN
        
        # Learning-based adjustments
        if pair in self.promoted_pairs:
            return base_skip * 0.5  # Scan 2x faster for volatile pairs
        
        if pair in self.demoted_pairs:
            return min(base_skip * 2.0, 30.0)  # Scan 2x slower for LIQ-prone pairs
        
        return base_skip
    
    def update(self, spreads: List[SpreadOpportunity]) -> float:
        """
        Update global interval based on scan results.
        
        Also updates per-pair metrics for all scanned opportunities.
        
        Returns: Next global scan interval
        """
        now = time.time()
        
        # Periodically sync promotion/demotion from DB analytics
        self.sync_with_db()
        
        # Update per-pair metrics
        for opp in spreads:
            self.update_pair(opp)
        
        # Check for promising spreads (> threshold) for global fast mode
        hot_pairs = [s for s in spreads if s.spread_pct > self.SPREAD_THRESHOLD]
        
        if hot_pairs:
            self.last_spread_spike = now
            for s in hot_pairs:
                self.warming_until[s.pair] = now + self.WARM_DURATION_SECONDS
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
        """Return pairs sorted by recent activity (warming pairs first)."""
        now = time.time()
        return sorted(
            all_pairs, 
            key=lambda p: self.warming_until.get(p[0], 0), 
            reverse=True
        )
    
    def get_stats(self) -> Dict[str, any]:
        """Get scanner statistics for debugging."""
        now = time.time()
        active = sum(1 for m in self.pair_metrics.values() if now >= m.skip_until)
        skipped = len(self.pair_metrics) - active
        warming = sum(1 for t in self.warming_until.values() if now < t)
        
        return {
            "mode": self.mode_name,
            "interval": self.current_interval,
            "pairs_tracked": len(self.pair_metrics),
            "pairs_active": active,
            "pairs_skipped": skipped,
            "pairs_warming": warming,
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

