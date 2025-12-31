"""
V81.0: Smart Thread Manager
============================
Centralized thread pool with resource limits and tracking.
Prevents the bot from cannibalizing work PC resources.

Features:
- Max 4 concurrent I/O workers (configurable)
- Named thread tracking
- Statistics collection
- Graceful shutdown coordination
"""

import threading
import time
import os
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Dict, Callable, Optional, Any
from dataclasses import dataclass
from src.shared.system.logging import Logger


@dataclass
class ThreadStats:
    """Statistics for thread tracking."""

    submitted: int = 0
    completed: int = 0
    failed: int = 0
    active: int = 0


class ThreadPoolManager:
    """
    V81.0: Centralized thread pool manager.

    Provides:
    - Bounded I/O thread pool (max 4 workers)
    - Long-running daemon thread registration
    - Stats for dashboard
    - Graceful shutdown
    """

    # Default limits (conservative for work PC)
    DEFAULT_IO_WORKERS = 4
    DEFAULT_NICE = True

    def __init__(self, max_io_workers: int = None):
        # Try to get from settings
        try:
            from config.settings import Settings

            # V86.1: Always Dynamic - Default to available resources
            import os

            # Use CPU count + 4, capped at 32
            # This allows "Turbo" performance by default when resources are free
            cpu_count = os.cpu_count() or 4
            default_workers = min(cpu_count + 4, 32)

            # Allow override from settings, otherwise use dynamic default
            max_io_workers = getattr(
                Settings, "THREAD_POOL_MAX_WORKERS", default_workers
            )

        except:
            max_io_workers = 8  # Fallback

        self.max_io_workers = max_io_workers
        self._io_pool: Optional[ThreadPoolExecutor] = None
        self._daemon_threads: Dict[str, threading.Thread] = {}
        self._stats = ThreadStats()
        self._lock = threading.Lock()
        self._shutdown = False
        self._start_time = time.time()

        # V86.0: Dynamic Throttling
        self._throttle_delay = 0.0
        self._resource_monitor_thread = None

        # Try to lower process priority (nice)
        self._set_low_priority()

        # Start resource monitor
        self._start_resource_monitor()

        Logger.info(
            f"🧵 [THREADS] ThreadPoolManager initialized (max_workers={max_io_workers})"
        )

    def _start_resource_monitor(self):
        """Start background thread to monitor CPU/RAM."""

        def monitor():
            import psutil

            while not self._shutdown:
                try:
                    cpu = psutil.cpu_percent(interval=1)
                    mem = psutil.virtual_memory().percent

                    # Dynamic Scaling Logic
                    if cpu > 85.0 or mem > 90.0:
                        # High Load -> Increase throttling
                        self._throttle_delay = min(self._throttle_delay + 0.1, 2.0)
                        if self._throttle_delay == 0.1:
                            Logger.warning(
                                f"🧵 [THREADS] High Load (CPU {cpu}%/MEM {mem}%) - Throttling I/O"
                            )
                    elif cpu < 50.0 and mem < 80.0:
                        # Low Load -> Decrease throttling
                        self._throttle_delay = max(self._throttle_delay - 0.1, 0.0)

                except Exception:
                    # psutil might fail or not be installed
                    time.sleep(5)

                time.sleep(5)  # Check every 5s

        self._resource_monitor_thread = threading.Thread(
            target=monitor, daemon=True, name="ResourceMonitor"
        )
        self._resource_monitor_thread.start()

    def _set_low_priority(self):
        """Lower process priority to be kind to work PC."""
        try:
            import psutil

            if os.name == "nt":  # Windows
                p = psutil.Process(os.getpid())
                p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
            else:  # Unix
                os.nice(10)
        except:
            pass  # Best effort

    @property
    def io_pool(self) -> ThreadPoolExecutor:
        """Lazy-initialized I/O thread pool."""
        if self._io_pool is None:
            self._io_pool = ThreadPoolExecutor(
                max_workers=self.max_io_workers, thread_name_prefix="IOPool"
            )
        return self._io_pool

    def submit_io(self, fn: Callable, *args, **kwargs) -> Future:
        """
        Submit an I/O-bound task to the pool.
        Checks resource pressure before submitting.
        """
        if self._shutdown:
            raise RuntimeError("ThreadPoolManager is shutting down")

        # Apply throttling if system is under load
        if self._throttle_delay > 0:
            time.sleep(self._throttle_delay)

        with self._lock:
            self._stats.submitted += 1
            self._stats.active += 1

        future = self.io_pool.submit(fn, *args, **kwargs)

        def callback(f):
            with self._lock:
                self._stats.active -= 1
                if f.exception():
                    self._stats.failed += 1
                else:
                    self._stats.completed += 1

        future.add_done_callback(callback)
        return future

    def submit_daemon(
        self, name: str, fn: Callable, *args, **kwargs
    ) -> threading.Thread:
        """
        Submit a long-running daemon thread.

        Use for: WebSocket listeners, polling loops, monitors.

        Args:
            name: Unique thread name
            fn: Function to run
            *args: Positional arguments

        Returns:
            Thread object (already started)
        """
        if self._shutdown:
            raise RuntimeError("ThreadPoolManager is shutting down")

        # Check for duplicate
        if name in self._daemon_threads:
            existing = self._daemon_threads[name]
            if existing.is_alive():
                Logger.debug(f"[THREADS] Thread '{name}' already running")
                return existing

        thread = threading.Thread(
            target=self._wrapped_daemon(name, fn, *args, **kwargs),
            daemon=True,
            name=name,
        )

        with self._lock:
            self._daemon_threads[name] = thread
            self._stats.submitted += 1

        thread.start()
        Logger.debug(f"[THREADS] Started daemon: {name}")

        return thread

    def _wrapped_daemon(self, name: str, fn: Callable, *args, **kwargs) -> Callable:
        """Wrapper to track daemon completion."""

        def wrapper():
            try:
                fn(*args, **kwargs)
            except Exception as e:
                Logger.debug(f"[THREADS] Daemon '{name}' error: {e}")
                with self._lock:
                    self._stats.failed += 1
            finally:
                with self._lock:
                    self._stats.completed += 1
                    if name in self._daemon_threads:
                        del self._daemon_threads[name]

        return wrapper

    def get_stats(self) -> Dict[str, Any]:
        """Get thread statistics for dashboard."""
        with self._lock:
            active_daemons = sum(
                1 for t in self._daemon_threads.values() if t.is_alive()
            )

            return {
                "io_workers": self.max_io_workers,
                "io_active": self._stats.active,
                "daemons_active": active_daemons,
                "daemons_total": len(self._daemon_threads),
                "submitted": self._stats.submitted,
                "completed": self._stats.completed,
                "failed": self._stats.failed,
                "uptime_s": int(time.time() - self._start_time),
            }

    def get_active_count(self) -> int:
        """Get total active thread count."""
        with self._lock:
            active_daemons = sum(
                1 for t in self._daemon_threads.values() if t.is_alive()
            )
            return self._stats.active + active_daemons

    def list_daemons(self) -> Dict[str, bool]:
        """List all daemon threads and their status."""
        with self._lock:
            return {
                name: thread.is_alive() for name, thread in self._daemon_threads.items()
            }

    def shutdown(self, wait: bool = True, timeout: float = 5.0):
        """
        Graceful shutdown of all threads.

        Args:
            wait: Whether to wait for completion
            timeout: Max seconds to wait
        """
        self._shutdown = True
        Logger.info("[THREADS] Initiating graceful shutdown...")

        # Shutdown I/O pool
        if self._io_pool:
            self._io_pool.shutdown(wait=wait, cancel_futures=True)

        # Wait for daemons (best effort)
        if wait:
            start = time.time()
            while time.time() - start < timeout:
                active = sum(1 for t in self._daemon_threads.values() if t.is_alive())
                if active == 0:
                    break
                time.sleep(0.1)

        Logger.info(f"[THREADS] Shutdown complete. Stats: {self.get_stats()}")


# Singleton
_thread_manager: Optional[ThreadPoolManager] = None


def get_thread_manager() -> ThreadPoolManager:
    """Get singleton thread manager."""
    global _thread_manager
    if _thread_manager is None:
        _thread_manager = ThreadPoolManager()
    return _thread_manager
