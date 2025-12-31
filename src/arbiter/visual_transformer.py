"""
Visual Transformer
==================
The Intermediary Layer that converts raw Market Data into distinct Visual Archetypes.

Concepts:
- **Globe**: A standard token node (Sphere).
- **Star**: A high-liquidity, high-impact node (Emissive).
- **Comet**: A trending/moving token (Discovery).
- **Nebula**: A cluster of related activity (Sector).
"""

from typing import Dict, Any, Optional
from src.shared.system.signal_bus import Signal, SignalType

class VisualTransformer:
    """
    Alchemist that turns Data into Light.
    """
    
    @staticmethod
    def transform(signal: Signal) -> Optional[Dict[str, Any]]:
        """
        Transforms a raw Signal into a Visual Payload.
        """
        data = signal.data
        source = signal.source or data.get("source", "UNKNOWN")
        
        # 1. Identity
        mint = data.get("mint") or data.get("token")
        if not mint:
            return None
            
        label = data.get("symbol", "???")
        
        # 2. Archetype & Color Mapping
        archetype = "sphere" # Default
        color = "#ffffff"
        size_multiplier = 1.0
        
        if source == "WSS_Listener" or source == "DEX":
            # Execution Layer (Green)
            color = "#39ff14" # Neon Green
            archetype = "flash_sphere"
            
        elif source == "PYTH":
            # Truth Layer (Cyan)
            color = "#00ffff"
            archetype = "pulse_star" # Pulsing stable star
            
        elif source == "PUMP_GRAD":
            # Graduation (Orange)
            color = "#ffaa00"
            archetype = "supernova" # Explosive
            size_multiplier = 5.0
            
        elif source == "DISCOVERY" or source == "SCRAPER":
            # Discovery (Purple)
            color = "#9945ff"
            archetype = "comet" # Entering the system
            
        elif source == "LAUNCHPAD":
            # Creation (Magenta)
            color = "#ff00ff"
            archetype = "spark"
            
        elif source == "ORCA":
            # Liquidity (Teal)
            color = "#008080"
            archetype = "fluid_orb" # Fluid
            
        elif source == "ARB":
            # Warning (Red)
            color = "#ff0000"
            archetype = "warning_crystal"
            
        # 3. Physics / Dimensions
        # In a real metadata layer, we'd lookup Market Cap to set Radius
        # For now, we use a default
        radius = 2.0 * size_multiplier
        
        return {
            "type": "flash", # The protocol message type
            "node": mint,
            "label": label,
            "visual": {
                "color": color,
                "archetype": archetype,
                "radius": radius,
                "roughness": 0.2, # TODO: Map to volatility
                "metalness": 0.8
            },
            # Flat attributes for legacy compatibility
            "color": color,
            "energy": size_multiplier
        }
