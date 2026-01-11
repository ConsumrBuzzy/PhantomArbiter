"""
API Health Check Module
=======================
V23.0: Provides async health checks for all configured APIs.
Used by dashboard to display API status grid.

Based on tests/integration/layer_c/test_all_apis.py pattern.
"""

import os
import asyncio
import httpx
from typing import Dict, Any, List
from dataclasses import dataclass
from enum import Enum

class APIStatus(Enum):
    OK = "ok"
    SLOW = "slow"
    ERROR = "error"
    UNCONFIGURED = "unconfigured"

@dataclass
class APIHealthResult:
    name: str
    status: APIStatus
    latency_ms: float = 0
    message: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "latency_ms": round(self.latency_ms, 1),
            "message": self.message
        }

class APIHealthChecker:
    """
    Async health checker for all configured APIs.
    """
    
    TIMEOUT = 10.0  # seconds
    SLOW_THRESHOLD = 3000  # ms
    
    def __init__(self):
        self.results: Dict[str, APIHealthResult] = {}
    
    async def check_all(self) -> List[Dict[str, Any]]:
        """Run all health checks concurrently."""
        checks = [
            self._check_quicknode(),
            self._check_helius(),
            self._check_jupiter(),
            self._check_pyth(),
            self._check_coingecko(),
            self._check_dexscreener(),
            self._check_solscan(),
        ]
        
        results = await asyncio.gather(*checks, return_exceptions=True)
        
        # Filter out exceptions and return valid results
        valid_results = []
        for result in results:
            if isinstance(result, APIHealthResult):
                valid_results.append(result.to_dict())
            elif isinstance(result, Exception):
                valid_results.append({
                    "name": "Unknown",
                    "status": "error",
                    "latency_ms": 0,
                    "message": str(result)[:50]
                })
        
        return valid_results
    
    async def _timed_request(self, url: str, method: str = "GET", **kwargs) -> tuple:
        """Execute request and return (response, latency_ms)."""
        import time
        start = time.perf_counter()
        
        async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
            if method == "POST":
                resp = await client.post(url, **kwargs)
            else:
                resp = await client.get(url, **kwargs)
        
        latency = (time.perf_counter() - start) * 1000
        return resp, latency
    
    async def _check_quicknode(self) -> APIHealthResult:
        """Check QuickNode RPC."""
        url = os.getenv("QUICKNODE_RPC_URL")
        if not url:
            return APIHealthResult("QuickNode", APIStatus.UNCONFIGURED, message="Not configured")
        
        try:
            payload = {"jsonrpc": "2.0", "id": 1, "method": "getHealth"}
            resp, latency = await self._timed_request(url, "POST", json=payload)
            data = resp.json()
            
            if data.get("result") == "ok":
                status = APIStatus.SLOW if latency > self.SLOW_THRESHOLD else APIStatus.OK
                return APIHealthResult("QuickNode", status, latency, "Healthy")
            else:
                return APIHealthResult("QuickNode", APIStatus.ERROR, latency, "Unhealthy")
        except Exception as e:
            return APIHealthResult("QuickNode", APIStatus.ERROR, message=str(e)[:50])
    
    async def _check_helius(self) -> APIHealthResult:
        """Check Helius RPC."""
        api_key = os.getenv("HELIUS_API_KEY")
        if not api_key:
            return APIHealthResult("Helius", APIStatus.UNCONFIGURED, message="Not configured")
        
        try:
            url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"
            payload = {"jsonrpc": "2.0", "id": 1, "method": "getHealth"}
            resp, latency = await self._timed_request(url, "POST", json=payload)
            data = resp.json()
            
            if "result" in data:
                status = APIStatus.SLOW if latency > self.SLOW_THRESHOLD else APIStatus.OK
                return APIHealthResult("Helius", status, latency, "Healthy")
            else:
                return APIHealthResult("Helius", APIStatus.ERROR, latency, "Auth failed")
        except Exception as e:
            return APIHealthResult("Helius", APIStatus.ERROR, message=str(e)[:50])
    
    async def _check_jupiter(self) -> APIHealthResult:
        """Check Jupiter API (no auth required)."""
        try:
            url = "https://public.jupiterapi.com/quote"
            params = {
                "inputMint": "So11111111111111111111111111111111111111112",
                "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "amount": "1000000000"
            }
            resp, latency = await self._timed_request(url, params=params)
            
            if resp.status_code == 200 and "outAmount" in resp.json():
                status = APIStatus.SLOW if latency > self.SLOW_THRESHOLD else APIStatus.OK
                return APIHealthResult("Jupiter", status, latency, "Quote OK")
            else:
                return APIHealthResult("Jupiter", APIStatus.ERROR, latency, f"Status: {resp.status_code}")
        except Exception as e:
            return APIHealthResult("Jupiter", APIStatus.ERROR, message=str(e)[:50])
    
    async def _check_pyth(self) -> APIHealthResult:
        """Check Pyth Network Hermes API."""
        try:
            feed_id = "0xef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d"
            url = f"https://hermes.pyth.network/v2/updates/price/latest?ids[]={feed_id}"
            resp, latency = await self._timed_request(url)
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get("parsed"):
                    status = APIStatus.SLOW if latency > self.SLOW_THRESHOLD else APIStatus.OK
                    return APIHealthResult("Pyth", status, latency, "Price feed OK")
            
            return APIHealthResult("Pyth", APIStatus.ERROR, latency, "No data")
        except Exception as e:
            return APIHealthResult("Pyth", APIStatus.ERROR, message=str(e)[:50])
    
    async def _check_coingecko(self) -> APIHealthResult:
        """Check CoinGecko API."""
        try:
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {"ids": "solana", "vs_currencies": "usd"}
            headers = {}
            
            api_key = os.getenv("COINGECKO_API_KEY")
            if api_key:
                headers["x-cg-demo-api-key"] = api_key
            
            resp, latency = await self._timed_request(url, params=params, headers=headers)
            
            if resp.status_code == 200:
                status = APIStatus.SLOW if latency > self.SLOW_THRESHOLD else APIStatus.OK
                auth = "Pro" if api_key else "Public"
                return APIHealthResult("CoinGecko", status, latency, f"OK ({auth})")
            elif resp.status_code == 429:
                return APIHealthResult("CoinGecko", APIStatus.ERROR, latency, "Rate limited")
            else:
                return APIHealthResult("CoinGecko", APIStatus.ERROR, latency, f"Status: {resp.status_code}")
        except Exception as e:
            return APIHealthResult("CoinGecko", APIStatus.ERROR, message=str(e)[:50])
    
    async def _check_dexscreener(self) -> APIHealthResult:
        """Check DexScreener API."""
        try:
            url = "https://api.dexscreener.com/latest/dex/tokens/So11111111111111111111111111111111111111112"
            resp, latency = await self._timed_request(url)
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get("pairs"):
                    status = APIStatus.SLOW if latency > self.SLOW_THRESHOLD else APIStatus.OK
                    return APIHealthResult("DexScreener", status, latency, "OK")
            
            return APIHealthResult("DexScreener", APIStatus.ERROR, latency, "No pairs")
        except Exception as e:
            return APIHealthResult("DexScreener", APIStatus.ERROR, message=str(e)[:50])
    
    async def _check_solscan(self) -> APIHealthResult:
        """Check SolScan public API."""
        try:
            # Using a known token for test
            url = "https://public-api.solscan.io/token/meta?tokenAddress=So11111111111111111111111111111111111111112"
            resp, latency = await self._timed_request(url)
            
            if resp.status_code == 200:
                status = APIStatus.SLOW if latency > self.SLOW_THRESHOLD else APIStatus.OK
                return APIHealthResult("SolScan", status, latency, "OK")
            else:
                return APIHealthResult("SolScan", APIStatus.ERROR, latency, f"Status: {resp.status_code}")
        except Exception as e:
            return APIHealthResult("SolScan", APIStatus.ERROR, message=str(e)[:50])


# Singleton
_checker = None

def get_api_health_checker() -> APIHealthChecker:
    global _checker
    if _checker is None:
        _checker = APIHealthChecker()
    return _checker
