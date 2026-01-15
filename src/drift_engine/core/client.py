from typing import Optional, List, Any
from solders.instruction import Instruction
from solders.pubkey import Pubkey

from src.drift_engine.core.builder import DriftOrderBuilder
from src.drift_engine.core.types import DriftPosition


class DriftClient:
    """
    High-level client for Drift Protocol integration.
    Wraps DriftOrderBuilder to provide an async interface for critical trading operations.
    """
    
    def __init__(self, network: str = "mainnet"):
        self.network = network
        self._builder: Optional[DriftOrderBuilder] = None
        self._wallet: Optional[Any] = None
    
    def set_wallet(self, wallet: Any) -> None:
        """Set wallet and initialize builder."""
        self._wallet = wallet
        if hasattr(wallet, 'get_public_key'):
            pk = wallet.get_public_key()
            # Ensure Pubkey object
            if isinstance(pk, str):
                pk = Pubkey.from_string(pk)
            self._builder = DriftOrderBuilder(pk)
    
    async def get_short_instructions(
        self,
        market: str,
        size: float,
    ) -> List[Instruction]:
        """Get instructions to open/increase short position."""
        if not self._builder:
            raise RuntimeError("DriftClient: wallet not set")
        return self._builder.build_short_order(market, size)
    
    async def get_long_instructions(
        self,
        market: str,
        size: float,
    ) -> List[Instruction]:
        """Get instructions to open/increase long position."""
        if not self._builder:
            raise RuntimeError("DriftClient: wallet not set")
        return self._builder.build_long_order(market, size)
    
    async def get_close_instructions(
        self,
        market: str,
        current_size: float,
    ) -> List[Instruction]:
        """Get instructions to close a position."""
        if not self._builder:
            raise RuntimeError("DriftClient: wallet not set")
        return self._builder.build_close_position(market, current_size)
    
    async def get_position(self, market: str) -> Optional[DriftPosition]:
        """Get current position for market."""
        if not self._builder:
            return None
        return await self._builder.get_position(market)

    def get_user_equity(self) -> float:
        """Get total account equity (USDC)."""
        if not self._builder:
            return 0.0
        return self._builder.get_user_equity()

    def get_active_capital(self) -> float:
        """Get capital currently deployed in active positions."""
        if not self._builder:
            return 0.0
        return self._builder.get_active_capital()

    def get_all_positions(self) -> List[DriftPosition]:
        """Get all perp positions for Combat Zone table."""
        if not self._builder:
            return []
        return self._builder.get_all_positions()

# Legacy Alias
DriftAdapter = DriftClient
