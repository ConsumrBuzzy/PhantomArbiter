"""
Connection Manager - WebSocket broadcast management.

Handles multiple browser clients and efficient message distribution.
"""

from __future__ import annotations

import json
import asyncio
from typing import List, Dict, Any, Set
from fastapi import WebSocket


class ConnectionManager:
    """
    Manages WebSocket connections to browser clients.
    Handles efficient broadcast with dead connection cleanup.
    """
    
    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
    
    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket from active connections."""
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
    
    @property
    def client_count(self) -> int:
        """Number of active connections."""
        return len(self.active_connections)
    
    async def broadcast(self, message: Dict[str, Any]) -> int:
        """
        Broadcast a message to all connected clients.
        
        Args:
            message: Dict to serialize and send
            
        Returns:
            Number of clients that received the message
        """
        if not self.active_connections:
            return 0
        
        # Validate JSON (no NaN)
        try:
            payload = json.dumps(message, allow_nan=False)
        except ValueError as e:
            # NaN or Inf detected - sanitize
            payload = self._sanitize_and_serialize(message)
            if not payload:
                return 0
        
        sent_count = 0
        dead_connections: List[WebSocket] = []
        
        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
                sent_count += 1
            except Exception:
                # Connection is dead
                dead_connections.append(connection)
        
        # Cleanup dead connections
        if dead_connections:
            async with self._lock:
                for conn in dead_connections:
                    if conn in self.active_connections:
                        self.active_connections.remove(conn)
        
        return sent_count
    
    async def broadcast_batch(self, messages: List[Dict[str, Any]]) -> int:
        """
        Broadcast multiple messages as a batch update.
        
        Args:
            messages: List of dicts to send
            
        Returns:
            Number of clients that received the batch
        """
        batch_payload = {
            "type": "BATCH_UPDATE",
            "data": messages
        }
        return await self.broadcast(batch_payload)
    
    @staticmethod
    def _sanitize_and_serialize(data: Any) -> str | None:
        """
        Recursively sanitize NaN/Inf values and serialize.
        
        Returns JSON string or None if serialization fails.
        """
        import math
        
        def sanitize(obj: Any) -> Any:
            if isinstance(obj, float):
                if math.isnan(obj) or math.isinf(obj):
                    return 0.0
                return obj
            elif isinstance(obj, dict):
                return {k: sanitize(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [sanitize(item) for item in obj]
            return obj
        
        try:
            sanitized = sanitize(data)
            return json.dumps(sanitized)
        except Exception:
            return None


# Global instance for Galaxy server
connection_manager = ConnectionManager()
