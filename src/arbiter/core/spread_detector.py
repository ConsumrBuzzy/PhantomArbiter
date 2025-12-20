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
        # For simulation: trigger on any net gain > 0
        # For live: use MIN_PROFIT_AFTER_FEES threshold
        return self.net_profit_usd > 0
    
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
        from src.shared.feeds import PriceSource
        self.feeds: Dict[str, 'PriceSource'] = {}
        
        if feeds:
            for feed in feeds:
                self.feeds[feed.get_name()] = feed
                
        # Configuration
        self.min_spread_pct = getattr(Settings, 'MIN_SPREAD_PCT', 0.1)
        self.default_trade_size = getattr(Settings, 'DEFAULT_TRADE_SIZE_USD', 100.0)
        
        # SOL price cache for gas calculation
        self._sol_price_cache = 95.0  # Default fallback
        self._sol_price_ts = 0.0
        
        # Cache
        self._price_cache: Dict[str, Dict[str, float]] = {}
        self._last_scan = 0.0
        
    def add_feed(self, feed) -> None:
        """Add a price feed source."""
        self.feeds[feed.get_name()] = feed
        
    def _get_sol_price(self) -> float:
        """Get live SOL/USD price for gas cost estimation."""
        import time
        
        # Cache for 30 seconds to avoid excessive API calls
        if time.time() - self._sol_price_ts < 30:
            return self._sol_price_cache
        
        SOL_MINT = "So11111111111111111111111111111111111111112"
        USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        
        for feed in self.feeds.values():
            try:
                spot = feed.get_spot_price(SOL_MINT, USDC_MINT)
                if spot and spot.price > 0:
                    self._sol_price_cache = spot.price
                    self._sol_price_ts = time.time()
                    return spot.price
            except:
                pass
        
        return self._sol_price_cache  # Return cached/default
        
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
            
        # Estimate profitability with ADAPTIVE fees
        gross_profit = trade_size * (spread_pct / 100)
        
        # Use centralized FeeEstimator for adaptive fees
        from src.arbiter.core.fee_estimator import get_fee_estimator
        fee_est = get_fee_estimator()
        
        # Update estimator's SOL price cache
        fee_est._sol_price_cache = self._get_sol_price()
        fee_est._sol_price_ts = time.time()
        
        fees = fee_est.estimate(
            trade_size_usd=trade_size,
            buy_dex=buy_dex,
            sell_dex=sell_dex,
            sol_price=fee_est._sol_price_cache
        )
        
        net_profit = gross_profit - fees.total_usd
        
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
            estimated_fees_usd=fees.total_usd,
            net_profit_usd=net_profit,
            max_size_usd=trade_size,
            confidence=0.9,
            timestamp=time.time()
        )
    
    def scan_all_pairs(self, pairs: List[Tuple[str, str, str]], trade_size: float = None) -> List[SpreadOpportunity]:
        """
        Scan multiple pairs for opportunities using SHARED batch price fetch.
        
        Uses src/core/data.batch_fetch_jupiter_prices which has:
        - Circuit breaker for Jupiter API
        - DexScreener fallback
        - Chunking for large batches
        
        Args:
            pairs: List of (pair_name, base_mint, quote_mint) tuples
            trade_size: USD value to test (affects slippage/fees)
            
        Returns:
            List of SpreadOpportunity sorted by spread_pct descending
        """
        import time
        from src.core.data import batch_fetch_jupiter_prices
        
        trade_size = trade_size or self.default_trade_size
        opportunities = []
        
        # Collect unique mints
        all_mints = list(set(
            base_mint for pair_name, base_mint, quote_mint in pairs
        ))
        
        # Use shared batch fetch (has circuit breaker + DexScreener fallback)
        jupiter_prices = batch_fetch_jupiter_prices(all_mints)
        
        # Also get prices from each feed for spread comparison
        feed_prices: Dict[str, Dict[str, float]] = {}
        feed_prices['JUPITER'] = jupiter_prices
        
        # Parallel fetch from other feeds
        from concurrent.futures import ThreadPoolExecutor
        
        for feed_name, feed in self.feeds.items():
            if feed_name.upper() == 'JUPITER':
                continue  # Already have Jupiter prices
            try:
                if hasattr(feed, 'get_multiple_prices'):
                    prices = feed.get_multiple_prices(all_mints)
                    if prices:
                        feed_prices[feed_name] = prices
                else:
                    # Fallback to parallel individual fetches
                    prices = {}
                    def fetch_single(mint):
                        try:
                            spot = feed.get_spot_price(mint, "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
                            return mint, spot.price if spot else 0
                        except:
                            return mint, 0
                    
                    with ThreadPoolExecutor(max_workers=10) as ex:
                        for mint, price in ex.map(fetch_single, all_mints):
                            if price > 0:
                                prices[mint] = price
                    
                    if prices:
                        feed_prices[feed_name] = prices
                        
            except Exception:
                pass
        
        if len(feed_prices) < 2:
            # Need at least 2 feeds for spread comparison
            # Fall back to sequential scan
            for pair_name, base_mint, quote_mint in pairs:
                opp = self.scan_pair(base_mint, quote_mint, pair_name, trade_size=trade_size)
                if opp:
                    opportunities.append(opp)
            return sorted(opportunities, key=lambda x: x.spread_pct, reverse=True)
        
        # Calculate spreads for each pair
        from src.arbiter.core.fee_estimator import get_fee_estimator
        fee_est = get_fee_estimator()
        fee_est._sol_price_cache = self._get_sol_price()
        fee_est._sol_price_ts = time.time()
        
        for pair_name, base_mint, quote_mint in pairs:
            # Gather prices from all feeds for this token
            prices: Dict[str, float] = {}
            for feed_name, feed_data in feed_prices.items():
                if base_mint in feed_data:
                    prices[feed_name] = feed_data[base_mint]
            
            if len(prices) < 2:
                continue
            
            # Find best buy and sell
            sorted_prices = sorted(prices.items(), key=lambda x: x[1])
            buy_dex, buy_price = sorted_prices[0]
            sell_dex, sell_price = sorted_prices[-1]
            
            spread_pct = ((sell_price - buy_price) / buy_price) * 100
            
            if spread_pct < 0.01:
                continue
            
            gross_profit = trade_size * (spread_pct / 100)
            fees = fee_est.estimate(
                trade_size_usd=trade_size,
                buy_dex=buy_dex,
                sell_dex=sell_dex,
                sol_price=fee_est._sol_price_cache
            )
            net_profit = gross_profit - fees.total_usd
            
            opportunities.append(SpreadOpportunity(
                pair=pair_name,
                base_mint=base_mint,
                quote_mint=quote_mint,
                buy_dex=buy_dex,
                sell_dex=sell_dex,
                buy_price=buy_price,
                sell_price=sell_price,
                spread_pct=spread_pct,
                gross_profit_usd=gross_profit,
                estimated_fees_usd=fees.total_usd,
                net_profit_usd=net_profit,
                max_size_usd=trade_size,
                confidence=0.9,
                timestamp=time.time()
            ))
        
        return sorted(opportunities, key=lambda x: x.spread_pct, reverse=True)
    
    def get_price_matrix(self) -> Dict[str, Dict[str, float]]:
        """
        Get the current price cache as a matrix.
        
        Returns:
            {pair: {dex: price, ...}, ...}
        """
        return self._price_cache.copy()
