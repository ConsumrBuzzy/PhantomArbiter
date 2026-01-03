import aiohttp
import asyncio
import os
from typing import List, Dict, Any, Optional
from .base import BaseScraper, logger

class BirdeyeScraper(BaseScraper):
    """
    Birdeye Scraper for 'Trending' and 'New' tokens.
    Requires BIRDEYE_API_KEY env var (public/free tier supported).
    """

    BASE_URL = "https://public-api.birdeye.so/defi/token_overview"
    # Using public endpoints where possible, or authenticated if key exists
    
    def __init__(self, mints: List[str], interval: float = 5.0):
        # Slower interval as Birdeye is stricter on limits
        super().__init__("Birdeye", "BIRDEYE", interval)
        self.mints = mints
        self.api_key = os.getenv("BIRDEYE_API_KEY", "")
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self):
        self._session = aiohttp.ClientSession(headers={
            "X-API-KEY": self.api_key,
            "x-chain": "solana",
            "accept": "application/json"
        })
        await super().start()

    async def stop(self):
        await super().stop()
        if self._session:
            await self._session.close()

    async def scrape(self) -> List[Dict[str, Any]]:
        """
        Fetch prices using Token Overview endpoint.
        Birdeye free tier is restrictive, so we batch carefully or use public endpoints.
        """
        if not self.mints or not self._session:
            return []
            
        results = []
        
        # Birdeye Multi-Price endpoint: https://public-api.birdeye.so/defi/multi_price
        # Max 50 addresses
        chunk_size = 50
        chunks = [self.mints[i:i + chunk_size] for i in range(0, len(self.mints), chunk_size)]

        for chunk in chunks:
            try:
                # Use public multi_price endpoint
                url = "https://public-api.birdeye.so/defi/multi_price"
                # If using Enterprise/Auth, url might differ
                
                params = {"list_address": ",".join(chunk)}
                
                async with self._session.get(url, params=params, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("success"):
                            items = data.get("data", {})
                            for mint, info in items.items():
                                if info:
                                    price = info.get("value")
                                    if price:
                                        results.append({
                                            "token": mint,
                                            "price": float(price),
                                            "source": "BIRDEYE",
                                            "timestamp": int(asyncio.get_running_loop().time() * 1000),
                                            "metadata": {
                                                "update_unix_time": info.get("updateUnixTime")
                                            }
                                        })
                    elif resp.status == 401:
                        logger.warning("[Birdeye] Unauthorized - Check API Key")
                        await asyncio.sleep(60) # Long backoff
                    elif resp.status == 429:
                        logger.warning("[Birdeye] Rate Limit")
                        await asyncio.sleep(10)

            except Exception as e:
                logger.error(f"[Birdeye] Chunk failed: {e}")

        return results
