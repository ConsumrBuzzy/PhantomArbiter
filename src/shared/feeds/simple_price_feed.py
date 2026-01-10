"""
Simple Price Feed - WebSocket-based live SOL price for Dashboard display.
No engine dependencies - runs standalone.
"""

import asyncio
import json
import time
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass

try:
    import websockets
except ImportError:
    websockets = None

try:
    import httpx
except ImportError:
    httpx = None

from src.shared.system.logging import Logger


@dataclass
class PriceData:
    """Current price snapshot."""
    symbol: str
    price: float
    change_24h: float = 0.0
    volume_24h: float = 0.0
    timestamp: float = 0.0


class SimplePriceFeed:
    """
    WebSocket-based price feed that streams SOL/USD from Pyth Network.
    Falls back to HTTP polling if WebSocket unavailable.
    """
    
    # Pyth WebSocket for real-time streaming
    PYTH_WS_URL = "wss://hermes.pyth.network/ws"
    PYTH_HTTP_URL = "https://hermes.pyth.network/api/latest_price_feeds"
    SOL_PYTH_ID = "0xef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d"
    
    def __init__(self, fallback_interval: float = 5.0):
        self.fallback_interval = fallback_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._callback: Optional[Callable] = None
        self._last_price: Optional[PriceData] = None
        self._ws_connected = False
        
    def set_callback(self, callback: Callable[[PriceData], None]):
        """Set the callback to receive price updates."""
        self._callback = callback
        
    def start(self):
        """Start the price feed."""
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        Logger.info("[PriceFeed] Starting price feed...")
        
    def stop(self):
        """Stop the price feed."""
        self._running = False
        if self._task:
            self._task.cancel()
        Logger.info("[PriceFeed] Stopped")
        
    @property
    def last_price(self) -> Optional[PriceData]:
        return self._last_price
        
    async def _run_loop(self):
        """Main loop - try WebSocket first, fallback to HTTP polling."""
        while self._running:
            try:
                # Try WebSocket connection first
                if websockets:
                    await self._websocket_stream()
                else:
                    Logger.warning("[PriceFeed] websockets not installed, using HTTP fallback")
                    await self._http_poll_loop()
            except asyncio.CancelledError:
                break
            except Exception as e:
                Logger.debug(f"[PriceFeed] Connection error: {e}")
                
            if self._running:
                await asyncio.sleep(2)  # Brief pause before reconnect
                
    async def _websocket_stream(self):
        """Stream prices via WebSocket from Pyth."""
        Logger.info(f"[PriceFeed] Connecting to Pyth WebSocket...")
        
        async with websockets.connect(self.PYTH_WS_URL) as ws:
            self._ws_connected = True
            Logger.info("[PriceFeed] ✅ WebSocket connected to Pyth")
            
            # Subscribe to SOL price feed
            subscribe_msg = {
                "type": "subscribe",
                "ids": [self.SOL_PYTH_ID]
            }
            await ws.send(json.dumps(subscribe_msg))
            
            while self._running:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=30.0)
                    data = json.loads(msg)
                    
                    if data.get("type") == "price_update":
                        price_feed = data.get("price_feed", {})
                        price_info = price_feed.get("price", {})
                        
                        price = float(price_info.get("price", 0)) * (10 ** int(price_info.get("expo", 0)))
                        
                        if price > 0:
                            price_data = PriceData(
                                symbol="SOL",
                                price=round(price, 2),
                                timestamp=time.time()
                            )
                            self._last_price = price_data
                            
                            if self._callback:
                                await self._callback(price_data)
                                
                except asyncio.TimeoutError:
                    # Send ping to keep connection alive
                    await ws.ping()
                except Exception as e:
                    Logger.debug(f"[PriceFeed] WS error: {e}")
                    break
                    
        self._ws_connected = False
        
    async def _http_poll_loop(self):
        """Fallback HTTP polling if WebSocket unavailable."""
        if httpx is None:
            Logger.warning("[PriceFeed] httpx not installed - price feed disabled")
            return
            
        Logger.info("[PriceFeed] Using HTTP polling fallback")
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            while self._running:
                try:
                    response = await client.get(
                        self.PYTH_HTTP_URL,
                        params={"ids[]": self.SOL_PYTH_ID}
                    )
                    if response.status_code == 200:
                        data = response.json()
                        if data and len(data) > 0:
                            price_info = data[0].get("price", {})
                            price = float(price_info.get("price", 0)) * (10 ** int(price_info.get("expo", 0)))
                            
                            if price > 0:
                                price_data = PriceData(
                                    symbol="SOL",
                                    price=round(price, 2),
                                    timestamp=time.time()
                                )
                                self._last_price = price_data
                                
                                if self._callback:
                                    await self._callback(price_data)
                                    
                except Exception as e:
                    Logger.debug(f"[PriceFeed] HTTP error: {e}")
                    
                await asyncio.sleep(self.fallback_interval)


# Singleton instance
_feed: Optional[SimplePriceFeed] = None


def get_price_feed() -> SimplePriceFeed:
    """Get or create the price feed singleton."""
    global _feed
    if _feed is None:
        _feed = SimplePriceFeed()
    return _feed
