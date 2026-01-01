"""
Visual Transformer V36
======================
The Intermediary Layer that converts raw Market Data into distinct Visual Archetypes.

V36 Enhancements:
- node_type: "TOKEN" (persistent) vs "EVENT" (transient swap/whale)
- Metric-driven sizing: radius based on volume, distance based on liquidity
- Whale detection with unique signifier
"""

from typing import Dict, Any, Optional
from src.shared.system.signal_bus import Signal, SignalType
import math

# Thresholds for whale detection
WHALE_THRESHOLD_USD = 50000  # $50k+ swap = whale

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
        
        # For events, symbol is the event type (e.g., "⚡ RAYDIUM"), label is the value
        is_event = data.get("is_event") or mint.startswith("SWAP_") or mint.startswith("FLASH_")
        
        if is_event:
            label = data.get("symbol") or "⚡ SWAP"
            event_label = data.get("label") or ""  # e.g., "$1.5k"
        else:
            label = data.get("symbol") or data.get("label")
            event_label = ""
            
            # Resolve missing label via Registry for actual tokens
            if not label or label == "???":
                try:
                    from src.shared.infrastructure.token_registry import TokenRegistry
                    registry = TokenRegistry()
                    if registry._initialized:
                         resolved = registry.get_symbol(mint)
                         if resolved:
                             label = resolved
                except Exception:
                     pass
        
        if not label:
            label = f"{mint[:4]}..{mint[-4:]}"

        # --- Metadata Extraction ---
        try:
            volume = float(data.get("volume_24h") or data.get("volume") or 0)
        except (ValueError, TypeError):
            volume = 0.0
        
        try:
            liquidity = float(data.get("liquidity", 1000))
        except (ValueError, TypeError):
            liquidity = 1000.0

        price = data.get("price") or data.get("price_usd") or 0.0
        change_24h = data.get("price_change_24h") or 0.0
        market_cap = data.get("market_cap") or data.get("fdv") or 0.0
        
        # Sanitization
        if math.isnan(volume) or math.isinf(volume): volume = 0.0
        if math.isnan(liquidity) or math.isinf(liquidity): liquidity = 1000.0
        try: price = float(price)
        except: price = 0.0
        try: change_24h = float(change_24h)
        except: change_24h = 0.0
        try: market_cap = float(market_cap)
        except: market_cap = 0.0

        # --- V36: Metric-Driven Sizing ---
        # Radius: Based on volume (larger volume = larger node)
        # Range: 0.5 (low volume) to 4.0 (high volume)
        volume_log = math.log10(max(volume, 1))  # log scale
        base_radius = min(max(0.5 + volume_log * 0.3, 0.5), 4.0)
        
        # Distance Factor: Based on liquidity (higher liquidity = closer to center)
        # Range: 0.2 (high liq, close) to 1.0 (low liq, far)
        liq_log = math.log10(max(liquidity, 100))
        distance_factor = max(0.2, 1.0 - liq_log * 0.1)
        
        # Velocity: Volume/Liquidity ratio (higher = faster movement)
        velocity_factor = min(max(volume / (liquidity + 1) * 0.1, 0.1), 5.0)

        # --- Node Type Detection ---
        is_event = source in ("WSS_Listener", "DEX", "HARVESTER", "WHALE", "BRIDGE")
        is_whale = volume >= WHALE_THRESHOLD_USD or source == "WHALE"
        node_type = "EVENT" if is_event else "TOKEN"
        
        # --- Base Params ---
        params = {
            "radius": base_radius,
            "roughness": 0.5,
            "emissive_intensity": 2.0,
            "hex_color": "#00ffaa",
            "price": price,
            "change_24h": change_24h,
            "volume": volume,
            "liquidity": liquidity,
            "market_cap": market_cap,
            "velocity_factor": velocity_factor,
            "distance_factor": distance_factor,
            "is_whale": is_whale
        }
        
        # --- Archetype Selection ---
        archetype = "GLOBE"
        color = "#00ffaa"
        
        # WHALE ALERT (Gold/Cyan Torus - Unique Signifier)
        if is_whale:
            archetype = "WHALE"
            color = "#ffd700" if volume >= 100000 else "#00ffcc"  # Gold for mega, cyan for large
            params.update({
                "radius": min(base_radius * 2, 6.0),  # Extra large
                "emissive_intensity": 10.0,
                "hex_color": color,
                "roughness": 0.0,
                "pulse": True,  # Frontend can use this for animation
                "velocity_factor": 0.1  # Slow majestic movement
            })
        
        # DEX SWAPS (Green Pulsar - Events)
        elif source in ("WSS_Listener", "DEX", "HARVESTER"):
            archetype = "PULSAR"
            color = "#39ff14"
            params.update({
                "radius": min(base_radius * 1.2, 2.5),
                "emissive_intensity": 3.0 + volume_log * 0.5,
                "hex_color": color,
                "roughness": 0.1,
                "flash": True  # Frontend can use for flash effect
            })
        
        # CLMM / ORCA (Teal Nova)
        elif source in ("ORCA", "DYDX", "METEORA"):
            archetype = "NOVA"
            color = "#00ffcc"
            params.update({
                "radius": base_radius * 1.3,
                "emissive_intensity": 2.5,
                "hex_color": color,
                "roughness": 0.2
            })
            
        # ORACLES / WATCHED TOKENS (Cyan Planet - Stable)
        elif source == "PYTH":
            archetype = "PLANET"
            color = "#00ffff"
            params.update({
                "radius": base_radius * 1.5,
                "emissive_intensity": 1.5 + (1 if data.get("in_position") else 0),
                "hex_color": "#ff00ff" if data.get("in_position") else color,  # Magenta if holding
                "roughness": 0.8
            })
            
        # DISCOVERIES (Purple Comet)
        elif source in ("DISCOVERY", "SCRAPER", "SAURON_PUMPFUN", "SAURON_RAYDIUM"):
            archetype = "COMET"
            color = "#9945ff"
            params.update({
                "radius": base_radius * 0.8,
                "emissive_intensity": 4.0,
                "hex_color": color,
                "roughness": 0.3
            })

        # GRADUATIONS / LAUNCHES (Orange Supernova)
        elif source in ("PUMP_GRAD", "LAUNCHPAD", "MIGRATION"):
            archetype = "SUPERNOVA"
            color = "#ffaa00"
            params.update({
                "radius": base_radius * 2.0,
                "emissive_intensity": 8.0,
                "hex_color": color,
                "roughness": 0.0,
                "velocity_factor": 0.0
            })
        
        # POOL / MOON (Orbits parent token)
        elif source in ("POOL", "ORCA_POOL", "RAYDIUM_POOL", "METEORA_POOL"):
            archetype = "MOON"
            # Color by DEX
            dex_colors = {
                "ORCA_POOL": "#00d4aa",
                "RAYDIUM_POOL": "#5ac4be", 
                "METEORA_POOL": "#ffd700"
            }
            color = dex_colors.get(source, "#aaaaaa")
            params.update({
                "radius": max(0.3, base_radius * 0.4),  # Small moon
                "emissive_intensity": 1.5,
                "hex_color": color,
                "roughness": 0.6,
                "parent_mint": data.get("parent_mint") or data.get("token_mint"),
                "pool_address": data.get("pool_address") or mint,
                "dex": source.replace("_POOL", ""),
                "orbit_speed": 0.02,
                "orbit_radius": 5 + (volume_log * 2)  # Larger pools orbit further
            })
            node_type = "MOON"

        # Log whale/major events
        if is_whale or archetype in ("SUPERNOVA", "WHALE"):
            print(f"🔮 [VOID_TRANSFORM] {archetype} spawned for {label} (${volume:,.0f})")
        else:
            print(f"🔮 [VOID_TRANSFORM] {archetype} spawned for {label}")

        return {
            "type": "ARCHETYPE_UPDATE",
            "id": mint,
            "label": label,
            "event_label": event_label,  # For events like "$1.5k" 
            "archetype": archetype,
            "node_type": node_type,
            "params": params
        }
