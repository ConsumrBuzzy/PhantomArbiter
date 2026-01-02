"""
Connection Validator - Preflight Health Check

Tests all connections from .env and reports status.
Run this to see which services are available on current station.
"""

import os
import asyncio
import time
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
from dotenv import load_dotenv

# Load .env
load_dotenv()


class ConnectionStatus(str, Enum):
    """Status of a connection."""
    OK = "✅ OK"
    MISSING = "⚠️ MISSING"
    FAILED = "❌ FAILED"
    TIMEOUT = "⏱️ TIMEOUT"
    INVALID = "🚫 INVALID"
    UNTESTED = "⬜ UNTESTED"


@dataclass
class ConnectionResult:
    """Result of testing a connection."""
    name: str
    env_var: str
    status: ConnectionStatus
    latency_ms: float = 0.0
    error: str = ""
    value_present: bool = False
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "env_var": self.env_var,
            "status": self.status.value,
            "latency_ms": round(self.latency_ms, 2),
            "error": self.error,
            "value_present": self.value_present,
        }


@dataclass
class ValidationReport:
    """Complete validation report."""
    timestamp: float = field(default_factory=time.time)
    results: List[ConnectionResult] = field(default_factory=list)
    
    def summary(self) -> Dict:
        ok = sum(1 for r in self.results if r.status == ConnectionStatus.OK)
        missing = sum(1 for r in self.results if r.status == ConnectionStatus.MISSING)
        failed = sum(1 for r in self.results if r.status == ConnectionStatus.FAILED)
        
        return {
            "total": len(self.results),
            "ok": ok,
            "missing": missing,
            "failed": failed,
            "healthy": ok == len(self.results),
        }
    
    def print_report(self) -> None:
        """Print human-readable report."""
        print("\n" + "=" * 60)
        print("   🔌 PHANTOM ARBITER - CONNECTION HEALTH CHECK")
        print("=" * 60)
        
        # Group by status
        for result in self.results:
            latency_str = f" ({result.latency_ms:.0f}ms)" if result.latency_ms > 0 else ""
            error_str = f" - {result.error}" if result.error else ""
            print(f"   {result.status.value}  {result.name}{latency_str}{error_str}")
        
        print("-" * 60)
        summary = self.summary()
        print(f"   Total: {summary['total']} | "
              f"OK: {summary['ok']} | "
              f"Missing: {summary['missing']} | "
              f"Failed: {summary['failed']}")
        
        if summary['healthy']:
            print("\n   ✅ All connections healthy!")
        else:
            print("\n   ⚠️ Some connections need attention.")
        print("=" * 60 + "\n")


class ConnectionValidator:
    """
    Validates all external connections from .env.
    
    Tests:
    - RPC endpoints (HTTP request)
    - WebSocket endpoints (connection test)
    - API keys (simple request)
    """
    
    # Connection definitions: (name, env_var, test_type, test_url_template)
    CONNECTIONS = [
        ("Helius RPC", "RPC_URL", "rpc", None),
        ("Helius WebSocket", "HELIUS_WS_URL", "wss", None),
        ("Helius API", "HELIUS_API_KEY", "helius_api", "https://api.helius.xyz/v0/addresses/{key}/balances"),
        ("Chainstack HTTP", "CHAINSTACK_HTTP_URL", "rpc", None),
        ("Chainstack WebSocket", "CHAINSTACK_WS_URL", "wss", None),
        ("Alchemy", "ALCHEMY_ENDPOINT", "rpc", None),
        ("Jupiter API", "JUPITER_API_KEY", "jupiter", "https://quote-api.jup.ag/v6/quote"),
        ("Birdeye API", "BIRDEYE_API_KEY", "birdeye", "https://public-api.birdeye.so/public/token_list"),
        ("Telegram Bot", "TELEGRAM_BOT_TOKEN", "telegram", None),
    ]
    
    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout
        self._results: List[ConnectionResult] = []
    
    async def validate_all(self) -> ValidationReport:
        """Test all connections and return report."""
        self._results = []
        
        tasks = []
        for name, env_var, test_type, url_template in self.CONNECTIONS:
            tasks.append(self._test_connection(name, env_var, test_type, url_template))
        
        await asyncio.gather(*tasks)
        
        return ValidationReport(results=self._results)
    
    async def _test_connection(
        self,
        name: str,
        env_var: str,
        test_type: str,
        url_template: Optional[str],
    ) -> None:
        """Test a single connection."""
        value = os.getenv(env_var, "").strip()
        
        # Check if present
        if not value:
            self._results.append(ConnectionResult(
                name=name,
                env_var=env_var,
                status=ConnectionStatus.MISSING,
                error=f"Set {env_var} in .env",
            ))
            return
        
        # Test based on type
        try:
            start = time.time()
            
            if test_type == "rpc":
                status, error = await self._test_rpc(value)
            elif test_type == "wss":
                status, error = await self._test_wss(value)
            elif test_type == "helius_api":
                status, error = await self._test_helius_api(value)
            elif test_type == "jupiter":
                status, error = await self._test_jupiter(value)
            elif test_type == "birdeye":
                status, error = await self._test_birdeye(value)
            elif test_type == "telegram":
                status, error = await self._test_telegram(value)
            else:
                status, error = ConnectionStatus.UNTESTED, "Unknown test type"
            
            latency = (time.time() - start) * 1000
            
            self._results.append(ConnectionResult(
                name=name,
                env_var=env_var,
                status=status,
                latency_ms=latency,
                error=error,
                value_present=True,
            ))
            
        except asyncio.TimeoutError:
            self._results.append(ConnectionResult(
                name=name,
                env_var=env_var,
                status=ConnectionStatus.TIMEOUT,
                error=f"Timeout after {self.timeout}s",
                value_present=True,
            ))
        except Exception as e:
            self._results.append(ConnectionResult(
                name=name,
                env_var=env_var,
                status=ConnectionStatus.FAILED,
                error=str(e)[:50],
                value_present=True,
            ))
    
    async def _test_rpc(self, url: str) -> Tuple[ConnectionStatus, str]:
        """Test RPC endpoint with getHealth."""
        import httpx
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getHealth",
            }
            resp = await client.post(url, json=payload)
            
            if resp.status_code == 200:
                data = resp.json()
                if "result" in data and data["result"] == "ok":
                    return ConnectionStatus.OK, ""
                elif "error" in data:
                    return ConnectionStatus.FAILED, data["error"].get("message", "RPC error")
            
            return ConnectionStatus.FAILED, f"HTTP {resp.status_code}"
    
    async def _test_wss(self, url: str) -> Tuple[ConnectionStatus, str]:
        """Test WebSocket connection."""
        try:
            import websockets
            
            async with asyncio.timeout(self.timeout):
                async with websockets.connect(url) as ws:
                    # Just connecting is enough
                    return ConnectionStatus.OK, ""
        except ImportError:
            return ConnectionStatus.UNTESTED, "websockets not installed"
        except Exception as e:
            return ConnectionStatus.FAILED, str(e)[:30]
    
    async def _test_helius_api(self, api_key: str) -> Tuple[ConnectionStatus, str]:
        """Test Helius API key."""
        import httpx
        
        url = f"https://api.helius.xyz/v0/addresses/11111111111111111111111111111111/balances?api-key={api_key}"
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url)
            
            if resp.status_code == 200:
                return ConnectionStatus.OK, ""
            elif resp.status_code == 401:
                return ConnectionStatus.INVALID, "Invalid API key"
            else:
                return ConnectionStatus.FAILED, f"HTTP {resp.status_code}"
    
    async def _test_jupiter(self, api_key: str) -> Tuple[ConnectionStatus, str]:
        """Test Jupiter API."""
        import httpx
        
        url = "https://quote-api.jup.ag/v6/quote"
        params = {
            "inputMint": "So11111111111111111111111111111111111111112",
            "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "amount": "1000000",
        }
        headers = {}
        if api_key:
            headers["x-api-key"] = api_key
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url, params=params, headers=headers)
            
            if resp.status_code == 200:
                return ConnectionStatus.OK, ""
            else:
                return ConnectionStatus.FAILED, f"HTTP {resp.status_code}"
    
    async def _test_birdeye(self, api_key: str) -> Tuple[ConnectionStatus, str]:
        """Test Birdeye API."""
        import httpx
        
        url = "https://public-api.birdeye.so/public/tokenlist"
        headers = {"X-API-KEY": api_key}
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url, headers=headers, params={"sort_by": "v24hUSD"})
            
            if resp.status_code == 200:
                return ConnectionStatus.OK, ""
            elif resp.status_code == 401:
                return ConnectionStatus.INVALID, "Invalid API key"
            else:
                return ConnectionStatus.FAILED, f"HTTP {resp.status_code}"
    
    async def _test_telegram(self, token: str) -> Tuple[ConnectionStatus, str]:
        """Test Telegram bot token."""
        import httpx
        
        url = f"https://api.telegram.org/bot{token}/getMe"
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url)
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    return ConnectionStatus.OK, ""
            elif resp.status_code == 401:
                return ConnectionStatus.INVALID, "Invalid token"
            
            return ConnectionStatus.FAILED, f"HTTP {resp.status_code}"
    
    def get_healthy_connections(self) -> List[str]:
        """Get list of healthy connection env vars."""
        return [r.env_var for r in self._results if r.status == ConnectionStatus.OK]
    
    def get_missing_connections(self) -> List[str]:
        """Get list of missing connections."""
        return [r.env_var for r in self._results if r.status == ConnectionStatus.MISSING]
    
    def get_failed_connections(self) -> List[str]:
        """Get list of failed connections."""
        return [r.env_var for r in self._results 
                if r.status in (ConnectionStatus.FAILED, ConnectionStatus.TIMEOUT, ConnectionStatus.INVALID)]


async def run_validation() -> ValidationReport:
    """Run validation and return report."""
    validator = ConnectionValidator(timeout=5.0)
    return await validator.validate_all()


def validate_sync() -> ValidationReport:
    """Synchronous wrapper for validation."""
    return asyncio.run(run_validation())


if __name__ == "__main__":
    report = validate_sync()
    report.print_report()
