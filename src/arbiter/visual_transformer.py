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
        Transforms a raw Signal into a Visual Archetype Payload.
        """
        data = signal.data
        source = signal.source or data.get("source", "UNKNOWN")
        
        # 1. Identity
        mint = data.get("mint") or data.get("token")
        if not mint:
            return None
            
        label = data.get("symbol", "???")
        
        # 2. Archetype Mapping
        # User defined: Pulsar, Planet, Supernova, Comet
        archetype = "GLOBE" # Fallback
        color = "#ffffff"
        params = {
            "radius": 1.0,
            "roughness": 0.5,
            "emissive_intensity": 1.0,
            "hex_color": "#FFFFFF"
        }
        
        if source == "WSS_Listener" or source == "DEX":
            # "The Pulsar" (Green) - Shockwave trigger
            archetype = "PULSAR"
            color = "#39ff14"
            params.update({
                "radius": 1.2,
                "emissive_intensity": 3.0,
                "hex_color": color,
                "roughness": 0.1
            })
            
        elif source == "PYTH":
            # "The Planet" (Cyan) - Stable body
            archetype = "PLANET"
            color = "#00ffff"
            params.update({
                "radius": 2.0,
                "emissive_intensity": 1.5,
                "hex_color": color,
                "roughness": 0.8 # Rocky texture
            })
            
        elif source == "PUMP_GRAD":
            # "The Supernova" (Orange) - Rapid expansion
            archetype = "SUPERNOVA"
            color = "#ffaa00"
            params.update({
                "radius": 3.0,
                "emissive_intensity": 8.0,
                "hex_color": color,
                "roughness": 0.0
            })
            
        elif source == "DISCOVERY" or source == "SCRAPER":
            # "The Comet" (Purple) - Moving trailer
            archetype = "COMET"
            color = "#9945ff"
            params.update({
                "radius": 0.8,
                "emissive_intensity": 4.0,
                "hex_color": color,
                "roughness": 0.3
            })

        return {
            "type": "ARCHETYPE_UPDATE",
            "id": mint,
            "label": label,
            "archetype": archetype,
            "params": params
        }
