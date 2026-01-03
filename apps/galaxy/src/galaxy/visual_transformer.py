"""
Visual Transformer - Market Data to Visual Archetype Mapping.

Converts raw event data into visual objects for Galaxy rendering.
Uses RSI for color gradient and DEX for sector positioning.
"""

from __future__ import annotations

import math
from typing import Dict, Any, Optional

from galaxy.models import (
    EventPayload, 
    VisualObject, 
    VisualParams,
    EventType,
)
from galaxy.coordinate_transformer import CoordinateTransformer, DexSector


# Thresholds
WHALE_THRESHOLD_USD = 50_000


def rsi_to_color(rsi: float) -> str:
    """
    Convert RSI to color gradient.
    
    RSI 0-30: Red (oversold)
    RSI 30-50: Orange→Yellow
    RSI 50-70: Yellow→Green
    RSI 70-100: Green (overbought)
    """
    rsi = max(0, min(100, rsi))
    
    if rsi < 30:
        # Red
        return "#ff4444"
    elif rsi < 40:
        # Red → Orange
        t = (rsi - 30) / 10
        r = 255
        g = int(68 + t * 102)  # 68 → 170
        return f"#{r:02x}{g:02x}44"
    elif rsi < 50:
        # Orange → Yellow
        t = (rsi - 40) / 10
        r = 255
        g = int(170 + t * 85)  # 170 → 255
        return f"#{r:02x}{g:02x}00"
    elif rsi < 60:
        # Yellow
        return "#ffff00"
    elif rsi < 70:
        # Yellow → Light Green
        t = (rsi - 60) / 10
        r = int(255 - t * 127)  # 255 → 128
        g = 255
        return f"#{r:02x}{g:02x}00"
    else:
        # Green (bullish)
        return "#00ff88"


class VisualTransformer:
    """
    Alchemist that turns Data into Light.
    Transforms raw events into visual archetypes with RSI-based coloring.
    """
    
    @classmethod
    def transform(cls, event: EventPayload) -> Optional[VisualObject]:
        """
        Transform an event payload into a visual object.
        
        Args:
            event: EventPayload from Core Engine
            
        Returns:
            VisualObject for Galaxy rendering, or None if invalid
        """
        data = event.data
        source = event.source or data.get("source", "UNKNOWN")
        
        # Identity
        mint = data.get("mint") or data.get("token")
        if not mint:
            return None
        
        # Label resolution
        label = data.get("symbol") or data.get("label")
        if not label or label == "???":
            label = f"{mint[:4]}..{mint[-4:]}"
        
        # Event label (for transient events like swaps)
        event_label = data.get("event_label", "")
        
        # --- Metric Extraction ---
        volume = cls._safe_float(data.get("volume_24h") or data.get("volume"), 0.0)
        liquidity = cls._safe_float(data.get("liquidity"), 1000.0)
        price = cls._safe_float(data.get("price") or data.get("price_usd"), 0.0)
        change_24h = cls._safe_float(data.get("price_change_24h"), 0.0)
        market_cap = cls._safe_float(data.get("market_cap") or data.get("fdv"), 0.0)
        rsi = cls._safe_float(data.get("rsi"), 50.0)
        
        # --- Metric-Driven Sizing ---
        volume_log = math.log10(max(volume, 1))
        base_radius = min(max(0.5 + volume_log * 0.3, 0.5), 4.0)
        
        liq_log = math.log10(max(liquidity, 100))
        distance_factor = max(0.2, 1.0 - liq_log * 0.1)
        velocity_factor = min(max(volume / (liquidity + 1) * 0.1, 0.1), 5.0)
        
        # --- Node Type Detection ---
        is_event = source in ("WSS_Listener", "DEX", "HARVESTER", "WHALE", "BRIDGE")
        is_whale = volume >= WHALE_THRESHOLD_USD or source == "WHALE"
        node_type = "EVENT" if is_event else "TOKEN"
        
        # --- Spatial Coordinates (with RSI for height) ---
        indicators = {"rsi_14": rsi, "rsi": rsi}
        x, y, z = CoordinateTransformer.get_xyz(data, indicators=indicators)
        
        # --- RSI-Based Default Color ---
        default_color = rsi_to_color(rsi)
        
        # --- Base Params ---
        params = VisualParams(
            x=x, y=y, z=z,
            radius=base_radius,
            roughness=0.5,
            emissive_intensity=2.0,
            hex_color=default_color,
            price=price,
            change_24h=change_24h,
            volume=volume,
            liquidity=liquidity,
            market_cap=market_cap,
            rsi=rsi,
            velocity_factor=velocity_factor,
            distance_factor=distance_factor,
            is_whale=is_whale,
            # V89.15: Pass Price & Category
            category=str(data.get("category", "UNKNOWN")),
            price_usd=float(data.get("price_usd", 0.0)),
        )
        
        # --- Archetype Selection ---
        archetype, color = cls._select_archetype(
            source=source,
            is_whale=is_whale,
            volume=volume,
            volume_log=volume_log,
            rsi=rsi,
            in_position=data.get("in_position", False),
        )
        
        # Update params with archetype-specific values
        params.hex_color = color
        cls._apply_archetype_params(params, archetype, source, data, volume_log, base_radius)
        
        return VisualObject(
            type="ARCHETYPE_UPDATE",
            id=mint,
            label=label,
            event_label=event_label,
            archetype=archetype,
            node_type=node_type,
            params=params,
        )
    
    @classmethod
    def transform_dict(cls, data: Dict[str, Any]) -> Optional[VisualObject]:
        """
        Transform a raw dict into a visual object.
        Convenience method for when EventPayload isn't constructed.
        """
        event = EventPayload(
            type=EventType.MARKET_UPDATE,
            source=data.get("source", "UNKNOWN"),
            data=data,
        )
        return cls.transform(event)
    
    @staticmethod
    def _safe_float(value: Any, default: float) -> float:
        """Safely convert to float with NaN/Inf handling."""
        try:
            result = float(value) if value is not None else default
            if math.isnan(result) or math.isinf(result):
                return default
            return result
        except (ValueError, TypeError):
            return default
    
    @staticmethod
    def _select_archetype(
        source: str,
        is_whale: bool,
        volume: float,
        volume_log: float,
        rsi: float,
        in_position: bool,
    ) -> tuple[str, str]:
        """Select archetype and color based on source and metrics."""
        
        # WHALE (Gold/Cyan Torus)
        if is_whale:
            color = "#ffd700" if volume >= 100_000 else "#00ffcc"
            return ("WHALE", color)
        
        # DEX SWAPS (Green Pulsar)
        if source in ("WSS_Listener", "DEX", "HARVESTER"):
            return ("PULSAR", "#39ff14")
        
        # CLMM/ORCA (Teal Nova)
        if source in ("ORCA", "DYDX", "METEORA"):
            return ("NOVA", "#00ffcc")
        
        # ORACLES (RSI-colored Planet)
        if source == "PYTH":
            if rsi < 30:
                color = "#ff4444"  # Red - oversold
            elif rsi < 50:
                color = "#ffaa00"  # Orange - weak
            elif rsi < 70:
                color = "#00ffff"  # Cyan - neutral
            else:
                color = "#00ff88"  # Green - overbought
            
            if in_position:
                color = "#ff00ff"  # Magenta - holding
            
            return ("PLANET", color)
        
        # DISCOVERIES (Purple Comet)
        if source in ("DISCOVERY", "SCRAPER", "SAURON_PUMPFUN", "SAURON_RAYDIUM"):
            return ("COMET", "#9945ff")
        
        # GRADUATIONS (Orange Supernova)
        if source in ("PUMP_GRAD", "LAUNCHPAD", "MIGRATION"):
            return ("SUPERNOVA", "#ffaa00")
        
        # POOLS (Moon)
        if source in ("POOL", "ORCA_POOL", "RAYDIUM_POOL", "METEORA_POOL"):
            dex_colors = {
                "ORCA_POOL": "#00d4aa",
                "RAYDIUM_POOL": "#5ac4be",
                "METEORA_POOL": "#ffd700",
            }
            return ("MOON", dex_colors.get(source, "#aaaaaa"))
        
        # Default: Globe
        return ("GLOBE", "#00ffaa")
    
    @staticmethod
    def _apply_archetype_params(
        params: VisualParams,
        archetype: str,
        source: str,
        data: Dict[str, Any],
        volume_log: float,
        base_radius: float,
    ) -> None:
        """Apply archetype-specific parameter modifications."""
        
        if archetype == "WHALE":
            params.radius = min(base_radius * 2, 6.0)
            params.emissive_intensity = 10.0
            params.roughness = 0.0
            params.pulse = True
            params.velocity_factor = 0.1
            
        elif archetype == "PULSAR":
            params.radius = min(base_radius * 1.2, 2.5)
            params.emissive_intensity = 3.0 + volume_log * 0.5
            params.roughness = 0.1
            params.flash = True
            
        elif archetype == "NOVA":
            params.radius = base_radius * 1.3
            params.emissive_intensity = 2.5
            params.roughness = 0.2
            
        elif archetype == "PLANET":
            params.radius = base_radius * 1.5
            params.emissive_intensity = 1.5 + (1 if data.get("in_position") else 0)
            params.roughness = 0.8
            
        elif archetype == "COMET":
            params.radius = base_radius * 0.8
            params.emissive_intensity = 4.0
            params.roughness = 0.3
            
        elif archetype == "SUPERNOVA":
            params.radius = base_radius * 2.0
            params.emissive_intensity = 8.0
            params.roughness = 0.0
            params.velocity_factor = 0.0
            
        elif archetype == "MOON":
            params.radius = max(0.3, base_radius * 0.4)
            params.emissive_intensity = 1.5
            params.roughness = 0.6
            params.parent_mint = data.get("parent_mint") or data.get("token_mint")
            params.pool_address = data.get("pool_address")
            params.dex = source.replace("_POOL", "")
            params.orbit_radius = 5 + (volume_log * 2)
