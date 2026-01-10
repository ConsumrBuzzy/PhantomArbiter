"""
Engine Registry
================
Central registry tracking all trading engine states.
Maintains status, configuration, and subprocess handles for lifecycle management.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from enum import Enum
import time
import asyncio


class EngineStatus(Enum):
    """Engine lifecycle states."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class EngineInfo:
    """
    Represents a single engine's state and metadata.
    """
    name: str
    display_name: str
    status: EngineStatus = EngineStatus.STOPPED
    pid: Optional[int] = None
    process: Optional[asyncio.subprocess.Process] = None
    config: Dict[str, Any] = field(default_factory=dict)
    started_at: Optional[float] = None
    error_msg: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for WebSocket transmission."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "status": self.status.value,
            "pid": self.pid,
            "config": self.config,
            "started_at": self.started_at,
            "uptime_seconds": (time.time() - self.started_at) if self.started_at else None,
            "error_msg": self.error_msg
        }


class EngineRegistry:
    """
    Singleton registry for all trading engines.
    Thread-safe state management for engine lifecycle.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._engines: Dict[str, EngineInfo] = {}
        self._lock = asyncio.Lock()
        
        # Register available engines with default configs
        self._register_defaults()
        self._initialized = True
    
    def _register_defaults(self):
        """Initialize all available engines."""
        defaults = [
            {
                "name": "arb",
                "display_name": "Arbitrage Engine",
                "config": {
                    "min_spread": 0.5,
                    "max_trade_usd": 100,
                    "scan_interval": 2,
                    "risk_tier": "mid"
                }
            },
            {
                "name": "funding",
                "display_name": "Funding Rate Engine",
                "config": {
                    "leverage": 2.0,
                    "watchdog_threshold": -0.0005,
                    "rebalance_enabled": True,
                    "max_position_usd": 500
                }
            },
            {
                "name": "scalp",
                "display_name": "Scalp Sniper Engine",
                "config": {
                    "take_profit_pct": 10.0,
                    "stop_loss_pct": 5.0,
                    "max_pods": 5,
                    "sentiment_threshold": 0.7
                }
            }
        ]
        
        for eng in defaults:
            self._engines[eng["name"]] = EngineInfo(
                name=eng["name"],
                display_name=eng["display_name"],
                config=eng["config"]
            )
    
    async def get_engine(self, name: str) -> Optional[EngineInfo]:
        """Get engine info by name."""
        async with self._lock:
            return self._engines.get(name)
    
    async def get_all_engines(self) -> Dict[str, EngineInfo]:
        """Get all registered engines."""
        async with self._lock:
            return dict(self._engines)
    
    async def update_status(self, name: str, status: EngineStatus, 
                           pid: Optional[int] = None,
                           process: Optional[asyncio.subprocess.Process] = None,
                           error_msg: Optional[str] = None):
        """Update engine status atomically."""
        async with self._lock:
            if name not in self._engines:
                return False
            
            engine = self._engines[name]
            engine.status = status
            engine.error_msg = error_msg
            
            if status == EngineStatus.RUNNING:
                engine.pid = pid
                engine.process = process
                engine.started_at = time.time()
            elif status == EngineStatus.STOPPED:
                engine.pid = None
                engine.process = None
                engine.started_at = None
            
            return True
    
    async def update_config(self, name: str, config: Dict[str, Any]) -> bool:
        """Update engine configuration."""
        async with self._lock:
            if name not in self._engines:
                return False
            
            self._engines[name].config.update(config)
            return True
    
    async def get_status_snapshot(self) -> Dict[str, Any]:
        """Get serializable snapshot of all engine states."""
        async with self._lock:
            return {
                name: engine.to_dict() 
                for name, engine in self._engines.items()
            }


# Global singleton
engine_registry = EngineRegistry()
