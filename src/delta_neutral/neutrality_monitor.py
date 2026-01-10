"""
DNEM Neutrality Monitor
=======================
The "Heartbeat" that keeps delta neutral positions balanced.

Runs a continuous monitoring loop that:
1. Polls wallet (spot) and Drift (perp) positions every 1000ms
2. Calculates delta drift using the Position Matrix
3. Generates RebalanceSignal when drift > 0.5%
4. Coordinates with SyncExecution for atomic rebalancing

This is the "brain" that prevents losing money during high volatility.
"""

from __future__ import annotations

import time
import asyncio
from typing import Optional, Callable, Awaitable, Any
from dataclasses import dataclass, field
from enum import Enum

from src.delta_neutral.types import (
    DeltaPosition,
    MarketState,
    RebalanceSignal,
    RebalanceDirection,
)
from src.delta_neutral.position_calculator import (
    build_delta_position,
    calculate_rebalance_signal,
    calculate_delta_drift,
)
from src.shared.system.logging import Logger


# =============================================================================
# CONFIGURATION
# =============================================================================


class MonitorState(Enum):
    """Current state of the neutrality monitor."""
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    ERROR = "ERROR"


@dataclass
class MonitorConfig:
    """Configuration for the neutrality monitor."""
    
    # Polling interval in milliseconds
    poll_interval_ms: int = 1000
    
    # Delta drift threshold for rebalance trigger
    drift_threshold_pct: float = 0.5
    
    # Minimum time between rebalances (prevent spam)
    min_rebalance_interval_sec: float = 60.0
    
    # Maximum consecutive errors before pause
    max_consecutive_errors: int = 3
    
    # Whether to auto-execute rebalances or just signal
    auto_execute: bool = False


# =============================================================================
# NEUTRALITY MONITOR
# =============================================================================


class NeutralityMonitor:
    """
    Background task that monitors delta neutrality.
    
    Ingests:
    - Wallet balance (Spot SOL)
    - Drift position (Perp SOL-PERP)
    
    Produces:
    - RebalanceSignal when drift exceeds threshold
    
    Example:
        >>> monitor = NeutralityMonitor(wallet, drift_adapter, price_cache)
        >>> monitor.on_rebalance_needed = lambda sig: print(f"Rebalance: {sig}")
        >>> await monitor.start()
    """
    
    def __init__(
        self,
        wallet: Any,           # WalletManager
        drift: Any,            # DriftAdapter
        price_cache: Any,      # SharedPriceCache or similar
        sync_executor: Optional[Any] = None,  # SyncExecution
        config: Optional[MonitorConfig] = None,
    ):
        self.wallet = wallet
        self.drift = drift
        self.price_cache = price_cache
        self.sync_executor = sync_executor
        self.config = config or MonitorConfig()
        
        # State
        self._state = MonitorState.IDLE
        self._task: Optional[asyncio.Task] = None
        self._last_position: Optional[DeltaPosition] = None
        self._last_rebalance_time: float = 0
        self._consecutive_errors = 0
        
        # Callbacks
        self.on_rebalance_needed: Optional[Callable[[RebalanceSignal], Awaitable[None]]] = None
        self.on_position_update: Optional[Callable[[DeltaPosition], Awaitable[None]]] = None
        self.on_error: Optional[Callable[[Exception], Awaitable[None]]] = None
        
        # Statistics
        self._polls_completed = 0
        self._signals_generated = 0
        self._rebalances_executed = 0
        self._total_drift_samples: list[float] = []
    
    # =========================================================================
    # LIFECYCLE
    # =========================================================================
    
    async def start(self) -> None:
        """Start the monitoring loop."""
        if self._state == MonitorState.RUNNING:
            Logger.warning("[DNEM] Monitor already running")
            return
        
        Logger.info("[DNEM] 🫀 Neutrality Monitor starting...")
        self._state = MonitorState.RUNNING
        self._task = asyncio.create_task(self._monitor_loop())
    
    async def stop(self) -> None:
        """Stop the monitoring loop."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        self._state = MonitorState.IDLE
        Logger.info("[DNEM] Neutrality Monitor stopped")
    
    async def pause(self) -> None:
        """Pause monitoring (keeps loop running but skips checks)."""
        self._state = MonitorState.PAUSED
        Logger.info("[DNEM] Neutrality Monitor paused")
    
    async def resume(self) -> None:
        """Resume monitoring from paused state."""
        if self._state == MonitorState.PAUSED:
            self._state = MonitorState.RUNNING
            Logger.info("[DNEM] Neutrality Monitor resumed")
    
    @property
    def is_running(self) -> bool:
        return self._state == MonitorState.RUNNING
    
    # =========================================================================
    # MAIN LOOP
    # =========================================================================
    
    async def _monitor_loop(self) -> None:
        """Main monitoring loop - runs every poll_interval_ms."""
        
        poll_interval_sec = self.config.poll_interval_ms / 1000.0
        
        while self._state in (MonitorState.RUNNING, MonitorState.PAUSED):
            try:
                if self._state == MonitorState.RUNNING:
                    await self._poll_positions()
                
                await asyncio.sleep(poll_interval_sec)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                await self._handle_error(e)
    
    async def _poll_positions(self) -> None:
        """Poll current positions and check for drift."""
        
        try:
            # Get current price
            spot_price = self._get_spot_price()
            if spot_price <= 0:
                Logger.warning("[DNEM] Invalid spot price, skipping poll")
                return
            
            # Get spot balance
            spot_qty = self._get_spot_balance()
            
            # Get perp position
            perp_qty = await self._get_perp_position()
            
            # Build position matrix
            position = build_delta_position(
                spot_qty=spot_qty,
                perp_qty=perp_qty,
                spot_price=spot_price,
                timestamp_ms=int(time.time() * 1000),
            )
            
            self._last_position = position
            self._polls_completed += 1
            self._total_drift_samples.append(position.delta_drift_pct)
            
            # Trim samples to last 100
            if len(self._total_drift_samples) > 100:
                self._total_drift_samples = self._total_drift_samples[-100:]
            
            # Notify position update
            if self.on_position_update:
                await self.on_position_update(position)
            
            # Check if rebalance needed
            signal = calculate_rebalance_signal(
                position,
                spot_price,
                drift_threshold_pct=self.config.drift_threshold_pct,
            )
            
            if signal:
                await self._handle_rebalance_signal(signal, spot_price)
            
            # Reset error counter on success
            self._consecutive_errors = 0
            
        except Exception as e:
            Logger.error(f"[DNEM] Poll error: {e}")
            raise
    
    # =========================================================================
    # DATA INGESTION
    # =========================================================================
    
    def _get_spot_price(self) -> float:
        """Get current SOL/USD price from cache."""
        try:
            # Try to get from price cache
            if hasattr(self.price_cache, 'get_price'):
                price = self.price_cache.get_price("SOL")
                if price and price > 0:
                    return price
            
            # Fallback to wallet's estimate
            if hasattr(self.wallet, 'get_sol_price'):
                return self.wallet.get_sol_price()
            
            # Default fallback
            return 150.0
            
        except Exception as e:
            Logger.debug(f"[DNEM] Price fetch error: {e}")
            return 150.0
    
    def _get_spot_balance(self) -> float:
        """Get SOL balance from wallet."""
        try:
            return self.wallet.get_sol_balance()
        except Exception as e:
            Logger.error(f"[DNEM] Wallet balance error: {e}")
            return 0.0
    
    async def _get_perp_position(self) -> float:
        """Get current perp position from Drift."""
        try:
            # Try to get from Drift adapter
            if hasattr(self.drift, 'get_position'):
                position = await self.drift.get_position("SOL-PERP")
                if position:
                    return position.size  # Negative for short
            
            # Fallback to zero (no position)
            return 0.0
            
        except Exception as e:
            Logger.debug(f"[DNEM] Perp position fetch error: {e}")
            return 0.0
    
    # =========================================================================
    # REBALANCE HANDLING
    # =========================================================================
    
    async def _handle_rebalance_signal(
        self,
        signal: RebalanceSignal,
        spot_price: float,
    ) -> None:
        """Handle a rebalance signal."""
        
        self._signals_generated += 1
        
        # Check minimum interval
        time_since_last = time.time() - self._last_rebalance_time
        if time_since_last < self.config.min_rebalance_interval_sec:
            Logger.debug(
                f"[DNEM] Rebalance skipped: {time_since_last:.0f}s < "
                f"{self.config.min_rebalance_interval_sec:.0f}s minimum"
            )
            return
        
        Logger.info(f"[DNEM] 📊 Rebalance signal: {signal}")
        
        # Notify callback
        if self.on_rebalance_needed:
            await self.on_rebalance_needed(signal)
        
        # Auto-execute if configured
        if self.config.auto_execute and self.sync_executor:
            try:
                Logger.info("[DNEM] Auto-executing rebalance...")
                bundle = await self.sync_executor.execute_sync_trade(signal, spot_price)
                
                if bundle.status == "CONFIRMED":
                    self._rebalances_executed += 1
                    self._last_rebalance_time = time.time()
                    Logger.info("[DNEM] ✅ Auto-rebalance complete")
                elif bundle.needs_rollback:
                    Logger.warning("[DNEM] ⚠️ Auto-rebalance needs rollback!")
                    await self.sync_executor.emergency_rollback(bundle)
                    
            except Exception as e:
                Logger.error(f"[DNEM] Auto-rebalance failed: {e}")
    
    # =========================================================================
    # ERROR HANDLING
    # =========================================================================
    
    async def _handle_error(self, error: Exception) -> None:
        """Handle monitoring errors."""
        
        self._consecutive_errors += 1
        Logger.error(f"[DNEM] Monitor error #{self._consecutive_errors}: {error}")
        
        # Notify callback
        if self.on_error:
            await self.on_error(error)
        
        # Pause if too many errors
        if self._consecutive_errors >= self.config.max_consecutive_errors:
            Logger.warning(
                f"[DNEM] Too many errors ({self._consecutive_errors}), pausing monitor"
            )
            self._state = MonitorState.ERROR
    
    # =========================================================================
    # MANUAL OPERATIONS
    # =========================================================================
    
    async def check_delta_now(self) -> Optional[RebalanceSignal]:
        """
        Manually trigger a delta check (outside normal polling).
        
        Returns:
            RebalanceSignal if rebalance needed, None otherwise
        """
        spot_price = self._get_spot_price()
        spot_qty = self._get_spot_balance()
        perp_qty = await self._get_perp_position()
        
        position = build_delta_position(
            spot_qty=spot_qty,
            perp_qty=perp_qty,
            spot_price=spot_price,
        )
        
        return calculate_rebalance_signal(
            position,
            spot_price,
            drift_threshold_pct=self.config.drift_threshold_pct,
        )
    
    def get_current_position(self) -> Optional[DeltaPosition]:
        """Get the last known position."""
        return self._last_position
    
    # =========================================================================
    # STATISTICS
    # =========================================================================
    
    def get_stats(self) -> dict:
        """Get monitor statistics."""
        avg_drift = (
            sum(self._total_drift_samples) / len(self._total_drift_samples)
            if self._total_drift_samples else 0.0
        )
        max_drift = max(self._total_drift_samples) if self._total_drift_samples else 0.0
        
        return {
            "state": self._state.value,
            "polls_completed": self._polls_completed,
            "signals_generated": self._signals_generated,
            "rebalances_executed": self._rebalances_executed,
            "consecutive_errors": self._consecutive_errors,
            "avg_drift_pct": round(avg_drift, 3),
            "max_drift_pct": round(max_drift, 3),
            "last_position": repr(self._last_position) if self._last_position else None,
        }
