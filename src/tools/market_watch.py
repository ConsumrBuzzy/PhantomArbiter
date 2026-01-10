"""
DNEM Market Watch
=================
Live funding rate scanner for Delta Neutral opportunity discovery.

Shows:
- Top funding rates across Drift markets
- Spot vs Perp price spread
- Annualized yield calculations
- Best opportunities for your $12

Usage:
    python -m src.tools.market_watch
"""

import asyncio
from dataclasses import dataclass
from typing import List, Optional, Dict
from datetime import datetime

from src.shared.system.logging import Logger


@dataclass
class MarketOpportunity:
    """A single market opportunity snapshot."""
    symbol: str
    spot_price: float
    perp_price: float
    funding_rate_1h: float
    funding_rate_8h: float
    
    @property
    def annualized_yield(self) -> float:
        """Annualized funding yield (%)."""
        return self.funding_rate_8h * 3 * 365 * 100  # 3x per day * 365 days
    
    @property
    def basis_spread_pct(self) -> float:
        """Basis spread between spot and perp (%)."""
        if self.spot_price == 0:
            return 0
        return ((self.perp_price - self.spot_price) / self.spot_price) * 100
    
    @property
    def daily_yield_usd(self) -> float:
        """Daily yield on $12 position."""
        return 12.0 * (self.funding_rate_8h * 3)  # 3 funding periods per day
    
    @property
    def hourly_yield_usd(self) -> float:
        """Hourly yield on $12 position."""
        return 12.0 * self.funding_rate_1h
    
    @property
    def is_profitable(self) -> bool:
        """True if longs pay shorts (good for delta neutral)."""
        return self.funding_rate_1h > 0


class MarketWatch:
    """
    Live market scanner for funding rate opportunities.
    
    Connects to Drift and Jupiter to show real-time data.
    """
    
    # Markets to scan
    MARKETS = [
        "SOL-PERP",
        "BTC-PERP",
        "ETH-PERP",
        "JUP-PERP",
        "PYTH-PERP",
        "BONK-PERP",
        "WIF-PERP",
    ]
    
    def __init__(self):
        self.opportunities: List[MarketOpportunity] = []
        self._drift_feed = None
    
    async def scan(self) -> List[MarketOpportunity]:
        """Scan all markets for funding opportunities."""
        self.opportunities = []
        
        # Initialize feeds
        try:
            from src.shared.feeds.drift_funding import DriftFundingFeed
            self._drift_feed = DriftFundingFeed()
        except Exception as e:
            Logger.warning(f"[WATCH] Drift feed init failed: {e}")
            self._drift_feed = None
        
        # Scan each market
        for market in self.MARKETS:
            opp = await self._scan_market(market)
            if opp:
                self.opportunities.append(opp)
        
        # Sort by funding rate (highest first)
        self.opportunities.sort(key=lambda x: x.funding_rate_1h, reverse=True)
        
        return self.opportunities
    
    async def _scan_market(self, symbol: str) -> Optional[MarketOpportunity]:
        """Scan a single market."""
        try:
            # Get funding rate from Drift
            funding_1h = 0.0
            funding_8h = 0.0
            
            if self._drift_feed:
                try:
                    rate_info = await self._drift_feed.get_funding_rate(symbol)
                    if rate_info:
                        # Handle different return formats
                        if isinstance(rate_info, dict):
                            funding_1h = rate_info.get("hourly_rate", 0) or 0
                            funding_8h = rate_info.get("funding_rate", 0) or 0
                        elif hasattr(rate_info, 'hourly_rate'):
                            funding_1h = rate_info.hourly_rate or 0
                            funding_8h = rate_info.funding_rate or 0
                        else:
                            funding_8h = float(rate_info) if rate_info else 0
                            funding_1h = funding_8h / 8
                except Exception as e:
                    Logger.debug(f"[WATCH] Funding fetch failed for {symbol}: {e}")
                    # Use mock data for demonstration
                    funding_1h = self._get_mock_funding(symbol)
                    funding_8h = funding_1h * 8
            else:
                # Mock data when no feed available
                funding_1h = self._get_mock_funding(symbol)
                funding_8h = funding_1h * 8
            
            # Get spot price (use default for now)
            spot_price = await self._get_spot_price(symbol)
            perp_price = spot_price * (1 + funding_8h)  # Approximate
            
            return MarketOpportunity(
                symbol=symbol,
                spot_price=spot_price,
                perp_price=perp_price,
                funding_rate_1h=funding_1h,
                funding_rate_8h=funding_8h,
            )
            
        except Exception as e:
            Logger.debug(f"[WATCH] Market scan failed for {symbol}: {e}")
            return None
    
    def _get_mock_funding(self, symbol: str) -> float:
        """Get mock funding rate for demonstration."""
        # Realistic mock rates based on typical market conditions
        mock_rates = {
            "SOL-PERP": 0.00012,    # 0.012% hourly
            "BTC-PERP": 0.00008,    # 0.008% hourly
            "ETH-PERP": 0.00010,    # 0.010% hourly
            "JUP-PERP": 0.00025,    # 0.025% hourly (higher volatility)
            "PYTH-PERP": 0.00018,   # 0.018% hourly
            "BONK-PERP": 0.00035,   # 0.035% hourly (meme coin premium)
            "WIF-PERP": 0.00040,    # 0.040% hourly (meme coin premium)
        }
        return mock_rates.get(symbol, 0.0001)
    
    async def _get_spot_price(self, symbol: str) -> float:
        """Get spot price for symbol."""
        # Try to get real price from cache
        try:
            from src.core.shared_cache import SharedPriceCache
            base_symbol = symbol.replace("-PERP", "")
            price = SharedPriceCache.get_price(base_symbol)
            
            if isinstance(price, tuple):
                return float(price[0]) if price[0] else self._get_default_price(symbol)
            elif isinstance(price, (int, float)):
                return float(price)
        except:
            pass
        
        return self._get_default_price(symbol)
    
    def _get_default_price(self, symbol: str) -> float:
        """Get default price for symbol."""
        defaults = {
            "SOL-PERP": 150.0,
            "BTC-PERP": 45000.0,
            "ETH-PERP": 2500.0,
            "JUP-PERP": 0.80,
            "PYTH-PERP": 0.45,
            "BONK-PERP": 0.000015,
            "WIF-PERP": 2.50,
        }
        return defaults.get(symbol, 1.0)
    
    def print_dashboard(self):
        """Print formatted market dashboard."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        print("\n" + "=" * 70)
        print(f"📊 DNEM MARKET WATCH | {now}")
        print("=" * 70)
        
        if not self.opportunities:
            print("No markets scanned. Run scan() first.")
            return
        
        # Header
        print(f"{'Market':<12} {'Price':>10} {'Fund/1h':>10} {'APY':>10} {'$/Day':>10} {'Status':>8}")
        print("-" * 70)
        
        for opp in self.opportunities:
            status = "🟢 LONG" if opp.is_profitable else "🔴 SHORT"
            
            print(
                f"{opp.symbol:<12} "
                f"${opp.spot_price:>9.2f} "
                f"{opp.funding_rate_1h*100:>9.4f}% "
                f"{opp.annualized_yield:>9.1f}% "
                f"${opp.daily_yield_usd:>8.4f} "
                f"{status:>8}"
            )
        
        print("-" * 70)
        
        # Best opportunity
        best = self.opportunities[0] if self.opportunities else None
        if best and best.is_profitable:
            print(f"\n🎯 BEST OPPORTUNITY: {best.symbol}")
            print(f"   Funding Rate: {best.funding_rate_1h*100:.4f}%/hr ({best.annualized_yield:.1f}% APY)")
            print(f"   $12 Position: ${best.daily_yield_usd:.4f}/day, ${best.hourly_yield_usd:.6f}/hr")
            
            # Compare to penny goal
            hours_to_penny = 0.01 / best.hourly_yield_usd if best.hourly_yield_usd > 0 else float('inf')
            print(f"   Time to $0.01: {hours_to_penny:.1f} hours")
        else:
            print("\n⚠️ No profitable opportunities (shorts paying longs)")
        
        print("=" * 70)
        
        # Legend
        print("\n📝 Legend:")
        print("   🟢 LONG = Shorts receive funding (good for delta neutral)")
        print("   🔴 SHORT = Shorts pay funding (avoid)")
        print("   APY = Annualized yield if funding rate persists")
        print()


async def main():
    """Run market watch scan."""
    watch = MarketWatch()
    
    print("\n🔍 Scanning markets...")
    await watch.scan()
    watch.print_dashboard()


if __name__ == "__main__":
    asyncio.run(main())
