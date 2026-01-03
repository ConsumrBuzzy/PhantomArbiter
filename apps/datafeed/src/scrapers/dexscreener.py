import aiohttp
import asyncio
from typing import List, Dict, Any, Optional
from .base import BaseScraper, logger

class DexScreenerScraper(BaseScraper):
    """
    High-Speed DexScreener Scraper.
    Fetches latest profiles for active tokens.
    """
    
    BASE_URL = "https://api.dexscreener.com/latest/dex/tokens"

    def __init__(self, mints: List[str], interval: float = 2.0):
        super().__init__("DexScreener", "DEXSCREENER", interval)
        self.mints = mints
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self):
        self._session = aiohttp.ClientSession()
        await super().start()

    async def stop(self):
        await super().stop()
        if self._session:
            await self._session.close()

    async def scrape(self) -> List[Dict[str, Any]]:
        """
        Fetch prices for configured mints in chunks of 30.
        """
        if not self.mints or not self._session:
            return []

        chunk_size = 30
        results = []
        
        # Split into chunks
        chunks = [self.mints[i:i + chunk_size] for i in range(0, len(self.mints), chunk_size)]
        
        for chunk in chunks:
            try:
                ids = ",".join(chunk)
                url = f"{self.BASE_URL}/{ids}"
                
                async with self._session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        pairs = data.get("pairs", [])
                        
                        # Process pairs into standardized updates
                        updates = self._process_pairs(pairs, chunk)
                        results.extend(updates)
                    elif resp.status == 429:
                        logger.warning("[DexScreener] Rate Limit (429)")
                        await asyncio.sleep(5)  # Backoff
                    else:
                        logger.warning(f"[DexScreener] Error {resp.status}")

            except Exception as e:
                logger.error(f"[DexScreener] Chunk failed: {e}")

        return results

    def _process_pairs(self, pairs: List[Dict], chunk_mints: List[str]) -> List[Dict[str, Any]]:
        """
        Normalize DexScreener pairs into PricePoints.
        Selects primary market (highest liquidity) for each mint.
        """
        updates = []
        mint_map = {m.lower(): m for m in chunk_mints}  # Case insensitive lookup
        grouped_pairs = {}

        # Group by canonical mint
        for pair in pairs:
            base_mint = pair.get("baseToken", {}).get("address", "").lower()
            if base_mint in mint_map:
                canonical_mint = mint_map[base_mint]
                if canonical_mint not in grouped_pairs:
                    grouped_pairs[canonical_mint] = []
                grouped_pairs[canonical_mint].append(pair)

        # Select best pair and normalize
        for mint, token_pairs in grouped_pairs.items():
            best_pair = self._select_best_pair(token_pairs)
            if best_pair:
                price = float(best_pair.get("priceUsd") or 0)
                if price > 0:
                    updates.append({
                        "token": mint,
                        "price": price,
                        "source": "DEXSCREENER",
                        "timestamp": int(asyncio.get_running_loop().time() * 1000),
                        "metadata": {
                            "liquidity": float(best_pair.get("liquidity", {}).get("usd", 0)),
                            "volume_24h": float(best_pair.get("volume", {}).get("h24", 0)),
                            "dex": best_pair.get("dexId"),
                            "pair_address": best_pair.get("pairAddress")
                        }
                    })
        return updates

    def _select_best_pair(self, pairs: List[Dict]) -> Dict:
        """Sort by liquidity desc."""
        return sorted(pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0), reverse=True)[0]
