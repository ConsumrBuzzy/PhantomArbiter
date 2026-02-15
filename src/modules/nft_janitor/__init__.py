"""
NFT Janitor Module
==================
Legacy NFT rent reclamation system for Solana.

This module discovers, purchases, and burns Legacy (non-compressed) NFTs
to reclaim their rent deposits for profit.

Components:
- scanner.py: Tensor API integration and NFT discovery
- buyer.py: NFT purchase execution
- burner.py: Metadata account burning and rent reclamation
- config.py: Configuration and thresholds
- cli.py: Command-line interface

Architecture Pattern:
Follows the Skimmer module design with singleton core, repository-based
database access, and status workflow tracking.
"""

from src.modules.nft_janitor.config import JanitorConfig

__all__ = [
    'JanitorConfig',
]
