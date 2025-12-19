# Arbitrage Engine Package
"""
src/arbitrage - Core arbitrage detection and execution system.

Submodules:
    feeds/      - Multi-DEX price sources (Jupiter, Raydium, Orca)
    strategies/ - Arbitrage strategy implementations
    core/       - Spread detection, risk management, orchestration
    monitoring/ - Real-time dashboard and Telegram alerts
"""

from .core.orchestrator import ArbitrageOrchestrator
from .core.spread_detector import SpreadDetector
from .monitoring.live_dashboard import LiveDashboard

__all__ = [
    "ArbitrageOrchestrator",
    "SpreadDetector", 
    "LiveDashboard",
]
