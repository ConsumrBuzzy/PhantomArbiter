"""
Trade Engine
============
Orchestrates trade execution logic, handling hybrid routing (Unified vs Jupiter),
fallback strategies, and the "Reality Check" feedback loop.
"""

import time
import re
from typing import Optional
from dataclasses import dataclass

from src.shared.system.logging import Logger
from src.legacy.arbiter.core.spread_detector import SpreadOpportunity
from src.legacy.arbiter.core.executor import ArbitrageExecutor
from src.shared.execution.unified_adapter import UnifiedEngineAdapter
from src.shared.execution.pool_index import get_pool_index
from src.legacy.arbiter.core.fee_estimator import get_fee_estimator
from src.shared.system.db_manager import db_manager
from src.legacy.arbiter.core.pod_engine import pod_manager


@dataclass
class TradeResult:
    """Standardized result from trade execution."""

    success: bool
    net_profit: float = 0.0
    fees: float = 0.0
    engine_used: str = "unknown"
    error: Optional[str] = None
    signature: Optional[str] = None
    pair: str = ""


class TradeEngine:
    """
    Component responsible for executing trades.
    Decouples execution logic from the main Arbiter loop.
    """

    def __init__(
        self,
        executor: ArbitrageExecutor,
        unified_adapter: Optional[UnifiedEngineAdapter] = None,
        use_unified: bool = False,
    ):
        self.executor = executor
        self.unified_adapter = unified_adapter
        self.use_unified = use_unified

    async def execute(
        self, opportunity: SpreadOpportunity, trade_size: float
    ) -> TradeResult:
        """
        Execute the trade using the best available method.
        Returns a TradeResult object.
        """
        result = None
        engine_used = "jupiter"
        start_time = time.time()

        # ═══ HYBRID ROUTING: Try direct DEX execution for Meteora/Orca/Raydium ═══
        if self.unified_adapter and self.use_unified:
            try:
                pool_index = get_pool_index()
                pools = pool_index.get_pools_for_opportunity(opportunity)

                buy_dex = opportunity.buy_dex.lower() if opportunity.buy_dex else ""
                sell_dex = opportunity.sell_dex.lower() if opportunity.sell_dex else ""

                # ═══ RAYDIUM CLMM PATH ═══
                if (
                    pools
                    and pools.raydium_clmm_pool
                    and (buy_dex == "raydium" or sell_dex == "raydium")
                ):
                    try:
                        from src.shared.execution.raydium_bridge import RaydiumBridge

                        bridge = RaydiumBridge()

                        Logger.info(
                            f"[HYBRID] ⚡ Using Raydium CLMM: {pools.raydium_clmm_pool[:8]}..."
                        )

                        swap_result = bridge.execute_swap(
                            pool_address=pools.raydium_clmm_pool,
                            input_mint=opportunity.quote_mint,  # USDC
                            amount=trade_size,
                            slippage_bps=50,  # 0.5% for CLMM
                        )

                        latency_ms = int((time.time() - start_time) * 1000)
                        pool_index.record_execution(
                            pair=opportunity.pair,
                            dex="raydium",
                            success=swap_result.success if swap_result else False,
                            latency_ms=latency_ms,
                            error=swap_result.error
                            if swap_result and not swap_result.success
                            else None,
                        )

                        if swap_result and swap_result.success:
                            get_fee_estimator().update_congestion_factor(
                                is_congested=False
                            )
                            engine_used = "raydium_clmm"
                            result = type(
                                "Result",
                                (),
                                {
                                    "success": True,
                                    "signature": swap_result.signature,
                                    "error": None,
                                },
                            )()
                        else:
                            Logger.warning(
                                f"[HYBRID] Raydium CLMM failed: {swap_result.error if swap_result else 'No result'}"
                            )

                    except Exception as e:
                        Logger.debug(f"[HYBRID] Raydium CLMM error: {e}")

                # ═══ METEORA/ORCA PATH ═══
                if (
                    result is None
                    and pools
                    and pool_index.can_use_unified_engine(opportunity)
                ):
                    # Determine which pools to use
                    buy_pool = (
                        pools.meteora_pool if buy_dex == "meteora" else pools.orca_pool
                    )
                    sell_pool = (
                        pools.orca_pool if sell_dex == "orca" else pools.meteora_pool
                    )

                    if buy_pool and sell_pool:
                        # Convert trade_size USD to lamports (assume 6 decimal USDC)
                        amount_lamports = int(trade_size * 1_000_000)

                        Logger.info(
                            f"[HYBRID] ⚡ Using unified engine: {buy_dex}→{sell_dex}"
                        )

                        unified_result = await self.unified_adapter.execute_atomic_arb(
                            buy_dex=buy_dex,
                            buy_pool=buy_pool,
                            sell_dex=sell_dex,
                            sell_pool=sell_pool,
                            input_mint=opportunity.quote_mint,  # USDC
                            output_mint=opportunity.base_mint,  # Target token
                            amount_in=amount_lamports,
                            slippage_bps=100,
                        )

                        # Record performance
                        latency_ms = int((time.time() - start_time) * 1000)
                        pool_index.record_execution(
                            pair=opportunity.pair,
                            dex=buy_dex,
                            success=unified_result.success,
                            latency_ms=latency_ms,
                            error=unified_result.error
                            if not unified_result.success
                            else None,
                        )

                        if unified_result.success:
                            # Decay congestion multiplier on success
                            get_fee_estimator().update_congestion_factor(
                                is_congested=False
                            )

                            engine_used = "unified"
                            # Create a dummy result compatible with fallback check
                            result = type(
                                "Result",
                                (),
                                {
                                    "success": True,
                                    "signature": unified_result.signature,
                                    "error": None,
                                },
                            )()
                        else:
                            Logger.warning(
                                f"[HYBRID] Unified failed: {unified_result.error}, falling back to Jupiter"
                            )

                            # ═══ V83.0: REALITY CHECK LOOP (Auto-Calibration) ═══
                            if unified_result.error and "Quote loss" in str(
                                unified_result.error
                            ):
                                self._handle_quote_loss(
                                    opportunity, trade_size, str(unified_result.error)
                                )

            except Exception as e:
                Logger.debug(f"[HYBRID] Unified engine error: {e}, using Jupiter")

        # ═══ FALLBACK: Use Jupiter via ArbitrageExecutor ═══
        if result is None:
            # 🗳️ V128.1: Elite Vote Gatekeeper
            # Ensure we don't use PublicRPC for Jito simulations
            from src.shared.infrastructure.rpc_balancer import get_rpc_balancer

            balancer = get_rpc_balancer()
            rpc_winner = balancer.get_winner()

            simulation_rpc = rpc_winner
            if rpc_winner and "public" in rpc_winner.name.lower():
                simulation_rpc = balancer.get_secondary_leader(exclude="public")
                Logger.info(
                    f" 🗳️ [V128.1] PublicRPC won latency, but shifting simulation to {simulation_rpc.name}"
                )

            result = await self.executor.execute_spatial_arb(
                opportunity, trade_size, rpc=simulation_rpc
            )

        # Process Final Result
        if result.success:
            # Calculate final net profit using opportunity data (accurate fees)
            # Adjust for actual size traded if needed (assuming trade_size)
            net_profit = opportunity.net_profit_usd * (
                trade_size / opportunity.max_size_usd
            )

            # V117: Centralized Audit Logging
            try:
                db_manager.log_trade(
                    {
                        "symbol": opportunity.pair,
                        "entry_price": opportunity.buy_price,
                        "exit_price": opportunity.sell_price,
                        "size_usd": trade_size,
                        "pnl_usd": net_profit,
                        "net_pnl_pct": (net_profit / trade_size) * 100,
                        "exit_reason": "ARBITER_HYBRID",
                        "is_win": net_profit > 0,
                        "engine_name": engine_used.upper(),
                        "fees_usd": opportunity.estimated_fees_usd,
                        "trigger_wallet": opportunity.trigger_wallet,
                    }
                )

                # V117: Update Alpha Wallet Performance
                if opportunity.trigger_wallet:
                    db_manager.update_wallet_performance(
                        opportunity.trigger_wallet,
                        is_win=(net_profit > 0),
                        pnl_usd=net_profit,
                    )
                    Logger.info(
                        f"📈 [SCOUT] Updated performance for wallet {opportunity.trigger_wallet[:8]} (PnL: ${net_profit:+.2f})"
                    )
            except Exception as e:
                Logger.debug(f"Audit logging error: {e}")

            return TradeResult(
                success=True,
                net_profit=net_profit,
                fees=opportunity.estimated_fees_usd,
                engine_used=engine_used,
                pair=opportunity.pair,
                signature=getattr(result, "signature", None),
            )
        else:
            return TradeResult(
                success=False,
                error=str(result.error)
                if hasattr(result, "error")
                else "Unknown execution error",
                pair=opportunity.pair,
            )

    def _handle_quote_loss(
        self, opportunity: SpreadOpportunity, trade_size: float, error_msg: str
    ):
        """Handle quote loss feedback loop."""
        # Always Penalize Pod on Quote Loss (Strategy Correction)
        # We process this BEFORE regex parsing to ensure penalty applies even if parsing fails
        pods_containing = pod_manager.get_pods_for_pair(opportunity.pair)
        for pod_name in pods_containing:
            pod_manager.penalize_pod(pod_name, duration_sec=300)  # 5 min penalty
            Logger.info(f"[POD] 🥅 Penalty Box for {pod_name} (5m) due to Quote Loss")

        try:
            # Extract loss amount (e.g. "Quote loss $-0.5668")
            loss_match = re.search(r"Quote loss \$-?([\d\.]+)", error_msg)
            if loss_match:
                loss_amt = float(loss_match.group(1))

                # 1. Log slippage for ML calibration
                token_symbol = opportunity.pair.split("/")[0]
                db_manager.log_slippage(
                    token=token_symbol,
                    pair=opportunity.pair,
                    expected_out=trade_size,
                    actual_out=trade_size - loss_amt,
                    trade_size_usd=trade_size,
                    dex="UNIFIED",
                )
                Logger.info(
                    f"[ML] 🧠 Auto-calibrated slippage logic for {opportunity.pair} (Loss: ${loss_amt:.4f})"
                )

                # 2. Update congestion factor
                get_fee_estimator().update_congestion_factor(is_congested=True)

        except Exception as e:
            Logger.debug(f"[ML] Calibration failed: {e}")
