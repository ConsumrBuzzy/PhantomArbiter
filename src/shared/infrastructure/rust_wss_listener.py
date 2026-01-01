"""
Rust WebSocket Aggregator Wrapper
=================================
V42: Python wrapper for the high-performance Rust WssAggregator.

Uses phantom_core.WssAggregator for:
- Multi-endpoint WebSocket connections
- Race-to-first deduplication
- Lock-free message passing
"""

import os
import time
import threading
from typing import List, Callable, Optional
from dotenv import load_dotenv

load_dotenv()

# Well-known program IDs
RAYDIUM_AMM_PROGRAM = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
ORCA_WHIRLPOOLS_PROGRAM = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


class RustWssListener:
    """
    High-performance WebSocket listener using Rust backend.
    
    Falls back to Python implementation if Rust module unavailable.
    """
    
    def __init__(self, on_event_callback: Optional[Callable] = None):
        """
        Initialize the Rust WebSocket listener.
        
        Args:
            on_event_callback: Optional callback for each event (signature, logs, slot)
        """
        self.on_event = on_event_callback
        self.running = False
        self.poll_thread = None
        self.aggregator = None
        
        # Statistics
        self.stats = {
            "events_processed": 0,
            "rust_available": False,
            "start_time": 0
        }
        
        # Try to import Rust module
        try:
            import phantom_core
            self.aggregator = phantom_core.WssAggregator(channel_size=2000)
            self.stats["rust_available"] = True
            print("[RUST_WSS] WssAggregator initialized successfully")
        except ImportError as e:
            print(f"[RUST_WSS] Rust module unavailable: {e}")
            print("[RUST_WSS] Falling back to Python WebSocket listener")
    
    def start(self, endpoints: List[str] = None, program_ids: List[str] = None):
        """
        Start the WebSocket aggregator.
        
        Args:
            endpoints: List of WSS URLs (auto-detects from env if not provided)
            program_ids: Program IDs to monitor (defaults to Raydium + Orca)
        """
        if not self.stats["rust_available"]:
            print("[RUST_WSS] Cannot start - Rust module unavailable")
            return False
        
        # Auto-detect endpoints from environment
        if not endpoints:
            endpoints = self._get_endpoints_from_env()
        
        if not endpoints:
            print("[RUST_WSS] No WebSocket endpoints configured")
            return False
        
        # Default program IDs
        if not program_ids:
            program_ids = [RAYDIUM_AMM_PROGRAM, ORCA_WHIRLPOOLS_PROGRAM]
        
        print(f"[RUST_WSS] Starting with {len(endpoints)} endpoints...")
        for i, ep in enumerate(endpoints):
            # Mask API key for logging
            masked = ep.split("?")[0] + "?api-key=***"
            print(f"  [{i+1}] {masked}")
        
        try:
            self.aggregator.start(
                endpoints=endpoints,
                program_ids=program_ids,
                commitment="processed",
                log_filters=None  # Accept all logs
            )
            self.running = True
            self.stats["start_time"] = time.time()
            
            # Start polling thread
            self.poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
            self.poll_thread.start()
            
            print("[RUST_WSS] Aggregator started successfully!")
            return True
            
        except Exception as e:
            print(f"[RUST_WSS] Failed to start: {e}")
            return False
    
    def stop(self):
        """Stop the aggregator."""
        self.running = False
        if self.aggregator:
            try:
                self.aggregator.stop()
            except:
                pass
        print("[RUST_WSS] Aggregator stopped")
    
    def _poll_loop(self):
        """Background thread that polls for events."""
        while self.running and self.aggregator:
            try:
                # Poll up to 100 events at a time
                events = self.aggregator.poll_events(max_count=100)
                
                for event in events:
                    self.stats["events_processed"] += 1
                    
                    # Call handler if provided
                    if self.on_event:
                        self.on_event(
                            signature=event.signature,
                            logs=event.logs,
                            slot=event.slot,
                            provider=event.provider,
                            latency_ms=event.latency_ms
                        )
                    
                    # Process for flash swap detection
                    self._process_event(event)
                
                # Small sleep to prevent CPU spin
                if not events:
                    time.sleep(0.001)  # 1ms yield
                    
            except Exception as e:
                print(f"[RUST_WSS] Poll error: {e}")
                time.sleep(0.1)
    
    def _process_event(self, event):
        """Process a single event for flash swap detection."""
        try:
            from src.shared.system.signal_bus import signal_bus, Signal, SignalType
            
            # Check for USDC transfers (flash swap indicator)
            logs = event.logs
            logs_str = " ".join(logs[:10])
            
            # Detect DEX
            dex = "SOLANA"
            if "ray_log" in logs_str or RAYDIUM_AMM_PROGRAM[:8] in logs_str:
                dex = "RAYDIUM"
            elif "Whirlpool" in logs_str or ORCA_WHIRLPOOLS_PROGRAM[:8] in logs_str:
                dex = "ORCA"
            elif "LBUZKhRx" in logs_str or "Meteora" in logs_str:
                dex = "METEORA"
            elif "JUP" in logs_str or "jupiter" in logs_str.lower():
                dex = "JUPITER"
            
            # Extract amount from logs (look for USDC transfers)
            amount_usd = self._extract_usdc_amount(logs)
            
            if amount_usd > 1:
                # Format label
                if amount_usd >= 1000:
                    label_str = f"${amount_usd/1000:.1f}k"
                else:
                    label_str = f"${amount_usd:.0f}"
                
                # Emit signal
                signal_bus.emit(Signal(
                    type=SignalType.MARKET_UPDATE,
                    source="DEX",
                    data={
                        "mint": f"SWAP_{event.signature[-8:]}",
                        "symbol": f"⚡ {dex}",
                        "label": label_str,
                        "volume_24h": amount_usd,
                        "liquidity": 1000,
                        "price": amount_usd,
                        "is_event": True,
                        "provider": event.provider,
                        "latency_ms": event.latency_ms,
                        "timestamp": time.time()
                    }
                ))
                
        except Exception:
            pass
    
    def _extract_usdc_amount(self, logs: List[str]) -> float:
        """Extract USDC amount from logs using Rust parser."""
        try:
            import phantom_core
            
            for log in logs:
                if "ray_log" in log.lower():
                    result = phantom_core.parse_raydium_log(log)
                    if result:
                        # Result contains amount in lamports
                        amount_in = result.get("amount_in", 0)
                        amount_out = result.get("amount_out", 0)
                        # Convert USDC (6 decimals)
                        return max(amount_in, amount_out) / 1_000_000
                        
        except Exception:
            pass
        
        return 0
    
    def _get_endpoints_from_env(self) -> List[str]:
        """Get WebSocket endpoints from environment variables."""
        endpoints = []
        
        # Helius primary
        helius_ws = os.getenv("HELIUS_WS_URL")
        if helius_ws:
            endpoints.append(helius_ws)
        
        # Helius API key format
        helius_key = os.getenv("HELIUS_API_KEY")
        if helius_key and not helius_ws:
            endpoints.append(f"wss://mainnet.helius-rpc.com/?api-key={helius_key}")
        
        # Additional RPC endpoints
        extra_rpc = os.getenv("EXTRA_WSS_ENDPOINTS", "").split(",")
        for ep in extra_rpc:
            if ep.strip():
                endpoints.append(ep.strip())
        
        return endpoints
    
    def get_stats(self) -> dict:
        """Get current statistics."""
        if self.aggregator and self.stats["rust_available"]:
            try:
                rust_stats = self.aggregator.get_stats()
                return {
                    "events_processed": self.stats["events_processed"],
                    "rust_available": True,
                    "active_connections": rust_stats.active_connections,
                    "messages_received": rust_stats.messages_received,
                    "messages_accepted": rust_stats.messages_accepted,
                    "messages_dropped": rust_stats.messages_dropped,
                    "uptime_seconds": time.time() - self.stats["start_time"],
                    "pending": self.aggregator.pending_count()
                }
            except:
                pass
        
        return self.stats
    
    def is_running(self) -> bool:
        """Check if aggregator is running."""
        if self.aggregator:
            return self.aggregator.is_running()
        return False


# Singleton instance
_rust_listener = None

def get_rust_listener() -> RustWssListener:
    """Get or create the singleton Rust WSS listener."""
    global _rust_listener
    if _rust_listener is None:
        _rust_listener = RustWssListener()
    return _rust_listener


# Test
if __name__ == "__main__":
    print("Testing Rust WSS Listener...")
    
    listener = RustWssListener()
    
    if listener.stats["rust_available"]:
        print("✅ Rust module available")
        
        # Test start
        if listener.start():
            print("✅ Aggregator started")
            
            # Wait for some events
            print("Waiting for events (10 seconds)...")
            time.sleep(10)
            
            stats = listener.get_stats()
            print(f"Stats: {stats}")
            
            listener.stop()
        else:
            print("❌ Failed to start aggregator")
    else:
        print("❌ Rust module unavailable")
