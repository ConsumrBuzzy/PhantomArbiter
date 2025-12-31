"""
V1.0: The Landlord Strategy
============================
Delta-neutral yield farming on Drift Protocol.

Concept:
- When the Arbiter has idle capital in inventory, we can earn yield by:
  1. Holding spot position (already have from arb wallet)
  2. Opening short perp position on Drift (hedge)
  3. Collecting positive funding rate payments

This turns idle time into profit time.

Strategy:
- Monitor SOL-PERP funding rate on Drift
- If funding rate > threshold (longs pay shorts), open SHORT hedge
- Collect funding payments every hour
- Close hedge when arb opportunity appears

Safety:
- Only hedge a % of inventory (default 50%)
- Auto-close if funding flips negative
- Position sizing based on collateral
"""

import asyncio
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

from src.shared.system.logging import Logger


class HedgeState(Enum):
    """State of the delta-neutral hedge."""

    IDLE = "IDLE"  # No hedge, waiting for opportunity
    HEDGED = "HEDGED"  # Delta-neutral position active
    CLOSING = "CLOSING"  # Closing hedge for arb execution
    COOLDOWN = "COOLDOWN"  # Just closed, cooling down


@dataclass
class FundingSnapshot:
    """Snapshot of funding rate conditions."""

    market: str
    rate_hourly: float  # Hourly funding rate (%)
    rate_annual: float  # Annualized rate (%)
    is_positive: bool  # True = longs pay shorts (good for us)
    mark_price: float
    timestamp: float


@dataclass
class LandlordPosition:
    """Current Landlord hedge position."""

    symbol: str
    size: float  # Size in base asset (negative = short)
    entry_price: float
    current_price: float
    unrealized_pnl: float
    funding_collected: float
    opened_at: float


class Landlord:
    """
    Delta-neutral yield farming strategy.

    Earns funding rate yield on idle inventory by shorting perps on Drift.
    """

    # Default thresholds
    MIN_FUNDING_RATE_HOURLY = 0.005  # 0.5% hourly = ~43% APY threshold
    MAX_HEDGE_RATIO = 0.5  # Hedge max 50% of inventory
    MIN_HEDGE_SIZE_USD = 10.0  # Minimum position size
    COOLDOWN_SECONDS = 300  # 5 min cooldown after closing

    def __init__(
        self,
        drift_adapter=None,
        wallet_manager=None,
        telegram=None,
        min_funding_rate: float = None,
        hedge_ratio: float = None,
    ):
        self.drift = drift_adapter
        self.wallet = wallet_manager
        self.telegram = telegram

        # Config
        self.min_funding_rate = min_funding_rate or self.MIN_FUNDING_RATE_HOURLY
        self.hedge_ratio = hedge_ratio or self.MAX_HEDGE_RATIO

        # State
        self.state = HedgeState.IDLE
        self.position: Optional[LandlordPosition] = None
        self.last_close_time: float = 0
        self.total_funding_earned: float = 0.0

        # Stats
        self.hedges_opened = 0
        self.hedges_closed = 0

    async def initialize(self) -> bool:
        """Initialize Landlord with Drift connection."""
        if not self.drift:
            try:
                from src.shared.infrastructure.drift_adapter import DriftAdapter

                self.drift = DriftAdapter("mainnet")
                await self.drift.connect()
            except Exception as e:
                Logger.error(f"[LANDLORD] Failed to init Drift: {e}")
                return False

        # Verify account
        result = await self.drift.verify_drift_account()
        if not result.get("ready"):
            Logger.warning(f"[LANDLORD] Drift not ready: {result.get('message')}")
            return False

        collateral = result.get("collateral", 0)
        Logger.info(f"[LANDLORD] ✅ Initialized | Collateral: ${collateral:.2f}")
        return True

    async def get_funding_snapshot(
        self, symbol: str = "SOL-PERP"
    ) -> Optional[FundingSnapshot]:
        """Get current funding rate conditions."""
        if not self.drift:
            return None

        funding = await self.drift.get_funding_rate(symbol)
        if not funding:
            return None

        return FundingSnapshot(
            market=symbol,
            rate_hourly=funding.get("rate_hourly", 0),
            rate_annual=funding.get("rate_annual", 0),
            is_positive=funding.get("is_positive", False),
            mark_price=funding.get("mark_price", 0),
            timestamp=time.time(),
        )

    async def should_hedge(self, inventory_value_usd: float) -> tuple[bool, str]:
        """
        Determine if we should open a hedge.

        Returns: (should_hedge, reason)
        """
        # Check cooldown
        if self.state == HedgeState.COOLDOWN:
            elapsed = time.time() - self.last_close_time
            if elapsed < self.COOLDOWN_SECONDS:
                return False, f"Cooldown ({int(self.COOLDOWN_SECONDS - elapsed)}s left)"

        # Check if already hedged
        if self.state == HedgeState.HEDGED:
            return False, "Already hedged"

        # Check inventory
        if inventory_value_usd < self.MIN_HEDGE_SIZE_USD:
            return False, f"Inventory too small (${inventory_value_usd:.2f})"

        # Check funding rate
        funding = await self.get_funding_snapshot()
        if not funding:
            return False, "Cannot fetch funding rate"

        if not funding.is_positive:
            return False, f"Negative funding ({funding.rate_hourly:.3f}%/h)"

        if funding.rate_hourly < self.min_funding_rate:
            return (
                False,
                f"Low funding ({funding.rate_hourly:.3f}%/h < {self.min_funding_rate:.3f}%)",
            )

        # All conditions met
        hedge_size = inventory_value_usd * self.hedge_ratio
        annual_yield = funding.rate_annual
        return True, f"✅ Hedge ${hedge_size:.2f} @ {annual_yield:.1f}% APY"

    async def open_hedge(self, inventory_value_usd: float) -> Dict[str, Any]:
        """
        Open delta-neutral hedge position.

        Opens a SHORT perp position to hedge spot inventory.
        """
        result = {"success": False, "error": None, "position": None}

        # Calculate size
        hedge_value = inventory_value_usd * self.hedge_ratio

        # Get current price for size calculation
        funding = await self.get_funding_snapshot()
        if not funding or funding.mark_price <= 0:
            result["error"] = "Cannot get mark price"
            return result

        # Size in SOL (base asset)
        size_base = hedge_value / funding.mark_price

        Logger.info(
            f"[LANDLORD] 📉 Opening SHORT hedge: {size_base:.4f} SOL @ ${funding.mark_price:.2f}"
        )

        try:
            # Place SHORT order
            order_result = await self.drift.place_perp_order(
                symbol="SOL-PERP", direction="SHORT", size=size_base
            )

            if not order_result.get("success"):
                result["error"] = order_result.get("error", "Order failed")
                return result

            # Update state
            self.position = LandlordPosition(
                symbol="SOL-PERP",
                size=-size_base,  # Negative = short
                entry_price=funding.mark_price,
                current_price=funding.mark_price,
                unrealized_pnl=0.0,
                funding_collected=0.0,
                opened_at=time.time(),
            )
            self.state = HedgeState.HEDGED
            self.hedges_opened += 1

            result["success"] = True
            result["position"] = self.position
            result["signature"] = order_result.get("signature")

            Logger.info(
                f"[LANDLORD] ✅ Hedge opened: {order_result.get('signature', '')[:16]}..."
            )

            # Telegram alert
            if self.telegram:
                msg = (
                    f"🏠 <b>LANDLORD HEDGE OPENED</b>\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"• Size: {abs(size_base):.4f} SOL SHORT\n"
                    f"• Entry: ${funding.mark_price:.2f}\n"
                    f"• APY: {funding.rate_annual:.1f}%\n"
                )
                self.telegram.send_alert(msg)

            return result

        except Exception as e:
            result["error"] = str(e)
            Logger.error(f"[LANDLORD] Hedge failed: {e}")
            return result

    async def close_hedge(self, reason: str = "Manual") -> Dict[str, Any]:
        """Close the current hedge position."""
        result = {"success": False, "error": None, "pnl": 0.0}

        if self.state != HedgeState.HEDGED or not self.position:
            result["error"] = "No active hedge"
            return result

        Logger.info(f"[LANDLORD] 📈 Closing hedge: {reason}")

        try:
            self.state = HedgeState.CLOSING

            # Close position on Drift
            close_result = await self.drift.close_position("SOL-PERP")

            if not close_result.get("success"):
                result["error"] = close_result.get("error", "Close failed")
                self.state = HedgeState.HEDGED  # Revert state
                return result

            # Calculate PnL
            final_funding = self.position.funding_collected
            self.total_funding_earned += final_funding

            result["success"] = True
            result["pnl"] = final_funding
            result["signature"] = close_result.get("signature")

            # Update state
            self.hedges_closed += 1
            self.last_close_time = time.time()
            self.state = HedgeState.COOLDOWN

            Logger.info(
                f"[LANDLORD] ✅ Hedge closed | Funding earned: ${final_funding:.4f}"
            )

            # Reset position
            self.position = None

            # Telegram alert
            if self.telegram:
                msg = (
                    f"🏠 <b>LANDLORD HEDGE CLOSED</b>\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"• Reason: {reason}\n"
                    f"• Funding Earned: ${final_funding:.4f}\n"
                    f"• Total Earned: ${self.total_funding_earned:.4f}\n"
                )
                self.telegram.send_alert(msg)

            return result

        except Exception as e:
            result["error"] = str(e)
            self.state = HedgeState.HEDGED  # Revert state
            Logger.error(f"[LANDLORD] Close failed: {e}")
            return result

    async def tick(
        self, inventory_value_usd: float, arb_opportunity: bool = False
    ) -> Dict[str, Any]:
        """
        Main loop tick - called by Arbiter each cycle.

        Manages hedge lifecycle based on conditions.

        Args:
            inventory_value_usd: Current spot inventory value
            arb_opportunity: True if there's an arb to execute (close hedge first)

        Returns:
            Dict with action taken and status
        """
        result = {"action": None, "status": self.state.value}

        # If arb opportunity, close hedge first
        if arb_opportunity and self.state == HedgeState.HEDGED:
            close_result = await self.close_hedge("Arb Opportunity")
            result["action"] = "CLOSE_FOR_ARB"
            result["close_result"] = close_result
            return result

        # If not hedged, check if we should open
        if self.state in [HedgeState.IDLE, HedgeState.COOLDOWN]:
            should, reason = await self.should_hedge(inventory_value_usd)

            if should:
                open_result = await self.open_hedge(inventory_value_usd)
                result["action"] = "OPEN_HEDGE"
                result["open_result"] = open_result
            else:
                result["action"] = "WAIT"
                result["reason"] = reason

            return result

        # If hedged, monitor and update
        if self.state == HedgeState.HEDGED and self.position:
            # Check if funding flipped negative
            funding = await self.get_funding_snapshot()
            if funding and not funding.is_positive:
                close_result = await self.close_hedge("Funding Flipped Negative")
                result["action"] = "CLOSE_NEGATIVE_FUNDING"
                result["close_result"] = close_result
                return result

            # Update position info
            if funding:
                self.position.current_price = funding.mark_price
                # Crude PnL estimate (funding only, ignoring price movement since delta-neutral)
                hours_open = (time.time() - self.position.opened_at) / 3600
                self.position.funding_collected = (
                    abs(self.position.size) * funding.rate_hourly / 100 * hours_open
                )

            result["action"] = "MONITOR"
            result["position"] = {
                "size": self.position.size,
                "entry": self.position.entry_price,
                "current": self.position.current_price,
                "funding_earned": self.position.funding_collected,
            }

        return result

    def get_status(self) -> Dict[str, Any]:
        """Get current Landlord status."""
        return {
            "state": self.state.value,
            "hedges_opened": self.hedges_opened,
            "hedges_closed": self.hedges_closed,
            "total_funding_earned": self.total_funding_earned,
            "position": {
                "symbol": self.position.symbol if self.position else None,
                "size": self.position.size if self.position else 0,
                "entry_price": self.position.entry_price if self.position else 0,
                "funding_collected": self.position.funding_collected
                if self.position
                else 0,
            }
            if self.position
            else None,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    async def test_landlord():
        print("=" * 60)
        print("Landlord Strategy Test")
        print("=" * 60)

        landlord = Landlord()

        # Initialize
        print("\n1. Initializing Landlord...")
        success = await landlord.initialize()
        print(f"   Init: {'✅' if success else '❌'}")

        if not success:
            print("   Cannot proceed without Drift connection")
            return

        # Get funding rate
        print("\n2. Fetching SOL-PERP funding rate...")
        funding = await landlord.get_funding_snapshot()
        if funding:
            print(f"   Rate: {funding.rate_hourly:.4f}%/hour")
            print(f"   Annual: {funding.rate_annual:.1f}%")
            print(
                f"   Direction: {'Longs pay Shorts ✅' if funding.is_positive else 'Shorts pay Longs'}"
            )
            print(f"   Price: ${funding.mark_price:.2f}")

        # Test hedge check
        print("\n3. Should we hedge $100 inventory?")
        should, reason = await landlord.should_hedge(100.0)
        print(f"   Result: {reason}")

        print("\n" + "=" * 60)
        print("Test complete!")

    asyncio.run(test_landlord())
