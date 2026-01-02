"""
Data Feed Client - gRPC client for Data Feed Engine.

Connects Director to Data Feed for price streaming.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Optional, Callable, Any, Dict, List
from enum import Enum

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

from src.shared.system.logging import Logger
from src.shared.system.signal_bus import signal_bus, Signal, SignalType


class ClientState(Enum):
    """Client connection states."""
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    ERROR = "ERROR"


@dataclass
class DataFeedConfig:
    """Data Feed client configuration."""
    url: str = "http://localhost:9000"
    reconnect_delay: float = 2.0
    max_reconnect_delay: float = 60.0
    request_timeout: float = 5.0
    poll_interval: float = 0.5


class DataFeedClient:
    """
    Client for connecting to Data Feed Engine.
    
    Receives price updates and publishes to local SignalBus.
    Falls back to HTTP polling until gRPC is fully implemented.
    """
    
    def __init__(self, config: Optional[DataFeedConfig] = None) -> None:
        self.config = config or DataFeedConfig()
        self._state = ClientState.DISCONNECTED
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # Stats
        self._messages_received = 0
        self._last_message_time = 0.0
        self._reconnect_count = 0
    
    @property
    def state(self) -> ClientState:
        return self._state
    
    @property
    def is_connected(self) -> bool:
        return self._state == ClientState.CONNECTED
    
    def start(self) -> None:
        """Start the client connection."""
        if httpx is None:
            Logger.warning("[DataFeedClient] httpx not installed - client disabled")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        Logger.info(f"[DataFeedClient] Connecting to {self.config.url}")
    
    def stop(self) -> None:
        """Stop the client connection."""
        self._running = False
        if self._task:
            self._task.cancel()
        Logger.info("[DataFeedClient] Stopped")
    
    async def _run_loop(self) -> None:
        """Main connection/polling loop."""
        delay = self.config.reconnect_delay
        
        while self._running:
            try:
                self._state = ClientState.CONNECTING
                
                # Test connection with health check
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"{self.config.url}/health",
                        timeout=self.config.request_timeout,
                    )
                    
                    if response.status_code == 200:
                        self._state = ClientState.CONNECTED
                        delay = self.config.reconnect_delay
                        Logger.info("[DataFeedClient] Connected to Data Feed")
                        
                        # Enter polling loop
                        await self._poll_loop(client)
                    else:
                        raise Exception(f"Health check failed: {response.status_code}")
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._state = ClientState.ERROR
                Logger.debug(f"[DataFeedClient] Connection error: {e}")
            
            if self._running:
                self._state = ClientState.RECONNECTING
                self._reconnect_count += 1
                Logger.debug(f"[DataFeedClient] Reconnecting in {delay}s...")
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, self.config.max_reconnect_delay)
        
        self._state = ClientState.DISCONNECTED
    
    async def _poll_loop(self, client: httpx.AsyncClient) -> None:
        """Poll for price updates (fallback until gRPC streaming)."""
        while self._running and self._state == ClientState.CONNECTED:
            try:
                response = await client.get(
                    f"{self.config.url}/snapshot",
                    timeout=self.config.request_timeout,
                )
                
                if response.status_code == 200:
                    data = response.json()
                    await self._process_snapshot(data)
                    self._messages_received += 1
                    self._last_message_time = time.time()
                    
            except Exception as e:
                Logger.debug(f"[DataFeedClient] Poll error: {e}")
                break
            
            await asyncio.sleep(self.config.poll_interval)
    
    async def _process_snapshot(self, data: Dict[str, Any]) -> None:
        """Process snapshot and emit signals."""
        prices = data.get("prices", [])
        
        for price_data in prices:
            try:
                signal = Signal(
                    type=SignalType.MARKET_UPDATE,
                    source="DATA_FEED",
                    data={
                        "symbol": price_data.get("symbol"),
                        "mint": price_data.get("mint"),
                        "price": price_data.get("price"),
                        "volume_24h": price_data.get("volume_24h", 0),
                        "liquidity": price_data.get("liquidity", 0),
                        "source": price_data.get("source", "DATA_FEED"),
                    }
                )
                await signal_bus.emit_async(signal)
            except Exception:
                pass
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics."""
        return {
            "state": self._state.value,
            "messages_received": self._messages_received,
            "last_message_time": self._last_message_time,
            "reconnect_count": self._reconnect_count,
        }


# Module-level convenience functions
_client: Optional[DataFeedClient] = None


def get_datafeed_client(config: Optional[DataFeedConfig] = None) -> DataFeedClient:
    """Get or create the global DataFeedClient instance."""
    global _client
    if _client is None:
        _client = DataFeedClient(config)
    return _client


def start_datafeed_client(url: str = "http://localhost:9000") -> DataFeedClient:
    """Start the data feed client with the given URL."""
    config = DataFeedConfig(url=url)
    client = get_datafeed_client(config)
    client.start()
    return client


def stop_datafeed_client() -> None:
    """Stop the global data feed client."""
    global _client
    if _client:
        _client.stop()
        _client = None
