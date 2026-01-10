"""
Signal Aggregator
==================
Aggregates and ranks trading signals from all cartridges into a unified feed.

Provides the data layer for the Market Scanner dashboard view.
"""

import asyncio
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import deque
import heapq


class SignalSource(Enum):
    """Signal origin engine."""
    ARB = "arb"
    FUNDING = "funding"
    SCALP = "scalp"
    SYSTEM = "system"


class SignalUrgency(Enum):
    """Signal priority level."""
    CRITICAL = 3  # Immediate action required
    HIGH = 2      # Strong opportunity
    MEDIUM = 1    # Moderate signal
    LOW = 0       # Informational


@dataclass
class AggregatedSignal:
    """
    Unified signal format from any cartridge.
    """
    id: str = ""
    source: SignalSource = SignalSource.SYSTEM
    signal_type: str = ""  # "ARB_OPP", "SCALP_ENTRY", "FUNDING_ALERT", etc.
    symbol: str = ""
    direction: str = ""  # "long", "short", "neutral"
    
    # Value metrics
    value: float = 0.0  # Primary value (spread %, funding rate, sentiment)
    value_usd: float = 0.0  # Estimated profit in USD
    confidence: float = 0.0  # 0.0 - 1.0
    
    urgency: SignalUrgency = SignalUrgency.LOW
    reason: str = ""
    
    # Timing
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    
    # Extra context
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for WebSocket transmission."""
        return {
            "id": self.id,
            "source": self.source.value,
            "signal_type": self.signal_type,
            "symbol": self.symbol,
            "direction": self.direction,
            "value": self.value,
            "value_usd": self.value_usd,
            "confidence": self.confidence,
            "urgency": self.urgency.value,
            "reason": self.reason,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "metadata": self.metadata
        }
    
    @property
    def score(self) -> float:
        """Calculate composite score for ranking."""
        # Weighted: urgency * 100 + confidence * value
        return (self.urgency.value * 100) + (self.confidence * abs(self.value))
    
    @property
    def is_expired(self) -> bool:
        """Check if signal has expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at
    
    def __lt__(self, other):
        """For heap comparison (max-heap by score)."""
        return self.score > other.score  # Inverted for max-heap


class SignalAggregator:
    """
    Aggregates signals from all cartridges into a ranked feed.
    
    Features:
    - Rolling window of signals (last N minutes)
    - Priority ranking by urgency + value
    - Signal deduplication
    - Expiration handling
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, max_signals: int = 100, window_minutes: int = 30):
        if self._initialized:
            return
        
        self.max_signals = max_signals
        self.window_seconds = window_minutes * 60
        
        # Signal storage
        self._signals: deque = deque(maxlen=max_signals)
        self._signal_ids: set = set()
        
        # Stats
        self.total_received: int = 0
        self.last_update: float = 0.0
        
        self._initialized = True
    
    def add_signal(self, signal: AggregatedSignal) -> bool:
        """
        Add a new signal to the aggregator.
        
        Returns:
            True if signal was added, False if duplicate/expired
        """
        # Skip duplicates
        if signal.id in self._signal_ids:
            return False
        
        # Skip expired
        if signal.is_expired:
            return False
        
        # Generate ID if missing
        if not signal.id:
            signal.id = f"{signal.source.value}_{signal.symbol}_{int(time.time() * 1000)}"
        
        self._signals.append(signal)
        self._signal_ids.add(signal.id)
        self.total_received += 1
        self.last_update = time.time()
        
        # Cleanup old signal IDs
        self._cleanup_old_ids()
        
        return True
    
    def _cleanup_old_ids(self):
        """Remove IDs from signals no longer in deque."""
        current_ids = {s.id for s in self._signals}
        self._signal_ids = current_ids
    
    def get_top_signals(self, limit: int = 10, source: SignalSource = None) -> List[AggregatedSignal]:
        """
        Get top-ranked signals, optionally filtered by source.
        
        Returns:
            List of signals sorted by score (highest first)
        """
        now = time.time()
        cutoff = now - self.window_seconds
        
        # Filter active signals
        active = [
            s for s in self._signals
            if s.created_at >= cutoff and not s.is_expired
        ]
        
        # Filter by source if specified
        if source:
            active = [s for s in active if s.source == source]
        
        # Sort by score
        active.sort(key=lambda s: s.score, reverse=True)
        
        return active[:limit]
    
    def get_by_urgency(self, urgency: SignalUrgency) -> List[AggregatedSignal]:
        """Get all signals of a specific urgency level."""
        return [
            s for s in self._signals
            if s.urgency == urgency and not s.is_expired
        ]
    
    def get_scanner_snapshot(self) -> Dict[str, Any]:
        """
        Get complete scanner state for dashboard.
        
        Returns:
            Dict with categorized signals and stats
        """
        now = time.time()
        
        # Get top signals per source
        arb_signals = self.get_top_signals(5, SignalSource.ARB)
        funding_signals = self.get_top_signals(5, SignalSource.FUNDING)
        scalp_signals = self.get_top_signals(5, SignalSource.SCALP)
        
        # Overall top opportunities
        top_all = self.get_top_signals(10)
        
        # Critical alerts
        critical = self.get_by_urgency(SignalUrgency.CRITICAL)
        
        return {
            "timestamp": now,
            "total_active": len([s for s in self._signals if not s.is_expired]),
            "last_update": self.last_update,
            
            # Top opportunities (heatmap data)
            "top_opportunities": [s.to_dict() for s in top_all],
            
            # Per-engine breakdown
            "by_source": {
                "arb": {
                    "count": len(arb_signals),
                    "signals": [s.to_dict() for s in arb_signals]
                },
                "funding": {
                    "count": len(funding_signals),
                    "signals": [s.to_dict() for s in funding_signals]
                },
                "scalp": {
                    "count": len(scalp_signals),
                    "signals": [s.to_dict() for s in scalp_signals]
                }
            },
            
            # Urgent items
            "critical_alerts": [s.to_dict() for s in critical],
            
            # Stats
            "stats": {
                "total_received": self.total_received,
                "arb_count": len([s for s in self._signals if s.source == SignalSource.ARB]),
                "funding_count": len([s for s in self._signals if s.source == SignalSource.FUNDING]),
                "scalp_count": len([s for s in self._signals if s.source == SignalSource.SCALP])
            }
        }
    
    def clear(self):
        """Clear all signals."""
        self._signals.clear()
        self._signal_ids.clear()


# ═══════════════════════════════════════════════════════════════
# SIGNAL CONVERTERS (Transform raw signals to AggregatedSignal)
# ═══════════════════════════════════════════════════════════════

def convert_arb_signal(data: Dict[str, Any]) -> AggregatedSignal:
    """Convert ARB_OPP signal to aggregated format."""
    profit_pct = data.get("profit_pct", 0)
    
    urgency = SignalUrgency.LOW
    if profit_pct > 2.0:
        urgency = SignalUrgency.CRITICAL
    elif profit_pct > 1.0:
        urgency = SignalUrgency.HIGH
    elif profit_pct > 0.5:
        urgency = SignalUrgency.MEDIUM
    
    return AggregatedSignal(
        source=SignalSource.ARB,
        signal_type="ARB_OPP",
        symbol=data.get("token", "???"),
        direction="neutral",
        value=profit_pct,
        value_usd=data.get("est_profit_sol", 0) * 150,  # Rough SOL->USD
        confidence=min(profit_pct / 3.0, 1.0),
        urgency=urgency,
        reason=f"Route: {data.get('route', '???')}",
        expires_at=time.time() + 30,  # Arb opps expire fast
        metadata={"route": data.get("route")}
    )


def convert_scalp_signal(data: Dict[str, Any]) -> AggregatedSignal:
    """Convert SCALP_SIGNAL to aggregated format."""
    confidence = data.get("confidence", 0)
    action = data.get("action", "HOLD")
    
    urgency = SignalUrgency.LOW
    if confidence > 0.9:
        urgency = SignalUrgency.HIGH
    elif confidence > 0.7:
        urgency = SignalUrgency.MEDIUM
    
    return AggregatedSignal(
        source=SignalSource.SCALP,
        signal_type="SCALP_SIGNAL",
        symbol=data.get("token", "???"),
        direction="long" if action == "BUY" else "short",
        value=confidence * 100,  # As percentage
        confidence=confidence,
        urgency=urgency,
        reason=data.get("signal", ""),
        expires_at=time.time() + 300,  # 5 min expiry
        metadata={"signal_type": data.get("signal")}
    )


def convert_funding_signal(data: Dict[str, Any]) -> AggregatedSignal:
    """Convert funding rate alert to aggregated format."""
    rate = data.get("funding_rate", 0)
    
    urgency = SignalUrgency.LOW
    if rate > 0.001:  # >0.1% per 8h
        urgency = SignalUrgency.HIGH
    elif rate > 0.0005:
        urgency = SignalUrgency.MEDIUM
    elif rate < -0.0005:
        urgency = SignalUrgency.CRITICAL  # Negative funding = danger
    
    return AggregatedSignal(
        source=SignalSource.FUNDING,
        signal_type="FUNDING_RATE",
        symbol=data.get("symbol", "SOL-PERP"),
        direction="short" if rate > 0 else "long",
        value=rate * 100,  # As percentage
        value_usd=rate * data.get("position_size", 0) * 150,
        confidence=0.8,
        urgency=urgency,
        reason=f"Funding: {rate:.4%}/8h",
        expires_at=time.time() + 3600,  # 1h expiry
        metadata={"rate_annual": rate * 3 * 365 * 100}
    )


# Global singleton
def get_aggregator() -> SignalAggregator:
    """Get the global signal aggregator instance."""
    return SignalAggregator()
