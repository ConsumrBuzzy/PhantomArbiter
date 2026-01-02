"""
WebSocket Manager - Real-time price feed connections.

Manages WebSocket connections to Helius, Raydium, and other data sources.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Callable, Any
from enum import Enum

try:
    import websockets
    from websockets.client import WebSocketClientProtocol
except ImportError:
    websockets = None  # type: ignore


class ConnectionState(str, Enum):
    """WebSocket connection states."""
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    ERROR = "ERROR"


@dataclass
class WssConfig:
    """WebSocket connection configuration."""
    name: str
    url: str
    subscriptions: List[str]
    reconnect_delay: float = 2.0
    max_reconnect_delay: float = 60.0
    ping_interval: float = 30.0


@dataclass
class WssStats:
    """WebSocket statistics."""
    name: str
    state: ConnectionState
    messages_received: int = 0
    last_message_time: float = 0.0
    reconnect_count: int = 0
    avg_latency_ms: float = 0.0


class WebSocketConnection:
    """
    Manages a single WebSocket connection.
    
    Handles reconnection, heartbeats, and message parsing.
    """
    
    def __init__(
        self,
        config: WssConfig,
        on_message: Callable[[str, Dict[str, Any]], None],
    ) -> None:
        self.config = config
        self._on_message = on_message
        self._ws: Optional[WebSocketClientProtocol] = None
        self._state = ConnectionState.DISCONNECTED
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # Stats
        self._messages_received = 0
        self._last_message_time = 0.0
        self._reconnect_count = 0
        self._latencies: List[float] = []
    
    @property
    def state(self) -> ConnectionState:
        return self._state
    
    @property
    def is_connected(self) -> bool:
        return self._state == ConnectionState.CONNECTED
    
    async def start(self) -> None:
        """Start the WebSocket connection."""
        if websockets is None:
            print(f"⚠️ [WSS:{self.config.name}] websockets library not installed")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
    
    async def stop(self) -> None:
        """Stop the WebSocket connection."""
        self._running = False
        if self._ws:
            await self._ws.close()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
    
    async def _run_loop(self) -> None:
        """Main connection loop with reconnection."""
        delay = self.config.reconnect_delay
        
        while self._running:
            try:
                self._state = ConnectionState.CONNECTING
                print(f"🔌 [WSS:{self.config.name}] Connecting to {self.config.url[:50]}...")
                
                async with websockets.connect(
                    self.config.url,
                    ping_interval=self.config.ping_interval,
                ) as ws:
                    self._ws = ws
                    self._state = ConnectionState.CONNECTED
                    delay = self.config.reconnect_delay  # Reset delay on success
                    print(f"✅ [WSS:{self.config.name}] Connected")
                    
                    # Send subscriptions
                    await self._subscribe()
                    
                    # Message loop
                    async for message in ws:
                        if not self._running:
                            break
                        await self._handle_message(message)
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._state = ConnectionState.ERROR
                print(f"⚠️ [WSS:{self.config.name}] Error: {e}")
            
            if self._running:
                self._state = ConnectionState.RECONNECTING
                self._reconnect_count += 1
                print(f"🔄 [WSS:{self.config.name}] Reconnecting in {delay}s...")
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, self.config.max_reconnect_delay)
        
        self._state = ConnectionState.DISCONNECTED
    
    async def _subscribe(self) -> None:
        """Send subscription messages."""
        if not self._ws or not self.config.subscriptions:
            return
        
        for sub in self.config.subscriptions:
            try:
                await self._ws.send(sub)
            except Exception as e:
                print(f"⚠️ [WSS:{self.config.name}] Subscribe failed: {e}")
    
    async def _handle_message(self, raw: str) -> None:
        """Parse and dispatch message."""
        self._messages_received += 1
        self._last_message_time = time.time()
        
        try:
            data = json.loads(raw)
            self._on_message(self.config.name, data)
        except json.JSONDecodeError:
            pass
    
    def get_stats(self) -> WssStats:
        """Get connection statistics."""
        avg_latency = sum(self._latencies) / len(self._latencies) if self._latencies else 0
        
        return WssStats(
            name=self.config.name,
            state=self._state,
            messages_received=self._messages_received,
            last_message_time=self._last_message_time,
            reconnect_count=self._reconnect_count,
            avg_latency_ms=round(avg_latency, 2),
        )


class WebSocketManager:
    """
    Manages multiple WebSocket connections.
    
    Provides unified interface for all data source connections.
    """
    
    def __init__(self) -> None:
        self._connections: Dict[str, WebSocketConnection] = {}
        self._message_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self._running = False
    
    def set_message_callback(
        self, callback: Callable[[str, Dict[str, Any]], None]
    ) -> None:
        """Set callback for incoming messages."""
        self._message_callback = callback
    
    def add_connection(self, config: WssConfig) -> None:
        """Add a WebSocket connection."""
        if config.name in self._connections:
            return
        
        conn = WebSocketConnection(config, self._dispatch_message)
        self._connections[config.name] = conn
    
    async def start(self) -> None:
        """Start all WebSocket connections."""
        self._running = True
        
        for conn in self._connections.values():
            await conn.start()
        
        print(f"🌐 [WSSManager] Started {len(self._connections)} connections")
    
    async def stop(self) -> None:
        """Stop all WebSocket connections."""
        self._running = False
        
        for conn in self._connections.values():
            await conn.stop()
        
        print("🌐 [WSSManager] All connections stopped")
    
    def _dispatch_message(self, source: str, data: Dict[str, Any]) -> None:
        """Dispatch message to callback."""
        if self._message_callback:
            try:
                self._message_callback(source, data)
            except Exception:
                pass
    
    def get_stats(self) -> Dict[str, WssStats]:
        """Get stats for all connections."""
        return {name: conn.get_stats() for name, conn in self._connections.items()}
    
    def get_connection_count(self) -> int:
        """Get number of active connections."""
        return sum(1 for c in self._connections.values() if c.is_connected)


# Global instance
_manager: Optional[WebSocketManager] = None


def get_websocket_manager() -> WebSocketManager:
    """Get or create the global WebSocketManager instance."""
    global _manager
    if _manager is None:
        _manager = WebSocketManager()
    return _manager
