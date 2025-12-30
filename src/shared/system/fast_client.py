
"""
V50.0 FastClient: The "Fast-Path" Bridge
========================================
Wraps the Rust `WssAggregator` to provide high-performance,
low-latency event streaming to the Python engine.

Architecture:
- Rust: Handles WSS connections, ping/pong, and JSON parsing in a background thread.
- Python: Polls the Rust channel via FFI (no GIL blocking on network).
"""

import asyncio
import logging
import time
from typing import List, AsyncGenerator, Optional

try:
    import phantom_core
    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False
    # Mock for development without compiled extension
    class MockWssAggregator:
        def __init__(self, size): pass
        def start(self, eps, pids, level): pass
        def stop(self): pass
        def poll_events(self, count): return []
        def is_running(self): return False

from src.shared.system.logging import Logger

class FastClient:
    """
    High-performance WSS Client using Rust backend.
    """
    
    def __init__(self, endpoints: List[str], channel_size: int = 10000):
        self.endpoints = endpoints
        self.channel_size = channel_size
        self.aggregator = None
        self._running = False
        
        if not RUST_AVAILABLE:
            Logger.warning("🦀 [FastClient] Rust extension not found! Using Mock.")
        else:
            Logger.info("🦀 [FastClient] Rust Extension Detected. Engaging Fast-Path.")

    def start(self, program_ids: List[str], commitment: str = "processed"):
        """Start the Rust WSS Aggregator."""
        if not RUST_AVAILABLE:
            self.aggregator = MockWssAggregator(self.channel_size)
            return

        try:
            self.aggregator = phantom_core.WssAggregator(self.channel_size)
            self.aggregator.start(self.endpoints, program_ids, commitment)
            self._running = True
            Logger.info(f"🚀 [FastClient] Started WSS Aggregator on {len(self.endpoints)} endpoints.")
        except Exception as e:
            Logger.error(f"❌ [FastClient] Failed to start Rust Aggregator: {e}")
            self.aggregator = None

    def stop(self):
        """Stop the aggregator."""
        if self.aggregator and self._running:
            try:
                self.aggregator.stop()
                self._running = False
                Logger.info("🛑 [FastClient] WSS Aggregator stopped.")
            except Exception as e:
                Logger.error(f"⚠️ [FastClient] Error stopping aggregator: {e}")

    async def events(self, poll_interval: float = 0.01) -> AsyncGenerator:
        """
        Async generator yielding events from the Rust backend.
        Polls the shared memory channel efficiently.
        """
        if not self.aggregator:
            return

        while self._running:
            # Poll Rust (non-blocking)
            # Fetch up to 50 events at a time to minimize FFI overhead
            events = self.aggregator.poll_events(50)
            
            if events:
                for event in events:
                    yield event
            else:
                # Sleep briefly if no events to yield CPU to other tasks
                await asyncio.sleep(poll_interval)
                
    def get_stats(self):
        if self.aggregator and RUST_AVAILABLE:
            return self.aggregator.get_stats()
        return None
