"""
Trend Engine - Tick to OHLCV Aggregation.

Converts raw price ticks into 1-minute OHLCV delta blocks.
Implements the "Bellows" compression strategy.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from collections import defaultdict


@dataclass
class DeltaBlock:
    """
    A single 1-minute OHLCV delta block.
    
    Represents the compressed state of a token for one time window.
    """
    timestamp: float  # Window start timestamp
    mint: str
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    liquidity: float = 0.0
    tick_count: int = 0
    sequence: int = 0  # For gap detection
    
    def to_jsonl(self) -> str:
        """Convert to JSONL format (compact)."""
        import json
        return json.dumps({
            "ts": int(self.timestamp),
            "mint": self.mint[:12],  # Truncate for space
            "sym": self.symbol,
            "o": round(self.open, 8),
            "h": round(self.high, 8),
            "l": round(self.low, 8),
            "c": round(self.close, 8),
            "v": round(self.volume, 2),
            "liq": round(self.liquidity, 2),
            "n": self.tick_count,
            "seq": self.sequence,
        }, separators=(",", ":"))
    
    @classmethod
    def from_jsonl(cls, line: str) -> "DeltaBlock":
        """Parse from JSONL format."""
        import json
        d = json.loads(line)
        return cls(
            timestamp=float(d["ts"]),
            mint=d["mint"],
            symbol=d.get("sym", ""),
            open=d["o"],
            high=d["h"],
            low=d["l"],
            close=d["c"],
            volume=d.get("v", 0),
            liquidity=d.get("liq", 0),
            tick_count=d.get("n", 0),
            sequence=d.get("seq", 0),
        )
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp,
            "mint": self.mint,
            "symbol": self.symbol,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "liquidity": self.liquidity,
            "tick_count": self.tick_count,
            "sequence": self.sequence,
        }


@dataclass
class WindowState:
    """Accumulator for a single token's current window."""
    mint: str
    symbol: str
    window_start: float  # Start of current 1-minute window
    open: float = 0.0
    high: float = 0.0
    low: float = float("inf")
    close: float = 0.0
    volume: float = 0.0
    liquidity: float = 0.0
    tick_count: int = 0
    last_price: float = 0.0  # For zero-delta detection


class TrendEngine:
    """
    Aggregates raw ticks into 1-minute OHLCV delta blocks.
    
    Features:
    - 1-minute windowing
    - Zero-change suppression (skip if price unchanged)
    - Sequence numbering for gap detection
    - Memory-efficient (only tracks active tokens)
    """
    
    # Window size in seconds
    WINDOW_SIZE = 60
    
    # Minimum price change to emit delta (0.01% threshold)
    ZERO_DELTA_THRESHOLD = 0.0001
    
    def __init__(self) -> None:
        self._windows: Dict[str, WindowState] = {}  # mint -> WindowState
        self._sequence = 0
        self._pending_deltas: List[DeltaBlock] = []
        self._last_flush = time.time()
        
        # Stats
        self._ticks_received = 0
        self._deltas_emitted = 0
        self._deltas_suppressed = 0
    
    def add_tick(
        self,
        mint: str,
        symbol: str,
        price: float,
        volume: float = 0.0,
        liquidity: float = 0.0,
        timestamp: Optional[float] = None,
    ) -> Optional[DeltaBlock]:
        """
        Add a price tick for aggregation.
        
        Returns a DeltaBlock if the previous window was closed.
        """
        if price <= 0:
            return None
        
        ts = timestamp or time.time()
        self._ticks_received += 1
        
        # Calculate window start (floor to minute)
        window_start = (int(ts) // self.WINDOW_SIZE) * self.WINDOW_SIZE
        
        # Get or create window
        window = self._windows.get(mint)
        
        closed_delta: Optional[DeltaBlock] = None
        
        if window is None:
            # First tick for this token
            window = WindowState(
                mint=mint,
                symbol=symbol,
                window_start=window_start,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=volume,
                liquidity=liquidity,
                tick_count=1,
                last_price=price,
            )
            self._windows[mint] = window
            
        elif window_start > window.window_start:
            # New window - close previous one
            closed_delta = self._close_window(window)
            
            # Start new window
            window.window_start = window_start
            window.open = price
            window.high = price
            window.low = price
            window.close = price
            window.volume = volume
            window.liquidity = liquidity
            window.tick_count = 1
            
        else:
            # Same window - update aggregates
            window.high = max(window.high, price)
            window.low = min(window.low, price)
            window.close = price
            window.volume += volume
            window.liquidity = liquidity  # Latest
            window.tick_count += 1
        
        return closed_delta
    
    def _close_window(self, window: WindowState) -> Optional[DeltaBlock]:
        """
        Close a window and emit delta block.
        
        Returns None if zero-delta suppression applies.
        """
        # Zero-delta suppression: skip if price unchanged
        if window.last_price > 0:
            price_change = abs(window.close - window.last_price) / window.last_price
            if price_change < self.ZERO_DELTA_THRESHOLD:
                self._deltas_suppressed += 1
                window.last_price = window.close
                return None
        
        window.last_price = window.close
        
        # Emit delta
        self._sequence += 1
        delta = DeltaBlock(
            timestamp=window.window_start,
            mint=window.mint,
            symbol=window.symbol,
            open=window.open,
            high=window.high,
            low=window.low,
            close=window.close,
            volume=window.volume,
            liquidity=window.liquidity,
            tick_count=window.tick_count,
            sequence=self._sequence,
        )
        
        self._pending_deltas.append(delta)
        self._deltas_emitted += 1
        
        return delta
    
    def flush_all(self) -> List[DeltaBlock]:
        """
        Force-close all open windows and return deltas.
        
        Called on shutdown to ensure no data loss.
        """
        deltas = []
        
        for window in self._windows.values():
            delta = self._close_window(window)
            if delta:
                deltas.append(delta)
        
        # Also return any pending
        deltas.extend(self._pending_deltas)
        self._pending_deltas = []
        self._last_flush = time.time()
        
        return deltas
    
    def get_pending_deltas(self) -> List[DeltaBlock]:
        """Get and clear pending delta blocks."""
        deltas = self._pending_deltas
        self._pending_deltas = []
        return deltas
    
    def check_window_expiry(self) -> List[DeltaBlock]:
        """
        Check for expired windows and close them.
        
        Should be called periodically (e.g., every second).
        """
        now = time.time()
        current_window = (int(now) // self.WINDOW_SIZE) * self.WINDOW_SIZE
        
        closed = []
        
        for window in self._windows.values():
            if window.window_start < current_window:
                delta = self._close_window(window)
                if delta:
                    closed.append(delta)
                # Reset window
                window.window_start = current_window
                window.open = window.close
                window.high = window.close
                window.low = window.close
                window.volume = 0
                window.tick_count = 0
        
        return closed
    
    def get_stats(self) -> Dict:
        """Get engine statistics."""
        return {
            "ticks_received": self._ticks_received,
            "deltas_emitted": self._deltas_emitted,
            "deltas_suppressed": self._deltas_suppressed,
            "active_windows": len(self._windows),
            "pending_deltas": len(self._pending_deltas),
            "sequence": self._sequence,
            "compression_ratio": (
                self._ticks_received / max(self._deltas_emitted, 1)
            ),
        }
    
    def get_sequence(self) -> int:
        """Get current sequence number."""
        return self._sequence


# Global instance
_engine: Optional[TrendEngine] = None


def get_trend_engine() -> TrendEngine:
    """Get or create the global TrendEngine instance."""
    global _engine
    if _engine is None:
        _engine = TrendEngine()
    return _engine
