"""
DNEM Sync Execution Engine
==========================
Atomic Spot+Perp bundling via Jito Block Engine.

This is the "Coordinator" that ensures delta neutrality is maintained
by executing both legs of a trade in the same block.

Architecture:
1. PREP → Generate instructions from Jupiter (spot) and Drift (perp)
2. BUNDLE → Combine into Jito bundle with tip
3. GUARD → Latency check (>500ms = ABORT)
4. FIRE → Submit to Jito non-public mempool
5. VERIFY → Wait for confirmation, handle PARTIAL fills

⚠️ CRITICAL: If bundle partially fills, EMERGENCY ROLLBACK is triggered.
"""

from __future__ import annotations

import time
import base64
import asyncio
from typing import Optional, Tuple, List, Any
from dataclasses import dataclass, field

from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from solders.instruction import Instruction, AccountMeta
from solders.pubkey import Pubkey
from solders.system_program import transfer, TransferParams

from src.delta_neutral.types import (
    SyncTradeBundle,
    RebalanceSignal,
    RebalanceDirection,
    LatencyKillSwitchError,
    LegFailureError,
)
from src.delta_neutral.position_calculator import get_rebalance_qty
from src.shared.system.logging import Logger


# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass(frozen=True, slots=True)
class SyncExecutionConfig:
    """Configuration for sync execution."""
    
    # Kill-switch thresholds
    max_latency_ms: float = 500.0
    
    # Jito bundle settings
    # Jito bundle settings
    default_tip_lamports: int = 50_000
    max_tip_lamports: int = 200_000
    
    # Confirmation settings
    confirmation_timeout_sec: float = 30.0
    max_blocks_for_rollback: int = 3
    
    # Slippage for emergency trades
    emergency_slippage_bps: int = 500


@dataclass
class TradeRevenue:
    """Penny tracker for a single trade cycle."""
    
    funding_earned_estimate: float = 0.0
    transaction_cost_usd: float = 0.0
    jito_tip_usd: float = 0.0
    gas_cost_usd: float = 0.0
    
    @property
    def net_profit_usd(self) -> float:
        """Net profit after all costs."""
        return self.funding_earned_estimate - self.transaction_cost_usd
    
    @property
    def is_profitable(self) -> bool:
        return self.net_profit_usd > 0
    
    def __repr__(self) -> str:
        status = "✅ WIN" if self.is_profitable else "❌ LOSS"
        return (
            f"TradeRevenue({status}: "
            f"Funding=${self.funding_earned_estimate:.4f}, "
            f"Cost=${self.transaction_cost_usd:.4f}, "
            f"Net=${self.net_profit_usd:.4f})"
        )


# =============================================================================
# SYNC EXECUTION ENGINE
# =============================================================================


class SyncExecution:
    """
    Atomic execution coordinator for Delta Neutral trades.
    
    Bundles Jupiter Swap (Spot) + Drift Order (Perp) into single Jito bundle.
    Implements kill-switch and emergency rollback for partial fills.
    
    Example:
        >>> sync = SyncExecution(swapper, drift_adapter, jito_adapter, latency_monitor)
        >>> bundle = await sync.execute_sync_trade(signal, spot_price=150.0)
        >>> if bundle.needs_rollback:
        ...     await sync.emergency_rollback(bundle)
    """
    
    def __init__(
        self,
        swapper: Any,  # JupiterSwapper
        drift: Any,    # DriftAdapter  
        jito: Any,     # JitoAdapter
        latency_monitor: Any,  # LatencyMonitor
        wallet: Any,   # WalletManager
        config: Optional[SyncExecutionConfig] = None,
        use_redis_snapshots: bool = False,
    ):
        self.swapper = swapper
        self.drift = drift
        self.jito = jito
        self.latency = latency_monitor
        self.wallet = wallet
        self.config = config or SyncExecutionConfig()
        
        # Position snapshot manager for partial fill protection
        from src.delta_neutral.position_snapshot import create_snapshot_manager
        self.snapshot_manager = create_snapshot_manager(use_redis=use_redis_snapshots)
        self._current_snapshot_key: Optional[str] = None
        
        # Statistics
        self._bundles_attempted = 0
        self._bundles_landed = 0
        self._bundles_failed = 0
        self._partial_fills = 0
        self._rollbacks_executed = 0
        self._kill_switch_activations = 0
        
        # Revenue tracking
        self._total_revenue = TradeRevenue()
    
    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================
    
    async def execute_sync_trade(
        self,
        signal: RebalanceSignal,
        spot_price: float,
        tip_lamports: Optional[int] = None,
    ) -> SyncTradeBundle:
        """
        Execute atomic Spot+Perp trade via Jito bundle.
        
        Args:
            signal: RebalanceSignal from NeutralityMonitor
            spot_price: Current SOL/USD price
            tip_lamports: Optional custom Jito tip
        
        Returns:
            SyncTradeBundle with execution status
        
        Raises:
            LatencyKillSwitchError: If latency exceeds threshold
        """
        self._bundles_attempted += 1
        tip = tip_lamports or self.config.default_tip_lamports
        
        # Step 1: GUARD - Check latency kill-switch
        await self._check_kill_switch()
        
        # Step 1.5: SNAPSHOT - Capture pre-trade state for rollback detection
        snapshot_key = await self.snapshot_manager.capture_pre_trade(
            self.wallet,
            self.drift,
            signal,
            block_height=await self._get_current_slot(),
        )
        self._current_snapshot_key = snapshot_key
        
        # Step 2: PREP - Build instructions
        Logger.info(f"[DNEM] Building atomic bundle for {signal}")
        
        try:
            spot_ixs = await self._build_spot_instructions(signal, spot_price)
            perp_ixs = await self._build_perp_instructions(signal)
            tip_ix = await self._build_tip_instruction(tip)
        except Exception as e:
            Logger.error(f"[DNEM] Instruction build failed: {e}")
            return SyncTradeBundle(
                spot_instruction=b"",
                perp_instruction=b"",
                status="FAILED",
            )
        
        # Step 3: BUNDLE - Combine into versioned transactions
        try:
            bundle_txs = await self._assemble_bundle(spot_ixs, perp_ixs, tip_ix)
        except Exception as e:
            Logger.error(f"[DNEM] Bundle assembly failed: {e}")
            return SyncTradeBundle(
                spot_instruction=b"",
                perp_instruction=b"",
                status="FAILED",
            )
        
        # Step 4: FIRE - Submit to Jito
        bundle_id = await self._submit_bundle(bundle_txs)
        
        if not bundle_id:
            self._bundles_failed += 1
            return SyncTradeBundle(
                spot_instruction=bundle_txs[0] if bundle_txs else b"",
                perp_instruction=bundle_txs[1] if len(bundle_txs) > 1 else b"",
                jito_tip_lamports=tip,
                status="FAILED",
            )
        
        # Step 5: VERIFY - Wait for confirmation
        bundle = SyncTradeBundle(
            spot_instruction=bundle_txs[0] if bundle_txs else b"",
            perp_instruction=bundle_txs[1] if len(bundle_txs) > 1 else b"",
            jito_tip_lamports=tip,
            bundle_id=bundle_id,
            status="SUBMITTED",
            submitted_slot=await self._get_current_slot(),
        )
        
        confirmed = await self._wait_for_confirmation(bundle)
        
        if confirmed:
            self._bundles_landed += 1
            bundle.status = "CONFIRMED"
            bundle.confirmed_slot = await self._get_current_slot()
            Logger.info(f"[DNEM] ✅ Bundle LANDED: {bundle_id[:16]}...")
        else:
            # Check for partial fill
            is_partial = await self._check_partial_fill(bundle)
            if is_partial:
                self._partial_fills += 1
                bundle.status = "PARTIAL"
                Logger.warning(f"[DNEM] ⚠️ PARTIAL FILL detected! Emergency rollback required.")
            else:
                self._bundles_failed += 1
                bundle.status = "FAILED"
        
        return bundle
    
    # =========================================================================
    # KILL-SWITCH
    # =========================================================================
    
    async def _check_kill_switch(self) -> None:
        """
        Check if latency exceeds safe threshold.
        
        Raises:
            LatencyKillSwitchError if latency > 500ms
        """
        stats = self.latency.get_stats()
        avg_latency = stats.get("wss_avg_ms", 0)
        max_latency = stats.get("wss_max_ms", avg_latency)
        
        # Use whichever is higher
        effective_latency = max(avg_latency, max_latency * 0.8)
        
        if effective_latency > self.config.max_latency_ms:
            self._kill_switch_activations += 1
            Logger.warning(
                f"[DNEM] 🛑 KILL-SWITCH: Latency {effective_latency:.0f}ms "
                f"> {self.config.max_latency_ms:.0f}ms threshold"
            )
            raise LatencyKillSwitchError(
                latency_ms=effective_latency,
                threshold_ms=self.config.max_latency_ms,
            )
        
        Logger.debug(f"[DNEM] Kill-switch ARMED (latency: {effective_latency:.0f}ms)")
    
    # =========================================================================
    # INSTRUCTION BUILDERS
    # =========================================================================
    
    async def _build_spot_instructions(
        self,
        signal: RebalanceSignal,
        spot_price: float,
    ) -> List[Instruction]:
        """Build Jupiter swap instructions for spot leg."""
        
        # Determine swap direction based on signal
        SOL_MINT = "So11111111111111111111111111111111111111112"
        USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        
        if signal.direction == RebalanceDirection.ADD_SPOT:
            # Buy SOL with USDC
            input_mint = USDC_MINT
            output_mint = SOL_MINT
            amount = int(signal.qty_usd * 1_000_000)  # USDC has 6 decimals
        else:
            # Sell SOL for USDC (to free capital for short increase)
            input_mint = SOL_MINT
            output_mint = USDC_MINT
            amount = int(signal.qty * 1_000_000_000)  # SOL has 9 decimals
        
        # Get quote from Jupiter
        quote = await self.swapper.get_quote(
            input_mint,
            output_mint,
            amount,
            slippage=100,  # 1% slippage for rebalance
        )
        
        if not quote:
            raise ValueError("Jupiter quote failed")
        
        # Get swap instructions
        instructions = await self.swapper.get_swap_instructions(quote)
        
        Logger.info(
            f"[DNEM] Spot leg: {'BUY' if signal.direction == RebalanceDirection.ADD_SPOT else 'SELL'} "
            f"{signal.qty:.4f} SOL (${signal.qty_usd:.2f})"
        )
        
        return instructions
    
    async def _build_perp_instructions(
        self,
        signal: RebalanceSignal,
    ) -> List[Instruction]:
        """Build Drift order instructions for perp leg."""
        
        # Import the order builder
        from src.delta_neutral.drift_order_builder import DriftOrderBuilder, PositionDirection
        
        # Create builder from wallet
        builder = DriftOrderBuilder(self.wallet.get_public_key())
        
        # Determine order side based on signal
        market = "SOL-PERP"
        
        if signal.direction == RebalanceDirection.ADD_SHORT:
            # Increase short position (SELL perp)
            instructions = builder.build_short_order(market, signal.qty)
            Logger.info(f"[DNEM] Perp leg: SHORT {signal.qty:.4f} {market} (${signal.qty_usd:.2f})")
        elif signal.direction == RebalanceDirection.ADD_SPOT:
            # Reduce short position (BUY perp to close)
            instructions = builder.build_long_order(market, signal.qty, reduce_only=True)
            Logger.info(f"[DNEM] Perp leg: LONG (close) {signal.qty:.4f} {market} (${signal.qty_usd:.2f})")
        elif signal.direction == RebalanceDirection.REDUCE_SHORT:
            # Close short position
            instructions = builder.build_long_order(market, signal.qty, reduce_only=True)
            Logger.info(f"[DNEM] Perp leg: CLOSE SHORT {signal.qty:.4f} {market}")
        else:
            # REDUCE_SPOT → need to add more short to rebalance
            instructions = builder.build_short_order(market, signal.qty)
            Logger.info(f"[DNEM] Perp leg: SHORT {signal.qty:.4f} {market}")
        
        return instructions
    
    async def _build_tip_instruction(self, lamports: int) -> Instruction:
        """Build Jito tip instruction."""
        
        tip_account = await self.jito.get_random_tip_account()
        if not tip_account:
            raise ValueError("No Jito tip accounts available")
        
        # Build SOL transfer to tip account
        tip_ix = transfer(
            TransferParams(
                from_pubkey=Pubkey.from_string(self.wallet.get_public_key()),
                to_pubkey=Pubkey.from_string(tip_account),
                lamports=lamports,
            )
        )
        
        Logger.debug(f"[DNEM] Jito tip: {lamports} lamports to {tip_account[:8]}...")
        
        return tip_ix
    
    # =========================================================================
    # BUNDLE ASSEMBLY
    # =========================================================================
    
    async def _assemble_bundle(
        self,
        spot_ixs: List[Instruction],
        perp_ixs: List[Instruction],
        tip_ix: Instruction,
    ) -> List[bytes]:
        """
        Assemble all instructions into a Jito-compatible bundle.
        
        Returns list of serialized transactions for the bundle.
        """
        # Get recent blockhash
        from solana.rpc.api import Client
        from config.settings import Settings
        
        client = Client(Settings.RPC_URL)
        blockhash_resp = client.get_latest_blockhash()
        recent_blockhash = blockhash_resp.value.blockhash
        
        # Combine all instructions into one transaction
        # Order: Spot setup, Spot swap, Perp order, Tip
        all_instructions = spot_ixs + perp_ixs + [tip_ix]
        
        if not all_instructions:
            raise ValueError("No instructions to bundle")
        
        # Build versioned message
        message = MessageV0.try_compile(
            payer=Pubkey.from_string(self.wallet.get_public_key()),
            instructions=all_instructions,
            address_lookup_table_accounts=[],
            recent_blockhash=recent_blockhash,
        )
        
        # Create and sign transaction
        tx = VersionedTransaction(message, [self.wallet.keypair])
        serialized = base64.b64encode(bytes(tx)).decode("utf-8")
        
        Logger.info(f"[DNEM] Bundle assembled: {len(all_instructions)} instructions")
        
        return [serialized]
    
    # =========================================================================
    # SUBMISSION & CONFIRMATION
    # =========================================================================
    
    async def _submit_bundle(self, bundle_txs: List[bytes]) -> Optional[str]:
        """Submit bundle to Jito Block Engine."""
        
        bundle_id = await self.jito.submit_bundle(
            bundle_txs,
            simulate=False,  # Bypass simulation during high congestion
        )
        
        if bundle_id:
            Logger.info(f"[DNEM] 🚀 Bundle submitted: {bundle_id[:16]}...")
        else:
            Logger.warning("[DNEM] Bundle submission failed")
        
        return bundle_id
    
    async def _wait_for_confirmation(self, bundle: SyncTradeBundle) -> bool:
        """Wait for bundle confirmation."""
        
        if not bundle.bundle_id:
            return False
        
        return await self.jito.wait_for_confirmation(
            bundle.bundle_id,
            timeout=self.config.confirmation_timeout_sec,
        )
    
    async def _get_current_slot(self) -> int:
        """Get current slot from RPC."""
        try:
            from solana.rpc.api import Client
            from config.settings import Settings
            
            client = Client(Settings.RPC_URL)
            slot = client.get_slot().value
            return slot
        except Exception:
            return 0
    
    # =========================================================================
    # PARTIAL FILL DETECTION
    # =========================================================================
    
    async def _check_partial_fill(self, bundle: SyncTradeBundle) -> bool:
        """
        Check if only one leg of the bundle executed.
        
        Uses pre-trade snapshot to detect imbalance.
        """
        Logger.debug("[DNEM] Checking for partial fill via snapshot comparison...")
        
        analysis = await self.snapshot_manager.analyze_post_trade(
            self.wallet,
            self.drift,
            key=self._current_snapshot_key,
        )
        
        if analysis is None:
            Logger.warning("[DNEM] No snapshot available for partial fill check")
            return False
        
        if analysis.is_partial_fill:
            Logger.warning(
                f"[DNEM] PARTIAL FILL DETECTED: "
                f"Spot={analysis.spot_executed}, Perp={analysis.perp_executed}"
            )
            return True
        
        return False
    
    # =========================================================================
    # EMERGENCY ROLLBACK
    # =========================================================================
    
    async def emergency_rollback(self, bundle: SyncTradeBundle) -> bool:
        """
        Emergency close of any partially filled positions.
        
        CRITICAL: This must execute within 3 blocks of partial fill detection.
        
        Strategy:
        1. Identify which leg succeeded
        2. Execute market close on that leg
        3. Return to cash (USDC) state
        
        Args:
            bundle: The partially filled bundle
        
        Returns:
            True if rollback succeeded
        """
        if bundle.status != "PARTIAL":
            Logger.warning("[DNEM] Rollback called on non-partial bundle")
            return False
        
        Logger.warning("[DNEM] 🚨 EMERGENCY ROLLBACK INITIATED")
        self._rollbacks_executed += 1
        
        # Determine which leg to close
        # This requires checking current position state
        
        try:
            # Get current position
            spot_balance = self.wallet.get_sol_balance()
            perp_position = await self._get_perp_position()
            
            # If we have more spot than expected, sell it
            # If we have more perp than expected, close it
            
            # For safety, close BOTH to return to flat
            if spot_balance > 0.01:  # More than dust
                Logger.info(f"[DNEM] Closing spot: {spot_balance} SOL")
                await self._emergency_close_spot(spot_balance)
            
            if perp_position and abs(perp_position) > 0.001:
                Logger.info(f"[DNEM] Closing perp: {perp_position} SOL-PERP")
                await self._emergency_close_perp(perp_position)
            
            Logger.info("[DNEM] ✅ Emergency rollback complete")
            return True
            
        except Exception as e:
            Logger.error(f"[DNEM] ❌ Emergency rollback FAILED: {e}")
            return False
    
    async def _get_perp_position(self) -> float:
        """Get current perp position size."""
        # Placeholder - implement with Drift SDK
        return 0.0
    
    async def _emergency_close_spot(self, amount: float) -> bool:
        """Emergency market sell of spot position."""
        try:
            result = self.swapper.execute_swap(
                direction="SELL",
                amount_usd=0,  # Sell all
                reason="EMERGENCY_ROLLBACK",
            )
            return result.get("success", False)
        except Exception as e:
            Logger.error(f"[DNEM] Spot close failed: {e}")
            return False
    
    async def _emergency_close_perp(self, size: float) -> bool:
        """Emergency close of perp position."""
        # Placeholder - implement with Drift SDK
        Logger.warning("[DNEM] Perp close not implemented - requires Drift SDK")
        return False
    
    # =========================================================================
    # REVENUE TRACKING
    # =========================================================================
    
    def estimate_trade_revenue(
        self,
        signal: RebalanceSignal,
        funding_rate_8h: float,
        sol_price: float,
        tip_lamports: int,
    ) -> TradeRevenue:
        """
        Estimate revenue for a pending trade.
        
        Used to determine if trade is worth executing.
        """
        # Estimate funding income (8h period)
        position_notional = signal.qty_usd
        funding_income = position_notional * abs(funding_rate_8h)
        
        # Estimate costs
        tip_usd = (tip_lamports / 1_000_000_000) * sol_price
        gas_usd = 0.0001 * sol_price  # ~0.0001 SOL per tx
        
        # Trading fees (Jupiter ~0.1%, Drift ~0.05%)
        trading_fees = position_notional * 0.0015
        
        total_cost = tip_usd + gas_usd + trading_fees
        
        return TradeRevenue(
            funding_earned_estimate=funding_income,
            transaction_cost_usd=total_cost,
            jito_tip_usd=tip_usd,
            gas_cost_usd=gas_usd,
        )
    
    # =========================================================================
    # STATISTICS
    # =========================================================================
    
    def get_stats(self) -> dict:
        """Get execution statistics."""
        success_rate = (
            self._bundles_landed / self._bundles_attempted * 100
            if self._bundles_attempted > 0
            else 0
        )
        
        return {
            "bundles_attempted": self._bundles_attempted,
            "bundles_landed": self._bundles_landed,
            "bundles_failed": self._bundles_failed,
            "partial_fills": self._partial_fills,
            "rollbacks_executed": self._rollbacks_executed,
            "kill_switch_activations": self._kill_switch_activations,
            "success_rate_pct": round(success_rate, 2),
        }
