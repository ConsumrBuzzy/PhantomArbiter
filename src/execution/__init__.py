"""
Execution Pipeline
==================
SRP-compliant trade execution layer.

Components:
- InstructionFactory: Pure instruction building (The Architect)
- BundleSubmitter: Jito submission (The Pilot)
- RecoveryManager: Partial fill handling (The Medic)
"""

from src.execution.instruction_factory import (
    InstructionFactory,
    SpotTradeIntent,
    PerpTradeIntent,
    BundleIntent,
    TradeDirection,
    get_instruction_factory,
)

from src.execution.bundle_submitter import (
    BundleSubmitter,
    SubmitterConfig,
    SubmissionResult,
    BundleStatus,
)

from src.execution.recovery_manager import (
    RecoveryManager,
    PositionState,
    PartialFillAnalysis,
    PartialFillType,
    RecoveryPath,
)


__all__ = [
    # Factory
    "InstructionFactory",
    "SpotTradeIntent",
    "PerpTradeIntent",
    "BundleIntent",
    "TradeDirection",
    "get_instruction_factory",
    # Submitter
    "BundleSubmitter",
    "SubmitterConfig",
    "SubmissionResult",
    "BundleStatus",
    # Recovery
    "RecoveryManager",
    "PositionState",
    "PartialFillAnalysis",
    "PartialFillType",
    "RecoveryPath",
]
