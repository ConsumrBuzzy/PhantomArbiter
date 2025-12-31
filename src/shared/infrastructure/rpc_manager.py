"""
RPC Failover Manager
====================
Manages a pool of RPC providers with automatic degradation detection and failover.
"""

import time
import requests
import os
from typing import List, Dict
from src.shared.system.logging import Logger


class RpcConnectionManager:
    """
    Manages RPC connection lifecycle, health tracking, and failover.
    """

    def __init__(self, rpc_urls: List[str] = None):
        # Default public RPCs if none provided
        self.rpc_urls = rpc_urls or [
            os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com"),
            "https://api.mainnet-beta.solana.com",  # Fallback 1
            "https://rpc.ankr.com/solana",  # Fallback 2
        ]

        # Deduplicate and filter empty
        self.rpc_urls = list(dict.fromkeys([u for u in self.rpc_urls if u]))

        self.current_index = 0
        self.stats: Dict[str, Dict] = {
            url: {
                "success": 0,
                "errors": 0,
                "avg_latency": 0.0,
                "last_error_time": 0,
                "status": "HEALTHY",
            }
            for url in self.rpc_urls
        }

        Logger.info(f"🛡️ [RPC] Manager initialized with {len(self.rpc_urls)} providers")

        # V9.1: Initial Latency Benchmark
        self.benchmark_providers()

    def benchmark_providers(self):
        """
        Ping all providers to determine the fastest one.
        Updates current_index to point to the lowest latency Healthy node.
        """
        Logger.info(f"🏎️ [RPC] Benchmarking {len(self.rpc_urls)} providers...")

        best_idx = 0
        min_latency = float("inf")

        for i, url in enumerate(self.rpc_urls):
            try:
                start = time.time()
                # Simple ping: getVersion or getHealth
                payload = {"jsonrpc": "2.0", "id": 1, "method": "getHealth"}
                resp = requests.post(url, json=payload, timeout=2)

                if resp.status_code == 200:
                    latency = (time.time() - start) * 1000
                    self._record_success(url, latency)
                    Logger.debug(f"   ✅ {url}: {latency:.0f}ms")

                    if latency < min_latency:
                        min_latency = latency
                        best_idx = i
                else:
                    self._record_error(url, f"HTTP {resp.status_code}")
                    Logger.debug(f"   ❌ {url}: HTTP {resp.status_code}")

            except Exception:
                self._record_error(url, "Timeout/Error")
                Logger.debug(f"   ❌ {url}: Timeout/Error")

        # Switch to best
        if best_idx != self.current_index:
            old = self.get_active_url()
            self.current_index = best_idx
            new = self.get_active_url()
            Logger.info(
                f"🏎️ [RPC] Latency Rebalance: Switched to {new} ({min_latency:.0f}ms)"
            )
        else:
            Logger.info(
                f"🏎️ [RPC] Retaining {self.get_active_url()} ({min_latency:.0f}ms)"
            )

    def get_active_url(self) -> str:
        return self.rpc_urls[self.current_index]

    def post(self, payload: dict, timeout: int = 5) -> requests.Response:
        """
        Execute POST request with metrics tracking and auto-failover on hard failure.
        """
        url = self.get_active_url()
        start = time.time()

        try:
            response = requests.post(url, json=payload, timeout=timeout)

            # Metrics
            latency = (time.time() - start) * 1000
            self._record_success(url, latency)

            # Check for Soft Failures (429, 5xx)
            if response.status_code == 429 or response.status_code >= 500:
                self._record_error(url, f"HTTP {response.status_code}")
                # Trigger checking logic?
                # For now, let the caller decide if they want to retry,
                # but we degrade the score internally.
                if response.status_code == 429:
                    # Rate limit - maybe switch immediately?
                    pass

            return response

        except requests.RequestException as e:
            self._record_error(url, str(e))
            # On connection error, try to switch immediately for the NEXT call
            # We don't retry *here* necessarily (or maybe we should?).
            # The WebSocketListener has a retry loop.
            self.switch_provider(reason=f"Network Error: {e}")
            raise e

    def _record_success(self, url: str, latency: float):
        s = self.stats[url]
        s["success"] += 1
        # Exponential moving average for latency
        if s["avg_latency"] == 0:
            s["avg_latency"] = latency
        else:
            s["avg_latency"] = 0.9 * s["avg_latency"] + 0.1 * latency

    def _record_error(self, url: str, error_msg: str):
        s = self.stats[url]
        s["errors"] += 1
        s["last_error_time"] = time.time()

        # Simple heuristic: If >3 errors in last minute, switch?
        # For now, rely on explicit switch calls or connection exceptions.

    def switch_provider(self, reason: str = "Unknown"):
        """Force rotation to next provider."""
        old_url = self.get_active_url()
        self.current_index = (self.current_index + 1) % len(self.rpc_urls)
        new_url = self.get_active_url()

        Logger.warning(
            f"🔄 [RPC] Switching Provider: {old_url} -> {new_url} (Reason: {reason})"
        )

    def get_stats(self):
        return {"active_provider": self.get_active_url(), "providers": self.stats}
