"""
ExecutionPod - The "Striker" Pod
================================
V140: Narrow Path Infrastructure (Phase 16)

The ExecutionPod bridges the gap between HopPod discovery and actual
execution via the Rust MultiHopBuilder. It consumes HOP_OPPORTUNITY
signals from the SignalBus and executes profitable cycles atomically.

Responsibilities:
1. Listen for high-priority HOP_OPPORTUNITY signals
2. Validate profitability against current MarketContext
3. Build swap instructions via Jupiter/DEX builders
4. Submit atomic bundle via MultiHopBuilder
5. Track execution results and update statistics
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from enum import Enum

from src.shared.system.logging import Logger
from src.engine.pod_manager import BasePod, PodConfig, PodSignal, PodType


class ExecutionMode(Enum):
    """Execution mode for the pod."""

    PAPER = "paper"  # Simulate execution, no real transactions, no builder
    LIVE = "live"  # Real execution with Jito bundles
    GHOST = "ghost"  # Dry run: Build real bundle, but don't submit
    DISABLED = "disabled"  # Consume signals but don't execute


@dataclass
class ExecutionResult:
    """Result of an execution attempt."""

    cycle_id: str
    success: bool
    signature: Optional[str] = None
    error: Optional[str] = None
    expected_profit_pct: float = 0.0
    actual_profit_pct: float = 0.0
    execution_time_ms: float = 0.0
    leg_count: int = 0
    tip_lamports: int = 0
    mode: str = "unknown"
    timestamp: float = field(default_factory=time.time)


class ExecutionPod(BasePod):
    """
    The "Striker" - executes profitable cycles found by HopPods.

    This pod acts as the final link in the chain:
    HopPod → SignalBus → ExecutionPod → MultiHopBuilder → Jito

    It applies final profitability checks using real-time MarketContext
    and only executes when confident of profit after all fees and tips.
    """

    def __init__(
        self,
        config: PodConfig,
        signal_callback: Callable[[PodSignal], None],
        mode: ExecutionMode = ExecutionMode.PAPER,
        min_profit_pct: float = 0.15,
        max_execution_per_minute: int = 5,
    ):
        super().__init__(config, signal_callback)

        self.mode = mode
        self.min_profit_pct = min_profit_pct
        self.max_execution_per_minute = max_execution_per_minute

        # Rust MultiHopBuilder (lazy init)
        self._hop_builder = None
        self._jupiter_client = None

        # Execution queue (signals waiting to be processed)
        self._queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=100)

        # Statistics
        self.executions_attempted = 0
        self.executions_succeeded = 0
        self.executions_failed = 0
        self.total_profit_lamports = 0
        self.execution_history: List[ExecutionResult] = []

        # Rate limiting
        self._execution_times: List[float] = []

        Logger.info(
            f"[ExecutionPod] Initialized in {mode.value} mode (min_profit={min_profit_pct}%)"
        )

    def set_mode(self, mode: ExecutionMode):
        """Runtime mode switch."""
        self.mode = mode
        Logger.info(f"[ExecutionPod] Switched to {mode.value} mode")
        # Re-init builders if switching to LIVE/GHOST
        if mode in [ExecutionMode.LIVE, ExecutionMode.GHOST]:
            self._init_builders()

    def _init_builders(self):
        """Lazy initialization of execution infrastructure."""
        if self._hop_builder is None:
            try:
                from phantom_core import MultiHopBuilder
                from config.settings import Settings

                private_key = getattr(Settings, "PRIVATE_KEY_BASE58", None)
                if not private_key:
                    if self.mode == ExecutionMode.LIVE:
                        Logger.warning(
                            "[ExecutionPod] No private key, falling back to PAPER"
                        )
                        self.mode = ExecutionMode.PAPER
                    elif self.mode == ExecutionMode.GHOST:
                        # Ghost execution needs a builder, use dummy key if needed or warn
                        Logger.warning("[ExecutionPod] No private key for GHOST mode")
                else:
                    self._hop_builder = MultiHopBuilder(
                        private_key,
                        cu_per_leg=60_000,
                        min_tip_lamports=10_000,
                    )
                    Logger.info(
                        f"[ExecutionPod] MultiHopBuilder initialized: {self._hop_builder.pubkey()[:8]}..."
                    )
            except ImportError:
                Logger.warning(
                    "[ExecutionPod] Rust extension not available, using PAPER"
                )
                self.mode = ExecutionMode.PAPER

        if self._jupiter_client is None:
            from src.engine.dex_builders import get_jupiter_client

            self._jupiter_client = get_jupiter_client(slippage_bps=30)

        # Initialize Ghost Validator if in GHOST mode
        if (
            self.mode == ExecutionMode.GHOST
            and getattr(self, "_ghost_validator", None) is None
        ):
            try:
                from src.engine.ghost_validator import GhostValidator
                from src.engine.dex_builders import MultiHopQuoteBuilder

                # We need a QuoteBuilder for validation
                # Reuse existing one or create new? QuoteBuilder needs jupiter_client
                quote_builder = MultiHopQuoteBuilder(self._jupiter_client)
                self._ghost_validator = GhostValidator(quote_builder)
                Logger.info("[ExecutionPod] 👻 GhostValidator initialized")
            except Exception as e:
                Logger.warning(f"[ExecutionPod] Failed to init GhostValidator: {e}")
                self._ghost_validator = None

    async def enqueue_opportunity(self, opportunity_data: Dict[str, Any]):
        """
        Add an opportunity to the execution queue.

        Called by Director when a high-priority HOP_OPPORTUNITY is received.
        """
        try:
            self._queue.put_nowait(opportunity_data)
        except asyncio.QueueFull:
            Logger.warning("[ExecutionPod] Execution queue full, dropping opportunity")

    async def _scan(self) -> List[PodSignal]:
        """
        Process opportunities from the queue.

        Unlike other pods that actively scan, ExecutionPod waits for
        opportunities to be pushed to its queue.
        """
        signals = []

        # Process up to 3 opportunities per scan cycle
        for _ in range(3):
            try:
                opportunity = self._queue.get_nowait()
                result = await self._execute_opportunity(opportunity)

                if result:
                    signals.append(
                        PodSignal(
                            pod_id=self.id,
                            pod_type=PodType.SCOUT,  # Reuse SCOUT for execution results
                            signal_type="EXECUTION_RESULT",
                            priority=5,
                            data={
                                "result": result.__dict__,
                                "mode": self.mode.value,
                            },
                        )
                    )

            except asyncio.QueueEmpty:
                break

        return signals

    async def _execute_opportunity(
        self, opp: Dict[str, Any]
    ) -> Optional[ExecutionResult]:
        """
        Execute a single opportunity.

        Args:
            opp: Opportunity data from HopPod signal

        Returns:
            ExecutionResult or None if skipped
        """
        start_time = time.time()

        # Rate limiting check
        if not self._check_rate_limit_execution():
            Logger.debug("[ExecutionPod] Rate limit reached, skipping")
            return None

        cycle_id = f"exec_{int(time.time() * 1000)}"
        path = opp.get("path", [])
        expected_profit_pct = opp.get("profit_pct", 0)
        hop_count = opp.get("hop_count", len(path) - 1)

        # Validate basic requirements
        if len(path) < 3:
            return ExecutionResult(
                cycle_id=cycle_id,
                success=False,
                error="Invalid path length",
                expected_profit_pct=expected_profit_pct,
                leg_count=hop_count,
            )

        # Check MarketContext for adjusted profitability
        from src.shared.models.context import get_market_context

        context = get_market_context()

        adjusted_threshold = context.get_adjusted_threshold(self.min_profit_pct)

        if expected_profit_pct < adjusted_threshold:
            Logger.debug(
                f"[ExecutionPod] Profit {expected_profit_pct:.3f}% < threshold {adjusted_threshold:.3f}%"
            )
            return ExecutionResult(
                cycle_id=cycle_id,
                success=False,
                error=f"Below adjusted threshold ({adjusted_threshold:.2f}%)",
                expected_profit_pct=expected_profit_pct,
                leg_count=hop_count,
            )

        # Check if trading is paused
        if context.should_pause_trading():
            Logger.debug(f"[ExecutionPod] Trading paused: {context.reason}")
            return ExecutionResult(
                cycle_id=cycle_id,
                success=False,
                error=f"Trading paused: {context.reason}",
                expected_profit_pct=expected_profit_pct,
                leg_count=hop_count,
            )

        self.executions_attempted += 1

        # Execute based on mode
        if self.mode == ExecutionMode.PAPER:
            result = await self._execute_paper(cycle_id, opp, context)
        elif self.mode in [ExecutionMode.LIVE, ExecutionMode.GHOST]:
            result = await self._execute_live(
                cycle_id, opp, context, dry_run=(self.mode == ExecutionMode.GHOST)
            )
        else:
            result = ExecutionResult(
                cycle_id=cycle_id,
                success=False,
                error="Execution disabled",
                expected_profit_pct=expected_profit_pct,
                leg_count=hop_count,
            )

        # Update stats
        result.execution_time_ms = (time.time() - start_time) * 1000
        result.mode = self.mode.value
        self._execution_times.append(time.time())
        self.execution_history.append(result)

        if len(self.execution_history) > 100:
            self.execution_history = self.execution_history[-50:]

        if result.success:
            self.executions_succeeded += 1
            Logger.info(
                f"[ExecutionPod] ✅ Executed {hop_count}-hop | +{result.expected_profit_pct:.3f}% ({self.mode.value})"
            )
        else:
            self.executions_failed += 1
            Logger.debug(
                f"[ExecutionPod] ❌ Failed ({self.mode.value}): {result.error}"
            )

        return result

    async def _execute_paper(
        self,
        cycle_id: str,
        opp: Dict[str, Any],
        context,
    ) -> ExecutionResult:
        """
        Paper trade execution - simulate without real transactions.
        """
        path = opp.get("path", [])
        expected_profit_pct = opp.get("profit_pct", 0)
        hop_count = opp.get("hop_count", len(path) - 1)

        # Simulate getting quotes (optional - can skip for speed)
        # In paper mode, we just log the theoretical trade

        Logger.info(
            f"[ExecutionPod] 📝 PAPER TRADE: {hop_count}-hop | "
            f"{path[0][:6]}→...→{path[-1][:6]} | +{expected_profit_pct:.3f}%"
        )

        return ExecutionResult(
            cycle_id=cycle_id,
            success=True,
            signature=f"paper_{cycle_id}",
            expected_profit_pct=expected_profit_pct,
            actual_profit_pct=expected_profit_pct,  # Assume perfect execution
            leg_count=hop_count,
            tip_lamports=0,
            mode="paper",
        )

    async def _execute_live(
        self,
        cycle_id: str,
        opp: Dict[str, Any],
        context,
        dry_run: bool = False,
    ) -> ExecutionResult:
        """
        Live execution via MultiHopBuilder and Jito.
        """
        self._init_builders()

        if not self._hop_builder:
            return ExecutionResult(
                cycle_id=cycle_id,
                success=False,
                error="MultiHopBuilder not available",
                expected_profit_pct=opp.get("profit_pct", 0),
                leg_count=opp.get("hop_count", 0),
            )

        path = opp.get("path", [])
        pools = opp.get("pools", [])
        expected_profit_pct = opp.get("profit_pct", 0)
        hop_count = opp.get("hop_count", len(path) - 1)

        try:
            # 1. Get quotes for each leg via Jupiter
            from src.engine.dex_builders import MultiHopQuoteBuilder

            quote_builder = MultiHopQuoteBuilder(self._jupiter_client)

            # Default to 1 SOL input for now (configurable)
            input_amount = 1_000_000_000  # 1 SOL in lamports

            quotes = await quote_builder.build_cycle_quotes(
                path=path,
                input_amount=input_amount,
                slippage_bps=30,
            )

            if not quotes:
                return ExecutionResult(
                    cycle_id=cycle_id,
                    success=False,
                    error="Failed to build quotes",
                    expected_profit_pct=expected_profit_pct,
                    leg_count=hop_count,
                )

            # 2. Validate still profitable after real quotes
            profit_metrics = quote_builder.calculate_cycle_profit(quotes, input_amount)
            actual_profit_pct = profit_metrics["profit_pct"]

            adjusted_threshold = context.get_adjusted_threshold(self.min_profit_pct)
            if actual_profit_pct < adjusted_threshold:
                return ExecutionResult(
                    cycle_id=cycle_id,
                    success=False,
                    error=f"Real profit {actual_profit_pct:.3f}% below threshold",
                    expected_profit_pct=expected_profit_pct,
                    actual_profit_pct=actual_profit_pct,
                    leg_count=hop_count,
                )

            # 3. Build swap instructions from quotes
            swap_legs = []
            for i, quote in enumerate(quotes):
                instructions = await self._jupiter_client.get_swap_instructions(
                    quote=quote,
                    user_public_key=self._hop_builder.pubkey(),
                )
                if instructions:
                    for ix in instructions:
                        # Convert to Rust SwapLeg
                        from phantom_core import SwapLeg

                        swap_legs.append(
                            SwapLeg(
                                pool_address=ix.pool_address,
                                dex=ix.dex,
                                input_mint=ix.input_mint,
                                output_mint=ix.output_mint,
                                instruction_data=list(ix.instruction_data),
                            )
                        )

            if len(swap_legs) != hop_count:
                return ExecutionResult(
                    cycle_id=cycle_id,
                    success=False,
                    error=f"Incomplete swap legs: got {len(swap_legs)}, expected {hop_count}",
                    expected_profit_pct=expected_profit_pct,
                    actual_profit_pct=actual_profit_pct,
                    leg_count=len(swap_legs),
                )

            # 4. Calculate tip based on congestion
            congestion_multiplier = context.global_min_profit_adj / 0.15  # Normalize
            expected_profit_lamports = int(profit_metrics["profit_amount"])

            tip_lamports = self._hop_builder.calculate_tip(
                leg_count=hop_count,
                congestion_multiplier=congestion_multiplier,
                expected_profit_lamports=expected_profit_lamports,
            )

            # 5. Get fresh blockhash
            from src.shared.infrastructure.rpc import get_recent_blockhash

            blockhash = await get_recent_blockhash()

            if not blockhash:
                return ExecutionResult(
                    cycle_id=cycle_id,
                    success=False,
                    error="Failed to get blockhash",
                    expected_profit_pct=expected_profit_pct,
                    actual_profit_pct=actual_profit_pct,
                    leg_count=hop_count,
                )

            # 6. Build and submit (or dry run)
            if dry_run:
                Logger.info(
                    f"[ExecutionPod] 👻 GHOST RUN: Skipping submission for {hop_count}-hop bundle"
                )
                Logger.info(
                    f"               Tip: {tip_lamports} | Expected Profit: {actual_profit_pct:.3f}%"
                )
                signature = f"ghost_{cycle_id}"

                # Trigger Ghost Validation (Look-Back)
                if self._ghost_validator:
                    asyncio.create_task(
                        self._ghost_validator.validate_later(
                            cycle_id=cycle_id,
                            path=path,
                            original_profit=actual_profit_pct,
                            input_amount=input_amount,
                        )
                    )
            else:
                signature = self._hop_builder.build_and_submit(
                    swap_legs=swap_legs,
                    tip_lamports=tip_lamports,
                    recent_blockhash=blockhash,
                    expected_profit_pct=actual_profit_pct,
                )

            return ExecutionResult(
                cycle_id=cycle_id,
                success=True,
                signature=signature,
                expected_profit_pct=expected_profit_pct,
                actual_profit_pct=actual_profit_pct,
                leg_count=hop_count,
                tip_lamports=tip_lamports,
                mode="ghost" if dry_run else "live",
            )

        except Exception as e:
            Logger.error(f"[ExecutionPod] Live execution error: {e}")
            return ExecutionResult(
                cycle_id=cycle_id,
                success=False,
                error=str(e),
                expected_profit_pct=expected_profit_pct,
                leg_count=hop_count,
                mode="ghost" if dry_run else "live",
            )

    def _check_rate_limit_execution(self) -> bool:
        """Check if we're within execution rate limits."""
        now = time.time()
        # Remove executions older than 1 minute
        self._execution_times = [t for t in self._execution_times if now - t < 60]
        return len(self._execution_times) < self.max_execution_per_minute

    def get_stats(self) -> Dict[str, Any]:
        """Get ExecutionPod statistics."""
        success_rate = (
            self.executions_succeeded / self.executions_attempted * 100
            if self.executions_attempted > 0
            else 0
        )

        # Count ghost validations if any
        ghost_validations = (
            self._ghost_validator.pending_validations if self._ghost_validator else 0
        )

        return {
            "pod_id": self.id,
            "pod_type": "execution",
            "status": self.status.value,
            "mode": self.mode.value,
            "executions_attempted": self.executions_attempted,
            "executions_succeeded": self.executions_succeeded,
            "executions_failed": self.executions_failed,
            "success_rate_pct": round(success_rate, 1),
            "queue_size": self._queue.qsize(),
            "min_profit_pct": self.min_profit_pct,
            "uptime_seconds": time.time() - self.created_at,
            "recent_history": [r.__dict__ for r in self.execution_history[-5:]],
            "ghost_pending": ghost_validations,
        }
