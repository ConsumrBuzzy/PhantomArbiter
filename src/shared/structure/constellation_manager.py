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

# Import Enum from Intelligence Layer
from src.shared.intelligence.taxonomy import TokenSector, taxonomy

@dataclass
class IslandCentroid:
    """Central position for a category island."""
    x: float
    z: float
    y: float = 0.0         # 3D Elevation
    radius: float = 25.0  # Island spread radius
    color: str = "#ffffff"


# Island positions on X,Z plane (arranged as archipelago)
# V35: Expanded Scale (x4) to reduce label overlap
ISLAND_CENTROIDS: Dict[TokenSector, IslandCentroid] = {
    # Center-ish region
    TokenSector.DEFI: IslandCentroid(x=0, z=0, radius=200, color="#00ff88"),
    TokenSector.INFRA: IslandCentroid(x=-400, z=-400, radius=180, color="#4169e1"),
    
    # Upper region (momentum plays)
    TokenSector.MEME: IslandCentroid(x=600, z=360, radius=300, color="#ff6b35"),
    TokenSector.AI: IslandCentroid(x=-600, z=480, radius=250, color="#9945ff"),
    
    # Side regions
    TokenSector.GAMING: IslandCentroid(x=720, z=-480, radius=180, color="#00ced1"),
    TokenSector.RWA: IslandCentroid(x=-720, z=-600, radius=150, color="#ffd700"),
    
    # Outer rim
    TokenSector.STABLE: IslandCentroid(x=-840, z=0, radius=100, color="#888888"),
    TokenSector.UNKNOWN: IslandCentroid(x=480, z=-720, radius=300, color="#666666"),
}


class ConstellationManager:
    """
    Manages token positioning within category constellations.
    """
    
    @classmethod
    def get_island_position_3d(
        cls,
        mint: str,
        symbol: str,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        volume: float = 0
    ) -> Tuple[float, float, float]:
        """
        V38: Get X,Y,Z position for a token using Spherical Fibonacci Lattice.
        Guarantees even distribution in 3D space, preventing clumping.
        """
        # 1. Determine Sector
        if category:
            try:
                token_sector = TokenSector(category.upper())
            except ValueError:
                token_sector = TokenSector.UNKNOWN
        else:
            classification = taxonomy.classify(symbol, mint, tags)
            token_sector = classification.sector
        
        # 2. Get island centroid
        island = ISLAND_CENTROIDS.get(token_sector, ISLAND_CENTROIDS[TokenSector.UNKNOWN])
        
        # 3. Calculate Deterministic 3D Position
        # We use the mint hash to assign a "slot" on the sphere (0 to 1000)
        # This simulates the perfect spacing of a Fibonacci lattice without needing to know total global count
        MAX_SLOTS = 1000
        slot_index = cls._mint_to_slot(mint, MAX_SLOTS)
        
        # Volume affects radium placement layer? 
        # Actually, for 3D clusters, let's keep them on the shell or fill the volume.
        # Let's use concentric shells based on volume.
        # High volume = Inner shell (Core). Low volume = Outer shell (Crust).
        
        # Invert volume logic: High volume -> Small radius multiplier
        # vol_factor 0.0 (high vol) to 1.0 (low vol)
        vol_factor = cls._volume_to_distance(volume, 1.0) 
        
        # Shell radius: Min 20% of island radius, Max 100%
        # Core tokens (high vol) are deep inside (0.2), Shitcoins are on surface (1.0)
        # Actually, let's flip it? Planets usually: High mass in center.
        # Let's put Blue Chips in the center (protected), Degen stuff on the crust.
        shell_radius = island.radius * (0.2 + (0.8 * vol_factor))
        
        # Fibonacci Sphere calculation
        dx, dy, dz = cls._fibonacci_sphere(slot_index, MAX_SLOTS, shell_radius)
        
        # Apply Island Offset
        return (
            round(island.x + dx, 2),
            round(island.y + dy + 150*0.0, 2), # Centered on island Y (0 usually)
            round(island.z + dz, 2)
        )

    @classmethod
    def get_island_position(cls, *args, **kwargs) -> Tuple[float, float]:
        """Legacy 2D support wrapper."""
        x, y, z = cls.get_island_position_3d(*args, **kwargs)
        return (x, z)


    @staticmethod
    def _fibonacci_sphere(i: int, n: int, radius: float) -> Tuple[float, float, float]:
        """
        Calculate point i on a Fibonacci sphere of n points.
        Returns (x, y, z) centered at 0,0,0.
        """
        phi = math.acos(1 - 2 * (i + 0.5) / n)
        theta = math.pi * (1 + 5**0.5) * i
        
        x = radius * math.cos(theta) * math.sin(phi)
        y = radius * math.cos(phi)
        z = radius * math.sin(theta) * math.sin(phi)
        
        return x, y, z

    @staticmethod
    def _mint_to_slot(mint: str, max_slots: int) -> int:
        """Deterministic slot assignment from mint hash."""
        if not mint: return 0
        hash_bytes = hashlib.md5(mint.encode()).digest()
        hash_int = int.from_bytes(hash_bytes[:4], 'big')
        return hash_int % max_slots
    
    @classmethod
    def _volume_to_distance(cls, volume: float, max_val: float) -> float:
        """
        Convert volume to normalized factor (0.0 to 1.0).
        High Volume ($100M) -> 0.0 (Center)
        Low Volume ($1k)    -> 1.0 (Edge)
        """
        if volume <= 0: return max_val
        
        # Log scale: 3 ($1k) to 9 ($1B)
        vol_log = math.log10(max(volume, 1))
        
        # Normalize between 3 and 9
        # val 3 -> (3-3)/6 = 0
        # val 9 -> (9-3)/6 = 1
        normalized = max(0.0, min(1.0, (vol_log - 3) / 6.0))
        
        # Invert: We want High Vol = 0 (Internal), Low Vol = 1 (External)
        return max_val * (1.0 - normalized)
    
    @classmethod
    def get_island_color(cls, category: TokenSector) -> str:
        """Get color for category island."""
        island = ISLAND_CENTROIDS.get(category, ISLAND_CENTROIDS[TokenSector.UNKNOWN])
        return island.color
    
    @classmethod
    def get_all_centroids(cls) -> Dict[str, Tuple[float, float]]:
        """Get all island centroids for visualization."""
        return {
            cat.value: (island.x, island.z)
            for cat, island in ISLAND_CENTROIDS.items()
        }

    @classmethod
    def get_sector_billboards(cls) -> List[Dict]:
        """
        V37: Get data for Sector Billboards (Visual Anchors).
        Returns a list of dicts suitable for VisualObject transformation.
        """
        billboards = []
        for sector, island in ISLAND_CENTROIDS.items():
            if sector == TokenSector.UNKNOWN:
                continue # No billboard for the unknown wastelands
            
            billboards.append({
                "id": f"BILLBOARD_{sector.value}",
                "label": sector.value,
                "x": island.x,
                "z": island.z,
                "y": 150, # Float above the island
                "hex_color": island.color,
                "type": "BILLBOARD"
            })
        return billboards
