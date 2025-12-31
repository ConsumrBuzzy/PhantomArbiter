"""
BridgePod - The "Liquidity Sniffer" Pod
=======================================
V140: Narrow Path Infrastructure (Phase 16)

The BridgePod monitors institutional liquidity inflows into Solana via
Circle (CCTP) and Wormhole. It detects "The Flood" before it hits
DEX pools, providing anticipatory signals for arbitrage.

Responsibilities:
1. Listen for CCTP and Wormhole events via SignalBus (from LogHarvester)
2. Aggregate inflow volume over sliding windows
3. Identify "Whale" inflows (> $250k)
4. Emit LIQUIDITY_INFLOW signals to "warm up" relevant HopPods
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Any, Callable

from src.shared.system.logging import Logger
from src.engine.pod_manager import BasePod, PodConfig, PodSignal, PodType


@dataclass
class BridgeEvent:
    """Represents a single bridge inflow event."""

    protocol: str  # "CCTP" or "WORMHOLE"
    tx_signature: str
    amount_usd: float
    token_mint: str
    recipient: str
    timestamp: float = field(default_factory=time.time)


class BridgePod(BasePod):
    """
    The "Sniffer" - detects incoming liquidity floods.

    This pod processes bridge-related events and identifies macro-level
    liquidity shifts that precede price impact in DEX pools.
    """

    def __init__(
        self,
        config: PodConfig,
        signal_callback: Callable[[PodSignal], None],
        whale_threshold_usd: float = 250_000.0,
        window_seconds: int = 300,  # 5-minute aggregation window
    ):
        super().__init__(config, signal_callback)

        self.whale_threshold_usd = whale_threshold_usd
        self.window_seconds = window_seconds

        # Inflow tracking
        self.recent_events: List[BridgeEvent] = []
        self.total_inflow_usd_1h = 0.0

        # Stats
        self.whale_count = 0
        self.total_events = 0

        Logger.info(
            f"[BridgePod] Initialized (whale_threshold=${whale_threshold_usd:,.0f})"
        )

    async def _scan(self) -> List[PodSignal]:
        """
        Periodically aggregate inflow data and prune old events.
        """
        now = time.time()

        # Prune old events
        self.recent_events = [e for e in self.recent_events if now - e.timestamp < 3600]

        # Calculate 1h total
        self.total_inflow_usd_1h = sum(e.amount_usd for e in self.recent_events)

        # The BridgePod doesn't actively scan; it processes signals pushed to it
        # or emitted during event handling.
        return []

    def handle_bridge_event(self, data: Dict[str, Any]):
        """
        Process a raw bridge event from LogHarvester.
        """
        protocol = data.get("protocol", "UNKNOWN")
        signature = data.get("signature", "unknown")
        amount_usd = data.get("amount_usd", 0.0)
        mint = data.get("mint", "unknown")
        recipient = data.get("recipient", "unknown")

        event = BridgeEvent(
            protocol=protocol,
            tx_signature=signature,
            amount_usd=amount_usd,
            token_mint=mint,
            recipient=recipient,
        )

        self.recent_events.append(event)
        self.total_events += 1

        # Check for Whale threshold
        if amount_usd >= self.whale_threshold_usd:
            self.whale_count += 1
            Logger.info(
                f"🐳 [BridgePod] WHALE DETECTED: ${amount_usd:,.0f} via {protocol} ({signature[:8]})"
            )

            # Emit LIQUIDITY_INFLOW signal immediately
            self.emit_signal(
                PodSignal(
                    pod_id=self.id,
                    pod_type=PodType.WHALE,
                    signal_type="LIQUIDITY_INFLOW",
                    priority=9,
                    data={
                        "protocol": protocol,
                        "amount_usd": amount_usd,
                        "mint": mint,
                        "recipient": recipient,
                        "signature": signature,
                        "interpretation": f"Incoming institutional flood: ${amount_usd:,.0f}",
                    },
                )
            )

    def get_stats(self) -> Dict[str, Any]:
        """Get BridgePod statistics."""
        return {
            "pod_id": self.id,
            "status": self.status.value,
            "total_events": self.total_events,
            "whale_count": self.whale_count,
            "inflow_1h_usd": self.total_inflow_usd_1h,
            "recent_count": len(self.recent_events),
            "whale_threshold": self.whale_threshold_usd,
        }
