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
        mode: ExecutionMode = ExecutionMode.PAPER,
        stuck_token_guard=None
    ):
        self.wallet = wallet
        self.swapper = swapper
        self.drift = drift_adapter
        self.jito = jito_adapter
        self.mode = mode
        self.stuck_token_guard = stuck_token_guard
        
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
    
    async def _fetch_quotes_async(
        self, 
        opportunity, 
        usdc_amount: int, 
        slippage_bps: int = 50
    ) -> tuple[Optional[Dict], Optional[Dict]]:
        """
        V130: Parallel quote fetching via thread pool.
        Prevents event loop blocking from synchronous HTTP calls.
        Saves ~200-400ms compared to sequential fetching.
        
        Note: Sell quote depends on buy output, so true parallelism isn't possible.
        However, wrapping in to_thread prevents event loop blocking.
        """
        router = self._get_smart_router()
        USDC = Settings.USDC_MINT
        
        try:
            # Buy quote in thread pool (non-blocking)
            buy_quote = await asyncio.to_thread(
                router.get_jupiter_quote,
                USDC, opportunity.base_mint, usdc_amount, slippage_bps
            )
            
            if not buy_quote:
                Logger.debug(f"[EXEC] Buy quote failed for {opportunity.pair}")
                return None, None
            
            expected_tokens = int(buy_quote.get('outAmount', 0))
            
            # Sell quote in thread pool (non-blocking)
            sell_quote = await asyncio.to_thread(
                router.get_jupiter_quote,
                opportunity.base_mint, USDC, expected_tokens, slippage_bps
            )
            
            if not sell_quote:
                Logger.debug(f"[EXEC] Sell quote failed for {opportunity.pair}")
                return buy_quote, None
            
            return buy_quote, sell_quote
            
        except Exception as e:
            Logger.debug(f"[EXEC] Quote fetch error: {e}")
            return None, None
    
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
                
            # Attach to opportunity for execution
            opportunity.buy_quote = buy_quote
            
            expected_tokens = int(buy_quote.get('outAmount', 0))
            
            # 2. Get sell quote
            sell_quote = router.get_jupiter_quote(
                opportunity.base_mint, USDC, expected_tokens, slippage_bps=50
            )
            if not sell_quote:
                return False, 0.0, "No Sell Liquidity"
                
            # Attach to opportunity for execution
            opportunity.sell_quote = sell_quote
                
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
        trade_size: float = None,
        rpc: Any = None
    ) -> ArbitrageExecution:
        """
        Execute spatial arbitrage (cross-DEX spread).
        V128.6: Robust quote handling for FAST-PATH.
        V128.1: Optional RPC for simulation.
        """
        start_time = time.time()
        trade_size = trade_size or getattr(Settings, 'DEFAULT_TRADE_SIZE_USD', 50.0)
        
        try:
            # 1. Ensure REAL quotes are present (crucial for Jito bundles)
            if not getattr(opportunity, 'buy_quote', None) or not getattr(opportunity, 'sell_quote', None):
                Logger.info(f"[EXEC] 🚀 Quote Cache Miss (FAST PATH) - Fetching for {opportunity.pair}")
                usdc_amount = int(trade_size * 1_000_000)
                
                # V130: Use async helper (non-blocking thread pool)
                quote_start = time.time()
                buy_quote, sell_quote = await self._fetch_quotes_async(
                    opportunity, usdc_amount, slippage_bps=50
                )
                quote_time_ms = (time.time() - quote_start) * 1000
                Logger.debug(f"[EXEC] ⚡ Quotes fetched in {quote_time_ms:.0f}ms")
                
                if not buy_quote:
                    return self._error_result("Failed to get buy quote", start_time)
                if not sell_quote:
                    return self._error_result("Failed to get sell quote", start_time)
                
                opportunity.buy_quote = buy_quote
                opportunity.sell_quote = sell_quote

            # 2. Extract verified quotes
            buy_quote = opportunity.buy_quote
            sell_quote = opportunity.sell_quote
            usdc_amount = int(buy_quote.get('inAmount', trade_size * 1_000_000))
            expected_usdc_back = int(sell_quote.get('outAmount', 0))
            projected_profit_usd = (expected_usdc_back - usdc_amount) / 1_000_000

            # V120: Minimum net profit filter (dynamic based on spread)
            SKIP_QUOTE_THRESHOLD = 0.015  # 1.5%
            scan_spread_pct = getattr(opportunity, 'spread_pct', 0)
            
            # 3. Liquidity Floor & Safety Checks
            if scan_spread_pct >= SKIP_QUOTE_THRESHOLD:
                # FAST PATH: Large spread allows smaller buffer
                MIN_SKIP_QUOTE_PROFIT = 0.015
                if projected_profit_usd < MIN_SKIP_QUOTE_PROFIT:
                    Logger.info(f"[EXEC] ⏭️ Skip-quote trade too thin: Net ${projected_profit_usd:.3f} < ${MIN_SKIP_QUOTE_PROFIT}")
                    return self._error_result(f"Skip-quote trade too thin: ${projected_profit_usd:.3f} < ${MIN_SKIP_QUOTE_PROFIT}", start_time)
            else:
                # NORMAL PATH: needs buffer for decay
                MIN_NET_PROFIT_USD = 0.15
                if projected_profit_usd < MIN_NET_PROFIT_USD:
                    Logger.info(f"[EXEC] ⏭️ Skipping thin spread: Net ${projected_profit_usd:.3f} < ${MIN_NET_PROFIT_USD}")
                    return self._error_result(f"Net too thin: ${projected_profit_usd:.3f} < ${MIN_NET_PROFIT_USD}", start_time)

            # 4. Mode-specific Execution
            legs = []
            if self.mode == ExecutionMode.PAPER:
                # ═══ PAPER MODE: Simulated Execution ═══
                legs = [
                    TradeResult(
                        success=True, trade_type="BUY",
                        input_token="USDC", output_token=opportunity.pair.split("/")[0],
                        input_amount=trade_size,
                        output_amount=int(buy_quote.get('outAmount', 0)) / 1e9,
                        price=opportunity.buy_price, fee_usd=0.01,
                        signature="PAPER_" + str(int(time.time())), timestamp=time.time(), execution_time_ms=250
                    ),
                    TradeResult(
                        success=True, trade_type="SELL",
                        input_token=opportunity.pair.split("/")[0], output_token="USDC",
                        input_amount=int(buy_quote.get('outAmount', 0)) / 1e9,
                        output_amount=expected_usdc_back / 1_000_000,
                        price=opportunity.sell_price, fee_usd=0.01,
                        signature="PAPER_" + str(int(time.time())+1), timestamp=time.time(), execution_time_ms=250
                    )
                ]
            elif self.mode == ExecutionMode.LIVE:
                # ═══ LIVE MODE: Atomic Bundled Execution ═══
                jito_status = "READY" if self.jito and await self.jito.is_available() else ("MISSING" if not self.jito else "OFFLINE")
                
                if jito_status == "READY":
                    Logger.info(f"[EXEC] 🛡️ Using Jito atomic bundle (Elite RPC: {getattr(rpc, 'name', 'Winner')})...")
                    result = await self._execute_bundled_swaps(buy_quote, sell_quote, rpc=rpc)
                    
                    if result and result.get("success"):
                        legs = result.get('legs', [])
                    else:
                        # V131: Fallback to sequential execution when Jito fails
                        error_msg = result.get('error', 'Jito bundle failed') if result else 'Jito bundle execution failed'
                        Logger.warning(f"[EXEC] Jito failed: {error_msg} - Trying sequential fallback...")
                        print(f"   ⚠️ Jito failed: {error_msg}")
                        print(f"   🔄 Attempting sequential RPC fallback...")
                        
                        try:
                            # Sequential fallback: Execute buy, then sell
                            fallback_result = await self._execute_sequential_fallback(buy_quote, sell_quote, rpc)
                            if fallback_result and fallback_result.get("success"):
                                Logger.info("[EXEC] ✅ Sequential fallback succeeded!")
                                print("   ✅ Sequential fallback SUCCEEDED!")
                                legs = fallback_result.get('legs', [])
                            else:
                                fb_error = fallback_result.get('error', 'Unknown') if fallback_result else 'Failed'
                                Logger.error(f"[EXEC] Sequential fallback also failed: {fb_error}")
                                return self._error_result(f"Both Jito and fallback failed: {fb_error}", start_time)
                        except Exception as e:
                            Logger.error(f"[EXEC] Sequential fallback exception: {e}")
                            return self._error_result(f"Fallback exception: {e}", start_time)
                else:
                    Logger.warning(f"[EXEC] 🛑 Jito {jito_status} - Aborting trade to prevent stuck tokens")
                    return self._error_result(f"Jito {jito_status} - Aborted", start_time)
            else:
                # DRY RUN
                Logger.info(f"[EXEC] DRY RUN - would execute {opportunity.pair} arb")
                return self._error_result("Dry run - no execution", start_time)

            # 5. Finalize Results
            total_input = trade_size
            total_output = legs[-1].output_amount if legs else trade_size
            gross_profit = total_output - total_input
            total_fees = sum(leg.fee_usd for leg in legs)
            net_profit = gross_profit - total_fees
            execution_time = int((time.time() - start_time) * 1000)
            
            self.total_trades += 1
            if net_profit > 0:
                self.successful_trades += 1
            self.total_profit += net_profit
            self.total_fees += total_fees
            
            Logger.info(
                f"[EXEC] ✅ Spatial arb complete!\n"
                f"   Input: ${total_input:.2f}\n"
                f"   Output: ${total_output:.2f}\n"
                f"   Net: ${net_profit:+.2f}"
            )
            
            return ArbitrageExecution(
                success=True, strategy="SPATIAL", legs=legs,
                total_input=total_input, total_output=total_output,
                gross_profit=gross_profit, fees=total_fees, net_profit=net_profit,
                execution_time_ms=execution_time, timestamp=time.time()
            )
        except Exception as e:
            Logger.error(f"[EXEC] Spatial arb error: {e}")
            return self._error_result(str(e), start_time)
    
    async def _execute_bundled_swaps(self, buy_quote: Dict, sell_quote: Dict, rpc: Any = None) -> Dict:
        """
        V130: Execute both swap legs as an atomic Jito bundle.
        
        OPTIMIZATION: Tip is embedded in sell transaction (2 txs instead of 3).
        This reduces bundle size by 33% for faster Jito ingestion.
        
        Bundle structure: [buy_tx, sell_tx_with_tip]
        """
        import base64
        import base58
        from solders.transaction import VersionedTransaction
        from solders.system_program import TransferParams, transfer
        from solders.message import MessageV0
        from solders.pubkey import Pubkey
        from solders.instruction import Instruction, AccountMeta
        
        try:
            Logger.info("[EXEC] Building atomic bundle (V131: parallel tx + embedded tip)...")
            
            # Get tip account first (needed for sell tx)
            tip_account = await self.jito.get_random_tip_account()
            if not tip_account:
                Logger.warning("[EXEC] No Jito tip account available")
                return {"success": False, "error": "No Jito tip account available", "legs": []}
            
            Logger.info(f"[EXEC] 💰 Tip account: {tip_account[:16]}...")
            
            # ═══ V131: PARALLEL TX FETCHING ═══
            # Fire both swap tx requests concurrently (~150-300ms savings)
            router = self._get_smart_router()
            
            buy_payload = {
                "quoteResponse": buy_quote,
                "userPublicKey": str(self.wallet.get_public_key()),
                "wrapAndUnwrapSol": True,
            }
            sell_payload = {
                "quoteResponse": sell_quote,
                "userPublicKey": str(self.wallet.get_public_key()),
                "wrapAndUnwrapSol": True,
            }
            
            # Parallel fetch in thread pool
            tx_start = time.time()
            buy_tx_data, sell_tx_fallback = await asyncio.gather(
                asyncio.to_thread(router.get_swap_transaction, buy_payload),
                asyncio.to_thread(router.get_swap_transaction, sell_payload),
                return_exceptions=True
            )
            tx_time_ms = (time.time() - tx_start) * 1000
            Logger.debug(f"[EXEC] ⚡ Parallel tx fetch: {tx_time_ms:.0f}ms")
            
            # Handle exceptions from gather
            if isinstance(buy_tx_data, Exception) or not buy_tx_data:
                return {"success": False, "error": "Failed to get buy tx", "legs": []}
            if 'swapTransaction' not in buy_tx_data:
                return {"success": False, "error": "Failed to get buy tx", "legs": []}
            
            buy_raw = base64.b64decode(buy_tx_data["swapTransaction"])
            buy_tx = VersionedTransaction.from_bytes(buy_raw)
            signed_buy = VersionedTransaction(buy_tx.message, [self.wallet.keypair])
            buy_b58 = base58.b58encode(bytes(signed_buy)).decode()
            
            # Get blockhash from buy tx for tip (ensures same expiry)
            recent_blockhash = buy_tx.message.recent_blockhash
            
            # ═══ SELL TX: Try to use swap-instructions API for embedded tip ═══
            sell_b58 = None
            TIP_AMOUNT_LAMPORTS = 10000  # ~$0.002
            
            try:
                # V131-FIX: Ensure swapper is initialized for instruction-level API
                if not self.swapper:
                    from src.shared.execution.swapper import JupiterSwapper
                    from src.shared.execution.wallet import WalletManager
                    self.swapper = JupiterSwapper(WalletManager())
                    
                sell_instructions = await self.swapper.get_swap_instructions(sell_quote)
                
                if sell_instructions:
                    # Create tip instruction
                    tip_ix = transfer(TransferParams(
                        from_pubkey=self.wallet.keypair.pubkey(),
                        to_pubkey=Pubkey.from_string(tip_account),
                        lamports=TIP_AMOUNT_LAMPORTS
                    ))
                    
                    # Append tip to swap instructions
                    all_instructions = sell_instructions + [tip_ix]
                    
                    # Build tipped sell transaction
                    sell_msg = MessageV0.try_compile(
                        payer=self.wallet.keypair.pubkey(),
                        instructions=all_instructions,
                        address_lookup_table_accounts=[],
                        recent_blockhash=recent_blockhash
                    )
                    
                    tipped_sell_tx = VersionedTransaction(sell_msg, [self.wallet.keypair])
                    sell_b58 = base58.b58encode(bytes(tipped_sell_tx)).decode()
                    Logger.debug("[EXEC] ✅ Built tipped sell tx (embedded)")
                        
            except Exception as e:
                Logger.warning(f"[EXEC] Embedded tip fallback triggered: {e}")
            
            # ═══ FALLBACK: Use pre-fetched sell tx + separate tip tx ═══
            if not sell_b58:
                Logger.debug("[EXEC] Using fallback: 3-tx bundle with pre-fetched sell")
                
                # V131-FIX: Use pre-fetched sell_tx_fallback instead of re-fetching
                if isinstance(sell_tx_fallback, Exception) or not sell_tx_fallback:
                    return {"success": False, "error": "Failed to get sell tx", "legs": []}
                if 'swapTransaction' not in sell_tx_fallback:
                    return {"success": False, "error": "Failed to get sell tx (no swapTransaction)", "legs": []}
                
                sell_raw = base64.b64decode(sell_tx_fallback["swapTransaction"])
                sell_tx = VersionedTransaction.from_bytes(sell_raw)
                signed_sell = VersionedTransaction(sell_tx.message, [self.wallet.keypair])
                sell_b58 = base58.b58encode(bytes(signed_sell)).decode()
                
                # Separate tip tx (fallback - 3 tx bundle)
                tip_ix = transfer(TransferParams(
                    from_pubkey=self.wallet.keypair.pubkey(),
                    to_pubkey=Pubkey.from_string(tip_account),
                    lamports=TIP_AMOUNT_LAMPORTS
                ))
                tip_msg = MessageV0.try_compile(
                    payer=self.wallet.keypair.pubkey(),
                    instructions=[tip_ix],
                    address_lookup_table_accounts=[],
                    recent_blockhash=recent_blockhash
                )
                tip_tx = VersionedTransaction(tip_msg, [self.wallet.keypair])
                tip_b58 = base58.b58encode(bytes(tip_tx)).decode()
                
                # 3-tx fallback bundle
                tx_bundle = [buy_b58, sell_b58, tip_b58]
                Logger.info(f"[EXEC] 🚀 Submitting 3-tx fallback bundle...")
            else:
                # 2-tx optimized bundle
                tx_bundle = [buy_b58, sell_b58]
                Logger.info(f"[EXEC] 🚀 Submitting 2-tx bundle (V130 embedded tip)...")
            
            # Submit bundle
            Logger.info(f"[EXEC] 📦 Bundle size: {len(tx_bundle)} txs")
            bundle_id = await self.jito.submit_bundle(tx_bundle, simulate=True, rpc=rpc)
            
            if not bundle_id:
                # V131: Enhanced failure logging
                Logger.warning(f"[EXEC] ⚠️ Jito submission failed - Check simulation logs above")
                Logger.debug(f"[EXEC] Bundle txs: {[tx[:20] + '...' for tx in tx_bundle]}")
                return {"success": False, "error": "Jito bundle submission failed", "legs": [], "should_fallback": True}
            
            Logger.info(f"[EXEC] ✅ Bundle submitted: {bundle_id[:16]}...")
            
            # V120: Wait for bundle landing confirmation
            # This ensures we only count successful trades and can detect failed bundles early.
            is_confirmed = await self.jito.wait_for_confirmation(bundle_id)
            
            if not is_confirmed:
                # Bundle failed (Invalid/Dropped) - Return failure to trigger sequential fallback?
                # Actually, sequential fallback logic is currently only for "Jito Unavailable".
                # To be robust: If bundle fails, we could try sequential execution if price is still good.
                Logger.warning(f"[EXEC] ⚠️ Jito bundle failed (Invalid/Dropped).")
                return {"success": False, "error": "Jito bundle failed verification", "legs": [], "should_fallback": True}
            
            # ═══ V131: ML Data Capture - Log slippage for training ═══
            try:
                from src.shared.system.db_manager import db_manager
                
                # Buy leg slippage (actual = what we got, expected = quote)
                buy_expected = int(buy_quote.get('outAmount', 0))
                # TODO: Get actual from on-chain tx when we have tx parser
                # For now, log expected as baseline (0% slippage assumed for confirmed)
                if buy_expected > 0:
                    db_manager.log_slippage(
                        token=buy_quote.get('outputMint', '')[:8],
                        pair=f"{buy_quote.get('outputMint', '')[:4]}/USDC",
                        expected_out=buy_expected,
                        actual_out=buy_expected,  # Placeholder until tx parser
                        trade_size_usd=int(buy_quote.get('inAmount', 0)) / 1e6,
                        dex="JUPITER"
                    )
                    Logger.debug("[ML] Logged buy slippage data")
            except Exception as e:
                Logger.debug(f"[ML] Slippage logging failed: {e}")
            
            # Create result legs
            legs = [
                TradeResult(
                    success=is_confirmed, trade_type="BUY",
                    input_token=buy_quote.get('inputMint', ''),
                    output_token=buy_quote.get('outputMint', ''),
                    input_amount=int(buy_quote.get('inAmount', 0)) / 1e6,
                    output_amount=int(buy_quote.get('outAmount', 0)) / 1e9,
                    price=0, fee_usd=0.01,
                    signature=bundle_id, error=None if is_confirmed else "Bundle failed to land",
                    timestamp=time.time(), execution_time_ms=0
                ),
                TradeResult(
                    success=is_confirmed, trade_type="SELL",
                    input_token=sell_quote.get('inputMint', ''),
                    output_token=sell_quote.get('outputMint', ''),
                    input_amount=int(sell_quote.get('inAmount', 0)) / 1e9,
                    output_amount=int(sell_quote.get('outAmount', 0)) / 1e6,
                    price=0, fee_usd=0.01,
                    signature=bundle_id, error=None if is_confirmed else "Bundle failed to land",
                    timestamp=time.time(), execution_time_ms=0
                )
            ]
            
            return {"success": is_confirmed, "bundle_id": bundle_id, "legs": legs}
            
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
    
    async def execute_triangular_arb(self, opportunity, dry_run: bool = True, rpc: Any = None) -> Optional[Dict]:
        """
        V120: Execute a triangular arbitrage trade (3 hops).
        V128.1: Optional RPC for simulation.
        Path: A -> B -> C -> A
        """
        start_time = time.time()
        
        # 1. Validation
        if not self.jito and not dry_run:
            Logger.error("[EXEC] ❌ Triangular Arb requires Jito (Atomic Bundle)")
            return None
            
        Logger.info(f"[EXEC] 📐 {'Observing' if dry_run else 'Executing'} Triangular: {' -> '.join(opportunity.route_tokens)}")
        
        try:
            # 2. Decimal Mapping (USDC vs SOL vs Others)
            def get_dec(mint):
                if mint == Settings.USDC_MINT: return 6
                if mint == "So11111111111111111111111111111111111111112": return 9
                # Fallback to wallet info or 9
                info = self.wallet.get_token_info(mint) if self.wallet else None
                return int(info.get('decimals', 9)) if info else 9

            d1 = get_dec(opportunity.route_tokens[0])
            d2 = get_dec(opportunity.route_tokens[1])
            d3 = get_dec(opportunity.route_tokens[2])

            # 3. Get Quotes for all 3 legs
            # Leg 1: A -> B
            quote1 = await self.swapper.get_quote(
                input_mint=opportunity.route_tokens[0],
                output_mint=opportunity.route_tokens[1],
                amount=int(opportunity.start_amount * 10**d1),
                slippage=50
            )
            
            if not quote1: return None
            
            # Leg 2: B -> C
            quote2 = await self.swapper.get_quote(
                input_mint=opportunity.route_tokens[1],
                output_mint=opportunity.route_tokens[2],
                amount=int(quote1['outAmount']),
                slippage=50
            )
            
            if not quote2: return None
            
            # Leg 3: C -> A
            quote3 = await self.swapper.get_quote(
                input_mint=opportunity.route_tokens[2],
                output_mint=opportunity.route_tokens[0],
                amount=int(quote2['outAmount']),
                slippage=50
            ) 
            
            if not quote3: return None
            
            # 4. Verify Final Output
            final_out = int(quote3['outAmount']) / 10**d1
            start_in = opportunity.start_amount
            
            estimated_profit = final_out - start_in
            Logger.info(f"[EXEC] 📐 REAL Profit: ${estimated_profit:.4f} (Scan was ${opportunity.net_profit_usd:.4f})")
            
            if dry_run:
                return {"success": True, "real_profit": estimated_profit}

            if estimated_profit <= 0.05: # Minimal hurdle
                Logger.warning(f"[EXEC] ❌ Quote slippage ate profit: ${estimated_profit:.4f}")
                return None
                
            # 5. Build Transactions (3 Swaps)
            # Both router and swapper can build txs
            from src.shared.system.smart_router import SmartRouter
            router = SmartRouter()
            
            tx1_data = router.get_swap_transaction({
                "quoteResponse": quote1,
                "userPublicKey": str(self.wallet.get_public_key()),
                "wrapAndUnwrapSol": True
            })
            tx2_data = router.get_swap_transaction({
                "quoteResponse": quote2,
                "userPublicKey": str(self.wallet.get_public_key()),
                "wrapAndUnwrapSol": True
            })
            tx3_data = router.get_swap_transaction({
                "quoteResponse": quote3,
                "userPublicKey": str(self.wallet.get_public_key()),
                "wrapAndUnwrapSol": True
            })
            
            if not (tx1_data and tx2_data and tx3_data):
                Logger.warning("[EXEC] ❌ Failed to build swap transactions")
                return None
                
            # 6. Build Jito Tip Transaction (Reuse blockhash 1)
            import base64
            from solders.transaction import VersionedTransaction
            
            buy_tx = VersionedTransaction.from_bytes(base64.b64decode(tx1_data["swapTransaction"]))
            recent_blockhash = buy_tx.message.recent_blockhash
            
            tip_account = await self.jito.get_random_tip_account()
            tip_lamports = 1000000 # 0.001 SOL (~$0.15) aggressive tip
            
            from solders.system_program import TransferParams, transfer
            from solders.message import MessageV0
            from solders.pubkey import Pubkey
            
            tip_ix = transfer(TransferParams(
                from_pubkey=self.wallet.get_public_key(),
                to_pubkey=Pubkey.from_string(tip_account),
                lamports=tip_lamports
            ))
            
            tip_msg = MessageV0.try_compile(
                payer=self.wallet.get_public_key(),
                instructions=[tip_ix],
                address_lookup_table_accounts=[],
                recent_blockhash=recent_blockhash
            )
            tip_tx = VersionedTransaction(tip_msg, [self.wallet.keypair])
            
            # 7. Sign and Serialize
            import base58
            def sign_b58(tx_data_or_obj):
                if isinstance(tx_data_or_obj, dict):
                    raw = base64.b64decode(tx_data_or_obj["swapTransaction"])
                    tx = VersionedTransaction.from_bytes(raw)
                else:
                    tx = tx_data_or_obj
                
                signed = VersionedTransaction(tx.message, [self.wallet.keypair])
                return base58.b58encode(bytes(signed)).decode()

            signed_txs = [
                sign_b58(tx1_data),
                sign_b58(tx2_data),
                sign_b58(tx3_data),
                base58.b58encode(bytes(tip_tx)).decode()
            ]
            
            # 8. Submit Bundle
            # V128.1: Simulation handled internally
            Logger.info(f"🚀 [JITO] Triangular Bundle (V128.1 Simulation on {getattr(rpc, 'name', 'Jito')})...")
            bundle_id = await self.jito.submit_bundle(signed_txs, simulate=True, rpc=rpc)
            
            if bundle_id:
                Logger.info(f"🚀 [JITO] Triangular Bundle Submitted: {bundle_id[:8]}...")
                return {"success": True, "bundle_id": bundle_id}
            
            return None

        except Exception as e:
            Logger.error(f"[EXEC] Triangular error: {e}")
            return None

    def _error_result(self, error_msg: str, start_time: float, legs: List[TradeResult] = None) -> Dict:
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
            error=error_msg
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
