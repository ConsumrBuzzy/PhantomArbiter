"""
Galaxy Models - Pydantic schemas for event payloads.

Fully decoupled from Core SignalBus types.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Event types received from Core Engine."""
    MARKET_UPDATE = "MARKET_UPDATE"
    NEW_TOKEN = "NEW_TOKEN"
    WHALE_ACTIVITY = "WHALE_ACTIVITY"
    ARB_OPP = "ARB_OPP"
    MARKET_INTEL = "MARKET_INTEL"
    WHIFF_DETECTED = "WHIFF_DETECTED"
    SYSTEM_STATS = "SYSTEM_STATS"
    LOG_UPDATE = "LOG_UPDATE"
    SCAN_UPDATE = "SCAN_UPDATE"
    HOP_PATH = "HOP_PATH"


class EventPayload(BaseModel):
    """Event received from Core Engine EventBridge."""
    type: EventType
    source: str = "CORE"
    timestamp: float = 0.0
    data: Dict[str, Any] = Field(default_factory=dict)


class VisualParams(BaseModel):
    """Visual parameters for a Galaxy object."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    radius: float = 1.0
    roughness: float = 0.5
    metalness: float = 0.2
    emissive_intensity: float = 2.0
    hex_color: str = "#00ffaa"
    velocity_factor: float = 1.0
    distance_factor: float = 1.0
    
    # Metadata for tooltips
    price: float = 0.0
    change_24h: float = 0.0
    volume: float = 0.0
    liquidity: float = 1000.0
    market_cap: float = 0.0
    rsi: float = 50.0
    
    # Animation hints
    pulse: bool = False
    flash: bool = False
    is_whale: bool = False
    
    # Moon/Pool specific
    parent_mint: Optional[str] = None
    pool_address: Optional[str] = None
    dex: Optional[str] = None
    orbit_speed: float = 0.02
    orbit_radius: float = 5.0


class VisualObject(BaseModel):
    """A visual object to render in the Galaxy."""
    type: str = "ARCHETYPE_UPDATE"
    id: str
    label: str
    event_label: str = ""
    archetype: str = "GLOBE"
    node_type: str = "TOKEN"
    params: VisualParams = Field(default_factory=VisualParams)


class BatchUpdate(BaseModel):
    """Batch of visual updates for broadcast."""
    type: str = "BATCH_UPDATE"
    data: List[VisualObject] = Field(default_factory=list)


class HopPath(BaseModel):
    """Arbitrage hop path visualization."""
    type: str = "HOP_PATH"
    path: List[str] = Field(default_factory=list)
    profit: float = 0.0
    source: str = "ARBITER"


class WhalePulse(BaseModel):
    """Whale activity pulse visualization."""
    type: str = "WHALE_PULSE"
    mint: str = ""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    intensity: float = 5.0
    color: str = "#ffd700"


class SystemStats(BaseModel):
    """System statistics for HUD display."""
    type: str = "SYSTEM_STATS"
    data: Dict[str, Any] = Field(default_factory=dict)


class LogEntry(BaseModel):
    """Log entry for stream display."""
    type: str = "LOG_ENTRY"
    level: str = "INFO"
    message: str = ""
    timestamp: float = 0.0


class ScanUpdate(BaseModel):
    """Arbitrage opportunity scan results."""
    type: str = "SCAN_UPDATE"
    opportunities: List[Dict[str, Any]] = Field(default_factory=list)
