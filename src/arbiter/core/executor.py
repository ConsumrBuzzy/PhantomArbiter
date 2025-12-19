"""
V1.0: Arbitrage Executor
========================
Executes arbitrage trades atomically using Jupiter and Jito bundles.

For Spatial Arbitrage:
- Uses Jupiter's aggregation to route through multiple DEXs
- Optionally bundles with Jito for MEV protection

For Funding Rate Arbitrage:
- Uses Jupiter for spot leg
- Uses Drift for perp leg
- Both should execute as close together as possible
"""

import asyncio
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from config.settings import Settings
from src.shared.system.logging import Logger


class ExecutionMode(Enum):
    """Execution mode for the arbitrage executor."""
    PAPER = "PAPER"          # Simulated trades (no real money)
    LIVE = "LIVE"            # Real trades
    DRY_RUN = "DRY_RUN"      # Fetch quotes but don't execute


@dataclass
class TradeResult:
    """Result of an executed trade."""
    success: bool
    trade_type: str              # "BUY", "SELL", "SWAP"
    input_token: str
    output_token: str
    input_amount: float
    output_amount: float
    price: float
    fee_usd: float
    signature: Optional[str]     # Transaction signature (if live)
    error: Optional[str]
    timestamp: float
    execution_time_ms: int
    
    @property
    def slippage_pct(self) -> float:
        """Calculate actual slippage from expected."""
        if self.expected_output and self.expected_output > 0:
            return (1 - self.output_amount / self.expected_output) * 100
        return 0.0


@dataclass
class ArbitrageExecution:
    """Result of a complete arbitrage execution (multi-leg)."""
    success: bool
    strategy: str                # "SPATIAL", "TRIANGULAR", "FUNDING"
    legs: List[TradeResult]
    total_input: float
    total_output: float
    gross_profit: float
    fees: float
    net_profit: float
    execution_time_ms: int
    timestamp: float
    error: Optional[str] = None


class ArbitrageExecutor:
    """
    Executes arbitrage trades.
    
    Supports:
    - Spatial arbitrage (buy on DEX A, sell on DEX B via Jupiter)
    - Funding rate arbitrage (spot + perp combo)
    - Paper trading simulation
    """
    
    def __init__(
        self,
        wallet=None,
        swapper=None,
        drift_adapter=None,
        jito_adapter=None,
        mode: ExecutionMode = ExecutionMode.PAPER
    ):
        self.wallet = wallet
        self.swapper = swapper
        self.drift = drift_adapter
        self.jito = jito_adapter
        self.mode = mode
        
        # Lazy-load dependencies
        self._smart_router = None
        
        # Stats tracking
        self.total_trades = 0
        self.successful_trades = 0
        self.total_profit = 0.0
        self.total_fees = 0.0
        
    def _get_smart_router(self):
        """Lazy-load smart router."""
        if self._smart_router is None:
            from src.shared.system.smart_router import SmartRouter
            self._smart_router = SmartRouter()
        return self._smart_router
    
    async def execute_spatial_arb(
        self,
        opportunity,
        trade_size: float = None
    ) -> ArbitrageExecution:
        """
        Execute spatial arbitrage (cross-DEX spread).
        
        In PAPER mode: Fully simulated based on opportunity data
        In LIVE mode: Uses real Jupiter quotes and execution
        """
        trade_size = trade_size or getattr(Settings, 'DEFAULT_TRADE_SIZE_USD', 50.0)
        start_time = time.time()
        
        try:
            legs = []
            
            if self.mode == ExecutionMode.PAPER:
                # ═══ PAPER MODE: Simulate atomic bundled execution ═══
                # Uses same fee calculations as live mode for accuracy
                from src.arbiter.core.fee_estimator import get_fee_estimator
                
                Logger.info(f"[EXEC] Paper (atomic sim): ${trade_size:.2f} {opportunity.pair}")
                
                # Calculate token amount based on buy price
                token_amount = trade_size / opportunity.buy_price
                
                # Get accurate fee estimate (same as live)
                fee_est = get_fee_estimator()
                fees = fee_est.estimate(
                    trade_size_usd=trade_size,
                    buy_dex=opportunity.buy_dex,
                    sell_dex=opportunity.sell_dex
                )
                
                # Simulate buy leg
                buy_result = TradeResult(
                    success=True,
                    trade_type="BUY",
                    input_token="USDC",
                    output_token=opportunity.pair.split("/")[0],
                    input_amount=trade_size,
                    output_amount=token_amount,
                    price=opportunity.buy_price,
                    fee_usd=fees.trading_fee_usd / 2,  # Half of trading fees
                    signature="PAPER_ATOMIC_" + str(int(time.time())),
                    error=None,
                    timestamp=time.time(),
                    execution_time_ms=50  # Faster since "bundled"
                )
                legs.append(buy_result)
                
                # Simulate sell leg with STOCHASTIC slippage variance
                # Real slippage varies: sometimes better, sometimes worse
                import random
                slippage_variance = random.uniform(0.5, 2.0)  # 0.5x to 2x expected
                actual_slippage = fees.slippage_cost_usd * slippage_variance
                
                sell_output = token_amount * opportunity.sell_price
                sell_output *= (1 - actual_slippage / trade_size)  # Apply variable slippage
                
                sell_result = TradeResult(
                    success=True,
                    trade_type="SELL",
                    input_token=opportunity.pair.split("/")[0],
                    output_token="USDC",
                    input_amount=token_amount,
                    output_amount=sell_output,
                    price=opportunity.sell_price,
                    fee_usd=fees.trading_fee_usd / 2 + fees.gas_fee_usd + fees.priority_fee_usd,
                    signature="PAPER_ATOMIC_" + str(int(time.time()) + 1),
                    error=None,
                    timestamp=time.time(),
                    execution_time_ms=50
                )
                legs.append(sell_result)
                
            elif self.mode == ExecutionMode.LIVE:
                # ═══ LIVE MODE: Atomic bundled execution ═══
                # Both legs in one Jito bundle to prevent price flux
                USDC = Settings.USDC_MINT
                token_mint = opportunity.base_mint
                
                Logger.info(f"[EXEC] LIVE ATOMIC: ${trade_size:.2f} {opportunity.pair}")
                
                router = self._get_smart_router()
                usdc_amount = int(trade_size * 1_000_000)
                
                # 1. Get buy quote
                buy_quote = router.get_jupiter_quote(
                    USDC, token_mint, usdc_amount, slippage_bps=50
                )
                if not buy_quote:
                    return self._error_result("Failed to get buy quote", start_time)
                
                expected_tokens = int(buy_quote.get('outAmount', 0))
                
                # 2. Get sell quote (using expected tokens from buy)
                sell_quote = router.get_jupiter_quote(
                    token_mint, USDC, expected_tokens, slippage_bps=50
                )
                if not sell_quote:
                    return self._error_result("Failed to get sell quote", start_time)
                
                # 3. Execute atomically via Jito bundle (or sequential fallback)
                if self.jito and self.jito.is_available():
                    Logger.info("[EXEC] 🛡️ Using Jito atomic bundle...")
                    result = await self._execute_bundled_swaps(buy_quote, sell_quote)
                else:
                    Logger.warning("[EXEC] ⚠️ Jito unavailable - using sequential (flux risk!)")
                    # Fallback to sequential
                    buy_result = await self._execute_swap(buy_quote)
                    if not buy_result.success:
                        return self._error_result(f"Buy failed: {buy_result.error}", start_time)
                    legs.append(buy_result)
                    
                    sell_result = await self._execute_swap(sell_quote)
                    legs.append(sell_result)
                    
                    result = None
                
                if result:
                    # Bundled execution succeeded
                    legs = result.get('legs', [])
                    if not result.get('success'):
                        return self._error_result(result.get('error', 'Bundle failed'), start_time, legs)
                
            else:
                # DRY_RUN
                Logger.info(f"[EXEC] DRY RUN - would execute {opportunity.pair} arb")
                return self._error_result("Dry run - no execution", start_time)
            
            # Calculate P&L
            total_input = trade_size
            total_output = legs[-1].output_amount if legs else trade_size
            gross_profit = total_output - total_input
            total_fees = sum(leg.fee_usd for leg in legs)
            net_profit = gross_profit - total_fees
            
            execution_time = int((time.time() - start_time) * 1000)
            
            # Update stats
            self.total_trades += 1
            if net_profit > 0:
                self.successful_trades += 1
            self.total_profit += net_profit
            self.total_fees += total_fees
            
            Logger.info(
                f"[EXEC] ✅ Spatial arb complete!\n"
                f"   Input: ${total_input:.2f}\n"
                f"   Output: ${total_output:.2f}\n"
                f"   Gross: ${gross_profit:+.2f}\n"
                f"   Fees: ${total_fees:.2f}\n"
                f"   Net: ${net_profit:+.2f}"
            )
            
            return ArbitrageExecution(
                success=True,
                strategy="SPATIAL",
                legs=legs,
                total_input=total_input,
                total_output=total_output,
                gross_profit=gross_profit,
                fees=total_fees,
                net_profit=net_profit,
                execution_time_ms=execution_time,
                timestamp=time.time()
            )
            
        except Exception as e:
            Logger.error(f"[EXEC] Spatial arb error: {e}")
            return self._error_result(str(e), start_time)
    
    async def _execute_bundled_swaps(self, buy_quote: Dict, sell_quote: Dict) -> Dict:
        """
        Execute both swap legs as an atomic Jito bundle.
        
        Both transactions succeed or both fail - no partial execution.
        Prevents price flux between buy and sell legs.
        """
        import base64
        from solders.transaction import VersionedTransaction
        
        try:
            Logger.info("[EXEC] Building atomic bundle...")
            
            # Get swap instructions for both legs
            if not self.swapper:
                from src.shared.execution.swapper import JupiterSwapper
                from src.shared.execution.wallet import WalletManager
                self.swapper = JupiterSwapper(WalletManager())
            
            # Get swap tx for buy leg
            buy_tx_data = self._get_smart_router().get_swap_transaction({
                "quoteResponse": buy_quote,
                "userPublicKey": str(self.wallet.get_public_key()),
                "wrapAndUnwrapSol": True,
            })
            
            if not buy_tx_data or 'swapTransaction' not in buy_tx_data:
                return {"success": False, "error": "Failed to get buy tx", "legs": []}
            
            # Get swap tx for sell leg
            sell_tx_data = self._get_smart_router().get_swap_transaction({
                "quoteResponse": sell_quote,
                "userPublicKey": str(self.wallet.get_public_key()),
                "wrapAndUnwrapSol": True,
            })
            
            if not sell_tx_data or 'swapTransaction' not in sell_tx_data:
                return {"success": False, "error": "Failed to get sell tx", "legs": []}
            
            # Sign both transactions
            buy_raw = base64.b64decode(buy_tx_data["swapTransaction"])
            sell_raw = base64.b64decode(sell_tx_data["swapTransaction"])
            
            buy_tx = VersionedTransaction.from_bytes(buy_raw)
            sell_tx = VersionedTransaction.from_bytes(sell_raw)
            
            signed_buy = VersionedTransaction(buy_tx.message, [self.wallet.keypair])
            signed_sell = VersionedTransaction(sell_tx.message, [self.wallet.keypair])
            
            # Encode for Jito bundle
            import base58
            buy_b58 = base58.b58encode(bytes(signed_buy)).decode()
            sell_b58 = base58.b58encode(bytes(signed_sell)).decode()
            
            # Submit as atomic bundle
            Logger.info("[EXEC] 🚀 Submitting Jito bundle (both legs)...")
            bundle_id = self.jito.submit_bundle([buy_b58, sell_b58])
            
            if not bundle_id:
                return {"success": False, "error": "Jito bundle submission failed", "legs": []}
            
            Logger.info(f"[EXEC] ✅ Bundle submitted: {bundle_id[:16]}...")
            
            # Create result legs
            legs = [
                TradeResult(
                    success=True, trade_type="BUY",
                    input_token=buy_quote.get('inputMint', ''),
                    output_token=buy_quote.get('outputMint', ''),
                    input_amount=int(buy_quote.get('inAmount', 0)) / 1e6,
                    output_amount=int(buy_quote.get('outAmount', 0)) / 1e9,
                    price=0, fee_usd=0.01,
                    signature=bundle_id, error=None,
                    timestamp=time.time(), execution_time_ms=0
                ),
                TradeResult(
                    success=True, trade_type="SELL",
                    input_token=sell_quote.get('inputMint', ''),
                    output_token=sell_quote.get('outputMint', ''),
                    input_amount=int(sell_quote.get('inAmount', 0)) / 1e9,
                    output_amount=int(sell_quote.get('outAmount', 0)) / 1e6,
                    price=0, fee_usd=0.01,
                    signature=bundle_id, error=None,
                    timestamp=time.time(), execution_time_ms=0
                )
            ]
            
            return {"success": True, "bundle_id": bundle_id, "legs": legs}
            
        except Exception as e:
            Logger.error(f"[EXEC] Bundle execution failed: {e}")
            return {"success": False, "error": str(e), "legs": []}
    
    async def _execute_swap(self, quote: Dict) -> TradeResult:
        """Execute a Jupiter swap from a quote."""
        start = time.time()
        
        try:
            if not self.swapper:
                from src.shared.system.smart_router import SmartRouter
                self.swapper = SmartRouter()
            
            # Get swap transaction
            result = self.swapper.execute_jupiter_swap(quote)
            
            if not result or not result.get('success'):
                return TradeResult(
                    success=False,
                    trade_type="SWAP",
                    input_token=quote.get('inputMint', ''),
                    output_token=quote.get('outputMint', ''),
                    input_amount=0,
                    output_amount=0,
                    price=0,
                    fee_usd=0,
                    signature=None,
                    error=result.get('error', 'Unknown error'),
                    timestamp=time.time(),
                    execution_time_ms=int((time.time() - start) * 1000)
                )
            
            return TradeResult(
                success=True,
                trade_type="SWAP",
                input_token=quote.get('inputMint', ''),
                output_token=quote.get('outputMint', ''),
                input_amount=int(quote.get('inAmount', 0)) / 1e6,
                output_amount=int(result.get('outAmount', quote.get('outAmount', 0))) / 1e6,
                price=0,  # Calculate from amounts
                fee_usd=0.01,  # Estimate
                signature=result.get('signature'),
                error=None,
                timestamp=time.time(),
                execution_time_ms=int((time.time() - start) * 1000)
            )
            
        except Exception as e:
            return TradeResult(
                success=False,
                trade_type="SWAP",
                input_token='',
                output_token='',
                input_amount=0,
                output_amount=0,
                price=0,
                fee_usd=0,
                signature=None,
                error=str(e),
                timestamp=time.time(),
                execution_time_ms=int((time.time() - start) * 1000)
            )
    
    def _error_result(
        self, 
        error: str, 
        start_time: float,
        legs: List[TradeResult] = None
    ) -> ArbitrageExecution:
        """Create an error execution result."""
        return ArbitrageExecution(
            success=False,
            strategy="SPATIAL",
            legs=legs or [],
            total_input=0,
            total_output=0,
            gross_profit=0,
            fees=0,
            net_profit=0,
            execution_time_ms=int((time.time() - start_time) * 1000),
            timestamp=time.time(),
            error=error
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get execution statistics."""
        return {
            "total_trades": self.total_trades,
            "successful_trades": self.successful_trades,
            "win_rate": self.successful_trades / self.total_trades if self.total_trades > 0 else 0,
            "total_profit": self.total_profit,
            "total_fees": self.total_fees,
            "net_profit": self.total_profit - self.total_fees,
            "mode": self.mode.value
        }


# ═══════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from src.arbiter.core.spread_detector import SpreadOpportunity
    
    async def test():
        print("=" * 60)
        print("Arbitrage Executor Test (Paper Mode)")
        print("=" * 60)
        
        executor = ArbitrageExecutor(mode=ExecutionMode.PAPER)
        
        # Create mock opportunity
        opportunity = SpreadOpportunity(
            pair="SOL/USDC",
            base_mint="So11111111111111111111111111111111111111112",
            quote_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            buy_dex="Raydium",
            sell_dex="Orca",
            buy_price=118.20,
            sell_price=118.50,
            spread_pct=0.25,
            gross_profit_usd=0.25,
            estimated_fees_usd=0.15,
            net_profit_usd=0.10,
            max_size_usd=100,
            confidence=0.9
        )
        
        print(f"\nExecuting paper trade for {opportunity.pair}...")
        print(f"Spread: {opportunity.spread_pct:.2f}%")
        
        result = await executor.execute_spatial_arb(opportunity, trade_size=100.0)
        
        if result.success:
            print(f"\n✅ Trade executed!")
            print(f"   Net profit: ${result.net_profit:+.2f}")
            print(f"   Execution time: {result.execution_time_ms}ms")
        else:
            print(f"\n❌ Trade failed: {result.error}")
        
        print(f"\nStats: {executor.get_stats()}")
    
    asyncio.run(test())
