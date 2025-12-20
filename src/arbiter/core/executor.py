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
    
    def _calculate_optimal_size(self, failed_size: float, failed_net: float, opportunity, real_slippage: float) -> float:
        """
        Analytically calculate the optimal trade size to maximize profit.
        
        Logic:
        - Profit P(x) = Revenue(x) - Cost(x)
        - Revenue(x) = x * (1 + spread)
        - Cost(x) = x * (1 + impact(x)) + fees
        
        Simplified Model (Linear Impact):
        - Impact(x) = k * x
        - Net(x) = x * spread - x * (k * x) - fees
        - Net(x) = x*spread - k*x^2 - fees
        
        To find max profit, derivative P'(x) = spread - 2kx = 0
        => x_opt = spread / (2k)
        
        We derive 'k' from the failed quote:
        - k = impact_pct / size
        """
        try:
            # 1. Estimate Impact Coefficient (k)
            # impact_pct is roughly proportional to size for small amounts
            if failed_size <= 0: return 10.0
            
            # Using the realized slippage/impact from the failed quote
            # If we don't have exact impact, we can infer it from the net vs expected
            # failed_net = (Actual - Input) - Fees
            # Expected Net (no slip) = Input * Spread - Fees
            # Loss due to slip = Expected Net - Actual Net
            
            expected_net = failed_size * (opportunity.spread_pct / 100) - 0.01 # approx fee
            slip_loss = expected_net - failed_net
            
            # slip_loss approx = k * size^2  => k = slip_loss / size^2
            k = slip_loss / (failed_size ** 2)
            
            if k <= 0: return 10.0 # Should not happen if loss occurred
            
            # 2. Optimal Size: x = spread / (2k)
            spread_decimal = opportunity.spread_pct / 100
            opt_size = spread_decimal / (2 * k)
            
            # 3. Safety Bounds
            # Don't exceed original size (liquidity might just end)
            # Don't go below min size
            opt_size = min(opt_size, failed_size * 0.9) # 90% of failed as cap
            opt_size = max(opt_size, 10.0)
            
            return round(opt_size, 2)
            
        except Exception as e:
            Logger.debug(f"Opt calculation failed: {e}")
            return failed_size * 0.5 # Fallback to 50%
            
    async def verify_liquidity(
        self, 
        opportunity, 
        trade_size: float = None
    ) -> tuple[bool, float, str]:
        """
        Verify if opportunity is profitable with REAL liquidity (fetching quotes).
        Returns: (is_valid, real_net_profit, status_message)
        """
        trade_size = trade_size or getattr(Settings, 'DEFAULT_TRADE_SIZE_USD', 50.0)
        
        try:
            # 0. Pre-Check using DataSourceManager (Local Cache / Tiered API)
            # This avoids expensive RPC calls for obviously bad tokens
            from src.shared.system.data_source_manager import DataSourceManager
            dsm = DataSourceManager()
            
            # A. Liquidity Check (TVL)
            liquidity_usd = dsm.get_liquidity(opportunity.base_mint)
            if liquidity_usd > 0 and liquidity_usd < 5000: # Skip if TVL < $5k
                 return False, 0.0, f"LOW LIQ (${liquidity_usd/1000:.1f}k)"
                 
            # B. Slippage Check
            passes, slip_pct, action = dsm.check_slippage_filter(opportunity.base_mint)
            if not passes:
                 return False, 0.0, f"HIGH SLIP ({slip_pct:.1f}%)"
            
            # If "HALF_SIZE" action, reduce trade size automatically
            if action == 'HALF_SIZE':
                 trade_size = trade_size / 2
            
            router = self._get_smart_router()
            usdc_amount = int(trade_size * 1_000_000)
            USDC = Settings.USDC_MINT
            
            # 1. Get buy quote
            buy_quote = router.get_jupiter_quote(
                USDC, opportunity.base_mint, usdc_amount, slippage_bps=50
            )
            if not buy_quote:
                return False, 0.0, "No Buy Liquidity"
                
            expected_tokens = int(buy_quote.get('outAmount', 0))
            
            # 2. Get sell quote
            sell_quote = router.get_jupiter_quote(
                opportunity.base_mint, USDC, expected_tokens, slippage_bps=50
            )
            if not sell_quote:
                return False, 0.0, "No Sell Liquidity"
                
            expected_usdc_back = int(sell_quote.get('outAmount', 0))
            
            # 3. Calculate Real Profit
            projected_profit_usd = (expected_usdc_back - usdc_amount) / 1_000_000
            
            # Fees (approx)
            est_fees = 0.01 
            real_net = projected_profit_usd - est_fees
            
            if real_net > 0:
                return True, real_net, "✅ LIVE"
            
            # RETRY LOGIC (Smart Sizing / Adaptive Trade Pricing)
            # Analytic Solver for Optimal Size
            
            # Calculate optimal size based on the loss we just observed
            opt_size = self._calculate_optimal_size(trade_size, real_net, opportunity, 0)
            
            if opt_size < trade_size and opt_size >= 10.0:
                 Logger.info(f"   📉 Adapting Size: ${trade_size:.2f} -> ${opt_size:.2f} (Calculated Optimal)")
                 
                 # Verify optimal size
                 is_valid, new_net, status = await self.verify_liquidity(opportunity, opt_size)
                 if is_valid:
                     return True, new_net, f"⚠️ SCALED (${opt_size:.0f})"

            return False, real_net, f"❌ LIQ (${real_net:+.2f})"
                
        except Exception as e:
            return False, 0.0, f"Error: {str(e)}"
    
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
                # ═══ PAPER MODE: Real-Quote Execution ═══
                # Fetch REAL quotes to verify liquidity and impact, just like Live mode.
                
                Logger.info(f"[EXEC] PAPER: Fetching quotes for ${trade_size:.2f} {opportunity.pair}")
                router = self._get_smart_router()
                usdc_amount = int(trade_size * 1_000_000)
                USDC = Settings.USDC_MINT
                
                # 1. Get buy quote
                buy_quote = router.get_jupiter_quote(
                    USDC, opportunity.base_mint, usdc_amount, slippage_bps=50
                )
                if not buy_quote:
                    return self._error_result("Failed to get buy quote", start_time)
                    
                expected_tokens = int(buy_quote.get('outAmount', 0))
                
                # 2. Get sell quote (using exact output from buy)
                sell_quote = router.get_jupiter_quote(
                    opportunity.base_mint, USDC, expected_tokens, slippage_bps=50
                )
                if not sell_quote:
                    return self._error_result("Failed to get sell quote", start_time)
                    
                expected_usdc_back = int(sell_quote.get('outAmount', 0))
                
                # 🚨 PHANTOM ARB CHECK (Liquidity Verification)
                projected_profit_usd = (expected_usdc_back - usdc_amount) / 1_000_000
                if projected_profit_usd <= 0:
                    Logger.warning(f"[EXEC] ✋ PAPER: Phantom Arb caught! Quote loss: ${projected_profit_usd:.4f}")
                    return self._error_result(f"Liquidity Fail: Quote loss ${projected_profit_usd:.4f}", start_time)

                # 3. Simulate Execution Result (using REAL quote data)
                # We assume execution matches quote (minus fees)
                
                # Buy Leg
                legs.append(TradeResult(
                    success=True, trade_type="BUY",
                    input_token="USDC", output_token=opportunity.pair.split("/")[0],
                    input_amount=trade_size,
                    output_amount=expected_tokens / 1e9, # Assuming 9 decimals, strict would check mint
                    price=opportunity.buy_price,
                    fee_usd=0.01, signature="PAPER_REAL_" + str(int(time.time())),
                    error=None, timestamp=time.time(), execution_time_ms=250
                ))
                
                # Sell Leg
                legs.append(TradeResult(
                    success=True, trade_type="SELL",
                    input_token=opportunity.pair.split("/")[0], output_token="USDC",
                    input_amount=expected_tokens / 1e9,
                    output_amount=expected_usdc_back / 1_000_000,
                    price=opportunity.sell_price,
                    fee_usd=0.01, signature="PAPER_REAL_" + str(int(time.time())+1),
                    error=None, timestamp=time.time(), execution_time_ms=250
                ))
                
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
                
                expected_usdc_back = int(sell_quote.get('outAmount', 0))
                
                # 🚨 PHANTOM ARB PROTECTION 🚨
                # Check if the Quoted Output (which includes price impact) is actually profitable.
                # Scan uses unit price (no impact), so it might show +34% on illiquid pairs.
                # Quote tells the truth about liquidity.
                
                projected_profit_usd = (expected_usdc_back - usdc_amount) / 1_000_000
                if projected_profit_usd <= 0:
                    Logger.warning(f"[EXEC] ✋ Phantom Arb Detected! Quote shows loss: ${projected_profit_usd:.4f}")
                    return self._error_result(f"Phantom Arb: Quote loss ${projected_profit_usd:.4f}", start_time)
                
                Logger.info(f"[EXEC] ✅ Quote verified: ${projected_profit_usd:+.4f} projected profit")

                # 3. Execute atomically via Jito bundle (or sequential fallback)
                jito_status = "READY" if self.jito and self.jito.is_available() else ("MISSING" if not self.jito else "OFFLINE")
                
                if jito_status == "READY":
                    Logger.info("[EXEC] 🛡️ Using Jito atomic bundle...")
                    result = await self._execute_bundled_swaps(buy_quote, sell_quote)
                else:
                    Logger.error(f"[EXEC] 🛑 Jito {jito_status} (Rate Limit?) - Aborting spatial arb to prevent stuck tokens")
                    return self._error_result(f"Jito Unavailable ({jito_status}) - Safe Abort", start_time)
                    # DISABLED SEQUENTIAL FALLBACK due to high stuck-token risk
                    # buy_result = await self._execute_swap(buy_quote)
                    if not buy_result.success:
                        return self._error_result(f"Buy failed: {buy_result.error}", start_time)
                    legs.append(buy_result)
                    
                    # Execute sell with retry on failure
                    sell_result = await self._execute_swap(sell_quote)
                    
                    # ═══ BUG FIX: Handle sell failure after successful buy ═══
                    if not sell_result.success:
                        Logger.error(f"[EXEC] ❌ SELL FAILED after successful buy! Attempting emergency retry...")
                        
                        # Emergency retry with escalating slippage
                        emergency_slippage_tiers = [100, 200, 500, 1000]  # 1% → 2% → 5% → 10%
                        sell_success = False
                        
                        for retry_idx, slippage_bps in enumerate(emergency_slippage_tiers):
                            Logger.warning(f"[EXEC] ⚠️ Emergency sell retry {retry_idx + 1}/{len(emergency_slippage_tiers)} @ {slippage_bps/100:.1f}% slippage")
                            
                            # Get fresh sell quote with higher slippage
                            emergency_quote = router.get_jupiter_quote(
                                token_mint, USDC, expected_tokens, slippage_bps=slippage_bps
                            )
                            if not emergency_quote:
                                continue
                            
                            sell_result = await self._execute_swap(emergency_quote)
                            if sell_result.success:
                                Logger.info(f"[EXEC] ✅ Emergency sell succeeded on retry {retry_idx + 1}!")
                                sell_success = True
                                break
                            
                            await asyncio.sleep(0.5)  # Brief pause between retries
                        
                        if not sell_success:
                            # Log stuck tokens for manual cleanup
                            Logger.error(f"[EXEC] ❌ STUCK TOKENS: {expected_tokens} units of {token_mint[:8]}... - MANUAL CLEANUP REQUIRED!")
                            Logger.error(f"[EXEC] 💡 Run: python scripts/manual_sweep.py to recover")
                            return self._error_result(
                                f"Sell failed after buy - STUCK {expected_tokens} tokens of {opportunity.pair}", 
                                start_time, 
                                legs
                            )
                    
                    legs.append(sell_result)
                    result = None
                
                if result:
                    # Bundled execution succeeded
                    legs = result.get('legs', [])
                    if not result.get('success'):
                        return self._error_result(result.get('error', 'Bundle failed'), start_time, legs)
                
                # Track actual slippage and log to DB
                if legs and len(legs) >= 2:
                    actual_usdc_back = legs[-1].output_amount * 1_000_000  # Convert to atomic
                    slippage_usd = (expected_usdc_back - actual_usdc_back) / 1_000_000
                    slippage_pct = (expected_usdc_back - actual_usdc_back) / expected_usdc_back * 100 if expected_usdc_back > 0 else 0
                    
                    Logger.info(f"[EXEC] 📊 Slippage: ${slippage_usd:.4f} ({slippage_pct:.2f}%)")
                    
                    # Log to DB for calibration
                    try:
                        from src.shared.system.db_manager import db_manager
                        db_manager.log_trade({
                            'symbol': opportunity.pair,
                            'entry_price': opportunity.buy_price,
                            'exit_price': opportunity.sell_price,
                            'size_usd': trade_size,
                            'pnl_usd': legs[-1].output_amount - trade_size,
                            'net_pnl_pct': ((legs[-1].output_amount - trade_size) / trade_size) * 100,
                            'exit_reason': 'ARBITER_SPATIAL',
                            'is_win': legs[-1].output_amount > trade_size,
                            'engine_name': 'ARBITER',
                            'slippage_pct': slippage_pct,
                            'slippage_usd': slippage_usd,
                            'fees_usd': opportunity.estimated_fees_usd,
                        })
                    except Exception as e:
                        Logger.debug(f"Trade logging error: {e}")
                
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
            
            # Encode signed transactions to base58 for Jito bundle
            import base58 as b58_module
            buy_b58 = b58_module.b58encode(bytes(signed_buy)).decode()
            sell_b58 = b58_module.b58encode(bytes(signed_sell)).decode()
            
            # ═══ CREATE TIP TRANSACTION ═══
            # Jito requires a SOL transfer to a tip account in the bundle
            from solders.system_program import TransferParams, transfer
            from solders.message import MessageV0
            from solders.pubkey import Pubkey
            from solders.hash import Hash
            import httpx
            import base58
            
            # Get random tip account from Jito
            tip_account = self.jito.get_random_tip_account()
            if not tip_account:
                Logger.warning("[EXEC] No Jito tip account available, falling back to sequential")
                # Return None to trigger sequential fallback
                return {"success": False, "error": "No Jito tip account available", "legs": []}
            
            Logger.info(f"[EXEC] 💰 Using tip account: {tip_account[:16]}...")
            
            # Create tip transfer instruction (10,000 lamports ≈ $0.002)
            TIP_AMOUNT_LAMPORTS = 10000
            tip_ix = transfer(TransferParams(
                from_pubkey=self.wallet.keypair.pubkey(),
                to_pubkey=Pubkey.from_string(tip_account),
                lamports=TIP_AMOUNT_LAMPORTS
            ))
            
            # Get recent blockhash for tip tx
            async with httpx.AsyncClient() as client:
                rpc_resp = await client.post(
                    "https://api.mainnet-beta.solana.com",
                    json={"jsonrpc": "2.0", "id": 1, "method": "getLatestBlockhash"},
                    timeout=10
                )
                blockhash_data = rpc_resp.json()
                recent_blockhash = blockhash_data.get("result", {}).get("value", {}).get("blockhash")
            
            if not recent_blockhash:
                return {"success": False, "error": "Failed to get blockhash for tip tx", "legs": []}
            
            # Build tip transaction
            tip_msg = MessageV0.try_compile(
                payer=self.wallet.keypair.pubkey(),
                instructions=[tip_ix],
                address_lookup_table_accounts=[],
                recent_blockhash=Hash.from_string(recent_blockhash)
            )
            tip_tx = VersionedTransaction(tip_msg, [self.wallet.keypair])
            tip_b58 = base58.b58encode(bytes(tip_tx)).decode()
            
            # Submit bundle with tip tx included
            Logger.info("[EXEC] 🚀 Submitting Jito bundle (buy + sell + tip)...")
            bundle_id = self.jito.submit_bundle([buy_b58, sell_b58, tip_b58])
            
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
                from src.shared.execution.swapper import JupiterSwapper
                from src.shared.execution.wallet import WalletManager
                wallet = WalletManager()
                self.swapper = JupiterSwapper(wallet)
            
            # Get swap transaction - use the quote to execute
            # JupiterSwapper.execute_swap expects different params
            input_mint = quote.get('inputMint', '')
            output_mint = quote.get('outputMint', '')
            in_amount = int(quote.get('inAmount', 0))
            
            # Execute the swap through JupiterSwapper
            result = self.swapper.execute_swap(
                direction="BUY",  # Direction relative to the output
                amount_usd=in_amount / 1_000_000,  # Convert from USDC units
                reason="ARB",
                target_mint=output_mint
            )
            
            if not result or not isinstance(result, dict) or not result.get('success'):
                error_msg = result.get('error', 'Unknown error') if isinstance(result, dict) else f"Unexpected return: {type(result)}"
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
                    error=error_msg,
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
