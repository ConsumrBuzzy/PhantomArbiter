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
        
        # 2. Archetype Mapping (Expanded V34)
        # Pulsar (Green) - DEX Swaps, Real-time trades
        # Planet (Cyan) - Oracle data, stable reference
        # Supernova (Orange) - Graduations, major events
        # Comet (Purple) - Discoveries, new tokens
        # Nova (Teal) - CLMM/Orca activity
        
        archetype = "GLOBE"
        color = "#00ffaa"  # Visible teal fallback
        params = {
            "radius": 1.0,
            "roughness": 0.5,
            "emissive_intensity": 2.0,  # Brighter default
            "hex_color": "#00ffaa"
        }
        
        # DEX SWAPS (Green Pulsar)
        if source in ("WSS_Listener", "DEX", "HARVESTER"):
            archetype = "PULSAR"
            color = "#39ff14"
            params.update({
                "radius": 1.2,
                "emissive_intensity": 3.0,
                "hex_color": color,
                "roughness": 0.1
            })
        
        # CLMM / ORCA (Teal Nova)
        elif source in ("ORCA", "DYDX", "METEORA"):
            archetype = "NOVA"
            color = "#00ffcc"
            params.update({
                "radius": 1.5,
                "emissive_intensity": 2.5,
                "hex_color": color,
                "roughness": 0.2
            })
            
        # ORACLES (Cyan Planet)
        elif source == "PYTH":
            archetype = "PLANET"
            color = "#00ffff"
            params.update({
                "radius": 2.0,
                "emissive_intensity": 1.5,
                "hex_color": color,
                "roughness": 0.8
            })
            
        # DISCOVERIES (Purple Comet)
        elif source in ("DISCOVERY", "SCRAPER", "SAURON_PUMPFUN", "SAURON_RAYDIUM"):
            archetype = "COMET"
            color = "#9945ff"
            
            # V2 Physics: Velocity based on volume/liquidity
            try:
                volume = float(data.get("volume_24h", 0))
            except (ValueError, TypeError):
                volume = 0.0
            
            try:
                liquidity = float(data.get("liquidity", 1000))
            except (ValueError, TypeError):
                liquidity = 1000.0
            
            # Sanitization (Prevent NaN/Inf which breaks JSON)
            import math
            if math.isnan(volume) or math.isinf(volume): volume = 0.0
            if math.isnan(liquidity) or math.isinf(liquidity): liquidity = 1000.0

            # Normalized velocity factor (0.1 to 5.0)
            velocity_factor = min(max(volume / (liquidity + 1) * 0.1, 0.1), 5.0)
            
            # Extract extended market data
            price = data.get("price") or data.get("price_usd") or 0.0
            change_24h = data.get("price_change_24h") or 0.0
            
            # Sanitize price/change
            try: price = float(price)
            except: price = 0.0
            try: change_24h = float(change_24h)
            except: change_24h = 0.0

            params.update({
                "radius": 0.8,
                "emissive_intensity": 4.0,
                "hex_color": color,
                "roughness": 0.3,
                "velocity_factor": velocity_factor,
                "price": price,
                "change_24h": change_24h,
                "volume": volume
            })

        # GRADUATIONS / LAUNCHES (Orange Supernova)
        elif source in ("PUMP_GRAD", "LAUNCHPAD", "MIGRATION"):
            archetype = "SUPERNOVA"
            color = "#ffaa00"
            params.update({
                "radius": 3.0,
                "emissive_intensity": 8.0,
                "hex_color": color,
                "roughness": 0.0,
                "velocity_factor": 0.0  # Stationary explosion
            })


        return {
            "type": "ARCHETYPE_UPDATE",
            "id": mint,
            "label": label,
            "archetype": archetype,
            "params": params
        }

