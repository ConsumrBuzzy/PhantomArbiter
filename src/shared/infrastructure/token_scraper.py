
import requests
import time
import os
from typing import Dict, Optional, List
from src.shared.system.logging import Logger

class TokenScraper:
    """
    V67.8 / V72.5: Token Metadata Scraper with Multi-API + Web Scraping
    
    Priority Chain (V72.5):
    1. Memory Cache
    2. Jupiter Token List
    3. DexScreener API
    4. Helius DAS API
    5. Birdeye API
    6. CoinMarketCap API (NEW)
    7. Web Scraping (DEXTools) (NEW)
    8. Unknown fallback
    """
    
    DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/tokens/{mint}"
    JUPITER_URL = "https://token.jup.ag/strict"
    BIRDEYE_URL = "https://public-api.birdeye.so/defi/token_overview?address={mint}"
    CMC_URL = "https://pro-api.coinmarketcap.com/v2/cryptocurrency/info"
    
    # V72.5: Web scraping URLs (no API key needed)
    DEXTOOLS_URL = "https://www.dextools.io/app/en/solana/pair-explorer/{mint}"
    SOLSCAN_URL = "https://solscan.io/token/{mint}"
    
    # V73.0: Negative cache TTL (don't retry failed sources for this long)
    NEGATIVE_CACHE_TTL = 3600  # 1 hour before retrying failed source
    
    def __init__(self):
        self.cache: Dict[str, Dict] = {}  # mint -> {symbol, name, ...}
        self.cache_ttl = 3600  # 1 hour for memory cache
        self.last_request = 0
        self.rate_limit = 1.0  # 1 second between requests
        
        # V73.0: Track failed sources per mint to avoid retrying
        # Format: {mint: {source: timestamp_of_failure}}
        self.failed_sources: Dict[str, Dict[str, float]] = {}
        
        # Load from DB on init
        self._load_from_db()
        
        # Preload Jupiter token list (optional, for fallback)
        self.jupiter_list: Dict[str, Dict] = {}
        self._load_jupiter_list()
        
        Logger.info(f"[SCRAPER] Token Scraper V73.0 Initialized (DB: {len(self.cache)}, Jupiter: {len(self.jupiter_list)})")

    def _load_from_db(self):
        """V67.9: Load cached tokens from database."""
        try:
            from src.shared.system.db_manager import db_manager
            with db_manager.cursor() as c:
                c.execute("SELECT mint, symbol, name, price, liquidity, volume_24h, dex, source, first_seen, last_seen FROM tokens")
                rows = c.fetchall()
                for row in rows:
                    self.cache[row[0]] = {
                        "symbol": row[1],
                        "name": row[2],
                        "price": row[3],
                        "liquidity": row[4],
                        "volume24h": row[5],
                        "dex": row[6],
                        "source": row[7],
                        "first_seen": row[8],
                        "last_seen": row[9],
                        "_cached_at": row[9]  # Use last_seen as cache time
                    }
        except Exception as e:
            Logger.debug(f"[SCRAPER] DB Load Failed: {e}")

    def _save_to_db(self, mint: str, info: Dict):
        """V67.9: Save token to database."""
        try:
            from src.shared.system.db_manager import db_manager
            now = time.time()
            with db_manager.cursor(commit=True) as c:
                c.execute("""
                INSERT INTO tokens (mint, symbol, name, price, liquidity, volume_24h, dex, source, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mint) DO UPDATE SET
                    symbol=excluded.symbol,
                    name=excluded.name,
                    price=excluded.price,
                    liquidity=excluded.liquidity,
                    volume_24h=excluded.volume_24h,
                    dex=excluded.dex,
                    source=excluded.source,
                    last_seen=excluded.last_seen
                """, (
                    mint,
                    info.get("symbol", "???"),
                    info.get("name", "Unknown"),
                    info.get("price", 0),
                    info.get("liquidity", 0),
                    info.get("volume24h", 0),
                    info.get("dex", ""),
                    info.get("source", "UNKNOWN"),
                    now,  # first_seen (won't update on conflict)
                    now   # last_seen
                ))
        except Exception as e:
            Logger.debug(f"[SCRAPER] DB Save Failed: {e}")

    def _load_jupiter_list(self):
        """Load Jupiter verified token list as fallback."""
        try:
            resp = requests.get(self.JUPITER_URL, timeout=10)
            if resp.status_code == 200:
                tokens = resp.json()
                for t in tokens:
                    self.jupiter_list[t.get("address", "")] = {
                        "symbol": t.get("symbol", "???"),
                        "name": t.get("name", "Unknown"),
                        "decimals": t.get("decimals", 9),
                        "logoURI": t.get("logoURI", "")
                    }
        except Exception as e:
            Logger.debug(f"[SCRAPER] Jupiter List Load Failed: {e}")

    # ═══════════════════════════════════════════════════════════════════
    # V73.0: Negative Cache Helpers
    # ═══════════════════════════════════════════════════════════════════
    
    def _should_skip_source(self, mint: str, source: str) -> bool:
        """Check if we should skip this source for this mint (recently failed)."""
        if mint not in self.failed_sources:
            return False
        
        failed_at = self.failed_sources[mint].get(source, 0)
        if failed_at == 0:
            return False
        
        # Skip if failure was within the TTL
        if time.time() - failed_at < self.NEGATIVE_CACHE_TTL:
            return True
        
        # TTL expired, clear and allow retry
        del self.failed_sources[mint][source]
        return False
    
    def _mark_source_failed(self, mint: str, source: str):
        """Mark a source as failed for this mint."""
        if mint not in self.failed_sources:
            self.failed_sources[mint] = {}
        self.failed_sources[mint][source] = time.time()
    
    def _clear_failed_sources(self, mint: str):
        """Clear all failed sources for a mint (call when found successfully)."""
        if mint in self.failed_sources:
            del self.failed_sources[mint]

    def lookup(self, mint: str) -> Dict:
        """
        Lookup token metadata by mint address.
        
        Returns: {
            'symbol': 'SOL',
            'name': 'Solana',
            'price': 150.0,
            'liquidity': 1000000.0,
            'volume24h': 500000.0,
            'source': 'DEXSCREENER' | 'JUPITER' | 'DB' | 'UNKNOWN'
        }
        """
        # 1. Check memory cache (hot path)
        if mint in self.cache:
            cached = self.cache[mint]
            # Return if fresh enough for memory cache
            if time.time() - cached.get("_cached_at", 0) < self.cache_ttl:
                cached["source"] = "DB"  # Mark as from cache
                return cached
        
        # 2. Check Jupiter list (fast fallback)
        if mint in self.jupiter_list:
            result = {**self.jupiter_list[mint], "source": "JUPITER", "_cached_at": time.time()}
            self.cache[mint] = result
            self._save_to_db(mint, result)
            return result
        
        # 3. Rate limit
        elapsed = time.time() - self.last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        
        # 4. Call DexScreener (V73.0: skip if previously failed)
        if not self._should_skip_source(mint, "DEXSCREENER"):
            try:
                url = self.DEXSCREENER_URL.format(mint=mint)
                resp = requests.get(url, timeout=5)
                self.last_request = time.time()
                
                if resp.status_code == 200:
                    data = resp.json()
                    pairs = data.get("pairs", [])
                    
                    if pairs:
                        pair = pairs[0]
                        base_token = pair.get("baseToken", {})
                        
                        result = {
                            "symbol": base_token.get("symbol", "???"),
                            "name": base_token.get("name", "Unknown"),
                            "price": float(pair.get("priceUsd", 0)),
                            "liquidity": float(pair.get("liquidity", {}).get("usd", 0)),
                            "volume24h": float(pair.get("volume", {}).get("h24", 0)),
                            "dex": pair.get("dexId", "unknown"),
                            "source": "DEXSCREENER",
                            "_cached_at": time.time()
                        }
                        self.cache[mint] = result
                        self._save_to_db(mint, result)
                        self._clear_failed_sources(mint)
                        return result
                    else:
                        # No pairs found - mark as failed for this source
                        self._mark_source_failed(mint, "DEXSCREENER")
                        
            except Exception as e:
                Logger.debug(f"[SCRAPER] DexScreener Lookup Failed: {e}")
        
        # 5. V70.0: Try Helius DAS API (getAsset) for newly launched tokens
        try:
            import os
            helius_key = os.getenv("HELIUS_API_KEY")
            if helius_key:
                helius_url = f"https://mainnet.helius-rpc.com/?api-key={helius_key}"
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getAsset",
                    "params": {"id": mint}
                }
                resp = requests.post(helius_url, json=payload, timeout=5)
                self.last_request = time.time()
                
                if resp.status_code == 200:
                    data = resp.json()
                    if "result" in data:
                        asset = data["result"]
                        content = asset.get("content", {})
                        metadata = content.get("metadata", {})
                        
                        symbol = metadata.get("symbol", "")
                        name = metadata.get("name", "")
                        
                        if symbol and symbol != "":
                            result = {
                                "symbol": symbol,
                                "name": name or symbol,
                                "price": 0,
                                "liquidity": 0,
                                "source": "HELIUS_DAS",
                                "_cached_at": time.time()
                            }
                            self.cache[mint] = result
                            self._save_to_db(mint, result)
                            Logger.debug(f"[SCRAPER] Helius DAS: Found {symbol} for {mint[:8]}")
                            return result
        except Exception as e:
            Logger.debug(f"[SCRAPER] Helius DAS Lookup Failed: {e}")
        
        # 6. V71.0: Try Birdeye API (requires BIRDEYE_API_KEY)
        try:
            birdeye_key = os.getenv("BIRDEYE_API_KEY")
            if birdeye_key:
                url = self.BIRDEYE_URL.format(mint=mint)
                headers = {"X-API-KEY": birdeye_key}
                resp = requests.get(url, headers=headers, timeout=5)
                self.last_request = time.time()
                
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success") and data.get("data"):
                        token_data = data["data"]
                        symbol = token_data.get("symbol", "")
                        name = token_data.get("name", "")
                        
                        if symbol and symbol != "":
                            result = {
                                "symbol": symbol,
                                "name": name or symbol,
                                "price": float(token_data.get("price", 0)),
                                "liquidity": float(token_data.get("liquidity", 0)),
                                "volume24h": float(token_data.get("v24hUSD", 0)),
                                "source": "BIRDEYE",
                                "_cached_at": time.time()
                            }
                            self.cache[mint] = result
                            self._save_to_db(mint, result)
                            Logger.debug(f"[SCRAPER] Birdeye: Found {symbol} for {mint[:8]}")
                            return result
        except Exception as e:
            Logger.debug(f"[SCRAPER] Birdeye Lookup Failed: {e}")
        
        # 7. V72.5: Try CoinMarketCap API
        try:
            cmc_key = os.getenv("COINMARKETCAP_API_KEY")
            if cmc_key:
                headers = {
                    "X-CMC_PRO_API_KEY": cmc_key,
                    "Accept": "application/json"
                }
                # CMC uses slug or address lookup
                params = {"address": mint}
                resp = requests.get(self.CMC_URL, headers=headers, params=params, timeout=5)
                self.last_request = time.time()
                
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status", {}).get("error_code") == 0:
                        # CMC returns dict keyed by ID
                        tokens = data.get("data", {})
                        if tokens:
                            token_data = list(tokens.values())[0]
                            symbol = token_data.get("symbol", "")
                            name = token_data.get("name", "")
                            
                            if symbol:
                                result = {
                                    "symbol": symbol,
                                    "name": name or symbol,
                                    "price": 0,
                                    "liquidity": 0,
                                    "source": "CMC",
                                    "_cached_at": time.time()
                                }
                                self.cache[mint] = result
                                self._save_to_db(mint, result)
                                Logger.debug(f"[SCRAPER] CMC: Found {symbol} for {mint[:8]}")
                                return result
        except Exception as e:
            Logger.debug(f"[SCRAPER] CMC Lookup Failed: {e}")
        
        # 8. V72.5: Web Scraping Fallback (Solscan HTML parse)
        try:
            # Light scraping - just get page title which often contains token name
            url = self.SOLSCAN_URL.format(mint=mint)
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = requests.get(url, headers=headers, timeout=5)
            self.last_request = time.time()
            
            if resp.status_code == 200:
                html = resp.text
                # Parse title: "TokenName (SYMBOL) | Solscan"
                import re
                title_match = re.search(r'<title>([^|]+)\|', html)
                if title_match:
                    title = title_match.group(1).strip()
                    # Parse "TokenName (SYMBOL)" format
                    name_match = re.search(r'^(.+?)\s*\(([A-Z0-9]+)\)', title)
                    if name_match:
                        name = name_match.group(1).strip()
                        symbol = name_match.group(2).strip()
                        
                        result = {
                            "symbol": symbol,
                            "name": name,
                            "price": 0,
                            "liquidity": 0,
                            "source": "SOLSCAN_SCRAPE",
                            "_cached_at": time.time()
                        }
                        self.cache[mint] = result
                        self._save_to_db(mint, result)
                        Logger.debug(f"[SCRAPER] Solscan Scrape: Found {symbol} for {mint[:8]}")
                        return result
        except Exception as e:
            Logger.debug(f"[SCRAPER] Solscan Scrape Failed: {e}")
        
        # 9. Return unknown with shortened mint
        return {
            "symbol": f"UNK_{mint[:4]}",
            "name": "Unknown Token",
            "source": "UNKNOWN"
        }

    def get_symbol(self, mint: str) -> str:
        """Convenience method to get just the symbol."""
        info = self.lookup(mint)
        return info.get("symbol", mint[:6])

    def get_name(self, mint: str) -> str:
        """Convenience method to get just the name."""
        info = self.lookup(mint)
        return info.get("name", "Unknown")

    def get_all_tokens(self) -> List[Dict]:
        """V67.9: Get all known tokens for ML training."""
        try:
            from src.shared.system.db_manager import db_manager
            with db_manager.cursor() as c:
                c.execute("SELECT mint, symbol, name, price, liquidity, volume_24h, first_seen, last_seen FROM tokens ORDER BY last_seen DESC")
                rows = c.fetchall()
                return [
                    {
                        "mint": r[0], "symbol": r[1], "name": r[2],
                        "price": r[3], "liquidity": r[4], "volume24h": r[5],
                        "first_seen": r[6], "last_seen": r[7]
                    }
                    for r in rows
                ]
        except Exception as e:
            Logger.error(f"[SCRAPER] get_all_tokens failed: {e}")
            return []

    def get_stats(self) -> Dict:
        """Get scraper statistics."""
        return {
            "memory_cache": len(self.cache),
            "jupiter_list": len(self.jupiter_list),
            "db_tokens": len(self.get_all_tokens())
        }


# Singleton instance
_scraper_instance: Optional[TokenScraper] = None

def get_token_scraper() -> TokenScraper:
    """Get or create the singleton TokenScraper."""
    global _scraper_instance
    if _scraper_instance is None:
        _scraper_instance = TokenScraper()
    return _scraper_instance

