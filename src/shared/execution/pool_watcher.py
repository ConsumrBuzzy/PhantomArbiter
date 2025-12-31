"""
Pool Price Watcher
==================
Real-time pool price monitoring via WebSocket subscriptions.

Uses accountSubscribe to watch Meteora/Orca pool accounts and
triggers callbacks when prices change (for arb detection).

Usage:
    watcher = PoolPriceWatcher()
    await watcher.start()
    await watcher.add_pool("meteora", pool_address, on_price_change)
"""

import os
import asyncio
import time
from typing import Dict, Optional, Callable, Any, List
from dataclasses import dataclass
from enum import Enum
from dotenv import load_dotenv

load_dotenv()

try:
    from src.shared.system.logging import Logger
except ImportError:

    class Logger:
        @staticmethod
        def info(msg):
            print(f"[INFO] {msg}")

        @staticmethod
        def warning(msg):
            print(f"[WARN] {msg}")

        @staticmethod
        def error(msg):
            print(f"[ERROR] {msg}")

        @staticmethod
        def debug(msg):
            pass


class PoolType(str, Enum):
    METEORA = "meteora"
    ORCA = "orca"


@dataclass
class PoolPrice:
    """Current price info for a pool."""

    pool_address: str
    pool_type: PoolType
    price: float  # Token X to Y price
    price_inverse: float  # Token Y to X price
    timestamp: float
    token_x: Optional[str] = None
    token_y: Optional[str] = None


@dataclass
class WatchedPool:
    """Pool being watched for price changes."""

    address: str
    pool_type: PoolType
    callback: Callable
    subscription_id: Optional[int] = None
    last_price: Optional[float] = None
    last_update: float = 0


class PoolPriceWatcher:
    """
    Real-time pool price watcher using WebSocket subscriptions.

    Supports:
    - Meteora DLMM pools
    - Orca Whirlpools
    - Custom callbacks on price changes
    """

    def __init__(self, wss_url: Optional[str] = None):
        """
        Initialize the watcher.

        Args:
            wss_url: WebSocket URL (defaults to HELIUS_WS_URL env var)
        """
        self.wss_url = wss_url or os.getenv("HELIUS_WS_URL") or self._build_helius_url()
        self._pools: Dict[str, WatchedPool] = {}
        self._ws = None
        self._running = False
        self._connected = False
        self._request_id = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._subscriptions: Dict[int, str] = {}  # sub_id -> pool_address

    def _build_helius_url(self) -> Optional[str]:
        """Build Helius WSS URL from API key."""
        api_key = os.getenv("HELIUS_API_KEY")
        if api_key:
            return f"wss://mainnet.helius-rpc.com/?api-key={api_key}"
        return None

    async def start(self) -> bool:
        """Start the watcher and connect to WSS."""
        if not self.wss_url:
            Logger.error(
                "[WATCHER] No WSS URL configured. Set HELIUS_WS_URL or HELIUS_API_KEY"
            )
            return False

        try:
            import websockets

            self._ws = await websockets.connect(
                self.wss_url, ping_interval=20, ping_timeout=10
            )
            self._running = True
            self._connected = True
            Logger.info("[WATCHER] 🔌 Connected to Helius WebSocket")

            # Start message handler
            asyncio.create_task(self._message_loop())
            return True

        except Exception as e:
            Logger.error(f"[WATCHER] Connection failed: {e}")
            return False

    async def stop(self):
        """Stop the watcher."""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None
        self._connected = False
        Logger.info("[WATCHER] Stopped")

    async def add_pool(
        self,
        pool_type: str,
        pool_address: str,
        callback: Callable[[PoolPrice], Any],
    ) -> bool:
        """
        Add a pool to watch.

        Args:
            pool_type: "meteora" or "orca"
            pool_address: Pool public key
            callback: Async function called with PoolPrice on changes

        Returns:
            True if subscription succeeded
        """
        if pool_address in self._pools:
            Logger.warning(f"[WATCHER] Pool already watched: {pool_address[:8]}...")
            return True

        pool = WatchedPool(
            address=pool_address,
            pool_type=PoolType(pool_type),
            callback=callback,
        )

        # Subscribe to account changes
        sub_id = await self._subscribe_account(pool_address)
        if sub_id is None:
            Logger.error(f"[WATCHER] Failed to subscribe to {pool_address[:8]}...")
            return False

        pool.subscription_id = sub_id
        self._pools[pool_address] = pool
        self._subscriptions[sub_id] = pool_address

        Logger.info(f"[WATCHER] 👁️ Watching {pool_type} pool: {pool_address[:8]}...")
        return True

    async def remove_pool(self, pool_address: str) -> bool:
        """Remove a pool from watching."""
        if pool_address not in self._pools:
            return False

        pool = self._pools[pool_address]
        if pool.subscription_id:
            await self._unsubscribe(pool.subscription_id)
            self._subscriptions.pop(pool.subscription_id, None)

        del self._pools[pool_address]
        Logger.info(f"[WATCHER] Removed pool: {pool_address[:8]}...")
        return True

    async def _subscribe_account(self, pubkey: str) -> Optional[int]:
        """Subscribe to account changes."""
        if not self._ws:
            return None

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "accountSubscribe",
            "params": [pubkey, {"encoding": "base64", "commitment": "confirmed"}],
        }

        try:
            future = asyncio.get_event_loop().create_future()
            self._pending[self._request_id] = future

            await self._ws.send(__import__("json").dumps(request))
            result = await asyncio.wait_for(future, timeout=10.0)

            if "result" in result:
                return result["result"]
            return None

        except Exception as e:
            Logger.error(f"[WATCHER] Subscribe error: {e}")
            return None

    async def _unsubscribe(self, sub_id: int) -> bool:
        """Unsubscribe from account."""
        if not self._ws:
            return False

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "accountUnsubscribe",
            "params": [sub_id],
        }

        try:
            await self._ws.send(__import__("json").dumps(request))
            return True
        except:
            return False

    async def _message_loop(self):
        """Handle incoming WebSocket messages."""
        import json

        try:
            async for message in self._ws:
                try:
                    data = json.loads(message)

                    # Response to a request
                    if "id" in data and data["id"] in self._pending:
                        future = self._pending.pop(data["id"])
                        future.set_result(data)

                    # Account notification
                    elif data.get("method") == "accountNotification":
                        await self._handle_account_update(data)

                except json.JSONDecodeError:
                    pass

        except Exception as e:
            Logger.warning(f"[WATCHER] Connection lost: {e}")
            self._connected = False
            await self._reconnect()

    async def _handle_account_update(self, data: dict):
        """Handle an account update notification."""
        params = data.get("params", {})
        sub_id = params.get("subscription")
        result = params.get("result", {})

        if sub_id not in self._subscriptions:
            return

        pool_address = self._subscriptions[sub_id]
        pool = self._pools.get(pool_address)

        if not pool:
            return

        # Parse price from account data
        price_info = await self._parse_pool_price(pool, result)

        if price_info:
            pool.last_price = price_info.price
            pool.last_update = time.time()

            # Trigger callback
            try:
                if asyncio.iscoroutinefunction(pool.callback):
                    await pool.callback(price_info)
                else:
                    pool.callback(price_info)
            except Exception as e:
                Logger.error(f"[WATCHER] Callback error: {e}")

    async def _parse_pool_price(
        self, pool: WatchedPool, result: dict
    ) -> Optional[PoolPrice]:
        """
        Parse price from pool account data.

        For now, uses a simplified approach. Full parsing would require
        deserializing the pool struct based on pool type.
        """
        try:
            # Get the account data
            value = result.get("value", {})
            data = value.get("data", [])

            if not data:
                return None

            # For real implementation, you'd deserialize the pool struct here
            # For now, we'll trigger the callback with basic info
            return PoolPrice(
                pool_address=pool.address,
                pool_type=pool.pool_type,
                price=pool.last_price or 0.0,  # Would be parsed from data
                price_inverse=1.0 / pool.last_price if pool.last_price else 0.0,
                timestamp=time.time(),
            )

        except Exception as e:
            Logger.debug(f"[WATCHER] Parse error: {e}")
            return None

    async def _reconnect(self):
        """Attempt to reconnect with backoff."""
        delay = 1.0
        while self._running and not self._connected:
            await asyncio.sleep(delay)
            Logger.info("[WATCHER] Reconnecting...")

            if await self.start():
                # Resubscribe to all pools
                for pool_address, pool in self._pools.items():
                    sub_id = await self._subscribe_account(pool_address)
                    if sub_id:
                        old_id = pool.subscription_id
                        pool.subscription_id = sub_id
                        if old_id:
                            self._subscriptions.pop(old_id, None)
                        self._subscriptions[sub_id] = pool_address
                return

            delay = min(delay * 2, 60)

    @property
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected

    @property
    def pool_count(self) -> int:
        """Get number of watched pools."""
        return len(self._pools)

    def get_pool_prices(self) -> Dict[str, PoolPrice]:
        """Get current prices for all watched pools."""
        return {
            addr: PoolPrice(
                pool_address=pool.address,
                pool_type=pool.pool_type,
                price=pool.last_price or 0.0,
                price_inverse=1.0 / pool.last_price if pool.last_price else 0.0,
                timestamp=pool.last_update,
            )
            for addr, pool in self._pools.items()
        }


# ═══════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════


async def create_arb_watcher(
    pools: List[dict],
    on_price_change: Callable[[PoolPrice], Any],
) -> PoolPriceWatcher:
    """
    Create a watcher for arbitrage monitoring.

    Args:
        pools: List of dicts with 'type' and 'address' keys
        on_price_change: Callback when any pool price changes

    Returns:
        Started PoolPriceWatcher

    Example:
        watcher = await create_arb_watcher([
            {"type": "meteora", "address": "BGm1tav..."},
            {"type": "orca", "address": "7qbRF6Y..."},
        ], on_price_change=handle_price)
    """
    watcher = PoolPriceWatcher()

    if not await watcher.start():
        raise RuntimeError("Failed to start pool watcher")

    for pool in pools:
        await watcher.add_pool(
            pool_type=pool["type"],
            pool_address=pool["address"],
            callback=on_price_change,
        )

    return watcher


# ═══════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    async def on_update(price: PoolPrice):
        print(f"📊 Price update: {price.pool_address[:8]}... @ {price.timestamp}")

    async def main():
        print("=" * 60)
        print("Pool Price Watcher Test")
        print("=" * 60)

        watcher = PoolPriceWatcher()

        if not await watcher.start():
            print("❌ Failed to start watcher")
            return

        print("\n✅ Connected! Watching pools...")
        print("(Press Ctrl+C to stop)")

        # Keep running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass

        await watcher.stop()
        print("\n✅ Stopped")

    asyncio.run(main())
