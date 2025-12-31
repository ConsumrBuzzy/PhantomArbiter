"""
WebSocketListener - Real-Time DEX Log Parsing (Rust Augmented)
==============================================================
V7.0.0: Integrating Rust WssAggregator (Phase 17.5).

Architecture:
- Rust WssAggregator handles "Race of the Nodes" (WSS connectivity)
- ProviderPool manages keys and rotation
- Python thread simply polls parsed events from shared memory
"""

import os
import time
import threading
from dotenv import load_dotenv

import phantom_core
from src.core.provider_pool import ProviderPool

env_path = os.path.join(os.path.dirname(__file__), "../../.env")
load_dotenv(env_path)

# Program IDs
RAYDIUM_AMM_PROGRAM = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
ORCA_WHIRLPOOLS_PROGRAM = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
RAYDIUM_CLMM_PROGRAM = "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

WSS_DEBUG = True


def wss_log(msg: str):
    if WSS_DEBUG:
        # Use Logger instead of print for better consistent formatting if available,
        # or fallback to labeled print
        print(f"   [WSS-RUST] {msg}")


class WebSocketListener:
    """
    V7.0.0: High-Performance Rust Aggregator Bridge.

    Replaces legacy asyncio/websockets loop with native Rust WssAggregator.
    Connects to 3-5 providers in parallel and deduplicates signals.
    """

    def __init__(self, price_cache, watched_mints: dict):
        self.price_cache = price_cache
        self.watched_mints = watched_mints
        self.symbol_to_mint = {v: k for k, v in watched_mints.items()}

        # Phase 17: Provider Pool
        self.provider_pool = ProviderPool()

        # Phase 17.5: Rust Aggregator
        # Channel size 5000 to absorb burst pressure
        self.aggregator = phantom_core.WssAggregator(channel_size=5000)

        # Loop control
        self.running = False
        self.thread = None
        self.poller_interval = 0.0001  # 100 microseconds (busy-wait style)

        # Stats
        self.stats = {
            "messages_received": 0,
            "swaps_detected": 0,
            "prices_updated": 0,
            "reconnects": 0,
            "connection_status": "disconnected",
            "raydium_swaps": 0,
            "orca_swaps": 0,
            "clmm_swaps": 0,
            "latency_stats": {},
        }

    def start(self):
        """Start the Rust WSS Aggregator and polling thread."""
        if self.running or self.aggregator.is_running():
            wss_log("Already running")
            return

        endpoints = self.provider_pool.get_wss_endpoints()
        if not endpoints:
            wss_log("⚠️ No WSS endpoints available via ProviderPool!")
            return

        wss_log(
            f"Starting Race with {len(endpoints)} nodes: {[e.split('//')[1].split('/')[0] for e in endpoints]}"
        )

        # Subscribe to key DEX interactions
        # We subscribe to logs for Raydium V4, CLMM, and Orca
        program_ids = [
            RAYDIUM_AMM_PROGRAM,
            ORCA_WHIRLPOOLS_PROGRAM,
            RAYDIUM_CLMM_PROGRAM,
        ]

        try:
            # Start Rust Aggregator (spawns tokio threads)
            self.aggregator.start(
                endpoints=endpoints, program_ids=program_ids, commitment="processed"
            )

            self.running = True
            self.stats["connection_status"] = "connected"

            # Start Python Poller Thread
            self.thread = threading.Thread(target=self._poll_loop, daemon=True)
            self.thread.start()

            wss_log("🚀 Rust Aggregator Online")

        except Exception as e:
            wss_log(f"CRITICAL: Failed to start aggregator: {e}")
            self.stats["connection_status"] = "error"

    def stop(self):
        """Stop aggregator and poller."""
        self.running = False
        try:
            self.aggregator.stop()
        except:
            pass
        self.stats["connection_status"] = "stopped"

    def _poll_loop(self):
        """
        High-frequency polling of the crossbeam channel.
        Since Rust handles network IO, this thread just dispatches events.
        """
        batch_size = 50

        while self.running:
            # Poll parsed events from Rust
            # poll_events returns list of WssEvent objects
            events = self.aggregator.poll_events(batch_size)

            if not events:
                # Slight sleep to yield GIL if queue empty
                time.sleep(0.001)
                continue

            for event in events:
                self._process_event(event)

    def _process_event(self, event):
        """
        Process a normalized WssEvent from Rust.

        Args:
            event: phantom_core.WssEvent
                .provider: str
                .slot: int
                .signature: str
                .logs: list[str]
        """
        self.stats["messages_received"] += 1
        self.stats["latency_stats"][event.provider] = event.latency_ms

        # Logs are already parsed list of strings
        logs = event.logs

        # Check for swap keywords
        # Rust might eventually filter this too
        is_swap = False
        dex = "OTHER"

        # Quick check first 5 logs contains standard swap signatures
        for log in logs[:10]:
            if "ray_log" in log:
                dex = "RAYDIUM"
                is_swap = True
                break
            if "Instruction: Swap" in log or "Instruction: SwapV2" in log:
                # Check program ID in logs usually appears before
                is_swap = True
                if not dex or dex == "OTHER":
                    # Infer logic
                    pass

        if not is_swap:
            # Broad check
            if any("Swap" in log for log in logs) or any("swap" in log for log in logs):
                is_swap = True

        if not is_swap:
            return

        self.stats["swaps_detected"] += 1

        if dex == "RAYDIUM":
            self.stats["raydium_swaps"] += 1
        else:
            # Check program IDs manually if not identified by log content "ray_log"
            logs_concat = "".join(logs)
            if RAYDIUM_CLMM_PROGRAM in logs_concat:
                self.stats["clmm_swaps"] += 1
                dex = "CLMM"
            elif ORCA_WHIRLPOOLS_PROGRAM in logs_concat:
                self.stats["orca_swaps"] += 1
                dex = "ORCA"

        # V22: Parse price if possible and update State (Flux)
        try:
            # Very simple heuristic extraction for Demo/V1
            # In production we'd use parsing of Transfer/Swap instructions
            # Here we just look for 'ray_log' or similar if available
            pass
        except:
            pass

        # Queue signature for Intelligence Scraper
        # This keeps the "Analyst" workflow alive
        try:
            # We use local import to avoid circular dependency
            from src.scraper.discovery.scrape_intelligence import (
                get_scrape_intelligence,
            )

            scraper = get_scrape_intelligence()
            scraper.add_signature(event.signature, dex=dex)
        except ImportError:
            pass  # Scraper not available
        except Exception:
            pass

        # V22: Trigger State Pulse for known mints (simulated for now if not parsed)
        # This ensures the Flux Gauge moves even without full parsing
        from src.shared.state.app_state import state

        # Randomly pick a watched mint to pulse if we can't parse real price yet
        # (Just to show activity in the dashboard as requested)
        if self.watched_mints and self.stats["swaps_detected"] % 5 == 0:
            import random

            target = random.choice(list(self.watched_mints.values()))
            # Update pulse with a dummy 'activity' signal or last known price
            # This is a signal that "data is flowing"
            state.update_stat(
                "wss_latency_ms",
                list(self.stats["latency_stats"].values())[-1]
                if self.stats["latency_stats"]
                else 0,
            )

        # V7.0.0: We do NOT fetch transactions here anymore.
        # This listener is strictly for signals (e.g. Scraper trigger or Price Cache invalidation)
        # Price updates are handled by dedicated Price Streamers now usually.

        # Periodic Stats Log
        if self.stats["swaps_detected"] % 1000 == 0:
            agg_stats = self.aggregator.get_stats()
            wss_log(
                f"📊 [RUST] {self.stats['swaps_detected']} swaps | "
                f"Rust Accepted: {agg_stats.messages_accepted} | "
                f"Dropped: {agg_stats.messages_dropped} | "
                f"Active: {agg_stats.active_connections}"
            )

    def get_stats(self) -> dict:
        """Combine Python and Rust stats."""
        base_stats = self.stats.copy()
        if hasattr(self, "aggregator"):
            rust_stats = self.aggregator.get_stats()
            base_stats["rust_accepted"] = rust_stats.messages_accepted
            base_stats["rust_dropped"] = rust_stats.messages_dropped
            base_stats["rust_active_conns"] = rust_stats.active_connections
        return base_stats

    def is_connected(self) -> bool:
        return (
            self.stats["connection_status"] == "connected"
            and self.aggregator.is_running()
        )

    def add_mint(self, mint: str, symbol: str):
        self.watched_mints[mint] = symbol
        self.symbol_to_mint[symbol] = mint

    def remove_mint(self, mint: str):
        symbol = self.watched_mints.pop(mint, None)
        if symbol:
            self.symbol_to_mint.pop(symbol, None)


def create_websocket_listener(price_cache, watched_mints: dict) -> WebSocketListener:
    return WebSocketListener(price_cache, watched_mints)
