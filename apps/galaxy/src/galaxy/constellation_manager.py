"""
Constellation Manager - Category Island Positioning

Maps tokens to X,Z coordinates based on category clusters.
Creates distinct "islands" for Memes, AI, DeFi, Infrastructure.
"""

from __future__ import annotations

import math
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum


class TokenCategory(str, Enum):
    """Token category classifications for island placement."""
    MEME = "MEME"               # WIF, BONK, POPCAT, DOGE clones
    AI = "AI"                   # pippin, virtual, ai16z
    DEFI = "DEFI"               # JUP, RAY, ORCA protocol tokens
    INFRASTRUCTURE = "INFRA"    # SOL, PYTH, JTO, core infrastructure
    GAMING = "GAMING"           # Gaming/NFT tokens
    STABLECOIN = "STABLE"       # USDC, USDT adjacent
    LST = "LST"                 # Liquid staking tokens
    NEW = "NEW"                 # Recently discovered, uncategorized
    UNKNOWN = "UNKNOWN"


@dataclass
class IslandCentroid:
    """Central position for a category island."""
    x: float
    z: float
    radius: float = 25.0  # Island spread radius
    color: str = "#ffffff"


# Island positions on X,Z plane (arranged as archipelago)
ISLAND_CENTROIDS: Dict[TokenCategory, IslandCentroid] = {
    # Center-ish region
    TokenCategory.DEFI: IslandCentroid(x=0, z=0, radius=20, color="#00ff88"),
    TokenCategory.INFRASTRUCTURE: IslandCentroid(x=-30, z=-30, radius=20, color="#4169e1"),
    
    # Upper region (momentum plays)
    TokenCategory.MEME: IslandCentroid(x=50, z=30, radius=30, color="#ff6b35"),
    TokenCategory.AI: IslandCentroid(x=-50, z=40, radius=25, color="#9945ff"),
    
    # Side regions
    TokenCategory.GAMING: IslandCentroid(x=60, z=-40, radius=20, color="#00ced1"),
    TokenCategory.LST: IslandCentroid(x=-60, z=-50, radius=15, color="#ffd700"),
    
    # Outer rim
    TokenCategory.NEW: IslandCentroid(x=0, z=70, radius=35, color="#ff00ff"),
    TokenCategory.STABLECOIN: IslandCentroid(x=-70, z=0, radius=10, color="#888888"),
    TokenCategory.UNKNOWN: IslandCentroid(x=40, z=-60, radius=30, color="#666666"),
}


# Keyword mapping for category detection (substring matching)
CATEGORY_KEYWORDS: Dict[TokenCategory, List[str]] = {
    TokenCategory.MEME: [
        "meme", "dog", "cat", "pepe", "wojak", "doge", "shib", "bonk", "wif", 
        "popcat", "fart", "frog", "ape", "moon", "elon", "trump", "biden", "jelly",
        "nub", "mini", "capy", "neiro", "pengu", "griffain", "ploi", "dupe",
        "uranus", "buzz", "freya", "kled", "grass", "io", "oil", "spsc",
    ],
    TokenCategory.AI: [
        "ai", "gpt", "agent", "virtual", "pippin", "sentient", "neural", "bot",
        "intelligence", "machine", "llm", "openai", "giga", "67_9avy",
    ],
    TokenCategory.DEFI: [
        "swap", "amm", "dex", "protocol", "yield", "stake", "lend", "borrow",
        "jup", "jupiter", "ray", "raydium", "orca", "marinade", "drift", "met",
        "ondo", "zeus", "core",
    ],
    TokenCategory.INFRASTRUCTURE: [
        "sol", "pyth", "jto", "jito", "wormhole", "bridge", "oracle", "infra",
        "render", "helium", "hnt", "mobile", "oi1",
    ],
    TokenCategory.GAMING: [
        "game", "nft", "play", "metaverse", "arcade", "star", "atlas", "genopets"
    ],
    TokenCategory.LST: [
        "msol", "bsol", "jitosol", "lst", "liquid", "staking"
    ],
    TokenCategory.STABLECOIN: [
        "usd", "usdc", "usdt", "dai", "stable", "peg"
    ],
}

# Direct symbol → category mapping for known tokens
SYMBOL_CATEGORY_MAP: Dict[str, TokenCategory] = {
    # Memes
    "WIF": TokenCategory.MEME,
    "BONK": TokenCategory.MEME,
    "POPCAT": TokenCategory.MEME,
    "PENGU": TokenCategory.MEME,
    "NEIRO": TokenCategory.MEME,
    "CAPY": TokenCategory.MEME,
    "TRUMP": TokenCategory.MEME,
    "BUZZ": TokenCategory.MEME,
    "FREYA": TokenCategory.MEME,
    "GRASS": TokenCategory.MEME,
    "NUB": TokenCategory.MEME,
    "MINI": TokenCategory.MEME,
    "URANUS": TokenCategory.MEME,
    "GRIFFAIN": TokenCategory.MEME,
    "PLOI": TokenCategory.MEME,
    "DUPE": TokenCategory.MEME,
    "SPSC": TokenCategory.MEME,
    "OIL": TokenCategory.MEME,
    "KLED": TokenCategory.MEME,
    
    # AI
    "PIPPIN": TokenCategory.AI,
    "VIRTUAL": TokenCategory.AI,
    "GIGA": TokenCategory.AI,
    "67_9AVY": TokenCategory.AI,
    
    # DeFi
    "JUP": TokenCategory.DEFI,
    "RAY": TokenCategory.DEFI,
    "ORCA": TokenCategory.DEFI,
    "MET": TokenCategory.DEFI,
    "ONDO": TokenCategory.DEFI,
    "ZEUS": TokenCategory.DEFI,
    "CORE": TokenCategory.DEFI,
    "DRIFT": TokenCategory.DEFI,
    
    # Infrastructure
    "SOL": TokenCategory.INFRASTRUCTURE,
    "PYTH": TokenCategory.INFRASTRUCTURE,
    "JTO": TokenCategory.INFRASTRUCTURE,
    "IO": TokenCategory.INFRASTRUCTURE,
    "OI1": TokenCategory.INFRASTRUCTURE,
    "MOBILE": TokenCategory.INFRASTRUCTURE,
    "HNT": TokenCategory.INFRASTRUCTURE,
    
    # LST
    "MSOL": TokenCategory.LST,
    "BSOL": TokenCategory.LST,
    "JITOSOL": TokenCategory.LST,
}


class ConstellationManager:
    """
    Manages token positioning within category constellations.
    
    Creates distinct "islands" on the X,Z plane:
    - Each category has a centroid
    - Tokens within category spread around centroid
    - High-volume tokens closer to center of island
    """
    
    @classmethod
    def get_island_position(
        cls,
        mint: str,
        symbol: str,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        volume: float = 0,
        liquidity: float = 1000,
    ) -> Tuple[float, float]:
        """
        Get X,Z position for a token based on its category island.
        
        Returns:
            Tuple of (x, z) coordinates on horizontal plane
        """
        # Detect category
        token_category = cls._detect_category(symbol, category, tags)
        
        # Get island centroid
        island = ISLAND_CENTROIDS.get(token_category, ISLAND_CENTROIDS[TokenCategory.UNKNOWN])
        
        # Calculate position within island
        # Higher volume = closer to center
        vol_factor = cls._volume_to_distance(volume, island.radius)
        
        # Use mint hash for consistent angle within island
        angle = cls._mint_to_angle(mint)
        
        # Position within island radius
        x = island.x + vol_factor * math.cos(angle)
        z = island.z + vol_factor * math.sin(angle)
        
        return (round(x, 2), round(z, 2))
    
    @classmethod
    def _detect_category(
        cls,
        symbol: str,
        category: Optional[str],
        tags: Optional[List[str]],
    ) -> TokenCategory:
        """Detect token category from symbol and tags."""
        # 1. Check direct symbol mapping
        if symbol:
            symbol_upper = symbol.upper()
            if symbol_upper in SYMBOL_CATEGORY_MAP:
                return SYMBOL_CATEGORY_MAP[symbol_upper]

        # 2. Check explicit category provided
        if category:
            try:
                return TokenCategory(category.upper())
            except ValueError:
                pass
        
        # 3. Check symbol and tags against keywords
        search_text = symbol.lower()
        if tags:
            search_text += " " + " ".join(t.lower() for t in tags)
        
        for cat, keywords in CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in search_text:
                    return cat
        
        return TokenCategory.UNKNOWN
    
    @classmethod
    def _volume_to_distance(cls, volume: float, island_radius: float) -> float:
        """
        Convert volume to distance from island center.
        Higher volume = closer to center (more important).
        """
        if volume <= 0:
            return island_radius  # Edge of island
        
        # Log scale
        vol_log = math.log10(max(volume, 1))
        
        # vol_log 3 ($1k) = edge, vol_log 8 ($100M) = center
        normalized = min(1, (vol_log - 3) / 5)
        
        # Invert: higher volume = smaller distance
        return island_radius * (1 - normalized * 0.8)
    
    @staticmethod
    def _mint_to_angle(mint: str) -> float:
        """Generate deterministic angle from mint hash."""
        if not mint:
            return 0.0
        
        hash_bytes = hashlib.md5(mint.encode()).digest()
        hash_int = int.from_bytes(hash_bytes[:4], 'big')
        
        return (hash_int / (2**32)) * 2 * math.pi
    
    @classmethod
    def get_category(cls, symbol: str, tags: Optional[List[str]] = None) -> TokenCategory:
        """Get category for a token."""
        return cls._detect_category(symbol, None, tags)
    
    @classmethod
    def get_island_color(cls, category: TokenCategory) -> str:
        """Get color for category island."""
        island = ISLAND_CENTROIDS.get(category, ISLAND_CENTROIDS[TokenCategory.UNKNOWN])
        return island.color
    
    @classmethod
    def get_all_centroids(cls) -> Dict[str, Tuple[float, float]]:
        """Get all island centroids for visualization."""
        return {
            cat.value: (island.x, island.z)
            for cat, island in ISLAND_CENTROIDS.items()
        }
