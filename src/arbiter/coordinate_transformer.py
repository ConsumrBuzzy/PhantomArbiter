"""
Coordinate Transformer - Galactic XYZ Semantic Mapping.

Maps market data to 3D spatial coordinates using Cylindrical Mapping:
- Radius (R): Market cap / volume (blue chips at center)
- Angle (θ): DEX sector (Raydium/Orca/Meteora districts)
- Height (Y): RSI momentum (overbought up, oversold down)

V141: Synced with Galaxy App Logic + Shared Constellation Manager
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
    """
    
    # Galaxy bounds
    GALAXY_RADIUS = 1500.0 # Supermassive V36
    CORE_RADIUS = 50.0   # Expanded Core
    RIM_RADIUS = 1200.0   # New tokens at the edge
    MAX_HEIGHT = 300.0   # Verticality V36
    
    @classmethod
    def get_xyz(
        cls,
        data: Dict[str, Any],
        indicators: Optional[Dict[str, Any]] = None,
    ) -> Tuple[float, float, float]:
        """
        Convert market data to XYZ coordinates using semantic mapping.
        """
        mint = data.get("mint") or data.get("token") or ""
        symbol = data.get("symbol") or data.get("label") or ""
        
        # Extract metrics
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
        y = cls._rsi_to_height(rsi)
        
        return (
            round(x, 2),
            round(y, 2),
            round(z, 2)
        )
    
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
