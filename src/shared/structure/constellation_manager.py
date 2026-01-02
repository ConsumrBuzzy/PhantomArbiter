"""
Constellation Manager - Category Island Positioning
===================================================
Maps tokens to X,Z coordinates based on category clusters.
Creates distinct "islands" for Memes, AI, DeFi, Infrastructure.

V2: Moved to Shared Structure to support Core & Galaxy.
    Depends on TaxonomyService for category detection.
"""

from __future__ import annotations

import math
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Import Enum from Taxonomy
from src.shared.structure.taxonomy import TokenCategory, taxonomy

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


class ConstellationManager:
    """
    Manages token positioning within category constellations.
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
        """
        # Detect category using provided string OR TaxonomyService
        if category:
            try:
                token_category = TokenCategory(category.upper())
            except ValueError:
                token_category = TokenCategory.UNKNOWN
        else:
            # Fallback to Taxonomy Service if no category provided
            token_category = taxonomy.classify(symbol, mint, tags)
        
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
