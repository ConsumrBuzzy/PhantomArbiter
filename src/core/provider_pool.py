"""
ProviderPool - Multi-Key RPC Aggregator (Phase 17)
===================================================
Manages multiple free-tier RPC endpoints with:
- Round-robin key rotation
- Health tracking (latency, error rate)
- Automatic failover
- Parallel WebSocket endpoint generation

Author: PyPro (Phase 17: The Signal Aggregator)
"""

from __future__ import annotations

import os
import time
import random
import threading
from dataclasses import dataclass, field
from typing import Optional
from collections import deque
from enum import Enum
from dotenv import load_dotenv

load_dotenv()


class ProviderType(Enum):
    """Supported RPC providers."""
    HELIUS = "helius"
    ALCHEMY = "alchemy"
    QUICKNODE = "quicknode"
    CHAINSTACK = "chainstack"
    TRITON = "triton"
    DRPC = "drpc"
    NOWNODES = "nownodes"
    ANKR = "ankr"
    LAVA = "lava"
    PUBLIC = "public"  # No key required


@dataclass
class ProviderEndpoint:
    """Single RPC endpoint with key and health metrics."""
    provider: ProviderType
    api_key: str
    http_url: str
    wss_url: str
    
    # Health metrics (updated in real-time)
    latency_ms: float = 0.0
    error_count: int = 0
    success_count: int = 0
    last_used: float = 0.0
    is_healthy: bool = True
    
    # Rate limit tracking
    rate_limit_until: float = 0.0
    
    @property
    def error_rate(self) -> float:
        """Calculate error rate (0.0 - 1.0)."""
        total = self.error_count + self.success_count
        if total == 0:
            return 0.0
        return self.error_count / total
    
    @property
    def is_rate_limited(self) -> bool:
        """Check if currently rate-limited (429)."""
        return time.time() < self.rate_limit_until
    
    def record_success(self, latency_ms: float) -> None:
        """Record a successful request."""
        self.success_count += 1
        # Exponential moving average for latency
        if self.latency_ms == 0:
            self.latency_ms = latency_ms
        else:
            self.latency_ms = 0.8 * self.latency_ms + 0.2 * latency_ms
        self.last_used = time.time()
        self.is_healthy = True
    
    def record_error(self, is_rate_limit: bool = False) -> None:
        """Record a failed request."""
        self.error_count += 1
        self.last_used = time.time()
        
        if is_rate_limit:
            # Exponential backoff: 1s, 2s, 4s, 8s, max 30s
            backoff = min(30, 2 ** min(self.error_count, 5))
            self.rate_limit_until = time.time() + backoff
        
        # Mark unhealthy if error rate > 30%
        if self.error_rate > 0.3 and self.success_count + self.error_count > 10:
            self.is_healthy = False
    
    def reset_health(self) -> None:
        """Reset health metrics (for periodic refresh)."""
        self.error_count = 0
        self.success_count = 0
        self.is_healthy = True


@dataclass 
class ProviderConfig:
    """Configuration for a provider type."""
    provider: ProviderType
    http_template: str  # URL template with {api_key} placeholder
    wss_template: str   # WSS URL template
    env_key_prefix: str  # e.g., "HELIUS_API_KEY" -> HELIUS_API_KEY_1, HELIUS_API_KEY_2


# Provider URL templates
PROVIDER_CONFIGS: dict[ProviderType, ProviderConfig] = {
    ProviderType.HELIUS: ProviderConfig(
        provider=ProviderType.HELIUS,
        http_template="https://mainnet.helius-rpc.com/?api-key={api_key}",
        wss_template="wss://mainnet.helius-rpc.com/?api-key={api_key}",
        env_key_prefix="HELIUS_API_KEY",
    ),
    ProviderType.ALCHEMY: ProviderConfig(
        provider=ProviderType.ALCHEMY,
        http_template="https://solana-mainnet.g.alchemy.com/v2/{api_key}",
        wss_template="wss://solana-mainnet.g.alchemy.com/v2/{api_key}",
        env_key_prefix="ALCHEMY_API_KEY",
    ),
    ProviderType.QUICKNODE: ProviderConfig(
        provider=ProviderType.QUICKNODE,
        http_template="https://{api_key}.solana-mainnet.quiknode.pro",
        wss_template="wss://{api_key}.solana-mainnet.quiknode.pro",
        env_key_prefix="QUICKNODE_API_KEY",
    ),
    ProviderType.CHAINSTACK: ProviderConfig(
        provider=ProviderType.CHAINSTACK,
        http_template="https://solana-mainnet.core.chainstack.com/{api_key}",
        wss_template="wss://solana-mainnet.core.chainstack.com/{api_key}",
        env_key_prefix="CHAINSTACK_API_KEY",
    ),
    ProviderType.TRITON: ProviderConfig(
        provider=ProviderType.TRITON,
        http_template="https://mainnet.triton.one/{api_key}",
        wss_template="wss://mainnet.triton.one/{api_key}",
        env_key_prefix="TRITON_API_KEY",
    ),
    ProviderType.DRPC: ProviderConfig(
        provider=ProviderType.DRPC,
        http_template="https://lb.drpc.org/ogrpc?network=solana&dkey={api_key}",
        wss_template="wss://lb.drpc.org/ogws?network=solana&dkey={api_key}",
        env_key_prefix="DRPC_API_KEY",
    ),
    ProviderType.NOWNODES: ProviderConfig(
        provider=ProviderType.NOWNODES,
        http_template="https://sol.nownodes.io/{api_key}",
        wss_template="wss://sol.nownodes.io/{api_key}",
        env_key_prefix="NOWNODES_API_KEY",
    ),
    ProviderType.ANKR: ProviderConfig(
        provider=ProviderType.ANKR,
        http_template="https://rpc.ankr.com/solana/{api_key}",
        wss_template="wss://rpc.ankr.com/solana/ws/{api_key}",
        env_key_prefix="ANKR_API_KEY",
    ),
    ProviderType.LAVA: ProviderConfig(
        provider=ProviderType.LAVA,
        http_template="https://solana.lava.build/rpc/v1/{api_key}",
        wss_template="wss://solana.lava.build/rpc/v1/{api_key}",
        env_key_prefix="LAVA_API_KEY",
    ),
}


class ProviderPool:
    """
    Multi-provider RPC pool with automatic failover and key rotation.
    
    Usage:
        pool = ProviderPool()
        pool.load_from_env()
        
        # Get best HTTP endpoint
        endpoint = pool.get_http_endpoint()
        
        # Get all WSS endpoints for parallel race
        wss_urls = pool.get_wss_endpoints()
    """
    
    def __init__(self) -> None:
        self._endpoints: list[ProviderEndpoint] = []
        self._lock = threading.Lock()
        self._round_robin_index = 0
        
        # Health check interval
        self._last_health_reset = time.time()
        self._health_reset_interval = 300  # Reset metrics every 5 min
    
    def load_from_env(self) -> int:
        """
        Load all API keys from environment variables.
        
        Supports multiple keys per provider:
        - HELIUS_API_KEY (single key)
        - HELIUS_API_KEY_1, HELIUS_API_KEY_2, ... (multiple keys)
        
        Returns:
            Number of endpoints loaded.
        """
        loaded = 0
        
        for provider_type, config in PROVIDER_CONFIGS.items():
            keys = self._get_env_keys(config.env_key_prefix)
            
            for key in keys:
                endpoint = ProviderEndpoint(
                    provider=provider_type,
                    api_key=key,
                    http_url=config.http_template.format(api_key=key),
                    wss_url=config.wss_template.format(api_key=key),
                )
                self._endpoints.append(endpoint)
                loaded += 1
        
        return loaded
    
    def _get_env_keys(self, prefix: str) -> list[str]:
        """Get all API keys for a prefix (supports _1, _2, ... suffixes)."""
        keys = []
        
        # Check base key (e.g., HELIUS_API_KEY)
        base_key = os.getenv(prefix)
        if base_key:
            keys.append(base_key.strip().strip('"').strip("'"))
        
        # Check numbered keys (e.g., HELIUS_API_KEY_1, HELIUS_API_KEY_2)
        for i in range(1, 10):
            numbered_key = os.getenv(f"{prefix}_{i}")
            if numbered_key:
                keys.append(numbered_key.strip().strip('"').strip("'"))
        
        return keys
    
    def add_endpoint(self, endpoint: ProviderEndpoint) -> None:
        """Manually add an endpoint."""
        with self._lock:
            self._endpoints.append(endpoint)
    
    def get_http_endpoint(self, prefer_provider: Optional[ProviderType] = None) -> Optional[ProviderEndpoint]:
        """
        Get the best available HTTP endpoint.
        
        Strategy:
        1. Filter out rate-limited and unhealthy endpoints
        2. Prefer specified provider if given
        3. Sort by latency (fastest first)
        4. Round-robin among top 3 for load distribution
        """
        self._maybe_reset_health()
        
        with self._lock:
            available = [
                ep for ep in self._endpoints
                if ep.is_healthy and not ep.is_rate_limited
            ]
            
            if not available:
                # Fallback: try any endpoint
                available = [ep for ep in self._endpoints if not ep.is_rate_limited]
            
            if not available:
                return None
            
            # Prefer specific provider
            if prefer_provider:
                preferred = [ep for ep in available if ep.provider == prefer_provider]
                if preferred:
                    available = preferred
            
            # Sort by latency (0 latency means untested, put at end)
            available.sort(key=lambda ep: ep.latency_ms if ep.latency_ms > 0 else 9999)
            
            # Round-robin among top 3
            top_n = min(3, len(available))
            idx = self._round_robin_index % top_n
            self._round_robin_index += 1
            
            return available[idx]
    
    def get_wss_endpoints(
        self, 
        max_count: int = 5,
        commitment: str = "processed"
    ) -> list[str]:
        """
        Get WSS endpoints for parallel race.
        
        Returns unique endpoints from different providers for maximum diversity.
        """
        self._maybe_reset_health()
        
        with self._lock:
            available = [
                ep for ep in self._endpoints
                if ep.is_healthy and not ep.is_rate_limited
            ]
            
            if not available:
                available = list(self._endpoints)
            
            # Diversify: pick one from each provider first
            by_provider: dict[ProviderType, list[ProviderEndpoint]] = {}
            for ep in available:
                by_provider.setdefault(ep.provider, []).append(ep)
            
            result = []
            
            # First pass: one from each provider
            for provider, eps in by_provider.items():
                if len(result) >= max_count:
                    break
                # Pick the healthiest one from this provider
                best = min(eps, key=lambda ep: ep.latency_ms if ep.latency_ms > 0 else 9999)
                result.append(best.wss_url)
            
            # Second pass: fill remaining slots
            remaining = [ep for ep in available if ep.wss_url not in result]
            random.shuffle(remaining)
            
            for ep in remaining:
                if len(result) >= max_count:
                    break
                result.append(ep.wss_url)
            
            return result
    
    def get_all_http_urls(self) -> list[str]:
        """Get all HTTP URLs for batch/race requests."""
        with self._lock:
            return [ep.http_url for ep in self._endpoints if ep.is_healthy]
    
    def record_success(self, url: str, latency_ms: float) -> None:
        """Record a successful request to an endpoint."""
        with self._lock:
            for ep in self._endpoints:
                if url in (ep.http_url, ep.wss_url):
                    ep.record_success(latency_ms)
                    break
    
    def record_error(self, url: str, is_rate_limit: bool = False) -> None:
        """Record a failed request to an endpoint."""
        with self._lock:
            for ep in self._endpoints:
                if url in (ep.http_url, ep.wss_url):
                    ep.record_error(is_rate_limit)
                    break
    
    def _maybe_reset_health(self) -> None:
        """Periodically reset health metrics to give recovered endpoints a chance."""
        now = time.time()
        if now - self._last_health_reset > self._health_reset_interval:
            with self._lock:
                for ep in self._endpoints:
                    ep.reset_health()
                self._last_health_reset = now
    
    def get_stats(self) -> dict:
        """Get pool statistics for monitoring."""
        with self._lock:
            return {
                "total_endpoints": len(self._endpoints),
                "healthy_endpoints": sum(1 for ep in self._endpoints if ep.is_healthy),
                "rate_limited": sum(1 for ep in self._endpoints if ep.is_rate_limited),
                "by_provider": {
                    provider.value: sum(1 for ep in self._endpoints if ep.provider == provider)
                    for provider in ProviderType
                },
                "avg_latency_ms": (
                    sum(ep.latency_ms for ep in self._endpoints if ep.latency_ms > 0) /
                    max(1, sum(1 for ep in self._endpoints if ep.latency_ms > 0))
                ),
            }
    
    def __len__(self) -> int:
        return len(self._endpoints)
    
    def __repr__(self) -> str:
        stats = self.get_stats()
        return f"ProviderPool({stats['healthy_endpoints']}/{stats['total_endpoints']} healthy)"


# Global singleton
_provider_pool: Optional[ProviderPool] = None


def get_provider_pool() -> ProviderPool:
    """Get or create the global ProviderPool singleton."""
    global _provider_pool
    if _provider_pool is None:
        _provider_pool = ProviderPool()
        count = _provider_pool.load_from_env()
        print(f"[ProviderPool] Loaded {count} endpoints from environment")
    return _provider_pool
