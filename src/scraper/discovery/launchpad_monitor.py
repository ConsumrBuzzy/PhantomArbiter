"""
V50.0: Multi-Launchpad Monitor
==============================
Unified event listener for Solana launchpads.

Monitors:
- Raydium LaunchLab (new launches)
- BONKfun (bonding curve events)
- Meteora DLMM (pool creation, migrations)
- Bags.fm (social-linked launches)

Uses logsSubscribe via Helius WebSocket for real-time detection.

Usage:
    monitor = get_launchpad_monitor()

    @monitor.on_launch
    async def handle_launch(event: LaunchEvent):
        print(f"New token: {event.mint}")

    await monitor.start()
"""

import asyncio
import time
from typing import Optional, Dict, Any, List, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum

from src.shared.system.logging import Logger
from config.settings import Settings


class LaunchPlatform(Enum):
    """Supported launchpad platforms."""

    PUMPFUN = "pump.fun"
    RAYDIUM_LAUNCHLAB = "raydium_launchlab"
    BONKFUN = "bonkfun"
    MOONSHOT = "moonshot"
    BAGS_FM = "bags.fm"
    METEORA = "meteora"
    UNKNOWN = "unknown"


class EventType(Enum):
    """Types of launchpad events."""

    NEW_LAUNCH = "new_launch"  # Fresh token created
    BONDING_PROGRESS = "bonding_progress"  # Bonding curve filling
    MIGRATION_START = "migration_start"  # Graduation beginning
    MIGRATION_COMPLETE = "migration_complete"  # Pool live on DEX
    SOCIAL_SIGNAL = "social_signal"  # Influencer activity


@dataclass
class LaunchEvent:
    """Event data for a new token launch."""

    platform: LaunchPlatform
    event_type: EventType
    mint: str
    name: str = ""
    symbol: str = ""
    creator: str = ""
    initial_supply: int = 0
    bonding_curve_address: str = ""
    timestamp: float = field(default_factory=time.time)
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def age_seconds(self) -> float:
        return time.time() - self.timestamp


@dataclass
class MigrationEvent:
    """Event data for token migration/graduation."""

    platform: LaunchPlatform
    mint: str
    bonding_curve_address: str
    destination_pool: str
    destination_dex: str  # "raydium", "meteora", "orca"
    liquidity_added_usd: float = 0.0
    timestamp: float = field(default_factory=time.time)
    raw_data: Dict[str, Any] = field(default_factory=dict)


# Type aliases for event handlers
LaunchHandler = Callable[[LaunchEvent], Awaitable[None]]
MigrationHandler = Callable[[MigrationEvent], Awaitable[None]]


class LaunchpadMonitor:
    """
    V50.0: Unified multi-platform launchpad monitor.

    Features:
    - Real-time WebSocket log subscription
    - Multi-program monitoring via Helius
    - Event normalization across platforms
    - Handler registration for launches and migrations

    Events emitted:
    - NEW_LAUNCH: Fresh token created on any platform
    - MIGRATION_START: Token beginning graduation to DEX
    - MIGRATION_COMPLETE: Token fully migrated, pool live
    - SOCIAL_SIGNAL: Influencer activity detected
    """

    # Program ID to Platform mapping
    PROGRAM_PLATFORMS = {
        "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": LaunchPlatform.PUMPFUN,
        "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj": LaunchPlatform.RAYDIUM_LAUNCHLAB,
        "BAGSB9TpGrZxQbEsrEznv5jXXdwyP6AXerN8aVRiAmcv": LaunchPlatform.BONKFUN,
        "dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN": LaunchPlatform.BAGS_FM,
        "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo": LaunchPlatform.METEORA,
    }

    def __init__(self):
        """Initialize launchpad monitor."""
        self._launch_handlers: List[LaunchHandler] = []
        self._migration_handlers: List[MigrationHandler] = []
        self._running = False
        self._ws_connection = None

        # Stats
        self._events_received = 0
        self._launches_detected = 0
        self._migrations_detected = 0

        # Get program IDs from settings
        self._program_ids = getattr(Settings, "LAUNCHPAD_PROGRAMS", {})

        Logger.info("   🔍 [DISCOVERY] Launchpad Monitor initialized")

    # =========================================================================
    # EVENT HANDLER REGISTRATION
    # =========================================================================

    def on_launch(self, handler: LaunchHandler) -> LaunchHandler:
        """
        Decorator to register a launch event handler.

        Usage:
            @monitor.on_launch
            async def handle(event: LaunchEvent):
                print(f"New: {event.mint}")
        """
        self._launch_handlers.append(handler)
        return handler

    def on_migration(self, handler: MigrationHandler) -> MigrationHandler:
        """
        Decorator to register a migration event handler.

        Usage:
            @monitor.on_migration
            async def handle(event: MigrationEvent):
                print(f"Migration: {event.mint} -> {event.destination_pool}")
        """
        self._migration_handlers.append(handler)
        return handler

    def add_launch_handler(self, handler: LaunchHandler) -> None:
        """Add a launch event handler."""
        self._launch_handlers.append(handler)

    def add_migration_handler(self, handler: MigrationHandler) -> None:
        """Add a migration event handler."""
        self._migration_handlers.append(handler)

    # =========================================================================
    # WEBSOCKET SUBSCRIPTION
    # =========================================================================

    async def start(self) -> None:
        """
        Start WebSocket log subscription for all monitored programs.

        Uses Helius logsSubscribe for real-time event detection.
        Subscribes to each launchpad program separately.
        """
        import os

        if self._running:
            Logger.warning("   🔍 [DISCOVERY] Monitor already running")
            return

        self._running = True

        # Get WebSocket URL from environment
        ws_url = os.getenv("HELIUS_WS_URL", "")
        if not ws_url:
            Logger.error(
                "   🔍 [DISCOVERY] HELIUS_WS_URL not set - cannot start monitor"
            )
            self._running = False
            return

        program_ids = list(self._program_ids.values()) if self._program_ids else []

        if not program_ids:
            Logger.warning("   🔍 [DISCOVERY] No programs configured - using defaults")
            program_ids = list(self.PROGRAM_PLATFORMS.keys())

        Logger.info(
            f"   🔍 [DISCOVERY] Starting monitor for {len(program_ids)} programs..."
        )

        try:
            import websockets

            while self._running:
                try:
                    async with websockets.connect(
                        ws_url, ping_interval=20, ping_timeout=10, close_timeout=5
                    ) as ws:
                        self._ws_connection = ws
                        Logger.success(
                            "   🔍 [DISCOVERY] WebSocket connected to Helius"
                        )

                        # Subscribe to each program
                        sub_id = 1
                        for program_id in program_ids:
                            await self._subscribe_to_program(ws, program_id, sub_id)
                            sub_id += 1

                        # Listen for messages
                        async for message in ws:
                            if not self._running:
                                break
                            await self._handle_message(message)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    if self._running:
                        Logger.warning(f"   🔍 [DISCOVERY] WSS reconnecting... ({e})")
                        await asyncio.sleep(5)

        except ImportError:
            Logger.error("   🔍 [DISCOVERY] websockets library not installed")
            self._running = False

    async def _subscribe_to_program(self, ws, program_id: str, sub_id: int) -> None:
        """Subscribe to logs for a specific program."""
        import json

        platform = self.PROGRAM_PLATFORMS.get(program_id, LaunchPlatform.UNKNOWN)

        subscription = {
            "jsonrpc": "2.0",
            "id": sub_id,
            "method": "logsSubscribe",
            "params": [{"mentions": [program_id]}, {"commitment": "confirmed"}],
        }
        await ws.send(json.dumps(subscription))
        Logger.info(
            f"   🔍 [DISCOVERY] Subscribed: {platform.value} ({program_id[:8]}...)"
        )

    async def _handle_message(self, message: str) -> None:
        """Handle incoming WebSocket message."""
        import json

        try:
            data = json.loads(message)

            # Skip subscription confirmations
            if "result" in data and "params" not in data:
                return

            # Extract log data
            params = data.get("params", {})
            result = params.get("result", {})
            value = result.get("value", {})

            logs = value.get("logs", [])
            signature = value.get("signature", "")

            if not logs or not signature:
                return

            self._events_received += 1

            # Detect event type from logs
            await self._parse_logs(logs, signature, value)

        except json.JSONDecodeError:
            pass
        except Exception as e:
            Logger.debug(f"   🔍 [DISCOVERY] Message parse error: {e}")

    async def _parse_logs(
        self, logs: List[str], signature: str, raw_value: Dict
    ) -> None:
        """Parse log messages to detect launch/migration events."""
        # Combine logs for pattern matching
        log_text = " ".join(logs[:20])  # First 20 log entries

        # Detect program from logs
        platform = LaunchPlatform.UNKNOWN
        for program_id, plat in self.PROGRAM_PLATFORMS.items():
            if program_id in log_text:
                platform = plat
                break

        if platform == LaunchPlatform.UNKNOWN:
            return

        # Detect event patterns
        # Pump.fun patterns
        if "Program log: Instruction: Create" in log_text:
            await self._handle_create_event(platform, signature, logs, raw_value)
        elif "Program log: Instruction: Buy" in log_text or "swap" in log_text.lower():
            # Potential trading activity
            pass
        elif "Program log: Migrate" in log_text or "graduation" in log_text.lower():
            await self._handle_migration_event(platform, signature, logs, raw_value)

    async def _handle_create_event(
        self, platform: LaunchPlatform, signature: str, logs: List[str], raw_value: Dict
    ) -> None:
        """Handle token creation event."""
        # Try to extract mint, name, symbol from logs
        mint = ""
        name = ""
        symbol = ""
        uri = ""

        # Helper to clean log values
        def clean(val):
            return val.strip(",").strip()

        for log in logs:
            parts = log.split()
            for i, part in enumerate(parts):
                lower_part = part.lower()

                # Mint
                if (lower_part == "mint:" or lower_part == "token:") and i + 1 < len(
                    parts
                ):
                    mint = clean(parts[i + 1])

                # Name (Pump.fun often: "name: BabyPepe")
                if lower_part == "name:" and i + 1 < len(parts):
                    # Name might be multiple words
                    # Grab everything until next key or end of string?
                    # Simple heuristic: grab next 1-3 words until a "key:" pattern
                    name_parts = []
                    for j in range(i + 1, len(parts)):
                        if ":" in parts[j]:
                            break
                        name_parts.append(parts[j])
                    name = " ".join(name_parts).strip(", ")

                # Symbol
                if lower_part == "symbol:" and i + 1 < len(parts):
                    symbol = clean(parts[i + 1])

                # URI
                if lower_part == "uri:" and i + 1 < len(parts):
                    uri = clean(parts[i + 1])

        if not mint:
            # Use signature as placeholder
            mint = f"UNKNOWN_{signature[:16]}"

        # V54.0: Register Token
        from src.scraper.discovery.token_registry import get_token_registry

        registry = get_token_registry()
        registry.register_token(mint, name, symbol, uri, platform.value)

        event = LaunchEvent(
            platform=platform,
            event_type=EventType.NEW_LAUNCH,
            mint=mint,
            name=name,
            symbol=symbol,
            raw_data=raw_value,
        )

        await self._emit_launch(event)

    async def _handle_migration_event(
        self, platform: LaunchPlatform, signature: str, logs: List[str], raw_value: Dict
    ) -> None:
        """Handle token migration/graduation event."""
        mint = ""
        destination_pool = ""

        # Parse migration details from logs
        for log in logs:
            if "mint:" in log.lower():
                parts = log.split()
                for i, part in enumerate(parts):
                    if part.lower() == "mint:" and i + 1 < len(parts):
                        mint = parts[i + 1].strip(",")
            if "pool:" in log.lower():
                parts = log.split()
                for i, part in enumerate(parts):
                    if part.lower() == "pool:" and i + 1 < len(parts):
                        destination_pool = parts[i + 1].strip(",")

        # Determine destination DEX based on platform
        destination_dex = "raydium"  # Default
        if platform == LaunchPlatform.MOONSHOT:
            destination_dex = "meteora"

        event = MigrationEvent(
            platform=platform,
            mint=mint or f"UNKNOWN_{signature[:16]}",
            bonding_curve_address="",
            destination_pool=destination_pool,
            destination_dex=destination_dex,
            raw_data=raw_value,
        )

        await self._emit_migration(event)

    def stop(self) -> None:
        """Stop the monitor."""
        self._running = False
        self._ws_connection = None
        Logger.info("   🔍 [DISCOVERY] Monitor stopped")

    # =========================================================================
    # EVENT PROCESSING
    # =========================================================================

    async def _process_log(self, log_data: Dict[str, Any]) -> None:
        """
        Process a log event from the WebSocket.

        Parses the log, determines the event type, and dispatches to handlers.
        """
        self._events_received += 1

        # Extract program ID
        program_id = log_data.get("programId", "")
        platform = self.PROGRAM_PLATFORMS.get(program_id, LaunchPlatform.UNKNOWN)

        if platform == LaunchPlatform.UNKNOWN:
            return

        # Parse based on platform
        # TODO: Implement platform-specific parsing
        pass

    async def _emit_launch(self, event: LaunchEvent) -> None:
        """Emit launch event to all handlers and SignalBus."""
        from src.shared.system.signal_bus import signal_bus, Signal, SignalType
        
        self._launches_detected += 1
        Logger.info(
            f"   🔍 [DISCOVERY] Launch: {event.symbol} on {event.platform.value}"
        )
        
        # V33: Signal Bus Integration
        signal_bus.emit(Signal(
            type=SignalType.MARKET_UPDATE,
            source="LAUNCHPAD",
            data={
                "symbol": event.symbol or "NEW",
                "label": f"{event.symbol} ({event.platform.value})",
                "token": event.mint,
                "mint": event.mint,
                "price": 0.0,
                "timestamp": event.timestamp,
                "meta": {"platform": event.platform.value}
            }
        ))

        for handler in self._launch_handlers:
            try:
                await handler(event)
            except Exception as e:
                Logger.error(f"   🔍 [DISCOVERY] Handler error: {e}")

    async def _emit_migration(self, event: MigrationEvent) -> None:
        """Emit migration event to all handlers and SignalBus."""
        from src.shared.system.signal_bus import signal_bus, Signal, SignalType
        
        self._migrations_detected += 1
        Logger.info(
            f"   🔍 [DISCOVERY] Migration: {event.mint[:16]}... -> {event.destination_dex}"
        )
        
        # V33: Signal Bus Integration
        signal_bus.emit(Signal(
            type=SignalType.MARKET_UPDATE,
            data={
                "source": "MIGRATION", # Gold/Orange Flash
                "symbol": "MIGRATION",
                "label": f"To {event.destination_dex}",
                "token": event.mint,
                "mint": event.mint,
                "price": 0.0,
                "timestamp": event.timestamp,
                "meta": {"dex": event.destination_dex}
            }
        ))

        for handler in self._migration_handlers:
            try:
                await handler(event)
            except Exception as e:
                Logger.error(f"   🔍 [DISCOVERY] Handler error: {e}")

    # =========================================================================
    # STATUS
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Get monitor status."""
        return {
            "running": self._running,
            "programs_monitored": len(self._program_ids),
            "events_received": self._events_received,
            "launches_detected": self._launches_detected,
            "migrations_detected": self._migrations_detected,
            "launch_handlers": len(self._launch_handlers),
            "migration_handlers": len(self._migration_handlers),
        }


# =============================================================================
# SINGLETON
# =============================================================================

_monitor_instance: Optional[LaunchpadMonitor] = None


def get_launchpad_monitor() -> LaunchpadMonitor:
    """Get or create the singleton LaunchpadMonitor."""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = LaunchpadMonitor()
    return _monitor_instance


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    import sys

    sys.path.insert(0, ".")

    print("\n🔍 Launchpad Monitor Test")
    print("=" * 50)

    monitor = get_launchpad_monitor()

    # Register test handlers
    @monitor.on_launch
    async def test_launch_handler(event: LaunchEvent):
        print(f"   Launch: {event.mint[:16]}... ({event.platform.value})")

    @monitor.on_migration
    async def test_migration_handler(event: MigrationEvent):
        print(f"   Migration: {event.mint[:16]}... -> {event.destination_dex}")

    print(f"\n📊 Status: {monitor.get_status()}")
    print("\n✅ Test complete!")
