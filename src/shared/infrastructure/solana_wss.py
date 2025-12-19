"""
Solana WebSocket Adapter
========================
Real-time Solana account subscriptions via WSS.

Supports:
- Account subscriptions (pool state changes)
- Log subscriptions (swap events)
- Signature subscriptions (tx confirmation)

Usage:
    from src.shared.infrastructure.solana_wss import SolanaWSS
    
    wss = SolanaWSS()
    await wss.connect()
    await wss.subscribe_account(pool_address, callback)
"""

import os
import json
import asyncio
from typing import Dict, Optional, Callable, Any, List
from dataclasses import dataclass, field
import websockets
from dotenv import load_dotenv

from src.shared.system.logging import Logger

load_dotenv()


@dataclass
class Subscription:
    """Active subscription info."""
    sub_id: int
    method: str
    params: List
    callback: Callable


class SolanaWSS:
    """
    Solana WebSocket adapter for real-time data streaming.
    
    Features:
    - Auto-reconnect on disconnect
    - Subscription management
    - Rate limit awareness (25 RPS for Chainstack)
    """
    
    def __init__(self, wss_url: str = None):
        self.wss_url = wss_url or os.getenv("CHAINSTACK_WSS_URL")
        
        if not self.wss_url:
            Logger.warning("[WSS] No CHAINSTACK_WSS_URL configured")
        
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._subscriptions: Dict[int, Subscription] = {}
        self._request_id = 0
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._running = False
        self._reconnect_delay = 1.0
        
    async def connect(self) -> bool:
        """Establish WSS connection."""
        if not self.wss_url:
            Logger.error("[WSS] Cannot connect - no WSS URL configured")
            return False
        
        try:
            self._ws = await websockets.connect(
                self.wss_url,
                ping_interval=20,
                ping_timeout=10
            )
            self._running = True
            self._reconnect_delay = 1.0  # Reset on successful connect
            
            # Start message handler
            asyncio.create_task(self._message_handler())
            
            Logger.info("[WSS] 🔌 Connected to Solana WebSocket")
            return True
            
        except Exception as e:
            Logger.error(f"[WSS] Connection failed: {e}")
            return False
    
    async def disconnect(self):
        """Close WSS connection."""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None
        Logger.info("[WSS] Disconnected")
    
    async def _message_handler(self):
        """Handle incoming WSS messages."""
        try:
            async for message in self._ws:
                try:
                    data = json.loads(message)
                    
                    # Check if it's a response to a request
                    if "id" in data and data["id"] in self._pending_requests:
                        future = self._pending_requests.pop(data["id"])
                        future.set_result(data)
                    
                    # Check if it's a subscription notification
                    elif "method" in data and data["method"] == "accountNotification":
                        sub_id = data.get("params", {}).get("subscription")
                        if sub_id in self._subscriptions:
                            sub = self._subscriptions[sub_id]
                            asyncio.create_task(sub.callback(data["params"]["result"]))
                    
                    elif "method" in data and data["method"] == "logsNotification":
                        sub_id = data.get("params", {}).get("subscription")
                        if sub_id in self._subscriptions:
                            sub = self._subscriptions[sub_id]
                            asyncio.create_task(sub.callback(data["params"]["result"]))
                            
                except json.JSONDecodeError:
                    Logger.debug(f"[WSS] Invalid JSON: {message[:100]}")
                    
        except websockets.ConnectionClosed:
            Logger.warning("[WSS] Connection closed, attempting reconnect...")
            await self._reconnect()
        except Exception as e:
            Logger.error(f"[WSS] Message handler error: {e}")
    
    async def _reconnect(self):
        """Attempt to reconnect with exponential backoff."""
        while self._running:
            await asyncio.sleep(self._reconnect_delay)
            
            if await self.connect():
                # Resubscribe to all existing subscriptions
                for sub in list(self._subscriptions.values()):
                    await self._resubscribe(sub)
                return
            
            self._reconnect_delay = min(self._reconnect_delay * 2, 60)
    
    async def _resubscribe(self, sub: Subscription):
        """Resubscribe after reconnect."""
        result = await self._send_request(sub.method, sub.params)
        if result and "result" in result:
            new_id = result["result"]
            del self._subscriptions[sub.sub_id]
            sub.sub_id = new_id
            self._subscriptions[new_id] = sub
    
    async def _send_request(self, method: str, params: List) -> Optional[Dict]:
        """Send a request and wait for response."""
        if not self._ws:
            return None
        
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params
        }
        
        future = asyncio.get_event_loop().create_future()
        self._pending_requests[self._request_id] = future
        
        try:
            await self._ws.send(json.dumps(request))
            result = await asyncio.wait_for(future, timeout=10.0)
            return result
        except asyncio.TimeoutError:
            self._pending_requests.pop(self._request_id, None)
            Logger.warning(f"[WSS] Request timeout: {method}")
            return None
        except Exception as e:
            Logger.error(f"[WSS] Request error: {e}")
            return None
    
    async def subscribe_account(
        self, 
        pubkey: str, 
        callback: Callable,
        encoding: str = "jsonParsed"
    ) -> Optional[int]:
        """
        Subscribe to account changes.
        
        Args:
            pubkey: Account public key to watch
            callback: Async function called on updates
            encoding: Data encoding (jsonParsed, base64, etc.)
            
        Returns:
            Subscription ID or None on failure
        """
        params = [pubkey, {"encoding": encoding, "commitment": "confirmed"}]
        result = await self._send_request("accountSubscribe", params)
        
        if result and "result" in result:
            sub_id = result["result"]
            self._subscriptions[sub_id] = Subscription(
                sub_id=sub_id,
                method="accountSubscribe",
                params=params,
                callback=callback
            )
            Logger.info(f"[WSS] 📡 Subscribed to account: {pubkey[:8]}...")
            return sub_id
        
        return None
    
    async def subscribe_logs(
        self,
        mentions: List[str],
        callback: Callable
    ) -> Optional[int]:
        """
        Subscribe to transaction logs mentioning specific accounts.
        
        Args:
            mentions: List of account pubkeys to watch
            callback: Async function called on log events
            
        Returns:
            Subscription ID or None on failure
        """
        params = [{"mentions": mentions}, {"commitment": "confirmed"}]
        result = await self._send_request("logsSubscribe", params)
        
        if result and "result" in result:
            sub_id = result["result"]
            self._subscriptions[sub_id] = Subscription(
                sub_id=sub_id,
                method="logsSubscribe",
                params=params,
                callback=callback
            )
            Logger.info(f"[WSS] 📡 Subscribed to logs for {len(mentions)} accounts")
            return sub_id
        
        return None
    
    async def unsubscribe(self, sub_id: int) -> bool:
        """Unsubscribe from a subscription."""
        if sub_id not in self._subscriptions:
            return False
        
        sub = self._subscriptions[sub_id]
        method = sub.method.replace("Subscribe", "Unsubscribe")
        
        result = await self._send_request(method, [sub_id])
        if result and result.get("result"):
            del self._subscriptions[sub_id]
            return True
        
        return False
    
    @property
    def is_connected(self) -> bool:
        """Check if WSS is connected."""
        return self._ws is not None and self._ws.open


# Singleton instance
_wss_instance: Optional[SolanaWSS] = None

def get_solana_wss() -> SolanaWSS:
    """Get or create singleton WSS instance."""
    global _wss_instance
    if _wss_instance is None:
        _wss_instance = SolanaWSS()
    return _wss_instance
