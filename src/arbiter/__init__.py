# src/arbiter - Arbitrage Engine Package
"""
Unified orchestrator for DEX arbitrage detection and execution.

Submodules:
    core/       - Spread detection, execution, pod management
    strategies/ - Trading strategy implementations
    monitoring/ - Live dashboard and Telegram alerts

Re-exports for backwards compatibility with src.arbitrage:
"""

from .arbiter import PhantomArbiter, ArbiterConfig
from .core.spread_detector import SpreadDetector
from .core.executor import ArbitrageExecutor
from .monitoring.live_dashboard import LiveDashboard

__all__ = [
    "PhantomArbiter",
    "ArbiterConfig",
    "SpreadDetector",
    "ArbitrageExecutor",
    "LiveDashboard",
]
