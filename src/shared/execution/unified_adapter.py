"""
Unified Engine Adapter
=======================
Provides a unified interface for the ArbitrageExecutor to use the 
new multi-DEX atomic execution engine (Meteora + Orca + Jito).

This adapter replaces the sequential Jupiter execution with
true atomic multi-DEX swaps in a single transaction.

Usage:
    from src.shared.execution.unified_adapter import UnifiedEngineAdapter
    
    adapter = UnifiedEngineAdapter()
    result = await adapter.execute_atomic_arb(
        buy_dex="meteora", buy_pool="BGm1...",
        sell_dex="orca", sell_pool="7qbR...",
        input_mint="USDC_MINT", output_mint="SOL_MINT",
        amount_usd=100
    )
"""

import os
import time
from typing import Dict, Optional, Any
from dataclasses import dataclass

from src.shared.execution.execution_bridge import ExecutionBridge, SwapLeg, ExecutionResult
from src.shared.execution.schemas import calculate_arb_strategy
from src.shared.system.logging import Logger


@dataclass
class AtomicArbResult:
    """Result of an atomic arbitrage execution."""
    success: bool
    signature: Optional[str] = None
    input_amount: float = 0
    output_amount: float = 0
    net_profit_usd: float = 0
    jito_tip_lamports: int = 0
    execution_time_ms: int = 0
    error: Optional[str] = None
    legs: list = None
    
    @property
    def net_profit_pct(self) -> float:
        if self.input_amount > 0:
            return (self.output_amount - self.input_amount) / self.input_amount * 100
        return 0.0


class UnifiedEngineAdapter:
    """
    Adapter for the unified TypeScript execution engine.
    
    Features:
    - True atomic multi-DEX execution (single transaction)
    - Automatic Jito tip calculation
    - Simulation before execution
    - Helius Sender for fast TX submission
    """
    
    def __init__(self):
        self._bridge = ExecutionBridge()
        self._private_key = os.getenv("PHANTOM_PRIVATE_KEY")
        
        # Stats
        self.total_arbs = 0
        self.successful_arbs = 0
        self.total_profit = 0.0
    
    def is_available(self) -> bool:
        """Check if the unified engine is available."""
        return self._bridge.is_available()
    
    async def pre_check_arbitrage(
        self,
        mint_in: str,
        mint_out: str,
        amount: int,
        min_profit_bps: int = 10
    ) -> tuple[bool, int]:
        """
        V83.0: Gatekeeper Quote.
        
        Uses Jupiter's Free API (60 RPM) to verify that the global routing
        confirms our local pool discovery before firing the atomic bundle.
        
        Args:
            mint_in: Input token mint
            mint_out: Output token mint
            amount: Amount in smallest units
            min_profit_bps: Minimum profit in basis points (default 10 = 0.1%)
            
        Returns:
            (is_profitable, out_amount) tuple
        """
        import os
        try:
            import httpx
        except ImportError:
            Logger.warning("[PRE-CHECK] httpx not installed, skipping pre-check")
            return True, 0
        
        api_key = os.getenv("JUPITER_API_KEY", "")
        url = f"https://api.jup.ag/swap/v1/quote?inputMint={mint_in}&outputMint={mint_out}&amount={amount}"
        
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                headers = {}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                
                response = await client.get(url, headers=headers)
                
                if response.status_code == 200:
                    quote = response.json()
                    out_amount = int(quote.get('outAmount', 0))
                    
                    # Calculate profit in basis points
                    if amount > 0:
                        profit_bps = ((out_amount - amount) / amount) * 10000
                        
                        if profit_bps >= min_profit_bps:
                            Logger.debug(f"[PRE-CHECK] ✅ Profit {profit_bps:.1f} bps >= {min_profit_bps} bps")
                            return True, out_amount
                        else:
                            Logger.debug(f"[PRE-CHECK] ❌ Profit {profit_bps:.1f} bps < {min_profit_bps} bps")
                            return False, out_amount
                else:
                    Logger.warning(f"[PRE-CHECK] Jupiter API returned {response.status_code}")
                    
        except Exception as e:
            Logger.debug(f"[PRE-CHECK] Error: {e}")
        
        # Default: allow execution (fail open for speed)
        return True, 0
    
    async def get_priority_fee(self, tier: str = "h") -> int:
        """
        Get dynamic priority fee from Raydium.
        
        Args:
            tier: "m" (Medium), "h" (High), "vh" (Very High)
            
        Returns:
            Priority fee in microLamports
        """
        from src.shared.execution.priority_fee import PriorityFeeClient
        return await PriorityFeeClient.get_fee_estimate(tier)
    
    async def execute_atomic_arb(
        self,
        buy_dex: str,
        buy_pool: str,
        sell_dex: str,
        sell_pool: str,
        input_mint: str,
        output_mint: str,
        amount_in: int,
        slippage_bps: int = 100,
        simulate_first: bool = True,
        jito_tip_lamports: Optional[int] = None,
        pre_check: bool = False,
        use_dynamic_fee: bool = True,
        priority_tier: str = "h",
    ) -> AtomicArbResult:
        """
        Execute an atomic arbitrage trade.
        
        BOTH legs execute in a SINGLE transaction:
        - If either leg fails (slippage, liquidity), the ENTIRE tx reverts
        - No risk of stuck tokens
        - Jito tip included for MEV protection
        
        Args:
            buy_dex: DEX for buy leg ("meteora" or "orca")
            buy_pool: Pool address for buy leg
            sell_dex: DEX for sell leg
            sell_pool: Pool address for sell leg
            input_mint: Input token mint (buy with this)
            output_mint: Intermediate token mint (buy this, then sell)
            amount_in: Amount in smallest units (lamports for SOL, etc.)
            slippage_bps: Slippage tolerance in basis points
            simulate_first: Run simulation before live execution
            jito_tip_lamports: Jito tip (auto-calculated if None)
            
        Returns:
            AtomicArbResult with execution details
        """
        start_time = time.time()
        
        if not self._private_key:
            return AtomicArbResult(
                success=False,
                error="PHANTOM_PRIVATE_KEY not configured",
                execution_time_ms=int((time.time() - start_time) * 1000)
            )
        
        if not self.is_available():
            return AtomicArbResult(
                success=False,
                error="Unified engine not available. Run: cd bridges && npm run build",
                execution_time_ms=int((time.time() - start_time) * 1000)
            )
        
        try:
            Logger.info(f"[UNIFIED] ⚡ Executing atomic arb: {buy_dex} → {sell_dex}")
            
            # Build legs
            legs = [
                SwapLeg(
                    dex=buy_dex,
                    pool=buy_pool,
                    input_mint=input_mint,
                    output_mint=output_mint,
                    amount=amount_in,
                    slippage_bps=slippage_bps,
                ),
                SwapLeg(
                    dex=sell_dex,
                    pool=sell_pool,
                    input_mint=output_mint,
                    output_mint=input_mint,
                    amount=0,  # Will use output from leg 1
                    slippage_bps=slippage_bps,
                ),
            ]
            
            # Calculate Jito tip if not provided
            if jito_tip_lamports is None:
                # Assume 0.5% profit for tip calculation
                estimated_profit = int(amount_in * 0.005)
                strategy = calculate_arb_strategy(amount_in, amount_in + estimated_profit)
                jito_tip_lamports = strategy["jito_tip_lamports"]
            
            # Simulate first (seatbelt)
            if simulate_first:
                Logger.info("[UNIFIED] 🧪 Running simulation...")
                sim_result = self._bridge.simulate(legs, self._private_key)
                
                if not sim_result.simulation_success:
                    Logger.warning(f"[UNIFIED] ❌ Simulation failed: {sim_result.simulation_error}")
                    return AtomicArbResult(
                        success=False,
                        error=f"Simulation failed: {sim_result.simulation_error}",
                        execution_time_ms=int((time.time() - start_time) * 1000)
                    )
                
                Logger.info(f"[UNIFIED] ✅ Simulation passed (CU: {sim_result.compute_units_used})")
            
            # Execute
            Logger.info(f"[UNIFIED] 🚀 Executing with {jito_tip_lamports} lamport Jito tip...")
            result = self._bridge.execute_swap(
                legs=legs,
                private_key=self._private_key,
                jito_tip_lamports=jito_tip_lamports,
            )
            
            execution_time = int((time.time() - start_time) * 1000)
            
            if result.success:
                self.total_arbs += 1
                self.successful_arbs += 1
                
                # Calculate profit from legs
                if result.legs and len(result.legs) >= 2:
                    input_amount = result.legs[0].input_amount
                    output_amount = result.legs[-1].output_amount
                    net_profit = (output_amount - input_amount) / 1_000_000  # Assume 6 decimals
                    self.total_profit += net_profit
                else:
                    input_amount = amount_in
                    output_amount = 0
                    net_profit = 0
                
                Logger.info(f"[UNIFIED] ✅ Arb executed: {result.signature}")
                
                return AtomicArbResult(
                    success=True,
                    signature=result.signature,
                    input_amount=input_amount / 1_000_000,
                    output_amount=output_amount / 1_000_000,
                    net_profit_usd=net_profit,
                    jito_tip_lamports=jito_tip_lamports,
                    execution_time_ms=execution_time,
                    legs=[leg.__dict__ for leg in result.legs] if result.legs else [],
                )
            else:
                self.total_arbs += 1
                Logger.error(f"[UNIFIED] ❌ Arb failed: {result.error}")
                
                return AtomicArbResult(
                    success=False,
                    error=result.error,
                    execution_time_ms=execution_time,
                )
                
        except Exception as e:
            Logger.error(f"[UNIFIED] Exception: {e}")
            return AtomicArbResult(
                success=False,
                error=str(e),
                execution_time_ms=int((time.time() - start_time) * 1000)
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get adapter statistics."""
        return {
            "total_arbs": self.total_arbs,
            "successful_arbs": self.successful_arbs,
            "win_rate": self.successful_arbs / self.total_arbs if self.total_arbs > 0 else 0,
            "total_profit": self.total_profit,
            "engine_available": self.is_available(),
        }


# ═══════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import asyncio
    
    async def test():
        print("=" * 60)
        print("Unified Engine Adapter Test")
        print("=" * 60)
        
        adapter = UnifiedEngineAdapter()
        
        print(f"\nEngine available: {adapter.is_available()}")
        print(f"Stats: {adapter.get_stats()}")
        
        print("\n✅ Adapter initialized successfully")
        print("   Ready for integration with ArbitrageExecutor")
    
    asyncio.run(test())
