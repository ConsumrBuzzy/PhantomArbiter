"""
V133: BackgroundWorkerManager - Extracted from DataBroker (SRP Refactor)
========================================================================
Manages the lifecycle and startup of background agent threads.

Responsibilities:
- Deferred startup tasks (Backfill, Validation)
- Agent thread management (Scout, Whale, Sauron, Sniper, Bitquery)
- Coordination of agent start-up delays
"""

import time
import threading
import asyncio
from typing import Any
from src.shared.system.logging import Logger


class BackgroundWorkerManager:
    """
    V133: Manages background worker threads for DataBroker agents.

    This component encapsulates the threaded startup logic previously
    nested inside DataBroker.run().
    """

    def __init__(self, broker: Any):
        """
        Initialize BackgroundWorkerManager.

        Args:
            broker: The DataBroker instance to manage workers for
        """
        self.broker = broker
        self.threads = {}

    def start_all(self):
        """Start all background workers with appropriate delays."""
        # 1. P2 Deferred Startup (Backfill/Validation)
        self._launch_thread("DeferredStartup", self._deferred_startup)

        # 2. Delayed Hunter Start (T+5s)
        self._launch_thread("Hunter", self._delayed_hunter_start)

        # 3. Agent Starts
        if self.broker.scout_agent:
            self._launch_thread("ScoutAgent", self._start_scout)
        
        if self.broker.whale_watcher:
            self._launch_thread("WhaleWatcher", self._start_whales)
            self._launch_thread("WhaleSensor", self._start_whale_sensor) # V140
        
        if self.broker.sauron:
            self._launch_thread("SauronDiscovery", self._start_sauron)
        
        if self.broker.sniper:
            self._launch_thread("SniperAgent", self._start_sniper)

        # 4. Optional Workers
        if self.broker.bitquery_adapter:
            self._launch_thread("BitqueryAdapter", self._start_bitquery)

        # 5. Agent Wiring (V68.0+)
        # Wire Sauron -> Sniper callback
        if self.broker.sauron and self.broker.sniper:
            self.broker.sauron.set_sniper_callback(self.broker.sniper.on_new_pool)
            # Wire Scout -> Sniper for Flash Audit
            self.broker.sniper.scout_agent = self.broker.scout_agent

        Logger.success("[WORKER_MGR] All background tasks launched and wired")

    def _launch_thread(self, name: str, target: Any):
        """Helper to launch a daemon thread."""
        t = threading.Thread(target=target, daemon=True, name=name)
        t.start()
        self.threads[name] = t

    def _deferred_startup(self):
        """P2 background initialization tasks (Backfill, Validation)."""
        time.sleep(0.1)  # Minimal pause

        # Task A: Backfill
        threading.Thread(
            target=self.broker._backfill_history, daemon=True, name="BackfillHistory"
        ).start()

        # Task B: Validation
        threading.Thread(
            target=self.broker._validate_tokens, daemon=True, name="ValidateTokens"
        ).start()

        Logger.success("[BROKER] P2 TASKS LAUNCHED IN BACKGROUND")

    def _delayed_hunter_start(self):
        """Hunter Daemon starting with delay."""
        time.sleep(5)
        Logger.info("   🏹 Hunter Daemon Starting...")
        self.broker.hunter.run_loop()

    def _start_scout(self):
        """Scout Agent (The Navigator)."""
        try:
            asyncio.run(self.broker.scout_agent.start())
        except Exception as e:
            Logger.error(f"[WORKER_MGR] Scout Agent failed: {e}")

    def _start_whales(self):
        """Whale Watcher (Copy Trader)."""
        try:
            asyncio.run(self.broker.whale_watcher.start())
        except Exception as e:
            Logger.error(f"[WORKER_MGR] Whale Watcher failed: {e}")

    def _start_whale_sensor(self):
        """Whale Sensor (I/O)."""
        try:
            if hasattr(self.broker.engine_mgr, "whale_sensor"):
                asyncio.run(self.broker.engine_mgr.whale_sensor.start())
        except Exception as e:
            Logger.error(f"[WORKER_MGR] Whale Sensor failed: {e}")

    def _start_sauron(self):
        """Sauron Discovery (Omni-Monitor)."""
        try:
            asyncio.run(self.broker.sauron.start())
        except Exception as e:
            Logger.error(f"[WORKER_MGR] Sauron Discovery failed: {e}")

    def _start_sniper(self):
        """Sniper Agent."""
        try:
            asyncio.run(self.broker.sniper.start())
        except Exception as e:
            Logger.error(f"[WORKER_MGR] Sniper Agent failed: {e}")

    def _start_bitquery(self):
        """Bitquery Real-time Stream."""
        if self.broker.bitquery_adapter:
            try:
                asyncio.run(self.broker.bitquery_adapter.start())
            except Exception as e:
                Logger.error(f"[WORKER_MGR] Bitquery Adapter failed: {e}")
