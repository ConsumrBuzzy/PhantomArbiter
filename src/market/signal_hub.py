"""
MarketSignalHub - The Market Intelligence Aggregator
=====================================================
Layer A: Market Monitor - Signal aggregation and distribution.

Aggregates signals from all Market Layer services into unified
MARKET_INTEL signals for Core/Manager and Visual layers to consume.

Data Flow:
    SignalScout ──┐
    PriceFeed   ──┼──▶ MarketSignalHub ──▶ MARKET_INTEL ──▶ Core + Visual
    MarketData  ──┤
    TokenDisc   ──┘
"""

import time
from typing import Dict, Optional
from dataclasses import dataclass

from src.shared.system.logging import Logger
from src.shared.system.signal_bus import signal_bus, Signal, SignalType


@dataclass
class MarketSnapshot:
    """Unified market intelligence snapshot."""
    mint: str
    pressure_bullish: float
    pressure_bearish: float
    pressure_volatile: float
    heat: float
    regime: str
    whiff_count: int
    timestamp: float


class MarketSignalHub:
    """
    Aggregates Market Layer signals into unified MARKET_INTEL.
    
    Provides a single subscription point for Core/Visual layers
    to receive all market context without subscribing to each
    individual service.
    """
    
    def __init__(self):
        self._last_intel: Dict[str, MarketSnapshot] = {}
        self._emit_interval = 2.0  # Emit every 2 seconds per mint
        self._last_emit_time: Dict[str, float] = {}
        
        # Subscribe to individual signals
        signal_bus.subscribe(SignalType.WHIFF_DETECTED, self._on_whiff)
        signal_bus.subscribe(SignalType.MARKET_UPDATE, self._on_price_update)
        signal_bus.subscribe(SignalType.NEW_TOKEN, self._on_new_token)
        
        Logger.info("📡 MarketSignalHub initialized")
    
    # =========================================================================
    # SIGNAL HANDLERS
    # =========================================================================
    
    def _on_whiff(self, signal: Signal) -> None:
        """Handle incoming whiff signals."""
        mint = signal.data.get("mint")
        if mint:
            self._maybe_emit_intel(mint)
    
    def _on_price_update(self, signal: Signal) -> None:
        """Handle price updates."""
        mint = signal.data.get("mint")
        if mint:
            self._maybe_emit_intel(mint)
    
    def _on_new_token(self, signal: Signal) -> None:
        """Handle new token discovery."""
        mint = signal.data.get("mint")
        if mint:
            self.emit_intel(mint)  # Immediate emit for new tokens
    
    # =========================================================================
    # INTEL EMISSION
    # =========================================================================
    
    def _maybe_emit_intel(self, mint: str) -> None:
        """Emit intel if enough time has passed."""
        now = time.time()
        last = self._last_emit_time.get(mint, 0)
        
        if (now - last) >= self._emit_interval:
            self.emit_intel(mint)
    
    def emit_intel(self, mint: str) -> None:
        """
        Emit unified MARKET_INTEL signal for a mint.
        
        Gathers data from all Market Layer services and publishes
        a single comprehensive signal.
        """
        try:
            from src.market import get_signal_scout, get_market_data
            
            scout = get_signal_scout()
            market = get_market_data()
            
            # Use Rust-accelerated methods if available
            if scout._rust_available:
                pressure = scout.get_rust_pressure(mint)
                heat = scout.get_rust_heat(mint)
            else:
                pressure = scout.get_pressure(mint)
                heat = scout.get_market_heat(mint)
            
            # Get regime
            regime = market.get_regime().value
            
            # Count active whiffs
            whiff_count = len(scout.get_whiffs(mint))
            
            # Create snapshot
            snapshot = MarketSnapshot(
                mint=mint,
                pressure_bullish=pressure.get("bullish", 0.0),
                pressure_bearish=pressure.get("bearish", 0.0),
                pressure_volatile=pressure.get("volatile", 0.0),
                heat=heat,
                regime=regime,
                whiff_count=whiff_count,
                timestamp=time.time(),
            )
            
            self._last_intel[mint] = snapshot
            self._last_emit_time[mint] = time.time()
            
            # Emit to SignalBus
            signal_bus.emit(Signal(
                type=SignalType.MARKET_INTEL,
                source="MarketSignalHub",
                data={
                    "mint": mint,
                    "pressure": pressure,
                    "heat": heat,
                    "regime": regime,
                    "whiff_count": whiff_count,
                },
            ))
            
            Logger.debug(f"📡 MARKET_INTEL: {mint[:8]} heat={heat:.2f} regime={regime}")
            
        except Exception as e:
            Logger.error(f"MarketSignalHub emit failed: {e}")
    
    def get_snapshot(self, mint: str) -> Optional[MarketSnapshot]:
        """Get last known snapshot for a mint."""
        return self._last_intel.get(mint)
    
    def emit_batch(self, mints: list) -> None:
        """Emit intel for multiple mints."""
        for mint in mints:
            self.emit_intel(mint)


# =============================================================================
# SINGLETON
# =============================================================================

_hub: Optional[MarketSignalHub] = None


def get_signal_hub() -> MarketSignalHub:
    """Get the MarketSignalHub singleton."""
    global _hub
    if _hub is None:
        _hub = MarketSignalHub()
    return _hub
