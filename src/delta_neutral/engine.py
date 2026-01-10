"""
DNEM Main Engine
================
Unified entry point for Delta Neutral Execution Module.

Supports both PAPER and LIVE modes by swapping adapters.

Usage:
    # Paper mode (simulation)
    python -m src.delta_neutral.engine --mode paper
    
    # Live mode (mainnet with real funds)
    python -m src.delta_neutral.engine --mode live --balance 12.0
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional, Literal
from dataclasses import dataclass

import traceback
from src.shared.system.logging import Logger


# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass
class DNEMConfig:
    """Configuration for Delta Neutral Engine."""
    
    # Mode
    mode: Literal["paper", "live"] = "paper"
    
    # Capital
    initial_balance_usd: float = 12.0
    leverage: float = 1.0
    
    # Thresholds
    drift_threshold_pct: float = 0.5
    max_latency_ms: float = 500.0
    min_funding_rate: float = 0.0001  # 0.01% minimum to trade
    
    # Execution
    jito_tip_lamports: int = 10_000
    jito_region: str = "ny"
    
    # Monitoring
    poll_interval_ms: int = 1000
    use_redis: bool = False


# =============================================================================
# MAIN ENGINE
# =============================================================================


class DeltaNeutralEngine:
    """
    Unified Delta Neutral trading engine.
    
    Automatically configures adapters based on mode:
    - PAPER: Uses mock adapters for simulation
    - LIVE: Uses real JitoAdapter, JupiterSwapper, DriftAdapter
    
    Example:
        >>> engine = DeltaNeutralEngine(DNEMConfig(mode="paper"))
        >>> await engine.initialize()
        >>> await engine.start()
    """
    
    def __init__(self, config: Optional[DNEMConfig] = None):
        self.config = config or DNEMConfig()
        
        # Components (initialized in initialize())
        self.wallet = None
        self.swapper = None
        self.drift = None
        self.jito = None
        self.latency_monitor = None
        self.sync_executor = None
        self.neutrality_monitor = None
        self.funding_feed = None
        
        # State
        self._running = False
        self._position_open = False
    
    async def initialize(self) -> bool:
        """
        Initialize all components based on mode.
        
        Returns:
            True if initialization succeeded
        """
        Logger.info("=" * 60)
        Logger.info(f"[DNEM] Initializing in {self.config.mode.upper()} mode")
        Logger.info(f"[DNEM] Balance: ${self.config.initial_balance_usd}")
        Logger.info("=" * 60)
        
        try:
            if self.config.mode == "paper":
                await self._init_paper_mode()
            else:
                await self._init_live_mode()
            
            # Initialize sync executor
            from src.delta_neutral.sync_execution import SyncExecution, SyncExecutionConfig
            
            exec_config = SyncExecutionConfig(
                max_latency_ms=self.config.max_latency_ms,
                default_tip_lamports=self.config.jito_tip_lamports,
            )
            
            self.sync_executor = SyncExecution(
                swapper=self.swapper,
                drift=self.drift,
                jito=self.jito,
                latency_monitor=self.latency_monitor,
                wallet=self.wallet,
                config=exec_config,
                use_redis_snapshots=self.config.use_redis,
            )
            
            # Initialize neutrality monitor
            from src.delta_neutral.neutrality_monitor import NeutralityMonitor, MonitorConfig
            
            monitor_config = MonitorConfig(
                poll_interval_ms=self.config.poll_interval_ms,
                drift_threshold_pct=self.config.drift_threshold_pct,
                auto_execute=False,  # Manual control for safety
            )
            
            self.neutrality_monitor = NeutralityMonitor(
                wallet=self.wallet,
                drift=self.drift,
                price_cache=self._get_price_cache(),
                sync_executor=self.sync_executor,
                config=monitor_config,
            )
            
            Logger.info("[DNEM] ✅ Initialization complete")
            return True
            
        except Exception as e:
            Logger.error(f"[DNEM] ❌ Initialization failed: {e}")
            traceback.print_exc()
            return False
    
    async def _init_paper_mode(self):
        """Initialize paper trading adapters."""
        from src.delta_neutral.paper_engine import (
            MockWallet,
            MockJitoAdapter,
            MockDriftAdapter,
            MockLatencyMonitor,
        )
        
        self.wallet = MockWallet(initial_usdc=self.config.initial_balance_usd)
        self.jito = MockJitoAdapter()
        self.drift = MockDriftAdapter()
        self.latency_monitor = MockLatencyMonitor()
        
        # Mock swapper for paper mode
        self.swapper = self._create_mock_swapper()
        
        Logger.info("[DNEM] Paper mode adapters loaded")
    
    async def _init_live_mode(self):
        """Initialize live trading adapters."""
        # Wallet
        from src.shared.execution.wallet import WalletManager
        self.wallet = WalletManager()
        
        if not self.wallet.keypair:
            raise RuntimeError("No wallet keypair found. Set SOLANA_PRIVATE_KEY env var.")
        
        Logger.info(f"[DNEM] Wallet: {self.wallet.get_public_key()}")
        
        # Jupiter Swapper
        from src.shared.execution.swapper import JupiterSwapper
        self.swapper = JupiterSwapper(self.wallet)
        
        # Jito Adapter
        from src.shared.infrastructure.jito_adapter import JitoAdapter
        self.jito = JitoAdapter(region=self.config.jito_region)
        
        # Check Jito availability
        # Check Jito availability with retries
        jito_connected = False
        for i in range(5):
            if await self.jito.is_available():
                jito_connected = True
                break
            Logger.warning(f"[DNEM] Jito init failed (attempt {i+1}/5). Retrying...")
            await asyncio.sleep(2.0)
            
        if not jito_connected:
            raise RuntimeError("Jito Block Engine not available after 5 attempts")
        
        Logger.info("[DNEM] Jito Block Engine connected")
        
        # Drift Adapter (simplified wrapper)
        from src.delta_neutral.drift_order_builder import DriftAdapter
        self.drift = DriftAdapter("mainnet")
        self.drift.set_wallet(self.wallet)
        
        # Latency Monitor
        from src.core.latency_monitor import LatencyMonitor
        self.latency_monitor = LatencyMonitor()
        
        # Funding Feed
        from src.shared.feeds.drift_funding import DriftFundingFeed
        self.funding_feed = DriftFundingFeed()
        
        Logger.info("[DNEM] Live mode adapters loaded")
    
    def _create_mock_swapper(self):
        """Create a mock swapper for paper mode."""
        class MockSwapper:
            def __init__(self, wallet):
                self.wallet = wallet
            
            async def get_quote(self, input_mint, output_mint, amount, slippage=100):
                # Return mock quote
                return {
                    "inputMint": input_mint,
                    "outputMint": output_mint,
                    "inAmount": str(amount),
                    "outAmount": str(int(amount * 0.999)),  # 0.1% slippage
                }
            
            async def get_swap_instructions(self, quote):
                # Return empty instructions for paper mode
                return []
            
            def execute_swap(self, direction, amount_usd, reason, **kwargs):
                return {"success": True}
        
        return MockSwapper(self.wallet)
    
    def _get_price_cache(self):
        """Get price cache (mock for paper, real for live)."""
        class MockPriceCache:
            def get_price(self, symbol):
                return 150.0  # Default SOL price
        
        if self.config.mode == "paper":
            return MockPriceCache()
        
        try:
            from src.core.shared_cache import SharedPriceCache
            return SharedPriceCache
        except ImportError:
            return MockPriceCache()
    
    # =========================================================================
    # TRADING OPERATIONS
    # =========================================================================
    
    async def open_position(self) -> bool:
        """
        Open the initial delta-neutral position.
        
        Allocates capital 50/50 to spot and perp short.
        """
        from src.delta_neutral.position_calculator import calculate_position_size
        from src.delta_neutral.types import RebalanceSignal, RebalanceDirection
        
        Logger.info("[DNEM] Opening delta-neutral position...")
        
        # Get current price
        sol_price_data = self._get_price_cache().get_price("SOL")
        
        # Handle tuple return (price, timestamp)
        if isinstance(sol_price_data, tuple):
            sol_price = float(sol_price_data[0]) if sol_price_data[0] else 150.0
        else:
            sol_price = float(sol_price_data) if sol_price_data else 150.0
        
        # Calculate position sizes
        spot_qty, perp_qty = calculate_position_size(
            total_balance_usd=self.config.initial_balance_usd,
            leverage=self.config.leverage,
            spot_price=sol_price,
        )
        
        capital_per_leg = self.config.initial_balance_usd / 2
        
        # Create entry signal
        signal = RebalanceSignal(
            direction=RebalanceDirection.ADD_SPOT,
            qty=spot_qty,
            qty_usd=capital_per_leg,
            current_drift_pct=100.0,  # No position = 100% drift
            reason="Initial position open",
            urgency=1,
        )
        
        if self.config.mode == "paper":
            # Paper mode: Use wallet directly
            self.wallet.buy_sol(capital_per_leg, sol_price)
            self.drift.open_short(spot_qty, sol_price)
            self._position_open = True
            Logger.info(f"[DNEM] Position opened: {spot_qty:.4f} SOL spot + short")
            return True
        else:
            # Live mode: Use SyncExecution
            bundle = await self.sync_executor.execute_sync_trade(signal, sol_price)
            
            if bundle.status == "CONFIRMED":
                self._position_open = True
                Logger.info(f"[DNEM] Position opened via Jito bundle: {bundle.bundle_id}")
                return True
            elif bundle.needs_rollback:
                await self.sync_executor.emergency_rollback(bundle)
                return False
            else:
                Logger.error(f"[DNEM] Position open failed: {bundle.status}")
                return False
    
    async def start_monitoring(self):
        """Start the neutrality monitoring loop."""
        if not self._position_open:
            Logger.warning("[DNEM] No position open. Call open_position() first.")
            return
        
        Logger.info("[DNEM] Starting neutrality monitor...")
        
        # Set callback for rebalance signals
        self.neutrality_monitor.on_rebalance_needed = self._handle_rebalance
        
        await self.neutrality_monitor.start()
    
    async def _handle_rebalance(self, signal):
        """Handle rebalance signal from monitor."""
        Logger.info(f"[DNEM] Rebalance signal received: {signal}")
        
        sol_price = self._get_price_cache().get_price("SOL")
        
        # Safety gate check (live mode only)
        if self.config.mode == "live":
            from src.delta_neutral.safety_gates import SafetyGate
            
            gate = SafetyGate()
            
            # Estimate expected profit from funding
            expected_profit = signal.qty_usd * 0.0001  # Conservative 0.01% rate
            
            can_execute = await gate.can_execute(
                wallet=self.wallet,
                latency_monitor=self.latency_monitor,
                expected_profit_usd=expected_profit,
                trade_amount_usd=signal.qty_usd,
                sol_price=sol_price,
                jito_tip_lamports=self.config.jito_tip_lamports,
            )
            
            if not can_execute:
                Logger.warning("[DNEM] SafetyGate blocked trade - skipping")
                return
        
        # Estimate profitability before executing
        revenue = self.sync_executor.estimate_trade_revenue(
            signal,
            funding_rate_8h=0.0001,  # Conservative estimate
            sol_price=sol_price,
            tip_lamports=self.config.jito_tip_lamports,
        )
        
        if not revenue.is_profitable:
            Logger.warning(f"[DNEM] Skipping unprofitable rebalance: {revenue}")
            return
        
        if self.config.mode == "live":
            bundle = await self.sync_executor.execute_sync_trade(signal, sol_price)
            
            if bundle.needs_rollback:
                await self.sync_executor.emergency_rollback(bundle)
    
    async def stop(self):
        """Stop the engine and close positions."""
        Logger.info("[DNEM] Stopping engine...")
        
        if self.neutrality_monitor:
            await self.neutrality_monitor.stop()
        
        if self.jito and hasattr(self.jito, 'close'):
            await self.jito.close()
        
        self._running = False
        Logger.info("[DNEM] Engine stopped")
    
    def get_status(self) -> dict:
        """Get current engine status."""
        status = {
            "mode": self.config.mode,
            "running": self._running,
            "position_open": self._position_open,
        }
        
        if self.neutrality_monitor:
            status["monitor"] = self.neutrality_monitor.get_stats()
        
        if self.sync_executor:
            status["executor"] = self.sync_executor.get_stats()
        
        return status


# =============================================================================
# CLI
# =============================================================================


async def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Delta Neutral Execution Engine")
    parser.add_argument("--mode", choices=["paper", "live"], default="paper")
    parser.add_argument("--balance", type=float, default=12.0)
    parser.add_argument("--cycles", type=int, default=5, help="Funding cycles to simulate")
    parser.add_argument("--rate", type=float, default=0.0001, help="Simulated funding rate")
    
    args = parser.parse_args()
    
    config = DNEMConfig(
        mode=args.mode,
        initial_balance_usd=args.balance,
    )
    
    engine = DeltaNeutralEngine(config)
    
    if not await engine.initialize():
        return
    
    # Open position
    if not await engine.open_position():
        Logger.error("[DNEM] Failed to open position")
        return
    
    if args.mode == "paper":
        # Paper mode: Run simulation cycles
        from src.delta_neutral.paper_engine import DeltaNeutralPaperEngine
        
        paper = DeltaNeutralPaperEngine(
            initial_balance=args.balance,
        )
        
        results = await paper.run_simulation(
            iterations=args.cycles,
            funding_rate_8h=args.rate,
        )
        
        paper.print_penny_tracker(results)
    else:
        # Live mode: Start monitoring
        Logger.info("[DNEM] Live mode - starting monitor (Ctrl+C to stop)")
        
        try:
            await engine.start_monitoring()
            
            # Keep running until interrupted
            while True:
                await asyncio.sleep(60)
                status = engine.get_status()
                Logger.info(f"[DNEM] Status: {status}")
                
        except KeyboardInterrupt:
            Logger.info("[DNEM] Interrupted by user")
        finally:
            await engine.stop()


if __name__ == "__main__":
    asyncio.run(main())
