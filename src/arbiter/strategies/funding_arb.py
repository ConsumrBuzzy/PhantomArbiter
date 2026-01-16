"""
V1.1: Funding Rate Arbitrage Strategy
=====================================
Cash & Carry: Long spot + Short perp = Delta neutral position.

Cycle Time: 1 hour (Drift funding interval)
Turnover: 24x/day (funding paid hourly)
Target Profit: Funding rate (0.01-0.1% per 8h typically)

This is the BEST strategy for small budgets because:
1. Low fees (open position once, collect funding 24x/day)
2. No racing against bots
3. Predictable income (not speculation)

Strategy Logic:
===============
1. Monitor funding rates on Drift perpetuals
2. When rate is positive (longs pay shorts):
   - Buy spot SOL equal to half budget
   - Short SOL-PERP on Drift for same amount
   - Position is delta-neutral (price changes cancel)
   - Collect funding every hour
3. When rate turns negative or too low:
   - Close both positions
   - Wait for better opportunity
"""

import asyncio
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from config.settings import Settings
from src.shared.system.logging import Logger


class PositionState(Enum):
    """State of the funding arbitrage position."""

    IDLE = "IDLE"  # No position
    ENTERING = "ENTERING"  # Opening positions
    ACTIVE = "ACTIVE"  # Position active, collecting funding
    EXITING = "EXITING"  # Closing positions
    ERROR = "ERROR"  # Something went wrong


@dataclass
class FundingPosition:
    """Tracks an active funding arbitrage position."""

    market: str  # e.g., "SOL-PERP"
    state: PositionState = PositionState.IDLE

    # Sizes
    spot_size: float = 0.0  # Amount of spot held
    perp_size: float = 0.0  # Amount of perp short
    total_usd: float = 0.0  # Total USD value

    # Entry info
    entry_price: float = 0.0
    entry_time: float = 0.0
    entry_funding_rate: float = 0.0

    # Cumulative P&L
    funding_collected: float = 0.0
    fees_paid: float = 0.0

    @property
    def net_pnl(self) -> float:
        return self.funding_collected - self.fees_paid

    @property
    def hours_active(self) -> float:
        if self.entry_time == 0:
            return 0
        return (time.time() - self.entry_time) / 3600

    @property
    def funding_payments(self) -> int:
        """Number of funding payments received."""
        return int(self.hours_active)


@dataclass
class FundingOpportunity:
    """A funding rate arbitrage opportunity."""

    market: str  # e.g., "SOL-PERP"
    funding_rate: float  # Per 8h, as percentage
    direction: str  # "SHORT_PERP" or "LONG_PERP"
    position_size: float  # USD value
    expected_funding: float  # Expected USD income per 8h
    estimated_fees: float  # Entry + exit fees
    net_profit_8h: float  # Net expected profit per funding
    time_to_funding_sec: float  # Seconds until next funding


class FundingRateArbitrage:
    """
    Funding Rate Arbitrage using Drift Protocol.

    Strategy:
    - If funding rate is POSITIVE (shorts pay longs):
      → Long spot SOL, Short SOL-PERP on Drift
      → Collect funding from shorts

    - If funding rate is NEGATIVE (longs pay shorts):
      → Short spot SOL (or hold USDC), Long SOL-PERP on Drift
      → Collect funding from longs

    The position is "delta neutral" - price movements in spot
    are offset by opposite movements in the perp.
    """

    def __init__(self, drift_adapter=None, wallet=None, funding_feed=None):
        self.drift = drift_adapter
        self.wallet = wallet

        # Lazy-load funding feed
        self._funding_feed = funding_feed

        # Config
        self.min_rate_pct = getattr(Settings, "FUNDING_MIN_RATE_PCT", 0.01)
        self.position_size = getattr(Settings, "FUNDING_POSITION_SIZE", 250.0)

        # State
        self.positions: Dict[str, FundingPosition] = {}
        self._running = False

    def _get_funding_feed(self):
        """Lazy-load funding feed."""
        if self._funding_feed is None:
            from src.shared.feeds.drift_funding import get_funding_feed

            # Use mock if Drift not connected
            use_mock = self.drift is None or not self.drift.connected
            self._funding_feed = get_funding_feed(use_mock=use_mock)
        return self._funding_feed

    async def check_opportunity(
        self, market: str = "SOL-PERP"
    ) -> Optional[FundingOpportunity]:
        """
        Check if funding rate is favorable for arbitrage.

        Args:
            market: Perp market to check

        Returns:
            FundingOpportunity if profitable, else None
        """
        feed = self._get_funding_feed()

        try:
            funding = await feed.get_funding_rate(market)
            if not funding:
                return None

            # Check if rate is high enough
            if abs(funding.rate_8h) < self.min_rate_pct:
                Logger.debug(
                    f"[FUNDING] {market} rate {funding.rate_8h:.4f}% below min {self.min_rate_pct}%"
                )
                return None

            # Calculate expected profit
            position_size = self.position_size
            expected_funding = position_size * (abs(funding.rate_8h) / 100)

            # Estimate fees (taker fee ~0.1% round trip = 0.2%)
            entry_fee = position_size * 0.001
            exit_fee = entry_fee
            total_fees = entry_fee + exit_fee

            net_profit = expected_funding - total_fees

            # Only return if profitable
            if net_profit <= 0:
                Logger.debug(f"[FUNDING] {market} not profitable after fees")
                return None

            return FundingOpportunity(
                market=market,
                funding_rate=funding.rate_8h,
                direction=funding.direction,
                position_size=position_size,
                expected_funding=expected_funding,
                estimated_fees=total_fees,
                net_profit_8h=net_profit,
                time_to_funding_sec=funding.time_to_next_funding,
            )

        except Exception as e:
            Logger.debug(f"[FUNDING] Check error: {e}")
            return None

    async def scan_all_markets(self) -> List[FundingOpportunity]:
        """Scan all markets for funding opportunities."""
        feed = self._get_funding_feed()
        opportunities = []

        for market in feed.MARKETS:
            opp = await self.check_opportunity(market)
            if opp:
                opportunities.append(opp)

        # Sort by profit potential
        return sorted(opportunities, key=lambda o: o.net_profit_8h, reverse=True)

    async def enter_position(self, opportunity: FundingOpportunity) -> Dict[str, Any]:
        """
        Enter a delta-neutral position.

        Steps:
        1. Buy spot (or sell if going long perp)
        2. Open opposite perp position on Drift

        This should be atomic-ish (both succeed or roll back).
        """
        if not self.drift or not self.wallet:
            return {"success": False, "error": "Missing adapter or wallet"}

        market = opportunity.market
        base = market.replace("-PERP", "")  # "SOL-PERP" -> "SOL"

        # Check if we already have a position
        if (
            market in self.positions
            and self.positions[market].state == PositionState.ACTIVE
        ):
            return {"success": False, "error": "Position already exists"}

        # Create position tracker
        position = FundingPosition(
            market=market,
            state=PositionState.ENTERING,
            total_usd=opportunity.position_size,
            entry_funding_rate=opportunity.funding_rate,
        )
        self.positions[market] = position

        try:
            Logger.info(
                f"[FUNDING] Entering {market} position: ${opportunity.position_size:.2f}"
            )

            # Step 1: Get current price
            mark_price = await self.drift.get_mark_price(market)
            if not mark_price:
                raise Exception("Failed to get mark price")

            position.entry_price = mark_price
            size_base = opportunity.position_size / mark_price

            # Step 2: Buy spot (via Jupiter)
            # TODO: Implement spot purchase
            # spot_result = await self.wallet.swap_usdc_to_sol(size_base)
            Logger.info(
                f"[FUNDING] Would buy {size_base:.4f} {base} spot @ ${mark_price:.2f}"
            )
            position.spot_size = size_base
            position.fees_paid += opportunity.position_size * 0.0005  # ~0.05% swap fee

            # Step 3: Short perp
            Logger.info(f"[FUNDING] Opening SHORT: {size_base:.4f} {market}")

            if self.drift.connected:
                result = await self.drift.place_perp_order(market, "SHORT", size_base)

                if not result.get("success"):
                    raise Exception(f"Perp order failed: {result.get('error')}")

                position.perp_size = size_base
                position.fees_paid += (
                    opportunity.position_size * 0.001
                )  # 0.1% taker fee
            else:
                # Paper mode
                Logger.info("[FUNDING] Paper mode - simulated SHORT")
                position.perp_size = size_base

            # Success!
            position.state = PositionState.ACTIVE
            position.entry_time = time.time()

            Logger.info(
                f"[FUNDING] ✅ Position opened!\n"
                f"   Spot: {position.spot_size:.4f} {base}\n"
                f"   Perp: -{position.perp_size:.4f} {market}\n"
                f"   Entry: ${mark_price:.2f}\n"
                f"   Expected 8h income: ${opportunity.expected_funding:.2f}"
            )

            return {
                "success": True,
                "position": position,
                "market": market,
                "size_usd": opportunity.position_size,
            }

        except Exception as e:
            position.state = PositionState.ERROR
            Logger.error(f"[FUNDING] Entry failed: {e}")

            # TODO: Rollback (close any open positions)

            return {"success": False, "error": str(e)}

    async def exit_position(self, market: str) -> Dict[str, Any]:
        """Exit the delta-neutral position for a market."""
        if market not in self.positions:
            return {"success": False, "error": "No position found"}

        position = self.positions[market]
        if position.state != PositionState.ACTIVE:
            return {"success": False, "error": f"Position not active: {position.state}"}

        position.state = PositionState.EXITING

        try:
            base = market.replace("-PERP", "")

            Logger.info(f"[FUNDING] Exiting {market} position...")

            # Step 1: Close perp
            if self.drift and self.drift.connected:
                result = await self.drift.close_position(market)
                if not result.get("success"):
                    raise Exception(f"Close perp failed: {result.get('error')}")
            else:
                Logger.info("[FUNDING] Paper mode - simulated close")

            position.fees_paid += position.total_usd * 0.001  # Exit fee

            # Step 2: Sell spot
            # TODO: Implement spot sale
            Logger.info(f"[FUNDING] Would sell {position.spot_size:.4f} {base} spot")
            position.fees_paid += position.total_usd * 0.0005

            # Calculate final P&L
            net_pnl = position.net_pnl

            Logger.info(
                f"[FUNDING] ✅ Position closed!\n"
                f"   Duration: {position.hours_active:.1f}h\n"
                f"   Funding collected: ${position.funding_collected:.2f}\n"
                f"   Fees paid: ${position.fees_paid:.2f}\n"
                f"   Net P&L: ${net_pnl:+.2f}"
            )

            # Mark as idle
            position.state = PositionState.IDLE

            return {
                "success": True,
                "pnl": net_pnl,
                "duration_hours": position.hours_active,
                "funding_payments": position.funding_payments,
            }

        except Exception as e:
            position.state = PositionState.ERROR
            Logger.error(f"[FUNDING] Exit failed: {e}")
            return {"success": False, "error": str(e)}

    def get_active_positions(self) -> List[FundingPosition]:
        """Get list of active positions."""
        return [p for p in self.positions.values() if p.state == PositionState.ACTIVE]

    def get_position_summary(self) -> Dict[str, Any]:
        """Get summary of all positions."""
        active = self.get_active_positions()

        total_size = sum(p.total_usd for p in active)
        total_funding = sum(p.funding_collected for p in active)
        total_fees = sum(p.fees_paid for p in active)

        return {
            "active_count": len(active),
            "total_size_usd": total_size,
            "total_funding_collected": total_funding,
            "total_fees_paid": total_fees,
            "net_pnl": total_funding - total_fees,
            "positions": [
                {
                    "market": p.market,
                    "size_usd": p.total_usd,
                    "hours_active": p.hours_active,
                    "funding_collected": p.funding_collected,
                    "net_pnl": p.net_pnl,
                }
                for p in active
            ],
        }


# ═══════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    async def test():
        print("=" * 60)
        print("Funding Rate Arbitrage Test")
        print("=" * 60)

        strategy = FundingRateArbitrage()

        # Check opportunities
        print("\nScanning markets...")
        opportunities = await strategy.scan_all_markets()

        for opp in opportunities:
            print(f"\n🎯 {opp.market}")
            print(f"   Rate: +{opp.funding_rate:.4f}%/8h")
            print(f"   Direction: {opp.direction}")
            print(f"   Expected funding: ${opp.expected_funding:.2f}")
            print(f"   Fees: ${opp.estimated_fees:.2f}")
            print(f"   Net profit: ${opp.net_profit_8h:.2f}/8h")

        if not opportunities:
            print("\nNo profitable opportunities found")

    asyncio.run(test())
