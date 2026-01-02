"""
Coordinate Transformer V140
===========================
The Physics Engine for the Solana Galaxy.
Maps high-dimensional signals to 3D celestial coordinates.
"""

import math
import hashlib
from typing import Dict, Any, Tuple

class CoordinateTransformer:
    """
    Translates market signals into spatial positions.
    """
    
    # Constants for normalization
    SOL_MINT = "So11111111111111111111111111111111111111112"
    BASE_RADIUS = 200.0  # Max spread of planets
    
    @staticmethod
    def get_xyz(data: Dict[str, Any]) -> Tuple[float, float, float]:
        """
        Calculates X, Y, Z based on market context.
        
        Logic:
        - R (Distance): Inversely proportional to Liquidity.
        - Z (Altitude): Momentum (RSI) vs Inefficiency (Spread).
        - Theta (Sector): Based on token identity/hash.
        """
        mint = data.get("mint") or data.get("token") or "UNKNOWN"
        
        # 1. The Core ($SOL) is always at (0,0,0)
        if mint == CoordinateTransformer.SOL_MINT:
            return 0.0, 0.0, 0.0
        
        # 2. Radial Distance (Gravity Well)
        # Higher liquidity = closer to core
        try:
            liquidity = float(data.get("liquidity", 1000.0))
        except (ValueError, TypeError):
            liquidity = 1000.0
            
        # Log scale gravity: R = 1 / log10(liq)
        # Log scale gravity: R = 1 / log10(liq)
        # We want to use the range [50, 900] for r
        liq_log = math.log10(max(liquidity, 10))
        # Map log scale 1 (10 USD) -> 10 (10B USD) to radius 900 -> 50
        # Formula: r = 900 - (liq_log - 1) * (850 / 9)
        r = 900.0 - (max(1.0, min(liq_log, 10.0)) - 1.0) * (850.0 / 9.0)
        r = max(50.0, min(r, 950.0))
        
        # 3. Z-Axis (Verticality)
        # Scalper (UP): High RSI = positive
        # Arbiter (DOWN): High Spread = negative
        z = 0.0
        
        # Scalper Signal (RSI)
        rsi = data.get("rsi", 50.0) or 50.0
        if rsi != 50.0:
            z = (rsi - 50.0) * 2.0  # RSI 80 -> Z=60
            
        # Arbiter Signal (Spread)
        spread = data.get("spread", 0.0) or 0.0
        if spread > 0.005:  # 0.5% threshold
            # Sub-surface pull: Higher spread = deeper
            z = - (spread * 2000.0)  # 1% spread -> Z=-20
            
        # 4. Sector (Theta/Phi)
        # Use mint hash to assign a stable sector
        hash_val = int(hashlib.md5(mint.encode()).hexdigest(), 16)
        theta = (hash_val % 360) * math.pi / 180.0
        
        # Map to Cartesian
        x = r * math.cos(theta)
        y = r * math.sin(theta)
        
        # V140: Spatial Jitter (Break perfect ring pattern)
        # Predictable noise based on hash to avoid flickering
        jitter_x = ((hash_val % 100) - 50) * 0.2
        jitter_y = (((hash_val >> 4) % 100) - 50) * 0.2
        jitter_z = (((hash_val >> 8) % 100) - 50) * 0.1
        
        x += jitter_x
        y += jitter_y
        z += jitter_z
        
        # V140: Final Validation (Avoid NaN in JSON)
        def safe_val(v):
            if math.isnan(v) or math.isinf(v): return 0.0
            return float(v)
            
        return safe_val(x), safe_val(y), safe_val(z)

    @staticmethod
    def get_moon_offset(pool_data: Dict[str, Any]) -> Tuple[float, float, float]:
        """
        Calculates orbital offset for a moon (DEX pool).
        Proportional to DEX lag or individual TVL.
        """
        # Individual pool TVL determines orbit radius
        try:
            liq = float(pool_data.get("liquidity", 1000.0))
        except:
            liq = 1000.0
            
        orbit_r = 10.0 + math.log10(max(liq, 10)) * 2.0
        
        # Orbit speed based on DEX (stable rotation)
        dex = pool_data.get("dex", "UNKNOWN").upper()
        speed_map = {"ORCA": 0.02, "RAYDIUM": 0.015, "METEORA": 0.01}
        speed = speed_map.get(dex, 0.01)
        
        # Time-based position
        t = time.time() * speed
        
        ox = orbit_r * math.cos(t)
        oz = orbit_r * math.sin(t)
        oy = (hash(dex) % 10 - 5) * 0.5  # Fixed vertical jitter per DEX
        
        return ox, oy, oz

import time
