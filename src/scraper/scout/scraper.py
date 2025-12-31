import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class TokenScraper:
    def __init__(self):
        self.birdeye_key = os.getenv("BIRDEYE_API_KEY")
        self.seen_tokens = set()

    async def start_scanning(self, interval: float = 60.0):
        """Background scanning loop for new tokens."""
        import asyncio
        from src.shared.system.signal_bus import signal_bus, Signal, SignalType
        from src.shared.system.logging import Logger
        
        Logger.info("[SCRAPER] 🦅 Starting background scan for Trending Solana Tokens...")
        
        while True:
            try:
                # Run the synchronous scrape in a thread
                candidates = await asyncio.to_thread(self.get_candidates)
                
                new_count = 0
                for c in candidates:
                    sig_id = c['address']
                    if sig_id not in self.seen_tokens:
                        self.seen_tokens.add(sig_id)
                        new_count += 1
                        
                        # Emit Discovery Signal (Purple Flash)
                        signal_bus.emit(Signal(
                            type=SignalType.MARKET_UPDATE,
                            source="DISCOVERY",
                            data={
                                "symbol": c.get("symbol", "NEW"),
                                "mint": c.get("address"),
                                "token": c.get("address"),
                                "price": 0.0,
                                "timestamp": asyncio.get_event_loop().time()
                            }
                        ))
                
                if new_count > 0:
                    Logger.info(f"[SCRAPER] 🔭 Discovered {new_count} new trending tokens")
                    
            except Exception as e:
                Logger.warning(f"[SCRAPER] Error: {e}")
                
            await asyncio.sleep(interval)

    def get_candidates(self):
        """Dispatches to the best available source."""
        if self.birdeye_key:
            return self._scrape_birdeye()
        else:
            print(
                "[SCRAPER] ⚠️ No Birdeye Key found. Falling back to DexScreener (Boosted)."
            )
            return self._scrape_dexscreener()

    def _scrape_birdeye(self):
        """
        Source: Birdeye Trending API
        Quality: High (Real volume/rank)
        """
        print("[SCRAPER] 🦅 Scanning Birdeye Trending...")
        url = "https://public-api.birdeye.so/defi/token_trending?sort_by=rank&limit=20"
        headers = {"X-API-KEY": self.birdeye_key, "accept": "application/json"}

        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                candidates = []
                for t in data.get("data", {}).get("tokens", []):
                    # Filter: Min $10k Liquidity
                    if t.get("liquidity", 0) > 10000:
                        candidates.append(
                            {
                                "address": t["address"],
                                "symbol": t["symbol"],
                                "source": "birdeye_trending",
                            }
                        )
                return candidates
            elif resp.status_code == 401:
                print("[SCRAPER] ❌ Birdeye Key Invalid.")
                return self._scrape_dexscreener()
            else:
                print(f"[SCRAPER] ❌ Birdeye Error: {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"[SCRAPER] ❌ Birdeye Error: {e}")

        return []

    def _scrape_dexscreener(self):
        """
        Source: DexScreener 'Latest Boosted' (Proxy for Trending)
        Quality: Medium (Paid boosts = active interest)
        """
        print("[SCRAPER] 🦅 Scanning DexScreener Boosted...")
        url = "https://api.dexscreener.com/token-boosts/latest/v1"

        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                candidates = []
                # DexScreener returns a list of boosted profiles
                for t in data[:20]:  # Check top 20
                    # Check chainId to ensure it's Solana
                    if t.get("chainId") == "solana":
                        # Try to get symbol from URL or generic fallback
                        # url example: https://dexscreener.com/solana/....
                        symbol = "UNKNOWN"
                        if "url" in t:
                            parts = t["url"].split("/")
                            if len(parts) > 1:
                                # We don't get ticker easily from boosts endpoint?
                                # Boosts endpoint returns: url, chainId, tokenAddress, icon, header, description...
                                # But maybe not symbol?
                                # We can fetch symbol detail later or infer it.
                                pass

                        candidates.append(
                            {
                                "address": t["tokenAddress"],
                                "symbol": symbol,  # Placeholder
                                "source": "dexscreener_boosted",
                            }
                        )
                return candidates
            else:
                print(f"[SCRAPER] ❌ DexScreener Error: {resp.status_code}")
        except Exception as e:
            print(f"[SCRAPER] ❌ DexScreener Error: {e}")

        return []


# --- Quick Test ---
if __name__ == "__main__":
    scraper = TokenScraper()
    found = scraper.get_candidates()
    print(f"\n🎯 Found {len(found)} Candidates:")
    for c in found:
        print(f"   - {c['symbol']} ({c['address']})")
