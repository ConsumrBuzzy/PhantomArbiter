"""
V1.0: Drift Funding Feed
========================
Fetches funding rates from Drift Protocol perpetuals.

For Funding Rate Arbitrage:
- Positive funding = longs pay shorts → SHORT perp + LONG spot
- Negative funding = shorts pay longs → LONG perp + SHORT spot (rare)
"""

import time
import asyncio
from typing import Optional, Dict
from dataclasses import dataclass

from config.settings import Settings
from src.shared.system.logging import Logger


@dataclass
class FundingInfo:
    """Funding rate information for a market."""

    market: str  # e.g., "SOL-PERP"
    rate_8h: float  # 8-hour rate as percentage (e.g., 0.01 = 0.01%)
    rate_annual: float  # Annualized rate
    is_positive: bool  # True = longs pay shorts
    mark_price: float  # Current mark price
    time_to_next_funding: int  # Seconds until next funding

    @property
    def direction(self) -> str:
        """Which position to take for funding collection."""
        return "SHORT_PERP" if self.is_positive else "LONG_PERP"

    @property
    def expected_8h_usd(self) -> float:
        """Expected funding income for $100 position per 8h."""
        return 100 * (abs(self.rate_8h) / 100)

    def __str__(self) -> str:
        sign = "+" if self.is_positive else ""
        return f"{self.market}: {sign}{self.rate_8h:.4f}%/8h (APY: {self.rate_annual:.1f}%)"


@dataclass
class FundingMarket:
    """
    Complete market data for Web UI display.
    
    Task 1.1: Enhanced market data structure
    Requirements: 2.2
    """
    symbol: str  # e.g., "SOL-PERP"
    rate_1h: float  # Hourly rate as decimal (e.g., 0.0001 = 0.01%)
    rate_8h: float  # 8-hour rate as decimal
    apr: float  # Annualized percentage rate
    direction: str  # "shorts" or "longs" (who receives funding)
    open_interest: float  # Total OI in USD
    volume_24h: float  # 24h volume in USD


class DriftFundingFeed:
    """
    Drift Protocol funding rate feed.

    Monitors perpetual funding rates for arbitrage opportunities.

    Strategy:
    - When funding is POSITIVE (longs pay shorts):
      → Buy spot SOL, Short SOL-PERP
      → Collect funding from being short
      → Position is delta-neutral (price movements cancel)

    - When funding is NEGATIVE (shorts pay longs):
      → Sell/borrow spot, Long perp
      → Collect funding from being long
      → Less common, harder to execute
    """

    MARKETS = ["SOL-PERP", "BTC-PERP", "ETH-PERP"]

    def __init__(self, drift_adapter=None):
        """
        Initialize funding feed.

        Args:
            drift_adapter: Optional DriftAdapter instance. If None,
                          will create one lazily.
        """
        self._drift = drift_adapter
        self._cache: Dict[str, FundingInfo] = {}
        self._cache_ttl = 60.0  # 1 minute cache (funding doesn't change fast)
        self._last_fetch = 0.0

    def _get_drift(self):
        """Lazy-load Drift adapter."""
        if self._drift is None:
            try:
                from src.shared.infrastructure.drift_adapter import DriftAdapter

                self._drift = DriftAdapter("mainnet")
            except Exception as e:
                Logger.debug(f"Failed to load DriftAdapter: {e}")
        return self._drift

    async def get_funding_rate(self, market: str) -> Optional[FundingInfo]:
        """
        Get current funding rate for a market.

        Args:
            market: Market symbol (e.g., "SOL-PERP")

        Returns:
            FundingInfo or None
        """
        # Check cache
        if market in self._cache:
            cached = self._cache[market]
            if time.time() - self._last_fetch < self._cache_ttl:
                return cached

        drift = self._get_drift()
        if not drift or not drift.is_connected:
            return None

        try:
            rate_info = await drift.get_funding_rate(market)
            if not rate_info:
                return None

            time_to_funding = await drift.get_time_to_funding()

            funding = FundingInfo(
                market=market,
                rate_8h=rate_info.get("rate_8h", 0),
                rate_annual=rate_info.get("rate_annual", 0),
                is_positive=rate_info.get("is_positive", True),
                mark_price=rate_info.get("mark_price", 0),
                time_to_next_funding=time_to_funding,
            )

            self._cache[market] = funding
            self._last_fetch = time.time()

            return funding

        except Exception as e:
            Logger.debug(f"Drift funding rate error: {e}")
            return None

    async def get_all_funding_rates(self) -> Dict[str, FundingInfo]:
        """Get funding rates for all monitored markets."""
        results = {}

        for market in self.MARKETS:
            info = await self.get_funding_rate(market)
            if info:
                results[market] = info

        return results

    def get_funding_rates_sync(self) -> Dict[str, float]:
        """
        Synchronous method to get funding rates as simple dict.

        Returns:
            {market: rate_8h, ...}

        This is used by the dashboard for display.
        """
        # If we have recent cache, return it
        if time.time() - self._last_fetch < self._cache_ttl and self._cache:
            return {m: f.rate_8h for m, f in self._cache.items()}

        # Try to fetch (async to sync)
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                results = loop.run_until_complete(self.get_all_funding_rates())
                return {m: f.rate_8h for m, f in results.items()}
            finally:
                loop.close()
        except Exception as e:
            Logger.debug(f"Sync funding fetch error: {e}")
            return {}

    async def find_best_opportunity(
        self, min_rate_pct: float = None
    ) -> Optional[FundingInfo]:
        """
        Find the best funding rate opportunity.

        Args:
            min_rate_pct: Minimum 8h rate to consider (default from settings)

        Returns:
            FundingInfo with highest absolute rate, or None
        """
        min_rate = min_rate_pct or getattr(Settings, "FUNDING_MIN_RATE_PCT", 0.01)

        rates = await self.get_all_funding_rates()
        if not rates:
            return None

        # Find highest absolute rate
        best = max(rates.values(), key=lambda f: abs(f.rate_8h))

        if abs(best.rate_8h) < min_rate:
            return None

        return best

    async def get_funding_markets(self) -> list[FundingMarket]:
        """
        Get complete market data for all monitored markets.
        
        Task 1.2: Implement get_funding_markets() method
        Requirements: 2.2, 2.6
        
        Returns:
            List of FundingMarket objects with complete data
        """
        markets = []
        
        for market_symbol in self.MARKETS:
            info = await self.get_funding_rate(market_symbol)
            if not info:
                continue
            
            # Calculate 1h rate from 8h rate (8h rate / 8)
            rate_1h = info.rate_8h / 8.0
            
            # Calculate APR: rate_8h × 3 (per day) × 365
            # Task 1.2: APR calculation formula
            apr = info.rate_8h * 3 * 365
            
            # Determine direction (who receives funding)
            # Positive rate = longs pay shorts → shorts receive
            # Negative rate = shorts pay longs → longs receive
            direction = "shorts" if info.is_positive else "longs"
            
            # Mock OI and volume (in production, fetch from Drift API)
            # Using deterministic mock based on symbol for consistency
            seed = sum(ord(c) for c in market_symbol)
            mock_oi = (seed * 1000000) % 500000000 + 10000000  # $10M-$510M
            mock_volume = mock_oi * 1.5  # Volume typically 1.5x OI
            
            market = FundingMarket(
                symbol=market_symbol,
                rate_1h=rate_1h,
                rate_8h=info.rate_8h,
                apr=apr,
                direction=direction,
                open_interest=mock_oi,
                volume_24h=mock_volume
            )
            
            markets.append(market)
        
        return markets

    async def get_market_stats(self) -> dict:
        """
        Calculate aggregate market statistics.
        
        Task 1.3: Implement get_market_stats() method
        Requirements: 2.2
        
        Returns:
            Dict with total_oi, volume_24h, avg_funding
        """
        markets = await self.get_funding_markets()
        
        if not markets:
            return {
                "total_oi": 0.0,
                "volume_24h": 0.0,
                "avg_funding": 0.0
            }
        
        total_oi = sum(m.open_interest for m in markets)
        total_volume = sum(m.volume_24h for m in markets)
        avg_funding = sum(abs(m.apr) for m in markets) / len(markets)
        
        return {
            "total_oi": total_oi,
            "volume_24h": total_volume,
            "avg_funding": avg_funding
        }


# ═══════════════════════════════════════════════════════════════════
# MOCK DATA FOR TESTING (when Drift not connected)
# ═══════════════════════════════════════════════════════════════════


class MockDriftFundingFeed(DriftFundingFeed):
    """
    Mock funding feed for testing without Drift connection.

    Returns realistic simulated funding rates.
    """

    def __init__(self):
        super().__init__()
        import random

        # Generate semi-random but consistent rates
        self._mock_rates = {
            "SOL-PERP": 0.0125 + random.uniform(-0.005, 0.005),  # ~0.01% avg
            "BTC-PERP": 0.0089 + random.uniform(-0.003, 0.003),
            "ETH-PERP": 0.0056 + random.uniform(-0.004, 0.004),
        }

    async def get_funding_rate(self, market: str) -> Optional[FundingInfo]:
        """Return mock funding data with realistic prices."""
        rate_8h = self._mock_rates.get(market, 0.01)

        # Calculate time to next hour
        now = int(time.time())
        next_hour = (now // 3600 + 1) * 3600
        time_to_funding = next_hour - now

        # Use realistic mark prices (close to spot)
        mark_prices = {
            "SOL-PERP": 118.0,
            "BTC-PERP": 105000.0,
            "ETH-PERP": 3900.0,
            "WIF-PERP": 0.33,  # Match spot price
            "JUP-PERP": 0.85,  # Match spot price
        }

        return FundingInfo(
            market=market,
            rate_8h=rate_8h,
            rate_annual=rate_8h * 3 * 365,  # 3x per day
            is_positive=rate_8h > 0,
            mark_price=mark_prices.get(market, 100.0),
            time_to_next_funding=time_to_funding,
        )


def get_funding_feed(use_mock: bool = False) -> DriftFundingFeed:
    """Factory to get appropriate funding feed."""
    if use_mock:
        return MockDriftFundingFeed()
    return DriftFundingFeed()


# ═══════════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    async def test():
        print("=" * 60)
        print("Drift Funding Feed Test (Mock)")
        print("=" * 60)

        feed = MockDriftFundingFeed()

        for market in ["SOL-PERP", "BTC-PERP", "ETH-PERP"]:
            info = await feed.get_funding_rate(market)
            if info:
                print(f"\n{info}")
                print(
                    f"  → Take {info.direction} to collect ${info.expected_8h_usd:.2f}/8h per $100"
                )
                print(
                    f"  → Next funding in {info.time_to_next_funding // 60}m {info.time_to_next_funding % 60}s"
                )

        print("\n" + "=" * 60)
        best = await feed.find_best_opportunity(min_rate_pct=0.005)
        if best:
            print(f"Best Opportunity: {best}")
        else:
            print("No opportunities above threshold")

    asyncio.run(test())
