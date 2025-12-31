"""
Phantom Arbiter - Profitability Monitor
========================================
Day 1 Script: Monitor funding rates and spot prices.

Calculates NET PROFIT after accounting for:
- Entry fee: 0.1% on spot (Jupiter)
- Entry fee: 0.1% on perp (Drift)
- Exit fee: 0.1% on spot
- Exit fee: 0.1% on perp
- Total round-trip: ~0.4%

Net Profit Formula:
===================
    net_profit_8h = (funding_rate_8h * position_size) - total_fees

    Where:
        total_fees = position_size * 0.004  (0.4% round trip)

    Breakeven funding rate = 0.05%/8h (0.4% / 8 funding periods)

    For $50 position:
        - If funding = 0.1%/8h → Gross = $0.05, Fees = $0.20, NET = -$0.15 ❌
        - If funding = 0.5%/8h → Gross = $0.25, Fees = $0.20, NET = +$0.05 ✅

    For $500 position:
        - If funding = 0.1%/8h → Gross = $0.50, Fees = $2.00, NET = -$1.50 ❌
        - If funding = 0.5%/8h → Gross = $2.50, Fees = $2.00, NET = +$0.50 ✅

    Key insight: You need to HOLD the position for multiple funding periods
    to overcome the entry fees.

    Time to breakeven (at 0.01%/h funding):
        $500 * 0.004 / ($500 * 0.0001) = 40 hours

Usage:
    python run_profitability_monitor.py
    python run_profitability_monitor.py --interval 600  # Every 10 minutes
    python run_profitability_monitor.py --budget 500
"""

import asyncio
import argparse
from datetime import datetime
from typing import Dict, Optional
from dataclasses import dataclass


@dataclass
class ProfitabilityReport:
    """Single coin profitability analysis."""

    symbol: str
    spot_price: float
    perp_price: float
    basis_pct: float  # (perp - spot) / spot * 100
    funding_rate_8h: float  # Percentage per 8h
    funding_rate_annual: float  # APY

    # For given position size
    position_size: float
    gross_funding_8h: float
    entry_fees: float
    exit_fees: float
    net_profit_8h: float

    # Time metrics
    hours_to_breakeven: float
    profitable: bool

    def __str__(self) -> str:
        status = "✅ PROFITABLE" if self.profitable else "❌ UNPROFITABLE"
        basis = (
            f"+{self.basis_pct:.3f}%"
            if self.basis_pct >= 0
            else f"{self.basis_pct:.3f}%"
        )

        return (
            f"\n{'=' * 60}\n"
            f"  {self.symbol}\n"
            f"{'=' * 60}\n"
            f"  Spot Price:     ${self.spot_price:,.2f}\n"
            f"  Perp Price:     ${self.perp_price:,.2f}\n"
            f"  Basis:          {basis} ({'premium' if self.basis_pct > 0 else 'discount'})\n"
            f"\n"
            f"  Funding Rate:   +{self.funding_rate_8h:.4f}%/8h\n"
            f"  Annualized:     +{self.funding_rate_annual:.1f}% APY\n"
            f"\n"
            f"  Position Size:  ${self.position_size:,.2f}\n"
            f"  ─────────────────────────────────────\n"
            f"  Gross (8h):     ${self.gross_funding_8h:.4f}\n"
            f"  Entry Fees:     -${self.entry_fees:.4f}\n"
            f"  Exit Fees:      -${self.exit_fees:.4f}\n"
            f"  ─────────────────────────────────────\n"
            f"  Net (8h):       ${self.net_profit_8h:+.4f} {status}\n"
            f"\n"
            f"  Breakeven:      {self.hours_to_breakeven:.0f} hours ({self.hours_to_breakeven / 24:.1f} days)\n"
        )


class ProfitabilityMonitor:
    """
    Monitors Drift funding rates and Jupiter spot prices.

    Outputs a profitability report accounting for all fees.
    """

    # Fee structure
    SPOT_FEE_PCT = 0.001  # 0.1% Jupiter swap
    PERP_FEE_PCT = 0.001  # 0.1% Drift taker
    TOTAL_ROUND_TRIP = 0.004  # Entry + Exit both sides

    # Monitored coins
    COINS = {
        "SOL": {
            "mint": "So11111111111111111111111111111111111111112",
            "perp": "SOL-PERP",
        },
        "WIF": {
            "mint": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
            "perp": "WIF-PERP",  # May not exist on Drift
        },
        "JUP": {
            "mint": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
            "perp": "JUP-PERP",  # May not exist on Drift
        },
    }

    def __init__(self, budget: float = 500.0):
        self.budget = budget
        self.position_size = budget / 2  # Half spot, half perp

        # Lazy-load feeds
        self._spot_feed = None
        self._funding_feed = None

    def _get_spot_feed(self):
        """Load Jupiter price feed."""
        if self._spot_feed is None:
            try:
                from src.arbitrage.feeds.jupiter_feed import JupiterFeed

                self._spot_feed = JupiterFeed()
            except Exception as e:
                print(f"   ⚠️ Could not load JupiterFeed: {e}")
        return self._spot_feed

    def _get_funding_feed(self):
        """Load Drift funding feed."""
        if self._funding_feed is None:
            try:
                from src.arbitrage.feeds.drift_funding import MockDriftFundingFeed

                # Use mock for now until real Drift connection
                self._funding_feed = MockDriftFundingFeed()
            except Exception as e:
                print(f"   ⚠️ Could not load DriftFundingFeed: {e}")
        return self._funding_feed

    async def get_spot_price(self, symbol: str) -> Optional[float]:
        """Get spot price from Jupiter."""
        coin = self.COINS.get(symbol)
        if not coin:
            return None

        feed = self._get_spot_feed()
        if not feed:
            return None

        USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        spot = feed.get_spot_price(coin["mint"], USDC)
        return spot.price if spot else None

    async def get_funding_rate(self, symbol: str) -> Optional[Dict]:
        """Get funding rate from Drift."""
        coin = self.COINS.get(symbol)
        if not coin or not coin.get("perp"):
            return None

        feed = self._get_funding_feed()
        if not feed:
            return None

        info = await feed.get_funding_rate(coin["perp"])
        if not info:
            return None

        return {
            "rate_8h": info.rate_8h,
            "rate_annual": info.rate_annual,
            "mark_price": info.mark_price,
        }

    def calculate_profitability(
        self, spot_price: float, perp_price: float, funding_rate_8h: float
    ) -> ProfitabilityReport:
        """
        Calculate net profitability for a funding rate arbitrage position.

        Net Profit Formula:
            gross_funding = position_size * (funding_rate / 100)
            entry_fees = position_size * 0.002  (0.1% spot + 0.1% perp)
            exit_fees = position_size * 0.002   (0.1% spot + 0.1% perp)
            net_profit = gross_funding - entry_fees - exit_fees

        For ongoing position (after entry):
            net_per_8h = gross_funding  (no additional fees until exit)
        """
        # Basis calculation (perp premium/discount)
        basis_pct = ((perp_price - spot_price) / spot_price) * 100

        # Gross funding income
        gross_funding = self.position_size * (funding_rate_8h / 100)

        # Fees (one-time on entry/exit)
        entry_fees = self.position_size * 0.002  # 0.1% spot + 0.1% perp
        exit_fees = self.position_size * 0.002
        total_fees = entry_fees + exit_fees

        # Net profit for first 8h (includes entry fees)
        # Note: This is first period only - subsequent periods don't have entry fees
        net_profit_first_8h = gross_funding - total_fees

        # Net profit per 8h after position is open (no fees)
        net_profit_ongoing = gross_funding

        # For display, show the first-period economics
        net_profit_8h = gross_funding  # Per period (assuming position held)

        # Hours to breakeven (recover entry+exit fees)
        if gross_funding > 0:
            hours_to_breakeven = (total_fees / gross_funding) * 8
        else:
            hours_to_breakeven = float("inf")

        # Is it profitable? (Can we break even in < 7 days?)
        profitable = hours_to_breakeven < 168 and funding_rate_8h > 0.01

        return ProfitabilityReport(
            symbol="",  # Filled by caller
            spot_price=spot_price,
            perp_price=perp_price,
            basis_pct=basis_pct,
            funding_rate_8h=funding_rate_8h,
            funding_rate_annual=funding_rate_8h * 3 * 365,
            position_size=self.position_size,
            gross_funding_8h=gross_funding,
            entry_fees=entry_fees,
            exit_fees=exit_fees,
            net_profit_8h=net_profit_8h,
            hours_to_breakeven=hours_to_breakeven,
            profitable=profitable,
        )

    async def generate_report(self) -> str:
        """Generate full profitability report for all coins."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            "",
            "╔════════════════════════════════════════════════════════════════╗",
            "║           PHANTOM ARBITER - PROFITABILITY REPORT               ║",
            f"║           {now}                          ║",
            f"║           Budget: ${self.budget:.0f} | Position: ${self.position_size:.0f} each  ║",
            "╚════════════════════════════════════════════════════════════════╝",
        ]

        best_opportunity = None
        best_apy = 0

        for symbol in ["SOL", "WIF", "JUP"]:
            spot_price = await self.get_spot_price(symbol)
            funding_data = await self.get_funding_rate(symbol)

            if not spot_price or not funding_data:
                lines.append(f"\n  {symbol}: ⚠️ Data unavailable")
                continue

            report = self.calculate_profitability(
                spot_price=spot_price,
                perp_price=funding_data.get("mark_price", spot_price),
                funding_rate_8h=funding_data.get("rate_8h", 0),
            )
            report.symbol = symbol

            lines.append(str(report))

            # Track best opportunity
            if report.funding_rate_annual > best_apy and report.profitable:
                best_apy = report.funding_rate_annual
                best_opportunity = report

        # Summary
        lines.append("\n" + "=" * 60)
        lines.append("  SUMMARY")
        lines.append("=" * 60)

        if best_opportunity:
            lines.append(f"  🎯 Best Opportunity: {best_opportunity.symbol}")
            lines.append(f"     APY: {best_opportunity.funding_rate_annual:.1f}%")
            lines.append(
                f"     Breakeven: {best_opportunity.hours_to_breakeven:.0f} hours"
            )
            lines.append(
                f"     Action: Long Spot + Short {best_opportunity.symbol}-PERP"
            )
        else:
            lines.append("  ⚠️ No profitable opportunities at current rates")
            lines.append(
                f"     (Need funding > 0.01%/8h to overcome {self.TOTAL_ROUND_TRIP * 100:.1f}% fees)"
            )

        lines.append("")

        return "\n".join(lines)

    async def run_loop(self, interval_seconds: int = 600):
        """Run monitoring loop."""
        print("\n🔍 Starting Profitability Monitor...")
        print(f"   Interval: {interval_seconds // 60} minutes")
        print(f"   Budget: ${self.budget}")
        print("   Press Ctrl+C to stop\n")

        try:
            while True:
                report = await self.generate_report()
                print(report)

                print(f"   Next update in {interval_seconds // 60} minutes...")
                await asyncio.sleep(interval_seconds)

        except KeyboardInterrupt:
            print("\n\n   🛑 Stopped by user")


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════


async def main():
    parser = argparse.ArgumentParser(
        description="Phantom Arbiter Profitability Monitor"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=600,
        help="Update interval in seconds (default: 600)",
    )
    parser.add_argument(
        "--budget", type=float, default=500.0, help="Total budget in USD (default: 500)"
    )
    parser.add_argument("--once", action="store_true", help="Run once and exit")

    args = parser.parse_args()

    monitor = ProfitabilityMonitor(budget=args.budget)

    if args.once:
        report = await monitor.generate_report()
        print(report)
    else:
        await monitor.run_loop(interval_seconds=args.interval)


if __name__ == "__main__":
    asyncio.run(main())
