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
import random
import httpx
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
        
        # Try live Drift API first, fallback to mock
        funding_data = await self._fetch_live_funding()
        
        if not funding_data:
            # Use mock data if live fetch fails
            Logger.info("[WATCH] Using mock funding data (Drift API unavailable)")
            funding_data = self._get_mock_funding_data()
        
        # Build opportunities from funding data
        for market, rate_info in funding_data.items():
            if market not in self.MARKETS:
                continue
            
            spot_price = await self._get_spot_price(market)
            
            opp = MarketOpportunity(
                symbol=market,
                spot_price=spot_price,
                perp_price=spot_price * (1 + rate_info["rate_8h"] / 100),
                funding_rate_1h=rate_info["rate_1h"],
                funding_rate_8h=rate_info["rate_8h"],
            )
            self.opportunities.append(opp)
        
        # Sort by funding rate (highest first)
        self.opportunities.sort(key=lambda x: x.funding_rate_1h, reverse=True)
        
        return self.opportunities
    
    async def _fetch_live_funding(self) -> Optional[Dict]:
        """Fetch live funding rates from Drift public Data API."""
        result = {}
        
        # Map our market names to Drift API format
        market_map = {
            "SOL-PERP": "SOL",
            "BTC-PERP": "BTC",
            "ETH-PERP": "ETH",
            "JUP-PERP": "JUP",
            "PYTH-PERP": "PYTH",
            "BONK-PERP": "BONK",
            "WIF-PERP": "WIF",
        }
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                for market, drift_name in market_map.items():
                    try:
                        # Drift Data API requires marketName parameter
                        url = f"https://data.api.drift.trade/fundingRates?marketName={drift_name}"
                        
                        response = await client.get(url)
                        
                        if response.status_code == 200:
                            data = response.json()
                            
                            # Response is a list of funding records, get the LAST one (most recent)
                            records = data if isinstance(data, list) else data.get("data", data)
                            
                            if records and len(records) > 0:
                                # Last record is most recent
                                latest = records[-1]
                                
                                raw_rate = float(latest.get("fundingRate", 0))
                                oracle_twap = float(latest.get("oraclePriceTwap", 1)) or 1
                                
                                # Convert to percentage (fundingRate / oraclePriceTwap * 100)
                                # This gives hourly rate since Drift updates hourly
                                rate_1h = (raw_rate / oracle_twap) * 100
                                rate_8h = rate_1h * 8  # Estimate 8h rate
                                
                                result[market] = {
                                    "rate_8h": rate_8h,
                                    "rate_1h": rate_1h,
                                }
                                Logger.debug(f"[WATCH] {market}: {rate_1h:.4f}%/hr")
                    except Exception as e:
                        Logger.debug(f"[WATCH] Failed to fetch {market}: {e}")
                        continue
                        
            if result:
                Logger.info(f"[WATCH] ✅ Fetched LIVE funding for {len(result)} markets")
                return result
                
        except Exception as e:
            Logger.debug(f"[WATCH] Live API fetch failed: {e}")
        
        return None
    
    def _get_mock_funding_data(self) -> Dict:
        """Get mock funding data with realistic rates."""
        
        return {
            "SOL-PERP": {"rate_8h": 0.0095 + random.uniform(-0.003, 0.005), "rate_1h": 0.0012},
            "BTC-PERP": {"rate_8h": 0.0078 + random.uniform(-0.002, 0.004), "rate_1h": 0.0010},
            "ETH-PERP": {"rate_8h": 0.0065 + random.uniform(-0.002, 0.003), "rate_1h": 0.0008},
            "JUP-PERP": {"rate_8h": 0.0180 + random.uniform(-0.005, 0.010), "rate_1h": 0.0023},
            "PYTH-PERP": {"rate_8h": 0.0140 + random.uniform(-0.004, 0.008), "rate_1h": 0.0018},
            "BONK-PERP": {"rate_8h": 0.0280 + random.uniform(-0.008, 0.015), "rate_1h": 0.0035},
            "WIF-PERP": {"rate_8h": 0.0320 + random.uniform(-0.010, 0.020), "rate_1h": 0.0040},
        }
    
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
