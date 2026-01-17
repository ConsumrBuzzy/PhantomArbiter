"""
Cache Manager for Drift SDK Singleton
=====================================

Provides thread-safe caching for market data to reduce RPC calls and prevent rate limiting.

Features:
- TTL-based cache expiration
- Thread-safe access with asyncio.Lock
- Automatic cleanup of expired entries
- Type-safe cache operations

Usage:
    cache = CacheManager()
    await cache.set("SOL-PERP:funding", 0.05, ttl=30)
    value = await cache.get("SOL-PERP:funding")
"""

import asyncio
import time
from typing import Any, Optional, Dict
from dataclasses import dataclass


@dataclass
class CacheEntry:
    """
    Cache entry with TTL support.
    
    Attributes:
        value: Cached data
        expires_at: Unix timestamp when entry expires
    """
    value: Any
    expires_at: float
    
    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return time.time() > self.expires_at


class CacheManager:
    """
    Thread-safe cache manager with TTL support.
    
    Provides caching for Drift market data to reduce RPC calls and prevent
    HTTP 429 rate limiting errors.
    """
    
    def __init__(self):
        """Initialize cache manager."""
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get cached value by key.
        
        Args:
            key: Cache key
        
        Returns:
            Cached value if exists and not expired, None otherwise
        """
        async with self._lock:
            entry = self._cache.get(key)
            
            if entry is None:
                return None
            
            if entry.is_expired():
                # Remove expired entry
                del self._cache[key]
                return None
            
            return entry.value
    
    async def set(self, key: str, value: Any, ttl: int = 30) -> None:
        """
        Set cached value with TTL.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (default: 30)
        """
        expires_at = time.time() + ttl
        
        async with self._lock:
            self._cache[key] = CacheEntry(value=value, expires_at=expires_at)
    
    async def clear(self) -> None:
        """Clear all cached entries."""
        async with self._lock:
            self._cache.clear()
    
    async def cleanup_expired(self) -> int:
        """
        Remove all expired entries.
        
        Returns:
            Number of entries removed
        """
        removed_count = 0
        current_time = time.time()
        
        async with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.expires_at <= current_time
            ]
            
            for key in expired_keys:
                del self._cache[key]
                removed_count += 1
        
        return removed_count
    
    async def size(self) -> int:
        """Get current cache size."""
        async with self._lock:
            return len(self._cache)
    
    def is_expired(self, key: str) -> bool:
        """
        Check if cache entry is expired (synchronous).
        
        Args:
            key: Cache key
        
        Returns:
            True if expired or doesn't exist, False otherwise
        """
        entry = self._cache.get(key)
        if entry is None:
            return True
        return entry.is_expired()