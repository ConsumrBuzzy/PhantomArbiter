"""
Galaxy Models - Pydantic schemas for event payloads.

Fully decoupled from Core SignalBus types.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Event types received from Core Engine."""
    MARKET_UPDATE = "MARKET_UPDATE"
    NEW_TOKEN = "NEW_TOKEN"
    WHALE_ACTIVITY = "WHALE_ACTIVITY"
    ARB_OPP = "ARB_OPP"
    MARKET_INTEL = "MARKET_INTEL"
    WHIFF_DETECTED = "WHIFF_DETECTED"
    SYSTEM_STATS = "SYSTEM_STATS"
    LOG_UPDATE = "LOG_UPDATE"
    SCAN_UPDATE = "SCAN_UPDATE"
    HOP_PATH = "HOP_PATH"


class EventPayload(BaseModel):
    """Event received from Core Engine EventBridge."""
    type: EventType
    source: str = "CORE"
    timestamp: float = 0.0
    data: Dict[str, Any] = Field(default_factory=dict)

    # V89.14: TokenRegistry-like methods added to EventPayload for demonstration
    # NOTE: In a real application, these methods and associated state
    # (_static, _dynamic, _confidence, _identity_cache, _last_cg_lookup)
    # would typically reside in a separate TokenRegistry class, not EventPayload.
    # This is a literal interpretation of the user's request to add them *into* EventPayload.

    # Internal state for the registry-like functionality
    _static: Dict[str, str] = Field(default_factory=dict)
    _dynamic: Dict[str, str] = Field(default_factory=dict)
    _confidence: Dict[str, Tuple[float, str]] = Field(default_factory=dict)
    _identity_cache: Dict[str, Any] = Field(default_factory=dict) # Placeholder for identity cache
    _last_cg_lookup: float = 0.0 # Initialize _last_cg_lookup for throttling

    def _fetch_from_coingecko(self, mint: str) -> Optional[Dict[str, Any]]:
        """
        V89.14: Fetch token data (including categories) from CoinGecko.
        Rate-limited to prevent 429s (Demo API: ~30 calls/min).
        """
        # Global throttle for CG (separate from DexScreener)
        now = time.time()
        # The _last_cg_lookup is now an instance attribute, initialized above.
        # if not hasattr(self, "_last_cg_lookup"):
        #     self._last_cg_lookup = 0.0 # This is now handled by the Field default_factory

        if now - self._last_cg_lookup < 2.0:  # 2s throttle ( conservative)
            return None

        self._last_cg_lookup = now

        try:
            url = f"https://api.coingecko.com/api/v3/coins/solana/contract/{mint}"
            resp = requests.get(url, timeout=5)

            if resp.status_code == 200:
                data = resp.json()
                Logger.debug(f"📚 [REGISTRY] CoinGecko Hit: {mint[:8]}...")
                return data
            elif resp.status_code == 429:
                Logger.warning("📚 [REGISTRY] CoinGecko Rate Limit Hit")
                
        except Exception as e:
            Logger.debug(f"📚 [REGISTRY] CoinGecko lookup failed for {mint[:8]}: {e}")

        return None

    def _fetch_from_dexscreener(self, mint: str) -> Optional[str]:
        """Placeholder for DexScreener fetch."""
        return None

    def _scrape_solscan(self, mint: str) -> Optional[str]:
        """Placeholder for Solscan scraping."""
        return None

    def _scrape_birdeye(self, mint: str) -> Optional[str]:
        """Placeholder for Birdeye scraping."""
        return None

    def get_symbol(self, mint: str) -> str:
        """Placeholder for get_symbol, which would call get_symbol_with_confidence."""
        symbol, _, _ = self.get_symbol_with_confidence(mint)
        return symbol

    def get_symbol_with_confidence(self, mint: str) -> Tuple[str, float, str]:
        """
        V89.11: Get symbol with confidence score and source.

        Waterfall priority:
        1. Static registry (Settings.ASSETS) - Verified
        2. Dynamic cache (previous lookups)
        3. Jupiter List - Verified (not implemented here)
        4. DexScreener API - Medium confidence
        5. CoinGecko API - High confidence (Rich Data)
        6. Web Scraping (Solscan/Birdeye) - Low confidence
        7. Fallback: truncated mint - No confidence

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

        # 4. Try CoinGecko (Rich Data)
        cg_data = self._fetch_from_coingecko(mint)
        if cg_data:
            symbol = cg_data.get("symbol", "").upper()
            if symbol:
                self._dynamic[mint] = symbol
                self._confidence[mint] = (CONFIDENCE_API, "coingecko")
                
                # V89.14: Opportunistic Metadata Cache
                if "categories" in cg_data:
                    # Store categories temporarily or persist?
                    # For now we just use the symbol, but typically we want to return more.
                    # We will handle category extraction in get_category_with_fallback
                    pass
                    
                return (symbol, CONFIDENCE_API, "coingecko")

        # 5. Try web scraping (if enabled)
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

        # 6. Fallback: truncated mint
        fallback = mint[:6] if len(mint) > 6 else mint
        self._dynamic[mint] = fallback
        self._confidence[mint] = (CONFIDENCE_UNKNOWN, "fallback")
        return (fallback, CONFIDENCE_UNKNOWN, "fallback")

    def get_category(self, mint: str) -> str:
        """Get the category for a token (uses cached identity, taxonomy, or external APIs)."""
        # Check cache first
        if mint in self._identity_cache:
            # Assuming _identity_cache stores objects with a 'category' attribute
            return self._identity_cache[mint].category
        
        # Determine symbol and potentially fetch rich data
        symbol = self.get_symbol(mint) # Hits cache or standard lookup
        
        # If unknown category in identity, try to enhance
        # Check if we have CoinGecko data available (opportunistic fetch)
        tags = []
        
        # We can try to fetch CG specifically if taxonomy fails or returns UNKNOWN
        classification = taxonomy.classify(symbol, mint)
        
        if classification.sector == TokenSector.UNKNOWN:
             # Try CoinGecko for categorization
             cg_data = self._fetch_from_coingecko(mint)
             if cg_data:
                 tags = cg_data.get("categories", [])
                 # Re-classify with tags
                 classification = taxonomy.classify(symbol, mint, tags)
        
        return classification.sector.value


class VisualParams(BaseModel):
    """Visual parameters for a Galaxy object."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    radius: float = 1.0
    roughness: float = 0.5
    metalness: float = 0.2
    emissive_intensity: float = 2.0
    hex_color: str = "#00ffaa"
    velocity_factor: float = 1.0
    distance_factor: float = 1.0
    
    # Metadata for tooltips
    price: float = 0.0
    change_24h: float = 0.0
    volume: float = 0.0
    liquidity: float = 1000.0
    market_cap: float = 0.0
    rsi: float = 50.0
    
    # Animation hints
    pulse: bool = False
    flash: bool = False
    is_whale: bool = False
    
    # Moon/Pool specific
    parent_mint: Optional[str] = None
    pool_address: Optional[str] = None
    dex: Optional[str] = None
    orbit_speed: float = 0.02
    moon_phase: float = 0.0
    
    # Semantic
    category: str = "UNKNOWN"
    price: float = 0.0


class VisualObject(BaseModel):
    """A visual object to render in the Galaxy."""
    type: str = "ARCHETYPE_UPDATE"
    id: str
    label: str
    event_label: str = ""
    archetype: str = "GLOBE"
    node_type: str = "TOKEN"
    params: VisualParams = Field(default_factory=VisualParams)


class BatchUpdate(BaseModel):
    """Batch of visual updates for broadcast."""
    type: str = "BATCH_UPDATE"
    data: List[VisualObject] = Field(default_factory=list)


class HopPath(BaseModel):
    """Arbitrage hop path visualization."""
    type: str = "HOP_PATH"
    path: List[str] = Field(default_factory=list)
    profit: float = 0.0
    source: str = "ARBITER"


class WhalePulse(BaseModel):
    """Whale activity pulse visualization."""
    type: str = "WHALE_PULSE"
    mint: str = ""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    intensity: float = 5.0
    color: str = "#ffd700"


class SystemStats(BaseModel):
    """System statistics for HUD display."""
    type: str = "SYSTEM_STATS"
    data: Dict[str, Any] = Field(default_factory=dict)


class LogEntry(BaseModel):
    """Log entry for stream display."""
    type: str = "LOG_ENTRY"
    level: str = "INFO"
    message: str = ""
    timestamp: float = 0.0


class ScanUpdate(BaseModel):
    """Arbitrage opportunity scan results."""
    type: str = "SCAN_UPDATE"
    opportunities: List[Dict[str, Any]] = Field(default_factory=list)
