"""
V133: MaintenanceService - Extracted from TacticalStrategy (SRP Refactor)
====================================================================
Handles periodic maintenance tasks on configurable intervals.

Responsibilities:
- Gas replenishment checks
- Position sync scheduling
- Heartbeat interval management
"""

import time
from typing import Callable, Dict


class MaintenanceService:
    """
    V133: Manages periodic maintenance tasks with configurable intervals.

    This component was extracted from TacticalStrategy to follow SRP.
    It handles scheduling and executing maintenance callbacks.
    """

    # Default intervals (seconds)
    GAS_CHECK_INTERVAL = 10  # Every 10 ticks
    POSITION_SYNC_INTERVAL = 5  # Every 5 seconds
    HEARTBEAT_INTERVAL = 60  # Every 60 seconds

    def __init__(self, engine_name: str = "PRIMARY"):
        """
        Initialize MaintenanceService.

        Args:
            engine_name: Identifier for logging
        """
        self.engine_name = engine_name
        self.start_time = time.time()

        # Timing state
        self._last_gas_check_tick = 0
        self._last_position_sync = 0
        self._last_heartbeat = 0

        # Registered callbacks
        self._callbacks: Dict[str, Callable] = {}

    def register_callback(self, name: str, callback: Callable) -> None:
        """Register a maintenance callback by name."""
        self._callbacks[name] = callback

    def tick(
        self,
        tick_count: int,
        gas_callback: Callable = None,
        sync_callback: Callable = None,
        heartbeat_callback: Callable = None,
    ) -> Dict[str, bool]:
        """
        Execute maintenance tasks based on timing intervals.

        Args:
            tick_count: Current tick number
            gas_callback: Called every GAS_CHECK_INTERVAL ticks
            sync_callback: Called every POSITION_SYNC_INTERVAL seconds
            heartbeat_callback: Called every HEARTBEAT_INTERVAL seconds

        Returns:
            Dict of which tasks were executed
        """
        executed = {"gas_check": False, "position_sync": False, "heartbeat": False}

        now = time.time()

        # 1. Gas check (tick-based)
        if tick_count % self.GAS_CHECK_INTERVAL == 0:
            if gas_callback:
                try:
                    gas_callback()
                    executed["gas_check"] = True
                except Exception:
                    pass

        # 2. Position sync (time-based)
        if now - self._last_position_sync >= self.POSITION_SYNC_INTERVAL:
            self._last_position_sync = now
            if sync_callback:
                try:
                    sync_callback()
                    executed["position_sync"] = True
                except Exception:
                    pass

        # 3. Heartbeat (time-based)
        if now - self._last_heartbeat >= self.HEARTBEAT_INTERVAL:
            self._last_heartbeat = now
            if heartbeat_callback:
                try:
                    heartbeat_callback()
                    executed["heartbeat"] = True
                except Exception:
                    pass

        return executed

    def get_uptime_minutes(self) -> int:
        """Return minutes since service started."""
        return int((time.time() - self.start_time) / 60)

    def reset_timing(self) -> None:
        """Reset all timing state (e.g., after pause/resume)."""
        self._last_gas_check_tick = 0
        self._last_position_sync = 0
        self._last_heartbeat = 0
