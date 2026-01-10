"""
DNEM Paper Mode Engine
======================
Complete paper trading simulation for Delta Neutral strategy testing.

This module provides:
1. MockLatencyMonitor - Simulates network conditions
2. MockJitoAdapter - Simulates bundle submission with realistic delays
3. DeltaNeutralPaperEngine - Full paper trading coordinator

Usage:
    python -m src.delta_neutral.paper_engine --iterations 5

Expected Output:
    Penny Tracker results showing simulated funding earnings.
"""

from __future__ import annotations

import time
import random
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from src.delta_neutral.types import (
    DeltaPosition,
    RebalanceSignal,
    RebalanceDirection,
    SyncTradeBundle,
)
from src.delta_neutral.position_calculator import (
    calculate_position_size,
    build_delta_position,
    calculate_rebalance_signal,
    estimate_funding_yield,
)
from src.delta_neutral.position_snapshot import SnapshotManager, LocalSnapshotStore
from src.shared.system.logging import Logger


# =============================================================================
# MOCK ADAPTERS
# =============================================================================


class MockLatencyMonitor:
    """Simulates network latency for paper trading."""
    
    def __init__(self, base_latency_ms: float = 50.0, jitter_ms: float = 20.0):
        self.base_latency = base_latency_ms
        self.jitter = jitter_ms
        self._samples: List[float] = []
    
    def get_stats(self) -> Dict[str, float]:
        current = self.base_latency + random.uniform(-self.jitter, self.jitter)
        self._samples.append(current)
        if len(self._samples) > 100:
            self._samples = self._samples[-100:]
        
        return {
            "wss_avg_ms": sum(self._samples) / len(self._samples) if self._samples else current,
            "wss_max_ms": max(self._samples) if self._samples else current,
        }
    
    def simulate_spike(self, duration_sec: float = 2.0):
        """Simulate a latency spike (for kill-switch testing)."""
        self.base_latency = 600.0  # Above kill-switch threshold
        asyncio.get_event_loop().call_later(duration_sec, self._reset_latency)
    
    def _reset_latency(self):
        self.base_latency = 50.0


class MockJitoAdapter:
    """Simulates Jito bundle submission for paper trading."""
    
    def __init__(self, success_rate: float = 0.95):
        self.success_rate = success_rate
        self._bundles_submitted = 0
        self._bundles_landed = 0
        self._tip_accounts = [
            "96gYtjT5y4W1tL1AjddPcNLa5r1Qj6bvmVWVV7Eq5mEk",
            "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
        ]
    
    async def get_tip_accounts(self, force_refresh: bool = False) -> List[str]:
        return self._tip_accounts
    
    async def get_random_tip_account(self) -> Optional[str]:
        return random.choice(self._tip_accounts)
    
    async def is_available(self) -> bool:
        return True
    
    async def submit_bundle(
        self,
        serialized_transactions: List[str],
        simulate: bool = True,
        rpc: Any = None,
    ) -> Optional[str]:
        """Simulate bundle submission."""
        self._bundles_submitted += 1
        
        # Simulate network delay (100-400ms like real Solana)
        await asyncio.sleep(random.uniform(0.1, 0.4))
        
        # Simulate success/failure based on configured rate
        if random.random() < self.success_rate:
            bundle_id = f"PAPER_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
            Logger.info(f"[PAPER JITO] Bundle submitted: {bundle_id}")
            return bundle_id
        else:
            Logger.warning("[PAPER JITO] Bundle submission failed (simulated)")
            return None
    
    async def wait_for_confirmation(
        self,
        bundle_id: str,
        timeout: float = 30.0,
    ) -> bool:
        """Simulate bundle confirmation."""
        # Simulate confirmation delay (1-3 seconds)
        await asyncio.sleep(random.uniform(1.0, 3.0))
        
        # High success rate for landed bundles
        if random.random() < 0.98:
            self._bundles_landed += 1
            Logger.info(f"[PAPER JITO] Bundle LANDED: {bundle_id}")
            return True
        else:
            Logger.warning(f"[PAPER JITO] Bundle FAILED: {bundle_id}")
            return False
    
    def get_stats(self) -> Dict[str, int]:
        return {
            "bundles_submitted": self._bundles_submitted,
            "bundles_landed": self._bundles_landed,
        }


class MockDriftAdapter:
    """Simulates Drift perp positions for paper trading."""
    
    def __init__(self):
        self._position_size: float = 0.0
        self._entry_price: float = 0.0
        self._realized_funding: float = 0.0
    
    async def get_position(self, market: str) -> Optional[Any]:
        if abs(self._position_size) < 0.0001:
            return None
        
        @dataclass
        class MockPosition:
            size: float
            entry_price: float
            unrealized_pnl: float = 0.0
        
        return MockPosition(
            size=self._position_size,
            entry_price=self._entry_price,
        )
    
    def open_short(self, size: float, price: float):
        """Simulate opening a short position."""
        self._position_size = -abs(size)
        self._entry_price = price
        Logger.info(f"[PAPER DRIFT] Opened SHORT: {size:.4f} SOL @ ${price:.2f}")
    
    def close_short(self, size: float, price: float):
        """Simulate closing a short position."""
        closed = min(abs(size), abs(self._position_size))
        self._position_size += closed
        if abs(self._position_size) < 0.0001:
            self._position_size = 0.0
        Logger.info(f"[PAPER DRIFT] Closed SHORT: {closed:.4f} SOL @ ${price:.2f}")
    
    def accrue_funding(self, rate_8h: float, notional: float):
        """Simulate funding rate accrual."""
        # Positive rate = shorts receive funding
        funding = abs(notional) * rate_8h
        self._realized_funding += funding
        Logger.debug(f"[PAPER DRIFT] Funding accrued: ${funding:.6f}")
        return funding


class MockWallet:
    """Simulates wallet for paper trading."""
    
    def __init__(self, initial_usdc: float = 12.0, initial_sol: float = 0.0):
        self.usdc_balance = initial_usdc
        self.sol_balance = initial_sol
        self._trades: List[Dict] = []
    
    def get_sol_balance(self) -> float:
        return self.sol_balance
    
    def get_usdc_balance(self) -> float:
        return self.usdc_balance
    
    def get_public_key(self):
        from solders.pubkey import Pubkey
        # Use a dummy pubkey for paper mode
        return Pubkey.from_string("11111111111111111111111111111111")
    
    @property
    def keypair(self):
        """Return a mock keypair for signing."""
        return None  # Paper mode doesn't need real signing
    
    def buy_sol(self, usd_amount: float, price: float, slippage_pct: float = 0.1):
        """Simulate buying SOL."""
        effective_price = price * (1 + slippage_pct / 100)
        sol_amount = usd_amount / effective_price
        
        if usd_amount > self.usdc_balance:
            Logger.warning(f"[PAPER WALLET] Insufficient USDC: {self.usdc_balance:.2f}")
            return False
        
        self.usdc_balance -= usd_amount
        self.sol_balance += sol_amount
        
        self._trades.append({
            "type": "BUY",
            "sol": sol_amount,
            "usd": usd_amount,
            "price": effective_price,
            "timestamp": time.time(),
        })
        
        Logger.info(f"[PAPER WALLET] Bought {sol_amount:.4f} SOL for ${usd_amount:.2f}")
        return True
    
    def sell_sol(self, sol_amount: float, price: float, slippage_pct: float = 0.1):
        """Simulate selling SOL."""
        effective_price = price * (1 - slippage_pct / 100)
        usd_amount = sol_amount * effective_price
        
        if sol_amount > self.sol_balance:
            Logger.warning(f"[PAPER WALLET] Insufficient SOL: {self.sol_balance:.4f}")
            return False
        
        self.sol_balance -= sol_amount
        self.usdc_balance += usd_amount
        
        self._trades.append({
            "type": "SELL",
            "sol": sol_amount,
            "usd": usd_amount,
            "price": effective_price,
            "timestamp": time.time(),
        })
        
        Logger.info(f"[PAPER WALLET] Sold {sol_amount:.4f} SOL for ${usd_amount:.2f}")
        return True
    
    def get_equity(self, sol_price: float) -> float:
        """Get total equity in USD."""
        return self.usdc_balance + (self.sol_balance * sol_price)


# =============================================================================
# PAPER ENGINE
# =============================================================================


@dataclass
class PaperTradeResult:
    """Result of a single paper trade cycle."""
    
    iteration: int
    spot_qty: float
    perp_qty: float
    funding_rate_8h: float
    funding_earned: float
    execution_cost: float
    net_profit: float
    duration_ms: float
    success: bool
    
    def __repr__(self) -> str:
        status = "✅" if self.success else "❌"
        return (
            f"{status} Trade #{self.iteration}: "
            f"Spot={self.spot_qty:.4f} SOL, "
            f"Funding=${self.funding_earned:.6f}, "
            f"Cost=${self.execution_cost:.6f}, "
            f"Net=${self.net_profit:.6f}"
        )


class DeltaNeutralPaperEngine:
    """
    Complete paper trading engine for DNEM strategy testing.
    
    Simulates the full Snap-Fire-Verify loop without touching mainnet.
    
    Example:
        >>> engine = DeltaNeutralPaperEngine(initial_balance=12.0)
        >>> results = await engine.run_simulation(iterations=5, funding_rate=0.0001)
        >>> engine.print_penny_tracker(results)
    """
    
    def __init__(
        self,
        initial_balance: float = 12.0,
        leverage: float = 1.0,
        sol_price: float = 150.0,
    ):
        self.initial_balance = initial_balance
        self.leverage = leverage
        self.sol_price = sol_price
        
        # Initialize mock components
        self.wallet = MockWallet(initial_usdc=initial_balance)
        self.drift = MockDriftAdapter()
        self.jito = MockJitoAdapter()
        self.latency = MockLatencyMonitor()
        self.snapshot_manager = SnapshotManager(use_redis=False)
        
        # Statistics
        self._results: List[PaperTradeResult] = []
        self._total_funding: float = 0.0
        self._total_costs: float = 0.0
    
    async def open_delta_neutral_position(self) -> bool:
        """
        Open the initial delta-neutral position.
        
        Allocates half to spot, half to perp short.
        """
        Logger.info("=" * 60)
        Logger.info("[DNEM PAPER] Opening Delta Neutral Position")
        Logger.info("=" * 60)
        
        # Calculate position sizes
        spot_qty, perp_qty = calculate_position_size(
            total_balance_usd=self.initial_balance,
            leverage=self.leverage,
            spot_price=self.sol_price,
        )
        
        capital_per_leg = self.initial_balance / 2
        
        # Execute spot leg (buy SOL)
        if not self.wallet.buy_sol(capital_per_leg, self.sol_price):
            return False
        
        # Execute perp leg (short SOL-PERP)
        self.drift.open_short(spot_qty, self.sol_price)
        
        # Simulate execution cost
        jito_tip = 10_000 / 1_000_000_000 * self.sol_price  # 10K lamports
        dex_fee = capital_per_leg * 0.001  # 0.1% fee
        self._total_costs += jito_tip + dex_fee
        
        Logger.info(f"[DNEM PAPER] Position opened: {spot_qty:.4f} SOL spot, {perp_qty:.4f} SOL short")
        Logger.info(f"[DNEM PAPER] Execution cost: ${jito_tip + dex_fee:.6f}")
        
        return True
    
    async def simulate_funding_cycle(
        self,
        iteration: int,
        funding_rate_8h: float = 0.0001,
    ) -> PaperTradeResult:
        """
        Simulate one funding rate collection cycle.
        
        In production, this would be an 8-hour cycle.
        For testing, we compress to instant simulation.
        """
        start_time = time.time()
        
        # Get current position state
        current_sol = self.wallet.get_sol_balance()
        perp_pos = await self.drift.get_position("SOL-PERP")
        perp_size = perp_pos.size if perp_pos else 0.0
        
        # Calculate notional for funding
        notional = abs(perp_size) * self.sol_price
        
        # Accrue funding (positive rate = shorts receive)
        funding_earned = self.drift.accrue_funding(funding_rate_8h, notional)
        self._total_funding += funding_earned
        
        # Simulate small price movement for delta drift
        price_change = random.uniform(-0.5, 0.5)  # ±$0.50 per cycle
        self.sol_price += price_change
        
        # Build current position for drift check
        position = build_delta_position(
            spot_qty=current_sol,
            perp_qty=perp_size,
            spot_price=self.sol_price,
        )
        
        # Check if rebalance needed
        signal = calculate_rebalance_signal(position, self.sol_price, drift_threshold_pct=0.5)
        
        execution_cost = 0.0
        if signal:
            Logger.info(f"[DNEM PAPER] Rebalance triggered: {signal.direction.value}")
            # Simulate rebalance cost
            execution_cost = 0.0005 * self.sol_price  # Small rebalance fee
            self._total_costs += execution_cost
        
        duration_ms = (time.time() - start_time) * 1000
        net_profit = funding_earned - execution_cost
        
        result = PaperTradeResult(
            iteration=iteration,
            spot_qty=current_sol,
            perp_qty=perp_size,
            funding_rate_8h=funding_rate_8h,
            funding_earned=funding_earned,
            execution_cost=execution_cost,
            net_profit=net_profit,
            duration_ms=duration_ms,
            success=True,
        )
        
        self._results.append(result)
        return result
    
    async def run_simulation(
        self,
        iterations: int = 5,
        funding_rate_8h: float = 0.0001,
    ) -> List[PaperTradeResult]:
        """
        Run a full paper trading simulation.
        
        Args:
            iterations: Number of funding cycles to simulate
            funding_rate_8h: Simulated 8-hour funding rate
        
        Returns:
            List of trade results
        """
        Logger.info("=" * 60)
        Logger.info(f"[DNEM PAPER] Starting Simulation: {iterations} iterations")
        Logger.info(f"[DNEM PAPER] Initial Balance: ${self.initial_balance}")
        Logger.info(f"[DNEM PAPER] Funding Rate: {funding_rate_8h * 100:.4f}% per 8h")
        Logger.info("=" * 60)
        
        # Open initial position
        if not await self.open_delta_neutral_position():
            Logger.error("[DNEM PAPER] Failed to open position")
            return []
        
        # Run funding cycles
        results = []
        for i in range(1, iterations + 1):
            Logger.info(f"\n--- Cycle {i}/{iterations} ---")
            result = await self.simulate_funding_cycle(i, funding_rate_8h)
            results.append(result)
            print(result)
            
            # Small delay between cycles
            await asyncio.sleep(0.1)
        
        return results
    
    def print_penny_tracker(self, results: List[PaperTradeResult] = None):
        """Print summary of penny tracking results."""
        results = results or self._results
        
        print("\n" + "=" * 60)
        print("📊 PENNY TRACKER RESULTS")
        print("=" * 60)
        
        total_funding = sum(r.funding_earned for r in results)
        total_costs = sum(r.execution_cost for r in results)
        net_profit = total_funding - total_costs
        
        print(f"Initial Balance:     ${self.initial_balance:.2f}")
        print(f"Final Equity:        ${self.wallet.get_equity(self.sol_price):.2f}")
        print(f"Total Funding:       ${total_funding:.6f}")
        print(f"Total Costs:         ${total_costs:.6f}")
        print(f"Net Profit:          ${net_profit:.6f}")
        print(f"Profit per Hour:     ${net_profit / (len(results) * 8):.6f} (simulated)")
        
        if net_profit > 0.01:
            print("\n🎉 TARGET MET: More than $0.01 earned!")
        elif net_profit > 0:
            print(f"\n📈 On track: {net_profit / 0.01 * 100:.1f}% of penny goal")
        else:
            print("\n⚠️ Negative return - check funding rates")
        
        print("=" * 60)


# =============================================================================
# CLI ENTRY POINT
# =============================================================================


async def main():
    """Run the paper trading simulation."""
    import argparse
    
    parser = argparse.ArgumentParser(description="DNEM Paper Trading Simulation")
    parser.add_argument("--iterations", type=int, default=5, help="Number of cycles")
    parser.add_argument("--balance", type=float, default=12.0, help="Initial USDC balance")
    parser.add_argument("--rate", type=float, default=0.0001, help="Funding rate (8h)")
    parser.add_argument("--price", type=float, default=150.0, help="SOL price")
    
    args = parser.parse_args()
    
    engine = DeltaNeutralPaperEngine(
        initial_balance=args.balance,
        sol_price=args.price,
    )
    
    results = await engine.run_simulation(
        iterations=args.iterations,
        funding_rate_8h=args.rate,
    )
    
    engine.print_penny_tracker(results)


if __name__ == "__main__":
    asyncio.run(main())
