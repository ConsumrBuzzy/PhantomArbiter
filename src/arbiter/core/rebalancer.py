"""
Phantom Arbiter - Rebalancing Engine
=====================================
The "Brain" that keeps positions delta-neutral.

Problem:
========
If SOL goes up 20%, your Spot is now worth $30 and your Short is worth $20.
You are no longer "Neutral" - exposed to price risk.

Solution:
=========
Every hour, check the balance. If difference is > 5%, rebalance:
- If Spot > Perp: Sell some spot, add to short margin
- If Perp > Spot: Close some short, buy more spot

This keeps the hedge tight and prevents runaway losses.
"""

import asyncio
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from config.settings import Settings
from src.shared.system.logging import Logger


@dataclass
class RebalanceAction:
    """Describes a rebalancing action to take."""
    coin: str
    action: str                  # "SELL_SPOT", "BUY_SPOT", "ADD_SHORT", "CLOSE_SHORT"
    amount_usd: float
    reason: str
    current_delta: float
    target_delta: float = 1.0


class RebalancingEngine:
    """
    Monitors positions and rebalances when delta drifts too far.
    
    Configuration:
    - check_interval: How often to check (default: 1 hour)
    - max_delta_drift: Maximum deviation before rebalance (default: 5%)
    - min_rebalance_usd: Minimum trade size worth rebalancing (default: $5)
    """
    
    def __init__(
        self,
        atomic_executor=None,
        check_interval: int = 3600,      # 1 hour
        max_delta_drift: float = 0.05,   # 5%
        min_rebalance_usd: float = 5.0
    ):
        self.executor = atomic_executor
        self.check_interval = check_interval
        self.max_delta_drift = max_delta_drift
        self.min_rebalance_usd = min_rebalance_usd
        
        # State
        self.last_check = 0.0
        self.rebalances_performed = 0
        self.total_rebalance_volume = 0.0
        
        # Running flag
        self._running = False
        
    async def check_and_rebalance(self, position) -> Optional[RebalanceAction]:
        """
        Check a single position and rebalance if needed.
        
        Args:
            position: AtomicPosition to check
            
        Returns:
            RebalanceAction if rebalance needed, else None
        """
        # Get current values
        spot_price, perp_price = await self._get_prices(position.coin)
        if not spot_price:
            return None
        
        # Calculate current USD values
        spot_value = position.spot_amount * spot_price
        perp_value = abs(position.perp_amount) * perp_price
        total_value = spot_value + perp_value
        
        # Calculate delta
        if total_value == 0:
            return None
            
        spot_weight = spot_value / total_value
        perp_weight = perp_value / total_value
        
        # Target is 50/50
        target_weight = 0.5
        delta_drift = abs(spot_weight - target_weight)
        
        Logger.debug(f"[REBAL] {position.coin}: Spot {spot_weight*100:.1f}% / Perp {perp_weight*100:.1f}% | Drift: {delta_drift*100:.1f}%")
        
        # Check if rebalance needed
        if delta_drift <= self.max_delta_drift:
            return None  # Within tolerance
        
        # Calculate rebalance amount
        imbalance_usd = (spot_weight - target_weight) * total_value
        
        if abs(imbalance_usd) < self.min_rebalance_usd:
            Logger.debug(f"[REBAL] Imbalance ${imbalance_usd:.2f} below min ${self.min_rebalance_usd}")
            return None
        
        # Determine action
        if spot_weight > target_weight:
            # Spot heavy - sell spot, add to short
            action = RebalanceAction(
                coin=position.coin,
                action="SELL_SPOT_ADD_SHORT",
                amount_usd=abs(imbalance_usd),
                reason=f"Spot heavy ({spot_weight*100:.1f}% vs 50% target)",
                current_delta=spot_weight / perp_weight if perp_weight > 0 else float('inf')
            )
        else:
            # Perp heavy - close some short, buy spot
            action = RebalanceAction(
                coin=position.coin,
                action="CLOSE_SHORT_BUY_SPOT",
                amount_usd=abs(imbalance_usd),
                reason=f"Perp heavy ({perp_weight*100:.1f}% vs 50% target)",
                current_delta=spot_weight / perp_weight if perp_weight > 0 else 0
            )
        
        Logger.info(f"[REBAL] 🔄 Rebalance needed: {action.action}")
        Logger.info(f"         Amount: ${action.amount_usd:.2f}")
        Logger.info(f"         Reason: {action.reason}")
        
        return action
    
    async def execute_rebalance(self, action: RebalanceAction) -> Dict[str, Any]:
        """Execute a rebalancing action."""
        Logger.info(f"[REBAL] Executing {action.action} for ${action.amount_usd:.2f}...")
        
        if not self.executor:
            return {"success": False, "error": "No executor configured"}
        
        # In paper mode or real mode, we'd do:
        # 1. Sell/buy spot on Jupiter
        # 2. Adjust perp position on Drift
        
        # For now, just log it
        self.rebalances_performed += 1
        self.total_rebalance_volume += action.amount_usd
        
        Logger.info(f"[REBAL] ✅ Rebalance complete (simulated)")
        
        return {
            "success": True,
            "action": action.action,
            "amount": action.amount_usd,
            "fees_estimated": action.amount_usd * 0.002  # 0.2% round trip
        }
    
    async def check_all_positions(self) -> List[RebalanceAction]:
        """Check all active positions for rebalancing needs."""
        if not self.executor:
            return []
        
        actions = []
        for coin, position in self.executor.positions.items():
            action = await self.check_and_rebalance(position)
            if action:
                actions.append(action)
        
        self.last_check = time.time()
        return actions
    
    async def run_loop(self, auto_execute: bool = False):
        """
        Run continuous rebalancing loop.
        
        Args:
            auto_execute: If True, automatically execute rebalances
        """
        self._running = True
        Logger.info(f"[REBAL] Starting rebalancing loop (interval: {self.check_interval//60} min)")
        
        while self._running:
            try:
                actions = await self.check_all_positions()
                
                if actions:
                    for action in actions:
                        if auto_execute:
                            await self.execute_rebalance(action)
                        else:
                            Logger.info(f"[REBAL] Would rebalance: {action}")
                else:
                    Logger.debug(f"[REBAL] All positions within tolerance")
                
                await asyncio.sleep(self.check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                Logger.error(f"[REBAL] Loop error: {e}")
                await asyncio.sleep(60)  # Wait and retry
        
        Logger.info("[REBAL] Rebalancing loop stopped")
    
    def stop(self):
        """Stop the rebalancing loop."""
        self._running = False
    
    async def _get_prices(self, coin: str) -> tuple:
        """Get current prices."""
        try:
            from src.arbitrage.feeds.jupiter_feed import JupiterFeed
            from src.arbitrage.feeds.drift_funding import MockDriftFundingFeed
            
            USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            MINTS = {
                "SOL": "So11111111111111111111111111111111111111112",
                "WIF": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
            }
            
            spot_feed = JupiterFeed()
            spot = spot_feed.get_spot_price(MINTS.get(coin, ""), USDC)
            spot_price = spot.price if spot else None
            
            funding_feed = MockDriftFundingFeed()
            info = await funding_feed.get_funding_rate(f"{coin}-PERP")
            perp_price = info.mark_price if info else spot_price
            
            return spot_price, perp_price
        except Exception as e:
            Logger.debug(f"Price fetch error: {e}")
            return None, None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get rebalancing statistics."""
        return {
            "rebalances_performed": self.rebalances_performed,
            "total_rebalance_volume": self.total_rebalance_volume,
            "check_interval_sec": self.check_interval,
            "max_delta_drift_pct": self.max_delta_drift * 100,
            "min_rebalance_usd": self.min_rebalance_usd,
            "last_check": self.last_check
        }


# ═══════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from src.arbiter.core.atomic_executor import AtomicExecutor, AtomicPosition
    
    async def test():
        print("=" * 60)
        print("Rebalancing Engine Test")
        print("=" * 60)
        
        # Create mock position with imbalance
        executor = AtomicExecutor(paper_mode=True)
        
        # Simulate a position that has drifted
        # Spot went up, so spot value > perp value
        position = AtomicPosition(
            coin="SOL",
            spot_amount=2.0,        # 2 SOL
            perp_amount=-1.5,       # Short 1.5 SOL (less than spot = imbalance)
            entry_spot_price=100.0,
            entry_perp_price=100.0,
            entry_time=time.time() - 3600,  # 1 hour ago
            total_usd=400.0
        )
        executor.positions["SOL"] = position
        
        # Check for rebalance
        rebalancer = RebalancingEngine(
            atomic_executor=executor,
            check_interval=60,
            max_delta_drift=0.05
        )
        
        print(f"\nPosition: {position.spot_amount} SOL spot, {position.perp_amount} SOL-PERP")
        print(f"Delta ratio: {position.delta_ratio:.2f}x (target: 1.0)")
        
        actions = await rebalancer.check_all_positions()
        
        if actions:
            print(f"\n🔄 Rebalance needed!")
            for action in actions:
                print(f"   Action: {action.action}")
                print(f"   Amount: ${action.amount_usd:.2f}")
                print(f"   Reason: {action.reason}")
        else:
            print(f"\n✅ Position within tolerance")
    
    asyncio.run(test())
