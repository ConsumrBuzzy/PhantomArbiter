"""
Instruction Factory
===================
Pure, deterministic Solana instruction building.

The "Architect" of the execution pipeline.
100% testable without RPC or wallet connections.

Responsibilities:
- Build Jupiter swap instructions
- Build Drift perp order instructions  
- Build Jito tip instructions
- Handle AddressLookupTables
- Set ComputeBudget limits
"""

from __future__ import annotations

import base64
from typing import List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from solders.instruction import Instruction, AccountMeta
from solders.pubkey import Pubkey
from solders.system_program import transfer, TransferParams
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price

from src.shared.system.logging import Logger


# ═══════════════════════════════════════════════════════════════════════════════
# TRADE INTENT SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class TradeDirection(Enum):
    """Direction of a trade leg."""
    BUY = "BUY"
    SELL = "SELL"
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(frozen=True)
class SpotTradeIntent:
    """Intent for a spot swap on Jupiter/Raydium."""
    
    input_mint: str
    output_mint: str
    amount_atomic: int  # Raw amount in smallest units
    slippage_bps: int = 50  # 0.5% default
    direction: TradeDirection = TradeDirection.BUY
    
    @property
    def amount_human(self) -> float:
        """Convert to human-readable amount (assumes 6 or 9 decimals)."""
        # SOL = 9 decimals, USDC = 6 decimals
        if "So111" in self.input_mint:
            return self.amount_atomic / 1_000_000_000
        return self.amount_atomic / 1_000_000


@dataclass(frozen=True)
class PerpTradeIntent:
    """Intent for a perp order on Drift."""
    
    market: str  # e.g., "SOL-PERP"
    size: float  # Base units (e.g., 1.5 SOL)
    direction: TradeDirection = TradeDirection.SHORT
    reduce_only: bool = False
    limit_price: Optional[float] = None  # None = market order
    
    @property
    def market_index(self) -> int:
        """Get Drift market index for the market."""
        MARKET_INDICES = {
            "SOL-PERP": 0,
            "BTC-PERP": 1,
            "ETH-PERP": 2,
        }
        return MARKET_INDICES.get(self.market, 0)


@dataclass
class BundleIntent:
    """Complete intent for an atomic bundle."""
    
    spot_leg: Optional[SpotTradeIntent] = None
    perp_leg: Optional[PerpTradeIntent] = None
    tip_lamports: int = 50_000
    compute_units: int = 400_000
    priority_fee_micro_lamports: int = 1000
    
    def __post_init__(self):
        if not self.spot_leg and not self.perp_leg:
            raise ValueError("Bundle must have at least one leg")


# ═══════════════════════════════════════════════════════════════════════════════
# INSTRUCTION FACTORY
# ═══════════════════════════════════════════════════════════════════════════════

class InstructionFactory:
    """
    Pure instruction builder for atomic trade bundles.
    
    This class contains NO side effects - it only constructs
    Solana instructions from trade intents.
    
    Usage:
        factory = InstructionFactory(payer_pubkey)
        instructions = await factory.build_bundle(bundle_intent)
    """
    
    # Standard mints
    SOL_MINT = "So11111111111111111111111111111111111111112"
    USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    
    # Jito tip accounts (8 total, round-robin)
    JITO_TIP_ACCOUNTS = [
        "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
        "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
        "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
        "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
        "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
        "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
        "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
        "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
    ]
    
    def __init__(self, payer_pubkey: str):
        """
        Initialize factory with payer public key.
        
        Args:
            payer_pubkey: The wallet that will pay for and sign transactions
        """
        self.payer = Pubkey.from_string(payer_pubkey)
        self._tip_account_index = 0
        
    def build_compute_budget_instructions(
        self,
        units: int = 400_000,
        priority_fee: int = 1000,
    ) -> List[Instruction]:
        """
        Build compute budget instructions.
        
        Args:
            units: Compute unit limit
            priority_fee: Priority fee in micro-lamports per CU
            
        Returns:
            List of [SetComputeUnitLimit, SetComputeUnitPrice] instructions
        """
        return [
            set_compute_unit_limit(units),
            set_compute_unit_price(priority_fee),
        ]
    
    def build_tip_instruction(
        self,
        lamports: int,
        tip_account: Optional[str] = None,
    ) -> Instruction:
        """
        Build Jito tip instruction.
        
        Args:
            lamports: Amount to tip in lamports
            tip_account: Specific tip account or None for round-robin
            
        Returns:
            SOL transfer instruction to tip account
        """
        if tip_account is None:
            tip_account = self._get_next_tip_account()
        
        return transfer(
            TransferParams(
                from_pubkey=self.payer,
                to_pubkey=Pubkey.from_string(tip_account),
                lamports=lamports,
            )
        )
    
    def _get_next_tip_account(self) -> str:
        """Round-robin through Jito tip accounts."""
        account = self.JITO_TIP_ACCOUNTS[self._tip_account_index]
        self._tip_account_index = (self._tip_account_index + 1) % len(self.JITO_TIP_ACCOUNTS)
        return account
    
    async def build_spot_instructions(
        self,
        intent: SpotTradeIntent,
        swapper: Any,  # JupiterSwapper
    ) -> List[Instruction]:
        """
        Build Jupiter swap instructions for spot leg.
        
        Args:
            intent: The spot trade intent
            swapper: JupiterSwapper instance for quote fetching
            
        Returns:
            List of swap instructions
        """
        # Get quote from Jupiter
        quote = await swapper.get_quote(
            intent.input_mint,
            intent.output_mint,
            intent.amount_atomic,
            slippage=intent.slippage_bps,
        )
        
        if not quote:
            raise ValueError(f"Jupiter quote failed for {intent.input_mint} -> {intent.output_mint}")
        
        # Get swap instructions
        instructions = await swapper.get_swap_instructions(quote)
        
        Logger.debug(
            f"[InstructionFactory] Built spot leg: "
            f"{intent.direction.value} {intent.amount_atomic} atomic units"
        )
        
        return instructions
    
    def build_perp_instructions(
        self,
        intent: PerpTradeIntent,
        user_pubkey: str,
    ) -> List[Instruction]:
        """
        Build Drift perp order instructions.
        
        Args:
            intent: The perp trade intent
            user_pubkey: User's Drift sub-account
            
        Returns:
            List of Drift order instructions
        """
        from src.delta_neutral.drift_order_builder import DriftOrderBuilder
        
        builder = DriftOrderBuilder(user_pubkey)
        
        if intent.direction == TradeDirection.SHORT:
            instructions = builder.build_short_order(
                intent.market,
                intent.size,
                reduce_only=intent.reduce_only,
            )
        else:  # LONG
            instructions = builder.build_long_order(
                intent.market,
                intent.size,
                reduce_only=intent.reduce_only,
            )
        
        Logger.debug(
            f"[InstructionFactory] Built perp leg: "
            f"{intent.direction.value} {intent.size} {intent.market}"
        )
        
        return instructions
    
    async def build_bundle_instructions(
        self,
        intent: BundleIntent,
        swapper: Any = None,
    ) -> List[Instruction]:
        """
        Build all instructions for an atomic bundle.
        
        Order:
        1. ComputeBudget (limit + price)
        2. Spot swap (if present)
        3. Perp order (if present)
        4. Jito tip
        
        Args:
            intent: Complete bundle intent
            swapper: JupiterSwapper for spot quotes
            
        Returns:
            Ordered list of all instructions
        """
        instructions = []
        
        # 1. Compute budget
        instructions.extend(
            self.build_compute_budget_instructions(
                units=intent.compute_units,
                priority_fee=intent.priority_fee_micro_lamports,
            )
        )
        
        # 2. Spot leg
        if intent.spot_leg and swapper:
            spot_ixs = await self.build_spot_instructions(intent.spot_leg, swapper)
            instructions.extend(spot_ixs)
        
        # 3. Perp leg
        if intent.perp_leg:
            perp_ixs = self.build_perp_instructions(
                intent.perp_leg,
                str(self.payer),
            )
            instructions.extend(perp_ixs)
        
        # 4. Jito tip
        instructions.append(self.build_tip_instruction(intent.tip_lamports))
        
        Logger.info(f"[InstructionFactory] Bundle built: {len(instructions)} instructions")
        
        return instructions
    
    def validate_instructions(self, instructions: List[Instruction]) -> Tuple[bool, List[str]]:
        """
        Validate instruction list for common errors.
        
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        if not instructions:
            errors.append("No instructions in bundle")
            return False, errors
        
        # Check for reasonable instruction count
        if len(instructions) > 20:
            errors.append(f"Too many instructions: {len(instructions)} (max 20)")
        
        # Verify all instructions have program IDs
        for i, ix in enumerate(instructions):
            if not ix.program_id:
                errors.append(f"Instruction {i} missing program_id")
        
        return len(errors) == 0, errors


# ═══════════════════════════════════════════════════════════════════════════════
# FACTORY SINGLETON
# ═══════════════════════════════════════════════════════════════════════════════

_factory_instance: Optional[InstructionFactory] = None


def get_instruction_factory(payer_pubkey: str) -> InstructionFactory:
    """Get or create InstructionFactory."""
    global _factory_instance
    
    if _factory_instance is None or str(_factory_instance.payer) != payer_pubkey:
        _factory_instance = InstructionFactory(payer_pubkey)
    
    return _factory_instance
