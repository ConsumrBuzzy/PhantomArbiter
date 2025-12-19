"""
V1.0: Spread Detector
=====================
Monitors price differences across DEXs to detect arbitrage opportunities.
"""

import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

from config.settings import Settings


@dataclass
class SpreadOpportunity:
    """
    Represents an arbitrage opportunity between two DEXs.
    
    A "spread" is the price difference between the best place to buy
    and the best place to sell the same asset.
    """
    pair: str                   # e.g., "SOL/USDC"
    base_mint: str              # Token being traded
    quote_mint: str             # Quote currency (usually USDC)
    
    buy_dex: str                # DEX with lowest price (buy here)
    sell_dex: str               # DEX with highest price (sell here)
    buy_price: float            # Price on buy DEX
    sell_price: float           # Price on sell DEX
    
    spread_pct: float           # (sell - buy) / buy * 100
    gross_profit_usd: float     # Profit before fees
    estimated_fees_usd: float   # Trading + gas fees
    net_profit_usd: float       # Profit after all costs
    
    max_size_usd: float         # Limited by liquidity depth
    confidence: float           # 0-1, based on price freshness
    
    timestamp: float = field(default_factory=time.time)
    
    @property
    def is_profitable(self) -> bool:
        """Is this opportunity profitable after fees?"""
        min_profit = getattr(Settings, 'MIN_PROFIT_AFTER_FEES', 0.10)
        return self.net_profit_usd >= min_profit
    
    @property
    def status(self) -> str:
        """Status indicator for dashboard."""
        if self.is_profitable and self.spread_pct >= 0.3:
            return "READY"
        elif self.spread_pct >= 0.1:
            return "MONITOR"
        else:
            return "LOW"


class SpreadDetector:
    """
    Detects price spreads across multiple DEXs.
    
    This is the core of spatial arbitrage - finding where
    to buy low and sell high across different venues.
    """
    
    def __init__(self, feeds: List = None):
        from src.arbitrage.feeds import PriceSource
        self.feeds: Dict[str, 'PriceSource'] = {}
        
        if feeds:
            for feed in feeds:
                self.feeds[feed.get_name()] = feed
                
        # Configuration
        self.min_spread_pct = getattr(Settings, 'MIN_SPREAD_PCT', 0.1)
        self.default_trade_size = getattr(Settings, 'DEFAULT_TRADE_SIZE_USD', 100.0)
        self.gas_fee_usd = 0.50  # Approximate gas in USD
        
        # Cache
        self._price_cache: Dict[str, Dict[str, float]] = {}
        self._last_scan = 0.0
        
    def add_feed(self, feed) -> None:
        """Add a price feed source."""
        self.feeds[feed.get_name()] = feed
        
    def scan_pair(
        self, 
        base_mint: str, 
        quote_mint: str,
        pair_name: str = None,
        trade_size: float = None
    ) -> Optional[SpreadOpportunity]:
        """
        Scan all DEXs for spread opportunity on a single pair.
        
        Args:
            base_mint: Token to trade
            quote_mint: Quote currency
            pair_name: Optional human-readable name (e.g., "SOL/USDC")
            trade_size: USD value to test (affects slippage)
            
        Returns:
            SpreadOpportunity if a spread exists, else None
        """
        if not self.feeds:
            return None
            
        trade_size = trade_size or self.default_trade_size
        pair_name = pair_name or f"{base_mint[:8]}/{quote_mint[:8]}"
        
        # Fetch prices from all feeds
        prices: Dict[str, float] = {}
        
        for name, feed in self.feeds.items():
            try:
                spot = feed.get_spot_price(base_mint, quote_mint)
                if spot and spot.price > 0:
                    prices[name] = spot.price
            except Exception as e:
                pass  # Skip failed feeds
                
        if len(prices) < 2:
            return None  # Need at least 2 DEXs to compare
            
        # Find best buy and sell
        sorted_prices = sorted(prices.items(), key=lambda x: x[1])
        buy_dex, buy_price = sorted_prices[0]      # Lowest price
        sell_dex, sell_price = sorted_prices[-1]   # Highest price
        
        # Calculate spread
        spread_pct = ((sell_price - buy_price) / buy_price) * 100
        
        if spread_pct < 0.01:  # Negligible spread
            return None
            
        # Estimate profitability
        gross_profit = trade_size * (spread_pct / 100)
        
        # Fees: ~0.3% round trip trading + gas
        trading_fees = trade_size * 0.003  
        total_fees = trading_fees + self.gas_fee_usd
        
        net_profit = gross_profit - total_fees
        
        return SpreadOpportunity(
            pair=pair_name,
            base_mint=base_mint,
            quote_mint=quote_mint,
            buy_dex=buy_dex,
            sell_dex=sell_dex,
            buy_price=buy_price,
            sell_price=sell_price,
            spread_pct=spread_pct,
            gross_profit_usd=gross_profit,
            estimated_fees_usd=total_fees,
            net_profit_usd=net_profit,
            max_size_usd=trade_size,
            confidence=0.9,
            timestamp=time.time()
        )
    
    def scan_all_pairs(self, pairs: List[Tuple[str, str, str]]) -> List[SpreadOpportunity]:
        """
        Scan multiple pairs for opportunities.
        
        Args:
            pairs: List of (pair_name, base_mint, quote_mint) tuples
            
        Returns:
            List of SpreadOpportunity sorted by spread_pct descending
        """
        opportunities = []
        
        for pair_name, base_mint, quote_mint in pairs:
            opp = self.scan_pair(base_mint, quote_mint, pair_name)
            if opp:
                opportunities.append(opp)
                
        return sorted(opportunities, key=lambda x: x.spread_pct, reverse=True)
    
    def get_price_matrix(self) -> Dict[str, Dict[str, float]]:
        """
        Get the current price cache as a matrix.
        
        Returns:
            {pair: {dex: price, ...}, ...}
        """
        return self._price_cache.copy()
