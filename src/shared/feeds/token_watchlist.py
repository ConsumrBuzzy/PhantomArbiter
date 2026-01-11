"""
Token Watchlist Feed
====================
Tracks prices for top meme/scalp targets across multiple DEX venues.
Broadcasts price updates to the dashboard.
"""

import asyncio
import time
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass, field

try:
    import httpx
except ImportError:
    httpx = None

from src.shared.system.logging import Logger


# Top meme tokens to track (can be extended via config)
DEFAULT_WATCHLIST = {
    "SOL": {
        "mint": "So11111111111111111111111111111111111111112",
        "symbol": "SOL",
        "category": "major"
    },
    "BONK": {
        "mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
        "symbol": "BONK",
        "category": "meme"
    },
    "WIF": {
        "mint": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
        "symbol": "WIF",
        "category": "meme"
    },
    "POPCAT": {
        "mint": "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr",
        "symbol": "POPCAT",
        "category": "meme"
    },
    "PNUT": {
        "mint": "2qEHjDLDLbuBgRYvsxhc5D6uDWAivNFZGan56P1tpump",
        "symbol": "PNUT",
        "category": "meme"
    },
    "GOAT": {
        "mint": "CzLsuqpE3yQfNbcNY6RxVqHABQHR3ePiPDrYXzFYpump",
        "symbol": "GOAT",
        "category": "meme"
    },
    "FARTCOIN": {
        "mint": "9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump",
        "symbol": "FARTCOIN",
        "category": "meme"
    },
    "AI16Z": {
        "mint": "HeLp6NuQkmYB4pYWo2zYs22mESHXPQYzXbB8n4V98jwC",
        "symbol": "AI16Z",
        "category": "ai"
    },
    "GRIFFAIN": {
        "mint": "KENJSbHwdw1PqvbNCgLJ4F2Scpz5tHkB8YGixzpump",
        "symbol": "GRIFFAIN",
        "category": "ai"
    },
    "ZEREBRO": {
        "mint": "8x5VqbHA8D7NkD52uNuS5nnt3PwA8pLD34ymskeSo2Wn",
        "symbol": "ZEREBRO",
        "category": "ai"
    }
}

# DEX venues to check
VENUES = ["jupiter", "raydium", "orca"]


@dataclass
class TokenPrice:
    """Price data for a single token across venues."""
    symbol: str
    mint: str
    category: str
    prices: Dict[str, float] = field(default_factory=dict)  # venue -> price
    best_bid: float = 0.0
    best_ask: float = 0.0
    spread_pct: float = 0.0
    volume_24h: float = 0.0
    change_24h: float = 0.0
    change_5m: float = 0.0
    change_1h: float = 0.0
    last_update: float = 0.0


class TokenWatchlistFeed:
    """
    Multi-token price tracker for scalp/arb targets.
    Fetches prices from DexScreener (aggregates all DEX venues).
    """
    
    DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/tokens"
    
    def __init__(self, interval: float = 5.0, watchlist: Dict = None):
        self.interval = interval
        self.watchlist = watchlist or DEFAULT_WATCHLIST
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._callback: Optional[Callable] = None
        self._prices: Dict[str, TokenPrice] = {}
        
    def set_callback(self, callback: Callable[[Dict[str, TokenPrice]], None]):
        """Set callback for price updates."""
        self._callback = callback
        
    def add_token(self, symbol: str, mint: str, category: str = "custom"):
        """Add a token to the watchlist."""
        self.watchlist[symbol] = {
            "mint": mint,
            "symbol": symbol,
            "category": category
        }
        
    def remove_token(self, symbol: str):
        """Remove a token from the watchlist."""
        self.watchlist.pop(symbol, None)
        self._prices.pop(symbol, None)
        
    def start(self):
        """Start the price feed."""
        if httpx is None:
            Logger.warning("[TokenWatchlist] httpx not installed - feed disabled")
            return
            
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        Logger.info(f"[TokenWatchlist] Started tracking {len(self.watchlist)} tokens")
        
    def stop(self):
        """Stop the price feed."""
        self._running = False
        if self._task:
            self._task.cancel()
        Logger.info("[TokenWatchlist] Stopped")
        
    @property
    def prices(self) -> Dict[str, TokenPrice]:
        return self._prices
        
    async def _run_loop(self):
        """Main fetch loop."""
        while self._running:
            try:
                await self._fetch_all_prices()
                
                if self._callback and self._prices:
                    await self._callback(self._prices)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                Logger.debug(f"[TokenWatchlist] Error: {e}")
                
            await asyncio.sleep(self.interval)
            
    async def _fetch_all_prices(self):
        """Fetch prices for all tokens in watchlist."""
        mints = [t["mint"] for t in self.watchlist.values()]
        
        # DexScreener supports batch requests (comma-separated)
        # But limit to 30 tokens per request
        batch_size = 30
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            for i in range(0, len(mints), batch_size):
                batch = mints[i:i+batch_size]
                await self._fetch_batch(client, batch)
                
    async def _fetch_batch(self, client: httpx.AsyncClient, mints: List[str]):
        """Fetch a batch of token prices from DexScreener."""
        try:
            # DexScreener accepts comma-separated mints
            mint_str = ",".join(mints)
            response = await client.get(f"{self.DEXSCREENER_API}/{mint_str}")
            
            if response.status_code != 200:
                return
                
            data = response.json()
            pairs = data.get("pairs", [])
            
            # Group pairs by base token
            token_pairs: Dict[str, List] = {}
            for pair in pairs:
                base_mint = pair.get("baseToken", {}).get("address")
                if base_mint:
                    if base_mint not in token_pairs:
                        token_pairs[base_mint] = []
                    token_pairs[base_mint].append(pair)
                    
            # Process each token
            for symbol, info in self.watchlist.items():
                mint = info["mint"]
                pairs_for_token = token_pairs.get(mint, [])
                
                if not pairs_for_token:
                    continue
                    
                # Extract prices by venue
                venue_prices = {}
                best_price = 0.0
                total_volume = 0.0
                change_24h = 0.0
                
                for pair in pairs_for_token:
                    dex = pair.get("dexId", "unknown").lower()
                    price = float(pair.get("priceUsd", 0) or 0)
                    volume = float(pair.get("volume", {}).get("h24", 0) or 0)
                    change = float(pair.get("priceChange", {}).get("h24", 0) or 0)
                    change_5m = float(pair.get("priceChange", {}).get("m5", 0) or 0)
                    change_1h = float(pair.get("priceChange", {}).get("h1", 0) or 0)
                    
                    if price > 0:
                        # Map DEX names
                        if "raydium" in dex:
                            venue_prices["raydium"] = price
                        elif "orca" in dex:
                            venue_prices["orca"] = price
                        elif "meteora" in dex:
                            venue_prices["meteora"] = price
                        else:
                            venue_prices[dex] = price
                            
                        if price > best_price:
                            best_price = price
                            change_24h = change
                            
                    total_volume += volume
                    
                # Calculate spread across venues
                prices_list = [p for p in venue_prices.values() if p > 0]
                spread_pct = 0.0
                if len(prices_list) >= 2:
                    spread_pct = (max(prices_list) - min(prices_list)) / min(prices_list) * 100
                    
                # Update tracked price
                self._prices[symbol] = TokenPrice(
                    symbol=symbol,
                    mint=mint,
                    category=info["category"],
                    prices=venue_prices,
                    best_bid=min(prices_list) if prices_list else 0,
                    best_ask=max(prices_list) if prices_list else 0,
                    spread_pct=spread_pct,
                    volume_24h=total_volume,
                    change_24h=change_24h,
                    change_5m=change_5m,
                    change_1h=change_1h,
                    last_update=time.time()
                )
                
        except Exception as e:
            Logger.debug(f"[TokenWatchlist] Fetch error: {e}")


# Singleton
_watchlist_feed: Optional[TokenWatchlistFeed] = None


def get_token_watchlist() -> TokenWatchlistFeed:
    """Get or create the token watchlist singleton."""
    global _watchlist_feed
    if _watchlist_feed is None:
        _watchlist_feed = TokenWatchlistFeed()
    return _watchlist_feed
