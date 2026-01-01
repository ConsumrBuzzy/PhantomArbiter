"""
LatencyMonitor - The Pulse Checker
===================================
Tracks the critical "Tick-to-Trade" latency across the pipeline.
"""

import time
import statistics
from collections import deque
from typing import Dict, List


class LatencyMonitor:
    """
    Sub-millisecond latency tracker for the Unified Core.
    
    Metrics:
    - Ingress Latency: Time from WSS event/timestamp (if available) to Python receipt.
    - Pipeline Latency: Time from Ingress to Logic Trigger.
    - Execution Latency: Time from Logic Trigger to Trade Submission.
    """

    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self.ingress_deltas = deque(maxlen=window_size)
        self.process_times = deque(maxlen=window_size)
        
        # Temp store for in-flight events
        self._pending: Dict[str, float] = {}

    def record_ingress(self, event_ts_ms: int):
        """
        Record the arrival of a WSS event.
        Args:
            event_ts_ms: The timestamp provided by the WSS feed (in ms).
        """
        now_ms = time.time() * 1000
        delta = max(0, now_ms - event_ts_ms)
        self.ingress_deltas.append(delta)

    def mark_start(self, event_id: str):
        """Mark start of processing for a specific event."""
        self._pending[event_id] = time.time() * 1000

    def mark_end(self, event_id: str) -> float:
        """Mark end of processing. Returns duration in ms."""
        start = self._pending.pop(event_id, None)
        if start:
            duration = (time.time() * 1000) - start
            self.process_times.append(duration)
            return duration
        return 0.0

    def get_stats(self) -> Dict[str, float]:
        """Get summary statistics."""
        def safe_mean(d): return statistics.mean(d) if d else 0.0
        def safe_max(d): return max(d) if d else 0.0

        return {
            "ingress_avg_ms": safe_mean(self.ingress_deltas),
            "ingress_max_ms": safe_max(self.ingress_deltas),
            "process_avg_ms": safe_mean(self.process_times),
            "process_max_ms": safe_max(self.process_times),
            "samples": len(self.ingress_deltas)
        }
