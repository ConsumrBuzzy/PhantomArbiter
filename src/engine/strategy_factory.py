"""
Strategy Factory
================
Phase 17: Modular Industrialization

Centralized factory for spawning Pod clusters based on the active strategy.
Decouples the Director from specific Pod implementations.
"""

from enum import Enum
from typing import List, Dict, Any

from src.engine.pod_manager import PodManager, BasePod
from src.shared.system.logging import Logger


class StrategyMode(Enum):
    SCALPER = "scalper"  # Traditional Scalping
    NARROW_PATH = "narrow_path"  # Multi-Hop Arbitrage (Phase 16)
    HYBRID = "hybrid"  # Both (High Load)


class StrategyFactory:
    """
    Spawns and configures Pods based on the selected Strategy Mode.
    """

    def __init__(self, pod_manager: PodManager):
        self.manager = pod_manager

    def spawn_pods(
        self, mode: StrategyMode, config: Dict[str, Any] = None
    ) -> List[BasePod]:
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
            from config.settings import Settings

            # 1. Bridge Pod (The Sniffer)
            bridge_pod = self.manager.spawn_bridge_pod(
                whale_threshold=config.get("whale_threshold", 250_000)
            )
            pods.append(bridge_pod)

            # 2. Cycle Pod (Governor of Wisdom)
            cycle_pod = self.manager.spawn_cycle_pod(
                name="market_governor", cooldown=1.0
            )
            pods.append(cycle_pod)

            # 3. Hop Pod (Multiverse Scanner)
            hop_pod = self.manager.spawn_hop_pod(
                name="sol_multiverse",
                start_token=getattr(
                    Settings, "SOL_MINT", "So11111111111111111111111111111111111111112"
                ),
                min_hops=getattr(Settings, "HOP_MIN_LEGS", 2),
                max_hops=getattr(Settings, "HOP_MAX_LEGS", 4),
                min_liquidity=getattr(Settings, "HOP_MIN_LIQUIDITY_USD", 5000),
                cooldown=getattr(Settings, "HOP_SCAN_INTERVAL_SEC", 2.0),
            )
            pods.append(hop_pod)

            # 4. Execution Pod (The Striker)
            # Default to PAPER or GHOST depending on config
            # But here we default to PAPER for safety unless overridden
            exec_mode = config.get("execution_mode", "paper")

            exec_pod = self.manager.spawn_execution_pod(
                name="striker",
                mode=exec_mode,
                min_profit_pct=getattr(Settings, "HOP_MIN_PROFIT_PCT", 0.15),
                cooldown=0.5,
            )
            pods.append(exec_pod)

        return pods

    def get_strategy_mode(self, settings_module: Any) -> StrategyMode:
        """Determine strategy from settings."""
        if getattr(settings_module, "HOP_ENGINE_ENABLED", False):
            return StrategyMode.NARROW_PATH
        return StrategyMode.SCALPER
