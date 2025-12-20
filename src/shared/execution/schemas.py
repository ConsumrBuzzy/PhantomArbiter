"""
Execution Schemas
==================
Pydantic models for Python/TypeScript communication.

These schemas define the contract between the Python "Brain" 
and the TypeScript "Driver" for atomic arbitrage execution.
"""

from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from enum import Enum


class Market(str, Enum):
    """Supported DEX markets."""
    METEORA = "meteora"
    ORCA = "orca"
    RAYDIUM = "raydium"
    JUPITER = "jupiter"


class SwapLeg(BaseModel):
    """
    One leg of a multi-DEX atomic swap.
    
    Example:
        leg = SwapLeg(
            market="meteora",
            pool_id="BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y",
            input_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
            output_mint="So11111111111111111111111111111111111111112",    # SOL
            amount_in=1000000,  # 1 USDC
            slippage_bps=50
        )
    """
    market: Literal["meteora", "orca", "raydium", "jupiter"]
    pool_id: str = Field(..., description="Pool public key address")
    input_mint: str = Field(..., description="Input token mint address")
    output_mint: str = Field(..., description="Output token mint address")
    amount_in: int = Field(..., description="Amount in smallest units (lamports, etc.)")
    slippage_bps: int = Field(default=50, description="Slippage tolerance in basis points (50 = 0.5%)")

    def to_engine_dict(self) -> dict:
        """Convert to format expected by TypeScript engine."""
        return {
            "dex": self.market,
            "pool": self.pool_id,
            "inputMint": self.input_mint,
            "outputMint": self.output_mint,
            "amount": self.amount_in,
            "slippageBps": self.slippage_bps,
        }


class ArbTask(BaseModel):
    """
    Complete arbitrage task for the execution engine.
    
    Example:
        task = ArbTask(
            task_id="arb-001",
            legs=[buy_leg, sell_leg],
            jito_tip_lamports=10000,
            compute_unit_limit=600000,
            priority_fee_micro_lamports=50000
        )
    """
    task_id: str = Field(..., description="Unique task identifier")
    legs: List[SwapLeg] = Field(..., min_length=1, description="Swap legs to execute atomically")
    
    # Jito Settings
    jito_tip_lamports: int = Field(
        default=10000, 
        ge=0,
        description="Tip for Jito bundle (0 = no tip, ~10000 = $0.002)"
    )
    
    # Compute Settings
    compute_unit_limit: int = Field(
        default=400000,
        description="Compute unit limit per leg"
    )
    priority_fee_micro_lamports: int = Field(
        default=50000,
        description="Priority fee in microlamports per compute unit"
    )

    def to_engine_command(self, private_key: str, simulate_only: bool = False) -> dict:
        """Convert to engine command format."""
        return {
            "command": "simulate" if simulate_only else "swap",
            "legs": [leg.to_engine_dict() for leg in self.legs],
            "privateKey": private_key,
            "priorityFee": self.priority_fee_micro_lamports,
            "jitoTipLamports": self.jito_tip_lamports,
            "simulateOnly": simulate_only,
        }


class LegResult(BaseModel):
    """Result from one swap leg execution."""
    dex: str
    input_mint: str
    output_mint: str
    input_amount: int
    output_amount: int
    price_impact: float = 0.0


class ExecutionResult(BaseModel):
    """
    Result from execution engine.
    
    Check `success` first, then `simulation_success` if simulating.
    """
    success: bool
    command: str
    signature: Optional[str] = None
    legs: List[LegResult] = Field(default_factory=list)
    error: Optional[str] = None
    simulation_success: Optional[bool] = None
    simulation_error: Optional[str] = None
    compute_units_used: Optional[int] = None
    timestamp: int = 0


# ═══════════════════════════════════════════════════════════════════
# PROFIT & TIP CALCULATORS
# ═══════════════════════════════════════════════════════════════════

def calculate_dynamic_tip(expected_profit_lamports: int, min_tip: int = 10000, tip_ratio: float = 0.1) -> int:
    """
    Calculate optimal Jito tip based on expected profit.
    
    Strategy: Tip 10% of profit, but at least min_tip to ensure inclusion.
    
    Args:
        expected_profit_lamports: Expected profit in lamports
        min_tip: Minimum tip (default: 10000 = ~$0.002)
        tip_ratio: Ratio of profit to tip (default: 0.1 = 10%)
        
    Returns:
        Tip amount in lamports
    """
    profit_based_tip = int(expected_profit_lamports * tip_ratio)
    return max(min_tip, profit_based_tip)


def calculate_arb_strategy(
    amount_in_lamports: int,
    expected_out_lamports: int,
    gas_cost_lamports: int = 5000,
    tip_ratio: float = 0.20,
    min_tip_lamports: int = 10000,
) -> dict:
    """
    Calculate complete arbitrage strategy with profit waterfall.
    
    Formula: Net Profit = (Gross Revenue - Swap Fees) - (Gas + Jito Tip)
    
    Args:
        amount_in_lamports: Amount put into first leg (in lamports)
        expected_out_lamports: Expected return after all legs (in lamports)
        gas_cost_lamports: Estimated gas cost (default: 5000 = ~$0.001)
        tip_ratio: Percentage of gross profit for Jito tip (default: 20%)
        min_tip_lamports: Minimum tip to ensure inclusion (default: 10000)
        
    Returns:
        dict with:
            - is_viable: True if net profit > 0
            - gross_profit_lamports: Raw profit before costs
            - jito_tip_lamports: Calculated tip amount
            - net_profit_lamports: Final profit after all costs
            - profit_bps: Net profit as basis points of input
    
    Example:
        result = calculate_arb_strategy(
            amount_in_lamports=100_000_000,    # 0.1 SOL
            expected_out_lamports=100_500_000  # 0.1005 SOL
        )
        if result['is_viable']:
            execute_arb(jito_tip=result['jito_tip_lamports'])
    """
    # Gross profit
    gross_profit = expected_out_lamports - amount_in_lamports
    
    # Calculate Jito tip (percentage of gross, with floor)
    tip_from_profit = int(gross_profit * tip_ratio)
    jito_tip = max(min_tip_lamports, tip_from_profit) if gross_profit > 0 else 0
    
    # Net profit after all costs
    total_costs = gas_cost_lamports + jito_tip
    net_profit = gross_profit - total_costs
    
    # Profit as basis points of input (for comparison)
    profit_bps = int((net_profit / amount_in_lamports) * 10000) if amount_in_lamports > 0 else 0
    
    return {
        "is_viable": net_profit > 0,
        "gross_profit_lamports": gross_profit,
        "jito_tip_lamports": jito_tip,
        "gas_cost_lamports": gas_cost_lamports,
        "net_profit_lamports": net_profit,
        "profit_bps": profit_bps,
    }


# ═══════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Example usage
    print("=" * 60)
    print("Execution Schemas Test")
    print("=" * 60)
    
    # Create swap legs
    buy_leg = SwapLeg(
        market="meteora",
        pool_id="BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y",
        input_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        output_mint="So11111111111111111111111111111111111111112",
        amount_in=1000000,
        slippage_bps=50
    )
    
    sell_leg = SwapLeg(
        market="meteora",
        pool_id="CgqwPLSFfht89pF5RSKGUUMFj5zRxoUt4861w2SkXaqY",
        input_mint="So11111111111111111111111111111111111111112",
        output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        amount_in=7800,  # ~7800 lamports of SOL
        slippage_bps=50
    )
    
    # Create arb task
    task = ArbTask(
        task_id="test-arb-001",
        legs=[buy_leg, sell_leg],
        jito_tip_lamports=10000,
        compute_unit_limit=600000,
        priority_fee_micro_lamports=50000
    )
    
    print("\n✅ ArbTask created:")
    print(f"   Task ID: {task.task_id}")
    print(f"   Legs: {len(task.legs)}")
    print(f"   Jito Tip: {task.jito_tip_lamports} lamports")
    
    # Test dynamic tip
    profit = 500000  # 0.5 SOL profit
    tip = calculate_dynamic_tip(profit)
    print(f"\n💡 Dynamic tip for {profit} lamports profit: {tip} lamports")
    
    print("\n" + "=" * 60)
