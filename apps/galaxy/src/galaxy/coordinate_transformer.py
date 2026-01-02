"""
Coordinate Transformer - Galactic XYZ Semantic Mapping.

Maps market data to 3D spatial coordinates using Cylindrical Mapping:
- Radius (R): Market cap / volume (blue chips at center)
- Angle (θ): DEX sector (Raydium/Orca/Meteora districts)
- Height (Y): RSI momentum (overbought up, oversold down)
"""

from __future__ import annotations

import math
import hashlib
from typing import Dict, Any, Tuple, Optional
from enum import Enum


class DexSector(str, Enum):
    """DEX district sectors in the galaxy."""
    RAYDIUM = "RAYDIUM"
    ORCA = "ORCA"
    METEORA = "METEORA"
    JUPITER = "JUPITER"
    PUMPFUN = "PUMPFUN"
    UNKNOWN = "UNKNOWN"


# DEX Sector angle ranges (in radians)
DEX_SECTORS = {
    DexSector.RAYDIUM: (0, 2 * math.pi / 3),              # 0° - 120°
    DexSector.ORCA: (2 * math.pi / 3, 4 * math.pi / 3),   # 120° - 240°
    DexSector.METEORA: (4 * math.pi / 3, 5 * math.pi / 3),# 240° - 300°
    DexSector.JUPITER: (5 * math.pi / 3, 11 * math.pi / 6),# 300° - 330°
    DexSector.PUMPFUN: (11 * math.pi / 6, 2 * math.pi),   # 330° - 360°
}


class CoordinateTransformer:
    """
    Maps market data to 3D galactic coordinates using Cylindrical Semantic Mapping.
    
    Coordinate System:
    - R (Radius): Market cap / volume → distance from center
    - θ (Theta): DEX sector → angular position
    - Y (Height): RSI - 50 → vertical position (momentum)
    
    This creates a "War Room" where:
    - Blue chips orbit the center
    - Tokens cluster by DEX
    - Overbought tokens rise, oversold sink
    """
    
    # Galaxy bounds
    GALAXY_RADIUS = 400.0 # Expanded V35
    CORE_RADIUS = 15.0   # Blue chips (high cap) near center
    RIM_RADIUS = 350.0   # New tokens at the edge
    MAX_HEIGHT = 120.0   # Expanded Verticality V35
    
    @classmethod
    def get_xyz(
        cls,
        data: Dict[str, Any],
        indicators: Optional[Dict[str, Any]] = None,
    ) -> Tuple[float, float, float]:
        """
        Convert market data to XYZ coordinates using semantic mapping.
        
        Args:
            data: Dict containing market metrics (liquidity, volume, dex, etc.)
            indicators: Optional dict with RSI, EMA, regime from WarmBuffer
            
        Returns:
            Tuple of (x, y, z) coordinates
        """
        mint = data.get("mint") or data.get("token") or ""
        symbol = data.get("symbol") or data.get("label") or ""
        
        # Extract metrics
        market_cap = cls._safe_float(data.get("market_cap") or data.get("fdv") or 0)
        liquidity = cls._safe_float(data.get("liquidity") or data.get("liquidity_usd") or 1000)
        volume = cls._safe_float(data.get("volume_24h") or data.get("volume") or 0)
        tags = data.get("tags") or data.get("categories") or []
        category = data.get("category")
        
        # Get RSI from indicators or data
        rsi = 50.0  # Neutral default
        if indicators:
            rsi = cls._safe_float(indicators.get("rsi_14") or indicators.get("rsi") or 50)
        elif "rsi" in data:
            rsi = cls._safe_float(data.get("rsi") or 50)
        
        # --- X,Z: Constellation Island Positioning ---
        # --- X,Z: Constellation Island Positioning ---
        # Uses category to cluster tokens into distinct islands
        from src.shared.structure.constellation_manager import ConstellationManager
        x, z = ConstellationManager.get_island_position(
            mint=mint,
            symbol=symbol,
            category=category,
            tags=tags if isinstance(tags, list) else [tags] if tags else None,
            volume=volume,
            liquidity=liquidity,
        )
        
        # --- HEIGHT: RSI momentum ---
        # RSI 50 = neutral (Y=0), RSI 70 = overbought (Y=+max), RSI 30 = oversold (Y=-max)
        y = cls._rsi_to_height(rsi)
        
        return (
            round(x, 2),
            round(y, 2),
            round(z, 2)
        )
    
    @classmethod
    def _cap_to_radius(cls, cap_value: float) -> float:
        """
        Convert market cap to radial distance.
        Higher cap = closer to center.
        """
        if cap_value <= 0:
            return cls.RIM_RADIUS
        
        # Log scale: $1M = 6, $100M = 8, $1B = 9
        log_cap = math.log10(max(cap_value, 1000))
        
        # Map: log 3 ($1k) → rim, log 9 ($1B) → core
        # Invert: higher cap = smaller radius
        normalized = (log_cap - 3) / 6  # 0 to 1
        normalized = max(0, min(1, normalized))
        
        # Core to rim
        radius = cls.RIM_RADIUS - (normalized * (cls.RIM_RADIUS - cls.CORE_RADIUS))
        
        return radius
    
    @classmethod
    def _rsi_to_height(cls, rsi: float) -> float:
        """
        Convert RSI to vertical position.
        RSI 50 = 0, RSI 70+ = positive, RSI 30- = negative
        """
        # Clamp RSI to 0-100
        rsi = max(0, min(100, rsi))
        
        # Center around 50
        offset = rsi - 50
        
        # Scale: 20 RSI points = MAX_HEIGHT
        height = (offset / 20) * cls.MAX_HEIGHT
        
        # Clamp to bounds
        return max(-cls.MAX_HEIGHT, min(cls.MAX_HEIGHT, height))
    
    @classmethod
    def _parse_dex(cls, dex: str) -> DexSector:
        """Parse DEX string to sector enum."""
        dex_upper = str(dex).upper()
        
        if "RAYDIUM" in dex_upper or "RAY" in dex_upper:
            return DexSector.RAYDIUM
        elif "ORCA" in dex_upper:
            return DexSector.ORCA
        elif "METEORA" in dex_upper:
            return DexSector.METEORA
        elif "JUPITER" in dex_upper or "JUP" in dex_upper:
            return DexSector.JUPITER
        elif "PUMP" in dex_upper:
            return DexSector.PUMPFUN
        else:
            return DexSector.UNKNOWN
    
    @classmethod
    def _get_sector_angle(cls, sector: DexSector, mint: str) -> float:
        """
        Get angle within DEX sector.
        Uses mint hash to distribute tokens within sector.
        """
        if sector == DexSector.UNKNOWN:
            # Unknown DEX: use full hash distribution
            return cls._mint_to_angle(mint, 0, 2 * math.pi)
        
        start, end = DEX_SECTORS.get(sector, (0, 2 * math.pi))
        return cls._mint_to_angle(mint, start, end)
    
    @classmethod
    def _mint_to_angle(cls, mint: str, min_angle: float, max_angle: float) -> float:
        """
        Generate deterministic angle within range from mint address.
        """
        if not mint:
            return min_angle
        
        hash_bytes = hashlib.md5(mint.encode()).digest()
        hash_int = int.from_bytes(hash_bytes[:4], 'big')
        
        # Map to range
        normalized = hash_int / (2**32)
        return min_angle + normalized * (max_angle - min_angle)
    
    @classmethod
    def get_pool_offset(
        cls, 
        parent_xyz: Tuple[float, float, float], 
        pool_index: int,
        total_pools: int = 4,
        spread: float = 1.0,
    ) -> Tuple[float, float, float]:
        """
        Calculate orbital position for a pool around its parent token.
        
        Spread controls orbit tightness (lower spread = closer pools = tighter spread)
        """
        px, py, pz = parent_xyz
        
        # Orbital radius based on spread
        orbit_radius = 3.0 + (spread * 2.0)
        angle = (2 * math.pi * pool_index) / max(total_pools, 1)
        
        # Orbit in XZ plane around parent
        ox = px + orbit_radius * math.cos(angle)
        oy = py + 0.5  # Slight vertical offset
        oz = pz + orbit_radius * math.sin(angle)
        
        return (round(ox, 2), round(oy, 2), round(oz, 2))
    
    @staticmethod
    def _safe_float(value: Any) -> float:
        """Safely convert to float with NaN/Inf handling."""
        try:
            f = float(value)
            if math.isnan(f) or math.isinf(f):
                return 0.0
            return f
        except (ValueError, TypeError):
            return 0.0
    
    @classmethod
    def get_sector_color(cls, sector: DexSector) -> str:
        """Get sector glow color."""
        colors = {
            DexSector.RAYDIUM: "#FF1493",   # Deep Pink
            DexSector.ORCA: "#00CED1",      # Dark Turquoise
            DexSector.METEORA: "#FFD700",   # Gold
            DexSector.JUPITER: "#32CD32",   # Lime Green
            DexSector.PUMPFUN: "#FF6347",   # Tomato
            DexSector.UNKNOWN: "#808080",   # Gray
        }
        return colors.get(sector, "#808080")

