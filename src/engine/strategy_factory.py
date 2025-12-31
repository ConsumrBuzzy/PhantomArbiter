"""
Strategy Factory
================
Phase 17: Modular Industrialization

Centralized factory for spawning Pod clusters based on the active strategy.
Decouples the Director from specific Pod implementations.
"""

from enum import Enum
from typing import List, Dict, Any

from src.engine.pod_manager import PodManager, BasePod, PodType
from src.shared.system.logging import Logger

class StrategyMode(Enum):
    SCALPER = "scalper"           # Traditional Scalping
    NARROW_PATH = "narrow_path"   # Multi-Hop Arbitrage (Phase 16)
    HYBRID = "hybrid"             # Both (High Load)

class StrategyFactory:
    """
    Spawns and configures Pods based on the selected Strategy Mode.
    """
    
    def __init__(self, pod_manager: PodManager):
        self.manager = pod_manager
        
    def spawn_pods(self, mode: StrategyMode, config: Dict[str, Any] = None) -> List[BasePod]:
        """
        Spawn all necessary pods for the given mode.
        """
        if config is None:
            config = {}
            
        pods = []
        Logger.info(f"[Factory] Initializing strategy: {mode.value.upper()}")
        
        if mode == StrategyMode.SCALPER or mode == StrategyMode.HYBRID:
            # Traditional Scalping Pods (Placeholder for now)
            pass
            
        if mode == StrategyMode.NARROW_PATH or mode == StrategyMode.HYBRID:
            # 1. Scavenger Layer (FailureTracker is built-in to Harvester, BridgePod needs explicit spawn)
            
            # 2. Bridge Pod (The Sniffer)
            bridge_pod = self.manager.spawn_bridge_pod(
                whale_threshold=config.get('whale_threshold', 250_000)
            )
            pods.append(bridge_pod)
            
        return pods

    def get_strategy_mode(self, settings_module: Any) -> StrategyMode:
        """Determine strategy from settings."""
        if getattr(settings_module, 'HOP_ENGINE_ENABLED', False):
            return StrategyMode.NARROW_PATH
        return StrategyMode.SCALPER
