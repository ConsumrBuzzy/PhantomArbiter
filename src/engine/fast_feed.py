import time
import logging
from typing import List, Optional, Callable
try:
    from phantom_core import WssAggregator, WssEvent, WssStats
except ImportError:
    # Fallback for when the extension isn't built yet (during dev)
    WssAggregator = None
    WssEvent = None
    WssStats = None

from src.system.rpc_pool import RpcPool
from src.core.constants import RAYDIUM_V4_PROGRAM_ID, ORCA_WHIRLPOOL_PROGRAM_ID

logger = logging.getLogger(__name__)

class FastFeed:
    """
    High-Performance Data Feed using Rust WssAggregator.
    Replaces legacy WebSocketListener for the 'Narrow Path' strategy.
    
    Bridge:
    [RPC Providers] -> (Rust Aggregator) -> [FastFeed.poll()] -> (Python Arb Engine)
    """

    def __init__(self, callback: Callable[[List['WssEvent']], None]):
        """
        Args:
            callback: Function to call with a batch of new events.
        """
        if WssAggregator is None:
            logger.error("❌ phantom_core extension not found! FastFeed disabled.")
            self.aggregator = None
            return

        self.aggregator = WssAggregator(channel_size=5000)
        self.callback = callback
        self.is_running = False
        
        # Stats
        self.last_poll_time = 0
        self.events_processed = 0

    def start(self, rpc_endpoints: List[str] = None):
        """
        Start the Rust Aggregator background threads.
        """
        if not self.aggregator:
            return

        if rpc_endpoints is None:
            # Auto-discover from RpcPool if not provided
            # We filter for WSS endpoints
            # Assuming RpcPool has a method or we config it
            # For now, use a hardcoded safe default or config
            from config.settings import RPC_WSS_ENDPOINTS
            rpc_endpoints = RPC_WSS_ENDPOINTS

        logger.info(f"🚀 Starting FastFeed with {len(rpc_endpoints)} endpoints...")
        
        programs = [
            RAYDIUM_V4_PROGRAM_ID,
            ORCA_WHIRLPOOL_PROGRAM_ID
        ]
        
        # Rust start method: endpoints, program_ids, commitment, log_filters
        # We focus on "Swap" logs for filtering to reduce noise
        filters = [
            "Instruction: Swap", 
            "Instruction: TwoHopSwap", 
            "ray_log"
        ]

        try:
            self.aggregator.start(
                endpoints=rpc_endpoints,
                program_ids=programs,
                commitment="processed",
                log_filters=filters
            )
            self.is_running = True
            logger.info("✅ FastFeed Aggregator Online.")
        except Exception as e:
            logger.critical(f"❌ Failed to start Rust Aggregator: {e}")

    def stop(self):
        if self.aggregator and self.is_running:
            self.aggregator.stop()
            self.is_running = False
            logger.info("🛑 FastFeed Stopped.")

    def tick(self):
        """
        Must be called frequently (e.g. every 1ms or in tight loop).
        Polls Rust channel and dispatches events.
        """
        if not self.is_running or not self.aggregator:
            return

        # Poll strictly limited batch to avoid blocking the main loop too long
        events = self.aggregator.poll_events(max_count=200)
        
        if events:
            self.events_processed += len(events)
            self.callback(events)

    def get_stats(self) -> dict:
        if not self.aggregator:
            return {}
        
        rust_stats = self.aggregator.get_stats()
        return {
            "active_conns": rust_stats.active_connections,
            "msgs_recv": rust_stats.messages_received,
            "msgs_accepted": rust_stats.messages_accepted,
            "msgs_dropped": rust_stats.messages_dropped,
            "py_processed": self.events_processed
        }
