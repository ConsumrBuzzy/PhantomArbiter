"""
Execution Client - gRPC client for Execution Engine.

Connects Director to Execution Engine for trade submission.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

from src.shared.system.logging import Logger
from src.shared.system.signal_bus import signal_bus, Signal, SignalType


@dataclass
class ExecutionConfig:
    """Execution client configuration."""
    url: str = "http://localhost:9001"
    request_timeout: float = 10.0
    max_retries: int = 3


class ExecutionClient:
    """
    Client for connecting to Execution Engine.
    
    Submits trade signals and receives execution results.
    Falls back to HTTP until gRPC is fully implemented.
    """
    
    def __init__(self, config: Optional[ExecutionConfig] = None) -> None:
        self.config = config or ExecutionConfig()
        self._connected = False
        
        # Stats
        self._signals_submitted = 0
        self._signals_filled = 0
        self._signals_failed = 0
    
    async def submit_signal(
        self,
        symbol: str,
        mint: str,
        action: str,
        size_usd: float,
        reason: str = "",
        confidence: float = 0.5,
        target_price: float = 0.0,
        stop_loss: float = 0.0,
        source: str = "DIRECTOR",
    ) -> Dict[str, Any]:
        """
        Submit a trade signal to Execution Engine.
        
        Returns acknowledgment with signal ID and status.
        """
        if httpx is None:
            return {"status": "ERROR", "message": "httpx not installed"}
        
        payload = {
            "symbol": symbol,
            "mint": mint,
            "action": action,
            "size_usd": size_usd,
            "reason": reason,
            "confidence": confidence,
            "target_price": target_price,
            "stop_loss": stop_loss,
            "source": source,
            "timestamp_ms": int(time.time() * 1000),
        }
        
        for attempt in range(self.config.max_retries):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.config.url}/api/v1/signal",
                        json=payload,
                        timeout=self.config.request_timeout,
                    )
                    
                    self._signals_submitted += 1
                    
                    if response.status_code == 200:
                        result = response.json()
                        if result.get("status") == "ACCEPTED":
                            self._signals_filled += 1
                        return result
                    else:
                        self._signals_failed += 1
                        return {
                            "status": "ERROR",
                            "message": f"HTTP {response.status_code}",
                        }
                        
            except Exception as e:
                if attempt == self.config.max_retries - 1:
                    self._signals_failed += 1
                    return {"status": "ERROR", "message": str(e)}
                await asyncio.sleep(0.5 * (attempt + 1))
        
        return {"status": "ERROR", "message": "Max retries exceeded"}
    
    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get current positions from Execution Engine."""
        if httpx is None:
            return []
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.config.url}/api/v1/positions",
                    timeout=self.config.request_timeout,
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data.get("positions", [])
        except Exception as e:
            Logger.debug(f"[ExecutionClient] Get positions error: {e}")
        
        return []
    
    async def get_pnl(self) -> Dict[str, Any]:
        """Get portfolio PnL from Execution Engine."""
        if httpx is None:
            return {}
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.config.url}/api/v1/pnl",
                    timeout=self.config.request_timeout,
                )
                
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            Logger.debug(f"[ExecutionClient] Get PnL error: {e}")
        
        return {}
    
    async def health_check(self) -> Dict[str, Any]:
        """Check Execution Engine health."""
        if httpx is None:
            return {"status": "ERROR", "message": "httpx not installed"}
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.config.url}/api/v1/health",
                    timeout=self.config.request_timeout,
                )
                
                if response.status_code == 200:
                    self._connected = True
                    return response.json()
                else:
                    self._connected = False
                    return {"status": "ERROR", "code": response.status_code}
        except Exception as e:
            self._connected = False
            return {"status": "ERROR", "message": str(e)}
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics."""
        return {
            "connected": self._connected,
            "signals_submitted": self._signals_submitted,
            "signals_filled": self._signals_filled,
            "signals_failed": self._signals_failed,
        }


# Module-level convenience functions
_client: Optional[ExecutionClient] = None


def get_execution_client(config: Optional[ExecutionConfig] = None) -> ExecutionClient:
    """Get or create the global ExecutionClient instance."""
    global _client
    if _client is None:
        _client = ExecutionClient(config)
    return _client
