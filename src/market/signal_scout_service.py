"""
SignalScoutService - The Unconventional Whiffs
===============================================
Layer A: Market Monitor - Asymmetric intelligence gathering.

Free-tier survival through "Whiff" detection:
- Signature polling (pre-transaction awareness)
- Liquidation log monitoring (Solend, Kamino, Marginfi)
- Failed transaction clustering (volatility detection)
- MEV bot activity detection

Design Philosophy:
    "Paid bots buy speed. Free bots buy intelligence."
    We detect the INTENT before the EFFECT hits the AMM.
"""

import asyncio
import time
from typing import Dict, List, Set, Optional, Callable
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum

from src.shared.system.logging import Logger
from src.shared.system.signal_bus import signal_bus, Signal, SignalType


class WhiffType(Enum):
    """Types of asymmetric signals."""
    LIQUIDATION = "LIQUIDATION"       # Lending protocol forced sell
    SIGNATURE_RACE = "SIGNATURE_RACE" # Fast bot activity detected
    FAILED_CLUSTER = "FAILED_CLUSTER" # High slippage volatility zone
    PRIORITY_FEE_SPIKE = "PRIORITY_FEE_SPIKE"  # Network congestion
    WHALE_INTENT = "WHALE_INTENT"     # Large wallet staging TX


@dataclass
class Whiff:
    """An asymmetric intelligence signal."""
    type: WhiffType
    mint: str
    source: str
    confidence: float  # 0.0 - 1.0
    direction: str  # "BULLISH", "BEARISH", "VOLATILE"
    magnitude: float  # Estimated impact (0.0 - 1.0)
    data: Dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    ttl_seconds: float = 30.0  # Whiffs expire quickly


@dataclass
class LiquidationEvent:
    """Parsed liquidation from lending protocol."""
    protocol: str  # SOLEND, KAMINO, MARGINFI
    collateral_mint: str
    debt_mint: str
    collateral_amount: float
    debt_amount: float
    liquidator: str
    timestamp: float


@dataclass
class FailedTxCluster:
    """Cluster of failed transactions indicating volatility."""
    program_id: str
    mint: str
    failed_count: int
    time_window_seconds: float
    avg_slippage_exceeded: float


class SignalScoutService:
    """
    The Unconventional Ears - Asymmetric intelligence gathering.
    
    Monitors "leading indicators" that appear before price moves:
    - Liquidation logs → Predictable sell pressure
    - Failed TX clusters → High volatility zone detected
    - Signature races → Fast bot activity incoming
    - Priority fee spikes → Network congestion ahead
    """
    
    # Known lending protocol program IDs
    LENDING_PROGRAMS = {
        "So1endDq2YkqhipRh3WViPa8hdiSpxWy6z3Z6tMCpAo": "SOLEND",
        "KLend2g3cP87fffoy8q1mQqGKjrxjC8boQo7AQnufHj": "KAMINO", 
        "MFv2hWf31Z9kbCa1snEPYctwafyhdvnV7FZnsebVacA": "MARGINFI",
    }
    
    # Known MEV/Arb bot wallets (sample - extend with actual data)
    KNOWN_FAST_BOTS: Set[str] = set()
    
    def __init__(self):
        # Whiff storage
        self._active_whiffs: Dict[str, List[Whiff]] = defaultdict(list)
        
        # Tracking state
        self._failed_tx_counts: Dict[str, List[float]] = defaultdict(list)
        self._signature_timestamps: Dict[str, float] = {}
        self._priority_fee_history: List[float] = []
        
        # Configuration
        self._failed_tx_window = 30.0  # seconds
        self._failed_tx_threshold = 5  # count to trigger
        self._fee_spike_threshold = 2.0  # 2x average
        
        # Callbacks
        self._whiff_callbacks: List[Callable[[Whiff], None]] = []
        
        self._running = False
        Logger.info("🔍 SignalScoutService initialized (Asymmetric Intel)")
    
    # =========================================================================
    # LIFECYCLE
    # =========================================================================
    
    def start(self) -> None:
        """Start listening for whiffs."""
        if self._running:
            return
        
        self._running = True
        Logger.info("👂 SignalScoutService starting whiff detection...")
        
        # Subscribe to relevant SignalBus events
        signal_bus.subscribe(SignalType.LOG_UPDATE, self._on_log_update)
        signal_bus.subscribe(SignalType.TX_FAILED, self._on_tx_failed)
        
        # Start background tasks
        asyncio.create_task(self._poll_priority_fees())
        
        Logger.info("✅ SignalScoutService listening for whiffs")
    
    def stop(self) -> None:
        """Stop listening."""
        self._running = False
        Logger.info("🛑 SignalScoutService stopped")
    
    # =========================================================================
    # WHIFF DETECTION
    # =========================================================================
    
    def detect_liquidation(self, log_data: dict) -> Optional[Whiff]:
        """
        Detect liquidation events from lending protocol logs.
        
        The Play: A liquidation creates immediate, predictable sell pressure.
        """
        program_id = log_data.get("program_id")
        if program_id not in self.LENDING_PROGRAMS:
            return None
        
        protocol = self.LENDING_PROGRAMS[program_id]
        logs = log_data.get("logs", [])
        
        # Parse liquidation from logs (protocol-specific)
        event = self._parse_liquidation_logs(protocol, logs)
        if not event:
            return None
        
        # Create whiff: Liquidation = BEARISH pressure on collateral token
        whiff = Whiff(
            type=WhiffType.LIQUIDATION,
            mint=event.collateral_mint,
            source=f"{protocol}_LIQUIDATION",
            confidence=0.85,  # High confidence - liquidation is confirmed
            direction="BEARISH",
            magnitude=min(1.0, event.collateral_amount / 10000),  # Normalize
            data={
                "protocol": protocol,
                "collateral_amount": event.collateral_amount,
                "debt_mint": event.debt_mint,
                "liquidator": event.liquidator,
            },
            ttl_seconds=60.0,  # Liquidation impact lasts ~1 minute
        )
        
        self._emit_whiff(whiff)
        return whiff
    
    def detect_failed_cluster(self, mint: str, program_id: str) -> Optional[Whiff]:
        """
        Detect clusters of failed transactions.
        
        The Angle: Multiple failed TXs on same route = high volatility zone.
        """
        now = time.time()
        
        # Track this failure
        key = f"{program_id}:{mint}"
        self._failed_tx_counts[key].append(now)
        
        # Prune old entries
        cutoff = now - self._failed_tx_window
        self._failed_tx_counts[key] = [
            t for t in self._failed_tx_counts[key] if t > cutoff
        ]
        
        count = len(self._failed_tx_counts[key])
        if count < self._failed_tx_threshold:
            return None
        
        # Cluster detected!
        whiff = Whiff(
            type=WhiffType.FAILED_CLUSTER,
            mint=mint,
            source=f"FAILED_TX_{program_id[:8]}",
            confidence=0.70,
            direction="VOLATILE",
            magnitude=min(1.0, count / 20),  # More failures = higher magnitude
            data={
                "program_id": program_id,
                "failed_count": count,
                "window_seconds": self._failed_tx_window,
            },
            ttl_seconds=30.0,  # Volatility zone is short-lived
        )
        
        self._emit_whiff(whiff)
        return whiff
    
    def detect_signature_race(self, signature: str, signer: str) -> Optional[Whiff]:
        """
        Detect fast bot activity via signature timing.
        
        The Play: Known fast bots send TXs before we see price impact.
        """
        if signer not in self.KNOWN_FAST_BOTS:
            return None
        
        # Fast bot activity detected
        whiff = Whiff(
            type=WhiffType.SIGNATURE_RACE,
            mint="UNKNOWN",  # We may not know the target yet
            source=f"FAST_BOT_{signer[:8]}",
            confidence=0.60,  # Medium - we don't know direction
            direction="VOLATILE",  # Fast bot = expect movement
            magnitude=0.5,
            data={
                "signature": signature,
                "signer": signer,
            },
            ttl_seconds=10.0,  # Very short TTL - race is immediate
        )
        
        self._emit_whiff(whiff)
        return whiff
    
    async def detect_priority_fee_spike(self) -> Optional[Whiff]:
        """
        Detect network congestion via priority fee analysis.
        
        The Angle: Fee spikes precede high-activity periods.
        """
        try:
            from src.shared.infrastructure.rpc_balancer import get_rpc_balancer
            rpc = get_rpc_balancer()
            
            # Get recent priority fees
            fees = await rpc.get_recent_prioritization_fees()
            if not fees:
                return None
            
            current_fee = fees[0].get("prioritizationFee", 0)
            self._priority_fee_history.append(current_fee)
            
            # Keep last 20 readings
            if len(self._priority_fee_history) > 20:
                self._priority_fee_history.pop(0)
            
            # Check for spike
            if len(self._priority_fee_history) < 5:
                return None
            
            avg_fee = sum(self._priority_fee_history[:-1]) / (len(self._priority_fee_history) - 1)
            if avg_fee <= 0:
                return None
            
            spike_ratio = current_fee / avg_fee
            if spike_ratio < self._fee_spike_threshold:
                return None
            
            # Fee spike detected
            whiff = Whiff(
                type=WhiffType.PRIORITY_FEE_SPIKE,
                mint="NETWORK",  # Network-wide
                source="FEE_MONITOR",
                confidence=0.75,
                direction="VOLATILE",
                magnitude=min(1.0, spike_ratio / 5),
                data={
                    "current_fee": current_fee,
                    "avg_fee": avg_fee,
                    "spike_ratio": spike_ratio,
                },
                ttl_seconds=60.0,
            )
            
            self._emit_whiff(whiff)
            return whiff
            
        except Exception as e:
            Logger.debug(f"Fee spike detection failed: {e}")
            return None
    
    # =========================================================================
    # WHIFF RETRIEVAL
    # =========================================================================
    
    def get_whiffs(self, mint: str = None, max_age: float = 30.0) -> List[Whiff]:
        """Get active whiffs for a mint (or all if None)."""
        now = time.time()
        result = []
        
        mints = [mint] if mint else list(self._active_whiffs.keys())
        
        for m in mints:
            whiffs = self._active_whiffs.get(m, [])
            for w in whiffs:
                age = now - w.timestamp
                if age <= min(max_age, w.ttl_seconds):
                    result.append(w)
        
        return result
    
    def get_market_heat(self, mint: str) -> float:
        """
        Get aggregated "market heat" score for a mint.
        
        Returns 0.0 (cold) to 1.0 (on fire).
        """
        whiffs = self.get_whiffs(mint)
        if not whiffs:
            return 0.0
        
        # Weight by confidence and magnitude
        heat = sum(w.confidence * w.magnitude for w in whiffs)
        return min(1.0, heat)
    
    def get_pressure(self, mint: str) -> Dict[str, float]:
        """
        Get directional pressure from whiffs.
        
        Returns {"bullish": 0.0-1.0, "bearish": 0.0-1.0, "volatile": 0.0-1.0}
        """
        whiffs = self.get_whiffs(mint)
        
        pressure = {"bullish": 0.0, "bearish": 0.0, "volatile": 0.0}
        
        for w in whiffs:
            key = w.direction.lower()
            if key in pressure:
                pressure[key] += w.confidence * w.magnitude
        
        # Normalize
        for key in pressure:
            pressure[key] = min(1.0, pressure[key])
        
        return pressure
    
    # =========================================================================
    # CALLBACKS
    # =========================================================================
    
    def on_whiff(self, callback: Callable[[Whiff], None]) -> None:
        """Register callback for new whiffs."""
        self._whiff_callbacks.append(callback)
    
    def _emit_whiff(self, whiff: Whiff) -> None:
        """Store and emit a new whiff."""
        self._active_whiffs[whiff.mint].append(whiff)
        
        # Prune old whiffs
        self._prune_whiffs(whiff.mint)
        
        # Notify callbacks
        for callback in self._whiff_callbacks:
            try:
                callback(whiff)
            except Exception as e:
                Logger.error(f"Whiff callback failed: {e}")
        
        # Emit to SignalBus
        signal_bus.publish(SignalType.WHIFF_DETECTED, {
            "type": whiff.type.value,
            "mint": whiff.mint,
            "direction": whiff.direction,
            "confidence": whiff.confidence,
        })
        
        Logger.debug(f"👃 WHIFF: {whiff.type.value} on {whiff.mint[:8]} ({whiff.direction})")
    
    def _prune_whiffs(self, mint: str) -> None:
        """Remove expired whiffs."""
        now = time.time()
        self._active_whiffs[mint] = [
            w for w in self._active_whiffs[mint]
            if (now - w.timestamp) <= w.ttl_seconds
        ]
    
    # =========================================================================
    # EVENT HANDLERS
    # =========================================================================
    
    def _on_log_update(self, signal: Signal) -> None:
        """Handle LOG_UPDATE from SignalBus."""
        log_data = signal.data
        self.detect_liquidation(log_data)
    
    def _on_tx_failed(self, signal: Signal) -> None:
        """Handle TX_FAILED from SignalBus."""
        mint = signal.data.get("mint")
        program_id = signal.data.get("program_id")
        if mint and program_id:
            self.detect_failed_cluster(mint, program_id)
    
    async def _poll_priority_fees(self) -> None:
        """Background task to poll priority fees."""
        while self._running:
            await self.detect_priority_fee_spike()
            await asyncio.sleep(10.0)  # Every 10 seconds
    
    # =========================================================================
    # PARSING HELPERS
    # =========================================================================
    
    def _parse_liquidation_logs(self, protocol: str, logs: List[str]) -> Optional[LiquidationEvent]:
        """
        Parse liquidation event from protocol logs.
        
        TODO: Implement protocol-specific parsing:
        - Solend: Look for "liquidate" instruction
        - Kamino: Look for "force_close_position"
        - Marginfi: Look for "liquidation_event"
        """
        # Placeholder - implement actual parsing per protocol
        for log in logs:
            if "liquidat" in log.lower():
                # Found liquidation indicator
                # Extract details from log (protocol-specific)
                return LiquidationEvent(
                    protocol=protocol,
                    collateral_mint="UNKNOWN",  # Parse from log
                    debt_mint="UNKNOWN",
                    collateral_amount=0.0,
                    debt_amount=0.0,
                    liquidator="UNKNOWN",
                    timestamp=time.time(),
                )
        return None
    
    def register_fast_bot(self, wallet: str) -> None:
        """Register a known fast bot wallet for signature racing."""
        self.KNOWN_FAST_BOTS.add(wallet)
        Logger.info(f"🤖 Registered fast bot: {wallet[:8]}...")


# ============================================================================
# SINGLETON
# ============================================================================

_scout: Optional[SignalScoutService] = None


def get_signal_scout() -> SignalScoutService:
    """Get the SignalScoutService singleton."""
    global _scout
    if _scout is None:
        _scout = SignalScoutService()
    return _scout
