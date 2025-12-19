"""
Phantom Arbiter - Atomic Execution Block
=========================================
Bundle Jupiter spot buy + Drift perp short into ONE transaction.

This ensures:
- Both happen or neither happens (atomic)
- No "naked" exposure (no spot without hedge, or vice versa)
- Single signature, single confirmation

Architecture:
============
1. Get Jupiter swap instructions (USDC → SOL)
2. Get Drift short instructions (SOL-PERP)
3. Bundle into one Solana transaction
4. Send with Jito for MEV protection (optional)
"""

import asyncio
import time
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from enum import Enum

from config.settings import Settings
from src.shared.system.logging import Logger


@dataclass
class AtomicPosition:
    """Represents a delta-neutral position."""
    coin: str                    # "SOL", "WIF", "JUP"
    spot_amount: float           # Amount of spot held
    perp_amount: float           # Amount of perp short (negative)
    entry_spot_price: float
    entry_perp_price: float
    entry_time: float
    total_usd: float             # Total position value
    
    # P&L tracking
    funding_collected: float = 0.0
    unrealized_pnl: float = 0.0
    
    @property
    def is_delta_neutral(self) -> bool:
        """Check if position is approximately delta neutral."""
        if self.spot_amount == 0:
            return False
        delta = abs(self.spot_amount - abs(self.perp_amount)) / self.spot_amount
        return delta < 0.05  # Within 5%
    
    @property
    def delta_ratio(self) -> float:
        """Ratio of spot to perp (should be ~1.0)."""
        if abs(self.perp_amount) == 0:
            return float('inf')
        return self.spot_amount / abs(self.perp_amount)


class AtomicExecutor:
    """
    Executes funding rate arbitrage atomically.
    
    Steps:
    1. Calculate position sizes (50/50 split)
    2. Get Jupiter swap instructions
    3. Get Drift short instructions
    4. Bundle into single transaction
    5. Send and confirm
    """
    
    def __init__(
        self,
        wallet=None,
        jupiter=None,
        drift=None,
        jito=None,
        paper_mode: bool = True
    ):
        self.wallet = wallet
        self.jupiter = jupiter
        self.drift = drift
        self.jito = jito
        self.paper_mode = paper_mode
        
        # Active positions
        self.positions: Dict[str, AtomicPosition] = {}
        
        # Stats
        self.total_entries = 0
        self.total_exits = 0
        self.total_funding = 0.0
        
    async def execute_funding_arb(
        self,
        target_coin: str,
        amount_usd: float,
        leverage: float = 1.0
    ) -> Dict[str, Any]:
        """
        Execute funding rate arbitrage entry.
        
        This bundles:
        1. Buy spot on Jupiter (50% of budget)
        2. Open perp short on Drift (50% of budget, 1x leverage)
        
        Args:
            target_coin: "SOL", "WIF", "JUP"
            amount_usd: Total USD to deploy
            leverage: Perp leverage (1.0 = delta neutral)
            
        Returns:
            Result dict with success, position, signature
        """
        spot_amount_usd = amount_usd / 2
        perp_amount_usd = amount_usd / 2
        
        Logger.info(f"[ATOMIC] Opening {target_coin} position: ${amount_usd:.2f} total")
        Logger.info(f"         Spot: ${spot_amount_usd:.2f} | Perp Short: ${perp_amount_usd:.2f}")
        
        start_time = time.time()
        
        try:
            if self.paper_mode:
                # ═══ PAPER MODE ═══
                return await self._paper_entry(target_coin, spot_amount_usd, perp_amount_usd)
            else:
                # ═══ LIVE MODE ═══
                return await self._live_entry(target_coin, spot_amount_usd, perp_amount_usd)
                
        except Exception as e:
            Logger.error(f"[ATOMIC] Entry failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def _paper_entry(
        self, 
        coin: str, 
        spot_usd: float, 
        perp_usd: float
    ) -> Dict[str, Any]:
        """Simulate entry for paper trading."""
        
        # Get current prices
        spot_price, perp_price = await self._get_prices(coin)
        if not spot_price:
            return {"success": False, "error": "Could not get spot price"}
        
        # Calculate amounts
        spot_amount = spot_usd / spot_price
        perp_amount = perp_usd / perp_price  # This will be "short" (negative)
        
        # Simulate fees
        spot_fee = spot_usd * 0.001  # 0.1%
        perp_fee = perp_usd * 0.001  # 0.1%
        
        # Create position
        position = AtomicPosition(
            coin=coin,
            spot_amount=spot_amount,
            perp_amount=-perp_amount,  # Negative = short
            entry_spot_price=spot_price,
            entry_perp_price=perp_price,
            entry_time=time.time(),
            total_usd=spot_usd + perp_usd
        )
        
        self.positions[coin] = position
        self.total_entries += 1
        
        Logger.info(f"[ATOMIC] ✅ Paper entry complete!")
        Logger.info(f"         Spot: {spot_amount:.6f} {coin} @ ${spot_price:.2f}")
        Logger.info(f"         Perp: -{perp_amount:.6f} {coin}-PERP @ ${perp_price:.2f}")
        Logger.info(f"         Fees: ${spot_fee + perp_fee:.4f}")
        Logger.info(f"         Delta: {position.delta_ratio:.3f}x (target: 1.0)")
        
        return {
            "success": True,
            "mode": "PAPER",
            "position": position,
            "fees_paid": spot_fee + perp_fee,
            "signature": f"PAPER_{coin}_{int(time.time())}"
        }
    
    async def _live_entry(
        self, 
        coin: str, 
        spot_usd: float, 
        perp_usd: float
    ) -> Dict[str, Any]:
        """
        Execute real atomic entry.
        
        This is the CRITICAL LOGIC - bundle both instructions in one TX.
        """
        Logger.info(f"[ATOMIC] LIVE entry for {coin}...")
        
        # 1. Get Jupiter swap instructions
        Logger.info("[ATOMIC] Step 1: Get Jupiter swap instructions...")
        jupiter_ix = await self._get_jupiter_instructions(coin, spot_usd)
        if not jupiter_ix:
            return {"success": False, "error": "Failed to get Jupiter instructions"}
        
        # 2. Get Drift short instructions
        Logger.info("[ATOMIC] Step 2: Get Drift short instructions...")
        drift_ix = await self._get_drift_short_instructions(coin, perp_usd)
        if not drift_ix:
            return {"success": False, "error": "Failed to get Drift instructions"}
        
        # 3. Bundle into one transaction
        Logger.info("[ATOMIC] Step 3: Bundle instructions...")
        
        # In a real implementation, we'd use:
        # tx = Transaction()
        # tx.add(jupiter_ix)
        # tx.add(drift_ix)
        # signature = await self.wallet.send_transaction(tx)
        
        # For now, placeholder
        Logger.warning("[ATOMIC] Live execution not fully implemented yet")
        return {"success": False, "error": "Live execution not implemented"}
    
    async def _get_jupiter_instructions(
        self, 
        coin: str, 
        amount_usd: float
    ) -> Optional[Any]:
        """Get Jupiter swap instructions (USDC → coin)."""
        if not self.jupiter:
            return None
            
        # Would call: jupiter.get_swap_instructions("USDC", coin, amount_usd)
        # Returns serialized instruction to add to TX
        return None
    
    async def _get_drift_short_instructions(
        self, 
        coin: str, 
        amount_usd: float, 
        leverage: float = 1.0
    ) -> Optional[Any]:
        """Get Drift perp short instructions."""
        if not self.drift:
            return None
            
        # Would call: drift.get_short_instructions(coin, amount_usd, leverage=1)
        # Returns serialized instruction to add to TX
        return None
    
    async def _get_prices(self, coin: str) -> Tuple[Optional[float], Optional[float]]:
        """Get current spot and perp prices."""
        try:
            from src.shared.feeds.jupiter_feed import JupiterFeed
            from src.shared.feeds.drift_funding import MockDriftFundingFeed
            
            USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            MINTS = {
                "SOL": "So11111111111111111111111111111111111111112",
                "WIF": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
                "JUP": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
            }
            
            spot_feed = JupiterFeed()
            spot_price_obj = spot_feed.get_spot_price(MINTS.get(coin, ""), USDC)
            spot_price = spot_price_obj.price if spot_price_obj else None
            
            funding_feed = MockDriftFundingFeed()
            funding_info = await funding_feed.get_funding_rate(f"{coin}-PERP")
            perp_price = funding_info.mark_price if funding_info else spot_price
            
            return spot_price, perp_price
            
        except Exception as e:
            Logger.debug(f"Price fetch error: {e}")
            return None, None
    
    async def close_position(self, coin: str) -> Dict[str, Any]:
        """
        Close a delta-neutral position.
        
        Steps:
        1. Close perp short on Drift
        2. Sell spot on Jupiter
        3. Bundle into one transaction
        """
        if coin not in self.positions:
            return {"success": False, "error": "No position found"}
        
        position = self.positions[coin]
        Logger.info(f"[ATOMIC] Closing {coin} position...")
        
        if self.paper_mode:
            # Get current prices
            spot_price, perp_price = await self._get_prices(coin)
            
            # Calculate P&L
            spot_pnl = position.spot_amount * (spot_price - position.entry_spot_price)
            perp_pnl = abs(position.perp_amount) * (position.entry_perp_price - perp_price)  # Short profits when price falls
            total_pnl = spot_pnl + perp_pnl + position.funding_collected
            
            # Fees
            exit_fees = position.total_usd * 0.002  # 0.1% each side
            net_pnl = total_pnl - exit_fees
            
            Logger.info(f"[ATOMIC] ✅ Paper exit complete!")
            Logger.info(f"         Spot P&L: ${spot_pnl:+.4f}")
            Logger.info(f"         Perp P&L: ${perp_pnl:+.4f}")
            Logger.info(f"         Funding:  ${position.funding_collected:+.4f}")
            Logger.info(f"         Fees:     -${exit_fees:.4f}")
            Logger.info(f"         Net P&L:  ${net_pnl:+.4f}")
            
            del self.positions[coin]
            self.total_exits += 1
            
            return {
                "success": True,
                "mode": "PAPER",
                "net_pnl": net_pnl,
                "fees_paid": exit_fees,
                "signature": f"PAPER_EXIT_{coin}_{int(time.time())}"
            }
        else:
            return {"success": False, "error": "Live exit not implemented"}
    
    def get_position_summary(self) -> Dict[str, Any]:
        """Get summary of all positions."""
        return {
            "active_positions": len(self.positions),
            "total_entries": self.total_entries,
            "total_exits": self.total_exits,
            "total_funding_collected": self.total_funding,
            "positions": {
                coin: {
                    "spot_amount": pos.spot_amount,
                    "perp_amount": pos.perp_amount,
                    "total_usd": pos.total_usd,
                    "delta_ratio": pos.delta_ratio,
                    "is_neutral": pos.is_delta_neutral,
                    "funding_collected": pos.funding_collected,
                    "age_hours": (time.time() - pos.entry_time) / 3600
                }
                for coin, pos in self.positions.items()
            }
        }


# ═══════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    async def test():
        print("=" * 60)
        print("Atomic Executor Test (Paper Mode)")
        print("=" * 60)
        
        executor = AtomicExecutor(paper_mode=True)
        
        # Open position
        result = await executor.execute_funding_arb("SOL", 500.0)
        print(f"\nEntry result: {result['success']}")
        
        if result['success']:
            print(f"\nPosition summary:")
            print(executor.get_position_summary())
            
            # Close position
            print("\n" + "-"*40)
            close_result = await executor.close_position("SOL")
            print(f"\nExit result: {close_result}")
    
    asyncio.run(test())
