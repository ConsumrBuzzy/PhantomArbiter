import re
from typing import Optional
from src.shared.system.logging import Logger
from src.shared.system.priority_queue import priority_queue
from config.settings import Settings
import phantom_core


class PumpFunMonitor:
    """
    Phase 6: Universal Discovery - Pump.fun Monitor.
    Tracks 'Complete' events on the Pump.fun bonding curve.
    """

    def __init__(self):
        self.aggregator: Optional[phantom_core.WssAggregator] = None
        self.program_id = Settings.LAUNCHPAD_PROGRAMS.get("PUMPFUN")
        self.is_running = False
        self.processed_sigs = set()

    def start(self):
        """Start the WSS Aggregator with 'Complete' filter."""
        if not self.program_id:
            Logger.error("🛑 [PumpMonitor] Pump.fun Program ID not found in Settings")
            return

        priority_queue.add(
            3,
            "LOG",
            {
                "level": "INFO",
                "message": f"🔭 [PumpMonitor] Starting Pulse Watch on {self.program_id[:8]}...",
            },
        )

        # Initialize Rust Aggregator with dedicated channel
        self.aggregator = phantom_core.WssAggregator(channel_size=5000)

        # WSS Endpoints (Use dedicated if available, else shared)
        # Note: We use the Helius/Atlas URI if configured, or default RPC
        endpoints = [Settings.RPC_URL.replace("https", "wss")]

        # KEY: Pass "Complete" as the filter
        # Only transactions with logs containing "Complete" will be sent to Python
        try:
            self.aggregator.start(
                endpoints=endpoints,
                program_ids=[self.program_id],
                commitment="processed",
                log_filters=["Complete"],
            )
            self.is_running = True
            Logger.success("✅ [PumpMonitor] Aggregator Online (Filter: 'Complete')")
        except Exception as e:
            Logger.error(f"❌ [PumpMonitor] Failed to start aggregator: {e}")

    def _process_graduation(self, event):
        """Extract Mint and Alert."""
        from src.shared.system.signal_bus import signal_bus, Signal, SignalType
        import asyncio
        
        # ... (Existing extraction logic) ...
        # Simplified for brevity in this replace call, utilizing existing logic structure
        
        Logger.info(f"🎓 [PumpMonitor] GRADUATION DETECTED! Sig: {event.signature}")

        mint = None
        for log in event.logs:
            m = re.search(r"Mint: ([1-9A-HJ-NP-Za-km-z]{32,44})", log)
            if m:
                mint = m.group(1)
                break
        
        if mint:
            # Emit "Graduation" Signal (Orange Flash)
            timestamp = asyncio.get_event_loop().time()
            signal_bus.emit(Signal(
                type=SignalType.MARKET_UPDATE,
                data={
                    "source": "PUMP_GRAD",
                    "symbol": "GRAD", # Label text
                    "token": mint,
                    "mint": mint,
                    "price": 0.0,
                    "timestamp": timestamp
                }
            ))

            priority_queue.add(
                1, "LOG",
                {"level": "SUCCESS", "message": f"🚀 [PumpMonitor] BONDING CURVE COMPLETE: {mint}"}
            )
        else:
            # Fallback log
            priority_queue.add(
                2,
                "LOG",
                {
                    "level": "INFO",
                    "message": f"⚠️ [PumpMonitor] Graduation event found (No Mint parsed). Sig: {event.signature}",
                },
            )

    async def start_monitoring(self, interval: float = 0.1):
        """Async polling loop for the Rust Aggregator."""
        import asyncio
        self.start() # Init Aggregator
        
        Logger.info("[PumpMonitor] 🔭 Rust-Accelerated Graduation Monitor Active")
        
        while self.is_running:
            try:
                # Poll events from Rust channel
                # We can run this frequently as it's just reading a queue
                await asyncio.to_thread(self.poll)
            except Exception as e:
                Logger.error(f"❌ [PumpMonitor] Poll Error: {e}")
                
            await asyncio.sleep(interval)

    def poll(self):
        """Poll for new graduation events."""
        if not self.is_running or not self.aggregator:
            return

        # Bulk poll
        events = self.aggregator.poll_events(50)
        for event in events:
            if event.signature in self.processed_sigs:
                continue

            self.processed_sigs.add(event.signature)
            self._process_graduation(event)
            
            # Keep set size managed
            if len(self.processed_sigs) > 10000:
                self.processed_sigs.clear()

    def stop(self):
        if self.aggregator:
            self.aggregator.stop()
        self.is_running = False
