"""
SharedPriceCache - Thread-Safe Price Storage
=============================================
Central cache for real-time prices from WebSocket feeds.
"""

import threading
import time


class SharedPriceCache:
    """Thread-safe price cache for real-time data."""
    
    def __init__(self):
        self.prices = {}  # {mint: {"price": float, "timestamp": float}}
        self.lock = threading.Lock()
    
    def update_price(self, mint: str, price: float):
        """Update price for a mint (called from WebSocket thread)."""
        with self.lock:
            self.prices[mint] = {
                "price": price,
                "timestamp": time.time()
            }
    
    def get_price(self, mint: str, max_age_seconds: float = 30.0) -> float:
        """
        Get cached price if fresh enough.
        
        Args:
            mint: Token mint address
            max_age_seconds: Maximum age before considered stale
            
        Returns:
            Price if fresh, 0.0 if stale or missing
        """
        with self.lock:
            data = self.prices.get(mint)
            if data:
                age = time.time() - data["timestamp"]
                if age <= max_age_seconds:
                    return data["price"]
        return 0.0
    
    def get_all_prices(self) -> dict:
        """Get snapshot of all cached prices."""
        with self.lock:
            return {
                mint: data["price"] 
                for mint, data in self.prices.items()
            }
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        with self.lock:
            now = time.time()
            total = len(self.prices)
            fresh = sum(1 for d in self.prices.values() if now - d["timestamp"] < 30)
            return {
                "total_cached": total,
                "fresh_count": fresh,
                "stale_count": total - fresh
            }


# Global cache instance
price_cache = SharedPriceCache()
