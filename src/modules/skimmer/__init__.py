"""
Private Investigator (Skimmer) Module
======================================
Identifies and reclaims rent from zombie Solana accounts.

ADR-005: Tier 2 (Asynchronous Side-Step) Architecture
- Discovery: Scan accounts and write to zombie_targets DB
- Execution: Main bot executes closures during low-gas windows

Safety Guardrails:
- MAX_ACCOUNTS_PER_RUN: Prevents unbounded scanning
- RECLAMATION_KEYPAIR: Separate keypair from trading wallet
- LP Detection: Prevents closing active liquidity positions
"""

from src.modules.skimmer.core import SkimmerCore

__all__ = ['SkimmerCore']
