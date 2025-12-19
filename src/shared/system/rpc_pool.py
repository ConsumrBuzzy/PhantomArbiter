"""
V9.6 RPC Pool Manager
=====================
Round-robin cycling across multiple public Solana RPC endpoints.
Provides resilience when endpoints are rate-limited or slow.
"""

import json
import os
import time
import requests
from typing import Optional, Dict, Any, List
from src.shared.system.logging import Logger


class RPCPool:
    """
    V9.6: Manages a pool of public Solana RPC endpoints.
    
    Features:
    - Round-robin cycling for load distribution
    - Automatic failover on endpoint failure
    - Cooldown tracking for rate-limited endpoints
    """
    
    # Default endpoints (fallback if config missing)
    DEFAULT_ENDPOINTS = [
        "https://api.mainnet-beta.solana.com",
        "https://rpc.ankr.com/solana",
    ]
    
    def __init__(self, config_path: str = None):
        self.config_path = config_path or os.path.join(
            os.path.dirname(__file__), "..", "..", "config", "rpc_pool.json"
        )
        self.endpoints: List[Dict] = []
        self.current_index = 0
        self.cooldowns: Dict[str, float] = {}  # url -> cooldown_until
        self.request_count = 0
        
        # V30.0: Health Tracking
        self.endpoint_stats: Dict[str, Dict] = {} # url -> {'failures': 0, 'avg_latency': 0.0, 'calls': 0}
        
        self._load_config()
    
    def _load_config(self):
        """Load endpoint configuration from JSON with env var substitution."""
        import re
        
        def substitute_env_vars(text: str) -> str:
            """Replace ${VAR} patterns with environment variable values."""
            pattern = r'\$\{([^}]+)\}'
            def replacer(match):
                var_name = match.group(1)
                return os.getenv(var_name, '')
            return re.sub(pattern, replacer, text)
        
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                    
                    # V9.7: Substitute environment variables in URLs
                    endpoints = []
                    for ep in config.get("endpoints", []):
                        if ep.get("enabled", True):
                            # V12.3-FIX: Skip execution_only endpoints (JITO)
                            if ep.get("execution_only", False):
                                continue
                            
                            url = ep.get("url", "")
                            ep["url"] = substitute_env_vars(url)
                            # Skip endpoints with unresolved env vars
                            if "${" not in ep["url"]:
                                endpoints.append(ep)
                    
                    self.endpoints = endpoints
                    self.settings = config.get("settings", {})
            
            if not self.endpoints:
                # Use defaults
                self.endpoints = [
                    {"name": "Default", "url": url, "priority": i}
                    for i, url in enumerate(self.DEFAULT_ENDPOINTS)
                ]
                self.settings = {"max_retries": 3, "timeout_seconds": 10}
                
            Logger.info(f"   📡 RPC Pool: {len(self.endpoints)} endpoints loaded")
            
        except Exception as e:
            Logger.warning(f"   ⚠️ RPC Pool config error: {e}, using defaults")
            self.endpoints = [
                {"name": "Default", "url": url, "priority": i}
                for i, url in enumerate(self.DEFAULT_ENDPOINTS)
            ]
            self.settings = {"max_retries": 3, "timeout_seconds": 10}
    
    def get_next_endpoint(self) -> str:
        """
        Get the next available RPC endpoint (round-robin).
        
        Skips endpoints in cooldown.
        """
        now = time.time()
        attempts = 0
        
        while attempts < len(self.endpoints):
            endpoint = self.endpoints[self.current_index]
            url = endpoint.get("url", "")
            
            # Advance index for next call (round-robin)
            self.current_index = (self.current_index + 1) % len(self.endpoints)
            attempts += 1
            
            # Check if endpoint is in cooldown
            if url in self.cooldowns and self.cooldowns[url] > now:
                continue  # Skip, try next
            
            return url
        
        # All endpoints in cooldown - return first one anyway
        return self.endpoints[0].get("url", self.DEFAULT_ENDPOINTS[0])
    
    def mark_failed(self, url: str):
        """Mark an endpoint as failed, apply cooldown."""
        cooldown_duration = self.settings.get("cooldown_on_failure_seconds", 60)
        self.cooldowns[url] = time.time() + cooldown_duration
        
        # Find endpoint name for logging
        name = "Unknown"
        for ep in self.endpoints:
            if ep.get("url") == url:
                name = ep.get("name", "Unknown")
                break
        
        Logger.warning(f"   ⚠️ RPC {name} failed, cooldown {cooldown_duration}s")
        
        # V30.0: Track failures
        if url not in self.endpoint_stats:
            self.endpoint_stats[url] = {'failures': 0, 'avg_latency': 0.0, 'calls': 0}
        self.endpoint_stats[url]['failures'] += 1
    
    def mark_success(self, url: str, latency: float = 0.0):
        """Clear cooldown for successful endpoint and update latency."""
        if url in self.cooldowns:
            del self.cooldowns[url]
            
        # V30.0: Track stats
        if url not in self.endpoint_stats:
            self.endpoint_stats[url] = {'failures': 0, 'avg_latency': 0.0, 'calls': 0}
            
        stats = self.endpoint_stats[url]
        stats['calls'] += 1
        # Moving average latency (simple)
        stats['avg_latency'] = (stats['avg_latency'] * 0.9) + (latency * 0.1) if stats['calls'] > 1 else latency
    
    def rpc_call(self, method: str, params: list = None) -> Optional[Dict]:
        """
        Execute an RPC call with automatic failover.
        
        Args:
            method: Solana RPC method name
            params: Method parameters
            
        Returns:
            RPC response dict or None on failure
        """
        max_retries = self.settings.get("max_retries", 3)
        timeout = self.settings.get("timeout_seconds", 10)
        
        for attempt in range(max_retries):
            url = self.get_next_endpoint()
            
            try:
                payload = {
                    "jsonrpc": "2.0",
                    "id": self.request_count,
                    "method": method,
                    "params": params or []
                }
                self.request_count += 1
                
                start_time = time.time()
                response = requests.post(
                    url,
                    json=payload,
                    timeout=timeout,
                    headers={"Content-Type": "application/json"}
                )
                latency = (time.time() - start_time) * 1000 # ms
                
                if response.status_code == 200:
                    data = response.json()
                    if "error" not in data:
                        self.mark_success(url, latency)
                        return data.get("result")
                    else:
                        # RPC error
                        self.mark_failed(url)
                elif response.status_code == 429:
                    # Rate limited
                    self.mark_failed(url)
                else:
                    self.mark_failed(url)
                    
            except requests.exceptions.Timeout:
                self.mark_failed(url)
            except Exception as e:
                self.mark_failed(url)
        
        return None
    
    def get_balance(self, address: str) -> Optional[float]:
        """Get SOL balance for an address."""
        result = self.rpc_call("getBalance", [address])
        if result:
            return result.get("value", 0) / 1e9  # Convert lamports to SOL
        return None
    
    def get_token_balance(self, token_account: str) -> Optional[float]:
        """Get SPL token balance for a token account."""
        result = self.rpc_call("getTokenAccountBalance", [token_account])
        if result and "value" in result:
            return float(result["value"].get("uiAmount", 0))
        return None
    
    def get_status(self) -> Dict:
        """Get current pool status for monitoring."""
        now = time.time()
        available = sum(
            1 for ep in self.endpoints
            if ep.get("url") not in self.cooldowns or self.cooldowns[ep["url"]] <= now
        )
        
        return {
            "total_endpoints": len(self.endpoints),
            "available_endpoints": available,
            "in_cooldown": len(self.endpoints) - available,
            "total_requests": self.request_count,
            "current_index": self.current_index
        }


# Singleton instance
_pool_instance: Optional[RPCPool] = None


def get_rpc_pool() -> RPCPool:
    """Get the singleton RPC pool instance."""
    global _pool_instance
    if _pool_instance is None:
        _pool_instance = RPCPool()
    return _pool_instance


# === Quick Test ===
if __name__ == "__main__":
    pool = get_rpc_pool()
    
    print("\n📡 RPC Pool Test")
    print("=" * 40)
    
    status = pool.get_status()
    print(f"   Total: {status['total_endpoints']}")
    print(f"   Available: {status['available_endpoints']}")
    
    # Test round-robin
    print("\n   Round-robin test:")
    for i in range(5):
        url = pool.get_next_endpoint()
        print(f"   {i+1}. {url[:50]}...")
