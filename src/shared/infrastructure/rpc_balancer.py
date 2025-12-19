"""
V48.0: RPC Load Balancer with Smart Throttling
===============================================
Manages multiple RPC providers with:
- Random round-robin selection (avoid predictable patterns)
- Rate limit detection (429) and exponential backoff
- Health tracking and auto-failover
- Request distribution logging

Supported Providers:
- Helius
- Alchemy
- (Extensible to more)
"""

import os
import time
import random
import requests
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from dotenv import load_dotenv

load_dotenv()


class ProviderStatus(Enum):
    """Provider health status."""
    HEALTHY = "healthy"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"


@dataclass
class RPCProvider:
    """RPC provider configuration and state."""
    name: str
    url: str
    weight: float = 1.0                    # Selection weight (higher = more likely)
    status: ProviderStatus = ProviderStatus.HEALTHY
    last_error_time: float = 0.0
    error_count: int = 0
    backoff_until: float = 0.0             # Don't use until this time
    request_count: int = 0
    success_count: int = 0
    
    # Backoff configuration
    base_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 60.0
    
    def is_available(self) -> bool:
        """Check if provider is available (not in backoff)."""
        if self.status == ProviderStatus.HEALTHY:
            return True
        if time.time() >= self.backoff_until:
            # Backoff expired, mark as potentially healthy
            return True
        return False
    
    def mark_success(self):
        """Mark successful request."""
        self.request_count += 1
        self.success_count += 1
        self.status = ProviderStatus.HEALTHY
        self.error_count = 0
    
    def mark_rate_limited(self):
        """Mark rate limited - apply exponential backoff."""
        self.request_count += 1
        self.error_count += 1
        self.status = ProviderStatus.RATE_LIMITED
        self.last_error_time = time.time()
        
        # Exponential backoff: 1s, 2s, 4s, 8s, 16s, 32s, 60s max
        backoff = min(
            self.base_backoff_seconds * (2 ** (self.error_count - 1)),
            self.max_backoff_seconds
        )
        self.backoff_until = time.time() + backoff
        print(f"   ⏳ [{self.name}] Rate limited - backoff {backoff:.1f}s")
    
    def mark_error(self, error: str = ""):
        """Mark error - lighter backoff than rate limit."""
        self.request_count += 1
        self.error_count += 1
        self.status = ProviderStatus.ERROR
        self.last_error_time = time.time()
        
        # Lighter backoff for generic errors
        backoff = min(self.base_backoff_seconds * self.error_count, 10.0)
        self.backoff_until = time.time() + backoff
        print(f"   ⚠️ [{self.name}] Error: {error[:50]} - backoff {backoff:.1f}s")


class RPCBalancer:
    """
    Smart RPC load balancer with throttle management.
    
    Features:
    - Random weighted selection across providers
    - Automatic rate limit detection (HTTP 429)
    - Exponential backoff per provider
    - Auto-failover on errors
    
    Usage:
        balancer = RPCBalancer()
        result = balancer.call("getHealth")
        result = balancer.call("getAccountInfo", [mint, {"encoding": "jsonParsed"}])
    """
    
    REQUEST_TIMEOUT = 10  # seconds
    MAX_RETRIES = 3       # max providers to try per request
    
    def __init__(self):
        """Initialize RPC balancer with available providers."""
        self.providers: List[RPCProvider] = []
        self._load_providers()
        
        print(f"   🔀 [RPC] Loaded {len(self.providers)} providers: {[p.name for p in self.providers]}")
    
    def _load_providers(self):
        """Load RPC providers from environment variables."""
        # Helius (preferred)
        helius_key = os.getenv("HELIUS_API_KEY")
        if helius_key:
            self.providers.append(RPCProvider(
                name="Helius",
                url=f"https://mainnet.helius-rpc.com/?api-key={helius_key}",
                weight=1.5  # Higher weight - preferred
            ))
        
        # Alchemy
        alchemy_url = os.getenv("ALCHEMY_ENDPOINT")
        if alchemy_url:
            self.providers.append(RPCProvider(
                name="Alchemy",
                url=alchemy_url,
                weight=1.0
            ))
        
        # QuickNode
        quicknode_url = os.getenv("QUICKNODE_ENDPOINT")
        if quicknode_url:
            self.providers.append(RPCProvider(
                name="QuickNode",
                url=quicknode_url,
                weight=1.0
            ))
        
        # Chainstack (25 RPS - high capacity)
        chainstack_url = os.getenv("CHAINSTACK_RPC_URL")
        if chainstack_url:
            self.providers.append(RPCProvider(
                name="Chainstack",
                url=chainstack_url,
                weight=1.5  # Higher weight due to 25 RPS
            ))
        
        # Public fallback (always added, but low weight)
        # Rate limited but useful as backup
        self.providers.append(RPCProvider(
            name="PublicRPC",
            url="https://api.mainnet-beta.solana.com",
            weight=0.3  # Low weight - only use when others fail
        ))
    
    def _get_available_providers(self) -> List[RPCProvider]:
        """Get list of currently available providers."""
        return [p for p in self.providers if p.is_available()]
    
    def _select_provider(self) -> Optional[RPCProvider]:
        """
        Select a provider using weighted random selection.
        
        Returns:
            Selected provider or None if none available
        """
        available = self._get_available_providers()
        
        if not available:
            # All providers in backoff - pick the one with shortest remaining backoff
            if self.providers:
                return min(self.providers, key=lambda p: p.backoff_until)
            return None
        
        # Weighted random selection
        total_weight = sum(p.weight for p in available)
        if total_weight <= 0:
            return random.choice(available)
        
        r = random.uniform(0, total_weight)
        cumulative = 0
        for provider in available:
            cumulative += provider.weight
            if r <= cumulative:
                return provider
        
        return available[-1]  # Fallback
    
    def call(
        self,
        method: str,
        params: Optional[List] = None,
        retries: int = None
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Make an RPC call with automatic load balancing and failover.
        
        Args:
            method: RPC method name (e.g., "getHealth", "getAccountInfo")
            params: Optional parameters list
            retries: Max retry attempts (default: MAX_RETRIES)
            
        Returns:
            (result_dict, error_string) - one will be None
        """
        if retries is None:
            retries = self.MAX_RETRIES
        
        if not self.providers:
            return None, "No RPC providers configured"
        
        tried_providers = set()
        last_error = None
        
        for attempt in range(retries):
            provider = self._select_provider()
            
            if not provider:
                return None, "No providers available"
            
            # Skip if already tried this provider
            if provider.name in tried_providers:
                continue
            tried_providers.add(provider.name)
            
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": method,
                "params": params or []
            }
            
            try:
                response = requests.post(
                    provider.url,
                    json=payload,
                    timeout=self.REQUEST_TIMEOUT
                )
                
                # Check for rate limiting
                if response.status_code == 429:
                    provider.mark_rate_limited()
                    last_error = f"{provider.name}: Rate limited (429)"
                    continue
                
                # Check for other HTTP errors
                if response.status_code != 200:
                    provider.mark_error(f"HTTP {response.status_code}")
                    last_error = f"{provider.name}: HTTP {response.status_code}"
                    continue
                
                data = response.json()
                
                # Check for RPC error in response
                if "error" in data:
                    error_msg = data["error"]
                    if isinstance(error_msg, dict):
                        error_msg = error_msg.get("message", str(error_msg))
                    
                    # Check if it's a rate limit error in the body
                    if "rate" in str(error_msg).lower() or "limit" in str(error_msg).lower():
                        provider.mark_rate_limited()
                        last_error = f"{provider.name}: {error_msg}"
                        continue
                    
                    provider.mark_error(str(error_msg)[:50])
                    last_error = f"{provider.name}: {error_msg}"
                    continue
                
                # Success!
                provider.mark_success()
                return data, None
                
            except requests.exceptions.Timeout:
                provider.mark_error("Timeout")
                last_error = f"{provider.name}: Timeout"
                continue
            except requests.exceptions.ConnectionError as e:
                provider.mark_error("Connection error")
                last_error = f"{provider.name}: Connection error"
                continue
            except Exception as e:
                provider.mark_error(str(e)[:50])
                last_error = f"{provider.name}: {str(e)[:50]}"
                continue
        
        return None, last_error or "All providers failed"
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics for all providers."""
        return {
            "providers": [
                {
                    "name": p.name,
                    "status": p.status.value,
                    "requests": p.request_count,
                    "success_rate": f"{(p.success_count / p.request_count * 100):.1f}%" if p.request_count > 0 else "N/A",
                    "available": p.is_available()
                }
                for p in self.providers
            ],
            "total_providers": len(self.providers),
            "available_providers": len(self._get_available_providers())
        }
    
    def reset_all(self):
        """Reset all provider states (for testing)."""
        for p in self.providers:
            p.status = ProviderStatus.HEALTHY
            p.error_count = 0
            p.backoff_until = 0


# Singleton instance
_balancer: Optional[RPCBalancer] = None

def get_rpc_balancer() -> RPCBalancer:
    """Get or create singleton RPC balancer."""
    global _balancer
    if _balancer is None:
        _balancer = RPCBalancer()
    return _balancer


# ═══════════════════════════════════════════════════════════════════
# TEST SCRIPT
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("RPC Load Balancer Test")
    print("=" * 60)
    
    balancer = RPCBalancer()
    
    # Test basic health check
    print("\n1. Testing getHealth across providers...")
    for i in range(5):
        result, error = balancer.call("getHealth")
        if result:
            print(f"   [{i+1}] ✅ Health: {result.get('result', 'ok')}")
        else:
            print(f"   [{i+1}] ❌ Error: {error}")
        time.sleep(0.5)
    
    # Show stats
    print("\n2. Provider Statistics...")
    stats = balancer.get_stats()
    for p in stats["providers"]:
        print(f"   {p['name']}: {p['status']} | Requests: {p['requests']} | Success: {p['success_rate']}")
    
    print(f"\n   Available: {stats['available_providers']}/{stats['total_providers']}")
    
    print("\n" + "=" * 60)
    print("Test complete!")
