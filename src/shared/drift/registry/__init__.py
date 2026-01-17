"""
Trading Engine Registry
======================

Registry and orchestration components for managing multiple trading engines.
"""

from .trading_engine_registry import TradingEngineRegistry
from .multi_engine_orchestrator import MultiEngineOrchestrator, OrchestrationResult
from .signal_conflict_resolver import SignalConflictResolver, ConflictResolution

__all__ = [
    'TradingEngineRegistry',
    'MultiEngineOrchestrator',
    'OrchestrationResult',
    'SignalConflictResolver',
    'ConflictResolution'
]