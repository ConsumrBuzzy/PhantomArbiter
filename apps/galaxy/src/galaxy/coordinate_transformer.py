"""
Coordinate Transformer - Galactic XYZ Mapping.

Maps market data to 3D spatial coordinates for Galaxy visualization.
Fully decoupled from Core - works with raw dicts.
"""

from __future__ import annotations

import math
import hashlib
from typing import Dict, Any, Tuple


class CoordinateTransformer:
    """
    Maps market data to 3D galactic coordinates.
    
    Coordinate System:
    - X: Liquidity axis (high liquidity = center, low = periphery)
    - Y: Volume axis (high volume = top, low = bottom)
    - Z: Volatility axis (high volatility = front, stable = back)
    """
    
    # Galaxy bounds
    GALAXY_RADIUS = 100.0
    CENTER_ZONE = 20.0  # High liquidity tokens near center
    
    @classmethod
    def get_xyz(cls, data: Dict[str, Any]) -> Tuple[float, float, float]:
        """
        Convert market data to XYZ coordinates.
        
        Args:
            data: Dict containing market metrics (liquidity, volume, etc.)
            
        Returns:
            Tuple of (x, y, z) coordinates
        """
        mint = data.get("mint") or data.get("token") or ""
        
        # Extract metrics with safe defaults
        try:
            liquidity = float(data.get("liquidity") or data.get("liquidity_usd") or 1000)
        except (ValueError, TypeError):
            liquidity = 1000.0
            
        try:
            volume = float(data.get("volume_24h") or data.get("volume") or 0)
        except (ValueError, TypeError):
            volume = 0.0
            
        try:
            change_24h = float(data.get("price_change_24h") or data.get("change_24h") or 0)
        except (ValueError, TypeError):
            change_24h = 0.0
        
        # Sanitize NaN/Inf
        if math.isnan(liquidity) or math.isinf(liquidity):
            liquidity = 1000.0
        if math.isnan(volume) or math.isinf(volume):
            volume = 0.0
        if math.isnan(change_24h) or math.isinf(change_24h):
            change_24h = 0.0
        
        # --- X: Liquidity-based radial distance ---
        # High liquidity = near center, low = far
        # Log scale to handle wide range ($1k to $100M)
        liq_log = math.log10(max(liquidity, 100))
        # liq_log ranges from 2 ($100) to 8 ($100M)
        # Map to distance: high liq (8) -> 10, low liq (2) -> 80
        distance = max(cls.CENTER_ZONE, cls.GALAXY_RADIUS - liq_log * 10)
        
        # Deterministic angle based on mint hash (consistent position)
        angle = cls._mint_to_angle(mint)
        
        x = distance * math.cos(angle)
        z_base = distance * math.sin(angle)
        
        # --- Y: Volume-based vertical position ---
        # High volume = top, low volume = bottom
        vol_log = math.log10(max(volume, 1))
        # vol_log ranges from 0 to 8
        y = (vol_log - 4) * 10  # Center around 0, scale by 10
        
        # --- Z: Volatility-based depth ---
        # High volatility = front (positive Z), stable = back (negative Z)
        volatility_factor = min(abs(change_24h), 50) / 50  # Normalize to 0-1
        z = z_base + (volatility_factor * 20 - 10)  # -10 to +10 offset
        
        return (
            round(x, 2),
            round(y, 2),
            round(z, 2)
        )
    
    @classmethod
    def get_pool_offset(
        cls, 
        parent_xyz: Tuple[float, float, float], 
        pool_index: int,
        total_pools: int = 4
    ) -> Tuple[float, float, float]:
        """
        Calculate orbital position for a pool around its parent token.
        
        Args:
            parent_xyz: Parent token's coordinates
            pool_index: Index of this pool (0, 1, 2...)
            total_pools: Total pools for this token
            
        Returns:
            Tuple of (x, y, z) for pool orbit position
        """
        px, py, pz = parent_xyz
        
        # Orbital parameters
        orbit_radius = 5.0
        angle = (2 * math.pi * pool_index) / max(total_pools, 1)
        
        # Orbit in XZ plane around parent
        ox = px + orbit_radius * math.cos(angle)
        oy = py + 1.0  # Slight vertical offset
        oz = pz + orbit_radius * math.sin(angle)
        
        return (round(ox, 2), round(oy, 2), round(oz, 2))
    
    @staticmethod
    def _mint_to_angle(mint: str) -> float:
        """
        Generate deterministic angle from mint address.
        Same mint always gets same angle for consistent positioning.
        """
        if not mint:
            return 0.0
        
        # Hash the mint to get consistent pseudo-random value
        hash_bytes = hashlib.md5(mint.encode()).digest()
        hash_int = int.from_bytes(hash_bytes[:4], 'big')
        
        # Map to 0-2π
        return (hash_int / (2**32)) * 2 * math.pi
