"""
V89.10: Token Registry
======================
Centralized token identification and metadata management.

Provides:
- Mint -> Symbol mapping (static + dynamic)
- DexScreener lookup for unknown tokens
- Memory + file cache for discovered tokens
"""

import time
import requests
from typing import Dict, Optional, Tuple, Any
from config.settings import Settings
from src.shared.system.logging import Logger
from src.shared.state.app_state import TokenIdentity, TokenRisk, TokenMarket

try:
    import httpx
    from bs4 import BeautifulSoup
    HAS_SCRAPING = True
except ImportError:
    HAS_SCRAPING = False
    Logger.warning("📚 [REGISTRY] httpx/bs4 not installed - web scraping disabled")

# V89.11: Confidence levels
CONFIDENCE_VERIFIED = 1.0  # Settings.ASSETS or Jupiter
CONFIDENCE_API = 0.8       # DexScreener
CONFIDENCE_SCRAPED = 0.5   # Web scraping
CONFIDENCE_UNKNOWN = 0.0   # Fallback to truncated mint


class TokenRegistry:
    """
    Centralized token identification singleton.
    
    Usage:
        from src.shared.infrastructure.token_registry import get_registry
        symbol = get_registry().get_symbol(mint)
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        
        # Static registry from Settings.ASSETS
        self._static: Dict[str, str] = {}  # mint -> symbol
        
        # Dynamic cache for discovered tokens
        self._dynamic: Dict[str, str] = {}  # mint -> symbol
        self._confidence: Dict[str, Tuple[float, str]] = {}  # mint -> (confidence, source)
        
        # V134: Full Metadata Cache (3-Tier)
        self._identity_cache: Dict[str, TokenIdentity] = {}
        self._risk_cache: Dict[str, TokenRisk] = {}
        self._market_cache: Dict[str, TokenMarket] = {}
        
        # Throttle DexScreener lookups
        self._last_lookup: float = 0
        self._lookup_interval: float = 0.5  # 500ms between lookups
        
        self._load_static()
        self._prefetch_from_cache()
        Logger.info("📚 [REGISTRY] TokenRegistry initialized")
    
    def _load_static(self):
        """Load static tokens from Settings.ASSETS."""
        if hasattr(Settings, 'ASSETS'):
            for symbol, mint in Settings.ASSETS.items():
                self._static[mint] = symbol
            Logger.info(f"📚 [REGISTRY] Loaded {len(self._static)} tokens from config")
    
    def _prefetch_from_cache(self):
        """Pre-fetch symbols for tokens in cache that we don't know."""
        try:
            from src.core.shared_cache import SharedPriceCache
            raw = SharedPriceCache._read_raw()
            market_data = raw.get("market_data", {})
            
            # Find unknown mints
            unknown = [mint for mint in market_data.keys() 
                       if mint not in self._static and mint not in self._dynamic]
            
            if unknown:
                Logger.info(f"📚 [REGISTRY] Pre-fetching {len(unknown)} unknown tokens...")
                # Try Jupiter list first (fast, no rate limit)
                self._load_jupiter_list(unknown)
                # Then DexScreener for any remaining
                still_unknown = [m for m in unknown if m not in self._dynamic]
                if still_unknown:
                    self.refresh_batch(still_unknown)
        except Exception as e:
            Logger.debug(f"📚 [REGISTRY] Prefetch failed: {e}")
    
    def _load_jupiter_list(self, mints_to_find: list = None):
        """
        V89.11: Load token symbols from Jupiter's verified token list.
        Uses file cache with 24h TTL to avoid repeated fetches.
        """
        import json
        import os
        
        cache_file = "data/jupiter_tokens.json"
        cache_ttl = 24 * 3600  # 24 hours
        
        # Check cache freshness
        use_cache = False
        if os.path.exists(cache_file):
            try:
                cache_age = time.time() - os.path.getmtime(cache_file)
                if cache_age < cache_ttl:
                    use_cache = True
                    Logger.debug(f"📚 [REGISTRY] Using cached Jupiter list ({cache_age/3600:.1f}h old)")
            except Exception:
                pass
        
        # Load from cache or fetch
        tokens = []
        if use_cache:
            try:
                with open(cache_file, 'r') as f:
                    tokens = json.load(f)
            except Exception as e:
                Logger.debug(f"📚 [REGISTRY] Cache read failed: {e}")
                use_cache = False
        
        if not use_cache:
            # Fetch fresh list
            try:
                url = "https://token.jup.ag/strict"
                resp = requests.get(url, timeout=10)
                
                if resp.status_code == 200:
                    tokens = resp.json()
                    # Save to cache
                    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
                    with open(cache_file, 'w') as f:
                        json.dump(tokens, f)
                    Logger.info(f"📚 [REGISTRY] Fetched & cached {len(tokens)} Jupiter tokens")
            except Exception as e:
                Logger.debug(f"📚 [REGISTRY] Jupiter fetch failed: {e}")
                return
        
        # Process tokens
        found = 0
        if mints_to_find:
            mints_set = set(mints_to_find)
            for token in tokens:
                addr = token.get("address", "")
                if addr in mints_set and addr not in self._dynamic:
                    self._dynamic[addr] = token.get("symbol", addr[:6])
                    self._confidence[addr] = (CONFIDENCE_VERIFIED, "jupiter")
                    found += 1
        else:
            # Load all tokens
            for token in tokens:
                addr = token.get("address", "")
                symbol = token.get("symbol", "")
                if addr and symbol and addr not in self._static:
                    self._dynamic[addr] = symbol
                    self._confidence[addr] = (CONFIDENCE_VERIFIED, "jupiter")
                    found += 1
        
        if found > 0:
            Logger.info(f"📚 [REGISTRY] Jupiter list: found {found} tokens")
    
    def get_symbol(self, mint: str) -> str:
        """
        Get symbol for a mint address (basic method - no confidence).
        See get_symbol_with_confidence for detailed info.
        """
        symbol, _, _ = self.get_symbol_with_confidence(mint)
        return symbol
    
    def get_symbol_with_confidence(self, mint: str) -> Tuple[str, float, str]:
        """
        V89.11: Get symbol with confidence score and source.
        
        Waterfall priority:
        1. Static registry (Settings.ASSETS) - Verified
        2. Dynamic cache (previous lookups)
        3. Jupiter List - Verified
        4. DexScreener API - Medium confidence
        5. Web Scraping (Solscan/Birdeye) - Low confidence
        6. Fallback: truncated mint - No confidence
        
        Returns:
            (symbol, confidence, source) tuple
        """
        # 1. Check static registry
        if mint in self._static:
            return (self._static[mint], CONFIDENCE_VERIFIED, "config")
        
        # 2. Check dynamic cache (with confidence)
        if mint in self._dynamic:
            symbol = self._dynamic[mint]
            confidence, source = self._confidence.get(mint, (CONFIDENCE_API, "cache"))
            return (symbol, confidence, source)
        
        # 3. Fetch from DexScreener (rate-limited)
        symbol = self._fetch_from_dexscreener(mint)
        if symbol:
            self._dynamic[mint] = symbol
            self._confidence[mint] = (CONFIDENCE_API, "dexscreener")
            return (symbol, CONFIDENCE_API, "dexscreener")
        
        # 4. Try web scraping (if enabled)
        if HAS_SCRAPING:
            symbol = self._scrape_solscan(mint)
            if symbol:
                self._dynamic[mint] = symbol
                self._confidence[mint] = (CONFIDENCE_SCRAPED, "solscan")
                return (symbol, CONFIDENCE_SCRAPED, "solscan")
            
            symbol = self._scrape_birdeye(mint)
            if symbol:
                self._dynamic[mint] = symbol
                self._confidence[mint] = (CONFIDENCE_SCRAPED, "birdeye")
                return (symbol, CONFIDENCE_SCRAPED, "birdeye")
        
        # 5. Fallback: truncated mint
        fallback = mint[:6] if len(mint) > 6 else mint
        self._dynamic[mint] = fallback
        self._confidence[mint] = (CONFIDENCE_UNKNOWN, "fallback")
        return (fallback, CONFIDENCE_UNKNOWN, "fallback")
    
    def get_full_metadata(self, mint: str) -> Dict[str, Any]:
        """
        V134: Get comprehensive 3-tier metadata.
        Returns a dict containing identity, risk, and market data.
        """
        # 1. Identity (Static)
        identity = self._identity_cache.get(mint)
        if not identity:
            symbol, _, _ = self.get_symbol_with_confidence(mint)
            identity = TokenIdentity(
                mint=mint,
                symbol=symbol,
                decimals=6, # Default, should fetch for accuracy
                name=symbol
            )
            self._identity_cache[mint] = identity
            
        # 2. Risk (Slow-Changing)
        risk = self._risk_cache.get(mint)
        if not risk:
            # Default low-risk assumption until vetted
            risk = TokenRisk()
            self._risk_cache[mint] = risk
            
        # 3. Market (Fast-Changing)
        market = self._market_cache.get(mint)
        if not market:
            market = TokenMarket()
            self._market_cache[mint] = market
            
        return {
            "identity": identity,
            "risk": risk,
            "market": market
        }
    
    def update_risk_data(self, mint: str, data: Dict):
        """Update risk tier for a token."""
        if mint not in self._risk_cache:
            self._risk_cache[mint] = TokenRisk()
            
        risk = self._risk_cache[mint]
        if 'mint_authority' in data: risk.mint_authority = data['mint_authority']
        if 'freeze_authority' in data: risk.freeze_authority = data['freeze_authority']
        if 'safety_score' in data: risk.safety_score = float(data['safety_score'])
        
    def update_market_data(self, mint: str, data: Dict):
        """Update market tier for a token."""
        if mint not in self._market_cache:
            self._market_cache[mint] = TokenMarket()
            
        mk = self._market_cache[mint]
        if 'price_usd' in data: mk.price_usd = float(data['price_usd'])
        if 'volume_1h' in data: mk.volume_1h = float(data['volume_1h'])
        mk.last_updated = time.time()
    
    def _fetch_from_dexscreener(self, mint: str) -> Optional[str]:
        """
        Fetch token symbol from DexScreener API.
        
        Rate-limited to prevent API abuse.
        """
        # Rate limit check
        now = time.time()
        if now - self._last_lookup < self._lookup_interval:
            return None
        
        self._last_lookup = now
        
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
            resp = requests.get(url, timeout=3)
            
            if resp.status_code == 200:
                data = resp.json()
                pairs = data.get('pairs', [])
                
                if pairs:
                    # Get symbol from first pair's baseToken
                    base_token = pairs[0].get('baseToken', {})
                    symbol = base_token.get('symbol', '')
                    
                    if symbol:
                        Logger.debug(f"📚 [REGISTRY] Discovered: {mint[:8]}... = {symbol}")
                        return symbol
                        
        except Exception as e:
            Logger.debug(f"📚 [REGISTRY] DexScreener lookup failed for {mint[:8]}: {e}")
        
        return None
    
    def _scrape_solscan(self, mint: str) -> Optional[str]:
        """
        V89.13: Scrape Solscan for token symbol using CSS selectors.
        HTML structure: <h4><span class="text-neutral6">TOKEN_NAME</span></h4>
        """
        if not HAS_SCRAPING:
            return None
            
        # Generic words to filter out
        GENERIC_WORDS = {'token', 'coin', 'solscan', 'solana', 'address', 'contract', 
                         'not', 'dot', 'and', 'or', 'the', 'a', 'an', 'of', 'in', 'on', 'at'}
        
        try:
            url = f"https://solscan.io/token/{mint}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'lxml')
                
                # V89.13: Target specific span with token name
                token_span = soup.find('span', {'class': 'text-neutral6'})
                if token_span:
                    symbol = token_span.text.strip().upper()
                    if symbol and symbol.lower() not in GENERIC_WORDS and symbol != mint[:6]:
                        Logger.debug(f"📚 [REGISTRY] Scraped from Solscan: {mint[:8]}... = {symbol}")
                        return symbol
                
                # Fallback: Try meta tag
                meta_title = soup.find('meta', {'property': 'og:title'})
                if meta_title:
                    content = meta_title.get('content', '')
                    parts = content.split()
                    for part in parts:
                        cleaned = part.strip('|()[]').upper()
                        if cleaned and cleaned.lower() not in GENERIC_WORDS and cleaned != mint[:6]:
                            Logger.debug(f"📚 [REGISTRY] Scraped from Solscan (meta): {mint[:8]}... = {cleaned}")
                            return cleaned
                        
        except Exception as e:
            Logger.debug(f"📚 [REGISTRY] Solscan scrape failed for {mint[:8]}: {e}")
        
        return None
    
    def _scrape_birdeye(self, mint: str) -> Optional[str]:
        """
        V89.13: Scrape Birdeye for token symbol using CSS selectors.
        HTML structure: <h1><span class="text-subtitle-medium-16">TOKEN_NAME</span></h1>
        """
        if not HAS_SCRAPING:
            return None
        
        # Generic words to filter out
        GENERIC_WORDS = {'token', 'coin', 'birdeye', 'solana', 'address', 'contract',
                         'not', 'dot', 'and', 'or', 'the', 'a', 'an', 'of', 'in', 'on', 'at'}
            
        try:
            url = f"https://birdeye.so/token/{mint}?chain=solana"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'lxml')
                
                # V89.13: Target specific span with token name
                token_span = soup.find('span', {'class': 'text-subtitle-medium-16'})
                if token_span:
                    symbol = token_span.text.strip().upper()
                    if symbol and symbol.lower() not in GENERIC_WORDS and symbol != mint[:6]:
                        Logger.debug(f"📚 [REGISTRY] Scraped from Birdeye: {mint[:8]}... = {symbol}")
                        return symbol
                
                # Fallback: Try meta tag or title
                meta_title = soup.find('meta', {'property': 'og:title'})
                if meta_title:
                    content = meta_title.get('content', '')
                    parts = content.split()
                    for part in parts:
                        cleaned = part.strip('|()[]').upper()
                        if cleaned and cleaned.lower() not in GENERIC_WORDS and cleaned != mint[:6]:
                            Logger.debug(f"📚 [REGISTRY] Scraped from Birdeye (meta): {mint[:8]}... = {cleaned}")
                            return cleaned
                        
        except Exception as e:
            Logger.debug(f"📚 [REGISTRY] Birdeye scrape failed for {mint[:8]}: {e}")
        
        return None
    
    def register_token(self, mint: str, symbol: str):
        """Manually register a token (adds to dynamic cache)."""
        self._dynamic[mint] = symbol
    
    def is_known(self, mint: str) -> bool:
        """Check if token is known (static or dynamic)."""
        return mint in self._static or mint in self._dynamic
    
    def get_all_known(self) -> Dict[str, str]:
        """Get all known tokens (static + dynamic)."""
        return {**self._static, **self._dynamic}
    
    def refresh_batch(self, mints: list) -> None:
        """
        Refresh market data for a batch of mints.
        Uses DexScreener batch endpoint for efficiency.
        """
        if not mints:
            return
            
        try:
            # Only fetch unknown mints
            unknown = [m for m in mints if m not in self._static and m not in self._dynamic]
            
            if not unknown:
                return
            
            # Chunk to 30 (DexScreener limit)
            for i in range(0, len(unknown), 30):
                chunk = unknown[i:i+30]
                ids = ",".join(chunk)
                
                url = f"https://api.dexscreener.com/latest/dex/tokens/{ids}"
                resp = requests.get(url, timeout=5)
                
                if resp.status_code == 200:
                    data = resp.json()
                    pairs = data.get('pairs', [])
                    
                    # Group by mint
                    mint_symbols = {}
                    for pair in pairs:
                        base = pair.get('baseToken', {})
                        addr = base.get('address', '').lower()
                        symbol = base.get('symbol', '')
                        
                        if addr and symbol:
                            # Find original case mint
                            for m in chunk:
                                if m.lower() == addr:
                                    mint_symbols[m] = symbol
                                    break
                    
                    # Update cache
                    for mint, symbol in mint_symbols.items():
                        self._dynamic[mint] = symbol
                    
                    Logger.debug(f"📚 [REGISTRY] Batch discovered {len(mint_symbols)} tokens")
                    
                time.sleep(0.3)  # Rate limit between chunks
                
        except Exception as e:
            Logger.debug(f"📚 [REGISTRY] Batch refresh failed: {e}")


# Singleton accessor
_registry: Optional[TokenRegistry] = None

def get_registry() -> TokenRegistry:
    """Get the TokenRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = TokenRegistry()
    return _registry
