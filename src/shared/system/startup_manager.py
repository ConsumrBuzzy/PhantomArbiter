import asyncio
from typing import List, Optional

from src.shared.system.logging import Logger
from src.utils.boot_utils import BootTimer
from src.core.data_broker import DataBroker
from src.engine.landlord_core import get_landlord

# Services
from src.services.ml_scheduler import (
    ml_retraining_loop,
    set_shutdown_event as set_ml_shutdown,
)
from src.services.discovery_service import (
    discovery_monitor_loop,
    set_shutdown_event as set_discovery_shutdown,
)
from src.services.liquidity_service import (
    liquidity_cycle_loop,
    set_shutdown_event as set_liquidity_shutdown,
)
from src.services.reporting_service import (
    performance_reporting_loop,
    set_shutdown_event as set_reporting_shutdown,
)


class StartupManager:
    """
    V86.4: Centralized Startup Orchestrator.
    Manages dependency injection, sequence, and graceful shutdown.
    """

    def __init__(self):
        self.shutdown_event = asyncio.Event()
        self.tasks: List[asyncio.Task] = []
        self.broker: Optional[DataBroker] = None
        self.landlord = None

        # Propagate shutdown event to services
        set_ml_shutdown(self.shutdown_event)
        set_discovery_shutdown(self.shutdown_event)
        set_liquidity_shutdown(self.shutdown_event)
        set_reporting_shutdown(self.shutdown_event)

    async def initialize_core(self):
        """Phase 1: Initialize Critical Components"""
        # Logger.section("SYSTEM INITIALIZATION")
        BootTimer.mark("Init Phase 1: Core Systems")

        # 1. Thread Manager
        from src.shared.system.thread_manager import get_thread_manager

        tm = get_thread_manager()
        BootTimer.mark("Thread Manager Ready")

        # 2. Data Broker (Merchant)
        self.broker = DataBroker()
        BootTimer.mark("Data Broker Initialized")

        # 3. Landlord (Yield)
        self.landlord = get_landlord()
        BootTimer.mark("Landlord Initialized")

        print("   ✅ Core Systems Initialized")
        return self.broker

    async def launch_services(self) -> List[asyncio.Task]:
        """Phase 2: Launch Background Services"""
        # Logger.section("STARTING CONCURRENT ENGINES")
        loop = asyncio.get_running_loop()

        # 1. Telegram Listener (via Broker)
        if hasattr(self.broker, "telegram_listener"):
            self.broker.telegram_listener.start()
            BootTimer.mark("Telegram Listener Started")

        # 2. Landlord Monitor
        if self.landlord:
            t = loop.create_task(
                self.landlord.run_monitoring_loop(), name="Landlord_Monitor"
            )
            self.tasks.append(t)

        # 3. ML Scheduler (On-Demand)
        self.tasks.append(
            loop.create_task(ml_retraining_loop(self.broker), name="ML_Monitor")
        )

        # 4. Performance Reporter (6h) & Heartbeat (5m)
        from src.services.reporting_service import heartbeat_loop

        self.tasks.append(
            loop.create_task(performance_reporting_loop(), name="Perf_Report")
        )
        self.tasks.append(
            loop.create_task(heartbeat_loop(self.broker), name="Heartbeat_Loop")
        )

        # 5. Liquidity Cycle
        self.tasks.append(
            loop.create_task(liquidity_cycle_loop(), name="Liquidity_Cycle")
        )

        # 6. Discovery Monitor
        self.tasks.append(
            loop.create_task(discovery_monitor_loop(), name="Discovery_Monitor")
        )

        # 7. Dashboard
        from src.shared.system.dashboard_service import get_dashboard_service

        dashboard = get_dashboard_service()
        dashboard.set_broker(self.broker)
        dashboard.start()
        # Force update
        loop.run_in_executor(None, dashboard.force_update)
        BootTimer.mark("Dashboard Started")

        # 8. Data Broker Main Loop (Threaded)
        print("   🔌 Starting Data Broker (Merchant) in Thread...")
        self.broker_future = loop.run_in_executor(None, self.broker.run)

        BootTimer.mark("All Services Launched")
        print("   ⏳ Systems Running. Press Ctrl+C to stop.\n")

        return self.tasks

    async def wait_for_shutdown(self):
        """Phase 3: Event Loop Wait & Graceful Shutdown"""
        try:
            while not self.shutdown_event.is_set():
                await asyncio.sleep(1.0)

                # Check critical failures
                if self.broker_future.done():
                    Logger.warning("[SYSTEM] Data Broker stopped unexpectedly.")
                    break

        except asyncio.CancelledError:
            print("\n🛑 Execution Cancelled")

        print("\n🛑 Shutting down system...")

        # Stop Components
        if self.broker:
            self.broker.stop()
        if self.landlord:
            self.landlord._running = False

        # Cancel Tasks
        for t in self.tasks:
            t.cancel()

        # Wait for cleanup
        await asyncio.gather(*self.tasks, return_exceptions=True)
        Logger.info("[SYSTEM] Shutdown Complete")

    def signal_handler(self, sig, frame):
        """Handle Ctrl+C"""
        Logger.warning("\n🛑 [SYSTEM] Shutdown Signal Received!")
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(self.shutdown_event.set)
        except:
            pass
