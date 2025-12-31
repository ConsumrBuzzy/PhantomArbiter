
"""
Log Harvester
=============
Relies on 'logsSubscribe' to capture Program-Level events at the speed of the validator.
Bypasses polling for instant detection of 'Graduation' and 'Token Birth' events.

V140 Update: Added FailureTracker for detecting swap failure spikes as
volatility signals. High failure rates indicate price pressure and
potential arbitrage opportunities.
"""

import json
import asyncio
import threading
import time
from typing import Callable, Dict, Optional, List
from collections import defaultdict
from dataclasses import dataclass, field
import websockets

from src.shared.system.logging import Logger
from src.shared.system.signal_bus import signal_bus, Signal, SignalType
from config.settings import Settings

# V140: Tracking institutional inflow
CIRCLE_CCTP_ID = "CCTP1BeS7S99Wf2f7C6YxG5iXqC8Zq5m2vGvXv5z"
WORMHOLE_BRIDGE_ID = "wormDTUZ2vDjnC7sbb6q9G2c474Y6G7J7J7J7J7J7J7"

# Program IDs
RAYDIUM_V4_ID = "675kPX9MCyJsD5ippTu671dKKkCtSE5v4RBmZJtHNv9v"
PUMPFUN_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
ORCA_WHIRLPOOL_ID = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
METEORA_DLMM_ID = "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"


@dataclass
class PoolFailureData:
    """Track failure data for a specific pool."""
    failures: List[float] = field(default_factory=list)  # Timestamps of failures
    last_success: float = 0.0  # Timestamp of last successful swap
    failure_count: int = 0
    recoil_detected: bool = False  # True when failures stop after spike
    

class FailureTracker:
    """
    The "Recoil Signal" Detector.
    
    When a pool has many failed swap attempts (slippage errors), it indicates:
    1. High demand / price pressure on that pool
    2. A "Latency War" is happening
    3. Price is about to break out
    
    We wait for the "Recoil" - when failures suddenly stop - then strike.
    """
    
    def __init__(
        self,
        window_seconds: float = 30.0,
        failure_threshold: int = 5,
        recoil_silence_seconds: float = 3.0,
    ):
        """
        Args:
            window_seconds: Time window to count failures
            failure_threshold: Failures in window to trigger alert
            recoil_silence_seconds: Silence duration to detect recoil
        """
        self.window_seconds = window_seconds
        self.failure_threshold = failure_threshold
        self.recoil_silence_seconds = recoil_silence_seconds
        
        # Pool tracking: pool_address -> PoolFailureData
        self._pools: Dict[str, PoolFailureData] = defaultdict(PoolFailureData)
        
        # Alert state (avoid spamming)
        self._last_alerts: Dict[str, float] = {}
        self._alert_cooldown = 10.0  # seconds
        
        # Statistics
        self.total_failures_tracked = 0
        self.alerts_emitted = 0
        self.recoils_detected = 0
        self.pools_under_pressure = 0
    
    def record_failure(self, pool_address: str, error_type: str = "unknown"):
        """Record a swap failure for a pool."""
        now = time.time()
        data = self._pools[pool_address]
        
        # Add timestamp
        data.failures.append(now)
        data.failure_count += 1
        self.total_failures_tracked += 1
        
        # Prune old failures
        cutoff = now - self.window_seconds
        data.failures = [t for t in data.failures if t > cutoff]
        
        # Check for spike
        if len(data.failures) >= self.failure_threshold:
            data.recoil_detected = False  # Reset recoil state
            self._maybe_emit_spike_alert(pool_address, len(data.failures), error_type)
    
    def record_success(self, pool_address: str):
        """Record a successful swap - potential recoil detection."""
        now = time.time()
        data = self._pools[pool_address]
        
        # Check if this is a recoil (success after spike)
        if data.failures and not data.recoil_detected:
            last_failure = max(data.failures) if data.failures else 0
            if now - last_failure > self.recoil_silence_seconds:
                # Silence after storm = recoil
                data.recoil_detected = True
                self.recoils_detected += 1
                self._emit_recoil_signal(pool_address)
        
        data.last_success = now
    
    def _maybe_emit_spike_alert(self, pool_address: str, failure_count: int, error_type: str):
        """Emit a failure spike alert if not on cooldown."""
        now = time.time()
        last_alert = self._last_alerts.get(pool_address, 0)
        
        if now - last_alert < self._alert_cooldown:
            return  # On cooldown
        
        self._last_alerts[pool_address] = now
        self.alerts_emitted += 1
        
        Logger.info(f"🔥 [FailureTracker] SPIKE: {pool_address[:8]}... | {failure_count} failures in {self.window_seconds}s")
        
        signal_bus.emit(Signal(
            type=SignalType.WHALE_ACTIVITY,  # Reuse for pressure signals
            source="FAILURE_TRACKER",
            data={
                "event": "FAILURE_SPIKE",
                "pool_address": pool_address,
                "failure_count": failure_count,
                "window_seconds": self.window_seconds,
                "error_type": error_type,
                "interpretation": "Price pressure detected - potential breakout",
            }
        ))
    
    def _emit_recoil_signal(self, pool_address: str):
        """Emit a recoil signal when failures stop after a spike."""
        Logger.info(f"⚡ [FailureTracker] RECOIL: {pool_address[:8]}... | Pressure released - strike window!")
        
        signal_bus.emit(Signal(
            type=SignalType.WHALE_ACTIVITY,
            source="FAILURE_TRACKER",
            data={
                "event": "RECOIL_DETECTED",
                "pool_address": pool_address,
                "interpretation": "Storm passed - price settled - opportunity window",
            }
        ))
    
    def get_hot_pools(self, min_failures: int = 3) -> List[Dict]:
        """Get pools currently under pressure."""
        now = time.time()
        hot = []
        
        for pool_address, data in self._pools.items():
            recent = [t for t in data.failures if now - t < self.window_seconds]
            if len(recent) >= min_failures:
                hot.append({
                    "pool": pool_address,
                    "failures": len(recent),
                    "recoil": data.recoil_detected,
                })
        
        self.pools_under_pressure = len(hot)
        return sorted(hot, key=lambda x: x["failures"], reverse=True)
    
    def get_stats(self) -> Dict:
        """Get tracker statistics."""
        return {
            "total_failures_tracked": self.total_failures_tracked,
            "alerts_emitted": self.alerts_emitted,
            "recoils_detected": self.recoils_detected,
            "pools_tracked": len(self._pools),
            "pools_under_pressure": self.pools_under_pressure,
        }


class LogHarvester:
    """
    Asynchronous Log Scanner.
    Connects to WSS and filters for key instruction logs.
    """
    
    def __init__(self):
        self.ws_url = Settings.HELIUS_WS_URL or "wss://api.mainnet-beta.solana.com"
        self.is_running = False
        self.reconnect_delay = 5
        self._thread = None
        
        # V140: Failure Tracker for volatility detection
        self.failure_tracker = FailureTracker(
            window_seconds=30.0,
            failure_threshold=5,
            recoil_silence_seconds=3.0,
        )
        
        # Stats
        self.stats = {
            "processed": 0,
            "graduations": 0,
            "launches": 0,
            "failures_detected": 0,
        }

    def start(self):
        """Start the harvester loop in a dedicated thread."""
        if self.is_running: return
        self.is_running = True
        self._thread = threading.Thread(target=self._run_forever, daemon=True, name="LogHarvester")
        self._thread.start()
        Logger.info("👁️ [HARVESTER] Started. Watching the Matrix.")

    def stop(self):
        self.is_running = False
        Logger.info("👁️ [HARVESTER] Stopped.")

    def _run_forever(self):
        """Thread wrapper for the async loop."""
        asyncio.run(self._connect_and_listen())

    async def _connect_and_listen(self):
        """Main WebSocket Loop."""
        while self.is_running:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    Logger.info(f"👁️ [HARVESTER] Connected to {self.ws_url}")
                    
                    # Subscribe to DEX programs for failure tracking
                    await self._subscribe(ws, RAYDIUM_V4_ID)
                    await self._subscribe(ws, ORCA_WHIRLPOOL_ID)
                    await self._subscribe(ws, METEORA_DLMM_ID)
                    
                    # V140: Subscribe to Bridge Programs
                    await self._subscribe(ws, CIRCLE_CCTP_ID)
                    await self._subscribe(ws, WORMHOLE_BRIDGE_ID)
                    
                    while self.is_running:
                        msg = await ws.recv()
                        await self._process_message(json.loads(msg))
                        
            except Exception as e:
                Logger.warning(f"👁️ [HARVESTER] Connection Lost: {e}. Reconnecting in {self.reconnect_delay}s...")
                await asyncio.sleep(self.reconnect_delay)

    async def _subscribe(self, ws, program_id: str):
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "logsSubscribe",
            "params": [
                {"mentions": [program_id]},
                {"commitment": "processed"} # Fastest possible commitment
            ]
        }
        await ws.send(json.dumps(payload))

    async def _process_message(self, data: dict):
        """Parse the raw log notification."""
        self.stats["processed"] += 1
        
        # Filter noise
        if "method" not in data or data["method"] != "logsNotification":
            return
            
        params = data.get("params", {})
        result = params.get("result", {})
        value = result.get("value", {})
        logs = value.get("logs", [])
        signature = value.get("signature", "unknown")
        err = value.get("err")  # V140: Check for transaction errors
        
        # V140: Track failures for volatility detection
        if err is not None:
            pool_address = self._extract_pool_from_logs(logs)
            if pool_address:
                error_type = self._classify_error(err, logs)
                self.failure_tracker.record_failure(pool_address, error_type)
                self.stats["failures_detected"] += 1
        
        # Analyze Logs for graduations
        is_raydium = False
        is_initialize2 = False
        
        for log in logs:
            if "Program 675kPX9MCyJsD5ippTu671dKKkCtSE5v4RBmZJtHNv9v invoke" in log:
                is_raydium = True
            
            # Key Indicator: "initialize2" -> Pool Creation
            if is_raydium and "initialize2" in log:
                is_initialize2 = True
                
            # If we see "success", fire signal
            if is_initialize2 and "Program 675kPX9MCyJsD5ippTu671dKKkCtSE5v4RBmZJtHNv9v success" in log:
                Logger.info(f"👁️ [HARVESTER] 🎓 GRADUATION: {signature}")
                self.stats["graduations"] += 1
                
                # Emit Signal
                signal_bus.emit(Signal(
                    type=SignalType.NEW_TOKEN,
                    source="HARVESTER",
                    data={
                        "event": "GRADUATION",
                        "signature": signature,
                        "program": "RAYDIUM"
                    }
                ))
                break
            
            # V140: Check for successful swaps (for recoil detection)
            if "swap" in log.lower() and "success" in log.lower() and err is None:
                pool_address = self._extract_pool_from_logs(logs)
                if pool_address:
                    self.failure_tracker.record_success(pool_address)
        
        # V140: Check for Bridge Inflows (Circle CCTP / Wormhole)
        is_bridge = False
        protocol = "UNKNOWN"
        amount_usd = 0.0
        
        for log in logs:
            if CIRCLE_CCTP_ID in log:
                is_bridge = True
                protocol = "CCTP"
                # Look for "Mint" or "DepositForBurn"
                if "mint" in log.lower() or "deposit" in log.lower():
                    amount_usd = self._extract_amount_from_logs(logs, "CCTP")
                break
            
            if WORMHOLE_BRIDGE_ID in log:
                is_bridge = True
                protocol = "WORMHOLE"
                if "complete" in log.lower() or "transfer" in log.lower():
                    amount_usd = self._extract_amount_from_logs(logs, "WORMHOLE")
                break
        
        if is_bridge and amount_usd > 0:
            Logger.info(f"👁️ [HARVESTER] 🌉 BRIDGE INFLOW: ${amount_usd:,.0f} via {protocol}")
            
            signal_bus.emit(Signal(
                type=SignalType.WHALE_ACTIVITY,
                source="HARVESTER",
                data={
                    "event": "BRIDGE_INFLOW",
                    "protocol": protocol,
                    "amount_usd": amount_usd,
                    "signature": signature,
                }
            ))
    
    def _extract_amount_from_logs(self, logs: List[str], protocol: str) -> float:
        """
        Heuristic to extract USD amount from bridge logs.
        On a real system, we'd parse the instruction data, but for 
        the "Whiff" strategy, we look for amount patterns in logs.
        """
        for log in logs:
            # Look for large numbers that might be lamports/units
            if "amount" in log.lower() or "value" in log.lower():
                import re
                numbers = re.findall(r'\d+', log)
                if numbers:
                    # Very rough heuristic: largest number normalized
                    raw_val = int(max(numbers, key=len))
                    if protocol == "CCTP":
                        return raw_val / 1_000_000.0  # USDC has 6 decimals
                    else:
                        return raw_val / 1_000_000_000.0  # Assume 9 decimals for SOL/ETH
        return 0.0
    
    def _extract_pool_from_logs(self, logs: List[str]) -> Optional[str]:
        """
        Extract pool address from logs.
        
        Looks for patterns like:
        - "Program <pool_address> invoke"
        - Account mentions in program logs
        """
        for log in logs:
            # Look for Raydium pool pattern
            if "675kPX9MCyJsD5ippTu671dKKkCtSE5v4RBmZJtHNv9v" in log:
                # Try to extract the first account after invoke
                # This is a heuristic - may need refinement
                parts = log.split()
                for i, part in enumerate(parts):
                    if len(part) == 44 and part.isalnum():
                        return part
        return None
    
    def _classify_error(self, err: dict, logs: List[str]) -> str:
        """Classify the type of transaction failure."""
        # Check for common error patterns
        err_str = str(err).lower()
        logs_str = " ".join(logs).lower()
        
        if "slippage" in logs_str or "exceeds" in logs_str:
            return "SLIPPAGE_EXCEEDED"
        elif "insufficient" in logs_str:
            return "INSUFFICIENT_FUNDS"
        elif "compute" in err_str:
            return "COMPUTE_EXCEEDED"
        else:
            return "UNKNOWN"
    
    def get_hot_pools(self) -> List[Dict]:
        """Get pools currently under failure pressure."""
        return self.failure_tracker.get_hot_pools()

