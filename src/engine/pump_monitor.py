import time
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

        priority_queue.add(3, 'LOG', {'level': 'INFO', 'message': f"🔭 [PumpMonitor] Starting Pulse Watch on {self.program_id[:8]}..."})
        
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
                log_filters=["Complete"] 
            )
            self.is_running = True
            Logger.success("✅ [PumpMonitor] Aggregator Online (Filter: 'Complete')")
        except Exception as e:
            Logger.error(f"❌ [PumpMonitor] Failed to start aggregator: {e}")
            
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
            
            # Analyze logs for Mint info
            self._process_graduation(event)
            
    def _process_graduation(self, event):
        """Extract Mint and Alert."""
        # Find potential Mint address in logs
        # Logic: Look for "Initialize2" or other context, OR just find the first Base58 string that isn't the program ID
        # For now, we'll dump the logs to inspect structure in dev mode
        
        # Simple heuristic: The mint is often the 2nd account in the transaction or mentioned in logs
        # If we can't find it easily from logs, we might need a quick RPC fetch (async)
        # But 'Complete' event usually implies we should look at the transaction.
        
        Logger.info(f"🎓 [PumpMonitor] GRADUATION DETECTED! Sig: {event.signature}")
        
        # Extract potential mints from logs?
        # Pattern: "Program log: Mint: <ADDRESS>"
        mint = None
        for log in event.logs:
             # Example: "Program log: Mint: 845..."
             # We rely on specific Pump.fun log patterns
             m = re.search(r"Mint: ([1-9A-HJ-NP-Za-km-z]{32,44})", log)
             if m:
                 mint = m.group(1)
                 break
        
        if mint:
            priority_queue.add(1, 'LOG', {'level': 'SUCCESS', 'message': f"🚀 [PumpMonitor] BONDING CURVE COMPLETE: {mint} https://solscan.io/tx/{event.signature}"})
            # Trigger Signal Bus?
            # signal_bus.emit(SignalType.SCOUT, {'type': 'GRADUATION', 'mint': mint, 'source': 'PUMP_FUN'})
        else:
             # Fallback log
             priority_queue.add(2, 'LOG', {'level': 'INFO', 'message': f"⚠️ [PumpMonitor] Graduation event found (No Mint parsed). Sig: {event.signature}"})

    def stop(self):
        if self.aggregator:
            self.aggregator.stop()
        self.is_running = False
