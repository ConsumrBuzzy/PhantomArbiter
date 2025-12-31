"""
Arb Detector
=============
Detects arbitrage opportunities between pools and triggers execution.

Integrates:
- PoolPriceWatcher (real-time price monitoring)
- ExecutionBridge (atomic swap execution)
- Profit calculator (Jito tip optimization)

Usage:
    detector = ArbDetector()
    await detector.start()
    await detector.add_pair("SOL/USDC", meteora_pool, orca_pool)
"""

import os
import asyncio
import time
from typing import Dict, Optional
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

try:
    from src.shared.system.logging import Logger
except ImportError:

    class Logger:
        @staticmethod
        def info(msg):
            print(f"[INFO] {msg}")

        @staticmethod
        def warning(msg):
            print(f"[WARN] {msg}")

        @staticmethod
        def error(msg):
            print(f"[ERROR] {msg}")

        @staticmethod
        def success(msg):
            print(f"[OK] {msg}")

        @staticmethod
        def debug(msg):
            pass


from src.shared.execution.pool_watcher import PoolPriceWatcher, PoolPrice
from src.shared.execution.schemas import calculate_arb_strategy
from src.shared.execution.execution_bridge import ExecutionBridge


@dataclass
class ArbPair:
    """A pair of pools to monitor for arb opportunities."""

    name: str
    pool_a_address: str
    pool_a_type: str  # "meteora" or "orca"
    pool_b_address: str
    pool_b_type: str
    input_mint: str  # e.g., USDC
    output_mint: str  # e.g., SOL
    min_profit_bps: int = 10  # Minimum profit in basis points (10 = 0.1%)
    trade_amount: int = 1_000_000  # Amount to trade (in input token smallest units)
    last_check: float = 0
    arb_count: int = 0


@dataclass
class ArbOpportunity:
    """Detected arbitrage opportunity."""

    pair_name: str
    direction: str  # "A_to_B" or "B_to_A"
    pool_buy: str
    pool_sell: str
    buy_price: float
    sell_price: float
    spread_bps: int
    estimated_profit_lamports: int
    jito_tip_lamports: int
    is_viable: bool
    timestamp: float


class ArbDetector:
    """
    Detects and executes cross-DEX arbitrage opportunities.

    Features:
    - Real-time pool monitoring via WebSocket
    - Automatic profit calculation
    - Dynamic Jito tip optimization
    - Atomic execution via unified engine
    """

    def __init__(
        self,
        min_profit_bps: int = 10,
        auto_execute: bool = False,
        max_concurrent_arbs: int = 1,
    ):
        """
        Initialize the detector.

        Args:
            min_profit_bps: Minimum profit to trigger arb (10 = 0.1%)
            auto_execute: If True, automatically execute viable arbs
            max_concurrent_arbs: Max simultaneous arb executions
        """
        self.min_profit_bps = min_profit_bps
        self.auto_execute = auto_execute
        self.max_concurrent_arbs = max_concurrent_arbs

        self._watcher = PoolPriceWatcher()
        self._bridge = ExecutionBridge()
        self._pairs: Dict[str, ArbPair] = {}
        self._prices: Dict[str, float] = {}  # pool_address -> last_price
        self._running = False
        self._active_arbs = 0

        # Stats
        self._opportunities_found = 0
        self._arbs_executed = 0
        self._total_profit = 0

        # Private key
        self._private_key = os.getenv("PHANTOM_PRIVATE_KEY")

    async def start(self) -> bool:
        """Start the detector."""
        if not self._bridge.is_available():
            Logger.error(
                "[ARB] Execution engine not available. Run: cd bridges && npm run build"
            )
            return False

        if not await self._watcher.start():
            Logger.error("[ARB] Failed to start pool watcher")
            return False

        self._running = True
        Logger.info("[ARB] 🚀 Arb Detector started")
        return True

    async def stop(self):
        """Stop the detector."""
        self._running = False
        await self._watcher.stop()
        Logger.info("[ARB] Stopped")

    async def add_pair(
        self,
        name: str,
        pool_a_address: str,
        pool_a_type: str,
        pool_b_address: str,
        pool_b_type: str,
        input_mint: str,
        output_mint: str,
        trade_amount: int = 1_000_000,
        min_profit_bps: int = None,
    ) -> bool:
        """
        Add a pair of pools to monitor for arbitrage.

        Args:
            name: Human-readable pair name (e.g., "SOL/USDC")
            pool_a_address: First pool address
            pool_a_type: First pool type ("meteora" or "orca")
            pool_b_address: Second pool address
            pool_b_type: Second pool type
            input_mint: Input token mint (e.g., USDC)
            output_mint: Output token mint (e.g., SOL)
            trade_amount: Amount to trade per arb
            min_profit_bps: Min profit for this pair (overrides default)

        Returns:
            True if pair was added successfully
        """
        pair = ArbPair(
            name=name,
            pool_a_address=pool_a_address,
            pool_a_type=pool_a_type,
            pool_b_address=pool_b_address,
            pool_b_type=pool_b_type,
            input_mint=input_mint,
            output_mint=output_mint,
            trade_amount=trade_amount,
            min_profit_bps=min_profit_bps or self.min_profit_bps,
        )

        # Subscribe to both pools
        success_a = await self._watcher.add_pool(
            pool_type=pool_a_type,
            pool_address=pool_a_address,
            callback=lambda p: self._on_price_update(p, pair),
        )

        success_b = await self._watcher.add_pool(
            pool_type=pool_b_type,
            pool_address=pool_b_address,
            callback=lambda p: self._on_price_update(p, pair),
        )

        if success_a and success_b:
            self._pairs[name] = pair
            Logger.info(f"[ARB] 👁️ Monitoring pair: {name}")
            return True

        Logger.error(f"[ARB] Failed to add pair: {name}")
        return False

    async def _on_price_update(self, price: PoolPrice, pair: ArbPair):
        """Handle price update from pool watcher."""
        self._prices[price.pool_address] = price.price

        # Check for arb opportunity
        opportunity = await self._check_arb(pair)

        if opportunity and opportunity.is_viable:
            self._opportunities_found += 1
            Logger.info(
                f"[ARB] 💰 Opportunity: {pair.name} | {opportunity.spread_bps}bps spread"
            )

            if self.auto_execute and self._active_arbs < self.max_concurrent_arbs:
                asyncio.create_task(self._execute_arb(opportunity, pair))

    async def _check_arb(self, pair: ArbPair) -> Optional[ArbOpportunity]:
        """Check if there's an arb opportunity for this pair."""
        price_a = self._prices.get(pair.pool_a_address)
        price_b = self._prices.get(pair.pool_b_address)

        if not price_a or not price_b or price_a == 0 or price_b == 0:
            return None

        # Calculate spread
        # If A is cheaper, buy on A, sell on B
        # If B is cheaper, buy on B, sell on A
        spread_a_to_b = ((price_b - price_a) / price_a) * 10000  # bps
        spread_b_to_a = ((price_a - price_b) / price_b) * 10000  # bps

        if spread_a_to_b > pair.min_profit_bps:
            # Buy on A, sell on B
            estimated_profit = int(pair.trade_amount * (spread_a_to_b / 10000))
            strategy = calculate_arb_strategy(
                pair.trade_amount, pair.trade_amount + estimated_profit
            )

            return ArbOpportunity(
                pair_name=pair.name,
                direction="A_to_B",
                pool_buy=pair.pool_a_address,
                pool_sell=pair.pool_b_address,
                buy_price=price_a,
                sell_price=price_b,
                spread_bps=int(spread_a_to_b),
                estimated_profit_lamports=strategy["net_profit_lamports"],
                jito_tip_lamports=strategy["jito_tip_lamports"],
                is_viable=strategy["is_viable"],
                timestamp=time.time(),
            )

        elif spread_b_to_a > pair.min_profit_bps:
            # Buy on B, sell on A
            estimated_profit = int(pair.trade_amount * (spread_b_to_a / 10000))
            strategy = calculate_arb_strategy(
                pair.trade_amount, pair.trade_amount + estimated_profit
            )

            return ArbOpportunity(
                pair_name=pair.name,
                direction="B_to_A",
                pool_buy=pair.pool_b_address,
                pool_sell=pair.pool_a_address,
                buy_price=price_b,
                sell_price=price_a,
                spread_bps=int(spread_b_to_a),
                estimated_profit_lamports=strategy["net_profit_lamports"],
                jito_tip_lamports=strategy["jito_tip_lamports"],
                is_viable=strategy["is_viable"],
                timestamp=time.time(),
            )

        return None

    async def _execute_arb(self, opp: ArbOpportunity, pair: ArbPair):
        """Execute an arbitrage opportunity."""
        if not self._private_key:
            Logger.error("[ARB] No PHANTOM_PRIVATE_KEY in environment")
            return

        self._active_arbs += 1

        try:
            Logger.info(f"[ARB] ⚡ Executing {opp.pair_name} arb...")

            # Build legs
            buy_pool_type = (
                pair.pool_a_type if opp.direction == "A_to_B" else pair.pool_b_type
            )
            sell_pool_type = (
                pair.pool_b_type if opp.direction == "A_to_B" else pair.pool_a_type
            )

            result = self._bridge.atomic_arb(
                leg1={
                    "dex": buy_pool_type,
                    "pool": opp.pool_buy,
                    "inputMint": pair.input_mint,
                    "outputMint": pair.output_mint,
                    "amount": pair.trade_amount,
                },
                leg2={
                    "dex": sell_pool_type,
                    "pool": opp.pool_sell,
                    "inputMint": pair.output_mint,
                    "outputMint": pair.input_mint,
                    "amount": 0,  # Will be output of leg1
                },
                private_key=self._private_key,
            )

            if result.success:
                self._arbs_executed += 1
                self._total_profit += opp.estimated_profit_lamports
                Logger.success(f"[ARB] ✅ Arb executed: {result.signature}")
                pair.arb_count += 1
            else:
                Logger.error(f"[ARB] ❌ Arb failed: {result.error}")

        except Exception as e:
            Logger.error(f"[ARB] Execution error: {e}")
        finally:
            self._active_arbs -= 1

    def get_stats(self) -> dict:
        """Get detector statistics."""
        return {
            "running": self._running,
            "pairs_count": len(self._pairs),
            "opportunities_found": self._opportunities_found,
            "arbs_executed": self._arbs_executed,
            "total_profit_lamports": self._total_profit,
            "active_arbs": self._active_arbs,
        }


# ═══════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    async def main():
        print("=" * 60)
        print("Arb Detector Test")
        print("=" * 60)

        detector = ArbDetector(
            min_profit_bps=10,  # 0.1% minimum
            auto_execute=False,  # Manual mode for testing
        )

        if not await detector.start():
            print("❌ Failed to start detector")
            return

        print("\n✅ Detector running!")
        print("Stats:", detector.get_stats())

        # Wait a bit then stop
        await asyncio.sleep(5)
        await detector.stop()

        print("\n" + "=" * 60)

    asyncio.run(main())
